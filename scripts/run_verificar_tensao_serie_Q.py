#!/usr/bin/env python3
"""
Varre vários Q_factor e mostra tensão energética (SoC mínimo) para cada um.
Útil para ver em qual Q a topologia deixa de ter tensão (p10 > 0.25).

Uso:
  python scripts/run_verificar_tensao_serie_Q.py <instancia.txt> [-n N] [-s SEED]

Exemplo:
  python scripts/run_verificar_tensao_serie_Q.py evrptw_instances/rc208_21.txt -n 30
"""

import argparse
import sys
import os

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.parser import parse_instance
from src.diagnostico_instancias import (
    _verificar_tensao_energetica_dados,
)


def main():
    parser = argparse.ArgumentParser(
        description="Série de verificação de tensão energética para vários Q_factor."
    )
    parser.add_argument("instancia", type=str, help="Caminho para o arquivo .txt da instância")
    parser.add_argument(
        "-n", "--n-solucoes",
        type=int,
        default=50,
        help="Número de soluções greedy por Q_factor (default: 50)",
    )
    parser.add_argument(
        "-s", "--seed",
        type=int,
        default=42,
        help="Semente (default: 42)",
    )
    parser.add_argument(
        "-q", "--factors",
        type=str,
        default="1.5,2.0,2.5,3.0",
        help="Q_factors separados por vírgula (default: 1.5,2.0,2.5,3.0)",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.instancia):
        print(f"Erro: arquivo não encontrado: {args.instancia}", file=sys.stderr)
        sys.exit(1)

    try:
        Q_factors = [float(x.strip()) for x in args.factors.split(",")]
    except ValueError:
        print("Erro: --factors deve ser números separados por vírgula (ex.: 1.5,2.0,3.0)", file=sys.stderr)
        sys.exit(1)

    print(f"Carregando: {args.instancia}")
    context = parse_instance(args.instancia)
    Q_orig = context.battery_capacity
    print(f"  Q original: {Q_orig:.2f}  Clientes: {len(context.customers)}\n")

    rng = np.random.default_rng(args.seed)

    print("=" * 75)
    print(f"TENSÃO ENERGÉTICA POR Q_factor (n_soluções={args.n_solucoes}, seed={args.seed})")
    print("  Critério: p10(SoC_min/Q) > 0.25 → sem tensão; ≤ 0.25 → tensão presente")
    print("=" * 75)
    print(f"  {'Q_factor':>8}  {'Q_usado':>10}  {'n_feas':>7}  {'p10':>7}  {'mediana':>8}  {'min':>7}  conclusão")
    print("-" * 75)

    for qf in Q_factors:
        dados = _verificar_tensao_energetica_dados(
            context, args.n_solucoes, rng, qf
        )
        nf = dados["n_feasible"]
        if nf == 0:
            print(f"  {qf:8.2f}  {dados['Q_usado']:10.2f}  {nf:7}  {'—':>7}  {'—':>8}  {'—':>7}  nenhuma factível")
            continue
        p10 = dados["p10"]
        med = dados["mediana"]
        mn = dados["minimo"]
        if dados["resultado"] is True:
            conc = "tensão presente"
        elif dados["resultado"] is False:
            conc = "sem tensão"
        else:
            conc = "—"
        print(f"  {qf:8.2f}  {dados['Q_usado']:10.2f}  {nf:7}  {p10:7.3f}  {med:8.3f}  {mn:7.3f}  {conc}")

    print()
    print("Interpretação: enquanto p10 ≤ 0.25 há arcos com SoC próximo de zero (tensão).")
    print("Se para algum Q_factor p10 > 0.25, a partir desse Q o Caminho A perde relevância.")
    print()


if __name__ == "__main__":
    main()
