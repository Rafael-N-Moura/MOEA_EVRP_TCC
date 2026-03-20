"""
Representacao de solucoes do EVRP.

Hierarquia: Solution > Route > Visit, com Segment para trechos deficientes
e CVVector para o vetor de violacao multidimensional.

Todos os campos necessarios para o IAS-EVRP completo estao presentes desde
o inicio; o NSGA-II da Fase 1 simplesmente nao usa todos eles.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional

from .instance import EVRPInstance


class NodeType(Enum):
    DEPOT = auto()
    CUSTOMER = auto()
    STATION = auto()


class InfeasType(Enum):
    FEASIBLE = auto()
    IES = auto()        # Inviabilidade Energetica Simples
    IEC = auto()        # Inviabilidade Energetica Cascata
    IC = auto()         # Inviabilidade de Capacidade
    IJT = auto()        # Inviabilidade de Janela de Tempo
    IM = auto()         # Inviabilidade Mista


NODE_TYPE_MAP = {'d': NodeType.DEPOT, 'f': NodeType.STATION, 'c': NodeType.CUSTOMER}


@dataclass
class Visit:
    node_id: int
    node_type: NodeType
    arrival_energy: float = 0.0
    departure_energy: float = 0.0
    arrival_time: float = 0.0
    service_start: float = 0.0
    departure_time: float = 0.0
    waiting_time: float = 0.0
    delay_time: float = 0.0


@dataclass
class Segment:
    """Trecho deficiente entre dois nos consecutivos da rota."""
    from_idx: int
    to_idx: int
    energy_consumed: float
    energy_deficit: float
    min_insert_cost: Optional[float] = None     # lazy: EOC calcula na Fase 2


@dataclass
class CVVector:
    """Vetor de violacao de restricoes, normalizado pela populacao."""
    cv_energy: float = 0.0
    cv_cascade: float = 0.0
    cv_cap: float = 0.0
    cv_tw: float = 0.0

    def total(self) -> float:
        """Escalar agregado usado pelo CDP."""
        return self.cv_energy + self.cv_cascade + self.cv_cap + self.cv_tw

    def is_feasible(self, tol: float = 1e-9) -> bool:
        return self.total() < tol


@dataclass
class SolutionMetadata:
    n_vehicles: int = 0
    total_distance: float = 0.0
    makespan: float = 0.0
    total_waiting: float = 0.0
    total_delay: float = 0.0
    inf_type: InfeasType = InfeasType.FEASIBLE
    corrected_obj: Optional[list] = None    # f_hat: preenchido pelo EOC (Fase 2)


@dataclass
class Route:
    visits: List[Visit] = field(default_factory=list)
    energy_profile: List[float] = field(default_factory=list)
    time_profile: List[float] = field(default_factory=list)
    deficient_segments: List[Segment] = field(default_factory=list)
    cv_route: CVVector = field(default_factory=CVVector)

    _raw_energy: float = 0.0
    _raw_cascade: float = 0.0
    _raw_cap: float = 0.0
    _raw_tw: float = 0.0

    def n_customers(self) -> int:
        return sum(1 for v in self.visits if v.node_type == NodeType.CUSTOMER)

    def n_stations(self) -> int:
        return sum(1 for v in self.visits if v.node_type == NodeType.STATION)

    def customer_ids(self) -> List[int]:
        return [v.node_id for v in self.visits if v.node_type == NodeType.CUSTOMER]


@dataclass
class Solution:
    routes: List[Route] = field(default_factory=list)
    metadata: SolutionMetadata = field(default_factory=SolutionMetadata)
    cv_components: CVVector = field(default_factory=CVVector)

    _raw_energy: float = 0.0
    _raw_cascade: float = 0.0
    _raw_cap: float = 0.0
    _raw_tw: float = 0.0
    _dirty: bool = True

    def objectives_3(self) -> List[float]:
        """Retorna [f1, f2, f3] para o Problem com 3 objetivos."""
        m = self.metadata
        return [float(m.n_vehicles), m.total_distance, m.makespan]

    def objectives_5(self) -> List[float]:
        """Retorna [f1, f2, f3, f4, f5] completo."""
        m = self.metadata
        return [float(m.n_vehicles), m.total_distance, m.makespan,
                m.total_waiting, m.total_delay]

    def all_customers(self) -> List[int]:
        result = []
        for r in self.routes:
            result.extend(r.customer_ids())
        return result

    def copy(self) -> Solution:
        return copy.deepcopy(self)


def check_invariants(sol: Solution, instance: EVRPInstance) -> None:
    """
    Verifica invariantes I1-I3. Lanca AssertionError se algum for violado.
    Usar em testes; desabilitar em producao.
    """
    all_customers = []

    for route in sol.routes:
        assert route.visits, 'Rota vazia'
        # I2: rota comeca e termina no deposito
        assert route.visits[0].node_type == NodeType.DEPOT, \
            f'I2: primeiro no nao e deposito (node_id={route.visits[0].node_id})'
        assert route.visits[-1].node_type == NodeType.DEPOT, \
            f'I2: ultimo no nao e deposito (node_id={route.visits[-1].node_id})'
        # I2: deposito nao aparece no meio
        for v in route.visits[1:-1]:
            assert v.node_type != NodeType.DEPOT, \
                f'I2: deposito no meio da rota (node_id={v.node_id})'
        # I1: acumula clientes
        for v in route.visits:
            if v.node_type == NodeType.CUSTOMER:
                all_customers.append(v.node_id)

    # I1: cada cliente exatamente uma vez
    assert sorted(all_customers) == sorted(instance.customer_ids), \
        f'I1: cobertura invalida. esperados={sorted(instance.customer_ids)}, obtidos={sorted(all_customers)}'
    assert len(all_customers) == len(set(all_customers)), 'I1: cliente duplicado'
