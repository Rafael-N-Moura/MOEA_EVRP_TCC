"""
Módulo de Decodificação para EVRPTW-PR.
Implementa a heurística construtiva que transforma genótipo (permutação) em fenótipo (rotas).
"""

from typing import List, Tuple, Optional
from .model import Context, Solution, Route, RouteStep, Node, NodeType

# Parâmetros de recarga preventiva
BATTERY_THRESHOLD_PREVENTIVE = 0.30  # 30% - Recarrega preventivamente quando bateria < 30%
BATTERY_THRESHOLD_CRITICAL = 0.15  # 15% - Considera retornar ao depósito quando < 15%
BATTERY_SAFETY_MARGIN = 0.20  # 20% - Margem de segurança após recarga


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
    Calcula quantidade de energia a recarregar com margem de segurança.
    
    Args:
        current_battery: Bateria atual
        energy_needed: Energia necessária para tarefa
        battery_capacity: Capacidade máxima
        current_position: Posição atual (estação)
        customer: Cliente a visitar
        context: Contexto com parâmetros
    
    Returns:
        Quantidade de energia a recarregar
    """
    # Calcula energia total necessária: da estação ao cliente + do cliente à segurança
    energy_station_to_customer = _calculate_energy_needed(current_position, customer, context)
    
    # Encontra estação/depósito mais próximo do cliente
    nearest_safety = context.get_nearest_station(customer)
    energy_customer_to_safety = _calculate_energy_needed(customer, nearest_safety, context)
    energy_customer_to_depot = _calculate_energy_needed(customer, context.depot, context)
    energy_customer_to_safety = min(energy_customer_to_safety, energy_customer_to_depot)
    
    total_energy_needed = energy_station_to_customer + energy_customer_to_safety
    
    # Adiciona margem de segurança (20% da capacidade)
    safety_margin = battery_capacity * BATTERY_SAFETY_MARGIN
    
    # Energia total desejada após recarga
    desired_battery = total_energy_needed + safety_margin
    
    # Quantidade a recarregar
    recharge_needed = max(0.0, desired_battery - current_battery)
    
    # Limita pela capacidade máxima
    recharge_needed = min(recharge_needed, battery_capacity - current_battery)
    
    return recharge_needed


def _recharge_at_station(
    route: Route,
    current_position: Node,
    current_battery: float,
    current_load: float,
    current_time: float,
    customer: Node,
    context: Context
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
    
    Returns:
        Tupla (nova_posição, nova_bateria, novo_tempo)
    """
    # Encontra estação mais próxima
    nearest_station = context.get_nearest_station(current_position)
    distance_to_station = current_position.distance_to(nearest_station)
    energy_to_station = distance_to_station * context.consumption_rate
    
    # Verifica se consegue chegar à estação
    if current_battery < energy_to_station:
        # Não consegue chegar - violação grave
        # Retorna estado atual (será tratado como violação)
        return current_position, current_battery, current_time
    
    # Vai para a estação
    battery_after_travel = current_battery - energy_to_station
    travel_time = distance_to_station / context.velocity
    arrival_time = current_time + travel_time
    
    # Calcula recarga necessária
    recharge_needed = _calculate_recharge_amount(
        battery_after_travel,
        _calculate_total_energy_for_customer(nearest_station, customer, context)[1],
        context.battery_capacity,
        nearest_station,
        customer,
        context
    )
    
    # Tempo de recarga
    recharge_time = recharge_needed * context.recharge_rate
    
    # Bateria após recarga
    battery_after_recharge = battery_after_travel + recharge_needed
    
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
    
    return nearest_station, battery_after_recharge, arrival_time + recharge_time


