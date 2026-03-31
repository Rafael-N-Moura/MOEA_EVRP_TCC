"""
Adaptação para pymoo: problema EVRPTW tri-objetivo com constraint handling.

Objetivos:
    f1 – número de veículos   (inteiro, minimizar)
    f2 – distância total      (contínuo, minimizar)
    f3 – makespan             (contínuo, minimizar)

Constraint handling via penalty adaptativa nos objetivos:
    cv = violação normalizada (TW/horizonte + bateria/Q).
    Se cv > 0: F_pymoo = F_real + cv × penalty_scale.
    Se cv = 0: F_pymoo = F_real (solução viável).

Isto implementa o Constrained Domination Principle de forma compatível
com TODOS os algoritmos (NSGA-II, MOEA/D, SMS-EMOA), já que MOEA/D
do pymoo não suporta n_ieq_constr > 0.

Os campos _F_real e _cv são armazenados para acesso posterior sem
necessidade de re-decodificação.
"""

import numpy as np
from pymoo.core.problem import ElementwiseProblem
from .model import Context
from .decoder import Decoder


class EVRPTWProblem(ElementwiseProblem):

    def __init__(self, context: Context, k_max: int = 50):
        self.context = context
        self.decoder = Decoder(context, k_max=k_max)
        n = context.n_customers

        super().__init__(
            n_var=n,
            n_obj=3,
            n_ieq_constr=0,
            xl=0,
            xu=n - 1,
        )

        horizon = float(context.all_nodes[0].due_date)
        self._penalty = np.array([
            float(n),
            float(n) * 200.0,
            horizon,
        ])

    def _evaluate(self, x, out, *args, **kwargs):
        F, cv = self.decoder.decode(x)
        if cv > 0:
            out["F"] = F + cv * self._penalty
        else:
            out["F"] = F
        out["_F_real"] = F.copy()
        out["_cv"] = np.array([cv])
