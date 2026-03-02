"""
Módulo de Decodificação para EVRPTW-PR.
Implementa a heurística construtiva que transforma genótipo (permutação) em fenótipo (rotas).
Suporta perfis de recarga (Conservative / Aggressive) conforme DECODER_ALTERNATIVO.md.
"""

from typing import List, Tuple, Optional
from .model import Context, Solution, Route, RouteStep, Node, NodeType

# Parâmetros de recarga (fallback quando perfil não especificado)
BATTERY_THRESHOLD_PREVENTIVE = 0.30  # 30% - Recarrega preventivamente quando bateria < 30%
BATTERY_THRESHOLD_CRITICAL = 0.15   # 15% - Considera retornar ao depósito quando < 15%
BATTERY_SAFETY_MARGIN = 0.05        # 5% - Margem de segurança após recarga


class RechargeProfile:
    """
    Perfil de recarga (DECODER_ALTERNATIVO.md §2.2, §3.2).
    - Conservative (C): viabilidade com margem; b_safe alto, buffer grande.
    - Aggressive (A): minimiza custo/tempo de recarga; b_safe mais baixo que C; pode ter g2_max_ratio.
    """
    __slots__ = ("name", "b_safe_ratio", "b_critical_ratio", "safety_margin_ratio", "prefer_nearest_station", "g2_max_ratio", "max_customers_per_route")

    def __init__(
        self,
        name: str,
        b_safe_ratio: float,
        b_critical_ratio: float,
        safety_margin_ratio: float,
        prefer_nearest_station: bool = False,
        g2_max_ratio: Optional[float] = None,
        max_customers_per_route: Optional[int] = None
    ):
        self.name = name
        self.b_safe_ratio = b_safe_ratio
        self.b_critical_ratio = b_critical_ratio
        self.safety_margin_ratio = safety_margin_ratio
        self.prefer_nearest_station = prefer_nearest_station
        self.g2_max_ratio = g2_max_ratio
        self.max_customers_per_route = max_customers_per_route


# Perfil conservador: recarga cedo, buffer grande (20–30%), estação por best detour
PROFILE_CONSERVATIVE = RechargeProfile(
    name="conservative",
    b_safe_ratio=0.35,
    b_critical_ratio=0.15,
    safety_margin_ratio=0.20,
    prefer_nearest_station=False,
    g2_max_ratio=None,
    max_customers_per_route=None
)

# Perfil agressivo: calibrado para n_vehicles_A ~10–30% abaixo de C, 10–30% soluções g2=0, G2 abaixo do teto
# b_safe/safety_margin um pouco maiores que antes para mais soluções viáveis; g2_max_ratio força split por rota
PROFILE_AGGRESSIVE = RechargeProfile(
    name="aggressive",
    b_safe_ratio=0.42,       # próximo do C para 10–30% g2=0 (C usa 0.35; aqui 0.42 recarrega ainda mais cedo)
    b_critical_ratio=0.14,
    safety_margin_ratio=0.18,  # buffer grande (C usa 0.20)
    prefer_nearest_station=True,
    g2_max_ratio=0.05,
    max_customers_per_route=3
)


def _calculate_energy_needed(
    from_node: Node,
    to_node: Node,
    context: Context
) -> float:
    """
    Calcula energia necessária para ir de um nó a outro.
    
    Args:
        from_node: Nó de origem
        to_node: Nó de destino
        context: Contexto com parâmetros
    
    Returns:
        Energia necessária
    """
    distance = from_node.distance_to(to_node)
    return distance * context.consumption_rate


def _calculate_total_energy_for_customer(
    current_position: Node,
    customer: Node,
    context: Context
) -> Tuple[float, float]:
    """
    Calcula energia total necessária para visitar um cliente e garantir segurança.
    
    Args:
        current_position: Posição atual do veículo
        customer: Cliente a visitar
        context: Contexto com parâmetros
    
    Returns:
        Tupla (energia_para_cliente, energia_total_com_seguranca)
    """
    # Energia para ir até o cliente
    energy_to_customer = _calculate_energy_needed(current_position, customer, context)
    
    # Energia para ir do cliente até estação/depósito mais próximo (safety buffer)
    nearest_safety = context.get_nearest_station(customer)
    energy_from_customer_to_safety = _calculate_energy_needed(customer, nearest_safety, context)
    
    # Também considera depósito como opção
    energy_to_depot = _calculate_energy_needed(customer, context.depot, context)
    energy_from_customer_to_safety = min(energy_from_customer_to_safety, energy_to_depot)
    
    total_energy = energy_to_customer + energy_from_customer_to_safety
    
    return energy_to_customer, total_energy


def _get_best_station(
    current_position: Node,
    destination: Node,
    current_battery: float,
    context: Context,
    force_battery_feasible: bool = True,
    prefer_nearest_station: bool = False,
    debug: bool = False
) -> Tuple[Node, bool]:
    """
    Encontra a melhor estação: Smart Detour (menor desvio) ou mais próxima no caminho (perfil A).
    
    Args:
        prefer_nearest_station: Se True (perfil agressivo), escolhe estação mais próxima; senão Smart Detour.
    """
    direct_distance = current_position.distance_to(destination)
    candidates = list(context.stations) + [context.depot]
    if not candidates:
        return context.depot, True

    best_station = None
    best_detour = float('inf')
    best_nearest = None
    min_dist_nearest = float('inf')
    best_reachable = None
    min_distance_to_reachable = float('inf')

    for station in candidates:
        distance_to_station = current_position.distance_to(station)
        energy_to_station = distance_to_station * context.consumption_rate
        is_reachable = current_battery >= energy_to_station

        if prefer_nearest_station:
            if is_reachable and distance_to_station < min_dist_nearest:
                min_dist_nearest = distance_to_station
                best_nearest = station
            elif not is_reachable and distance_to_station < min_distance_to_reachable:
                min_distance_to_reachable = distance_to_station
                best_reachable = station
            continue
        # Smart Detour
        distance_station_to_dest = station.distance_to(destination)
        detour_distance = distance_to_station + distance_station_to_dest - direct_distance
        if force_battery_feasible:
            if is_reachable and detour_distance < best_detour:
                best_detour = detour_distance
                best_station = station
        else:
            if is_reachable and detour_distance < best_detour:
                best_detour = detour_distance
                best_station = station
            elif not is_reachable and distance_to_station < min_distance_to_reachable:
                min_distance_to_reachable = distance_to_station
                best_reachable = station

    if prefer_nearest_station:
        if best_nearest is not None:
            return best_nearest, False
        if best_reachable is not None:
            return best_reachable, True
        return context.get_nearest_station(current_position), True

    if best_station is not None:
        return best_station, False
    if best_reachable is not None:
        return best_reachable, True
    return context.get_nearest_station(current_position), True


