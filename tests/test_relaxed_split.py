#!/usr/bin/env python3
"""
Testes do Split DP relaxado (apenas NEW decoder).
Baseline OLD vem do CSV existente: convergence_log_c101_21_no_ls_100k.csv

Teste 1 – 5 runs NSGA-II (new Split) 100k evals + comparação com CSV antigo
Teste 2 – Variação de f3 na frente de Pareto
Teste 3 – Auditor independente nas soluções viáveis
Teste 4 – 3 algoritmos (NSGA-II, MOEA/D, SMS-EMOA), Kruskal-Wallis nos HVs
"""

import sys, os, time, json, csv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.moo.moead import MOEAD
from pymoo.algorithms.moo.sms import SMSEMOA
from pymoo.optimize import minimize
from pymoo.indicators.hv import HV
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation
from pymoo.core.callback import Callback

from src import parse_instance, EVRPTWProblem, Decoder, TWBiasedSampling


# ─────────────────────────────────────────────────────────────────────
# Auditor independente
# ─────────────────────────────────────────────────────────────────────
class IndependentAuditor:
    def __init__(self, ctx):
        self.ctx = ctx
        self.Q = ctx.battery_capacity
        self.C = ctx.vehicle_capacity
        self.r = ctx.consumption_rate
        self.g = ctx.recharge_rate
        self.depot = ctx.depot_idx
        self.dist = ctx.dist_matrix
        self.travel = ctx.travel_matrix
        self.nodes = ctx.all_nodes
        self._is_station = set()
        for i in range(len(ctx.stations)):
            self._is_station.add(ctx._station_start + i)
        self._is_customer = set(ctx.customer_node_indices)

    def audit_solution(self, expanded_routes):
        viols = []
        all_customers_visited = []
        f2_total = 0.0
        f3_tw_total = 0.0

        for ri, route in enumerate(expanded_routes):
            rv, dist_route, tw_v, ret_time = self._audit_one_route(route, ri)
            viols.extend(rv)
            f2_total += dist_route
            f3_tw_total += tw_v
            for p in route:
                if p in self._is_customer:
                    all_customers_visited.append(p)

        expected = sorted(self.ctx.customer_node_indices)
        actual = sorted(all_customers_visited)
        if actual != expected:
            missing = set(expected) - set(actual)
            dup = [c for c in actual if actual.count(c) > 1]
            if missing:
                viols.append(f"clientes faltando: {missing}")
            if dup:
                viols.append(f"clientes duplicados: {set(dup)}")

        # No novo modelo, cv=0 ignora violações de tempo se for auditor estrito de bateria
        # Porém o auditor ainda checa TUDO, então viols terá erros de TW se existirem.
        # Mas f3 reflete o TW total.
        f1 = float(len(expanded_routes))
        return len(viols) == 0, viols, f1, f2_total, f3_tw_total

    def _audit_one_route(self, route, route_idx):
        viols = []
        depot = self.depot
        tw_v = 0.0
        if route[0] != depot:
            viols.append(f"R{route_idx}: não começa no depósito")
        if route[-1] != depot:
            viols.append(f"R{route_idx}: não termina no depósito")

        t = 0.0
        bat = self.Q
        load = 0.0
        dist_total = 0.0
        prev = route[0]

        for step, p in enumerate(route[1:], 1):
            arc_dist = self.dist[prev, p]
            arc_energy = arc_dist * self.r
            dist_total += arc_dist

            if bat < arc_energy - 1e-6:
                viols.append(
                    f"R{route_idx} passo {step}: bateria {bat:.4f} < "
                    f"energia {arc_energy:.4f} (nó {self.nodes[p].id})")
            bat = max(bat - arc_energy, 0.0)

            t += self.travel[prev, p]
            node = self.nodes[p]

            if t > node.due_date + 1e-6:
                if p != depot:
                    viols.append(
                        f"R{route_idx} passo {step}: TW violada, "
                        f"chegada={t:.4f} > due={node.due_date} ({node.id})")
                # Somamos a penalidade apenas se não for estação, pois f3 é "por cliente e depot"
                if p not in self._is_station:
                    tw_v += t - node.due_date

            t = max(t, node.ready_time)

            if p in self._is_station:
                t += self.g * (self.Q - bat)
                bat = self.Q
            elif p != depot:
                load += node.demand
                t += node.service_time
            prev = p

        if load > self.C + 1e-6:
            viols.append(f"R{route_idx}: sobrecarga {load:.2f} > C={self.C}")
        return viols, dist_total, tw_v, t


