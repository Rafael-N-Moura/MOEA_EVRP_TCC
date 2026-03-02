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
    Contém todas as rotas e métricas de avaliação.
    """
    routes: List[Route] = field(default_factory=list)
    total_vehicles: int = 0
    total_distance: float = 0.0
    total_cost: float = 0.0  # f1: Custo total (veículos + distância)
    avg_dissatisfaction: float = 0.0  # f2: Insatisfação média (0.0 = totalmente satisfeito, 1.0 = totalmente insatisfeito)
    is_feasible: bool = True
    violations: List[str] = field(default_factory=list)
    battery_violation: float = 0.0  # G2: Déficit de bateria (positivo se violação, 0 se viável)
    skipped_customer_ids: List[str] = field(default_factory=list)  # Clientes não visitados (ex.: impossíveis por bateria)
    
    def __post_init__(self):
        """Calcula métricas finais"""
        self.total_vehicles = len(self.routes)
        self.total_distance = sum(route.total_distance for route in self.routes)
        # total_cost e avg_dissatisfaction serão calculados no decoder após ter todos os dados
    
    def calculate_objectives(self, context: 'Context'):
        """
        Calcula os objetivos finais (custo e insatisfação).
        Deve ser chamado após todas as rotas estarem completas.
        """
        # Calcula custo total: (Nveic * CustoVeic) + (Disttotal * CustoDist)
        self.total_cost = (self.total_vehicles * context.vehicle_cost) + (self.total_distance * context.distance_cost)
        
        # Calcula satisfação média: atendidos contribuem com seu score; não atendidos (skipped) = 0
        customer_satisfactions = []
        for route in self.routes:
            for step in route.steps:
                if step.node.type == NodeType.CUSTOMER:
                    customer_satisfactions.append(step.satisfaction_score)
        n_total = len(context.customers)
        if n_total > 0:
            avg_satisfaction = sum(customer_satisfactions) / n_total  # não atendidos contam como 0
            self.avg_dissatisfaction = 1.0 - avg_satisfaction
        else:
            self.avg_dissatisfaction = 1.0
    
    def calculate_battery_violation(self, context: 'Context'):
        """
        Calcula a violação de bateria (G2) como déficit de energia.
        Retorna valor positivo se há violação, 0 se viável.
        
        Args:
            context: Contexto com parâmetros do problema
        
        Returns:
            Déficit de bateria (energia requerida - energia disponível)
        """
        total_deficit = 0.0
        
        for route in self.routes:
            current_battery = context.battery_capacity
            current_position = context.depot
            
            for step in route.steps:
                if step.node == context.depot and step != route.steps[0]:
                    # Retorno ao depósito - recarrega
                    current_battery = context.battery_capacity
                    current_position = context.depot
                    continue
                
                # Calcula energia necessária para chegar ao próximo nó
                distance = current_position.distance_to(step.node)
                energy_needed = distance * context.consumption_rate
                
                # Verifica se tem bateria suficiente
                if current_battery < energy_needed:
                    # Violação: déficit de energia
                    deficit = energy_needed - current_battery
                    total_deficit += deficit
                    current_battery = 0.0  # Continua com bateria zerada
                else:
                    current_battery -= energy_needed
                
                # Se for estação, recarrega
                if step.node.type == NodeType.STATION and step.recharge_amount > 0:
                    current_battery = min(context.battery_capacity, current_battery + step.recharge_amount)
                
                current_position = step.node
        
        self.battery_violation = total_deficit
        return total_deficit
    
    def add_violation(self, message: str):
        """Registra uma violação física (bateria/carga) - violações de tempo não marcam como inviável"""
        # Apenas violações físicas (bateria/carga) marcam como inviável
        # Violações de tempo são tratadas via satisfação
        if "Bateria" in message or "carga" in message.lower():
            self.is_feasible = False
        self.violations.append(message)
