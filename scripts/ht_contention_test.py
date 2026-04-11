#!/usr/bin/env python3
"""
ht_contention_test.py
=====================
Testa se o Hyperthreading (HT) causa contenção em execuções paralelas
do NSGA-II no EVRPTW com o i9-10900F (10 físicos / 20 lógicos).

Metodologia:
  - Carga total FIXA: N_TOTAL_SEEDS runs × NSGA-II × N_EVALS por run
  - Paralelismo varia: [1, 2, 4, 5, 6, 8, 10, 12, 15, 20] workers
  - Cada configuração roda TODOS os seeds (mesma carga total)
  - Mede: wallclock, throughput (runs/s), speedup, eficiência (%)

Interpretação:
  - Eficiência alta até 10 workers → HT NÃO ajuda após isso (CPU-bound)
  - Eficiência cai bruscamente após 10 → HT contention confirmada
  - Se eficiência >50% em 20 workers → HT ajuda marginalmente

OMP/MKL/BLAS threading é forçado para 1 thread por processo para evitar
oversubscription (numpy usando múltiplos threads × múltiplos processos).

Uso:
    python scripts/ht_contention_test.py
    python scripts/ht_contention_test.py --n-evals 5000 --total-seeds 20
    python scripts/ht_contention_test.py --workers 1 2 4 8 10 20

Saída:
    - Tabela no terminal por nível de paralelismo
    - CSV em results/ht_contention_<timestamp>.csv
    - JSON em results/ht_contention_<timestamp>.json
"""

# ──────────────────────────────────────────────────────────────────────────
# CRÍTICO: restringir threading interno do numpy/MKL/OpenBLAS ANTES de
# qualquer import numpy. Evita oversubscription quando múltiplos processos
# rodam simultaneamente (cada processo com seu próprio numpy interno).
# ──────────────────────────────────────────────────────────────────────────
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("BLIS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")

import sys
import time
import csv
import json
import platform
import argparse
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np

# ---------------------------------------------------------------------------
# Configurações padrão
# ---------------------------------------------------------------------------
DEFAULT_INSTANCE    = os.path.join(ROOT, "evrptw_instances", "rc101_21.txt")
DEFAULT_N_EVALS     = 5_000       # avaliações por run (ajuste ao poder da máquina)
DEFAULT_TOTAL_SEEDS = 20          # seeds fixas = carga total constante
DEFAULT_POP_SIZE    = 100
DEFAULT_WORKERS     = [1, 2, 4, 5, 6, 8, 10, 12, 15, 20]

ALGORITHM_NAME = "NSGA-II"       # fixo — uma variável por vez


# ---------------------------------------------------------------------------
# Worker (nível de módulo — obrigatório para multiprocessing/pickle)
# ---------------------------------------------------------------------------

def _worker(job: tuple) -> dict:
    """
    Executa um run de NSGA-II e retorna métricas.
    Rodado em processo separado pelo ProcessPoolExecutor.

    NOTA: No Linux (fork), herda o espaço de memória do pai, incluindo
    imports e variáveis globais. Os os.environ aqui garantem que processos
    filho também respeitem o limite de 1 thread numpy.
    """
    # Garante restrição de threading no processo filho também
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["BLIS_NUM_THREADS"] = "1"
    os.environ["NUMEXPR_NUM_THREADS"] = "1"

    inst_path, n_evals, pop_size, seed = job

    # Imports locais garantem que o processo filho encontra o módulo
    # mesmo se fork não estiver disponível (ex: Windows/spawn)
    sys.path.insert(0, ROOT)

    from pymoo.algorithms.moo.nsga2 import NSGA2
    from pymoo.optimize import minimize
    from pymoo.operators.crossover.ox import OrderCrossover
    from pymoo.operators.mutation.inversion import InversionMutation
    from src import parse_instance, EVRPTWProblem, TWBiasedSampling

    ctx     = parse_instance(inst_path)
    problem = EVRPTWProblem(ctx, k_max=0)   # sem local search no benchmark

    alg = NSGA2(
        pop_size=pop_size,
        sampling=TWBiasedSampling(),
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
        eliminate_duplicates=True,
    )

    t0 = time.perf_counter()
    res = minimize(problem, alg, ("n_eval", n_evals), verbose=False, seed=seed)
    elapsed = time.perf_counter() - t0

    cv_arr = res.pop.get("_cv")
    n_feas = int(np.sum(cv_arr[:, 0] <= 1e-9)) if cv_arr is not None else 0
    n_total = len(cv_arr) if cv_arr is not None else 0

    return {
        "seed":      seed,
        "elapsed_s": round(elapsed, 4),
        "n_feasible": n_feas,
        "n_total":   n_total,
    }


