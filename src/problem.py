"""
Módulo de Adaptação para Pymoo.
Conecta a lógica de negócio (decoder) à biblioteca de otimização.
"""

import numpy as np
from pymoo.core.problem import ElementwiseProblem
from .model import Context
from .decoder import decode


# Constantes de penalização (apenas para violações físicas graves)
PENALTY_COST = 100000  # Penalidade para custo em caso de violação física
PENALTY_DISSATISFACTION = 1.0  # Penalidade para insatisfação (máxima insatisfação)


class EVRPTWProblem(ElementwiseProblem):
    """
    Problema Multi-Objetivo EVRPTW-PR adaptado para Pymoo.
    
    Objetivos:
    - f1: Minimizar custo total (veículos + distância)
    - f2: Minimizar insatisfação média (0.0 = totalmente satisfeito, 1.0 = totalmente insatisfeito)
    """
    
    def __init__(self, context: Context):
        """
        Inicializa o problema.
        
        Args:
            context: Contexto global com mapa e parâmetros
        """
        self.context = context
        n_customers = len(context.customers)
        
        # Define problema: n variáveis (permutação de clientes), 2 objetivos
        super().__init__(
            n_var=n_customers,
            n_obj=2,
            n_constr=0,  # Sem restrições explícitas (penalização no objetivo)
            xl=0,
            xu=n_customers - 1,
            elementwise_evaluation=True
        )
    
    def _evaluate(self, x, out, *args, **kwargs):
        """
        Avalia um indivíduo (permutação de clientes).
        
        Args:
            x: Array numpy com permutação de índices (genótipo)
            out: Dicionário de saída do Pymoo
        """
        # Converte array numpy para lista de inteiros
        individual = x.astype(int).tolist()
        
        # Decodifica genótipo em fenótipo (solução)
        solution = decode(individual, self.context)
        
        # Extrai objetivos
        f1 = solution.total_cost  # Custo total (veículos + distância)
        f2 = solution.avg_dissatisfaction  # Insatisfação média
        
        # Aplicação de penalidade apenas para violações físicas graves (bateria/carga)
        # Violações de tempo não marcam como inviável, apenas aumentam insatisfação
        if not solution.is_feasible:
            f1 = f1 + PENALTY_COST
            f2 = min(1.0, f2 + PENALTY_DISSATISFACTION)  # Limita em 1.0
            # Justificativa: Garante que soluções fisicamente inviáveis sejam dominadas
            # por soluções viáveis na seleção do NSGA-II
        
        # Retorna objetivos
        out["F"] = np.array([f1, f2])
        
        # Opcional: armazena solução completa para análise posterior
        if hasattr(self, '_last_solution'):
            self._last_solution = solution
