#!/usr/bin/env python3
"""
Teste de integridade do BatteryFocusedNSGA2: modo 100% conservador vs NSGA-II normal.

Condições do teste (simulam NSGA-II normal):
- População inicial 100% avaliada com decoder conservador (force_battery_feasible=True).
- Cruzamento apenas viável × viável (feasible_mating_ratio=1.0).
- Offspring 100% avaliada com decoder conservador (todos vêm de F×F).
- Proporção de inviáveis 0 (infeasible_ratio=0).

Com isso, os resultados do BatteryFocused devem ser próximos ao NSGA-II padrão
(mesma instância, mesmo seed, mesmas gerações e população). Compara tamanho da
frente de Pareto, min/média de f1 e f2.
"""

import os
import sys
import argparse
import numpy as np
from pymoo.optimize import minimize
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation

# Garante que o projeto está no path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import parse_instance, EVRPTWProblem
from src.battery_focused_nsga2 import BatteryFocusedNSGA2
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.operators.sampling.rnd import PermutationRandomSampling


def run_nsga2_standard(problem, n_gen, pop_size, seed):
    """Executa NSGA-II padrão (sempre decoder conservador)."""
    algo = NSGA2(
        pop_size=pop_size,
        sampling=PermutationRandomSampling(),
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
        eliminate_duplicates=True,
    )
    res = minimize(problem, algo, ("n_gen", n_gen), seed=seed, verbose=False)
    return res


def run_battery_focused_baseline(problem, n_gen, pop_size, seed):
    """Executa BatteryFocusedNSGA2 em modo baseline: 100% conservador, 100% F×F."""
    algo = BatteryFocusedNSGA2(
        pop_size=pop_size,
        infeasible_ratio=0.0,
        feasible_mating_ratio=1.0,
        all_conservative_init=True,
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
        eliminate_duplicates=True,
    )
    res = minimize(problem, algo, ("n_gen", n_gen), seed=seed, verbose=False)
    return res


def main():
    parser = argparse.ArgumentParser(
        description="Teste de integridade: BatteryFocused em modo 100%% conservador vs NSGA-II"
    )
    parser.add_argument(
        "instance",
        nargs="?",
        default="evrptw_instances/rc208_21.txt",
        help="Caminho da instância EVRPTW",
    )
    parser.add_argument("--n-gen", type=int, default=50, help="Gerações")
    parser.add_argument("--pop-size", type=int, default=100, help="Tamanho da população")
    parser.add_argument("--seed", type=int, default=42, help="Seed para reprodutibilidade")
    parser.add_argument("--verbose", action="store_true", help="Mostrar saída dos algoritmos")
    args = parser.parse_args()

    instance_path = args.instance
    if not os.path.isabs(instance_path):
        instance_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            instance_path,
        )
    if not os.path.isfile(instance_path):
        print(f"Instância não encontrada: {instance_path}")
        sys.exit(1)

    print("=" * 70)
    print("TESTE DE INTEGRIDADE: BatteryFocused (100% conservador) vs NSGA-II")
    print("=" * 70)
    print(f"Instância: {instance_path}")
    print(f"Gerações: {args.n_gen} | População: {args.pop_size} | Seed: {args.seed}")
    print()

    context = parse_instance(instance_path)
    n_gen, pop_size, seed = args.n_gen, args.pop_size, args.seed

    # Problema NSGA-II: decoder conservador, sem restrições explícitas (penalização implícita)
    problem_nsga2 = EVRPTWProblem(
        context,
        use_constraints=False,
        force_battery_feasible=True,
    )

    # Problema BatteryFocused: com restrições (G2); algoritmo força conservador no teste
    problem_battery = EVRPTWProblem(
        context,
        use_constraints=True,
        force_battery_feasible=False,
    )

    verbose = args.verbose
    print("Rodando NSGA-II padrão...")
    res_nsga2 = run_nsga2_standard(problem_nsga2, n_gen, pop_size, seed)
    F_nsga2 = res_nsga2.F
    print("Rodando BatteryFocused (modo baseline: 100% conservador, 100% F×F)...")
    res_battery = run_battery_focused_baseline(problem_battery, n_gen, pop_size, seed)
    F_battery = res_battery.F

    # Comparação
    print()
    print("=" * 70)
    print("RESULTADOS")
    print("=" * 70)

    def stats(name, F):
        if F is None or len(F) == 0:
            print(f"  {name}: nenhuma solução na frente de Pareto")
            return
        f1, f2 = F[:, 0], F[:, 1]
        print(f"  {name}:")
        print(f"    Tamanho da frente: {len(F)}")
        print(f"    f1 (custo):       min={f1.min():.2f}, mean={f1.mean():.2f}, max={f1.max():.2f}")
        print(f"    f2 (insat.):     min={f2.min():.4f}, mean={f2.mean():.4f}, max={f2.max():.4f}")

    stats("NSGA-II (padrão)", F_nsga2)
    print()
    stats("BatteryFocused (baseline)", F_battery)

    print()
    print("Comparação direta:")
    if F_nsga2 is not None and len(F_nsga2) > 0 and F_battery is not None and len(F_battery) > 0:
        diff_f1_min = abs(F_battery[:, 0].min() - F_nsga2[:, 0].min())
        diff_f1_mean = abs(F_battery[:, 0].mean() - F_nsga2[:, 0].mean())
        diff_f2_min = abs(F_battery[:, 1].min() - F_nsga2[:, 1].min())
        print(f"  Diferença |f1_min|:   {diff_f1_min:.2f}")
        print(f"  Diferença |f1_mean|:  {diff_f1_mean:.2f}")
        print(f"  Diferença |f2_min|:   {diff_f2_min:.4f}")
        # Critério: mesma ordem de grandeza e frente de Pareto não vazia
        rel_f1 = diff_f1_min / (F_nsga2[:, 0].min() + 1e-12)
        rel_f2 = diff_f2_min / (F_nsga2[:, 1].min() + 1e-12)
        print()
        if rel_f1 < 0.15 and rel_f2 < 0.2:
            print("  Conclusão: resultados na mesma faixa (integridade OK; pequenas diferenças são esperadas")
            print("             pois a sobrevivência do BatteryFocused difere do NSGA-II padrão).")
        else:
            print("  Conclusão: diferenças grandes; verificar decoder, seed ou aumentar n_gen.")
    else:
        print("  Não foi possível comparar (uma das frentes está vazia).")

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
