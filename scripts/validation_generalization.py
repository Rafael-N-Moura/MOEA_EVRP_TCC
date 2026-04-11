#!/usr/bin/env python3
"""
validation_generalization.py
=============================
Script 2 — Validação de generalização (C1 vs C9) em 6 instâncias novas

Verifica que a vantagem do Weighted Sum (C9) sobre a Tchebycheff (C1)
se mantém em instâncias disjuntas das usadas no experimento de tuning.

Configurações comparadas:
  C1 : n_neighbors=20, prob=0.9, Tchebycheff  (canônica / baseline)
  C9 : n_neighbors=10, prob=0.9, Weighted Sum (vencedora do tuning)

Instâncias novas (sem overlap com as 4 do tuning):
  c104_21  — C-1xx
  c206_21  — C-2xx
  r110_21  — R-1xx
  r205_21  — R-2xx
  rc105_21 — RC-1xx  ← totalmente novo (RC não estava no tuning)
  rc205_21 — RC-2xx  ← totalmente novo

5 runs × seed determinística por (config_id, instance, run_idx)
Total: 2 × 6 × 5 = 60 runs × 600k evals

Recursos:
  - Paralelo: 10 workers (ajuste com --n-workers)
  - Persistência incremental: CSV append
  - Retomada automática: pula runs já no CSV
  - Análise final: HV consistente por instância + ranking + relatório MD

Uso tmux (recomendado):
  tmux new -s validation_gen
  python scripts/validation_generalization.py 2>&1 | tee validation_gen.log
  Ctrl+B D  (detach)

  # Acompanhar:
  tmux attach -t validation_gen  ou  tail -f validation_gen.log

Testes rápidos:
  python scripts/validation_generalization.py --dry-run        # 1 run, 5k evals
  python scripts/validation_generalization.py --n-evals 10000  # 10k, debug
"""

# Threading constraint ANTES de qualquer import numpy
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("BLIS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import sys, time, csv, json, pickle, hashlib, argparse, warnings, traceback
from datetime import datetime
from multiprocessing import Pool

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Configurações do experimento
# ─────────────────────────────────────────────────────────────────────────────

N_EVALS_FULL = 600_000
N_WORKERS    = 10
N_RUNS       = 5
POP_SIZE     = 105

# Apenas C1 e C9
CONFIGS = [
    # id,  label,            n_neigh, prob,  decomp,         theta
    ("C1", "Tchebycheff",    20,      0.9,   "tchebycheff",  None),
    ("C9", "WeightedSum",    10,      0.9,   "weighted-sum", None),
]

# 6 instâncias novas — sem overlap com {c101_21, c208_21, r106_21, r201_21}
INSTANCES = {
    "c104_21":  os.path.join(ROOT, "evrptw_instances", "c104_21.txt"),
    "c206_21":  os.path.join(ROOT, "evrptw_instances", "c206_21.txt"),
    "r110_21":  os.path.join(ROOT, "evrptw_instances", "r110_21.txt"),
    "r205_21":  os.path.join(ROOT, "evrptw_instances", "r205_21.txt"),
    "rc105_21": os.path.join(ROOT, "evrptw_instances", "rc105_21.txt"),
    "rc205_21": os.path.join(ROOT, "evrptw_instances", "rc205_21.txt"),
}

CSV_FIELDS = [
    "config_id", "config_label", "instance", "run_idx", "seed",
    "n_neighbors", "prob_neighbor_mating", "decomposition",
    "n_evals", "effective_evals",
    "n_feasible", "n_total",
    "n_unique_feasible", "n_f1_layers",
    "best_f1", "best_f2", "best_f3",
    "hv_raw",
    "elapsed_s", "timestamp", "error",
]


# ─────────────────────────────────────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────────────────────────────────────

def _seed(config_id, instance_name, run_idx):
    key = f"{config_id}_{instance_name}_{run_idx}"
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2 ** 32)


