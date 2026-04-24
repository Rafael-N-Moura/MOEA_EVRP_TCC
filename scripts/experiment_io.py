"""
experiment_io.py
================
Módulo de I/O para o experimento principal do TCC — EVRPTW tri-objetivo.

Implementa a estrutura formal de output descrita em output_formal.md:
  - ConvergenceCallback : captura snapshots durante a otimização
  - compute_pareto_front: extrai front viável não-dominada (F e X)
  - build_instance_info : constrói dict de info da instância
  - build_run_result    : monta o dicionário completo do run
  - save_run            : salva pickle + linha no index.csv
  - load_run            : carrega pickle
  - compute_hv_quick    : HV com ref_point local (para inspeção rápida)

Uso típico (em um worker process):
    from scripts.experiment_io import (
        ConvergenceCallback, build_instance_info,
        build_run_result, save_run, CSV_FIELDS,
    )

    cb  = ConvergenceCallback(interval=10_000)
    res = minimize(problem, alg, ("n_eval", 600_000),
                   callback=cb, verbose=False, seed=seed)

    result = build_run_result(
        metadata={...},
        config={...},
        instance_info=build_instance_info(ctx),
        pymoo_result=res,
        callback=cb,
        elapsed=elapsed,
    )
    pkl_rel, csv_row = save_run(result, experiment_dir)
"""

import os
import subprocess
import pickle
import csv

import numpy as np
from pymoo.core.callback import Callback

# ─────────────────────────────────────────────────────────────────────────────
# CSV index structure
# ─────────────────────────────────────────────────────────────────────────────

CSV_FIELDS = [
    "algorithm_id", "instance", "run_idx", "seed",
    "n_evals_budget", "n_evals_actual",
    "n_feasible", "n_pareto",
    "hv_quick", "igd_plus_quick",
    "best_f1", "best_f2", "best_f3",
    "n_f1_layers",
    "elapsed_seconds", "timestamp_start", "timestamp_end",
    "status", "pickle_path",
    "git_commit",
]


# ─────────────────────────────────────────────────────────────────────────────
# Callback de convergência
# ─────────────────────────────────────────────────────────────────────────────

class ConvergenceCallback(Callback):
    """
    Captura snapshots da frente de Pareto viável a cada `interval` avaliações.

    Cada snapshot é um dict com:
        n_eval    : int   — avaliações acumuladas
        n_feasible: int   — soluções viáveis na população
        F_pareto  : ndarray (n_nd, 3) — frente não-dominada viável (objetivos)
        best_f1   : float — mínimo f1 na frente
        best_f2   : float — mínimo f2 na frente
        best_f3   : float — mínimo f3 na frente

    Nota: não armazenamos X no histórico para manter tamanho do pickle razoável.
    O X completo está em final_population.
    """

    def __init__(self, interval: int = 10_000):
        super().__init__()
        self.interval  = interval
        self._next     = interval
        self.history   = []

    def notify(self, algorithm):
        n_eval = algorithm.evaluator.n_eval
        if n_eval < self._next:
            return
        self._next += self.interval

        cv_arr = algorithm.pop.get("_cv")
        F_real = algorithm.pop.get("_F_real")

        # Fallbacks robustos para MOEA/D, que pode não propagar os atributos
        # customizados (_cv, _F_real) da mesma forma que NSGA-II/SMS-EMOA
        # dependendo da versão do pymoo.
        if cv_arr is None:
            cv_arr = algorithm.pop.get("CV")
        if F_real is None:
            F_real = algorithm.pop.get("F")

        # Se ainda None após fallbacks, registra snapshot vazio mas não aborta
        if cv_arr is None or F_real is None:
            self.history.append({
                "n_eval":     int(n_eval),
                "n_feasible": 0,
                "F_pareto":   np.empty((0, 3)),
                "best_f1":    float("nan"),
                "best_f2":    float("nan"),
                "best_f3":    float("nan"),
            })
            return

        mask   = cv_arr[:, 0] <= 1e-9
        n_feas = int(mask.sum())
        F_feas = F_real[mask] if n_feas > 0 else np.empty((0, 3))
        F_nd   = _non_dominated(F_feas) if n_feas > 0 else F_feas

        snap = {
            "n_eval":     int(n_eval),
            "n_feasible": n_feas,
            "F_pareto":   F_nd.copy(),
        }
        if len(F_nd) > 0:
            snap["best_f1"] = float(F_nd[:, 0].min())
            snap["best_f2"] = float(F_nd[:, 1].min())
            snap["best_f3"] = float(F_nd[:, 2].min())
        else:
            snap["best_f1"] = snap["best_f2"] = snap["best_f3"] = float("nan")

        self.history.append(snap)


