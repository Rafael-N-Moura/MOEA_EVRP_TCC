#!/usr/bin/env python3
"""
Teste com CV como Quarto Objetivo (f4).
Sem Busca Local (k_max=0), Split Relaxado.
1 run de cada (NSGA-II, MOEA/D, SMS-EMOA), 100k evals.
"""

import sys, os, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymoo.core.problem import ElementwiseProblem
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.moo.moead import MOEAD
from pymoo.algorithms.moo.sms import SMSEMOA
from pymoo.optimize import minimize
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation
from pymoo.core.callback import Callback

from src import parse_instance, Decoder, TWBiasedSampling

class EVRPTW_4Obj(ElementwiseProblem):
    def __init__(self, ctx, k_max=0):
        self.context = ctx
        self.decoder = Decoder(ctx, k_max=k_max)
        super().__init__(
            n_var=ctx.n_customers,
            n_obj=4,
            n_ieq_constr=0,
            xl=0.0,
            xu=1.0
        )
        
    def _evaluate(self, x, out, *args, **kwargs):
        perm = np.argsort(x)
        F, cv = self.decoder.decode(perm)
        # F[0:3] -> f1, f2, f3; cv -> f4
        out["F"] = [F[0], F[1], F[2], cv]

class ConvergenceTracker(Callback):
    def __init__(self, interval=5000):
        super().__init__()
        self.interval = interval
        self._next = interval
        self.curve = []

    def notify(self, algorithm):
        n_eval = algorithm.evaluator.n_eval
        if n_eval < self._next and n_eval < 100000:
            return
        if n_eval >= self._next:
            self._next += self.interval

        F = algorithm.pop.get("F")
        if F is None or len(F) == 0:
            return
            
        # Pega o min de toda a população para cada objetivo
        min_f1 = float(F[:, 0].min())
        min_f2 = float(F[:, 1].min())
        min_f3 = float(F[:, 2].min())
        min_f4 = float(F[:, 3].min()) # f4 é o antigo cv
        
        self.curve.append((int(n_eval), min_f1, min_f2, min_f3, min_f4))


def _ops():
    return dict(
        sampling=TWBiasedSampling(),
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
    )

def _ref_dirs():
    try:
        from pymoo.util.ref_dirs import get_reference_directions
        return get_reference_directions("das-dennis", 4, n_partitions=7) # n_points = ~120
    except ImportError:
        from pymoo.util.reference_direction import get_reference_directions
        return get_reference_directions("das-dennis", 4, n_partitions=7)

def main():
    print("=" * 80)
    print("  TESTE: 4 OBJETIVOS (f4 = CV) — r201_21")
    print("  Sem Busca Local (k_max=0) | 100k evals | 1 run por algoritmo")
    print("=" * 80)

    ctx = parse_instance("evrptw_instances/r201_21.txt")
    prob_4obj = EVRPTW_4Obj(ctx, k_max=0)

    algos = {
        "NSGA-II": lambda: NSGA2(pop_size=100, eliminate_duplicates=True, **_ops()),
        "MOEA/D": lambda: MOEAD(ref_dirs=_ref_dirs(), n_neighbors=20, prob_neighbor_mating=0.7, **_ops()),
        "SMS-EMOA": lambda: SMSEMOA(pop_size=100, eliminate_duplicates=True, **_ops()),
    }

    results = {}

    for name, init_alg in algos.items():
        print(f"\n[{name}] Iniciando otimização...")
        alg = init_alg()
        cb = ConvergenceTracker(interval=10000)
        
        t0 = time.time()
        res = minimize(prob_4obj, alg, ("n_eval", 100_000), callback=cb, verbose=False, seed=42)
        tempo = time.time() - t0
        
        results[name] = cb.curve
        
        print(f"[{name}] Concluído em {tempo:.1f}s")
        print(f"{'Evals':>8} | {'min_f1':>8} | {'min_f2':>10} | {'min_f3':>10} | {'min_f4 (cv)':>12}")
        print("-" * 65)
        for ev, f1, f2, f3, f4 in cb.curve:
            print(f"{ev:>8} | {f1:>8.0f} | {f2:>10.1f} | {f3:>10.1f} | {f4:>12.4f}")

if __name__ == "__main__":
    main()
