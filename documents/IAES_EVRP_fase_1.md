**IAS-EVRP**

Especificacao para a Fase Incremental 1

_Representacao · Inicializacao · NSGA-II + CDP com pymoo_

Documento de implementacao coerente com o framework IAS-EVRP

# **1\. Contexto e objetivo do passo incremental**

Este documento especifica tudo o que e necessario para implementar a Fase 1 do IAS-EVRP: uma base de codigo solida, sem retrabalho futuro, que permita executar um primeiro experimento com NSGA-II utilizando Constraint Dominance Principle (CDP) no framework pymoo. O objetivo desta fase nao e produzir resultados competitivos - e validar a representacao, a inicializacao e o pipeline de avaliacao antes de introduzir os componentes especializados do IAS-EVRP (EOC, SIFO-E, DIMO-E, ORPG, ORE).

A logica de nao retrabalho e simples: tudo o que e escrito nesta fase e permanente. A representacao das solucoes, o CI, a inicializacao em tres camadas e o carregamento de instancias nao mudam quando o algoritmo evoluir de NSGA-II para IAS-EVRP. O que muda e apenas a camada do algoritmo - os operadores de selecao, as regras de sobrevivencia e os mecanismos de gestao de inviabilidade.

## **1.1 O que o NSGA-II + CDP valida**

Com este experimento sera possivel observar:

- Como o CDP trata os tres tipos de inviabilidade (IES, IC, IJT) de forma uniforme, sem distinção - o que confirma empiricamente a necessidade do tratamento diferenciado do IAS-EVRP.
- Se o mascaramento de objetivos e real nas instancias escolhidas: solucoes IES devem aparecer em posicoes aparentemente competitivas na frente de Pareto do CDP.
- A qualidade da inicializacao em tres camadas: a distribuicao de tipos (FVR, ERatio) ao longo das geracoes com CDP.
- O comportamento de convergencia de referencia que servira de baseline para comparacao com o IAS-EVRP.

## **1.2 Mapa de evolucao: o que fica, o que muda**

A tabela abaixo define explicitamente o destino de cada componente desta fase:

| **Componente**                                      | **Status na Fase 2+** | **Detalhe**                                                                                                          |
| --------------------------------------------------- | --------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Representacao (Solution, Route, Visit, Segment, CV) | Permanente            | Sem alteracoes. Todos os campos ja estao definidos para o IAS-EVRP completo.                                         |
| Classificador de Inviabilidade (CI)                 | Permanente            | O vetor de 4 componentes (cv_energy, cv_cascade, cv_cap, cv_tw) ja e produzido. O CDP apenas usa o escalar agregado. |
| Inicializacao em tres camadas                       | Permanente            | O DIMO-E usa diretamente os contadores da verificar_inicializacao() para calcular os limiares gamma.                 |
| Carregamento de instancias (EVRPInstance)           | Permanente            | Interface de dados compartilhada por todos os componentes.                                                           |
| EVRPProblem (pymoo)                                 | Adaptado              | Na Fase 2, o Problem.evaluate() e mantido mas passa a alimentar o SIFO-E em vez do NSGA-II standard.                 |
| EVRPSampling, EVRPCrossover, EVRPMutation (pymoo)   | Substituidos          | Na Fase 2, os operadores pymoo sao substituidos por CrossoverEVRP, ORPG, ORE do IAS-EVRP.                            |
| Regra de dominancia CDP (escalar G)                 | Substituida           | Na Fase 2, CDP e substituido por dominancia energia-consciente (<=\_ECD) do SIFO-E.                                  |
| EOC, SIFO-E, DIMO-E, ORPG, ORE, Arquivo Elite IES   | Adicionados na Fase 2 | Nao implementados nesta fase. A arquitetura desta fase e projetada para recebe-los sem conflito.                     |

# **2\. Arquitetura em tres camadas**

O codigo e organizado em tres camadas com responsabilidades separadas. Essa separacao e o que garante ausencia de retrabalho: cada camada pode ser substituida ou estendida independentemente.

| **Camada**                    | **Modulos**                                  | **O que contem**                                                                                                         |
| ----------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| 1 - Representacao e Avaliacao | representation.py, evaluator.py, instance.py | Classes de dados (Solution, Route, Visit...), CI, calculo de objetivos, carregamento de instancias. Nunca importa pymoo. |
| 2 - Inicializacao             | initialization.py                            | Tres camadas (viavel, IES, aleatoria), ORE para fallback, verificar_inicializacao(). Usa apenas a camada 1.              |
| 3 - Algoritmo (pymoo)         | problem.py, operators.py, runner.py          | EVRPProblem, EVRPSampling, EVRPCrossover, EVRPMutation. Unica camada que importa pymoo. Substituida na Fase 2.           |

**Nota:** _A camada 3 e a unica que conhece pymoo. As camadas 1 e 2 sao puro Python - testáveis de forma independente com unit tests antes de qualquer integracao com o algoritmo._

## **2.1 Estrutura de diretorios**

evrp/

\__init_\_.py

instance.py # EVRPInstance, carregamento de arquivos

representation.py # Solution, Route, Visit, Segment, CVVector, SolutionMetadata

evaluator.py # CI (classificador), compute_objectives, PopulationStats

initialization.py # Inicializacao 3 camadas, ORE, verificar_inicializacao

problem.py # EVRPProblem (pymoo Problem)

operators.py # EVRPSampling, EVRPCrossover, EVRPMutation (pymoo)

runner.py # Configuracao e execucao do experimento

metrics.py # FVR, ECD, ERatio, coleta de metricas por geracao

tests/

test_representation.py

test_ci.py

test_initialization.py

data/

schneider/ # Instancias Schneider et al. (2014)

# **3\. Carregamento de instancias (instance.py)**

## **3.1 Formato das instancias Schneider et al. (2014)**

As instancias do benchmark padrao do EVRP (Schneider et al., 2014) estao disponiveis em formato texto. Cada linha descreve um no com os campos: StringID, Type, x, y, demand, ReadyTime, DueDate, ServiceTime. O campo Type pode ser 'd' (depot), 'f' (station) ou 'c' (customer).

## **3.2 Estrutura EVRPInstance**

\# instance.py

from dataclasses import dataclass, field

from typing import Dict, List, Tuple

import numpy as np

@dataclass

class Node:

node_id: int

node_type: str # 'd', 'f', 'c'

x: float

y: float

demand: float # 0 para deposito e estacoes

ready_time: float # janela de tempo: abertura (b_i)

due_date: float # janela de tempo: fechamento (e_i)

service_time: float # tempo de servico (s_i)

@dataclass

class EVRPInstance:

name: str

nodes: List\[Node\]

depot_id: int

customer_ids: List\[int\]

station_ids: List\[int\]

Q: float # capacidade de carga

B: float # capacidade de bateria

v: float # velocidade (distancia/tempo)

t_charge: float # tempo de recarga total (modelo recarga total)

\# Matrizes pre-computadas (eficiencia no CI)

dist: np.ndarray # dist\[i\]\[j\]: distancia euclidiana

energy: np.ndarray # energy\[i\]\[j\]: consumo = dist\[i\]\[j\] \* r (taxa de consumo)

travel_time: np.ndarray # travel_time\[i\]\[j\] = dist\[i\]\[j\] / v

