"""
Modelos de dados para o EVRPTW.

Node      – ponto no mapa (depósito, estação ou cliente)
Context   – instância carregada com matrizes de distância pré-computadas
"""

from dataclasses import dataclass
from enum import Enum
from typing import List

import numpy as np


class NodeType(Enum):
    DEPOT = 'd'
    STATION = 'f'
    CUSTOMER = 'c'


@dataclass(frozen=True)
class Node:
    """Ponto imutável no mapa (depósito, estação de recarga ou cliente)."""
    id: str
    type: NodeType
    x: float
    y: float
    demand: float
    ready_time: float
    due_date: float
    service_time: float

    def distance_to(self, other: 'Node') -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5


class Context:
    """
    Contexto completo de uma instância EVRPTW.

    Parâmetros (notação da especificação):
        Q = battery_capacity      capacidade da bateria
        C = vehicle_capacity      capacidade de carga do veículo
        r = consumption_rate      taxa de consumo de energia (proporcional à distância)
        g = recharge_rate         taxa inversa de recarga (tempo por unidade de energia)
        v = velocity              velocidade média

    Pré-computa:
        dist_matrix   – distância euclidiana entre todos os pares de nós
        travel_matrix – tempo de viagem  (dist / v)
    """

    def __init__(
        self,
        depot: Node,
        stations: List[Node],
        customers: List[Node],
        battery_capacity: float = 0.0,
        vehicle_capacity: float = 0.0,
        consumption_rate: float = 1.0,
        recharge_rate: float = 1.0,
        velocity: float = 1.0,
    ):
        self.depot = depot
        self.stations = list(stations)
        self.customers = list(customers)
        self.battery_capacity = battery_capacity
        self.vehicle_capacity = vehicle_capacity
        self.consumption_rate = consumption_rate
        self.recharge_rate = recharge_rate
        self.velocity = velocity
        self.n_customers = len(customers)

        # Vetor ordenado: [depot, estações..., clientes...]
        self.all_nodes: List[Node] = [depot] + self.stations + self.customers
        self.n_nodes = len(self.all_nodes)

        # Faixas de índice dentro de all_nodes
        self.depot_idx = 0
        self._station_start = 1
        self._customer_start = 1 + len(self.stations)

        # Índices de estações válidas para inserção (exclui S0, mesma posição do depot)
        self.valid_station_indices: List[int] = [
            self._station_start + i
            for i, s in enumerate(self.stations)
            if s.id != "S0"
        ]

        # Mapa: posição do cliente (0..n-1) → índice em all_nodes
        self.customer_node_indices: List[int] = list(range(
            self._customer_start,
            self._customer_start + self.n_customers,
        ))

        self._precompute_matrices()
        self._check_reachability()

    # ------------------------------------------------------------------
    def _precompute_matrices(self):
        coords = np.array([(n.x, n.y) for n in self.all_nodes])
        diff = coords[:, np.newaxis, :] - coords[np.newaxis, :, :]
        self.dist_matrix: np.ndarray = np.sqrt((diff ** 2).sum(axis=2))
        self.travel_matrix: np.ndarray = self.dist_matrix / self.velocity

    def _check_reachability(self):
        Q, r, d = self.battery_capacity, self.consumption_rate, self.depot_idx
        for i, cidx in enumerate(self.customer_node_indices):
            e_out = self.dist_matrix[d, cidx] * r
            e_back = self.dist_matrix[cidx, d] * r
            if e_out > Q:
                raise ValueError(
                    f"Cliente {self.customers[i].id} inalcançável com bateria cheia "
                    f"(energia={e_out:.2f} > Q={Q})")
            if e_back > Q:
                raise ValueError(
                    f"Cliente {self.customers[i].id} não retorna ao depot "
                    f"(energia={e_back:.2f} > Q={Q})")
