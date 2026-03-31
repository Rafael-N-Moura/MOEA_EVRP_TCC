#!/usr/bin/env python3
"""
Benchmark de tempo — instâncias grandes (100 clientes).

Roda 5 000 avaliações com cada um dos 3 algoritmos em 3 instâncias
representativas (uma por família C / R / RC) e extrapola:
  - tempo por avaliação (ms/eval)
  - tempo estimado para N evals de interesse
  - soluções factíveis na frente final
"""

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from pymoo.algorithms.moo.nsga2  import NSGA2
from pymoo.algorithms.moo.moead  import MOEAD
from pymoo.algorithms.moo.sms    import SMSEMOA
from pymoo.optimize              import minimize
from pymoo.operators.crossover.ox      import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation

from src import parse_instance, EVRPTWProblem, TWBiasedSampling

# ── Instâncias de benchmark ───────────────────────────────────────────
BENCH_INSTANCES = {
    "c101_21":  "evrptw_instances/c101_21.txt",   # C – TW apertada
    "r204_21":  "evrptw_instances/r204_21.txt",   # R – TW folgada
    "rc101_21": "evrptw_instances/rc101_21.txt",  # RC – misto
}

# Avaliações no benchmark; os valores de interesse são extrapolados
BENCH_EVALS = 5_000

# Horizontes para extrapolação (ajuste conforme necessidade)
EXTRAPOL_TARGETS = [20_000, 50_000, 100_000, 175_000, 500_000]

POP_SIZE = 100
SEED     = 42


# ── Fábrica de algoritmos ─────────────────────────────────────────────
def _ops():
    return dict(
        sampling=TWBiasedSampling(),
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
    )

def _ref_dirs():
    try:
        from pymoo.util.ref_dirs import get_reference_directions
    except ImportError:
        from pymoo.util.reference_direction import get_reference_directions
    return get_reference_directions("das-dennis", 3, n_partitions=13)

ALGORITHMS = {
    "NSGA-II":  lambda: NSGA2(pop_size=POP_SIZE, eliminate_duplicates=True, **_ops()),
    "MOEA/D":   lambda: MOEAD(_ref_dirs(), n_neighbors=20,
                               prob_neighbor_mating=0.7, **_ops()),
    "SMS-EMOA": lambda: SMSEMOA(pop_size=POP_SIZE, eliminate_duplicates=True, **_ops()),
}


# ── Execução ──────────────────────────────────────────────────────────
def bench_one(alg_name, alg_fn, problem):
    alg = alg_fn()
    t0  = time.time()
    res = minimize(problem, alg, ("n_eval", BENCH_EVALS), verbose=False, seed=SEED)
    elapsed = time.time() - t0

    cv_arr = res.pop.get("_cv")
    n_feas = int(np.sum(cv_arr[:, 0] <= 1e-9)) if cv_arr is not None else 0
    ms_per = elapsed / BENCH_EVALS * 1000

    extrap = {n: elapsed / BENCH_EVALS * n for n in EXTRAPOL_TARGETS}
    return elapsed, ms_per, n_feas, extrap


def fmt_hms(s):
    h = int(s // 3600); m = int((s % 3600) // 60); sec = s % 60
    if h:    return f"{h}h {m:02d}m {sec:04.1f}s"
    if m:    return f"{m}m {sec:04.1f}s"
    return f"{sec:.1f}s"


def main():
    print("=" * 72)
    print(f"BENCHMARK DE TEMPO  —  {BENCH_EVALS:,} avaliações × 3 algoritmos × 3 instâncias")
    print("=" * 72)

    # Cabeçalho da tabela de extrapolação
    tgt_header = "   ".join(f"{n//1000:>6}k" for n in EXTRAPOL_TARGETS)
    print(f"\n{'Instância':<11}  {'Algoritmo':<9}  "
          f"{'ms/eval':>7}  {'factíveis':>9}  {tgt_header}")
    print("─" * 72)

    timing_data = {}   # (inst, alg) → elapsed

    for inst_name, inst_path in BENCH_INSTANCES.items():
        ctx     = parse_instance(inst_path)
        problem = EVRPTWProblem(ctx)
        tws     = [c.due_date - c.ready_time for c in ctx.customers]

        print(f"\n  {inst_name}  ({ctx.n_customers} clientes, "
              f"TW média={np.mean(tws):.0f}, "
              f"Q={ctx.battery_capacity:.1f}, C={ctx.vehicle_capacity:.0f})")

        for alg_name, alg_fn in ALGORITHMS.items():
            elapsed, ms_per, n_feas, extrap = bench_one(alg_name, alg_fn, problem)

            ext_str = "   ".join(fmt_hms(v).rjust(9) for v in extrap.values())
            print(f"  {inst_name:<11}  {alg_name:<9}  "
                  f"{ms_per:>7.2f}  {n_feas:>9}  {ext_str}")

            timing_data[(inst_name, alg_name)] = {"ms_per_eval": ms_per,
                                                   "n_feas": n_feas,
                                                   "extrap": extrap}

    # ── Resumo: experimento primário ─────────────────────────────────
    print(f"\n{'=' * 72}")
    print("ESTIMATIVA DO EXPERIMENTO PRIMÁRIO")
    print(f"  (18 instâncias × 3 algoritmos × 31 runs = 1 674 jobs)")
    print(f"{'=' * 72}")

    # Criterios por classe (usa calibração se existir)
    import json
    cal_path = "results/calibration/calibration_summary.json"
    if os.path.exists(cal_path):
        with open(cal_path) as f:
            cal = json.load(f)
        crit_small = cal.get("criterion_small", 38_000)
        crit_large = cal.get("criterion_large", 175_000)
        print(f"  Critérios (calibração): small={crit_small:,}  large={crit_large:,}")
    else:
        crit_small, crit_large = 38_000, 175_000
        print(f"  Critérios (default):    small={crit_small:,}  large={crit_large:,}")

    print()
    for alg_name in ALGORITHMS:
        # Média de ms/eval para instâncias grandes
        samples = [v["ms_per_eval"] for (i, a), v in timing_data.items() if a == alg_name]
        avg_ms  = np.mean(samples)

        # 18 instâncias: ~9 small (C10/C15) + 9 large (_21)
        n_small, n_large = 9, 9
        n_runs = 31
        t_small = n_small * n_runs * avg_ms / 1000 * crit_small
        t_large = n_large * n_runs * avg_ms / 1000 * crit_large
        t_total = t_small + t_large

        print(f"  {alg_name:<9}: {avg_ms:.2f} ms/eval  "
              f"→ small≈{fmt_hms(t_small)}  "
              f"large≈{fmt_hms(t_large)}  "
              f"TOTAL≈{fmt_hms(t_total)}")

    print()
    print("  * estimativa com 1 processo série, sem paralelismo")
    print("  * instâncias small usam média de ms/eval das grandes (conservador)")
    print("=" * 72)


if __name__ == "__main__":
    main()
