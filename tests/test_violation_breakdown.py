#!/usr/bin/env python3
"""
Relatório de Violações Iniciais (Bateria vs Janela de Tempo).
Gera N permutações aleatórias e passa pelo Split Relaxado, contabilizando a fonte primária da inviabilidade.
"""

import sys, os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import parse_instance, Decoder

def main():
    print("=" * 80)
    print("  RELATÓRIO DE INVIABILIDADE INICIAL: BATERIA vs TEMPO")
    print("  Decoder: Split Relaxado (Sem Local Search)")
    print("=" * 80)

    # Testaremos as duas instâncias para conferir a diferença
    instances = ["evrptw_instances/c101_21.txt", "evrptw_instances/r201_21.txt"]
    N_SAMPLES = 500  # Quantidade de permutações aleatórias analisadas por instância

    for path in instances:
        inst_name = os.path.basename(path).replace(".txt", "")
        ctx = parse_instance(path)
        decoder = Decoder(ctx, k_max=0)
        
        n_viable = 0
        n_only_tw = 0
        n_only_bat = 0
        n_both = 0
        
        avg_tw_violation = 0.0
        avg_bat_violation = 0.0

        for seed in range(N_SAMPLES):
            np.random.seed(seed)
            perm = np.random.permutation(ctx.n_customers)
            
            # _split retorna uma lista de listas com os nos dos clientes em rotas baseadas na cap
            routes = decoder._split(perm)
            
            total_tw = 0.0
            total_bat = 0.0
            
            for route_cust in routes:
                _, tw_v, bat_v = decoder._insert_stations(route_cust)
                total_tw += tw_v
                total_bat += bat_v
                
            if total_tw <= 1e-9 and total_bat <= 1e-9:
                n_viable += 1
            elif total_tw > 1e-9 and total_bat <= 1e-9:
                n_only_tw += 1
            elif total_bat > 1e-9 and total_tw <= 1e-9:
                n_only_bat += 1
            else:
                n_both += 1
                
            avg_tw_violation += total_tw
            avg_bat_violation += total_bat

        avg_tw_violation /= N_SAMPLES
        avg_bat_violation /= N_SAMPLES
        total_infeasible = n_only_tw + n_only_bat + n_both

        print(f"\n[Instância: {inst_name}] — {N_SAMPLES} Permutações Aleatórias")
        print(f"Total Viáveis   : {n_viable}")
        print(f"Total Inviáveis : {total_infeasible}")
        print(f"   ↳ Só p/ Tempo  : {n_only_tw} ({(n_only_tw/N_SAMPLES)*100:.1f}%)")
        print(f"   ↳ Só p/ Bateria: {n_only_bat} ({(n_only_bat/N_SAMPLES)*100:.1f}%)")
        print(f"   ↳ Por AMBOS    : {n_both} ({(n_both/N_SAMPLES)*100:.1f}%)")
        
        print(f"Média Absoluta de Atraso de TW (tw_v) : {avg_tw_violation:.1f} unidades de tempo p/ sol.")
        print(f"Média Absoluta de Déficit de Bat (bat_v): {avg_bat_violation:.1f} kw p/ sol.")

if __name__ == "__main__":
    main()
