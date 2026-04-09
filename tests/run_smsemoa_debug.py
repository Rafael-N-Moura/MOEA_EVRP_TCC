#!/usr/bin/env python3
import sys, os, time
sys.path.insert(0, '/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC')

import numpy as np
from pymoo.algorithms.moo.sms import SMSEMOA
from pymoo.optimize import minimize
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation
from pymoo.core.callback import Callback

from src import parse_instance, EVRPTWProblem, TWBiasedSampling

def run_instance(instance_path):
    print(f"\n=============================================")
    print(f" Rodando SMS-EMOA em {instance_path}")
    print(f"=============================================")
    ctx = parse_instance(instance_path)
    prob = EVRPTWProblem(ctx, k_max=0)
    
    alg = SMSEMOA(
        pop_size=100,
        sampling=TWBiasedSampling(),
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
        eliminate_duplicates=True
    )
    t0 = time.time()
    print(f"{'Evals':>7} | {'Feas':>4} | {'f1 (Min)':>10} | {'f2 (Min)':>10} | {'f3 (Min)':>10} | {'f3 (Avg)':>10} | {'f3 (Max)':>10}")
    print("-" * 80)
    
    class LivePrintCb(Callback):
        def __init__(self):
            super().__init__()
            self.next_eval = 0

        def notify(self, algorithm):
            n_eval = algorithm.evaluator.n_eval
            if n_eval >= self.next_eval or n_eval <= 200:
                if n_eval >= self.next_eval:
                    self.next_eval += 10000
                cv_arr = algorithm.pop.get("_cv")
                F_real = algorithm.pop.get("_F_real")
                if cv_arr is None or F_real is None:
                    return
                mask = cv_arr[:, 0] <= 1e-9
                nf = int(mask.sum())
                if nf > 0:
                    f1 = F_real[mask, 0].min()
                    f2 = F_real[mask, 1].min()
                    f3m = F_real[mask, 2].min()
                    f3avg = F_real[mask, 2].mean()
                    f3max = F_real[mask, 2].max()
                    print(f"{n_eval:7d} | {nf:4d} | {f1:10.0f} | {f2:10.1f} | {f3m:10.1f} | {f3avg:10.1f} | {f3max:10.1f}")
                else:
                    cvm = cv_arr[:, 0].min()
                    print(f"{n_eval:7d} | {nf:4d} | {'--':>10} | {'--':>10} | {'--':>10} | min_cv = {cvm:.4f}")

    res = minimize(prob, alg, ("n_eval", 100000), callback=LivePrintCb(), verbose=False, seed=42)
    print(f"-> Tempo total: {time.time() - t0:.1f}s")

if __name__ == "__main__":
    run_instance("/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/evrptw_instances/c101_21.txt")
    run_instance("/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/evrptw_instances/r201_21.txt")
