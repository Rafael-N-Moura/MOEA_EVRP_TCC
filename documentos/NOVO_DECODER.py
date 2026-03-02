"""
Módulo de Decodificação para EVRPTW-PR.
Implementa a heurística construtiva com Separação Radical de Modos (IDEA Concept).
"""

from typing import List, Tuple, Optional
import math
from .model import Context, Solution, Route, RouteStep, Node, NodeType

# -------------------------------------------------------------------------
# FUNÇÕES AUXILIARES DE ENERGIA E SELEÇÃO
# -------------------------------------------------------------------------

def _calculate_energy_needed(from_node: Node, to_node: Node, context: Context) -> float:
    return from_node.distance_to(to_node) * context.consumption_rate

def _get_safety_buffer(node: Node, context: Context) -> float:
    """Calcula energia mínima para chegar à estação mais próxima."""
    if node.node_type == NodeType.DEPOT:
        return 0.0
    nearest_station = min(context.stations, key=lambda s: node.distance_to(s))
    return _calculate_energy_needed(node, nearest_station, context)

def _get_best_station_for_trip(
    current_node: Node, 
    target_node: Node, 
    current_battery: float, 
    context: Context
) -> Node:
    """Encontra a estação que minimiza o desvio (Usado apenas no modo Viável)."""
    valid_stations = []
    
    # Filtra por alcance
    for station in context.stations:
        energy_to_station = _calculate_energy_needed(current_node, station, context)
        if current_battery >= energy_to_station - 1e-5:
            valid_stations.append(station)
    
    candidates = valid_stations if valid_stations else context.stations

    # Menor desvio: Atual -> Estação -> Alvo
    best_station = min(
        candidates,
        key=lambda s: current_node.distance_to(s) + s.distance_to(target_node)
    )
    return best_station

# -------------------------------------------------------------------------
# FUNÇÃO PRINCIPAL DE DECODIFICAÇÃO
# -------------------------------------------------------------------------

