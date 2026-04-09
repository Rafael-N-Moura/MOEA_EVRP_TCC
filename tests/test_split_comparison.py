"""
Teste comparativo: Split dual (antigo) vs Split relaxado (novo)

Gera uma permutação aleatória com seed=42 para c101_21 e roda
ambas as versões do decoder lado a lado, imprimindo detalhes
completos de cada fase.
"""

import sys
import os
import numpy as np

# Adiciona o diretório raiz ao path
ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, ROOT)

# Importar módulos individualmente sem acionar src/__init__.py (que requer pymoo)
import importlib.util

def _load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_model = _load_module('src.model', os.path.join(ROOT, 'src', 'model.py'))
_parser = _load_module('src.parser', os.path.join(ROOT, 'src', 'parser.py'))
_decoder = _load_module('src.decoder', os.path.join(ROOT, 'src', 'decoder.py'))

parse_instance = _parser.parse_instance
Decoder = _decoder.Decoder


# =====================================================================
# Split ANTIGO (dual: check_tw=True + check_tw=False) — cópia inline
# =====================================================================
class OldSplitDecoder(Decoder):
    """Decoder com a versão antiga do Split (dual check_tw)."""

    def _split(self, perm):
        ready = self.ready
        cust = self.cust_node

        routes_tw = self._split_dp_old(perm, check_tw=True)
        routes_cap = self._split_dp_old(perm, check_tw=False)

        if routes_cap is not None:
            routes_cap = [sorted(r, key=lambda c: ready[cust[c]])
                          for r in routes_cap]

        candidates = [r for r in (routes_tw, routes_cap) if r is not None]
        best_routes, best_cv = candidates[0], float('inf')

        for routes in candidates:
            total_tw, total_bat = 0.0, 0.0
            for cust_seq in routes:
                _, tw_v, bat_v = self._insert_stations(cust_seq)
                total_tw += tw_v
                total_bat += bat_v
            cv = total_tw / max(self.horizon, 1.0) + total_bat / max(self.Q, 1.0)
            if cv < best_cv:
                best_cv = cv
                best_routes = routes

        return best_routes

    def _split_dp_old(self, perm, check_tw):
        n = len(perm)
        INF_V = float('inf')
        V = [INF_V] * (n + 1)
        V[0] = 0.0
        P = [-1] * (n + 1)

        dist = self.dist
        travel = self.travel
        depot = self.depot
        cust = self.cust_node
        dem = self.demand
        ready = self.ready
        due = self.due
        service = self.service
        C = self.C

        for i in range(1, n + 1):
            load = 0.0
            ci = cust[perm[i - 1]]
            cost = dist[depot, ci] + dist[ci, depot]
            t_dep = 0.0

            for j in range(i, n + 1):
                cj = cust[perm[j - 1]]
                load += dem[perm[j - 1]]
                if load > C:
                    break

                if j > i:
                    cprev = cust[perm[j - 2]]
                    cost = cost - dist[cprev, depot] + dist[cprev, cj] + dist[cj, depot]
                    t_arr = t_dep + travel[cprev, cj]
                else:
                    t_arr = travel[depot, cj]

                if check_tw and t_arr > due[cj]:
                    break

                t_dep = max(t_arr, ready[cj]) + service[cj]

                cand = V[i - 1] + cost
                if cand < V[j]:
                    V[j] = cand
                    P[j] = i - 1

        if V[n] >= INF_V:
            if not check_tw:
                return [[int(c)] for c in perm]
            return None

        routes, j = [], n
        while j > 0:
            start = P[j] + 1
            routes.append([int(perm[k]) for k in range(start - 1, j)])
            j = P[j]
        routes.reverse()
        return routes


# =====================================================================
# Funções de instrumentação
# =====================================================================
def get_customer_id(decoder, cust_idx):
    """Retorna o ID do cliente (C1, C2, ...) dado o índice 0-based."""
    node_idx = decoder.cust_node[cust_idx]
    # all_nodes[node_idx].id — mas não temos acesso direto aqui
    return f"C{cust_idx + 1}"


