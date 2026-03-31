#!/usr/bin/env python3
"""
Exporta a frente de Pareto final (não-dominada) do NSGA-II para uma instância.

Exporta apenas soluções VIÁVEIS (cv <= 1e-9), usando objetivos reais (_F_real),
e calcula a frente não-dominada nessa subpopulação viável.

Saída: CSV com uma linha por solução na frente, contendo f1, f2, f3.

Exemplo:
  python scripts/export_final_pareto_front.py \
    --instance evrptw_instances/r201_21.txt \
    --k-max 0 \
    --n-eval 100000 \
    --pop-size 100 \
    --seed 42 \
    --out results/pareto_front_r201_21_nsga2_no_ls_100k.csv
"""

import sys
import os
import argparse
import csv
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation

from src import parse_instance, EVRPTWProblem, TWBiasedSampling


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True, help="Caminho da instância .txt")
    ap.add_argument("--k-max", type=int, default=0, help="k_max do Decoder (0 = sem busca local)")
    ap.add_argument("--n-eval", type=int, default=100_000, help="Critério de parada (avaliações)")
    ap.add_argument("--pop-size", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", required=True, help="CSV de saída")
    args = ap.parse_args()

    ctx = parse_instance(args.instance)
    problem = EVRPTWProblem(ctx, k_max=args.k_max)

    alg = NSGA2(
        pop_size=args.pop_size,
        sampling=TWBiasedSampling(),
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
        eliminate_duplicates=True,
    )

    t0 = time.time()
    res = minimize(problem, alg, ("n_eval", int(args.n_eval)), verbose=False, seed=int(args.seed))
    elapsed = time.time() - t0

    pop = res.pop
    cv_arr = pop.get("_cv")
    F_real = pop.get("_F_real")

    if cv_arr is None or F_real is None:
        raise RuntimeError("População não contém _cv/_F_real; verifique src/problem.py")

    feas_mask = cv_arr[:, 0] <= 1e-9
    F_feas = F_real[feas_mask]

    if len(F_feas) == 0:
        print("Nenhuma solução viável na população final; nada a exportar.")
        return

    from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting
    nds = NonDominatedSorting()
    fronts = nds.do(F_feas)
    nd = F_feas[fronts[0]].copy()

    # Ordenação determinística: f1, f2, f3
    order = np.lexsort((nd[:, 2], nd[:, 1], nd[:, 0]))
    nd = nd[order]

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["f1", "f2", "f3"])
        for f1, f2, f3 in nd:
            w.writerow([f"{float(f1):.0f}", f"{float(f2):.6f}", f"{float(f3):.6f}"])

    print(f"Instância: {args.instance}")
    print(f"  k_max: {args.k_max} | pop: {args.pop_size} | n_eval: {args.n_eval} | seed: {args.seed}")
    print(f"  Tempo: {elapsed:.1f}s")
    print(f"  Pop final: {len(F_real)} ind. | Viáveis: {int(feas_mask.sum())}")
    print(f"  Frente não-dominada (viáveis): {len(nd)} soluções")
    print(f"CSV: {args.out}")


if __name__ == "__main__":
    main()

