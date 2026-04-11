#!/usr/bin/env python3
"""
validation_audit_ws.py
=======================
Script 1 — Validação técnica via auditor independente (C9 e C11)

Verifica que as soluções produzidas pelas configurações Weighted Sum
(C9: n_neighbors=10 e C11: n_neighbors=5) são fisicamente válidas.

Contexto:
  Os pickles do experimento de tuning contêm apenas vetores de objetivos
  (numpy array [f1, f2, f3]), NÃO as permutações. Por isso o script
  re-executa C9 e C11 com as mesmas seeds determinísticas e um número
  menor de avaliações (default 10k — rápido, ~2 min) para coletar as
  permutações da população final.

Checagens por solução viável (cv=0):
  1. Auditor independente não reporta nenhuma violação hard
     (bateria, capacidade, clientes duplicados/faltando)
  2. f1, f2, f3 do decoder == auditor (tolerância 1e-6)
  3. f3 (atrasos TW) do auditor == f3 do decoder (tolerância 1e-5)

Interpretação:
  Zero violações + zero discrepâncias → HV alto de C9/C11 é legítimo
  Alguma violação/discrepância → bug ou constraint silenciosa → investigar

Uso:
  python scripts/validation_audit_ws.py                # 10k evals, ~2min
  python scripts/validation_audit_ws.py --n-evals 300000  # reproduz experimento
  python scripts/validation_audit_ws.py --n-evals 50000 --paralelo  # debug rápido
"""

import os, sys, time, csv, json, argparse, warnings, hashlib
from datetime import datetime

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Configurações das instâncias usadas no tuning
# (mesmas sementes determinísticas do moead_tuning.py)
# ─────────────────────────────────────────────────────────────────────────────
INSTANCES = {
    "c101_21": os.path.join(ROOT, "evrptw_instances", "c101_21.txt"),
    "c208_21": os.path.join(ROOT, "evrptw_instances", "c208_21.txt"),
    "r106_21": os.path.join(ROOT, "evrptw_instances", "r106_21.txt"),
    "r201_21": os.path.join(ROOT, "evrptw_instances", "r201_21.txt"),
}

# Configurações a auditar (Weighted Sum)
CONFIGS_TO_AUDIT = [
    ("C9",  10, 0.9, "weighted-sum", None),  # n_neigh, prob, decomp, theta
    ("C11",  5, 0.9, "weighted-sum", None),
]

N_RUNS = 4       # igual ao experimento de tuning
POP_SIZE = 105   # Das-Dennis, 3 obj, n_partitions=13


def _deterministic_seed(config_id: str, instance_name: str, run_idx: int) -> int:
    key = f"{config_id}_{instance_name}_{run_idx}"
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2 ** 32)


def _get_ref_dirs():
    try:
        from pymoo.util.ref_dirs import get_reference_directions
    except ImportError:
        from pymoo.util.reference_direction import get_reference_directions
    return get_reference_directions("das-dennis", 3, n_partitions=13)


def _build_moead(n_neighbors, prob, decomp, theta, ref_dirs, ops):
    from pymoo.algorithms.moo.moead import MOEAD
    kwargs = dict(ref_dirs=ref_dirs, n_neighbors=n_neighbors,
                  prob_neighbor_mating=prob, **ops)
    if decomp == "weighted-sum":
        from pymoo.decomposition.weighted_sum import WeightedSum
        kwargs["decomposition"] = WeightedSum()
    elif decomp == "pbi":
        from pymoo.decomposition.pbi import PBI
        kwargs["decomposition"] = PBI(theta=theta)
    return MOEAD(**kwargs)


