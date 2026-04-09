#!/usr/bin/env python3
"""
timing_large_instance.py
========================
Mede o tempo real de execução dos algoritmos NSGA-II, MOEA/D e SMS-EMOA
em uma instância grande do EVRPTW (padrão: r204_21.txt — 100 clientes).

Uso:
    python scripts/timing_large_instance.py
    python scripts/timing_large_instance.py --instance evrptw_instances/c101_21.txt
    python scripts/timing_large_instance.py --n-evals 20000 --runs 3

Saída:
    - Log em tempo real no terminal (run × algoritmo → tempo)
    - Tabela resumo final (média ± std por algoritmo)
    - CSV em results/timing_large_<instance>_<timestamp>.csv
    - JSON em results/timing_large_<instance>_<timestamp>.json
"""

import sys
import os
import time
import csv
import json
import platform
import argparse
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Garante que o root do projeto está no sys.path
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
from pymoo.algorithms.moo.nsga2  import NSGA2
from pymoo.algorithms.moo.moead  import MOEAD
from pymoo.algorithms.moo.sms    import SMSEMOA
from pymoo.optimize              import minimize
from pymoo.operators.crossover.ox      import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation
from pymoo.indicators.hv import HV

from src import parse_instance, EVRPTWProblem, TWBiasedSampling


# ---------------------------------------------------------------------------
# Padrões configuráveis via CLI
# ---------------------------------------------------------------------------
DEFAULT_INSTANCE = os.path.join(ROOT, "evrptw_instances", "r204_21.txt")
DEFAULT_N_EVALS  = 10_000   # avaliações por run (ajuste conforme tempo disponível)
DEFAULT_RUNS     = 3        # número de runs por algoritmo
DEFAULT_POP_SIZE = 100      # tamanho de população alvo

ALGORITHMS = ["NSGA-II", "MOEA/D", "SMS-EMOA"]


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------

def _get_ref_dirs(n_obj=3, n_partitions=13):
    try:
        from pymoo.util.ref_dirs import get_reference_directions
    except ImportError:
        from pymoo.util.reference_direction import get_reference_directions
    return get_reference_directions("das-dennis", n_obj, n_partitions=n_partitions)


def _operators():
    return dict(
        sampling=TWBiasedSampling(),
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
    )


def _build_algorithm(name: str, pop_size: int):
    """Instancia o algoritmo pelo nome."""
    ops = _operators()
    if name == "NSGA-II":
        return NSGA2(pop_size=pop_size, eliminate_duplicates=True, **ops)
    elif name == "MOEA/D":
        ref_dirs = _get_ref_dirs()
        return MOEAD(ref_dirs, n_neighbors=20, prob_neighbor_mating=0.7, **ops)
    elif name == "SMS-EMOA":
        return SMSEMOA(pop_size=pop_size, eliminate_duplicates=True, **ops)
    else:
        raise ValueError(f"Algoritmo desconhecido: {name}")


def _effective_pop(name: str, pop_size: int) -> int:
    """Retorna o tamanho de população efetivo (MOEA/D usa nº de direções)."""
    if name == "MOEA/D":
        return len(_get_ref_dirs())
    return pop_size


