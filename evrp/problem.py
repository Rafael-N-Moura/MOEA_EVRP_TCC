"""
EVRPProblem: integracao com pymoo via ElementwiseProblem.

3 objetivos: f1=n_vehicles, f2=total_distance, f3=makespan.
1 restricao de desigualdade (CDP escalar): G[0] = cv_total.
Representacao: X[i,0] = objeto Solution (dtype=object, n_var=1).
"""

import numpy as np
from pymoo.core.problem import ElementwiseProblem

from .evaluator import PopulationStats, renormalize, run_ci, update_pop_stats
from .instance import EVRPInstance
from .representation import Solution


class EVRPProblem(ElementwiseProblem):

    def __init__(self, instance: EVRPInstance):
        super().__init__(
            n_var=1,
            n_obj=3,
            n_ieq_constr=1,
            xl=None,
            xu=None,
        )
        self.instance = instance
        self.pop_stats = PopulationStats()

    def _evaluate(self, x, out, *args, **kwargs):
        sol: Solution = x[0]

        if sol._dirty:
            run_ci(sol, self.instance, self.pop_stats)

        out['F'] = np.array(sol.objectives_3(), dtype=float)
        out['G'] = np.array([sol.cv_components.total()], dtype=float)

    def refresh_pop_stats(self, solutions: list) -> None:
        """Atualiza pop_stats e re-normaliza CVs. Chamar via callback a cada geracao."""
        self.pop_stats = update_pop_stats(solutions)
        for sol in solutions:
            renormalize(sol, self.pop_stats)