def get_node_label(decoder, node_idx):
    """Retorna um label legível para qualquer nó."""
    if node_idx == decoder.depot:
        return "D0"
    if decoder._is_station[node_idx]:
        return f"S{node_idx - 1}"  # estações começam no índice 1
    # É cliente
    cust_start = decoder.cust_node[0]
    c_num = node_idx - cust_start + 1
    return f"C{c_num}"


def insert_stations_instrumented(decoder, customers):
    """
    Versão instrumentada de _insert_stations.
    Retorna (route, tw_viol, bat_viol, details)
    onde details é uma lista de dicts por nó visitado.
    """
    EPS = 1e-6
    depot = decoder.depot
    route = [depot]
    t, bat, ant, d_acc = 0.0, decoder.Q, depot, 0.0
    tw_viol = 0.0
    bat_viol = 0.0
    nc = len(customers)
    details = []

    # Nó inicial (depot)
    details.append({
        'node': depot,
        'label': 'D0',
        'type': 'depot',
        't_arr': 0.0,
        'ready': decoder.ready[depot],
        'due': decoder.due[depot],
        't_start': 0.0,
        't_dep': 0.0,
        'bat_before': decoder.Q,
        'consumption': 0.0,
        'bat_after': decoder.Q,
        'recharge': 0.0,
        'tw_viol': 0.0,
        'bat_viol': 0.0,
    })

    for idx in range(nc):
        dest = decoder.cust_node[customers[idx]]
        prox = decoder.cust_node[customers[idx + 1]] if idx + 1 < nc else depot
        e_nec = decoder.dist[ant, dest] * decoder.r

        if bat >= e_nec:
            t_arr = t + decoder.travel[ant, dest]
            tw_v = max(0.0, t_arr - decoder.due[dest])
            tw_viol += tw_v
            t_start = max(t_arr, decoder.ready[dest])
            t_out = t_start + decoder.service[dest]
            consumption = e_nec
            bat_after = bat - e_nec

            details.append({
                'node': dest,
                'label': get_node_label(decoder, dest),
                'type': 'customer',
                't_arr': t_arr,
                'ready': decoder.ready[dest],
                'due': decoder.due[dest],
                't_start': t_start,
                't_dep': t_out,
                'bat_before': bat,
                'consumption': consumption,
                'bat_after': bat_after,
                'recharge': 0.0,
                'tw_viol': tw_v,
                'bat_viol': 0.0,
            })

            t = t_out
            bat = bat_after
            d_acc += decoder.dist[ant, dest]
            route.append(dest)
            ant = dest
        else:
            good, fallback = decoder._find_candidates(
                ant, dest, prox, t, bat, d_acc, EPS)

            if good:
                best = min(good, key=lambda x: x[1])
            elif fallback:
                best = min(fallback, key=lambda x: x[1])
            else:
                bv = e_nec - bat
                bat_viol += bv
                t_arr = t + decoder.travel[ant, dest]
                tw_v = max(0.0, t_arr - decoder.due[dest])
                tw_viol += tw_v
                t_start = max(t_arr, decoder.ready[dest])
                t_out = t_start + decoder.service[dest]

                details.append({
                    'node': dest,
                    'label': get_node_label(decoder, dest),
                    'type': 'customer (forced, no station)',
                    't_arr': t_arr,
                    'ready': decoder.ready[dest],
                    'due': decoder.due[dest],
                    't_start': t_start,
                    't_dep': t_out,
                    'bat_before': bat,
                    'consumption': e_nec,
                    'bat_after': 0.0,
                    'recharge': 0.0,
                    'tw_viol': tw_v,
                    'bat_viol': bv,
                })

                bat = 0.0
                t = t_out
                d_acc += decoder.dist[ant, dest]
                route.append(dest)
                ant = dest
                continue

            s, _score, t_out, bat_dest, t_dest = best
            # Detalhe da estação
            e1 = decoder.dist[ant, s] * decoder.r
            t_s_arr = t + decoder.travel[ant, s]
            bat_s = bat - e1
            recharge_amount = decoder.Q - bat_s
            t_rec = t_s_arr + decoder.g * recharge_amount

            details.append({
                'node': s,
                'label': get_node_label(decoder, s),
                'type': 'station',
                't_arr': t_s_arr,
                'ready': decoder.ready[s],
                'due': decoder.due[s],
                't_start': t_s_arr,
                't_dep': t_rec,
                'bat_before': bat,
                'consumption': e1,
                'bat_after': decoder.Q,
                'recharge': recharge_amount,
                'tw_viol': 0.0,
                'bat_viol': 0.0,
            })

            # Detalhe do cliente destino após estação
            e2 = decoder.dist[s, dest] * decoder.r
            tw_v = max(0.0, t_dest - decoder.due[dest])
            tw_viol += tw_v
            t_start = max(t_dest, decoder.ready[dest])
            t_out_cust = t_start + decoder.service[dest]

            details.append({
                'node': dest,
                'label': get_node_label(decoder, dest),
                'type': 'customer (after station)',
                't_arr': t_dest,
                'ready': decoder.ready[dest],
                'due': decoder.due[dest],
                't_start': t_start,
                't_dep': t_out_cust,
                'bat_before': decoder.Q,
                'consumption': e2,
                'bat_after': bat_dest,
                'recharge': 0.0,
                'tw_viol': tw_v,
                'bat_viol': 0.0,
            })

            route.append(s)
            route.append(dest)
            t = t_out
            bat = bat_dest
            d_acc += decoder.dist[ant, s] + decoder.dist[s, dest]
            ant = dest

    # Retorno ao depot
    e_ret = decoder.dist[ant, depot] * decoder.r
    if bat >= e_ret:
        t_depot = t + decoder.travel[ant, depot]
        details.append({
            'node': depot,
            'label': 'D0',
            'type': 'depot (return)',
            't_arr': t_depot,
            'ready': decoder.ready[depot],
            'due': decoder.due[depot],
            't_start': t_depot,
            't_dep': t_depot,
            'bat_before': bat,
            'consumption': e_ret,
            'bat_after': bat - e_ret,
            'recharge': 0.0,
            'tw_viol': max(0.0, t_depot - decoder.due[depot]),
            'bat_viol': 0.0,
        })
        route.append(depot)
    else:
        ret = decoder._find_return_station(ant, t, bat)
        if ret is not None:
            s, t_depot = ret
            e1 = decoder.dist[ant, s] * decoder.r
            t_s = t + decoder.travel[ant, s]
            bat_s = bat - e1
            recharge_amount = decoder.Q - bat_s

            details.append({
                'node': s,
                'label': get_node_label(decoder, s),
                'type': 'station (return)',
                't_arr': t_s,
                'ready': decoder.ready[s],
                'due': decoder.due[s],
                't_start': t_s,
                't_dep': t_s + decoder.g * recharge_amount,
                'bat_before': bat,
                'consumption': e1,
                'bat_after': decoder.Q,
                'recharge': recharge_amount,
                'tw_viol': 0.0,
                'bat_viol': 0.0,
            })

            e2 = decoder.dist[s, depot] * decoder.r
            details.append({
                'node': depot,
                'label': 'D0',
                'type': 'depot (return)',
                't_arr': t_depot,
                'ready': decoder.ready[depot],
                'due': decoder.due[depot],
                't_start': t_depot,
                't_dep': t_depot,
                'bat_before': decoder.Q,
                'consumption': e2,
                'bat_after': decoder.Q - e2,
                'recharge': 0.0,
                'tw_viol': max(0.0, t_depot - decoder.due[depot]),
                'bat_viol': 0.0,
            })
            route.append(s)
            route.append(depot)
        else:
            bv = e_ret - bat
            bat_viol += bv
            t_depot = t + decoder.travel[ant, depot]
            details.append({
                'node': depot,
                'label': 'D0',
                'type': 'depot (return, forced)',
                't_arr': t_depot,
                'ready': decoder.ready[depot],
                'due': decoder.due[depot],
                't_start': t_depot,
                't_dep': t_depot,
                'bat_before': bat,
                'consumption': e_ret,
                'bat_after': 0.0,
                'recharge': 0.0,
                'tw_viol': max(0.0, t_depot - decoder.due[depot]),
                'bat_viol': bv,
            })
            route.append(depot)

    tw_viol += max(0.0, t_depot - decoder.due[depot])

    return route, tw_viol, bat_viol, details


