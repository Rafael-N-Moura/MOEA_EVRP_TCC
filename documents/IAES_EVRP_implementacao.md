**DETALHAMENTO DE IMPLEMENTAÇÃO**

**IAS-EVRP: Quatro Componentes Fundamentais**

_Representação · Inicialização · Crossover · Classificador de Inviabilidade_

_Documento complementar ao framework IAS-EVRP_

_Coerente com Cai et al. (2026) - CMOEA-IAS - e Ou et al. (2024) - CEOA_

# **1\. Representação de Soluções**

A representação é o alicerce sobre o qual todos os operadores do IAS-EVRP operam. Ela precisa satisfazer um conjunto de exigências simultâneas derivadas diretamente da arquitetura proposta: suportar clientes e estações com semânticas distintas, armazenar o perfil energético completo para que o Classificador de Inviabilidade (CI) opere em O(1) por nó, expor os trechos deficientes para o Estimador de Objetivos Corrigidos (EOC), e permitir que o Operador de Reparo Parcial Guiado (ORPG) e o Operador de Remoção de Estação (ORE) modifiquem a solução sem recalcular o perfil do zero.

## **1.1 Hierarquia de Objetos**

A representação é estruturada em três camadas hierárquicas:

Solution

├── routes: List\[Route\] # lista de rotas (uma por veículo)

├── metadata: SolutionMetadata # informações agregadas da solução

└── cv_components: CVVector # vetor de violação separado por tipo

Route

├── visits: List\[Visit\] # sequência de nós visitados

├── energy_profile: List\[float\] # nível de bateria em cada nó

├── time_profile: List\[float\] # tempo de chegada em cada nó

├── deficient_segments: List\[Segment\] # trechos com déficit energético

└── cv_route: CVRouteVector # componentes de violação desta rota

Visit

├── node_id: int # índice no grafo G = (V, E)

├── node_type: NodeType # DEPOT | CUSTOMER | STATION

├── arrival_energy: float # nível de bateria ao chegar

├── departure_energy: float # nível de bateria ao partir

├── arrival_time: float # instante de chegada

├── service_start: float # inicio do serviço (>= b_i)

├── departure_time: float # instante de partida

├── waiting_time: float # max(0, b_i - arrival_time)

└── delay_time: float # max(0, arrival_time - e_i)

Segment # trecho entre dois nós consecutivos

├── from_idx: int # índice em visits\[\]

├── to_idx: int # índice em visits\[\]

├── energy*consumed: float # e*{ij} consumido no trecho

├── energy_deficit: float # max(0, energy_consumed - arrival_energy_from)

└── min_insert_cost: float # δ_dist(i,j) - calculado lazy pelo EOC

SolutionMetadata

├── n_vehicles: int # |routes| = f1

├── total_distance: float # soma de dist por rota = f2

├── makespan: float # max(travel_time por rota) = f3

├── total_waiting: float # soma de waiting_time = f4

├── total_delay: float # soma de delay_time = f5

├── inf_type: InfeasType # FEASIBLE | IES | IEC | IC | IJT | IM

└── corrected_obj: Optional\[ObjectiveVector\] # f̂ - preenchido pelo EOC

CVVector

├── cv_energy: float # violação energética normalizada (IES/IEC)

├── cv_cascade: float # severidade de cascata normalizada (IEC)

├── cv_cap: float # violação de capacidade normalizada (IC)

└── cv_tw: float # violação de janela de tempo normalizada (IJT)

## **1.2 Invariantes Estruturais**

A representação mantém um conjunto de **invariantes** que devem ser verdadeiros para qualquer objeto Solution em qualquer ponto da execução do algoritmo:

- **I1 - Cobertura de clientes:** Todo cliente c ∈ C aparece em exatamente um Visit de exatamente uma Route, com node_type = CUSTOMER.
- **I2 - Limite de rotas:** Toda Route começa e termina com um Visit de node_type = DEPOT. O nó depósito não aparece no meio de nenhuma rota.
- **I3 - Multiplicidade de estações:** Uma estação s ∈ S pode aparecer em zero ou mais Routes, e em zero ou mais posições dentro da mesma Route. Não há restrição de unicidade para estações.
- **I4 - Consistência do perfil energético:** Para todo Visit v\[j\] com j > 0: v\[j\].arrival_energy = v\[j-1\].departure_energy - e(v\[j-1\].node_id, v\[j\].node_id). Se v\[j-1\].node_type = STATION, então v\[j-1\].departure_energy = B (recarga completa). Caso contrário, departure_energy = arrival_energy.
- **I5 - Consistência do perfil de tempo:** Para todo Visit v\[j\]: v\[j\].arrival_time = v\[j-1\].departure_time + t(v\[j-1\].node_id, v\[j\].node_id). A service_start = max(arrival_time, b_i) onde b_i é o início da janela de tempo do nó.
- **I6 - Derivação dos CVs:** Os valores em cv_route e cv_components são sempre derivados do conteúdo de visits\[\] e não são mantidos independentemente. Qualquer modificação em visits\[\] invalida os CVs e exige recalculação via CI.

**Relação com o CI e o EOC**

O invariante I6 é crucial: o CI nunca assume que os campos cv\_\* estão corretos, sempre recalcula após qualquer operação de modificação. O EOC, por sua vez, usa os deficient_segments pré-calculados (que são um subproduto do CI) para evitar repetir a varredura do perfil energético. A sinergia é: CI calcula perfil + identifica segmentos deficientes + popula CVs; EOC consome deficient_segments e popula corrected_obj.

## **1.3 Exemplo Concreto de Representação**

Considere uma instância com 8 clientes (C = {1,...,8}), 3 estações (S = {s1, s2, s3}), depósito D = 0, capacidade B = 100 unidades de energia. A solução abaixo tem 2 rotas, sendo a Rota 1 energeticamente viável e a Rota 2 com IES em um trecho:

Solution {

routes: \[

Route 1 (veículo 1) - VIÁVEL:

visits: \[

Visit(D, DEPOT, dep_energy=100, dep_time=0),

Visit(1, CUSTOMER, arr_energy=72, dep_time=15, wait=0, delay=0),

Visit(s1, STATION, arr_energy=45, dep_energy=100, ...), # recarga

Visit(3, CUSTOMER, arr_energy=68, dep_time=55, wait=0, delay=0),

Visit(5, CUSTOMER, arr_energy=31, dep_time=75, wait=0, delay=0),

Visit(D, DEPOT, arr_energy=8 ) # OK >=0

\]

energy_profile: \[100, 72, 45, 100, 68, 31, 8\]

deficient_segments: \[\] # nenhum

cv_route: { energy: 0, cascade: 0, cap: 0, tw: 0 }

Route 2 (veículo 2) - IES:

visits: \[

Visit(D, DEPOT, dep_energy=100, dep_time=0),

Visit(2, CUSTOMER, arr_energy=60, dep_time=20, wait=0, delay=0),

Visit(4, CUSTOMER, arr_energy=10, dep_time=40, wait=0, delay=0),

Visit(6, CUSTOMER, arr_energy=-25, dep_time=??) # DÉFICIT!

Visit(7, CUSTOMER, arr_energy=-60, ...),

Visit(8, CUSTOMER, arr_energy=-80, ...),

Visit(D, DEPOT, arr_energy=-95 )

\]

energy_profile: \[100, 60, 10, -25, -60, -80, -95\]

deficient_segments: \[

Segment(from=4, to=6, deficit=35, min_insert_cost=None) # lazy

\]

cv_route: { energy: 35, cascade: 3, cap: 0, tw: 0 }

\# cascade=3: 3 nós após o déficit inicial

\]

metadata: { n_vehicles:2, total_distance:310, makespan:120, ... }

cv_components: { cv_energy: 0.35, cv_cascade: 0.12, cv_cap: 0.0, cv_tw: 0.0 }

\# inf_type = IES (cv_energy > 0, cv_cascade > 0 mas cascade veio de 1 segmento)

\# NOTA: cascade=3 significa 3 visits consecutivos em débito após o 1o déficit

\# Se o déficit tivesse 2 segmentos INDEPENDENTES, seria ainda IES

\# Se tivesse 2 segmentos consecutivos SEM estação entre eles → IEC

}

