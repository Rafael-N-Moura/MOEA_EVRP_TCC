"""
Módulo de Parsing para arquivos de instância Schneider.
Responsável por converter texto bruto em objetos Context.
"""

import re
from typing import List, Tuple
from .model import Node, NodeType, Context


def parse_instance(filepath: str) -> Context:
    """
    Lê e parseia um arquivo de instância Schneider.
    
    Args:
        filepath: Caminho para o arquivo .txt
        
    Returns:
        Context: Objeto contendo todos os nós e parâmetros
    """
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    # Sanitização: remove linhas em branco e cabeçalho
    clean_lines = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith('StringID'):  # Ignora cabeçalho
            clean_lines.append(line)
    
    # Separação: dados de nós vs parâmetros
    node_lines = []
    params = {}
    
    for line in clean_lines:
        # Verifica se é linha de parâmetro (formato: "Q Vehicle fuel tank capacity /62.14/")
        param_match = re.search(r'/([\d.]+)/', line)
        if param_match:
            value = float(param_match.group(1))
            if 'Q Vehicle fuel tank capacity' in line:
                params['battery_capacity'] = value
            elif 'C Vehicle load capacity' in line:
                params['vehicle_capacity'] = value
            elif 'r fuel consumption rate' in line:
                params['consumption_rate'] = value
            elif 'g inverse refueling rate' in line:
                params['recharge_rate'] = value
            elif 'v average Velocity' in line:
                params['velocity'] = value
        else:
            # É linha de nó
            node_lines.append(line)
    
    # Parse dos nós
    depot = None
    stations = []
    customers = []
    
    for line in node_lines:
        parts = line.split()
        if len(parts) < 8:
            continue
        
        node_id = parts[0]
        node_type_str = parts[1]
        x = float(parts[2])
        y = float(parts[3])
        demand = float(parts[4])
        ready_time = float(parts[5])
        due_date = float(parts[6])
        service_time = float(parts[7])
        
        # Converte tipo string para enum
        if node_type_str == 'd':
            node_type = NodeType.DEPOT
        elif node_type_str == 'f':
            node_type = NodeType.STATION
        elif node_type_str == 'c':
            node_type = NodeType.CUSTOMER
        else:
            continue  # Tipo desconhecido, ignora
        
        node = Node(
            id=node_id,
            type=node_type,
            x=x,
            y=y,
            demand=demand,
            ready_time=ready_time,
            due_date=due_date,
            service_time=service_time
        )
        
        # Categorização
        if node_type == NodeType.DEPOT:
            depot = node
        elif node_type == NodeType.STATION:
            stations.append(node)
        elif node_type == NodeType.CUSTOMER:
            customers.append(node)
    
    # Validação
    if depot is None:
        raise ValueError("Depósito não encontrado no arquivo")
    
    # Aplica defaults se parâmetros não foram encontrados
    battery_capacity = params.get('battery_capacity', 0.0)
    vehicle_capacity = params.get('vehicle_capacity', 0.0)
    consumption_rate = params.get('consumption_rate', 1.0)  # Default conforme especificação
    recharge_rate = params.get('recharge_rate', 1.0)  # Default
    velocity = params.get('velocity', 1.0)  # Default conforme especificação
    
    # Cria contexto
    context = Context(
        depot=depot,
        stations=stations,
        customers=customers,
        battery_capacity=battery_capacity,
        vehicle_capacity=vehicle_capacity,
        consumption_rate=consumption_rate,
        recharge_rate=recharge_rate,
        velocity=velocity
    )
    
    return context