def _n_gen(n_evals: int, pop_size: int) -> int:
    return max(1, n_evals // pop_size)


def _compute_hv(res, ref_point):
    """HV sobre as soluções viáveis; retorna 0.0 se nenhuma."""
    cv_arr = res.pop.get("_cv")
    F_real = res.pop.get("_F_real")
    if cv_arr is None or F_real is None:
        return 0.0
    feasible = cv_arr[:, 0] <= 1e-9
    Ff = F_real[feasible]
    if len(Ff) == 0:
        return 0.0
    return float(HV(ref_point=ref_point)(Ff))


def _estimate_ref_point(problem, n_samples=200, seed=0):
    """Estima ref_point com amostras aleatórias (1.1 × max por objetivo)."""
    rng = np.random.default_rng(seed)
    n = problem.n_var
    F_list = []
    for _ in range(n_samples):
        x = rng.permutation(n)
        F, _ = problem.decoder.decode(x)
        F_list.append(F)
    F_arr = np.array(F_list)
    return F_arr.max(axis=0) * 1.1


def fmt_hms(seconds: float) -> str:
    """Formata segundos em h m s legível."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h:
        return f"{h}h {m:02d}m {s:04.1f}s"
    if m:
        return f"{m}m {s:04.1f}s"
    return f"{s:.2f}s"


def _machine_info() -> dict:
    return {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "node": platform.node(),
    }


# ---------------------------------------------------------------------------
# Execução de um único run
# ---------------------------------------------------------------------------

def run_once(algo_name: str, problem, pop_size: int, n_evals: int, seed: int, ref_point):
    """
    Executa um algoritmo por n_evals avaliações e retorna métricas de tempo.

    Returns
    -------
    dict com: elapsed_s, ms_per_eval, n_feasible, n_total, effective_evals, hv
    """
    eff_pop   = _effective_pop(algo_name, pop_size)
    n_gens    = _n_gen(n_evals, eff_pop)
    eff_evals = n_gens * eff_pop

    alg = _build_algorithm(algo_name, pop_size)

    wall_start = time.perf_counter()
    res = minimize(problem, alg, ("n_gen", n_gens), verbose=False, seed=seed)
    elapsed = time.perf_counter() - wall_start

    cv_arr = res.pop.get("_cv")
    n_total  = len(cv_arr) if cv_arr is not None else 0
    n_feas   = int(np.sum(cv_arr[:, 0] <= 1e-9)) if cv_arr is not None else 0

    hv = _compute_hv(res, ref_point)
    ms_per = (elapsed / eff_evals * 1000) if eff_evals > 0 else 0.0

    return {
        "elapsed_s":     round(elapsed, 3),
        "ms_per_eval":   round(ms_per, 4),
        "effective_pop":  eff_pop,
        "n_gens":         n_gens,
        "effective_evals": eff_evals,
        "n_feasible":    n_feas,
        "n_total":       n_total,
        "hv":            round(hv, 8),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Mede tempo de execução real dos 3 algoritmos em instância grande."
    )
    ap.add_argument(
        "--instance",
        default=DEFAULT_INSTANCE,
        help=f"Caminho para arquivo de instância (padrão: {DEFAULT_INSTANCE})"
    )
    ap.add_argument(
        "--n-evals", type=int, default=DEFAULT_N_EVALS,
        help=f"Avaliações alvo por run (padrão: {DEFAULT_N_EVALS})"
    )
    ap.add_argument(
        "--runs", type=int, default=DEFAULT_RUNS,
        help=f"Número de runs por algoritmo (padrão: {DEFAULT_RUNS})"
    )
    ap.add_argument(
        "--pop-size", type=int, default=DEFAULT_POP_SIZE,
        help=f"Tamanho de população (padrão: {DEFAULT_POP_SIZE})"
    )
    ap.add_argument(
        "--algorithms", nargs="+", default=ALGORITHMS,
        choices=ALGORITHMS,
        help="Algoritmos a executar (padrão: todos)"
    )
    ap.add_argument(
        "--seed-start", type=int, default=1,
        help="Seed inicial; seeds = seed_start, seed_start+1, ..."
    )
    args = ap.parse_args()

    # ── Cabeçalho ───────────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    inst_name = os.path.splitext(os.path.basename(args.instance))[0]
    machine   = _machine_info()

    print("=" * 72)
    print("TIMING — EVRPTW INSTÂNCIA GRANDE")
    print("=" * 72)
    print(f"  Instância  : {args.instance}")
    print(f"  Algoritmos : {', '.join(args.algorithms)}")
    print(f"  Runs       : {args.runs}  |  N_evals-alvo : {args.n_evals:,}")
    print(f"  Pop-size   : {args.pop_size}")
    print(f"  Máquina    : {machine['node']}  ({machine['platform']})")
    print(f"  Python     : {machine['python']}")
    print("=" * 72)

    # ── Carrega instância ────────────────────────────────────────────────
    print(f"\nCarregando: {args.instance}")
    ctx     = parse_instance(args.instance)
    problem = EVRPTWProblem(ctx)
    tws     = [c.due_date - c.ready_time for c in ctx.customers]

    print(f"  Clientes : {ctx.n_customers}")
    print(f"  Estações : {len(ctx.stations)}")
    print(f"  TW média : {np.mean(tws):.1f}  |  TW mín: {min(tws):.1f}  |  TW máx: {max(tws):.1f}")
    print(f"  Q={ctx.battery_capacity}  C={ctx.vehicle_capacity}  "
          f"r={ctx.consumption_rate}  g={ctx.recharge_rate}  v={ctx.velocity}")

    # ── Estima ref_point ────────────────────────────────────────────────
    print("\nEstimando ponto de referência (amostras aleatórias)…")
    ref_point = _estimate_ref_point(problem, n_samples=200, seed=0)
    print(f"  ref_point = {ref_point}")

    # ── Execução principal ───────────────────────────────────────────────
    seeds   = list(range(args.seed_start, args.seed_start + args.runs))
    records = []   # lista de dicts para CSV/JSON

    # timing_stats[algo] = lista de elapsed por run
    timing_stats = {a: [] for a in args.algorithms}

    global_start = time.perf_counter()

    for run_idx, seed in enumerate(seeds, start=1):
        print(f"\n{'─' * 60}")
        print(f"  RUN {run_idx}/{args.runs}  (seed={seed})")
        print(f"{'─' * 60}")

        for algo in args.algorithms:
            eff_pop   = _effective_pop(algo, args.pop_size)
            n_gens    = _n_gen(args.n_evals, eff_pop)
            eff_evals = n_gens * eff_pop

            print(f"\n  [{algo}]  pop={eff_pop}  n_gen={n_gens}  "
                  f"evals_reais={eff_evals:,}", end="", flush=True)

            metrics = run_once(algo, problem, args.pop_size, args.n_evals, seed, ref_point)

            timing_stats[algo].append(metrics["elapsed_s"])

            print(f"  →  {fmt_hms(metrics['elapsed_s'])}  "
                  f"({metrics['ms_per_eval']:.3f} ms/eval)  "
                  f"viáveis={metrics['n_feasible']}/{metrics['n_total']}  "
                  f"HV={metrics['hv']:.6f}")

            records.append({
                "timestamp":      timestamp,
                "instance":       inst_name,
                "run":            run_idx,
                "seed":           seed,
                "algorithm":      algo,
                "n_evals_target": args.n_evals,
                "effective_pop":  metrics["effective_pop"],
                "n_gens":         metrics["n_gens"],
                "effective_evals": metrics["effective_evals"],
                "elapsed_s":      metrics["elapsed_s"],
                "ms_per_eval":    metrics["ms_per_eval"],
                "n_feasible":     metrics["n_feasible"],
                "n_total":        metrics["n_total"],
                "hv":             metrics["hv"],
                "machine_node":   machine["node"],
                "platform":       machine["platform"],
                "python":         machine["python"],
            })

    global_elapsed = time.perf_counter() - global_start

    # ── Tabela resumo ────────────────────────────────────────────────────
    print(f"\n\n{'═' * 72}")
    print("RESUMO — TEMPO DE EXECUÇÃO POR ALGORITMO")
    print(f"{'═' * 72}")

    header = (f"{'Algoritmo':<12}"
              + "".join(f"{'Run '+str(i):>11}" for i in range(1, args.runs + 1))
              + f"{'Média':>11}"
              + f"{'±Std':>9}"
              + f"{'ms/eval (med)':>14}")
    print(header)
    print("─" * len(header))

    for algo in args.algorithms:
        run_times = timing_stats[algo]
        mean_t    = np.mean(run_times)
        std_t     = np.std(run_times)

        # ms/eval: usa os effective_evals do primeiro run deste algo
        eff_pop   = _effective_pop(algo, args.pop_size)
        eff_evals = _n_gen(args.n_evals, eff_pop) * eff_pop
        ms_med    = mean_t / eff_evals * 1000 if eff_evals > 0 else 0.0

        row = (f"{algo:<12}"
               + "".join(f"{fmt_hms(t):>11}" for t in run_times)
               + f"{fmt_hms(mean_t):>11}"
               + f"{std_t:>9.2f}s"
               + f"{ms_med:>14.3f}")
        print(row)

    print(f"{'═' * 72}")
    print(f"\n  Tempo total de execução do script : {fmt_hms(global_elapsed)}")

    # ── HV Resumo ────────────────────────────────────────────────────────
    print(f"\n{'─' * 72}")
    print("HV FINAL POR ALGORITMO (média ± std)")
    print(f"{'─' * 72}")
    for algo in args.algorithms:
        algo_recs = [r for r in records if r["algorithm"] == algo]
        hvs = [r["hv"] for r in algo_recs]
        print(f"  {algo:<10}: {np.mean(hvs):.6f} ± {np.std(hvs):.6f}  "
              f"(runs: {hvs})")

    # ── Exporta CSV ──────────────────────────────────────────────────────
    results_dir = os.path.join(ROOT, "results")
    os.makedirs(results_dir, exist_ok=True)

    csv_name  = f"timing_large_{inst_name}_{timestamp}.csv"
    csv_path  = os.path.join(results_dir, csv_name)
    json_name = f"timing_large_{inst_name}_{timestamp}.json"
    json_path = os.path.join(results_dir, json_name)

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    print(f"\n  CSV  salvo : {csv_path}")

    # ── Exporta JSON (com sumário estatístico) ───────────────────────────
    summary = {
        "meta": {
            "timestamp":      timestamp,
            "instance":       inst_name,
            "n_evals_target": args.n_evals,
            "pop_size":       args.pop_size,
            "runs":           args.runs,
            "seeds":          seeds,
            "machine":        machine,
        },
        "instance_info": {
            "n_customers": ctx.n_customers,
            "n_stations":  len(ctx.stations),
            "battery_capacity": ctx.battery_capacity,
            "vehicle_capacity": ctx.vehicle_capacity,
        },
        "ref_point": ref_point.tolist(),
        "results_by_algorithm": {},
        "records": records,
    }

    for algo in args.algorithms:
        algo_recs  = [r for r in records if r["algorithm"] == algo]
        run_times  = [r["elapsed_s"] for r in algo_recs]
        hvs        = [r["hv"] for r in algo_recs]
        ms_per_run = [r["ms_per_eval"] for r in algo_recs]

        summary["results_by_algorithm"][algo] = {
            "elapsed_s":   {"runs": run_times,
                             "mean": round(float(np.mean(run_times)), 3),
                             "std":  round(float(np.std(run_times)), 3)},
            "ms_per_eval": {"runs": ms_per_run,
                             "mean": round(float(np.mean(ms_per_run)), 4)},
            "hv":          {"runs": hvs,
                             "mean": round(float(np.mean(hvs)), 8),
                             "std":  round(float(np.std(hvs)), 8)},
            "n_feasible":  [r["n_feasible"] for r in algo_recs],
        }

    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  JSON salvo : {json_path}")

    print(f"\n{'═' * 72}")
    print("Execução concluída!")
    print(f"{'═' * 72}\n")


if __name__ == "__main__":
    main()