def _should_recharge_preventively(
    current_battery: float,
    battery_capacity: float,
    energy_needed: float,
    profile: Optional[RechargeProfile] = None
) -> bool:
    """
    Decide se deve recarregar preventivamente antes de visitar um cliente.
    Usa b_safe e b_critical do perfil quando fornecido (DECODER_ALTERNATIVO §2.2).
    
    Args:
        current_battery: Bateria atual
        battery_capacity: Capacidade máxima da bateria
        energy_needed: Energia total necessária para visitar cliente + segurança
    
    Returns:
        True se deve recarregar preventivamente
    """
    b_safe = profile.b_safe_ratio if profile else BATTERY_THRESHOLD_PREVENTIVE
    b_crit = profile.b_critical_ratio if profile else BATTERY_THRESHOLD_CRITICAL
    if current_battery < battery_capacity * b_safe:
        return True
    if current_battery < energy_needed:
        return True
    battery_after = current_battery - energy_needed
    if battery_after < battery_capacity * b_crit:
        return True
    return False


def _calculate_recharge_amount(
    current_battery: float,
    energy_needed: float,
    battery_capacity: float,
    current_position: Node,
    customer: Node,
    context: Context,
    profile: Optional[RechargeProfile] = None
) -> float:
    """
    Calcula quantidade de energia a recarregar. Margem conforme perfil (C: grande, A: pequena).
    """
    energy_station_to_customer = _calculate_energy_needed(current_position, customer, context)
    nearest_safety = context.get_nearest_station(customer)
    energy_customer_to_safety = _calculate_energy_needed(customer, nearest_safety, context)
    energy_customer_to_depot = _calculate_energy_needed(customer, context.depot, context)
    energy_customer_to_safety = min(energy_customer_to_safety, energy_customer_to_depot)
    total_energy_needed = energy_station_to_customer + energy_customer_to_safety

    if total_energy_needed > battery_capacity:
        return battery_capacity - current_battery

    margin_ratio = profile.safety_margin_ratio if profile else BATTERY_SAFETY_MARGIN
    safety_margin = battery_capacity * margin_ratio
    desired_battery = total_energy_needed + safety_margin
    recharge_needed = max(0.0, desired_battery - current_battery)
    recharge_needed = min(recharge_needed, battery_capacity - current_battery)
    return recharge_needed


def _travel_with_debt(
    route: Route,
    current_position: Node,
    current_battery: float,
    current_load: float,
    current_time: float,
    destination: Node,
    context: Context,
    solution: 'Solution',
    debug: bool = False
) -> Tuple[Node, float, float]:
    """
    Realiza viagem com dívida (quando não há bateria suficiente).
    Adiciona distância e tempo reais à rota e acumula violação (G2) pelo déficit.
    """
    distance = current_position.distance_to(destination)
    energy_needed = distance * context.consumption_rate

    if debug:
        print(f"      [DÍVIDA] Viagem com dívida:")
        print(f"        De: {current_position.id} -> Para: {destination.id}")
        print(f"        Distância: {distance:.2f}")
        print(f"        Energia necessária: {energy_needed:.2f}")
        print(f"        Bateria atual: {current_battery:.2f}")

    if current_battery < energy_needed:
        deficit = energy_needed - current_battery
        solution.battery_violation += deficit
        if debug:
            print(f"        [VIOLAÇÃO G2] Déficit: {deficit:.2f}")
            print(f"        G2 acumulado: {solution.battery_violation:.2f}")

    travel_time = distance / context.velocity
    arrival_time = current_time + travel_time
    battery_after = 0.0

    # Se destino é estação, adiciona passo da estação
    if destination.type == NodeType.STATION:
        # Calcula recarga necessária para continuar
        # (assumindo que precisa recarregar para continuar)
        recharge_needed = min(context.battery_capacity * 0.5, context.battery_capacity)  # Recarrega 50% ou capacidade máxima
        recharge_time = recharge_needed * context.recharge_rate
        battery_after = recharge_needed
        
        station_step = RouteStep(
            node=destination,
            arrival_time=arrival_time,
            departure_time=arrival_time + recharge_time,
            battery_arrival=0.0,
            battery_departure=battery_after,
            recharge_amount=recharge_needed,
            load=current_load
        )
        route.add_step(station_step)
        return destination, battery_after, arrival_time + recharge_time
    
    # Se destino é cliente, apenas atualiza posição (passo do cliente será adicionado depois)
    return destination, battery_after, arrival_time


def _recharge_at_station(
    route: Route,
    current_position: Node,
    current_battery: float,
    current_load: float,
    current_time: float,
    customer: Node,
    context: Context,
    solution: 'Solution' = None,
    allow_debt: bool = False,
    force_battery_feasible: bool = True,
    profile: Optional[RechargeProfile] = None,
    debug: bool = False
) -> Tuple[Node, float, float]:
    """
    Recarrega na melhor estação usando Smart Detour.
    
    Conforme especificação: escolhe estação que minimiza desvio triangular
    (Origem -> Estação -> Destino), respeitando autonomia atual.
    
    Args:
        route: Rota atual
        current_position: Posição atual
        current_battery: Bateria atual
        current_load: Carga atual
        current_time: Tempo atual
        customer: Cliente que será visitado após recarga
        context: Contexto com parâmetros
        solution: Solução para acumular violação (opcional)
        allow_debt: Se True, permite viagem com dívida se não conseguir chegar à estação
        force_battery_feasible: Se True, só considera estações alcançáveis (modo conservador)
        debug: Se True, imprime informações de debug
    
    Returns:
        Tupla (nova_posição, nova_bateria, novo_tempo)
    """
    prefer_nearest = profile.prefer_nearest_station if profile else False
    best_station, used_fallback = _get_best_station(
        current_position,
        customer,
        current_battery,
        context,
        force_battery_feasible=force_battery_feasible,
        prefer_nearest_station=prefer_nearest,
        debug=debug
    )
    
    distance_to_station = current_position.distance_to(best_station)
    energy_to_station = distance_to_station * context.consumption_rate
    
    if debug:
        method = "Fallback" if used_fallback else "Smart Detour"
        print(f"    [ESTAÇÃO] Melhor estação ({method}): {best_station.id}")
        print(f"      Distância: {distance_to_station:.2f}")
        print(f"      Energia necessária: {energy_to_station:.2f}")
        print(f"      Bateria atual: {current_battery:.2f}")
    
    # Verifica se consegue chegar à estação
    if current_battery < energy_to_station:
        if debug:
            print(f"      [PROBLEMA] Bateria insuficiente para chegar à estação!")
            print(f"        Déficit: {energy_to_station - current_battery:.2f}")
        
        if allow_debt and solution is not None:
            if debug:
                print(f"      [DÍVIDA] Modo inviável - permite viagem com dívida")
            # Modo inviável: permite viagem com dívida
            return _travel_with_debt(
                route, current_position, current_battery, current_load,
                current_time, best_station, context, solution, debug
            )
        else:
            if debug:
                print(f"      [ERRO] Não consegue chegar e modo conservador não permite dívida")
            # Não consegue chegar - violação grave
            # Retorna estado atual (será tratado como violação)
            return current_position, current_battery, current_time
    
    # Vai para a estação
    battery_after_travel = current_battery - energy_to_station
    travel_time = distance_to_station / context.velocity
    arrival_time = current_time + travel_time
    
    # Calcula recarga necessária
    total_energy_needed = _calculate_total_energy_for_customer(best_station, customer, context)[1]
    recharge_needed = _calculate_recharge_amount(
        battery_after_travel,
        total_energy_needed,
        context.battery_capacity,
        best_station,
        customer,
        context,
        profile=profile
    )
    
    if debug:
        print(f"      [RECARGA] Cálculo:")
        print(f"        Bateria após viagem: {battery_after_travel:.2f}")
        print(f"        Energia total necessária: {total_energy_needed:.2f}")
        print(f"        Quantidade a recarregar: {recharge_needed:.2f}")
    
    # Tempo de recarga
    recharge_time = recharge_needed * context.recharge_rate
    
    # Bateria após recarga
    battery_after_recharge = battery_after_travel + recharge_needed
    
    if debug:
        print(f"      [RECARGA] Resultado:")
        print(f"        Tempo de recarga: {recharge_time:.2f}")
        print(f"        Bateria após recarga: {battery_after_recharge:.2f}")
        print(f"        Tempo de chegada: {arrival_time:.2f}")
        print(f"        Tempo de saída: {arrival_time + recharge_time:.2f}")
    
    # Cria passo da estação
    station_step = RouteStep(
        node=best_station,
        arrival_time=arrival_time,
        departure_time=arrival_time + recharge_time,
        battery_arrival=battery_after_travel,
        battery_departure=battery_after_recharge,
        recharge_amount=recharge_needed,
        load=current_load
    )
    route.add_step(station_step)
    
    if debug:
        print(f"      [ESTAÇÃO] Passo adicionado à rota: {best_station.id}")
    
    return best_station, battery_after_recharge, arrival_time + recharge_time


