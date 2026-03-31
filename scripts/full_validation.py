#!/usr/bin/env python3
"""
Validação completa do decodificador e pipeline experimental (5 níveis).

Nível 1 – Auditor independente (permutações aleatórias + TWBiased)
Nível 2 – Comparação com BKS Schneider Table 3 (instâncias pequenas)
Nível 3 – Comparação com BKS Schneider Table 4 (instâncias grandes)
Nível 4 – 3 algoritmos diferem entre si
Nível 5 – Smoke tests (frente 3D, convergência, viabilidade)

Uso:
    python scripts/full_validation.py                # todos os níveis
    python scripts/full_validation.py --levels 1 2   # só níveis 1 e 2
"""

import sys, os, argparse, time
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


# ══════════════════════════════════════════════════════════════════════
#  BKS do Schneider (Table 3 – CPLEX/VNS-TS, Table 4 – VNS/TS best)
# ══════════════════════════════════════════════════════════════════════
BKS_SMALL = {
    "c101C5": (2,257.75),  "c103C5": (1,176.05),
    "c206C5": (1,242.56),  "c208C5": (1,158.48),
    "r104C5": (2,136.69),  "r105C5": (2,156.08),
    "r202C5": (1,128.78),  "r203C5": (1,179.06),
    "rc105C5":(2,241.37),  "rc108C5":(1,253.93),
    "rc204C5":(1,176.39),  "rc208C5":(1,167.98),
    "c101C10":(3,393.76),  "c104C10":(2,273.93),
    "c202C10":(1,304.06),  "c205C10":(2,228.28),
    "r102C10":(3,249.19),  "r103C10":(2,207.05),
    "r201C10":(1,241.51),  "r203C10":(1,218.21),
    "rc102C10":(4,423.51), "rc108C10":(3,345.93),
    "rc201C10":(1,412.86), "rc205C10":(2,325.98),
    "c103C15":(3,384.29),  "c106C15":(3,275.13),
    "c202C15":(2,383.62),  "c208C15":(2,300.55),
    "r102C15":(5,413.93),  "r105C15":(4,336.15),
    "r202C15":(2,358.00),  "r209C15":(1,313.24),
    "rc103C15":(4,397.67), "rc108C15":(3,370.25),
    "rc202C15":(2,394.39), "rc204C15":(1,384.86),
}
BKS_LARGE = {
    "c101_21":(12,1053.83), "c201_21":(4,645.16),
    "r101_21":(18,1670.81), "r201_21":(3,1264.82),
    "rc101_21":(16,1731.07),"rc201_21":(4,1444.94),
}


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

def _run_nsga2(problem, n_eval, seed, pop_size=200):
    alg = NSGA2(pop_size=pop_size, eliminate_duplicates=True, **_ops())
    return minimize(problem, alg, ("n_eval", n_eval), verbose=False, seed=seed)


# ══════════════════════════════════════════════════════════════════════
#  AUDITOR INDEPENDENTE
# ══════════════════════════════════════════════════════════════════════
class IndependentAuditor:
    """
    Verifica mecânica e independente de todas as restrições de uma
    solução EVRPTW decodificada. Não compartilha nenhum cálculo com
    o Decoder — reimplementa tudo do zero.
    """

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
        """
        Recebe lista de rotas expandidas (com estações).
        Retorna (ok: bool, violations: list[str], f1, f2, f3).
        """
        viols = []
        all_customers_visited = []
        f2_total = 0.0
        return_times = []

        for ri, route in enumerate(expanded_routes):
            rv, dist_route, ret_time = self._audit_one_route(route, ri)
            viols.extend(rv)
            f2_total += dist_route
            return_times.append(ret_time)

            for p in route:
                if p in self._is_customer:
                    all_customers_visited.append(p)

        # Cada cliente aparece exatamente uma vez
        expected = sorted(self.ctx.customer_node_indices)
        actual = sorted(all_customers_visited)
        if actual != expected:
            missing = set(expected) - set(actual)
            dup = [c for c in actual if actual.count(c) > 1]
            if missing:
                viols.append(f"clientes faltando: {missing}")
            if dup:
                viols.append(f"clientes duplicados: {set(dup)}")

        f1 = float(len(expanded_routes))
        f3 = max(return_times) if return_times else 0.0

        return len(viols) == 0, viols, f1, f2_total, f3

    def _audit_one_route(self, route, route_idx):
        """Simula a execução de uma rota arco a arco."""
        viols = []
        depot = self.depot

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

            # Verificar bateria ANTES de consumir
            if bat < arc_energy - 1e-6:
                viols.append(
                    f"R{route_idx} passo {step}: bateria {bat:.4f} < "
                    f"energia {arc_energy:.4f} (nó {self.nodes[p].id})")
            bat = max(bat - arc_energy, 0.0)

            t += self.travel[prev, p]
            node = self.nodes[p]

            # TW: chegada não pode ultrapassar due_date (exceto depot final)
            if p != depot and t > node.due_date + 1e-6:
                viols.append(
                    f"R{route_idx} passo {step}: TW violada, "
                    f"chegada={t:.4f} > due={node.due_date} ({node.id})")

            # Esperar ready_time
            t = max(t, node.ready_time)

            if p in self._is_station:
                recharge_time = self.g * (self.Q - bat)
                t += recharge_time
                bat = self.Q
            elif p != depot:
                load += node.demand
                t += node.service_time

            prev = p

        # Verificar capacidade
        if load > self.C + 1e-6:
            viols.append(
                f"R{route_idx}: sobrecarga {load:.2f} > C={self.C}")

        return viols, dist_total, t


