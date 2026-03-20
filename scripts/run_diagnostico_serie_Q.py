#!/usr/bin/env python3
"""
Série de diagnósticos variando Q (capacidade de bateria) na mesma instância.
Antes de rodar qualquer algoritmo, mapeia a transição de regime em função de Q.

Uso:
  python scripts/run_diagnostico_serie_Q.py <instancia.txt> [-n N] [-s SEED]

Exemplo de resultado esperado (rc208):
  Q = 165.63  → ESPARSO_DESFAVORAVEL (confirmado)
  Q = 248.44  → ESPARSO_DESFAVORAVEL ou transição
  Q = 331.26  → transição
  Q = 496.89  → ESPARSO_FAVORAVEL
  Q = 828.15  → MODERADO ou DENSO
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.parser import parse_instance
from src.diagnostico_instancias import (
    calcular_Q_alvo,
    criar_variacao_Q,
    diagnosticar_instancia,
)


def main():
    parser = argparse.ArgumentParser(
        description="Diagnóstico em série variando Q (battery_capacity)."
    )
    parser.add_argument("instancia", type=str, help="Caminho para o arquivo .txt da instância")
    parser.add_argument(
        "-n", "--n-amostras",
        type=int,
        default=200,
        help="Amostras por diagnóstico (default: 200)",
    )
    parser.add_argument(
        "-s", "--seed",
        type=int,
        default=42,
        help="Semente (default: 42)",
    )
    parser.add_argument(
        "-f", "--fator-max",
        type=float,
        default=None,
        help="Fator máximo de Q (ex.: 10 para testar até 10×Q). Se omitido, usa 5 ou mais quando Q_alvo exige.",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.instancia):
        print(f"Erro: arquivo não encontrado: {args.instancia}", file=sys.stderr)
        sys.exit(1)

    print(f"Carregando: {args.instancia}")
    context = parse_instance(args.instancia)
    n = len(context.customers)
    Q_orig = context.battery_capacity
    print(f"  Clientes: {n}  Q original: {Q_orig:.2f}  r: {context.consumption_rate}\n")

    # --- Q alvo (condição para marginais existirem) ---
    q_alvo = calcular_Q_alvo(context)
    print("=" * 60)
    print("CONDIÇÃO PARAMÉTRICA (Q vs distâncias típicas)")
    print("=" * 60)
    print(f"  Distância média entre clientes: {q_alvo['dist_media']:.2f}")
    print(f"  Distância p75:                  {q_alvo['dist_p75']:.2f}")
    print(f"  Distância p90:                  {q_alvo['dist_p90']:.2f}")
    print(f"  Q atual:                       {q_alvo['Q_atual']:.2f}")
    print(f"  Q mínimo para FR local > 0:    {q_alvo['Q_fr_local']:.2f}")
    print(f"  Q alvo para marginais locais:   {q_alvo['Q_marginais']:.2f}")
    print(f"  Fator de aumento necessário:    {q_alvo['fator_aumento_necessario']:.2f}x")
    print()

    # --- Série de Q ---
    # Incluir fatores além de 5x se Q_alvo para marginais exige mais (ex.: rc208 ~7.25x)
    if args.fator_max is not None:
        fator_max = args.fator_max
    else:
        fator_max = max(5.0, min(10.0, q_alvo["fator_aumento_necessario"] * 1.2))
    fatores = [1.0, 1.5, 2.0, 3.0, 5.0]
    if fator_max > 5.0:
        extras = [7.0, 10.0] if fator_max > 7 else [7.0]
        for e in extras:
            if e <= fator_max and e not in fatores:
                fatores.append(e)
        fatores.sort()
    Qs_testar = [Q_orig * f for f in fatores]

    print("=" * 60)
    print("SÉRIE DE DIAGNÓSTICOS (n_amostras={}, seed={})".format(args.n_amostras, args.seed))
    print("=" * 60)

    resultados_serie = []
    for Q_val in Qs_testar:
        ctx_q = criar_variacao_Q(context, Q_val)
        res = diagnosticar_instancia(ctx_q, n_amostras=args.n_amostras, seed=args.seed)
        regime = res["regime"]
        fr_energia = res["feasibility_rate_energia"]
        fr_local = res.get("fr_local") or {}
        marg_local = fr_local.get("marginais_locais_medio")
        bases = fr_local.get("n_bases_usadas", 0)

        resultados_serie.append({
            "Q": Q_val,
            "regime": regime,
            "fr_energia": fr_energia,
            "marginais_locais": marg_local,
            "n_bases": bases,
        })

        marg_str = f"{marg_local:.2f}" if marg_local is not None else "—"
        bases_str = str(bases) if bases is not None else "0"
        print(f"  Q = {Q_val:8.2f}  →  {regime:25s}  "
              f"FR_global={fr_energia:.3f}  bases={bases_str}  marg_local={marg_str}")

    print()
    if resultados_serie and all(r["regime"] == "ESPARSO_DESFAVORAVEL" for r in resultados_serie):
        print("Conclusão: na série testada, a instância permaneceu ESPARSO_DESFAVORAVEL.")
        print("          Para ver transição, aumente Q (ex.: até Q_marginais acima) ou use -f 10.")
    else:
        print("Conclusão: a série define em qual Q a instância entra em regime favorável à técnica.")
    print()


if __name__ == "__main__":
    main()
