#!/usr/bin/env python3
import sys, os, csv, time
sys.path.insert(0, '/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC')

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.moo.moead import MOEAD
from pymoo.algorithms.moo.sms import SMSEMOA
from pymoo.util.ref_dirs import get_reference_directions
from pymoo.optimize import minimize
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation
from pymoo.core.callback import Callback

from src import parse_instance, EVRPTWProblem, TWBiasedSampling

class CSVTracker(Callback):
    def __init__(self, alg_name, csv_writer):
        super().__init__()
        self.alg_name = alg_name
        self.csv_writer = csv_writer

    def notify(self, algorithm):
        n_eval = algorithm.evaluator.n_eval
        cv_arr = algorithm.pop.get("_cv")
        F_real = algorithm.pop.get("_F_real")
        if cv_arr is None or F_real is None:
            return
            
        mask = cv_arr[:, 0] <= 1e-9
        n_feas = int(mask.sum())
        min_cv = float(cv_arr[:, 0].min())
        
        gen = algorithm.n_gen
        
        if n_feas > 0:
            best_f1 = F_real[mask, 0].min()
            best_f2 = F_real[mask, 1].min()
            best_f3 = F_real[mask, 2].min()
            mean_f1 = F_real[mask, 0].mean()
            mean_f2 = F_real[mask, 1].mean()
            mean_f3 = F_real[mask, 2].mean()
            
            self.csv_writer.writerow([
                self.alg_name, gen, n_eval, n_feas,
                f"{best_f1:.4f}", f"{best_f2:.4f}", f"{best_f3:.4f}",
                f"{mean_f1:.4f}", f"{mean_f2:.4f}", f"{mean_f3:.4f}",
                f"{min_cv:.6f}"
            ])
        else:
            self.csv_writer.writerow([
                self.alg_name, gen, n_eval, n_feas,
                "","","", "","","",
                f"{min_cv:.6f}"
            ])

def run_experiment_for_instance(instance_name):
    instance_path = f"/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/evrptw_instances/{instance_name}.txt"
    out_csv = f"/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/results/convergence_log_{instance_name}_no_ls_100k_3obj.csv"
    
    ctx = parse_instance(instance_path)
    prob = EVRPTWProblem(ctx, k_max=0)
    
    with open(out_csv, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["algorithm","generation","n_eval","n_feasible","best_f1","best_f2","best_f3","mean_f1_feas","mean_f2_feas","mean_f3_feas","min_cv_pop"])
        
        alg_nsga2 = NSGA2(pop_size=100, sampling=TWBiasedSampling(), crossover=OrderCrossover(), mutation=InversionMutation(), eliminate_duplicates=True)
        print(f"[{time.strftime('%H:%M:%S')}] Iniciando NSGA2 em {instance_name}...")
        minimize(prob, alg_nsga2, ("n_eval", 100000), callback=CSVTracker("NSGA-II", writer), verbose=False, seed=42)
        
        ref_dirs = get_reference_directions("das-dennis", 3, n_partitions=13)
        alg_moead = MOEAD(ref_dirs, n_neighbors=20, prob_neighbor_mating=0.7, sampling=TWBiasedSampling(), crossover=OrderCrossover(), mutation=InversionMutation())
        print(f"[{time.strftime('%H:%M:%S')}] Iniciando MOEA/D em {instance_name}...")
        minimize(prob, alg_moead, ("n_eval", 100000), callback=CSVTracker("MOEA/D", writer), verbose=False, seed=42)
        
        alg_sms = SMSEMOA(pop_size=100, sampling=TWBiasedSampling(), crossover=OrderCrossover(), mutation=InversionMutation(), eliminate_duplicates=True)
        print(f"[{time.strftime('%H:%M:%S')}] Iniciando SMS-EMOA em {instance_name}...")
        minimize(prob, alg_sms, ("n_eval", 100000), callback=CSVTracker("SMS-EMOA", writer), verbose=False, seed=42)
        
    print(f"[{time.strftime('%H:%M:%S')}] CSV de {instance_name} finalizado em {out_csv}!")

if __name__ == "__main__":
    os.makedirs("/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/results", exist_ok=True)
    run_experiment_for_instance("c101_21")
    run_experiment_for_instance("r201_21")