def decode(
    individual: List[int],
    context: Context,
    force_battery_feasible: bool = True,
    debug: bool = False,
    use_radical_infeasible: bool = False
) -> Solution:
    """
    Decodifica uma permutação de IDs de clientes em uma solução completa.

    Args:
        individual: Lista de inteiros representando IDs de clientes (ex: [5, 12, 1, ...])
                   Os IDs devem corresponder aos índices dos clientes na lista context.customers
        context: Contexto global com mapa e parâmetros
        force_battery_feasible: Se True, força viabilidade de bateria (recargas preventivas, G2=0).
                               Se False, modo inviável (permite dívida de bateria).
        debug: Se True, imprime logs detalhados durante a decodificação
        use_radical_infeasible: Se True e force_battery_feasible=False, modo "radical": não insere
                               nenhuma estação (só movimento em linha reta), acumula G2. Maior gap
                               inviável vs viável. Ignorado quando force_battery_feasible=True.

    Returns:
        Solution: Solução completa com rotas, métricas e viabilidade
    """
    solution = Solution()
    solution.battery_violation = 0.0  # Inicializa violação de bateria

    # Perfil de recarga (DECODER_ALTERNATIVO §2.2, §4.1): C = viável, A = inviável controlado, None = radical
    if force_battery_feasible:
        profile: Optional[RechargeProfile] = PROFILE_CONSERVATIVE
    elif use_radical_infeasible:
        profile = None  # radical: sem estações
    else:
        profile = PROFILE_AGGRESSIVE

    if debug:
        print(f"[DECODE] Iniciando decodificação - force_battery_feasible={force_battery_feasible}")
        if profile:
            print(f"[DECODE] Perfil de recarga: {profile.name}")
        if not force_battery_feasible and use_radical_infeasible:
            print(f"[DECODE] Modo inviável RADICAL (sem estações)")
        print(f"[DECODE] Número de clientes: {len(individual)}")
    
    # Mapeia índices para objetos Node dos clientes
    customer_nodes = []
    for idx in individual:
        if 0 <= idx < len(context.customers):
            customer_nodes.append(context.customers[idx])
    
    # Inicialização: Abre Veículo 1 no Depósito
    current_vehicle = 1
    current_route = Route(vehicle_id=current_vehicle)
    current_position = context.depot
    current_battery = context.battery_capacity  # Bateria cheia
    current_load = 0.0
    current_time = 0.0
    
    if debug:
        print(f"[VEÍCULO {current_vehicle}] INICIADO no depósito")
        print(f"  Bateria inicial: {current_battery:.2f}/{context.battery_capacity:.2f}")
        print(f"  Carga inicial: {current_load:.2f}/{context.vehicle_capacity:.2f}")
        print(f"  Tempo inicial: {current_time:.2f}")
    
    # Passo inicial: saída do depósito
    depot_step = RouteStep(
        node=context.depot,
        arrival_time=0.0,
        departure_time=0.0,
        battery_arrival=context.battery_capacity,
        battery_departure=context.battery_capacity,
        load=0.0
    )
    current_route.add_step(depot_step)
    
    # G2 acumulado só na rota atual (modo agressivo: split se superar g2_max_ratio * Q_bat)
    current_route_g2 = 0.0
    
    # Iteração: por cliente (while para permitir retry do mesmo cliente após split por g2_max)
    customer_idx = 0
    while customer_idx < len(customer_nodes):
        customer = customer_nodes[customer_idx]
        if debug:
            print(f"\n[DECODE] Processando cliente {customer_idx+1}/{len(customer_nodes)}: {customer.id}")
            print(f"  Posição atual: {current_position.id}, Bateria: {current_battery:.2f}/{context.battery_capacity:.2f}")
        # Passo A: Verificação de Capacidade de Carga
        if current_load + customer.demand > context.vehicle_capacity:
            if debug:
                print(f"  [CAPACIDADE] Carga atual ({current_load:.2f}) + demanda ({customer.demand:.2f}) > capacidade ({context.vehicle_capacity:.2f})")
                print(f"  [VEÍCULO {current_vehicle}] FECHANDO - Retornando ao depósito por capacidade")
            
            # Retorna ao depósito, fecha veículo atual, abre novo veículo
            return_to_depot(
                current_route, current_position, context.depot,
                current_battery, current_load, current_time, context, solution,
                force_battery_feasible, profile=profile, debug=debug
            )

            if debug:
                print(f"  [VEÍCULO {current_vehicle}] FECHADO - G2 acumulado até agora: {solution.battery_violation:.2f}")
                print(f"  [VEÍCULO {current_vehicle}] Total de passos: {len(current_route.steps)}")
            
            solution.routes.append(current_route)
            
            # Abre novo veículo (reset G2 da rota para modo agressivo)
            current_vehicle += 1
            current_route_g2 = 0.0
            current_route = Route(vehicle_id=current_vehicle)
            current_position = context.depot
            current_battery = context.battery_capacity
            current_load = 0.0
            current_time = 0.0
            
            if debug:
                print(f"  [VEÍCULO {current_vehicle}] INICIADO no depósito")
                print(f"    Bateria inicial: {current_battery:.2f}/{context.battery_capacity:.2f}")
                print(f"    Carga inicial: {current_load:.2f}/{context.vehicle_capacity:.2f}")
                print(f"    Tempo inicial: {current_time:.2f}")
            
            # Passo inicial do novo veículo
            depot_step = RouteStep(
                node=context.depot,
                arrival_time=0.0,
                departure_time=0.0,
                battery_arrival=context.battery_capacity,
                battery_departure=context.battery_capacity,
                load=0.0
            )
            current_route.add_step(depot_step)
        
        # Passo B: Verificação de Chegada (Decisão de Ir ao Cliente)
        # Calcula energia necessária para chegar ao cliente
        energy_to_customer = _calculate_energy_needed(current_position, customer, context)
        
        # Encontra estação mais próxima do cliente (para safety buffer)
        nearest_station_from_customer = context.get_nearest_station(customer)
        energy_customer_to_safety = _calculate_energy_needed(customer, nearest_station_from_customer, context)
        
        if debug:
            print(f"  [ENERGIA] Para cliente {customer.id}:")
            print(f"    Energia até cliente: {energy_to_customer:.2f}")
            print(f"    Energia cliente -> estação mais próxima ({nearest_station_from_customer.id}): {energy_customer_to_safety:.2f}")
            print(f"    Total necessário (com safety): {energy_to_customer + energy_customer_to_safety:.2f}")
            print(f"    Bateria atual: {current_battery:.2f}")
        
        if force_battery_feasible:
            # MODO CONSERVADOR: Look-ahead + buffer do perfil (DECODER_ALTERNATIVO §3.2)
            margin_ratio = profile.safety_margin_ratio if profile else BATTERY_SAFETY_MARGIN
            total_energy_needed = energy_to_customer + energy_customer_to_safety + context.battery_capacity * margin_ratio

            # Caso 1: Cliente impossível (energia mínima ida+volta segurança > capacidade)
            raw_energy_needed = energy_to_customer + energy_customer_to_safety
            if raw_energy_needed > context.battery_capacity:
                if debug:
                    print(f"  [DESCARTE] Cliente {customer.id} impossível (energia {raw_energy_needed:.2f} > capacidade {context.battery_capacity:.2f}) - não visitado, G2 não alterado")
                solution.skipped_customer_ids.append(customer.id)
                customer_idx += 1
                continue

            # Caso 1b: Total com margem excede capacidade — não dá para ter bateria suficiente (evita loop infinito com Q pequeno)
            if total_energy_needed > context.battery_capacity:
                if debug:
                    print(f"  [DESCARTE] Cliente {customer.id} impossível (total com margem {total_energy_needed:.2f} > capacidade {context.battery_capacity:.2f}) - não visitado")
                solution.skipped_customer_ids.append(customer.id)
                customer_idx += 1
                continue

            # Loop: garantir bateria >= total_energy_needed; ou recarga preventiva se SOC < b_safe (DECODER_ALTERNATIVO §3.1)
            skipped_this_customer = False
            need_recharge = current_battery < total_energy_needed
            if profile and not need_recharge:
                need_recharge = _should_recharge_preventively(
                    current_battery, context.battery_capacity, total_energy_needed, profile
                )
            max_recharge_iters = 50  # evita loop infinito (ex.: Q pequeno, estações distantes)
            recharge_iters = 0
            while need_recharge and recharge_iters < max_recharge_iters:
                recharge_iters += 1
                # Uma recarga por iteração até ter bateria >= total_energy_needed (ida + safety)
                if debug:
                    print(f"  [RECARGA PREVENTIVA] Bateria ({current_battery:.2f}) < total necessário ({total_energy_needed:.2f})")
                    print(f"    Vai para estação mais próxima de {current_position.id}")
                
                new_position, new_battery, new_time = _recharge_at_station(
                    current_route,
                    current_position,
                    current_battery,
                    current_load,
                    current_time,
                    customer,
                    context,
                    solution,
                    allow_debt=False,
                    force_battery_feasible=True,
                    profile=profile,
                    debug=debug
                )
                
                if debug:
                    print(f"  [RECARGA] Após recarga:")
                    print(f"    Posição: {new_position.id} (era {current_position.id})")
                    print(f"    Bateria: {new_battery:.2f} (era {current_battery:.2f})")
                    print(f"    Tempo: {new_time:.2f} (era {current_time:.2f})")
                
                # Verifica se conseguiu chegar à estação
                if new_position == current_position and abs(new_battery - current_battery) < 0.01:
                    # Não consegue chegar à estação: retorna ao depósito (split) ou descarta cliente — sem G2
                    if debug:
                        print(f"  [SPLIT/STUCK] Não conseguiu chegar à estação após recarga preventiva")
                    energy_to_depot = _calculate_energy_needed(current_position, context.depot, context)
                    if current_battery >= energy_to_depot:
                        if debug:
                            print(f"  [SPLIT] Retornando ao depósito e abrindo novo veículo")
                        return_to_depot(
                            current_route, current_position, context.depot,
                            current_battery, current_load, current_time, context, solution,
                            force_battery_feasible, profile=profile, debug=debug
                        )
                        solution.routes.append(current_route)
                        current_vehicle += 1
                        current_route_g2 = 0.0
                        current_route = Route(vehicle_id=current_vehicle)
                        current_position = context.depot
                        current_battery = context.battery_capacity
                        current_load = 0.0
                        current_time = 0.0
                        depot_step = RouteStep(
                            node=context.depot,
                            arrival_time=0.0,
                            departure_time=0.0,
                            battery_arrival=context.battery_capacity,
                            battery_departure=context.battery_capacity,
                            load=0.0
                        )
                        current_route.add_step(depot_step)
                        energy_to_customer = _calculate_energy_needed(current_position, customer, context)
                        nearest_station_from_customer = context.get_nearest_station(customer)
                        energy_customer_to_safety = _calculate_energy_needed(customer, nearest_station_from_customer, context)
                        margin_ratio = profile.safety_margin_ratio if profile else BATTERY_SAFETY_MARGIN
                        total_energy_needed = energy_to_customer + energy_customer_to_safety + context.battery_capacity * margin_ratio
                        raw_energy_needed = energy_to_customer + energy_customer_to_safety
                        if raw_energy_needed > context.battery_capacity:
                            solution.skipped_customer_ids.append(customer.id)
                            skipped_this_customer = True
                            break
                    else:
                        # Não consegue nem voltar ao depósito: return_to_depot faz cadeia de estações (sem G2)
                        return_to_depot(
                            current_route, current_position, context.depot,
                            current_battery, current_load, current_time, context, solution,
                            force_battery_feasible, profile=profile, debug=debug
                        )
                        solution.routes.append(current_route)
                        current_vehicle += 1
                        current_route_g2 = 0.0
                        current_route = Route(vehicle_id=current_vehicle)
                        current_position = context.depot
                        current_battery = context.battery_capacity
                        current_load = 0.0
                        current_time = 0.0
                        depot_step = RouteStep(
                            node=context.depot,
                            arrival_time=0.0,
                            departure_time=0.0,
                            battery_arrival=context.battery_capacity,
                            battery_departure=context.battery_capacity,
                            load=0.0
                        )
                        current_route.add_step(depot_step)
                        solution.skipped_customer_ids.append(customer.id)
                        skipped_this_customer = True
                        break
                else:
                    current_position = new_position
                    current_battery = new_battery
                    current_time = new_time
                    energy_to_customer = _calculate_energy_needed(current_position, customer, context)
                    nearest_station_from_customer = context.get_nearest_station(customer)
                    energy_customer_to_safety = _calculate_energy_needed(customer, nearest_station_from_customer, context)
                    margin_ratio = profile.safety_margin_ratio if profile else BATTERY_SAFETY_MARGIN
                    total_energy_needed = energy_to_customer + energy_customer_to_safety + context.battery_capacity * margin_ratio
                    raw_energy_needed = energy_to_customer + energy_customer_to_safety
                    if raw_energy_needed > context.battery_capacity:
                        solution.skipped_customer_ids.append(customer.id)
                        skipped_this_customer = True
                        break
                    need_recharge = current_battery < total_energy_needed
                    if profile and not need_recharge:
                        need_recharge = _should_recharge_preventively(
                            current_battery, context.battery_capacity, total_energy_needed, profile
                        )
                    # Evita loop infinito quando Q é pequeno: já estamos com bateria cheia e ainda precisamos de mais que a capacidade
                    if current_battery >= context.battery_capacity - 1e-6 and total_energy_needed > context.battery_capacity:
                        solution.skipped_customer_ids.append(customer.id)
                        skipped_this_customer = True
                        break
                    if debug:
                        print(f"    Nova energia até cliente: {energy_to_customer:.2f}")
                    continue
            if recharge_iters >= max_recharge_iters and need_recharge:
                # Limite de recargas atingido sem conseguir bateria suficiente — descarta cliente
                solution.skipped_customer_ids.append(customer.id)
                skipped_this_customer = True
            if skipped_this_customer:
                customer_idx += 1
                continue
        else:
            # MODO INVIÁVEL (agressivo com estações)
            # Recarga se: bateria < energia até cliente OU SOC < b_safe OU bateria < ida+volta segurança (evita resgate com dívida → 10–30% g2=0)
            need_recharge_agg = current_battery < energy_to_customer
            if profile and not need_recharge_agg and current_battery < context.battery_capacity * profile.b_safe_ratio:
                need_recharge_agg = True
            total_energy_agg = None
            if profile:
                margin_agg = profile.safety_margin_ratio if profile else BATTERY_SAFETY_MARGIN
                energy_customer_to_depot = _calculate_energy_needed(customer, context.depot, context)
                # Exigir bateria para: ida ao cliente + volta (estação ou depósito) + margem → evita dívida no retorno
                energy_back = max(energy_customer_to_safety, energy_customer_to_depot)
                total_energy_agg = energy_to_customer + energy_back + context.battery_capacity * margin_agg
                if not need_recharge_agg and current_battery < total_energy_agg:
                    need_recharge_agg = True
            # Se bateria < ida+volta segurança: não permitir dívida na recarga (split se não alcançar estação) → g2=0
            avoid_stranded = profile is not None and total_energy_agg is not None and current_battery < total_energy_agg
            if not use_radical_infeasible and need_recharge_agg:
                # Split por g2_max antes de ir à estação com dívida (evita uma rota com G2 excessivo)
                g2_max_per_route = float("inf")
                if profile and getattr(profile, "g2_max_ratio", None) is not None:
                    g2_max_per_route = profile.g2_max_ratio * context.battery_capacity
                best_station, _ = _get_best_station(
                    current_position, customer, current_battery, context,
                    force_battery_feasible=False, prefer_nearest_station=profile.prefer_nearest_station if profile else True
                )
                energy_to_station = _calculate_energy_needed(current_position, best_station, context)
                deficit_to_station = max(0.0, energy_to_station - current_battery)
                if deficit_to_station > 0 and current_route_g2 + deficit_to_station > g2_max_per_route:
                    if debug:
                        print(f"  [G2_MAX] Antes recarga: G2 rota ({current_route_g2:.1f}) + déficit até estação ({deficit_to_station:.1f}) > {g2_max_per_route:.1f} → split")
                    return_to_depot(
                        current_route, current_position, context.depot,
                        current_battery, current_load, current_time, context, solution,
                        force_battery_feasible, profile=profile, debug=debug
                    )
                    solution.routes.append(current_route)
                    current_vehicle += 1
                    current_route_g2 = 0.0
                    current_route = Route(vehicle_id=current_vehicle)
                    current_position = context.depot
                    current_battery = context.battery_capacity
                    current_load = 0.0
                    current_time = 0.0
                    depot_step = RouteStep(
                        node=context.depot,
                        arrival_time=0.0,
                        departure_time=0.0,
                        battery_arrival=context.battery_capacity,
                        battery_departure=context.battery_capacity,
                        load=0.0
                    )
                    current_route.add_step(depot_step)
                    continue
                g2_before_recharge = solution.battery_violation
                # Sem dívida na recarga no agressivo (split se não alcançar estação) → mais soluções com g2=0
                allow_debt_recharge = False
                new_position, new_battery, new_time = _recharge_at_station(
                    current_route,
                    current_position,
                    current_battery,
                    current_load,
                    current_time,
                    customer,
                    context,
                    solution,
                    allow_debt=allow_debt_recharge,
                    force_battery_feasible=False,
                    profile=profile,
                    debug=debug
                )
                current_route_g2 += solution.battery_violation - g2_before_recharge
                # Ficou preso (não alcançou estação)? Split como no conservador
                if new_position == current_position and abs(new_battery - current_battery) < 0.01:
                    energy_to_depot = _calculate_energy_needed(current_position, context.depot, context)
                    if current_battery >= energy_to_depot:
                        return_to_depot(
                            current_route, current_position, context.depot,
                            current_battery, current_load, current_time, context, solution,
                            force_battery_feasible, profile=profile, debug=debug
                        )
                        solution.routes.append(current_route)
                        current_vehicle += 1
                        current_route_g2 = 0.0
                        current_route = Route(vehicle_id=current_vehicle)
                        current_position = context.depot
                        current_battery = context.battery_capacity
                        current_load = 0.0
                        current_time = 0.0
                        depot_step = RouteStep(
                            node=context.depot,
                            arrival_time=0.0,
                            departure_time=0.0,
                            battery_arrival=context.battery_capacity,
                            battery_departure=context.battery_capacity,
                            load=0.0
                        )
                        current_route.add_step(depot_step)
                        continue
                current_position = new_position
                current_battery = new_battery
                current_time = new_time
                energy_to_customer = _calculate_energy_needed(current_position, customer, context)

        # Passo C: Visita ao Cliente
        # Calcula distância para tempo de viagem
        distance_to_customer = current_position.distance_to(customer)
        battery_needed = energy_to_customer
        
        # Verificação final de bateria (antes de viajar para o cliente)
        if current_battery < battery_needed:
            if not force_battery_feasible:
                # MODO AGRESSIVO: split por g2_max antes de aceitar dívida (mantém n_vehicles_A próximo de n_vehicles_C)
                deficit = battery_needed - current_battery
                g2_max_per_route = float("inf")
                if profile and getattr(profile, "g2_max_ratio", None) is not None:
                    g2_max_per_route = profile.g2_max_ratio * context.battery_capacity
                if current_route_g2 + deficit > g2_max_per_route:
                    if debug:
                        print(f"  [G2_MAX] G2 rota ({current_route_g2:.1f}) + déficit ({deficit:.1f}) > {g2_max_per_route:.1f} → split")
                    return_to_depot(
                        current_route, current_position, context.depot,
                        current_battery, current_load, current_time, context, solution,
                        force_battery_feasible, profile=profile, debug=debug
                    )
                    solution.routes.append(current_route)
                    current_vehicle += 1
                    current_route_g2 = 0.0
                    current_route = Route(vehicle_id=current_vehicle)
                    current_position = context.depot
                    current_battery = context.battery_capacity
                    current_load = 0.0
                    current_time = 0.0
                    depot_step = RouteStep(
                        node=context.depot,
                        arrival_time=0.0,
                        departure_time=0.0,
                        battery_arrival=context.battery_capacity,
                        battery_departure=context.battery_capacity,
                        load=0.0
                    )
                    current_route.add_step(depot_step)
                    continue  # retry same customer with new vehicle
                # Viagem com dívida (G2 abaixo do teto): permite soluções inviáveis com g2 controlado (maioria abaixo de g2_max)
                if debug:
                    print(f"  [DÍVIDA] Viajando com dívida para {customer.id} (G2 rota permanece abaixo do teto)")
                g2_before = solution.battery_violation
                current_position, current_battery, current_time = _travel_with_debt(
                    current_route,
                    current_position,
                    current_battery,
                    current_load,
                    current_time,
                    customer,
                    context,
                    solution,
                    debug=debug
                )
                current_route_g2 += solution.battery_violation - g2_before
                battery_needed = 0.0
            else:
                # MODO CONSERVADOR: não deve acontecer (loop de recarga garante total_energy).
                # Se acontecer, descarta cliente sem violar G2.
                if debug:
                    print(f"  [DESCARTE] Bateria insuficiente para {customer.id} após recarga - cliente não visitado, G2 não alterado")
                solution.skipped_customer_ids.append(customer.id)
                customer_idx += 1
                continue
        else:
            # Tem bateria suficiente - viaja normalmente
            if debug:
                print(f"  [VIAGEM] Bateria suficiente - viajando normalmente")
                print(f"    Bateria antes: {current_battery:.2f}")
            current_battery -= battery_needed
            travel_time = distance_to_customer / context.velocity
            current_time += travel_time
            if debug:
                print(f"    Bateria depois: {current_battery:.2f}")
                print(f"    Tempo de viagem: {travel_time:.2f}")
                print(f"    Tempo total: {current_time:.2f}")
        
        # Se não foi viagem com dívida, calcula tempo de chegada
        if battery_needed > 0:  # Se não foi viagem com dívida, current_time já foi atualizado acima
            arrival_time = current_time
        else:
            # Viagem com dívida já atualizou current_time
            arrival_time = current_time
        
        # Verificação de janela de tempo e cálculo de satisfação
        if arrival_time < customer.ready_time:
            # Espera até ready_time
            arrival_time = customer.ready_time
        
        # Calcula satisfação baseada em atraso
        satisfaction_score = 1.0
        if arrival_time > customer.due_date:
            # Atraso detectado - calcula decaimento de satisfação
            delay = arrival_time - customer.due_date
            # Si = max(0, 1.0 - (Atraso/Tolerancia))
            satisfaction_score = max(0.0, 1.0 - (delay / context.delay_tolerance))
            # Registra informação (mas não marca como inviável - tempo é soft constraint)
            solution.violations.append(
                f"Veículo {current_vehicle}: Cliente {customer.id} - "
                f"Chegada {arrival_time:.2f} após due_date {customer.due_date:.2f} "
                f"(atraso: {delay:.2f}, satisfação: {satisfaction_score:.3f})"
            )
        
        # Tempo de serviço
        departure_time = arrival_time + customer.service_time
        
        # Atualiza carga
        current_load += customer.demand
        
        # Cria passo do cliente com satisfação calculada
        customer_step = RouteStep(
            node=customer,
            arrival_time=arrival_time,
            departure_time=departure_time,
            battery_arrival=current_battery,
            battery_departure=current_battery,  # Não recarrega em cliente
            load=current_load,
            satisfaction_score=satisfaction_score
        )
        current_route.add_step(customer_step)
        
        if debug:
            print(f"  [CLIENTE] Cliente {customer.id} visitado")
            print(f"    Chegada: {arrival_time:.2f} (ready: {customer.ready_time:.2f}, due: {customer.due_date:.2f})")
            print(f"    Partida: {departure_time:.2f}")
            print(f"    Bateria: {current_battery:.2f}")
            print(f"    Carga: {current_load:.2f}")
            print(f"    Satisfação: {satisfaction_score:.3f}")
        
        # Atualiza estado
        current_position = customer
        current_time = departure_time
        
        # Passo D: Saída do Cliente (Gestão do Risco Assumido)
        # Modo radical: não faz resgate em estação (próximo movimento será em linha reta com dívida se necessário)
        if not force_battery_feasible and not use_radical_infeasible:
            nearest_station_from_customer = context.get_nearest_station(customer)
            energy_customer_to_safety = _calculate_energy_needed(customer, nearest_station_from_customer, context)

            if current_battery < energy_customer_to_safety:
                # Ficou ilhado - resgate físico com dívida usando Smart Detour
                if debug:
                    print(f"  [RESGATE] Ficou ilhado no cliente {customer.id}!")
                    print(f"    Bateria: {current_battery:.2f}")
                    print(f"    Energia necessária para estação: {energy_customer_to_safety:.2f}")
                # Usa Smart Detour para escolher melhor estação para resgate
                # No modo otimista, considera todas as estações (mesmo não alcançáveis)
                # O destino do resgate é o depósito (ou próximo cliente, mas simplificamos para depósito)
                best_rescue_station, used_fallback = _get_best_station(
                    current_position,
                    context.depot,  # Destino do resgate (depósito)
                    current_battery,
                    context,
                    force_battery_feasible=False,  # Modo otimista - permite estações não alcançáveis
                    debug=debug
                )
                if debug:
                    method = "Fallback" if used_fallback else "Smart Detour"
                    print(f"    Melhor estação para resgate ({method}): {best_rescue_station.id}")
                g2_before_rescue = solution.battery_violation
                current_position, current_battery, current_time = _travel_with_debt(
                    current_route,
                    current_position,
                    current_battery,
                    current_load,
                    current_time,
                    best_rescue_station,
                    context,
                    solution,
                    debug
                )
                current_route_g2 += solution.battery_violation - g2_before_rescue
                if debug:
                    print(f"  [RESGATE] Após resgate:")
                    print(f"    Posição: {current_position.id}")
                    print(f"    Bateria: {current_battery:.2f}")
                    print(f"    Tempo: {current_time:.2f}")
                # Após resgate, current_position já é a estação e current_battery já foi recarregada
        
        # Modo agressivo: split por teto de G2 ou por máx. clientes por rota (n_vehicles_A ~10–30% abaixo de C)
        n_customers_this_route = sum(1 for s in current_route.steps if s.node.type == NodeType.CUSTOMER)
        if not force_battery_feasible and profile and getattr(profile, "max_customers_per_route", None) is not None:
            if n_customers_this_route >= profile.max_customers_per_route:
                if debug:
                    print(f"  [MAX_CLIENTES] Rota com {n_customers_this_route} clientes >= {profile.max_customers_per_route} → fechando rota")
                return_to_depot(
                    current_route, current_position, context.depot,
                    current_battery, current_load, current_time, context, solution,
                    force_battery_feasible, profile=profile, debug=debug
                )
                solution.routes.append(current_route)
                current_vehicle += 1
                current_route_g2 = 0.0
                current_route = Route(vehicle_id=current_vehicle)
                current_position = context.depot
                current_battery = context.battery_capacity
                current_load = 0.0
                current_time = 0.0
                depot_step = RouteStep(
                    node=context.depot,
                    arrival_time=0.0,
                    departure_time=0.0,
                    battery_arrival=context.battery_capacity,
                    battery_departure=context.battery_capacity,
                    load=0.0
                )
                current_route.add_step(depot_step)
        if not force_battery_feasible and profile and getattr(profile, "g2_max_ratio", None) is not None:
            g2_max_per_route = profile.g2_max_ratio * context.battery_capacity
            if current_route_g2 > g2_max_per_route:
                if debug:
                    print(f"  [G2_MAX] G2 rota ({current_route_g2:.1f}) > {g2_max_per_route:.1f} → fechando rota")
                return_to_depot(
                    current_route, current_position, context.depot,
                    current_battery, current_load, current_time, context, solution,
                    force_battery_feasible, profile=profile, debug=debug
                )
                solution.routes.append(current_route)
                current_vehicle += 1
                current_route_g2 = 0.0
                current_route = Route(vehicle_id=current_vehicle)
                current_position = context.depot
                current_battery = context.battery_capacity
                current_load = 0.0
                current_time = 0.0
                depot_step = RouteStep(
                    node=context.depot,
                    arrival_time=0.0,
                    departure_time=0.0,
                    battery_arrival=context.battery_capacity,
                    battery_departure=context.battery_capacity,
                    load=0.0
                )
                current_route.add_step(depot_step)
        
        customer_idx += 1
    
    # Finalização: Último veículo retorna ao depósito
    if debug:
        print(f"\n[DECODE] Finalizando - Retornando ao depósito")
        print(f"  Veículo: {current_vehicle}")
        print(f"  Posição: {current_position.id}, Bateria: {current_battery:.2f}, G2 acumulado: {solution.battery_violation:.2f}")
    
    return_to_depot(
        current_route, current_position, context.depot,
        current_battery, current_load, current_time, context, solution,
        force_battery_feasible, profile=profile, debug=debug
    )
    
    if debug:
        print(f"  [VEÍCULO {current_vehicle}] FECHADO")
        print(f"    Total de passos: {len(current_route.steps)}")
        print(f"    G2 final: {solution.battery_violation:.2f}")
    
    solution.routes.append(current_route)
    
    # Recalcula métricas básicas (veículos e distância)
    solution.__post_init__()
    
    # Calcula objetivos finais (custo e insatisfação)
    solution.calculate_objectives(context)
    
    # G2 já foi calculado durante decodificação (otimização)
    # Não precisa chamar calculate_battery_violation() novamente
    
    return solution