r: float = 1.0 # taxa de consumo de energia por unidade de distancia

def load_schneider(filepath: str, Q: float, B: float, v: float = 1.0,

r: float = 1.0, t_charge: float = 0.0) -> EVRPInstance:

'''

Carrega instancia no formato Schneider et al. (2014).

Q, B, v, r, t_charge sao parametros do veiculo (nao estao no arquivo).

Para instancias c101_21.txt: Q=200, B=75, v=1.0, r=0.125

'''

nodes = \[\]

depot_id = None

customer_ids = \[\]

station_ids = \[\]

with open(filepath) as f:

for line in f:

parts = line.strip().split()

if len(parts) < 8: continue

nid = len(nodes)

ntype = parts\[1\]

node = Node(nid, ntype, float(parts\[2\]), float(parts\[3\]),

float(parts\[4\]), float(parts\[5\]),

float(parts\[6\]), float(parts\[7\]))

nodes.append(node)

if ntype == 'd': depot_id = nid

elif ntype == 'c': customer_ids.append(nid)

elif ntype == 'f': station_ids.append(nid)

n = len(nodes)

dist = np.zeros((n, n))

for i in range(n):

for j in range(n):

dx = nodes\[i\].x - nodes\[j\].x

dy = nodes\[i\].y - nodes\[j\].y

dist\[i\]\[j\] = np.sqrt(dx\*dx + dy\*dy)

energy = dist \* r

travel_time = dist / v if v > 0 else dist

return EVRPInstance(name=filepath, nodes=nodes, depot_id=depot_id,

customer_ids=customer_ids, station_ids=station_ids,

Q=Q, B=B, v=v, t_charge=t_charge,

dist=dist, energy=energy, travel_time=travel_time, r=r)

# **4\. Representacao de solucoes (representation.py)**

A representacao e identica a especificada no documento de implementacao, traduzida para Python com dataclasses. Todos os campos necessarios para o IAS-EVRP completo estao presentes desde o inicio - o NSGA-II simplesmente nao usa todos eles.

## **4.1 Tipos enumerados**

\# representation.py

from \_\_future\_\_ import annotations

from dataclasses import dataclass, field

from enum import Enum, auto

from typing import List, Optional

class NodeType(Enum):

DEPOT = auto()

CUSTOMER = auto()

STATION = auto()

class InfeasType(Enum):

FEASIBLE = auto()

IES = auto() # Inviabilidade Energetica Simples

IEC = auto() # Inviabilidade Energetica Cascata

IC = auto() # Inviabilidade de Capacidade

IJT = auto() # Inviabilidade de Janela de Tempo

IM = auto() # Inviabilidade Mista

## **4.2 Classes Visit, Segment, CVVector e SolutionMetadata**

@dataclass

class Visit:

node_id: int

node_type: NodeType

arrival_energy: float = 0.0

departure_energy: float = 0.0

arrival_time: float = 0.0

service_start: float = 0.0

departure_time: float = 0.0

waiting_time: float = 0.0

delay_time: float = 0.0

@dataclass

class Segment:

from_idx: int # indice em visits\[\]

to_idx: int # indice em visits\[\]

energy_consumed: float

energy_deficit: float # max(0, deficit no trecho)

min_insert_cost: Optional\[float\] = None # calculado lazy pelo EOC

@dataclass

class CVVector:

cv_energy: float = 0.0 # violacao energetica normalizada (IES/IEC)

cv_cascade: float = 0.0 # severidade de cascata normalizada (IEC)

cv_cap: float = 0.0 # violacao de capacidade normalizada

cv_tw: float = 0.0 # violacao de janela de tempo normalizada

def total(self) -> float:

'''Escalar agregado usado pelo CDP.'''

return self.cv_energy + self.cv_cascade + self.cv_cap + self.cv_tw

def is_feasible(self, tol: float = 1e-9) -> bool:

return self.total() < tol

@dataclass

class SolutionMetadata:

n_vehicles: int = 0

total_distance: float = 0.0

makespan: float = 0.0

total_waiting: float = 0.0

total_delay: float = 0.0

inf_type: InfeasType = InfeasType.FEASIBLE

corrected_obj: Optional\[list\] = None # f_hat: preenchido pelo EOC (Fase 2)

## **4.3 Classes Route e Solution**

@dataclass

class Route:

visits: List\[Visit\] = field(default_factory=list)

energy_profile: List\[float\] = field(default_factory=list)

time_profile: List\[float\] = field(default_factory=list)

deficient_segments: List\[Segment\] = field(default_factory=list)

cv_route: CVVector = field(default_factory=CVVector)

\_raw_energy: float = 0.0 # violacao bruta (nao normalizada)

\_raw_cascade: float = 0.0

\_raw_cap: float = 0.0

\_raw_tw: float = 0.0

def n_customers(self) -> int:

return sum(1 for v in self.visits if v.node_type == NodeType.CUSTOMER)

def n_stations(self) -> int:

return sum(1 for v in self.visits if v.node_type == NodeType.STATION)

def customer_ids(self) -> List\[int\]:

return \[v.node_id for v in self.visits if v.node_type == NodeType.CUSTOMER\]

@dataclass

class Solution:

routes: List\[Route\] = field(default_factory=list)

metadata: SolutionMetadata = field(default_factory=SolutionMetadata)

cv_components: CVVector = field(default_factory=CVVector)

\_raw_energy: float = 0.0

\_raw_cascade: float = 0.0

\_raw_cap: float = 0.0

\_raw_tw: float = 0.0

\_dirty: bool = True # True = perfis desatualizados, CI deve ser re-executado

def objectives(self) -> List\[float\]:

'''Retorna \[f1, f2, f3, f4, f5\] para uso pelo Problem.evaluate().'''

m = self.metadata

return \[float(m.n_vehicles), m.total_distance, m.makespan,

m.total_waiting, m.total_delay\]

def all_customers(self) -> List\[int\]:

result = \[\]

for r in self.routes:

result.extend(r.customer_ids())

return result

def copy(self) -> 'Solution':

'''Copia profunda para uso nos operadores de crossover.'''

import copy

return copy.deepcopy(self)

## **4.4 Invariantes como funcao de verificacao**

A funcao check_invariants() deve ser chamada nos testes unitarios apos cada operacao que modifica a solucao. Em producao, pode ser desabilitada para performance.

def check_invariants(sol: Solution, instance: EVRPInstance) -> None:

'''Verifica I1-I5. Lanca AssertionError se algum invariante for violado.'''

all_customers = \[\]

for route in sol.routes:

\# I2: rota comeca e termina no deposito

assert route.visits\[0\].node_type == NodeType.DEPOT, 'I2: primeiro no nao e deposito'

assert route.visits\[-1\].node_type == NodeType.DEPOT, 'I2: ultimo no nao e deposito'

\# I2: deposito nao aparece no meio

for v in route.visits\[1:-1\]:

assert v.node_type != NodeType.DEPOT, 'I2: deposito no meio da rota'

\# I1: acumula clientes

for v in route.visits:

if v.node_type == NodeType.CUSTOMER:

all_customers.append(v.node_id)

\# I1: cada cliente aparece exatamente uma vez

assert sorted(all_customers) == sorted(instance.customer_ids), \\

f'I1: cobertura de clientes invalida'