def _get_ref_dirs():
    try:
        from pymoo.util.ref_dirs import get_reference_directions
    except ImportError:
        from pymoo.util.reference_direction import get_reference_directions
    return get_reference_directions("das-dennis", 3, n_partitions=13)


def _build_moead(n_neighbors, prob, decomp, theta, ref_dirs, ops):
    from pymoo.algorithms.moo.moead import MOEAD
    kwargs = dict(ref_dirs=ref_dirs, n_neighbors=n_neighbors,
                  prob_neighbor_mating=prob, **ops)
    if decomp == "weighted-sum":
        from pymoo.decomposition.weighted_sum import WeightedSum
        kwargs["decomposition"] = WeightedSum()
    elif decomp == "pbi":
        from pymoo.decomposition.pbi import PBI
        kwargs["decomposition"] = PBI(theta=theta)
    return MOEAD(**kwargs)


def _compute_hv(F_feas, ref_point):
    from pymoo.indicators.hv import HV
    if len(F_feas) == 0:
        return 0.0
    if np.any(F_feas >= ref_point):
        return 0.0
    return float(HV(ref_point=ref_point)(F_feas))


def _local_ref_point(n, horizon):
    return np.array([float(n) * 1.5, horizon * 2.0, horizon * float(n) * 1.5])

