#!/usr/bin/env python3
"""
pilot_experiment.py
===================
Experimento piloto do TCC — EVRPTW tri-objetivo.

  3 algoritmos × 4 instâncias × 10 runs × 850k avaliações = 120 runs

Propósito:
  - Validar critério de parada (850k = eps=2% da calibração)
  - Wilcoxon pareado entre pares com n=10 (poder estatístico suficiente)
  - Coletar dados de instâncias novas (c104_21, r110_21)
  - Estimar tempo real do run para dimensionar o experimento principal
  - Resultados integráveis ao experimento principal (mesmo formato de pickle)

Output:
  - results/pilot_{timestamp}/pickles/{alg}/{inst}/run{NN}.pkl
  - results/pilot_{timestamp}/index.csv
  - results/pilot_{timestamp}/pilot_quick_analysis.md

Seed: hash SHA-256 de "pilot_{alg}_{inst}_{run_idx}" — diferente da calibração
      ("calib_") e do experimento principal (sem prefixo).

Uso:
  # Dry-run (~30s — verifica pipeline sem custo):
  python scripts/pilot_experiment.py --dry-run

  # 1 run real de validação (~42 min):
  python scripts/pilot_experiment.py --n-runs 1 --instances c101_21 --algorithms nsga2

  # Piloto completo (rodar no tmux do servidor, ~8-9h):
  python scripts/pilot_experiment.py 2>&1 | tee pilot.log

  # Retomada após interrupção:
  python scripts/pilot_experiment.py --results-dir results/pilot_20260413_HHMMSS

  # Apenas análise dos pickles existentes (sem executar runs):
  python scripts/pilot_experiment.py --analyze-only \\
    --results-dir results/pilot_20260413_HHMMSS
"""

