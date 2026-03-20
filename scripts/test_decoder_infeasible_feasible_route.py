"""
Teste de sanidade do decoder_infeasible: rota curta manualmente factível.
Constrói uma instância mínima (depósito, 1 estação, 3 clientes próximos),
uma ordem de visita que sabemos ser factível, e verifica cv_energia=0 e cv_tw=0.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.model import Node, NodeType, Context
from src.decoder_infeasible import decode_infeasible


def make_feasible_test_context() -> Context:
    """
    Instância mínima onde uma rota depot -> C0 -> C1 -> C2 -> depot é factível.
    - Todos os pontos alinhados no eixo x para contas simples.
    - Bateria e capacidade grandes; janelas largas; r=1, v=1.
    """
    depot = Node(
        id="D0",
        type=NodeType.DEPOT,
        x=0.0,
        y=0.0,
        demand=0.0,
        ready_time=0.0,
        due_date=500.0,
        service_time=0.0,
    )
    station = Node(
        id="S0",
        type=NodeType.STATION,
        x=25.0,
        y=0.0,
        demand=0.0,
        ready_time=0.0,
        due_date=500.0,
        service_time=0.0,
    )
    # Clientes próximos ao depósito: (5,0), (10,0), (15,0)
    c0 = Node(id="C0", type=NodeType.CUSTOMER, x=5.0,  y=0.0, demand=10.0, ready_time=0.0, due_date=400.0, service_time=5.0)
    c1 = Node(id="C1", type=NodeType.CUSTOMER, x=10.0, y=0.0, demand=10.0, ready_time=0.0, due_date=400.0, service_time=5.0)
    c2 = Node(id="C2", type=NodeType.CUSTOMER, x=15.0, y=0.0, demand=10.0, ready_time=0.0, due_date=400.0, service_time=5.0)

    return Context(
        depot=depot,
        stations=[station],
        customers=[c0, c1, c2],
        battery_capacity=50.0,   # distância total depot->C0->C1->C2->depot = 5+5+5+15 = 30
        vehicle_capacity=50.0,  # demanda total = 30
        consumption_rate=1.0,
        recharge_rate=1.0,
        velocity=1.0,
    )


def main():
    context = make_feasible_test_context()
    n = len(context.customers)

    # Ordem de visita: 0, 1, 2 (ao longo do eixo x, ida e volta curta)
    pi = [0, 1, 2]
    delta = [1.0] * n  # recarga total se precisar parar na estação

    sol = decode_infeasible(pi, delta, context)

    print("=== Teste: rota manualmente factível ===")
    print(f"  f1 (distância):     {sol.f1:.4f}")
    print(f"  f2 (folga norm.):  {sol.f2:.4f}")
    print(f"  cv_energia:        {sol.cv_energia:.4f}")
    print(f"  cv_tw:             {sol.cv_tw:.4f}")
    print(f"  n_rotas:           {len(sol.routes)}")

    ok = True
    if sol.cv_energia != 0:
        print(f"  ERRO: esperado cv_energia=0, obtido {sol.cv_energia}")
        ok = False
    if sol.cv_tw != 0:
        print(f"  ERRO: esperado cv_tw=0, obtido {sol.cv_tw}")
        ok = False
    if sol.f2 > 0:
        print(f"  AVISO: f2 deveria ser <= 0 (folga normalizada), obtido {sol.f2}")

    if ok:
        print("  Resultado: cv_energia=0 e cv_tw=0 — decoder reproduz factibilidade.")
    else:
        print("  Resultado: FALHA nos checks.")
        sys.exit(1)


if __name__ == "__main__":
    main()
