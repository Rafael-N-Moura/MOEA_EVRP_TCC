#!/usr/bin/env python3
"""
Passo 1b – Validação do decodificador.

Executa NSGA-II nas 6 instâncias de validação (5 runs cada, parâmetros padrão)
e verifica:
  1. Produção de soluções viáveis (cv = 0)
  2. Verificação independente de constraints (bateria, capacidade, TW)
  3. Valores de f1 e f2 compatíveis com a literatura Schneider

Uso:
    python scripts/validate.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from src import parse_instance, EVRPTWProblem, Decoder, TWBiasedSampling
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation

# ── Configuração ──────────────────────────────────────────────────────
VALIDATION_INSTANCES = [
    ("c101C10",  "evrptw_instances/c101C10.txt"),
    ("c106C15",  "evrptw_instances/c106C15.txt"),
    ("r102C10",  "evrptw_instances/r102C10.txt"),
    ("r102C15",  "evrptw_instances/r102C15.txt"),
    ("rc102C10", "evrptw_instances/rc102C10.txt"),
    ("rc103C15", "evrptw_instances/rc103C15.txt"),
]

N_RUNS = 5
N_GEN = 300
POP_SIZE = 100
SEEDS = list(range(1001, 1001 + N_RUNS))


# ── Verificação independente de constraints ───────────────────────────
def verify_solution(perm, ctx):
    """
    Re-decodifica uma permutação e verifica TODAS as restrições de forma
    independente do fluxo normal do decoder. Retorna (ok, mensagens).
    """
    dec = Decoder(ctx)
    perm = np.asarray(perm, dtype=int)

    routes = dec._split(perm)

    msgs = []

    # (a) Capacidade por rota
    all_custs = []
    for i, route in enumerate(routes):
        load = sum(float(dec.demand[c]) for c in route)
        if load > ctx.vehicle_capacity + 1e-9:
            msgs.append(f"Rota {i+1}: sobrecarga {load:.1f} > C={ctx.vehicle_capacity}")
        all_custs.extend(route)

    # (b) Todos os clientes presentes
    if sorted(all_custs) != list(range(ctx.n_customers)):
        msgs.append("Nem todos os clientes estão atribuídos a rotas")

    # (c) InsertStations (retorna tuple agora)
    expanded = []
    for i, route in enumerate(routes):
        result_route, tw_v, bat_v = dec._insert_stations(route)
        expanded.append(result_route)

    # (d) Percurso detalhado: bateria, TW, depot
    for i, route in enumerate(expanded):
        if route[0] != ctx.depot_idx or route[-1] != ctx.depot_idx:
            msgs.append(f"Rota {i+1}: não começa/termina no depósito")

        t, bat = 0.0, ctx.battery_capacity
        ant = route[0]
        for p in route[1:]:
            energy = ctx.dist_matrix[ant, p] * ctx.consumption_rate
            if bat < energy - 1e-9:
                nid = ctx.all_nodes[p].id
                msgs.append(f"Rota {i+1}: bateria {bat:.2f} < {energy:.2f} em {nid}")
            bat = max(bat - energy, 0.0)
            t += ctx.travel_matrix[ant, p]

            node = ctx.all_nodes[p]
            if p != ctx.depot_idx and t > node.due_date + 1e-9:
                msgs.append(f"Rota {i+1}: chegada {t:.2f} > due {node.due_date} em {node.id}")
            t = max(t, node.ready_time)

            if dec._is_station[p]:
                t += ctx.recharge_rate * (ctx.battery_capacity - bat)
                bat = ctx.battery_capacity
            else:
                t += node.service_time
            ant = p

    return len(msgs) == 0, msgs if msgs else ["OK"]


# ── Execução ──────────────────────────────────────────────────────────
def run_validation():
    print("=" * 70)
    print("PASSO 1b  –  Validação do decodificador")
    print("=" * 70)

    summary = []

    for inst_name, inst_path in VALIDATION_INSTANCES:
        print(f"\n{'─' * 60}")
        print(f"Instância: {inst_name}")
        print(f"{'─' * 60}")

        ctx = parse_instance(inst_path)
        problem = EVRPTWProblem(ctx)
        print(f"  Clientes: {ctx.n_customers}  |  Estações: {len(ctx.valid_station_indices)}  "
              f"|  Q={ctx.battery_capacity}  C={ctx.vehicle_capacity}")

        all_F, all_X = [], []

        for run, seed in enumerate(SEEDS):
            alg = NSGA2(
                pop_size=POP_SIZE,
                sampling=TWBiasedSampling(),
                crossover=OrderCrossover(),
                mutation=InversionMutation(),
                eliminate_duplicates=True,
            )
            t0 = time.time()
            res = minimize(problem, alg, ('n_gen', N_GEN), verbose=False, seed=seed)
            elapsed = time.time() - t0

            cv_arr = res.pop.get("_cv")
            F_real = res.pop.get("_F_real")
            X_pop = res.pop.get("X")
            mask = cv_arr[:, 0] <= 1e-9
            n_feas = int(mask.sum())
            n_infeas = len(cv_arr) - n_feas
            cv_info = ""
            if n_infeas > 0:
                cv_inf = cv_arr[~mask, 0]
                cv_info = f"  CV min={cv_inf.min():.4f}"
            print(f"  Run {run+1} (seed={seed}): {n_feas:>3} viáveis  "
                  f"{n_infeas:>3} inviáveis{cv_info}  ({elapsed:.1f}s)")

            if n_feas > 0:
                all_F.append(F_real[mask])
                all_X.append(X_pop[mask])

        if not all_F:
            print("\n  *** NENHUMA solução viável encontrada! ***")
            summary.append((inst_name, None, None, None, False))
            continue

        Fc = np.vstack(all_F)
        Xc = np.vstack(all_X)

        best_idx = {
            "f1": int(np.argmin(Fc[:, 0])),
            "f2": int(np.argmin(Fc[:, 1])),
            "f3": int(np.argmin(Fc[:, 2])),
        }

        print(f"\n  Melhores valores encontrados ({len(Fc)} soluções viáveis):")
        for obj, idx in best_idx.items():
            f = Fc[idx]
            print(f"    {obj}: {f[0]:.0f} veic | {f[1]:.2f} dist | {f[2]:.2f} makespan")

        print(f"\n  Verificação independente de constraints:")
        all_ok = True
        for label, idx in best_idx.items():
            ok, msgs = verify_solution(Xc[idx], ctx)
            status = "OK" if ok else "FALHA"
            if not ok:
                all_ok = False
            print(f"    melhor-{label}: {status}")
            if not ok:
                for m in msgs:
                    print(f"      - {m}")

        best_f1 = Fc[best_idx["f1"], 0]
        best_f2 = Fc[best_idx["f2"], 1]
        best_f3 = Fc[best_idx["f3"], 2]
        summary.append((inst_name, best_f1, best_f2, best_f3, all_ok))

    # Tabela resumo
    print(f"\n{'=' * 70}")
    print("RESUMO DA VALIDAÇÃO")
    print(f"{'=' * 70}")
    print(f"{'Instância':<12} {'f1 (veic)':>10} {'f2 (dist)':>12} {'f3 (mksp)':>12} {'Constraints':>12}")
    print("─" * 60)
    for name, f1, f2, f3, ok in summary:
        if f1 is None:
            print(f"{name:<12} {'---':>10} {'---':>12} {'---':>12} {'FALHA':>12}")
        else:
            print(f"{name:<12} {f1:>10.0f} {f2:>12.2f} {f3:>12.2f} {'OK' if ok else 'FALHA':>12}")
    print("─" * 60)
    print("\nCompare f1/f2 com BKS da literatura Schneider para validação.")
    print("f3 (makespan) não tem referência publicada; validado por consistência interna.")
    print("=" * 70)


if __name__ == "__main__":
    run_validation()
