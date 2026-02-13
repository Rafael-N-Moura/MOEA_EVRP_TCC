"""
Módulo de Decodificação para EVRPTW-PR.
Implementa a heurística construtiva que transforma genótipo (permutação) em fenótipo (rotas).
"""

from typing import List
from .model import Context, Solution, Route, RouteStep, Node, NodeType


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
        
        # Passo B: Verificação de Viabilidade Energética (Safety Buffer)
        distance_to_customer = current_position.distance_to(customer)
        battery_needed = distance_to_customer * context.consumption_rate
        
        # Simula ir para o cliente
        battery_after_customer = current_battery - battery_needed
        
        # Encontra estação mais próxima do cliente (ou depósito como fallback)
        nearest_station = context.get_nearest_station(customer)
        distance_to_safety = customer.distance_to(nearest_station)
        # Também considera depósito como opção de segurança
        distance_to_depot = customer.distance_to(context.depot)
        distance_to_safety = min(distance_to_safety, distance_to_depot)
        battery_for_safety = distance_to_safety * context.consumption_rate
        
        # Teste: Bateria suficiente para chegar ao cliente E ir para estação/depósito?
        if battery_after_customer < battery_for_safety:
            # FALHOU: Precisa recarregar antes
            # Encontra estação mais próxima da posição atual
            nearest_station_from_current = context.get_nearest_station(current_position)
            
            # Insere visita à estação
            distance_to_station = current_position.distance_to(nearest_station_from_current)
            battery_needed_to_station = distance_to_station * context.consumption_rate
            
            # Verifica se tem bateria para chegar à estação
            if current_battery < battery_needed_to_station:
                # Não consegue nem chegar à estação - violação grave
                solution.add_violation(
                    f"Veículo {current_vehicle}: Bateria insuficiente para chegar à estação"
                )
                # Tenta mesmo assim (para permitir penalização)
                current_battery = 0.0
            else:
                # Vai para a estação
                current_battery -= battery_needed_to_station
                travel_time = distance_to_station / context.velocity
                arrival_time = current_time + travel_time
                
                # Calcula recarga necessária
                # Precisa: energia para ir da estação ao cliente + energia para ir do cliente à próxima estação
                # Mas já está na estação, então precisa considerar a energia da estação ao cliente
                # Essa estação n pode ser a mesma de antes?
                distance_station_to_customer = nearest_station_from_current.distance_to(customer)
                energy_station_to_customer = distance_station_to_customer * context.consumption_rate
                total_energy_needed = energy_station_to_customer + battery_for_safety
                recharge_needed = max(0.0, total_energy_needed - current_battery)
                recharge_needed = min(recharge_needed, context.battery_capacity - current_battery)
                
                # Tempo de recarga
                recharge_time = recharge_needed * context.recharge_rate
                
                # Atualiza bateria
                battery_after_recharge = current_battery + recharge_needed
                
                # Cria passo da estação
                station_step = RouteStep(
                    node=nearest_station_from_current,
                    arrival_time=arrival_time,
                    departure_time=arrival_time + recharge_time,
                    battery_arrival=current_battery,
                    battery_departure=battery_after_recharge,
                    recharge_amount=recharge_needed,
                    load=current_load
                )
                current_route.add_step(station_step)
                
                # Atualiza estado
                current_position = nearest_station_from_current
                current_battery = battery_after_recharge
                current_time = arrival_time + recharge_time
        
        # Passo C: Visita ao Cliente (com verificação de janelas de tempo)
        distance_to_customer = current_position.distance_to(customer)
        battery_needed = distance_to_customer * context.consumption_rate
        
        # Verifica bateria
        if current_battery < battery_needed:
            solution.add_violation(
                f"Veículo {current_vehicle}: Bateria insuficiente para chegar ao cliente {customer.id}"
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