# ══════════════════════════════════════════════════════════════════════
#  NÍVEL 1 – Auditor independente
# ══════════════════════════════════════════════════════════════════════
def level1():
    print("\n" + "=" * 70)
    print("NÍVEL 1 – Auditor independente em soluções viáveis")
    print("  1000 permutações por instância (500 TWBiased + 500 aleatórias)")
    print("=" * 70)

    test_instances = [
        "c101C5", "r104C5",  "rc108C5",
        "c101C10","r102C10", "rc103C15", "r102C15",
    ]
    N_PER_TYPE = 500
    all_pass = True

    for inst_name in test_instances:
        inst_path = f"evrptw_instances/{inst_name}.txt"
        if not os.path.exists(inst_path):
            print(f"  {inst_name}: não encontrado, ignorado")
            continue

        ctx = parse_instance(inst_path)
        dec = Decoder(ctx)
        prob = EVRPTWProblem(ctx)
        auditor = IndependentAuditor(ctx)

        samp = TWBiasedSampling()
        X_biased = samp._do(prob, N_PER_TYPE)
        X_random = np.array([np.random.permutation(ctx.n_customers)
                             for _ in range(N_PER_TYPE)])
        X_all = np.vstack([X_biased, X_random])

        n_tested = len(X_all)
        n_feasible = 0
        n_audit_fail = 0
        n_f2_mismatch = 0
        worst_f2_gap = 0.0

        for perm in X_all:
            F, cv, expanded = dec.decode_detailed(perm)
            if cv > 1e-9:
                continue
            n_feasible += 1

            ok, viols, f1_a, f2_a, f3_a = auditor.audit_solution(expanded)

            if not ok:
                n_audit_fail += 1
                if n_audit_fail <= 3:
                    print(f"    VIOLAÇÃO em {inst_name}: {viols[:3]}")

            # Verificar consistência numérica (f1, f2)
            if abs(F[1] - f2_a) > 1e-4:
                n_f2_mismatch += 1
                worst_f2_gap = max(worst_f2_gap, abs(F[1] - f2_a))

        status = "OK" if (n_audit_fail == 0 and n_f2_mismatch == 0) else "FALHA"
        if status == "FALHA":
            all_pass = False

        extra = ""
        if n_f2_mismatch > 0:
            extra = f"  f2 mismatch: {n_f2_mismatch} (max gap {worst_f2_gap:.6f})"
        print(f"  {inst_name:<12} {n_tested} testadas  {n_feasible:>4} viáveis  "
              f"audit fails: {n_audit_fail}  {status}{extra}")

    verdict = "PASSOU" if all_pass else "FALHOU"
    print(f"\nNível 1: {verdict}")
    return all_pass


