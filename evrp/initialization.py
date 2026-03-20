"""
Inicializacao em tres camadas para o IAS-EVRP.

Camada V: solucoes viaveis (insercao com seguranca energetica)
Camada E: solucoes IES (pula estacao com probabilidade p_skip, clamp apos deficit)
Camada R: solucoes aleatorias (sem verificacao de restricoes)

ORE fallback: converte viaveis em IES removendo estacao aleatoria.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass
from typing import List, Optional

from .evaluator import (
    PopulationStats, classify_type, renormalize, run_ci, update_pop_stats,
)
from .instance import EVRPInstance
from .representation import (
    InfeasType, NodeType, Route, Solution, Visit,
)


# ---------------------------------------------------------------------------
# Resultado da inicializacao
# ---------------------------------------------------------------------------

@dataclass
class InitResult:
    population: List[Solution]
    n_V: int
    n_IES: int
    n_IEC: int
    n_IC: int
    n_IJT: int
    n_IM: int
    eta: float          # proporcao total de inviaveis
    eta_E: float        # n_IES / N_P
    eta_C: float        # n_IC / N_P
    eta_T: float        # n_IJT / N_P
    pop_stats: PopulationStats


# ---------------------------------------------------------------------------
# Funcoes auxiliares
# ---------------------------------------------------------------------------

def _best_station(from_id: int, to_id: int, curr_energy: float,
                  inst: EVRPInstance) -> Optional[int]:
    """Estacao de menor desvio de rota alcancavel com curr_energy."""
    best_s, best_delta = None, float('inf')
    for s_id in inst.station_ids:
        if inst.energy[from_id][s_id] <= curr_energy + 1e-9:
            delta = (inst.dist[from_id][s_id]
                     + inst.dist[s_id][to_id]
                     - inst.dist[from_id][to_id])
            if delta < best_delta:
                best_delta = delta
                best_s = s_id
    return best_s


def _new_route(depot_id: int) -> Route:
    return Route(visits=[Visit(node_id=depot_id, node_type=NodeType.DEPOT)])


def _close_route(route: Route, depot_id: int) -> Route:
    route.visits.append(Visit(node_id=depot_id, node_type=NodeType.DEPOT))
    return route


# ---------------------------------------------------------------------------
# Camada V: solucoes viaveis
# ---------------------------------------------------------------------------

def _generate_feasible(inst: EVRPInstance, beta_s: float) -> Solution:
    """
    Insercao sequencial com verificacao de capacidade, energia e janela de tempo.
    Ordena clientes por ready_time (com perturbacao para diversidade).
    Abre nova rota quando o proximo cliente nao cabe.
    """
    customers = inst.customer_ids[:]
    customers.sort(key=lambda c: inst.nodes[c].ready_time + random.uniform(0, 30))

    routes: List[Route] = []
    curr_route = _new_route(inst.depot_id)
    curr_energy = inst.B
    curr_time = 0.0
    curr_demand = 0.0
    last_node = inst.depot_id

    i = 0
    while i < len(customers):
        c = customers[i]
        node_c = inst.nodes[c]
        inserted = False

        # Capacidade
        if curr_demand + node_c.demand > inst.Q + 1e-9:
            routes.append(_close_route(curr_route, inst.depot_id))
            curr_route = _new_route(inst.depot_id)
            curr_energy = inst.B
            curr_time = 0.0
            curr_demand = 0.0
            last_node = inst.depot_id
            continue

        e_to_c = inst.energy[last_node][c]
        e_to_depot = inst.energy[c][inst.depot_id]
        needs_station = curr_energy - e_to_c - e_to_depot < beta_s * inst.B

        # Calcula tempo de chegada (com possivel detour por estacao)
        if needs_station:
            s_id = _best_station(last_node, c, curr_energy, inst)
            if s_id is not None:
                energy_at_s = curr_energy - inst.energy[last_node][s_id]
                recharge_t = (inst.B - max(0.0, energy_at_s)) * inst.g
                arr_time = (curr_time
                            + inst.travel_time[last_node][s_id]
                            + recharge_t
                            + inst.travel_time[s_id][c])
            else:
                arr_time = float('inf')
        else:
            s_id = None
            arr_time = curr_time + inst.travel_time[last_node][c]

        # Verifica janela de tempo
        if arr_time <= node_c.due_date + 1e-9:
            if needs_station and s_id is not None:
                energy_at_s = curr_energy - inst.energy[last_node][s_id]
                recharge_t = (inst.B - max(0.0, energy_at_s)) * inst.g
                curr_route.visits.append(Visit(s_id, NodeType.STATION))
                curr_time += inst.travel_time[last_node][s_id] + recharge_t
                curr_energy = inst.B
                last_node = s_id

            curr_route.visits.append(Visit(c, NodeType.CUSTOMER))
            curr_energy -= inst.energy[last_node][c]
            curr_time += inst.travel_time[last_node][c]
            wait = max(0.0, node_c.ready_time - curr_time)
            curr_time += wait + node_c.service_time
            curr_demand += node_c.demand
            last_node = c
            inserted = True

        if not inserted:
            if last_node == inst.depot_id:
                # Ja estamos numa rota nova a partir do deposito e ainda falhou:
                # forca insercao (aceitando violacao de TW e/ou energia)
                curr_route.visits.append(Visit(c, NodeType.CUSTOMER))
                curr_energy -= inst.energy[last_node][c]
                curr_time += inst.travel_time[last_node][c]
                wait = max(0.0, node_c.ready_time - curr_time)
                curr_time += wait + node_c.service_time
                curr_demand += node_c.demand
                last_node = c
                i += 1
            else:
                # Abre nova rota e tenta de novo
                routes.append(_close_route(curr_route, inst.depot_id))
                curr_route = _new_route(inst.depot_id)
                curr_energy = inst.B
                curr_time = 0.0
                curr_demand = 0.0
                last_node = inst.depot_id
            continue

        i += 1

    routes.append(_close_route(curr_route, inst.depot_id))
    return Solution(routes=routes)


# ---------------------------------------------------------------------------
# Camada E: solucoes IES
# ---------------------------------------------------------------------------

def _generate_ies(inst: EVRPInstance, p_skip: float) -> Solution:
    """
    Gera solucao IES: respeita TW e capacidade, mas pula estacoes com prob p_skip.
    Clamp: apos primeiro deficit numa rota, energia e fixada em 0 para evitar cascata.
    """
    customers = inst.customer_ids[:]
    customers.sort(key=lambda c: inst.nodes[c].ready_time + random.uniform(0, 30))

    routes: List[Route] = []
    curr_route = _new_route(inst.depot_id)
    curr_energy = inst.B
    curr_time = 0.0
    curr_demand = 0.0
    last_node = inst.depot_id
    deficit_gerado = False

    i = 0
    while i < len(customers):
        c = customers[i]
        node_c = inst.nodes[c]

        # Capacidade
        if curr_demand + node_c.demand > inst.Q + 1e-9:
            routes.append(_close_route(curr_route, inst.depot_id))
            curr_route = _new_route(inst.depot_id)
            curr_energy = inst.B
            curr_time = 0.0
            curr_demand = 0.0
            last_node = inst.depot_id
            deficit_gerado = False
            continue

        e_to_c = inst.energy[last_node][c]
        needs_station = curr_energy - e_to_c < 1e-9
        skip_this = needs_station and not deficit_gerado and random.random() < p_skip

        if skip_this:
            # Pula estacao: tenta inserir diretamente (gera deficit)
            arr_time = curr_time + inst.travel_time[last_node][c]
            if arr_time <= node_c.due_date + 1e-9:
                curr_route.visits.append(Visit(c, NodeType.CUSTOMER))
                curr_energy -= e_to_c
                curr_energy = 0.0       # CLAMP
                deficit_gerado = True
                curr_time = arr_time
                wait = max(0.0, node_c.ready_time - curr_time)
                curr_time += wait + node_c.service_time
                curr_demand += node_c.demand
                last_node = c
                i += 1
                continue
            # TW violada: fallback para insercao com estacao

        # Tenta inserir normalmente (com estacao se necessario)
        if needs_station and not skip_this:
            s_id = _best_station(last_node, c, curr_energy, inst)
            if s_id is not None:
                energy_at_s = curr_energy - inst.energy[last_node][s_id]
                recharge_t = (inst.B - max(0.0, energy_at_s)) * inst.g
                arr_via_s = (curr_time
                             + inst.travel_time[last_node][s_id]
                             + recharge_t
                             + inst.travel_time[s_id][c])
                if arr_via_s <= node_c.due_date + 1e-9:
                    curr_route.visits.append(Visit(s_id, NodeType.STATION))
                    curr_time += inst.travel_time[last_node][s_id] + recharge_t
                    curr_energy = inst.B
                    last_node = s_id
                    needs_station = False

        arr_time = curr_time + inst.travel_time[last_node][c]
        if arr_time <= node_c.due_date + 1e-9 and not needs_station:
            curr_route.visits.append(Visit(c, NodeType.CUSTOMER))
            curr_energy -= inst.energy[last_node][c]
            if deficit_gerado:
                curr_energy = max(0.0, curr_energy)
            curr_time = arr_time
            wait = max(0.0, node_c.ready_time - curr_time)
            curr_time += wait + node_c.service_time
            curr_demand += node_c.demand
            last_node = c
            i += 1
        elif last_node == inst.depot_id:
            # Forca insercao em rota nova
            curr_route.visits.append(Visit(c, NodeType.CUSTOMER))
            curr_energy -= inst.energy[last_node][c]
            curr_time += inst.travel_time[last_node][c]
            wait = max(0.0, node_c.ready_time - curr_time)
            curr_time += wait + node_c.service_time
            curr_demand += node_c.demand
            last_node = c
            i += 1
        else:
            routes.append(_close_route(curr_route, inst.depot_id))
            curr_route = _new_route(inst.depot_id)
            curr_energy = inst.B
            curr_time = 0.0
            curr_demand = 0.0
            last_node = inst.depot_id
            deficit_gerado = False

    routes.append(_close_route(curr_route, inst.depot_id))
    return Solution(routes=routes)


# ---------------------------------------------------------------------------
# Camada R: solucoes aleatorias
# ---------------------------------------------------------------------------

def _generate_random(inst: EVRPInstance) -> Solution:
    """Sem verificacoes de restricoes. Gera IEC, IC, IJT para diversidade."""
    customers = inst.customer_ids[:]
    random.shuffle(customers)

    depot_due = inst.nodes[inst.depot_id].due_date
    r_threshold = random.uniform(0, depot_due * 0.5)

    routes: List[Route] = []
    curr_route = _new_route(inst.depot_id)
    curr_time = 0.0
    last_node = inst.depot_id

    for c in customers:
        curr_time += inst.travel_time[last_node][c]
        delay = max(0.0, curr_time - inst.nodes[c].due_date)

        if delay > r_threshold:
            routes.append(_close_route(curr_route, inst.depot_id))
            curr_route = _new_route(inst.depot_id)
            curr_time = 0.0
            last_node = inst.depot_id
            curr_time += inst.travel_time[last_node][c]

        curr_route.visits.append(Visit(c, NodeType.CUSTOMER))
        curr_time += inst.nodes[c].service_time
        last_node = c

    routes.append(_close_route(curr_route, inst.depot_id))
    return Solution(routes=routes)


# ---------------------------------------------------------------------------
# ORE fallback
# ---------------------------------------------------------------------------

def ore_fallback(sol: Solution, inst: EVRPInstance) -> Optional[Solution]:
    """Remove uma estacao aleatoria de uma solucao viavel para gerar IES."""
    new_sol = sol.copy()
    candidates = []
    for r_idx, route in enumerate(new_sol.routes):
        for v_idx, v in enumerate(route.visits):
            if v.node_type == NodeType.STATION:
                candidates.append((r_idx, v_idx))

    if not candidates:
        return None

    r_idx, v_idx = random.choice(candidates)
    new_sol.routes[r_idx].visits.pop(v_idx)
    new_sol._dirty = True
    return new_sol


# ---------------------------------------------------------------------------
# Funcao principal de inicializacao
# ---------------------------------------------------------------------------

def initialize(inst: EVRPInstance, N_P: int = 100,
               alpha_V: float = 0.40, alpha_E: float = 0.35,
               beta_s: float = 0.20, p_skip: float = 0.50,
               max_tries_mult: int = 5, seed: int = 42) -> InitResult:

    random.seed(seed)

    n_V = round(alpha_V * N_P)
    n_E = round(alpha_E * N_P)
    n_R = N_P - n_V - n_E

    population: List[Solution] = []
    empty_stats = PopulationStats()

    # ── Camada V ───────────────────────────────────────────────
    tries, n_V_real = 0, 0
    while n_V_real < n_V and tries < max_tries_mult * n_V:
        sol = _generate_feasible(inst, beta_s)
        run_ci(sol, inst, empty_stats)
        if sol.metadata.inf_type == InfeasType.FEASIBLE:
            population.append(sol)
            n_V_real += 1
        else:
            # Aceita solucoes nao-viaveis da Camada V como bonus de diversidade
            population.append(sol)
        tries += 1
        if len(population) >= n_V:
            break

    # ── Camada E ───────────────────────────────────────────────
    tries, n_E_real = 0, 0
    while n_E_real < n_E and tries < max_tries_mult * n_E:
        sol = _generate_ies(inst, p_skip)
        run_ci(sol, inst, empty_stats)
        if sol.metadata.inf_type == InfeasType.IES:
            population.append(sol)
            n_E_real += 1
        tries += 1

    # Fallback via ORE
    feasible_pool = [s for s in population
                     if s.metadata.inf_type == InfeasType.FEASIBLE]
    ore_tries = 0
    while n_E_real < n_E and feasible_pool and ore_tries < max_tries_mult * n_E:
        src = random.choice(feasible_pool)
        candidate = ore_fallback(src, inst)
        if candidate is not None:
            run_ci(candidate, inst, empty_stats)
            if candidate.metadata.inf_type == InfeasType.IES:
                population.append(candidate)
                n_E_real += 1
        ore_tries += 1

    # ── Camada R ───────────────────────────────────────────────
    for _ in range(n_R):
        sol = _generate_random(inst)
        run_ci(sol, inst, empty_stats)
        population.append(sol)

    # ── Completar ate N_P se necessario ────────────────────────
    while len(population) < N_P:
        sol = _generate_random(inst)
        run_ci(sol, inst, empty_stats)
        population.append(sol)

    # ── Pos-inicializacao: normalizar com stats reais ──────────
    stats = update_pop_stats(population)
    for sol in population:
        renormalize(sol, stats)
        sol.metadata.inf_type = classify_type(sol.cv_components)

    # ── Contagem de tipos ──────────────────────────────────────
    counts = Counter(s.metadata.inf_type for s in population)
    n_V_f = counts[InfeasType.FEASIBLE]
    n_IES = counts[InfeasType.IES]
    n_IEC = counts[InfeasType.IEC]
    n_IC = counts[InfeasType.IC]
    n_IJT = counts[InfeasType.IJT]
    n_IM = counts[InfeasType.IM]

    total_inf = N_P - n_V_f
    eta = total_inf / N_P if N_P > 0 else 0.0
    eta_E = n_IES / N_P if N_P > 0 else 0.0
    eta_C = n_IC / N_P if N_P > 0 else 0.0
    eta_T = n_IJT / N_P if N_P > 0 else 0.0

    # ── Alertas de diagnostico ─────────────────────────────────
    if eta < 0.15:
        print(f'[INIT ALERTA] Instancia facil: eta={eta:.2f}. Aumente p_skip.')
    if eta > 0.70:
        print(f'[INIT ALERTA] Instancia muito dificil: eta={eta:.2f}.')
    frac_ies = n_IES / max(1, total_inf)
    if frac_ies < 0.40 and total_inf > 0:
        print(f'[INIT ALERTA] Poucos IES entre inviaveis: {frac_ies:.0%}.')

    return InitResult(
        population=population,
        n_V=n_V_f, n_IES=n_IES, n_IEC=n_IEC,
        n_IC=n_IC, n_IJT=n_IJT, n_IM=n_IM,
        eta=eta, eta_E=eta_E, eta_C=eta_C, eta_T=eta_T,
        pop_stats=stats,
    )
