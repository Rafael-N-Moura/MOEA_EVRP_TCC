"""
Teste comparativo: viável vs inviável e análise de reparo.

1) Comparativo viável vs inviável (mesma permutação):
   Soluções inviáveis tendem a ter melhores objetivos (menor f1, f2). O script
   mede esse ganho decodificando cada permutação duas vezes (True e False).

2) Análise de reparo (inviável → viável):
   Quanto os objetivos mudam quando uma solução inviável é reparada (redecodificada
   com force_battery_feasible=True). Mostra variação absoluta e percentual (deterioração).
"""

import argparse
import numpy as np
from pathlib import Path

from src.parser import parse_instance
from src.decoder import decode


def run_paired_comparison(context, permutations, verbose=True, use_radical_infeasible=False):
    """
    Para cada permutação: decodifica com force_battery_feasible=True e False.
    use_radical_infeasible: se True, modo inviável radical (sem estações) — maior gap.
    """
    n = len(permutations)
    f1_feas, f2_feas, g2_feas = [], [], []
    f1_infeas, f2_infeas, g2_infeas = [], [], []

    for i, perm in enumerate(permutations):
        if verbose and (i + 1) % max(1, n // 10) == 0:
            print(f"  Decodificando {i+1}/{n} ...")
        sol_feas = decode(perm, context, force_battery_feasible=True)
        f1_feas.append(sol_feas.total_cost)
        f2_feas.append(sol_feas.avg_dissatisfaction)
        g2_feas.append(sol_feas.battery_violation)
        sol_infeas = decode(
            perm, context, force_battery_feasible=False,
            use_radical_infeasible=use_radical_infeasible
        )
        f1_infeas.append(sol_infeas.total_cost)
        f2_infeas.append(sol_infeas.avg_dissatisfaction)
        g2_infeas.append(sol_infeas.battery_violation)

    f1_feas = np.array(f1_feas)
    f2_feas = np.array(f2_feas)
    g2_feas = np.array(g2_feas)
    f1_infeas = np.array(f1_infeas)
    f2_infeas = np.array(f2_infeas)
    g2_infeas = np.array(g2_infeas)

    # Ganho dos inviáveis em relação ao viável (positivo = inviável melhor)
    gain_f1 = np.where(f1_feas > 0, (f1_feas - f1_infeas) / f1_feas * 100, 0.0)
    gain_f2 = np.where(f2_feas > 0, (f2_feas - f2_infeas) / f2_feas * 100, 0.0)

    # Deterioração ao reparar (inviável → viável): delta absoluto e % em relação ao inviável
    delta_f1 = f1_feas - f1_infeas
    delta_f2 = f2_feas - f2_infeas
    pct_deterioration_f1 = np.where(f1_infeas > 0, delta_f1 / f1_infeas * 100, 0.0)
    pct_deterioration_f2 = np.where(f2_infeas > 0, delta_f2 / f2_infeas * 100, 0.0)

    return {
        "f1_feas": f1_feas,
        "f2_feas": f2_feas,
        "g2_feas": g2_feas,
        "f1_infeas": f1_infeas,
        "f2_infeas": f2_infeas,
        "g2_infeas": g2_infeas,
        "gain_f1_pct": gain_f1,
        "gain_f2_pct": gain_f2,
        "delta_f1": delta_f1,
        "delta_f2": delta_f2,
        "pct_deterioration_f1": pct_deterioration_f1,
        "pct_deterioration_f2": pct_deterioration_f2,
        "n": n,
    }


def print_paired_report(data, instance_name=""):
    """Imprime relatório dos pares (mesma permutação, viável vs inviável)."""
    f1_f, f2_f = data["f1_feas"], data["f2_feas"]
    g2_f = data["g2_feas"]
    f1_i, f2_i = data["f1_infeas"], data["f2_infeas"]
    g2_i = data["g2_infeas"]
    g1, g2 = data["gain_f1_pct"], data["gain_f2_pct"]
    n = data["n"]

    title = "Comparativo Viável vs Inviável (mesma permutação)" + (f" — {instance_name}" if instance_name else "")
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)
    print(f"N = {n} permutações decodificadas duas vezes (force_battery_feasible True e False).")
    print()

    print("Objetivos — Viável (force_battery_feasible=True):")
    print(f"  f1 (custo):       médio = {f1_f.mean():.2f},  min = {f1_f.min():.2f},  max = {f1_f.max():.2f}")
    print(f"  f2 (insatisf.):   médio = {f2_f.mean():.4f},  min = {f2_f.min():.4f},  max = {f2_f.max():.4f}")
    print(f"  G2 (bateria):     médio = {g2_f.mean():.2f},  min = {g2_f.min():.2f},  max = {g2_f.max():.2f}")
    print()

    print("Objetivos — Inviável (force_battery_feasible=False):")
    print(f"  f1 (custo):       médio = {f1_i.mean():.2f},  min = {f1_i.min():.2f},  max = {f1_i.max():.2f}")
    print(f"  f2 (insatisf.):   médio = {f2_i.mean():.4f},  min = {f2_i.min():.4f},  max = {f2_i.max():.4f}")
    print(f"  G2 (bateria):     médio = {g2_i.mean():.2f},  min = {g2_i.min():.2f},  max = {g2_i.max():.2f}")
    print()

    print("Ganho dos INVIÁVEIS em relação ao VIÁVEL (mesma permutação):")
    print(f"  Ganho em f1 (custo):       médio = {g1.mean():.2f}%,  min = {g1.min():.2f}%,  max = {g1.max():.2f}%")
    print(f"  Ganho em f2 (insatisf.):   médio = {g2.mean():.2f}%,  min = {g2.min():.2f}%,  max = {g2.max():.2f}%")
    print("  (positivo = inviável tem objetivo menor, i.e. melhor)")
    print()

    # Quantas vezes o inviável domina o viável (em f1, f2)?
    dominates = (f1_i <= f1_f) & (f2_i <= f2_f) & ((f1_i < f1_f) | (f2_i < f2_f))
    strictly_better_f1 = f1_i < f1_f
    strictly_better_f2 = f2_i < f2_f
    print("Comparação por solução:")
    print(f"  Inviável domina viável (f1,f2):     {dominates.sum()}/{n} ({100*dominates.mean():.1f}%)")
    print(f"  Inviável com f1 menor que viável:   {strictly_better_f1.sum()}/{n} ({100*strictly_better_f1.mean():.1f}%)")
    print(f"  Inviável com f2 menor que viável:   {strictly_better_f2.sum()}/{n} ({100*strictly_better_f2.mean():.1f}%)")
    print("=" * 70)
    print()


