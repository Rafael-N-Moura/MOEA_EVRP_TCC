#!/usr/bin/env python3
import sys, os
import numpy as np

sys.path.insert(0, '/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC')

from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.moo.sms import SMSEMOA
from pymoo.optimize import minimize
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation

from src import parse_instance, EVRPTWProblem, TWBiasedSampling

def run_and_save(alg_name, alg_class, instance_path, out_csv):
    print(f"Rodando {alg_name} (100k avaliações, sem busca local)...")
    ctx = parse_instance(instance_path)
    prob = EVRPTWProblem(ctx, k_max=0)
    
    alg = alg_class(
        pop_size=100,
        sampling=TWBiasedSampling(),
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
        eliminate_duplicates=True
    )
    
    res = minimize(prob, alg, ("n_eval", 100000), verbose=False, seed=42)
    
    cv_arr = res.pop.get("_cv")
    if cv_arr is None:
        cv_arr = res.pop.get("CV")
        
    F_real = res.pop.get("_F_real")
    if F_real is None:
        # fallback to basic F if problem didn't inject F_real
        F_real = res.pop.get("F")
        
    feas_idx = np.where(cv_arr[:, 0] <= 1e-9)[0]
    if len(feas_idx) > 0:
        F_feas = F_real[feas_idx]
        
        from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting
        I = NonDominatedSorting().do(F_feas, only_non_dominated_front=True)
        F_pareto = F_feas[I]
        
        sorted_idx = np.lexsort((F_pareto[:, 1], F_pareto[:, 0]))
        F_pareto = F_pareto[sorted_idx]
        
        with open(out_csv, "w") as f:
            f.write("f1,f2,f3\n")
            for row in F_pareto:
                f.write(f"{int(row[0])},{row[1]:.6f},{row[2]:.6f}\n")
        print(f"✅ Frente {alg_name} salva perfeitamente em: {out_csv} com {len(F_pareto)} soluções Pareto-ótimas.")
    else:
        print(f"❌ {alg_name}: 0 soluções viáveis encontradas!")

if __name__ == "__main__":
    inst = "/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/evrptw_instances/r201_21.txt"
    nsga2_csv = "/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/results/pareto_front_r201_21_nsga2_no_ls_100k_3obj.csv"
    sms_csv = "/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/results/pareto_front_r201_21_smsemoa_no_ls_100k_3obj.csv"
    
    run_and_save("NSGA-II", NSGA2, inst, nsga2_csv)
    run_and_save("SMS-EMOA", SMSEMOA, inst, sms_csv)