def _fmt_hms(s):
    h = int(s // 3600); m = int((s % 3600) // 60); sec = s % 60
    if h:  return f"{h}h {m:02d}m {sec:04.1f}s"
    if m:  return f"{m}m {sec:04.1f}s"
    return f"{sec:.2f}s"


# ─────────────────────────────────────────────────────────────────────────────
# Worker
# ─────────────────────────────────────────────────────────────────────────────

def run_task(task):
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    sys.path.insert(0, ROOT)

    config_id  = task["config_id"]
    clabel     = task["config_label"]
    inst_name  = task["instance"]
    inst_path  = task["inst_path"]
    run_idx    = task["run_idx"]
    seed       = task["seed"]
    n_neighbors = task["n_neighbors"]
    prob       = task["prob"]
    decomp     = task["decomp"]
    theta      = task["theta"]
    n_evals    = task["n_evals"]

    base = dict(
        config_id=config_id, config_label=clabel, instance=inst_name,
        run_idx=run_idx, seed=seed, n_neighbors=n_neighbors,
        prob_neighbor_mating=prob, decomposition=decomp,
        n_evals=n_evals, effective_evals=0,
        n_feasible=0, n_total=0, n_unique_feasible=0, n_f1_layers=0,
        best_f1="", best_f2="", best_f3="", hv_raw=0.0,
        elapsed_s=0.0,
        timestamp=datetime.now().isoformat(timespec="seconds"),
        error="",
    )

    try:
        from pymoo.optimize import minimize
        from pymoo.operators.crossover.ox import OrderCrossover
        from pymoo.operators.mutation.inversion import InversionMutation
        from src import parse_instance, EVRPTWProblem, TWBiasedSampling

        ctx     = parse_instance(inst_path)
        problem = EVRPTWProblem(ctx, k_max=0)

        ref_dirs = _get_ref_dirs()
        ops = dict(sampling=TWBiasedSampling(),
                   crossover=OrderCrossover(),
                   mutation=InversionMutation())

        alg = _build_moead(n_neighbors, prob, decomp, theta, ref_dirs, ops)

        t0 = time.perf_counter()
        res = minimize(problem, alg, ("n_eval", n_evals), verbose=False, seed=seed)
        elapsed = time.perf_counter() - t0

        cv_arr = res.pop.get("_cv")
        F_real = res.pop.get("_F_real")
        n_total = len(cv_arr) if cv_arr is not None else 0
        mask    = cv_arr[:, 0] <= 1e-9 if cv_arr is not None else np.zeros(0, bool)
        n_feas  = int(mask.sum())
        F_feas  = F_real[mask].copy() if n_feas > 0 else np.empty((0, 3))

        horizon    = float(ctx.all_nodes[0].due_date)
        ref_local  = _local_ref_point(ctx.n_customers, horizon)
        hv_raw     = _compute_hv(F_feas, ref_local)

        unique_F   = np.unique(np.round(F_feas, 6), axis=0) if n_feas > 0 else F_feas
        n_uniq     = len(unique_F)
        f1_layers  = int(len(np.unique(F_feas[:, 0]))) if n_feas > 0 else 0

        actual_evals = res.algorithm.evaluator.n_eval \
            if hasattr(res, "algorithm") else n_evals

        base.update(dict(
            effective_evals=actual_evals,
            n_feasible=n_feas,
            n_total=n_total,
            n_unique_feasible=n_uniq,
            n_f1_layers=f1_layers,
            best_f1=float(F_feas[:, 0].min()) if n_feas > 0 else "",
            best_f2=float(F_feas[:, 1].min()) if n_feas > 0 else "",
            best_f3=float(F_feas[:, 2].min()) if n_feas > 0 else "",
            hv_raw=hv_raw,
            elapsed_s=round(elapsed, 3),
            timestamp=datetime.now().isoformat(timespec="seconds"),
            error="",
            _F_feas=F_feas,
        ))

    except Exception as exc:
        base["error"] = f"{type(exc).__name__}: {exc}"
        base["_F_feas"] = np.empty((0, 3))
        print(f"\n  [ERRO] {config_id}/{inst_name}/run{run_idx}: {exc}")
        traceback.print_exc()

    return base


# ─────────────────────────────────────────────────────────────────────────────
# Análise final
# ─────────────────────────────────────────────────────────────────────────────

def analyze(results_dir, csv_path):
    print(f"\n{'═'*72}")
    print("ANÁLISE FINAL — C1 vs C9 (GENERALIZAÇÃO)")
    print(f"{'═'*72}")

    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)

    ok_rows = [r for r in rows if not r.get("error", "").strip()]
    print(f"  Runs OK : {len(ok_rows)} / {len(rows)}")

    instances  = sorted(set(r["instance"] for r in ok_rows))
    config_ids = [c[0] for c in CONFIGS]
    cfg_labels = {c[0]: c[1] for c in CONFIGS}

    # Carrega frentes de pickle
    fronts = {}
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

    # ref_point por instância (110% do pior entre C1 e C9)
    ref_points = {}
    for inst in instances:
        all_F = []
        for (cid, i, ridx), F in fronts.items():
            if i == inst and len(F) > 0:
                all_F.append(F)
        ref_points[inst] = np.vstack(all_F).max(axis=0) * 1.1 if all_F else None

    # HV por (config, instância, run)
    hv_table = {}
    for r in ok_rows:
        cid  = r["config_id"]
        inst = r["instance"]
        ridx = int(r["run_idx"])
        key  = (cid, inst, ridx)
        ref  = ref_points.get(inst)
        if ref is not None and key in fronts and len(fronts[key]) > 0:
            hv = _compute_hv(fronts[key], ref)
        else:
            hv = float(r.get("hv_raw", 0))
        hv_table.setdefault((cid, inst), []).append(hv)

    # Tabela por instância
    print(f"\n  {'Instância':<12}  {'Config':<6}  {'HV_med':>14}  {'HV_IQR':>10}  "
          f"{'Únicos':>7}  {'BestF1':>7}  Δ_vs_C1")
    print(f"  {'─'*72}")

    win_c9 = 0
    for inst in instances:
        hv_c1_med = np.median(hv_table.get(("C1", inst), [0]))
        hv_c9_med = np.median(hv_table.get(("C9", inst), [0]))
        if hv_c9_med > hv_c1_med:
            win_c9 += 1

        for cid in config_ids:
            hvs   = hv_table.get((cid, inst), [])
            inst_rows = [r for r in ok_rows if r["config_id"] == cid and r["instance"] == inst]
            uniq  = [int(r["n_unique_feasible"]) for r in inst_rows if r.get("n_unique_feasible")]
            f1s   = [float(r["best_f1"]) for r in inst_rows if r.get("best_f1")]

            hv_med = float(np.median(hvs)) if hvs else 0.0
            hv_iqr = float(np.subtract(*np.percentile(hvs, [75, 25]))) if len(hvs) > 1 else 0.0
            uniq_m = float(np.median(uniq)) if uniq else 0.0
            f1_m   = float(np.median(f1s))  if f1s  else float("nan")

            rel = ""
            if cid == "C9" and hv_c1_med > 0:
                pct = (hv_med / hv_c1_med - 1) * 100
                rel = f"{pct:+.1f}%%"

            print(f"  {inst if cid=='C1' else '':<12}  {cid:<6}  {hv_med:>14.2f}  "
                  f"{hv_iqr:>10.2f}  {uniq_m:>7.1f}  {f1_m:>7.1f}  {rel}")

    # Diagnóstico do cenário — só emite se ambas as configs têm dados
    has_c1 = any(hv_table.get(("C1", inst), [0]) and
                 max(hv_table.get(("C1", inst), [0])) > 0
                 for inst in instances)
    has_c9 = any(hv_table.get(("C9", inst), [0]) and
                 max(hv_table.get(("C9", inst), [0])) > 0
                 for inst in instances)

    print(f"\n{'─'*72}")
    if not (has_c1 and has_c9):
        configs_present = [c for c in ["C1", "C9"]
                           if any(hv_table.get((c, i), [0]) for i in instances)]
        print(f"  [INFO] Diagnóstico de cenário omitido: experimento parcial "
              f"(configs presentes: {configs_present}).")
        print(f"  Execute com ambas as configs (C1 e C9) para obter o diagnóstico completo.")
        scenario = "N/A — experimento parcial"
        msg = "Rode com --configs C1 C9 (ou sem --configs) para diagnóstico completo."
    else:
        print(f"  C9 > C1 em {win_c9} / {len(instances)} instâncias")
        if win_c9 >= 5:
            scenario = "A — Vantagem CONFIRMADA"
            msg = ("C9 (Weighted Sum) supera C1 (Tchebycheff) na maioria das instâncias.\n"
                   "  Justifica adotar Weighted Sum como configuração base do MOEA/D.")
        elif win_c9 >= 3:
            scenario = "B — Vantagem PARCIAL"
            msg = ("C9 supera C1 em algumas instâncias mas não em todas.\n"
                   "  O efeito pode depender do tipo de instância (C/R/RC ou 1xx/2xx).\n"
                   "  Investigar quais tipos beneficiam.")
        else:
            scenario = "C — Vantagem NÃO CONFIRMADA"
            msg = ("C9 não supera consistentemente C1 nas novas instâncias.\n"
                   "  O achado do tuning pode ser específico das 4 instâncias originais.\n"
                   "  Manter configuração canônica (C1) é defensável.")

    print(f"\n  CENÁRIO: {scenario}")
    print(f"  {msg}")

    # Relatório Markdown
    md_path = os.path.join(results_dir, "validation_gen_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Validação de Generalização — C1 vs C9\n\n")
        f.write(f"**Gerado em**: {datetime.now().isoformat(timespec='seconds')}\n\n")
        f.write(f"**Cenário**: {scenario}\n\n")
        f.write(f"C9 > C1 em {win_c9}/{len(instances)} instâncias.\n\n")
        f.write("## Resultados por Instância\n\n")
        f.write("| Instância | Config | HV med | HV IQR | Únicos | Best F1 | Δ% vs C1 |\n")
        f.write("|-----------|--------|--------|--------|--------|---------|----------|\n")
        for inst in instances:
            hv_c1 = np.median(hv_table.get(("C1", inst), [0]))
            for cid in config_ids:
                hvs  = hv_table.get((cid, inst), [])
                inst_rows = [r for r in ok_rows if r["config_id"] == cid and r["instance"] == inst]
                f1s  = [float(r["best_f1"]) for r in inst_rows if r.get("best_f1")]
                uniq = [int(r["n_unique_feasible"]) for r in inst_rows if r.get("n_unique_feasible")]
                hv_med = float(np.median(hvs)) if hvs else 0.0
                hv_iqr = float(np.subtract(*np.percentile(hvs, [75, 25]))) if len(hvs) > 1 else 0.0
                f1_m   = float(np.median(f1s)) if f1s else float("nan")
                uniq_m = float(np.median(uniq)) if uniq else 0.0
                rel = f"{(hv_med/hv_c1-1)*100:+.1f}" if cid == "C9" and hv_c1 > 0 else ""
                f.write(f"| {inst if cid=='C1' else ''} | {cid} | {hv_med:.2f} | "
                        f"{hv_iqr:.2f} | {uniq_m:.0f} | {f1_m:.1f} | {rel} |\n")

    csv_analysis = os.path.join(results_dir, "validation_gen_analysis.csv")
    analysis_rows = []
    for inst in instances:
        hv_c1 = np.median(hv_table.get(("C1", inst), [0]))
        for cid in config_ids:
            hvs = hv_table.get((cid, inst), [])
            analysis_rows.append({
                "config_id": cid, "instance": inst,
                "hv_median": round(float(np.median(hvs)) if hvs else 0, 4),
                "hv_iqr":    round(float(np.subtract(*np.percentile(hvs, [75, 25]))) if len(hvs) > 1 else 0, 4),
                "rel_vs_c1": round((float(np.median(hvs))/hv_c1-1)*100, 2) if cid == "C9" and hv_c1 > 0 else "",
                "n_runs":    len(hvs),
            })
    if analysis_rows:
        with open(csv_analysis, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=analysis_rows[0].keys())
            w.writeheader(); w.writerows(analysis_rows)

    print(f"\n  Relatório MD : {md_path}")
    print(f"  CSV análise  : {csv_analysis}")
    print(f"{'═'*72}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Generalização C1 vs C9 em 6 instâncias novas."
    )
    ap.add_argument("--dry-run",    action="store_true",
                    help="1 tarefa, 5k evals — verificação rápida")
    ap.add_argument("--n-evals",    type=int, default=None)
    ap.add_argument("--n-workers",  type=int, default=N_WORKERS)
    ap.add_argument("--n-runs",     type=int, default=N_RUNS)
    ap.add_argument("--instances",  nargs="+", default=None)
    ap.add_argument("--configs",    nargs="+", default=None)
    ap.add_argument("--results-dir", default=None)
    ap.add_argument("--analyze-only", action="store_true")
    args = ap.parse_args()

    n_evals   = 5_000 if args.dry_run else (args.n_evals or N_EVALS_FULL)
    n_workers = 1     if args.dry_run else args.n_workers
    n_runs    = 1     if args.dry_run else args.n_runs

    active_configs   = [c for c in CONFIGS if args.configs is None or c[0] in args.configs]
    active_instances = {k: v for k, v in INSTANCES.items()
                        if args.instances is None or k in args.instances}

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = args.results_dir or os.path.join(ROOT, "results",
                                                    f"validation_gen_{timestamp}")
    os.makedirs(results_dir, exist_ok=True)
    fronts_dir  = os.path.join(results_dir, "fronts")
    os.makedirs(fronts_dir, exist_ok=True)
    csv_path    = os.path.join(results_dir, "validation_gen_runs.csv")

    if args.analyze_only:
        analyze(results_dir, csv_path)
        return

    total_tasks = len(active_configs) * len(active_instances) * n_runs
    print("=" * 72)
    print("GENERALIZAÇÃO — C1 (Tchebycheff) vs C9 (Weighted Sum)")
    print("=" * 72)
    print(f"  Modo       : {'DRY-RUN' if args.dry_run else 'COMPLETO'}")
    print(f"  Configs    : {[c[0] for c in active_configs]}")
    print(f"  Instâncias : {list(active_instances.keys())}")
    print(f"  Runs       : {n_runs}  |  N_evals: {n_evals:,}")
    print(f"  Total tasks: {total_tasks}  |  Workers: {n_workers}")
    print(f"  Resultados : {results_dir}")
    print("=" * 72)

    # Retomada
    completed = set()
    if os.path.exists(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if not row.get("error", "").strip():
                    completed.add((row["config_id"], row["instance"], int(row["run_idx"])))
        if completed:
            print(f"\n  Retomada: {len(completed)} runs já completos")

    # Gera tasks
    tasks = []
    for cfg in active_configs:
        cid, clabel, nn, prob, decomp, theta = cfg
        for inst_name, inst_path in active_instances.items():
            for run_idx in range(1, n_runs + 1):
                key = (cid, inst_name, run_idx)
                if key in completed:
                    continue
                tasks.append({
                    "config_id":    cid,
                    "config_label": clabel,
                    "instance":     inst_name,
                    "inst_path":    inst_path,
                    "run_idx":      run_idx,
                    "seed":         _seed(cid, inst_name, run_idx),
                    "n_neighbors":  nn,
                    "prob":         prob,
                    "decomp":       decomp,
                    "theta":        theta,
                    "n_evals":      n_evals,
                })

    if not tasks:
        print("\n  Todas as tasks completas. Rodando análise...")
        analyze(results_dir, csv_path)
        return

    print(f"\n  Tasks restantes: {len(tasks)} / {total_tasks}")

    # CSV
    csv_new = not os.path.exists(csv_path)
    csv_file   = open(csv_path, "a", newline="", encoding="utf-8")
    csv_writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
    if csv_new:
        csv_writer.writeheader()
    csv_file.flush()

    # Progress header
    print(f"\n{'─'*72}")
    print(f"  {'#':>4}  {'Config':<6}  {'Instância':<12}  {'Run':<4}  "
          f"{'Evals':>8}  {'Feas':>5}  {'Únicos':>7}  {'HV_raw':>14}  {'Tempo':>9}")
    print(f"{'─'*72}")

    global_start = time.perf_counter()
    done_count   = len(completed)
    errors       = 0

    with Pool(processes=n_workers) as pool:
        for result in pool.imap_unordered(run_task, tasks):
            done_count += 1
            has_error = bool(result.get("error", "").strip())
            if has_error:
                errors += 1

            F_feas = result.pop("_F_feas", None)

            # Pickle da frente
            if F_feas is not None and len(F_feas) > 0:
                pname = f"{result['config_id']}__{result['instance']}__{result['run_idx']}.pkl"
                with open(os.path.join(fronts_dir, pname), "wb") as pf:
                    pickle.dump(F_feas, pf, protocol=4)

            # CSV
            csv_row = {k: result.get(k, "") for k in CSV_FIELDS}
            csv_writer.writerow(csv_row)
            csv_file.flush()

            elapsed_total = time.perf_counter() - global_start
            frac  = done_count / total_tasks
            eta_s = (elapsed_total / frac - elapsed_total) if frac > 0 else 0
            eta   = f"{int(eta_s//60)}m{int(eta_s%60):02d}s"

            print(f"  {done_count:>4}/{total_tasks}  "
                  f"{result['config_id']:<6}  {result['instance']:<12}  "
                  f"{result['run_idx']:<4}  "
                  f"{result.get('effective_evals', 0):>8,}  "
                  f"{result.get('n_feasible', 0):>5}  "
                  f"{result.get('n_unique_feasible', 0):>7}  "
                  f"{result.get('hv_raw', 0):>14.2f}  "
                  f"{result.get('elapsed_s', 0):>8.1f}s  "
                  f"{'ERRO' if has_error else 'ok'}  ETA:{eta}")

    csv_file.close()

    total_elapsed = time.perf_counter() - global_start
    h, rem = divmod(int(total_elapsed), 3600)
    m, s   = divmod(rem, 60)
    print(f"\n{'─'*72}")
    print(f"  Concluído em {h}h {m:02d}m {s:02d}s  |  Erros: {errors}/{len(tasks)}")

    analyze(results_dir, csv_path)


if __name__ == "__main__":
    main()
