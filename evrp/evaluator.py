"""
Classificador de Inviabilidade (CI) e funcoes de avaliacao.

Nucleo computacional do IAS-EVRP: percorre rotas sequencialmente,
calcula perfis de energia/tempo, identifica segmentos deficientes,
normaliza violacoes e classifica o tipo de inviabilidade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .instance import EVRPInstance
from .representation import (
    CVVector, InfeasType, NodeType, Route, Segment, Solution,
)


# ---------------------------------------------------------------------------
# PopulationStats e normalizacao
# ---------------------------------------------------------------------------

@dataclass
class PopulationStats:
    max_energy: float = 0.0
    min_energy: float = float('inf')
    max_cascade: float = 0.0
    min_cascade: float = float('inf')
    max_cap: float = 0.0
    min_cap: float = float('inf')
    max_tw: float = 0.0
    min_tw: float = float('inf')


def update_pop_stats(population: List[Solution]) -> PopulationStats:
    """O(N_P): uma passagem linear sobre a populacao."""
    stats = PopulationStats()
    for sol in population:
        if sol._raw_energy > stats.max_energy:
            stats.max_energy = sol._raw_energy
        if sol._raw_energy < stats.min_energy:
            stats.min_energy = sol._raw_energy
        if sol._raw_cascade > stats.max_cascade:
            stats.max_cascade = sol._raw_cascade
        if sol._raw_cascade < stats.min_cascade:
            stats.min_cascade = sol._raw_cascade
        if sol._raw_cap > stats.max_cap:
            stats.max_cap = sol._raw_cap
        if sol._raw_cap < stats.min_cap:
            stats.min_cap = sol._raw_cap
        if sol._raw_tw > stats.max_tw:
            stats.max_tw = sol._raw_tw
        if sol._raw_tw < stats.min_tw:
            stats.min_tw = sol._raw_tw
    return stats


def _normalize(raw: float, max_raw: float, min_raw: float) -> float:
    if max_raw <= min_raw:
        return 1.0 if raw > 1e-9 else 0.0
    return (raw - min_raw) / (max_raw - min_raw)


def renormalize(sol: Solution, stats: PopulationStats) -> None:
    """Atualiza cv_components sem recalcular perfis (usa _raw armazenado)."""
    sol.cv_components.cv_energy = _normalize(
        sol._raw_energy, stats.max_energy, stats.min_energy)
    sol.cv_components.cv_cascade = _normalize(
        sol._raw_cascade, stats.max_cascade, stats.min_cascade)
    sol.cv_components.cv_cap = _normalize(
        sol._raw_cap, stats.max_cap, stats.min_cap)
    sol.cv_components.cv_tw = _normalize(
        sol._raw_tw, stats.max_tw, stats.min_tw)


# ---------------------------------------------------------------------------
# compute_route_profile: nucleo do CI
# ---------------------------------------------------------------------------

def compute_route_profile(route: Route, inst: EVRPInstance) -> None:
    """
    Percorre a rota sequencialmente calculando perfis de energia e tempo.
    Popula energy_profile, time_profile, deficient_segments e _raw_*.
    """
    route.energy_profile = []
    route.time_profile = []
    route.deficient_segments = []
    route._raw_energy = 0.0
    route._raw_cascade = 0.0
    route._raw_cap = 0.0
    route._raw_tw = 0.0

    if len(route.visits) < 2:
        route.energy_profile.append(inst.B)
        route.time_profile.append(0.0)
        return

    curr_energy = inst.B
    curr_time = 0.0
    total_demand = 0.0
    in_cascade = False

    route.energy_profile.append(curr_energy)
    route.time_profile.append(curr_time)

    for j in range(1, len(route.visits)):
        prev = route.visits[j - 1]
        curr = route.visits[j]
        i_id, j_id = prev.node_id, curr.node_id

        # ── Energia ──────────────────────────────────────────
        e_ij = inst.energy[i_id][j_id]
        curr_energy -= e_ij
        curr.arrival_energy = curr_energy

        if curr_energy < -1e-9:
            deficit = -curr_energy
            route._raw_energy += deficit
            seg = Segment(
                from_idx=j - 1, to_idx=j,
                energy_consumed=e_ij,
                energy_deficit=deficit,
            )
            route.deficient_segments.append(seg)
            if in_cascade:
                route._raw_cascade += 1
            else:
                in_cascade = True
        else:
            in_cascade = False

        if curr.node_type == NodeType.STATION:
            curr.departure_energy = inst.B
            curr_energy = inst.B
            in_cascade = False
        else:
            curr.departure_energy = max(0.0, curr_energy)

        route.energy_profile.append(curr_energy)

        # ── Tempo ────────────────────────────────────────────
        t_ij = inst.travel_time[i_id][j_id]
        curr_time += t_ij
        curr.arrival_time = curr_time

        if curr.node_type == NodeType.CUSTOMER:
            node = inst.nodes[j_id]
            wait = max(0.0, node.ready_time - curr_time)
            delay = max(0.0, curr_time - node.due_date)
            curr.waiting_time = wait
            curr.delay_time = delay
            curr.service_start = curr_time + wait
            curr_time += wait + node.service_time
            excess = max(0.0, delay - inst.md)
            if excess > 1e-9:
                route._raw_tw += excess
            total_demand += node.demand
        elif curr.node_type == NodeType.STATION:
            energy_to_recharge = inst.B - max(0.0, curr.arrival_energy)
            recharge_time = energy_to_recharge * inst.g
            curr_time += recharge_time

        curr.departure_time = curr_time
        route.time_profile.append(curr_time)

    # ── Capacidade ───────────────────────────────────────────
    route._raw_cap = max(0.0, total_demand - inst.Q)

    # ── Janela do deposito ───────────────────────────────────
    depot = inst.nodes[inst.depot_id]
    last_time = route.visits[-1].arrival_time
    depot_delay = last_time - depot.due_date
    if depot_delay > 1e-9:
        excess = max(0.0, depot_delay - inst.md)
        if excess > 1e-9:
            route._raw_tw += excess


# ---------------------------------------------------------------------------
# classify_type
# ---------------------------------------------------------------------------

def classify_type(cv: CVVector, tol: float = 1e-9) -> InfeasType:
    has_e = cv.cv_energy > tol
    has_cas = cv.cv_cascade > tol
    has_cap = cv.cv_cap > tol
    has_tw = cv.cv_tw > tol

    n = sum([has_e, has_cas, has_cap, has_tw])
    if n == 0:
        return InfeasType.FEASIBLE

    if (has_e or has_cas) and (has_cap or has_tw):
        return InfeasType.IM

    if has_e and not has_cap and not has_tw:
        return InfeasType.IEC if has_cas else InfeasType.IES

    if has_cap and not has_e and not has_tw:
        return InfeasType.IC

    if has_tw and not has_e and not has_cap:
        return InfeasType.IJT

    return InfeasType.IM


# ---------------------------------------------------------------------------
# compute_objectives
# ---------------------------------------------------------------------------

def compute_objectives(sol: Solution, inst: EVRPInstance) -> None:
    """Calcula f1-f5 e armazena em sol.metadata. Sem correcao EOC."""
    m = sol.metadata
    m.n_vehicles = len(sol.routes)
    m.total_distance = 0.0
    m.makespan = 0.0
    m.total_waiting = 0.0
    m.total_delay = 0.0

    for route in sol.routes:
        dist_r = sum(
            inst.dist[route.visits[k].node_id][route.visits[k + 1].node_id]
            for k in range(len(route.visits) - 1)
        )
        m.total_distance += dist_r

        if len(route.visits) >= 2:
            tempo_r = route.visits[-1].arrival_time - route.visits[0].departure_time
        else:
            tempo_r = 0.0
        m.makespan = max(m.makespan, tempo_r)

        for v in route.visits:
            if v.node_type == NodeType.CUSTOMER:
                m.total_waiting += v.waiting_time
                m.total_delay += v.delay_time


# ---------------------------------------------------------------------------
# run_ci: orquestrador
# ---------------------------------------------------------------------------

def run_ci(sol: Solution, inst: EVRPInstance, stats: PopulationStats) -> None:
    """Executa CI completo: perfil, violacoes brutas, normalizacao, tipo, objetivos."""
    sol._raw_energy = 0.0
    sol._raw_cascade = 0.0
    sol._raw_cap = 0.0
    sol._raw_tw = 0.0

    for route in sol.routes:
        compute_route_profile(route, inst)
        sol._raw_energy += route._raw_energy
        sol._raw_cascade += route._raw_cascade
        sol._raw_cap += route._raw_cap
        sol._raw_tw += route._raw_tw

    renormalize(sol, stats)
    sol.metadata.inf_type = classify_type(sol.cv_components)
    compute_objectives(sol, inst)
    sol._dirty = False
