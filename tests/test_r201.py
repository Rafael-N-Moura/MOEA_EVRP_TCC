#!/usr/bin/env python3
"""
Teste rápido do Split relaxado na instância r201_21 (menos restrita).
1 run NSGA-II, 100k evals, k_max=0 (sem LS).
"""

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation
from pymoo.core.callback import Callback

from src import parse_instance, EVRPTWProblem, TWBiasedSampling

class ConvergenceTracker(Callback):
    def __init__(self, interval=2000):
        super().__init__()
        self.interval = interval
        self._next = interval
        self.curve = []

    def notify(self, algorithm):
        n_eval = algorithm.evaluator.n_eval
        if n_eval < self._next:
            return
        self._next += self.interval

        cv_arr = algorithm.pop.get("_cv")
        F_real = algorithm.pop.get("_F_real")
        if cv_arr is None or F_real is None:
            return

        min_cv = float(cv_arr[:, 0].min())
        mask = cv_arr[:, 0] <= 1e-9
        n_feas = int(mask.sum())
        
        # Evolução do f1, f2, f3 da população inteira (incluindo inviáveis)
        min_f1 = float(F_real[:, 0].min())
        min_f2 = float(F_real[:, 1].min())
        min_f3 = float(F_real[:, 2].min())

        self.curve.append((int(n_eval), min_f1, min_f2, min_f3, min_cv, n_feas))

def main():
    print("=" * 70)
    print("  TESTE SPLIT RELAXADO - r201_21 (1 run, sem LS)")
    print("=" * 70)

    inst_path = "evrptw_instances/r201_21.txt"
    ctx = parse_instance(inst_path)
    prob = EVRPTWProblem(ctx, k_max=0)

    print(f"Instância: r201_21")
    print(f"Clientes: {ctx.n_customers}")
    print(f"Bateria (Q): {ctx.battery_capacity}")
    print(f"Capacidade (C): {ctx.vehicle_capacity}")
    
    cb = ConvergenceTracker(interval=5000)
    ops = dict(
        sampling=TWBiasedSampling(),
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
    )
    alg = NSGA2(pop_size=100, eliminate_duplicates=True, **ops)

    t0 = time.time()
    res = minimize(prob, alg, ("n_eval", 100_000), callback=cb, verbose=False, seed=42)
    elapsed = time.time() - t0

    cv_arr = res.pop.get("_cv")
    F_real = res.pop.get("_F_real")
    mask = cv_arr[:, 0] <= 1e-9
    n_feas = int(mask.sum())

    if n_feas > 0:
        Ff = F_real[mask]
        best_f1 = float(Ff[:, 0].min())
        best_f2 = float(Ff[:, 1].min())
    else:
        best_f1, best_f2 = np.nan, np.nan

    print(f"\nFinalizado em {elapsed:.1f}s")
    print(f"Viáveis: {n_feas}/{len(cv_arr)}")
    print(f"min_cv: {cv_arr[:, 0].min():.4f}")
    if n_feas > 0:
        print(f"f1_min: {best_f1:.0f}")
        print(f"f2_min: {best_f2:.2f}")

    print("\nConvergência (a cada 5k evals - extraídos independente de viabilidade):")
    print(f"{'Evals':>8} {'min_f1':>8} {'min_f2':>10} {'min_f3':>10} {'min_cv':>8} {'viáveis':>8}")
    print("-" * 58)
    for ev, f1, f2, f3, cv, nf in cb.curve:
        print(f"{ev:>8} {f1:>8.0f} {f2:>10.1f} {f3:>10.1f} {cv:>8.4f} {nf:>8}")

if __name__ == "__main__":
    main()