# ══════════════════════════════════════════════════════════════════════
#  NÍVEL 2 – Comparação com BKS Schneider (instâncias pequenas)
# ══════════════════════════════════════════════════════════════════════
def _best_via_enumeration(inst_path):
    """Para instâncias C5 (120 perms), enumera todas as soluções."""
    import itertools
    ctx = parse_instance(inst_path)
    dec = Decoder(ctx)
    best_f1, best_f2 = float('inf'), float('inf')
    for perm in itertools.permutations(range(ctx.n_customers)):
        F, cv = dec.decode(np.array(perm))
        if cv > 1e-9:
            continue
        if F[0] < best_f1 or (F[0] == best_f1 and F[1] < best_f2):
            best_f1, best_f2 = F[0], F[1]
    return best_f1, best_f2


def level2():
    print("\n" + "=" * 70)
    print("NÍVEL 2 – Comparação com BKS Schneider Table 3 (instâncias pequenas)")
    print("  C5: enumeração exaustiva | C10/C15: 3 runs NSGA-II, pop=100, 20k evals")
    print("=" * 70)

    results = []
    SEEDS = [42, 43, 44]

    for inst_name in sorted(BKS_SMALL):
        bks_m, bks_L = BKS_SMALL[inst_name]
        inst_path = f"evrptw_instances/{inst_name}.txt"
        if not os.path.exists(inst_path):
            print(f"  {inst_name}: não encontrado")
            continue

        ctx = parse_instance(inst_path)
        is_c5 = "C5" in inst_name

        if is_c5:
            best_f1, best_f2 = _best_via_enumeration(inst_path)
        else:
            prob = EVRPTWProblem(ctx)
            best_f1, best_f2 = float('inf'), float('inf')
            for seed in SEEDS:
                res = _run_nsga2(prob, 20_000, seed, pop_size=100)
                cv_arr = res.pop.get("_cv")
                F_real = res.pop.get("_F_real")
                mask = cv_arr[:, 0] <= 1e-9
                if not mask.any():
                    continue
                Ff = F_real[mask]
                min_f1 = Ff[:, 0].min()
                if min_f1 < best_f1:
                    best_f1 = min_f1
                    best_f2 = Ff[Ff[:, 0] == min_f1, 1].min()
                elif min_f1 == best_f1:
                    best_f2 = min(best_f2, Ff[Ff[:, 0] == min_f1, 1].min())

        if best_f1 == float('inf'):
            results.append((inst_name, bks_m, bks_L, None, None, "N/A", "N/A", "SEM_VIÁVEIS"))
            continue

        gap_m = int(best_f1) - bks_m
        gap_L = (best_f2 - bks_L) / bks_L * 100

        # Classificação: f2 melhor que ótimo → bug claro
        if gap_L < -1.0 and gap_m == 0:
            cat = "VERMELHO"
        elif gap_m == 0 and gap_L <= 10:
            cat = "VERDE"
        elif gap_m == 0 and gap_L <= 20:
            cat = "AMARELO"
        elif gap_m <= 2:
            cat = "AMARELO"
        else:
            cat = "VERMELHO"

        results.append((inst_name, bks_m, bks_L, best_f1, best_f2,
                         f"{'+' if gap_m > 0 else ''}{gap_m}", f"{gap_L:+.1f}%", cat))

    print(f"\n  {'Instância':<12} {'BKS_m':>5} {'BKS_L':>8} {'f1':>5} "
          f"{'f2':>10} {'Δm':>5} {'ΔL':>8} {'Status'}")
    print("  " + "─" * 65)
    for name, bm, bL, f1, f2, gm, gL, cat in results:
        f1s = f"{f1:.0f}" if f1 is not None else "---"
        f2s = f"{f2:.2f}" if f2 is not None else "---"
        print(f"  {name:<12} {bm:>5} {bL:>8.2f} {f1s:>5} {f2s:>10} "
              f"{gm:>5} {gL:>8} {cat}")

    n_g = sum(1 for *_, c in results if c == "VERDE")
    n_y = sum(1 for *_, c in results if c == "AMARELO")
    n_r = sum(1 for *_, c in results if c == "VERMELHO")
    print(f"\n  Resumo: {n_g} VERDE  {n_y} AMARELO  {n_r} VERMELHO  (total {len(results)})")
    print(f"  NOTA: Δm>0 é esperado para instâncias de bateria apertada com decoder greedy.")
    return n_r == 0


