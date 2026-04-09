"""
Decodificador EVRPTW em quatro fases.

    Decode(π) = Evaluate( InsertStations( LocalSearch( Split(π) ) ) )

Fase 1 – Split (Prins relaxado): particiona a permutação com DP.
         Apenas duas condições fecham uma rota:
           (a) acúmulo de demanda excede C
           (b) tempo estimado de retorno ao depot excede o horizonte
         Violações de TW individuais NÃO fecham a rota.
Fase 2 – LocalSearch: relocate inter-rota com recálculo de estações.
         Move um cliente de cada vez; InsertStations é chamado para
         avaliar cada candidato. Critério: economia de custo > 0
         (distância + violações TW/bateria).
         First-improvement com restart. K_max limita movimentos.
Fase 3 – InsertStations: insere estações com recarga total, critério
         balanceado e look-ahead. Acumula violações de TW e bateria.
Fase 4 – Evaluate: percorre rotas expandidas e calcula [f1, f2, f3].
    f1 = Número de veículos
    f2 = Distância total
    f3 = Atrasos totais de Janela de Tempo (Soft Constraint)

Retorno: (F, cv) onde F = np.array([f1, f2, f3]) e cv = escalar de
violação de bateria normalizada (cv = 0 → veículo consegue fazer a rota sem enguiçar).
"""

import numpy as np
from .model import Context

_DEFAULT_K_MAX = 50
_NEAREST_ROUTES = 5


