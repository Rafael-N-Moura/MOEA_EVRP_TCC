#!/usr/bin/env python3
"""
Mostra detalhes de uma rota inicial gerada aleatoriamente
usando o Split Relaxado para evidenciar os saltos geográficos.
"""

import sys, os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import parse_instance, Decoder

def main():
    ctx = parse_instance("evrptw_instances/c101_21.txt")
    decoder = Decoder(ctx, k_max=0)
    
    np.random.seed(42)  # Fixar semente para reprodutibilidade
    perm = np.random.permutation(ctx.n_customers)
    
    print("=" * 80)
    print(f"  EXEMPLO DE ROTA ALEATÓRIA VIA SPLIT RELAXADO (c101_21)")
    print(f"  Capacidade Bateria (Q): {ctx.battery_capacity:.1f}")
    print("=" * 80)

    routes = decoder._split(perm)
    
    rotas_mostradas = 0
    for i, route_cust in enumerate(routes, 1):
        _, tw_v, bat_v = decoder._insert_stations(route_cust)
        
        # Só vamos mostrar se tiver violação de bateria pra exemplificar os grandes saltos
        if bat_v <= 1e-9:
            continue
            
        rotas_mostradas += 1
        print(f"\n[Rota {i}]")
        
        seq_str = " -> ".join(f"C{c}" for c in route_cust)
        print(f"Sequência: Depot -> {seq_str} -> Depot")
        carga = sum(ctx.all_nodes[ctx.customer_node_indices[c-1]].demand for c in route_cust)
        print(f"Carga: {carga:.1f} / {ctx.vehicle_capacity}")
        
        print("Saltos Geográficos Diretos (Se não houvesse estação intermerdiária):")
        prev = ctx.depot_idx
        for step, cust_idx in enumerate(route_cust, 1):
            real_node = ctx.customer_node_indices[cust_idx - 1]
            dist = ctx.dist_matrix[prev, real_node]
            energia_gasta = dist * ctx.consumption_rate
            
            orig_name = "Depot" if prev == ctx.depot_idx else f"C{ctx.customer_node_indices.index(prev)+1}"
            dest_name = f"C{cust_idx}"
            
            alert = ""
            if energia_gasta > ctx.battery_capacity:
                alert = f" [!!! SALTO IMPOSSÍVEL !!! Bat. Max é {ctx.battery_capacity:.1f}]"
            elif energia_gasta > (ctx.battery_capacity * 0.7):
                alert = " [(Consome >70% da bateria num salto)]"
                
            print(f"  {step}. {orig_name:>5} -> {dest_name:<5} | Dist: {dist:>5.1f} | Gasta: {energia_gasta:>5.1f} kWh {alert}")
            prev = real_node
            
        dist_ret = ctx.dist_matrix[prev, ctx.depot_idx]
        energia_ret = dist_ret * ctx.consumption_rate
        orig_name = f"C{ctx.customer_node_indices.index(prev)+1}"
        alert_ret = ""
        if energia_ret > ctx.battery_capacity:
            alert_ret = f" [!!! SALTO IMPOSSÍVEL !!! Bat. Max é {ctx.battery_capacity:.1f}]"
        print(f"  R. {orig_name:>5} -> Depot | Dist: {dist_ret:>5.1f} | Gasta: {energia_ret:>5.1f} kWh {alert_ret}")
        
        print(f"\n=> Veredito Final da _insert_stations() (que tentou achar estações):")
        print(f"   Atraso Acumulado de TW (tw_v) : {tw_v:.1f} m")
        print(f"   Falta Acumulada de Bat (bat_v): {bat_v:.1f} kW -> (Essa rota o caminhão enguiça)")
        print("-" * 80)
        
        if rotas_mostradas >= 2:
            break

if __name__ == "__main__":
    main()
