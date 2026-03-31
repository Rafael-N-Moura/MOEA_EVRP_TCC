#!/usr/bin/env python3
"""
Passo 3a – Tuning de parâmetros dos algoritmos.

Grid search por algoritmo:
  NSGA-II:  3 × 4 = 12 configurações   (p_crossover × p_mutation)
  MOEA/D:   4 × (3 + 9) = 48 configs   (T × [Tchebi×pnm + PBI×θ×pnm])
  SMS-EMOA: 3 × 4 = 12 configurações   (p_crossover × p_mutation)
  ─────────────────────────────────────
  Total: 72 configurações × 6 instâncias × 10 runs = 4 320 execuções

Instâncias de treino (C15, distintas do experimento primário):
  c103C15, c202C15, r102C15, r202C15, rc103C15, rc202C15

Seleção: configuração com maior HV médio global (média sobre 6 instâncias).
Ref point: calculado retrospectivamente por algoritmo × instância.

Uso:
    python scripts/tune.py                          # tudo
    python scripts/tune.py --algorithm nsga2        # só NSGA-II
    python scripts/tune.py --algorithm moead        # só MOEA/D
    python scripts/tune.py --algorithm smsemoa      # só SMS-EMOA
"""

import sys
import os
import argparse
import time
import json
from itertools import product

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.moo.moead import MOEAD
from pymoo.algorithms.moo.sms import SMSEMOA
from pymoo.optimize import minimize
from pymoo.indicators.hv import HV
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation

from src import parse_instance, EVRPTWProblem, TWBiasedSampling

# ── Configuração ──────────────────────────────────────────────────────
TRAIN_INSTANCES = {
    "c103C15":  "evrptw_instances/c103C15.txt",
    "c202C15":  "evrptw_instances/c202C15.txt",
    "r102C15":  "evrptw_instances/r102C15.txt",
    "r202C15":  "evrptw_instances/r202C15.txt",
    "rc103C15": "evrptw_instances/rc103C15.txt",
    "rc202C15": "evrptw_instances/rc202C15.txt",
}

N_RUNS = 10
POP_SIZE = 100
SEEDS = list(range(1001, 1001 + N_RUNS))
OUTPUT_DIR = "results/tuning"

DEFAULT_N_EVAL = 50_000          # fallback se calibração não existir


# ── Helpers ───────────────────────────────────────────────────────────
def _get_ref_dirs(n_obj, n_partitions):
    try:
        from pymoo.util.ref_dirs import get_reference_directions
    except ImportError:
        from pymoo.util.reference_direction import get_reference_directions
    return get_reference_directions("das-dennis", n_obj, n_partitions=n_partitions)


def _operators(pc=0.9, pm=None, n_cust=15):
    if pm is None:
        pm = 1.0 / n_cust
    return dict(
        sampling=TWBiasedSampling(),
        crossover=OrderCrossover(prob=pc),
        mutation=InversionMutation(prob=pm),
    )


def _resolve_pm(pm_val, n_cust):
    return 1.0 / n_cust if pm_val == "1/n" else float(pm_val)


# ── Geração de configurações ─────────────────────────────────────────
def build_nsga2_configs():
    cfgs = []
    for pc, pm in product([0.7, 0.8, 0.9], [0.05, 0.10, 0.20, "1/n"]):
        cfgs.append({"algorithm": "NSGA-II", "p_crossover": pc, "p_mutation": pm})
    return cfgs


def build_moead_configs():
    cfgs = []
    for T in [10, 15, 20, 30]:
        for pnm in [0.7, 0.9, 1.0]:
            cfgs.append({
                "algorithm": "MOEA/D", "n_neighbors": T,
                "decomposition": "tchebi", "prob_neighbor_mating": pnm,
            })
        for theta in [1, 3, 5]:
            for pnm in [0.7, 0.9, 1.0]:
                cfgs.append({
                    "algorithm": "MOEA/D", "n_neighbors": T,
                    "decomposition": "pbi", "theta": theta,
                    "prob_neighbor_mating": pnm,
                })
    return cfgs


def build_smsemoa_configs():
    cfgs = []
    for pc, pm in product([0.7, 0.8, 0.9], [0.05, 0.10, 0.20, "1/n"]):
        cfgs.append({"algorithm": "SMS-EMOA", "p_crossover": pc, "p_mutation": pm})
    return cfgs


