#!/usr/bin/env python3
"""
moead_tuning.py
===============
Experimento de ablação do MOEA/D para EVRPTW tri-objetivo.

Configurações testadas (12):
  C1  (canônica): n_neighbors=20, prob_neighbor_mating=0.9, Tchebycheff
  C2 : n_neighbors=15, prob=0.9, Tchebycheff
  C3 : n_neighbors=10, prob=0.9, Tchebycheff
  C4 : n_neighbors=5,  prob=0.9, Tchebycheff
  C5 : n_neighbors=3,  prob=0.9, Tchebycheff
  C6 : n_neighbors=10, prob=0.7, Tchebycheff
  C7 : n_neighbors=10, prob=0.5, Tchebycheff
  C8 : n_neighbors=10, prob=0.9, PBI(theta=5)
  C9 : n_neighbors=10, prob=0.9, Weighted Sum
  C10: n_neighbors=5,  prob=0.7, PBI(theta=5)
  C11: n_neighbors=5,  prob=0.9, Weighted Sum
  C12: n_neighbors=3,  prob=0.5, PBI(theta=5)

Instâncias (4):
  c101_21 — C-1xx, tw_ratio=0.051, difícil
  c208_21 — C-2xx, tw_ratio=0.735, fácil
  r106_21 — R-1xx, tw_ratio=0.311, intermediário
  r201_21 — R-2xx, tw_ratio=0.784, fácil

4 runs × seed determinística por (config_id, instance, run_idx)
Total: 12 × 4 × 4 = 192 runs

Recursos:
  - Paralelo: 10 workers (multiprocessing.Pool)
  - Persistência incremental: CSV append por run (tolerância a falhas)
  - Retomada: pula tasks (config, instance, run) já no CSV
  - Análise: HV recalculado com ref_point consistente por instância

Modos de execução:
  python moead_tuning.py                  # experimento completo
  python moead_tuning.py --dry-run        # 1 tarefa, 5k evals
  python moead_tuning.py --n-evals 50000 # debug/teste

Uso tmux recomendado:
  tmux new -s moead_tuning
  python scripts/moead_tuning.py 2>&1 | tee moead_tuning.log
  Ctrl+B D  (detach)
"""

# ── Threading constraint ANTES de qualquer import numpy ──────────────────
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("BLIS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import sys
import time
import csv
import json
import pickle
import hashlib
import argparse
import warnings
import traceback
from datetime import datetime
from multiprocessing import Pool

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Configurações do experimento
# ─────────────────────────────────────────────────────────────────────────────

N_EVALS_FULL = 300_000     # avaliações por run (experimento completo)
N_WORKERS    = 10          # workers paralelos (físicos do i9-10900F)
N_RUNS       = 4           # runs por (config, instância)
POP_SIZE     = 105         # nº de direções Das-Dennis (n_partitions=13, 3 obj)

CONFIGS = [
    # id,   label,                        n_neigh, prob,  decomp,      theta
    ("C1",  "canônica",                   20,      0.9,  "tchebycheff", None),
    ("C2",  "n_neigh=15",                 15,      0.9,  "tchebycheff", None),
    ("C3",  "n_neigh=10",                 10,      0.9,  "tchebycheff", None),
    ("C4",  "n_neigh=5",                   5,      0.9,  "tchebycheff", None),
    ("C5",  "n_neigh=3",                   3,      0.9,  "tchebycheff", None),
    ("C6",  "prob=0.7",                   10,      0.7,  "tchebycheff", None),
    ("C7",  "prob=0.5",                   10,      0.5,  "tchebycheff", None),
    ("C8",  "PBI(5)",                     10,      0.9,  "pbi",          5.0),
    ("C9",  "WeightedSum",                10,      0.9,  "weighted-sum", None),
    ("C10", "n5+p0.7+PBI",                5,      0.7,  "pbi",          5.0),
    ("C11", "n5+WS",                       5,      0.9,  "weighted-sum", None),
    ("C12", "extremo(n3+p0.5+PBI)",        3,      0.5,  "pbi",          5.0),
]

INSTANCES = {
    "c101_21": os.path.join(ROOT, "evrptw_instances", "c101_21.txt"),
    "c208_21": os.path.join(ROOT, "evrptw_instances", "c208_21.txt"),
    "r106_21": os.path.join(ROOT, "evrptw_instances", "r106_21.txt"),
    "r201_21": os.path.join(ROOT, "evrptw_instances", "r201_21.txt"),
}

# CSV header fixo
CSV_FIELDS = [
    "config_id", "config_label", "instance", "run_idx", "seed",
    "n_neighbors", "prob_neighbor_mating", "decomposition", "pbi_theta",
    "n_evals", "effective_evals",
    "n_feasible", "n_total",
    "n_unique_obj", "n_unique_feasible",
    "n_f1_layers",
    "best_f1", "best_f2", "best_f3",
    "hv_raw",          # HV com ref_point local só desta run (para debug)
    "elapsed_s",
    "timestamp",
    "error",           # vazio se ok, mensagem se falhou
]


# ─────────────────────────────────────────────────────────────────────────────
# Funções auxiliares
# ─────────────────────────────────────────────────────────────────────────────

def _deterministic_seed(config_id: str, instance_name: str, run_idx: int) -> int:
    """Seed reproduzível: hash de (config_id, instance, run_idx) % 2^32."""
    key = f"{config_id}_{instance_name}_{run_idx}"
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2 ** 32)


