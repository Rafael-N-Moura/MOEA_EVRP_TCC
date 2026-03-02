# Heurística de Construção de Rotas — Decoder EVRPTW-PR

Documento didático que descreve em detalhe como a heurística de construção de rotas implementada em `src/decoder.py` transforma uma **permutação de clientes** (genótipo) em uma **solução completa** (fenótipo) com rotas, recargas e métricas, considerando os **modos conservador** e **agressivo**.

---

## 1. Contexto do problema: EVRPTW-PR

- **EVRPTW-PR**: *Electric Vehicle Routing Problem with Time Windows and Partial Recharging*
- **Entidades**: um **depósito** (D0), **estações de recarga** (S0–S20), **clientes** (C1, C2, …).
- **Cada cliente** tem: coordenadas (x, y), demanda, janela de tempo (ready_time, due_date), tempo de serviço.
- **Veículo elétrico**: capacidade de carga C, bateria Q, consumo r (energia por unidade de distância), velocidade v, taxa de recarga g.
- **Objetivos**: minimizar custo (veículos + distância) e minimizar insatisfação média (janelas de tempo são *soft*).
- **Restrições duras**: capacidade de carga (G1) e bateria (G2). O decoder pode operar em modo **viável** (G2=0) ou **inviável controlado** (G2>0, limitado por tetos).

O decoder é a **heurística construtiva** que, dado uma ordem de clientes, decide:
- quando abrir/fechar rota (novo veículo),
- quando ir a uma estação para recarregar,
- quanto recarregar,
- e em modo agressivo quando aceitar “dívida” de bateria (G2) e quando fechar rota por teto de G2 ou por limite de clientes.

---

## 2. Entrada e saída do decoder

### 2.1 Entrada

- **`individual`**: lista de inteiros — permutação de **índices** dos clientes (ex.: `[0, 5, 2, …]`).
- **`context`**: instância de `Context` com depósito, estações, clientes, capacidade de bateria/carga, consumo, velocidade, taxa de recarga, etc.
- **`force_battery_feasible`**: 
  - `True` → **modo conservador**: nunca aceita dívida de bateria; recargas preventivas garantem G2=0.
  - `False` → **modo agressivo** (ou radical): pode aceitar dívida (G2>0), com controle por perfil.
- **`use_radical_infeasible`**: só relevante se `force_battery_feasible=False`. Se `True`, modo **radical**: não insere estações; só movimento em linha reta, acumulando G2 (maior gap inviável vs viável).

### 2.2 Saída

- **`Solution`**: objeto com:
  - **`routes`**: lista de `Route`, cada uma com `steps` (depósito → clientes/estações → depósito).
  - **`total_vehicles`**, **`total_distance`**, **`total_cost`**, **`avg_dissatisfaction`**.
  - **`battery_violation`** (G2): déficit total de energia (0 se viável).
  - **`skipped_customer_ids`**: clientes não visitados (ex.: impossíveis por bateria no conservador).
  - **`violations`**: mensagens de atraso (tempo) e outras.

---

## 3. Perfis de recarga: Conservative vs Aggressive

O comportamento da recarga é parametrizado por um **perfil** (`RechargeProfile`). O decoder escolhe o perfil assim:

- **`force_battery_feasible=True`** → `PROFILE_CONSERVATIVE`
- **`force_battery_feasible=False`** e não radical → `PROFILE_AGGRESSIVE`
- **Modo radical** → `profile = None` (sem estações).

### 3.1 Parâmetros do perfil

| Parâmetro | Conservador (C) | Agressivo (A) | Significado |
|-----------|------------------|---------------|-------------|
| **b_safe_ratio** | 0,35 | 0,42 | Recarga preventiva quando SOC &lt; este % da capacidade (ex.: 35% ou 42%). |
| **b_critical_ratio** | 0,15 | 0,14 | Abaixo deste %, considera situação crítica (voltar/recarregar). |
| **safety_margin_ratio** | 0,20 | 0,18 | Margem de segurança (em % da capacidade) após recarga. |
| **prefer_nearest_station** | False | True | C: Smart Detour (menor desvio). A: estação mais próxima. |
| **g2_max_ratio** | None | 0,05 | Teto de G2 por rota = este valor × Q; acima disso fecha rota. |
| **max_customers_per_route** | None | 3 | Máximo de clientes por rota no agressivo (força mais rotas/veículos). |

- **Conservador**: prioriza viabilidade (G2=0), recarga mais cedo (b_safe 35%), margem grande (20%), escolha de estação por **menor desvio** (Smart Detour).
- **Agressivo**: menos veículos em média, aceita um pouco de G2 mas limitado; recarga ainda preventiva (b_safe 42%), estação **mais próxima**, teto G2 por rota (5% Q) e no máximo 3 clientes por rota para forçar split.