def decode(individual: List[int], context: Context) -> Solution:
    """
    Decodifica uma permutação de IDs de clientes em uma solução completa.
    
    Args:
        individual: Lista de inteiros representando IDs de clientes (ex: [5, 12, 1, ...])
                   Os IDs devem corresponder aos índices dos clientes na lista context.customers
        context: Contexto global com mapa e parâmetros
    
    Returns:
        Solution: Solução completa com rotas, métricas e viabilidade
    """
    solution = Solution()
    
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
    for customer in customer_nodes:
        # Passo A: Verificação de Capacidade de Carga
        if current_load + customer.demand > context.vehicle_capacity:
            # Retorna ao depósito, fecha veículo atual, abre novo veículo
            return_to_depot(
                current_route, current_position, context.depot,
                current_battery, current_load, current_time, context
            )
            
            solution.routes.append(current_route)
            
            # Abre novo veículo
            current_vehicle += 1
            current_route = Route(vehicle_id=current_vehicle)
            current_position = context.depot
            current_battery = context.battery_capacity
            current_load = 0.0
            current_time = 0.0
            
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
        
        # Passo B: Verificação Preventiva de Viabilidade Energética
        # Calcula energia total necessária ANTES de decidir visitar cliente
        energy_to_customer, total_energy_needed = _calculate_total_energy_for_customer(
            current_position, customer, context
        )
        
        # Verifica se precisa recarregar preventivamente
        needs_recharge = _should_recharge_preventively(
            current_battery,
            context.battery_capacity,
            total_energy_needed
        )
        
        if needs_recharge:
            # Tenta recarregar na estação mais próxima
            new_position, new_battery, new_time = _recharge_at_station(
                current_route,
                current_position,
                current_battery,
                current_load,
                current_time,
                customer,
                context
            )
            
            # Verifica se conseguiu recarregar (se não conseguiu, new_battery == current_battery)
            if new_battery == current_battery and current_battery < energy_to_customer:
                # Não conseguiu chegar à estação - violação grave
                solution.add_violation(
                    f"Veículo {current_vehicle}: Bateria insuficiente para chegar à estação "
                    f"(bateria: {current_battery:.2f}, necessário: {energy_to_customer:.2f})"
                )
                # Continua com bateria atual (será violação ao tentar visitar cliente)
            else:
                # Atualiza estado após recarga
                current_position = new_position
                current_battery = new_battery
                current_time = new_time
                
                # Recalcula energia necessária da nova posição
                energy_to_customer, total_energy_needed = _calculate_total_energy_for_customer(
                    current_position, customer, context
                )
        
        # Verificação adicional: Se bateria está crítica e não há estação próxima,
        # considera retornar ao depósito e abrir novo veículo
        if current_battery < context.battery_capacity * BATTERY_THRESHOLD_CRITICAL:
            # Verifica se é melhor retornar ao depósito
            energy_to_depot = _calculate_energy_needed(current_position, context.depot, context)
            if current_battery >= energy_to_depot:
                # Tem bateria para retornar - considera retornar se próximo cliente está longe
                if total_energy_needed > current_battery * 0.8:  # Se precisa de mais de 80% da bateria atual
                    # Retorna ao depósito e abre novo veículo
                    return_to_depot(
                        current_route, current_position, context.depot,
                        current_battery, current_load, current_time, context
                    )
                    solution.routes.append(current_route)
                    
                    # Abre novo veículo
                    current_vehicle += 1
                    current_route = Route(vehicle_id=current_vehicle)
                    current_position = context.depot
                    current_battery = context.battery_capacity
                    current_load = 0.0
                    current_time = 0.0
                    
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
                    
                    # Recalcula energia necessária do depósito
                    energy_to_customer, total_energy_needed = _calculate_total_energy_for_customer(
                        current_position, customer, context
                    )
        
        # Passo C: Visita ao Cliente (com verificação de janelas de tempo)
        # Usa energia já calculada anteriormente
        battery_needed = energy_to_customer
        
        # Calcula distância para tempo de viagem
        distance_to_customer = current_position.distance_to(customer)
        
        # Verificação final de bateria (após todas as tentativas de recarga)
        if current_battery < battery_needed:
            solution.add_violation(
                f"Veículo {current_vehicle}: Bateria insuficiente para chegar ao cliente {customer.id} "
                f"(bateria: {current_battery:.2f}, necessário: {battery_needed:.2f})"
            )
            current_battery = 0.0  # Permite continuação para penalização
        else:
            current_battery -= battery_needed
        
        # Calcula tempo de viagem
        travel_time = distance_to_customer / context.velocity
        arrival_time = current_time + travel_time
        
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
        
        # Atualiza estado
        current_position = customer
        current_time = departure_time
    
    # Finalização: Último veículo retorna ao depósito
    return_to_depot(
        current_route, current_position, context.depot,
        current_battery, current_load, current_time, context
    )
    solution.routes.append(current_route)
    
    # Recalcula métricas básicas (veículos e distância)
    solution.__post_init__()
    
    # Calcula objetivos finais (custo e insatisfação)
    solution.calculate_objectives(context)
    
    return solution


def return_to_depot(
    route: Route,
    current_position: Node,
    depot: Node,
    current_battery: float,
    current_load: float,
    current_time: float,
    context: Context
):
    """
    Adiciona passo de retorno ao depósito e fecha a rota.
    """
    distance_to_depot = current_position.distance_to(depot)
    battery_needed = distance_to_depot * context.consumption_rate
    
    # Verifica se tem bateria suficiente
    if current_battery < battery_needed:
        # Violação - não consegu e retornar
        # Mas permite continuação para penalização
        arrival_battery = 0.0
    else:
        arrival_battery = current_battery - battery_needed
    
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
