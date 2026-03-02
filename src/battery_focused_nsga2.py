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


def nsga2_survival(F_nds, n_survive, F_cd=None, random_state=None):
    """
    Seleção de sobrevivência seguindo o pipeline do NSGA-II (RankAndCrowding do pymoo).
    
    Pipeline:
    1. Non-dominated sorting em F_nds → frentes F1, F2, ...
    2. Acumular frentes em ordem até ultrapassar n_survive.
    3. Na frente que "estoura", ordenar por crowding distance (maior primeiro)
       calculada em F_cd e ficar com os primeiros k = n_survive − |já selecionados|.
    
    Permite usar espaços diferentes para NDS e para crowding:
    - A_F (viáveis): F_nds = (f1, f2), F_cd = (f1, f2)  → NSGA-II canônico.
    - A_I (inviáveis): F_nds = (f1, f2, G2), F_cd = (f1, f2)
      → ranking considera proximidade de factibilidade, diversidade medida em objetivos.
    
    Args:
        F_nds: array (n, m1) usado para non-dominated sorting.
        n_survive: número de sobreviventes desejado.
        F_cd: array (n, m2) usado para crowding distance. Se None, usa F_nds.
        random_state: se fornecido, desempate em crowding usa sorteio (como pymoo).
    
    Returns:
        Índices dos sobreviventes (0 a len(F_nds)-1), no máximo n_survive.
    """
    n = len(F_nds)
    if n == 0:
        return np.array([], dtype=int)
    if F_cd is None:
        F_cd = F_nds
    n_survive = min(n_survive, n)
    nds = NonDominatedSorting()
    fronts = nds.do(F_nds)
    survivors = []
    for k, front in enumerate(fronts):
        front = np.atleast_1d(front)
        n_add = len(front)
        if len(survivors) + n_add > n_survive:
            n_remove = len(survivors) + n_add - n_survive
            cd = calculate_crowding_distance(F_cd[front])
            if random_state is not None:
                order = _randomized_argsort_desc(cd, random_state)
            else:
                order = np.argsort(-cd)
            n_keep = n_add - n_remove
            I = order[:n_keep]
            survivors.extend(front[I].tolist())
        else:
            cd = calculate_crowding_distance(F_cd[front])
            if random_state is not None:
                order = _randomized_argsort_desc(cd, random_state)
            else:
                order = np.argsort(-cd)
            survivors.extend(front[order].tolist())
    return np.array(survivors, dtype=int)


