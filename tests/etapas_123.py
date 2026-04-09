#!/usr/bin/env python3
import sys, os, time, json
import numpy as np
import matplotlib.pyplot as plt
import multiprocessing as mp
from scipy.stats import kruskal

sys.path.insert(0, '/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC')

from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.moo.moead import MOEAD
from pymoo.algorithms.moo.sms import SMSEMOA
from pymoo.util.ref_dirs import get_reference_directions
from pymoo.optimize import minimize
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation
from pymoo.core.callback import Callback
from pymoo.indicators.hv import HV

from src import parse_instance, EVRPTWProblem, TWBiasedSampling, Decoder
from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting
from tests.test_relaxed_split import IndependentAuditor

LOG_FILE = "/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/results/master_validation.log"

def log(msg):
    print(msg)
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")

# =========================================================
# ETAPA 1
# =========================================================

class HVTracker(Callback):
    def __init__(self, step=5000):
        super().__init__()
        self.step = step
        self.next_eval = step
        self.history = [] 

    def notify(self, algorithm):
        n_eval = algorithm.evaluator.n_eval
        if n_eval >= self.next_eval:
            cv_arr = algorithm.pop.get("_cv")
            F_real = algorithm.pop.get("_F_real")
            
            mask = ()
            if cv_arr is not None and F_real is not None:
                mask = cv_arr[:, 0] <= 1e-9
            
            if len(mask) > 0 and mask.sum() > 0:
                F_feas = F_real[mask]
                I = NonDominatedSorting().do(F_feas, only_non_dominated_front=True)
                front = F_feas[I].tolist()
                self.history.append((n_eval, front))
            else:
                self.history.append((n_eval, []))
            
            while self.next_eval <= n_eval:
                self.next_eval += self.step

def run_etapa1_single(args):
    inst_path, seed, max_eval = args
    ctx = parse_instance(inst_path)
    prob = EVRPTWProblem(ctx, k_max=0)
    
    cb = HVTracker(5000)
    alg = NSGA2(
        pop_size=100,
        sampling=TWBiasedSampling(),
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
        eliminate_duplicates=True
    )
    
    minimize(prob, alg, ("n_eval", max_eval), callback=cb, verbose=False, seed=seed)
    return os.path.basename(inst_path), seed, cb.history

def etapa_1():
    log("\n" + "="*50)
    log(" ETAPA 1: Convergência NSGA-II")
    log("="*50)
    
    instances = ["/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/evrptw_instances/c101_21.txt", 
                 "/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/evrptw_instances/r201_21.txt"]
    seeds = [42, 43, 44, 45, 46]
    max_eval = 500000
    
    tasks = [(inst, s, max_eval) for inst in instances for s in seeds]
    results = {os.path.basename(inst): [] for inst in instances}
    
    log(f"Iniciando {len(tasks)} runs estendidas de até {max_eval} avs...")
    t0 = time.time()
    
    with mp.Pool(mp.cpu_count()) as pool:
        for i, (inst_name, seed, hist) in enumerate(pool.imap_unordered(run_etapa1_single, tasks)):
            results[inst_name].append(hist)
            log(f" [{time.time()-t0:.1f}s] Finalizado Etapa 1: {inst_name} // seed {seed}")
            
    # HVs
    nadir_points = {}
    for inst_name in results:
        all_sols = []
        for hist in results[inst_name]:
            for eval_n, front in hist:
                all_sols.extend(front)
        if len(all_sols) > 0:
            all_sols = np.array(all_sols)
            nadir_points[inst_name] = all_sols.max(axis=0) * 1.1
        else:
            nadir_points[inst_name] = [100.0, 10000.0, 100000.0]
            
    hv_curves = {inst: {} for inst in results}
    for inst_name, runs in results.items():
        ref_point = nadir_points[inst_name]
        ind = HV(ref_point=ref_point)
        for run_i, hist in enumerate(runs):
            curve_dict = {}
            for eval_n, front in hist:
                val = ind.do(np.array(front)) if len(front) > 0 else 0.0
                curve_dict[eval_n] = val
            hv_curves[inst_name][run_i] = curve_dict
            
    stab_points = {}
    for inst_name, runs in hv_curves.items():
        eval_steps = sorted(runs[0].keys())
        avg_hv = []
        for e in eval_steps:
            avg_hv.append(np.mean([runs[i].get(e, 0) for i in range(len(runs))]))
            
        plt.figure()
        plt.plot(eval_steps, avg_hv, label="Média HV")
        plt.title(f"Convergência {inst_name}")
        plt.xlabel("Avaliações")
        plt.ylabel("Hypervolume")
        plt.grid()
        plt.savefig(f"/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/results/etapa1_{inst_name}_hv.png")
        
        stab_eval = max_eval
        for i in range(2, len(eval_steps)):
            curr = avg_hv[i]
            prev = avg_hv[i-2]
            if prev > 0:
                growth = (curr - prev) / prev
                if growth < 0.005: 
                    # Verifica robustez: os próximos 2 passos também devem crescer < 0.5% a partir de prev
                    if i+2 < len(eval_steps):
                        g2 = (avg_hv[i+1] - prev) / prev
                        g3 = (avg_hv[i+2] - prev) / prev
                        if g2 < 0.005 and g3 < 0.005:
                            stab_eval = eval_steps[i]
                            break
                    else:
                        stab_eval = eval_steps[i]
                        break
        stab_points[inst_name] = stab_eval
        log(f"Estabilização {inst_name}: {stab_eval} avaliações")
        
    global_stab = max(stab_points.values())
    stopping_eval = int(round((global_stab * 1.2) / 5000.0) * 5000)
    log(f"Ponto de estabilização global selecionado: {global_stab}")
    log(f"CRITÉRIO DE PARADA OFICIAL => {stopping_eval} Avaliações")
    return stopping_eval