---

## 4. Visão geral do fluxo principal

O decoder percorre a permutação de clientes **em ordem**. Para cada cliente, na rota atual:

1. **Passo A — Capacidade**: se carga atual + demanda do cliente &gt; C, fecha a rota (retorno ao depósito), abre novo veículo e **não avança** o índice do cliente (o mesmo cliente será tentado no novo veículo).
2. **Passo B — Decisão de ir ao cliente (bateria)**:
   - **Conservador**: exige bateria ≥ “total necessário” (ida ao cliente + volta ao refúgio mais próximo + margem). Se não tiver, entra em loop de **recarga preventiva** até atingir esse total (ou até split/descarte). Nunca aceita dívida.
   - **Agressivo**: pode recarregar preventivamente (com perfil A) ou, sob condições, **viajar com dívida** para o cliente ou para estação; há **split por teto G2** e por **max_customers_per_route**.
3. **Passo C — Visita ao cliente**: calcula tempo de viagem, chegada, janela (espera/atraso), satisfação, adiciona o passo do cliente, atualiza posição, bateria e tempo.
4. **Passo D — Pós-visita (só agressivo)**: se ficar “ilhado” (bateria &lt; energia até estação mais próxima), faz **resgate com dívida** até uma estação; em seguida verifica **max_customers_per_route** e **g2_max** para eventual fechamento de rota.

No final, o último veículo retorna ao depósito via `return_to_depot`.

---

## 5. Funções auxiliares (resumo)

### 5.1 Energia e “total necessário”

- **`_calculate_energy_needed(from_node, to_node, context)`**  
  Energia = distância × consumo.

- **`_calculate_total_energy_for_customer(current_position, customer, context)`**  
  Retorna `(energia_até_cliente, energia_total_com_segurança)`.  
  O “total com segurança” é: ida ao cliente + menor de (cliente→estação mais próxima, cliente→depósito). Usado para saber quanto de bateria precisamos para ir ao cliente e ainda ter “refúgio”.

### 5.2 Escolha da estação: Smart Detour vs mais próxima

**`_get_best_station(current_position, destination, current_battery, context, force_battery_feasible, prefer_nearest_station, debug)`**

- **Smart Detour** (`prefer_nearest_station=False`, perfil conservador):
  - Desvio = (distância atual→estação) + (estação→destino) − (distância direta atual→destino).
  - Escolhe a estação **alcançável** com menor desvio (ou fallback para mais próxima se nenhuma alcançável).
- **Mais próxima** (`prefer_nearest_station=True`, perfil agressivo):
  - Escolhe a estação **mais próxima** da posição atual (alcançável ou não; se não alcançável, pode ser usada em modo dívida depois).

`force_battery_feasible` controla se só considera estações alcançáveis para “melhor” ou também candidata para fallback.

### 5.3 Recarga preventiva

**`_should_recharge_preventively(current_battery, battery_capacity, energy_needed, profile)`**

Retorna `True` se:

- SOC &lt; b_safe × Q, ou  
- bateria &lt; energia necessária, ou  
- bateria após consumir essa energia ficaria &lt; b_critical × Q.

Assim, o conservador (e o agressivo quando em modo preventivo) recarrega “cedo” para não chegar perto do crítico.

### 5.4 Quanto recarregar

**`_calculate_recharge_amount(...)`**

- Calcula energia total necessária da **estação** até o cliente e daí ao refúgio (estação ou depósito mais próximo).
- Desejo = essa energia + **margem** (safety_margin_ratio × Q).
- Recarga = mínimo entre (desejo − bateria atual) e (Q − bateria atual). Se total necessário &gt; Q, recarrega até encher.

### 5.5 Viagem com dívida

**`_travel_with_debt(route, current_position, current_battery, current_load, current_time, destination, context, solution, debug)`**

- Usado quando não há bateria suficiente para o trecho.
- Calcula déficit (energia necessária − bateria), soma em `solution.battery_violation` (G2).
- Atualiza tempo de viagem; bateria no destino fica 0 (ou recarga se destino for estação).
- Se o destino for **estação**, adiciona o passo da estação (com recarga fixa 50% da capacidade) e retorna posição = estação, bateria após recarga, tempo.  
- Se o destino for **cliente**, apenas retorna (cliente será adicionado pelo fluxo principal).

### 5.6 Recarga na estação

**`_recharge_at_station(..., allow_debt, force_battery_feasible, profile, ...)`**