assert len(all_customers) == len(set(all_customers)), 'I1: cliente duplicado'

\# I3: estacoes podem aparecer multiplas vezes (sem verificacao negativa)

\# I4 e I5 sao verificados implicitamente pelo CI (dirty flag)

# **5\. Classificador de Inviabilidade - CI (evaluator.py)**

O CI e o componente mais critico da Fase 1. Sua implementacao deve ser identica a especificada no documento de implementacao, sem simplificacoes. O NSGA-II usa apenas o escalar CVVector.total() para o CDP, mas os 4 componentes individuais (cv_energy, cv_cascade, cv_cap, cv_tw) sao necessarios desde agora para a coleta de metricas e para a Fase 2.

## **5.1 PopulationStats e normalizacao**

\# evaluator.py

from dataclasses import dataclass, field

from typing import List

from .representation import \*

from .instance import EVRPInstance

@dataclass

class PopulationStats:

max_energy: float = 0.0

min_energy: float = float('inf')

max_cascade: float = 0.0

min_cascade: float = float('inf')

max_cap: float = 0.0

min_cap: float = float('inf')

max_tw: float = 0.0

min_tw: float = float('inf')

def update_pop_stats(population: List\[Solution\]) -> PopulationStats:

'''O(N_P): uma passagem linear. Deve ser chamada apos cada geracao.'''

stats = PopulationStats()

for sol in population:

if sol.\_raw_energy > stats.max_energy: stats.max_energy = sol.\_raw_energy

if sol.\_raw_energy < stats.min_energy: stats.min_energy = sol.\_raw_energy

if sol.\_raw_cascade > stats.max_cascade: stats.max_cascade = sol.\_raw_cascade

if sol.\_raw_cascade < stats.min_cascade: stats.min_cascade = sol.\_raw_cascade

if sol.\_raw_cap > stats.max_cap: stats.max_cap = sol.\_raw_cap

if sol.\_raw_cap < stats.min_cap: stats.min_cap = sol.\_raw_cap

if sol.\_raw_tw > stats.max_tw: stats.max_tw = sol.\_raw_tw

if sol.\_raw_tw < stats.min_tw: stats.min_tw = sol.\_raw_tw

return stats

def \_normalize(raw: float, max_raw: float, min_raw: float) -> float:

if max_raw == min_raw:

return 1.0 if min_raw > 1e-9 else 0.0

return (raw - min_raw) / (max_raw - min_raw)

def renormalize(sol: Solution, stats: PopulationStats) -> None:

'''Atualiza cv_components sem recalcular perfis (usa \_raw armazenado).'''

sol.cv_components.cv_energy = \_normalize(sol.\_raw_energy, stats.max_energy, stats.min_energy)

sol.cv_components.cv_cascade = \_normalize(sol.\_raw_cascade, stats.max_cascade, stats.min_cascade)

sol.cv_components.cv_cap = \_normalize(sol.\_raw_cap, stats.max_cap, stats.min_cap)

sol.cv_components.cv_tw = \_normalize(sol.\_raw_tw, stats.max_tw, stats.min_tw)

## **5.2 compute_route_profile: nucleo do CI**

def compute_route_profile(route: Route, inst: EVRPInstance) -> None:

'''

Percorre a rota sequencialmente calculando perfis de energia e tempo.

Popula energy*profile, time_profile, deficient_segments, \_raw*\*.'''

route.energy_profile = \[\]

route.time_profile = \[\]

route.deficient_segments = \[\]

route.\_raw_energy = 0.0

route.\_raw_cascade = 0.0

route.\_raw_cap = 0.0

route.\_raw_tw = 0.0

curr_energy = inst.B

curr_time = 0.0

total_demand = 0.0

in_cascade = False

route.energy_profile.append(curr_energy)

route.time_profile.append(curr_time)

for j in range(1, len(route.visits)):

prev = route.visits\[j-1\]

curr = route.visits\[j\]

i_id, j_id = prev.node_id, curr.node_id

\# ── Energia ──────────────────────────────────────────────

e_ij = inst.energy\[i_id\]\[j_id\]

curr_energy -= e_ij

curr.arrival_energy = curr_energy

if curr_energy < -1e-9: # deficit

deficit = -curr_energy

route.\_raw_energy += deficit

seg = Segment(from_idx=j-1, to_idx=j,

energy_consumed=e_ij,

energy_deficit=deficit,

min_insert_cost=None) # lazy: EOC calcula

route.deficient_segments.append(seg)

if in_cascade:

route.\_raw_cascade += 1

else:

in_cascade = True

else:

in_cascade = False

if curr.node_type == NodeType.STATION:

curr.departure_energy = inst.B

curr_energy = inst.B

in_cascade = False

else:

curr.departure_energy = max(0.0, curr_energy)

route.energy_profile.append(curr_energy)

\# ── Tempo ─────────────────────────────────────────────────

t_ij = inst.travel_time\[i_id\]\[j_id\]

curr_time += t_ij

curr.arrival_time = curr_time

if curr.node_type == NodeType.CUSTOMER:

node = inst.nodes\[j_id\]

wait = max(0.0, node.ready_time - curr_time)

delay = max(0.0, curr_time - node.due_date)

curr.waiting_time = wait

curr.delay_time = delay

curr.service_start = curr_time + wait

curr_time += wait + node.service_time

if delay > 1e-9:

route.\_raw_tw += delay

total_demand += node.demand

elif curr.node_type == NodeType.STATION:

curr_time += inst.t_charge

curr.departure_time = curr_time

route.time_profile.append(curr_time)

\# ── Capacidade ────────────────────────────────────────────────

route.\_raw_cap = max(0.0, total_demand - inst.Q)

\# ── Janela do deposito ────────────────────────────────────────

depot = inst.nodes\[inst.depot_id\]

last_time = route.visits\[-1\].arrival_time

if last_time > depot.due_date + 1e-9:

route.\_raw_tw += last_time - depot.due_date

## **5.3 CI completo: classify_type e compute_objectives**

def classify_type(cv: CVVector, tol: float = 1e-9) -> InfeasType:

has_e = cv.cv_energy > tol

has_cas = cv.cv_cascade > tol

has_cap = cv.cv_cap > tol

has_tw = cv.cv_tw > tol

n = sum(\[has_e, has_cas, has_cap, has_tw\])

if n == 0: return InfeasType.FEASIBLE

if (has_e or has_cas) and (has_cap or has_tw): return InfeasType.IM

if has_e and not has_cap and not has_tw:

return InfeasType.IEC if has_cas else InfeasType.IES

if has_cap and not has_e and not has_tw: return InfeasType.IC

if has_tw and not has_e and not has_cap: return InfeasType.IJT

return InfeasType.IM

def compute_objectives(sol: Solution, inst: EVRPInstance) -> None:

'''Calcula f1-f5 e armazena em sol.metadata. Nao aplica correcao (sem EOC).'''

m = sol.metadata

m.n_vehicles = len(sol.routes)

m.total_distance = 0.0

m.makespan = 0.0

m.total_waiting = 0.0

m.total_delay = 0.0

for route in sol.routes:

dist_r = sum(inst.dist\[route.visits\[k\].node_id\]\[route.visits\[k+1\].node_id\]

for k in range(len(route.visits)-1))

m.total_distance += dist_r