# ─── Threading constraints ANTES de qualquer import numpy ────────────────────
import os
os.environ.setdefault("OMP_NUM_THREADS",    "1")
os.environ.setdefault("MKL_NUM_THREADS",    "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("BLIS_NUM_THREADS",   "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import sys, time, csv, json, pickle, hashlib, argparse, glob, warnings, traceback, random
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
# Constantes — idênticas ao experimento principal exceto N_RUNS e N_EVALS
# ─────────────────────────────────────────────────────────────────────────────

N_EVALS_FULL  = 850_000   # eps=2% da calibração  (max(N*) = 700k × 1.2 ≈ 850k)
N_WORKERS     = 10
N_RUNS        = 10        # reduzido de 30; suficiente para Wilcoxon
POP_SIZE      = 105       # Das-Dennis H=13, 3 objetivos → 105 pontos
CONV_INTERVAL = 10_000    # snapshot a cada 10k evals → 85 snapshots em 850k

# 4 instâncias cobrindo: C-1xx restrita, C-1xx generaliz., R-1xx generaliz., R-2xx folgada
PILOT_INSTANCES = {
    "c101_21": os.path.join(ROOT, "evrptw_instances", "c101_21.txt"),
    "c104_21": os.path.join(ROOT, "evrptw_instances", "c104_21.txt"),
    "r110_21": os.path.join(ROOT, "evrptw_instances", "r110_21.txt"),
    "r201_21": os.path.join(ROOT, "evrptw_instances", "r201_21.txt"),
}

ALGORITHM_DEFS = {
    "nsga2": {
        "label":    "NSGA-II",
        "pop_size": POP_SIZE,
        "config": {
            "pop_size":             POP_SIZE,
            "crossover":            "OrderCrossover(prob=0.9)",
            "mutation":             "InversionMutation()",
            "eliminate_duplicates": True,
        },
    },
    "moead_ws": {
        "label":    "MOEA/D (Weighted Sum)",
        "pop_size": POP_SIZE,
        "config": {
            "pop_size":             POP_SIZE,
            "n_neighbors":          10,
            "prob_neighbor_mating": 0.9,
            "decomposition":        "weighted-sum",
            "crossover":            "OrderCrossover(prob=0.9)",
            "mutation":             "InversionMutation()",
            "ref_dirs":             "das-dennis(n_partitions=13)",
        },
    },
    "smsemoa": {
        "label":    "SMS-EMOA",
        "pop_size": POP_SIZE,
        "config": {
            "pop_size":             POP_SIZE,
            "crossover":            "OrderCrossover(prob=0.9)",
            "mutation":             "InversionMutation()",
            "eliminate_duplicates": True,
        },
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Seed determinística
# Prefixo "pilot_" garante seeds diferentes da calibração ("calib_") e
# do experimento principal (sem prefixo) — evita correlação acidental.
# ─────────────────────────────────────────────────────────────────────────────

def _seed(alg_id: str, inst_name: str, run_idx: int) -> int:
    key = f"pilot_{alg_id}_{inst_name}_{run_idx}"
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2 ** 32)


# ─────────────────────────────────────────────────────────────────────────────
# Construtor de algoritmo — idêntico ao main_experiment.py
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

    ops = dict(
        sampling  = TWBiasedSampling(),
        crossover = OrderCrossover(),
        mutation  = InversionMutation(),
    )

    if algorithm_id == "nsga2":
        from pymoo.algorithms.moo.nsga2 import NSGA2
        return NSGA2(pop_size=POP_SIZE, eliminate_duplicates=True, **ops)

    elif algorithm_id == "moead_ws":
        from pymoo.algorithms.moo.moead import MOEAD
        from pymoo.decomposition.weighted_sum import WeightedSum
        return MOEAD(
            ref_dirs             = _get_ref_dirs(),
            n_neighbors          = 10,
            prob_neighbor_mating = 0.9,
            decomposition        = WeightedSum(),
            **ops,
        )

    elif algorithm_id == "smsemoa":
        from pymoo.algorithms.moo.sms import SMSEMOA
        return SMSEMOA(pop_size=POP_SIZE, eliminate_duplicates=True, **ops)

    raise ValueError(f"Algoritmo desconhecido: {algorithm_id!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Worker — executa um único run
# ─────────────────────────────────────────────────────────────────────────────

def run_task(task: dict) -> dict:
    """
    Executa um único run do piloto.
    Salva pickle + linha CSV em disco e retorna resumo para log em tempo real.
    """
    # Garante restrição de threads no processo filho (Pool fork pode herdar errado)
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[var] = "1"

    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, "scripts"))

    algorithm_id  = task["algorithm_id"]
    inst_name     = task["instance"]
    inst_path     = task["inst_path"]
    run_idx       = task["run_idx"]
    seed          = task["seed"]
    n_evals       = task["n_evals"]
    experiment_dir = task["experiment_dir"]
    index_csv     = task["index_csv"]
    git_commit    = task["git_commit"]
    conv_interval = task.get("conv_interval", CONV_INTERVAL)

    summary = {
        "algorithm_id": algorithm_id,
        "instance":     inst_name,
        "run_idx":      run_idx,
        "n_evals":      n_evals,
        "n_feasible":   0,
        "n_pareto":     0,
        "hv_quick":     0.0,
        "best_f1":      "",
        "elapsed_s":    0.0,
        "status":       "error",
        "error_msg":    "",
    }

    try:
        from pymoo.optimize import minimize
        from src import parse_instance, EVRPTWProblem
        from experiment_io import (ConvergenceCallback, build_instance_info,
                                   build_run_result, save_run)

        ctx     = parse_instance(inst_path)
        problem = EVRPTWProblem(ctx, k_max=0)   # sem local search
        alg     = _build_algorithm(algorithm_id)
        cb      = ConvergenceCallback(interval=conv_interval)

        ts_start = datetime.now().isoformat(timespec="seconds")
        t0       = time.perf_counter()
        res      = minimize(problem, alg, ("n_eval", n_evals),
                            callback=cb, verbose=False, seed=seed)
        elapsed  = time.perf_counter() - t0

        metadata = {
            "algorithm_id":    algorithm_id,
            "instance":        inst_name,
            "run_idx":         run_idx,
            "seed":            seed,
            "n_evals_budget":  n_evals,
            "pop_size":        POP_SIZE,
            "timestamp_start": ts_start,
            "git_commit":      git_commit,
            "n_customers":     ctx.n_customers,
            "experiment_type": "pilot",          # identifica o tipo de experimento
        }

        inst_info = build_instance_info(ctx)
        config    = ALGORITHM_DEFS[algorithm_id]["config"].copy()

        result = build_run_result(
            metadata=metadata,
            config=config,
            instance_info=inst_info,
            pymoo_result=res,
            callback=cb,
            elapsed=elapsed,
        )

        _, csv_row = save_run(result, experiment_dir, index_csv)

        summary.update({
            "n_feasible": csv_row["n_feasible"],
            "n_pareto":   csv_row["n_pareto"],
            "hv_quick":   csv_row["hv_quick"],
            "best_f1":    csv_row["best_f1"],
            "elapsed_s":  round(elapsed, 1),
            "status":     "ok",
        })

    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        summary["error_msg"] = err
        print(f"\n  [ERRO] {algorithm_id}/{inst_name}/run{run_idx}: {err}")
        traceback.print_exc()
        try:
            from experiment_io import mark_run_error
            mark_run_error(index_csv, algorithm_id, inst_name, run_idx, seed,
                           err, git_commit=git_commit)
        except Exception:
            pass

    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Análise pós-hoc inline
# ─────────────────────────────────────────────────────────────────────────────

def quick_analysis(exp_dir: str, index_csv: str,
                   algorithms: list, instances: list) -> str:
    """
    Analisa os pickles gerados e produz pilot_quick_analysis.md.
    Calcula: HV mediano + IQR, IGD+, n_pareto, n_f1_layers, Wilcoxon entre pares.
    """
    from experiment_io import load_run, _non_dominated

    print(f"\n{'═'*72}")
    print("ANÁLISE PÓS-HOC DO PILOTO")
    print(f"{'═'*72}")

    # ── 1. Lê os pickles via index.csv ───────────────────────────────────────
    if not os.path.exists(index_csv):
        print("  index.csv não encontrado — análise pulada.")
        return ""

    runs_ok = []
    with open(index_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status", "") == "ok":
                runs_ok.append(row)

    if not runs_ok:
        print("  Nenhum run com status=ok — análise pulada.")
        return ""

    print(f"  {len(runs_ok)} runs ok")

    data = {}   # (alg, inst, run_idx) → run_dict
    for row in runs_ok:
        alg  = row["algorithm_id"]
        inst = row["instance"]
        ridx = int(row["run_idx"])
        pkl  = os.path.join(exp_dir, row["pickle_path"])
        if not os.path.exists(pkl):
            continue
        try:
            data[(alg, inst, ridx)] = load_run(pkl)
        except Exception as e:
            print(f"  [AVISO] Erro ao ler {pkl}: {e}")

    if not data:
        print("  Nenhum pickle legível — análise pulada.")
        return ""

    algs  = [a for a in algorithms if any(k[0] == a for k in data)]
    insts = [i for i in instances  if any(k[1] == i for k in data)]

    # ── 2. Frentes de referência por instância ────────────────────────────────
    ref_fronts = {}
    ref_points = {}
    for inst in insts:
        all_F = [d["pareto_front"]["F"] for k, d in data.items()
                 if k[1] == inst and len(d["pareto_front"]["F"]) > 0]
        if not all_F:
            continue
        combined      = np.vstack(all_F)
        ref_points[inst] = combined.max(axis=0) * 1.1
        ref_fronts[inst] = _non_dominated(combined)
        print(f"  {inst}: ref_front={len(ref_fronts[inst])} sols")

    # ── 3. Métricas por run ───────────────────────────────────────────────────
    def hv_val(F, ref):
        from pymoo.indicators.hv import HV
        if len(F) == 0 or ref is None: return 0.0
        mask = np.all(F < ref, axis=1)
        F_d  = F[mask]
        return float(HV(ref_point=ref)(F_d)) if len(F_d) > 0 else 0.0

    def igd_plus_val(F_approx, F_ref):
        if len(F_approx) == 0 or F_ref is None or len(F_ref) == 0:
            return float("nan")
        try:
            from pymoo.indicators.igd_plus import IGDPlus
            return float(IGDPlus(F_ref)(F_approx))
        except Exception:
            return float("nan")

    metrics = {}   # (alg, inst, run_idx) → {hv, igd_plus, n_pareto, n_f1_layers}
    for key, run in data.items():
        alg, inst, ridx = key
        F_p = run["pareto_front"]["F"]
        hv  = hv_val(F_p, ref_points.get(inst))
        igd = igd_plus_val(F_p, ref_fronts.get(inst))
        n_nd  = len(F_p)
        n_lay = int(len(np.unique(np.round(F_p[:, 0], 6)))) if n_nd > 0 else 0
        bf3   = float(F_p[:, 2].min()) if n_nd > 0 else float("nan")
        metrics[key] = {"hv": hv, "igd_plus": igd,
                        "n_pareto": n_nd, "n_f1_layers": n_lay, "best_f3": bf3}

    # ── 4. Agregação ──────────────────────────────────────────────────────────
    def agg(alg, inst, metric):
        vals = [metrics[(a, i, r)][metric] for (a, i, r) in metrics
                if a == alg and i == inst and not np.isnan(metrics[(a, i, r)][metric])]
        if not vals: return float("nan"), float("nan"), 0
        arr  = np.array(vals)
        q25, q75 = np.percentile(arr, [25, 75])
        return float(np.median(arr)), float(q75 - q25), len(vals)

    # ── 5. Wilcoxon entre pares (por instância) ───────────────────────────────
    def wilcoxon_p(alg_a, alg_b, inst, metric):
        """Wilcoxon signed-rank test bilateral — emparelha por run_idx."""
        vals_a, vals_b = [], []
        ridxs = sorted(set(k[2] for k in metrics if k[0] == alg_a and k[1] == inst))
        for r in ridxs:
            ka = (alg_a, inst, r);  kb = (alg_b, inst, r)
            if ka in metrics and kb in metrics:
                va = metrics[ka].get(metric, float("nan"))
                vb = metrics[kb].get(metric, float("nan"))
                if not np.isnan(va) and not np.isnan(vb):
                    vals_a.append(va);  vals_b.append(vb)
        if len(vals_a) < 4:
            return float("nan")
        try:
            from scipy.stats import wilcoxon
            _, p = wilcoxon(vals_a, vals_b, alternative="two-sided", zero_method="zsplit")
            return float(p)
        except Exception:
            return float("nan")

    # ── 6. Gera relatório Markdown ────────────────────────────────────────────
    ts  = datetime.now().isoformat(timespec="seconds")
    md  = []
    md.append("# Análise Rápida do Experimento Piloto\n")
    md.append(f"**Gerado em**: {ts}\n")
    md.append(f"**Algoritmos**: {', '.join(algs)}\n")
    md.append(f"**Instâncias**: {', '.join(insts)}\n")

    # Tabela HV
    md.append("\n## HV Mediano (+ IQR)\n")
    md.append("| Instância | " + " | ".join(f"{a} med (IQR)" for a in algs) + " | Vencedor |\n")
    md.append("|" + "---|" * (len(algs) + 2) + "\n")
    wins_hv = {a: 0 for a in algs}
    for inst in insts:
        cells = [inst]
        hvs   = {}
        for a in algs:
            med, iqr, n = agg(a, inst, "hv")
            hvs[a] = med
            cells.append(f"{med:.0f} ({iqr:.0f})" if not np.isnan(med) else "—")
        win = max((a for a in algs if not np.isnan(hvs.get(a, float("nan")))),
                  key=lambda a: hvs[a], default="—")
        wins_hv[win] = wins_hv.get(win, 0) + 1
        cells.append(win)
        md.append("| " + " | ".join(cells) + " |\n")
    md.append(f"\n**Vitórias**: {', '.join(f'{a}={wins_hv.get(a,0)}' for a in algs)}\n")

    # Tabela IGD+
    md.append("\n## IGD+ Mediano (+ IQR)\n")
    md.append("> Menor é melhor.\n\n")
    md.append("| Instância | " + " | ".join(f"{a} med (IQR)" for a in algs) + " | Vencedor |\n")
    md.append("|" + "---|" * (len(algs) + 2) + "\n")
    wins_igd = {a: 0 for a in algs}
    for inst in insts:
        cells = [inst]
        igds  = {}
        for a in algs:
            med, iqr, n = agg(a, inst, "igd_plus")
            igds[a] = med
            cells.append(f"{med:.2f} ({iqr:.2f})" if not np.isnan(med) else "—")
        win = min((a for a in algs if not np.isnan(igds.get(a, float("nan")))),
                  key=lambda a: igds[a], default="—")
        wins_igd[win] = wins_igd.get(win, 0) + 1
        cells.append(win)
        md.append("| " + " | ".join(cells) + " |\n")
    md.append(f"\n**Vitórias**: {', '.join(f'{a}={wins_igd.get(a,0)}' for a in algs)}\n")

    # Tabela n_pareto e n_f1_layers
    md.append("\n## Tamanho da Frente e Diversidade\n")
    md.append("| Instância | Algoritmo | n_pareto med | n_f1_layers med |\n")
    md.append("|---|---|---|---|\n")
    for inst in insts:
        for a in algs:
            nd_med, _, _  = agg(a, inst, "n_pareto")
            lay_med, _, _ = agg(a, inst, "n_f1_layers")
            md.append(f"| {inst} | {a} | {nd_med:.1f} | {lay_med:.1f} |\n")

    # Wilcoxon
    pairs = [("smsemoa", "nsga2"), ("smsemoa", "moead_ws"), ("nsga2", "moead_ws")]
    pairs = [(a, b) for (a, b) in pairs if a in algs and b in algs]

    md.append("\n## Wilcoxon Signed-Rank (bilateral, α=0.05)\n")
    md.append("> Comparação de HV mediano por instância.\n")
    md.append("> p < 0.05 → diferença estatisticamente significativa.\n\n")
    md.append("| Instância | Par | p-valor | Significativo? |\n")
    md.append("|---|---|---|---|\n")
    for inst in insts:
        for (a, b) in pairs:
            p = wilcoxon_p(a, b, inst, "hv")
            sig = "✅" if (not np.isnan(p) and p < 0.05) else "❌"
            p_str = f"{p:.4f}" if not np.isnan(p) else "n/a (n<4)"
            md.append(f"| {inst} | {a} vs {b} | {p_str} | {sig} |\n")

    # Estimativa de tempo por run
    elapsed_ok = []
    for row in runs_ok:
        try:
            elapsed_ok.append(float(row["elapsed_seconds"]))
        except (ValueError, KeyError):
            pass
    if elapsed_ok:
        median_s = float(np.median(elapsed_ok))
        md.append(f"\n## Tempo por Run\n")
        md.append(f"- Mediana: **{median_s/60:.1f} min** ({median_s:.0f}s)\n")
        md.append(f"- Mín: {min(elapsed_ok)/60:.1f} min  |  Máx: {max(elapsed_ok)/60:.1f} min\n")
        est_main_h = 56 * 3 * 30 * median_s / 10 / 3600
        md.append(f"- Estimativa experimento principal (56inst × 3alg × 30runs ÷ 10workers): "
                  f"**~{est_main_h:.0f}h**\n")

    # Salva
    md_path = os.path.join(exp_dir, "pilot_quick_analysis.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.writelines(md)

    # Imprime resumo no console
    print(f"\n  Vitórias HV  : {', '.join(f'{a}={wins_hv.get(a,0)}' for a in algs)}")
    print(f"  Vitórias IGD+: {', '.join(f'{a}={wins_igd.get(a,0)}' for a in algs)}")
    print(f"  pilot_quick_analysis.md → {md_path}")

    return md_path


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Experimento piloto EVRPTW — 3 alg × 4 inst × 10 runs"
    )
    ap.add_argument("--dry-run",     action="store_true",
                    help="1 run, 5k evals — verifica pipeline (~30s)")
    ap.add_argument("--n-evals",     type=int,   default=None,
                    help=f"Avaliações por run (padrão: {N_EVALS_FULL:,})")
    ap.add_argument("--n-runs",      type=int,   default=N_RUNS,
                    help=f"Runs por (algoritmo, instância) (padrão: {N_RUNS})")
    ap.add_argument("--n-workers",   type=int,   default=N_WORKERS,
                    help=f"Workers paralelos (padrão: {N_WORKERS})")
    ap.add_argument("--algorithms",  nargs="+",  default=None,
                    help="Subset de algoritmos ex: nsga2 moead_ws")
    ap.add_argument("--instances",   nargs="+",  default=None,
                    help="Subset de instâncias ex: c101_21 r201_21")
    ap.add_argument("--results-dir", default=None,
                    help="Diretório de resultados (cria com timestamp se omitido)")
    ap.add_argument("--analyze-only", action="store_true",
                    help="Pula execução — apenas analisa pickles existentes")
    ap.add_argument("--conv-interval", type=int, default=CONV_INTERVAL,
                    help=f"Eval entre snapshots (padrão: {CONV_INTERVAL:,})")
    args = ap.parse_args()

    # ── Parâmetros efetivos ───────────────────────────────────────────────────
    n_evals   = 5_000 if args.dry_run else (args.n_evals or N_EVALS_FULL)
    n_runs    = 1     if args.dry_run else args.n_runs
    n_workers = 1     if args.dry_run else args.n_workers

    active_algs  = {k: v for k, v in ALGORITHM_DEFS.items()
                    if args.algorithms is None or k in args.algorithms}
    active_insts = {k: v for k, v in PILOT_INSTANCES.items()
                    if args.instances is None or k in args.instances}

    if not active_algs:
        print(f"[ERRO] Algoritmos inválidos: {args.algorithms}")
        print(f"  Disponíveis: {list(ALGORITHM_DEFS.keys())}")
        sys.exit(1)

    if not active_insts:
        print(f"[ERRO] Instâncias não encontradas: {args.instances}")
        print(f"  Disponíveis: {list(PILOT_INSTANCES.keys())}")
        sys.exit(1)

    # ── Diretório de resultados ───────────────────────────────────────────────
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    exp_dir    = args.results_dir or os.path.join(ROOT, "results",
                                                   f"pilot_{timestamp}")
    os.makedirs(exp_dir, exist_ok=True)
    index_csv  = os.path.join(exp_dir, "index.csv")
    git_commit = get_git_commit(ROOT)

    # ── Modo analyze-only ─────────────────────────────────────────────────────
    if args.analyze_only:
        if not os.path.exists(index_csv):
            print(f"[ERRO] index.csv não encontrado em {exp_dir}")
            sys.exit(1)
        quick_analysis(exp_dir, index_csv,
                       list(active_algs.keys()), list(active_insts.keys()))
        return

    # ── Verifica paths das instâncias ─────────────────────────────────────────
    for name, path in active_insts.items():
        if not os.path.exists(path):
            print(f"[ERRO] Instância não encontrada: {path}")
            sys.exit(1)

    # ── Estimativa de tempo ───────────────────────────────────────────────────
    total_tasks    = len(active_algs) * len(active_insts) * n_runs
    est_s_per_run  = n_evals * 0.012     # ~12 ms/eval no i9
    est_wall_h     = total_tasks * est_s_per_run / n_workers / 3600

    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    print("=" * 72)
    print("EXPERIMENTO PILOTO — EVRPTW TRI-OBJETIVO")
    print("=" * 72)
    print(f"  Modo        : {'DRY-RUN (5k evals, 1 run, 1 worker)' if args.dry_run else 'PILOTO COMPLETO'}")
    print(f"  Algoritmos  : {list(active_algs.keys())}")
    print(f"  Instâncias  : {list(active_insts.keys())}")
    print(f"  Runs/combo  : {n_runs}  |  N_evals: {n_evals:,}")
    print(f"  Total tasks : {total_tasks}")
    print(f"  Workers     : {n_workers}")
    print(f"  ETA estim.  : ~{est_wall_h:.1f}h  ({est_s_per_run/60:.0f} min/run est.)")
    print(f"  git commit  : {git_commit}")
    print(f"  Resultados  : {exp_dir}")
    print("=" * 72)

    if not args.dry_run:
        print("\n  Verifique o espaço em disco antes de prosseguir.")
        print(f"  Estimativa de uso: ~{total_tasks * 10 // 1024 + 1}–"
              f"{total_tasks * 20 // 1024 + 1} GB (10–20 MB/pickle × {total_tasks})")

    # ── Retomada — carrega runs já completos ─────────────────────────────────
    completed: set = set()
    if os.path.exists(index_csv):
        with open(index_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("status", "") == "ok":
                    completed.add((row["algorithm_id"], row["instance"],
                                   int(row["run_idx"])))
        if completed:
            print(f"\n  Retomada: {len(completed)} runs ok (serão pulados)")

    # ── Gera lista de tasks ───────────────────────────────────────────────────
    tasks = []
    for alg_id in active_algs:
        for inst_name, inst_path in active_insts.items():
            for run_idx in range(1, n_runs + 1):
                if (alg_id, inst_name, run_idx) in completed:
                    continue
                tasks.append({
                    "algorithm_id":   alg_id,
                    "instance":       inst_name,
                    "inst_path":      inst_path,
                    "run_idx":        run_idx,
                    "seed":           _seed(alg_id, inst_name, run_idx),
                    "n_evals":        n_evals,
                    "experiment_dir": exp_dir,
                    "index_csv":      index_csv,
                    "git_commit":     git_commit,
                    "conv_interval":  args.conv_interval,
                })

    if not tasks:
        print("\n  Todos os runs completos. Rodando análise...")
        quick_analysis(exp_dir, index_csv,
                       list(active_algs.keys()), list(active_insts.keys()))
        return

    # Embaralhamento determinístico — intercala algoritmos e instâncias.
    # Problemas aparecem cedo; carga é distribuída uniformemente pelos workers.
    random.seed(42)
    random.shuffle(tasks)

    print(f"\n  Tasks restantes: {len(tasks)} / {total_tasks}  (embaralhadas, seed=42)")
    print(f"\n{'─'*72}")
    print(f"  {'#':>5}  {'Alg':<10}  {'Instância':<12}  {'Run':<4}  "
          f"{'Feas':>5}  {'Pareto':>7}  {'HV_quick':>14}  {'BestF1':>7}  "
          f"{'Tempo':>8}  Status")
    print(f"{'─'*72}")

    # ── Execução paralela ─────────────────────────────────────────────────────
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
            frac  = done_count / total_tasks if total_tasks > 0 else 1
            eta_s = (elapsed_total / frac - elapsed_total) if frac > 0 else 0
            eta   = f"{int(eta_s//3600)}h{int((eta_s%3600)//60):02d}m"

            status_str = (f"ERRO: {s.get('error_msg','')[:35]}"
                          if has_error else f"ok  ETA:{eta}")
            print(f"  {done_count:>5}/{total_tasks}  "
                  f"{s['algorithm_id']:<10}  {s['instance']:<12}  "
                  f"{s['run_idx']:<4}  "
                  f"{s.get('n_feasible',0):>5}  "
                  f"{s.get('n_pareto',0):>7}  "
                  f"{s.get('hv_quick',0):>14.2f}  "
                  f"{str(s.get('best_f1',''))[:6]:>7}  "
                  f"{s.get('elapsed_s',0):>7.1f}s  "
                  f"{status_str}")

    total_elapsed = time.perf_counter() - global_start
    h, rem = divmod(int(total_elapsed), 3600)
    m, secs = divmod(rem, 60)
    print(f"\n{'─'*72}")
    print(f"  Concluído em {h}h {m:02d}m {secs:02d}s  |  Erros: {error_count}/{len(tasks)}")
    print(f"  index.csv : {index_csv}")

    # ── Análise pós-hoc ───────────────────────────────────────────────────────
    quick_analysis(exp_dir, index_csv,
                   list(active_algs.keys()), list(active_insts.keys()))

    print(f"\n{'═'*72}")
    print("Piloto concluído.")
    print(f"{'═'*72}")
    print(f"\nPróximos passos:")
    print(f"  Análise completa (IGD+, spacing, spread, hipóteses):")
    print(f"    python scripts/analyze_metrics.py --results-dir {exp_dir}")


if __name__ == "__main__":
    main()