**Distinção IES vs IEC na Representação**

O campo deficient_segments é a chave para distinguir IES de IEC. Se a lista contém apenas Segments que, quando ordenados por from_idx, são separados por pelo menos um Visit do tipo STATION entre eles (ou se há apenas um único Segment deficiente), a solução é IES. Se dois ou mais Segments consecutivos não têm nenhuma STATION entre eles (ausência de recarga que poderia ter interrompido a cascata), a solução é IEC.

Na prática: def is_IEC(route): return any(s1.to_idx == s2.from_idx for s1,s2 in zip(segs, segs\[1:\])) - dois segmentos deficientes adjacentes sem estação intermediária caracterizam cascata.

## **1.4 Operações Fundamentais na Representação**

Todas as operações que modificam a solução seguem o protocolo **Modificar → Recomputar Perfil → Invocar CI**. As operações primitivas são:

| **Operação**                   | **Parâmetros**                                                     | **Custo Temporal**                                         | **Invalida**                                                   |
| ------------------------------ | ------------------------------------------------------------------ | ---------------------------------------------------------- | -------------------------------------------------------------- |
| insert_station(route, pos, s)  | route: índice da rota; pos: posição após visits\[pos\]; s: estação | O(\|route\| - pos) - recalcula perfil a partir de pos      | energy_profile\[pos:\], deficient_segments, cv_route, CVVector |
| remove_station(route, pos)     | route, pos: visit do tipo STATION a remover                        | O(\|route\| - pos) - recalcula perfil a partir de pos      | energy_profile\[pos:\], deficient_segments, cv_route, CVVector |
| swap_customers(r1, p1, r2, p2) | Troca customers nas posições p1/p2 nas rotas r1/r2                 | O(max(\|r1\|, \|r2\|)) - recalcula ambas as rotas inteiras | Ambas as rotas, CVVector                                       |
| insert_customer(route, pos, c) | Insere cliente c na posição pos da rota                            | O(\|route\| - pos) - recalcula desde pos                   | energy_profile\[pos:\], time_profile\[pos:\], cv_route         |
| remove_customer(route, pos)    | Remove cliente em pos                                              | O(\|route\| - pos)                                         | Idem                                                           |
| merge_routes(r1, r2)           | Une duas rotas em uma                                              | O(\|r1\| + \|r2\|)                                         | Route inteira e CVVector                                       |
| split_route(route, pos)        | Divide rota em pos, gerando 2 rotas                                | O(\|route\| - pos)                                         | Ambas as novas rotas e CVVector                                |

A regra de recalculação parcial (apenas a partir da posição modificada) é possível porque os invariantes I4 e I5 garantem que o perfil é calculado de forma estritamente sequencial: cada visit depende apenas do anterior. Isso reduz o custo de operações locais (inserção/remoção de estação) de O(|route|) completo para O(|route| - pos).

# **2\. Classificador de Inviabilidade (CI)**

O CI é o motor de diagnóstico do IAS-EVRP. Sua saída - o vetor CVVector = (cv_energy, cv_cascade, cv_cap, cv_tw) e o campo inf_type - alimenta diretamente o SIFO-E (para a relação de dominância ≺_ECD), o DIMO-E (para os limiares γ_E, γ_C, γ_T) e o EOC (que usa deficient_segments). A implementação deve ser O(Σ|rota|) sobre toda a solução - linear no número total de visitas.

## **2.1 Pseudocódigo Completo do CI**

função CI(x: Solution, pop_stats: PopulationStats) → Solution:

\# Passo 1: calcular perfis e coletar violações brutas por rota

total_energy_raw ← 0 # soma dos déficits energéticos

total_cascade_raw ← 0 # contagem ponderada de nós em cascata

total_cap_raw ← 0 # excesso de demanda agregado

total_tw_raw ← 0 # excesso de atraso agregado

para cada rota r em x.routes:

(r, raw) ← compute_route_profile(r) # veja 2.2

total_energy_raw += raw.energy_raw

total_cascade_raw += raw.cascade_raw

total_cap_raw += raw.cap_raw

total_tw_raw += raw.tw_raw

\# Passo 2: normalizar usando máx/mín da população atual

x.cv_components.cv_energy ← normalize(total_energy_raw,

pop_stats.max_energy_raw,

pop_stats.min_energy_raw)

x.cv_components.cv_cascade ← normalize(total_cascade_raw,

pop_stats.max_cascade_raw,

pop_stats.min_cascade_raw)

x.cv_components.cv_cap ← normalize(total_cap_raw,

pop_stats.max_cap_raw,

pop_stats.min_cap_raw)

x.cv_components.cv_tw ← normalize(total_tw_raw,

pop_stats.max_tw_raw,

pop_stats.min_tw_raw)

\# Passo 3: classificar tipo de inviabilidade

x.metadata.inf_type ← classify_type(x.cv_components) # veja 2.3

\# Passo 4: atualizar objetivos na metadata (sempre usa valores originais f)

x.metadata ← compute_objectives(x) # veja 2.4

retorna x

função normalize(raw, max_raw, min_raw) → float:

se max_raw == min_raw:

retorna 1.0 se min_raw > 0 senão 0.0 # consistente com Ou et al.

retorna (raw - min_raw) / (max_raw - min_raw)

## **2.2 Cálculo do Perfil de Rota e Violações Brutas**

A função compute_route_profile é o núcleo computacional do CI. Ela percorre a rota sequencialmente, calculando o estado energético e temporal a cada visita, e coleta todas as violações brutas:

função compute_route_profile(r: Route) → (Route, RawViolations):

\# Estado inicial: depósito de partida

curr_energy ← B # bateria cheia

curr_time ← 0 # tempo zero

total_demand ← 0

energy_raw ← 0 # acumulador: soma de déficits

cascade_raw ← 0 # acumulador: nós em cascata

tw_raw ← 0 # acumulador: excesso de atraso

in_cascade ← False

r.deficient_segments ← \[\]

para j de 1 até len(r.visits) - 1: # exclui depósito de partida

prev_visit ← r.visits\[j-1\]

curr_visit ← r.visits\[j\]

\# ── Energia ──────────────────────────────────────────────────────

dist_ij ← d\[prev_visit.node_id\]\[curr_visit.node_id\]

energy_ij ← e\[prev_visit.node_id\]\[curr_visit.node_id\]

curr_energy ← curr_energy - energy_ij

curr_visit.arrival_energy ← curr_energy

se curr_energy < 0: # déficit energético

