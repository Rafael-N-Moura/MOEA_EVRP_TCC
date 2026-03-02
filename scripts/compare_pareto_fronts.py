#!/usr/bin/env python3
"""
Compara duas frentes de Pareto (NSGA-II vs BatteryFocused ou dois .npz).

Uso:
  # Com arquivos .npz (gerados com python main.py ... --save-front)
  python scripts/compare_pareto_fronts.py logs/nsga2_rc208_21_<ts>_front.npz logs/battery_focused_nsga2_rc208_21_<ts>_front.npz

  # Com arquivos de log .txt (extrai a seção "Todas as soluções da frente de Pareto")
  python scripts/compare_pareto_fronts.py logs/nsga2_rc208_21_20260225_005005.txt logs/battery_focused_nsga2_rc208_21_20260225_004659.txt
"""

import argparse
import re
import sys
import numpy as np


def load_F_from_npz(path):
    """Carrega array F (n, 2) de um .npz (chave 'F')."""
    data = np.load(path)
    if "F" not in data:
        raise ValueError(f"Arquivo {path} não contém chave 'F'")
    F = np.asarray(data["F"])
    if F.ndim != 2 or F.shape[1] != 2:
        raise ValueError(f"F deve ser (n, 2), obteve shape {F.shape}")
    return F


