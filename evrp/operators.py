"""
Operadores pymoo para o EVRP: Sampling, Crossover e Mutation.

EVRPSampling: delega para initialization.initialize().
EVRPCrossover: crossover de rotas (Wang et al.) com integridade estrutural.
EVRPMutation: or-opt (relocate) com guia de energia.

Os operadores preservam a cobertura energetica existente sem inserir
estacoes novas (reparacao energetica pertence a Fase 2 — ORPG).
"""

from __future__ import annotations

import copy
import random
from typing import List, Tuple

import numpy as np
from pymoo.core.crossover import Crossover
from pymoo.core.mutation import Mutation
from pymoo.core.sampling import Sampling

from .evaluator import PopulationStats, run_ci
from .initialization import InitResult, initialize
from .instance import EVRPInstance
from .representation import NodeType, Route, Solution, Visit


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

class EVRPSampling(Sampling):
    """Delegado para initialize(). Armazena InitResult para uso pelo runner."""

    def __init__(self, instance: EVRPInstance, init_params: dict):
        super().__init__()
        self.instance = instance
        self.init_params = init_params
        self.init_result: InitResult | None = None

    def _do(self, problem, n_samples, **kwargs):
        result = initialize(self.instance, N_P=n_samples, **self.init_params)
        self.init_result = result
        problem.pop_stats = result.pop_stats
        problem.init_result = result  # armazena no problem (persistente)

        X = np.empty((n_samples, 1), dtype=object)
        for i, sol in enumerate(result.population):
            X[i, 0] = sol
        return X


# ---------------------------------------------------------------------------
# Crossover de rotas (Wang et al.)
# ---------------------------------------------------------------------------

class EVRPCrossover(Crossover):
    def __init__(self):
        super().__init__(2, 2)  # 2 pais, 2 filhos

    def _do(self, problem, X, **kwargs):
        n_matings = X.shape[1]
        Y = np.empty((2, n_matings, 1), dtype=object)

        for k in range(n_matings):
            p1: Solution = X[0, k, 0]
            p2: Solution = X[1, k, 0]
            c1, c2 = _route_crossover(p1, p2, problem.instance)
            Y[0, k, 0] = c1
            Y[1, k, 0] = c2

        return Y


def _route_crossover(p1: Solution, p2: Solution,
                     inst: EVRPInstance) -> Tuple[Solution, Solution]:
    if not p1.routes or not p2.routes:
        return p1.copy(), p2.copy()

    r1 = random.choice(p1.routes)
    r2 = random.choice(p2.routes)

    C1 = set(r1.customer_ids())
    C2 = set(r2.customer_ids())

    c1 = _build_offspring(p2, C1, r1, inst)
    c2 = _build_offspring(p1, C2, r2, inst)

    return c1, c2


def _cleanup_zombie_stations(route: Route) -> None:
    """
    Remove estacoes que ficaram sem clientes adjacentes apos remocao
    de clientes no crossover. Uma estacao e 'zumbi' se ambos os vizinhos
    imediatos sao deposito ou outra estacao. Nao insere nada.
    """
    changed = True
    while changed:
        changed = False
        new_visits = []
        for i, v in enumerate(route.visits):
            if v.node_type != NodeType.STATION:
                new_visits.append(v)
                continue
            prev_type = route.visits[i - 1].node_type if i > 0 else None
            next_type = route.visits[i + 1].node_type if i < len(route.visits) - 1 else None
            if (prev_type in (NodeType.DEPOT, NodeType.STATION)
                    and next_type in (NodeType.DEPOT, NodeType.STATION)):
                changed = True
                continue
            new_visits.append(v)
        route.visits = new_visits


def _build_offspring(base: Solution, to_remove: set,
                     new_route: Route, inst: EVRPInstance) -> Solution:
    child = base.copy()
    removed: List[int] = []

    for route in child.routes:
        kept = []
        for v in route.visits:
            if v.node_type == NodeType.CUSTOMER and v.node_id in to_remove:
                removed.append(v.node_id)
            else:
                kept.append(v)
        route.visits = kept

    # Remove rotas que ficaram vazias (so depositos e/ou estacoes)
    child.routes = [r for r in child.routes if r.n_customers() > 0]

    # Conserta depositos (I2)
    for r in child.routes:
        if not r.visits or r.visits[0].node_type != NodeType.DEPOT:
            r.visits.insert(0, Visit(inst.depot_id, NodeType.DEPOT))
        if r.visits[-1].node_type != NodeType.DEPOT:
            r.visits.append(Visit(inst.depot_id, NodeType.DEPOT))

    # Adiciona rota herdada
    imported = Route(visits=[copy.copy(v) for v in new_route.visits])
    child.routes.append(imported)

    # Orfaos: clientes removidos do base que NAO estao na rota importada
    imported_custs = set(v.node_id for v in new_route.visits
                         if v.node_type == NodeType.CUSTOMER)
    orphans = [c for c in removed if c not in imported_custs]

    if orphans:
        _reinsert_orphans(child, orphans, inst)

    # Limpa estacoes zumbi em todas as rotas
    for route in child.routes:
        _cleanup_zombie_stations(route)

    child._dirty = True
    return child


