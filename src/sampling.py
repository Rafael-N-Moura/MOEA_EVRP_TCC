"""
Operador de amostragem inicial adaptado ao EVRPTW.

TWBiasedSampling gera permutações biased para factibilidade de janelas
de tempo: ordena clientes por ready_time com ruído proporcional à
largura mediana das TW. Mantém fração da população puramente aleatória
para diversidade genética.
"""

import numpy as np
from pymoo.core.sampling import Sampling


class TWBiasedSampling(Sampling):
    """
    Amostragem inicial com viés temporal para EVRPTW.

    - Fração ``biased_ratio`` da população: permutações geradas por
      argsort(ready_time + ruído), com escala de ruído proporcional
      à largura mediana das janelas de tempo da instância.
    - Restante: permutações uniformemente aleatórias (diversidade).
    """

    def __init__(self, biased_ratio=0.75):
        super().__init__()
        self.biased_ratio = biased_ratio

    def _do(self, problem, n_samples, **kwargs):
        n = problem.n_var
        ctx = problem.context
        X = np.empty((n_samples, n), dtype=int)

        ready = np.array([c.ready_time for c in ctx.customers])
        tw_widths = np.array([c.due_date - c.ready_time for c in ctx.customers])
        noise_scale = max(float(np.median(tw_widths)), 1.0)

        n_biased = int(n_samples * self.biased_ratio)

        for i in range(n_samples):
            if i < n_biased:
                noise = np.random.uniform(-noise_scale, noise_scale, size=n)
                X[i] = np.argsort(ready + noise)
            else:
                X[i] = np.random.permutation(n)

        return X
