"""
Módulo de Adaptação para Pymoo.
Conecta a lógica de negócio (decoder) à biblioteca de otimização.
"""

import numpy as np
from pymoo.core.problem import ElementwiseProblem
from typing import List
from .model import Context
from .decoder import decode


# Constantes de penalização (apenas para violações físicas graves)
PENALTY_MULTIPLIER = 100000  # Multiplicador de penalidade para violações físicas

# Mapeamento de nomes de objetivos para valores na Solution
OBJECTIVE_MAP = {
    'vehicles': 'val_vehicles',
    'distance': 'val_distance',
    'duration': 'val_duration',
    'time_window': 'val_time_window_violation',
    'wait_time': 'val_wait_time',
    'recharge_time': 'val_recharge_time'
}


class EVRPFlexProblem(ElementwiseProblem):
    """
    Problema Multi-Objetivo EVRPTW-PR adaptado para Pymoo com seleção dinâmica de objetivos.
    
    Permite selecionar quais dos 6 objetivos atômicos serão otimizados:
    - vehicles: Número de Veículos (K)
    - distance: Distância Total Percorrida (D)
    - duration: Duração Total das Rotas (T)
    - time_window: Violação de Janelas de Tempo (Tw)
    - wait_time: Tempo de Espera (W)
    - recharge_time: Tempo de Recarga (Rc)
    """
    
    def __init__(self, context: Context, objectives: List[str] = None):
        """
        Inicializa o problema com seleção dinâmica de objetivos.
        
        Args:
            context: Contexto global com mapa e parâmetros
            objectives: Lista de strings indicando quais objetivos usar.
                       Ex: ['vehicles', 'distance'] para 2 objetivos
                       Ex: ['vehicles', 'distance', 'duration', 'time_window', 'wait_time', 'recharge_time'] para 6
                       Se None, usa todos os 6 objetivos.
        """
        self.context = context
        n_customers = len(context.customers)
        
        # Define objetivos (padrão: todos os 6)
        if objectives is None:
            objectives = ['vehicles', 'distance', 'duration', 'time_window', 'wait_time', 'recharge_time']
        
        # Valida objetivos
        valid_objectives = set(OBJECTIVE_MAP.keys())
        invalid = set(objectives) - valid_objectives
        if invalid:
            raise ValueError(f"Objetivos inválidos: {invalid}. Válidos: {valid_objectives}")
        
        self.objectives = objectives
        n_obj = len(objectives)
        
        # Define problema: n variáveis (permutação de clientes), n_obj objetivos
        super().__init__(
            n_var=n_customers,
            n_obj=n_obj,
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
        
        # Extrai objetivos dinamicamente
        objective_values = []
        for obj_name in self.objectives:
            attr_name = OBJECTIVE_MAP[obj_name]
            value = getattr(solution, attr_name)
            objective_values.append(value)
        
        # Aplicação de penalidade para violações físicas graves (bateria/carga)
        # Penalização proporcional ao número de violações físicas
        if not solution.is_feasible:
            # Conta apenas violações físicas (bateria/carga), não violações de tempo
            physical_violations = sum(1 for v in solution.violations 
                                    if "Bateria" in v or "carga" in v.lower())
            # Penalidade proporcional: base + (violações * fator)
            # Isso permite diferenciar soluções com diferentes níveis de violação
            base_penalty = PENALTY_MULTIPLIER * 0.1  # Base menor
            violation_penalty = physical_violations * (PENALTY_MULTIPLIER * 0.01)  # Por violação
            penalty = base_penalty + violation_penalty
            objective_values = [v + penalty for v in objective_values]
        
        # Retorna objetivos
        out["F"] = np.array(objective_values)
        
        # Opcional: armazena solução completa para análise posterior
        if hasattr(self, '_last_solution'):
            self._last_solution = solution


# Mantém classe antiga para compatibilidade
class EVRPTWProblem(EVRPFlexProblem):
    """
    Problema Multi-Objetivo EVRPTW-PR (compatibilidade com código antigo).
    Usa objetivos agregados: custo e insatisfação.
    """
    
    def __init__(self, context: Context):
        """
        Inicializa o problema com objetivos agregados (custo e insatisfação).
        
        Args:
            context: Contexto global com mapa e parâmetros
        """
        # Usa objetivos básicos para compatibilidade
        super().__init__(context, objectives=['vehicles', 'distance'])
    
    def _evaluate(self, x, out, *args, **kwargs):
        """
        Avalia um indivíduo usando objetivos agregados (custo e insatisfação).
        """
        # Converte array numpy para lista de inteiros
        individual = x.astype(int).tolist()
        
        # Decodifica genótipo em fenótipo (solução)
        solution = decode(individual, self.context)
        
        # Extrai objetivos agregados
        f1 = solution.total_cost  # Custo total (veículos + distância)
        f2 = solution.avg_dissatisfaction  # Insatisfação média
        
        # Aplicação de penalidade para violações físicas
        if not solution.is_feasible:
            f1 = f1 + PENALTY_MULTIPLIER
            f2 = min(1.0, f2 + 1.0)  # Limita insatisfação em 1.0
        
        # Retorna objetivos
        out["F"] = np.array([f1, f2])
        
        # Opcional: armazena solução completa para análise posterior
        if hasattr(self, '_last_solution'):
            self._last_solution = solution
