#!/usr/bin/env python3
"""
stopping_criterion.py
======================
Calibra formalmente o critério de parada do experimento principal.

Implementa o procedimento descrito em paralelizacao_e_parada.md:

  Fase 1 — Calibração ampla (90 runs):
    6 instâncias representativas (uma por célula tipo × série):
      c101_21  (C-1xx), c201_21  (C-2xx)
      r101_21  (R-1xx), r201_21  (R-2xx)
      rc101_21 (RC-1xx), rc201_21 (RC-2xx)
    3 algoritmos (nsga2, moead_ws, smsemoa) × 5 runs
    Orçamento: 1.000.000 avaliações OU 60 minutos por run (o que vier primeiro)
    Snapshot de HV a cada 10.000 avaliações

  Fase 2 — Identificação de N* por (algoritmo, instância):
    HV mediano sobre os 5 runs em cada snapshot
    Critério: janela móvel de 50k evals, threshold ε=1%,
              3 pontos consecutivos abaixo do threshold

  Fase 3 — Agregação:
    N*_global = max(N*) × 1.2, arredondado para múltiplo de 10.000

Outputs:
  1. stopping_criterion_report.md   — N* oficial + justificativa para o TCC
  2. stopping_criterion_analysis.csv — tabela N* por (algo, inst)
  3. preliminary_comparison.csv     — HV mediano final por (algo, inst)
  4. convergence_curves/            — dados de curva HV para plots

Os 90 runs usam a mesma estrutura de pickle do experimento principal
(experiment_io.py), reutilizando todo o código de análise.

Uso:
  # Rodar calibração completa (recomendado com tmux no servidor):
  python scripts/stopping_criterion.py 2>&1 | tee stopping_criterion.log

  # Dry-run (1 run, 5k evals — verifica o pipeline):
  python scripts/stopping_criterion.py --dry-run

  # Só análise (dados já rodados):
  python scripts/stopping_criterion.py --analyze-only --results-dir results/stopping_criterion_...

  # Ajustar limite de tempo (padrão: 3600s = 60min):
  python scripts/stopping_criterion.py --max-seconds 1800   # 30 min

Tmux:
  tmux new -s stopping
  python scripts/stopping_criterion.py 2>&1 | tee stopping_criterion.log
  Ctrl+B D
  tail -f stopping_criterion.log
"""