class Decoder:
    def __init__(self, context: Context, k_max: int = _DEFAULT_K_MAX):
        self.Q = context.battery_capacity
        self.C = context.vehicle_capacity
        self.r = context.consumption_rate
        self.g = context.recharge_rate
        self.n = context.n_customers
        self.depot = context.depot_idx
        self.dist = context.dist_matrix
        self.travel = context.travel_matrix
        self.cust_node = context.customer_node_indices
        self.stations = context.valid_station_indices

        self.demand = np.array([c.demand for c in context.customers])
        self.ready = np.array([nd.ready_time for nd in context.all_nodes])
        self.due = np.array([nd.due_date for nd in context.all_nodes])
        self.service = np.array([nd.service_time for nd in context.all_nodes])

        self.horizon = float(self.due[self.depot])
        self.k_max = k_max

        self._is_station = np.zeros(context.n_nodes, dtype=bool)
        for i in range(len(context.stations)):
            self._is_station[context._station_start + i] = True

        self._node_x = np.array([nd.x for nd in context.all_nodes])
        self._node_y = np.array([nd.y for nd in context.all_nodes])

        # Pré-computa energia mínima de cada nó até a estação mais próxima.
        # Usado pelo look-ahead para decidir recarga preventiva.
        n_nodes = context.n_nodes
        self._min_station_energy = np.full(n_nodes, float('inf'))
        if self.stations:
            for node in range(n_nodes):
                min_e = float('inf')
                for s in self.stations:
                    e = self.dist[node, s] * self.r
                    if e < min_e:
                        min_e = e
                self._min_station_energy[node] = min_e

    # ==================================================================
    # Ponto de entrada público
    # ==================================================================
    def decode(self, perm):
        """Decode(π) → (np.array([f1, f2, f3]), cv)."""
        F, cv, _ = self.decode_detailed(perm)
        return F, cv

    def decode_detailed(self, perm):
        """Decode(π) → (F, cv, expanded_routes)."""
        perm = np.asarray(perm, dtype=int)
        routes = self._split(perm)

        expanded, total_tw, total_bat = self._expand_routes(routes)
        cv = total_bat / max(self.Q, 1.0)

        if self.k_max > 0 and len(routes) > 1:
            routes_ls = self._local_search(routes)
            exp_ls, tw_ls, bat_ls = self._expand_routes(routes_ls)
            cv_ls = bat_ls / max(self.Q, 1.0)
            if cv_ls <= cv:
                expanded, cv = exp_ls, cv_ls
                total_tw = tw_ls

        F = self._evaluate(expanded, total_tw)
        return F, float(cv), expanded

    def _expand_routes(self, routes):
        """Insere estações em todas as rotas, retorna (expanded, tw, bat)."""
        expanded = []
        total_tw = 0.0
        total_bat = 0.0
        for cust_seq in routes:
            route, tw_v, bat_v = self._insert_stations(cust_seq)
            expanded.append(route)
            total_tw += tw_v
            total_bat += bat_v
        return expanded, total_tw, total_bat

    # ==================================================================
    # Fase 1 – Split
    # ==================================================================
    def _split(self, perm):
        """
        Split relaxado: particiona a permutação usando DP com apenas
        duas condições de quebra de rota:
          1. Acúmulo de demanda excede C (capacidade de carga)
          2. Tempo estimado de retorno ao depot excede o horizonte

        Violações de TW individuais NÃO fecham a rota — serão
        capturadas depois por InsertStations/Evaluate como cv.
        """
        return self._split_dp(perm)

    def _split_dp(self, perm):
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
        service = self.service
        C = self.C
        horizon = self.horizon

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

                t_dep = max(t_arr, ready[cj]) + service[cj]

                # Verifica se o retorno ao depot excede o horizonte
                t_return = t_dep + travel[cj, depot]
                if t_return > horizon:
                    break

                cand = V[i - 1] + cost
                if cand < V[j]:
                    V[j] = cand
                    P[j] = i - 1

        if V[n] >= INF_V:
            return [[int(c)] for c in perm]

        routes, j = [], n
        while j > 0:
            start = P[j] + 1
            routes.append([int(perm[k]) for k in range(start - 1, j)])
            j = P[j]
        routes.reverse()
        return routes

    # ==================================================================
    # Fase 2 – LocalSearch (relocate inter-rota, first-improvement)
    # ==================================================================
    def _local_search(self, routes):
        """
        Relocate inter-rota com recálculo de estações.

        Para cada movimento candidato, InsertStations é chamado nas
        rotas afetadas para obter a distância expandida real.
        Critério de aceitação: economia de distância total > 0.
        First-improvement com restart após cada movimento aceito.
        """
        dem = self.demand
        C = self.C

        routes = [list(r) for r in routes]

        # Pré-computar custo (distância expandida) de cada rota
        costs = []
        for r in routes:
            costs.append(self._expanded_cost(r))

        k = 0
        improved = True

        while improved and k < self.k_max:
            improved = False
            move = self._find_first_improving_move(routes, costs)

            if move is not None:
                ri, rj, route_i_new, route_j_new, cost_i_new, cost_j_new = move

                routes[ri] = route_i_new
                costs[ri] = cost_i_new
                routes[rj] = route_j_new
                costs[rj] = cost_j_new

                if not routes[ri]:
                    routes.pop(ri)
                    costs.pop(ri)

                k += 1
                improved = True

        return [r for r in routes if r]

    def _find_first_improving_move(self, routes, costs):
        """
        Encontra o primeiro relocate com economia > 0.

        Para cada cliente, avalia inserção apenas nas K rotas mais
        próximas por centróide geográfico (_NEAREST_ROUTES).

        Retorna (ri, rj, route_i_new, route_j_new, cost_i_new, cost_j_new)
        ou None.
        """
        dem = self.demand
        C = self.C
        cust = self.cust_node
        nx = self._node_x
        ny = self._node_y
        nr = len(routes)

        # Centróides e cargas das rotas
        centroids_x = np.empty(nr)
        centroids_y = np.empty(nr)
        loads = np.empty(nr)
        for idx in range(nr):
            nodes = [cust[c] for c in routes[idx]]
            centroids_x[idx] = np.mean(nx[nodes])
            centroids_y[idx] = np.mean(ny[nodes])
            loads[idx] = sum(float(dem[c]) for c in routes[idx])

        K = min(_NEAREST_ROUTES, nr - 1)

        for ri in range(nr):
            if not routes[ri]:
                continue

            for ci_pos in range(len(routes[ri])):
                c = routes[ri][ci_pos]
                c_node = cust[c]
                c_dem = float(dem[c])

                route_i_new = routes[ri][:ci_pos] + routes[ri][ci_pos + 1:]
                cost_i_new = (self._expanded_cost(route_i_new)
                              if route_i_new else 0.0)
                removal_saving = costs[ri] - cost_i_new

                # K rotas mais próximas do cliente c
                dx = centroids_x - nx[c_node]
                dy = centroids_y - ny[c_node]
                dists_sq = dx * dx + dy * dy
                dists_sq[ri] = np.inf  # excluir rota de origem
                nearest = np.argpartition(dists_sq, K)[:K]

                for rj in nearest:
                    if not routes[rj]:
                        continue
                    if loads[rj] + c_dem > C:
                        continue

                    nj = len(routes[rj])
                    for pos in range(nj + 1):
                        route_j_new = (routes[rj][:pos]
                                       + [c]
                                       + routes[rj][pos:])
                        cost_j_new = self._expanded_cost(route_j_new)
                        insertion_cost = cost_j_new - costs[rj]

                        if removal_saving - insertion_cost > 1e-9:
                            return (ri, rj, route_i_new, route_j_new,
                                    cost_i_new, cost_j_new)

        return None

    def _expanded_cost(self, customers):
        """
        Custo da rota expandida: distância + violações.

        Inclui TW e bateria para que a LS evite movimentos que
        destruam viabilidade mesmo que economizem distância.
        """
        expanded, tw_v, bat_v = self._insert_stations(customers)
        d = 0.0
        for i in range(len(expanded) - 1):
            d += self.dist[expanded[i], expanded[i + 1]]
        return d + tw_v + bat_v

    # ==================================================================
    # Fase 3 – InsertStations  (greedy, recarga total, acumula violações)
    #          Com look-ahead preventivo: antes de ir direto ao cliente,
    #          verifica se teremos energia para "escapar" (chegar ao
    #          próximo destino ou à estação mais próxima).
    # ==================================================================
    def _insert_stations(self, customers):
        """Retorna (route, tw_violation, bat_violation). Nunca falha."""
        EPS = 1e-6
        depot = self.depot
        route = [depot]
        t, bat, ant, d_acc = 0.0, self.Q, depot, 0.0
        tw_viol = 0.0
        bat_viol = 0.0
        nc = len(customers)
        min_st_e = self._min_station_energy

        for idx in range(nc):
            dest = self.cust_node[customers[idx]]
            prox = self.cust_node[customers[idx + 1]] if idx + 1 < nc else depot
            e_nec = self.dist[ant, dest] * self.r

            if bat >= e_nec:
                # ── Look-ahead preventivo ──
                # Verifica se após chegar em dest teremos energia para
                # alcançar o próximo ponto OU a estação mais próxima
                # de dest (o que for menor). Se não, recarrega antes.
                bat_after = bat - e_nec
                e_next = self.dist[dest, prox] * self.r
                e_escape = min(e_next, min_st_e[dest])

                if bat_after >= e_escape:
                    # Seguro: vai direto ao cliente
                    t_arr = t + self.travel[ant, dest]
                    tw_viol += max(0.0, t_arr - self.due[dest])
                    t = max(t_arr, self.ready[dest]) + self.service[dest]
                    bat -= e_nec
                    d_acc += self.dist[ant, dest]
                    route.append(dest)
                    ant = dest
                    continue

                # Look-ahead falhou: recarregar preventivamente.
                # Busca estação entre ant e dest (mesma lógica do
                # caso reativo, mas agora temos energia para chegar).
                good, fallback = self._find_candidates(
                    ant, dest, prox, t, bat, d_acc, EPS)

                if good:
                    best = min(good, key=lambda x: x[1])
                elif fallback:
                    best = min(fallback, key=lambda x: x[1])
                else:
                    # Nenhuma estação acessível entre ant e dest.
                    # Vai direto mesmo — o look-ahead pode ser
                    # pessimista (e.g., estação alcançável depois).
                    t_arr = t + self.travel[ant, dest]
                    tw_viol += max(0.0, t_arr - self.due[dest])
                    t = max(t_arr, self.ready[dest]) + self.service[dest]
                    bat -= e_nec
                    d_acc += self.dist[ant, dest]
                    route.append(dest)
                    ant = dest
                    continue

                s, _score, t_out, bat_dest, t_dest = best
                route.append(s)
                route.append(dest)
                tw_viol += max(0.0, t_dest - self.due[dest])
                t = t_out
                bat = bat_dest
                d_acc += self.dist[ant, s] + self.dist[s, dest]
                ant = dest

            else:
                # ── Caso reativo: bateria insuficiente para o arco ──
                good, fallback = self._find_candidates(
                    ant, dest, prox, t, bat, d_acc, EPS)

                if good:
                    best = min(good, key=lambda x: x[1])
                elif fallback:
                    best = min(fallback, key=lambda x: x[1])
                else:
                    bat_viol += e_nec - bat
                    bat = 0.0
                    t_arr = t + self.travel[ant, dest]
                    tw_viol += max(0.0, t_arr - self.due[dest])
                    t = max(t_arr, self.ready[dest]) + self.service[dest]
                    d_acc += self.dist[ant, dest]
                    route.append(dest)
                    ant = dest
                    continue

                s, _score, t_out, bat_dest, t_dest = best
                route.append(s)
                route.append(dest)
                tw_viol += max(0.0, t_dest - self.due[dest])
                t = t_out
                bat = bat_dest
                d_acc += self.dist[ant, s] + self.dist[s, dest]
                ant = dest

        e_ret = self.dist[ant, depot] * self.r
        if bat >= e_ret:
            t_depot = t + self.travel[ant, depot]
            route.append(depot)
        else:
            ret = self._find_return_station(ant, t, bat)
            if ret is not None:
                s, t_depot = ret
                route.append(s)
                route.append(depot)
            else:
                bat_viol += e_ret - bat
                t_depot = t + self.travel[ant, depot]
                route.append(depot)

        tw_viol += max(0.0, t_depot - self.due[depot])

        return route, tw_viol, bat_viol

    def _find_candidates(self, ant, dest, prox, t, bat, d_acc, eps):
        """Separa estações em good (look-ahead OK) e fallback."""
        good = []
        fallback = []

        for s in self.stations:
            e1 = self.dist[ant, s] * self.r
            e2 = self.dist[s, dest] * self.r
            if e1 > bat or e2 > self.Q:
                continue

            t_s = t + self.travel[ant, s]
            bat_s = bat - e1
            t_rec = t_s + self.g * (self.Q - bat_s)
            t_dest = t_rec + self.travel[s, dest]
            bat_dest = self.Q - e2
            t_out = max(t_dest, self.ready[dest]) + self.service[dest]

            det_d = self.dist[ant, s] + self.dist[s, dest] - self.dist[ant, dest]
            det_t = t_dest - (t + self.travel[ant, dest])
            score = det_d / max(d_acc, eps) + det_t / max(t, eps)

            entry = (s, score, t_out, bat_dest, t_dest)

            if t_out + self.travel[dest, prox] <= self.due[prox]:
                good.append(entry)
            else:
                fallback.append(entry)

        return good, fallback

    def _find_return_station(self, ant, t, bat):
        """Encontra estação para retorno ao depot. Retorna (s, t_depot) ou None."""
        depot = self.depot
        best_s, best_det = None, float('inf')
        best_t_depot = None

        for s in self.stations:
            e1 = self.dist[ant, s] * self.r
            if e1 > bat:
                continue
            e2 = self.dist[s, depot] * self.r
            if e2 > self.Q:
                continue

            t_s = t + self.travel[ant, s]
            bat_s = bat - e1
            t_depot = t_s + self.g * (self.Q - bat_s) + self.travel[s, depot]

            det = self.dist[ant, s] + self.dist[s, depot] - self.dist[ant, depot]
            if det < best_det:
                best_det = det
                best_s = s
                best_t_depot = t_depot

        return (best_s, best_t_depot) if best_s is not None else None

    # ==================================================================
    # Fase 4 – Evaluate  (calcula [f1, f2, f3])
    # f3 agora é a Violação de Janela de Tempo tolerada de toda a solução
    # ==================================================================
    def _evaluate(self, expanded_routes, tw_v):
        f1 = float(len(expanded_routes))
        f2 = 0.0

        for route in expanded_routes:
            ant = route[0]
            for p in route[1:]:
                f2 += self.dist[ant, p]
                ant = p

        f3 = tw_v
        return np.array([f1, f2, f3])