def load_F_from_log(path):
    """Extrai pontos da frente de Pareto de um log .txt (seção 'Todas as soluções da frente de Pareto')."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    # Procura linhas "  Solução i: Custo=xxx, Insatisfação=yyy"
    pattern = re.compile(r"Solução\s+\d+:\s+Custo=([\d.]+),\s+Insatisfação=([\d.]+)")
    matches = pattern.findall(text)
    if not matches:
        raise ValueError(f"Nenhum ponto da frente de Pareto encontrado em {path}")
    F = np.array([[float(m[0]), float(m[1])] for m in matches])
    return F


def load_F(path):
    """Carrega F de .npz ou .txt (detecta pela extensão)."""
    path = str(path)
    if path.lower().endswith(".npz"):
        return load_F_from_npz(path)
    if path.lower().endswith(".txt"):
        return load_F_from_log(path)
    raise ValueError(f"Extensão não suportada: use .npz ou .txt (path={path})")


def dominates(a, b):
    """True se a domina b (ambos minimização: a <= b em todos e a < b em pelo menos um)."""
    return np.all(a <= b) and np.any(a < b)


def count_dominated_by(A, B):
    """Número de pontos em A que são dominados por pelo menos um ponto em B."""
    n = 0
    for i in range(len(A)):
        for j in range(len(B)):
            if dominates(B[j], A[i]):
                n += 1
                break
    return n


def hypervolume_2d(F, ref):
    """Hipervolume 2D (área) com referência ref = (ref_f1, ref_f2). F e ref são arrays 1d ou 2d."""
    F = np.atleast_2d(F)
    ref = np.atleast_1d(ref)
    if ref.size != 2:
        ref = np.array([ref[0], ref[1]])
    # Ordenar por f1 e calcular área sob a curva (step function)
    idx = np.argsort(F[:, 0])
    F = F[idx]
    x = np.concatenate([[ref[0]], F[:, 0], [ref[0]]])
    y = np.concatenate([[ref[1]], np.minimum.accumulate(F[:, 1][::-1])[::-1], [F[-1, 1]]])
    area = 0.0
    for i in range(len(x) - 1):
        area += (x[i] - x[i + 1]) * y[i + 1]
    return area


def main():
    parser = argparse.ArgumentParser(
        description="Compara duas frentes de Pareto (.npz ou .txt log)"
    )
    parser.add_argument("file_a", help="Primeira frente (.npz ou .txt)")
    parser.add_argument("file_b", help="Segunda frente (.npz ou .txt)")
    parser.add_argument(
        "--ref",
        type=float,
        nargs=2,
        default=None,
        metavar=("ref_f1", "ref_f2"),
        help="Ponto de referência para hipervolume (ex.: 35000 0.03). Se omitido, usa (max(f1)+margin, max(f2)+margin)"
    )
    parser.add_argument(
        "--name-a",
        type=str,
        default="A",
        help="Nome da primeira frente para o relatório"
    )
    parser.add_argument(
        "--name-b",
        type=str,
        default="B",
        help="Nome da segunda frente para o relatório"
    )
    args = parser.parse_args()

    try:
        F_a = load_F(args.file_a)
        F_b = load_F(args.file_b)
    except Exception as e:
        print(f"Erro ao carregar arquivos: {e}", file=sys.stderr)
        sys.exit(1)

    name_a, name_b = args.name_a, args.name_b

    print("=" * 70)
    print("COMPARAÇÃO DE FRENTES DE PARETO")
    print("=" * 70)
    print(f"  {name_a}: {args.file_a}  →  {len(F_a)} pontos")
    print(f"  {name_b}: {args.file_b}  →  {len(F_b)} pontos")
    print()

    # Estatísticas
    def stats(F, name):
        f1, f2 = F[:, 0], F[:, 1]
        print(f"  {name}:")
        print(f"    f1 (custo):       min={f1.min():.2f}, max={f1.max():.2f}, média={f1.mean():.2f}")
        print(f"    f2 (insatisf.):   min={f2.min():.6f}, max={f2.max():.6f}, média={f2.mean():.6f}")

    print("Estatísticas por objetivo:")
    stats(F_a, name_a)
    stats(F_b, name_b)
    print()

    # Dominância
    n_a_dom_by_b = count_dominated_by(F_a, F_b)
    n_b_dom_by_a = count_dominated_by(F_b, F_a)
    print("Dominância (minimização):")
    print(f"  Pontos de {name_a} dominados por algum de {name_b}: {n_a_dom_by_b}/{len(F_a)}")
    print(f"  Pontos de {name_b} dominados por algum de {name_a}: {n_b_dom_by_a}/{len(F_b)}")
    if n_a_dom_by_b == 0 and n_b_dom_by_a == 0:
        print("  → Nenhuma frente domina a outra (podem ser equivalentes ou incomparáveis).")
    elif n_b_dom_by_a == 0 and n_a_dom_by_b > 0:
        print(f"  → {name_b} domina estritamente alguns pontos de {name_a}; {name_b} não é pior.")
    elif n_a_dom_by_b == 0 and n_b_dom_by_a > 0:
        print(f"  → {name_a} domina estritamente alguns pontos de {name_b}; {name_a} não é pior.")
    else:
        print("  → Cada frente domina alguns pontos da outra (frentes diferentes).")
    print()

    # Hipervolume (referência comum)
    if args.ref is not None:
        ref = np.array(args.ref)
    else:
        all_f1 = np.concatenate([F_a[:, 0], F_b[:, 0]])
        all_f2 = np.concatenate([F_a[:, 1], F_b[:, 1]])
        margin_f1 = max(1.0, (all_f1.max() - all_f1.min()) * 0.1)
        margin_f2 = max(1e-6, (all_f2.max() - all_f2.min() + 1e-9) * 0.1)
        ref = np.array([all_f1.max() + margin_f1, all_f2.max() + margin_f2])

    hv_a = hypervolume_2d(F_a, ref)
    hv_b = hypervolume_2d(F_b, ref)
    print("Hipervolume 2D (maior = melhor; ref =", ref.round(4).tolist(), ")")
    print(f"  {name_a}: {hv_a:.4f}")
    print(f"  {name_b}: {hv_b:.4f}")
    diff = hv_a - hv_b
    if abs(diff) < 1e-9:
        print("  → Valores praticamente iguais.")
    elif diff > 0:
        print(f"  → {name_a} tem hipervolume maior em {diff:.4f}.")
    else:
        print(f"  → {name_b} tem hipervolume maior em {-diff:.4f}.")
    print("=" * 70)


if __name__ == "__main__":
    main()