# ─────────────────────────────────────────────────────────────────────────────
# Utilitários internos
# ─────────────────────────────────────────────────────────────────────────────

def _non_dominated(F: np.ndarray) -> np.ndarray:
    """
    Filtra soluções não-dominadas de F (minimização, shape n×k).
    Usa O(n²) — aceitável para n ≤ 200.
    """
    n = len(F)
    if n == 0:
        return F
    dominated = np.zeros(n, dtype=bool)
    for i in range(n):
        if dominated[i]:
            continue
        for j in range(n):
            if i == j or dominated[j]:
                continue
            # j domina i?
            if np.all(F[j] <= F[i]) and np.any(F[j] < F[i]):
                dominated[i] = True
                break
    return F[~dominated]


def _non_dominated_with_index(F: np.ndarray):
    """
    Retorna (F_nd, idx_nd): frente não-dominada e índices correspondentes.
    """
    n = len(F)
    if n == 0:
        return F, np.array([], dtype=int)
    dominated = np.zeros(n, dtype=bool)
    for i in range(n):
        if dominated[i]:
            continue
        for j in range(n):
            if i == j or dominated[j]:
                continue
            if np.all(F[j] <= F[i]) and np.any(F[j] < F[i]):
                dominated[i] = True
                break
    idx = np.where(~dominated)[0]
    return F[idx], idx


# ─────────────────────────────────────────────────────────────────────────────
# Funções públicas
# ─────────────────────────────────────────────────────────────────────────────