deficit ← -curr_energy # magnitude do déficit

energy_raw += deficit

\# Registrar segmento deficiente

seg ← Segment(from_idx=j-1, to_idx=j,

energy_consumed=energy_ij,

energy_deficit=deficit,

min_insert_cost=None) # lazy: EOC calcula depois

r.deficient_segments.append(seg)

\# Lógica de cascata

se in_cascade:

cascade_raw += 1 # nó consecutivo em déficit

senão:

in_cascade ← True

\# primeiro nó deficiente não conta para cascade_raw

senão:

in_cascade ← False # sai da cascata

\# Se é estação: recarrega bateria

se curr_visit.node_type == STATION:

curr_visit.departure_energy ← B

curr_energy ← B

in_cascade ← False # estação interrompe qualquer cascata

senão:

curr_visit.departure_energy ← curr_energy

\# ── Tempo ────────────────────────────────────────────────────────

travel_time_ij ← t\[prev_visit.node_id\]\[curr_visit.node_id\]

curr_time += travel_time_ij

curr_visit.arrival_time ← curr_time

se curr_visit.node_type == CUSTOMER:

wait ← max(0, b\[curr_visit.node_id\] - curr_time)

delay ← max(0, curr_time - e\[curr_visit.node_id\])

curr_visit.waiting_time ← wait

curr_visit.delay_time ← delay

curr_time += wait + s\[curr_visit.node_id\] # espera + serviço

\# Excesso de atraso (restrição soft: delay <= md)

se delay > md:

tw_raw += delay - md

senão se curr_visit.node_type == STATION:

curr_time += t_charge # tempo de recarga (modelo de recarga total)

curr_visit.departure_time ← curr_time

\# ── Capacidade ───────────────────────────────────────────────────

se curr_visit.node_type == CUSTOMER:

total_demand += q\[curr_visit.node_id\]

\# Violação de capacidade: excesso sobre Q

cap_raw ← max(0, total_demand - Q)

\# Violação de janela do depósito: retorno após fechamento

ultimo_dep_time ← r.visits\[-1\].arrival_time

se ultimo_dep_time > e\[depot\]:

tw_raw += ultimo_dep_time - e\[depot\]

raw ← RawViolations(energy_raw, cascade_raw, cap_raw, tw_raw)

retorna (r, raw)

## **2.3 Regras de Classificação de Tipo**

Após a normalização dos CVs, a função classify_type aplica as seguintes regras em ordem de prioridade:

função classify_type(cv: CVVector) → InfeasibilityType:

\# Verifica presença de cada tipo de violação

tem_energia ← cv.cv_energy > ε # ε = tolerância numérica (e.g. 1e-9)

tem_cascata ← cv.cv_cascade > ε

tem_cap ← cv.cv_cap > ε

tem_tw ← cv.cv_tw > ε

n_tipos ← soma(tem_energia, tem_cascata, tem_cap, tem_tw)

se n_tipos == 0:

retorna FEASIBLE

\# Múltiplos tipos simultâneos

se (tem_energia ou tem_cascata) e (tem_cap ou tem_tw):

retorna IM # Inviabilidade Mista

\# Somente violações energéticas

se tem_energia e não tem_cap e não tem_tw:

se tem_cascata:

retorna IEC # Inviabilidade Energética Cascata

senão:

retorna IES # Inviabilidade Energética Simples

\# Somente capacidade (sem energia)

se tem_cap e não tem_energia e não tem_tw:

retorna IC

\# Somente janela de tempo (sem energia)

se tem_tw e não tem_energia e não tem_cap:

retorna IJT

\# Caso restante: IC + IJT sem energia

retorna IM

**Nota sobre a distinção IES vs IEC**

O campo cv*cascade é não-zero quando existe pelo menos um par de segmentos deficientes \_consecutivos* sem uma estação de recarga entre eles. Mais precisamente: cascade*raw conta o número de nós visitados \_após* o primeiro nó deficiente de uma cascata sem haver recarga intermediária. Uma cascata com 3 nós deficientes consecutivos gera cascade_raw = 2 (o segundo e terceiro nós contam; o primeiro é o 'gatilho').

Consequentemente, IES corresponde a: cv_energy > 0 E cv_cascade == 0. IEC corresponde a: cv_energy > 0 E cv_cascade > 0. Esta distinção garante que o DIMO-E possa gerenciar IES e IEC com limiares separados e estratégias de geração distintas.

## **2.4 Cálculo dos Objetivos (Não-mascarados)**

Os objetivos _f₁...f₅_ são calculados diretamente dos perfis armazenados na representação, sem qualquer correção. São os objetivos **mascarados** no caso de soluções energeticamente inviáveis. O EOC (fora do CI) é responsável por calcular _f̂_ a partir deles:

função compute_objectives(x: Solution) → SolutionMetadata:

f1 ← len(x.routes) # número de veículos

f2 ← 0

f3 ← 0

f4 ← 0

f5 ← 0

para cada rota r em x.routes:

dist_rota ← 0

para j de 0 até len(r.visits) - 2:

dist_rota += d\[r.visits\[j\].node_id\]\[r.visits\[j+1\].node_id\]

f2 += dist_rota

tempo_rota ← r.visits\[-1\].arrival_time - r.visits\[0\].departure_time

f3 ← max(f3, tempo_rota) # makespan = máximo

f4 += soma(v.waiting_time para v em r.visits se v.node_type == CUSTOMER)

f5 += soma(v.delay_time para v em r.visits se v.node_type == CUSTOMER)

retorna SolutionMetadata(n_vehicles=f1, total_distance=f2,

makespan=f3, total_waiting=f4, total_delay=f5)

## **2.5 Atualização das Estatísticas da População (PopulationStats)**

A normalização dos CVs depende de estatísticas globais da população atual (máximo e mínimo de cada violação bruta). Essas estatísticas precisam ser **re-calculadas após cada modificação da população**. Para evitar overhead excessivo, o algoritmo mantém um objeto PopulationStats que é atualizado de forma eficiente:

\# Atualização eficiente de PopulationStats

\# Chamada após: geração de descendentes, SIFO-E, DIMO-E

função update_pop_stats(pop: List\[Solution\]) → PopulationStats:

\# O(N_P): uma passagem linear sobre a população

stats ← PopulationStats()

para s em pop:

stats.max_energy_raw ← max(stats.max_energy_raw, s.\_raw.energy_raw)

stats.min_energy_raw ← min(stats.min_energy_raw, s.\_raw.energy_raw)

stats.max_cascade_raw ← max(stats.max_cascade_raw, s.\_raw.cascade_raw)

stats.min_cascade_raw ← min(stats.min_cascade_raw, s.\_raw.cascade_raw)

stats.max_cap_raw ← max(stats.max_cap_raw, s.\_raw.cap_raw)

stats.min_cap_raw ← min(stats.min_cap_raw, s.\_raw.cap_raw)

stats.max_tw_raw ← max(stats.max_tw_raw, s.\_raw.tw_raw)

stats.min_tw_raw ← min(stats.min_tw_raw, s.\_raw.tw_raw)

retorna stats

\# ATENÇÃO: os campos cv\_\* nas Solution são apenas válidos em relação

\# ao PopulationStats do momento em que o CI foi chamado.

\# Após update_pop_stats, é necessário renormalizar toda a população.

\# Para evitar re-execução completa do CI, armazena-se \_raw separadamente