tempo_r = route.visits\[-1\].arrival_time - route.visits\[0\].departure_time

m.makespan = max(m.makespan, tempo_r)

m.total_waiting += sum(v.waiting_time for v in route.visits

if v.node_type == NodeType.CUSTOMER)

m.total_delay += sum(v.delay_time for v in route.visits

if v.node_type == NodeType.CUSTOMER)

def run_ci(sol: Solution, inst: EVRPInstance, stats: PopulationStats) -> None:

'''Executa CI completo: perfil, violacoes brutas, normalizacao, tipo.'''

sol.\_raw_energy = 0.0; sol.\_raw_cascade = 0.0

sol.\_raw_cap = 0.0; sol.\_raw_tw = 0.0

for route in sol.routes:

compute_route_profile(route, inst)

sol.\_raw_energy += route.\_raw_energy

sol.\_raw_cascade += route.\_raw_cascade

sol.\_raw_cap += route.\_raw_cap

sol.\_raw_tw += route.\_raw_tw

renormalize(sol, stats)

sol.metadata.inf_type = classify_type(sol.cv_components)

compute_objectives(sol, inst)

sol.\_dirty = False

# **6\. Inicializacao em tres camadas (initialization.py)**

A inicializacao produz a populacao P0 com distribuicao de tipos coerente com os limiares do DIMO-E (Fase 2). Os contadores produzidos por verificar_inicializacao() sao armazenados e reutilizados diretamente na Fase 2 para calcular gamma_E, gamma_C, gamma_T.

## **6.1 Parametros e valores padrao**

| **Parametro**  | **Valor padrao** | **Range**      | **Descricao**                                              |
| -------------- | ---------------- | -------------- | ---------------------------------------------------------- |
| alpha_V        | 0.40             | \[0.30, 0.60\] | Fracao-alvo de solucoes viaveis na populacao inicial       |
| alpha_E        | 0.35             | \[0.20, 0.45\] | Fracao-alvo de solucoes IES na populacao inicial           |
| alpha_R        | 0.25             | \[0.15, 0.35\] | Fracao restante (IEC/IC/IJT/aleatorio)                     |
| beta_s         | 0.20             | \[0.0, 0.40\]  | Limiar de seguranca energetica (fracao de B) para camada V |
| p_skip_station | 0.50             | \[0.30, 0.70\] | Probabilidade de pular insercao de estacao na camada E     |
| max_tries_mult | 5                | \[3, 10\]      | Multiplicador de tentativas por camada (5 x n_target)      |

## **6.2 Funcao auxiliar: melhor estacao**

\# initialization.py

import random

from .representation import \*

from .instance import EVRPInstance

from .evaluator import run_ci, update_pop_stats, renormalize, PopulationStats

def \_best_station(from_id: int, to_id: int, curr_energy: float,

inst: EVRPInstance) -> Optional\[int\]:

'''Estacao alvo de menor desvio de rota alcancavel com curr_energy.'''

best_s, best_delta = None, float('inf')

for s_id in inst.station_ids:

if inst.energy\[from_id\]\[s_id\] <= curr_energy + 1e-9:

delta = inst.dist\[from_id\]\[s_id\] + inst.dist\[s_id\]\[to_id\] - inst.dist\[from_id\]\[to_id\]

if delta < best_delta:

best_delta = delta

best_s = s_id

return best_s

def \_new_route(depot_id: int) -> Route:

depot_visit = Visit(node_id=depot_id, node_type=NodeType.DEPOT)

return Route(visits=\[depot_visit\])

def \_close_route(route: Route, depot_id: int) -> Route:

route.visits.append(Visit(node_id=depot_id, node_type=NodeType.DEPOT))

return route

## **6.3 Camada V: solucoes viaveis**

def \_generate_feasible(inst: EVRPInstance, beta_s: float) -> Solution:

customers = inst.customer_ids\[:\]

random.shuffle(customers)

routes = \[\]

curr_route = \_new_route(inst.depot_id)

curr_energy = inst.B

curr_time = 0.0

curr_demand = 0.0

last_node = inst.depot_id

while customers:

c = customers\[0\]

node_c = inst.nodes\[c\]

\# Violacao de capacidade: abre nova rota

if curr_demand + node_c.demand > inst.Q + 1e-9:

routes.append(\_close_route(curr_route, inst.depot_id))

curr_route = \_new_route(inst.depot_id)

curr_energy = inst.B

curr_time = 0.0

curr_demand = 0.0

last_node = inst.depot_id

continue

e_to_c = inst.energy\[last_node\]\[c\]

e_to_depot = inst.energy\[c\]\[inst.depot_id\]

\# Verificacao de seguranca: ir a c E retornar ao deposito

if curr_energy - e_to_c - e_to_depot < beta_s \* inst.B:

s_id = \_best_station(last_node, c, curr_energy, inst)

if s_id is None:

\# Nenhuma estacao alcancavel: fecha rota

routes.append(\_close_route(curr_route, inst.depot_id))

curr_route = \_new_route(inst.depot_id)

curr_energy = inst.B

curr_time = 0.0

curr_demand = 0.0

last_node = inst.depot_id

continue

\# Insere estacao

curr_route.visits.append(Visit(s_id, NodeType.STATION))

curr_time += inst.travel_time\[last_node\]\[s_id\] + inst.t_charge

curr_energy = inst.B

last_node = s_id

curr_route.visits.append(Visit(c, NodeType.CUSTOMER))

curr_energy -= e_to_c

curr_time += inst.travel_time\[last_node\]\[c\]

curr_demand += node_c.demand

last_node = c

customers.pop(0)

routes.append(\_close_route(curr_route, inst.depot_id))

return Solution(routes=routes)

## **6.4 Camada E: solucoes IES**

def \_generate_ies(inst: EVRPInstance, p_skip: float) -> Solution:

'''

Igual a \_generate_feasible mas com beta_s=0 e probabilidade p_skip de

pular a insercao de estacao quando a bateria ficaria negativa.

Clamp: apos primeiro deficit, energia e fixada em 0 para nao gerar IEC.

'''

customers = inst.customer_ids\[:\]

random.shuffle(customers)

routes = \[\]

curr_route = \_new_route(inst.depot_id)

curr_energy = inst.B

curr_demand = 0.0

last_node = inst.depot_id

deficit_gerado = False # clamp: so 1 trecho deficiente por rota

while customers:

c = customers\[0\]

node_c = inst.nodes\[c\]

if curr_demand + node_c.demand > inst.Q + 1e-9:

routes.append(\_close_route(curr_route, inst.depot_id))

curr_route = \_new_route(inst.depot_id)

curr_energy = inst.B

curr_demand = 0.0

last_node = inst.depot_id

deficit_gerado = False

continue

e_to_c = inst.energy\[last_node\]\[c\]

if curr_energy - e_to_c < -1e-9 and not deficit_gerado:

\# Bateria ficaria negativa: decide se insere estacao

if random.random() < p_skip:

\# Pula: gera IES

curr_route.visits.append(Visit(c, NodeType.CUSTOMER))

curr_energy -= e_to_c

curr_energy = 0.0 # CLAMP: evita cascata

deficit_gerado = True

else:

s_id = \_best_station(last_node, c, curr_energy, inst)

if s_id:

curr_route.visits.append(Visit(s_id, NodeType.STATION))

