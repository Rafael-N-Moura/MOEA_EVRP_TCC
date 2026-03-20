"""
Decodificador para EVRPTW-PR com gestão de soluções inviáveis (decoder_spec).
Transforma cromossomo (π, δ) em solução com f1, f2, cv_energia, cv_tw.
Recarga = δ·(Q−SoC) por estação; violações acumuladas sem interromper a rota.
"""

from dataclasses import dataclass, field
from typing import List, Union, Optional, Tuple
import numpy as np

from .model import Context, Node, NodeType, Route, RouteStep


def _dist(a: Node, b: Node) -> float:
    """Distância euclidiana entre nós."""
    return a.distance_to(b)


def _energy_needed(context: Context, a: Node, b: Node) -> float:
    """Energia necessária para ir de a a b."""
    return context.consumption_rate * _dist(a, b)


@dataclass
class DecodedSolutionInfeasible:
    """
    Resultado da decodificação (π, δ).
    Usado pelo problem_2obj_constraints; não altera o Solution do modelo atual.
    """
    routes: List[Route] = field(default_factory=list)
    f1: float = 0.0   # custo total de rota (soma das distâncias)
    f2: float = 0.0   # folga normalizada em [−1,0]: −Σ max(0,l_j−τ_j) / Σ(l_j−e_j)
    cv_energia: float = 0.0  # déficit total de energia (≥ 0)
    cv_tw: float = 0.0       # violação total de janela de tempo (≥ 0)


def _return_to_depot(
    context: Context,
    depot: Node,
    stations: List[Node],
    delta: List[float],
    R: int,
    rota_atual: Route,
    pos: Node,
    SoC: float,
    tempo: float,
    idx_delta: int,
    f1_custo: float,
    f2_energia: float,
    cv_energia: float,
    cv_tw: float,
    e_0: float,
    l_0: float,
    ref_soc_min: Optional[List[float]] = None,
) -> Tuple[Route, Node, float, float, int, float, float, float, float]:
    """
    Subrotina: retornar ao depósito (decoder_spec §3.4).
    Insere estações se necessário (mesma lógica do Passo 2 com destino = depósito).
    Retorna (rota_atual, pos, SoC, tempo, idx_delta, f1_custo, f2_energia, cv_energia, cv_tw).
    """
    r = context.consumption_rate
    g = context.recharge_rate
    v = context.velocity
    Q = context.battery_capacity

    energia_necessaria = _energy_needed(context, pos, depot)

    if energia_necessaria > SoC:
        melhor_f: Optional[Node] = None
        menor_desv = float("inf")

        for f in stations:
            e_pos_f = _energy_needed(context, pos, f)
            e_f_dep = _energy_needed(context, f, depot)
            if e_pos_f > SoC:
                continue
            soc_em_f = SoC - e_pos_f
            delta_usar = delta[idx_delta] if idx_delta < R else 1.0
            soc_pos_recarga = soc_em_f + delta_usar * (Q - soc_em_f)
            if soc_pos_recarga < e_f_dep:
                continue
            desv = _dist(pos, f) + _dist(f, depot) - _dist(pos, depot)
            if desv < menor_desv:
                menor_desv = desv
                melhor_f = f

        if melhor_f is not None:
            d_pos_f = _dist(pos, melhor_f)
            f1_custo += d_pos_f
            f2_energia += r * d_pos_f
            SoC -= r * d_pos_f
            if ref_soc_min is not None:
                ref_soc_min[0] = min(ref_soc_min[0], SoC)
            tempo += d_pos_f / v

            delta_i = delta[idx_delta] if idx_delta < R else 1.0
            e_recarg = delta_i * (Q - SoC)
            SoC += e_recarg
            if ref_soc_min is not None:
                ref_soc_min[0] = min(ref_soc_min[0], SoC)
            tempo += e_recarg / g
            idx_delta += 1

            # Passo da estação na rota
            bat_arrival = SoC - e_recarg
            step_station = RouteStep(
                node=melhor_f,
                arrival_time=tempo - e_recarg / g,
                departure_time=tempo,
                battery_arrival=bat_arrival,
                battery_departure=SoC,
                recharge_amount=e_recarg,
                load=0.0,
                satisfaction_score=1.0,
            )
            rota_atual.add_step(step_station)
            pos = melhor_f
        else:
            deficit = energia_necessaria - SoC
            cv_energia += deficit
            SoC = 0.0
            if ref_soc_min is not None:
                ref_soc_min[0] = min(ref_soc_min[0], SoC)

    # Viajar ao depósito
    d_pos_dep = _dist(pos, depot)
    f1_custo += d_pos_dep
    f2_energia += r * d_pos_dep
    SoC -= r * d_pos_dep
    SoC = max(SoC, 0.0)
    if ref_soc_min is not None:
        ref_soc_min[0] = min(ref_soc_min[0], SoC)
    tempo += d_pos_dep / v
    pos = depot

    # Violação TW do depósito (Opção A da spec)
    if tempo > l_0:
        cv_tw += tempo - l_0

    return (
        rota_atual,
        pos,
        SoC,
        tempo,
        idx_delta,
        f1_custo,
        f2_energia,
        cv_energia,
        cv_tw,
    )


