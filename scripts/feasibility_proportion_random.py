#!/usr/bin/env python3
"""
Script para estimar a proporção de soluções factíveis (G2=0) no espaço de busca.

Gera N cromossomos aleatórios (permutações de clientes) e decodifica cada um nos três modos:
  - Conservador: force_battery_feasible=True (sempre visa G2=0)
  - Agressivo:   force_battery_feasible=False, use_radical_infeasible=False (perfil A, com estações)
  - Radical:     force_battery_feasible=False, use_radical_infeasible=True (sem estações)

Conta quantas soluções resultam com G2=0 (factíveis em bateria) em cada modo.

Uso:
  python scripts/feasibility_proportion_random.py <instância.txt> [--n N] [--seed S]
  python scripts/feasibility_proportion_random.py evrptw_instances/rc208_21.txt --n 1000
"""

import argparse
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import parse_instance, decode


def run_feasibility_sampling(context, n_chromosomes: int, seed=None):
    """
    Gera n_chromosomes permutações aleatórias e decodifica cada uma nos três modos.
    Retorna contagens de soluções factíveis (G2=0) por modo.
    """
    if seed is not None:
        np.random.seed(seed)
    n_customers = len(context.customers)

    count_feasible_conservative = 0
    count_feasible_aggressive = 0
    count_feasible_radical = 0

    for i in range(n_chromosomes):
        chrom = np.random.permutation(n_customers).astype(int).tolist()

        # Conservador
        sol_c = decode(
            chrom,
            context,
            force_battery_feasible=True,
            use_radical_infeasible=False,
        )
        if sol_c.battery_violation <= 0.0:
            count_feasible_conservative += 1

        # Agressivo
        sol_a = decode(
            chrom,
            context,
            force_battery_feasible=False,
            use_radical_infeasible=False,
        )
        if sol_a.battery_violation <= 0.0:
            count_feasible_aggressive += 1

        # Radical
        sol_r = decode(
            chrom,
            context,
            force_battery_feasible=False,
            use_radical_infeasible=True,
        )
        if sol_r.battery_violation <= 0.0:
            count_feasible_radical += 1

    return {
        "conservative": (count_feasible_conservative, n_chromosomes),
        "aggressive": (count_feasible_aggressive, n_chromosomes),
        "radical": (count_feasible_radical, n_chromosomes),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Estima proporção de soluções factíveis (G2=0) no espaço de busca (decoder conservador, agressivo e radical)."
    )
    parser.add_argument(
        "instance",
        type=str,
        nargs="?",
        default="evrptw_instances/rc208_21.txt",
        help="Caminho da instância EVRPTW (ex: evrptw_instances/rc208_21.txt)",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=1000,
        help="Número de cromossomos aleatórios a gerar (default: 1000)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Semente para reprodutibilidade",
    )
    args = parser.parse_args()

    instance_path = args.instance
    if not os.path.isfile(instance_path):
        print(f"Erro: arquivo de instância não encontrado: {instance_path}")
        sys.exit(1)

    print(f"Carregando instância: {instance_path}")
    context = parse_instance(instance_path)
    n_customers = len(context.customers)
    print(f"Clientes: {n_customers}, Estações: {len(context.stations)}")
    print(f"Gerando {args.n} cromossomos aleatórios e decodificando em 3 modos...")
    if args.seed is not None:
        print(f"Semente: {args.seed}")

    results = run_feasibility_sampling(context, args.n, seed=args.seed)

    print("\n" + "=" * 60)
    print("PROPORÇÃO DE SOLUÇÕES FACTÍVEIS (G2 = 0)")
    print("=" * 60)
    print(f"{'Modo':<14} {'Factíveis':>10} {'Total':>8} {'Proporção':>12}")
    print("-" * 60)
    for mode, (count, total) in results.items():
        pct = 100.0 * count / total if total else 0.0
        print(f"{mode:<14} {count:>10} {total:>8} {pct:>10.2f}%")
    print("=" * 60)
    print("\nInterpretação:")
    print("  - Conservador: por construção tende a G2=0; clientes impossíveis são pulados.")
    print("  - Agressivo:   usa estações com perfil A; parte das permutações pode resultar em G2=0.")
    print("  - Radical:     sem estações (só linha reta); espera-se poucas ou nenhuma com G2=0.")
    print()


if __name__ == "__main__":
    main()
