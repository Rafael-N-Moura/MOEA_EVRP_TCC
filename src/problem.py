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
    
    Restrições:
    - G1: Capacidade de carga (sempre 0, tratado pelo decoder)
    - G2: Violação de bateria (déficit de energia, positivo se violação)
    """
    
    def __init__(
        self,
        context: Context,
        use_constraints: bool = False,
        force_battery_feasible: bool = False,
        use_radical_infeasible: bool = False
    ):
        """
        Inicializa o problema.

        Args:
            context: Contexto global com mapa e parâmetros
            use_constraints: Se True, usa restrições (G) em vez de penalização
            force_battery_feasible: Se True, força viabilidade de bateria no decoder
            use_radical_infeasible: Se True e force_battery_feasible=False, decoder em modo
                                   radical (sem estações). Maior gap inviável vs viável.
        """
        self.context = context
        self.use_constraints = use_constraints
        self.force_battery_feasible = force_battery_feasible
        self.use_radical_infeasible = use_radical_infeasible
        n_customers = len(context.customers)
        
        # Define problema: n variáveis (permutação de clientes), 2 objetivos
        # Se usar restrições, adiciona 2 restrições (G1=capacidade, G2=bateria)
        n_constr = 2 if use_constraints else 0
        
        super().__init__(
            n_var=n_customers,
            n_obj=2,
            n_constr=n_constr,
            xl=0,
            xu=n_customers - 1,
            elementwise_evaluation=True
        )
    
    def _evaluate(self, x, out, *args, **kwargs):
        """
        Avalia um indivíduo (permutação de clientes).
        
        Args:
            x: Array numpy com permutação de índices (genótipo) ou objeto Individual
            out: Dicionário de saída do Pymoo
        """
        # CRÍTICO: O pymoo pode passar um objeto Individual em vez de array numpy
        # em certos contextos (ex: quando chamado através de problem.evaluate()).
        # Precisamos extrair o array X se x for um Individual.
        if hasattr(x, 'X'):
            # x é um objeto Individual - extrai o array X
            x = x.X
        elif not isinstance(x, np.ndarray):
            # x não é array numpy nem Individual - tenta converter
            try:
                x = np.array(x)
            except (TypeError, ValueError):
                # Se falhar, tenta acessar como atributo
                if hasattr(x, 'get'):
                    x = x.get("X")
                else:
                    raise TypeError(f"Tipo inesperado para x: {type(x)}. Esperado array numpy ou Individual.")
        
        # Converte array numpy para lista de inteiros
        individual = x.astype(int).tolist()
        
        # Decodifica genótipo em fenótipo (solução)
        # Durante evolução, sempre usa force_battery_feasible=False para expor violações
        # O sampling híbrido será tratado na inicialização do algoritmo
        solution = decode(
            individual,
            self.context,
            force_battery_feasible=self.force_battery_feasible,
            use_radical_infeasible=getattr(self, "use_radical_infeasible", False)
        )
        
        # Extrai objetivos
        f1 = solution.total_cost  # Custo total (veículos + distância)
        f2 = solution.avg_dissatisfaction  # Insatisfação média
        
        if self.use_constraints:
            # Modo com restrições: expõe violações como G (restrições)
            # G1: Capacidade de carga (sempre 0, tratado pelo decoder)
            g1 = 0.0
            
            # G2: Violação de bateria (déficit de energia)
            # Valor positivo = violação, 0 ou negativo = viável
            g2 = solution.battery_violation
            
            out["F"] = np.array([f1, f2])
            out["G"] = np.array([g1, g2])
        else:
            # Modo com penalização (compatibilidade com código antigo)
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