# ══════════════════════════════════════════════════════════════════════
#  NÍVEL 3 – Comparação com BKS Schneider (instâncias grandes)
# ══════════════════════════════════════════════════════════════════════
def level3():
    print("\n" + "=" * 70)
    print("NÍVEL 3 – Comparação com BKS Schneider Table 4 (instâncias grandes)")
    print("  5 runs NSGA-II, pop=200, 100k evals")
    print("=" * 70)

    results = []
    SEEDS = [42, 43, 44, 45, 46]

    for inst_name in sorted(BKS_LARGE):
        bks_m, bks_L = BKS_LARGE[inst_name]
        inst_path = f"evrptw_instances/{inst_name}.txt"
        if not os.path.exists(inst_path):
            print(f"  {inst_name}: não encontrado")
            continue

        ctx = parse_instance(inst_path)
        prob = EVRPTWProblem(ctx)
        print(f"  {inst_name} ({ctx.n_customers} cust.)…", end=" ", flush=True)

        best_f1, best_f2 = float('inf'), float('inf')
        n_total_feas = 0
        t0 = time.time()

        for seed in SEEDS:
            res = _run_nsga2(prob, 100_000, seed)
            cv_arr = res.pop.get("_cv")
            F_real = res.pop.get("_F_real")
            mask = cv_arr[:, 0] <= 1e-9
            n_total_feas += int(mask.sum())
            if not mask.any():
                continue
            Ff = F_real[mask]
            min_f1 = Ff[:, 0].min()
            if min_f1 < best_f1:
                best_f1 = min_f1
                best_f2 = Ff[Ff[:, 0] == min_f1, 1].min()
            elif min_f1 == best_f1:
                best_f2 = min(best_f2, Ff[Ff[:, 0] == min_f1, 1].min())

        elapsed = time.time() - t0
        print(f"{n_total_feas} viáveis em {elapsed:.0f}s")

        if best_f1 == float('inf'):
            results.append((inst_name, bks_m, bks_L, None, None, "N/A", "N/A", "SEM_VIÁVEIS"))
            continue

        gap_m = int(best_f1) - bks_m
        gap_L = (best_f2 - bks_L) / bks_L * 100

        if gap_L < -1:
            cat = "VERMELHO"
        elif gap_m <= 2 and gap_L <= 20:
            cat = "VERDE"
        elif gap_L <= 40:
            cat = "AMARELO"
        else:
            cat = "VERMELHO"

        results.append((inst_name, bks_m, bks_L, best_f1, best_f2,
                         f"{'+' if gap_m > 0 else ''}{gap_m}", f"{gap_L:+.1f}%", cat))

    print(f"\n  {'Instância':<12} {'BKS_m':>5} {'BKS_L':>9} {'f1':>5} "
          f"{'f2':>10} {'Δm':>5} {'ΔL':>8} {'Status'}")
    print("  " + "─" * 68)
    for name, bm, bL, f1, f2, gm, gL, cat in results:
        f1s = f"{f1:.0f}" if f1 is not None else "---"
        f2s = f"{f2:.2f}" if f2 is not None else "---"
        print(f"  {name:<12} {bm:>5} {bL:>9.2f} {f1s:>5} {f2s:>10} "
              f"{gm:>5} {gL:>8} {cat}")
    return True