def audit_run(ctx, problem, decoder, auditor, config_id, inst_name,
              run_idx, n_evals, verbose=False):
    """
    Executa uma run de MOEA/D com a config especificada,
    audita cada solução viável da população final.
    Retorna dict com resultados de auditoria.
    """
    from pymoo.optimize import minimize
    from pymoo.operators.crossover.ox import OrderCrossover
    from pymoo.operators.mutation.inversion import InversionMutation
    from src import TWBiasedSampling

    cid, n_neigh, prob, decomp, theta = (config_id, *[None]*4)
    for c in CONFIGS_TO_AUDIT:
        if c[0] == config_id:
            _, n_neigh, prob, decomp, theta = c

    seed = _deterministic_seed(config_id, inst_name, run_idx)
    ref_dirs = _get_ref_dirs()
    ops = dict(sampling=TWBiasedSampling(),
               crossover=OrderCrossover(),
               mutation=InversionMutation())

    alg = _build_moead(n_neigh, prob, decomp, theta, ref_dirs, ops)

    t0 = time.perf_counter()
    res = minimize(problem, alg, ("n_eval", n_evals), verbose=False, seed=seed)
    elapsed = time.perf_counter() - t0

    # Coleta população
    X_all    = res.pop.get("X")          # permutações (n_pop, n_var)
    cv_arr   = res.pop.get("_cv")        # (n_pop, 1)
    F_real   = res.pop.get("_F_real")    # (n_pop, 3)

    if X_all is None or cv_arr is None:
        return {"error": "pop vazia", "config_id": config_id,
                "instance": inst_name, "run_idx": run_idx}

    n_total  = len(X_all)
    mask_feas = cv_arr[:, 0] <= 1e-9
    n_feas   = int(mask_feas.sum())

    results_per_sol = []
    violations_hard  = 0
    obj_discrepancies = 0
    n_audited = 0

    for i in np.where(mask_feas)[0]:
        perm = X_all[i].astype(int)
        F_dec, cv_dec, expanded = decoder.decode_detailed(perm)

        n_audited += 1
        ok, viols, f1_a, f2_a, f3_a = auditor.audit_solution(expanded)

        # Filtra violações soft de TW (são aceitas — f3 as captura)
        hard_viols = [v for v in viols if "TW violada" not in v]

        has_hard_viol = len(hard_viols) > 0
        match_f1 = abs(F_dec[0] - f1_a) < 1e-6
        match_f2 = abs(F_dec[1] - f2_a) < 1e-6
        match_f3 = abs(F_dec[2] - f3_a) < 1e-5

        if has_hard_viol:
            violations_hard += 1
        if not (match_f1 and match_f2 and match_f3):
            obj_discrepancies += 1

        if (has_hard_viol or not (match_f1 and match_f2 and match_f3)) and verbose:
            print(f"    !!  {config_id}/{inst_name}/run{run_idx}/sol{i}")
            if has_hard_viol:
                print(f"        HARD VIOLS: {hard_viols[:3]}")
            if not match_f1:
                print(f"        f1: dec={F_dec[0]:.4f} audit={f1_a:.4f}")
            if not match_f2:
                print(f"        f2: dec={F_dec[1]:.4f} audit={f2_a:.4f}")
            if not match_f3:
                print(f"        f3: dec={F_dec[2]:.6f} audit={f3_a:.6f}")

        results_per_sol.append({
            "sol_idx":          int(i),
            "cv_dec":           float(cv_dec),
            "f1_dec":           float(F_dec[0]),
            "f2_dec":           float(F_dec[1]),
            "f3_dec":           float(F_dec[2]),
            "f1_aud":           float(f1_a),
            "f2_aud":           float(f2_a),
            "f3_aud":           float(f3_a),
            "has_hard_viol":    has_hard_viol,
            "hard_viols":       hard_viols[:5],
            "match_f1":         bool(match_f1),
            "match_f2":         bool(match_f2),
            "match_f3":         bool(match_f3),
        })

    return {
        "config_id":        config_id,
        "instance":         inst_name,
        "run_idx":          run_idx,
        "seed":             seed,
        "n_evals":          n_evals,
        "elapsed_s":        round(elapsed, 2),
        "n_total_pop":      n_total,
        "n_feasible":       n_feas,
        "n_audited":        n_audited,
        "violations_hard":  violations_hard,
        "obj_discrepancies": obj_discrepancies,
        "passed":           (violations_hard == 0 and obj_discrepancies == 0),
        "solutions":        results_per_sol,
    }


