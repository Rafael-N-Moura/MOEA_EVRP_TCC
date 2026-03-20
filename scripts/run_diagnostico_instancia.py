#!/usr/bin/env python3
"""
Roda o diagnóstico de instância (FR, distribuição de CV, regime) e imprime o resultado.
Uso: python scripts/run_diagnostico_instancia.py <caminho_instancia.txt> [n_amostras] [seed]
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.parser import parse_instance
from src.diagnostico_instancias import diagnosticar_instancia


def main():
    parser = argparse.ArgumentParser(
        description="Diagnóstico de instância (FR, CV, regime) antes de experimentos."
    )
    parser.add_argument("instancia", type=str, help="Caminho para o arquivo .txt da instância")
    parser.add_argument(
        "-n", "--n-amostras",
        type=int,
        default=1000,
        help="Número de amostras para estimar FR e distribuição de CV (default: 1000)",
    )
    parser.add_argument(
        "-s", "--seed",
        type=int,
        default=42,
        help="Semente aleatória (default: 42)",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.instancia):
        print(f"Erro: arquivo não encontrado: {args.instancia}", file=sys.stderr)
        sys.exit(1)

    print(f"Carregando instância: {args.instancia}")
    context = parse_instance(args.instancia)
    n = len(context.customers)
    print(f"  Clientes: {n}  Estações: {len(context.stations)}  Q: {context.battery_capacity}  C: {context.vehicle_capacity}\n")

    print(f"Rodando diagnóstico (n_amostras={args.n_amostras}, seed={args.seed})...")
    res = diagnosticar_instancia(context, n_amostras=args.n_amostras, seed=args.seed)

    print("\n" + "=" * 60)
    print("1. FEASIBILITY RATE — espaço aleatório global")
    print("=" * 60)
    print(f"  FR (só energia):     {res['feasibility_rate_energia']:.4f}")
    print(f"  FR (energia + TW):   {res['feasibility_rate_total']:.4f}")

    fl = res.get("fr_local") or {}
    print("\n" + "=" * 60)
    print("1b. FR LOCAL — vizinhança de soluções factíveis (relevante para CMOEA)")
    print("=" * 60)
    if fl.get("sem_solucao_base_factivel"):
        print("  Nenhuma solução base factível encontrada pela heurística greedy.")
        print("  (Instância pode ser energeticamente muito restritiva.)")
    else:
        print(f"  Bases factíveis usadas: {fl.get('n_bases_usadas', 0)}")
        fr_loc = fl.get('fr_local_medio')
        marg = fl.get('marginais_locais_medio')
        grav = fl.get('graves_locais_medio')
        print(f"  FR local médio:        {fr_loc:.4f}" if fr_loc is not None else "  FR local médio:        —")
        print(f"  Marginais locais (0<CV<10% Q): {marg:.4f}" if marg is not None else "  Marginais locais:      —")
        print(f"  Graves locais (CV≥10% Q):      {grav:.4f}" if grav is not None else "  Graves locais:         —")

    print("\n" + "=" * 60)
    print("2. DISTRIBUIÇÃO DE CV")
    print("=" * 60)
    ce = res["cv_energia_distribuicao"]
    print("  Energia (normalizado por Q):")
    if ce["sem_inviaveis"]:
        print("    (nenhum inviável energético na amostra)")
    else:
        print(f"    n_inviáveis: {ce['n_inviaveis']}")
        print(f"    mediana: {ce['mediana_norm']:.4f}  p25: {ce['p25_norm']:.4f}  p75: {ce['p75_norm']:.4f}  p90: {ce['p90_norm']:.4f}")
    print(f"  Proporção marginais (CV < 10% Q): {res['proporcao_marginais']:.4f}")

    ct = res["cv_tw_distribuicao"]
    print("  TW (normalizado por soma de janelas):")
    if ct["sem_inviaveis"]:
        print("    (nenhum inviável TW na amostra)")
    else:
        print(f"    n_inviáveis: {ct['n_inviaveis']}")
        print(f"    mediana: {ct['mediana_norm']:.4f}  p25: {ct['p25_norm']:.4f}  p75: {ct['p75_norm']:.4f}  p90: {ct['p90_norm']:.4f}")
    print(f"  Proporção marginais TW: {res['proporcao_marginais_tw']:.4f}")

    print("\n" + "=" * 60)
    print("3. REGIME E EXPECTATIVA")
    print("=" * 60)
    print(f"  Regime:     {res['regime']}")
    print(f"  Expectativa: {res['expectativa']}")

    print("\n" + "=" * 60)
    print("4. FRONTEIRA (estrutural)")
    print("=" * 60)
    print(f"  {res['fronteira_fragmentada']}")

    print()


if __name__ == "__main__":
    main()