# =========================================================
# ETAPA 2
# =========================================================

def run_etapa2_single(args):
    alg_name, inst_name, seed, max_eval = args
    inst_path = f"/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/evrptw_instances/{inst_name}"
    ctx = parse_instance(inst_path)
    prob = EVRPTWProblem(ctx, k_max=0)
    
    if alg_name == "NSGA-II":
        alg = NSGA2(pop_size=100, sampling=TWBiasedSampling(), crossover=OrderCrossover(), mutation=InversionMutation(), eliminate_duplicates=True)
    elif alg_name == "MOEA/D":
        ref_dirs = get_reference_directions("das-dennis", 3, n_partitions=13)
        alg = MOEAD(ref_dirs, n_neighbors=20, prob_neighbor_mating=0.7, sampling=TWBiasedSampling(), crossover=OrderCrossover(), mutation=InversionMutation())
    elif alg_name == "SMS-EMOA":
        alg = SMSEMOA(pop_size=100, sampling=TWBiasedSampling(), crossover=OrderCrossover(), mutation=InversionMutation(), eliminate_duplicates=True)
        
    res = minimize(prob, alg, ("n_eval", max_eval), verbose=False, seed=seed)
    
    cv_arr = res.pop.get("_cv")
    F_real = res.pop.get("_F_real")
    if cv_arr is None: cv_arr = res.pop.get("CV")
    if F_real is None: F_real = res.pop.get("F")
    
    mask = cv_arr[:, 0] <= 1e-9
    
    feas_F = F_real[mask].tolist() if mask.sum() > 0 else []
    X_feas = res.pop.get("X")[mask].tolist() if mask.sum() > 0 else []
    
    return alg_name, inst_name, seed, feas_F, X_feas

def etapa_2(stopping_eval):
    log("\n" + "="*50)
    log(" ETAPA 2: Validações (0 discrepâncias, HV, Kruskal)")
    log("="*50)
    
    instances = ["c101_21.txt", "r201_21.txt", "rc201_21.txt"]
    algs = ["NSGA-II", "MOEA/D", "SMS-EMOA"]
    seeds = list(range(42, 52)) # 10 seeds
    
    tasks = [(a, i, s, stopping_eval) for a in algs for i in instances for s in seeds]
    results = {} # inst -> alg -> [feas_F, X]
    
    log(f"Iniciando {len(tasks)} runs de todos os algoritmos ({stopping_eval} evals)...")
    t0 = time.time()
    with mp.Pool(mp.cpu_count()) as pool:
        for c, (alg_name, inst_name, seed, F, X) in enumerate(pool.imap_unordered(run_etapa2_single, tasks)):
            if inst_name not in results: results[inst_name] = {}
            if alg_name not in results[inst_name]: results[inst_name][alg_name] = []
            results[inst_name][alg_name].append({"F": F, "X": X, "seed": seed})
            if (c+1) % 15 == 0:
                log(f" [{time.time()-t0:.1f}s] Completado {c+1}/{len(tasks)}")
                
    # Varredura de Auditor
    log("\n Verificação 1: Auditor Independente")
    auditor_discrepancias = 0
    
    for inst_name in instances:
        ctx = parse_instance(f"/Users/rafaelmoura/MOEA_EVRP_TCC_2/MOEA_EVRP_TCC/evrptw_instances/{inst_name}")
        dec = Decoder(ctx)
        auditor = IndependentAuditor(ctx)
        
        for alg_name in algs:
            for run in results[inst_name][alg_name]:
                for perm in run["X"]:
                    from numpy import array
                    p_arr = array(perm, dtype=int)
                    F_dec, cv_dec, expanded = dec.decode_detailed(p_arr)
                    if cv_dec <= 1e-9:
                        ok, viols, a_f1, a_f2, a_f3 = auditor.audit_solution(expanded)
                        hard = [v for v in viols if "TW violada" not in v]
                        if len(hard) > 0:
                            auditor_discrepancias += 1
                        # Validando match estrito
                        if abs(F_dec[0] - a_f1) > 1e-6 or abs(F_dec[1] - a_f2) > 1e-6 or abs(F_dec[2] - a_f3) > 1e-5:
                            auditor_discrepancias += 1
                            
    log(f" Erros de Auditoria: {auditor_discrepancias} {'✅' if auditor_discrepancias==0 else '❌'}")
    
    # HVs
    log("\n Verificações 2 e 3: HVs finitos/positivos e Kruskal-Wallis")
    kruskal_passed = 0
    hv_matrix = {inst: {a: [] for a in algs} for inst in instances}
    
    for inst_name in instances:
        all_sols = []
        for alg_name in algs:
            for run in results[inst_name][alg_name]:
                all_sols.extend(run["F"])
        
        nadir = np.array(all_sols).max(axis=0) * 1.1 if all_sols else [100, 10000, 100000]
        ind = HV(ref_point=nadir)
        
        for alg_name in algs:
            for run in results[inst_name][alg_name]:
                if len(run["F"]) > 0:
                    val = ind.do(np.array(run["F"]))
                    hv_matrix[inst_name][alg_name].append(val)
                else:
                    hv_matrix[inst_name][alg_name].append(0.0)
                    
        groups = [hv_matrix[inst_name][a] for a in algs]
        stat, p = kruskal(*groups)
        log(f" -> {inst_name}: Kruskal p={p:.5f}")
        if p < 0.10: kruskal_passed += 1
        
    log(f" Instâncias com p < 0.10: {kruskal_passed}/3 {'✅' if kruskal_passed>=2 else '❌'}")
    
    # Camadas f1
    log("\n Verificação 4: diversidade f1 na frente")
    f1_passed = False
    for inst_name in instances:
        for alg_name in algs:
            for run in results[inst_name][alg_name]:
                if len(run["F"]) > 0:
                    unique_f1 = len(set([f[0] for f in run["F"]]))
                    if unique_f1 > 3:
                        f1_passed = True
    log(f" Frente com >3 valores f1: {'Sim ✅' if f1_passed else 'Não ❌'}")
    
    return results, hv_matrix

