#!/usr/bin/env python3
import sys, os, glob
import numpy as np
import multiprocessing as mp

sys.path.insert(0, '/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC')

from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation

from src import parse_instance, EVRPTWProblem, TWBiasedSampling

def run_single_instance(args):
    inst_path, seed = args
    inst_name = os.path.basename(inst_path)
    ctx = parse_instance(inst_path)
    prob = EVRPTWProblem(ctx, k_max=0)
    
    alg = NSGA2(
        pop_size=50,
        sampling=TWBiasedSampling(),
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
        eliminate_duplicates=False
    )
    
    res = minimize(prob, alg, ("n_eval", 25000), verbose=False, seed=seed)
    
    cv_arr = res.pop.get("_cv")
    if cv_arr is None:
        cv_arr = res.pop.get("CV")
        
    F_real = res.pop.get("_F_real")
    if F_real is None:
        F_real = res.pop.get("F")
        
    feas_idx = np.where(cv_arr[:, 0] <= 1e-9)[0]
    best_sol = None
    
    if len(feas_idx) > 0:
        F_feas = F_real[feas_idx]
        
        # Minimizar f3 primeiro, depois f1, depois f2
        sorted_idx = np.lexsort((F_feas[:, 1], F_feas[:, 0], F_feas[:, 2]))
        best_sol = F_feas[sorted_idx[0]]
        
    return inst_name, seed, best_sol

def main():
    base_dir = "/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/evrptw_instances"
    small_files = glob.glob(os.path.join(base_dir, "*C*.txt"))
    small_files = [f for f in small_files if os.path.isfile(f) and not f.endswith("all_instances_bundle.txt")]
    
    print(f"Encontradas {len(small_files)} instâncias pequenas.")
    
    tasks = []
    seeds = [42, 43, 44, 45, 46]
    for f in small_files:
        for seed in seeds:
            tasks.append((f, seed))
            
    results = {}
    print(f"Iniciando {len(tasks)} execuções com 50.000 avaliações cada usando Multiprocessing...")
    
    with mp.Pool(mp.cpu_count()) as pool:
        for i, (inst_name, seed, best_sol) in enumerate(pool.imap_unordered(run_single_instance, tasks)):
            if inst_name not in results:
                results[inst_name] = []
            results[inst_name].append(best_sol)
            if (i+1) % 36 == 0:
                print(f" Completados {i+1}/{len(tasks)} execuções...")
                
    print("\n\n=== RESULTADOS: MELHOR SOLUÇÃO F3=0 (ou mínimo f3) POR INSTÂNCIA ===")
    final_output = []
    for inst_name in sorted(results.keys()):
        sols = [s for s in results[inst_name] if s is not None]
        if len(sols) == 0:
            final_output.append(f"{inst_name}: Nenhuma solução viável encontrada.")
            continue
            
        sols = np.array(sols)
        sorted_idx = np.lexsort((sols[:, 1], sols[:, 0], sols[:, 2]))
        best = sols[sorted_idx[0]]
        
        final_output.append(f"{inst_name:15s} | f1={int(best[0]):2d} veículos | f2={best[1]:8.2f} dist | f3={best[2]:8.2f} atraso")
        
    for line in final_output:
        print(line)
        
    with open("/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/results/best_small_instances.txt", "w") as f:
        f.write("\n".join(final_output))

if __name__ == "__main__":
    main()
