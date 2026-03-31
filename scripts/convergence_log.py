#!/usr/bin/env python3
"""
Log de convergência por geração (3 algoritmos: NSGA-II, MOEA/D, SMS-EMOA).

Para cada geração registra, entre indivíduos viáveis (cv ≈ 0):
  melhor f1, melhor f2, melhor f3 (objetivos reais, não penalizados),
  médias entre viáveis, nº de viáveis, n_eval acumulado, min_cv na população.

Se não houver viáveis na geração: best_* = vazio.

Uso:
    python scripts/convergence_log.py
    python scripts/convergence_log.py --instance evrptw_instances/c101_21.txt --k-max 0 --n-gen 100
    python scripts/convergence_log.py --instance evrptw_instances/c101_21.txt --k-max 0 --n-eval 100000
"""

import sys
import os
import argparse
import csv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from pymoo.core.callback import Callback
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.moo.moead import MOEAD
from pymoo.algorithms.moo.sms import SMSEMOA
from pymoo.optimize import minimize
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation

from src import parse_instance, EVRPTWProblem, TWBiasedSampling


def _ref_dirs():
    try:
        from pymoo.util.ref_dirs import get_reference_directions
    except ImportError:
        from pymoo.util.reference_direction import get_reference_directions
    return get_reference_directions("das-dennis", 3, n_partitions=13)


def _ops():
    return dict(
        sampling=TWBiasedSampling(),
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
    )


class GenerationLogger(Callback):
    def __init__(self, algorithm_name: str, out_rows: list):
        super().__init__()
        self.algorithm_name = algorithm_name
        self.rows = out_rows

    def notify(self, algorithm):
        gen = int(algorithm.n_gen)
        n_eval = int(algorithm.evaluator.n_eval)
        pop = algorithm.pop
        cv_arr = pop.get("_cv")
        F_real = pop.get("_F_real")

        if cv_arr is None or F_real is None:
            self.rows.append({
                "algorithm": self.algorithm_name,
                "generation": gen,
                "n_eval": n_eval,
                "n_feasible": 0,
                "best_f1": "",
                "best_f2": "",
                "best_f3": "",
                "mean_f1_feas": "",
                "mean_f2_feas": "",
                "mean_f3_feas": "",
                "min_cv_pop": "",
            })
            return

        mask = cv_arr[:, 0] <= 1e-9
        n_feas = int(mask.sum())
        min_cv = float(cv_arr[:, 0].min())

        row = {
            "algorithm": self.algorithm_name,
            "generation": gen,
            "n_eval": n_eval,
            "n_feasible": n_feas,
            "min_cv_pop": f"{min_cv:.6f}",
        }

        if n_feas > 0:
            Ff = F_real[mask]
            row["best_f1"] = f"{float(Ff[:, 0].min()):.4f}"
            row["best_f2"] = f"{float(Ff[:, 1].min()):.4f}"
            row["best_f3"] = f"{float(Ff[:, 2].min()):.4f}"
            row["mean_f1_feas"] = f"{float(Ff[:, 0].mean()):.4f}"
            row["mean_f2_feas"] = f"{float(Ff[:, 1].mean()):.4f}"
            row["mean_f3_feas"] = f"{float(Ff[:, 2].mean()):.4f}"
        else:
            row["best_f1"] = row["best_f2"] = row["best_f3"] = ""
            row["mean_f1_feas"] = row["mean_f2_feas"] = row["mean_f3_feas"] = ""

        self.rows.append(row)


def run_algorithm(name, alg_factory, problem, termination, seed, rows):
    cb = GenerationLogger(name, rows)
    alg = alg_factory()
    minimize(problem, alg, termination, callback=cb, verbose=False, seed=seed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--instance",
        default="evrptw_instances/c101C10.txt",
        help="Instância (default: c101C10 — 10 clientes, relativamente fácil)",
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument(
        "--n-gen",
        type=int,
        default=None,
        help="Parada por número de gerações (default: 120 se --n-eval omitido)",
    )
    g.add_argument(
        "--n-eval",
        type=int,
        default=None,
        help="Parada por número total de avaliações (substitui --n-gen)",
    )
    ap.add_argument("--pop-size", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--k-max",
        type=int,
        default=50,
        help="Intensidade da busca local no decoder (0 = desligada)",
    )
    ap.add_argument(
        "--out",
        default="results/convergence_log.csv",
        help="CSV com uma linha por (algoritmo × geração)",
    )
    args = ap.parse_args()

    if args.n_eval is not None:
        termination = ("n_eval", int(args.n_eval))
        stop_desc = f"n_eval = {args.n_eval:,}"
    else:
        n_gen = args.n_gen if args.n_gen is not None else 120
        termination = ("n_gen", n_gen)
        stop_desc = f"n_gen = {n_gen} (≈ {n_gen * args.pop_size:,} avaliações)"

    ctx = parse_instance(args.instance)
    problem = EVRPTWProblem(ctx, k_max=args.k_max)
    pop = args.pop_size

    print(f"Instância: {args.instance}")
    print(f"  Clientes: {ctx.n_customers}  |  Q={ctx.battery_capacity}  C={ctx.vehicle_capacity}")
    print(f"  k_max (busca local): {args.k_max}")
    print(f"  Parada: {stop_desc}  |  pop_size: {pop}")
    print()

    rows = []

    def nsga2():
        return NSGA2(pop_size=pop, eliminate_duplicates=True, **_ops())

    def moead():
        return MOEAD(
            _ref_dirs(),
            n_neighbors=20,
            prob_neighbor_mating=0.7,
            **_ops(),
        )

    def smsemoa():
        return SMSEMOA(pop_size=pop, eliminate_duplicates=True, **_ops())

    for name, factory in [
        ("NSGA-II", nsga2),
        ("MOEA/D", moead),
        ("SMS-EMOA", smsemoa),
    ]:
        print(f"Rodando {name}…")
        run_algorithm(name, factory, problem, termination, args.seed, rows)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    fieldnames = [
        "algorithm", "generation", "n_eval", "n_feasible",
        "best_f1", "best_f2", "best_f3",
        "mean_f1_feas", "mean_f2_feas", "mean_f3_feas",
        "min_cv_pop",
    ]
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"\nCSV completo: {args.out}")
    print("\n--- Amostra (primeiras 5 gerações de cada algoritmo) ---")
    for alg in ["NSGA-II", "MOEA/D", "SMS-EMOA"]:
        sub = [r for r in rows if r["algorithm"] == alg][:5]
        print(f"\n{alg}:")
        for r in sub:
            print(
                f"  gen {r['generation']:>3}  n_eval={r['n_eval']:<6}  "
                f"feas={r['n_feasible']:>3}  "
                f"best (f1,f2,f3)=({r['best_f1'] or '-':>8},{r['best_f2'] or '-':>10},{r['best_f3'] or '-':>10})  "
                f"min_cv={r['min_cv_pop']}"
            )

    print("\n--- Últimas 5 gerações de cada algoritmo ---")
    for alg in ["NSGA-II", "MOEA/D", "SMS-EMOA"]:
        sub = [r for r in rows if r["algorithm"] == alg][-5:]
        print(f"\n{alg}:")
        for r in sub:
            print(
                f"  gen {r['generation']:>3}  n_eval={r['n_eval']:<6}  "
                f"feas={r['n_feasible']:>3}  "
                f"best (f1,f2,f3)=({r['best_f1'] or '-':>8},{r['best_f2'] or '-':>10},{r['best_f3'] or '-':>10})  "
                f"min_cv={r['min_cv_pop']}"
            )


if __name__ == "__main__":
    main()
