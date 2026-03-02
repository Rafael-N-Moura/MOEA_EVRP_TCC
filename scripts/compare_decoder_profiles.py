#!/usr/bin/env python3
"""
Script de comparação entre decoder em modo conservador e modo agressivo.

Gera N permutações aleatórias de clientes e decodifica cada uma duas vezes:
  - Conservador: force_battery_feasible=True (perfil C — b_safe alto, buffer grande, Smart Detour)
  - Agressivo:   force_battery_feasible=False, use_radical_infeasible=False (perfil A — b_safe baixo, buffer pequeno, estação mais próxima)

Compara métricas: f1 (custo), f2 (insatisfação), G2 (violação bateria), veículos, distância, número de recargas, clientes não visitados.

Uso:
  python scripts/compare_decoder_profiles.py <instância.txt> [--n-permutations N] [--seed S] [--output arquivo.csv]
"""

import argparse
import os
import sys
import numpy as np

# Permite importar src a partir da raiz do projeto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import parse_instance, decode
from src.model import NodeType


def count_recharges(solution):
    """Conta quantas paradas em estação de recarga existem na solução."""
    n = 0
    for route in solution.routes:
        for step in route.steps:
            if step.node.type == NodeType.STATION:
                n += 1
    return n


def extract_metrics(solution):
    """Extrai métricas de uma solução decodificada."""
    return {
        "f1": solution.total_cost,
        "f2": solution.avg_dissatisfaction,
        "g2": solution.battery_violation,
        "n_vehicles": solution.total_vehicles,
        "total_distance": solution.total_distance,
        "n_recharges": count_recharges(solution),
        "n_skipped": len(solution.skipped_customer_ids),
        "feasible": solution.battery_violation <= 0.0,
    }


def run_comparison(context, n_permutations, seed=None):
    """
    Gera n_permutations permutações aleatórias e decodifica cada uma em modo conservador e agressivo.

    Returns:
        list of dicts: cada elemento tem "perm_id", "conservative", "aggressive" (dicts de métricas).
    """
    if seed is not None:
        np.random.seed(seed)
    n_customers = len(context.customers)
    results = []
    for i in range(n_permutations):
        perm = np.random.permutation(n_customers).astype(int).tolist()
        # Modo conservador (perfil C)
        sol_c = decode(
            perm,
            context,
            force_battery_feasible=True,
            use_radical_infeasible=False,
        )
        # Modo agressivo (perfil A) — com estações, não radical
        sol_a = decode(
            perm,
            context,
            force_battery_feasible=False,
            use_radical_infeasible=False,
        )
        results.append({
            "perm_id": i + 1,
            "conservative": extract_metrics(sol_c),
            "aggressive": extract_metrics(sol_a),
        })
    return results


def summary_stats(values):
    """Retorna dict com mean, min, max, std para uma lista de números."""
    a = np.array(values, dtype=float)
    return {
        "mean": float(np.mean(a)),
        "min": float(np.min(a)),
        "max": float(np.max(a)),
        "std": float(np.std(a)) if len(a) > 1 else 0.0,
    }