def decode_infeasible(
    pi: List[int],
    delta: Union[List[float], np.ndarray],
    context: Context,
    return_soc_min: bool = False,
) -> Union[DecodedSolutionInfeasible, Tuple[DecodedSolutionInfeasible, Optional[float]]]:
    """
    Decodifica cromossomo (π, δ) em solução com f1, f2, cv_energia, cv_tw.
    Conforme docs/decoder_spec.md (Passos 1–5, subrotina retorno, casos limite).

    Args:
        pi: Permutação dos índices dos clientes (0..n-1); ordem de visita.
        delta: Vetor de frações de recarga [0, 1], tamanho R (ex.: R = n).
        context: Contexto com depósito, estações, clientes e parâmetros.

    Returns:
        DecodedSolutionInfeasible com routes, f1 (distância), f2 (folga média
        normalizada), cv_energia, cv_tw.
    """
    if isinstance(delta, np.ndarray):
        delta = delta.flatten().tolist()
    n = len(context.customers)
    R = len(delta)
    depot = context.depot
    stations = context.stations
    Q_carga = context.vehicle_capacity
    Q_energy = context.battery_capacity
    r = context.consumption_rate
    g = context.recharge_rate
    v = context.velocity
    e_0 = depot.ready_time
    l_0 = depot.due_date
    ref_soc_min: Optional[List[float]] = [Q_energy] if return_soc_min else None

    rotas: List[Route] = []
    vehicle_id = 1
    rota_atual = Route(vehicle_id=vehicle_id)
    # Passo inicial: saída do depósito
    step_depot_out = RouteStep(
        node=depot,
        arrival_time=e_0,
        departure_time=e_0,
        battery_arrival=Q_energy,
        battery_departure=Q_energy,
        recharge_amount=0.0,
        load=0.0,
        satisfaction_score=1.0,
    )
    rota_atual.add_step(step_depot_out)

    SoC = Q_energy
    tempo = e_0
    carga = 0.0
    pos = depot
    idx_delta = 0
    cv_energia = 0.0
    cv_tw = 0.0
    f1_custo = 0.0
    f2_energia = 0.0  # usado internamente (distância × r); f2 de saída = folga
    # τ_j = instante de início de serviço no cliente j (para folga média)
    service_start_times: List[float] = [0.0] * n

    for j in range(n):
        if j >= len(pi):
            break
        idx_cliente = pi[j]
        if idx_cliente < 0 or idx_cliente >= n:
            continue
        c_j = context.customers[idx_cliente]
        dem_j = c_j.demand
        e_j = c_j.ready_time
        l_j = c_j.due_date
        s_j = c_j.service_time

        # ─── PASSO 1 — Verificar capacidade de carga ───
        if carga + dem_j > Q_carga:
            (
                rota_atual,
                pos,
                SoC,
                tempo,
                idx_delta,
                f1_custo,
                f2_energia,
                cv_energia,
                cv_tw,
            ) = _return_to_depot(
                context,
                depot,
                stations,
                delta,
                R,
                rota_atual,
                pos,
                SoC,
                tempo,
                idx_delta,
                f1_custo,
                f2_energia,
                cv_energia,
                cv_tw,
                e_0,
                l_0,
                ref_soc_min,
            )
            step_depot_end = RouteStep(
                node=depot,
                arrival_time=tempo,
                departure_time=tempo,
                battery_arrival=SoC,
                battery_departure=SoC,
                recharge_amount=0.0,
                load=0.0,
                satisfaction_score=1.0,
            )
            rota_atual.add_step(step_depot_end)
            rotas.append(rota_atual)

            vehicle_id += 1
            rota_atual = Route(vehicle_id=vehicle_id)
            step_depot_out = RouteStep(
                node=depot,
                arrival_time=e_0,
                departure_time=e_0,
                battery_arrival=Q_energy,
                battery_departure=Q_energy,
                recharge_amount=0.0,
                load=0.0,
                satisfaction_score=1.0,
            )
            rota_atual.add_step(step_depot_out)
            SoC = Q_energy
            tempo = e_0
            carga = 0.0
            pos = depot

        # ─── PASSO 2 — Verificar energia e inserir estação se necessário ───
        energia_necessaria = _energy_needed(context, pos, c_j)

        if energia_necessaria > SoC:
            melhor_f: Optional[Node] = None
            menor_desv = float("inf")

            for f in stations:
                e_pos_f = _energy_needed(context, pos, f)
                e_f_cj = _energy_needed(context, f, c_j)
                if e_pos_f > SoC:
                    continue
                soc_em_f = SoC - e_pos_f
                delta_usar = delta[idx_delta] if idx_delta < R else 1.0
                soc_pos_recarga = soc_em_f + delta_usar * (Q_energy - soc_em_f)
                if soc_pos_recarga < e_f_cj:
                    continue
                desv = _dist(pos, f) + _dist(f, c_j) - _dist(pos, c_j)
                if desv < menor_desv:
                    menor_desv = desv
                    melhor_f = f

            if melhor_f is not None:
                d_pos_f = _dist(pos, melhor_f)
                f1_custo += d_pos_f
                f2_energia += r * d_pos_f
                SoC -= r * d_pos_f
                if ref_soc_min is not None:
                    ref_soc_min[0] = min(ref_soc_min[0], SoC)
                tempo += d_pos_f / v

                delta_i = delta[idx_delta] if idx_delta < R else 1.0
                e_recarg = delta_i * (Q_energy - SoC)
                SoC += e_recarg
                if ref_soc_min is not None:
                    ref_soc_min[0] = min(ref_soc_min[0], SoC)
                tempo += e_recarg / g
                idx_delta += 1

                t_arrival_station = tempo - e_recarg / g
                bat_arrival_station = SoC - e_recarg
                step_station = RouteStep(
                    node=melhor_f,
                    arrival_time=t_arrival_station,
                    departure_time=tempo,
                    battery_arrival=bat_arrival_station,
                    battery_departure=SoC,
                    recharge_amount=e_recarg,
                    load=carga,
                    satisfaction_score=1.0,
                )
                rota_atual.add_step(step_station)
                pos = melhor_f
            else:
                deficit = energia_necessaria - SoC
                cv_energia += deficit
                SoC = 0.0
                if ref_soc_min is not None:
                    ref_soc_min[0] = min(ref_soc_min[0], SoC)

        # ─── PASSO 3 — Viajar até o cliente ───
        d_pos_cj = _dist(pos, c_j)
        f1_custo += d_pos_cj
        f2_energia += r * d_pos_cj
        SoC -= r * d_pos_cj
        SoC = max(SoC, 0.0)
        if ref_soc_min is not None:
            ref_soc_min[0] = min(ref_soc_min[0], SoC)
        tempo += d_pos_cj / v
        pos = c_j
        arrival_time_client = tempo  # tempo de chegada (antes de eventual espera)

        # ─── PASSO 4 — Verificar janela de tempo ───
        if tempo < e_j:
            tempo = e_j
        if tempo > l_j:
            cv_tw += tempo - l_j
        # τ_j = instante de início de serviço (para folga média)
        service_start_times[idx_cliente] = tempo

        # ─── PASSO 5 — Servir o cliente ───
        tempo += s_j
        carga += dem_j

        step_client = RouteStep(
            node=c_j,
            arrival_time=arrival_time_client,
            departure_time=tempo,
            battery_arrival=SoC,
            battery_departure=SoC,
            recharge_amount=0.0,
            load=carga,
            satisfaction_score=1.0,
        )
        rota_atual.add_step(step_client)

    # ─── Fechamento: retornar ao depósito e fechar última rota ───
    (
        rota_atual,
        pos,
        SoC,
        tempo,
        idx_delta,
        f1_custo,
        f2_energia,
        cv_energia,
        cv_tw,
    ) = _return_to_depot(
        context,
        depot,
        stations,
        delta,
        R,
        rota_atual,
        pos,
        SoC,
        tempo,
        idx_delta,
        f1_custo,
        f2_energia,
        cv_energia,
        cv_tw,
        e_0,
        l_0,
    )
    step_depot_end = RouteStep(
        node=depot,
        arrival_time=tempo,
        departure_time=tempo,
        battery_arrival=SoC,
        battery_departure=SoC,
        recharge_amount=0.0,
        load=0.0,
        satisfaction_score=1.0,
    )
    rota_atual.add_step(step_depot_end)
    rotas.append(rota_atual)

    # f₂ = folga média normalizada em [−1, 0]:
    #   soma_folgas = Σ max(0, l_j − τ_j)
    #   folga_max   = Σ (l_j − e_j)  (soma das larguras de janela)
    #   f₂ = −soma_folgas / folga_max  (0 = sem folga, −1 = folga máxima)
    soma_folgas = sum(
        max(0.0, context.customers[j].due_date - service_start_times[j])
        for j in range(n)
    )
    folga_max = sum(
        context.customers[j].due_date - context.customers[j].ready_time
        for j in range(n)
    )
    if folga_max > 0:
        f2_folga = -soma_folgas / folga_max
    else:
        f2_folga = 0.0

    sol = DecodedSolutionInfeasible(
        routes=rotas,
        f1=f1_custo,
        f2=f2_folga,
        cv_energia=cv_energia,
        cv_tw=cv_tw,
    )
    if return_soc_min:
        soc_min = ref_soc_min[0] if (ref_soc_min is not None and cv_energia == 0) else None
        return (sol, soc_min)
    return sol


def decode_registrar_soc_minimo(
    pi: List[int],
    delta: List[float],
    context: Context,
) -> Optional[float]:
    """
    Decodifica (π, δ) e retorna o SoC mínimo ao longo da rota se a solução for factível (cv_energia=0).
    Caso contrário retorna None.
    """
    _, soc_min = decode_infeasible(pi, delta, context, return_soc_min=True)
    return soc_min
