"""
Algoritmo NSGA-II customizado com Directed Mating focado em bateria.

Implementa estratégias para preservar soluções inviáveis (com violação de bateria)
e forçar acasalamento entre soluções viáveis e inviáveis para melhorar convergência.
"""

import math
import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.sampling import Sampling
from pymoo.core.selection import Selection
from pymoo.core.crossover import Crossover
from pymoo.core.mutation import Mutation
from pymoo.core.population import Population
from pymoo.operators.sampling.rnd import PermutationRandomSampling
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation
from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting
from pymoo.core.variable import get
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pymoo.core.problem import Problem


def calculate_crowding_distance(F):
    """
    Calcula crowding distance para um conjunto de soluções.
    
    Args:
        F: Array numpy de shape (n, m) onde n é número de soluções e m é número de objetivos
    
    Returns:
        Array numpy de shape (n,) com crowding distances
    """
    n_points, n_obj = F.shape
    
    if n_points <= 2:
        # Se há 2 ou menos pontos, todos têm distância infinita
        return np.full(n_points, np.inf)
    
    # Inicializa crowding distance
    distance = np.zeros(n_points)
    
    # Para cada objetivo
    for m in range(n_obj):
        # Ordena por objetivo m
        sorted_indices = np.argsort(F[:, m])
        sorted_F = F[sorted_indices, m]
        
        # Pontos extremos têm distância infinita
        distance[sorted_indices[0]] = np.inf
        distance[sorted_indices[-1]] = np.inf
        
        # Calcula distância normalizada para pontos intermediários
        f_range = sorted_F[-1] - sorted_F[0]
        if f_range > 0:
            for i in range(1, n_points - 1):
                distance[sorted_indices[i]] += (sorted_F[i + 1] - sorted_F[i - 1]) / f_range
    
    return distance


class HybridSampling(Sampling):
    """
    Sampling híbrido que gera 50% da população com force_battery_feasible=True
    e 50% com force_battery_feasible=False.
    """
    
    def __init__(self, problem: 'Problem' = None, **kwargs):
        super().__init__(**kwargs)
        self.problem = problem
        self.base_sampling = PermutationRandomSampling()
    
    def _do(self, problem, n_samples, **kwargs):
        # Gera permutações aleatórias
        X = self.base_sampling._do(problem, n_samples, **kwargs)
        
        # Marca quais indivíduos devem usar force_battery_feasible=True
        # Primeira metade usa True, segunda metade usa False
        n_feasible = n_samples // 2
        feasible_mask = np.zeros(n_samples, dtype=bool)
        feasible_mask[:n_feasible] = True
        
        # Armazena máscara no problema para uso durante avaliação
        if hasattr(problem, '_sampling_feasible_mask'):
            problem._sampling_feasible_mask = feasible_mask
        else:
            problem._sampling_feasible_mask = feasible_mask
        
        return X


