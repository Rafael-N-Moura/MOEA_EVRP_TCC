"""
Script principal para execução dos algoritmos NSGA-II, MOEA/D e SMS-EMOA
no problema EVRPTW tri-objetivo.

Objetivos:
    f1 – número de veículos
    f2 – distância total
    f3 – makespan
"""

import argparse
import time

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.moo.moead import MOEAD
from pymoo.algorithms.moo.sms import SMSEMOA
from pymoo.optimize import minimize
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation

from src import parse_instance, EVRPTWProblem, TWBiasedSampling


# ------------------------------------------------------------------
# Utilitários
# ------------------------------------------------------------------
def _get_ref_dirs(n_obj, n_partitions):
    """Importa get_reference_directions compatível com pymoo 0.6.x."""
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


def _print_results(name, res, elapsed):
    cv_arr = res.pop.get("_cv")
    F_real = res.pop.get("_F_real")
    feasible_mask = cv_arr[:, 0] <= 1e-9
    n_feas = int(feasible_mask.sum())
    n_infeas = len(cv_arr) - n_feas

    print(f"\n{'=' * 60}")
    print(f"{name} finalizado  ({elapsed:.1f}s)")
    print(f"{'=' * 60}")
    print(f"Solucoes na frente: {len(cv_arr)}  (viáveis: {n_feas}  inviáveis: {n_infeas})")

    if n_feas > 0:
        Ff = F_real[feasible_mask]
        print(f"  f1 (veiculos) :  min={Ff[:, 0].min():.0f}   max={Ff[:, 0].max():.0f}")
        print(f"  f2 (distancia):  min={Ff[:, 1].min():.2f}  max={Ff[:, 1].max():.2f}")
        print(f"  f3 (makespan) :  min={Ff[:, 2].min():.2f}  max={Ff[:, 2].max():.2f}")
    else:
        print("  Nenhuma solucao viável encontrada.")

    if n_infeas > 0:
        cv = cv_arr[~feasible_mask, 0]
        print(f"  CV inviáveis:    min={cv.min():.4f}  max={cv.max():.4f}")

    print(f"{'=' * 60}\n")


# ------------------------------------------------------------------
# Algoritmos
# ------------------------------------------------------------------
def run_nsga2(problem, n_gen, pop_size, seed, verbose):
    alg = NSGA2(pop_size=pop_size, **_operators(), eliminate_duplicates=True)
    t0 = time.time()
    res = minimize(problem, alg, ('n_gen', n_gen), verbose=verbose, seed=seed)
    _print_results("NSGA-II", res, time.time() - t0)
    return res


def run_moead(problem, n_gen, pop_size, seed, verbose):
    ref_dirs = _get_ref_dirs(n_obj=3, n_partitions=13)   # 105 direções para 3 obj
    actual_pop = len(ref_dirs)
    if actual_pop != pop_size:
        print(f"MOEA/D: pop_size ajustado de {pop_size} para {actual_pop} "
              f"(numero de direcoes de referencia)")

    alg = MOEAD(
        ref_dirs,
        n_neighbors=20,
        prob_neighbor_mating=0.7,
        **_operators(),
    )
    t0 = time.time()
    res = minimize(problem, alg, ('n_gen', n_gen), verbose=verbose, seed=seed)
    _print_results("MOEA/D", res, time.time() - t0)
    return res


def run_smsemoa(problem, n_gen, pop_size, seed, verbose):
    alg = SMSEMOA(pop_size=pop_size, **_operators(), eliminate_duplicates=True)
    t0 = time.time()
    res = minimize(problem, alg, ('n_gen', n_gen), verbose=verbose, seed=seed)
    _print_results("SMS-EMOA", res, time.time() - t0)
    return res


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description='EVRPTW tri-objetivo: NSGA-II / MOEA/D / SMS-EMOA')
    ap.add_argument('instance', help='Caminho para arquivo de instancia (.txt)')
    ap.add_argument('--algorithm',
                    choices=['nsga2', 'moead', 'smsemoa', 'all'],
                    default='all')
    ap.add_argument('--n-gen', type=int, default=100)
    ap.add_argument('--pop-size', type=int, default=100)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--no-verbose', action='store_true')
    ap.add_argument('--plot', action='store_true',
                    help='Gera scatter 3D da frente de Pareto')
    args = ap.parse_args()

    # Carrega instância
    print(f"Carregando instancia: {args.instance}")
    ctx = parse_instance(args.instance)
    print(f"  Depot: {ctx.depot.id}")
    print(f"  Estacoes: {len(ctx.stations)} "
          f"({len(ctx.valid_station_indices)} validas para insercao)")
    print(f"  Clientes: {ctx.n_customers}")
    print(f"  Q={ctx.battery_capacity}  C={ctx.vehicle_capacity}  "
          f"r={ctx.consumption_rate}  g={ctx.recharge_rate}  v={ctx.velocity}")

    problem = EVRPTWProblem(ctx)
    verbose = not args.no_verbose
    results = {}

    if args.algorithm in ('nsga2', 'all'):
        results['NSGA-II'] = run_nsga2(
            problem, args.n_gen, args.pop_size, args.seed, verbose)
    if args.algorithm in ('moead', 'all'):
        results['MOEA/D'] = run_moead(
            problem, args.n_gen, args.pop_size, args.seed, verbose)
    if args.algorithm in ('smsemoa', 'all'):
        results['SMS-EMOA'] = run_smsemoa(
            problem, args.n_gen, args.pop_size, args.seed, verbose)

    # Visualização 3D opcional
    if args.plot and results:
        try:
            from pymoo.visualization.scatter import Scatter
            plot = Scatter(title="Frente de Pareto",
                          labels=["f1 (veiculos)", "f2 (distancia)", "f3 (makespan)"])
            for name, res in results.items():
                cv_arr = res.pop.get("_cv")
                F_real = res.pop.get("_F_real")
                feas = F_real[cv_arr[:, 0] <= 1e-9]
                if len(feas) > 0:
                    plot.add(feas, label=name)
            plot.show()
        except Exception as e:
            print(f"Erro ao gerar grafico: {e}")

    print("Execucao concluida!")


if __name__ == '__main__':
    main()