def get_git_commit(repo_path: str = None) -> str:
    """Retorna o hash curto do commit atual (7 chars) ou 'unknown'."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_path or os.getcwd(),
            capture_output=True, text=True, timeout=5,
        )
        commit = r.stdout.strip()
        return commit if commit else "unknown"
    except Exception:
        return "unknown"


def compute_pareto_front(F: np.ndarray, CV: np.ndarray, X: np.ndarray):
    """
    Extrai a frente de Pareto viável (cv=0) não-dominada da população.

    Args:
        F  : (pop_size, 3)          — objetivos (penalizados)
        CV : (pop_size, 1) ou (pop_size,) — constraint violation
        X  : (pop_size, n_customers) — permutações

    Returns:
        F_pareto : (n_nd, 3)
        X_pareto : (n_nd, n_customers)
    """
    cv_1d = CV[:, 0] if CV.ndim == 2 else CV
    mask  = cv_1d <= 1e-9
    n_feas = int(mask.sum())

    n_cust = X.shape[1]
    empty_F = np.empty((0, 3))
    empty_X = np.empty((0, n_cust), dtype=int)

    if n_feas == 0:
        return empty_F, empty_X

    # Usa F_real se disponível; aqui F already contains F_real from caller
    F_feas = F[mask]
    X_feas = X[mask]

    F_nd, idx_nd = _non_dominated_with_index(F_feas)
    return F_nd, X_feas[idx_nd]


def build_instance_info(ctx) -> dict:
    """
    Constrói o dict de info da instância a partir do Context.

    Campos:
        n_customers, n_stations, depot_horizon,
        Q (battery_capacity), C (vehicle_capacity),
        r (consumption_rate), g (recharge_rate), v (velocity),
        tw_ratio (mean TW width / horizon, over customers)
    """
    horizon = float(ctx.all_nodes[ctx.depot_idx].due_date)

    cust_nodes = [ctx.all_nodes[i] for i in ctx.customer_node_indices]
    tw_widths  = [nd.due_date - nd.ready_time for nd in cust_nodes]
    tw_ratio   = float(np.mean(tw_widths) / horizon) if horizon > 0 else float("nan")

    return {
        "n_customers":   ctx.n_customers,
        "n_stations":    len(ctx.stations),
        "depot_horizon": horizon,
        "Q":             float(ctx.battery_capacity),
        "C":             float(ctx.vehicle_capacity),
        "r":             float(ctx.consumption_rate),
        "g":             float(ctx.recharge_rate),
        "v":             float(ctx.velocity),
        "tw_ratio":      round(tw_ratio, 4),
    }


def compute_hv_quick(F_pareto: np.ndarray) -> float:
    """
    HV com ref_point local = 1.1 × max(F_pareto, axis=0).
    Apenas para inspeção rápida. Valores oficiais são recalculados
    em pós-análise com ref_point consistente por instância.
    """
    from pymoo.indicators.hv import HV
    if len(F_pareto) == 0:
        return 0.0
    ref_point = F_pareto.max(axis=0) * 1.1
    if np.any(ref_point <= 0):
        return 0.0
    try:
        return float(HV(ref_point=ref_point)(F_pareto))
    except Exception:
        return 0.0


def build_run_result(
    metadata: dict,
    config: dict,
    instance_info: dict,
    pymoo_result,
    callback: ConvergenceCallback,
    elapsed: float,
) -> dict:
    """
    Monta o dicionário completo do run, conforme a spec de output_formal.md.

    Args:
        metadata       : campos de identificação/controle do run
        config         : parâmetros do algoritmo
        instance_info  : dict retornado por build_instance_info()
        pymoo_result   : objeto retornado por pymoo.optimize.minimize()
        callback       : ConvergenceCallback já populado pelo minimize()
        elapsed        : tempo de execução em segundos

    Returns:
        dict com chaves: metadata, config, instance_info,
                         final_population, pareto_front, convergence_history
    """
    from datetime import datetime

    res = pymoo_result
    pop = res.pop

    # Extrai arrays da população
    F_all  = pop.get("_F_real")   # objetivos reais (sem penalidade)
    CV_all = pop.get("_cv")       # constraint violation (n_pop, 1)
    X_all  = pop.get("X")         # permutações (n_pop, n_cust)

    if F_all is None:
        F_all = pop.get("F")      # fallback: objetivos penalizados

    n_pop = len(F_all) if F_all is not None else 0

    # Frente de Pareto: viáveis não-dominadas
    if F_all is not None and CV_all is not None and X_all is not None and n_pop > 0:
        F_pareto, X_pareto = compute_pareto_front(F_all, CV_all, X_all)
    else:
        n_cust = metadata.get("n_customers", 100)
        F_pareto = np.empty((0, 3))
        X_pareto = np.empty((0, n_cust), dtype=int)

    # Atualiza metadata
    ts_end = datetime.now().isoformat(timespec="seconds")
    actual_evals = (res.algorithm.evaluator.n_eval
                    if hasattr(res, "algorithm") else metadata.get("n_evals_budget", 0))

    metadata.update({
        "n_evals_actual": actual_evals,
        "timestamp_end":  ts_end,
        "elapsed_seconds": round(elapsed, 3),
        "status":          "ok",
    })

    return {
        "metadata": metadata,
        "config":   config,
        "instance_info": instance_info,
        "final_population": {
            "F":  F_all.copy()  if F_all  is not None else np.empty((0, 3)),
            "CV": CV_all.copy() if CV_all is not None else np.empty((0, 1)),
            "X":  X_all.copy()  if X_all  is not None else np.empty((0, 0), dtype=int),
        },
        "pareto_front": {
            "F": F_pareto,
            "X": X_pareto,
        },
        "convergence_history": callback.history,
    }


def save_run(result: dict, experiment_dir: str,
             index_csv_path: str = None) -> tuple:
    """
    Salva o resultado de um run:
      - pickle em {experiment_dir}/pickles/{alg}/{instance}/run{idx:02d}.pkl
      - retorna (pkl_rel_path, csv_row_dict) para que o caller salve no index.csv

    Args:
        result         : dict retornado por build_run_result()
        experiment_dir : raiz do experimento (results/main_experiment/)
        index_csv_path : se fornecido, escreve/appenda linha no index CSV

    Returns:
        (pkl_relative_path, csv_row_dict)
    """
    meta = result["metadata"]
    alg  = meta["algorithm_id"]
    inst = meta["instance"]
    ridx = meta["run_idx"]

    # Diretório e caminho do pickle
    pkl_dir  = os.path.join(experiment_dir, "pickles", alg, inst)
    os.makedirs(pkl_dir, exist_ok=True)
    pkl_name = f"run{ridx:02d}.pkl"
    pkl_abs  = os.path.join(pkl_dir, pkl_name)
    pkl_rel  = os.path.relpath(pkl_abs, experiment_dir)

    # Injeta o path no metadata
    result["metadata"]["pickle_path"] = pkl_rel

    # Salva pickle
    with open(pkl_abs, "wb") as f:
        pickle.dump(result, f, protocol=4)

    # Monta linha do CSV
    F_p  = result["pareto_front"]["F"]
    CV   = result["final_population"]["CV"]
    cv_1d = CV[:, 0] if CV.ndim == 2 and len(CV) > 0 else CV
    n_feas = int((cv_1d <= 1e-9).sum()) if len(cv_1d) > 0 else 0
    n_nd   = len(F_p)
    hv_q   = compute_hv_quick(F_p)
    f1_layers = int(len(np.unique(F_p[:, 0]))) if n_nd > 0 else 0

    csv_row = {
        "algorithm_id":    alg,
        "instance":        inst,
        "run_idx":         ridx,
        "seed":            meta.get("seed", ""),
        "n_evals_budget":  meta.get("n_evals_budget", ""),
        "n_evals_actual":  meta.get("n_evals_actual", ""),
        "n_feasible":      n_feas,
        "n_pareto":        n_nd,
        "hv_quick":        round(hv_q, 6),
        "igd_plus_quick":  "",   # calculado em pós-análise
        "best_f1":         float(F_p[:, 0].min()) if n_nd > 0 else "",
        "best_f2":         round(float(F_p[:, 1].min()), 4) if n_nd > 0 else "",
        "best_f3":         round(float(F_p[:, 2].min()), 4) if n_nd > 0 else "",
        "n_f1_layers":     f1_layers,
        "elapsed_seconds": meta.get("elapsed_seconds", ""),
        "timestamp_start": meta.get("timestamp_start", ""),
        "timestamp_end":   meta.get("timestamp_end", ""),
        "status":          meta.get("status", "ok"),
        "pickle_path":     pkl_rel,
        "git_commit":      meta.get("git_commit", "unknown"),
    }

    # Escreve no index CSV se fornecido
    if index_csv_path is not None:
        new_file = not os.path.exists(index_csv_path)
        with open(index_csv_path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if new_file:
                w.writeheader()
            w.writerow(csv_row)

    return pkl_rel, csv_row


def load_run(pkl_path: str) -> dict:
    """Carrega um run result de um arquivo pickle."""
    with open(pkl_path, "rb") as f:
        return pickle.load(f)


def mark_run_error(index_csv_path: str, algorithm_id: str,
                   instance: str, run_idx: int, seed: int,
                   error_msg: str, **extra) -> dict:
    """
    Registra um run com erro no index CSV.
    Garante que runs com falha fiquem rastreáveis.
    """
    from datetime import datetime
    csv_row = {k: "" for k in CSV_FIELDS}
    csv_row.update({
        "algorithm_id": algorithm_id,
        "instance":     instance,
        "run_idx":      run_idx,
        "seed":         seed,
        "status":       f"error: {error_msg[:120]}",
        "timestamp_end": datetime.now().isoformat(timespec="seconds"),
        **{k: v for k, v in extra.items() if k in CSV_FIELDS},
    })
    new_file = not os.path.exists(index_csv_path)
    with open(index_csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(csv_row)
    return csv_row