def decode(
    individual: List[int], 
    context: Context, 
    force_battery_feasible: bool = True
) -> Solution:
    
    solution = Solution()
    solution.battery_violation = 0.0
    
    customers = [context.customers[i] for i in individual if i < len(context.customers)]
    
    current_route = Route(vehicle_id=1)
    current_route.add_step(RouteStep(context.depot, 0.0, 0.0, context.battery_capacity, context.battery_capacity, 0.0))
    
    current_node = context.depot
    current_battery = context.battery_capacity
    current_load = 0.0
    current_time = 0.0
    vehicle_idx = 1

    # =====================================================================
    # LÓGICA MODO VIÁVEL (Rigoroso, Insere Estações)
    # =====================================================================
    def execute_feasible_move(target_node: Node) -> bool:
        nonlocal current_node, current_battery, current_time, current_route, current_load
        
        energy_trip = _calculate_energy_needed(current_node, target_node, context)
        energy_buffer = _get_safety_buffer(target_node, context) if target_node.node_type != NodeType.DEPOT else 0.0
        
        must_recharge = current_battery < (energy_trip + energy_buffer)
        
        if must_recharge:
            station = _get_best_station_for_trip(current_node, target_node, current_battery, context)
            energy_station = _calculate_energy_needed(current_node, station, context)
            
            if current_battery < energy_station:
                return True # Falha Crítica: Não alcança nem a estação. Aborta split.

            # Viaja para Estação
            dist_station = current_node.distance_to(station)
            arr_time_st = current_time + (dist_station / context.velocity)
            arr_bat_st = current_battery - energy_station
            
            # Recarga
            energy_trip_from_st = _calculate_energy_needed(station, target_node, context)
            target_level = min(context.battery_capacity, energy_trip_from_st + energy_buffer + (context.battery_capacity * 0.05))
            recharge_qty = target_level - arr_bat_st
            
            dep_time_st = arr_time_st + (recharge_qty / context.recharge_rate)
            
            current_route.add_step(RouteStep(
                station, arr_time_st, dep_time_st, arr_bat_st, target_level, current_load, recharge_amount=recharge_qty
            ))
            
            current_node = station
            current_battery = target_level
            current_time = dep_time_st
            energy_trip = energy_trip_from_st # Atualiza energia necessária para o alvo

        # Viaja para o Alvo
        dist_target = current_node.distance_to(target_node)
        arr_time = current_time + (dist_target / context.velocity)
        arr_bat = current_battery - energy_trip
        
        if arr_bat < 0: return True # Fallback de segurança

        start_service = max(arr_time, getattr(target_node, 'ready_time', 0))
        dep_time = start_service + getattr(target_node, 'service_time', 0)
        
        current_route.add_step(RouteStep(target_node, arr_time, dep_time, arr_bat, arr_bat, current_load))
        
        current_node = target_node
        current_battery = arr_bat
        current_time = dep_time
        return False

    # =====================================================================
    # LÓGICA MODO INVIÁVEL (Ignora Estações, Pura Exploração Geométrica)
    # =====================================================================
    def execute_infeasible_move(target_node: Node) -> bool:
        nonlocal current_node, current_battery, current_time, current_route, current_load
        
        energy_trip = _calculate_energy_needed(current_node, target_node, context)
        dist_target = current_node.distance_to(target_node)
        travel_time = dist_target / context.velocity
        
        ghost_time_penalty = 0.0
        
        # Avalia Bateria em Linha Reta
        if current_battery < energy_trip:
            # Dívida de Energia: Chegou zerado e ainda faltou
            deficit = energy_trip - current_battery
            solution.battery_violation += deficit
            
            # TEMPO FANTASMA: Se ele tivesse recarregado essa falta, quanto tempo demoraria?
            # Isso impede que o f2 (satisfação) fique mentiroso.
            ghost_time_penalty = deficit / context.recharge_rate
            
            current_battery = 0.0 # Bateria zera
        else:
            current_battery -= energy_trip

        # Aplica o movimento com a penalidade temporal (se houver)
        arr_time = current_time + travel_time + ghost_time_penalty
        
        start_service = max(arr_time, getattr(target_node, 'ready_time', 0))
        dep_time = start_service + getattr(target_node, 'service_time', 0)
        
        current_route.add_step(RouteStep(target_node, arr_time, dep_time, current_battery, current_battery, current_load))
        
        current_node = target_node
        current_time = dep_time
        return False

    # --- LOOP PRINCIPAL DE CLIENTES ---
    solution.routes.append(current_route)
    
    for customer in customers:
        # Check Carga (Hard Constraint, igual para ambos)
        if current_load + customer.demand > context.vehicle_capacity:
            if force_battery_feasible:
                execute_feasible_move(context.depot)
            else:
                execute_infeasible_move(context.depot)
                
            vehicle_idx += 1
            current_route = Route(vehicle_id=vehicle_idx)
            current_route.add_step(RouteStep(context.depot, current_time, current_time, context.battery_capacity, context.battery_capacity, 0.0))
            solution.routes.append(current_route)
            
            current_node = context.depot
            current_battery = context.battery_capacity
            current_load = 0.0
            # Time NÃO zera, frota heterogênea temporal
        
        # Movimento
        if force_battery_feasible:
            split_needed = execute_feasible_move(customer)
            if split_needed:
                # Aborta e tenta com veículo novo
                vehicle_idx += 1
                current_route = Route(vehicle_id=vehicle_idx)
                current_route.add_step(RouteStep(context.depot, current_time, current_time, context.battery_capacity, context.battery_capacity, 0.0))
                solution.routes.append(current_route)
                current_node = context.depot
                current_battery = context.battery_capacity
                current_load = 0.0
                execute_feasible_move(customer)
        else:
            execute_infeasible_move(customer)

        current_load += customer.demand
        
    # Retorno Final ao Depósito
    if force_battery_feasible:
        execute_feasible_move(context.depot)
    else:
        execute_infeasible_move(context.depot)
    
    solution.calculate_objectives(context)
    return solution