def print_repair_report(data, instance_name=""):
    """
    Análise de reparo: quanto os objetivos mudam quando uma solução inviável
    é reparada (redecodificada com force_battery_feasible=True).
    """
    f1_i, f2_i = data["f1_infeas"], data["f2_infeas"]
    f1_f, f2_f = data["f1_feas"], data["f2_feas"]
    d1, d2 = data["delta_f1"], data["delta_f2"]
    p1, p2 = data["pct_deterioration_f1"], data["pct_deterioration_f2"]
    n = data["n"]

    title = "Análise de reparo (inviável → viável)" + (f" — {instance_name}" if instance_name else "")
    print("=" * 70)
    print(title)
    print("=" * 70)
    print("Mudança nos objetivos quando a mesma permutação é decodificada em modo")
    print("viável (force_battery_feasible=True). Valores positivos = piora após reparo.")
    print()

    print("Variação absoluta (reparado − inviável):")
    print(f"  Δf1 (custo):       médio = {d1.mean():.2f},  min = {d1.min():.2f},  max = {d1.max():.2f}")
    print(f"  Δf2 (insatisf.):  médio = {d2.mean():.6f},  min = {d2.min():.6f},  max = {d2.max():.6f}")
    print()

    print("Variação percentual em relação ao valor INVIÁVEL (quanto piora ao reparar):")
    print(f"  Δf1 %:  médio = {p1.mean():.2f}%,  min = {p1.min():.2f}%,  max = {p1.max():.2f}%")
    print(f"  Δf2 %:  médio = {p2.mean():.2f}%,  min = {p2.min():.2f}%,  max = {p2.max():.2f}%")
    print("  (positivo = reparo aumenta o objetivo, i.e. solução fica pior nesse objetivo)")
    print()

    # Resumo: em quantos casos o reparo piora cada objetivo
    worse_f1 = d1 > 0
    worse_f2 = d2 > 0
    better_f1 = d1 < 0
    better_f2 = d2 < 0
    print("Efeito do reparo por solução:")
    print(f"  Reparo piora f1 (custo):      {worse_f1.sum()}/{n} ({100*worse_f1.mean():.1f}%)")
    print(f"  Reparo piora f2 (insatisf.):  {worse_f2.sum()}/{n} ({100*worse_f2.mean():.1f}%)")
    print(f"  Reparo melhora f1:            {better_f1.sum()}/{n} ({100*better_f1.mean():.1f}%)")
    print(f"  Reparo melhora f2:            {better_f2.sum()}/{n} ({100*better_f2.mean():.1f}%)")
    print("=" * 70)
    print()