def main():
    ap = argparse.ArgumentParser(description="Auditoria das configs Weighted Sum (C9, C11)")
    ap.add_argument("--n-evals", type=int, default=10_000,
                    help="Avaliações por run (padrão 10k = rápido ~2min; "
                         "usa 300000 para reproduzir experimento)")
    ap.add_argument("--configs", nargs="+", default=["C9", "C11"],
                    help="Configs a auditar (padrão: C9 C11)")
    ap.add_argument("--instances", nargs="+", default=None,
                    help="Instâncias (padrão: todas as 4 do tuning)")
    ap.add_argument("--runs", type=int, default=N_RUNS,
                    help=f"Runs por (config, instância) (padrão: {N_RUNS})")
    ap.add_argument("--verbose", action="store_true",
                    help="Imprime detalhes de cada discrepância")
    args = ap.parse_args()

    from src import parse_instance, EVRPTWProblem, Decoder
    from tests.test_relaxed_split import IndependentAuditor

    active_configs  = [c for c in CONFIGS_TO_AUDIT if c[0] in args.configs]
    active_instances = {k: v for k, v in INSTANCES.items()
                        if args.instances is None or k in args.instances}

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = os.path.join(ROOT, "results")
    os.makedirs(results_dir, exist_ok=True)

    total_runs   = len(active_configs) * len(active_instances) * args.runs
    total_audited = 0
    total_hard    = 0
    total_disc    = 0
    all_results   = []

    print("=" * 72)
    print("VALIDAÇÃO TÉCNICA — AUDITOR INDEPENDENTE (C9 / C11 Weighted Sum)")
    print("=" * 72)
    print(f"  Configs    : {[c[0] for c in active_configs]}")
    print(f"  Instâncias : {list(active_instances.keys())}")
    print(f"  Runs       : {args.runs}  |  n_evals: {args.n_evals:,}")
    print(f"  Total runs : {total_runs}")
    print(f"  Checagens  : cv=0 → auditor hard viols + f1/f2/f3 match")
    print("=" * 72)

    global_start = time.perf_counter()

    # ── Por instância — carrega ctx/decoder/auditor uma vez ───────────
    run_count = 0
    for inst_name, inst_path in active_instances.items():
        print(f"\n{'─'*72}")
        print(f"  Instância: {inst_name}")
        print(f"{'─'*72}")

        ctx     = parse_instance(inst_path)
        problem = EVRPTWProblem(ctx, k_max=0)   # sem LS
        decoder = Decoder(ctx, k_max=0)
        auditor = IndependentAuditor(ctx)

        for cfg in active_configs:
            config_id = cfg[0]

            for run_idx in range(1, args.runs + 1):
                run_count += 1
                seed = _deterministic_seed(config_id, inst_name, run_idx)
                print(f"  [{run_count:3d}/{total_runs}] {config_id} / {inst_name} / run{run_idx}"
                      f"  (seed={seed})", end="", flush=True)

                t0 = time.perf_counter()
                r  = audit_run(ctx, problem, decoder, auditor,
                               config_id, inst_name, run_idx,
                               args.n_evals, verbose=args.verbose)
                elapsed = time.perf_counter() - t0

                status = "✅ OK" if r.get("passed") else "❌ FALHA"
                print(f"  →  feas={r['n_feasible']}/{r['n_total_pop']}  "
                      f"auditadas={r['n_audited']}  "
                      f"hard_viols={r['violations_hard']}  "
                      f"discr={r['obj_discrepancies']}  "
                      f"{elapsed:.1f}s  {status}")

                total_audited += r["n_audited"]
                total_hard    += r["violations_hard"]
                total_disc    += r["obj_discrepancies"]
                all_results.append(r)

    global_elapsed = time.perf_counter() - global_start

    # ── Resumo final ──────────────────────────────────────────────────
    print(f"\n\n{'═'*72}")
    print("RESULTADO FINAL — AUDITORIA TÉCNICA")
    print(f"{'═'*72}")
    print(f"  Tempo total    : {global_elapsed:.1f}s")
    print(f"  Runs auditadas : {total_runs}")
    print(f"  Soluções aud.  : {total_audited}")
    print(f"  Viols hard     : {total_hard}  (esperado: 0)")
    print(f"  Discrepâncias  : {total_disc}  (esperado: 0)")
    print()

    verdict = "✅ PASSOU" if (total_hard == 0 and total_disc == 0) else "❌ FALHOU"
    print(f"  VEREDITO: {verdict}")

    if total_hard > 0 or total_disc > 0:
        print(f"\n  Primeiras falhas:")
        shown = 0
        for r in all_results:
            if r.get("passed"):
                continue
            for sol in r.get("solutions", []):
                if sol["has_hard_viol"] or not (sol["match_f1"] and sol["match_f2"] and sol["match_f3"]):
                    print(f"    {r['config_id']}/{r['instance']}/run{r['run_idx']}/sol{sol['sol_idx']}")
                    if sol["has_hard_viol"]:
                        print(f"      HARD: {sol['hard_viols'][:2]}")
                    if not sol["match_f1"]: print(f"      f1: dec={sol['f1_dec']:.4f} aud={sol['f1_aud']:.4f}")
                    if not sol["match_f2"]: print(f"      f2: dec={sol['f2_dec']:.4f} aud={sol['f2_aud']:.4f}")
                    if not sol["match_f3"]: print(f"      f3: dec={sol['f3_dec']:.6f} aud={sol['f3_aud']:.6f}")
                    shown += 1
                    if shown >= 10:
                        break
            if shown >= 10:
                break

    # ── Tabela por config/instância ───────────────────────────────────
    print(f"\n  {'Config':<6}  {'Instância':<12}  {'Aud.':>6}  {'Hard':>6}  {'Discr':>6}  Estado")
    print(f"  {'─'*55}")
    for cfg in active_configs:
        for inst_name in active_instances:
            runs_here = [r for r in all_results
                         if r["config_id"] == cfg[0] and r["instance"] == inst_name]
            n_aud = sum(r["n_audited"] for r in runs_here)
            n_hrd = sum(r["violations_hard"] for r in runs_here)
            n_dsc = sum(r["obj_discrepancies"] for r in runs_here)
            st    = "✅" if n_hrd == 0 and n_dsc == 0 else "❌"
            print(f"  {cfg[0]:<6}  {inst_name:<12}  {n_aud:>6}  {n_hrd:>6}  {n_dsc:>6}  {st}")

    print(f"\n{'═'*72}")

    # ── Interpreta resultado ──────────────────────────────────────────
    print("\nINTERPRETAÇÃO:")
    if total_hard == 0 and total_disc == 0:
        print("  ✅ Zero violações hard + zero discrepâncias de objetivos.")
        print("  As configurações Weighted Sum (C9 e C11) produzem soluções")
        print("  fisicamente válidas. O HV alto observado no experimento de tuning")
        print("  é LEGÍTIMO — não é artefato de bug ou constraint silenciosa.")
        print("  → Pode prosseguir com Script 2 (generalização).")
    else:
        print("  ❌ Foram encontradas violações ou discrepâncias.")
        print("  Investigar antes de prosseguir com o Script 2.")

    # ── Salva JSON ────────────────────────────────────────────────────
    json_path = os.path.join(results_dir, f"audit_ws_{timestamp}.json")
    # Remove 'solutions' detail se for muito grande para salvar
    summary_results = []
    for r in all_results:
        s = {k: v for k, v in r.items() if k != "solutions"}
        summary_results.append(s)

    with open(json_path, "w") as f:
        json.dump({
            "timestamp":      timestamp,
            "n_evals":        args.n_evals,
            "total_audited":  total_audited,
            "total_hard":     total_hard,
            "total_disc":     total_disc,
            "passed":         (total_hard == 0 and total_disc == 0),
            "runs":           summary_results,
        }, f, indent=2)
    print(f"\n  JSON: {json_path}")
    print(f"{'═'*72}\n")


if __name__ == "__main__":
    main()
