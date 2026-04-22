"""
fixed_inversion.py
==================
FixedInversionMutation — correção do double-sampling de probabilidade de mutação.

Problema (pymoo >= 0.6):
    A classe base ``Mutation.do()`` usa ``self.prob`` para filtrar quais indivíduos
    da população são passados para ``_do()``.  O método ``InversionMutation._do()``
    do pymoo repete esse filtro internamente (aplica ``self.prob`` **novamente** a
    cada indivíduo antes de executar a inversão).  O resultado é que a probabilidade
    efetiva de mutação é:

        P_efetiva = prob × prob = prob²

    Exemplo: pm=0.10 → taxa efetiva ~1%; pm=0.26 → ~6.8%.
    O único caso sem impacto é pm=1.0 (default), pois 1² = 1.

    Por esse motivo, todos os experimentos anteriores (calibração, piloto,
    stopping criterion) que usaram ``InversionMutation()`` sem argumento explícito
    (pm=1.0) **não foram afetados**.  Apenas o hypertuning que amostrou pm < 1.0
    sofreu o efeito — os valores vencedores (pm≈0.26 para NSGA-II/SMS-EMOA,
    pm≈0.20 para MOEA/D) estavam na verdade compensando o double-sampling para
    atingir uma taxa efetiva em torno de 5–7%.

Correção implementada:
    Subclasseamos ``InversionMutation`` e sobrescrevemos ``_do`` para aplicar a
    inversão **incondicionalmente** a todos os indivíduos recebidos — eles já
    foram filtrados pelo wrapper ``Mutation.do()`` usando ``self.prob``.

Referência:
    pm_bug.md — descrição completa do bug e da correção esperada.
"""

import numpy as np
from pymoo.operators.mutation.inversion import InversionMutation


class FixedInversionMutation(InversionMutation):
    """
    InversionMutation sem double-sampling de probabilidade.

    A classe base ``Mutation.do()`` já filtra os indivíduos usando ``self.prob``
    antes de chamar ``_do()``.  Esta subclasse remove o segundo filtro que existia
    no ``_do()`` original do pymoo, garantindo que:

        P_efetiva = prob  (e não prob²)

    Uso idêntico ao original::

        mutation = FixedInversionMutation(prob=0.10)

    Isso fará com que exatamente ~10% dos indivíduos da população sofram inversão,
    em vez de ~1% como acontecia com o operador original.
    """

    def _do(self, problem, X, **kwargs):
        """
        Aplica inversão de segmento aleatório a TODOS os indivíduos recebidos.

        Os indivíduos já foram pre-selecionados pelo wrapper ``Mutation.do()``
        com base em ``self.prob``, portanto não há necessidade — e seria um bug —
        aplicar ``self.prob`` novamente aqui.

        Parameters
        ----------
        problem : pymoo.core.problem.Problem
            Problema sendo resolvido (usado pelo parent para context; não alteramos).
        X : np.ndarray, shape (n_individuals, n_var)
            Cromossomos (permutações) dos indivíduos selecionados para mutação.

        Returns
        -------
        Y : np.ndarray, shape (n_individuals, n_var)
            Cromossomos com inversão aplicada.
        """
        Y = X.copy()
        n_individuals, n_var = Y.shape

        for i in range(n_individuals):
            # Seleciona dois pontos de corte distintos no intervalo [0, n_var)
            a, b = sorted(np.random.choice(n_var, 2, replace=False))
            # Inverte o segmento [a, b] inclusive
            Y[i, a:b + 1] = Y[i, a:b + 1][::-1]

        return Y
