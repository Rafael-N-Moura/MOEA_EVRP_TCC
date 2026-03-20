"""
Metricas por geracao especificas do EVRP.

FVR: proporcao de viaveis na populacao.
ERatio: proporcao de IES na populacao.
ECD: diferenca media entre f2 de viaveis e f2 de IES (mascaramento).
"""

from collections import Counter
from dataclasses import dataclass
from typing import List

from .representation import InfeasType, Solution


@dataclass
class GenerationMetrics:
    generation: int
    fvr: float
    eratio: float
    n_pareto_feasible: int
    avg_cv_energy: float
    avg_cv_cap: float
    avg_cv_tw: float
    avg_f2_feasible: float
    avg_f2_ies: float
    n_feasible: int
    n_IES: int
    n_IEC: int
    n_IC: int
    n_IJT: int
    n_IM: int
    best_f1_feasible: float
    best_f2_feasible: float
    best_f3_feasible: float
    avg_f1_feasible: float
    avg_f3_feasible: float
    # Metricas diagnosticas
    n_truly_feasible: int          # raw_energy < tol AND raw_cap < tol AND raw_tw < tol
    avg_custs_per_route: float     # media de clientes por rota (viaveis normalizados)
    pct_single_cust_routes: float  # fracao de rotas com 1 cliente (viaveis normalizados)
    avg_raw_energy: float          # media de raw_energy na populacao toda


def compute_generation_metrics(solutions: List[Solution],
                               generation: int) -> GenerationMetrics:
    counts = Counter(s.metadata.inf_type for s in solutions)
    N = len(solutions)

    n_feasible = counts[InfeasType.FEASIBLE]
    n_ies = counts[InfeasType.IES]

    feasible_sols = [s for s in solutions
                     if s.metadata.inf_type == InfeasType.FEASIBLE]
    ies_sols = [s for s in solutions
                if s.metadata.inf_type == InfeasType.IES]

    best_f1 = min((s.metadata.n_vehicles for s in feasible_sols),
                  default=float('inf'))
    best_f2 = min((s.metadata.total_distance for s in feasible_sols),
                  default=float('inf'))
    best_f3 = min((s.metadata.makespan for s in feasible_sols),
                  default=float('inf'))

    # Diagnosticas: viabilidade real e estrutura de rotas
    tol = 1e-9
    n_truly_feasible = sum(
        1 for s in solutions
        if s._raw_energy < tol and s._raw_cap < tol and s._raw_tw < tol
    )

    all_custs_per_route = []
    n_single = 0
    n_total_routes = 0
    for s in feasible_sols:
        for r in s.routes:
            nc = r.n_customers()
            all_custs_per_route.append(nc)
            n_total_routes += 1
            if nc == 1:
                n_single += 1

    avg_custs_per_route = (sum(all_custs_per_route) / len(all_custs_per_route)
                           if all_custs_per_route else 0.0)
    pct_single = n_single / n_total_routes if n_total_routes > 0 else 0.0

    avg_raw_energy = _avg(s._raw_energy for s in solutions)

    return GenerationMetrics(
        generation=generation,
        fvr=n_feasible / N if N > 0 else 0.0,
        eratio=n_ies / N if N > 0 else 0.0,
        n_pareto_feasible=_count_pareto(feasible_sols),
        avg_cv_energy=_avg(s.cv_components.cv_energy for s in solutions),
        avg_cv_cap=_avg(s.cv_components.cv_cap for s in solutions),
        avg_cv_tw=_avg(s.cv_components.cv_tw for s in solutions),
        avg_f2_feasible=_avg(s.metadata.total_distance for s in feasible_sols),
        avg_f2_ies=_avg(s.metadata.total_distance for s in ies_sols),
        n_feasible=n_feasible,
        n_IES=n_ies,
        n_IEC=counts[InfeasType.IEC],
        n_IC=counts[InfeasType.IC],
        n_IJT=counts[InfeasType.IJT],
        n_IM=counts[InfeasType.IM],
        best_f1_feasible=best_f1 if best_f1 != float('inf') else 0.0,
        best_f2_feasible=best_f2,
        best_f3_feasible=best_f3,
        avg_f1_feasible=_avg(s.metadata.n_vehicles for s in feasible_sols),
        avg_f3_feasible=_avg(s.metadata.makespan for s in feasible_sols),
        n_truly_feasible=n_truly_feasible,
        avg_custs_per_route=avg_custs_per_route,
        pct_single_cust_routes=pct_single,
        avg_raw_energy=avg_raw_energy,
    )


def _avg(gen) -> float:
    vals = list(gen)
    return sum(vals) / len(vals) if vals else 0.0


def _count_pareto(solutions: List[Solution]) -> int:
    """Conta solucoes nao-dominadas em f1-f3 (O(n^2))."""
    if not solutions:
        return 0

    objs = [s.objectives_3() for s in solutions]
    non_dom = 0

    for i, oi in enumerate(objs):
        dominated = False
        for j, oj in enumerate(objs):
            if i == j:
                continue
            if (all(oj[k] <= oi[k] for k in range(3))
                    and any(oj[k] < oi[k] for k in range(3))):
                dominated = True
                break
        if not dominated:
            non_dom += 1

    return non_dom