def config_label(cfg):
    alg = cfg["algorithm"]
    if alg in ("NSGA-II", "SMS-EMOA"):
        return f"{alg}_pc{cfg['p_crossover']}_pm{cfg['p_mutation']}"
    d = cfg["decomposition"]
    th = f"_th{cfg['theta']}" if "theta" in cfg else ""
    return (f"MOEAD_T{cfg['n_neighbors']}_{d}{th}"
            f"_pnm{cfg['prob_neighbor_mating']}")


# ── Fábricas de algoritmos ────────────────────────────────────────────
def make_algorithm(cfg, n_cust):
    alg = cfg["algorithm"]

    if alg == "NSGA-II":
        pm = _resolve_pm(cfg["p_mutation"], n_cust)
        return NSGA2(pop_size=POP_SIZE,
                     **_operators(cfg["p_crossover"], pm, n_cust),
                     eliminate_duplicates=True)

    if alg == "MOEA/D":
        ref_dirs = _get_ref_dirs(3, n_partitions=13)
        ops = _operators(n_cust=n_cust)
        decomp_obj = None
        if cfg["decomposition"] == "pbi":
            try:
                from pymoo.decomposition.pbi import PBI
            except ImportError:
                from pymoo.decomposition.asf import PBI
            decomp_obj = PBI(theta=cfg.get("theta", 5))
        else:
            try:
                from pymoo.decomposition.tchebicheff import Tchebicheff
            except ImportError:
                from pymoo.decomposition.asf import Tchebicheff
            decomp_obj = Tchebicheff()
        return MOEAD(ref_dirs, n_neighbors=cfg["n_neighbors"],
                     decomposition=decomp_obj,
                     prob_neighbor_mating=cfg["prob_neighbor_mating"],
                     **ops)

    if alg == "SMS-EMOA":
        pm = _resolve_pm(cfg["p_mutation"], n_cust)
        return SMSEMOA(pop_size=POP_SIZE,
                       **_operators(cfg["p_crossover"], pm, n_cust),
                       eliminate_duplicates=True)

    raise ValueError(f"Algoritmo desconhecido: {alg}")


# ── Tuning de um algoritmo ───────────────────────────────────────────
def tune_algorithm(alg_name, configs, problems, n_eval):
    """
    Executa o grid search para um algoritmo.
    Retorna dict {label: {config, hv_per_instance, global_hv, global_std}}.
    """
    n_cfgs = len(configs)
    n_inst = len(problems)
    total_runs = n_cfgs * n_inst * N_RUNS
    print(f"\n{'=' * 60}")
    print(f"Tuning {alg_name}  ({n_cfgs} configs × {n_inst} inst × {N_RUNS} runs = {total_runs})")
    print(f"{'=' * 60}")

    # Passo 1: executar tudo, armazenar frentes
    # fronts[label][inst_name] = [F_run0, F_run1, ..., F_run9]
    fronts = {}
    label_to_cfg = {}
    done = 0

    for ci, cfg in enumerate(configs):
        label = config_label(cfg)
        label_to_cfg[label] = cfg
        fronts[label] = {}

        for inst_name, (ctx, problem) in problems.items():
            run_fronts = []
            for seed in SEEDS:
                try:
                    alg = make_algorithm(cfg, ctx.n_customers)
                    res = minimize(problem, alg, ("n_eval", n_eval),
                                   verbose=False, seed=seed)
                    cv_arr = res.pop.get("_cv")
                    F_real = res.pop.get("_F_real")
                    mask = cv_arr[:, 0] <= 1e-9
                    run_fronts.append(F_real[mask] if mask.any() else None)
                except Exception as exc:
                    print(f"    ERRO {label} / {inst_name} / seed={seed}: {exc}")
                    run_fronts.append(None)
                done += 1

            fronts[label][inst_name] = run_fronts

        pct = 100 * done / total_runs
        print(f"  [{ci+1}/{n_cfgs}] {label}  ({pct:.0f}%)")

    # Passo 2: ref point por instância (sobre TODAS as configs deste algoritmo)
    ref_points = {}
    for inst_name in problems:
        all_F = []
        for label in fronts:
            for F in fronts[label][inst_name]:
                if F is not None and len(F) > 0:
                    all_F.append(F)
        if all_F:
            ref_points[inst_name] = 1.1 * np.vstack(all_F).max(axis=0)
        else:
            ref_points[inst_name] = None

    # Passo 3: computar HV
    results = {}
    for label in fronts:
        hv_per_inst = {}
        for inst_name in problems:
            rp = ref_points[inst_name]
            if rp is None:
                hv_per_inst[inst_name] = 0.0
                continue
            indicator = HV(ref_point=rp)
            run_hvs = []
            for F in fronts[label][inst_name]:
                if F is not None and len(F) > 0:
                    run_hvs.append(float(indicator.do(F)))
                else:
                    run_hvs.append(0.0)
            hv_per_inst[inst_name] = float(np.mean(run_hvs))

        global_hv = float(np.mean(list(hv_per_inst.values())))
        global_std = float(np.std(list(hv_per_inst.values())))
        results[label] = {
            "config": label_to_cfg[label],
            "hv_per_instance": hv_per_inst,
            "global_hv": global_hv,
            "global_std": global_std,
        }

    # Ranking
    ranked = sorted(results.items(), key=lambda x: -x[1]["global_hv"])
    print(f"\n  Top-5 {alg_name}:")
    for i, (label, r) in enumerate(ranked[:5]):
        print(f"    {i+1}. {label}  HV={r['global_hv']:.6f}")

    best_label, best = ranked[0]
    print(f"\n  MELHOR: {best_label}")
    print(f"  Config: {best['config']}")

    return {
        "best_config": best["config"],
        "best_label": best_label,
        "best_hv": best["global_hv"],
        "top5": [(l, r["global_hv"]) for l, r in ranked[:5]],
        "all_results": {l: {"global_hv": r["global_hv"],
                            "global_std": r["global_std"]}
                        for l, r in results.items()},
    }