curr_energy = inst.B

last_node = s_id

curr_route.visits.append(Visit(c, NodeType.CUSTOMER))

curr_energy -= inst.energy\[last_node\]\[c\]

else:

curr_route.visits.append(Visit(c, NodeType.CUSTOMER))

curr_energy -= e_to_c

curr_energy = max(0.0, curr_energy) if deficit_gerado else curr_energy

curr_demand += node_c.demand

last_node = c

customers.pop(0)

routes.append(\_close_route(curr_route, inst.depot_id))

return Solution(routes=routes)

## **6.5 Camada R: solucoes aleatorias**

def \_generate_random(inst: EVRPInstance) -> Solution:

'''Sem verificacoes de restricoes. Gera IEC, IC, IJT para diversidade.'''

customers = inst.customer_ids\[:\]

random.shuffle(customers)

r_threshold = random.uniform(0, inst.nodes\[inst.depot_id\].due_date \* 0.5)

routes = \[\]

curr_route = \_new_route(inst.depot_id)

curr_time = 0.0

last_node = inst.depot_id

for c in customers:

curr_time += inst.travel_time\[last_node\]\[c\]

delay = max(0.0, curr_time - inst.nodes\[c\].due_date)

if delay > r_threshold:

routes.append(\_close_route(curr_route, inst.depot_id))

curr_route = \_new_route(inst.depot_id)

curr_time = 0.0

last_node = inst.depot_id

curr_time += inst.travel_time\[last_node\]\[c\]

curr_route.visits.append(Visit(c, NodeType.CUSTOMER))

curr_time += inst.nodes\[c\].service_time

last_node = c

routes.append(\_close_route(curr_route, inst.depot_id))

return Solution(routes=routes)

## **6.6 ORE: operador de remocao de estacao (fallback)**

O ORE e necessario como fallback quando a camada E nao atinge o alvo n_E (instancias dificeis de gerar IES naturalmente). Nesta fase ele e simples - na Fase 2 sera estendido para selecionar estacoes por 'folga' energetica.

def ore_fallback(sol: Solution, inst: EVRPInstance) -> Optional\[Solution\]:

'''

Remove uma estacao aleatorio de uma solucao viavel para gerar uma IES.

Retorna None se nao ha estacoes removiveis.

'''

new_sol = sol.copy()

\# Coleta todas as estacoes removiveis (exceto unicas necessarias)

candidates = \[\]

for r_idx, route in enumerate(new_sol.routes):

for v_idx, v in enumerate(route.visits):

if v.node_type == NodeType.STATION:

candidates.append((r_idx, v_idx))

if not candidates:

return None

r_idx, v_idx = random.choice(candidates)

new_sol.routes\[r_idx\].visits.pop(v_idx)

new_sol.\_dirty = True

return new_sol

## **6.7 Funcao principal de inicializacao**

@dataclass

class InitResult:

population: List\[Solution\]

n_V: int

n_IES: int

n_IEC: int

n_IC: int

n_IJT: int

n_IM: int

eta: float # proporcao total de inviaveis = base para gamma

eta_E: float # n_IES / N_P

eta_C: float # n_IC / N_P

eta_T: float # n_IJT / N_P

pop_stats: PopulationStats

def initialize(inst: EVRPInstance, N_P: int = 100,

alpha_V: float = 0.40, alpha_E: float = 0.35,

beta_s: float = 0.20, p_skip: float = 0.50,

max_tries_mult: int = 5, seed: int = 42) -> InitResult:

random.seed(seed)

n_V = round(alpha_V \* N_P)

n_E = round(alpha_E \* N_P)

n_R = N_P - n_V - n_E

population = \[\]

empty_stats = PopulationStats() # stats vazias para CI inicial

\# ── Camada V ──────────────────────────────────────────────────

tries, n_V_real = 0, 0

while n_V_real < n_V and tries < max_tries_mult \* n_V:

sol = \_generate_feasible(inst, beta_s)

run_ci(sol, inst, empty_stats)

if sol.metadata.inf_type == InfeasType.FEASIBLE:

population.append(sol)

n_V_real += 1

tries += 1

\# ── Camada E ──────────────────────────────────────────────────

tries, n_E_real = 0, 0

while n_E_real < n_E and tries < max_tries_mult \* n_E:

sol = \_generate_ies(inst, p_skip)

run_ci(sol, inst, empty_stats)

if sol.metadata.inf_type == InfeasType.IES:

population.append(sol)

n_E_real += 1

tries += 1

\# Fallback via ORE se nao atingiu n_E

feasible_pool = \[s for s in population if s.metadata.inf_type == InfeasType.FEASIBLE\]

while n_E_real < n_E and feasible_pool:

src = random.choice(feasible_pool)

candidate = ore_fallback(src, inst)

if candidate is not None:

run_ci(candidate, inst, empty_stats)

if candidate.metadata.inf_type == InfeasType.IES:

population.append(candidate)

n_E_real += 1

\# ── Camada R ──────────────────────────────────────────────────

for \_in range(n_R):

sol = \_generate_random(inst)

run_ci(sol, inst, empty_stats)

population.append(sol)

\# ── Pos-inicializacao: normalizar com stats reais ──────────────

stats = update_pop_stats(population)

for sol in population:

renormalize(sol, stats)

sol.metadata.inf_type = classify_type(sol.cv_components)

\# ── Contagem de tipos ─────────────────────────────────────────

from collections import Counter

counts = Counter(s.metadata.inf_type for s in population)

n_V_f = counts\[InfeasType.FEASIBLE\]

n_IES = counts\[InfeasType.IES\]

n_IEC = counts\[InfeasType.IEC\]

n_IC = counts\[InfeasType.IC\]

n_IJT = counts\[InfeasType.IJT\]

n_IM = counts\[InfeasType.IM\]

total_inf = N_P - n_V_f

eta = total_inf / N_P

eta_E = n_IES / N_P

eta_C = n_IC / N_P

eta_T = n_IJT / N_P

\# ── Alertas de diagnostico ────────────────────────────────────

if eta < 0.15:

print(f'\[INIT ALERTA\] Instancia facil: eta={eta:.2f}. Aumente p_skip.')

if eta > 0.70:

print(f'\[INIT ALERTA\] Instancia muito dificil: eta={eta:.2f}.')

frac_ies = n_IES / max(1, total_inf)

if frac_ies < 0.40:

print(f'\[INIT ALERTA\] Poucos IES entre inviaveis: {frac_ies:.0%}.')

return InitResult(population=population,

n_V=n_V_f, n_IES=n_IES, n_IEC=n_IEC, n_IC=n_IC, n_IJT=n_IJT, n_IM=n_IM,

eta=eta, eta_E=eta_E, eta_C=eta_C, eta_T=eta_T, pop_stats=stats)

# **7\. Integracao com pymoo: EVRPProblem e operadores**

A integracao com pymoo usa a abordagem de representacao por objeto: cada solucao e armazenada como um objeto Python no array X (dtype=object). Essa abordagem e a unica que funciona sem retrabalho para representacoes de comprimento variavel como o EVRP.

## **7.1 Decisao de design: X como array de objetos**

