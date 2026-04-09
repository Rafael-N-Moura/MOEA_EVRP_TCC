#!/usr/bin/env python3
"""
Checa se todas as 500 permutações aleatórias tinham saltos diretos entre 
dois pontos consecutivos maiores que a capacidade baterica do veículo.
E checa também os triângulos: se tem saltos onde (A -> Estação -> B) todos custam > Q.
"""

import sys, os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import parse_instance, Decoder

def main():
    ctx = parse_instance("evrptw_instances/c101_21.txt")
    decoder = Decoder(ctx, k_max=0)
    N = 500

    count_permutation_with_impossible_jump = 0
    count_permutation_with_unrecoverable_jump = 0

    for seed in range(N):
        np.random.seed(seed)
        perm = np.random.permutation(ctx.n_customers)
        routes = decoder._split(perm)
        
        has_impossible_jump = False
        has_unrecoverable_jump = False
        
        for route_cust in routes:
            prev = ctx.depot_idx
            for cust_idx in route_cust:
                real_node = ctx.customer_node_indices[cust_idx - 1]
                dist = ctx.dist_matrix[prev, real_node]
                energia = dist * ctx.consumption_rate
                
                if energia > ctx.battery_capacity:
                    has_impossible_jump = True
                    
                    # Vamos ver se dá pra salvar com um posto (Station)
                    # Dá pra salvar se existir um posto "s" tal que 
                    # Dist(prev, s) <= Q  E  Dist(s, real_node) <= Q
                    can_recover = False
                    for i in range(len(ctx.stations)):
                        s_idx = ctx._station_start + i
                        dist_ida = ctx.dist_matrix[prev, s_idx] * ctx.consumption_rate
                        dist_volta = ctx.dist_matrix[s_idx, real_node] * ctx.consumption_rate
                        if dist_ida <= ctx.battery_capacity and dist_volta <= ctx.battery_capacity:
                            can_recover = True
                            break
                    if not can_recover:
                        has_unrecoverable_jump = True
                        
                prev = real_node
                
            dist_ret = ctx.dist_matrix[prev, ctx.depot_idx]
            energia_ret = dist_ret * ctx.consumption_rate
            if energia_ret > ctx.battery_capacity:
                has_impossible_jump = True
                
                can_recover = False
                for i in range(len(ctx.stations)):
                    s_idx = ctx._station_start + i
                    dist_ida = ctx.dist_matrix[prev, s_idx] * ctx.consumption_rate
                    dist_volta = ctx.dist_matrix[s_idx, ctx.depot_idx] * ctx.consumption_rate
                    if dist_ida <= ctx.battery_capacity and dist_volta <= ctx.battery_capacity:
                        can_recover = True
                        break
                if not can_recover:
                    has_unrecoverable_jump = True

        if has_impossible_jump:
            count_permutation_with_impossible_jump += 1
        if has_unrecoverable_jump:
            count_permutation_with_unrecoverable_jump += 1

    print("="*60)
    print(f"ANÁLISE DOS SALTOS NAS 500 PERMUTAÇÕES (Instância: c101_21)")
    print(f"Capacidade de Bateria (Q): {ctx.battery_capacity:.2f}")
    print("="*60)
    print(f"Permutações c/ no mínimo UM salto direto > Q   : {count_permutation_with_impossible_jump}/{N}")
    print(f"Destas, permutações que NENHUMA ESTAÇÃO salva  : {count_permutation_with_unrecoverable_jump}/{N}")

if __name__ == "__main__":
    main()
