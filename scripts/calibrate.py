#!/usr/bin/env python3
"""
Passo 2a – Execuções exploratórias e calibração do critério de parada.

Para cada instância de calibração executa 5 runs de NSGA-II, registrando
a frente não-dominada a cada 500 avaliações.  Após todos os runs:

  1. Computa ref_point = 1.1 × max(F) por instância
  2. Calcula curva de hipervolume por run
  3. Identifica ponto de estabilização (< 0.5% de melhoria em 5 000 evals)
  4. Critério de parada = estabilização × 1.2 (arredondado p/ múltiplo de 1 000)
  5. Verifica frente trivial em r101_21 (CV < 0.1%)

Uso:
    python scripts/calibrate.py                 # todas as instâncias
    python scripts/calibrate.py --small-only    # só C10/C15 (rápido)
"""

import sys
import os
import argparse
import time
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from pymoo.core.callback import Callback
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize
from pymoo.indicators.hv import HV
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation

from src import parse_instance, EVRPTWProblem, TWBiasedSampling

# ── Configuração ──────────────────────────────────────────────────────
INSTANCES_SMALL = {
    "c101C10": "evrptw_instances/c101C10.txt",
    "r102C15": "evrptw_instances/r102C15.txt",
}
INSTANCES_LARGE = {
    "c101_21": "evrptw_instances/c101_21.txt",
    "r101_21": "evrptw_instances/r101_21.txt",
    "r204_21": "evrptw_instances/r204_21.txt",
}

N_RUNS = 5
POP_SIZE = 100
RECORD_INTERVAL = 500
SEEDS = list(range(2001, 2001 + N_RUNS))

MAX_EVALS_SMALL = 50_000
MAX_EVALS_LARGE = 500_000

OUTPUT_DIR = "results/calibration"


# ── Callback para gravação de frentes ─────────────────────────────────
class FrontRecorder(Callback):
    """Grava a frente não-dominada viável a cada *interval* avaliações."""

    def __init__(self, interval=500):
        super().__init__()
        self.interval = interval
        self.history = []          # [(n_evals, F_nd | None)]
        self._next_threshold = interval

    def notify(self, algorithm):
        n_evals = algorithm.evaluator.n_eval
        if n_evals < self._next_threshold:
            return
        self._next_threshold += self.interval

        cv_arr = algorithm.pop.get("_cv")
        F_real = algorithm.pop.get("_F_real")

        if cv_arr is None or F_real is None:
            self.history.append((int(n_evals), None))
            return

        mask = cv_arr[:, 0] <= 1e-9
        feasible = F_real[mask]

        if len(feasible) == 0:
            self.history.append((int(n_evals), None))
            return

        from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting
        nds = NonDominatedSorting()
        fronts = nds.do(feasible)
        nd = feasible[fronts[0]].copy()
        self.history.append((int(n_evals), nd))


# ── Funções de análise ────────────────────────────────────────────────
def compute_hv_curve(history, ref_point):
    indicator = HV(ref_point=ref_point)
    curve = []
    for n_evals, F in history:
        hv = float(indicator.do(F)) if F is not None else 0.0
        curve.append((n_evals, hv))
    return curve