def analyze_version(decoder, perm, version_name):
    """Roda o decoder e imprime análise detalhada."""
    print(f"\n{'='*80}")
    print(f"  {version_name}")
    print(f"{'='*80}")

    # --- Fase 1: Split ---
    perm_arr = np.asarray(perm, dtype=int)
    routes = decoder._split(perm_arr)

    n_routes = len(routes)
    clients_per_route = [len(r) for r in routes]
    demand_per_route = [sum(float(decoder.demand[c]) for c in r) for r in routes]

    print(f"\n--- SPLIT ---")
    print(f"Número de rotas: {n_routes}")
    print(f"Clientes por rota: {clients_per_route}")
    print(f"Demanda por rota:  {[f'{d:.0f}' for d in demand_per_route]}")
    print(f"Demanda total:     {sum(demand_per_route):.0f}")
    print(f"Min/Max/Média clientes: {min(clients_per_route)}/{max(clients_per_route)}/{np.mean(clients_per_route):.1f}")

    # --- Fase 3: InsertStations (por rota) ---
    print(f"\n--- INSERT STATIONS (resumo por rota) ---")
    all_expanded = []
    all_details = []
    total_tw = 0.0
    total_bat = 0.0
    longest_route_idx = -1
    longest_route_len = 0

    for ri, cust_seq in enumerate(routes):
        expanded, tw_v, bat_v, details = insert_stations_instrumented(decoder, cust_seq)
        all_expanded.append(expanded)
        all_details.append(details)
        total_tw += tw_v
        total_bat += bat_v

        n_stations = sum(1 for d in details if 'station' in d['type'])
        n_clients = len(cust_seq)

        if n_clients > longest_route_len:
            longest_route_len = n_clients
            longest_route_idx = ri

        # Violações de TW individuais
        tw_violations = [(d['label'], d['tw_viol']) for d in details
                         if d['tw_viol'] > 0]
        bat_violations = [(d['label'], d['bat_viol']) for d in details
                          if d['bat_viol'] > 0]

        seq_labels = [get_node_label(decoder, n) for n in expanded]

        if n_routes <= 20 or tw_violations or bat_violations:
            print(f"\n  Rota {ri}: {n_clients} clientes, {n_stations} estações")
            print(f"    Sequência: {' → '.join(seq_labels)}")
            if tw_violations:
                print(f"    Violações TW: {', '.join(f'{lbl}: {v:.1f}' for lbl, v in tw_violations)}")
            if bat_violations:
                print(f"    Violações BAT: {', '.join(f'{lbl}: {v:.2f}' for lbl, v in bat_violations)}")
            if not tw_violations and not bat_violations:
                print(f"    Sem violações")

    # --- Fase 4: Evaluate ---
    F = decoder._evaluate(all_expanded)
    f1, f2, f3 = F
    cv_tw = total_tw / max(decoder.horizon, 1.0)
    cv_bat = total_bat / max(decoder.Q, 1.0)
    cv_total = cv_tw + cv_bat

    print(f"\n--- EVALUATE ---")
    print(f"f1 (veículos):   {f1:.0f}")
    print(f"f2 (distância):  {f2:.2f}")
    print(f"f3 (makespan):   {f3:.2f}")
    print(f"cv_tw:           {cv_tw:.6f}  (soma TW: {total_tw:.2f})")
    print(f"cv_bat:          {cv_bat:.6f}  (soma BAT: {total_bat:.2f})")
    print(f"cv_total:        {cv_total:.6f}")

    # --- Rota mais longa em detalhe ---
    if longest_route_idx >= 0:
        print(f"\n--- ROTA MAIS LONGA (Rota {longest_route_idx}, {longest_route_len} clientes) ---")
        print(f"Clientes: {[get_customer_id(decoder, c) for c in routes[longest_route_idx]]}")
        details = all_details[longest_route_idx]

        print(f"\n{'Nó':<10} {'Tipo':<28} {'t_arr':>8} {'ready':>8} {'due':>8} "
              f"{'t_start':>8} {'t_dep':>8} {'TW viol':>8} "
              f"{'bat_bef':>8} {'consum':>8} {'bat_aft':>8} {'recharge':>8} {'BAT viol':>8}")
        print("-" * 160)
        for d in details:
            print(f"{d['label']:<10} {d['type']:<28} "
                  f"{d['t_arr']:8.1f} {d['ready']:8.1f} {d['due']:8.1f} "
                  f"{d['t_start']:8.1f} {d['t_dep']:8.1f} {d['tw_viol']:8.1f} "
                  f"{d['bat_before']:8.2f} {d['consumption']:8.2f} {d['bat_after']:8.2f} "
                  f"{d['recharge']:8.2f} {d['bat_viol']:8.2f}")

    return {
        'f1': f1, 'f2': f2, 'f3': f3,
        'cv_tw': cv_tw, 'cv_bat': cv_bat, 'cv_total': cv_total,
        'n_routes': n_routes,
        'clients_per_route': clients_per_route,
    }