- Escolhe a melhor estação via `_get_best_station` (Smart Detour ou mais próxima conforme perfil).
- Se não conseguir chegar à estação:
  - Com `allow_debt=True` e `solution` não nulo: chama `_travel_with_debt` até a estação (acumula G2).
  - Caso contrário: retorna sem mudar posição/bateria/tempo (fluxo principal trata como “preso” e faz split ou descarte).
- Se conseguir chegar: consome energia até a estação, calcula `_calculate_recharge_amount`, adiciona passo da estação, retorna nova posição (estação), nova bateria, novo tempo.

### 5.7 Retorno ao depósito

**`return_to_depot(route, current_position, depot, current_battery, current_load, current_time, context, solution, force_battery_feasible, profile, debug)`**

- Calcula energia necessária para ir ao depósito.
- Se bateria &lt; necessário:
  - **Conservador** ou **agressivo com déficit pequeno** (≤ 6% Q): tenta recarga preventiva (ir a estação, recarregar, inclusive cadeia de estações se precisar) **sem** registrar dívida.
  - Se não conseguir chegar à estação no retorno (agressivo com perfil): pode registrar o déficit em G2.
  - **Agressivo com déficit grande** e sem tentativa preventiva: registra dívida em G2 e “retorna” com bateria 0.
- Adiciona o passo final de chegada ao depósito (arrival_time, battery_arrival, load=0).

---

## 6. Modo conservador (detalhado)

- **Perfil**: `PROFILE_CONSERVATIVE` (b_safe=0,35, margem 20%, Smart Detour).
- **Objetivo**: G2 = 0 sempre; clientes impossíveis são **descartados** (`skipped_customer_ids`).

### 6.1 Passo B no conservador

1. **Total necessário**:  
   `total_energy_needed = energy_to_customer + energy_customer_to_safety + safety_margin_ratio × Q`

2. **Cliente impossível**:  
   Se (energia ida + volta ao refúgio) &gt; Q, ou se total com margem &gt; Q, cliente é descartado (sem alterar G2).

3. **Loop de recarga preventiva** (até bateria ≥ total_energy_needed e sem acionar preventiva por b_safe/b_critical):
   - Chama `_recharge_at_station` com `allow_debt=False`, `force_battery_feasible=True`, perfil conservador.
   - Se após recarga a posição não mudou (não conseguiu chegar à estação):
     - Se dá para voltar ao depósito: `return_to_depot`, fecha rota, abre novo veículo, **recalcula** total necessário para o **mesmo** cliente no novo veículo; se ainda impossível, descarta.
     - Se não dá para voltar: mesmo fluxo de fechar rota e abrir nova; cliente pode ser descartado.
   - Se mudou de posição: atualiza posição/bateria/tempo e repete o critério (bateria ≥ total necessário e preventiva).  
   - Proteção: máximo de 50 iterações de recarga; se total necessário &gt; Q mesmo com bateria cheia, descarta cliente.

4. **Passo C**: Só visita o cliente se tiver bateria ≥ energia até o cliente. No conservador, após o loop isso deve estar garantido; se por edge case não estiver, descarta cliente (sem G2).

### 6.2 Retorno ao depósito (conservador)

- Sempre tenta recarga preventiva se bateria &lt; necessário para o depósito (incluindo cadeia de estações). Não registra dívida; se não conseguir chegar a nenhuma estação no caminho, o comportamento depende do trecho (cadeia limitada a 20 iterações).

---

## 7. Modo agressivo (detalhado)

- **Perfil**: `PROFILE_AGGRESSIVE` (b_safe=0,42, margem 18%, estação mais próxima, g2_max_ratio=0,05, max_customers_per_route=3).
- **Objetivo**: Menos veículos em média, algumas soluções com G2=0 e muitas com G2 &gt; 0 mas limitado (teto por rota e por decisões de split).

### 7.1 Passo B no agressivo

1. **Decisão de recarregar**:
   - `need_recharge_agg = (bateria < energia até cliente)` OU  
     `(SOC < b_safe × Q)` OU  
     `(bateria < total_energy_agg)` onde  
     `total_energy_agg = energia até cliente + max(volta ao refúgio, volta ao depósito) + margem × Q`.
   - Objetivo: evitar dívida desnecessária no retorno (parte das soluções com G2=0).

2. **Antes de ir à estação (com dívida possível)**:
   - Calcula teto G2 por rota: `g2_max_per_route = g2_max_ratio × Q` (ex.: 0,05 × Q).
   - Estima déficit até a melhor estação. Se `current_route_g2 + deficit_to_station > g2_max_per_route`, **não** vai com dívida; faz **split**: `return_to_depot`, fecha rota, abre novo veículo e **continua** com o mesmo cliente (sem avançar índice).