# ─────────────────────────────────────────────────────────────────────
# Callback de convergência
# ─────────────────────────────────────────────────────────────────────
class ConvergenceTracker(Callback):
    def __init__(self, interval=2000):
        super().__init__()
        self.interval = interval
        self._next = interval
        self.curve = []

    def notify(self, algorithm):
        n_eval = algorithm.evaluator.n_eval
        if n_eval < self._next:
            return
        self._next += self.interval

        cv_arr = algorithm.pop.get("_cv")
        F_real = algorithm.pop.get("_F_real")
        if cv_arr is None or F_real is None:
            return

        min_cv = float(cv_arr[:, 0].min())
        mask = cv_arr[:, 0] <= 1e-9
        n_feas = int(mask.sum())
        best_f1 = float(F_real[mask, 0].min()) if n_feas > 0 else float('nan')

        self.curve.append((int(n_eval), best_f1, min_cv, n_feas))


# ─────────────────────────────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────────────────────────────
INSTANCE_PATH = "evrptw_instances/c101_21.txt"
OLD_CSV = "results/convergence_log_c101_21_no_ls_100k.csv"
N_EVAL = 100_000
POP_SIZE = 100
SEEDS = [42, 43, 44, 45, 46]
RESULTS_DIR = "results/split_test"


def _ops():
    return dict(
        sampling=TWBiasedSampling(),
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
    )