\# e a renormalização é feita em O(N_P) sem recalcular os perfis.

# **3\. Inicialização Adaptada ao EVRP**

A inicialização é responsável por criar a população P₀ com uma distribuição de tipos de inviabilidade coerente com os limiares γ_E, γ_C e γ_T do DIMO-E. Como η é calculado pela proporção natural de inviáveis na população inicial (Eq. 23 de Cai et al.), a inicialização precisa gerar as camadas com as proporções corretas **antes** de calcular η - o que significa que η reflete a dificuldade natural da instância, não um alvo pré-definido. A inicialização em três camadas assegura que essa proporção caia na faixa \[0.2, 0.4\] típica das instâncias reais.

## **3.1 Parâmetros da Inicialização**

| **Parâmetro** | **Descrição**                                   | **Valor Padrão** | **Impacto**                                                              |
| ------------- | ----------------------------------------------- | ---------------- | ------------------------------------------------------------------------ |
| α_V           | Fração-alvo de soluções viáveis                 | 0.40             | Aumentar → mais viáveis → η menor → menos exploração infeasível          |
| α_E           | Fração-alvo de soluções IES                     | 0.35             | Aumentar → mais IES → melhor cobertura de regiões próximas ao limite     |
| α_R           | Fração-alvo de soluções aleatórias (IEC/IC/IJT) | 0.25             | Aumentar → mais diversidade bruta → maior risco de IEC severas           |
| β_s           | Limiar de segurança energética (em fração de B) | 0.20             | Camada V: não começar trecho se energia < β_s × B                        |
| θ_insert      | Limiar de inserção automática no crossover      | 0.15 × d_avg     | Trechos com custo de inserção abaixo deste são reparados automaticamente |
| N_P           | Tamanho da população                            | 100 (herdado)    | Determina tamanho absoluto de cada camada                                |

## **3.2 Pseudocódigo Completo da Inicialização**

função Inicialização(N_P, α_V, α_E, α_R, β_s) → List\[Solution\]:

n_V ← round(α_V × N_P) # target de viáveis

n_E ← round(α_E × N_P) # target de IES

n_R ← N_P - n_V - n_E # restante (IEC/IC/IJT/aleatório)

P₀ ← \[\]

\# ─── CAMADA V: Soluções Viáveis ───────────────────────────────────

tentativas_V ← 0

enquanto len(P₀_V) < n_V e tentativas_V < 5 × n_V:

sol ← gerar_solucao_com_seguranca(β_s) # veja 3.3

sol ← CI(sol, pop_stats_vazia) # classifica

se sol.metadata.inf_type == FEASIBLE:

P₀.append(sol)

tentativas_V += 1

\# Se não atingiu n_V (instância difícil), complementa com o que tiver

\# ─── CAMADA E: Soluções IES ───────────────────────────────────────

tentativas_E ← 0

n_E_geradas ← 0

enquanto n_E_geradas < n_E e tentativas_E < 5 × n_E:

sol ← gerar_solucao_sem_seguranca() # veja 3.4

sol ← CI(sol, pop_stats_vazia)

se sol.metadata.inf_type == IES:

P₀.append(sol)

n_E_geradas += 1

tentativas_E += 1

\# Se não atingiu n_E (muito difícil gerar IES), usa ORE sobre viáveis

se n_E_geradas < n_E:

deficit ← n_E - n_E_geradas

viáveis_disponíveis ← \[s para s em P₀ se s.metadata.inf_type == FEASIBLE\]

para i em range(min(deficit, len(viáveis_disponíveis))):

ies ← ORE(viáveis_disponíveis\[i\]) # remove estação folga

ies ← CI(ies, pop_stats_vazia)

se ies.metadata.inf_type == IES:

P₀.append(ies)

\# ─── CAMADA R: Soluções Aleatórias ───────────────────────────────

para \_em range(n_R):

sol ← gerar_solucao_aleatoria() # veja 3.5

sol ← CI(sol, pop_stats_vazia) # classifica sem normalizar

P₀.append(sol)

\# ─── Pós-inicialização: normalizar e verificar ────────────────────

pop_stats ← update_pop_stats(P₀)

para sol em P₀: # renormaliza os CVs

sol.cv_components ← renormalize(sol.\_raw, pop_stats)

verificar_inicialização(P₀, n_V, n_E, n_R) # veja Seção 3.6

retorna P₀

## **3.3 Geração de Soluções Viáveis (Camada V)**

O algoritmo de geração viável usa inserção sequencial de clientes com verificação energética e inserção proativa de estações quando o nível de bateria cai abaixo do limiar _β_s × B_:

função gerar_solucao_com_seguranca(β_s) → Solution:

clientes_nao_atribuidos ← shuffle(C) # ordem aleatória

rotas ← \[\]

rota_atual ← nova_rota_do_depósito()

curr_energy ← B

curr_time ← 0

curr_demand ← 0

enquanto clientes_nao_atribuidos não vazio:

c ← clientes_nao_atribuidos\[0\]

\# Verifica se c pode ser inserido sem violar capacidade

se curr_demand + q\[c\] > Q:

rotas.append(fechar_rota(rota_atual)) # fecha e abre nova

rota_atual ← nova_rota_do_depósito()

curr_energy ← B

curr_time ← 0

curr_demand ← 0

continua

\# Energia necessária para ir ao cliente

energia_para_c ← e\[ultimo_no(rota_atual)\]\[c\]

energia_para_depot_depois ← e\[c\]\[depot\]

\# Verificação de segurança: consegue ir a c E retornar ao depósito?

se curr_energy - energia_para_c - energia_para_depot_depois < β_s × B:

\# Inserir estação antes de ir a c

s_best ← melhor_estacao_para_inserir(ultimo_no(rota_atual), c, curr_energy)

se s_best é None: # nenhuma estação alcançável

\# Fecha rota e começa nova (c será atendido depois)

rotas.append(fechar_rota(rota_atual))

rota_atual ← nova_rota_do_depósito()

curr_energy ← B

curr_time ← 0

curr_demand ← 0

continua

senão:

inserir_station_em_rota(rota_atual, s_best)

curr_energy ← B # recarga completa

curr_time += t\[ultimo_no_anterior(rota_atual)\]\[s_best\] + t_charge

\# Inserir cliente c

inserir_customer_em_rota(rota_atual, c)

curr_energy -= energia_para_c

curr_time += t\[ultimo_no_anterior(rota_atual)\]\[c\]

curr_demand += q\[c\]

clientes_nao_atribuidos.remove(c)

rotas.append(fechar_rota(rota_atual))

retorna Solution(routes=rotas)

função melhor_estacao_para_inserir(from_node, to_node, curr_energy):

\# Encontra estação alcançável de from_node com curr_energy

\# que minimize o desvio de rota (δ_dist)

candidatas ← \[s para s em S se e\[from_node\]\[s\] <= curr_energy\]

se não candidatas: retorna None

retorna argmin\_{s em candidatas} (d\[from_node\]\[s\] + d\[s\]\[to_node\] - d\[from_node\]\[to_node\])

## **3.4 Geração de Soluções IES (Camada E)**

A camada IES usa o mesmo algoritmo base mas com β*s = 0 (sem margem de segurança) e com verificação energética \_para o trecho atual apenas*, sem considerar o retorno ao depósito. Isso permite que um único trecho ultrapasse a autonomia, gerando IES controladas:

