#!/usr/bin/env python3
"""
Script de comparação multiobjetivo: NSGA-II padrão vs BatteryFocusedNSGA2.

Executa N execuções de cada algoritmo usando a MESMA seed por execução
(seed 1 na run 1, seed 2 na run 2, ...), garantindo permutações iniciais
idênticas para comparação justa. Battery-focused é sempre rodado com
decoder não-radical (--no-radical: com estações no modo inviável).

Métricas: hipervolume (HV), tamanho da frente, tempo, estatísticas de f1/f2.

Uso:
  python scripts/run_compare_nsga2_battery.py evrptw_instances/rc208_21.txt
  python scripts/run_compare_nsga2_battery.py evrptw_instances/rc208_21.txt --runs 10 --n-gen 100 --no-verbose
  python scripts/run_compare_nsga2_battery.py evrptw_instances/rc208_21.txt --runs 5 --save-front
"""

import argparse
import os
import sys
import time
import numpy as np
import pandas as pd

# Garante que o projeto está no path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import parse_instance, EVRPTWProblem
from main import run_nsga2, run_battery_focused_nsga2


def hypervolume_2d(F, ref):
    """
    Hipervolume 2D (área) com referência ref = (ref_f1, ref_f2).
    F: (n, 2), ref: (2,) ou array. Minimização: ref deve ser pior que todos os pontos.
    """
    F = np.atleast_2d(np.asarray(F, dtype=float))
    ref = np.atleast_1d(np.asarray(ref, dtype=float))
    if F.size == 0:
        return 0.0
    if ref.size != 2:
        ref = np.array([float(ref[0]), float(ref[1])])
    # Ordenar por f1 e calcular área sob a curva (step function)
    idx = np.argsort(F[:, 0])
    F = F[idx]
    x = np.concatenate([[ref[0]], F[:, 0], [ref[0]]])
    y = np.concatenate([[ref[1]], np.minimum.accumulate(F[:, 1][::-1])[::-1], [F[-1, 1]]])
    area = 0.0
    for i in range(len(x) - 1):
        area += (x[i] - x[i + 1]) * y[i + 1]
    return float(area)


def extract_front(res):
    """Extrai F da frente de Pareto do resultado (res.F ou res.opt.get('F'))."""
    if hasattr(res, "F") and res.F is not None and len(res.F) > 0:
        return np.asarray(res.F, dtype=float)
    if hasattr(res, "opt") and res.opt is not None and len(res.opt) > 0 and res.opt.has("F"):
        return np.asarray(res.opt.get("F"), dtype=float)
    if hasattr(res, "pop") and res.pop is not None and len(res.pop) > 0 and res.pop.has("F"):
        F = res.pop.get("F")
        from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting
        nds = NonDominatedSorting()
        fronts = nds.do(F)
        if len(fronts) > 0 and len(fronts[0]) > 0:
            return np.asarray(F[fronts[0]], dtype=float)
        return np.asarray(F, dtype=float)
    return np.empty((0, 2), dtype=float)