class InfeasibleSurvival(Selection):
    """
    Estratégia de sobrevivência que preserva uma porcentagem de soluções inviáveis.
    
    Divide população em:
    - Grupo A (Viáveis): G2 <= 0
    - Grupo B (Inviáveis): G2 > 0
    
    Preenche população com:
    - Cota de viáveis: usando Rank & Crowding Distance
    - Cota de inviáveis: ordenados por Shadow Cost (SC = f1 + gamma*G2)
    
    Shadow Cost:
    - Penaliza violações de bateria (G2) proporcionalmente à sua gravidade
    - Gamma é calculado dinamicamente baseado no contexto do problema
    - severity_multiplier = 20.0 (aumentado para desencorajar violações triviais)
    """
    
    def __init__(self, infeasible_ratio: float = 0.25):
        """
        Args:
            infeasible_ratio: Proporção de soluções inviáveis a preservar (0.2 a 0.3)
        """
        super().__init__()
        self.infeasible_ratio = infeasible_ratio
    
    def _do(self, pop, n_select, n_parents=1, **kwargs):
        """
        Seleciona exatamente n_select indivíduos da população combinada (pais + filhos).
        
        Implementa lógica de cotas rígidas:
        - Cota inviável: n_select * infeasible_ratio
        - Cota viável: n_select - cota_inviável
        
        Garante que exatamente n_select indivíduos sejam retornados (corte rígido).
        """
        # CRÍTICO: Cotas baseadas em n_select (tamanho desejado), não em len(pop)
        n_infeasible_target = int(n_select * self.infeasible_ratio)
        n_feasible_target = n_select - n_infeasible_target
        
        # GARANTE mínimo de soluções viáveis (10% da população)
        # Isso previne desaparecimento completo de soluções viáveis
        min_feasible = max(1, int(n_select * 0.10))  # Pelo menos 10% ou 1 solução
        
        # Separa em viáveis e inviáveis baseado em G2
        feasible_mask = pop.get("G")[:, 1] <= 0  # G2 <= 0
        feasible_indices = np.where(feasible_mask)[0]
        infeasible_indices = np.where(~feasible_mask)[0]
        
        selected = []
        
        # ===== PASSO 1: Seleção de Viáveis (Rank & Crowding Distance) =====
        if len(feasible_indices) > 0:
            feasible_pop = pop[feasible_indices]
            
            # Non-dominated sorting
            nds = NonDominatedSorting()
            fronts = nds.do(feasible_pop.get("F"))
            
            # Ordena por rank (frente) e crowding distance
            feasible_sorted = []
            for rank, front_indices in enumerate(fronts):
                rank_pop = feasible_pop[front_indices]
                
                if len(rank_pop) > 2:
                    # Calcula crowding distance
                    cd = calculate_crowding_distance(rank_pop.get("F"))
                    # Ordena índices da frente por crowding distance (maior primeiro)
                    sorted_within_front = np.array(front_indices)[np.argsort(-cd)]
                    feasible_sorted.extend(sorted_within_front.tolist())
                else:
                    feasible_sorted.extend(front_indices)
            
            # CORTE RÍGIDO: Seleciona no máximo n_feasible_target
            # MAS garante mínimo de min_feasible viáveis
            n_select_feasible = max(min_feasible, min(n_feasible_target, len(feasible_sorted)))
            selected_feasible = feasible_indices[feasible_sorted[:n_select_feasible]]
            selected.extend(selected_feasible.tolist())
            
            # Se há menos viáveis que a cota, ajusta cota de inviáveis
            if n_select_feasible < n_feasible_target:
                n_infeasible_target = n_select - len(selected)
        else:
            # PROBLEMA: Não há soluções viáveis na população
            # Isso não deveria acontecer, mas se acontecer, vamos tentar "reparar" algumas
            # Por enquanto, apenas logamos o problema
            print(f"AVISO: Nenhuma solução viável encontrada na população de {len(pop)} indivíduos!")
            print(f"  G2 min: {pop.get('G')[:, 1].min():.2f}, max: {pop.get('G')[:, 1].max():.2f}")
            print(f"  Tentando selecionar soluções com menor G2...")
            
            # Fallback: Seleciona soluções com menor G2 (menos inviáveis)
            G2_values = pop.get("G")[:, 1]
            least_infeasible_indices = np.argsort(G2_values)[:min_feasible]
            selected.extend(least_infeasible_indices.tolist())
            # Ajusta cota de inviáveis
            n_infeasible_target = n_select - len(selected)
        
        # ===== PASSO 2: Seleção de Inviáveis (por Shadow Cost) =====
        if len(infeasible_indices) > 0 and len(selected) < n_select:
            infeasible_pop = pop[infeasible_indices]
            F = infeasible_pop.get("F")
            G = infeasible_pop.get("G")
            
            f1_values = F[:, 0]  # Custo (f1)
            g2_values = G[:, 1]  # Violação de bateria (G2)
            
            # Calcula Shadow Cost: SC = f1 + (gamma * G2)
            # Gamma é calculado baseado no contexto do problema
            gamma = None
            if 'algorithm' in kwargs and hasattr(kwargs['algorithm'], 'problem'):
                problem = kwargs['algorithm'].problem
                if hasattr(problem, 'context'):
                    context = problem.context
                    # Calcula gamma baseado no custo de energia
                    # Gamma = (km_per_kWh * distance_cost) * severity_multiplier
                    km_per_kwh = 1.0 / context.consumption_rate
                    base_energy_cost = km_per_kwh * context.distance_cost
                    severity_multiplier = 5.0  # Aumentado de 5.0 para desencorajar violações triviais
                    gamma = base_energy_cost * severity_multiplier
                    print(f"  [SHADOW_COST] Gamma calculado: {gamma:.2f} (base={base_energy_cost:.2f}, severity={severity_multiplier})")
            
            if gamma is None:
                # Fallback: usa gamma fixo se não conseguir acessar contexto
                # Estimativa conservadora: assume que 1 kWh = 2 km e custo = 2.0/km
                # Então base_energy_cost = 2 km/kWh * 2.0 R$/km = 4.0 R$/kWh
                # Com severity_multiplier = 20.0: gamma = 80.0
                gamma = 80.0
                print(f"  [SHADOW_COST] AVISO: Usando gamma fixo (fallback): {gamma:.2f}")
            
            # Calcula Shadow Cost para cada inviável
            shadow_costs = f1_values + (gamma * g2_values)
            
            # Ordena por menor Shadow Cost (menor = melhor)
            infeasible_sorted = infeasible_indices[np.argsort(shadow_costs)]
            
            # Log das top 3 soluções inviáveis (para debug)
            if len(shadow_costs) > 0:
                top3_indices = np.argsort(shadow_costs)[:min(3, len(shadow_costs))]
                print(f"  [SHADOW_COST] Top 3 inviáveis: ", end="")
                for idx in top3_indices:
                    orig_idx = infeasible_indices[idx]
                    print(f"f1={f1_values[idx]:.1f}, G2={g2_values[idx]:.2f}, SC={shadow_costs[idx]:.1f} | ", end="")
                print()
            
            # CORTE RÍGIDO: Seleciona no máximo n_infeasible_target
            n_remaining = n_select - len(selected)
            n_select_infeasible = min(n_infeasible_target, len(infeasible_sorted), n_remaining)
            selected_infeasible = infeasible_sorted[:n_select_infeasible]
            selected.extend(selected_infeasible.tolist())
        
        # ===== PASSO 3: Completar com Viáveis Restantes (se necessário) =====
        if len(selected) < n_select:
            remaining_feasible = [i for i in feasible_indices if i not in selected]
            if len(remaining_feasible) > 0:
                remaining_pop = pop[remaining_feasible]
                f1_values = remaining_pop.get("F")[:, 0]
                remaining_sorted = np.array(remaining_feasible)[np.argsort(f1_values)]
                n_needed = n_select - len(selected)
                selected.extend(remaining_sorted[:n_needed].tolist())
        
        # ===== PASSO 4: Completar com Inviáveis Restantes (se necessário) =====
        if len(selected) < n_select:
            remaining_infeasible = [i for i in infeasible_indices if i not in selected]
            if len(remaining_infeasible) > 0:
                n_needed = n_select - len(selected)
                selected.extend(remaining_infeasible[:n_needed].tolist())
        
        # ===== VERIFICAÇÃO DE SEGURANÇA: Garante exatamente n_select =====
        # Se por algum motivo ainda faltam, completa aleatoriamente (raro, mas evita crash)
        if len(selected) < n_select:
            all_indices = list(range(len(pop)))
            remaining = [i for i in all_indices if i not in selected]
            n_needed = n_select - len(selected)
            if len(remaining) >= n_needed:
                selected.extend(np.random.choice(remaining, size=n_needed, replace=False).tolist())
            else:
                selected.extend(remaining)
        
        # CORTE FINAL: Se por algum motivo selecionou mais que n_select, trunca
        if len(selected) > n_select:
            selected = selected[:n_select]
        
        # Garante que retorna exatamente n_select (verificação final)
        if len(selected) != n_select:
            # Log de erro para debug (mas não quebra execução)
            print(f"AVISO: InfeasibleSurvival selecionou {len(selected)} indivíduos, esperado {n_select}. Ajustando...")
            if len(selected) < n_select:
                # Completa com os primeiros disponíveis (fallback)
                all_indices = list(range(len(pop)))
                remaining = [i for i in all_indices if i not in selected]
                n_needed = n_select - len(selected)
                if len(remaining) >= n_needed:
                    selected.extend(remaining[:n_needed])
                else:
                    selected.extend(remaining)
                    # Se ainda faltam, repete alguns (último recurso)
                    while len(selected) < n_select:
                        selected.append(selected[0] if len(selected) > 0 else 0)
            else:
                # Se selecionou mais, trunca
                selected = selected[:n_select]
        
        # Converte para lista de inteiros Python (não numpy)
        result = []
        for idx in selected:
            if isinstance(idx, (np.integer, np.int64, np.int32)):
                result.append(int(idx))
            else:
                result.append(int(idx))
        
        # Verificação final: deve ter exatamente n_select
        assert len(result) == n_select, f"Erro crítico: retornou {len(result)} índices, esperado {n_select}"
        
        return result


class DirectedMatingSelection(Selection):
    """
    Estratégia de acasalamento direcionado.
    
    Seleciona pais de forma que:
    - Pai 1: Do grupo de viáveis (G2 <= 0)
    - Pai 2: Do grupo de inviáveis (G2 > 0)
    
    Isso força cruzamento entre soluções seguras e soluções eficientes.
    """
    
    def _do(self, pop, n_select, n_parents=2, **kwargs):
        n = n_select
        
        # Separa em viáveis e inviáveis
        feasible_mask = pop.get("G")[:, 1] <= 0
        feasible_indices = np.where(feasible_mask)[0]
        infeasible_indices = np.where(~feasible_mask)[0]
        
        selected = []
        
        for i in range(n):
            # Pai 1: Seleciona do grupo viável (aleatório ou por torneio)
            if len(feasible_indices) > 0:
                parent1_idx = np.random.choice(feasible_indices)
            else:
                # Fallback: seleciona qualquer um se não há viáveis
                parent1_idx = np.random.choice(len(pop))
            
            # Pai 2: Seleciona do grupo inviável (aleatório ou por torneio)
            if len(infeasible_indices) > 0:
                parent2_idx = np.random.choice(infeasible_indices)
            else:
                # Fallback: seleciona qualquer um se não há inviáveis
                parent2_idx = np.random.choice(len(pop))
            
            selected.append([parent1_idx, parent2_idx])
        
        return np.array(selected)