def main():
    instance_path = os.path.join(
        os.path.dirname(__file__), '..', 'evrptw_instances', 'c101_21.txt'
    )
    ctx = parse_instance(instance_path)

    print(f"Instância: c101_21")
    print(f"Clientes: {ctx.n_customers}")
    print(f"Bateria (Q): {ctx.battery_capacity}")
    print(f"Capacidade (C): {ctx.vehicle_capacity}")
    print(f"Taxa consumo (r): {ctx.consumption_rate}")
    print(f"Taxa recarga (g): {ctx.recharge_rate}")
    print(f"Horizonte (due depot): {ctx.all_nodes[0].due_date}")
    print(f"Demanda total: {sum(c.demand for c in ctx.customers):.0f}")
    print(f"Rotas mínimas (capacidade): {int(np.ceil(sum(c.demand for c in ctx.customers) / ctx.vehicle_capacity))}")

    # Permutação aleatória reproduzível
    rng = np.random.default_rng(seed=42)
    perm = rng.permutation(ctx.n_customers)
    print(f"\nPermutação (seed=42, primeiros 20): {perm[:20].tolist()}")

    # --- Versão ANTIGA (dual Split) ---
    old_decoder = OldSplitDecoder(ctx, k_max=0)  # k_max=0 → sem LS
    old_results = analyze_version(old_decoder, perm, "VERSÃO ANTIGA (Split dual: check_tw=True + check_tw=False)")

    # --- Versão NOVA (Split relaxado) ---
    new_decoder = Decoder(ctx, k_max=0)  # k_max=0 → sem LS
    new_results = analyze_version(new_decoder, perm, "VERSÃO NOVA (Split relaxado)")

    # --- Comparação final ---
    print(f"\n{'='*80}")
    print(f"  COMPARAÇÃO RESUMIDA")
    print(f"{'='*80}")
    print(f"\n{'Métrica':<25} {'Antigo':>15} {'Novo':>15} {'Δ':>15}")
    print("-" * 70)
    for key, label in [('f1', 'f1 (veículos)'), ('f2', 'f2 (distância)'),
                        ('f3', 'f3 (makespan)'), ('cv_tw', 'cv_tw'),
                        ('cv_bat', 'cv_bat'), ('cv_total', 'cv_total')]:
        old_v = old_results[key]
        new_v = new_results[key]
        delta = new_v - old_v
        print(f"{label:<25} {old_v:>15.4f} {new_v:>15.4f} {delta:>+15.4f}")

    print(f"\n{'Distribuição rotas':<25} {'Antigo':>15} {'Novo':>15}")
    print("-" * 55)
    print(f"{'Nº rotas':<25} {old_results['n_routes']:>15} {new_results['n_routes']:>15}")
    old_cpr = old_results['clients_per_route']
    new_cpr = new_results['clients_per_route']
    print(f"{'Min clientes/rota':<25} {min(old_cpr):>15} {min(new_cpr):>15}")
    print(f"{'Max clientes/rota':<25} {max(old_cpr):>15} {max(new_cpr):>15}")
    print(f"{'Média clientes/rota':<25} {np.mean(old_cpr):>15.1f} {np.mean(new_cpr):>15.1f}")

    # Histograma de tamanhos de rota
    print(f"\nHistograma tamanho de rota (antigo):")
    for size in sorted(set(old_cpr)):
        count = old_cpr.count(size)
        print(f"  {size:2d} clientes: {'█' * count} ({count})")

    print(f"\nHistograma tamanho de rota (novo):")
    for size in sorted(set(new_cpr)):
        count = new_cpr.count(size)
        print(f"  {size:2d} clientes: {'█' * count} ({count})")


if __name__ == '__main__':
    main()
