"""
Módulo de Decodificação para EVRPTW-PR.
Implementa a heurística construtiva que transforma genótipo (permutação) em fenótipo (rotas).
"""

from typing import List, Tuple, Optional
from .model import Context, Solution, Route, RouteStep, Node, NodeType

# Parâmetros de recarga preventiva (conforme especificação)
BATTERY_THRESHOLD_PREVENTIVE = 0.30  # 30% - Recarrega preventivamente quando bateria < 30%
BATTERY_THRESHOLD_CRITICAL = 0.15  # 15% - Considera retornar ao depósito quando < 15%
BATTERY_SAFETY_MARGIN = 0.05  # 5% - Margem de segurança após recarga (conforme especificação)


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


def _should_recharge_preventively(
    current_battery: float,
    battery_capacity: float,
    energy_needed: float
) -> bool:
    """
    Decide se deve recarregar preventivamente antes de visitar um cliente.
    
    Args:
        current_battery: Bateria atual
        battery_capacity: Capacidade máxima da bateria
        energy_needed: Energia total necessária para visitar cliente + segurança
    
    Returns:
        True se deve recarregar preventivamente
    """
    # Recarrega se bateria está abaixo do threshold preventivo
    if current_battery < battery_capacity * BATTERY_THRESHOLD_PREVENTIVE:
        return True
    
    # Recarrega se bateria atual não é suficiente para a tarefa
    if current_battery < energy_needed:
        return True
    
    # Recarrega se após a tarefa a bateria ficaria muito baixa (< threshold crítico)
    battery_after = current_battery - energy_needed
    if battery_after < battery_capacity * BATTERY_THRESHOLD_CRITICAL:
        return True
    
    return False


