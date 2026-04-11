#!/usr/bin/env python3
"""
main_experiment.py
==================
Experimento principal do TCC — EVRPTW tri-objetivo.

Três algoritmos × 56 instâncias × N_RUNS runs cada.
  nsga2    : NSGA-II (pop=100, eliminate_duplicates)
  moead_ws : MOEA/D  (pop=105 Das-Dennis, Weighted Sum, n_neighbors=10)
  smsemoa  : SMS-EMOA (pop=100, eliminate_duplicates)

Output por run (conforme output_formal.md):
  - pickle em results/main_experiment/pickles/{alg}/{inst}/run{idx:02d}.pkl
    contém: metadata, config, instance_info, final_population (F/CV/X),
            pareto_front (F/X), convergence_history (snapshots a cada 10k evals)
  - linha em results/main_experiment/index.csv

Paralelismo:
  - multiprocessing.Pool com N_WORKERS workers
  - OMP_NUM_THREADS=1 forçado em cada worker
  - Retomada: pula runs já no index.csv (status=ok)

Estimativa de tempo (sem local search, ~12ms/eval no i9):
  600k evals → ~120min/run
  56 instâncias × 3 algoritmos × 30 runs = 5040 runs totais
  Com 10 workers: ~1008 horas/10 = ~100 horas ≈ 4 dias
  Com 5 runs e seleção de 14 inst: 14×3×5 = 210 runs → ~42 horas ≈ 1.75 dias

  Use --n-runs e --instances para controlar escopo.

Uso:
  # Experimento completo (56 inst, 30 runs, 600k evals):
  python scripts/main_experiment.py 2>&1 | tee main_experiment.log

  # Subconjunto de teste:
  python scripts/main_experiment.py --n-evals 50000 --n-runs 2 --instances c101_21 r106_21

  # Dry-run (1 run por combo, 5k evals):
  python scripts/main_experiment.py --dry-run

  # Continuar após interrupção (mesmo results-dir):
  python scripts/main_experiment.py --results-dir results/main_experiment_20260412_031415

  # Apenas análise de ref_point e calibração (pós-experimento):
  python scripts/main_experiment.py --calibrate-only --results-dir results/main_experiment_...

Tmux (recomendado):
  tmux new -s main_exp
  python scripts/main_experiment.py 2>&1 | tee main_experiment.log
  Ctrl+B D   # detach
  tail -f main_experiment.log
"""