def _reinsert_orphans(sol: Solution, orphans: List[int],
                      inst: EVRPInstance) -> None:
    """
    Reinsere clientes orfaos com guia de energia.
    Prefere posicoes onde a energia existente e suficiente para alcancar
    o cliente sem deficit. Nao insere estacoes — apenas usa informacao
    de energia como guia para evitar destruir cobertura existente.
    """
    for c_id in orphans:
        best_pos, best_cost = None, float('inf')
        node_c = inst.nodes[c_id]
        found_energy_ok = False

        for r_idx, route in enumerate(sol.routes):
            demand_r = sum(inst.nodes[v.node_id].demand
                          for v in route.visits
                          if v.node_type == NodeType.CUSTOMER)
            if demand_r + node_c.demand > inst.Q + 1e-9:
                continue

            for pos in range(1, len(route.visits)):
                prev_id = route.visits[pos - 1].node_id
                next_id = route.visits[pos].node_id
                cost = (inst.dist[prev_id][c_id]
                        + inst.dist[c_id][next_id]
                        - inst.dist[prev_id][next_id])

                dep_energy = route.visits[pos - 1].departure_energy
                energy_at_pos = dep_energy if dep_energy > 0 else inst.B
                energy_ok = (energy_at_pos - inst.energy[prev_id][c_id]) >= -1e-9

                if energy_ok:
                    if not found_energy_ok:
                        found_energy_ok = True
                        best_cost = float('inf')
                        best_pos = None
                    if cost < best_cost:
                        best_cost = cost
                        best_pos = (r_idx, pos)
                elif not found_energy_ok and cost < best_cost:
                    best_cost = cost
                    best_pos = (r_idx, pos)

        if best_pos and found_energy_ok:
            r_idx, pos = best_pos
            sol.routes[r_idx].visits.insert(pos, Visit(c_id, NodeType.CUSTOMER))
        else:
            new_r = Route(visits=[
                Visit(inst.depot_id, NodeType.DEPOT),
                Visit(c_id, NodeType.CUSTOMER),
                Visit(inst.depot_id, NodeType.DEPOT),
            ])
            sol.routes.append(new_r)


# ---------------------------------------------------------------------------
# Mutation: or-opt (relocate) com guia de energia
# ---------------------------------------------------------------------------

class EVRPMutation(Mutation):
    def __init__(self, prob: float = 0.15):
        super().__init__()
        self.prob = prob

    def _do(self, problem, X, **kwargs):
        for i in range(len(X)):
            if random.random() < self.prob:
                sol: Solution = X[i, 0]
                X[i, 0] = _or_opt_mutation(sol, problem.instance)
        return X


def _or_opt_mutation(sol: Solution, inst: EVRPInstance) -> Solution:
    """
    Move um cliente aleatorio para a melhor posicao disponivel em qualquer rota.
    Usa guia de energia: prefere posicoes onde a energia existente e suficiente.
    Muito menos destrutivo que 2-opt para perfis energeticos.
    """
    if not sol.routes:
        return sol
    new_sol = sol.copy()

    all_cust_positions = [
        (r_idx, v_idx)
        for r_idx, route in enumerate(new_sol.routes)
        for v_idx, v in enumerate(route.visits)
        if v.node_type == NodeType.CUSTOMER
    ]
    if not all_cust_positions:
        return new_sol

    src_r, src_v = random.choice(all_cust_positions)
    c_id = new_sol.routes[src_r].visits[src_v].node_id
    node_c = inst.nodes[c_id]

    new_sol.routes[src_r].visits.pop(src_v)
    if new_sol.routes[src_r].n_customers() == 0:
        new_sol.routes.pop(src_r)

    best_pos, best_cost = None, float('inf')
    found_energy_ok = False

    for r_idx, route in enumerate(new_sol.routes):
        demand_r = sum(inst.nodes[v.node_id].demand for v in route.visits
                       if v.node_type == NodeType.CUSTOMER)
        if demand_r + node_c.demand > inst.Q + 1e-9:
            continue
        for pos in range(1, len(route.visits)):
            prev_id = route.visits[pos - 1].node_id
            next_id = route.visits[pos].node_id
            cost = (inst.dist[prev_id][c_id]
                    + inst.dist[c_id][next_id]
                    - inst.dist[prev_id][next_id])

            dep_energy = route.visits[pos - 1].departure_energy
            energy_at_pos = dep_energy if dep_energy > 0 else inst.B
            energy_ok = (energy_at_pos - inst.energy[prev_id][c_id]) >= -1e-9

            if energy_ok:
                if not found_energy_ok:
                    found_energy_ok = True
                    best_cost = float('inf')
                    best_pos = None
                if cost < best_cost:
                    best_cost = cost
                    best_pos = (r_idx, pos)
            elif not found_energy_ok and cost < best_cost:
                best_cost = cost
                best_pos = (r_idx, pos)

    if best_pos:
        r_idx, pos = best_pos
        new_sol.routes[r_idx].visits.insert(pos, Visit(c_id, NodeType.CUSTOMER))
    else:
        new_sol.routes.append(Route(visits=[
            Visit(inst.depot_id, NodeType.DEPOT),
            Visit(c_id, NodeType.CUSTOMER),
            Visit(inst.depot_id, NodeType.DEPOT),
        ]))

    new_sol._dirty = True
    return new_sol
