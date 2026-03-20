Deixa eu pensar com calma sobre o que está acontecendo antes de propor qualquer mudança.

---

## Diagnóstico do problema real

O operador de crossover faz crossover de rotas, remove clientes conflitantes e reinsere órfãos. O problema não é o CDP em si — o CDP está fazendo exatamente o que deveria. O problema é que os operadores são **estruturalmente inadequados para o EVRP**: não porque precisem inserir estações, mas porque destroem a estrutura energética existente de forma patológica.

Quando clientes são removidos de uma rota, as estações que estavam entre eles *ficam*. Você acaba com rotas tipo `[D → s1 → s2 → c3 → D]` onde duas estações consecutivas sem clientes entre elas consomem autonomia sem necessidade. Depois, os órfãos são reinseridos puramente por custo de distância, sem nenhuma consideração energética, criando trechos longos sem recarga. O resultado: quase todo filho é inviável, e sob CDP os filhos infeasible perdem para qualquer pai feasible, então a população congela na melhor solução viável da geração 0.

Isso não é o CDP se comportando mal — é o operador de crossover destruindo estrutura que precisaria ser mantida.

## O princípio que guia a solução

A distinção central para manter coerência é:

**Reparação energética** = inserir estações novas para corrigir déficits → isso é o ORPG, pertence à Fase 2, daria vantagem indevida ao baseline.

**Integridade estrutural** = não destruir desnecessariamente a cobertura energética que já existe → isso é requisito mínimo de qualquer operador EVRP razoável na literatura, não constitui vantagem.

Os operadores atuais violam a integridade estrutural. A correção não é adicionar reparação — é parar de destruir o que já existe.

## As três correções específicas

### 1. Limpeza de estações órfãs após crossover

Quando clientes são removidos de uma rota, estações que ficam sem clientes adjacentes se tornam "zumbis" — consomem tempo e criam ilusão de cobertura energética que não existe. A regra é simples: uma estação só tem razão de existir se houver pelo menos um cliente em algum dos trechos que ela cobre.O diagrama abaixo ilustra por que o problema acontece e o que a correção resolve:---

## As três correções e o código

### Correção 1: limpeza de estações zumbi (`_cleanup_zombie_stations`)

Esta função deve ser chamada logo após `_build_offspring`, antes do `CI`. Não insere nada — apenas remove estações que perderam sua razão de existir.

```python
def _cleanup_zombie_stations(route: Route) -> None:
    """
    Remove estações que ficaram sem clientes adjacentes após remoção de clientes.
    Uma estação é 'zumbi' se os nós imediatamente anterior e posterior são
    ambos: depósito, ou outra estação, ou se ela é o único nó não-depósito.
    Não insere nada — apenas remove redundâncias estruturais.
    """
    changed = True
    while changed:
        changed = False
        new_visits = []
        for i, v in enumerate(route.visits):
            if v.node_type != NodeType.STATION:
                new_visits.append(v)
                continue
            # Verifica vizinhos
            prev_type = route.visits[i-1].node_type if i > 0 else None
            next_type = route.visits[i+1].node_type if i < len(route.visits)-1 else None
            # Zumbi: estação entre depósito/estação e depósito/estação (sem cliente próximo)
            prev_is_noncust = prev_type in (NodeType.DEPOT, NodeType.STATION)
            next_is_noncust = next_type in (NodeType.DEPOT, NodeType.STATION)
            if prev_is_noncust and next_is_noncust:
                changed = True  # remove e reinicia varredura
                continue
            new_visits.append(v)
        route.visits = new_visits
```

---

### Correção 2: reinserção de órfãos com guia de energia (`_reinsert_orphans` — substituição)

A lógica muda em dois pontos: (a) ao avaliar posições, verifica se a energia no ponto de inserção é suficiente para chegar ao cliente sem déficit imediato; (b) se nenhuma posição com energia suficiente existir, abre nova rota em vez de forçar uma inserção catastrófica. Sem inserir estações.