função gerar_solucao_sem_seguranca() → Solution:

\# Igual a gerar_solucao_com_seguranca, mas:

\# 1. β_s = 0 → sem limiar de segurança

\# 2. Verifica apenas se consegue CHEGAR ao próximo cliente (não o retorno)

\# 3. Não insere estação proativamente

\# 4. Resultado: pode haver 1 trecho onde bateria < 0 (IES)

\# Parametrização adicional: probabilidade p_skip_station ∈ \[0.3, 0.6\]

\# Com probabilidade p_skip_station, mesmo quando estação seria útil,

\# ela não é inserida → gera IES de forma mais controlada

clientes_nao_atribuidos ← shuffle(C)

rotas ← \[\]

rota_atual ← nova_rota_do_depósito()

curr_energy ← B

enquanto clientes_nao_atribuidos não vazio:

c ← clientes_nao_atribuidos\[0\]

energia_para_c ← e\[ultimo_no(rota_atual)\]\[c\]

\# Capacidade ainda é verificada (só IES energética, não IC)

se curr_demand + q\[c\] > Q:

rotas.append(fechar_rota(rota_atual))

rota_atual ← nova_rota_do_depósito()

curr_energy ← B

curr_demand ← 0

continua

\# Insere c mesmo que energia fique negativa em 1 trecho

se curr_energy - energia_para_c < 0:

se rand() < p_skip_station: # pula inserção de estação

inserir_customer_em_rota(rota_atual, c) # gera IES aqui

curr_energy -= energia_para_c # fica negativo

senão:

\# Com prob. (1-p_skip): insere estação e continua viável

s_best ← melhor_estacao_para_inserir(ultimo_no(rota_atual), c, curr_energy)

se s_best:

inserir_station_em_rota(rota_atual, s_best)

curr_energy ← B

inserir_customer_em_rota(rota_atual, c)

curr_energy -= energia_para_c

senão:

inserir_customer_em_rota(rota_atual, c)

curr_energy -= energia_para_c

\# IMPORTANTE: após o primeiro trecho negativo, clamp energy=0

\# para não acumular cascata além do primeiro trecho

se curr_energy < 0: curr_energy ← 0

\# Isso garante que apenas 1 trecho seja deficiente → IES, não IEC

curr_demand += q\[c\]

clientes_nao_atribuidos.remove(c)

rotas.append(fechar_rota(rota_atual))

retorna Solution(routes=rotas)

## **3.5 Geração de Soluções Aleatórias (Camada R)**

função gerar_solucao_aleatoria() → Solution:

\# Sem qualquer verificação de restrições

\# Usa o operador de inicialização ignorando restrições de

\# janela de tempo (similar ao CMOEA-IAS de Cai et al.)

\# Amostra um limiar de atraso r ~ Uniform(0, md × 2)

r ← Uniform(0, md × 2)

clientes_nao_atribuidos ← shuffle(C)

rota_atual ← nova_rota_do_depósito()

rotas ← \[\]

atraso_medio_rota ← 0

enquanto clientes_nao_atribuidos não vazio:

c ← clientes_nao_atribuidos\[0\]

\# Inserção tentativa e verificação de atraso médio

atraso_c ← calcular_atraso_se_inserir(rota_atual, c)

se (atraso_medio_rota + atraso_c) / (|rota_atual| + 1) > r:

rotas.append(fechar_rota(rota_atual))

rota_atual ← nova_rota_do_depósito()

atraso_medio_rota ← 0

continua

inserir_customer_em_rota(rota_atual, c)

atraso_medio_rota ← (atraso_medio_rota + atraso_c) / |rota_atual|

clientes_nao_atribuidos.remove(c)

\# SEM inserção de estações → provavelmente IEC ou IC

rotas.append(fechar_rota(rota_atual))

retorna Solution(routes=rotas)

## **3.6 Verificação Pós-inicialização**

Após gerar P₀ completo, a função verificar_inicialização realiza um conjunto de verificações para garantir que a população inicial satisfaz as condições esperadas pelo DIMO-E. Estas verificações são executadas uma única vez e servem também para diagnóstico e ajuste de parâmetros:

função verificar_inicialização(P₀, n_V_target, n_E_target, n_R) → VerifResult:

\# Contagem real por tipo

contagem ← Counter(sol.metadata.inf_type para sol em P₀)

n_V_real ← contagem\[FEASIBLE\]

n_IES_real ← contagem\[IES\]

n_IEC_real ← contagem\[IEC\]

n_IC_real ← contagem\[IC\]

n_IJT_real ← contagem\[IJT\]

n_IM_real ← contagem\[IM\]

η_real ← (n_IES_real + n_IEC_real + n_IC_real + n_IJT_real + n_IM_real) / N_P

\# Verificação 1: proporção de inviáveis dentro da faixa esperada

ALERTA se η_real < 0.15:

'Instância fácil: poucos inviáveis naturais. Considere reduzir α_V

ou aumentar p_skip_station para gerar mais IES artificialmente.'

ALERTA se η_real > 0.70:

'Instância muito difícil: muitos inviáveis. η = {η_real:.2f}.

Considere aumentar α_V ou reduzir n_R.'

\# Verificação 2: IES constitui a maioria dos inviáveis

fração_IES ← n_IES_real / max(1, N_P - n_V_real)

ALERTA se fração_IES < 0.40:

'Poucos IES entre os inviáveis ({fração_IES:.0%}).

O DIMO-E pode ter dificuldade em manter γ_E. Revise p_skip_station.'

\# Verificação 3: cobertura da frente de Pareto inicial (diversidade objetivos)

f2_values ← \[sol.metadata.total_distance para sol em P₀

se sol.metadata.inf_type == FEASIBLE\]

se len(f2_values) > 1:

coef_var_f2 ← std(f2_values) / mean(f2_values)

ALERTA se coef_var_f2 < 0.05:

'Diversidade baixa em f2 entre soluções viáveis (CV={coef_var_f2:.2f}).

Considere aumentar α_R para mais diversidade.'

\# Verificação 4: invariantes de representação

para sol em P₀:

para rota em sol.routes:

assert(rota.visits\[0\].node_type == DEPOT)

assert(rota.visits\[-1\].node_type == DEPOT)

clientes_rota ← \[v.node_id para v em rota.visits se v.node_type==CUSTOMER\]

assert(sem duplicatas em clientes_rota)

todos_clientes ← flatten(clientes de todas as rotas em P₀)

assert(set(todos_clientes) == C) # todo cliente atendido exatamente uma vez

\# Relatório

retorna VerifResult(

η=η_real, n_V=n_V_real, n_IES=n_IES_real,

n_IEC=n_IEC_real, n_IC=n_IC_real, n_IJT=n_IJT_real,

fração_IES_entre_inviáveis=fração_IES,

coef_var_f2=coef_var_f2

)

**Uso do Resultado de Verificação pelo DIMO-E**

O resultado de verificar_inicialização alimenta diretamente o cálculo de η do DIMO-E (Eq. 23 do documento principal). Especificamente:

η_E = n_IES_real / N_P → threshold de soluções IES (γ_E = (rand(-0.01,0.01) + η_E) × N_P)

η_C = n_IC_real / N_P → threshold de IC (γ_C)

η_T = n_IJT_real / N_P → threshold de IJT (γ_T)

# **4\. Operador de Crossover com Consciência Energética**

