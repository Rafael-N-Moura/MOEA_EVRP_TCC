"""
Validação estatística: NSGA-II (baseline) vs BatteryFocusedNSGA2 (proposta).

Executa N_RUNS execuções com sementes distintas, coleta métricas (melhor custo,
hipervolume, taxa de sucesso, número de veículos) e aplica teste de Wilcoxon.

Uso:
  python run_batch.py [--runs 30] [--instance evrptw_instances/rc208_21.txt]

Baseado em: documentos/PROTOCOLO_VALIDACAO_ESTATISTICA.md
"""

import argparse
import io
import os
import sys
import numpy as np
import pandas as pd
from scipy.stats import ranksums
from pymoo.optimize import minimize
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation
from pymoo.operators.sampling.rnd import PermutationRandomSampling

from src import parse_instance, EVRPTWProblem
from src.battery_focused_nsga2 import BatteryFocusedNSGA2
from src.decoder import decode
from pymoo.algorithms.moo.nsga2 import NSGA2

# Tentar importar HV (pymoo)
try:
    from pymoo.indicators.hv import HV
    HAS_HV = True
except ImportError:
    HAS_HV = False

# -----------------------------------------------------------------------------
# Configurações
# -----------------------------------------------------------------------------
INSTANCE_PATH_DEFAULT = "evrptw_instances/rc208_21.txt"
N_RUNS_DEFAULT = 30
POP_SIZE = 100
N_GEN_DEFAULT = 100
# Bateria: usar a da instância (ex.: 100). Sobrescrever só se necessário.
BATTERY_CAPACITY_OVERRIDE = None  # None = usar valor do arquivo


def _get_result_data(res):
    """Extrai F, X, G, CV do resultado (opt ou pop)."""
    if hasattr(res, "opt") and res.opt is not None and len(res.opt) > 0:
        F = res.opt.get("F")
        X = res.opt.get("X")
        G = res.opt.get("G") if res.opt.has("G") else None
        CV = res.opt.get("CV") if res.opt.has("CV") else None
    else:
        F = getattr(res, "F", None)
        X = getattr(res, "X", None)
        G = getattr(res, "G", None)
        CV = getattr(res, "CV", None)
    if F is None and hasattr(res, "pop") and res.pop is not None and len(res.pop) > 0:
        F = res.pop.get("F")
        X = res.pop.get("X")
        G = res.pop.get("G") if res.pop.has("G") else None
        CV = res.pop.get("CV") if res.pop.has("CV") else None
    return F, X, G, CV


def extract_feasible_front(res):
    """
    Extrai apenas soluções viáveis (CV <= 0 e G <= tol).
    Retorna (F_feasible, X_feasible) para uso em HV e melhor custo.
    """
    F, X, G, CV = _get_result_data(res)
    if F is None or len(F) == 0:
        return np.empty((0, 2)), None

    valid = np.ones(len(F), dtype=bool)
    if CV is not None:
        cv_flat = np.asarray(CV).flatten()
        valid &= (cv_flat <= 0)
    if G is not None and np.ndim(G) >= 1:
        g_mask = np.all(np.asarray(G) <= 1e-5, axis=1)
        valid &= g_mask

    F_feas = np.asarray(F)[valid]
    X_feas = np.asarray(X)[valid] if X is not None else None
    return F_feas, X_feas


def get_best_f1_and_n_vehicles(res, context):
    """
    Da frente viável, retorna (melhor_f1, n_veículos da melhor solução).
    Se não houver viável: (np.nan, np.nan).
    """
    F_feas, X_feas = extract_feasible_front(res)
    if F_feas is None or len(F_feas) == 0:
        return np.nan, np.nan

    best_idx = np.argmin(F_feas[:, 0])
    best_f1 = float(F_feas[best_idx, 0])
    n_vehicles = np.nan
    if X_feas is not None and best_idx < len(X_feas):
        try:
            x_best = np.asarray(X_feas[best_idx]).flatten()
            individual = x_best.astype(int).tolist()
            solution = decode(individual, context, force_battery_feasible=True)
            n_vehicles = len(solution.routes)
        except Exception:
            pass
    return best_f1, n_vehicles