def _get_ref_dirs(n_obj=3, n_partitions=13):
    try:
        from pymoo.util.ref_dirs import get_reference_directions
    except ImportError:
        from pymoo.util.reference_direction import get_reference_directions
    return get_reference_directions("das-dennis", n_obj, n_partitions=n_partitions)


def _build_moead(n_neighbors, prob_neighbor_mating, decomposition, pbi_theta,
                 ref_dirs, operators):
    from pymoo.algorithms.moo.moead import MOEAD
    kwargs = dict(
        ref_dirs=ref_dirs,
        n_neighbors=n_neighbors,
        prob_neighbor_mating=prob_neighbor_mating,
        **operators,
    )
    if decomposition == "tchebycheff":
        # default do pymoo MOEAD
        pass
    elif decomposition == "pbi":
        from pymoo.decomposition.pbi import PBI
        kwargs["decomposition"] = PBI(theta=pbi_theta)
    elif decomposition == "weighted-sum":
        from pymoo.decomposition.weighted_sum import WeightedSum
        kwargs["decomposition"] = WeightedSum()
    return MOEAD(**kwargs)


def _extract_pareto_front(res):
    """Extrai frente viável (cv=0) do resultado pymoo."""
    cv_arr = res.pop.get("_cv")
    F_real = res.pop.get("_F_real")
    if cv_arr is None or F_real is None:
        return np.empty((0, 3))
    mask = cv_arr[:, 0] <= 1e-9
    return F_real[mask].copy()


def _compute_hv(F_feasible: np.ndarray, ref_point: np.ndarray) -> float:
    from pymoo.indicators.hv import HV
    if len(F_feasible) == 0:
        return 0.0
    # garantir que nenhum ponto domina o ref_point
    if np.any(F_feasible >= ref_point):
        return 0.0
    return float(HV(ref_point=ref_point)(F_feasible))


def _metrics_from_front(F_feasible: np.ndarray, ref_point_local: np.ndarray):
    """Calcula métricas da frente viável."""
    n_feas = len(F_feasible)
    if n_feas == 0:
        return dict(
            n_unique_feasible=0, n_f1_layers=0,
            best_f1=float("nan"), best_f2=float("nan"), best_f3=float("nan"),
            hv_raw=0.0,
        )
    unique_F  = np.unique(np.round(F_feasible, 6), axis=0)
    f1_vals   = np.unique(F_feasible[:, 0])
    hv_raw    = _compute_hv(F_feasible, ref_point_local)
    return dict(
        n_unique_feasible=len(unique_F),
        n_f1_layers=len(f1_vals),
        best_f1=float(F_feasible[:, 0].min()),
        best_f2=float(F_feasible[:, 1].min()),
        best_f3=float(F_feasible[:, 2].min()),
        hv_raw=hv_raw,
    )