# ── CLI ───────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--algorithm", choices=["nsga2", "moead", "smsemoa"],
                    default=None, help="Tunar só um algoritmo")
    args = ap.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Critério de parada da calibração
    cal_path = "results/calibration/calibration_summary.json"
    if os.path.exists(cal_path):
        with open(cal_path) as f:
            cal = json.load(f)
        n_eval = cal.get("criterion_small", DEFAULT_N_EVAL)
        print(f"Critério da calibração: {n_eval:,} evals")
    else:
        n_eval = DEFAULT_N_EVAL
        print(f"Calibração não encontrada. Usando default: {n_eval:,} evals")

    # Carregar instâncias
    problems = {}
    for name, path in TRAIN_INSTANCES.items():
        ctx = parse_instance(path)
        problems[name] = (ctx, EVRPTWProblem(ctx))
    print(f"Instâncias de treino: {', '.join(problems.keys())}")

    # Algoritmos a tunar
    algo_map = {
        "nsga2":   ("NSGA-II",  build_nsga2_configs()),
        "moead":   ("MOEA/D",   build_moead_configs()),
        "smsemoa": ("SMS-EMOA", build_smsemoa_configs()),
    }

    if args.algorithm:
        algo_map = {args.algorithm: algo_map[args.algorithm]}

    all_results = {}
    t_total = time.time()

    for key, (alg_name, configs) in algo_map.items():
        t0 = time.time()
        res = tune_algorithm(alg_name, configs, problems, n_eval)
        elapsed = time.time() - t0
        res["elapsed_seconds"] = elapsed
        all_results[alg_name] = res
        print(f"\n  Tempo {alg_name}: {elapsed/60:.1f} min")

    # ── Resumo final ──────────────────────────────────────────────────
    total_time = time.time() - t_total
    print(f"\n{'=' * 70}")
    print("RESUMO DO TUNING")
    print(f"{'=' * 70}")

    for alg_name, res in all_results.items():
        print(f"\n{alg_name}:")
        print(f"  Melhor: {res['best_label']}  (HV={res['best_hv']:.6f})")
        cfg = res["best_config"]
        for k, v in cfg.items():
            if k != "algorithm":
                print(f"    {k}: {v}")

    print(f"\nTempo total: {total_time/60:.1f} min")

    # Salvar
    save = {}
    for alg_name, res in all_results.items():
        save[alg_name] = {
            "best_config": res["best_config"],
            "best_label":  res["best_label"],
            "best_hv":     res["best_hv"],
            "top5":        res["top5"],
            "elapsed_seconds": res["elapsed_seconds"],
        }
    with open(os.path.join(OUTPUT_DIR, "tuning_results.json"), "w") as f:
        json.dump(save, f, indent=2)

    print(f"\nResultados salvos em {OUTPUT_DIR}/tuning_results.json")
    print("=" * 70)


if __name__ == "__main__":
    main()