def find_stabilization(curves, window=5000, threshold=0.005, interval=500):
    if not curves or all(len(c) == 0 for c in curves):
        return 0

    max_evals = max(e for c in curves for e, _ in c)
    n_ck = max_evals // interval

    arrs = []
    for curve in curves:
        a = np.zeros(n_ck)
        for e, hv in curve:
            idx = e // interval - 1
            if 0 <= idx < n_ck:
                a[idx] = hv
        arrs.append(a)
    arrs = np.array(arrs)

    final_hv = arrs[:, -1].max()
    if final_hv == 0:
        return max_evals

    w = max(window // interval, 1)
    for t in range(n_ck - w):
        growth = max((a[t: t + w].max() - a[t]) for a in arrs)
        if growth < threshold * final_hv:
            return (t + 1) * interval

    return max_evals


# ── Loop principal ────────────────────────────────────────────────────
def calibrate_instance(inst_name, inst_path, max_evals):
    ctx = parse_instance(inst_path)
    problem = EVRPTWProblem(ctx)

    histories = []
    run_times = []

    for run, seed in enumerate(SEEDS):
        cb = FrontRecorder(interval=RECORD_INTERVAL)
        alg = NSGA2(
            pop_size=POP_SIZE,
            sampling=TWBiasedSampling(),
            crossover=OrderCrossover(),
            mutation=InversionMutation(),
            eliminate_duplicates=True,
        )
        t0 = time.time()
        res = minimize(problem, alg, ("n_eval", max_evals),
                       callback=cb, verbose=False, seed=seed)
        elapsed = time.time() - t0
        run_times.append(elapsed)
        histories.append(cb.history)

        cv_arr = res.pop.get("_cv")
        n_feas = int(np.sum(cv_arr[:, 0] <= 1e-9)) if cv_arr is not None else 0
        print(f"  Run {run+1}: {elapsed:6.1f}s  |  {n_feas:>3} viáveis  "
              f"|  {len(cb.history)} checkpoints")

    # Ref point
    all_F = [F for h in histories for _, F in h if F is not None]
    if not all_F:
        print("  *** Nenhuma solução viável ***")
        return {
            "stabilization": max_evals,
            "criterion": max_evals,
            "ref_point": None,
            "avg_time": np.mean(run_times),
            "trivial": True,
        }

    stacked = np.vstack(all_F)
    ref_point = (1.1 * stacked.max(axis=0)).tolist()

    hv_curves = [compute_hv_curve(h, np.array(ref_point)) for h in histories]

    stab = find_stabilization(hv_curves, window=5000,
                              threshold=0.005, interval=RECORD_INTERVAL)
    criterion = int(np.ceil(stab * 1.2 / 1000) * 1000)
    criterion = min(criterion, max_evals)

    final_hvs = [c[-1][1] for c in hv_curves if c]
    hv_mean = np.mean(final_hvs) if final_hvs else 0
    hv_cv = (np.std(final_hvs) / hv_mean) if hv_mean > 0 else 0

    avg_time = float(np.mean(run_times))

    print(f"\n  Ref point:    [{ref_point[0]:.1f}, {ref_point[1]:.1f}, {ref_point[2]:.1f}]")
    print(f"  Estabilização: {stab} evals")
    print(f"  Critério (×1.2): {criterion} evals")
    print(f"  Tempo médio/run: {avg_time:.1f}s")
    if "r101" in inst_name:
        print(f"  HV CV entre runs: {hv_cv:.4f}  "
              f"({'TRIVIAL' if hv_cv < 0.001 else 'OK'})")

    curves_save = {}
    for r, curve in enumerate(hv_curves):
        curves_save[f"run_{r+1}"] = curve
    out_path = os.path.join(OUTPUT_DIR, f"hv_curves_{inst_name}.json")
    with open(out_path, "w") as f:
        json.dump(curves_save, f)

    return {
        "stabilization": stab,
        "criterion": criterion,
        "ref_point": ref_point,
        "avg_time": avg_time,
        "trivial": bool(hv_cv < 0.001) if "r101" in inst_name else None,
        "hv_final_mean": float(hv_mean),
        "hv_final_cv": float(hv_cv),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--small-only", action="store_true",
                    help="Executa somente instâncias C10/C15 (rápido)")
    args = ap.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    instances = dict(INSTANCES_SMALL)
    if not args.small_only:
        instances.update(INSTANCES_LARGE)

    print("=" * 70)
    print("PASSO 2a  –  Calibração do critério de parada")
    print(f"Instâncias: {', '.join(instances.keys())}")
    print("=" * 70)

    results = {}

    for name, path in instances.items():
        is_large = name.endswith("_21")
        max_evals = MAX_EVALS_LARGE if is_large else MAX_EVALS_SMALL

        print(f"\n{'─' * 60}")
        print(f"{name}  (max_evals={max_evals:,})")
        print(f"{'─' * 60}")

        results[name] = calibrate_instance(name, path, max_evals)

    print(f"\n{'=' * 70}")
    print("RESUMO")
    print(f"{'=' * 70}")

    print(f"\n{'Instância':<12} {'Estab.':>8} {'Critério':>10} {'Tempo/run':>10}")
    print("─" * 44)
    for name, r in results.items():
        print(f"{name:<12} {r['stabilization']:>8,} {r['criterion']:>10,} {r['avg_time']:>9.1f}s")

    crit_21 = [r["criterion"] for n, r in results.items() if "_21" in n]
    crit_small = [r["criterion"] for n, r in results.items() if "_21" not in n]
    final_large = max(crit_21) if crit_21 else None
    final_small = max(crit_small) if crit_small else None

    print(f"\nCritério de parada:")
    if final_small:
        print(f"  Instâncias C10/C15: {final_small:,} evals")
    if final_large:
        print(f"  Instâncias _21:     {final_large:,} evals")

    if "r101_21" in results and results["r101_21"].get("trivial"):
        print("\n  ATENÇÃO: r101_21 produz frente trivial.")
        print("  Recomendação: substituir por r102_21 no experimento primário.")

    if crit_21:
        avg_t = np.mean([r["avg_time"] for n, r in results.items() if "_21" in n])
        total_primary = 18 * 3 * 31
        est_h = total_primary * avg_t / 3600
        print(f"\nEstimativa do experimento primário:")
        print(f"  {total_primary} runs × {avg_t:.1f}s ≈ {est_h:.1f} horas")

    summary = {"per_instance": results}
    if final_large:
        summary["criterion_large"] = final_large
    if final_small:
        summary["criterion_small"] = final_small
    with open(os.path.join(OUTPUT_DIR, "calibration_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nResultados salvos em {OUTPUT_DIR}/")
    print("=" * 70)


if __name__ == "__main__":
    main()