O crossover do IAS-EVRP estende o operador de rotas de Wang et al. (utilizado no CMOEA-IAS) com uma fase adicional de verificação e correção energética pós-crossover. O operador base troca subconjuntos de rotas entre dois pais; a extensão decide, para cada rota do filho, quais trechos deficientes devem ser automaticamente corrigidos (custo baixo) e quais devem ser preservados como IES (custo alto, valor exploratório).

## **4.1 Visão Geral em Três Fases**

| **Fase**                        | **O que faz**                                                                                                                                                                                                                     | **Resultado**                                                               |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Fase 1 - Crossover Base         | Seleciona rotas de p1 e p2, remove conflitos de clientes, gera dois filhos com rotas misturadas. Herdado de Wang et al. (2015/2017) sem modificações.                                                                             | Dois filhos com invariantes I1 e I2 satisfeitos mas sem garantia energética |
| Fase 2 - Diagnóstico Energético | Executa o Passo 1 do CI (compute_route_profile) sobre cada rota dos filhos. Identifica deficient_segments e calcula δ_dist(i,j) via EOC para cada trecho.                                                                         | Lista de trechos deficientes com custo de inserção calculado                |
| Fase 3 - Decisão de Correção    | Para cada trecho deficiente: se δ_dist < θ_insert → insere estação automaticamente (filho fica viável naquele trecho). Se δ_dist ≥ θ_insert → preserva déficit (filho classificado como IES). Garante nunca gerar IEC por design. | Filhos com tipo definido (FEASIBLE ou IES), prontos para CI completo        |

## **4.2 Pseudocódigo Completo**

função CrossoverEVRP(p1: Solution, p2: Solution, θ_insert) → (Solution, Solution):

\# ═══ FASE 1: Crossover Base (Wang et al.) ═══════════════════════

\# Seleciona uma rota aleatória de cada pai

r1_sel ← escolher_rota_aleatória(p1) # rota selecionada do pai 1

r2_sel ← escolher_rota_aleatória(p2) # rota selecionada do pai 2

\# Clientes em cada rota selecionada

C1 ← {v.node_id para v em r1_sel.visits se v.node_type==CUSTOMER}

C2 ← {v.node_id para v em r2_sel.visits se v.node_type==CUSTOMER}

\# Gerar filho 1: herda r1_sel de p1, remove C1 de p2, insere r1_sel

filho1 ← copiar_solução(p2)

filho1 ← remover_clientes_de_solução(filho1, C1) # remove C1 de p2

filho1.routes.append(copiar_rota(r1_sel)) # insere rota de p1

filho1 ← reinserir*clientes*órfãos(filho1) # veja 4.3

\# Gerar filho 2: herda r2_sel de p2, remove C2 de p1, insere r2_sel

filho2 ← copiar_solução(p1)

filho2 ← remover_clientes_de_solução(filho2, C2)

filho2.routes.append(copiar_rota(r2_sel))

filho2 ← reinserir*clientes*órfãos(filho2)

\# ═══ FASE 2: Diagnóstico Energético ════════════════════════════

para filho em \[filho1, filho2\]:

para rota em filho.routes:

(rota, raw) ← compute_route_profile(rota) # CI parcial

\# Calcula δ_dist para cada segmento deficiente (EOC parcial)

para seg em rota.deficient_segments:

seg.min_insert_cost ← calcular_delta_dist(seg, S)

\# ═══ FASE 3: Decisão de Correção ════════════════════════════════

para filho em \[filho1, filho2\]:

para rota em filho.routes:

segs_para_corrigir ← \[\]

segs_para_preservar ← \[\]

para seg em rota.deficient_segments:

se seg.min_insert_cost < θ_insert:

segs_para_corrigir.append(seg)

senão:

segs_para_preservar.append(seg)

\# Correção: inserir estação nos trechos baratos

\# ATENÇÃO: inserções mudam índices - processar de trás para frente

para seg em reversed(sorted(segs_para_corrigir, key=lambda s: s.from_idx)):

s_best ← estacao_de_menor_desvio(seg.from_idx, seg.to_idx, rota)

inserir_station_em_rota(rota, posicao=seg.from_idx+1, estacao=s_best)

\# inserir_station_em_rota recalcula perfil a partir de from_idx+1

\# Após correções, recalcular perfil completo da rota

se segs_para_corrigir:

(rota, \_) ← compute_route_profile(rota)

\# ═══ Garantia Anti-IEC ══════════════════════════════════════════

\# A Fase 3 assegura que segmentos preservados são individualmente deficientes

\# mas não consecutivos (pois cada um foi avaliado e ou corrigido ou marcado).

\# Um segmento preservado (IES candidato) nunca é adjacente a outro preservado

\# se seguirmos a lógica abaixo:

para filho em \[filho1, filho2\]:

para rota em filho.routes:

\# Verificação anti-IEC: se dois preservados são adjacentes, corrige o menor

segs_deficientes ← rota.deficient_segments

para i em range(len(segs_deficientes) - 1):

s1, s2 ← segs_deficientes\[i\], segs_deficientes\[i+1\]

se s1.to_idx == s2.from_idx: # adjacentes → IEC em formação

\# Corrige o de menor custo (mesmo que > θ_insert)

se s1.min_insert_cost <= s2.min_insert_cost:

corrigir_segmento(rota, s1)

senão:

corrigir_segmento(rota, s2)

\# Re-executar compute_route_profile após correções anti-IEC

(rota, \_) ← compute_route_profile(rota)

\# CI completo (com normalização usando pop_stats atual)

para filho em \[filho1, filho2\]:

filho ← CI(filho, pop_stats_atual)

retorna (filho1, filho2)

## **4.3 Reinserção de Clientes Órfãos**

Após remover clientes conflitantes de uma solução, alguns clientes ficam 'órfãos' - sem rota atribuída. A função reinserir*clientes*órfãos os reinsere de forma gulosa, com consciência energética:

função reinserir*clientes*órfãos(sol: Solution) → Solution:

órfãos ← \[c para c em C se c não está em nenhuma rota de sol\]

órfãos ← sorted(órfãos, key=lambda c: urgencia_temporal(c)) # by time window

para c em órfãos:

melhor_pos ← None

melhor_custo ← ∞

para rota em sol.routes:

\# Tenta inserir c em cada posição da rota (entre visitas consecutivas)

para pos em range(1, len(rota.visits)):

se violaria_capacidade(rota, c): continue

custo_insercao ← calcular_custo_insercao(rota, pos, c)

energia_após_c ← energia_em_pos(rota, pos) - e\[rota.visits\[pos-1\].node_id\]\[c\]

se energia_após_c >= 0: # inserção energeticamente viável

se custo_insercao < melhor_custo:

melhor_custo ← custo_insercao

melhor_pos ← (rota, pos)

senão:

\# Inserção energeticamente inviável: aceita se custo baixo

\# e probabilisticamente (aceita IES com prob. p_ies_insert)

deficit ← -energia_após_c

delta_dist ← calcular_delta_dist_para_c(rota, pos, c, S)

custo_corrigido ← custo_insercao + delta_dist

se delta_dist < θ_insert e custo_corrigido < melhor_custo:

melhor_custo ← custo_corrigido

melhor_pos ← (rota, pos)

se melhor_pos é None:

\# Nenhuma posição válida: abre nova rota para c