def generate_permutations(context, n_permutations, seed=42):
    """Gera n_permutations permutações aleatórias dos índices de clientes."""
    n_customers = len(context.customers)
    rng = np.random.default_rng(seed)
    perms = [rng.permutation(n_customers).tolist() for _ in range(n_permutations)]
    return perms


def load_permutations_from_npy(filepath):
    """Carrega matriz de genótipos (N x n_var) e retorna lista de listas."""
    X = np.load(filepath)
    if X.ndim == 1:
        X = X.reshape(1, -1)
    return [X[i].astype(int).tolist() for i in range(len(X))]


def main():
    parser = argparse.ArgumentParser(
        description="Compara objetivos de soluções viáveis vs inviáveis (mesma permutação)."
    )
    parser.add_argument(
        "instance",
        nargs="?",
        default="evrptw_instances/rc208_21.txt",
        help="Caminho da instância (ex: evrptw_instances/rc208_21.txt)",
    )
    parser.add_argument(
        "-n",
        type=int,
        default=50,
        help="Número de permutações a testar (default: 50)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Semente para geração de permutações (default: 42)",
    )
    parser.add_argument(
        "--load-x",
        type=str,
        default=None,
        metavar="FILE.npy",
        help="Se informado, carrega genótipos de FILE.npy em vez de gerar aleatórios",
    )
    parser.add_argument(
        "-q",
        action="store_true",
        help="Modo quieto (menos impressões durante o loop)",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        metavar="FILE.csv",
        help="Salva resultados por solução em CSV",
    )
    parser.add_argument(
        "--radical",
        action="store_true",
        help="Usar modo inviável radical (sem estações) para maior gap",
    )
    args = parser.parse_args()

    instance_path = Path(args.instance)
    if not instance_path.exists():
        print(f"Erro: instância não encontrada: {instance_path}")
        return 1

    context = parse_instance(str(instance_path))
    instance_name = instance_path.stem
    n_customers = len(context.customers)

    if args.load_x:
        permutations = load_permutations_from_npy(args.load_x)
        print(f"Carregadas {len(permutations)} permutações de {args.load_x}")
    else:
        permutations = generate_permutations(context, args.n, seed=args.seed)
        print(f"Geradas {args.n} permutações aleatórias (seed={args.seed})")

    if len(permutations) == 0:
        print("Nenhuma permutação para avaliar.")
        return 1

    if args.radical:
        print("Modo inviável: RADICAL (sem estações)")
    data = run_paired_comparison(
        context, permutations, verbose=not args.q,
        use_radical_infeasible=args.radical
    )
    print_paired_report(data, instance_name=instance_name)
    print_repair_report(data, instance_name=instance_name)

    if args.csv:
        import csv
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "f1_feas", "f2_feas", "g2_feas",
                "f1_infeas", "f2_infeas", "g2_infeas",
                "gain_f1_pct", "gain_f2_pct",
                "delta_f1", "delta_f2",
                "pct_deterioration_f1", "pct_deterioration_f2",
            ])
            for i in range(data["n"]):
                w.writerow([
                    data["f1_feas"][i], data["f2_feas"][i], data["g2_feas"][i],
                    data["f1_infeas"][i], data["f2_infeas"][i], data["g2_infeas"][i],
                    data["gain_f1_pct"][i], data["gain_f2_pct"][i],
                    data["delta_f1"][i], data["delta_f2"][i],
                    data["pct_deterioration_f1"][i], data["pct_deterioration_f2"][i],
                ])
        print(f"Resultados salvos em: {args.csv}")
    return 0


if __name__ == "__main__":
    exit(main())