```python
def _reinsert_orphans(sol: Solution, orphans: list, inst: EVRPInstance) -> None:
    for c_id in orphans:
        best_pos, best_cost = None, float('inf')
        node_c = inst.nodes[c_id]
        found_energy_ok = False  # há alguma posição energeticamente plausível?

        for r_idx, route in enumerate(sol.routes):
            demand_r = sum(inst.nodes[v.node_id].demand for v in route.visits
                           if v.node_type == NodeType.CUSTOMER)
            if demand_r + node_c.demand > inst.Q + 1e-9:
                continue

            # Estima energia aproximada em cada posição (usa departure_energy se disponível,
            # senão faz estimativa conservadora da energia restante após visita anterior)
            curr_energy_est = inst.B
            for pos in range(1, len(route.visits)):
                prev_id = route.visits[pos-1].node_id
                next_id = route.visits[pos].node_id
                e_to_c   = inst.energy[prev_id][c_id]
                e_c_next = inst.energy[c_id][next_id]
                cost_dist = (inst.dist[prev_id][c_id] + inst.dist[c_id][next_id]
                             - inst.dist[prev_id][next_id])

                # Energia estimada ao chegar na posição (aproximada, sem recalcular perfil)
                # departure_energy está disponível se CI já foi rodado, senão usa heurística
                if route.visits[pos-1].departure_energy > 0:
                    energy_at_pos = route.visits[pos-1].departure_energy
                else:
                    energy_at_pos = inst.B  # conservador: assume bateria cheia no início

                energy_ok = (energy_at_pos - e_to_c) >= -1e-9  # chegaria sem déficit

                if energy_ok:
                    found_energy_ok = True
                    if cost_dist < best_cost:
                        best_cost = cost_dist
                        best_pos = (r_idx, pos)
                else:
                    # Posição inviável energeticamente: aceita apenas se não há opção viável
                    # e o custo é razoável (evita inserções claramente destruidoras)
                    if not found_energy_ok and cost_dist < best_cost:
                        best_cost = cost_dist
                        best_pos = (r_idx, pos)

        if best_pos and found_energy_ok:
            r_idx, pos = best_pos
            sol.routes[r_idx].visits.insert(pos, Visit(c_id, NodeType.CUSTOMER))
        elif best_pos and not found_energy_ok:
            # Nenhuma posição energeticamente ok em nenhuma rota existente:
            # abre nova rota em vez de forçar inserção catastrófica
            # (nova rota começa com bateria cheia → apenas 1 cliente → provavelmente viável)
            new_r = Route(visits=[
                Visit(inst.depot_id, NodeType.DEPOT),
                Visit(c_id, NodeType.CUSTOMER),
                Visit(inst.depot_id, NodeType.DEPOT),
            ])
            sol.routes.append(new_r)
        else:
            # Fallback: abre rota nova (cliente não coube por capacidade em nenhuma rota)
            new_r = Route(visits=[
                Visit(inst.depot_id, NodeType.DEPOT),
                Visit(c_id, NodeType.CUSTOMER),
                Visit(inst.depot_id, NodeType.DEPOT),
            ])
            sol.routes.append(new_r)
```

---

### Correção 3: Or-opt (relocate) em vez de 2-opt para mutação

O 2-opt inverte segmentos inteiros, o que pode separar um cliente de sua estação de recarga mais próxima e criar trechos longos sem cobertura energética. Or-opt move um único cliente, perturbação muito menor.