nova_rota ← nova_rota_do_depósito()

inserir_customer_em_rota(nova_rota, c)

sol.routes.append(nova_rota)

senão:

(rota_alvo, pos_alvo) ← melhor_pos

inserir_customer_em_rota(rota_alvo, pos_alvo, c)

\# Se gerou déficit energético, inserir estação automaticamente

se energia_em_pos(rota_alvo, pos_alvo) < 0:

s_best ← melhor_estacao_para_inserir(

rota_alvo.visits\[pos_alvo-1\].node_id, c, ...)

inserir_station_em_rota(rota_alvo, pos_alvo, s_best)

retorna sol

## **4.4 Exemplo Passo a Passo do Crossover**

Considere dois pais com as seguintes rotas (simplificado, apenas IDs de nós):

Pai 1:

Rota A: \[D → 1 → 3 → s1 → 5 → 7 → D\] (viável, B=100, usa estação s1)

Rota B: \[D → 2 → 4 → 6 → 8 → D\] (viável)

Pai 2:

Rota C: \[D → 1 → 2 → 5 → D\] (viável)

Rota D: \[D → 3 → 4 → 6 → 7 → 8 → D\] (viável)

─── FASE 1: Crossover Base ───────────────────────────────────────

r1_sel ← Rota A de Pai 1 → C1 = {1, 3, 5, 7}

r2_sel ← Rota D de Pai 2 → C2 = {3, 4, 6, 7, 8}

Filho 1 = Pai 2 − C1 + r1_sel:

Remove {1,3,5,7} de Pai 2:

Rota C restante: \[D → 2 → D\] (1 e 5 removidos de C)

Rota D restante: \[D → 4 → 6 → 8 → D\] (3 e 7 removidos de D)

Adiciona Rota A: \[D → 1 → 3 → s1 → 5 → 7 → D\]

Filho 1: { \[D→2→D\], \[D→4→6→8→D\], \[D→1→3→s1→5→7→D\] }

Filho 2 = Pai 1 − C2 + r2_sel:

Remove {3,4,6,7,8} de Pai 1:

Rota A restante: \[D → 1 → s1 → 5 → D\] (3 e 7 removidos; s1 mantida)

Rota B restante: \[D → 2 → D\] (4,6,8 removidos)

Adiciona Rota D: \[D → 3 → 4 → 6 → 7 → 8 → D\]

Filho 2: { \[D→1→s1→5→D\], \[D→2→D\], \[D→3→4→6→7→8→D\] }

─── FASE 2: Diagnóstico Energético (Filho 2, Rota D herdada) ────

Rota D: \[D → 3 → 4 → 6 → 7 → 8 → D\]

Perfil: \[100, 72, 41, 8, -28, -60, -90\]

↑depósito ↑déficit no trecho 7→8: deficit=28

↑continua em cascata: trecho 8→D

deficient_segments = \[Segment(from=3, to=4, deficit=28, custo=?)\]

Cálculo de δ_dist para trecho 7→8:

s1 disponível: d(7,s1)+d(s1,8) - d(7,8) = 12+9-15 = 6 ← melhor

s2 disponível: d(7,s2)+d(s2,8) - d(7,8) = 25+18-15 = 28

s3 disponível: muito longe

δ_dist(7→8) = 6

─── FASE 3: Decisão (θ_insert = 10) ─────────────────────────────

δ_dist(7→8) = 6 < θ_insert = 10 → CORRIGIR automaticamente

Insere s1 entre 7 e 8:

Rota D corrigida: \[D → 3 → 4 → 6 → 7 → s1 → 8 → D\]

Novo perfil: \[100, 72, 41, 8, 100, 71, 45\] ← viável

Filho 2 resultante: FEASIBLE (todos os trechos viáveis após correção)

→ CI classifica como FEASIBLE, corrected_obj = None (não necessário)

**Garantia de Coerência com o DIMO-E**

O crossover é projetado para nunca produzir IEC por design (garantia anti-IEC na Fase 3). Isso garante que o pool de IEC gerenciado pelo DIMO-E seja sempre de origem controlada (Camada R da inicialização ou geração explícita pelo DIMO-E). As IES produzidas pelo crossover têm custo de inserção acima de θ_insert - precisamente as mais difíceis de reparar e, portanto, as mais informativas sobre regiões de alta curvatura da frente de Pareto.

## **4.5 Cálculo de θ_insert e sua Relação com o EOC**

O limiar θ_insert determina o ponto de corte entre 'inserção barata que não agrega informação' e 'trecho deficiente que vale preservar como IES'. Ele deve ser calibrado em relação à distribuição de δ_dist na instância:

\# Calibração de θ_insert (executada uma vez antes da inicialização)

função calibrar_theta_insert(instância) → float:

\# Amostrar δ_dist para todos os pares de nós vizinhos no grafo

deltas ← \[\]

para cada aresta (i, j) em E onde i ∈ C, j ∈ C:

delta*ij ← min*{s em S} (d(i,s) + d(s,j) - d(i,j))

deltas.append(delta_ij)

\# θ_insert = percentil 25 da distribuição de δ_dist

\# Significa: 25% dos trechos teriam inserção 'barata'

\# Ajustável: percentil mais baixo → mais correções automáticas → menos IES

\# percentil mais alto → menos correções → mais IES (mais risco)

θ_insert ← percentile(deltas, 25)

retorna θ_insert

\# Relação com o EOC:

\# O EOC usa o mesmo δ_dist para corrigir objetivos no SIFO-E.

\# Trechos com δ_dist < θ_insert são automaticamente corrigidos no crossover

\# → nunca chegarão ao EOC como segmentos deficientes.

\# Trechos com δ_dist ≥ θ_insert chegam ao EOC e contribuem para f̂.

\# Isso cria uma divisão de trabalho clara:

\# crossover: corrige o barato | EOC: estima o custoso

# **5\. Síntese de Coerência entre os Componentes**

Esta seção sintetiza como os quatro componentes detalhados interagem de forma coerente com o restante do framework IAS-EVRP, garantindo que nenhuma decisão de implementação conflite com os mecanismos propostos no documento principal.

## **5.1 Mapa de Dependências de Dados**

Inicialização

│

├── gera Solution com visits\[\] preenchidos

└──→ CI(sol) ──────────────────────────────────────────────────────┐

│ │

├── compute_route_profile() → energy_profile, time_profile│

├── identifica deficient_segments\[\] │

├── calcula \_raw = (energy_raw, cascade_raw, cap_raw, tw_raw)│

├── normalize() → cv_components = (cv_e, cv_cas, cv_c, cv_t)│

├── classify_type() → inf_type │

└── compute_objectives() → f1...f5 em metadata │

│

update_pop_stats(P) ────────────────────→ PopulationStats ←─────────────┘

│ │

└── max/min por tipo de raw ─────────────→ renormalize() nos CVs

EOC(x) ← consume x.deficient_segments\[\]

│

├── calcula δ_dist(i,j) = min_s {d(i,s)+d(s,j)-d(i,j)} para cada seg

├── calcula α(x) = fator de confiança (1 para IES, <1 para IEC)

└── produz x.metadata.corrected_obj = f̂ = (f̂1,...,f̂5)

SIFO-E ← consume x.cv_components e x.metadata.corrected_obj

│

├── relação ≺_ECD usa f̂ para IES/IEC, f para viáveis/IC/IJT