def _calculate_recharge_amount(
    current_battery: float,
    energy_needed: float,
    battery_capacity: float,
    current_position: Node,
    customer: Node,
    context: Context
) -> float:
    """
    Calcula quantidade de energia a recarregar com margem de segurança (Smart Recharge).
    
    Conforme especificação: E_alvo = E(S_atual -> C_alvo) + E_buffer(C_alvo) + Margem(5%)
    
    Args:
        current_battery: Bateria atual (após chegar na estação)
        energy_needed: Energia necessária para tarefa (não usado diretamente, recalculamos)
        battery_capacity: Capacidade máxima
        current_position: Posição atual (estação)
        customer: Cliente a visitar
        context: Contexto com parâmetros
    
    Returns:
        Quantidade de energia a recarregar
    """
    # Calcula energia total necessária: da estação ao cliente + do cliente à segurança
    energy_station_to_customer = _calculate_energy_needed(current_position, customer, context)
    
    # Encontra estação/depósito mais próximo do cliente (safety buffer)
    nearest_safety = context.get_nearest_station(customer)
    energy_customer_to_safety = _calculate_energy_needed(customer, nearest_safety, context)
    energy_customer_to_depot = _calculate_energy_needed(customer, context.depot, context)
    energy_customer_to_safety = min(energy_customer_to_safety, energy_customer_to_depot)
    
    total_energy_needed = energy_station_to_customer + energy_customer_to_safety
    
    # Verifica se é fisicamente impossível (conforme especificação - Cliente Impossível)
    if total_energy_needed > battery_capacity:
        # Cliente impossível: retorna capacidade máxima (100%)
        # No modo conservador, isso será detectado e abortará a rota
        return battery_capacity - current_battery
    
    # Adiciona margem de segurança (5% conforme especificação)
    safety_margin = battery_capacity * BATTERY_SAFETY_MARGIN
    
    # Energia total desejada após recarga
    desired_battery = total_energy_needed + safety_margin
    
    # Quantidade a recarregar: Delta_E = min(Q, E_alvo) - max(0, E_atual)
    recharge_needed = max(0.0, desired_battery - current_battery)
    
    # Limita pela capacidade máxima
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
    
    Adiciona distância e tempo reais à rota, mas acumula violação (G2) pelo déficit de energia.
    
    Args:
        route: Rota atual
        current_position: Posição atual
        current_battery: Bateria atual
        current_load: Carga atual
        current_time: Tempo atual
        destination: Destino (estação ou cliente)
        context: Contexto com parâmetros
        solution: Solução para acumular violação (G2)
    
    Returns:
        Tupla (nova_posição, nova_bateria (zerada), novo_tempo)
    """
    distance = current_position.distance_to(destination)
    energy_needed = distance * context.consumption_rate
    
    if debug:
        print(f"      [DÍVIDA] Viagem com dívida:")
        print(f"        De: {current_position.id} -> Para: {destination.id}")
        print(f"        Distância: {distance:.2f}")
        print(f"        Energia necessária: {energy_needed:.2f}")
        print(f"        Bateria atual: {current_battery:.2f}")
    
    # Calcula déficit de energia
    if current_battery < energy_needed:
        deficit = energy_needed - current_battery
        solution.battery_violation += deficit  # Acumula G2
        if debug:
            print(f"        [VIOLAÇÃO G2] Déficit: {deficit:.2f}")
            print(f"        G2 acumulado: {solution.battery_violation:.2f}")
    
    # Viaja fisicamente (adiciona distância e tempo reais)
    travel_time = distance / context.velocity
    arrival_time = current_time + travel_time
    
    # Bateria fica zerada (virtualmente pagou a dívida com violação)
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
    debug: bool = False
) -> Tuple[Node, float, float]:
    """
    Recarrega na estação mais próxima.
    
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
    
    Returns:
        Tupla (nova_posição, nova_bateria, novo_tempo)
    """
    # Encontra estação mais próxima
    nearest_station = context.get_nearest_station(current_position)
    distance_to_station = current_position.distance_to(nearest_station)
    energy_to_station = distance_to_station * context.consumption_rate
    
    if debug:
        print(f"    [ESTAÇÃO] Estação mais próxima: {nearest_station.id}")
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
                current_time, nearest_station, context, solution, debug
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
    total_energy_needed = _calculate_total_energy_for_customer(nearest_station, customer, context)[1]
    recharge_needed = _calculate_recharge_amount(
        battery_after_travel,
        total_energy_needed,
        context.battery_capacity,
        nearest_station,
        customer,
        context
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
        node=nearest_station,
        arrival_time=arrival_time,
        departure_time=arrival_time + recharge_time,
        battery_arrival=battery_after_travel,
        battery_departure=battery_after_recharge,
        recharge_amount=recharge_needed,
        load=current_load
    )
    route.add_step(station_step)
    
    if debug:
        print(f"      [ESTAÇÃO] Passo adicionado à rota: {nearest_station.id}")
    
    return nearest_station, battery_after_recharge, arrival_time + recharge_time


def decode(individual: List[int], context: Context, force_battery_feasible: bool = True, debug: bool = False) -> Solution:
    """
    Decodifica uma permutação de IDs de clientes em uma solução completa.
    
    Args:
        individual: Lista de inteiros representando IDs de clientes (ex: [5, 12, 1, ...])
                   Os IDs devem corresponder aos índices dos clientes na lista context.customers
        context: Contexto global com mapa e parâmetros
        force_battery_feasible: Se True, força viabilidade de bateria retornando ao depósito
                               preventivamente. Se False, permite violações de bateria para
                               explorar limites (modo relaxado).
        debug: Se True, imprime logs detalhados durante a decodificação
    
    Returns:
        Solution: Solução completa com rotas, métricas e viabilidade
    """
    solution = Solution()
    solution.battery_violation = 0.0  # Inicializa violação de bateria
    
    if debug:
        print(f"[DECODE] Iniciando decodificação - force_battery_feasible={force_battery_feasible}")
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
    
    # Iteração: Para cada cliente na permutação
    for customer_idx, customer in enumerate(customer_nodes):
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
                current_battery, current_load, current_time, context, solution, force_battery_feasible, debug
            )
            
            if debug:
                print(f"  [VEÍCULO {current_vehicle}] FECHADO - G2 acumulado até agora: {solution.battery_violation:.2f}")
                print(f"  [VEÍCULO {current_vehicle}] Total de passos: {len(current_route.steps)}")
            
            solution.routes.append(current_route)
            
            # Abre novo veículo
            current_vehicle += 1
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
            # MODO CONSERVADOR: Look-ahead rigoroso (conforme especificação)
            # Verifica se consegue chegar E sair do cliente (total_energy = E_trip + E_safe)
            total_energy_needed = energy_to_customer + energy_customer_to_safety
            
            # Check 1: Consigo chegar no Cliente?
            if current_battery < energy_to_customer:
                if debug:
                    print(f"  [RECARGA PREVENTIVA 1] Bateria ({current_battery:.2f}) < energia até cliente ({energy_to_customer:.2f})")
                    print(f"    Vai para estação mais próxima de {current_position.id}")
                
                # Não consegue chegar - precisa recarregar AGORA
                # Vai para estação mais próxima
                new_position, new_battery, new_time = _recharge_at_station(
                    current_route,
                    current_position,
                    current_battery,
                    current_load,
                    current_time,
                    customer,
                    context,
                    solution,
                    allow_debt=False,  # Modo conservador não permite dívida
                    debug=debug
                )
                
                if debug:
                    print(f"  [RECARGA] Após recarga:")
                    print(f"    Posição: {new_position.id} (era {current_position.id})")
                    print(f"    Bateria: {new_battery:.2f} (era {current_battery:.2f})")
                    print(f"    Tempo: {new_time:.2f} (era {current_time:.2f})")
                
                # Verifica se conseguiu chegar à estação
                if new_position == current_position and abs(new_battery - current_battery) < 0.01:
                    # CRÍTICO: Não consegue chegar nem na estação mais próxima
                    if debug:
                        print(f"  [ERRO] Não conseguiu chegar à estação após recarga preventiva!")
                        print(f"    Posição: {current_position.id}, Bateria: {current_battery:.2f}")
                    # Conforme especificação: Retornar ao depósito e encerrar rota (split)
                    energy_to_depot = _calculate_energy_needed(current_position, context.depot, context)
                    if current_battery >= energy_to_depot:
                        if debug:
                            print(f"  [SPLIT] Retornando ao depósito e abrindo novo veículo")
                        # Tem bateria para voltar ao depósito - faz split
                        return_to_depot(
                            current_route, current_position, context.depot,
                            current_battery, current_load, current_time, context, solution, force_battery_feasible, debug
                        )
                        solution.routes.append(current_route)
                        
                        # Abre novo veículo
                        current_vehicle += 1
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
                        
                        # Recalcula energia do novo veículo
                        energy_to_customer = _calculate_energy_needed(current_position, customer, context)
                        nearest_station_from_customer = context.get_nearest_station(customer)
                        energy_customer_to_safety = _calculate_energy_needed(customer, nearest_station_from_customer, context)
                        total_energy_needed = energy_to_customer + energy_customer_to_safety
                    else:
                        # Não consegue nem voltar ao depósito - erro crítico
                        # Adiciona violação e continua (não deveria acontecer)
                        deficit = energy_to_depot - current_battery
                        solution.battery_violation += deficit
                        solution.add_violation(
                            f"Veículo {current_vehicle}: Não consegue retornar ao depósito "
                            f"(bateria: {current_battery:.2f}, necessário: {energy_to_depot:.2f})"
                        )
                        # Força retorno ao depósito mesmo assim
                        return_to_depot(
                            current_route, current_position, context.depot,
                            0.0, current_load, current_time, context, solution, force_battery_feasible, debug
                        )
                        solution.routes.append(current_route)
                        
                        # Abre novo veículo
                        current_vehicle += 1
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
                        
                        # Recalcula energia do novo veículo
                        energy_to_customer = _calculate_energy_needed(current_position, customer, context)
                        nearest_station_from_customer = context.get_nearest_station(customer)
                        energy_customer_to_safety = _calculate_energy_needed(customer, nearest_station_from_customer, context)
                        total_energy_needed = energy_to_customer + energy_customer_to_safety
                else:
                    # Recarga funcionou, atualiza estado
                    current_position = new_position
                    current_battery = new_battery
                    current_time = new_time
                    # Recalcula energia necessária da nova posição
                    energy_to_customer = _calculate_energy_needed(current_position, customer, context)
                    nearest_station_from_customer = context.get_nearest_station(customer)
                    energy_customer_to_safety = _calculate_energy_needed(customer, nearest_station_from_customer, context)
                    total_energy_needed = energy_to_customer + energy_customer_to_safety
            
            # Check 2 (Look-ahead): Consigo sair do Cliente? (Bat >= E_trip + E_safe)
            if current_battery < total_energy_needed:
                if debug:
                    print(f"  [RECARGA PREVENTIVA 2] Look-ahead: Bateria ({current_battery:.2f}) < total necessário ({total_energy_needed:.2f})")
                    print(f"    Risco de ficar ilhado - recarga preventiva")
                    print(f"    Vai para estação mais próxima de {current_position.id}")
                
                # Risco de ficar ilhado - recarga preventiva
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
                    debug=debug
                )
                
                if debug:
                    print(f"  [RECARGA] Após recarga preventiva:")
                    print(f"    Posição: {new_position.id} (era {current_position.id})")
                    print(f"    Bateria: {new_battery:.2f} (era {current_battery:.2f})")
                    print(f"    Tempo: {new_time:.2f} (era {current_time:.2f})")
                
                # Atualiza estado após recarga preventiva
                if new_position != current_position or abs(new_battery - current_battery) > 0.01:
                    current_position = new_position
                    current_battery = new_battery
                    current_time = new_time
                    # Recalcula energia necessária da nova posição
                    energy_to_customer = _calculate_energy_needed(current_position, customer, context)
                    if debug:
                        print(f"    Nova energia até cliente: {energy_to_customer:.2f}")
        else:
            # MODO INVIÁVEL: Verificação Simples (Arriscada, sem Safety Buffer)
            # Verifica apenas se consegue chegar ao cliente (ignora se vai ficar ilhado)
            if current_battery < energy_to_customer:
                # Não consegue chegar nem no cliente - tenta ir para estação (corretivo)
                new_position, new_battery, new_time = _recharge_at_station(
                    current_route,
                    current_position,
                    current_battery,
                    current_load,
                    current_time,
                    customer,
                    context,
                    solution,
                    allow_debt=True,  # Permite viagem com dívida
                    debug=debug
                )
                
                # Atualiza estado após recarga (ou viagem com dívida)
                current_position = new_position
                current_battery = new_battery
                current_time = new_time
                # Recalcula energia necessária da nova posição
                energy_to_customer = _calculate_energy_needed(current_position, customer, context)
        
        # Passo C: Visita ao Cliente
        # Calcula distância para tempo de viagem
        distance_to_customer = current_position.distance_to(customer)
        battery_needed = energy_to_customer
        
        # Verificação final de bateria (antes de viajar para o cliente)
        if current_battery < battery_needed:
            if not force_battery_feasible:
                # MODO OTIMISTA: Permite viagem com dívida (conforme especificação)
                if debug:
                    print(f"  [DÍVIDA] Modo otimista - viajando com dívida para {customer.id}")
                # Viaja fisicamente, acumula G2, mas soma distância real em f1
                current_position, current_battery, current_time = _travel_with_debt(
                    current_route,
                    current_position,
                    current_battery,
                    current_load,
                    current_time,
                    customer,
                    context,
                    solution,
                    debug
                )
                # Após viagem com dívida, bateria já está zerada e posição já é o cliente
                battery_needed = 0.0
            else:
                # MODO CONSERVADOR: Não deveria acontecer após recarga preventiva
                # Se aconteceu, é um bug ou cliente impossível
                # Verifica se é cliente impossível (total > capacidade)
                nearest_station_from_customer = context.get_nearest_station(customer)
                energy_customer_to_safety = _calculate_energy_needed(customer, nearest_station_from_customer, context)
                total_energy = energy_to_customer + energy_customer_to_safety
                
                if total_energy > context.battery_capacity:
                    # Cliente impossível - conforme especificação: no modo conservador, adiciona violação
                    if debug:
                        print(f"  [ERRO CRÍTICO] Cliente impossível!")
                        print(f"    Total energia necessária: {total_energy:.2f}")
                        print(f"    Capacidade bateria: {context.battery_capacity:.2f}")
                        print(f"    Bateria atual: {current_battery:.2f}")
                        print(f"    Energia necessária para cliente: {battery_needed:.2f}")
                    # e tenta visitar mesmo assim (mas vai falhar e adicionar G2)
                    # Isso é melhor que pular o cliente completamente
                    deficit = battery_needed - current_battery
                    old_g2 = solution.battery_violation
                    solution.battery_violation += deficit
                    solution.add_violation(
                        f"Veículo {current_vehicle}: Cliente {customer.id} impossível "
                        f"(energia total necessária: {total_energy:.2f} > capacidade: {context.battery_capacity:.2f})"
                    )
                    if debug:
                        print(f"  [VIOLAÇÃO G2] Cliente impossível")
                        print(f"    Déficit: {deficit:.2f}")
                        print(f"    G2 antes: {old_g2:.2f} -> G2 depois: {solution.battery_violation:.2f}")
                    # Tenta visitar mesmo assim (vai acumular violação)
                    current_battery = 0.0
                else:
                    # Erro na lógica - adiciona violação como último recurso
                    if debug:
                        print(f"  [ERRO CRÍTICO] Bateria insuficiente após recarga preventiva!")
                        print(f"    Bateria: {current_battery:.2f}")
                        print(f"    Necessário: {battery_needed:.2f}")
                        print(f"    Total energia necessária: {total_energy:.2f}")
                        print(f"    Capacidade: {context.battery_capacity:.2f}")
                        print(f"    Posição atual: {current_position.id}")
                    deficit = battery_needed - current_battery
                    old_g2 = solution.battery_violation
                    solution.battery_violation += deficit
                    solution.add_violation(
                        f"Veículo {current_vehicle}: Bateria insuficiente após recarga preventiva "
                        f"(bateria: {current_battery:.2f}, necessário: {battery_needed:.2f})"
                    )
                    if debug:
                        print(f"  [VIOLAÇÃO G2] Bateria insuficiente após recarga preventiva")
                        print(f"    Déficit: {deficit:.2f}")
                        print(f"    G2 antes: {old_g2:.2f} -> G2 depois: {solution.battery_violation:.2f}")
                    current_battery = 0.0
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
        # Se chegou no cliente no modo inviável "no cheiro", pode estar ilhado
        if not force_battery_feasible:
            # Verifica se consegue sair do cliente para próxima estação
            nearest_station_from_customer = context.get_nearest_station(customer)
            energy_customer_to_safety = _calculate_energy_needed(customer, nearest_station_from_customer, context)
            
            if current_battery < energy_customer_to_safety:
                # Ficou ilhado - resgate físico com dívida
                if debug:
                    print(f"  [RESGATE] Ficou ilhado no cliente {customer.id}!")
                    print(f"    Bateria: {current_battery:.2f}")
                    print(f"    Energia necessária para estação: {energy_customer_to_safety:.2f}")
                    print(f"    Estação mais próxima: {nearest_station_from_customer.id}")
                current_position, current_battery, current_time = _travel_with_debt(
                    current_route,
                    current_position,
                    current_battery,
                    current_load,
                    current_time,
                    nearest_station_from_customer,
                    context,
                    solution,
                    debug
                )
                if debug:
                    print(f"  [RESGATE] Após resgate:")
                    print(f"    Posição: {current_position.id}")
                    print(f"    Bateria: {current_battery:.2f}")
                    print(f"    Tempo: {current_time:.2f}")
                # Após resgate, current_position já é a estação e current_battery já foi recarregada
    
    # Finalização: Último veículo retorna ao depósito
    if debug:
        print(f"\n[DECODE] Finalizando - Retornando ao depósito")
        print(f"  Veículo: {current_vehicle}")
        print(f"  Posição: {current_position.id}, Bateria: {current_battery:.2f}, G2 acumulado: {solution.battery_violation:.2f}")
    
    return_to_depot(
        current_route, current_position, context.depot,
        current_battery, current_load, current_time, context, solution, force_battery_feasible, debug
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
    debug: bool = False
):
    """
    Adiciona passo de retorno ao depósito e fecha a rota.
    
    No modo conservador (force_battery_feasible=True), se não tiver bateria suficiente
    para retornar diretamente, vai para a estação mais próxima e recarrega o suficiente
    para chegar ao depósito.
    
    Args:
        solution: Solução para acumular violação de bateria (opcional, para otimização)
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
    if current_battery < battery_needed:
        if force_battery_feasible:
            # MODO CONSERVADOR: Tenta recarregar na estação mais próxima antes de retornar
            if debug:
                print(f"    [RECARGA PREVENTIVA] Bateria insuficiente para retornar diretamente")
                print(f"      Vai para estação mais próxima para recarregar")
            
            # Encontra estação mais próxima
            nearest_station = context.get_nearest_station(current_position)
            distance_to_station = current_position.distance_to(nearest_station)
            energy_to_station = distance_to_station * context.consumption_rate
            
            if debug:
                print(f"      Estação mais próxima: {nearest_station.id}")
                print(f"      Distância até estação: {distance_to_station:.2f}")
                print(f"      Energia necessária até estação: {energy_to_station:.2f}")
            
            # Verifica se consegue chegar à estação (deveria estar garantido pelo safety buffer)
            if current_battery < energy_to_station:
                # Não consegue chegar à estação - erro crítico
                if debug:
                    print(f"      [ERRO CRÍTICO] Não consegue chegar à estação!")
                    print(f"        Déficit: {energy_to_station - current_battery:.2f}")
                if solution is not None:
                    deficit = battery_needed - current_battery
                    old_g2 = solution.battery_violation
                    solution.battery_violation += deficit
                    solution.add_violation(
                        f"Veículo {route.vehicle_id}: Não consegue chegar à estação para recarregar "
                        f"antes de retornar ao depósito (bateria: {current_battery:.2f}, "
                        f"necessário para estação: {energy_to_station:.2f})"
                    )
                    if debug:
                        print(f"        G2 antes: {old_g2:.2f} -> G2 depois: {solution.battery_violation:.2f}")
                arrival_battery = 0.0
                travel_time = distance_to_depot / context.velocity
                arrival_time = current_time + travel_time
            else:
                # Vai para a estação
                battery_after_travel_to_station = current_battery - energy_to_station
                travel_time_to_station = distance_to_station / context.velocity
                arrival_time_at_station = current_time + travel_time_to_station
                
                # Calcula energia necessária da estação ao depósito (com margem de segurança)
                energy_station_to_depot = _calculate_energy_needed(nearest_station, depot, context)
                safety_margin = context.battery_capacity * BATTERY_SAFETY_MARGIN
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
                    node=nearest_station,
                    arrival_time=arrival_time_at_station,
                    departure_time=arrival_time_at_station + recharge_time,
                    battery_arrival=battery_after_travel_to_station,
                    battery_departure=battery_after_recharge,
                    recharge_amount=recharge_needed,
                    load=current_load
                )
                route.add_step(station_step)
                
                # Atualiza posição e estado para retornar ao depósito
                current_position = nearest_station
                current_battery = battery_after_recharge
                current_time = arrival_time_at_station + recharge_time
                
                # Recalcula distância e energia necessária da estação ao depósito
                distance_to_depot = current_position.distance_to(depot)
                battery_needed = distance_to_depot * context.consumption_rate
                
                if debug:
                    print(f"      [RETORNO] Após recarga, retornando ao depósito")
                    print(f"        Bateria: {current_battery:.2f}")
                    print(f"        Energia necessária: {battery_needed:.2f}")
                
                # Verifica se após recarga consegue retornar
                if current_battery < battery_needed:
                    # Ainda não consegue - erro na lógica ou cliente impossível
                    if debug:
                        print(f"        [ERRO] Ainda não consegue retornar após recarga!")
                        print(f"          Déficit: {battery_needed - current_battery:.2f}")
                    if solution is not None:
                        deficit = battery_needed - current_battery
                        old_g2 = solution.battery_violation
                        solution.battery_violation += deficit
                        solution.add_violation(
                            f"Veículo {route.vehicle_id}: Não consegue retornar ao depósito mesmo após recarga "
                            f"(bateria: {current_battery:.2f}, necessário: {battery_needed:.2f})"
                        )
                        if debug:
                            print(f"          G2 antes: {old_g2:.2f} -> G2 depois: {solution.battery_violation:.2f}")
                    arrival_battery = 0.0
                else:
                    arrival_battery = current_battery - battery_needed
                    if debug:
                        print(f"        [OK] Bateria suficiente após recarga - chegando com {arrival_battery:.2f}")
                
                travel_time = distance_to_depot / context.velocity
                arrival_time = current_time + travel_time
        else:
            # MODO OTIMISTA: Permite viagem com dívida
            if debug:
                print(f"    [DÍVIDA] Modo otimista - retornando com dívida")
            if solution is not None:
                deficit = battery_needed - current_battery
                old_g2 = solution.battery_violation
                solution.battery_violation += deficit
                if debug:
                    print(f"      G2 antes: {old_g2:.2f} -> G2 depois: {solution.battery_violation:.2f}")
            arrival_battery = 0.0
            travel_time = distance_to_depot / context.velocity
            arrival_time = current_time + travel_time
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