# Threading constraint ANTES de qualquer import numpy
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("BLIS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import sys, time, csv, json, pickle, hashlib, random, argparse, warnings, traceback
from typing import Optional
from datetime import datetime
from multiprocessing import Pool

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import numpy as np

from experiment_io import (
    ConvergenceCallback, build_instance_info, build_run_result,
    save_run, mark_run_error, get_git_commit, CSV_FIELDS,
)

# ─────────────────────────────────────────────────────────────────────────────
# Parâmetros do experimento de calibração
# ─────────────────────────────────────────────────────────────────────────────

N_EVALS_MAX  = 1_000_000   # hard cap (tempo vai vencer antes no servidor)
MAX_SECONDS  = 3_600       # 60 minutos por run
N_WORKERS    = 10
N_RUNS_CALIB = 5
CONV_INTERVAL = 10_000     # snapshot a cada 10k → 100 snapshots em 1M

# Janela para critério de estabilidade
WINDOW_EVALS  = 50_000     # = 5 snapshots
EPS_THRESHOLD = 0.01       # 1%
N_CONSECUTIVE = 3          # 3 pontos consecutivos abaixo do threshold

# Margem de segurança e arredondamento
SAFETY_MARGIN  = 1.20      # +20%
ROUND_TO       = 10_000    # múltiplo de 10k

# 6 instâncias representativas (uma por combinação tipo × série)
CALIB_INSTANCES = {
    "c101_21":  os.path.join(ROOT, "evrptw_instances", "c101_21.txt"),   # C-1xx
    "c201_21":  os.path.join(ROOT, "evrptw_instances", "c201_21.txt"),   # C-2xx
    "r101_21":  os.path.join(ROOT, "evrptw_instances", "r101_21.txt"),   # R-1xx
    "r201_21":  os.path.join(ROOT, "evrptw_instances", "r201_21.txt"),   # R-2xx
    "rc101_21": os.path.join(ROOT, "evrptw_instances", "rc101_21.txt"),  # RC-1xx
    "rc201_21": os.path.join(ROOT, "evrptw_instances", "rc201_21.txt"),  # RC-2xx
}

# Pop sizes — 105 para os três (valor natural de Das-Dennis com H=13, 3 objetivos).
# NSGA-II e SMS-EMOA usam 105 para igualar o MOEA/D e garantir comparação justa.
POP_SIZES = {"nsga2": 105, "moead_ws": 105, "smsemoa": 105}

ALGORITHM_CONFIGS = {
    "nsga2":    {"pop_size": 105, "crossover": "OrderCrossover(prob=0.9)",
                 "mutation": "InversionMutation()", "eliminate_duplicates": True},
    "moead_ws": {"pop_size": 105, "n_neighbors": 10, "prob_neighbor_mating": 0.9,
                 "decomposition": "weighted-sum", "crossover": "OrderCrossover(prob=0.9)",
                 "mutation": "InversionMutation()", "ref_dirs": "das-dennis(n_partitions=13)"},
    "smsemoa":  {"pop_size": 105, "crossover": "OrderCrossover(prob=0.9)",
                 "mutation": "InversionMutation()", "eliminate_duplicates": True},
}


# ─────────────────────────────────────────────────────────────────────────────
# Callback com limite de tempo
# ─────────────────────────────────────────────────────────────────────────────

class TimeLimitedConvergenceCallback(ConvergenceCallback):
    """
    ConvergenceCallback estendido com limite de tempo.

    Quando `max_seconds` é atingido, força a parada do algoritmo
    incrementando artificialmente o contador de avaliações para além
    do orçamento máximo. O n_eval real é salvo antes do incremento.
    """

    def __init__(self, interval: int = 10_000,
                 max_seconds: float = 3_600,
                 max_evals: int = 1_000_000):
        super().__init__(interval=interval)
        self.max_seconds    = max_seconds
        self.max_evals      = max_evals
        self._wall_start    = None
        self.stopped_by_time = False
        self.actual_evals_at_stop = None

    def notify(self, algorithm):
        if self._wall_start is None:
            self._wall_start = time.perf_counter()

        # Registra o snapshot normalmente
        super().notify(algorithm)

        # Verifica limite de tempo
        elapsed = time.perf_counter() - self._wall_start
        if (not self.stopped_by_time) and (elapsed >= self.max_seconds):
            self.stopped_by_time = True
            self.actual_evals_at_stop = algorithm.evaluator.n_eval
            # Força parada: pymoo checa n_eval >= max_evals para terminar
            algorithm.evaluator.n_eval = self.max_evals + 1


# ─────────────────────────────────────────────────────────────────────────────
# Construtores de algoritmo (espelho de main_experiment.py)
# ─────────────────────────────────────────────────────────────────────────────

def _get_ref_dirs():
    try:
        from pymoo.util.ref_dirs import get_reference_directions
    except ImportError:
        from pymoo.util.reference_direction import get_reference_directions
    return get_reference_directions("das-dennis", 3, n_partitions=13)


def _build_algorithm(algorithm_id: str):
    from pymoo.operators.crossover.ox import OrderCrossover
    from pymoo.operators.mutation.inversion import InversionMutation
    from src import TWBiasedSampling

    ops = dict(sampling=TWBiasedSampling(),
               crossover=OrderCrossover(),
               mutation=InversionMutation())

    if algorithm_id == "nsga2":
        from pymoo.algorithms.moo.nsga2 import NSGA2
        return NSGA2(pop_size=105, eliminate_duplicates=True, **ops)
    elif algorithm_id == "moead_ws":
        from pymoo.algorithms.moo.moead import MOEAD
        from pymoo.decomposition.weighted_sum import WeightedSum
        return MOEAD(ref_dirs=_get_ref_dirs(), n_neighbors=10,
                     prob_neighbor_mating=0.9, decomposition=WeightedSum(), **ops)
    elif algorithm_id == "smsemoa":
        from pymoo.algorithms.moo.sms import SMSEMOA
        return SMSEMOA(pop_size=105, eliminate_duplicates=True, **ops)
    raise ValueError(f"Algoritmo desconhecido: {algorithm_id!r}")


def _seed(alg_id: str, inst: str, run_idx: int) -> int:
    key = f"calib_{alg_id}_{inst}_{run_idx}"
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2 ** 32)


# ─────────────────────────────────────────────────────────────────────────────
# Worker
# ─────────────────────────────────────────────────────────────────────────────