def run_single_experiment(seed, context, n_gen, verbose=False, silent=True):
    """
    Executa uma rodada: NSGA-II (baseline) e BatteryFocusedNSGA2 (proposta).
    Usa o mesmo seed para ambos.
    Se silent=True, suprime stdout durante as execuções (recomendado para batch).
    """
    term = ("n_gen", n_gen)
    out = io.StringIO() if silent else sys.stdout

    def run_minimize(problem, algorithm):
        if silent:
            old_stdout, sys.stdout = sys.stdout, out
        try:
            return minimize(
                problem, algorithm, term, seed=seed, verbose=verbose
            )
        finally:
            if silent:
                sys.stdout = old_stdout

    # 1) Baseline: NSGA-II (penalização, sempre viável no decoder)
    problem_std = EVRPTWProblem(context, use_constraints=False, force_battery_feasible=True)
    algo_std = NSGA2(
        pop_size=POP_SIZE,
        sampling=PermutationRandomSampling(),
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
        eliminate_duplicates=True,
    )
    res_std = run_minimize(problem_std, algo_std)

    # 2) Proposta: BatteryFocusedNSGA2 (restrições, permite inviáveis na evolução)
    problem_custom = EVRPTWProblem(context, use_constraints=True, force_battery_feasible=False)
    algo_custom = BatteryFocusedNSGA2(
        pop_size=POP_SIZE,
        infeasible_ratio=0.25,
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
        eliminate_duplicates=True,
    )
    res_custom = run_minimize(problem_custom, algo_custom)

    return res_std, res_custom