```python
def _or_opt_mutation(sol: Solution, inst: EVRPInstance) -> Solution:
    """
    Move um cliente aleatório para a melhor posição disponível em qualquer rota.
    Critério: menor custo de inserção (distância). Não insere estações.
    Muito menos destrutivo que 2-opt para perfis energéticos.
    """
    if not sol.routes:
        return sol
    new_sol = sol.copy()

    # Escolhe cliente aleatório
    all_cust_positions = [
        (r_idx, v_idx)
        for r_idx, route in enumerate(new_sol.routes)
        for v_idx, v in enumerate(route.visits)
        if v.node_type == NodeType.CUSTOMER
    ]
    if not all_cust_positions:
        return new_sol

    src_r, src_v = random.choice(all_cust_positions)
    c_id = new_sol.routes[src_r].visits[src_v].node_id
    node_c = inst.nodes[c_id]

    # Remove o cliente da rota de origem
    new_sol.routes[src_r].visits.pop(src_v)
    # Se rota ficou vazia (só depósitos), remove a rota
    if new_sol.routes[src_r].n_customers() == 0:
        new_sol.routes.pop(src_r)
        # Reajusta índices de busca
        search_routes = list(range(len(new_sol.routes)))
    else:
        search_routes = list(range(len(new_sol.routes)))

    # Encontra melhor posição de reinserção com guia de energia
    best_pos, best_cost = None, float('inf')
    found_energy_ok = False

    for r_idx in search_routes:
        route = new_sol.routes[r_idx]
        demand_r = sum(inst.nodes[v.node_id].demand for v in route.visits
                       if v.node_type == NodeType.CUSTOMER)
        if demand_r + node_c.demand > inst.Q + 1e-9:
            continue
        for pos in range(1, len(route.visits)):
            prev_id = route.visits[pos-1].node_id
            next_id = route.visits[pos].node_id
            cost = (inst.dist[prev_id][c_id] + inst.dist[c_id][next_id]
                    - inst.dist[prev_id][next_id])
            energy_at_pos = (route.visits[pos-1].departure_energy
                             if route.visits[pos-1].departure_energy > 0 else inst.B)
            energy_ok = (energy_at_pos - inst.energy[prev_id][c_id]) >= -1e-9
            if energy_ok:
                found_energy_ok = True
                if cost < best_cost:
                    best_cost = cost
                    best_pos = (r_idx, pos)
            elif not found_energy_ok and cost < best_cost:
                best_cost = cost
                best_pos = (r_idx, pos)

    if best_pos:
        r_idx, pos = best_pos
        new_sol.routes[r_idx].visits.insert(pos, Visit(c_id, NodeType.CUSTOMER))
    else:
        # Abre nova rota
        new_sol.routes.append(Route(visits=[
            Visit(inst.depot_id, NodeType.DEPOT),
            Visit(c_id, NodeType.CUSTOMER),
            Visit(inst.depot_id, NodeType.DEPOT),
        ]))

    new_sol._dirty = True
    return new_sol


class EVRPMutation(Mutation):
    def __init__(self, prob: float = 0.15):
        super().__init__()
        self.prob = prob

    def _do(self, problem, X, **kwargs):
        for i in range(len(X)):
            if random.random() < self.prob:
                sol: Solution = X[i, 0]
                X[i, 0] = _or_opt_mutation(sol, problem.instance)
        return X
```

---

### Onde encaixar a limpeza no crossover

Em `_build_offspring`, adicione uma linha logo após `_reinsert_orphans`:

```python
def _build_offspring(base, to_remove, new_route, inst):
    child = base.copy()
    # ... remoção de clientes e conserto de depósitos (igual ao anterior) ...
    child.routes.append(...)
    _reinsert_orphans(child, orphans, inst)
    # NOVO: limpar estações zumbi em todas as rotas após reinserção
    for route in child.routes:
        _cleanup_zombie_stations(route)
    child._dirty = True
    return child
```

---

## Por que isso mantém a comparação justa

A distinção que importa aqui é entre dois tipos de melhoria nos operadores:

**O que foi feito (integridade estrutural):** preferir posições onde a energia já existente na solução é suficiente, e não criar rotas energeticamente impossíveis gratuitamente. Isso não adiciona cobertura energética nova — não insere estações, não repara déficits. É o equivalente, no VRP clássico, de verificar capacidade na reinserção de clientes: ninguém consideraria isso "vantagem indevida".

**O que não foi feito (reparação energética — reservado para o IAS-EVRP):** inserir estações para corrigir trechos deficientes, usar θ_insert para decidir o que corrigir, o ORPG como pipeline IES → viável. Nada disso está aqui.

O resultado esperado com essas correções é que cruzamentos de dois pais viáveis produzam uma mistura — talvez 40–60% viáveis, 20–30% IES, o restante IC ou IJT. Esse é exatamente o cenário que permite observar o CDP atuando de forma uniforme sobre todos os tipos, o mascaramento acontecendo (IES com `f2` menor que viáveis), e a convergência seguindo seu curso — o que torna o experimento válido como baseline e como evidência para a Fase 2.