def run_task(task: dict) -> dict:
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, "scripts"))

    alg_id    = task["algorithm_id"]
    inst_name = task["instance"]
    inst_path = task["inst_path"]
    run_idx   = task["run_idx"]
    seed      = task["seed"]
    n_evals   = task["n_evals"]
    max_sec   = task["max_seconds"]
    exp_dir   = task["experiment_dir"]
    idx_csv   = task["index_csv"]
    git_cmt   = task["git_commit"]
    interval  = task.get("conv_interval", CONV_INTERVAL)

    summary = dict(algorithm_id=alg_id, instance=inst_name, run_idx=run_idx,
                   seed=seed, n_feasible=0, n_pareto=0, hv_quick=0.0,
                   elapsed_s=0.0, status="error", error_msg="",
                   stopped_by_time=False, actual_evals=0)

    try:
        from pymoo.optimize import minimize
        from src import parse_instance, EVRPTWProblem
        from experiment_io import build_instance_info, build_run_result, save_run

        ctx     = parse_instance(inst_path)
        problem = EVRPTWProblem(ctx, k_max=0)
        alg     = _build_algorithm(alg_id)
        cb      = TimeLimitedConvergenceCallback(
                      interval=interval, max_seconds=max_sec, max_evals=n_evals)

        ts_start = datetime.now().isoformat(timespec="seconds")
        t0 = time.perf_counter()
        res = minimize(problem, alg, ("n_eval", n_evals),
                       callback=cb, verbose=False, seed=seed)
        elapsed = time.perf_counter() - t0

        # n_evals real (antes de eventual fake para encerrar por tempo)
        actual_evals = (cb.actual_evals_at_stop if cb.stopped_by_time
                        else res.algorithm.evaluator.n_eval)

        metadata = dict(
            algorithm_id=alg_id, instance=inst_name, run_idx=run_idx,
            seed=seed, n_evals_budget=n_evals, pop_size=POP_SIZES[alg_id],
            timestamp_start=ts_start, git_commit=git_cmt,
            n_customers=ctx.n_customers,
            stopped_by_time=cb.stopped_by_time,
        )

        result = build_run_result(
            metadata=metadata,
            config=ALGORITHM_CONFIGS[alg_id].copy(),
            instance_info=build_instance_info(ctx),
            pymoo_result=res,
            callback=cb,
            elapsed=elapsed,
        )
        # Corrige n_evals_actual para o valor real (não o fake)
        result["metadata"]["n_evals_actual"] = actual_evals

        pkl_rel, csv_row = save_run(result, exp_dir, idx_csv)

        summary.update(dict(
            n_feasible=csv_row["n_feasible"],
            n_pareto=csv_row["n_pareto"],
            hv_quick=csv_row["hv_quick"],
            elapsed_s=round(elapsed, 1),
            status="ok",
            stopped_by_time=cb.stopped_by_time,
            actual_evals=actual_evals,
        ))

    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        summary["error_msg"] = err
        print(f"\n  [ERRO] {alg_id}/{inst_name}/run{run_idx}: {err}")
        traceback.print_exc()
        try:
            from experiment_io import mark_run_error
            mark_run_error(idx_csv, alg_id, inst_name, run_idx, seed, err)
        except Exception:
            pass

    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Análise de critério de parada
# ─────────────────────────────────────────────────────────────────────────────

def _compute_hv_safe(F_pareto: np.ndarray, ref_point: np.ndarray) -> float:
    """HV com ref_point dado; retorna 0 se F_pareto inválido."""
    from pymoo.indicators.hv import HV
    if len(F_pareto) == 0:
        return 0.0
    dominated = np.all(F_pareto < ref_point, axis=1)
    F_dom = F_pareto[dominated]
    if len(F_dom) == 0:
        return 0.0
    try:
        return float(HV(ref_point=ref_point)(F_dom))
    except Exception:
        return 0.0