├── densidade usa shifted objectives com parâmetro q(g,G,τ_tipo)

└── produz P atualizado (tamanho N_P)

DIMO-E ← consume inf_type de cada sol em P

│

├── conta Inf_IES, Inf_IEC, Inf_IC, Inf_IJT

├── compara com γ_E, γ_C, γ_T (derivados de η da inicialização)

├── se IES < γ_E → chama ORE(viável) → gera IES → CI(nova_ies)

├── se IES > γ_E → chama ORPG(elite_IES) → gera viável → CI(nova_vias)

└── produz P com proporções reguladas

CrossoverEVRP(p1, p2) ← consume visits\[\], energy_profile

│

├── Fase 1: crossover base sobre routes\[\]

├── Fase 2: compute_route_profile() parcial + EOC parcial (só δ_dist)

├── Fase 3: inserir estações baratas ou preservar IES

└── CI(filho) → retorna filho classificado

## **5.2 Tabela de Coerência de Invariantes**

| **Componente**           | **Produz/Mantém**                                                | **Consome**                              | **Invariante Garantido**                                                           |
| ------------------------ | ---------------------------------------------------------------- | ---------------------------------------- | ---------------------------------------------------------------------------------- |
| Representação (Solution) | visits\[\], energy_profile, deficient_segments, cv_components    | -                                        | I1-I6: cobertura, limites, consistência de perfis                                  |
| CI                       | cv_components, inf_type, deficient_segments atualizados, f1...f5 | visits\[\], pop_stats                    | cv_components são sempre derivados de visits\[\] via CI após qualquer modificação  |
| PopulationStats          | max/min de cada violação bruta                                   | sol.\_raw de toda a pop                  | Normalização dos CVs é sempre relativa à população atual, nunca absoluta           |
| EOC                      | corrected_obj (f̂)                                                | deficient_segments, pop_stats            | f̂_m(x) ≥ f_m(x) para todo m afetado por energia - never piora objetivos mascarados |
| Inicialização            | P₀ com distribuição de tipos                                     | parâmetros α_V, α_E, α_R, β_s            | η = Inf_num(P₀)/N_P ∈ \[0.15, 0.70\] - verificado por verificar_inicialização()    |
| CrossoverEVRP            | filhos com inf_type ∈ {FEASIBLE, IES}                            | visits\[\], deficient_segments, θ_insert | Nunca produz IEC - Fase 3 garante que trechos deficientes sejam isolados           |
| ORE                      | IES derivadas de viáveis                                         | energy_profile, estações com folga       | IES geradas têm exatamente 1 segmento deficiente (isolado) → sempre IES, nunca IEC |
| ORPG                     | Viáveis derivadas de IES                                         | deficient_segments, δ_dist               | Viáveis retornadas satisfazem I4 (energy_profile ≥ 0) após inserções               |

**Ponto de Atenção Central na Implementação**

O maior risco de incoerência está na **sincronização entre visit\[\] e os campos derivados** (energy_profile, cv_components, deficient_segments, corrected_obj). Recomenda-se implementar um campo sol.\_dirty_flag = True que é ativado por toda operação primitiva de modificação (insert_station, remove_station, swap_customers, etc.). O CI deve verificar este flag antes de retornar CVs ou deficient_segments - se dirty=True, recalcula antes de retornar. O EOC deve verificar se corrected_obj é None e, se for, calculá-lo sob demanda (lazy evaluation).

Essa estratégia de dirty flag + lazy evaluation garante que: (1) nenhum componente consome dados desatualizados, (2) o CI não é chamado desnecessariamente quando uma solução não foi modificada, e (3) o EOC só calcula f̂ para as soluções que de fato precisam dele (IES e IEC selecionadas pelo SIFO-E).

## **5.3 Ordem de Chamadas no Loop Principal**

\# Loop principal do IAS-EVRP (expandido para mostrar chamadas de componentes)

P₀ ← Inicialização(N_P, α_V, α_E, α_R, β_s)

→ para cada sol: CI(sol, pop_stats_vazia)

pop_stats ← update_pop_stats(P₀)

→ renormaliza cv_components de todo P₀

verif ← verificar_inicialização(P₀, ...)

γ_E ← (rand(-0.01,0.01) + verif.η_E) × N_P

γ_C ← (rand(-0.01,0.01) + verif.η_C) × N_P

γ_T ← (rand(-0.01,0.01) + verif.η_T) × N_P

A_E ← \[\] # arquivo elite IES (vazio inicialmente)

A ← \[\] # arquivo externo

P ← P₀

para g de 1 até G_max:

\# 1. Gerar descendentes

O ← \[\]

para i em range(N_P // 2):

p1, p2 ← TournamentSelection(P, ≺_ECD)

f1, f2 ← CrossoverEVRP(p1, p2, θ_insert)

\# CrossoverEVRP já chama CI internamente

O.extend(\[f1, f2\])

\# 2. Atualizar pop_stats (população combinada)

pop_combinada ← P + O

pop_stats ← update_pop_stats(pop_combinada)

para sol em pop_combinada:

sol.cv_components ← renormalize(sol.\_raw, pop_stats)

\# 3. EOC: calcula f̂ para IES/IEC na população combinada

para sol em pop_combinada:

se sol.metadata.inf_type em {IES, IEC}:

EOC(sol) # preenche sol.metadata.corrected_obj

\# 4. SIFO-E: seleção ambiental com ≺_ECD e objetivos corrigidos

P ← SIFO-E(pop_combinada, N_P, q=sigmoid(g, G_max, τ_tipo))

\# 5. DIMO-E: gestão de proporções de inviáveis

P ← DIMO-E(P, P₀, γ_E, γ_C, γ_T)

\# DIMO-E chama CI nas soluções que gera (ORE ou ORPG parcial)

\# 6. Atualizar arquivo elite IES

A_E ← AtualizaEliteIES(P, A_E, N_E) # seleciona melhores IES por f̂

\# 7. Atualizar arquivo externo (só viáveis)

A ← AtualizaArquivo(A, P, ε-dom)

\# 8. ALSC: busca local encadeada nos arquivos

A ← ALSC(A) # busca local multi-objetivo (herdada de MMA-ALSC)

A ← RE(A) + SE(A) + FRC(A) # busca local EVRP-específica

\# 9. ORPG: reparo parcial das elite IES

para ies em A_E\[:N_E_orpg\]: # aplica ORPG nas N_E_orpg melhores

viavel ← ORPG(ies)

se viavel não é None:

A ← AtualizaArquivo(A, \[viavel\], ε-dom)

retorna A

**Referências Relevantes**

\[1\] Cai, Y. et al. (2026). CMOEA-IAS. Applied Soft Computing, 190, 114597.

\[2\] Ou, J. et al. (2024). CEOA. Expert Systems With Applications, 255, 124712.

\[3\] Wang, J. et al. (2015/2017). Multiobjective VRP with simultaneous delivery and pickup. IEEE Trans. Cybern., 46(3), 582-594.

\[4\] Schneider, M., Stenger, A., & Goeke, D. (2014). The EVRP with time windows and recharging stations. Transportation Science, 48(4), 500-520.

\[5\] Zhang, K. et al. (2022). MMA-ALSC. Evolutionary Intelligence, 15, 2283-2294.

\[6\] Zitzler, E., Laumanns, M., & Thiele, L. (2001). SPEA2. TIK-Report 103.