def return_to_depot(
    route: Route,
    current_position: Node,
    depot: Node,
    current_battery: float,
    current_load: float,
    current_time: float,
    context: Context,
    solution: 'Solution' = None,
    force_battery_feasible: bool = True,
    profile: Optional[RechargeProfile] = None,
    debug: bool = False
):
    """
    Adiciona passo de retorno ao depósito e fecha a rota.
    Usa perfil para margem de segurança e escolha de estação (DECODER_ALTERNATIVO §2.12).
    """
    distance_to_depot = current_position.distance_to(depot)
    battery_needed = distance_to_depot * context.consumption_rate
    
    if debug:
        print(f"  [RETORNO] Retornando ao depósito")
        print(f"    Posição atual: {current_position.id}")
        print(f"    Distância: {distance_to_depot:.2f}")
        print(f"    Energia necessária: {battery_needed:.2f}")
        print(f"    Bateria atual: {current_battery:.2f}")
    
    # Verifica se tem bateria suficiente
    # Conservador: sempre tenta recarga preventiva.
    # Agressivo: tenta preventiva só quando déficit é pequeno (≤6% Q); senão registra dívida → 10–30% g2=0, maioria g2 abaixo do teto
    deficit_return = max(0.0, battery_needed - current_battery) if current_battery < battery_needed else 0.0
    is_aggressive = profile is not None and getattr(profile, "g2_max_ratio", None) is not None
    try_preventive = force_battery_feasible or (
        is_aggressive and deficit_return <= 0.06 * context.battery_capacity
    )
    if current_battery < battery_needed:
        if try_preventive:
            margin_ratio = profile.safety_margin_ratio if profile else BATTERY_SAFETY_MARGIN
            # Tenta recarregar na estação mais próxima antes de retornar (perfil define prefer_nearest)
            if debug:
                print(f"    [RECARGA PREVENTIVA] Bateria insuficiente para retornar diretamente")
                print(f"      Vai para estação mais próxima para recarregar")
            
            prefer_nearest = profile.prefer_nearest_station if profile else False
            best_station, used_fallback = _get_best_station(
                current_position,
                depot,
                current_battery,
                context,
                force_battery_feasible=True,
                prefer_nearest_station=prefer_nearest,
                debug=debug
            )
            distance_to_station = current_position.distance_to(best_station)
            energy_to_station = distance_to_station * context.consumption_rate
            
            if debug:
                method = "Fallback" if used_fallback else "Smart Detour"
                print(f"      Melhor estação ({method}): {best_station.id}")
                print(f"      Distância até estação: {distance_to_station:.2f}")
                print(f"      Energia necessária até estação: {energy_to_station:.2f}")
            
            # Verifica se consegue chegar à estação (safety buffer no último cliente deveria garantir)
            if current_battery < energy_to_station:
                # Não consegue chegar à estação
                if debug:
                    print(f"      [RETORNO] Não consegue chegar à estação - passo direto ao depósito")
                arrival_battery = 0.0
                travel_time = distance_to_depot / context.velocity
                arrival_time = current_time + travel_time
                # Modo agressivo: registra dívida do retorno (mix: algumas soluções g2=0, maioria g2 abaixo do teto)
                if solution is not None and profile is not None and getattr(profile, "g2_max_ratio", None) is not None:
                    solution.battery_violation += max(0.0, battery_needed - current_battery)
            else:
                # Vai para a estação
                battery_after_travel_to_station = current_battery - energy_to_station
                travel_time_to_station = distance_to_station / context.velocity
                arrival_time_at_station = current_time + travel_time_to_station
                
                # Calcula energia necessária da estação ao depósito (margem conforme perfil)
                energy_station_to_depot = _calculate_energy_needed(best_station, depot, context)
                safety_margin = context.battery_capacity * margin_ratio
                total_energy_needed_from_station = energy_station_to_depot + safety_margin
                
                # Calcula recarga necessária
                recharge_needed = max(0.0, total_energy_needed_from_station - battery_after_travel_to_station)
                recharge_needed = min(recharge_needed, context.battery_capacity - battery_after_travel_to_station)
                
                if debug:
                    print(f"      [RECARGA] Cálculo:")
                    print(f"        Bateria após chegar à estação: {battery_after_travel_to_station:.2f}")
                    print(f"        Energia estação -> depósito: {energy_station_to_depot:.2f}")
                    print(f"        Margem de segurança: {safety_margin:.2f}")
                    print(f"        Total necessário: {total_energy_needed_from_station:.2f}")
                    print(f"        Quantidade a recarregar: {recharge_needed:.2f}")
                
                # Tempo de recarga
                recharge_time = recharge_needed * context.recharge_rate
                
                # Bateria após recarga
                battery_after_recharge = battery_after_travel_to_station + recharge_needed
                
                if debug:
                    print(f"      [RECARGA] Resultado:")
                    print(f"        Tempo de recarga: {recharge_time:.2f}")
                    print(f"        Bateria após recarga: {battery_after_recharge:.2f}")
                
                # Adiciona passo da estação
                station_step = RouteStep(
                    node=best_station,
                    arrival_time=arrival_time_at_station,
                    departure_time=arrival_time_at_station + recharge_time,
                    battery_arrival=battery_after_travel_to_station,
                    battery_departure=battery_after_recharge,
                    recharge_amount=recharge_needed,
                    load=current_load
                )
                route.add_step(station_step)
                
                # Atualiza posição e estado para retornar ao depósito
                current_position = best_station
                current_battery = battery_after_recharge
                current_time = arrival_time_at_station + recharge_time
                
                # Recalcula distância e energia necessária da estação ao depósito
                distance_to_depot = current_position.distance_to(depot)
                battery_needed = distance_to_depot * context.consumption_rate
                
                if debug:
                    print(f"      [RETORNO] Após recarga, retornando ao depósito")
                    print(f"        Bateria: {current_battery:.2f}")
                    print(f"        Energia necessária: {battery_needed:.2f}")
                
                # Caso 4: Se após recarga ainda não consegue chegar ao depósito, cadeia de estações (sem G2)
                max_chain_iters = 20  # evita loop infinito
                chain_iters = 0
                while current_battery < battery_needed and chain_iters < max_chain_iters:
                    chain_iters += 1
                    if debug:
                        print(f"        [CADEIA RECARGA] Bateria ({current_battery:.2f}) < necessário ({battery_needed:.2f}) - próxima estação")
                    best_station, _ = _get_best_station(
                        current_position, depot, current_battery, context,
                        force_battery_feasible=True,
                        prefer_nearest_station=prefer_nearest,
                        debug=debug
                    )
                    distance_to_station = current_position.distance_to(best_station)
                    energy_to_station = distance_to_station * context.consumption_rate
                    if current_battery < energy_to_station:
                        if debug:
                            print(f"        [CADEIA] Não consegue chegar à próxima estação - encerra cadeia (sem G2)")
                        break
                    battery_after_travel = current_battery - energy_to_station
                    travel_time_to_station = distance_to_station / context.velocity
                    arrival_time_at_station = current_time + travel_time_to_station
                    energy_station_to_depot = _calculate_energy_needed(best_station, depot, context)
                    safety_margin = context.battery_capacity * margin_ratio
                    total_needed = energy_station_to_depot + safety_margin
                    recharge_needed = max(0.0, min(
                        total_needed - battery_after_travel,
                        context.battery_capacity - battery_after_travel
                    ))
                    recharge_time = recharge_needed * context.recharge_rate
                    battery_after_recharge = battery_after_travel + recharge_needed
                    station_step = RouteStep(
                        node=best_station,
                        arrival_time=arrival_time_at_station,
                        departure_time=arrival_time_at_station + recharge_time,
                        battery_arrival=battery_after_travel,
                        battery_departure=battery_after_recharge,
                        recharge_amount=recharge_needed,
                        load=current_load
                    )
                    route.add_step(station_step)
                    current_position = best_station
                    current_battery = battery_after_recharge
                    current_time = arrival_time_at_station + recharge_time
                    distance_to_depot = current_position.distance_to(depot)
                    battery_needed = distance_to_depot * context.consumption_rate
                if current_battery >= battery_needed:
                    arrival_battery = current_battery - battery_needed
                    if debug:
                        print(f"        [OK] Cadeia de recargas - chegando ao depósito com {arrival_battery:.2f}")
                else:
                    arrival_battery = 0.0
                    if debug:
                        print(f"        [OK] Cadeia encerrada - chegada ao depósito com bateria 0 (sem G2)")
                travel_time = distance_to_depot / context.velocity
                arrival_time = current_time + travel_time
        else:
            # MODO OTIMISTA: Permite viagem com dívida
            deficit = battery_needed - current_battery
            if debug:
                print(f"    [DÍVIDA] Modo otimista - retornando com dívida")
            if solution is not None:
                solution.battery_violation += deficit
                if debug:
                    print(f"      G2 incremento: {deficit:.2f}")
            travel_time = distance_to_depot / context.velocity
            arrival_time = current_time + travel_time
            arrival_battery = 0.0
    else:
        # Tem bateria suficiente - retorna diretamente
        arrival_battery = current_battery - battery_needed
        if debug:
            print(f"    [OK] Bateria suficiente - chegando com {arrival_battery:.2f}")
    travel_time = distance_to_depot / context.velocity
    arrival_time = current_time + travel_time
    
    # Passo final: retorno ao depósito
    depot_return_step = RouteStep(
        node=depot,
        arrival_time=arrival_time,
        departure_time=arrival_time,
        battery_arrival=arrival_battery,
        battery_departure=arrival_battery,
        load=0.0  # Descarga completa
    )
    route.add_step(depot_return_step)