def main():
    parser = argparse.ArgumentParser(description="Validação estatística NSGA-II vs BatteryFocusedNSGA2")
    parser.add_argument("--instance", type=str, default=INSTANCE_PATH_DEFAULT,
                        help=f"Caminho da instância (default: {INSTANCE_PATH_DEFAULT})")
    parser.add_argument("--runs", type=int, default=N_RUNS_DEFAULT,
                        help=f"Número de execuções independentes (default: {N_RUNS_DEFAULT})")
    parser.add_argument("--verbose", action="store_true", help="Saída verbose do minimize")
    parser.add_argument("--no-hv", action="store_true", help="Desabilitar cálculo de Hipervolume")
    parser.add_argument("--n-gen", type=int, default=N_GEN_DEFAULT,
                        help=f"Número de gerações (default: {N_GEN_DEFAULT}). Use valor menor para testes rápidos.")
    args = parser.parse_args()

    instance_path = args.instance
    n_runs = args.runs
    n_gen = args.n_gen
    verbose = args.verbose
    compute_hv = HAS_HV and not args.no_hv

    if not os.path.isfile(instance_path):
        print(f"Erro: Instância não encontrada: {instance_path}")
        sys.exit(1)

    print("Carregando instância...")
    context = parse_instance(instance_path)
    if BATTERY_CAPACITY_OVERRIDE is not None:
        context.battery_capacity = float(BATTERY_CAPACITY_OVERRIDE)
        print(f"  Bateria sobrescrita para: {context.battery_capacity}")
    print(f"  Bateria (Q): {context.battery_capacity}")
    print(f"  Clientes: {len(context.customers)}")
    print(f"Iniciando bateria de testes ({n_runs} execuções)...")

    results_base = []   # lista de (F_feas, X_feas) para cada run baseline
    results_prop = []   # lista de (F_feas, X_feas) para cada run proposta

    silent = not verbose
    for i in range(n_runs):
        print(f"  Execução {i+1}/{n_runs}...", end="\r", flush=True)
        res_std, res_prop = run_single_experiment(i, context, n_gen=n_gen, verbose=verbose, silent=silent)
        results_base.append(extract_feasible_front(res_std))
        results_prop.append(extract_feasible_front(res_prop))

    print("\nExecuções concluídas. Calculando métricas...")

    # Coleta best f1, n_vehicles e success por run (a partir de F_feas e X_feas já extraídos)
    rows = []
    for i in range(n_runs):
        F_base, X_base = results_base[i]
        F_prop, X_prop = results_prop[i]

        if len(F_base) == 0:
            best_f1_base = np.nan
            n_veh_base = np.nan
            success_base = 0
        else:
            best_f1_base = float(np.min(F_base[:, 0]))
            success_base = 1
            idx = np.argmin(F_base[:, 0])
            n_veh_base = _n_vehicles_from_x(X_base, idx, context)
        if len(F_prop) == 0:
            best_f1_prop = np.nan
            n_veh_prop = np.nan
            success_prop = 0
        else:
            best_f1_prop = float(np.min(F_prop[:, 0]))
            success_prop = 1
            idx = np.argmin(F_prop[:, 0])
            n_veh_prop = _n_vehicles_from_x(X_prop, idx, context)

        rows.append({
            "Run": i + 1,
            "Seed": i,
            "Best_f1_Base": best_f1_base,
            "Best_f1_Prop": best_f1_prop,
            "N_vehicles_Base": n_veh_base,
            "N_vehicles_Prop": n_veh_prop,
            "Success_Base": success_base,
            "Success_Prop": success_prop,
            "N_feasible_Base": len(F_base),
            "N_feasible_Prop": len(F_prop),
        })

    df = pd.DataFrame(rows)

    # Hipervolume (global nadir/ideal)
    all_solutions = []
    for F_feas, _ in results_base + results_prop:
        if len(F_feas) > 0:
            all_solutions.append(F_feas)
    if len(all_solutions) == 0:
        print("AVISO: Nenhuma solução viável encontrada em nenhuma execução.")
        df["HV_Base"] = np.nan
        df["HV_Prop"] = np.nan
    else:
        all_F = np.vstack(all_solutions)
        ideal = np.min(all_F, axis=0)
        nadir = np.max(all_F, axis=0)
        denom = nadir - ideal
        denom[denom == 0] = 1.0
        ref_point = np.array([1.1, 1.1])
        hv_calc = HV(ref_point=ref_point) if HAS_HV else None

        hv_base_list = []
        hv_prop_list = []
        for i in range(n_runs):
            F_b, _ = results_base[i]
            F_p, _ = results_prop[i]
            if compute_hv and hv_calc is not None:
                if len(F_b) > 0:
                    norm_b = (F_b - ideal) / denom
                    hv_base_list.append(hv_calc(norm_b))
                else:
                    hv_base_list.append(0.0)
                if len(F_p) > 0:
                    norm_p = (F_p - ideal) / denom
                    hv_prop_list.append(hv_calc(norm_p))
                else:
                    hv_prop_list.append(0.0)
            else:
                hv_base_list.append(np.nan)
                hv_prop_list.append(np.nan)
        df["HV_Base"] = hv_base_list
        df["HV_Prop"] = hv_prop_list

    if "HV_Base" not in df.columns:
        df["HV_Base"] = np.nan
        df["HV_Prop"] = np.nan

    # ---- Relatório ----
    print("\n" + "=" * 60)
    print("RELATÓRIO DE VALIDAÇÃO ESTATÍSTICA")
    print("=" * 60)
    print(f"Instância: {instance_path} | Bateria: {context.battery_capacity}")
    print(f"Execuções: {n_runs} | Pop: {POP_SIZE} | Gerações: {n_gen}")

    # Taxa de sucesso (viabilidade)
    s_base = df["Success_Base"].sum()
    s_prop = df["Success_Prop"].sum()
    print("\n--- TAXA DE SUCESSO (≥1 solução viável) ---")
    print(f"Baseline (NSGA-II):  {s_base}/{n_runs} ({100*s_base/n_runs:.1f}%)")
    print(f"Proposta (BatteryFocused): {s_prop}/{n_runs} ({100*s_prop/n_runs:.1f}%)")

    # Melhor custo (f1)
    valid_base = df["Best_f1_Base"].dropna()
    valid_prop = df["Best_f1_Prop"].dropna()
    print("\n--- MELHOR CUSTO (f1) ---")
    if len(valid_base) > 0:
        print(f"Baseline  (média ± dp): {valid_base.mean():.2f} ± {valid_base.std():.2f}  "
              f"[min={valid_base.min():.2f}, max={valid_base.max():.2f}]")
    else:
        print("Baseline: nenhuma solução viável")
    if len(valid_prop) > 0:
        print(f"Proposta  (média ± dp): {valid_prop.mean():.2f} ± {valid_prop.std():.2f}  "
              f"[min={valid_prop.min():.2f}, max={valid_prop.max():.2f}]")
    else:
        print("Proposta: nenhuma solução viável")

    if len(valid_base) >= 3 and len(valid_prop) >= 3:
        stat, p_val = ranksums(valid_base, valid_prop)
        print(f"Wilcoxon (ranksums) p-value: {p_val:.5f}")
        if p_val < 0.05 and valid_prop.mean() < valid_base.mean():
            print(">> Proposta é ESTATISTICAMENTAMENTE MELHOR em custo (p < 0.05)")
        elif p_val < 0.05 and valid_base.mean() < valid_prop.mean():
            print(">> Baseline é ESTATISTICAMENTE MELHOR em custo (p < 0.05)")
        else:
            print(">> Sem diferença estatística significativa em custo.")

    # Número de veículos (mediana/média do melhor por run)
    v_base = df["N_vehicles_Base"].dropna()
    v_prop = df["N_vehicles_Prop"].dropna()
    print("\n--- NÚMERO DE VEÍCULOS (da melhor solução por run) ---")
    if len(v_base) > 0:
        print(f"Baseline  (média): {v_base.mean():.1f}  [min={v_base.min():.0f}, max={v_base.max():.0f}]")
    if len(v_prop) > 0:
        print(f"Proposta  (média): {v_prop.mean():.1f}  [min={v_prop.min():.0f}, max={v_prop.max():.0f}]")

    # Hipervolume
    if compute_hv and not df["HV_Base"].isna().all():
        print("\n--- HIPERVOLUME (normalizado) ---")
        print(f"Baseline  (média ± dp): {df['HV_Base'].mean():.4f} ± {df['HV_Base'].std():.4f}")
        print(f"Proposta  (média ± dp): {df['HV_Prop'].mean():.4f} ± {df['HV_Prop'].std():.4f}")
        stat_hv, p_hv = ranksums(df["HV_Base"], df["HV_Prop"])
        print(f"Wilcoxon p-value (HV): {p_hv:.5f}")
        if p_hv < 0.05 and df["HV_Prop"].mean() > df["HV_Base"].mean():
            print(">> Proposta é ESTATISTICAMENTE MELHOR em HV (p < 0.05)")
        elif p_hv < 0.05:
            print(">> Baseline é ESTATISTICAMENTE MELHOR em HV (p < 0.05)")
        else:
            print(">> Sem diferença estatística significativa em HV.")

    # Tamanho da frente viável (métrica extra)
    print("\n--- TAMANHO DA FRENTE VIÁVEL (média de soluções viáveis por run) ---")
    print(f"Baseline:  {df['N_feasible_Base'].mean():.1f}  |  Proposta: {df['N_feasible_Prop'].mean():.1f}")

    out_csv = "resultados_validacao_estatistica.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nResultados salvos em: {out_csv}")
    print("=" * 60)


def _n_vehicles_from_x(X_feas, idx, context):
    """Dado X_feas (array 2D ou 1D) e índice da melhor solução, decodifica e retorna len(routes)."""
    if X_feas is None:
        return np.nan
    try:
        X_feas = np.asarray(X_feas)
        if X_feas.ndim == 1:
            x_best = X_feas
        else:
            x_best = X_feas[idx]
        x_best = np.asarray(x_best).flatten()
        individual = x_best.astype(int).tolist()
        solution = decode(individual, context, force_battery_feasible=True)
        return len(solution.routes)
    except Exception:
        return np.nan


if __name__ == "__main__":
    main()
