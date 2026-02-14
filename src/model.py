"""
Módulo de Modelos de Dados para EVRPTW-PR
Define as estruturas de dados imutáveis e mutáveis do sistema.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum


class NodeType(Enum):
    """Tipo de nó no mapa"""
    DEPOT = 'd'
    STATION = 'f'
    CUSTOMER = 'c'


@dataclass(frozen=True)
class Node:
    """
    Representa um ponto no mapa (imutável).
    Pode ser depósito, estação de recarga ou cliente.
    """
    id: str
    type: NodeType
    x: float
    y: float
    demand: float
    ready_time: float
    due_date: float
    service_time: float
    
    def distance_to(self, other: 'Node') -> float:
        """Calcula distância euclidiana até outro nó"""
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5


@dataclass
class Context:
    """
    Contexto global contendo o mapa e constantes físicas do problema.
    """
    depot: Node
    stations: List[Node]
    customers: List[Node]
    nodes_dict: Dict[str, Node] = field(default_factory=dict)
    
    # Parâmetros físicos do veículo
    battery_capacity: float = 0.0  # Q
    vehicle_capacity: float = 0.0  # C
    consumption_rate: float = 1.0  # r (default)
    recharge_rate: float = 1.0  # g (default)
    velocity: float = 1.0  # v (default)
    
    # Parâmetros de custo
    vehicle_cost: float = 1000.0  # Custo fixo por veículo
    distance_cost: float = 1.0  # Custo por unidade de distância
    
    # Parâmetros de satisfação
    delay_tolerance: float = 200.0  # Tolerância para cálculo de decaimento de satisfação (ajustado para permitir mais variação)
    
    def __post_init__(self):
        """Constrói dicionário de nós para acesso rápido"""
        self.nodes_dict = {}
        self.nodes_dict[self.depot.id] = self.depot
        for station in self.stations:
            self.nodes_dict[station.id] = station
        for customer in self.customers:
            self.nodes_dict[customer.id] = customer
    
    def get_node(self, node_id: str) -> Optional[Node]:
        """Retorna nó por ID"""
        return self.nodes_dict.get(node_id)
    
    def get_nearest_station(self, from_node: Node) -> Node:
        """
        Encontra a estação mais próxima de um nó.
        Considera também o depósito como opção (retorna o mais próximo entre estações e depósito).
        """
        if not self.stations:
            return self.depot  # Fallback para depósito
        
        # Inicia com primeira estação
        nearest = self.stations[0]
        min_dist = from_node.distance_to(nearest)
        
        # Verifica outras estações
        for station in self.stations[1:]:
            dist = from_node.distance_to(station)
            if dist < min_dist:
                min_dist = dist
                nearest = station
        
        # Também considera depósito como opção
        depot_dist = from_node.distance_to(self.depot)
        if depot_dist < min_dist:
            return self.depot
        
        return nearest


@dataclass
class RouteStep:
    """
    Registro detalhado de uma parada em uma rota (para auditoria).
    """
    node: Node
    arrival_time: float
    departure_time: float
    battery_arrival: float
    battery_departure: float
    recharge_amount: float = 0.0
    load: float = 0.0
    satisfaction_score: float = 1.0  # Score de satisfação (0.0 a 1.0)
    wait_time: float = 0.0  # Tempo de espera (se chegou antes de ready_time)
    recharge_time: float = 0.0  # Tempo gasto recarregando nesta parada
    time_window_violation: float = 0.0  # Atraso em relação ao due_date (se > 0)
    
    def __post_init__(self):
        """Garante que battery_departure seja calculado corretamente"""
        if self.battery_departure == 0.0 and self.recharge_amount > 0.0:
            self.battery_departure = self.battery_arrival + self.recharge_amount


@dataclass
class Route:
    """
    Representa uma rota completa de um veículo.
    """
    vehicle_id: int
    steps: List[RouteStep] = field(default_factory=list)
    total_distance: float = 0.0
    
    def add_step(self, step: RouteStep):
        """Adiciona um passo à rota"""
        self.steps.append(step)
        if len(self.steps) > 1:
            prev_node = self.steps[-2].node
            curr_node = step.node
            self.total_distance += prev_node.distance_to(curr_node)


@dataclass
class Solution:
    """
    Solução completa do problema EVRPTW-PR.
    Contém todas as rotas e métricas de avaliação granulares.
    """
    routes: List[Route] = field(default_factory=list)
    
    # Métricas básicas (calculadas automaticamente)
    total_vehicles: int = 0
    total_distance: float = 0.0
    
    # 6 Objetivos Atômicos (granulares)
    val_vehicles: int = 0  # f1: Número de Veículos (K)
    val_distance: float = 0.0  # f2: Distância Total Percorrida (D)
    val_duration: float = 0.0  # f3: Duração Total das Rotas (T) - Viagem + Serviço + Espera + Recarga
    val_time_window_violation: float = 0.0  # f4: Violação de Janelas de Tempo (Tw) - Soma dos atrasos
    val_wait_time: float = 0.0  # f5: Tempo de Espera (W) - Tempo esperando cliente abrir
    val_recharge_time: float = 0.0  # f6: Tempo de Recarga (Rc) - Tempo improdutivo conectado
    
    # Métricas agregadas (mantidas para compatibilidade)
    total_cost: float = 0.0
    avg_dissatisfaction: float = 0.0
    
    is_feasible: bool = True
    violations: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Calcula métricas básicas"""
        self.total_vehicles = len(self.routes)
        self.total_distance = sum(route.total_distance for route in self.routes)
    
    def calculate_all_objectives(self, context: 'Context'):
        """
        Calcula todos os 6 objetivos atômicos de forma granular.
        Deve ser chamado após todas as rotas estarem completas.
        """
        # f1: Número de Veículos
        self.val_vehicles = len(self.routes)
        
        # f2: Distância Total
        self.val_distance = sum(route.total_distance for route in self.routes)
        
        # Inicializa acumuladores para f3, f4, f5, f6
        total_duration = 0.0
        total_time_window_violation = 0.0
        total_wait_time = 0.0
        total_recharge_time = 0.0
        
        # Percorre todas as rotas e steps para calcular métricas
        for route in self.routes:
            if not route.steps:
                continue
            
            # f3: Duração Total = soma de (viagem + serviço + espera + recarga)
            # Para cada step: duração = departure_time - arrival_time
            # Para cada transição: tempo de viagem = arrival_time[next] - departure_time[prev]
            for i, step in enumerate(route.steps):
                # Duração do step (serviço + espera + recarga)
                step_duration = step.departure_time - step.arrival_time
                total_duration += step_duration
                
                # Tempo de viagem até este step (se não é o primeiro)
                if i > 0:
                    prev_step = route.steps[i-1]
                    travel_time = step.arrival_time - prev_step.departure_time
                    total_duration += travel_time
                
                # f4: Violação de Janelas de Tempo (soma dos atrasos)
                if step.time_window_violation > 0:
                    total_time_window_violation += step.time_window_violation
                
                # f5: Tempo de Espera (wait_time já calculado no step)
                total_wait_time += step.wait_time
                
                # f6: Tempo de Recarga
                total_recharge_time += step.recharge_time
        
        # f3: Duração Total das Rotas
        self.val_duration = total_duration
        
        # f4: Violação de Janelas de Tempo
        self.val_time_window_violation = total_time_window_violation
        
        # f5: Tempo de Espera
        self.val_wait_time = total_wait_time
        
        # f6: Tempo de Recarga
        self.val_recharge_time = total_recharge_time
        
        # Calcula métricas agregadas (para compatibilidade)
        self.total_cost = (self.val_vehicles * context.vehicle_cost) + (self.val_distance * context.distance_cost)
        
        # Calcula satisfação média (para compatibilidade)
        customer_satisfactions = []
        for route in self.routes:
            for step in route.steps:
                if step.node.type == NodeType.CUSTOMER:
                    customer_satisfactions.append(step.satisfaction_score)
        
        if customer_satisfactions:
            avg_satisfaction = sum(customer_satisfactions) / len(customer_satisfactions)
            self.avg_dissatisfaction = 1.0 - avg_satisfaction
        else:
            self.avg_dissatisfaction = 1.0
    
    def add_violation(self, message: str):
        """Registra uma violação física (bateria/carga) - violações de tempo não marcam como inviável"""
        # Apenas violações físicas (bateria/carga) marcam como inviável
        # Violações de tempo são tratadas via satisfação
        if "Bateria" in message or "carga" in message.lower():
            self.is_feasible = False
        self.violations.append(message)