pymoo espera arrays numpy X de shape (n_pop, n_var). Para representacoes de comprimento variavel, a convencao e usar n_var=1 com dtype=object, onde X\[i, 0\] e o objeto Solution. Todos os operadores (Sampling, Crossover, Mutation) seguem essa convencao uniformemente.

**Nota:** _Na Fase 2, os operadores pymoo (EVRPSampling, EVRPCrossover, EVRPMutation) serao substituidos pelos operadores IAS-EVRP. O EVRPProblem e mantido sem alteracoes - apenas o algoritmo muda. A camada de problema e, portanto, permanente._

## **7.2 EVRPProblem**

\# problem.py

import numpy as np

from pymoo.core.problem import ElementwiseProblem

from .representation import Solution, InfeasType

from .instance import EVRPInstance

from .evaluator import run_ci, update_pop_stats, renormalize, PopulationStats

class EVRPProblem(ElementwiseProblem):

'''

Problema EVRP multi-objetivo para pymoo.

Objetivos: \[f1=n_vehicles, f2=dist, f3=makespan, f4=wait, f5=delay\]

Restricao G\[0\]: cv_total (CDP escalar). G <= 0 = viavel.

'''

def \__init_\_(self, instance: EVRPInstance):

super().\__init_\_(

n_var=1,

n_obj=5,

n_ieq_constr=1, # Um escalar para CDP

xl=None, xu=None

)

self.instance = instance

self.pop_stats = PopulationStats() # atualizado externamente

def \_evaluate(self, x, out, \*args, \*\*kwargs):

sol: Solution = x\[0\]

if sol.\_dirty:

run_ci(sol, self.instance, self.pop_stats)

out\['F'\] = sol.objectives()

\# CDP: cv_total = 0 significa viavel (G <= 0 = viavel em pymoo)

out\['G'\] = \[sol.cv_components.total()\]

def update_pop_stats(self, population: list) -> None:

'''

Deve ser chamado ao final de cada geracao antes da proxima avaliacao.

Atualiza a normalizacao dos CVs para a geracao atual.

'''

self.pop_stats = update_pop_stats(population)

for sol in population:

renormalize(sol, self.pop_stats)

## **7.3 EVRPSampling**

\# operators.py

import numpy as np

from pymoo.core.sampling import Sampling

from pymoo.core.crossover import Crossover

from pymoo.core.mutation import Mutation

from .initialization import initialize, InitResult

from .instance import EVRPInstance

from .representation import \*

from .evaluator import run_ci, PopulationStats

import random

class EVRPSampling(Sampling):

'''Delegado para initialize(). Armazena InitResult para uso pelo runner.'''

def \__init_\_(self, instance: EVRPInstance, init_params: dict):

super().\__init_\_()

self.instance = instance

self.init_params = init_params

self.init_result: InitResult = None

def \_do(self, problem, n_samples, \*\*kwargs):

result = initialize(self.instance, N_P=n_samples, \*\*self.init_params)

self.init_result = result

problem.pop_stats = result.pop_stats # injeta stats iniciais no Problem

X = np.empty((n_samples, 1), dtype=object)

for i, sol in enumerate(result.population):

X\[i, 0\] = sol

return X

## **7.4 EVRPCrossover: crossover de rotas (sem consciencia energetica)**

Nesta fase, o crossover de rotas e implementado sem a Fase 3 de correcao energetica (sem theta_insert). O CDP gerenciara as inviabilidades produzidas. Na Fase 2, este operador sera substituido pelo CrossoverEVRP com consciencia energetica.

class EVRPCrossover(Crossover):

def \__init_\_(self):

super().\__init_\_(2, 2) # 2 pais, 2 filhos

def \_do(self, problem, X, \*\*kwargs):

\# X.shape = (n_parents=2, n_matings, n_var=1)

n_matings = X.shape\[1\]

Y = np.empty((2, n_matings, 1), dtype=object)

for k in range(n_matings):

p1: Solution = X\[0, k, 0\]

p2: Solution = X\[1, k, 0\]

c1, c2 = \_route_crossover(p1, p2, problem.instance)

Y\[0, k, 0\] = c1

Y\[1, k, 0\] = c2

return Y

def \_route_crossover(p1: Solution, p2: Solution,

inst: EVRPInstance) -> tuple:

'''Crossover de rotas (Wang et al.) sem correcao energetica.'''

if not p1.routes or not p2.routes:

return p1.copy(), p2.copy()

r1 = random.choice(p1.routes)

r2 = random.choice(p2.routes)

C1 = set(r1.customer_ids())

C2 = set(r2.customer_ids())

c1 = \_build_offspring(p2, C1, r1, inst)

c2 = \_build_offspring(p1, C2, r2, inst)

return c1, c2

def \_build_offspring(base: Solution, to_remove: set,

new_route: Route, inst: EVRPInstance) -> Solution:

'''Remove clientes conflitantes de base, adiciona new_route, reinsere orfaos.'''

child = base.copy()

orphans = \[\]

for route in child.routes:

kept = \[\]

for v in route.visits:

if v.node_type == NodeType.CUSTOMER and v.node_id in to_remove:

orphans.append(v.node_id)

else:

kept.append(v)

route.visits = kept

\# Remove rotas que ficaram vazias (so deposito)

child.routes = \[r for r in child.routes if r.n_customers() > 0\]

\# Conserta depositos (garante I2 apos remocao)

for r in child.routes:

if r.visits\[0\].node_type != NodeType.DEPOT:

r.visits.insert(0, Visit(inst.depot_id, NodeType.DEPOT))

if r.visits\[-1\].node_type != NodeType.DEPOT:

r.visits.append(Visit(inst.depot_id, NodeType.DEPOT))

\# Adiciona rota herdada

child.routes.append(new_route.copy() if hasattr(new_route, 'copy')

else Route(visits=\[v for v in new_route.visits\]))

\# Reinsere orfaos (greedy: menor custo de insercao)

\_reinsert_orphans(child, orphans, inst)

child.\_dirty = True

return child

def \_reinsert_orphans(sol: Solution, orphans: list, inst: EVRPInstance) -> None:

for c_id in orphans:

best_pos, best_cost = None, float('inf')

node_c = inst.nodes\[c_id\]

for r_idx, route in enumerate(sol.routes):

\# Verifica capacidade aproximada (sem recalcular perfil completo)

demand_r = sum(inst.nodes\[v.node_id\].demand for v in route.visits

if v.node_type == NodeType.CUSTOMER)

if demand_r + node_c.demand > inst.Q + 1e-9:

continue

for pos in range(1, len(route.visits)):

prev_id = route.visits\[pos-1\].node_id

next_id = route.visits\[pos\].node_id

cost = (inst.dist\[prev_id\]\[c_id\] + inst.dist\[c_id\]\[next_id\]

\- inst.dist\[prev_id\]\[next_id\])

if cost < best_cost:

best_cost = cost

best_pos = (r_idx, pos)

if best_pos:

r_idx, pos = best_pos

sol.routes\[r_idx\].visits.insert(pos, Visit(c_id, NodeType.CUSTOMER))

else:

\# Abre nova rota

new_r = Route(visits=\[

Visit(inst.depot_id, NodeType.DEPOT),

Visit(c_id, NodeType.CUSTOMER),

Visit(inst.depot_id, NodeType.DEPOT)

\])

sol.routes.append(new_r)

## **7.5 EVRPMutation: 2-opt intra-rota**