# =========================================================
# ETAPA 3
# =========================================================

def etapa_3(results, hv_matrix):
    log("\n" + "="*50)
    log(" ETAPA 3: Tendências Visíveis (Hipóteses)")
    log("="*50)
    
    instances = ["c101_21.txt", "r201_21.txt", "rc201_21.txt"]
    algs = ["NSGA-II", "MOEA/D", "SMS-EMOA"]
    
    # H1: Rank do NSGA-II é pior q SMS-EMOA?
    nsga_worse = 0
    for inst in instances:
        nsga_hv = np.mean(hv_matrix[inst]["NSGA-II"])
        sms_hv = np.mean(hv_matrix[inst]["SMS-EMOA"])
        if nsga_hv < sms_hv: nsga_worse += 1
    log(f" H1 (NSGA-II HV < SMS-EMOA HV): Verificado em {nsga_worse}/3 instâncias")
    
    # Hnova: SMS-EMOA cobre mais f1 layers?
    sms_more_layers = 0
    for inst in instances:
        nsga_f1 = np.mean([len(set([f[0] for f in r["F"]])) for r in results[inst]["NSGA-II"]])
        sms_f1 = np.mean([len(set([f[0] for f in r["F"]])) for r in results[inst]["SMS-EMOA"]])
        if sms_f1 > nsga_f1: sms_more_layers += 1
    log(f" Hnova (SMS cobre + cam. f1 q NSGA-II): Verificado em {sms_more_layers}/3 instâncias")
    
    # Hdelay: MOEA/D tem menor best_f3?
    moea_smaller_f3 = 0
    for inst in instances:
        from numpy import array
        nsga_f3 = np.mean([min([f[2] for f in r["F"]]+[float('inf')]) for r in results[inst]["NSGA-II"]])
        sms_f3  = np.mean([min([f[2] for f in r["F"]]+[float('inf')]) for r in results[inst]["SMS-EMOA"]])
        moea_f3 = np.mean([min([f[2] for f in r["F"]]+[float('inf')]) for r in results[inst]["MOEA/D"]])
        
        if moea_f3 < nsga_f3 and moea_f3 < sms_f3: moea_smaller_f3 += 1
    log(f" Hdelay (MOEA/D menor f3 real): Verificado em {moea_smaller_f3}/3 instâncias")
    
    # H3: c101 diferente de r201?
    c_pattern = (np.mean(hv_matrix["c101_21.txt"]["SMS-EMOA"]) > np.mean(hv_matrix["c101_21.txt"]["NSGA-II"]))
    r_pattern = (np.mean(hv_matrix["r201_21.txt"]["SMS-EMOA"]) > np.mean(hv_matrix["r201_21.txt"]["NSGA-II"]))
    diff_pattern = (c_pattern != r_pattern)
    log(f" H3 (c101 padrão diferente de r201): {diff_pattern}")

if __name__ == "__main__":
    if os.path.exists(LOG_FILE): os.remove(LOG_FILE)
    
    # Executa pipeline:
    stopping_eval = etapa_1()
    results, hv_matrix = etapa_2(stopping_eval)
    etapa_3(results, hv_matrix)
    
    log("\n### FIM DO PIPELINE DE VALIDAÇÃO GERAL ###")