def print_and_save(results, context, instance_path=None, output_path=None):
    """Imprime resumo e tabela; opcionalmente salva CSV por permutação."""
    n = len(results)
    if n == 0:
        print("Nenhuma permutação avaliada.")
        return

    # Agregações por modo
    keys_metric = ["f1", "f2", "g2", "n_vehicles", "total_distance", "n_recharges", "n_skipped"]
    summary = {"conservative": {}, "aggressive": {}}
    for mode in ["conservative", "aggressive"]:
        for k in keys_metric:
            vals = [r[mode][k] for r in results]
            summary[mode][k] = summary_stats(vals)
        feasible = [r[mode]["feasible"] for r in results]
        summary[mode]["pct_feasible"] = 100.0 * sum(feasible) / len(feasible)

    # Tabela resumida
    print("\n" + "=" * 80)
    print("COMPARAÇÃO DECODER: CONSERVADOR vs AGRESSIVO")
    print("=" * 80)
    inst_label = instance_path or getattr(context, "name", "N/A")
    print(f"Instância: {inst_label} | Clientes: {len(context.customers)}")
    print(f"Permutações aleatórias: {n}")
    print()

    print("-" * 80)
    print(f"{'Métrica':<22} | {'Conservador (C)':^26} | {'Agressivo (A)':^26}")
    print(f"{'':22} | {'mean   min   max':^26} | {'mean   min   max':^26}")
    print("-" * 80)

    for k in keys_metric:
        sc = summary["conservative"][k]
        sa = summary["aggressive"][k]
        print(f"{k:<22} | {sc['mean']:>8.2f} {sc['min']:>8.2f} {sc['max']:>8.2f}   | {sa['mean']:>8.2f} {sa['min']:>8.2f} {sa['max']:>8.2f}")
    print(f"{'% viável (G2<=0)':<22} | {summary['conservative']['pct_feasible']:>24.1f}% | {summary['aggressive']['pct_feasible']:>24.1f}%")
    print("-" * 80)

    # Diferenças médias (A - C)
    print("\nDiferença média (Agressivo − Conservador):")
    for k in keys_metric:
        mean_c = summary["conservative"][k]["mean"]
        mean_a = summary["aggressive"][k]["mean"]
        diff = mean_a - mean_c
        pct = (100.0 * diff / mean_c) if mean_c != 0 else 0.0
        print(f"  {k}: {diff:+.2f} ({pct:+.1f}%)")
    print()

    # CSV por permutação (opcional)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            header = [
                "perm_id",
                "c_f1", "c_f2", "c_g2", "c_n_vehicles", "c_total_distance", "c_n_recharges", "c_n_skipped", "c_feasible",
                "a_f1", "a_f2", "a_g2", "a_n_vehicles", "a_total_distance", "a_n_recharges", "a_n_skipped", "a_feasible",
            ]
            f.write(",".join(header) + "\n")
            for r in results:
                row = [
                    r["perm_id"],
                    r["conservative"]["f1"], r["conservative"]["f2"], r["conservative"]["g2"],
                    r["conservative"]["n_vehicles"], r["conservative"]["total_distance"],
                    r["conservative"]["n_recharges"], r["conservative"]["n_skipped"],
                    1 if r["conservative"]["feasible"] else 0,
                    r["aggressive"]["f1"], r["aggressive"]["f2"], r["aggressive"]["g2"],
                    r["aggressive"]["n_vehicles"], r["aggressive"]["total_distance"],
                    r["aggressive"]["n_recharges"], r["aggressive"]["n_skipped"],
                    1 if r["aggressive"]["feasible"] else 0,
                ]
                f.write(",".join(str(x) for x in row) + "\n")
        print(f"Resultados por permutação salvos em: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Compara decoder em modo conservador vs agressivo sobre permutações aleatórias."
    )
    parser.add_argument(
        "instance",
        type=str,
        help="Caminho para o arquivo da instância (.txt)",
    )
    parser.add_argument(
        "--n-permutations",
        type=int,
        default=50,
        help="Número de permutações aleatórias (default: 50)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Semente aleatória para reprodutibilidade",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Caminho para salvar CSV com resultados por permutação",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.instance):
        print(f"Erro: arquivo não encontrado: {args.instance}")
        sys.exit(1)

    print(f"Carregando instância: {args.instance}")
    context = parse_instance(args.instance)
    print(f"  Clientes: {len(context.customers)} | Estações: {len(context.stations)}")
    print(f"  Executando {args.n_permutations} permutações (conservador + agressivo)...")

    results = run_comparison(context, args.n_permutations, seed=args.seed)
    print_and_save(results, context, instance_path=args.instance, output_path=args.output)


if __name__ == "__main__":
    main()