class EVRPMutation(Mutation):

def \__init_\_(self, prob: float = 0.1):

super().\__init_\_()

self.prob = prob

def \_do(self, problem, X, \*\*kwargs):

for i in range(len(X)):

if random.random() < self.prob:

sol: Solution = X\[i, 0\]

X\[i, 0\] = \_two_opt_mutation(sol, problem.instance)

return X

def \_two_opt_mutation(sol: Solution, inst: EVRPInstance) -> Solution:

'''2-opt em uma rota aleatoria (apenas entre clientes, mantem estacoes).'''

if not sol.routes: return sol

new_sol = sol.copy()

route = random.choice(new_sol.routes)

cust_positions = \[i for i, v in enumerate(route.visits)

if v.node_type == NodeType.CUSTOMER\]

if len(cust_positions) < 2: return new_sol

i, j = sorted(random.sample(cust_positions, 2))

\# Inverte segmento de clientes entre posicoes i e j

route.visits\[i:j+1\] = route.visits\[i:j+1\]\[::-1\]

new_sol.\_dirty = True

return new_sol

# **8\. Runner e metricas (runner.py, metrics.py)**

## **8.1 Callback para atualizacao de pop_stats e coleta de metricas**

Em pymoo, o callback e a maneira de executar logica personalizada ao final de cada geracao. O callback abaixo (a) atualiza o PopulationStats do Problem (necessario para re-normalizacao dos CVs) e (b) coleta as metricas especificas do EVRP a cada geracao.

\# runner.py

import numpy as np

from pymoo.algorithms.moo.nsga2 import NSGA2

from pymoo.optimize import minimize

from pymoo.core.callback import Callback

from .problem import EVRPProblem

from .operators import EVRPSampling, EVRPCrossover, EVRPMutation

from .metrics import compute_generation_metrics, GenerationMetrics

from .instance import EVRPInstance

from .evaluator import update_pop_stats

from .representation import InfeasType

class EVRPCallback(Callback):

def \__init_\_(self, problem: EVRPProblem):

super().\__init_\_()

self.problem = problem

self.history: list = \[\]

def notify(self, algorithm):

pop = algorithm.pop

solutions = \[ind.X\[0\] for ind in pop\]

\# 1. Atualiza pop_stats e re-normaliza CVs

self.problem.update_pop_stats(solutions)

\# 2. Coleta metricas

gen = algorithm.n_gen

metrics = compute_generation_metrics(solutions, gen)

self.history.append(metrics)

\# 3. Log resumido a cada 10 geracoes

if gen % 10 == 0:

print(f'Gen {gen:4d} | FVR={metrics.fvr:.2%} | '

f'ERatio={metrics.eratio:.2%} | '

f'n_pareto={metrics.n_pareto_feasible}')

def run_experiment(instance: EVRPInstance,

N_P: int = 100,

N_gen: int = 300,

init_params: dict = None,

seed: int = 42) -> dict:

if init_params is None:

init_params = dict(alpha_V=0.40, alpha_E=0.35, beta_s=0.20, p_skip=0.50)

problem = EVRPProblem(instance)

sampling = EVRPSampling(instance, init_params)

callback = EVRPCallback(problem)

algorithm = NSGA2(

pop_size=N_P,

sampling=sampling,

crossover=EVRPCrossover(),

mutation=EVRPMutation(prob=0.15),

eliminate_duplicates=False # solucoes de comprimento variavel

)

res = minimize(

problem,

algorithm,

('n_gen', N_gen),

callback=callback,

seed=seed,

verbose=False

)

return {

'result': res,

'history': callback.history,

'init_result': sampling.init_result,

'pareto_solutions': \[ind.X\[0\] for ind in res.opt\]

}

## **8.2 Metricas por geracao**

\# metrics.py

from dataclasses import dataclass

from typing import List

from .representation import Solution, InfeasType

from collections import Counter

@dataclass

class GenerationMetrics:

generation: int

fvr: float # Feasible Visit Rate: proporcao de viaveis na pop

eratio: float # proporcao de IES na pop

n_pareto_feasible: int # solucoes viaveis na frente de Pareto estimada

avg_cv_energy: float

avg_cv_cap: float

avg_cv_tw: float

avg_f2_feasible: float # distancia media das solucoes viaveis

avg_f2_ies: float # distancia media das solucoes IES (mascaramento)

n_IES: int

n_IEC: int

n_IC: int

n_IJT: int

n_IM: int

def compute_generation_metrics(solutions: List\[Solution\],

generation: int) -> GenerationMetrics:

counts = Counter(s.metadata.inf_type for s in solutions)

N = len(solutions)

n_feasible = counts\[InfeasType.FEASIBLE\]

n_ies = counts\[InfeasType.IES\]

feasible_sols = \[s for s in solutions if s.metadata.inf_type == InfeasType.FEASIBLE\]

ies_sols = \[s for s in solutions if s.metadata.inf_type == InfeasType.IES\]

return GenerationMetrics(

generation=generation,

fvr=n_feasible / N if N > 0 else 0.0,

eratio=n_ies / N if N > 0 else 0.0,

n_pareto_feasible=\_count_pareto(feasible_sols),

avg_cv_energy=sum(s.cv_components.cv_energy for s in solutions)/N if N > 0 else 0,

avg_cv_cap=sum(s.cv_components.cv_cap for s in solutions)/N if N > 0 else 0,

avg_cv_tw=sum(s.cv_components.cv_tw for s in solutions)/N if N > 0 else 0,

avg_f2_feasible=sum(s.metadata.total_distance for s in feasible_sols)/len(feasible_sols) if feasible_sols else 0,

avg_f2_ies=sum(s.metadata.total_distance for s in ies_sols)/len(ies_sols) if ies_sols else 0,

n_IES=n_ies,

n_IEC=counts\[InfeasType.IEC\],

n_IC=counts\[InfeasType.IC\],

n_IJT=counts\[InfeasType.IJT\],

n_IM=counts\[InfeasType.IM\]

)

def \_count_pareto(solutions: List\[Solution\]) -> int:

'''Conta solucoes nao-dominadas em f1-f5 (simples, O(n^2)).'''

if not solutions: return 0

non_dom = 0

objs = \[s.objectives() for s in solutions\]

for i, oi in enumerate(objs):

dominated = False

for j, oj in enumerate(objs):

if i == j: continue

if all(oj\[k\] <= oi\[k\] for k in range(5)) and any(oj\[k\] < oi\[k\] for k in range(5)):

dominated = True

break

if not dominated:

non_dom += 1

return non_dom

# **9\. Configuracao do experimento de validacao**

## **9.1 Instancias recomendadas para Fase 1**

| **Instancia** | **Clientes** | **Estacoes** | **Dificuldade** | **Proposito**                                                  |
| ------------- | ------------ | ------------ | --------------- | -------------------------------------------------------------- |
| c101_21       | 21           | 3            | Facil           | Sanity check: deve convergir para solucoes viaveis rapidamente |
| c201_21       | 21           | 3            | Facil           | Janelas de tempo largas - testa IJT vs IES                     |
| r101_21       | 21           | 3            | Media           | Distribuicao aleatoria - testa diversidade                     |
| c101_51       | 51           | 3            | Media-alta      | Primeira instancia de tamanho real                             |
| r101_51       | 51           | 3            | Alta            | Instancia desafiadora - valida escalabilidade do CI            |