3. **Recarga no agressivo**:
   - `_recharge_at_station` com `allow_debt=False` (não permite dívida **na ida à estação**), `force_battery_feasible=False` (pode escolher estação não alcançável como candidata).
   - G2 acumulado na rota é atualizado com o que foi somado em `solution.battery_violation` nesta chamada (no agressivo atual, a recarga em si não gera dívida porque allow_debt=False).
   - Se ficar “preso” (posição não mudou): retorna ao depósito, fecha rota, abre nova, **continue** (mesmo cliente).

4. **Passo C — Bateria insuficiente para ir ao cliente**:
   - Se `current_route_g2 + deficit > g2_max_per_route`: split (retorno ao depósito, novo veículo, **continue** com o mesmo cliente).
   - Caso contrário: **viagem com dívida** até o cliente via `_travel_with_debt`; atualiza `current_route_g2`, posição, tempo; bateria após chegada = 0 (o passo do cliente é adicionado em seguida).

### 7.2 Passo D no agressivo (pós-visita)

1. **Resgate se ilhado**:  
   Se, após visitar o cliente, `current_battery < energy_customer_to_safety`, considera “ilhado”. Escolhe melhor estação para resgate (destino = depósito) com `_get_best_station(..., force_battery_feasible=False)` e faz `_travel_with_debt` até essa estação (acumula G2 na rota).

2. **Fechar rota por max_customers_per_route**:  
   Se a rota atual já tem ≥ 3 clientes (valor de `max_customers_per_route`), fecha rota (return_to_depot), abre novo veículo.

3. **Fechar rota por g2_max**:  
   Se `current_route_g2 > g2_max_per_route`, fecha rota e abre novo veículo.

Assim, o agressivo mantém G2 por rota sob controle e força mais rotas (menos clientes por rota), gerando um número de veículos entre ~10–30% abaixo do conservador em várias instâncias, com uma fração de soluções com G2=0 e a maioria com G2 abaixo do teto.

---

## 8. Resgate “ilhado” (apenas agressivo)

Depois de visitar um cliente, se a bateria ficar abaixo da energia mínima para chegar a qualquer estação (ou depósito), o veículo está “ilhado”. No modo agressivo (e não radical):

- Chama `_get_best_station(current_position, context.depot, current_battery, context, force_battery_feasible=False)` para escolher a melhor estação para ir em direção ao depósito.
- Chama `_travel_with_debt` até essa estação; o déficit é contado em G2 e o passo da estação (com recarga) é inserido pela própria `_travel_with_debt` quando o destino é estação.
- Posição e bateria passam a ser da estação após recarga; o fluxo segue para o próximo cliente (ou fechamento por max_customers / g2_max).

---

## 9. Tabela comparativa rápida

| Aspecto | Conservador | Agressivo |
|--------|-------------|-----------|
| **Perfil** | PROFILE_CONSERVATIVE | PROFILE_AGGRESSIVE |
| **G2** | Sempre 0 | Pode &gt; 0, limitado por g2_max_ratio por rota |
| **Escolha de estação** | Smart Detour (menor desvio) | Mais próxima |
| **Recarga preventiva** | b_safe 35%, margem 20% | b_safe 42%, margem 18% |
| **Dívida** | Nunca | Sim: para cliente, para estação (resgate), no retorno (se déficit &gt; 6% Q) |
| **Split** | Por capacidade; por “preso” (não alcança estação) | Por capacidade; por g2_max antes de recarga/cliente; por max_customers (3); por “preso” |
| **Clientes impossíveis** | Descartados (skipped) | Evitados quando possível; podem gerar descarte ou split |
| **Número de veículos** | Maior (mais rotas “seguras”) | Menor em média (~10–30% em várias instâncias) |

---

## 10. Conclusão

A heurística do `decoder.py` é uma **construtiva gulosa** que:

- **Respeita a ordem** da permutação (prioridade dos clientes).
- **Garante capacidade** fechando rota e abrindo novo veículo.
- **Conservador**: garante G2=0 com recarga preventiva e Smart Detour; clientes impossíveis são descartados.
- **Agressivo**: reduz veículos e custo aceitando G2 limitado por rota (g2_max_ratio) e por cliente por rota (max_customers_per_route), com recarga “mais próxima”, resgate com dívida quando ilhado e retorno com dívida quando o déficit é grande.

Assim, o mesmo genótipo (permutação) pode produzir soluções **viáveis** (conservador) ou **inviáveis controladas** (agressivo), permitindo comparar frentes de Pareto e estratégias de busca (ex.: battery-focused vs NSGA-II) no mesmo problema EVRPTW-PR.
