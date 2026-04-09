#!/usr/bin/env python3
import sys, os, time
import numpy as np

sys.path.insert(0, '/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC')

from src import parse_instance, Decoder
from tests.test_relaxed_split import IndependentAuditor

def run_auditor_test(instance_path, n_perms=1000, n_det=100):
    print(f"\n=============================================")
    print(f" Validando Auditor em {os.path.basename(instance_path)}")
    print(f"=============================================")
    
    ctx = parse_instance(instance_path)
    dec = Decoder(ctx)
    auditor = IndependentAuditor(ctx)
    
    n_cust = ctx.n_customers
    
    # 1. Testar 1000 permutações aleatórias
    np.random.seed(42)
    print(f" Testando {n_perms} permutações aleatórias...")
    discrepancies = 0
    t0 = time.time()
    
    for i in range(n_perms):
        perm = np.random.permutation(n_cust)
        F, cv, expanded = dec.decode_detailed(perm)
        
        ok, viols, a_f1, a_f2, a_f3 = auditor.audit_solution(expanded)
        
        match_f1 = abs(F[0] - a_f1) < 1e-6
        match_f2 = abs(F[1] - a_f2) < 1e-6
        match_f3 = abs(F[2] - a_f3) < 1e-5
        
        # Filtra as violações 'soft' de janela de tempo
        hard_viols = [v for v in viols if "TW violada" not in v]
        
        if cv == 0.0 and len(hard_viols) > 0:
            print(f"  [DISCREPÂNCIA HARD] cv decodificador = 0.0, MAS auditor detectou falhas:")
            for v in hard_viols: print(f"     -> {v}")
            discrepancies += 1
            
        if not match_f1 or not match_f2 or not match_f3:
            print(f"  [DISCREPÂNCIA OBJETIVOS] P: {perm[:5]}...")
            print(f"     Decodificador: f1={F[0]:.2f}, f2={F[1]:.2f}, f3={F[2]:.2f}")
            print(f"     Auditor:       f1={a_f1:.2f}, f2={a_f2:.2f}, f3={a_f3:.2f}")
            discrepancies += 1
            
    print(f"  Concluído em {time.time() - t0:.2f}s. Discrepâncias encontradas: {discrepancies}")
    
    # 2. Testar determinismo
    print(f" Testando determinismo ({n_det} permutações repetidas 3 vezes)...")
    det_fails = 0
    t1 = time.time()
    for i in range(n_det):
        perm = np.random.permutation(n_cust)
        F1, cv1, exp1 = dec.decode_detailed(perm)
        F2, cv2, exp2 = dec.decode_detailed(perm)
        F3, cv3, exp3 = dec.decode_detailed(perm)
        
        if not np.allclose(F1, F2) or not np.allclose(F1, F3):
            det_fails += 1
            print(f"  [FALHA DETERMINISMO f] na perm {i}")
        if cv1 != cv2 or cv1 != cv3:
            det_fails += 1
            print(f"  [FALHA DETERMINISMO cv] na perm {i}")
        if exp1 != exp2 or exp1 != exp3:
            det_fails += 1
            print(f"  [FALHA DETERMINISMO exp] na perm {i}")
            
    print(f"  Concluído em {time.time() - t1:.2f}s. Falhas de determinismo: {det_fails}")
    
    if discrepancies == 0 and det_fails == 0:
        print("  ✅ CRITÉRIO DE PASSAGEM ATINGIDO: Zero discrepâncias. Determinismo 100%.")
    else:
        print("  ❌ FALHOU NOS CRITÉRIOS!")

if __name__ == "__main__":
    run_auditor_test("/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/evrptw_instances/c101_21.txt", 1000, 100)
    run_auditor_test("/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/evrptw_instances/r201_21.txt", 1000, 100)