def _randomized_argsort_desc(values, random_state):
    """Ordena por valores decrescentes; empates quebrados aleatoriamente (como pymoo)."""
    rng = np.random.default_rng(random_state)
    values = np.asarray(values)
    n = len(values)
    random_tie = rng.random(n)
    perm = np.lexsort((-random_tie, -values))
    return perm


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
    Estratégia de sobrevivência com Arquivo Inviável Delimitado (Bounded Infeasible Archive).
    
    - Viáveis (G2 <= 0): seleção por Rank & Crowding em (f1, f2).
    - Inviáveis: apenas "quase viáveis" (G2 <= epsilon_max = bateria * max_violation_ratio)
      são considerados; acima disso são descartados (lixo evolutivo).
    - Entre os inviáveis aceitáveis: seleção por Rank & Crowding em (f1, f2) puros
      (sem Shadow Cost), para diversidade e Hipervolume.
    - Fallback: se faltar gente, completa com rejeitados por menor G2.
    """
    
    def __init__(self, infeasible_ratio: float = 0.25, max_violation_ratio: float = 0.90):
        """
        Args:
            infeasible_ratio: Proporção da população que deve ser inviável (ex.: 25%).
            max_violation_ratio: Tolerância máxima de violação G2 (ex.: 15% da capacidade da bateria).
        """
        super().__init__()
        self.infeasible_ratio = infeasible_ratio
        self.max_violation_ratio = max_violation_ratio
    
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
        acceptable_infeasible_indices = np.array(infeasible_indices)
        rejected_infeasible_indices = np.array([], dtype=int)

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
        
        # ===== PASSO 2: Seleção de Inviáveis (Arquivo Delimitado: epsilon + Rank & Crowding em F) =====
        # Filtro epsilon: só inviáveis com G2 <= bateria * max_violation_ratio ("quase viáveis").
        rejected_infeasible_indices = np.array([], dtype=int)
        if len(infeasible_indices) > 0 and len(selected) < n_select:
            G_inf = pop.get("G")[infeasible_indices, 1]
            battery_capacity = None
            if 'algorithm' in kwargs and hasattr(kwargs['algorithm'], 'problem'):
                problem = kwargs['algorithm'].problem
                if hasattr(problem, 'context'):
                    battery_capacity = getattr(problem.context, 'battery_capacity', None)
            if battery_capacity is None or battery_capacity <= 0:
                battery_capacity = 100.0
            max_g2_allowed = battery_capacity * self.max_violation_ratio
            acceptable_mask = G_inf <= max_g2_allowed
            acceptable_infeasible_indices = np.array(infeasible_indices)[acceptable_mask]
            rejected_infeasible_indices = np.array(infeasible_indices)[~acceptable_mask]

            if len(acceptable_infeasible_indices) > 0:
                infeasible_pop = pop[acceptable_infeasible_indices]
                F_inf = infeasible_pop.get("F")

                nds_inf = NonDominatedSorting()
                fronts_inf = nds_inf.do(F_inf)

                n_remaining = n_select - len(selected)
                n_select_infeasible = min(n_infeasible_target, len(acceptable_infeasible_indices), n_remaining)
                selected_infeasible_local = []

                for front in fronts_inf:
                    front = np.atleast_1d(front)
                    if len(selected_infeasible_local) + len(front) <= n_select_infeasible:
                        selected_infeasible_local.extend(front.tolist())
                    else:
                        n_missing = n_select_infeasible - len(selected_infeasible_local)
                        F_front = F_inf[front]
                        cd_front = calculate_crowding_distance(F_front)
                        sorted_in_front = np.argsort(-cd_front)[:n_missing]
                        for i in sorted_in_front:
                            selected_infeasible_local.append(front[i])
                        break

                selected_infeasible_global = np.array(acceptable_infeasible_indices)[selected_infeasible_local]
                selected.extend(selected_infeasible_global.tolist())
                if len(rejected_infeasible_indices) > 0 or len(acceptable_infeasible_indices) != len(infeasible_indices):
                    print(f"  [INFEASIBLE_BOUNDED] Aceitos G2<={max_g2_allowed:.1f}: {len(acceptable_infeasible_indices)}, "
                          f"rejeitados: {len(rejected_infeasible_indices)}, selecionados: {len(selected_infeasible_global)}")
        
        # ===== PASSO 3: Completar com Viáveis Restantes (se necessário) =====
        if len(selected) < n_select:
            remaining_feasible = [i for i in feasible_indices if i not in selected]
            if len(remaining_feasible) > 0:
                remaining_pop = pop[remaining_feasible]
                f1_values = remaining_pop.get("F")[:, 0]
                remaining_sorted = np.array(remaining_feasible)[np.argsort(f1_values)]
                n_needed = n_select - len(selected)
                selected.extend(remaining_sorted[:n_needed].tolist())
        
        # ===== PASSO 4: Completar com Inviáveis Restantes (aceitáveis primeiro, depois rejeitados por G2) =====
        if len(selected) < n_select:
            remaining_acceptable = [i for i in acceptable_infeasible_indices if i not in selected]
            if len(rejected_infeasible_indices) > 0:
                g2_rej = pop.get("G")[rejected_infeasible_indices, 1]
                remaining_rejected_sorted = rejected_infeasible_indices[np.argsort(g2_rej)].tolist()
            else:
                remaining_rejected_sorted = []
            remaining_infeasible = remaining_acceptable + remaining_rejected_sorted
            if len(remaining_infeasible) > 0:
                n_needed = n_select - len(selected)
                selected.extend(remaining_infeasible[:n_needed])
        
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


# Base de rank para inviáveis: todo viável tem rank < RANK_INFEASIBLE_BASE, todo inviável >= base
RANK_INFEASIBLE_BASE = 10000


class BinaryTournamentWithInfeasible(Selection):
    """
    Torneio binário como no NSGA-II, com competidores podendo vir de A_F (viáveis) ou A_I (inviáveis).
    
    - pI(t): probabilidade de sortear um competidor da população inviável. Fase inicial pI maior (ex. 0.3–0.5), final menor (ex. 0.1–0.2).
    - Para cada torneio: sortear c1 e c2 com prob (1-pI) de A_F e prob pI de A_I.
    - Comparação: (1) ambos factíveis → (rank, crowding) como NSGA-II; (2) um factível e um inviável → factível ganha; (3) ambos inviáveis → dominância em (f1,f2,G2) e diversidade em (f1,f2).
    Requer que pop já tenha "rank" e "crowding" definidos (via _update_rank_and_crowding_for_mating).
    """
    
    def __init__(self, pI_start: float = 0.4, pI_end: float = 0.15):
        super().__init__()
        self.pI_start = pI_start
        self.pI_end = pI_end
    
    def _pI(self, algorithm) -> float:
        t = getattr(algorithm, "_current_gen", 1)
        T = max(1, getattr(algorithm, "n_gen", 100))
        progress = min(1.0, max(0.0, (t - 1) / max(1, T - 1)))
        return self.pI_start + (self.pI_end - self.pI_start) * progress
    
    def _do(self, pop, n_select, n_parents=2, **kwargs):
        n = len(pop)
        if n == 0:
            return np.array([], dtype=int).reshape(0, n_parents)
        if not pop.has("G") or not pop.has("F") or not pop.has("rank") or not pop.has("crowding"):
            return np.array([[np.random.randint(0, n), np.random.randint(0, n)] for _ in range(n_select)])
        
        G = pop.get("G")
        F = pop.get("F")
        rank = pop.get("rank")
        crowding = np.asarray(pop.get("crowding"), dtype=float)
        feasible_mask = G[:, 1] <= 0
        feasible_indices = np.where(feasible_mask)[0]
        infeasible_indices = np.where(~feasible_mask)[0]
        n_feasible = len(feasible_indices)
        n_infeasible = len(infeasible_indices)
        algorithm = kwargs.get("algorithm")
        pI = self._pI(algorithm) if algorithm is not None else 0.2
        
        def pick_competitor():
            if n_feasible == 0:
                return int(np.random.choice(infeasible_indices))
            if n_infeasible == 0:
                return int(np.random.choice(feasible_indices))
            if np.random.random() < pI:
                return int(np.random.choice(infeasible_indices))
            return int(np.random.choice(feasible_indices))
        
        def wins(c1: int, c2: int) -> int:
            f1, f2 = rank[c1] < RANK_INFEASIBLE_BASE, rank[c2] < RANK_INFEASIBLE_BASE
            if f1 and f2:
                if rank[c1] != rank[c2]:
                    return c1 if rank[c1] < rank[c2] else c2
                return c1 if crowding[c1] >= crowding[c2] else c2
            if f1 and not f2:
                return c1
            if not f1 and f2:
                return c2
            if rank[c1] != rank[c2]:
                return c1 if rank[c1] < rank[c2] else c2
            return c1 if crowding[c1] >= crowding[c2] else c2
        
        selected = []
        for _ in range(n_select * n_parents):
            c1, c2 = pick_competitor(), pick_competitor()
            while c2 == c1 and n > 1:
                c2 = pick_competitor()
            selected.append(wins(c1, c2))
        return np.array(selected, dtype=int).reshape(n_select, n_parents)


class DirectedMatingSelection(Selection):
    """
    [Legado] Mating por proporção viável×viável vs viável×inviável (proximidade).
    Mantido para referência; uso preferencial: BinaryTournamentWithInfeasible.
    """
    
    def __init__(self, feasible_mating_ratio: float = 0.7):
        super().__init__()
        self.feasible_mating_ratio = feasible_mating_ratio
    
    def _do(self, pop, n_select, n_parents=2, **kwargs):
        n = n_select
        if not pop.has("G") or not pop.has("F"):
            return np.array([[np.random.randint(0, len(pop)), np.random.randint(0, len(pop))] for _ in range(n)])
        
        G = pop.get("G")
        F = pop.get("F")
        feasible_mask = G[:, 1] <= 0
        feasible_indices = np.where(feasible_mask)[0]
        infeasible_indices = np.where(~feasible_mask)[0]
        n_feasible = len(feasible_indices)
        n_infeasible = len(infeasible_indices)
        
        selected = []
        for _ in range(n):
            use_feasible_feasible = (
                n_feasible >= 2
                and (n_infeasible == 0 or np.random.random() < self.feasible_mating_ratio)
            )
            if use_feasible_feasible:
                i, j = np.random.choice(n_feasible, size=2, replace=False)
                parent1_idx = int(feasible_indices[i])
                parent2_idx = int(feasible_indices[j])
            else:
                if n_feasible == 0:
                    i1 = np.random.randint(0, n_infeasible)
                    i2 = (i1 + 1 + np.random.randint(0, max(1, n_infeasible - 1))) % n_infeasible
                    parent1_idx = int(infeasible_indices[i1])
                    parent2_idx = int(infeasible_indices[i2])
                elif n_infeasible == 0:
                    i, j = np.random.choice(n_feasible, size=2, replace=False)
                    parent1_idx = int(feasible_indices[i])
                    parent2_idx = int(feasible_indices[j])
                else:
                    parent1_from_F = np.random.random() < 0.5
                    if parent1_from_F:
                        parent1_idx = int(np.random.choice(feasible_indices))
                        other_indices = infeasible_indices
                    else:
                        parent1_idx = int(np.random.choice(infeasible_indices))
                        other_indices = feasible_indices
                    F_other = F[other_indices]
                    f1 = F[parent1_idx]
                    r = F_other.max(axis=0) - F_other.min(axis=0)
                    r = np.where(r > 1e-12, r, 1.0)
                    F_norm = (F_other - F_other.min(axis=0)) / r
                    f1_norm = (f1 - F_other.min(axis=0)) / r
                    dist = np.sqrt(np.sum((F_norm - f1_norm) ** 2, axis=1))
                    j = int(np.argmin(dist))
                    parent2_idx = int(other_indices[j])
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
        feasible_mating_ratio=0.7,
        pI_start=0.4,
        pI_end=0.15,
        all_conservative_init=False,
        test_all_feasible=False,
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
            feasible_mating_ratio: [Legado] Ignorado quando usa torneio binário (pI); mantido por compatibilidade
            pI_start: Prob. de sortear competidor inviável no início (ex.: 0.3–0.5)
            pI_end: Prob. de sortear competidor inviável no fim (ex.: 0.1–0.2)
            all_conservative_init: Se True, usa NSGA-II puro (mating/survival padrão) — teste baseline.
            test_all_feasible: Se True, usa o pipeline de dois arquivos mas com 100% viável: init e offspring
                sempre com decoder conservador, N_I=0. Serve para verificar integridade (resultados = NSGA-II).
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
        self.all_conservative_init = all_conservative_init
        self.test_all_feasible = test_all_feasible
        self._hybrid_sampling = None
        # Tamanhos dos dois arquivos (Seção 4 - REFENCIA_TEORICA): A_F (Convergence), A_I (Diversity)
        # test_all_feasible: N_I=0 para que survival = NSGA-II (só A_F, tamanho pop_size)
        if test_all_feasible:
            self._n_F = int(pop_size)
            self._n_I = 0
        else:
            self._n_F = int(pop_size * (1 - infeasible_ratio))  # N_F
            self._n_I = int(pop_size * infeasible_ratio)          # N_I (α·N_F, α ∈ [0.1, 0.3])
        self._use_two_archives = True   # Se True, usa dinâmica dos dois arquivos (Seção 4)
        self._epsilon_F = 0.0           # CV <= epsilon_F → factível (usamos G2 <= 0)
        self._cv_max_ratio = 0.8        # CV_max = cv_max_ratio * Q_bat; descarta inviáveis com G2 > CV_max (§5.1)
        # Sem limite de G2 na seleção de inviáveis (max_violation_ratio=inf aceita todos)
        self._infeasible_survival = InfeasibleSurvival(infeasible_ratio, max_violation_ratio=math.inf)
        self._directed_mating = None
        # Modo baseline (all_conservative_init): mantém mating e survival do NSGA-II para teste de integridade.
        # Caso contrário: torneio binário com competidores de A_F e A_I (pI(t)).
        if not self.all_conservative_init:
            self._directed_mating = BinaryTournamentWithInfeasible(pI_start=pI_start, pI_end=pI_end)
        # Armazena operadores explicitamente para uso em _advance
        self._crossover_op = crossover
        self._mutation_op = mutation
        # Rastreia número de geração para logs
        self._current_gen = 0
        
        # Substitui o mating apenas quando NÃO em modo baseline (para igualar NSGA-II padrão no teste)
        if not self.all_conservative_init:
            from pymoo.core.mating import Mating
            
            class CustomMating(Mating):
                def __init__(self, crossover, mutation, directed_mating):
                    super().__init__(selection=None, crossover=crossover, mutation=mutation)
                    self._directed_mating = directed_mating
                
                def _do(self, problem, pop, n_offsprings, **kwargs):
                    pop = BatteryFocusedNSGA2._validate_and_fix_pop_X(pop, problem, log_prefix="[CUSTOM_MATING] Pre-op: ")
                    n_matings = math.ceil(n_offsprings / self.crossover.n_offsprings)
                    parents_array = self._directed_mating._do(pop, n_matings, n_parents=2, **kwargs)
                    if pop.has("G"):
                        G = pop.get("G")
                        g2 = G[:, 1]
                        is_ff_mating = (g2[parents_array[:, 0]] <= 0) & (g2[parents_array[:, 1]] <= 0)
                    else:
                        is_ff_mating = np.zeros(n_matings, dtype=bool)
                    parents = parents_array.tolist()
                    pop = BatteryFocusedNSGA2._validate_and_fix_pop_X(pop, problem, log_prefix="[CUSTOM_MATING] Pre-crossover: ")
                    try:
                        _off = self.crossover.do(problem, pop, parents, **kwargs)
                    except (ValueError, AttributeError, TypeError) as e:
                        print(f"[CUSTOM_MATING] Crossover falhou: {e}. Tentando corrigir Population...")
                        pop = BatteryFocusedNSGA2._validate_and_fix_pop_X(pop, problem, log_prefix="[CUSTOM_MATING] Retry-crossover: ")
                        _off = self.crossover.do(problem, pop, parents, **kwargs)
                    _off = BatteryFocusedNSGA2._validate_and_fix_pop_X(_off, problem, log_prefix="[CUSTOM_MATING] Post-crossover: ")
                    off = self.mutation.do(problem, _off, **kwargs)
                    off = BatteryFocusedNSGA2._validate_and_fix_pop_X(off, problem, log_prefix="[CUSTOM_MATING] Post-mutation: ")
                    n_off = len(off)
                    n_off_per_mating = getattr(self.crossover, "n_offsprings", 1)
                    is_ff_offspring = np.repeat(is_ff_mating, n_off_per_mating)[:n_off]
                    algorithm = kwargs.get("algorithm")
                    if algorithm is not None:
                        algorithm._last_offspring_ff_mask = is_ff_offspring
                    return off
            
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
        
        # ===== Modo baseline (teste integridade): 100% conservador, sem split =====
        if getattr(self, "all_conservative_init", False):
            pop_all = Population.new("X", X)
            pop_all = self._validate_and_fix_pop_X(pop_all, problem, log_prefix="[INIT] Baseline: ")
            original_flag = getattr(problem, "force_battery_feasible", None)
            if hasattr(problem, "force_battery_feasible"):
                problem.force_battery_feasible = True
            try:
                out = problem.evaluate(X, return_as_dictionary=True, **kwargs)
                pop_all.set("F", out["F"])
                if "G" in out:
                    pop_all.set("G", out["G"])
            finally:
                if original_flag is not None:
                    problem.force_battery_feasible = original_flag
            self.pop = self._validate_and_fix_pop_X(pop_all, problem, log_prefix="[INIT] Baseline pós-eval: ")
            if self.pop.has("G"):
                n_f = np.sum(self.pop.get("G")[:, 1] <= 0)
                print(f"[INIT] Baseline (100% conservador): {n_f}/{len(self.pop)} viáveis (G2<=0)")
            self._update_opt_after_initialization()
            # Rank e crowding na pop inicial para o tournament selection do NSGA-II padrão
            F = self.pop.get("F")
            nds = NonDominatedSorting()
            fronts = nds.do(F)
            n = len(self.pop)
            rank = np.zeros(n, dtype=int)
            for r, front in enumerate(fronts):
                front = np.atleast_1d(front)
                rank[front] = r
            crowding = np.zeros(n)
            for front in fronts:
                front = np.atleast_1d(front)
                if len(front) > 2:
                    cd = calculate_crowding_distance(F[front])
                    for i, idx in enumerate(front):
                        crowding[idx] = cd[i]
                else:
                    crowding[front] = np.inf
            self.pop.set("rank", rank)
            self.pop.set("crowding", crowding)
            if len(self.pop) > 0 and self.pop.has("G"):
                G = self.pop.get("G")
                n_f = np.sum(G[:, 1] <= 0)
                n_inv = len(self.pop) - n_f
                print(f"Gen {self._current_gen:3d} | Pop: {len(self.pop):3d} | Viáveis: {n_f:3d} | Inviáveis: {n_inv:3d} [Inicial Baseline]")
            return
        
        # ===== test_all_feasible: pipeline dois arquivos com 100% viável (init 100% conservador) =====
        if getattr(self, "test_all_feasible", False):
            n_feasible = self.pop_size  # todos no lote "viável"
            X_feasible = X.copy()
            X_infeasible = np.zeros((0, X.shape[1]), dtype=X.dtype)
            pop_feasible = Population.new("X", X_feasible)
            pop_feasible = self._validate_and_fix_pop_X(pop_feasible, problem, log_prefix="[INIT] TestAllFeasible: ")
            original_flag = getattr(problem, "force_battery_feasible", None)
            if hasattr(problem, "force_battery_feasible"):
                problem.force_battery_feasible = True
            try:
                out = problem.evaluate(X_feasible, return_as_dictionary=True, **kwargs)
                pop_feasible.set("F", out["F"])
                if "G" in out:
                    pop_feasible.set("G", out["G"])
            finally:
                if original_flag is not None:
                    problem.force_battery_feasible = original_flag
            if len(X_infeasible) == 0:
                self.pop = pop_feasible
            else:
                pop_infeasible = Population.new("X", X_infeasible)
                self.pop = Population.merge(pop_feasible, pop_infeasible)
            self.pop = self._validate_and_fix_pop_X(self.pop, problem, log_prefix="[INIT] TestAllFeasible pós-eval: ")
            n_f = np.sum(self.pop.get("G")[:, 1] <= 0) if self.pop.has("G") else len(self.pop)
            print(f"[INIT] TestAllFeasible: 100% conservador, {n_f}/{len(self.pop)} viáveis (G2<=0); pipeline dois arquivos com N_I=0")
            self._update_opt_after_initialization()
            return
        
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
    
    def _update_two_archives(self, pop):
        """
        Atualiza os dois arquivos conforme Seção 4 (REFENCIA_TEORICA.md).
        
        - A_F (Convergence Archive): todos os viáveis do merge (pop atual + offspring).
          Processo idêntico ao NSGA-II: NDS em (f1, f2), ranking por frentes F1, F2, ...,
          crowding distance dentro de cada frente; acumular frentes até ultrapassar N_F;
          na última frente parcial ordenar por crowding e pegar os primeiros até completar N_F.
          Ver nsga2_survival().
        - A_I (Diversity Archive): todos os inviáveis do merge (pool único, sem pré-filtro).
          NDS em (f1, f2, G2), crowding em (f1, f2), acumular frentes até N_I.
          Ver nsga2_survival().
        Garante população total = pop_size (N_F + N_I); se há menos viáveis que N_F,
        completa com inviáveis até pop_size.
        
        Args:
            pop: Population (merge de população atual + offspring), com F e G.
        Returns:
            Population de tamanho pop_size = A_F ∪ A_I.
        """
        n_select = self.pop_size
        N_F = self._n_F
        N_I = self._n_I
        epsilon_F = self._epsilon_F
        
        if not pop.has("F") or not pop.has("G"):
            return pop
        F = pop.get("F")
        G = pop.get("G")
        # CV para factibilidade: G2 (violação de bateria)
        cv = G[:, 1]
        feasible_mask = cv <= epsilon_F
        feasible_indices = np.where(feasible_mask)[0]
        infeasible_indices = np.where(~feasible_mask)[0]
        
        selected_indices = []
        
        # ----- A_F: Arquivo factível (Convergence Archive) -----
        # Pipeline idêntico ao NSGA-II: NDS em (f1,f2), ranking por frente, crowding por frente,
        # acumular frentes até ultrapassar N_F; na frente parcial ordenar por crowding e pegar os primeiros.
        if len(feasible_indices) > 0:
            feasible_pop = pop[feasible_indices]
            F_f = feasible_pop.get("F")
            survivor_local = nsga2_survival(
                F_f, N_F, random_state=getattr(self, "random_state", None)
            )
            selected_f = [feasible_indices[i] for i in survivor_local]
            selected_indices.extend(selected_f)
        
        # ----- A_I: Arquivo inviável (Diversity Archive) -----
        # NSGAzinho: pool único com TODOS os inviáveis do merge; sem pré-filtro de qualidade.
        # NDS em (f1, f2, G2): ranking considera proximidade de factibilidade.
        # Crowding em (f1, f2): diversidade medida no espaço de objetivos reais.
        # Acumular frentes até N_I; na frente parcial, ordenar por crowding e completar.
        n_remaining = n_select - len(selected_indices)
        if len(infeasible_indices) > 0 and n_remaining > 0:
            F_inf = F[infeasible_indices]
            G2_inf = G[infeasible_indices, 1]
            F_nds_inf = np.column_stack([F_inf[:, 0], F_inf[:, 1], G2_inf])
            F_cd_inf = F_inf  # crowding em (f1, f2)
            survivor_local_inf = nsga2_survival(
                F_nds_inf, n_remaining, F_cd=F_cd_inf,
                random_state=getattr(self, "random_state", None)
            )
            selected_i = [infeasible_indices[i] for i in survivor_local_inf]
            selected_indices.extend(selected_i)
        
        # Garantir exatamente n_select (completar com restantes ou duplicatas se necessário)
        if len(selected_indices) < n_select:
            all_indices = list(range(len(pop)))
            remaining = [i for i in all_indices if i not in selected_indices]
            n_needed = n_select - len(selected_indices)
            if len(remaining) >= n_needed:
                selected_indices.extend(
                    np.random.choice(remaining, size=n_needed, replace=False).tolist()
                )
            else:
                selected_indices.extend(remaining)
                # Se ainda faltam (ex.: só 75 viáveis, 0 inviáveis), completa ciclando nos já escolhidos
                n_prev = len(selected_indices)
                for i in range(n_select - n_prev):
                    selected_indices.append(selected_indices[i % n_prev])
        if len(selected_indices) > n_select:
            selected_indices = selected_indices[:n_select]
        
        return pop[selected_indices]
    
    def _update_rank_and_crowding_for_mating(self):
        """
        Atualiza rank e crowding em self.pop para uso no torneio binário.
        - Viáveis (A_F): NDS em F, rank 0,1,2,..., crowding por frente em F.
        - Inviáveis (A_I): NDS em (f1, f2, G2), rank = RANK_INFEASIBLE_BASE + frente;
          diversidade = crowding em (f1, f2) por frente.
        Assim, no torneio: factível sempre ganha de inviável; entre factíveis (rank, crowding);
        entre inviáveis (rank, crowding) em (f1,f2,G2) e (f1,f2).
        """
        pop = self.pop
        n = len(pop)
        if n == 0 or not pop.has("F") or not pop.has("G"):
            return
        F = pop.get("F")
        G = pop.get("G")
        feasible_mask = G[:, 1] <= 0
        feasible_indices = np.where(feasible_mask)[0]
        infeasible_indices = np.where(~feasible_mask)[0]
        rank_all = np.full(n, RANK_INFEASIBLE_BASE + 9999, dtype=float)
        crowding_all = np.zeros(n, dtype=float)
        nds = NonDominatedSorting()
        
        if len(feasible_indices) > 0:
            F_f = F[feasible_indices]
            fronts_f = nds.do(F_f)
            for r, front in enumerate(fronts_f):
                front = np.atleast_1d(front)
                for idx in front:
                    rank_all[feasible_indices[idx]] = float(r)
                if len(front) > 0:
                    cd = calculate_crowding_distance(F_f[front])
                    for i, idx in enumerate(front):
                        crowding_all[feasible_indices[idx]] = cd[i]
        
        if len(infeasible_indices) > 0:
            F_inf = F[infeasible_indices]
            G2_inf = G[infeasible_indices, 1]
            F3 = np.column_stack([F_inf[:, 0], F_inf[:, 1], G2_inf])
            fronts_i = nds.do(F3)
            for r, front in enumerate(fronts_i):
                front = np.atleast_1d(front)
                for idx in front:
                    rank_all[infeasible_indices[idx]] = float(RANK_INFEASIBLE_BASE + r)
                if len(front) > 0:
                    cd = calculate_crowding_distance(F_inf[front])
                    for i, idx in enumerate(front):
                        crowding_all[infeasible_indices[idx]] = cd[i]
        
        pop.set("rank", rank_all)
        pop.set("crowding", crowding_all)
    
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
        
        # Rank e crowding para torneio binário (A_F e A_I); só quando usamos seleção com inviáveis
        if not getattr(self, "all_conservative_init", False):
            self._update_rank_and_crowding_for_mating()
        
        # Gera filhos usando o mating customizado (já configurado)
        off = self.mating.do(self.problem, self.pop, self.n_offsprings, algorithm=self, random_state=self.random_state)
        
        # VALIDAÇÃO 3: Após criar offspring, valida X dos filhos
        off = self._validate_and_fix_pop_X(off, self.problem, log_prefix=f"[GEN {self._current_gen}] Post-mating: ")
        
        # ===== PIPELINE: F×F → decoder conservador; resto → agressivo. Pool viável/inviável por G2 =====
        # Modo baseline: toda offspring com decoder conservador (igual NSGA-II)
        if getattr(self, "all_conservative_init", False) and len(off) > 0:
            original_force = self.problem.force_battery_feasible
            self.problem.force_battery_feasible = True
            try:
                self.evaluator.eval(self.problem, off, **kwargs)
            finally:
                self.problem.force_battery_feasible = original_force
            if len(off) > 0:
                print(f"  [DECODER] Baseline: toda offspring em modo conservador")
        # test_all_feasible: mesmo pipeline dois arquivos, mas toda offspring com conservador (100% viável)
        elif getattr(self, "test_all_feasible", False) and len(off) > 0:
            original_force = self.problem.force_battery_feasible
            self.problem.force_battery_feasible = True
            try:
                self.evaluator.eval(self.problem, off, **kwargs)
            finally:
                self.problem.force_battery_feasible = original_force
            if len(off) > 0:
                print(f"  [DECODER] TestAllFeasible: toda offspring em modo conservador")
        elif len(off) > 0:
            mask_ff = getattr(self, "_last_offspring_ff_mask", None)
            n_off = len(off)
            if mask_ff is not None and len(mask_ff) == n_off:
                n_ff = int(np.sum(mask_ff))
                n_mixed = n_off - n_ff
                original_force = self.problem.force_battery_feasible
                if n_ff > 0 and n_mixed > 0:
                    off_ff = off[mask_ff]
                    off_mixed = off[~mask_ff]
                    self.problem.force_battery_feasible = True
                    try:
                        self.evaluator.eval(self.problem, off_ff, **kwargs)
                    finally:
                        self.problem.force_battery_feasible = original_force
                    self.problem.force_battery_feasible = False
                    try:
                        self.evaluator.eval(self.problem, off_mixed, **kwargs)
                    finally:
                        self.problem.force_battery_feasible = original_force
                    n_obj = off_ff.get("F").shape[1]
                    n_g = off_ff.get("G").shape[1]
                    F_all = np.zeros((n_off, n_obj))
                    G_all = np.zeros((n_off, n_g))
                    F_all[mask_ff] = off_ff.get("F")
                    F_all[~mask_ff] = off_mixed.get("F")
                    G_all[mask_ff] = off_ff.get("G")
                    G_all[~mask_ff] = off_mixed.get("G")
                    off.set("F", F_all)
                    off.set("G", G_all)
                elif n_ff > 0:
                    self.problem.force_battery_feasible = True
                    try:
                        self.evaluator.eval(self.problem, off, **kwargs)
                    finally:
                        self.problem.force_battery_feasible = original_force
                else:
                    self.problem.force_battery_feasible = False
                    try:
                        self.evaluator.eval(self.problem, off, **kwargs)
                    finally:
                        self.problem.force_battery_feasible = original_force
                # Log: entre os filhos F×I/I×F (decoder agressivo), quantos ficaram viáveis e mínimos de f1/f2
                if n_mixed > 0 and off.has("G"):
                    mixed_mask = ~mask_ff
                    G_off = off.get("G")
                    F_off = off.get("F")
                    feasible_from_mixed = mixed_mask & (G_off[:, 1] <= 0)
                    n_feas_mixed = int(np.sum(feasible_from_mixed))
                    if n_feas_mixed > 0:
                        f1_min_mixed = np.min(F_off[feasible_from_mixed, 0])
                        f2_min_mixed = np.min(F_off[feasible_from_mixed, 1])
                        print(f"  [F×I/I×F viáveis] n={n_feas_mixed}/{n_mixed} | f1_min={f1_min_mixed:.1f} | f2_min={f2_min_mixed:.4f}")
                    else:
                        print(f"  [F×I/I×F viáveis] n=0/{n_mixed} (nenhum filho agressivo viável)")
                print(f"  [DECODER] F×F (conservador): {n_ff} | F×I/I×F (agressivo): {n_mixed}")
            else:
                original_force = self.problem.force_battery_feasible
                self.problem.force_battery_feasible = False
                try:
                    self.evaluator.eval(self.problem, off, **kwargs)
                finally:
                    self.problem.force_battery_feasible = original_force
                # Toda offspring é F×I/I×F (agressivo); log viáveis e mínimos f1/f2
                if off.has("G"):
                    G_off = off.get("G")
                    F_off = off.get("F")
                    feasible = (G_off[:, 1] <= 0)
                    n_feas = int(np.sum(feasible))
                    n_off = len(off)
                    if n_feas > 0:
                        f1_min_mixed = np.min(F_off[feasible, 0])
                        f2_min_mixed = np.min(F_off[feasible, 1])
                        print(f"  [F×I/I×F viáveis] n={n_feas}/{n_off} | f1_min={f1_min_mixed:.1f} | f2_min={f2_min_mixed:.4f}")
                    else:
                        print(f"  [F×I/I×F viáveis] n=0/{n_off} (nenhum filho agressivo viável)")
                print(f"  [DECODER] Offspring toda em modo agressivo (sem máscara F×F)")

        # VALIDAÇÃO 4: Após avaliação, valida X novamente
        # (avaliação não deve modificar X, mas vamos garantir)
        off = self._validate_and_fix_pop_X(off, self.problem, log_prefix=f"[GEN {self._current_gen}] Post-eval: ")
        
        # Combina população atual com filhos
        pop = Population.merge(self.pop, off)
        
        # VALIDAÇÃO 5: Após merge, valida X
        pop = self._validate_and_fix_pop_X(pop, self.problem, log_prefix=f"[GEN {self._current_gen}] Post-merge: ")
        
        # Log: tamanho dos pools viável/inviável após toda a offspring passar pelo decoder, antes da seleção
        if len(pop) > 0 and pop.has("G"):
            G_merged = pop.get("G")
            n_viable = int(np.sum(G_merged[:, 1] <= 0))
            n_inv = len(pop) - n_viable
            print(f"  [POOL] viáveis: {n_viable} | inviáveis: {n_inv} (antes da seleção)")
        
        # Filtro CV_max (§5.1): descarta inviáveis com G2 > cv_max_ratio * Q_bat
        if getattr(self, '_cv_max_ratio', None) is not None and pop.has("G") and hasattr(self.problem, 'context'):
            battery_capacity = getattr(self.problem.context, 'battery_capacity', None) or 100.0
            cv_max = battery_capacity * self._cv_max_ratio
            G = pop.get("G")
            keep = G[:, 1] <= cv_max
            if not np.all(keep):
                n_discarded = np.sum(~keep)
                pop = pop[keep]
                if n_discarded > 0:
                    print(f"  [CV_MAX] Descartados {n_discarded} indivíduos com G2 > {cv_max:.1f} ({self._cv_max_ratio*100:.0f}% Q_bat)")
        
        # Atualização da população: baseline usa survival do NSGA-II; senão dois arquivos ou cotas
        if getattr(self, "all_conservative_init", False):
            # Igual NSGA-II: RankAndCrowdingSurvival (rank, depois crowding)
            self.pop = self.survival.do(self.problem, pop, n_survive=self.pop_size, **kwargs)
            if len(self.pop) > 0 and self.pop.has("G"):
                n_f = np.sum(self.pop.get("G")[:, 1] <= 0)
                print(f"  [BASELINE] Survival NSGA-II: {n_f} viáveis")
        elif getattr(self, '_use_two_archives', False):
            # A_F (Convergence) + A_I (Diversity): NDS+crowding por arquivo, tamanhos N_F e N_I
            self.pop = self._update_two_archives(pop)
            if len(self.pop) > 0 and self.pop.has("G"):
                n_f = np.sum(self.pop.get("G")[:, 1] <= self._epsilon_F)
                print(f"  [DOIS ARQUIVOS] A_F (Convergence): {n_f}, A_I (Diversity): {len(self.pop) - n_f}")
        else:
            selected_indices = self._infeasible_survival._do(pop, self.pop_size, algorithm=self)
            self.pop = pop[selected_indices]
        
        # VALIDAÇÃO 6: Após survival/archives, valida X final
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