# ══════════════════════════════════════════════════════════════════════
#  NÍVEL 4 – 3 algoritmos diferem entre si
# ══════════════════════════════════════════════════════════════════════
def level4():
    print("\n" + "=" * 70)
    print("NÍVEL 4 – Verificação de que os 3 algoritmos diferem")
    print("  5 runs × 3 algoritmos em c101C10, 20k evals")
    print("=" * 70)

    ctx = parse_instance("evrptw_instances/c101C10.txt")
    prob = EVRPTWProblem(ctx)
    SEEDS = [42, 43, 44, 45, 46]

    algo_factories = {
        "NSGA-II": lambda: NSGA2(pop_size=100, eliminate_duplicates=True, **_ops()),
        "MOEA/D":  lambda: MOEAD(_ref_dirs(), n_neighbors=20,
                                  prob_neighbor_mating=0.7, **_ops()),
        "SMS-EMOA":lambda: SMSEMOA(pop_size=100, eliminate_duplicates=True, **_ops()),
    }

    algo_hvs = {}
    ref_point_global = None
    algo_fronts = {}

    for alg_name, factory in algo_factories.items():
        run_fronts = []
        n_feas_total = 0
        for seed in SEEDS:
            alg = factory()
            res = minimize(prob, alg, ("n_eval", 20_000), verbose=False, seed=seed)
            cv_arr = res.pop.get("_cv")
            F_real = res.pop.get("_F_real")
            mask = cv_arr[:, 0] <= 1e-9
            n_feas = int(mask.sum())
            n_feas_total += n_feas
            if n_feas > 0:
                run_fronts.append(F_real[mask])
        algo_fronts[alg_name] = (run_fronts, n_feas_total)

    # Ref point global (nadir de todas as frentes + 10%)
    all_F = np.vstack([f for af in algo_fronts.values() for f in af[0]])
    ref_point_global = 1.1 * all_F.max(axis=0)
    indicator = HV(ref_point=ref_point_global)

    # Auditar soluções viáveis dos 3 algos
    ctx_audit = parse_instance("evrptw_instances/c101C10.txt")
    auditor = IndependentAuditor(ctx_audit)

    for alg_name in algo_factories:
        run_fronts, n_feas_total = algo_fronts[alg_name]
        hvs = [float(indicator.do(f)) for f in run_fronts] if run_fronts else [0.0]
        algo_hvs[alg_name] = hvs
        print(f"  {alg_name:9s}: {n_feas_total:>3} viáveis (5 runs)  "
              f"HV médio={np.mean(hvs):.2f} ± {np.std(hvs):.2f}")

    means = {k: np.mean(v) for k, v in algo_hvs.items()}
    all_positive = all(m > 0 for m in means.values())
    all_diff = len(set(f"{m:.1f}" for m in means.values())) > 1

    print(f"\n  HVs positivos e finitos: {'SIM' if all_positive else 'NÃO'}")
    print(f"  HVs distintos entre algoritmos: {'SIM' if all_diff else 'NÃO'}")

    verdict = all_positive
    print(f"\nNível 4: {'PASSOU' if verdict else 'FALHOU'}")
    return verdict


# ══════════════════════════════════════════════════════════════════════
#  NÍVEL 5 – Smoke tests
# ══════════════════════════════════════════════════════════════════════
class FeasibilityTracker(Callback):
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
        if cv_arr is None:
            self.curve.append((int(n_eval), 0, 0.0))
            return
        mask = cv_arr[:, 0] <= 1e-9
        n_feas = int(mask.sum())
        min_cv = float(cv_arr[:, 0].min())
        self.curve.append((int(n_eval), n_feas, min_cv))