def _local_ref_point(ctx):
    """Ref_point rápido baseado em valores máximos teóricos (para hv_raw)."""
    n = ctx.n_customers
    horizon = float(ctx.all_nodes[0].due_date)
    # estimativas conservadoras: 1.5× pior caso
    f1_max = float(n) * 1.5
    f2_max = horizon * 2.0
    f3_max = horizon * float(n) * 1.5
    return np.array([f1_max, f2_max, f3_max])


# ─────────────────────────────────────────────────────────────────────────────
# Função worker — rodará em processo separado
# ─────────────────────────────────────────────────────────────────────────────

def run_single_task(task: dict) -> dict:
    """
    Executa um único run do MOEA/D.
    Recebe task dict, retorna result dict (sempre serializável).
    Captura exceções para não matar o pool.
    """
    # Garante restrição de threading no processo filho
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    sys.path.insert(0, ROOT)

    config_id   = task["config_id"]
    config_label= task["config_label"]
    inst_name   = task["instance"]
    inst_path   = task["inst_path"]
    run_idx     = task["run_idx"]
    seed        = task["seed"]
    n_neighbors = task["n_neighbors"]
    prob        = task["prob_neighbor_mating"]
    decomp      = task["decomposition"]
    theta       = task["pbi_theta"]
    n_evals     = task["n_evals"]

    base_result = {
        "config_id":             config_id,
        "config_label":          config_label,
        "instance":              inst_name,
        "run_idx":               run_idx,
        "seed":                  seed,
        "n_neighbors":           n_neighbors,
        "prob_neighbor_mating":  prob,
        "decomposition":         decomp,
        "pbi_theta":             theta if theta is not None else "",
        "n_evals":               n_evals,
        "effective_evals":       0,
        "n_feasible":            0,
        "n_total":               0,
        "n_unique_obj":          0,
        "n_unique_feasible":     0,
        "n_f1_layers":           0,
        "best_f1":               "",
        "best_f2":               "",
        "best_f3":               "",
        "hv_raw":                0.0,
        "elapsed_s":             0.0,
        "timestamp":             datetime.now().isoformat(timespec="seconds"),
        "error":                 "",
    }

    try:
        from pymoo.optimize import minimize
        from pymoo.operators.crossover.ox import OrderCrossover
        from pymoo.operators.mutation.inversion import InversionMutation
        from src import parse_instance, EVRPTWProblem, TWBiasedSampling

        ctx     = parse_instance(inst_path)
        problem = EVRPTWProblem(ctx, k_max=0)   # local search OFF

        ref_dirs = _get_ref_dirs()
        ops = dict(
            sampling=TWBiasedSampling(),
            crossover=OrderCrossover(),
            mutation=InversionMutation(),
        )

        alg = _build_moead(n_neighbors, prob, decomp, theta, ref_dirs, ops)

        t0 = time.perf_counter()
        res = minimize(problem, alg, ("n_eval", n_evals), verbose=False, seed=seed)
        elapsed = time.perf_counter() - t0

        # Extrai frente
        cv_arr = res.pop.get("_cv")
        F_real = res.pop.get("_F_real")
        n_total = len(cv_arr) if cv_arr is not None else 0
        mask    = cv_arr[:, 0] <= 1e-9 if cv_arr is not None else np.zeros(0, bool)
        n_feas  = int(mask.sum())

        F_feas  = _extract_pareto_front(res)
        ref_local = _local_ref_point(ctx)
        metrics = _metrics_from_front(F_feas, ref_local)

        # Contagem de soluções únicas (total, incluindo inviáveis)
        n_unique_obj = 0
        if F_real is not None and len(F_real) > 0:
            n_unique_obj = len(np.unique(np.round(F_real, 6), axis=0))

        actual_evals = res.algorithm.evaluator.n_eval if hasattr(res, "algorithm") else n_evals

        base_result.update({
            "effective_evals":   actual_evals,
            "n_feasible":        n_feas,
            "n_total":           n_total,
            "n_unique_obj":      n_unique_obj,
            "n_unique_feasible": metrics["n_unique_feasible"],
            "n_f1_layers":       metrics["n_f1_layers"],
            "best_f1":           metrics["best_f1"] if not np.isnan(metrics["best_f1"]) else "",
            "best_f2":           metrics["best_f2"] if not np.isnan(metrics["best_f2"]) else "",
            "best_f3":           metrics["best_f3"] if not np.isnan(metrics["best_f3"]) else "",
            "hv_raw":            metrics["hv_raw"],
            "elapsed_s":         round(elapsed, 3),
            "timestamp":         datetime.now().isoformat(timespec="seconds"),
            "error":             "",
            # Dados extras para análise posterior (não no CSV principal)
            "_F_feas":           F_feas,    # removido antes de salvar CSV
        })

    except Exception as exc:
        base_result["error"] = f"{type(exc).__name__}: {exc}"
        base_result["_F_feas"] = np.empty((0, 3))
        tb = traceback.format_exc()
        print(f"\n  [ERRO] {config_id}/{inst_name}/run{run_idx}: {exc}\n{tb}")

    return base_result