# Threading constraint ANTES de qualquer import numpy
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("BLIS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import sys, time, csv, json, pickle, hashlib, argparse, glob, warnings, traceback
from datetime import datetime
from multiprocessing import Pool

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np

# Importa módulo de I/O após definir ROOT
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from experiment_io import (
    ConvergenceCallback, build_instance_info, build_run_result,
    save_run, mark_run_error, get_git_commit, CSV_FIELDS,
)

# ─────────────────────────────────────────────────────────────────────────────
# Configurações do experimento
# ─────────────────────────────────────────────────────────────────────────────

N_EVALS_FULL = 600_000
N_WORKERS    = 10
N_RUNS       = 30
CONV_INTERVAL = 10_000   # snapshot a cada 10k evals → 60 snapshots em 600k

# Pop sizes — 105 para os três (valor natural de Das-Dennis H=13, 3 objetivos).
# NSGA-II e SMS-EMOA usam 105 para igualar o MOEA/D (comparação justa).
POP_NSGA2   = 105
POP_MOEAD   = 105   # Das-Dennis n_partitions=13, 3 objetivos → 105 pontos
POP_SMSEMOA = 105

# Algoritmos disponíveis
ALGORITHM_DEFS = {
    "nsga2": {
        "label":    "NSGA-II",
        "pop_size": POP_NSGA2,
        "config": {
            "pop_size":             POP_NSGA2,
            "crossover":            "OrderCrossover(prob=0.9)",
            "mutation":             "InversionMutation()",
            "eliminate_duplicates": True,
        },
    },
    "moead_ws": {
        "label":    "MOEA/D (Weighted Sum)",
        "pop_size": POP_MOEAD,
        "config": {
            "pop_size":             POP_MOEAD,
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
        "pop_size": POP_SMSEMOA,
        "config": {
            "pop_size":             POP_SMSEMOA,
            "crossover":            "OrderCrossover(prob=0.9)",
            "mutation":             "InversionMutation()",
            "eliminate_duplicates": True,
        },
    },
}

# Todas as 56 instâncias *_21.txt
def _discover_instances():
    pattern = os.path.join(ROOT, "evrptw_instances", "*_21.txt")
    paths   = sorted(glob.glob(pattern))
    return {os.path.basename(p).replace(".txt", ""): p for p in paths}

ALL_INSTANCES = _discover_instances()


# ─────────────────────────────────────────────────────────────────────────────
# Semente determinística
# ─────────────────────────────────────────────────────────────────────────────

def _seed(algorithm_id: str, instance_name: str, run_idx: int) -> int:
    key = f"{algorithm_id}_{instance_name}_{run_idx}"
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2 ** 32)


# ─────────────────────────────────────────────────────────────────────────────
# Construtores de algoritmo
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
        return NSGA2(pop_size=POP_NSGA2, eliminate_duplicates=True, **ops)

    elif algorithm_id == "moead_ws":
        from pymoo.algorithms.moo.moead import MOEAD
        from pymoo.decomposition.weighted_sum import WeightedSum
        return MOEAD(
            ref_dirs              = _get_ref_dirs(),
            n_neighbors           = 10,
            prob_neighbor_mating  = 0.9,
            decomposition         = WeightedSum(),
            **ops,
        )

    elif algorithm_id == "smsemoa":
        from pymoo.algorithms.moo.sms import SMSEMOA
        return SMSEMOA(pop_size=POP_SMSEMOA, eliminate_duplicates=True, **ops)

    else:
        raise ValueError(f"Algoritmo desconhecido: {algorithm_id!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Worker — executa um único run
# ─────────────────────────────────────────────────────────────────────────────

def run_task(task: dict) -> dict:
    """
    Executa um único run do experimento principal.
    Retorna um dict resumido para log em tempo real.
    O resultado completo já é salvo em disco pelo worker.
    """
    # Garante restrição de threads no processo filho
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
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
        "seed":         seed,
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
        t0 = time.perf_counter()
        res = minimize(problem, alg, ("n_eval", n_evals),
                       callback=cb, verbose=False, seed=seed)
        elapsed = time.perf_counter() - t0

        # Metadata completa
        pop_size = ALGORITHM_DEFS[algorithm_id]["pop_size"]
        metadata = {
            "algorithm_id":   algorithm_id,
            "instance":       inst_name,
            "run_idx":        run_idx,
            "seed":           seed,
            "n_evals_budget": n_evals,
            "pop_size":       pop_size,
            "timestamp_start": ts_start,
            "git_commit":     git_commit,
            "n_customers":    ctx.n_customers,
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

        pkl_rel, csv_row = save_run(result, experiment_dir, index_csv)

        # Resumo para log em tempo real
        F_p = result["pareto_front"]["F"]
        summary.update({
            "n_feasible": csv_row["n_feasible"],
            "n_pareto":   csv_row["n_pareto"],
            "hv_quick":   csv_row["hv_quick"],
            "best_f1":    csv_row["best_f1"],
            "elapsed_s":  round(elapsed, 1),
            "status":     "ok",
            "pkl_path":   pkl_rel,
        })

    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        summary["error_msg"] = err
        print(f"\n  [ERRO] {algorithm_id}/{inst_name}/run{run_idx}: {err}")
        traceback.print_exc()
        # Registra no CSV para rastreabilidade
        try:
            from experiment_io import mark_run_error
            mark_run_error(index_csv, algorithm_id, inst_name, run_idx, seed,
                           err, git_commit=git_commit)
        except Exception:
            pass

    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Calibração pós-experimento
# ─────────────────────────────────────────────────────────────────────────────

def calibrate(experiment_dir: str, index_csv: str):
    """
    Lê todos os pickles e calcula:
      1. reference_points.json — ref_point por instância (110% do pior valor
         entre todos os algoritmos e runs)
      2. reference_fronts/{inst}.pkl — frente de referência (união de todas
         as frentes Pareto não-dominadas de todos alg/runs por instância)

    Esses dados são a "calibração oficial" para HV e IGD+.
    """
    print(f"\n{'═'*72}")
    print("CALIBRAÇÃO PÓS-EXPERIMENTO")
    print(f"{'═'*72}")

    # Lê índice
    if not os.path.exists(index_csv):
        print("  index.csv não encontrado.")
        return

    rows = []
    with open(index_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status", "") == "ok" and row.get("pickle_path", ""):
                rows.append(row)

    if not rows:
        print("  Nenhum run com status=ok no index.csv.")
        return

    instances = sorted(set(r["instance"] for r in rows))
    print(f"  {len(rows)} runs ok  |  {len(instances)} instâncias")

    ref_points    = {}
    ref_fronts    = {}
    ref_front_dir = os.path.join(experiment_dir, "reference_fronts")
    os.makedirs(ref_front_dir, exist_ok=True)

    for inst in instances:
        inst_rows = [r for r in rows if r["instance"] == inst]
        all_F = []

        for r in inst_rows:
            pkl_path = os.path.join(experiment_dir, r["pickle_path"])
            if not os.path.exists(pkl_path):
                continue
            try:
                from experiment_io import load_run
                data  = load_run(pkl_path)
                F_p   = data["pareto_front"]["F"]
                if len(F_p) > 0:
                    all_F.append(F_p)
            except Exception as e:
                print(f"  [AVISO] Erro ao ler {pkl_path}: {e}")

        if not all_F:
            print(f"  [AVISO] Sem frentes válidas para {inst}")
            continue

        combined = np.vstack(all_F)

        # ref_point = 110% do pior valor observado por objetivo
        ref_points[inst] = (combined.max(axis=0) * 1.1).tolist()

        # Frente de referência = non-dominated da união de todas as frentes
        from experiment_io import _non_dominated
        ref_front     = _non_dominated(combined)
        ref_fronts[inst] = ref_front
        ref_front_path  = os.path.join(ref_front_dir, f"{inst}.pkl")
        with open(ref_front_path, "wb") as pf:
            pickle.dump(ref_front, pf, protocol=4)

        print(f"  {inst}: ref_point={[f'{v:.1f}' for v in ref_points[inst]]}  "
              f"ref_front_size={len(ref_front)}  ({len(all_F)} runs carregados)")

    # Salva reference_points.json
    rp_path = os.path.join(experiment_dir, "reference_points.json")
    with open(rp_path, "w") as f:
        json.dump(ref_points, f, indent=2)

    print(f"\n  reference_points.json → {rp_path}")
    print(f"  reference_fronts/     → {ref_front_dir}")
    print(f"{'═'*72}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Experimento principal EVRPTW — NSGA-II vs MOEA/D-WS vs SMS-EMOA"
    )
    ap.add_argument("--dry-run",    action="store_true",
                    help="1 run por combinação, 5k evals — verificação rápida")
    ap.add_argument("--n-evals",    type=int,  default=None,
                    help=f"Avaliações por run (padrão: {N_EVALS_FULL:,})")
    ap.add_argument("--n-runs",     type=int,  default=N_RUNS,
                    help=f"Runs por (algoritmo, instância) (padrão: {N_RUNS})")
    ap.add_argument("--n-workers",  type=int,  default=N_WORKERS,
                    help=f"Workers paralelos (padrão: {N_WORKERS})")
    ap.add_argument("--algorithms", nargs="+", default=None,
                    help="Subset de algoritmos ex: nsga2 moead_ws")
    ap.add_argument("--instances",  nargs="+", default=None,
                    help="Subset de instâncias ex: c101_21 r106_21")
    ap.add_argument("--results-dir", default=None,
                    help="Diretório de resultados (cria novo se não existir)")
    ap.add_argument("--calibrate-only", action="store_true",
                    help="Pula execução, só faz calibração (requer --results-dir)")
    ap.add_argument("--conv-interval", type=int, default=CONV_INTERVAL,
                    help=f"Evals entre snapshots de convergência (padrão: {CONV_INTERVAL:,})")
    args = ap.parse_args()

    # ── Parâmetros efetivos ────────────────────────────────────────────
    n_evals   = 5_000 if args.dry_run else (args.n_evals or N_EVALS_FULL)
    n_runs    = 1     if args.dry_run else args.n_runs
    n_workers = 1     if args.dry_run else args.n_workers

    active_algs  = {k: v for k, v in ALGORITHM_DEFS.items()
                    if args.algorithms is None or k in args.algorithms}
    active_insts = {k: v for k, v in ALL_INSTANCES.items()
                    if args.instances is None or k in args.instances}

    # ── Diretório de resultados ────────────────────────────────────────
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    exp_dir     = args.results_dir or os.path.join(ROOT, "results",
                                                    f"main_experiment_{timestamp}")
    os.makedirs(exp_dir, exist_ok=True)
    index_csv   = os.path.join(exp_dir, "index.csv")
    git_commit  = get_git_commit(ROOT)

    # ── Modo calibrate-only ───────────────────────────────────────────
    if args.calibrate_only:
        if not os.path.exists(index_csv):
            print(f"[ERRO] index.csv não encontrado em {exp_dir}")
            sys.exit(1)
        calibrate(exp_dir, index_csv)
        return

    # ── Cabeçalho ─────────────────────────────────────────────────────
    total_tasks = len(active_algs) * len(active_insts) * n_runs
    est_min_per_run = n_evals * 0.012 / 60   # ~12ms/eval sem LS
    est_wall_h = total_tasks * est_min_per_run / n_workers / 60

    print("=" * 72)
    print("EXPERIMENTO PRINCIPAL — EVRPTW TRI-OBJETIVO")
    print("=" * 72)
    print(f"  Modo        : {'DRY-RUN' if args.dry_run else 'COMPLETO'}")
    print(f"  Algoritmos  : {list(active_algs.keys())}")
    print(f"  Instâncias  : {len(active_insts)}  {'(todas)' if len(active_insts)==56 else list(active_insts.keys())}")
    print(f"  Runs        : {n_runs}  |  N_evals: {n_evals:,}")
    print(f"  Total tasks : {total_tasks}")
    print(f"  Workers     : {n_workers}")
    print(f"  ETA estim.  : ~{est_wall_h:.1f}h  ({est_min_per_run:.0f} min/run est.)")
    print(f"  git commit  : {git_commit}")
    print(f"  Resultados  : {exp_dir}")
    print("=" * 72)

    # ── Retomada — carrega runs já completos ──────────────────────────
    completed: set = set()
    if os.path.exists(index_csv):
        with open(index_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("status", "") == "ok":
                    completed.add((row["algorithm_id"], row["instance"],
                                   int(row["run_idx"])))
        if completed:
            print(f"\n  Retomada: {len(completed)} runs ok (serão pulados)")

    # ── Gera lista de tasks ───────────────────────────────────────────
    tasks = []
    for alg_id in active_algs:
        for inst_name, inst_path in active_insts.items():
            for run_idx in range(1, n_runs + 1):
                key = (alg_id, inst_name, run_idx)
                if key in completed:
                    continue
                tasks.append({
                    "algorithm_id":  alg_id,
                    "instance":      inst_name,
                    "inst_path":     inst_path,
                    "run_idx":       run_idx,
                    "seed":          _seed(alg_id, inst_name, run_idx),
                    "n_evals":       n_evals,
                    "experiment_dir": exp_dir,
                    "index_csv":     index_csv,
                    "git_commit":    git_commit,
                    "conv_interval": args.conv_interval,
                })

    if not tasks:
        print("\n  Todos os runs completos. Rodando calibração...")
        calibrate(exp_dir, index_csv)
        return

    # ── Embaralhamento determinístico ─────────────────────────────────
    # Evita que todos os runs de um mesmo (alg, inst) rodem juntos.
    # Problemas aparecem cedo; algoritmos diferentes ficam intercalados.
    import random as _random
    _random.seed(42)
    _random.shuffle(tasks)

    print(f"\n  Tasks restantes: {len(tasks)} / {total_tasks}  (embaralhadas, seed=42)")
    print(f"\n{'─'*72}")
    print(f"  {'#':>5}  {'Alg':<10}  {'Instância':<12}  {'Run':<4}  "
          f"{'Feas':>5}  {'Pareto':>7}  {'HV_quick':>14}  {'BestF1':>7}  "
          f"{'Tempo':>8}  Status")
    print(f"{'─'*72}")

    # ── Execução paralela ─────────────────────────────────────────────
    global_start  = time.perf_counter()
    done_count    = len(completed)
    error_count   = 0

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

            print(f"  {done_count:>5}/{total_tasks}  "
                  f"{s['algorithm_id']:<10}  {s['instance']:<12}  "
                  f"{s['run_idx']:<4}  "
                  f"{s.get('n_feasible',0):>5}  "
                  f"{s.get('n_pareto',0):>7}  "
                  f"{s.get('hv_quick',0):>14.2f}  "
                  f"{str(s.get('best_f1',''))[:6]:>7}  "
                  f"{s.get('elapsed_s',0):>7.1f}s  "
                  f"{'ERRO: '+s.get('error_msg','')[:30] if has_error else 'ok'}  ETA:{eta}")

    total_elapsed = time.perf_counter() - global_start
    h, rem = divmod(int(total_elapsed), 3600)
    m, s   = divmod(rem, 60)
    print(f"\n{'─'*72}")
    print(f"  Concluído em {h}h {m:02d}m {s:02d}s  |  Erros: {error_count}/{len(tasks)}")
    print(f"  index.csv   : {index_csv}")

    # ── Calibração automática ao final ────────────────────────────────
    calibrate(exp_dir, index_csv)


if __name__ == "__main__":
    main()