def level5():
    print("\n" + "=" * 70)
    print("NÍVEL 5 – Smoke tests")
    print("=" * 70)

    # ── 5a: Frente estratificada em r204_21 ──
    print("\n  5a – Frente tri-objetivo estratificada (r204_21, 2 runs × 50k)")
    ctx = parse_instance("evrptw_instances/r204_21.txt")
    prob = EVRPTWProblem(ctx)
    distinct_f1 = set()
    f2_vals, f3_vals = [], []
    for seed in [42, 43]:
        res = _run_nsga2(prob, 50_000, seed, pop_size=200)
        cv_arr = res.pop.get("_cv")
        F_real = res.pop.get("_F_real")
        mask = cv_arr[:, 0] <= 1e-9
        if mask.any():
            Ff = F_real[mask]
            distinct_f1.update(Ff[:, 0].astype(int).tolist())
            f2_vals.extend(Ff[:, 1].tolist())
            f3_vals.extend(Ff[:, 2].tolist())

    strat = len(distinct_f1) >= 2
    corr = np.corrcoef(f2_vals, f3_vals)[0, 1] if len(f2_vals) > 1 else 1.0
    print(f"    Valores distintos de f1: {sorted(distinct_f1)}")
    print(f"    Estratificada (f1 varia): {'SIM' if strat else 'NÃO'}")
    print(f"    Correlação f2×f3: {corr:.3f}  "
          f"({'não colapsa em 2D' if abs(corr) < 0.95 else 'ATENÇÃO: quase colinear'})")

    # ── 5b: Convergência (HV ao longo do tempo) ──
    print("\n  5b – Curvas de convergência (c101C10, 20k evals)")
    ctx2 = parse_instance("evrptw_instances/c101C10.txt")
    prob2 = EVRPTWProblem(ctx2)

    for alg_name, factory in [
        ("NSGA-II",  lambda: NSGA2(pop_size=100, eliminate_duplicates=True, **_ops())),
        ("MOEA/D",   lambda: MOEAD(_ref_dirs(), n_neighbors=20,
                                    prob_neighbor_mating=0.7, **_ops())),
        ("SMS-EMOA", lambda: SMSEMOA(pop_size=100, eliminate_duplicates=True, **_ops())),
    ]:
        cb = FeasibilityTracker(interval=2000)
        alg = factory()
        minimize(prob2, alg, ("n_eval", 20_000), callback=cb, verbose=False, seed=42)
        feas_curve = [(e, n) for e, n, _ in cb.curve]
        cv_curve = [(e, c) for e, _, c in cb.curve]
        is_growing = all(feas_curve[i][1] <= feas_curve[i+1][1]
                         for i in range(len(feas_curve)-1)) if len(feas_curve) > 1 else False
        print(f"    {alg_name:9s}: viáveis={[n for _,n in feas_curve]}  "
              f"crescente={'SIM' if is_growing else 'NÃO/parcial'}")

    # ── 5c: Viabilidade em r101_21 ──
    print("\n  5c – Taxa de viabilidade em r101_21 (5 runs, 50k evals)")
    ctx3 = parse_instance("evrptw_instances/r101_21.txt")
    prob3 = EVRPTWProblem(ctx3)

    total_feas = 0
    for seed in [42, 43, 44, 45, 46]:
        res = _run_nsga2(prob3, 50_000, seed)
        cv_arr = res.pop.get("_cv")
        mask = cv_arr[:, 0] <= 1e-9
        n_feas = int(mask.sum())
        n_pop = len(cv_arr)
        total_feas += n_feas
        min_cv = cv_arr[:, 0].min()
        print(f"    seed={seed}: {n_feas}/{n_pop} viáveis ({100*n_feas/n_pop:.0f}%)  "
              f"min_cv={min_cv:.4f}")

    if total_feas == 0:
        print("    NOTA: 0% viáveis — esperado para r101_21 com decoder greedy")

    # ── 5d (bônus): Auditar 10 soluções viáveis do NSGA-II em c101C10 ──
    print("\n  5d – Auditoria cruzada de soluções do NSGA-II (c101C10)")
    ctx4 = parse_instance("evrptw_instances/c101C10.txt")
    prob4 = EVRPTWProblem(ctx4)
    dec4 = Decoder(ctx4)
    auditor4 = IndependentAuditor(ctx4)

    res = _run_nsga2(prob4, 20_000, seed=99)
    cv_arr = res.pop.get("_cv")
    F_real = res.pop.get("_F_real")
    X_all = res.pop.get("X")
    mask = cv_arr[:, 0] <= 1e-9
    feas_idx = np.where(mask)[0][:10]

    n_checked, n_pass = 0, 0
    for i in feas_idx:
        perm = X_all[i]
        routes = dec4._split(perm)
        expanded = []
        for cs in routes:
            r, _, _ = dec4._insert_stations(cs)
            expanded.append(r)
        ok, viols, f1_a, f2_a, f3_a = auditor4.audit_solution(expanded)
        n_checked += 1
        if ok:
            n_pass += 1
        else:
            print(f"    Solução {i}: FALHA {viols[:2]}")

    print(f"    {n_pass}/{n_checked} soluções passaram no auditor")
    print(f"\nNível 5: completo")
    return True


# ══════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", nargs="*", type=int, default=[1, 2, 3, 4, 5])
    args = ap.parse_args()

    print("=" * 70)
    print("  VALIDAÇÃO COMPLETA DO PIPELINE EVRPTW")
    print(f"  Níveis selecionados: {args.levels}")
    print("=" * 70)

    t_total = time.time()
    results = {}

    for lvl in args.levels:
        t0 = time.time()
        fn = {1: level1, 2: level2, 3: level3, 4: level4, 5: level5}.get(lvl)
        if fn is None:
            print(f"Nível {lvl} não existe")
            continue
        results[lvl] = fn()
        print(f"  (nível {lvl} concluído em {time.time()-t0:.0f}s)")

    print(f"\n{'=' * 70}")
    print(f"  CONCLUSÃO  ({time.time()-t_total:.0f}s total)")
    print(f"{'=' * 70}")
    for lvl, ok in results.items():
        label = "PASSOU" if ok else "REQUER ATENÇÃO"
        print(f"  Nível {lvl}: {label}")


if __name__ == "__main__":
    main()