def run_single_pair(seed, context, instance_name, n_gen, pop_size, verbose, save_front):
    """
    Executa uma rodada: NSGA-II e BatteryFocused com a MESMA seed.
    Sempre usa decoder não-radical para battery-focused (use_radical_infeasible=False).
    """
    problem_nsga2 = EVRPTWProblem(
        context=context,
        use_constraints=False,
        force_battery_feasible=True,
        use_radical_infeasible=False,
    )
    t0 = time.perf_counter()
    res_nsga2 = run_nsga2(
        problem_nsga2,
        n_gen=n_gen,
        pop_size=pop_size,
        verbose=verbose,
        instance_name=instance_name,
        save_front=save_front,
        seed=seed,
    )
    time_nsga2 = time.perf_counter() - t0

    problem_battery = EVRPTWProblem(
        context=context,
        use_constraints=True,
        force_battery_feasible=False,
        use_radical_infeasible=False,  # --no-radical
    )
    t0 = time.perf_counter()
    res_battery = run_battery_focused_nsga2(
        problem_battery,
        n_gen=n_gen,
        pop_size=pop_size,
        infeasible_ratio=0.30,
        feasible_mating_ratio=0.7,
        test_all_feasible=False,
        verbose=verbose,
        instance_name=instance_name,
        save_front=save_front,
        seed=seed,
    )
    time_battery = time.perf_counter() - t0

    return {
        "res_nsga2": res_nsga2,
        "res_battery": res_battery,
        "time_nsga2": time_nsga2,
        "time_battery": time_battery,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Comparação multiobjetivo: NSGA-II vs BatteryFocused (mesma seed por run, battery com --no-radical)"
    )
    parser.add_argument(
        "instance",
        type=str,
        help="Caminho da instância EVRPTW (.txt)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=10,
        help="Número de execuções por algoritmo (default: 10). Mesma seed por run para ambos.",
    )
    parser.add_argument(
        "--n-gen",
        type=int,
        default=100,
        help="Número de gerações (default: 100)",
    )
    parser.add_argument(
        "--pop-size",
        type=int,
        default=100,
        help="Tamanho da população (default: 100)",
    )
    parser.add_argument(
        "--no-verbose",
        action="store_true",
        help="Desativar saída verbose durante as execuções",
    )
    parser.add_argument(
        "--save-front",
        action="store_true",
        help="Salvar frente de Pareto (.npz) em logs/ para cada execução",
    )
    parser.add_argument(
        "--out-csv",
        type=str,
        default="logs/compare_nsga2_battery_metrics.csv",
        help="Caminho do CSV de saída com métricas (default: logs/compare_nsga2_battery_metrics.csv)",
    )
    args = parser.parse_args()

    instance_path = args.instance
    n_runs = args.runs
    n_gen = args.n_gen
    pop_size = args.pop_size
    verbose = not args.no_verbose
    save_front = args.save_front
    out_csv = args.out_csv

    if not os.path.isfile(instance_path):
        print(f"Erro: Instância não encontrada: {instance_path}")
        sys.exit(1)

    instance_name = os.path.splitext(os.path.basename(instance_path))[0]
    print("Carregando instância...")
    context = parse_instance(instance_path)
    print(f"  Clientes: {len(context.customers)} | Bateria Q: {context.battery_capacity}")
    print(f"Execuções: {n_runs} | Gerações: {n_gen} | Pop: {pop_size}")
    print("BatteryFocused sempre com decoder não-radical (--no-radical). Mesma seed por run para ambos.\n")

    os.makedirs(os.path.dirname(out_csv) or "logs", exist_ok=True)

    all_results = []
    all_F_for_ref = []

    for run in range(1, n_runs + 1):
        seed = run  # seed 1, 2, ..., n_runs (mesma seed para os dois algoritmos nesta run)
        print(f"Run {run}/{n_runs} (seed={seed})...")
        pair = run_single_pair(
            seed=seed,
            context=context,
            instance_name=instance_name,
            n_gen=n_gen,
            pop_size=pop_size,
            verbose=verbose,
            save_front=save_front,
        )
        F_nsga2 = extract_front(pair["res_nsga2"])
        F_battery = extract_front(pair["res_battery"])

        if len(F_nsga2) > 0:
            all_F_for_ref.append(F_nsga2)
        if len(F_battery) > 0:
            all_F_for_ref.append(F_battery)

        all_results.append({
            "run": run,
            "seed": seed,
            "algorithm": "nsga2",
            "n_pareto": len(F_nsga2),
            "time_s": pair["time_nsga2"],
            "f1_min": float(np.min(F_nsga2[:, 0])) if len(F_nsga2) > 0 else np.nan,
            "f1_max": float(np.max(F_nsga2[:, 0])) if len(F_nsga2) > 0 else np.nan,
            "f2_min": float(np.min(F_nsga2[:, 1])) if len(F_nsga2) > 0 else np.nan,
            "f2_max": float(np.max(F_nsga2[:, 1])) if len(F_nsga2) > 0 else np.nan,
            "F": F_nsga2,
        })
        all_results.append({
            "run": run,
            "seed": seed,
            "algorithm": "battery_focused",
            "n_pareto": len(F_battery),
            "time_s": pair["time_battery"],
            "f1_min": float(np.min(F_battery[:, 0])) if len(F_battery) > 0 else np.nan,
            "f1_max": float(np.max(F_battery[:, 0])) if len(F_battery) > 0 else np.nan,
            "f2_min": float(np.min(F_battery[:, 1])) if len(F_battery) > 0 else np.nan,
            "f2_max": float(np.max(F_battery[:, 1])) if len(F_battery) > 0 else np.nan,
            "F": F_battery,
        })

    # Ponto de referência comum para Hipervolume (nadir + margem no espaço original)
    if len(all_F_for_ref) > 0:
        all_F = np.vstack(all_F_for_ref)
        ideal = np.min(all_F, axis=0)
        nadir = np.max(all_F, axis=0)
        margin = (nadir - ideal) * 0.1
        margin[margin == 0] = 1.0  # dimensão constante: margem fixa
        ref_point = nadir + margin
    else:
        ideal = nadir = ref_point = None

    # Calcular HV por frente (espaço original com ref_point comum = comparável entre runs)
    for r in all_results:
        F = r["F"]
        if len(F) == 0:
            r["hv"] = np.nan
        elif ref_point is not None:
            r["hv"] = hypervolume_2d(F, ref_point)
        else:
            r["hv"] = np.nan

    # DataFrame sem coluna F (não serializável no CSV)
    rows = []
    for r in all_results:
        rows.append({
            "run": r["run"],
            "seed": r["seed"],
            "algorithm": r["algorithm"],
            "n_pareto": r["n_pareto"],
            "hv": r["hv"],
            "time_s": r["time_s"],
            "f1_min": r["f1_min"],
            "f1_max": r["f1_max"],
            "f2_min": r["f2_min"],
            "f2_max": r["f2_max"],
        })
    df = pd.DataFrame(rows)
    df.to_csv(out_csv, index=False)
    print(f"\nMétricas salvas em: {out_csv}")

    # Relatório
    print("\n" + "=" * 70)
    print("RELATÓRIO DE COMPARAÇÃO MULTIOBJETIVO (NSGA-II vs BatteryFocused)")
    print("=" * 70)
    print(f"Instância: {instance_path} | Runs: {n_runs} | Mesma seed por run")
    print(f"Gerações: {n_gen} | População: {pop_size} | BatteryFocused: --no-radical")
    print()

    for algo in ["nsga2", "battery_focused"]:
        sub = df[df["algorithm"] == algo]
        print(f"--- {algo.upper()} ---")
        print(f"  Tamanho da frente (média ± dp): {sub['n_pareto'].mean():.1f} ± {sub['n_pareto'].std():.1f}  [min={sub['n_pareto'].min():.0f}, max={sub['n_pareto'].max():.0f}]")
        print(f"  Hipervolume (média ± dp):     {sub['hv'].mean():.4f} ± {sub['hv'].std():.4f}")
        print(f"  Tempo (s) (média ± dp):       {sub['time_s'].mean():.2f} ± {sub['time_s'].std():.2f}")
        if sub["f1_min"].notna().any():
            print(f"  f1 (custo)  - min médio: {sub['f1_min'].mean():.2f}  |  f2 (insat.) - min médio: {sub['f2_min'].mean():.4f}")
        print()

    # Comparação HV (maior é melhor)
    hv_nsga2 = df[df["algorithm"] == "nsga2"]["hv"]
    hv_battery = df[df["algorithm"] == "battery_focused"]["hv"]
    if hv_nsga2.notna().all() and hv_battery.notna().all():
        try:
            from scipy.stats import ranksums
            stat, p_val = ranksums(hv_battery, hv_nsga2)
            print("--- Teste estatístico (Hipervolume) ---")
            print(f"  Wilcoxon ranksums: estatística={stat:.4f}, p-value={p_val:.5f}")
            if p_val < 0.05:
                if hv_battery.mean() > hv_nsga2.mean():
                    print("  >> BatteryFocused apresenta HV significativamente MAIOR (p < 0.05)")
                else:
                    print("  >> NSGA-II apresenta HV significativamente MAIOR (p < 0.05)")
            else:
                print("  >> Sem diferença estatística significativa em HV (p >= 0.05)")
        except ImportError:
            pass

    print("=" * 70)


if __name__ == "__main__":
    main()
