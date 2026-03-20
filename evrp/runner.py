"""
Configuracao e execucao do experimento NSGA-II + CDP para o EVRP.

EVRPCallback: atualiza pop_stats a cada geracao e coleta metricas.
run_experiment: configura NSGA-II com os operadores EVRP e executa.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np
from pymoo.algorithms.moo.moead import MOEAD
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.callback import Callback
from pymoo.core.problem import ElementwiseProblem
from pymoo.decomposition.tchebicheff import Tchebicheff
from pymoo.optimize import minimize
from pymoo.util.ref_dirs import get_reference_directions

from .evaluator import update_pop_stats
from .instance import EVRPInstance
from .metrics import GenerationMetrics, compute_generation_metrics
from .operators import EVRPCrossover, EVRPMutation, EVRPSampling
from .problem import EVRPProblem
from .representation import Solution


@dataclass
class OffspringCensus:
    generation: int
    n_offspring: int
    n_truly_feasible: int     # raw_energy < tol AND raw_cap < tol AND raw_tw < tol
    n_raw_energy_zero: int    # raw_energy < tol
    n_raw_tw_zero: int        # raw_tw < tol
    avg_raw_energy: float
    avg_raw_tw: float


class EVRPMOEADProblem(ElementwiseProblem):
    """
    Adaptador sem restricoes explicitas para MOEA/D.
    Aplica penalizacao escalar em F com base no CV total.
    """

    def __init__(self, base_problem: EVRPProblem, penalty: float = 1e4):
        super().__init__(
            n_var=base_problem.n_var,
            n_obj=base_problem.n_obj,
            n_ieq_constr=0,
            xl=base_problem.xl,
            xu=base_problem.xu,
        )
        self.base = base_problem
        self.instance = base_problem.instance
        self.penalty = penalty
        self.pop_stats = base_problem.pop_stats

    def _evaluate(self, x, out, *args, **kwargs):
        tmp = {}
        self.base._evaluate(x, tmp, *args, **kwargs)
        F = np.array(tmp['F'], dtype=float)
        cv_total = float(tmp['G'][0]) if 'G' in tmp else 0.0
        out['F'] = F + self.penalty * cv_total


class EVRPCallback(Callback):

    def __init__(self, problem: EVRPProblem, census_interval: int = 25):
        super().__init__()
        self.problem = problem
        self.history: List[GenerationMetrics] = []
        self.offspring_census: List[OffspringCensus] = []
        self.census_interval = census_interval

    def notify(self, algorithm):
        pop = algorithm.pop
        solutions = [ind.X[0] for ind in pop]

        # 1. Atualiza pop_stats e re-normaliza CVs
        self.problem.refresh_pop_stats(solutions)

        # 2. Coleta metricas
        gen = algorithm.n_gen
        metrics = compute_generation_metrics(solutions, gen)
        self.history.append(metrics)

        # 3. Censo de offspring (a cada census_interval geracoes)
        if (gen % self.census_interval == 0 or gen == 1) and hasattr(algorithm, 'off'):
            off = algorithm.off
            if off is not None:
                tol = 1e-9
                if hasattr(off, 'X'):
                    # Alguns algoritmos (ex.: MOEA/D) expõem apenas 1 offspring.
                    off_items = [off]
                else:
                    off_items = list(off)
                if off_items:
                    off_sols = [ind.X[0] for ind in off_items if ind.X[0] is not None]
                    evaluated = [s for s in off_sols if not s._dirty]
                    if evaluated:
                        census = OffspringCensus(
                            generation=gen,
                            n_offspring=len(evaluated),
                            n_truly_feasible=sum(
                                1 for s in evaluated
                                if s._raw_energy < tol and s._raw_cap < tol and s._raw_tw < tol),
                            n_raw_energy_zero=sum(1 for s in evaluated if s._raw_energy < tol),
                            n_raw_tw_zero=sum(1 for s in evaluated if s._raw_tw < tol),
                            avg_raw_energy=sum(s._raw_energy for s in evaluated) / len(evaluated),
                            avg_raw_tw=sum(s._raw_tw for s in evaluated) / len(evaluated),
                        )
                        self.offspring_census.append(census)

        # 4. Log a cada 25 geracoes (f1=n_vehicles, f2=dist, f3=makespan)
        if gen % 25 == 0 or gen == 1:
            print(f'Gen {gen:4d} | FVR={metrics.fvr:.0%} '
                  f'ERatio={metrics.eratio:.0%} '
                  f'Pareto={metrics.n_pareto_feasible} '
                  f'bestF1={metrics.best_f1_feasible:.0f} '
                  f'bestF2={metrics.best_f2_feasible:.0f} '
                  f'bestF3={metrics.best_f3_feasible:.0f}')


def run_experiment(instance: EVRPInstance,
                   N_P: int = 100,
                   N_gen: int = 300,
                   init_params: dict | None = None,
                   mutation_prob: float = 0.15,
                   algorithm_name: str = 'nsga2',
                   moead_n_neighbors: int = 20,
                   moead_prob_neighbor_mating: float = 0.9,
                   seed: int = 42,
                   verbose: bool = True) -> dict:

    if init_params is None:
        init_params = dict(
            alpha_V=0.40, alpha_E=0.35,
            beta_s=0.20, p_skip=0.50, seed=seed,
        )

    problem = EVRPProblem(instance)
    sampling = EVRPSampling(instance, init_params)
    callback = EVRPCallback(problem)

    algo_name = algorithm_name.lower()
    optimize_problem = problem

    if algo_name == 'nsga2':
        algorithm = NSGA2(
            pop_size=N_P,
            sampling=sampling,
            crossover=EVRPCrossover(),
            mutation=EVRPMutation(prob=mutation_prob),
            eliminate_duplicates=False,
        )
        algo_label = 'NSGA-II+CDP'
    elif algo_name == 'moead':
        # MOEA/D do pymoo nao aceita restricoes explicitas (G).
        # Usa adaptador com penalizacao no vetor de objetivos.
        optimize_problem = EVRPMOEADProblem(problem, penalty=1e4)

        # Para n_obj=3, usa direcoes de referencia no simplex (Tchebycheff).
        n_partitions = 0
        while (n_partitions + 1) * (n_partitions + 2) // 2 <= N_P:
            n_partitions += 1
        n_partitions = max(1, n_partitions - 1)
        ref_dirs = get_reference_directions("das-dennis", 3, n_partitions=n_partitions)
        algorithm = MOEAD(
            ref_dirs=ref_dirs,
            n_neighbors=moead_n_neighbors,
            decomposition=Tchebicheff(),
            prob_neighbor_mating=moead_prob_neighbor_mating,
            sampling=sampling,
            crossover=EVRPCrossover(),
            mutation=EVRPMutation(prob=mutation_prob),
        )
        algo_label = 'MOEA/D (Tchebycheff)'
    else:
        raise ValueError(f'algorithm_name invalido: {algorithm_name}')

    if verbose:
        print(f'=== EVRP {algo_label}: {instance.name} ===')
        print(f'N_P={N_P}, N_gen={N_gen}, seed={seed}')
        print(f'B={instance.B:.1f}, Q={instance.Q:.0f}, '
              f'n_cust={instance.n_customers}, n_stat={instance.n_stations}')

    res = minimize(
        optimize_problem,
        algorithm,
        ('n_gen', N_gen),
        callback=callback,
        seed=seed,
        verbose=False,
    )

    pareto = [ind.X[0] for ind in res.opt] if res.opt is not None else []
    init_result = getattr(problem, 'init_result', None)
    if init_result is None:
        init_result = getattr(optimize_problem, 'init_result', sampling.init_result)

    if verbose:
        ir = init_result
        if ir:
            print(f'\nInit: V={ir.n_V} IES={ir.n_IES} IEC={ir.n_IEC} '
                  f'IC={ir.n_IC} IJT={ir.n_IJT} IM={ir.n_IM}')
            print(f'eta={ir.eta:.2f}, eta_E={ir.eta_E:.2f}')

        last = callback.history[-1] if callback.history else None
        if last:
            print(f'\nFinal (gen {last.generation}): '
                  f'FVR={last.fvr:.0%}, Pareto={last.n_pareto_feasible}, '
                  f'bestF1={last.best_f1_feasible:.0f} '
                  f'bestF2={last.best_f2_feasible:.0f} '
                  f'bestF3={last.best_f3_feasible:.0f}')

    return {
        'result': res,
        'history': callback.history,
        'init_result': init_result,
        'pareto_solutions': pareto,
        'offspring_census': callback.offspring_census,
    }
