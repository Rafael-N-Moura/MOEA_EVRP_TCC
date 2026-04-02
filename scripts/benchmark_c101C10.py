"""
Benchmark: NSGA-II vs MOEA/D vs SMS-EMOA
Instância : c101C10
Avaliações : 10.000 (exatas)
Pop size   : 105  (MOEA/D usa 105 direções Das-Dennis para 3 obj, n_partitions=12 → 91; ou 13 → 105)
Runs       : 5
Seeds      : 1..5

Ao final:
  - Tabela de HV por run e algoritmo
  - Exporta população final do MOEA/D (última run, seed=5)
  - Conta soluções únicas no espaço objetivo (valores reais)
"""

import sys
import os
import time
import csv
import json
import numpy as np
import warnings

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Caminho raiz do projeto
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src import parse_instance, EVRPTWProblem, TWBiasedSampling

from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.moo.moead import MOEAD
from pymoo.algorithms.moo.sms import SMSEMOA
from pymoo.optimize import minimize
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation
from pymoo.indicators.hv import HV

# ---------------------------------------------------------------------------
# Configurações do experimento
# ---------------------------------------------------------------------------
INSTANCE  = os.path.join(ROOT, "evrptw_instances", "c101C10.txt")
N_EVALS   = 10_000      # avaliações totais (exatas)
POP_SIZE  = 105         # tamanho de população alvo
N_RUNS    = 5
SEEDS     = list(range(1, N_RUNS + 1))
RESULTS_DIR = os.path.join(ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_ref_dirs(n_obj=3, n_partitions=13):
    try:
        from pymoo.util.ref_dirs import get_reference_directions
    except ImportError:
        from pymoo.util.reference_direction import get_reference_directions
    rd = get_reference_directions("das-dennis", n_obj, n_partitions=n_partitions)
    return rd


def _operators():
    return dict(
        sampling=TWBiasedSampling(),
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
    )


def _n_gen_from_evals(n_evals, pop_size):
    """Converte avaliações totais em número de gerações."""
    return max(1, n_evals // pop_size)


def _compute_hv(res, ref_point):
    """Calcula HV sobre as soluções viáveis (cv=0). Retorna 0.0 se nenhuma viável."""
    cv_arr   = res.pop.get("_cv")
    F_real   = res.pop.get("_F_real")
    feasible = (cv_arr[:, 0] <= 1e-9)
    Ff       = F_real[feasible]
    if len(Ff) == 0:
        return 0.0
    ind = HV(ref_point=ref_point)
    return float(ind(Ff))


def _build_ref_point(problem, n_samples=200, seed=0):
    """Estima ponto de referência com base em amostras aleatórias."""
    rng = np.random.default_rng(seed)
    n   = problem.n_var
    F_list = []
    for _ in range(n_samples):
        x  = rng.permutation(n)
        F, _ = problem.decoder.decode(x)
        F_list.append(F)
    F_arr = np.array(F_list)
    # ref_point = 1.1 × máximo em cada objetivo
    ref = F_arr.max(axis=0) * 1.1
    return ref


# ---------------------------------------------------------------------------
# Execução dos algoritmos
# ---------------------------------------------------------------------------

def run_algo(name, problem, pop_size, seed):
    """
    Executa um algoritmo e retorna o resultado do pymoo.
    n_gen é calculado para que n_gen * pop_size ≈ N_EVALS.
    """
    actual_pop = pop_size
    ref_dirs = None

    if name == "MOEA/D":
        ref_dirs = _get_ref_dirs(n_obj=3, n_partitions=13)
        actual_pop = len(ref_dirs)          # deve ser 105
        print(f"  MOEA/D: {actual_pop} direções de referência")

    n_gen = _n_gen_from_evals(N_EVALS, actual_pop)
    actual_evals = n_gen * actual_pop
    print(f"  n_gen={n_gen}  pop={actual_pop}  evals_reais={actual_evals}")

    ops = _operators()

    if name == "NSGA-II":
        alg = NSGA2(pop_size=actual_pop, eliminate_duplicates=True, **ops)
    elif name == "MOEA/D":
        alg = MOEAD(
            ref_dirs,
            n_neighbors=20,
            prob_neighbor_mating=0.7,
            **ops,
        )
    elif name == "SMS-EMOA":
        alg = SMSEMOA(pop_size=actual_pop, eliminate_duplicates=True, **ops)
    else:
        raise ValueError(f"Algoritmo desconhecido: {name}")

    t0  = time.time()
    res = minimize(problem, alg, ("n_gen", n_gen), verbose=False, seed=seed)
    elapsed = time.time() - t0
    return res, elapsed, actual_evals


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("BENCHMARK  EVRPTW — c101C10")
    print(f"Algoritmos : NSGA-II | MOEA/D | SMS-EMOA")
    print(f"Avaliações : {N_EVALS}  |  Pop-alvo : {POP_SIZE}  |  Runs : {N_RUNS}")
    print("=" * 70)

    # Carrega instância
    print(f"\nCarregando: {INSTANCE}")
    ctx = parse_instance(INSTANCE)
    print(f"  Clientes : {ctx.n_customers}")
    print(f"  Estações : {len(ctx.stations)}")
    print(f"  Q={ctx.battery_capacity}  C={ctx.vehicle_capacity}  "
          f"r={ctx.consumption_rate}  g={ctx.recharge_rate}  v={ctx.velocity}\n")

    problem = EVRPTWProblem(ctx)

    # Ponto de referência (estimado uma vez)
    print("Estimando ponto de referência…")
    ref_point = _build_ref_point(problem, n_samples=300, seed=42)
    print(f"  ref_point = {ref_point}\n")

    algos   = ["NSGA-II", "MOEA/D", "SMS-EMOA"]
    hv_data = {a: [] for a in algos}       # hv_data[algo][run]
    moead_last_res = None                   # guarda última run do MOEA/D

    all_rows = []   # para CSV

    for run_idx, seed in enumerate(SEEDS, start=1):
        print(f"\n{'─'*60}")
        print(f"  RUN {run_idx}/5  (seed={seed})")
        print(f"{'─'*60}")

        for algo in algos:
            print(f"\n  [{algo}]")
            res, elapsed, actual_evals = run_algo(algo, problem, POP_SIZE, seed)

            hv = _compute_hv(res, ref_point)
            hv_data[algo].append(hv)

            cv_arr   = res.pop.get("_cv")
            F_real   = res.pop.get("_F_real")
            feasible_mask = cv_arr[:, 0] <= 1e-9
            n_feas   = int(feasible_mask.sum())

            print(f"    evals={actual_evals}  tempo={elapsed:.1f}s  "
                  f"viáveis={n_feas}/{len(cv_arr)}  HV={hv:.6f}")

            all_rows.append({
                "run": run_idx,
                "seed": seed,
                "algorithm": algo,
                "actual_evals": actual_evals,
                "n_feasible": n_feas,
                "n_total": len(cv_arr),
                "hv": hv,
                "elapsed_s": round(elapsed, 2),
            })

            if algo == "MOEA/D" and run_idx == N_RUNS:
                moead_last_res = res

    # -----------------------------------------------------------------------
    # Tabela resumo HV
    # -----------------------------------------------------------------------
    print(f"\n\n{'=' * 70}")
    print("RESULTADO — HV FINAL POR RUN")
    print(f"{'=' * 70}")
    header = f"{'Algoritmo':<12}" + "".join(f"{'Run '+str(i):>12}" for i in range(1, N_RUNS+1)) \
             + f"{'Média':>12}" + f"{'Std':>10}"
    print(header)
    print("-" * len(header))
    for algo in algos:
        vals  = hv_data[algo]
        row   = f"{algo:<12}" + "".join(f"{v:>12.6f}" for v in vals)
        row  += f"{np.mean(vals):>12.6f}" + f"{np.std(vals):>10.6f}"
        print(row)
    print(f"{'=' * 70}\n")

    # -----------------------------------------------------------------------
    # Salva CSV com todos os resultados
    # -----------------------------------------------------------------------
    csv_path = os.path.join(RESULTS_DIR, "benchmark_c101C10_hv.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"CSV salvo em: {csv_path}")

    # -----------------------------------------------------------------------
    # Análise do MOEA/D — população final
    # -----------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("ANÁLISE — POPULAÇÃO FINAL DO MOEA/D (última run, seed=5)")
    print("=" * 70)

    res = moead_last_res
    cv_arr   = res.pop.get("_cv")
    F_real   = res.pop.get("_F_real")
    X_all    = res.pop.get("X")

    n_total  = len(cv_arr)
    feasible_mask = cv_arr[:, 0] <= 1e-9
    n_feas   = int(feasible_mask.sum())

    print(f"\nTamanho da população total : {n_total}")
    print(f"Soluções viáveis           : {n_feas}")
    print(f"Soluções inviáveis         : {n_total - n_feas}")

    # Soluções únicas em F_real (arredondado a 6 casas)
    F_rounded = np.round(F_real, 6)
    unique_F  = np.unique(F_rounded, axis=0)
    n_unique  = len(unique_F)
    print(f"\nSoluções únicas (espaço objetivo, 6 decimais) : {n_unique} / {n_total}")

    # Soluções únicas em X (genótipo)
    X_list   = [tuple(x) for x in X_all]
    n_unique_X = len(set(X_list))
    print(f"Soluções únicas (genótipo / permutação)       : {n_unique_X} / {n_total}")

    # Entre viáveis
    if n_feas > 0:
        F_feas = F_real[feasible_mask]
        F_feas_rounded = np.round(F_feas, 6)
        unique_feas = np.unique(F_feas_rounded, axis=0)
        print(f"Soluções únicas viáveis (obj)                 : {len(unique_feas)} / {n_feas}")

        print("\nEstatísticas dos objetivos (viáveis):")
        for j, label in enumerate(["f1 (veículos)", "f2 (distância)", "f3 (makespan)"]):
            vals = F_feas[:, j]
            print(f"  {label:15s}  min={vals.min():.4f}  max={vals.max():.4f}  "
                  f"mean={vals.mean():.4f}")

    # Exporta CSV com população completa
    pop_csv  = os.path.join(RESULTS_DIR, "moead_population_c101C10.csv")
    with open(pop_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["idx", "f1_real", "f2_real", "f3_real", "cv", "feasible"]
            + [f"x{i}" for i in range(X_all.shape[1])]
        )
        for i in range(n_total):
            row = [i, F_real[i,0], F_real[i,1], F_real[i,2],
                   cv_arr[i,0], int(feasible_mask[i])] + list(X_all[i])
            writer.writerow(row)
    print(f"\nPopulação MOEA/D exportada: {pop_csv}")

    # JSON com a frente viável
    if n_feas > 0:
        front_json = os.path.join(RESULTS_DIR, "moead_pareto_front_c101C10.json")
        front_data = [
            {"f1": float(F_feas[i,0]),
             "f2": float(F_feas[i,1]),
             "f3": float(F_feas[i,2])}
            for i in range(len(F_feas))
        ]
        with open(front_json, "w") as f:
            json.dump(front_data, f, indent=2)
        print(f"Frente Pareto MOEA/D (JSON): {front_json}")

    # Salva ref_point e resumo HV em JSON
    summary = {
        "instance": "c101C10",
        "n_evals_target": N_EVALS,
        "pop_size": POP_SIZE,
        "n_runs": N_RUNS,
        "ref_point": ref_point.tolist(),
        "hv": {algo: {"runs": hv_data[algo],
                       "mean": float(np.mean(hv_data[algo])),
                       "std":  float(np.std(hv_data[algo]))}
               for algo in algos},
        "moead_population_analysis": {
            "n_total": n_total,
            "n_feasible": n_feas,
            "n_unique_obj": n_unique,
            "n_unique_genotype": n_unique_X,
        }
    }
    summary_json = os.path.join(RESULTS_DIR, "benchmark_summary_c101C10.json")
    with open(summary_json, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Sumário JSON: {summary_json}")

    print("\nBenchmark concluído!\n")


if __name__ == "__main__":
    main()