def find_nstar(eval_points: list, hv_medians: list,
               window_evals: int = WINDOW_EVALS,
               eps: float = EPS_THRESHOLD,
               n_consecutive: int = N_CONSECUTIVE) -> Optional[int]:
    """
    Encontra N* — primeiro ponto onde a melhoria relativa em janela
    móvel fica abaixo de `eps` por `n_consecutive` pontos consecutivos.

    Retorna N* (int) ou None se o algoritmo não convergiu no budget.
    """
    if len(eval_points) < 2:
        return None
    snap_step    = eval_points[1] - eval_points[0]
    window_snaps = max(1, window_evals // snap_step)

    # Mínimo de pontos necessários para avaliar ao menos 1 janela completa
    # com os n_consecutive pontos consecutivos requeridos.
    # Ex: window_snaps=5, n_consecutive=3 → mínimo de 8 pontos.
    min_viable = window_snaps + n_consecutive
    if len(eval_points) < min_viable:
        return None

    n = len(eval_points)
    below = []
    for i in range(window_snaps, n):
        hv_now  = hv_medians[i]
        hv_prev = hv_medians[i - window_snaps]
        if hv_prev <= 0:
            below.append(False)
            continue
        rel = (hv_now - hv_prev) / hv_prev
        below.append(rel < eps)

    for i in range(len(below) - n_consecutive + 1):
        if all(below[i:i + n_consecutive]):
            return eval_points[window_snaps + i]

    return None   # não convergiu dentro do budget


def analyze(exp_dir: str, index_csv: str,
            window_evals: int = WINDOW_EVALS,
            eps: float = EPS_THRESHOLD,
            n_consecutive: int = N_CONSECUTIVE,
            safety: float = SAFETY_MARGIN,
            round_to: int = ROUND_TO):
    """
    Fases 2, 3 e 4 do procedimento formal de calibração.
    Lê pickles, computa curvas de HV mediano, identifica N*, agrega.
    Produz:
      - stopping_criterion_report.md
      - stopping_criterion_analysis.csv
      - preliminary_comparison.csv
      - convergence_curves/{algo}_{inst}.json
    """
    from experiment_io import load_run, _non_dominated

    print(f"\n{'═'*72}")
    print("ANÁLISE DO CRITÉRIO DE PARADA")
    print(f"{'═'*72}")

    if not os.path.exists(index_csv):
        print("  index.csv não encontrado.")
        return

    rows = []
    with open(index_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status", "") == "ok" and row.get("pickle_path"):
                rows.append(row)

    instances  = sorted(set(r["instance"] for r in rows))
    algorithms = sorted(set(r["algorithm_id"] for r in rows))
    print(f"  {len(rows)} runs ok  |  {len(instances)} instâncias  |  {len(algorithms)} algoritmos")

    # ── Passo 1: ref_point consistente por instância ──────────────────
    print("\n  Calculando ref_points por instância...")
    ref_points = {}
    for inst in instances:
        inst_rows = [r for r in rows if r["instance"] == inst]
        all_F = []
        for r in inst_rows:
            pkl_path = os.path.join(exp_dir, r["pickle_path"])
            try:
                data = load_run(pkl_path)
                F_p  = data["pareto_front"]["F"]
                if len(F_p) > 0:
                    all_F.append(F_p)
            except Exception as e:
                print(f"    [AVISO] {pkl_path}: {e}")
        if all_F:
            combined = np.vstack(all_F)
            ref_points[inst] = combined.max(axis=0) * 1.1
            print(f"    {inst}: ref_point=[{', '.join(f'{v:.1f}' for v in ref_points[inst])}]")
        else:
            print(f"    [AVISO] Sem dados para {inst}")

    # ── Passo 2: curvas HV por (algo, inst, run) ──────────────────────
    print("\n  Construindo curvas de HV...")
    # hv_curves[algo][inst] = list of (eval_points, hv_values) per run
    hv_curves: dict = {}
    for alg_id in algorithms:
        hv_curves[alg_id] = {}
        for inst in instances:
            if inst not in ref_points:
                continue
            ref  = ref_points[inst]
            runs = [r for r in rows if r["algorithm_id"] == alg_id and r["instance"] == inst]
            inst_curves = []
            for r in runs:
                pkl_path = os.path.join(exp_dir, r["pickle_path"])
                try:
                    data = load_run(pkl_path)
                    hist = data.get("convergence_history", [])
                    if not hist:
                        continue
                    evals = [s["n_eval"] for s in hist]
                    hvs   = [_compute_hv_safe(s["F_pareto"], ref) for s in hist]
                    inst_curves.append((evals, hvs))
                except Exception as e:
                    print(f"    [AVISO] {pkl_path}: {e}")
            hv_curves[alg_id][inst] = inst_curves

    # ── Passo 3: HV mediano e identificação de N* ─────────────────────
    print("\n  Identificando N* por (algoritmo, instância)...")
    curves_dir = os.path.join(exp_dir, "convergence_curves")
    os.makedirs(curves_dir, exist_ok=True)

    nstar_table = {}   # (alg, inst) -> N* ou None
    median_final_hv = {}  # (alg, inst) -> float

    for alg_id in algorithms:
        for inst in instances:
            if inst not in ref_points:
                continue
            curves = hv_curves[alg_id].get(inst, [])
            if not curves:
                nstar_table[(alg_id, inst)] = None
                median_final_hv[(alg_id, inst)] = 0.0
                continue

            # Alinha pontos de medição usando o primeiro run como referência.
            # Filtra runs com snapshots insuficientes (cortadas por tempo):
            #   mínimo = window_snaps + n_consecutive para find_nstar funcionar.
            snap_step_est = CONV_INTERVAL  # estimativa; real vem dos dados
            window_snaps_est = max(1, window_evals // snap_step_est)
            min_snaps = window_snaps_est + n_consecutive

            ref_evals   = curves[0][0]
            aligned_hvs = []
            n_short     = 0
            for (ev, hv) in curves:
                ev_arr = np.array(ev);  hv_arr = np.array(hv)
                if len(ev_arr) == 0:
                    n_short += 1
                    continue
                if len(ev_arr) < min_snaps:
                    n_short += 1
                    continue
                min_len = min(len(ev), len(ref_evals))
                aligned_hvs.append(hv_arr[:min_len])

            if n_short > 0:
                print(f"    [INFO] {alg_id}/{inst}: {n_short} run(s) com "
                      f"< {min_snaps} snapshots ignoradas (provavelmente cortadas por tempo)")

            if not aligned_hvs:
                nstar_table[(alg_id, inst)] = None
                median_final_hv[(alg_id, inst)] = 0.0
                continue

            min_len   = min(len(a) for a in aligned_hvs)
            eval_pts  = ref_evals[:min_len]
            median_hv = np.median(np.vstack([a[:min_len] for a in aligned_hvs]), axis=0).tolist()

            # Salva curva para plots externos
            curve_path = os.path.join(curves_dir, f"{alg_id}_{inst}.json")
            with open(curve_path, "w") as jf:
                json.dump({"eval_points": eval_pts, "hv_median": median_hv,
                           "n_runs": len(aligned_hvs), "n_runs_skipped": n_short,
                           "ref_point": ref_points[inst].tolist()}, jf)

            nstar = find_nstar(eval_pts, median_hv, window_evals, eps, n_consecutive)
            nstar_table[(alg_id, inst)] = nstar
            median_final_hv[(alg_id, inst)] = median_hv[-1] if median_hv else 0.0

            nstar_str = f"{nstar:,}" if nstar else "não convergiu"
            skip_str  = f" [{n_short} ignoradas]" if n_short else ""
            print(f"    {alg_id:<10}  {inst:<12}  N*={nstar_str:>12}  "
                  f"HV_final={median_final_hv[(alg_id, inst)]:.2f}  "
                  f"({len(aligned_hvs)} runs{skip_str})")

    # ── Passo 4: Agregação e margem de segurança ──────────────────────
    valid_nstar = [v for v in nstar_table.values() if v is not None]
    if valid_nstar:
        nstar_max    = max(valid_nstar)
        nstar_global = int(np.ceil(nstar_max * safety / round_to) * round_to)
    else:
        nstar_max    = None
        nstar_global = None

    print(f"\n  {'─'*60}")
    print(f"  N* por (algo, inst): {len(valid_nstar)} convergidos / {len(nstar_table)} total")
    if valid_nstar:
        print(f"  max(N*)             = {nstar_max:,}")
        print(f"  × {safety:.0%} margem     = {nstar_max * safety:,.0f}")
        print(f"  arredondado         = {nstar_global:,}  ← critério de parada oficial")
    else:
        print("  Nenhum algoritmo convergiu — aumentar orçamento ou revisar instâncias.")

    # ── Outputs ───────────────────────────────────────────────────────
    _save_analysis_csv(exp_dir, nstar_table, median_final_hv, algorithms, instances,
                       nstar_global, window_evals, eps)
    _save_preliminary_comparison(exp_dir, median_final_hv, algorithms, instances)
    _save_report(exp_dir, nstar_table, median_final_hv, algorithms, instances,
                 nstar_max, nstar_global, window_evals, eps, n_consecutive,
                 safety, round_to, valid_nstar)

    return nstar_global


def _save_analysis_csv(exp_dir, nstar_table, median_final_hv, algorithms, instances,
                       nstar_global, window_evals, eps):
    path = os.path.join(exp_dir, "stopping_criterion_analysis.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["algorithm_id", "instance", "nstar", "nstar_converged",
                    "hv_median_final", "window_evals", "eps_threshold"])
        for alg in algorithms:
            for inst in instances:
                ns  = nstar_table.get((alg, inst))
                hv  = median_final_hv.get((alg, inst), 0.0)
                w.writerow([alg, inst,
                             ns if ns else "",
                             1 if ns else 0,
                             f"{hv:.4f}", window_evals, eps])
        w.writerow(["—", "GLOBAL", nstar_global if nstar_global else "", "",
                    "", window_evals, eps])
    print(f"\n  stopping_criterion_analysis.csv → {path}")


def _save_preliminary_comparison(exp_dir, median_final_hv, algorithms, instances):
    path = os.path.join(exp_dir, "preliminary_comparison.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["instance"] + list(algorithms) + ["winner"])
        w.writeheader()
        for inst in instances:
            row = {"instance": inst}
            max_hv = -1
            winner = ""
            for alg in algorithms:
                hv = median_final_hv.get((alg, inst), 0.0)
                row[alg] = f"{hv:.4f}"
                if hv > max_hv:
                    max_hv = hv;  winner = alg
            row["winner"] = winner
            w.writerow(row)
    print(f"  preliminary_comparison.csv    → {path}")

    # Resumo no console
    print(f"\n  COMPARAÇÃO PRELIMINAR (HV mediano, ref_point consistente por instância):")
    print(f"  {'Instância':<12} " + "  ".join(f"{a:<10}" for a in algorithms) + "  Vencedor")
    print(f"  {'─'*72}")
    wins = {a: 0 for a in algorithms}
    for inst in instances:
        row_vals = []
        max_hv = -1;  win = ""
        for alg in algorithms:
            hv = median_final_hv.get((alg, inst), 0.0)
            row_vals.append(f"{hv:.2f}")
            if hv > max_hv:
                max_hv = hv;  win = alg
        wins[win] += 1
        print(f"  {inst:<12} " + "  ".join(f"{v:<10}" for v in row_vals) + f"  {win}")
    print(f"  {'─'*72}")
    print(f"  Vitórias: " + "  ".join(f"{a}={wins[a]}" for a in algorithms))


def _save_report(exp_dir, nstar_table, median_final_hv, algorithms, instances,
                 nstar_max, nstar_global, window_evals, eps, n_consecutive,
                 safety, round_to, valid_nstar):
    path = os.path.join(exp_dir, "stopping_criterion_report.md")
    ts   = datetime.now().isoformat(timespec="seconds")

    with open(path, "w", encoding="utf-8") as f:
        f.write("# Relatório de Calibração do Critério de Parada\n\n")
        f.write(f"**Gerado em**: {ts}\n\n")
        f.write("## Resultado Principal\n\n")
        if nstar_global:
            f.write(f"**Critério de parada oficial: {nstar_global:,} avaliações**\n\n")
            f.write(f"- max(N*) = {nstar_max:,}\n")
            f.write(f"- × {safety:.0%} (margem de segurança) = {nstar_max * safety:,.0f}\n")
            f.write(f"- Arredondado para múltiplo de {round_to:,} → **{nstar_global:,}**\n\n")
        else:
            f.write("**Critério de parada: não determinado** "
                    "(nenhum algoritmo convergiu no budget disponível).\n\n")

        f.write("## Metodologia\n\n")
        f.write(f"- **Instâncias de calibração**: {', '.join(instances)}\n")
        f.write(f"- **Algoritmos**: {', '.join(algorithms)}\n")
        f.write(f"- **Janela móvel**: {window_evals:,} avaliações\n")
        f.write(f"- **Threshold ε**: {eps*100:.1f}%\n")
        f.write(f"- **Pontos consecutivos**: {n_consecutive}\n\n")

        f.write("## Trecho para o TCC\n\n")
        f.write("> O critério de parada foi calibrado seguindo um procedimento formal de "
                "identificação de estabilidade do hipervolume. Para cada combinação "
                "(algoritmo, instância) em um conjunto de 6 instâncias representativas "
                "(uma por célula de tipo espacial × série — C-1xx, C-2xx, R-1xx, R-2xx, "
                "RC-1xx, RC-2xx), foram executados 5 runs com orçamento estendido. "
                f"O hipervolume mediano foi calculado a cada {CONV_INTERVAL:,} avaliações. "
                f"Identificou-se o ponto de estabilização N*(algoritmo, instância) como o "
                f"primeiro ponto onde a melhoria relativa em janela móvel de {window_evals:,} "
                f"avaliações fica abaixo de {eps*100:.0f}% e permanece abaixo nos "
                f"{n_consecutive} pontos subsequentes. O critério de parada global foi "
                f"definido como max{{N*(algoritmo, instância)}} × {safety:.0%}, "
                f"arredondado para o múltiplo de {round_to:,} mais próximo, "
                "garantindo que o algoritmo mais lento na instância mais difícil tenha "
                f"orçamento suficiente para convergência. O valor obtido foi "
                # Nota: este é um conditional expression — o f-string com
                # {nstar_global:,} só é avaliado quando nstar_global é não-None.
                # Python avalia apenas o branch ativo da expressão condicional.
                f"**{nstar_global:,} avaliações**.\n\n" if nstar_global else
                "> (Completar após obter resultados de calibração.)\n\n")

        f.write("## N* por (Algoritmo, Instância)\n\n")
        f.write("| Algoritmo | Instância | N* | Convergiu | HV Final |\n")
        f.write("|-----------|-----------|---:|-----------|----------|\n")
        for alg in algorithms:
            for inst in instances:
                ns  = nstar_table.get((alg, inst))
                hv  = median_final_hv.get((alg, inst), 0.0)
                ns_str = f"{ns:,}" if ns else "não convergiu"
                conv   = "✅" if ns else "❌"
                f.write(f"| {alg} | {inst} | {ns_str} | {conv} | {hv:.2f} |\n")

        f.write("\n## Comparação Preliminar dos Algoritmos\n\n")
        f.write("| Instância | " + " | ".join(algorithms) + " | Vencedor |\n")
        f.write("|-----------|" + "|".join(["-----" for _ in algorithms]) + "|----------|\n")
        wins = {a: 0 for a in algorithms}
        for inst in instances:
            hvs = {alg: median_final_hv.get((alg, inst), 0.0) for alg in algorithms}
            win = max(hvs, key=hvs.get)
            wins[win] += 1
            row = " | ".join(f"{hvs[a]:.2f}" for a in algorithms)
            f.write(f"| {inst} | {row} | {win} |\n")
        f.write("\n**Vitórias**: " + ", ".join(f"{a}={wins[a]}" for a in algorithms) + "\n\n")

        f.write("## Robustez do MOEA/D-WS\n\n")
        if "moead_ws" in algorithms:
            moead_hvs = [median_final_hv.get(("moead_ws", inst), 0.0) for inst in instances]
            f.write(f"- HV mediano em {len(instances)} instâncias:\n")
            for inst, hv in zip(instances, moead_hvs):
                f.write(f"  - {inst}: {hv:.2f}\n")
            if moead_hvs and max(moead_hvs) > 0:
                cv_pct = np.std(moead_hvs) / np.mean(moead_hvs) * 100
                f.write(f"- Coef. de variação: {cv_pct:.1f}%\n")
                if cv_pct < 30:
                    f.write("- **Robusto**: variação < 30% entre instâncias.\n")
                else:
                    f.write("- **Variável**: variação elevada — investigar instâncias específicas.\n")
        f.write("\n")

    print(f"  stopping_criterion_report.md  → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Calibração formal do critério de parada — EVRPTW TCC"
    )
    ap.add_argument("--dry-run",     action="store_true",
                    help="1 run, 5k evals — verifica pipeline sem executar tudo")
    ap.add_argument("--n-evals",     type=int, default=None,
                    help=f"Hard cap de avaliações (padrão: {N_EVALS_MAX:,})")
    ap.add_argument("--max-seconds", type=int, default=MAX_SECONDS,
                    help=f"Limite de tempo por run em segundos (padrão: {MAX_SECONDS})")
    ap.add_argument("--n-runs",      type=int, default=N_RUNS_CALIB,
                    help=f"Runs por (algoritmo, instância) (padrão: {N_RUNS_CALIB})")
    ap.add_argument("--n-workers",   type=int, default=N_WORKERS)
    ap.add_argument("--algorithms",  nargs="+", default=None)
    ap.add_argument("--instances",   nargs="+", default=None)
    ap.add_argument("--results-dir", default=None)
    ap.add_argument("--analyze-only",action="store_true",
                    help="Pula execução, só analisa pickles existentes")
    ap.add_argument("--eps",    type=float, default=EPS_THRESHOLD)
    ap.add_argument("--window", type=int,   default=WINDOW_EVALS)
    ap.add_argument("--consecutive", type=int, default=N_CONSECUTIVE)
    args = ap.parse_args()

    n_evals   = 5_000         if args.dry_run else (args.n_evals or N_EVALS_MAX)
    max_sec   = 30            if args.dry_run else args.max_seconds
    n_runs    = 1             if args.dry_run else args.n_runs
    n_workers = 1             if args.dry_run else args.n_workers

    active_algs  = ["nsga2", "moead_ws", "smsemoa"]
    if args.algorithms:
        active_algs = [a for a in active_algs if a in args.algorithms]

    active_insts = dict(CALIB_INSTANCES)
    if args.instances:
        active_insts = {k: v for k, v in CALIB_INSTANCES.items() if k in args.instances}

    # Verifica que os arquivos de instância existem
    missing = [k for k, v in active_insts.items() if not os.path.exists(v)]
    if missing:
        print(f"[ERRO] Instâncias faltando: {missing}")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    exp_dir   = args.results_dir or os.path.join(ROOT, "results",
                                                  f"stopping_criterion_{timestamp}")
    os.makedirs(exp_dir, exist_ok=True)
    index_csv = os.path.join(exp_dir, "index.csv")
    git_commit = get_git_commit(ROOT)

    if args.analyze_only:
        if not os.path.exists(index_csv):
            print(f"[ERRO] index.csv não encontrado em {exp_dir}")
            sys.exit(1)
        analyze(exp_dir, index_csv,
                window_evals=args.window, eps=args.eps,
                n_consecutive=args.consecutive)
        return

    total_tasks = len(active_algs) * len(active_insts) * n_runs
    est_sec_per_run = min(n_evals * 0.012, max_sec)
    est_wall_h = total_tasks * est_sec_per_run / n_workers / 3600

    print("=" * 72)
    print("CALIBRAÇÃO DO CRITÉRIO DE PARADA — EVRPTW TCC")
    print("=" * 72)
    print(f"  Modo        : {'DRY-RUN' if args.dry_run else 'COMPLETO'}")
    print(f"  Algoritmos  : {active_algs}")
    print(f"  Instâncias  : {list(active_insts.keys())}")
    print(f"  Runs        : {n_runs}  |  max_evals: {n_evals:,}  |  max_time: {max_sec}s")
    print(f"  Total tasks : {total_tasks}")
    print(f"  Workers     : {n_workers}")
    print(f"  ETA estim.  : ~{est_wall_h:.1f}h  (~{min(n_evals*0.012/60, max_sec/60):.0f}min/run)")
    print(f"  Critério    : janela={args.window:,} evals, ε={args.eps*100:.1f}%, {args.consecutive} pontos")
    print(f"  git commit  : {git_commit}")
    print(f"  Resultados  : {exp_dir}")
    print("=" * 72)

    # Retomada
    completed: set = set()
    if os.path.exists(index_csv):
        with open(index_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("status", "") == "ok":
                    completed.add((row["algorithm_id"], row["instance"], int(row["run_idx"])))
        if completed:
            print(f"\n  Retomada: {len(completed)} runs ok (serão pulados)")

    # Gera tasks
    tasks = []
    for alg_id in active_algs:
        for inst_name, inst_path in active_insts.items():
            for run_idx in range(1, n_runs + 1):
                if (alg_id, inst_name, run_idx) in completed:
                    continue
                tasks.append({
                    "algorithm_id":  alg_id,
                    "instance":      inst_name,
                    "inst_path":     inst_path,
                    "run_idx":       run_idx,
                    "seed":          _seed(alg_id, inst_name, run_idx),
                    "n_evals":       n_evals,
                    "max_seconds":   max_sec,
                    "experiment_dir": exp_dir,
                    "index_csv":     index_csv,
                    "git_commit":    git_commit,
                    "conv_interval": CONV_INTERVAL,
                })

    if not tasks:
        print("\n  Todos os runs completos. Rodando análise...")
        analyze(exp_dir, index_csv,
                window_evals=args.window, eps=args.eps,
                n_consecutive=args.consecutive)
        return

    # Embaralha (seed=42) — expõe problemas cedo e intercala algoritmos
    random.seed(42)
    random.shuffle(tasks)

    print(f"\n  Tasks restantes: {len(tasks)} / {total_tasks}  (embaralhadas, seed=42)")
    print(f"\n{'─'*72}")
    print(f"  {'#':>4}  {'Alg':<10}  {'Instância':<12}  {'Run':<4}  "
          f"{'Feas':>5}  {'Pareto':>6}  {'HV':>12}  {'Tempo':>8}  {'⏱️':>5}  Status")
    print(f"{'─'*72}")

    global_start = time.perf_counter()
    done_count   = len(completed)
    error_count  = 0

    with Pool(processes=n_workers) as pool:
        for s in pool.imap_unordered(run_task, tasks):
            done_count += 1
            has_error   = s["status"] != "ok"
            if has_error:
                error_count += 1

            elapsed_total = time.perf_counter() - global_start
            frac  = done_count / total_tasks
            eta_s = (elapsed_total / frac - elapsed_total) if frac > 0 else 0
            eta   = f"{int(eta_s//3600)}h{int((eta_s%3600)//60):02d}m"
            by_t  = "⏱" if s.get("stopped_by_time") else ""

            print(f"  {done_count:>4}/{total_tasks}  "
                  f"{s['algorithm_id']:<10}  {s['instance']:<12}  "
                  f"{s['run_idx']:<4}  "
                  f"{s.get('n_feasible',0):>5}  "
                  f"{s.get('n_pareto',0):>6}  "
                  f"{s.get('hv_quick',0):>12.2f}  "
                  f"{s.get('elapsed_s',0):>7.1f}s  "
                  f"{by_t:>5}  "
                  f"{'ERRO: '+s.get('error_msg','')[:25] if has_error else 'ok'}  ETA:{eta}")

    total_elapsed = time.perf_counter() - global_start
    h, rem = divmod(int(total_elapsed), 3600)
    m, s = divmod(rem, 60)
    print(f"\n{'─'*72}")
    print(f"  Concluído em {h}h {m:02d}m {s:02d}s  |  Erros: {error_count}/{len(tasks)}")
    print(f"  index.csv : {index_csv}")

    analyze(exp_dir, index_csv,
            window_evals=args.window, eps=args.eps,
            n_consecutive=args.consecutive)


if __name__ == "__main__":
    main()