class BatteryFocusedNSGA2(NSGA2):
    """
    Variante do NSGA-II com Directed Mating focado em bateria.
    
    Características:
    1. Sampling híbrido: 50% viável, 50% inviável na inicialização
    2. Sobrevivência de inviáveis: preserva ~25% de soluções inviáveis ordenadas por custo
    3. Acasalamento direcionado: cruza viáveis com inviáveis
    """
    
    def __init__(
        self,
        pop_size=100,
        infeasible_ratio=0.25,
        sampling=None,
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
        eliminate_duplicates=True,
        **kwargs
    ):
        """
        Args:
            pop_size: Tamanho da população
            infeasible_ratio: Proporção de soluções inviáveis a preservar
            sampling: Estratégia de sampling (usa HybridSampling se None)
            crossover: Operador de crossover
            mutation: Operador de mutação
            eliminate_duplicates: Se True, elimina duplicatas
        """
        # Cria sampling híbrido se não fornecido
        if sampling is None:
            # Será configurado após problema ser definido
            sampling = PermutationRandomSampling()
        
        super().__init__(
            pop_size=pop_size,
            sampling=sampling,
            crossover=crossover,
            mutation=mutation,
            eliminate_duplicates=eliminate_duplicates,
            **kwargs
        )
        
        self.infeasible_ratio = infeasible_ratio
        self._hybrid_sampling = None
        self._infeasible_survival = InfeasibleSurvival(infeasible_ratio)
        self._directed_mating = DirectedMatingSelection()
        # Armazena operadores explicitamente para uso em _advance
        self._crossover_op = crossover
        self._mutation_op = mutation
        # Rastreia número de geração para logs
        self._current_gen = 0
        
        # Substitui o mating padrão para usar nossa seleção customizada
        # Isso evita que o NSGA2 padrão tente usar tournament selection que precisa de crowding distance
        from pymoo.core.mating import Mating
        
        # Cria um mating customizado que usa nossa seleção direcionada
        class CustomMating(Mating):
            def __init__(self, crossover, mutation, directed_mating):
                super().__init__(selection=None, crossover=crossover, mutation=mutation)
                self._directed_mating = directed_mating
            
            def _do(self, problem, pop, n_offsprings, **kwargs):
                """
                Realiza mating (crossover + mutation) com validações de X.
                
                MODIFICAÇÕES:
                - Valida X antes de qualquer operação
                - Valida X antes de chamar crossover
                - Valida X após crossover
                - Valida X após mutation
                - Melhora tratamento de exceções com validação antes de retry
                """
                # VALIDAÇÃO 1: Antes de qualquer operação, valida pop
                pop = BatteryFocusedNSGA2._validate_and_fix_pop_X(pop, problem, log_prefix="[CUSTOM_MATING] Pre-op: ")
                
                # Usa seleção direcionada em vez de tournament
                # Calcula quantos matings são necessários
                n_matings = math.ceil(n_offsprings / self.crossover.n_offsprings)
                
                # Obtém índices dos pais (array 2D com shape (n_matings, n_parents))
                parents_array = self._directed_mating._do(pop, n_matings, n_parents=2, **kwargs)
                
                # Converte para lista de listas (formato esperado por crossover.do())
                parents = parents_array.tolist()
                
                # VALIDAÇÃO 2: Antes de chamar crossover, valida pop novamente
                # (pode ter sido modificada por operações anteriores)
                pop = BatteryFocusedNSGA2._validate_and_fix_pop_X(pop, problem, log_prefix="[CUSTOM_MATING] Pre-crossover: ")
                
                # CRÍTICO: O crossover.do() espera (problem, pop, parents, ...)
                # Onde pop é a Population original e parents é lista de listas de índices
                # O crossover.do() então faz: pop = [pop[mating] for mating in parents]
                # Isso cria uma lista de Population objects, cada um com os pais para um mating
                try:
                    _off = self.crossover.do(problem, pop, parents, **kwargs)
                except (ValueError, AttributeError, TypeError) as e:
                    # Se falhar, tenta corrigir pop e tentar novamente
                    print(f"[CUSTOM_MATING] Crossover falhou: {e}. Tentando corrigir Population...")
                    pop = BatteryFocusedNSGA2._validate_and_fix_pop_X(pop, problem, log_prefix="[CUSTOM_MATING] Retry-crossover: ")
                    _off = self.crossover.do(problem, pop, parents, **kwargs)
                
                # VALIDAÇÃO 3: Após crossover, valida offspring
                _off = BatteryFocusedNSGA2._validate_and_fix_pop_X(_off, problem, log_prefix="[CUSTOM_MATING] Post-crossover: ")
                
                # Aplica mutation
                off = self.mutation.do(problem, _off, **kwargs)
                
                # VALIDAÇÃO 4: Após mutation, valida offspring
                off = BatteryFocusedNSGA2._validate_and_fix_pop_X(off, problem, log_prefix="[CUSTOM_MATING] Post-mutation: ")
                
                return off
        
        # Substitui o mating padrão
        self.mating = CustomMating(crossover, mutation, self._directed_mating)
    
    @staticmethod
    def _validate_and_fix_pop_X(pop, problem, log_prefix=""):
        """
        Valida e corrige o atributo X de cada Individual na Population.
        
        Garante que:
        - X é um numpy.ndarray
        - X tem shape (n_var,)
        - X tem dtype apropriado (int para permutações)
        
        Args:
            pop: Population object
            problem: Problem object (para obter n_var)
            log_prefix: Prefixo para logs (opcional)
        
        Returns:
            Population: Nova Population com X corrigido (ou pop original se já estava correto)
        """
        X_list = []
        needs_fix = False
        fix_reasons = []
        
        for i, individual in enumerate(pop):
            x_val = individual.X
            original_type = type(x_val)
            original_shape = x_val.shape if hasattr(x_val, 'shape') else 'N/A'
            original_dtype = x_val.dtype if hasattr(x_val, 'dtype') else 'N/A'
            
            # Verifica se precisa corrigir
            if not isinstance(x_val, np.ndarray):
                needs_fix = True
                x_val = np.array(x_val)
                fix_reasons.append(
                    f"Individual {i}: {original_type} -> numpy.ndarray"
                )
            
            if x_val.ndim == 0:
                # ERRO CRÍTICO: X é escalar
                raise ValueError(
                    f"Individual {i} tem X como escalar: {x_val}. "
                    f"Isso indica corrupção grave da estrutura da Population. "
                    f"Tipo original: {original_type}, Shape original: {original_shape}"
                )
            
            if x_val.ndim > 1:
                needs_fix = True
                original_shape_before_flatten = x_val.shape
                x_val = x_val.flatten()
                fix_reasons.append(
                    f"Individual {i}: shape {original_shape_before_flatten} -> {x_val.shape} (flattened)"
                )
            
            if x_val.shape[0] != problem.n_var:
                raise ValueError(
                    f"Individual {i} tem X com shape {x_val.shape}, "
                    f"esperado ({problem.n_var},). "
                    f"Isso indica incompatibilidade entre genótipo e problema. "
                    f"Tipo original: {original_type}, Shape original: {original_shape}"
                )
            
            # Garante dtype int para permutações
            if x_val.dtype != int and x_val.dtype != np.int64 and x_val.dtype != np.int32:
                needs_fix = True
                original_dtype_before_cast = x_val.dtype
                x_val = x_val.astype(int)
                fix_reasons.append(
                    f"Individual {i}: dtype {original_dtype_before_cast} -> int"
                )
            
            X_list.append(x_val)
        
        # Se não precisa corrigir, retorna pop original
        if not needs_fix:
            return pop
        
        # Log das correções
        if log_prefix:
            print(f"{log_prefix}[FIX_X] Corrigidos {len(fix_reasons)} indivíduos:")
            for reason in fix_reasons[:5]:  # Mostra apenas os 5 primeiros
                print(f"{log_prefix}  - {reason}")
            if len(fix_reasons) > 5:
                print(f"{log_prefix}  ... e mais {len(fix_reasons) - 5} indivíduos")
        
        # Recria Population com X corrigido
        X_fixed = np.array(X_list)  # Shape: (len(pop), n_var)
        pop_fixed = Population.new("X", X_fixed)
        
        # Copia todos os outros atributos (F, G, CV, etc.)
        # Population não tem método keys(), então copiamos manualmente os atributos comuns
        # Nota: 'feas' e 'rank' são propriedades read-only calculadas automaticamente pelo Pymoo
        # a partir de G e CV, então não precisam ser copiadas
        if pop.has("F"):
            pop_fixed.set("F", pop.get("F"))
        if pop.has("G"):
            pop_fixed.set("G", pop.get("G"))
        if pop.has("CV"):
            pop_fixed.set("CV", pop.get("CV"))
        if pop.has("crowding"):
            pop_fixed.set("crowding", pop.get("crowding"))
        
        return pop_fixed
    
    def _set_optimum(self, **kwargs):
        """
        Sobrescreve _set_optimum do NSGA2 padrão para evitar que ele limpe nosso opt.
        
        O NSGA2 padrão chama este método e pode estar sobrescrevendo nosso opt
        com uma população vazia ou incorreta. Vamos garantir que opt nunca fique vazio.
        """
        # Se opt já existe e não está vazio, mantém (não sobrescreve)
        if hasattr(self, 'opt') and len(self.opt) > 0:
            # Verifica se opt ainda é válido (tem indivíduos com rank 0 ou é viável)
            if self.pop.has("rank"):
                # Se pop tem rank, verifica se opt ainda contém indivíduos com rank 0
                rank_0_indices = np.where(self.pop.get("rank") == 0)[0]
                if len(rank_0_indices) > 0:
                    # Opt pode precisar ser atualizado, mas não vamos limpar
                    # Deixa a atualização manual em _advance fazer o trabalho
                    pass
            # Mantém opt atual (não sobrescreve)
            return
        
        # Se opt não existe ou está vazio, usa lógica padrão do NSGA2
        # Mas com verificações para garantir que nunca fique vazio
        from pymoo.util.function import has_feasible
        
        if not has_feasible(self.pop):
            # Sem soluções viáveis, pega a com menor CV
            CV = self.pop.get("CV")
            if len(CV) > 0:
                min_cv_idx = np.argmin(CV)
                self.opt = self.pop[[min_cv_idx]]
            else:
                # Fallback: primeiro indivíduo
                if len(self.pop) > 0:
                    self.opt = Population.create(self.pop[0])
                else:
                    self.opt = Population()
        else:
            # Com soluções viáveis, pega rank 0
            if self.pop.has("rank"):
                rank_0_indices = np.where(self.pop.get("rank") == 0)[0]
                if len(rank_0_indices) > 0:
                    self.opt = self.pop[rank_0_indices]
                else:
                    # Fallback: primeiro indivíduo viável
                    feasible_mask = self.pop.get("feas")
                    if np.any(feasible_mask):
                        feasible_indices = np.where(feasible_mask)[0]
                        self.opt = Population.create(self.pop[feasible_indices[0]])
                    else:
                        # Último recurso: primeiro indivíduo
                        if len(self.pop) > 0:
                            self.opt = Population.create(self.pop[0])
                        else:
                            self.opt = Population()
            else:
                # Pop não tem rank, usa primeiro indivíduo
                if len(self.pop) > 0:
                    self.opt = Population.create(self.pop[0])
                else:
                    self.opt = Population()
        
        # VERIFICAÇÃO FINAL: Garante que opt nunca fique vazio
        if len(self.opt) == 0 and len(self.pop) > 0:
            self.opt = Population.create(self.pop[0])
    
    def _initialize_advance(self, infills=None, **kwargs):
        """
        Inicializa população com sampling híbrido seguindo estratégia de fusão.
        
        Fluxo:
        1. Amostragem Pura: Gera N genótipos (X) brutos
        2. Fissionamento: Divide em dois lotes (X_feasible, X_infeasible)
        3. Encapsulamento Temporário: Cria duas populações virgens
        4. Avaliação Condicionada: Avalia cada lote com flag diferente
        5. Fusão: Merge das duas populações em self.pop
        """
        # Inicializa contador de geração
        self._current_gen = 0
        
        # O problema está disponível como self.problem após setup
        problem = self.problem
        
        # Cria sampling híbrido
        self._hybrid_sampling = HybridSampling(problem)
        self.sampling = self._hybrid_sampling
        
        # ===== PASSO 1: Amostragem Pura =====
        # Gera N genótipos (cromossomos X) brutos
        X = self.sampling.do(problem, self.pop_size, **kwargs)
        
        # VALIDAÇÃO 1: Garante que X retornado pelo sampling está correto
        # sampling.do() pode retornar Population ou array numpy, precisamos extrair X se necessário
        if isinstance(X, Population):
            # Se retornou Population, extrai o array X
            X = X.get("X", to_numpy=True)
        elif not isinstance(X, np.ndarray):
            # Se não é array numpy nem Population, tenta converter
            X = np.array(X)
        
        # Garante numpy array e dtype int
        X = np.array(X, dtype=int)
        assert X.ndim == 2, f"X do sampling deve ser 2D, mas tem shape {X.shape}"
        assert X.shape == (self.pop_size, problem.n_var), \
            f"X deve ter shape ({self.pop_size}, {problem.n_var}), mas tem {X.shape}"
        
        # ===== PASSO 2: Fissionamento =====
        # Divide matematicamente em dois lotes
        n_feasible = self.pop_size // 2
        X_feasible = X[:n_feasible].copy()  # .copy() para evitar views
        X_infeasible = X[n_feasible:].copy()
        
        # VALIDAÇÃO 2: Garante que slices estão corretos
        assert X_feasible.ndim == 2, f"X_feasible deve ser 2D, mas tem shape {X_feasible.shape}"
        assert X_infeasible.ndim == 2, f"X_infeasible deve ser 2D, mas tem shape {X_infeasible.shape}"
        assert X_feasible.shape[0] == n_feasible, \
            f"X_feasible deve ter {n_feasible} linhas, mas tem {X_feasible.shape[0]}"
        assert X_infeasible.shape[0] == (self.pop_size - n_feasible), \
            f"X_infeasible deve ter {self.pop_size - n_feasible} linhas, mas tem {X_infeasible.shape[0]}"
        
        # ===== PASSO 3: Encapsulamento Temporário =====
        # Cria duas populações virgens contendo apenas os genótipos
        pop_feasible = Population.new("X", X_feasible)
        pop_infeasible = Population.new("X", X_infeasible)
        print(f"[INIT] Passo 3: Criadas populações - Viáveis: {len(pop_feasible)}, Inviáveis: {len(pop_infeasible)}")
        
        # VALIDAÇÃO 3: Verifica que Population objects foram criadas corretamente
        pop_feasible = self._validate_and_fix_pop_X(pop_feasible, problem, log_prefix="[INIT] Passo 3: ")
        pop_infeasible = self._validate_and_fix_pop_X(pop_infeasible, problem, log_prefix="[INIT] Passo 3: ")
        
        # ===== PASSO 4: Avaliação Condicionada =====
        # Salva estado original para restaurar depois
        original_flag = problem.force_battery_feasible if hasattr(problem, 'force_battery_feasible') else None
        
        try:
            if hasattr(problem, 'force_battery_feasible'):
                # Lote A: Modo Seguro (True) - Soluções com estações inseridas e G2 = 0
                problem.force_battery_feasible = True
                if len(X_feasible) > 0:
                    print(f"[INIT] Passo 4A: Avaliando {len(X_feasible)} indivíduos com force_battery_feasible=True")
                    # Usa problem.evaluate() diretamente com arrays numpy (evita erro de Individual)
                    out_feasible = problem.evaluate(X_feasible, return_as_dictionary=True, **kwargs)
                    F_feasible = out_feasible["F"]
                    if "G" in out_feasible:
                        G_feasible = out_feasible["G"]
                        pop_feasible.set("F", F_feasible)
                        pop_feasible.set("G", G_feasible)
                        # Log: Verifica quantos são realmente viáveis após avaliação
                        n_actually_feasible = np.sum(G_feasible[:, 1] <= 0)
                        print(f"[INIT] Passo 4A: Após avaliação - {n_actually_feasible}/{len(G_feasible)} realmente viáveis (G2 <= 0)")
                    else:
                        pop_feasible.set("F", F_feasible)
                        print(f"[INIT] Passo 4A: Avaliação concluída (sem restrições G)")
                
                # Lote B: Modo Arriscado (False) - Soluções diretas e G2 > 0
                problem.force_battery_feasible = False
                if len(X_infeasible) > 0:
                    print(f"[INIT] Passo 4B: Avaliando {len(X_infeasible)} indivíduos com force_battery_feasible=False")
                    # Usa problem.evaluate() diretamente com arrays numpy (evita erro de Individual)
                    out_infeasible = problem.evaluate(X_infeasible, return_as_dictionary=True, **kwargs)
                    F_infeasible = out_infeasible["F"]
                    if "G" in out_infeasible:
                        G_infeasible = out_infeasible["G"]
                        pop_infeasible.set("F", F_infeasible)
                        pop_infeasible.set("G", G_infeasible)
                        # Log: Verifica quantos são realmente inviáveis após avaliação
                        n_actually_infeasible = np.sum(G_infeasible[:, 1] > 0)
                        print(f"[INIT] Passo 4B: Após avaliação - {n_actually_infeasible}/{len(G_infeasible)} realmente inviáveis (G2 > 0)")
                    else:
                        pop_infeasible.set("F", F_infeasible)
                        print(f"[INIT] Passo 4B: Avaliação concluída (sem restrições G)")
            else:
                # Se problema não tem force_battery_feasible, avalia tudo normalmente
                if len(X_feasible) > 0:
                    out_feasible = problem.evaluate(X_feasible, return_as_dictionary=True, **kwargs)
                    F_feasible = out_feasible["F"]
                    if "G" in out_feasible:
                        G_feasible = out_feasible["G"]
                        pop_feasible.set("F", F_feasible)
                        pop_feasible.set("G", G_feasible)
                    else:
                        pop_feasible.set("F", F_feasible)
                
                if len(X_infeasible) > 0:
                    out_infeasible = problem.evaluate(X_infeasible, return_as_dictionary=True, **kwargs)
                    F_infeasible = out_infeasible["F"]
                    if "G" in out_infeasible:
                        G_infeasible = out_infeasible["G"]
                        pop_infeasible.set("F", F_infeasible)
                        pop_infeasible.set("G", G_infeasible)
                    else:
                        pop_infeasible.set("F", F_infeasible)
        finally:
            # Restaura estado padrão (geralmente False para evolução)
            if original_flag is not None:
                problem.force_battery_feasible = original_flag
        
        # VALIDAÇÃO 4: Após avaliação, verifica que X ainda está correto
        pop_feasible = self._validate_and_fix_pop_X(pop_feasible, problem, log_prefix="[INIT] Passo 4: ")
        pop_infeasible = self._validate_and_fix_pop_X(pop_infeasible, problem, log_prefix="[INIT] Passo 4: ")
        
        # ===== PASSO 5: Fusão na População Principal =====
        # As duas populações avaliadas são fundidas em uma única self.pop
        self.pop = Population.merge(pop_feasible, pop_infeasible)
        
        # VALIDAÇÃO 5: Após merge, verifica que X ainda está correto
        self.pop = self._validate_and_fix_pop_X(self.pop, problem, log_prefix="[INIT] Passo 5: ")
        print(f"[INIT] Passo 5: População fundida - Tamanho total: {len(self.pop)}")
        if self.pop.has("G"):
            G = self.pop.get("G")
            n_feasible_actual = np.sum(G[:, 1] <= 0)
            n_infeasible_actual = len(G) - n_feasible_actual
            pct_feasible = (n_feasible_actual / len(G)) * 100 if len(G) > 0 else 0.0
            print(f"[INIT] Passo 5: Após merge - Viáveis: {n_feasible_actual} ({pct_feasible:.1f}%), Inviáveis: {n_infeasible_actual}")
        
        # ===== PASSO 6: Inicialização do Arquivo de Ótimos (Opt) =====
        # Atualiza opt com soluções não-dominadas viáveis (se houver)
        print(f"[INIT] Passo 6: Atualizando opt...")
        self._update_opt_after_initialization()
        print(f"[INIT] Passo 6: Opt atualizado - Tamanho: {len(self.opt)}")
        if len(self.opt) > 0:
            if self.opt.has("G"):
                G_opt = self.opt.get("G")
                n_feasible_opt = np.sum(G_opt[:, 1] <= 0)
                print(f"[INIT] Passo 6: Opt contém {n_feasible_opt}/{len(self.opt)} soluções viáveis")
            if self.opt.has("cv"):
                cv_opt = self.opt.get("cv")
                print(f"[INIT] Passo 6: Opt tem 'cv' - min: {cv_opt.min() if len(cv_opt) > 0 else 'N/A'}, max: {cv_opt.max() if len(cv_opt) > 0 else 'N/A'}")
            else:
                print(f"[INIT] Passo 6: AVISO - Opt não tem 'cv' (será necessário calcular)")
        
        # Log: Estatísticas da população inicial
        if len(self.pop) > 0 and self.pop.has("G"):
            G = self.pop.get("G")
            n_feasible_actual = np.sum(G[:, 1] <= 0)
            n_infeasible_actual = len(G) - n_feasible_actual
            pct_feasible = (n_feasible_actual / len(G)) * 100 if len(G) > 0 else 0.0
            print(f"Gen {self._current_gen:3d} | Pop: {len(self.pop):3d} | Viáveis: {n_feasible_actual:3d} ({pct_feasible:5.1f}%) | Inviáveis: {n_infeasible_actual:3d} [Inicial]")
    
    def _update_opt_after_initialization(self):
        """
        Atualiza opt (soluções não-dominadas) após inicialização.
        Filtra apenas soluções viáveis (G2 <= 0) para opt.
        """
        if len(self.pop) == 0:
            print(f"[UPDATE_OPT] População vazia, criando opt vazio")
            self.opt = Population()
            return
        
        nds = NonDominatedSorting()
        F = self.pop.get("F")
        
        # Se há restrições, filtra apenas viáveis (G <= 0)
        if self.pop.has("G"):
            G = self.pop.get("G")
            cv = np.sum(np.maximum(G, 0), axis=1)
            feasible_mask = cv == 0
            n_feasible = np.sum(feasible_mask)
            print(f"[UPDATE_OPT] População tem {len(self.pop)} indivíduos, {n_feasible} viáveis (cv == 0)")
            
            if np.any(feasible_mask):
                feasible_pop = self.pop[feasible_mask]
                print(f"[UPDATE_OPT] Filtrando {len(feasible_pop)} soluções viáveis para opt")
                if len(feasible_pop) > 0:
                    F_feasible = feasible_pop.get("F")
                    fronts = nds.do(F_feasible)
                    print(f"[UPDATE_OPT] Non-dominated sorting encontrou {len(fronts)} frentes")
                    if len(fronts) > 0 and len(fronts[0]) > 0:
                        valid_indices = [idx for idx in fronts[0] if 0 <= idx < len(feasible_pop)]
                        if len(valid_indices) > 0:
                            self.opt = feasible_pop[valid_indices]
                            print(f"[UPDATE_OPT] Opt criado com {len(self.opt)} soluções da primeira frente viável")
                        else:
                            self.opt = feasible_pop
                            print(f"[UPDATE_OPT] Opt criado com todas as {len(self.opt)} soluções viáveis (índices inválidos)")
                    else:
                        self.opt = feasible_pop
                        print(f"[UPDATE_OPT] Opt criado com todas as {len(self.opt)} soluções viáveis (sem frentes)")
                else:
                    # Fallback: usa toda população
                    print(f"[UPDATE_OPT] AVISO: feasible_pop vazio após filtro, usando toda população como fallback")
                    fronts = nds.do(F)
                    if len(fronts) > 0 and len(fronts[0]) > 0:
                        self.opt = self.pop[fronts[0]]
                        print(f"[UPDATE_OPT] Opt criado com {len(self.opt)} soluções da primeira frente (fallback)")
                    else:
                        self.opt = self.pop
                        print(f"[UPDATE_OPT] Opt criado com toda população {len(self.opt)} (fallback, sem frentes)")
            else:
                # Sem soluções viáveis, usa todas as soluções
                print(f"[UPDATE_OPT] AVISO: Nenhuma solução viável encontrada, usando toda população")
                fronts = nds.do(F)
                if len(fronts) > 0 and len(fronts[0]) > 0:
                    self.opt = self.pop[fronts[0]]
                    print(f"[UPDATE_OPT] Opt criado com {len(self.opt)} soluções da primeira frente (sem viáveis)")
                else:
                    self.opt = self.pop
                    print(f"[UPDATE_OPT] Opt criado com toda população {len(self.opt)} (sem viáveis, sem frentes)")
        else:
            # Sem restrições, usa non-dominated sorting normal
            print(f"[UPDATE_OPT] População sem restrições G, usando non-dominated sorting normal")
            fronts = nds.do(F)
            if len(fronts) > 0 and len(fronts[0]) > 0:
                self.opt = self.pop[fronts[0]]
                print(f"[UPDATE_OPT] Opt criado com {len(self.opt)} soluções da primeira frente")
            else:
                self.opt = self.pop
                print(f"[UPDATE_OPT] Opt criado com toda população {len(self.opt)} (sem frentes)")
        
        # CRÍTICO: Garante que opt tenha G (cv será calculado automaticamente pelo Pymoo)
        # O display do pymoo precisa de opt.get("cv") para funcionar
        # cv é uma propriedade read-only calculada automaticamente a partir de G
        if len(self.opt) > 0 and self.pop.has("G") and not self.opt.has("G"):
            print(f"[UPDATE_OPT] AVISO: Opt não tem 'G', isso pode causar problemas")
            # Se opt não tem G, não podemos calcular cv
            # Isso não deveria acontecer se opt foi criado a partir de pop
        
        # Verificação final: garante que opt nunca fique vazio
        if len(self.opt) == 0:
            print(f"[UPDATE_OPT] AVISO CRÍTICO: Opt ficou vazio após todas as tentativas!")
            if len(self.pop) > 0:
                self.opt = Population.create(self.pop[0])
                # Garante que tem G (cv será calculado automaticamente pelo Pymoo)
                if self.pop.has("G") and not self.opt.has("G"):
                    print(f"[UPDATE_OPT] AVISO: Opt fallback não tem 'G'")
                print(f"[UPDATE_OPT] Opt criado com primeiro indivíduo como fallback (tamanho: {len(self.opt)})")
            else:
                self.opt = Population()
                print(f"[UPDATE_OPT] ERRO: População também está vazia, opt permanece vazio")
    
    def _advance(self, infills=None, **kwargs):
        """
        Avança uma geração com estratégias customizadas.
        
        MODIFICAÇÕES:
        - Valida X antes de chamar mating (crossover)
        - Valida X após criar offspring
        - Valida X após merge de pais e filhos
        - Valida X após survival selection
        """
        # Incrementa contador de geração
        self._current_gen += 1
        
        # VALIDAÇÃO 1: Antes de qualquer operação, valida pop atual
        self.pop = self._validate_and_fix_pop_X(self.pop, self.problem, log_prefix=f"[GEN {self._current_gen}] ")
        
        # Durante avaliação, sempre usa force_battery_feasible=False
        # para expor violações reais
        if hasattr(self.problem, 'force_battery_feasible'):
            self.problem.force_battery_feasible = False
        
        # Log: Estatísticas detalhadas da população atual (antes de gerar filhos)
        if len(self.pop) > 0 and self.pop.has("G"):
            G = self.pop.get("G")
            F = self.pop.get("F")
            n_feasible = np.sum(G[:, 1] <= 0)
            n_infeasible = len(G) - n_feasible
            pct_feasible = (n_feasible / len(G)) * 100 if len(G) > 0 else 0.0
            
            # Estatísticas dos viáveis
            if n_feasible > 0:
                feasible_mask = G[:, 1] <= 0
                F_feasible = F[feasible_mask]
                f1_feasible_mean = np.mean(F_feasible[:, 0])
                f1_feasible_min = np.min(F_feasible[:, 0])
                f2_feasible_mean = np.mean(F_feasible[:, 1])
                f2_feasible_min = np.min(F_feasible[:, 1])
            else:
                f1_feasible_mean = f1_feasible_min = f2_feasible_mean = f2_feasible_min = 0.0
            
            # Estatísticas dos inviáveis
            if n_infeasible > 0:
                infeasible_mask = G[:, 1] > 0
                F_infeasible = F[infeasible_mask]
                G_infeasible = G[infeasible_mask]
                f1_infeasible_mean = np.mean(F_infeasible[:, 0])
                f1_infeasible_min = np.min(F_infeasible[:, 0])
                f2_infeasible_mean = np.mean(F_infeasible[:, 1])
                g2_infeasible_mean = np.mean(G_infeasible[:, 1])
                g2_infeasible_min = np.min(G_infeasible[:, 1])
                g2_infeasible_max = np.max(G_infeasible[:, 1])
            else:
                f1_infeasible_mean = f1_infeasible_min = f2_infeasible_mean = 0.0
                g2_infeasible_mean = g2_infeasible_min = g2_infeasible_max = 0.0
            
            print(f"Gen {self._current_gen:3d} | Pop: {len(self.pop):3d} | Viáveis: {n_feasible:3d} ({pct_feasible:5.1f}%) | Inviáveis: {n_infeasible:3d}")
            if n_feasible > 0:
                print(f"  └─ Viáveis: f1 médio={f1_feasible_mean:.1f}, min={f1_feasible_min:.1f} | "
                      f"f2 médio={f2_feasible_mean:.3f}, min={f2_feasible_min:.3f}")
            if n_infeasible > 0:
                print(f"  └─ Inviáveis: f1 médio={f1_infeasible_mean:.1f}, min={f1_infeasible_min:.1f} | "
                      f"f2 médio={f2_infeasible_mean:.3f} | G2 médio={g2_infeasible_mean:.2f}, "
                      f"min={g2_infeasible_min:.2f}, max={g2_infeasible_max:.2f}")
        
        # Usa método padrão do NSGA-II mas com sobrevivência customizada
        # O mating customizado já foi configurado no __init__ para usar seleção direcionada
        # Então podemos usar o método padrão do NSGA2, mas substituir apenas a sobrevivência
        
        # VALIDAÇÃO 2: Antes de chamar mating, valida pop novamente
        # (pode ter sido modificada por operações anteriores)
        self.pop = self._validate_and_fix_pop_X(self.pop, self.problem, log_prefix=f"[GEN {self._current_gen}] Pre-mating: ")
        
        # Gera filhos usando o mating customizado (já configurado)
        off = self.mating.do(self.problem, self.pop, self.n_offsprings, algorithm=self, random_state=self.random_state)
        
        # VALIDAÇÃO 3: Após criar offspring, valida X dos filhos
        off = self._validate_and_fix_pop_X(off, self.problem, log_prefix=f"[GEN {self._current_gen}] Post-mating: ")
        
        # ===== REPARO PROBABILÍSTICO (LAMARCKIANO) =====
        # 50% dos filhos são avaliados com force_battery_feasible=True (tentativa de gerar novos viáveis)
        # 50% dos filhos são avaliados com force_battery_feasible=False (exploração de novos limites inviáveis)
        if len(off) > 0:
            n_offspring = len(off)
            n_repair = n_offspring // 2  # 50% para reparo
            
            # Embaralha índices para seleção aleatória (usa random_state do algoritmo)
            # self.random_state é um Generator, não RandomState
            repair_indices = self.random_state.choice(n_offspring, size=n_repair, replace=False)
            repair_mask = np.zeros(n_offspring, dtype=bool)
            repair_mask[repair_indices] = True
            
            # Salva estado original do problema
            original_force_feasible = self.problem.force_battery_feasible
            
            # Avalia 50% com force_battery_feasible=True (REPARO)
            if np.any(repair_mask):
                off_repair = off[repair_mask]
                self.problem.force_battery_feasible = True
                try:
                    self.evaluator.eval(self.problem, off_repair, **kwargs)
                    # Log: verifica quantos ficaram viáveis após reparo
                    if off_repair.has("G"):
                        G_repair = off_repair.get("G")
                        n_feasible_after_repair = np.sum(G_repair[:, 1] <= 0)
                        print(f"  [REPARO] {len(off_repair)} filhos avaliados com force_battery_feasible=True → {n_feasible_after_repair} viáveis")
                    else:
                        print(f"  [REPARO] {len(off_repair)} filhos avaliados com force_battery_feasible=True")
                finally:
                    # Restaura estado original
                    self.problem.force_battery_feasible = original_force_feasible
            
            # Avalia 50% com force_battery_feasible=False (EXPLORAÇÃO)
            if np.any(~repair_mask):
                off_explore = off[~repair_mask]
                self.problem.force_battery_feasible = False
                try:
                    self.evaluator.eval(self.problem, off_explore, **kwargs)
                    print(f"  [EXPLORAÇÃO] {len(off_explore)} filhos avaliados com force_battery_feasible=False")
                finally:
                    # Restaura estado original
                    self.problem.force_battery_feasible = original_force_feasible
        
        # VALIDAÇÃO 4: Após avaliação, valida X novamente
        # (avaliação não deve modificar X, mas vamos garantir)
        off = self._validate_and_fix_pop_X(off, self.problem, log_prefix=f"[GEN {self._current_gen}] Post-eval: ")
        
        # Combina população atual com filhos
        pop = Population.merge(self.pop, off)
        
        # VALIDAÇÃO 5: Após merge, valida X
        pop = self._validate_and_fix_pop_X(pop, self.problem, log_prefix=f"[GEN {self._current_gen}] Post-merge: ")
        
        # Aplica sobrevivência customizada para manter tamanho
        selected_indices = self._infeasible_survival._do(pop, self.pop_size, algorithm=self)
        self.pop = pop[selected_indices]
        
        # VALIDAÇÃO 6: Após survival, valida X final
        self.pop = self._validate_and_fix_pop_X(self.pop, self.problem, log_prefix=f"[GEN {self._current_gen}] Post-survival: ")
        
        # Log: Estatísticas detalhadas da população após seleção
        if len(self.pop) > 0 and self.pop.has("G"):
            G = self.pop.get("G")
            F = self.pop.get("F")
            n_feasible = np.sum(G[:, 1] <= 0)
            n_infeasible = len(G) - n_feasible
            pct_feasible = (n_feasible / len(G)) * 100 if len(G) > 0 else 0.0
            
            # Estatísticas dos viáveis após seleção
            if n_feasible > 0:
                feasible_mask = G[:, 1] <= 0
                F_feasible = F[feasible_mask]
                f1_feasible_mean = np.mean(F_feasible[:, 0])
                f1_feasible_min = np.min(F_feasible[:, 0])
                f2_feasible_mean = np.mean(F_feasible[:, 1])
                f2_feasible_min = np.min(F_feasible[:, 1])
            else:
                f1_feasible_mean = f1_feasible_min = f2_feasible_mean = f2_feasible_min = 0.0
            
            # Estatísticas dos inviáveis após seleção
            if n_infeasible > 0:
                infeasible_mask = G[:, 1] > 0
                F_infeasible = F[infeasible_mask]
                G_infeasible = G[infeasible_mask]
                f1_infeasible_mean = np.mean(F_infeasible[:, 0])
                f1_infeasible_min = np.min(F_infeasible[:, 0])
                f2_infeasible_mean = np.mean(F_infeasible[:, 1])
                g2_infeasible_mean = np.mean(G_infeasible[:, 1])
                g2_infeasible_min = np.min(G_infeasible[:, 1])
                g2_infeasible_max = np.max(G_infeasible[:, 1])
            else:
                f1_infeasible_mean = f1_infeasible_min = f2_infeasible_mean = 0.0
                g2_infeasible_mean = g2_infeasible_min = g2_infeasible_max = 0.0
            
            print(f"      | Pop: {len(self.pop):3d} | Viáveis: {n_feasible:3d} ({pct_feasible:5.1f}%) | Inviáveis: {n_infeasible:3d} [Após Seleção]")
            if n_feasible > 0:
                print(f"        └─ Viáveis: f1 médio={f1_feasible_mean:.1f}, min={f1_feasible_min:.1f} | "
                      f"f2 médio={f2_feasible_mean:.3f}, min={f2_feasible_min:.3f}")
            if n_infeasible > 0:
                print(f"        └─ Inviáveis: f1 médio={f1_infeasible_mean:.1f}, min={f1_infeasible_min:.1f} | "
                      f"f2 médio={f2_infeasible_mean:.3f} | G2 médio={g2_infeasible_mean:.2f}, "
                      f"min={g2_infeasible_min:.2f}, max={g2_infeasible_max:.2f}")
        
        # CRÍTICO: Atualiza opt (soluções não-dominadas) para evitar erro no display
        # O NSGA2 padrão faz isso automaticamente, mas como sobrescrevemos _advance, precisamos fazer manualmente
        # NonDominatedSorting já está importado no início do arquivo
        nds = NonDominatedSorting()
        
        # Encontra soluções não-dominadas na população atual
        # GARANTE que opt nunca fique vazio (isso causa erro no display)
        if len(self.pop) == 0:
            # Se pop está vazio, mantém opt anterior (se existir)
            if not hasattr(self, 'opt') or len(self.opt) == 0:
                self.opt = Population()
        else:
            F = self.pop.get("F")
            # Se há restrições, filtra apenas viáveis (G <= 0)
            if self.pop.has("G"):
                G = self.pop.get("G")
                # Constraint violation: soma de todas as violações (G > 0)
                cv = np.sum(np.maximum(G, 0), axis=1)
                # Filtra apenas soluções viáveis (cv == 0)
                feasible_mask = cv == 0
                if np.any(feasible_mask):
                    feasible_pop = self.pop[feasible_mask]
                    # GARANTE que feasible_pop não está vazio
                    if len(feasible_pop) > 0:
                        F_feasible = feasible_pop.get("F")
                        fronts = nds.do(F_feasible)
                        if len(fronts) > 0 and len(fronts[0]) > 0:
                            # Verifica se índices são válidos
                            valid_indices = [idx for idx in fronts[0] if 0 <= idx < len(feasible_pop)]
                            if len(valid_indices) > 0:
                                self.opt = feasible_pop[valid_indices]
                            else:
                                # Fallback: usa toda feasible_pop
                                self.opt = feasible_pop
                        else:
                            # Se não há frentes, usa toda feasible_pop
                            self.opt = feasible_pop
                    else:
                        # Se feasible_pop está vazio, usa toda população
                        fronts = nds.do(F)
                        if len(fronts) > 0 and len(fronts[0]) > 0:
                            self.opt = self.pop[fronts[0]]
                        else:
                            self.opt = self.pop
                else:
                    # Se não há soluções viáveis, usa todas as soluções (melhor que nada)
                    fronts = nds.do(F)
                    if len(fronts) > 0 and len(fronts[0]) > 0:
                        self.opt = self.pop[fronts[0]]
                    else:
                        # Se não há frentes, usa toda a população
                        self.opt = self.pop
            else:
                # Sem restrições, usa non-dominated sorting normal
                fronts = nds.do(F)
                if len(fronts) > 0 and len(fronts[0]) > 0:
                    self.opt = self.pop[fronts[0]]
                else:
                    self.opt = self.pop
            
            # VERIFICAÇÃO FINAL CRÍTICA: GARANTE que opt nunca fique vazio
            # Se opt está vazio após todas as atribuições, usa primeiro indivíduo da população
            if len(self.opt) == 0:
                # Usa primeiro indivíduo da população como fallback obrigatório
                if len(self.pop) > 0:
                    self.opt = Population.create(self.pop[0])
                else:
                    # Se pop também está vazio (não deveria acontecer), mantém opt anterior
                    if hasattr(self, 'opt') and len(self.opt) > 0:
                        # Mantém opt anterior
                        pass
                    else:
                        # Último recurso: cria população vazia (vai dar erro, mas é melhor que crashar)
                        self.opt = Population()
        
        # VERIFICAÇÃO FINAL ABSOLUTA: Se opt ainda está vazio, força criação
        # Isso nunca deveria acontecer, mas é uma última linha de defesa
        if not hasattr(self, 'opt') or len(self.opt) == 0:
            if len(self.pop) > 0:
                self.opt = Population.create(self.pop[0])
            else:
                self.opt = Population()
    
    def _post_advance(self, **kwargs):
        """
        Sobrescreve _post_advance para garantir que opt nunca fique vazio antes do display.
        O display do pymoo tenta acessar opt.get("cv").min() e falha se opt está vazio.
        
        CRÍTICO: A verificação deve ser FEITA ANTES de chamar super(), pois o display
        é chamado dentro de super()._post_advance().
        
        Além disso, verificamos se o algorithm passado para o callback é o mesmo objeto.
        """
        # Log para debug: verifica se opt está válido
        opt_size = len(self.opt) if hasattr(self, 'opt') else 0
        print(f"[POST_ADVANCE] Iniciando - Gen: {self._current_gen}, Pop: {len(self.pop)}, Opt: {opt_size}")
        
        # GARANTE que opt nunca fique vazio ANTES de chamar super()
        # O display é chamado dentro de super()._post_advance(), então precisamos
        # garantir que opt está preenchido ANTES disso
        if not hasattr(self, 'opt') or len(self.opt) == 0:
            print(f"[POST_ADVANCE] AVISO: Opt vazio ou não existe, criando fallback")
            if len(self.pop) > 0:
                self.opt = Population.create(self.pop[0])
                print(f"[POST_ADVANCE] Opt fallback criado - tamanho: {len(self.opt)}")
            else:
                self.opt = Population()
                print(f"[POST_ADVANCE] ERRO CRÍTICO: Pop também está vazia")
        
        # Salva ID do objeto self para verificar se callback recebe o mesmo
        self_id = id(self)
        opt_id_before = id(self.opt) if hasattr(self, 'opt') else None
        opt_size_before = len(self.opt) if hasattr(self, 'opt') else 0
        
        print(f"[POST_ADVANCE] Self ID: {self_id}, Opt ID: {opt_id_before}, Opt size: {opt_size_before}")
        
        # Chama método padrão
        try:
            super()._post_advance(**kwargs)
            print(f"[POST_ADVANCE] Concluído com sucesso")
        except ValueError as e:
            if "zero-size array" in str(e) and ("minimum" in str(e) or "cv" in str(e)):
                print(f"[POST_ADVANCE] ERRO CAPTURADO: {e}")
                print(f"  Opt após erro: ID={id(self.opt)}, tamanho={len(self.opt)}")
                print(f"  Self ID ainda é o mesmo? {id(self) == self_id}")
                
                # Verifica se opt foi modificado
                if len(self.opt) == 0:
                    print(f"[POST_ADVANCE] Opt ficou vazio! Recriando...")
                    if len(self.pop) > 0:
                        # Recria opt usando nossa lógica
                        nds = NonDominatedSorting()
                        F = self.pop.get("F")
                        
                        if self.pop.has("G"):
                            G = self.pop.get("G")
                            cv = np.sum(np.maximum(G, 0), axis=1)
                            feasible_mask = cv == 0
                            if np.any(feasible_mask):
                                feasible_pop = self.pop[feasible_mask]
                                if len(feasible_pop) > 0:
                                    F_feasible = feasible_pop.get("F")
                                    fronts = nds.do(F_feasible)
                                    if len(fronts) > 0 and len(fronts[0]) > 0:
                                        self.opt = feasible_pop[fronts[0][:min(5, len(fronts[0]))]]
                                    else:
                                        self.opt = feasible_pop[:min(5, len(feasible_pop))]
                                else:
                                    self.opt = Population.create(self.pop[0])
                            else:
                                self.opt = Population.create(self.pop[0])
                        else:
                            fronts = nds.do(F)
                            if len(fronts) > 0 and len(fronts[0]) > 0:
                                self.opt = self.pop[fronts[0][:min(5, len(fronts[0]))]]
                            else:
                                self.opt = Population.create(self.pop[0])
                        
                        print(f"[POST_ADVANCE] Opt recriado - tamanho: {len(self.opt)}")
                        # Tenta novamente
                        super()._post_advance(**kwargs)
                        print(f"[POST_ADVANCE] Concluído após correção")
                    else:
                        raise RuntimeError("Pop também está vazia")
            else:
                raise