def _ref_dirs():
    try:
        from pymoo.util.ref_dirs import get_reference_directions
    except ImportError:
        from pymoo.util.reference_direction import get_reference_directions
    return get_reference_directions("das-dennis", 3, n_partitions=13)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def load_old_csv_summary():
    """Carrega resumo do CSV antigo para comparação."""
    summary = {}  # {algorithm: {last_gen data}}
    with open(OLD_CSV, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            alg = row['algorithm'].strip()
            if alg not in summary:
                summary[alg] = []
            summary[alg].append(row)

    results = {}
    for alg, rows in summary.items():
        last = rows[-1]
        first_feas = None
        for r in rows:
            if r.get('best_f1') and r['best_f1'].strip():
                first_feas = r
                break

        results[alg] = {
            "n_eval_final": int(last.get('n_eval', 0)),
            "best_f1_final": float(last['best_f1']) if last.get('best_f1', '').strip() else None,
            "best_f2_final": float(last['best_f2']) if last.get('best_f2', '').strip() else None,
            "best_f3_final": float(last['best_f3']) if last.get('best_f3', '').strip() else None,
            "n_feasible_final": int(last['n_feasible']) if last.get('n_feasible', '').strip() else 0,
            "best_f1_initial": float(first_feas['best_f1']) if first_feas and first_feas.get('best_f1', '').strip() else None,
            "n_eval_first_feas": int(first_feas['n_eval']) if first_feas else None,
        }
    return results


# ═════════════════════════════════════════════════════════════════════
# TESTE 1: 5 runs NSGA-II NEW + comparação com CSV antigo
# ═════════════════════════════════════════════════════════════════════
def test1():
    print("\n" + "=" * 70)
    print("  TESTE 1 — 5 runs NSGA-II c101_21 (Split relaxado)")
    print("  100k avaliações, pop_size=100")
    print("  Baseline: convergence_log_c101_21_no_ls_100k.csv")
    print("=" * 70)

    ctx = parse_instance(INSTANCE_PATH)
    prob = EVRPTWProblem(ctx, k_max=0)  # sem LS, igual ao baseline CSV
    ensure_dir(RESULTS_DIR)

    # Carregar baseline do CSV
    old_data = load_old_csv_summary()
    print(f"\n  Baseline (CSV antigo, Split dual):")
    for alg, data in old_data.items():
        print(f"    {alg:12s}: f1_final={data['best_f1_final']:.0f}  "
              f"f1_initial={data['best_f1_initial']:.0f}  "
              f"n_feas_final={data['n_feasible_final']}")

    # Rodar NEW
    print(f"\n  ── NEW Split (5 runs NSGA-II) ──")
    all_curves = []
    final_results = []

    for run_i, seed in enumerate(SEEDS):
        cb = ConvergenceTracker(interval=2000)
        alg = NSGA2(pop_size=POP_SIZE, eliminate_duplicates=True, **_ops())
        t0 = time.time()
        res = minimize(prob, alg, ("n_eval", N_EVAL),
                       callback=cb, verbose=False, seed=seed)
        elapsed = time.time() - t0

        cv_arr = res.pop.get("_cv")
        F_real = res.pop.get("_F_real")
        mask = cv_arr[:, 0] <= 1e-9
        n_feas = int(mask.sum())

        if n_feas > 0:
            Ff = F_real[mask]
            best_f1 = float(Ff[:, 0].min())
            best_f2 = float(Ff[:, 1].min())
            best_f3_min = float(Ff[:, 2].min())
            best_f3_max = float(Ff[:, 2].max())
        else:
            best_f1, best_f2, best_f3_min, best_f3_max = np.nan, np.nan, np.nan, np.nan

        # f1 inicial (primeira geração com viáveis)
        first_f1 = None
        first_eval = None
        for e, f1, cv, nf in cb.curve:
            if nf > 0:
                first_f1 = f1
                first_eval = e
                break

        print(f"    Run {run_i+1} (seed={seed}): "
              f"f1_final={best_f1:.0f}  f2={best_f2:.1f}  "
              f"f1_initial={first_f1}  "
              f"viáveis={n_feas}/{len(cv_arr)}  "
              f"min_cv={cv_arr[:, 0].min():.6f}  "
              f"{elapsed:.0f}s")

        final_results.append({
            "seed": seed,
            "best_f1": best_f1,
            "best_f2": best_f2,
            "n_feasible": n_feas,
            "f1_initial": first_f1,
            "first_feas_eval": first_eval,
            "elapsed": round(elapsed, 1),
        })

        all_curves.append(cb.curve)

        # Salvar frente para testes 2, 3
        if n_feas > 0:
            front_data = {
                "F_real": F_real[mask].tolist(),
                "X": res.pop.get("X")[mask].tolist(),
            }
            fpath = os.path.join(RESULTS_DIR, f"front_NEW_seed{seed}.json")
            with open(fpath, "w") as f:
                json.dump(front_data, f)

    # Resumo comparativo
    new_f1s = [r["best_f1"] for r in final_results if not np.isnan(r["best_f1"])]
    new_f1_initials = [r["f1_initial"] for r in final_results if r["f1_initial"] is not None]
    old_nsga = old_data.get("NSGA-II", {})

    print(f"\n  ── COMPARAÇÃO NSGA-II ──")
    print(f"  {'Métrica':<25} {'OLD (CSV)':>15} {'NEW (média)':>15} {'Δ':>10}")
    print(f"  {'-'*65}")
    if old_nsga.get("best_f1_initial"):
        print(f"  {'f1 inicial':<25} {old_nsga['best_f1_initial']:>15.0f} "
              f"{np.mean(new_f1_initials):>15.1f} "
              f"{np.mean(new_f1_initials) - old_nsga['best_f1_initial']:>+10.1f}")
    if old_nsga.get("best_f1_final"):
        print(f"  {'f1 final (best)':<25} {old_nsga['best_f1_final']:>15.0f} "
              f"{np.min(new_f1s):>15.0f} "
              f"{np.min(new_f1s) - old_nsga['best_f1_final']:>+10.0f}")
    print(f"  {'f1 final (avg 5 runs)':<25} {'':>15} {np.mean(new_f1s):>15.1f}")

    # Convergência (amostragem)
    print(f"\n  Convergência média (NEW, 5 runs):")
    print(f"  {'n_eval':>8} {'best_f1':>8} {'min_cv':>10} {'n_feas':>7}")
    print(f"  {'-'*35}")

    all_evals = sorted(set(e for c in all_curves for e, *_ in c))
    for ev in all_evals[::5]:  # every 10k evals
        f1s, cvs, nfs = [], [], []
        for c in all_curves:
            for e, f1, cv, nf in c:
                if e == ev:
                    f1s.append(f1 if not np.isnan(f1) else 0)
                    cvs.append(cv)
                    nfs.append(nf)
                    break
        if f1s:
            f1_str = f"{np.mean(f1s):8.1f}" if any(not np.isnan(f) for f in f1s) else f"{'N/A':>8}"
            print(f"  {ev:>8d} {f1_str} {np.mean(cvs):>10.4f} {np.mean(nfs):>7.1f}")

    # Salvar curvas
    cpath = os.path.join(RESULTS_DIR, "convergence_NEW.json")
    with open(cpath, "w") as f:
        json.dump({"runs": [
            {"seed": s, "curve": c, **r}
            for s, c, r in zip(SEEDS, all_curves, final_results)
        ]}, f, indent=2)


# ═════════════════════════════════════════════════════════════════════
# TESTE 2: Variação de f3 na frente de Pareto
# ═════════════════════════════════════════════════════════════════════
def test2():
    print("\n" + "=" * 70)
    print("  TESTE 2 — Variação de f3 na frente de Pareto (NEW Split)")
    print("=" * 70)

    all_f1, all_f2, all_f3 = [], [], []
    n_loaded = 0

    for seed in SEEDS:
        fpath = os.path.join(RESULTS_DIR, f"front_NEW_seed{seed}.json")
        if not os.path.exists(fpath):
            continue
        with open(fpath) as f:
            data = json.load(f)
        F = np.array(data["F_real"])
        all_f1.extend(F[:, 0].tolist())
        all_f2.extend(F[:, 1].tolist())
        all_f3.extend(F[:, 2].tolist())
        n_loaded += 1

    if not all_f3:
        print("  Sem dados de frente — rode teste 1 primeiro")
        return False

    f1_arr = np.array(all_f1)
    f2_arr = np.array(all_f2)
    f3_arr = np.array(all_f3)

    f3_min, f3_max = f3_arr.min(), f3_arr.max()
    f3_range_pct = (f3_max - f3_min) / f3_min * 100 if f3_min > 0 else 0

    print(f"\n  {n_loaded} runs, {len(all_f3)} soluções viáveis")
    print(f"  f1 range: [{f1_arr.min():.0f}, {f1_arr.max():.0f}]")
    print(f"  f2 range: [{f2_arr.min():.1f}, {f2_arr.max():.1f}]")
    print(f"  f3 range: [{f3_min:.2f}, {f3_max:.2f}]")
    print(f"  f3 variação relativa: {f3_range_pct:.1f}%")

    # Baseline antigo tinha ~6.7% de range em f3
    print(f"\n  Baseline antigo (CSV): f3 range ~6.7%")
    passed = f3_range_pct > 6.7
    print(f"  Critério: f3_range > 6.7% → {'PASSOU' if passed else 'FALHOU'} ({f3_range_pct:.1f}%)")

    if len(all_f3) > 1:
        corr = np.corrcoef(f2_arr, f3_arr)[0, 1]
        print(f"  Correlação f2×f3: {corr:.3f}  "
              f"({'trade-off real' if abs(corr) < 0.95 else 'quase colinear'})")

    # f3 por nível de f1
    distinct_f1 = sorted(set(f1_arr.astype(int)))
    print(f"\n  f3 por nível de f1:")
    for f1_val in distinct_f1[:12]:
        mask = f1_arr == f1_val
        if mask.sum() > 0:
            f3_sub = f3_arr[mask]
            print(f"    f1={int(f1_val):3d}: f3 ∈ [{f3_sub.min():.2f}, {f3_sub.max():.2f}] "
                  f"(n={mask.sum()})")

    return passed


# ═════════════════════════════════════════════════════════════════════
# TESTE 3: Auditor independente em soluções viáveis
# ═════════════════════════════════════════════════════════════════════
def test3():
    print("\n" + "=" * 70)
    print("  TESTE 3 — Auditor independente em soluções viáveis (cv=0)")
    print("=" * 70)

    ctx = parse_instance(INSTANCE_PATH)
    dec = Decoder(ctx)
    auditor = IndependentAuditor(ctx)

    total_checked = 0
    total_pass = 0
    total_fail = 0

    for seed in SEEDS:
        fpath = os.path.join(RESULTS_DIR, f"front_NEW_seed{seed}.json")
        if not os.path.exists(fpath):
            continue
        with open(fpath) as f:
            data = json.load(f)

        X_all = data["X"]
        n_this = 0
        n_fail_this = 0

        for i, perm in enumerate(X_all):
            perm = np.array(perm, dtype=int)
            F, cv, expanded = dec.decode_detailed(perm)

            if cv > 1e-9:
                print(f"  WARNING: seed={seed} sol {i} cv={cv:.4f} (esperado 0)")
                continue

            ok, viols, f1_a, f2_a, f3_a = auditor.audit_solution(expanded)
            total_checked += 1
            n_this += 1

            if ok:
                total_pass += 1
            else:
                total_fail += 1
                n_fail_this += 1
                if n_fail_this <= 3:
                    print(f"  FALHA seed={seed} sol {i}: {viols[:3]}")

        print(f"  seed={seed}: {n_this} verificadas, {n_fail_this} falhas")

    verdict = "PASSOU" if total_fail == 0 else "FALHOU"
    print(f"\n  Total: {total_checked} verificadas, {total_pass} OK, {total_fail} falhas")
    print(f"  Teste 3: {verdict}")
    return total_fail == 0


# ═════════════════════════════════════════════════════════════════════
# TESTE 4: 3 algoritmos, Kruskal-Wallis nos HVs
# ═════════════════════════════════════════════════════════════════════
def test4():
    print("\n" + "=" * 70)
    print("  TESTE 4 — 3 algoritmos × 5 runs, Kruskal-Wallis (Split novo)")
    print("  c101_21, 100k evals")
    print("=" * 70)

    from scipy.stats import kruskal

    ctx = parse_instance(INSTANCE_PATH)
    prob = EVRPTWProblem(ctx, k_max=0)  # sem LS, igual ao baseline CSV

    algo_factories = {
        "NSGA-II": lambda: NSGA2(pop_size=POP_SIZE, eliminate_duplicates=True, **_ops()),
        "MOEA/D":  lambda: MOEAD(_ref_dirs(), n_neighbors=20,
                                  prob_neighbor_mating=0.7, **_ops()),
        "SMS-EMOA": lambda: SMSEMOA(pop_size=POP_SIZE, eliminate_duplicates=True, **_ops()),
    }

    algo_fronts = {}
    ref_point_parts = []

    for alg_name, factory in algo_factories.items():
        print(f"\n  ── {alg_name} ──")
        run_fronts = []
        for run_i, seed in enumerate(SEEDS):
            alg = factory()
            t0 = time.time()
            res = minimize(prob, alg, ("n_eval", N_EVAL), verbose=False, seed=seed)
            elapsed = time.time() - t0

            cv_arr = res.pop.get("_cv")
            F_real = res.pop.get("_F_real")
            mask = cv_arr[:, 0] <= 1e-9
            n_feas = int(mask.sum())

            if n_feas > 0:
                Ff = F_real[mask]
                run_fronts.append(Ff)
                ref_point_parts.append(Ff.max(axis=0))
                print(f"    Run {run_i+1} (seed={seed}): "
                      f"f1={Ff[:, 0].min():.0f}  f2={Ff[:, 1].min():.1f}  "
                      f"viáveis={n_feas}  {elapsed:.0f}s")
            else:
                run_fronts.append(None)
                print(f"    Run {run_i+1} (seed={seed}): "
                      f"SEM VIÁVEIS  min_cv={cv_arr[:, 0].min():.4f}  {elapsed:.0f}s")

        algo_fronts[alg_name] = run_fronts

    # Ref point
    if not ref_point_parts:
        print("\n  Nenhuma solução viável — Teste 4 FALHOU")
        return False

    ref_point = 1.1 * np.vstack(ref_point_parts).max(axis=0)
    indicator = HV(ref_point=ref_point)
    print(f"\n  Ref point: [{ref_point[0]:.1f}, {ref_point[1]:.1f}, {ref_point[2]:.1f}]")

    # HVs
    algo_hvs = {}
    print(f"\n  {'Algo':12s} {'Run1':>8} {'Run2':>8} {'Run3':>8} "
          f"{'Run4':>8} {'Run5':>8} {'Média':>8} {'Std':>8}")
    print(f"  {'-'*68}")

    for alg_name in algo_factories:
        fronts = algo_fronts[alg_name]
        hvs = []
        for f in fronts:
            if f is not None:
                hvs.append(float(indicator.do(f)))
            else:
                hvs.append(0.0)
        algo_hvs[alg_name] = hvs

        hv_strs = [f"{h:>8.1f}" for h in hvs]
        print(f"  {alg_name:12s} {''.join(hv_strs)} {np.mean(hvs):>8.1f} {np.std(hvs):>8.1f}")

    # Kruskal-Wallis
    hv_groups = list(algo_hvs.values())
    stat, pvalue = kruskal(*hv_groups)
    print(f"\n  Kruskal-Wallis: H={stat:.4f}  p-value={pvalue:.6f}")
    if pvalue < 0.05:
        print(f"  → Diferença SIGNIFICATIVA (p < 0.05)")
    else:
        print(f"  → Diferença NÃO significativa (p ≥ 0.05)")

    # Comparar com baseline
    old_data = load_old_csv_summary()
    print(f"\n  Comparação f1 final (best) por algoritmo:")
    print(f"  {'Algo':12s} {'OLD (CSV)':>12} {'NEW (best)':>12} {'Δ':>8}")
    print(f"  {'-'*44}")
    for alg_name in algo_factories:
        old_f1 = old_data.get(alg_name, {}).get("best_f1_final")
        fronts = algo_fronts[alg_name]
        new_f1s = [float(f[:, 0].min()) for f in fronts if f is not None]
        new_best = min(new_f1s) if new_f1s else float('nan')
        old_str = f"{old_f1:.0f}" if old_f1 else "N/A"
        delta = f"{new_best - old_f1:+.0f}" if old_f1 and not np.isnan(new_best) else "N/A"
        print(f"  {alg_name:12s} {old_str:>12} {new_best:>12.0f} {delta:>8}")

    # Salvar
    rpath = os.path.join(RESULTS_DIR, "test4_results.json")
    with open(rpath, "w") as f:
        json.dump({
            "algo_hvs": algo_hvs,
            "ref_point": ref_point.tolist(),
            "kruskal_h": float(stat),
            "kruskal_p": float(pvalue),
        }, f, indent=2)

    return pvalue < 0.05


# ═════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════
def main():
    import argparse
    ap = argparse.ArgumentParser(description="Testes do Split DP relaxado")
    ap.add_argument("--tests", nargs="*", type=int, default=[1, 2, 3],
                    help="Testes a executar (1-4). Default: 1, 2, 3")
    args = ap.parse_args()

    print("=" * 70)
    print("  TESTES DO SPLIT DP RELAXADO")
    print(f"  Testes selecionados: {args.tests}")
    print("=" * 70)

    ensure_dir(RESULTS_DIR)
    t_total = time.time()
    results = {}

    for t in args.tests:
        t0 = time.time()
        if t == 1:
            test1()
            results[1] = True
        elif t == 2:
            results[2] = test2()
        elif t == 3:
            results[3] = test3()
        elif t == 4:
            results[4] = test4()
        print(f"\n  (teste {t} concluído em {time.time()-t0:.0f}s)")

    print(f"\n{'=' * 70}")
    print(f"  CONCLUSÃO  ({time.time()-t_total:.0f}s total)")
    print(f"{'=' * 70}")
    for t, ok in results.items():
        label = "PASSOU" if ok else "REQUER ATENÇÃO"
        print(f"  Teste {t}: {label}")


if __name__ == "__main__":
    main()