# ---------------------------------------------------------------------------
# Execução de um nível de paralelismo
# ---------------------------------------------------------------------------

def run_parallel(n_workers: int, seeds: list, inst_path: str,
                 n_evals: int, pop_size: int) -> tuple:
    """
    Distribui todos os seeds entre n_workers processos paralelos.
    Retorna (resultados, wallclock_total).
    """
    jobs = [(inst_path, n_evals, pop_size, seed) for seed in seeds]

    results = []
    wall_start = time.perf_counter()

    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(_worker, j): j for j in jobs}
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as exc:
                seed = futures[fut][3]
                print(f"\n  [ERRO] seed={seed}: {exc}")

    wall_elapsed = time.perf_counter() - wall_start
    return results, wall_elapsed


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def fmt_hms(s: float) -> str:
    h = int(s // 3600); m = int((s % 3600) // 60); sec = s % 60
    if h:  return f"{h}h {m:02d}m {sec:04.1f}s"
    if m:  return f"{m}m {sec:04.1f}s"
    return f"{sec:.2f}s"


def _machine_info() -> dict:
    return {
        "node":      platform.node(),
        "platform":  platform.platform(),
        "processor": platform.processor(),
        "python":    platform.python_version(),
        "cpu_count": os.cpu_count(),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Testa HT contention variando workers paralelos (NSGA-II fixo)."
    )
    ap.add_argument("--instance",     default=DEFAULT_INSTANCE)
    ap.add_argument("--n-evals",      type=int, default=DEFAULT_N_EVALS,
                    help=f"Avaliações por run (padrão: {DEFAULT_N_EVALS})")
    ap.add_argument("--total-seeds",  type=int, default=DEFAULT_TOTAL_SEEDS,
                    help=f"Total de runs fixos (padrão: {DEFAULT_TOTAL_SEEDS})")
    ap.add_argument("--pop-size",     type=int, default=DEFAULT_POP_SIZE)
    ap.add_argument("--workers",      type=int, nargs="+", default=DEFAULT_WORKERS,
                    help="Lista de contagens de workers a testar")
    ap.add_argument("--seed-start",   type=int, default=1)
    args = ap.parse_args()

    # ── Setup ──────────────────────────────────────────────────────────
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    inst_name  = os.path.splitext(os.path.basename(args.instance))[0]
    machine    = _machine_info()
    seeds      = list(range(args.seed_start, args.seed_start + args.total_seeds))
    worker_counts = sorted(set(args.workers))

    print("=" * 72)
    print("HT CONTENTION TEST — EVRPTW / NSGA-II")
    print("=" * 72)
    print(f"  Máquina    : {machine['node']}  ({machine['platform']})")
    print(f"  CPUs lógicas: {machine['cpu_count']}")
    print(f"  Python     : {machine['python']}")
    print(f"  Instância  : {args.instance}")
    print(f"  Algoritmo  : {ALGORITHM_NAME}  (local search OFF)")
    print(f"  Total runs : {args.total_seeds} seeds fixas × {args.n_evals:,} evals")
    print(f"  Workers    : {worker_counts}")
    print(f"  OMP/MKL    : 1 thread por processo (forçado)")
    print("=" * 72)

    # ── Estimativa de tempo total ───────────────────────────────────────
    # (rápida: 10 evals para medir ms/eval antes de tudo)
    print("\nEstimando tempo por run (10 evals)...", end="", flush=True)
    _r, _w = run_parallel(1, [seeds[0]], args.instance, 10, args.pop_size)
    ms_est = _r[0]["elapsed_s"] / 10 * 1000
    run_est = ms_est / 1000 * args.n_evals
    total_seq_est = run_est * args.total_seeds
    print(f"  {ms_est:.1f} ms/eval  →  ~{fmt_hms(run_est)}/run  "
          f"→  sequencial total ≈{fmt_hms(total_seq_est)}")
    print(f"  Tempo estimado desta suite: "
          f"~{fmt_hms(total_seq_est * (1 + len(worker_counts)//2))}\n")

    # ── Execução principal ─────────────────────────────────────────────
    summary_rows = []
    baseline_throughput = None
    all_run_records     = []

    print(f"{'Workers':>8}  {'Wallclock':>12}  "
          f"{'Throughput':>12}  {'Speedup':>8}  "
          f"{'Eficiência':>11}  {'ms/eval med':>12}  "
          f"{'Feas med':>9}")
    print("─" * 80)

    for n_workers in worker_counts:
        print(f"  [{n_workers:2d}]  rodando {args.total_seeds} seeds...",
              end="", flush=True)

        results, wall = run_parallel(
            n_workers, seeds, args.instance, args.n_evals, args.pop_size
        )

        if not results:
            print("  ERRO — nenhum resultado")
            continue

        elapsed_list = [r["elapsed_s"] for r in results]
        throughput   = len(results) / wall                 # runs/segundo
        ms_med       = float(np.mean(elapsed_list)) / args.n_evals * 1000
        feas_med     = float(np.mean([r["n_feasible"] for r in results]))

        if baseline_throughput is None:
            baseline_throughput = throughput

        speedup    = throughput / baseline_throughput
        efficiency = speedup / n_workers * 100.0

        print(f"\r  [{n_workers:2d}]  "
              f"{fmt_hms(wall):>12}  "
              f"{throughput:>9.3f} r/s  "
              f"{speedup:>8.2f}x  "
              f"{efficiency:>10.1f}%%  "
              f"{ms_med:>12.3f}  "
              f"{feas_med:>9.1f}")

        row = {
            "n_workers":         n_workers,
            "wall_s":            round(wall, 3),
            "n_completed":       len(results),
            "throughput_rps":    round(throughput, 6),
            "speedup":           round(speedup, 4),
            "efficiency_pct":    round(efficiency, 2),
            "elapsed_mean_s":    round(float(np.mean(elapsed_list)), 3),
            "elapsed_std_s":     round(float(np.std(elapsed_list)), 3),
            "ms_per_eval_mean":  round(ms_med, 4),
            "feasible_mean":     round(feas_med, 2),
        }
        summary_rows.append(row)

        for r in results:
            all_run_records.append({
                "n_workers":   n_workers,
                "seed":        r["seed"],
                "elapsed_s":   r["elapsed_s"],
                "ms_per_eval": round(r["elapsed_s"] / args.n_evals * 1000, 4),
                "n_feasible":  r["n_feasible"],
                "n_total":     r["n_total"],
            })

    # ── Tabela final completa ──────────────────────────────────────────
    print(f"\n\n{'═' * 72}")
    print("RESULTADO FINAL — ANÁLISE DE HT CONTENTION")
    print(f"{'═' * 72}")
    print(f"  Workers  Wallclock    Throughput   Speedup  Eficiência  ms/eval")
    print(f"  {'─'*65}")
    for row in summary_rows:
        eff_str = f"{row['efficiency_pct']:.1f}%%"
        bar_len = int(row["efficiency_pct"] / 5)   # escala: 100% = 20 chars
        bar = "█" * min(bar_len, 20)
        print(f"  {row['n_workers']:6d}   {fmt_hms(row['wall_s']):>10s}   "
              f"{row['throughput_rps']:>8.3f} r/s  "
              f"{row['speedup']:>7.2f}x  "
              f"{eff_str:>10s}  "
              f"{row['ms_per_eval_mean']:>7.3f}  {bar}")

    # ── Recomendação automática ────────────────────────────────────────
    print(f"\n{'─' * 72}")
    print("DIAGNÓSTICO:")

    eff_at_10 = next((r["efficiency_pct"] for r in summary_rows
                      if r["n_workers"] == 10), None)
    eff_at_20 = next((r["efficiency_pct"] for r in summary_rows
                      if r["n_workers"] == 20), None)

    if eff_at_10 is not None and eff_at_20 is not None:
        ht_gain = eff_at_20 / eff_at_10  # >1 = HT ajuda relativamente
        print(f"  Eficiência em 10 workers (físicos) : {eff_at_10:.1f}%%")
        print(f"  Eficiência em 20 workers (HT)      : {eff_at_20:.1f}%%")
        if eff_at_20 < 40:
            print("  → HT PREJUDICA significativamente. Usar ≤10 workers.")
        elif eff_at_20 < 60:
            print("  → HT ajuda pouco. Recomendado: 10 workers (físicos).")
        else:
            print("  → HT ajuda marginalmente. Pode usar até 20 workers.")

    # Melhor throughput
    best = max(summary_rows, key=lambda r: r["throughput_rps"])
    print(f"  Maior throughput : {best['n_workers']} workers "
          f"({best['throughput_rps']:.3f} r/s, speedup={best['speedup']:.2f}x)")

    # Melhor eficiência
    best_eff = max(summary_rows, key=lambda r: r["efficiency_pct"])
    print(f"  Maior eficiência : {best_eff['n_workers']} workers "
          f"({best_eff['efficiency_pct']:.1f}%%)")

    recommended = best["n_workers"]
    print(f"\n  RECOMENDAÇÃO: usar {recommended} workers paralelos.")
    print(f"{'─' * 72}")

    # ── Exporta CSV ────────────────────────────────────────────────────
    results_dir = os.path.join(ROOT, "results")
    os.makedirs(results_dir, exist_ok=True)

    summary_csv = os.path.join(results_dir, f"ht_contention_summary_{timestamp}.csv")
    with open(summary_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=summary_rows[0].keys())
        w.writeheader(); w.writerows(summary_rows)

    runs_csv = os.path.join(results_dir, f"ht_contention_runs_{timestamp}.csv")
    with open(runs_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=all_run_records[0].keys())
        w.writeheader(); w.writerows(all_run_records)

    # ── Exporta JSON ───────────────────────────────────────────────────
    json_path = os.path.join(results_dir, f"ht_contention_{timestamp}.json")
    with open(json_path, "w") as f:
        json.dump({
            "meta": {
                "timestamp":    timestamp,
                "instance":     inst_name,
                "algorithm":    ALGORITHM_NAME,
                "n_evals":      args.n_evals,
                "total_seeds":  args.total_seeds,
                "pop_size":     args.pop_size,
                "worker_counts": worker_counts,
                "machine":      machine,
                "env": {
                    "OMP_NUM_THREADS":  os.environ.get("OMP_NUM_THREADS"),
                    "MKL_NUM_THREADS":  os.environ.get("MKL_NUM_THREADS"),
                    "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS"),
                },
            },
            "summary":  summary_rows,
            "all_runs": all_run_records,
        }, f, indent=2)

    print(f"\n  CSV sumário  : {summary_csv}")
    print(f"  CSV runs     : {runs_csv}")
    print(f"  JSON         : {json_path}")
    print(f"\n{'═' * 72}")
    print("Concluído!")
    print(f"{'═' * 72}\n")


if __name__ == "__main__":
    main()
