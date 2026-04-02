"""
MOEA/D Configuration Sweep — c101C10
======================================
Compara 4 configurações de hiperparâmetros do MOEA/D:

  A (baseline) : n_neighbors=20, prob_neighbor_mating=0.7
  B            : n_neighbors=10, prob_neighbor_mating=0.9
  C            : n_neighbors=20, prob_neighbor_mating=0.9
  D            : n_neighbors=10, prob_neighbor_mating=0.7

Métricas por configuração:
  - HV médio e variância entre 5 runs
  - Número de soluções únicas no espaço objetivo (última run)
  - Tabela comparativa final

Parâmetros fixos:
  Instância   : c101C10
  Avaliações  : 10.000  (n_gen=95, pop=105 → 9.975 efetivos)
  Seeds       : 1..5
"""

import sys
import os
import time
import csv
import json
import warnings
import numpy as np

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src import parse_instance, EVRPTWProblem, TWBiasedSampling
from pymoo.algorithms.moo.moead import MOEAD
from pymoo.optimize import minimize
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation
from pymoo.indicators.hv import HV

# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------
INSTANCE    = os.path.join(ROOT, "evrptw_instances", "c101C10.txt")
N_EVALS     = 10_000
POP_SIZE    = 105       # deve coincidir com número de direções Das-Dennis
N_RUNS      = 5
SEEDS       = list(range(1, N_RUNS + 1))
RESULTS_DIR = os.path.join(ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

CONFIGS = {
    "A": {"n_neighbors": 20, "prob_neighbor_mating": 0.7},  # baseline
    "B": {"n_neighbors": 10, "prob_neighbor_mating": 0.9},
    "C": {"n_neighbors": 20, "prob_neighbor_mating": 0.9},
    "D": {"n_neighbors": 10, "prob_neighbor_mating": 0.7},
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_ref_dirs(n_obj=3, n_partitions=13):
    try:
        from pymoo.util.ref_dirs import get_reference_directions
    except ImportError:
        from pymoo.util.reference_direction import get_reference_directions
    return get_reference_directions("das-dennis", n_obj, n_partitions=n_partitions)


def _operators():
    return dict(
        sampling=TWBiasedSampling(),
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
    )


def _n_gen(n_evals, pop):
    return max(1, n_evals // pop)


def _compute_hv(res, ref_point):
    cv_arr   = res.pop.get("_cv")
    F_real   = res.pop.get("_F_real")
    feasible = cv_arr[:, 0] <= 1e-9
    Ff = F_real[feasible]
    if len(Ff) == 0:
        return 0.0
    return float(HV(ref_point=ref_point)(Ff))


def _unique_obj(res):
    """Número de soluções únicas no espaço objetivo (6 decimais)."""
    F_real = res.pop.get("_F_real")
    return int(len(np.unique(np.round(F_real, 6), axis=0)))


def _unique_obj_feasible(res):
    cv_arr = res.pop.get("_cv")
    F_real = res.pop.get("_F_real")
    Ff = F_real[cv_arr[:, 0] <= 1e-9]
    if len(Ff) == 0:
        return 0
    return int(len(np.unique(np.round(Ff, 6), axis=0)))


def _build_ref_point(problem, n_samples=300, seed=42):
    rng = np.random.default_rng(seed)
    n = problem.n_var
    F_list = []
    for _ in range(n_samples):
        x = rng.permutation(n)
        F, _ = problem.decoder.decode(x)
        F_list.append(F)
    return np.array(F_list).max(axis=0) * 1.1


def run_moead(problem, cfg_params, seed, n_gen, ref_dirs):
    alg = MOEAD(ref_dirs, **cfg_params, **_operators())
    t0  = time.time()
    res = minimize(problem, alg, ("n_gen", n_gen), verbose=False, seed=seed)
    return res, time.time() - t0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 72)
    print("MOEA/D CONFIG SWEEP — c101C10")
    print("Configs: A(baseline) | B | C | D")
    print(f"Avaliações: {N_EVALS}  |  Pop: {POP_SIZE}  |  Runs: {N_RUNS}")
    print("=" * 72)

    ctx     = parse_instance(INSTANCE)
    problem = EVRPTWProblem(ctx)

    print(f"\nEstimando ponto de referência...")
    ref_point = _build_ref_point(problem, n_samples=300, seed=42)
    print(f"  ref_point = {ref_point}\n")

    ref_dirs  = _get_ref_dirs(n_obj=3, n_partitions=13)
    actual_pop = len(ref_dirs)          # 105
    n_gen      = _n_gen(N_EVALS, actual_pop)
    actual_evals = n_gen * actual_pop

    print(f"Direções de referência : {actual_pop}")
    print(f"Gerações               : {n_gen}")
    print(f"Avaliações efetivas    : {actual_evals}")
    print()

    # Estrutura de coleta
    results = {
        cfg: {
            "hv_runs":      [],
            "unique_runs":  [],      # únicas na última run (total pop)
            "unique_feas":  [],      # únicas viáveis na última run
            "elapsed":      [],
            "last_res":     None,
        }
        for cfg in CONFIGS
    }

    all_rows = []

    # Loop principal
    for run_idx, seed in enumerate(SEEDS, start=1):
        print(f"\n{'─' * 72}")
        print(f"  RUN {run_idx}/5  (seed={seed})")
        print(f"{'─' * 72}")
        print(f"  {'Config':<6}  {'n_neigh':>8}  {'p_neigh':>8}  "
              f"{'HV':>14}  {'Únicos(tot)':>12}  {'Únicos(feas)':>13}  {'Tempo(s)':>9}")
        print(f"  {'─'*6}  {'─'*8}  {'─'*8}  {'─'*14}  {'─'*12}  {'─'*13}  {'─'*9}")

        for cfg_name, cfg_params in CONFIGS.items():
            res, elapsed = run_moead(problem, cfg_params, seed, n_gen, ref_dirs)

            hv      = _compute_hv(res, ref_point)
            n_uniq  = _unique_obj(res)
            n_uniq_f= _unique_obj_feasible(res)

            results[cfg_name]["hv_runs"].append(hv)
            results[cfg_name]["unique_runs"].append(n_uniq)
            results[cfg_name]["unique_feas"].append(n_uniq_f)
            results[cfg_name]["elapsed"].append(elapsed)
            if run_idx == N_RUNS:
                results[cfg_name]["last_res"] = res

            nn  = cfg_params["n_neighbors"]
            pnm = cfg_params["prob_neighbor_mating"]
            print(f"  {cfg_name:<6}  {nn:>8}  {pnm:>8.1f}  "
                  f"{hv:>14.2f}  {n_uniq:>12}  {n_uniq_f:>13}  {elapsed:>9.1f}s")

            all_rows.append({
                "run": run_idx,
                "seed": seed,
                "config": cfg_name,
                "n_neighbors": nn,
                "prob_neighbor_mating": pnm,
                "actual_evals": actual_evals,
                "hv": hv,
                "n_unique_obj": n_uniq,
                "n_unique_obj_feasible": n_uniq_f,
                "elapsed_s": round(elapsed, 2),
            })

    # -----------------------------------------------------------------------
    # Tabela resumo agregado
    # -----------------------------------------------------------------------
    print(f"\n\n{'=' * 90}")
    print("RESULTADO AGREGADO — MOEA/D CONFIG SWEEP (c101C10)")
    print(f"{'=' * 90}")
    hdr = (f"  {'Cfg':<4}  {'n_neigh':>8}  {'p_neigh':>8}  "
           f"{'HV_médio':>14}  {'HV_std':>12}  {'HV_var':>14}  "
           f"{'Únicos_média':>13}  {'Únicos_feas_média':>18}")
    print(hdr)
    print("  " + "─" * (len(hdr) - 2))

    summary_data = {}
    for cfg_name, cfg_params in CONFIGS.items():
        hvs   = results[cfg_name]["hv_runs"]
        uniqs = results[cfg_name]["unique_feas"]
        uniq_all = results[cfg_name]["unique_runs"]

        hv_mean  = float(np.mean(hvs))
        hv_std   = float(np.std(hvs))
        hv_var   = float(np.var(hvs))
        uq_mean  = float(np.mean(uniqs))
        uqa_mean = float(np.mean(uniq_all))

        nn  = cfg_params["n_neighbors"]
        pnm = cfg_params["prob_neighbor_mating"]

        tag = " ← baseline" if cfg_name == "A" else ""
        print(f"  {cfg_name:<4}  {nn:>8}  {pnm:>8.1f}  "
              f"{hv_mean:>14.2f}  {hv_std:>12.2f}  {hv_var:>14.2f}  "
              f"{uq_mean:>13.1f}  {uqa_mean:>18.1f}{tag}")

        summary_data[cfg_name] = {
            "n_neighbors": nn,
            "prob_neighbor_mating": pnm,
            "hv_runs": hvs,
            "hv_mean": hv_mean,
            "hv_std":  hv_std,
            "hv_var":  hv_var,
            "unique_obj_feasible_mean": uq_mean,
            "unique_obj_total_mean": uqa_mean,
        }

    print(f"{'=' * 90}\n")

    # -----------------------------------------------------------------------
    # Comparação por run (tabela detalhada)
    # -----------------------------------------------------------------------
    print("HV por run (comparativo):")
    head2 = f"  {'Run':<6}" + "".join(f"  {f'Config {c}':>14}" for c in CONFIGS)
    print(head2)
    print("  " + "─" * (len(head2) - 2))
    for i in range(N_RUNS):
        row = f"  {i+1:<6}"
        for cfg in CONFIGS:
            row += f"  {results[cfg]['hv_runs'][i]:>14.2f}"
        print(row)
    print()

    # -----------------------------------------------------------------------
    # Diagnóstico de colapso
    # -----------------------------------------------------------------------
    print("─" * 72)
    print("DIAGNÓSTICO DE COLAPSO (Soluções Únicas)")
    print("─" * 72)
    COLLAPSE_THRESHOLD = 10  # menos de 10 únicas = colapso

    any_fixed = False
    for cfg_name in CONFIGS:
        uq_mean = summary_data[cfg_name]["unique_obj_feasible_mean"]
        collapsed = uq_mean < COLLAPSE_THRESHOLD
        status = "COLAPSO" if collapsed else "OK"
        print(f"  Config {cfg_name}: {uq_mean:.1f} únicas viáveis (média 5 runs) — [{status}]")
        if not collapsed:
            any_fixed = True

    print()
    if not any_fixed:
        print(">>> NENHUMA CONFIGURAÇÃO resolveu o colapso de diversidade.")
        print("    Todas as 4 configs apresentam convergência prematura severa.")
        print("    O problema está na instância pequena (10 clientes) + MOEA/D sem")
        print("    eliminate_duplicates → a decomposição escalar força múltiplos")
        print("    subproblemas ao mesmo ponto ótimo quando o espaço de Pareto")
        print("    é extremamente reduzido.")
        print("    Ajustes em n_neighbors/prob_neighbor_mating não são suficientes;")
        print("    seria necessário: diversidade explícita, niching, ou instância maior.")
    else:
        best = max(summary_data, key=lambda c: summary_data[c]["unique_obj_feasible_mean"])
        print(f"    Config {best} apresentou melhor diversidade.")

    # -----------------------------------------------------------------------
    # Salva arquivos
    # -----------------------------------------------------------------------
    csv_path = os.path.join(RESULTS_DIR, "moead_config_sweep_c101C10.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nCSV detalhado : {csv_path}")

    json_path = os.path.join(RESULTS_DIR, "moead_config_sweep_summary.json")
    with open(json_path, "w") as f:
        json.dump({
            "instance": "c101C10",
            "n_evals_target": N_EVALS,
            "actual_evals": actual_evals,
            "pop_size": actual_pop,
            "n_runs": N_RUNS,
            "ref_point": ref_point.tolist(),
            "configs": summary_data,
        }, f, indent=2)
    print(f"JSON sumário  : {json_path}")
    print("\nConcluído!\n")


if __name__ == "__main__":
    main()