**Nota:** _Parametros do veiculo para instancias Schneider (2014): Q=200, B=75, r=0.125, v=1.0, t_charge=0.0. Estes valores sao os do benchmark padrao e devem ser verificados para cada arquivo de instancia._

## **9.2 Parametros do experimento**

| **Parametro**               | **Valor**          | **Justificativa**                                          |
| --------------------------- | ------------------ | ---------------------------------------------------------- |
| N_P (populacao)             | 100                | Padrao do CMOEA-IAS para comparabilidade futura            |
| N_gen (geracoes)            | 300                | Suficiente para convergencia nas instancias de 21 clientes |
| alpha_V / alpha_E / alpha_R | 0.40 / 0.35 / 0.25 | Valores padrao do documento de implementacao               |
| beta_s                      | 0.20               | 20% de margem de seguranca energetica na camada V          |
| p_skip_station              | 0.50               | 50% de chance de pular estacao na camada E                 |
| prob_mutation               | 0.15               | 15% de probabilidade de mutacao 2-opt por individuo        |
| seeds                       | 5 (42,43,44,45,46) | Media sobre 5 sementes para reduzir variancia              |
| Objetivos ativos            | f1, f2, f3, f4, f5 | Todos os 5 objetivos do IAS-EVRP completo                  |

## **9.3 Script de execucao minimo**

\# run_baseline.py

from evrp.instance import load_schneider

from evrp.runner import run_experiment

import json

inst = load_schneider('data/schneider/c101_21.txt',

Q=200, B=75, v=1.0, r=0.125, t_charge=0.0)

results = run_experiment(

instance=inst,

N_P=100, N_gen=300,

init_params=dict(alpha_V=0.40, alpha_E=0.35,

beta_s=0.20, p_skip=0.50, seed=42)

)

\# Inspecao da inicializacao

ir = results\['init_result'\]

print(f'Inicializacao: V={ir.n_V}, IES={ir.n_IES}, IEC={ir.n_IEC}, IC={ir.n_IC}')

print(f'eta={ir.eta:.2f}, eta_E={ir.eta_E:.2f}')

\# Evolucao das metricas-chave

for m in results\['history'\]\[::50\]:

print(f'Gen {m.generation:3d}: FVR={m.fvr:.2%}, ERatio={m.eratio:.2%}, '

f'f2_viavel={m.avg_f2_feasible:.1f}, f2_IES={m.avg_f2_ies:.1f}')

\# ECD por geracao: diferenca entre f2 de IES e f2 de viaveis

\# Se avg_f2_ies &lt; avg_f2_feasible =&gt; mascaramento confirmado

ecd = \[m.avg_f2_feasible - m.avg_f2_ies for m in results\['history'\] if m.n_IES > 0\]

if ecd:

print(f'ECD medio: {sum(ecd)/len(ecd):.2f} (positivo = mascaramento presente)')

## **9.4 O que observar nos resultados**

Os seguintes fenomenos sao os mais relevantes para validar a base de implementacao e motivar a Fase 2:

- FVR ao longo das geracoes: o CDP deve aumentar a proporcao de viaveis progressivamente. Se FVR cair ou estagnar, ha bug na avaliacao ou no crossover.
- ECD positivo: avg_f2_IES < avg_f2_FEASIBLE ao longo das geracoes confirma empiricamente o mascaramento de objetivos. Este e o resultado mais importante desta fase.
- ERatio oscilante: sem o DIMO-E, a proporcao de IES deve oscilar de forma nao controlada. Isso motivara visualmente a necessidade do DIMO-E na Fase 2.
- Qualidade da frente de Pareto: n_pareto_feasible deve crescer ao longo das geracoes. Se ficar estagnado, ha problema de diversidade.
- Invariantes de representacao: check_invariants() deve passar em todos os individuos da populacao final. Se falhar, ha bug no crossover ou na reinserção de orfaos.

# **10\. Roteiro para a Fase 2: o que adicionar e onde**

Com a Fase 1 funcionando e validada, a transicao para o IAS-EVRP completo e incremental. Os componentes sao adicionados um a um, sem alterar o que ja existe.

## **10.1 Componentes a adicionar por modulo**

| **Componente**                           | **Modulo destino**                     | **Dependencias da Fase 1**                                             |
| ---------------------------------------- | -------------------------------------- | ---------------------------------------------------------------------- |
| EOC (Estimador de Objetivos Corrigidos)  | evaluator.py                           | deficient_segments (ja calculado pelo CI), inst.dist, inst.station_ids |
| ORPG (Reparo Parcial Guiado)             | operators.py                           | EOC, deficient_segments, insert_station                                |
| ORE estendido (folga energetica)         | operators.py (estende ore_fallback)    | energy_profile (ja calculado pelo CI)                                  |
| CrossoverEVRP com consciencia energetica | operators.py (substitui EVRPCrossover) | EOC, theta_insert                                                      |
| SIFO-E (selecao energia-consciente)      | algorithm.py (novo)                    | corrected_obj do EOC, cv_components, relacao <=\_ECD                   |
| DIMO-E (gestao de proporcoes)            | algorithm.py (novo)                    | inf_type, eta_E/eta_C/eta_T do InitResult, ORPG, ORE                   |
| Arquivo Elite IES                        | algorithm.py (novo)                    | corrected_obj do EOC, ORPG                                             |
| Busca local RE+SE+FRC                    | local_search.py (novo)                 | energy_profile, station_ids                                            |

## **10.2 O que nao muda**

- representation.py inteiro (Solution, Route, Visit, Segment, CVVector, SolutionMetadata, InfeasType, NodeType)
- instance.py inteiro (EVRPInstance, load_schneider)
- evaluator.py: compute_route_profile, classify_type, compute_objectives, PopulationStats, update_pop_stats, renormalize - permanentes
- initialization.py inteiro (incluindo InitResult com eta_E, eta_C, eta_T)
- metrics.py inteiro (GenerationMetrics, compute_generation_metrics)
- EVRPProblem.\_evaluate() - o calculo de F e G nao muda; apenas quem consome G muda

## **10.3 Sequencia recomendada de implementacao na Fase 2**

- Implementar e testar EOC isoladamente (unit test: f_hat >= f para solucoes IES).
- Implementar CrossoverEVRP com Fase 3 (theta_insert). Verificar garantia anti-IEC.
- Implementar ORPG e testar o pipeline IES -> viavel (unit test com RSE).
- Implementar ORE estendido com selecao por folga energetica.
- Implementar SIFO-E: relacao de dominancia <=\_ECD usando corrected_obj.
- Implementar DIMO-E com limiares gamma_E/gamma_C/gamma_T derivados do InitResult.
- Implementar Arquivo Elite IES e o pipeline completo.
- Adicionar busca local RE+SE+FRC sobre o arquivo externo.
- Rodar experimento comparativo: NSGA-II+CDP vs IAS-EVRP nas mesmas instancias e sementes.

_Documento gerado como especificacao tecnica da Fase 1 do IAS-EVRP._

_Coerente com: Cai et al. (2026) - CMOEA-IAS; Ou et al. (2024) - CEOA; Schneider et al. (2014) - EVRPTW benchmark._