# ─────────────────────────────────────────────────────────────────────────────
# Análise final
# ─────────────────────────────────────────────────────────────────────────────

def analyze_results(results_dir: str, csv_path: str):
    """
    Carrega resultados do CSV + pickles, recalcula HV com ref_point
    consistente por instância (110% do pior valor observado), gera
    tabela agregada e relatório Markdown.
    """
    print(f"\n{'═'*72}")
    print("ANÁLISE FINAL — MOEA/D TUNING")
    print(f"{'═'*72}")

    # ── Carrega CSV ────────────────────────────────────────────────────
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)

    if not rows:
        print("  CSV vazio — nada a analisar.")
        return

    # filtra só os bem-sucedidos
    ok_rows = [r for r in rows if not r.get("error", "").strip()]
    failed  = [r for r in rows if r.get("error", "").strip()]
    print(f"  Runs completos : {len(ok_rows)} / {len(rows)}")
    if failed:
        print(f"  Runs com erro  : {len(failed)}")
        for r in failed:
            print(f"    {r['config_id']}/{r['instance']}/run{r['run_idx']}: {r['error'][:80]}")

    instances   = sorted(set(r["instance"] for r in ok_rows))
    config_ids  = [c[0] for c in CONFIGS]

    # ── Carrega frentes Pareto dos pickles ─────────────────────────────
    fronts: dict[str, list] = {}  # (config_id, instance, run_idx) → F_feas
    pickle_dir = os.path.join(results_dir, "fronts")
    if os.path.isdir(pickle_dir):
        for fname in os.listdir(pickle_dir):
            if not fname.endswith(".pkl"):
                continue
            try:
                parts = fname.replace(".pkl", "").split("__")
                if len(parts) == 3:
                    cid, inst, ridx = parts
                    with open(os.path.join(pickle_dir, fname), "rb") as pf:
                        fronts[(cid, inst, int(ridx))] = pickle.load(pf)
            except Exception:
                pass

    # ── ref_point por instância: 110% do pior observado ───────────────
    ref_points: dict[str, np.ndarray] = {}
    for inst in instances:
        inst_rows = [r for r in ok_rows if r["instance"] == inst]
        all_F = []
        for r in inst_rows:
            key = (r["config_id"], r["instance"], int(r["run_idx"]))
            if key in fronts and len(fronts[key]) > 0:
                all_F.append(fronts[key])
        if all_F:
            combined = np.vstack(all_F)
            ref_points[inst] = combined.max(axis=0) * 1.1
        else:
            # fallback: usa heurística
            print(f"  [AVISO] Sem frentes Pareto carregadas para {inst} — "
                  f"ref_point via heurística.")
            ref_points[inst] = None

    # ── HV recalculado (consistente) ──────────────────────────────────
    hv_table: dict[tuple, list] = {}  # (config_id, instance) → [hv_run1, ...]
    for inst in instances:
        for cid in config_ids:
            hv_table[(cid, inst)] = []

    for r in ok_rows:
        cid  = r["config_id"]
        inst = r["instance"]
        ridx = int(r["run_idx"])
        key  = (cid, inst, ridx)
        ref  = ref_points.get(inst)
        if ref is not None and key in fronts and len(fronts[key]) > 0:
            hv = _compute_hv(fronts[key], ref)
        else:
            # fallback: usa hv_raw do CSV
            hv = float(r.get("hv_raw", 0))
        if (cid, inst) in hv_table:
            hv_table[(cid, inst)].append(hv)

    # ── Tabela de resultados por instância ────────────────────────────
    # Agregação: mediana e IQR do HV, mediana de métricas auxiliares
    summary: dict[tuple, dict] = {}
    for inst in instances:
        for cid in config_ids:
            inst_rows = [r for r in ok_rows
                         if r["config_id"] == cid and r["instance"] == inst]
            hvs    = hv_table.get((cid, inst), [])
            unique = [int(r["n_unique_feasible"]) for r in inst_rows if r["n_unique_feasible"]]
            f1bits = [float(r["best_f1"]) for r in inst_rows if r.get("best_f1")]
            f3bits = [float(r["best_f3"]) for r in inst_rows if r.get("best_f3")]
            elaps  = [float(r["elapsed_s"]) for r in inst_rows if r.get("elapsed_s")]

            summary[(cid, inst)] = {
                "hv_median":     float(np.median(hvs))    if hvs    else 0.0,
                "hv_iqr":        float(np.subtract(*np.percentile(hvs, [75, 25]))) if len(hvs) > 1 else 0.0,
                "hv_mean":       float(np.mean(hvs))      if hvs    else 0.0,
                "unique_median": float(np.median(unique)) if unique  else 0.0,
                "best_f1_med":   float(np.median(f1bits)) if f1bits  else float("nan"),
                "best_f3_med":   float(np.median(f3bits)) if f3bits  else float("nan"),
                "elapsed_med":   float(np.median(elaps))  if elaps   else 0.0,
                "n_runs":        len(inst_rows),
            }

    # ── Imprime tabelas por instância ─────────────────────────────────
    cfg_labels = {c[0]: c[1] for c in CONFIGS}
    cfg_params  = {c[0]: (c[2], c[3], c[4]) for c in CONFIGS}

    for inst in instances:
        print(f"\n  {'─'*72}")
        ref = ref_points.get(inst)
        ref_str = f"{ref}" if ref is not None else "heurística"
        print(f"  Instância: {inst}   ref_point={ref_str}")
        print(f"  {'─'*72}")
        header = (f"  {'Config':<6}  {'Label':<22}  {'n_n':<4}  {'prob':<5}  "
                  f"{'Decomp':<12}  {'HV_med':>14}  {'HV_IQR':>10}  "
                  f"{'Únicos':>7}  {'BestF1':>7}  {'BestF3':>10}")
        print(header)
        print("  " + "─" * (len(header) - 2))

        inst_summary = {cid: summary[(cid, inst)] for cid in config_ids}
        # Ranking por HV mediano
        ranked = sorted(config_ids, key=lambda c: inst_summary[c]["hv_median"], reverse=True)

        for rank, cid in enumerate(ranked, 1):
            s = inst_summary[cid]
            nn, prob, decomp = cfg_params[cid]
            lbl   = cfg_labels[cid]
            c1_hv = inst_summary["C1"]["hv_median"]
            rel   = f"({(s['hv_median']/c1_hv-1)*100:+.1f}%%)" if c1_hv > 0 else ""
            print(f"  {cid:<6}  {lbl:<22}  {nn:<4}  {prob:<5.1f}  "
                  f"{decomp:<12}  {s['hv_median']:>14.2f}  {s['hv_iqr']:>10.2f}  "
                  f"{s['unique_median']:>7.1f}  {s['best_f1_med']:>7.1f}  "
                  f"{s['best_f3_med']:>10.2f}  #{rank}{rel}")

    # ── Ranking global (soma de ranks por instância) ───────────────────
    print(f"\n  {'═'*72}")
    print("  RANKING GLOBAL (por HV mediano — menor rank = melhor)")
    print(f"  {'─'*72}")

    global_rank: dict[str, list] = {cid: [] for cid in config_ids}
    for inst in instances:
        inst_sorted = sorted(config_ids,
                             key=lambda c: summary[(c, inst)]["hv_median"],
                             reverse=True)
        for rank, cid in enumerate(inst_sorted, 1):
            global_rank[cid].append(rank)

    overall = sorted(config_ids, key=lambda c: np.mean(global_rank[c]))
    print(f"  {'Config':<6}  {'Label':<22}  {'Rank médio':>11}  "
          f"{'Ranks por instância'}")
    print("  " + "─" * 60)
    for cid in overall:
        ranks = global_rank[cid]
        lbl   = cfg_labels[cid]
        print(f"  {cid:<6}  {lbl:<22}  {np.mean(ranks):>11.2f}  {ranks}")

    winner = overall[0]
    nn, prob, decomp = cfg_params[winner]
    print(f"\n  ★ MELHOR CONFIGURAÇÃO GLOBAL: {winner}  "
          f"n_neighbors={nn}, prob={prob}, decomp={decomp}")

    # ── Salva CSV de análise ───────────────────────────────────────────
    analysis_rows = []
    for (cid, inst), s in summary.items():
        nn, prob, decomp = cfg_params[cid]
        analysis_rows.append({
            "config_id":    cid,
            "config_label": cfg_labels[cid],
            "instance":     inst,
            "n_neighbors":  nn,
            "prob":         prob,
            "decomp":       decomp,
            **{k: round(v, 6) if isinstance(v, float) else v for k, v in s.items()},
            "global_rank_mean": round(float(np.mean(global_rank[cid])), 2),
        })

    analysis_csv = os.path.join(results_dir, "moead_tuning_analysis.csv")
    with open(analysis_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=analysis_rows[0].keys())
        w.writeheader(); w.writerows(analysis_rows)

    # ── Salva relatório Markdown ───────────────────────────────────────
    md_path = os.path.join(results_dir, "moead_tuning_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# MOEA/D Tuning Report\n\n")
        f.write(f"**Gerado em**: {datetime.now().isoformat(timespec='seconds')}\n\n")
        f.write(f"**Runs concluídos**: {len(ok_rows)} / {len(rows)}\n\n")
        f.write(f"**Melhor configuração global**: {winner} — "
                f"n_neighbors={nn}, prob={prob}, decomp={decomp}\n\n")
        f.write("## Ranking Global\n\n")
        f.write("| Config | Label | Rank médio | Ranks |\n")
        f.write("|--------|-------|-----------|-------|\n")
        for cid in overall:
            ranks = global_rank[cid]
            f.write(f"| {cid} | {cfg_labels[cid]} | "
                    f"{np.mean(ranks):.2f} | {ranks} |\n")
        f.write("\n")
        for inst in instances:
            f.write(f"## {inst}\n\n")
            f.write("| Config | HV median | HV IQR | Únicos | Best F1 | Best F3 |\n")
            f.write("|--------|-----------|--------|--------|---------|----------|\n")
            inst_sorted = sorted(config_ids,
                                 key=lambda c: summary[(c, inst)]["hv_median"],
                                 reverse=True)
            for cid in inst_sorted:
                s = summary[(cid, inst)]
                f.write(f"| {cid} | {s['hv_median']:.2f} | {s['hv_iqr']:.2f} | "
                        f"{s['unique_median']:.0f} | {s['best_f1_med']:.1f} | "
                        f"{s['best_f3_med']:.2f} |\n")
            f.write("\n")

    print(f"\n  CSV análise : {analysis_csv}")
    print(f"  Relatório   : {md_path}")
    print(f"{'═'*72}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="MOEA/D ablation study para EVRPTW tri-objetivo."
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="Roda 1 tarefa com 5k evals para verificar funcionamento")
    ap.add_argument("--n-evals", type=int, default=None,
                    help=f"Override de avaliações por run (padrão: {N_EVALS_FULL:,})")
    ap.add_argument("--n-workers", type=int, default=N_WORKERS,
                    help=f"Número de workers paralelos (padrão: {N_WORKERS})")
    ap.add_argument("--n-runs",    type=int, default=N_RUNS,
                    help=f"Runs por (config, instância) (padrão: {N_RUNS})")
    ap.add_argument("--configs",  nargs="+", default=None,
                    help="Subset de configs a rodar ex: C1 C3 C8")
    ap.add_argument("--instances", nargs="+", default=None,
                    help="Subset de instâncias ex: c101_21 r106_21")
    ap.add_argument("--results-dir", default=None,
                    help="Diretório de resultados (padrão: results/moead_tuning_<ts>)")
    ap.add_argument("--analyze-only", action="store_true",
                    help="Pula execução e só roda análise final (requer --results-dir)")
    args = ap.parse_args()

    # ── Parâmetros efetivos ────────────────────────────────────────────
    n_evals   = 5_000 if args.dry_run else (args.n_evals or N_EVALS_FULL)
    n_workers = 1     if args.dry_run else args.n_workers
    n_runs    = 1     if args.dry_run else args.n_runs

    active_configs   = [c for c in CONFIGS if args.configs is None or c[0] in args.configs]
    active_instances = {k: v for k, v in INSTANCES.items()
                        if args.instances is None or k in args.instances}

    # ── Diretório de resultados ────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.results_dir:
        results_dir = args.results_dir
    else:
        results_dir = os.path.join(ROOT, "results", f"moead_tuning_{timestamp}")
    os.makedirs(results_dir, exist_ok=True)
    fronts_dir = os.path.join(results_dir, "fronts")
    os.makedirs(fronts_dir, exist_ok=True)

    csv_path = os.path.join(results_dir, "moead_tuning_runs.csv")

    # ── Modo analyze-only ─────────────────────────────────────────────
    if args.analyze_only:
        if not os.path.exists(csv_path):
            print(f"[ERRO] CSV não encontrado: {csv_path}")
            sys.exit(1)
        analyze_results(results_dir, csv_path)
        return

    # ── Cabeçalho ─────────────────────────────────────────────────────
    total_tasks = len(active_configs) * len(active_instances) * n_runs
    print("=" * 72)
    print("MOEA/D TUNING — EVRPTW TRI-OBJETIVO")
    print("=" * 72)
    print(f"  Modo       : {'DRY-RUN' if args.dry_run else 'COMPLETO'}")
    print(f"  Configs    : {len(active_configs)}  ({[c[0] for c in active_configs]})")
    print(f"  Instâncias : {len(active_instances)}  ({list(active_instances.keys())})")
    print(f"  Runs/tarefa: {n_runs}")
    print(f"  Total tasks: {total_tasks}")
    print(f"  N_evals    : {n_evals:,}")
    print(f"  Workers    : {n_workers}")
    print(f"  Resultados : {results_dir}")
    print("=" * 72)

    # ── Carrega tasks já completas (retomada) ─────────────────────────
    completed: set[tuple] = set()
    if os.path.exists(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if not row.get("error", "").strip():
                    completed.add((row["config_id"], row["instance"], int(row["run_idx"])))
        if completed:
            print(f"\n  Retomada: {len(completed)} runs já completos (serão pulados)")

    # ── Gera lista de tarefas ──────────────────────────────────────────
    tasks = []
    for cfg in active_configs:
        cid, clabel, nn, prob, decomp, theta = cfg
        for inst_name, inst_path in active_instances.items():
            for run_idx in range(1, n_runs + 1):
                key = (cid, inst_name, run_idx)
                if key in completed:
                    continue
                seed = _deterministic_seed(cid, inst_name, run_idx)
                tasks.append({
                    "config_id":            cid,
                    "config_label":         clabel,
                    "instance":             inst_name,
                    "inst_path":            inst_path,
                    "run_idx":              run_idx,
                    "seed":                 seed,
                    "n_neighbors":          nn,
                    "prob_neighbor_mating": prob,
                    "decomposition":        decomp,
                    "pbi_theta":            theta,
                    "n_evals":              n_evals,
                })

    if not tasks:
        print("\n  Todas as tasks já completas. Rodando análise final...")
        analyze_results(results_dir, csv_path)
        return

    print(f"\n  Tasks restantes: {len(tasks)} (de {total_tasks})")

    # ── Inicializa CSV se novo ─────────────────────────────────────────
    csv_new = not os.path.exists(csv_path)
    csv_file = open(csv_path, "a", newline="", encoding="utf-8")
    csv_writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
    if csv_new:
        csv_writer.writeheader()
    csv_file.flush()

    # ── Execução paralela ─────────────────────────────────────────────
    print(f"\n{'─'*72}")
    print(f"  {'#':>4}  {'Config':<6}  {'Instância':<12}  {'Run':<4}  "
          f"{'Evals':>8}  {'Feas':>5}  {'Únicos':>7}  "
          f"{'HV_raw':>14}  {'Tempo':>9}  Estado")
    print(f"{'─'*72}")

    global_start = time.perf_counter()
    completed_count = len(completed)
    errors = 0

    with Pool(processes=n_workers) as pool:
        for result in pool.imap_unordered(run_single_task, tasks):
            completed_count += 1
            has_error = bool(result.get("error", "").strip())
            if has_error:
                errors += 1

            # Remove campo interno antes de salvar
            F_feas = result.pop("_F_feas", None)

            # Persiste frente de Pareto em pickle
            if F_feas is not None and len(F_feas) > 0:
                pname = (f"{result['config_id']}__{result['instance']}"
                         f"__{result['run_idx']}.pkl")
                with open(os.path.join(fronts_dir, pname), "wb") as pf:
                    pickle.dump(F_feas, pf, protocol=4)

            # Persiste no CSV
            csv_row = {k: result.get(k, "") for k in CSV_FIELDS}
            csv_writer.writerow(csv_row)
            csv_file.flush()

            # Log em tempo real
            elapsed_total = time.perf_counter() - global_start
            frac  = completed_count / total_tasks
            eta_s = (elapsed_total / frac - elapsed_total) if frac > 0 else 0
            eta   = f"{int(eta_s//60)}m{int(eta_s%60):02d}s"

            estado = "ERRO" if has_error else "ok"
            print(f"  {completed_count:>4}/{total_tasks}  "
                  f"{result['config_id']:<6}  {result['instance']:<12}  "
                  f"{result['run_idx']:<4}  "
                  f"{result.get('effective_evals', 0):>8,}  "
                  f"{result.get('n_feasible', 0):>5}  "
                  f"{result.get('n_unique_feasible', 0):>7}  "
                  f"{result.get('hv_raw', 0):>14.2f}  "
                  f"{result.get('elapsed_s', 0):>8.1f}s  "
                  f"{estado}  ETA:{eta}")

    csv_file.close()

    total_elapsed = time.perf_counter() - global_start
    print(f"\n{'─'*72}")
    h, rem = divmod(int(total_elapsed), 3600)
    m, s   = divmod(rem, 60)
    print(f"  Concluído em {h}h {m:02d}m {s:02d}s  |  Erros: {errors}/{len(tasks)}")

    # ── Análise final ─────────────────────────────────────────────────
    analyze_results(results_dir, csv_path)


if __name__ == "__main__":
    main()
