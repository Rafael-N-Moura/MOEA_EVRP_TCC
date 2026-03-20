"""
Carregamento de instancias EVRPTW no formato Schneider et al. (2014).
Produz EVRPInstance com matrizes pre-computadas de distancia, energia e tempo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np


@dataclass
class Node:
    node_id: int
    node_type: str          # 'd' (depot), 'f' (station), 'c' (customer)
    x: float
    y: float
    demand: float
    ready_time: float       # b_i: abertura da janela de tempo
    due_date: float         # e_i: fechamento da janela de tempo
    service_time: float     # s_i


@dataclass
class EVRPInstance:
    name: str
    nodes: List[Node]
    depot_id: int
    customer_ids: List[int]
    station_ids: List[int]
    Q: float                # capacidade de carga do veiculo
    B: float                # capacidade da bateria
    r: float                # taxa de consumo de energia por unidade de distancia
    v: float                # velocidade media
    g: float                # inverse refueling rate (tempo por unidade de energia)
    t_charge: float         # tempo MAXIMO de recarga (B * g, referencia)
    md: float               # maximum allowable delay (atraso toleravel antes de contar como violacao)

    dist: np.ndarray = field(repr=False)
    energy: np.ndarray = field(repr=False)
    travel_time: np.ndarray = field(repr=False)

    @property
    def n_customers(self) -> int:
        return len(self.customer_ids)

    @property
    def n_stations(self) -> int:
        return len(self.station_ids)

    @property
    def n_nodes(self) -> int:
        return len(self.nodes)


def load_schneider(filepath: str,
                   Q: Optional[float] = None,
                   B: Optional[float] = None,
                   r: Optional[float] = None,
                   v: Optional[float] = None,
                   g: Optional[float] = None,
                   t_charge: Optional[float] = None,
                   md: float = 0.0) -> EVRPInstance:
    """
    Carrega instancia no formato Schneider et al. (2014).

    Parametros do veiculo sao lidos do proprio arquivo. Valores passados
    explicitamente sobrescrevem os do arquivo (util para experimentos
    com variacao de B ou Q).
    """
    with open(filepath) as f:
        lines = f.readlines()

    nodes: List[Node] = []
    depot_id: Optional[int] = None
    customer_ids: List[int] = []
    station_ids: List[int] = []
    file_params: dict = {}

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('StringID'):
            continue

        param_match = re.search(r'/([\d.]+)/', stripped)
        if param_match:
            value = float(param_match.group(1))
            if stripped.startswith('Q'):
                file_params['B'] = value        # Q no arquivo = bateria
            elif stripped.startswith('C'):
                file_params['Q'] = value        # C no arquivo = carga
            elif stripped.startswith('r'):
                file_params['r'] = value
            elif stripped.startswith('g'):
                file_params['g'] = value
            elif stripped.startswith('v'):
                file_params['v'] = value
            continue

        parts = stripped.split()
        if len(parts) < 8:
            continue

        nid = len(nodes)
        ntype = parts[1]

        node = Node(
            node_id=nid,
            node_type=ntype,
            x=float(parts[2]),
            y=float(parts[3]),
            demand=float(parts[4]),
            ready_time=float(parts[5]),
            due_date=float(parts[6]),
            service_time=float(parts[7]),
        )
        nodes.append(node)

        if ntype == 'd':
            depot_id = nid
        elif ntype == 'c':
            customer_ids.append(nid)
        elif ntype == 'f':
            station_ids.append(nid)

    if depot_id is None:
        raise ValueError(f"Deposito nao encontrado em {filepath}")

    # Resolve parametros: argumento explicito > arquivo > default
    B_val = B if B is not None else file_params.get('B', 0.0)
    Q_val = Q if Q is not None else file_params.get('Q', 0.0)
    r_val = r if r is not None else file_params.get('r', 1.0)
    v_val = v if v is not None else file_params.get('v', 1.0)
    g_val = g if g is not None else file_params.get('g', 0.0)

    if t_charge is not None:
        t_charge_val = t_charge
        if t_charge_val == 0.0 and g is None:
            g_val = 0.0
    elif g_val > 0:
        t_charge_val = B_val * g_val
    else:
        t_charge_val = 0.0

    # Matrizes pre-computadas
    n = len(nodes)
    coords = np.array([[nd.x, nd.y] for nd in nodes])
    diff = coords[:, np.newaxis, :] - coords[np.newaxis, :, :]
    dist_matrix = np.sqrt((diff ** 2).sum(axis=2))
    energy_matrix = dist_matrix * r_val
    tt_matrix = dist_matrix / v_val if v_val > 0 else dist_matrix.copy()

    import os
    name = os.path.splitext(os.path.basename(filepath))[0]

    return EVRPInstance(
        name=name,
        nodes=nodes,
        depot_id=depot_id,
        customer_ids=customer_ids,
        station_ids=station_ids,
        Q=Q_val,
        B=B_val,
        r=r_val,
        v=v_val,
        g=g_val,
        t_charge=t_charge_val,
        md=md,
        dist=dist_matrix,
        energy=energy_matrix,
        travel_time=tt_matrix,
    )
