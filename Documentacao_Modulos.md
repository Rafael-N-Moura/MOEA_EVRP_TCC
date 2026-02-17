# Documentação Técnica: Módulos do Sistema EVRPTW-PR Multi-Objetivo

**Versão:** 1.0  
**Data:** 2024  
**Autor:** Sistema de Documentação Automática

---

## Índice

1. [Visão Geral da Arquitetura](#visão-geral-da-arquitetura)
2. [Módulo src/model.py](#módulo-srcmodelpy)
3. [Módulo src/parser.py](#módulo-srcparserpy)
4. [Módulo src/decoder.py](#módulo-srcdecoderpy)
5. [Módulo src/problem.py](#módulo-srcproblempy)
6. [Módulo main.py](#módulo-mainpy)
7. [Fluxo de Execução Completo](#fluxo-de-execução-completo)

---

## Visão Geral da Arquitetura

O sistema implementa uma arquitetura de **Simulação por Caixa Preta** (Black-Box Simulation), garantindo isolamento total entre:

- **Lógica de Otimização**: Algoritmos evolutivos (NSGA-II, MOEA/D) que manipulam genótipos
- **Lógica de Negócio**: Regras físicas do EVRPTW-PR (bateria, carga, janelas de tempo)

O fluxo de dados segue o padrão:
```
Genótipo (Permutação) → Decodificador → Fenótipo (Solução) → Objetivos (f1, f2)
```

---

## Módulo src/model.py

### Propósito

Define todas as estruturas de dados do sistema, incluindo classes imutáveis para dados estáticos e classes mutáveis para dados dinâmicos.

### Classes Principais

#### 1. `NodeType` (Enum)

Enumeração que define os tipos de nós no mapa:

```python
class NodeType(Enum):
    DEPOT = 'd'      # Depósito
    STATION = 'f'    # Estação de recarga
    CUSTOMER = 'c'   # Cliente
```

**Uso**: Categorização e validação de nós durante o parsing e processamento.

---

#### 2. `Node` (Frozen Dataclass)

Representa um ponto geográfico imutável no mapa.

**Atributos:**
- `id` (str): Identificador único (ex: "C1", "S0", "D0")
- `type` (NodeType): Tipo do nó (depot, station, customer)
- `x, y` (float): Coordenadas cartesianas
- `demand` (float): Demanda de carga (0 para depot/station)
- `ready_time` (float): Início da janela de tempo
- `due_date` (float): Fim da janela de tempo
- `service_time` (float): Tempo de serviço no nó

**Métodos:**
- `distance_to(other: Node) -> float`: Calcula distância euclidiana até outro nó

**Características:**
- **Imutável** (frozen=True): Garante integridade dos dados estáticos
- **Hashable**: Pode ser usado como chave em dicionários

**Exemplo de Uso:**
```python
customer = Node(
    id="C1",
    type=NodeType.CUSTOMER,
    x=41.0, y=49.0,
    demand=10.0,
    ready_time=36.0,
    due_date=46.0,
    service_time=10.0
)
distance = customer.distance_to(depot)
```

---

#### 3. `Context` (Dataclass)

Contexto global contendo o mapa completo e parâmetros físicos do problema.

**Atributos:**
- `depot` (Node): Nó do depósito
- `stations` (List[Node]): Lista de estações de recarga
- `customers` (List[Node]): Lista de clientes
- `nodes_dict` (Dict[str, Node]): Dicionário para acesso rápido por ID
- `battery_capacity` (float): Capacidade máxima da bateria (Q)
- `vehicle_capacity` (float): Capacidade máxima de carga (C)
- `consumption_rate` (float): Taxa de consumo de energia por unidade de distância (r)
- `recharge_rate` (float): Taxa de recarga (tempo por unidade de energia) (g)
- `velocity` (float): Velocidade média do veículo (v)

**Métodos:**
- `__post_init__()`: Constrói `nodes_dict` automaticamente após inicialização
- `get_node(node_id: str) -> Optional[Node]`: Busca nó por ID
- `get_nearest_station(from_node: Node) -> Node`: Encontra estação mais próxima

**Lógica de `get_nearest_station()`:**
1. Se não há estações, retorna o depósito (fallback)
2. Itera sobre todas as estações
3. Calcula distância euclidiana para cada uma
4. Retorna a estação com menor distância

**Exemplo de Uso:**
```python
context = Context(
    depot=depot_node,
    stations=[station1, station2, ...],
    customers=[customer1, customer2, ...],
    battery_capacity=62.14,
    vehicle_capacity=200.0,
    consumption_rate=1.0,
    recharge_rate=0.48,
    velocity=1.0
)

nearest = context.get_nearest_station(customer)
```

---

#### 4. `RouteStep` (Dataclass)

Registro detalhado de uma parada em uma rota (para auditoria e análise).

**Atributos:**
- `node` (Node): Nó visitado
- `arrival_time` (float): Tempo de chegada
- `departure_time` (float): Tempo de saída
- `battery_arrival` (float): Nível de bateria na chegada
- `battery_departure` (float): Nível de bateria na saída
- `recharge_amount` (float): Quantidade de energia recarregada (0 se não for estação)
- `load` (float): Carga do veículo após a parada

**Lógica de `__post_init__()`:**
- Se `battery_departure == 0.0` e `recharge_amount > 0.0`, calcula automaticamente:
  - `battery_departure = battery_arrival + recharge_amount`

**Uso**: Permite rastreabilidade completa de cada movimento do veículo.

---

#### 5. `Route` (Dataclass)

Representa uma rota completa de um único veículo.

**Atributos:**
- `vehicle_id` (int): Identificador do veículo
- `steps` (List[RouteStep]): Lista sequencial de paradas
- `total_distance` (float): Distância total percorrida

**Métodos:**
- `add_step(step: RouteStep)`: Adiciona um passo à rota e atualiza `total_distance`

**Lógica de `add_step()`:**
1. Adiciona o passo à lista
2. Se há mais de um passo, calcula distância entre o nó anterior e o atual
3. Adiciona essa distância a `total_distance`

---

#### 6. `Solution` (Dataclass)

Solução completa do problema EVRPTW-PR.

**Atributos:**
- `routes` (List[Route]): Lista de todas as rotas (uma por veículo)
- `total_vehicles` (int): Número total de veículos utilizados
- `total_distance` (float): Distância total de todas as rotas
- `is_feasible` (bool): Indica se a solução é viável (sem violações)
- `violations` (List[str]): Lista de mensagens de violação

**Métodos:**
- `__post_init__()`: Calcula `total_vehicles` e `total_distance` automaticamente
- `add_violation(message: str)`: Registra violação e marca solução como inviável

**Lógica de `__post_init__()`:**
```python
self.total_vehicles = len(self.routes)
self.total_distance = sum(route.total_distance for route in self.routes)
```

**Lógica de `add_violation()`:**
1. Define `is_feasible = False`
2. Adiciona mensagem à lista de violações

---

## Módulo src/parser.py

### Propósito

Responsável por ler e converter arquivos de instância Schneider (.txt) em objetos `Context` utilizáveis pelo sistema.

### Função Principal: `parse_instance(filepath: str) -> Context`

### Algoritmo de Parsing

#### Fase 1: Leitura e Sanitização

```python
1. Abre arquivo e lê todas as linhas
2. Para cada linha:
   - Remove espaços em branco (strip)
   - Ignora linhas vazias
   - Ignora linha de cabeçalho (que começa com "StringID")
3. Armazena linhas válidas em clean_lines
```

**Exemplo de linha ignorada:**
```
StringID   Type       x          y          demand     ReadyTime  DueDate    ServiceTime
```

---

#### Fase 2: Separação de Dados

```python
Para cada linha em clean_lines:
  Se linha contém padrão "/(número)/":
    → É linha de parâmetro
    Extrai valor numérico
    Identifica tipo de parâmetro:
      - "Q Vehicle fuel tank capacity" → battery_capacity
      - "C Vehicle load capacity" → vehicle_capacity
      - "r fuel consumption rate" → consumption_rate
      - "g inverse refueling rate" → recharge_rate
      - "v average Velocity" → velocity
  Senão:
    → É linha de nó
    Adiciona a node_lines
```

**Exemplo de linha de parâmetro:**
```
Q Vehicle fuel tank capacity /62.14/
```

**Regex utilizada:** `r'/([\d.]+)/'` - captura número entre barras

---

#### Fase 3: Parse de Nós

```python
Para cada linha em node_lines:
  1. Divide linha em partes (split por espaços)
  2. Valida: deve ter pelo menos 8 colunas
  3. Extrai dados:
     - node_id = parts[0]        # Ex: "C1", "S0"
     - node_type_str = parts[1]  # "d", "f", "c"
     - x = float(parts[2])
     - y = float(parts[3])
     - demand = float(parts[4])
     - ready_time = float(parts[5])
     - due_date = float(parts[6])
     - service_time = float(parts[7])
  
  4. Converte node_type_str para NodeType enum
  5. Cria objeto Node
  6. Categoriza:
     - Se DEPOT → adiciona a depot
     - Se STATION → adiciona a stations
     - Se CUSTOMER → adiciona a customers
```

**Exemplo de linha de nó:**
```
C1         c          41.0       49.0       10.0       36.0       46.0       10.0
```

---

#### Fase 4: Validação e Aplicação de Defaults

```python
1. Valida: depot não pode ser None
   Se None → raise ValueError

2. Aplica defaults se parâmetros não encontrados:
   - consumption_rate = 1.0 (se não especificado)
   - recharge_rate = 1.0 (se não especificado)
   - velocity = 1.0 (se não especificado)
   - battery_capacity = 0.0 (se não especificado - pode causar erro)
   - vehicle_capacity = 0.0 (se não especificado - pode causar erro)
```

---

#### Fase 5: Criação do Context

```python
Cria objeto Context com:
  - depot, stations, customers
  - Parâmetros físicos (com defaults aplicados)

O __post_init__ do Context constrói automaticamente nodes_dict
```

### Tratamento de Erros

- **Arquivo não encontrado**: Exceção de I/O padrão do Python
- **Depósito ausente**: `ValueError("Depósito não encontrado no arquivo")`
- **Formato inválido**: Linhas com menos de 8 colunas são ignoradas silenciosamente

### Exemplo de Uso

```python
from src import parse_instance

context = parse_instance("evrptw_instances/r101_21.txt")
print(f"Clientes: {len(context.customers)}")
print(f"Estações: {len(context.stations)}")
print(f"Capacidade bateria: {context.battery_capacity}")
```

---

## Módulo src/decoder.py

### Propósito

Implementa a **heurística construtiva** que transforma um genótipo (permutação de índices de clientes) em um fenótipo (solução completa com rotas).

Este é o **coração lógico** do sistema, onde todas as regras físicas do EVRPTW-PR são aplicadas.

### Função Principal: `decode(individual: List[int], context: Context) -> Solution`

### Algoritmo de Decodificação

#### Pré-processamento

```python
1. Mapeia índices do indivíduo para objetos Node:
   customer_nodes = []
   Para cada idx em individual:
     Se 0 <= idx < len(context.customers):
       Adiciona context.customers[idx] a customer_nodes
```

**Nota**: O indivíduo é uma permutação de índices (0 a n-1), não IDs de nós.

---

#### Inicialização

```python
1. Cria Solution vazia
2. Inicializa primeiro veículo:
   - current_vehicle = 1
   - current_route = Route(vehicle_id=1)
   - current_position = context.depot
   - current_battery = context.battery_capacity (bateria cheia)
   - current_load = 0.0
   - current_time = 0.0

3. Adiciona passo inicial (saída do depósito):
   - Cria RouteStep no depósito
   - arrival_time = 0.0
   - departure_time = 0.0
   - battery_arrival = battery_capacity
   - battery_departure = battery_capacity
```

---

#### Loop Principal: Processamento de Cada Cliente

Para cada `customer` em `customer_nodes`, executa três passos principais:

##### **Passo A: Verificação de Capacidade de Carga**

```python
Se current_load + customer.demand > context.vehicle_capacity:
  1. Retorna ao depósito:
     - Chama return_to_depot()
     - Adiciona passo de retorno à rota atual
     - Fecha rota atual (adiciona a solution.routes)
  
  2. Abre novo veículo:
     - current_vehicle += 1
     - Cria nova Route
     - Reseta estado:
       * current_position = depot
       * current_battery = battery_capacity (cheia)
       * current_load = 0.0
       * current_time = 0.0
  
  3. Adiciona passo inicial do novo veículo (saída do depósito)
```

**Lógica**: Se a carga atual mais a demanda do cliente exceder a capacidade, é necessário um novo veículo.

---

##### **Passo B: Verificação de Viabilidade Energética (Safety Buffer)**

Este é o passo mais complexo, garantindo que o veículo sempre tenha energia suficiente para chegar a uma estação ou depósito.

```python
1. Calcula energia necessária para ir ao cliente:
   distance_to_customer = current_position.distance_to(customer)
   battery_needed = distance_to_customer * context.consumption_rate
   battery_after_customer = current_battery - battery_needed

2. Encontra estação mais próxima do cliente:
   nearest_station = context.get_nearest_station(customer)
   distance_to_safety = customer.distance_to(nearest_station)
   battery_for_safety = distance_to_safety * context.consumption_rate

3. Teste de viabilidade:
   Se battery_after_customer < battery_for_safety:
     → PRECISA RECARREGAR ANTES
     
     a) Encontra estação mais próxima da posição atual:
        nearest_station_from_current = context.get_nearest_station(current_position)
     
     b) Verifica se consegue chegar à estação:
        Se current_battery < battery_needed_to_station:
          → Violação grave (registra, mas continua)
          current_battery = 0.0
        Senão:
          → Vai para a estação
          
          c) Calcula recarga necessária:
             - Distância da estação ao cliente
             - Energia necessária: estação→cliente + cliente→próxima estação
             - Recarga = max(0, energia_necessária - bateria_atual)
             - Limita pela capacidade máxima
          
          d) Calcula tempo de recarga:
             recharge_time = recharge_needed * context.recharge_rate
          
          e) Atualiza bateria:
             battery_after_recharge = current_battery + recharge_needed
          
          f) Cria RouteStep da estação:
             - arrival_time = current_time + travel_time
             - departure_time = arrival_time + recharge_time
             - battery_arrival = current_battery
             - battery_departure = battery_after_recharge
             - recharge_amount = recharge_needed
          
          g) Atualiza estado:
             current_position = nearest_station_from_current
             current_battery = battery_after_recharge
             current_time = departure_time
```

**Conceito de Safety Buffer**: O veículo deve sempre ter energia suficiente para chegar a uma estação ou depósito após visitar um cliente. Isso previne situações onde o veículo fica sem bateria no meio de uma rota.

---

##### **Passo C: Visita ao Cliente (com Verificação de Janelas de Tempo)**

```python
1. Calcula energia e tempo para chegar ao cliente:
   distance_to_customer = current_position.distance_to(customer)
   battery_needed = distance_to_customer * context.consumption_rate
   travel_time = distance_to_customer / context.velocity

2. Verifica bateria:
   Se current_battery < battery_needed:
     → Violação (registra, mas continua)
     current_battery = 0.0
   Senão:
     current_battery -= battery_needed

3. Calcula tempo de chegada:
   arrival_time = current_time + travel_time

4. Verificação de janela de tempo:
   Se arrival_time < customer.ready_time:
     → Espera até ready_time
     arrival_time = customer.ready_time
   
   Se arrival_time > customer.due_date:
     → Violação de janela de tempo
     Registra violação (mas mantém visita para penalização)

5. Calcula tempo de saída:
   departure_time = arrival_time + customer.service_time

6. Atualiza carga:
   current_load += customer.demand

7. Cria RouteStep do cliente:
   - arrival_time (ajustado se necessário)
   - departure_time
   - battery_arrival = current_battery
   - battery_departure = current_battery (não recarrega em cliente)
   - load = current_load

8. Atualiza estado:
   current_position = customer
   current_time = departure_time
```

**Tratamento de Violações**: Quando uma violação é detectada (janela de tempo, bateria insuficiente), ela é registrada mas a visita é mantida. Isso permite que o algoritmo evolutivo aprenda através de penalização.

---

#### Finalização

```python
1. Último veículo retorna ao depósito:
   - Chama return_to_depot()
   - Adiciona passo de retorno
   
2. Adiciona última rota à solução:
   solution.routes.append(current_route)

3. Recalcula métricas:
   solution.__post_init__()  # Calcula total_vehicles e total_distance
```

---

### Função Auxiliar: `return_to_depot(...)`

Adiciona passo de retorno ao depósito e fecha a rota.

**Algoritmo:**
```python
1. Calcula distância e energia necessária:
   distance_to_depot = current_position.distance_to(depot)
   battery_needed = distance_to_depot * context.consumption_rate

2. Verifica bateria:
   Se current_battery < battery_needed:
     → Violação (não consegue retornar)
     arrival_battery = 0.0
   Senão:
     arrival_battery = current_battery - battery_needed

3. Calcula tempo de viagem:
   travel_time = distance_to_depot / context.velocity
   arrival_time = current_time + travel_time

4. Cria RouteStep de retorno:
   - node = depot
   - arrival_time
   - departure_time = arrival_time (não fica no depósito)
   - battery_arrival = arrival_battery
   - battery_departure = arrival_battery
   - load = 0.0 (descarga completa)

5. Adiciona passo à rota
```

---

### Características Importantes

1. **Determinístico**: Dada a mesma permutação e contexto, sempre produz a mesma solução
2. **Construtivo**: Constrói solução incrementalmente, cliente por cliente
3. **Conservador**: Safety buffer garante que veículo sempre pode chegar a estação/depósito
4. **Tolerante a Violações**: Registra violações mas permite continuação (para aprendizado)

---

## Módulo src/problem.py

### Propósito

Adapta a lógica de negócio (decoder) à biblioteca de otimização Pymoo, implementando a interface `ElementwiseProblem`.

### Classe Principal: `EVRPTWProblem`

Herda de `pymoo.core.problem.ElementwiseProblem`, que avalia indivíduos um por vez (não em lote).

---

### Constantes de Penalização

```python
PENALTY_V = 100    # Penalidade para número de veículos
PENALTY_D = 10000  # Penalidade para distância
```

**Justificativa**: Valores grandes o suficiente para garantir que soluções inviáveis sejam sempre dominadas por soluções viáveis no NSGA-II.

---

### Método `__init__(self, context: Context)`

**Algoritmo:**
```python
1. Armazena context
2. Calcula número de clientes: n_customers = len(context.customers)
3. Chama super().__init__() com:
   - n_var = n_customers (número de variáveis = número de clientes)
   - n_obj = 2 (dois objetivos: veículos e distância)
   - n_constr = 0 (sem restrições explícitas)
   - xl = 0 (limite inferior)
   - xu = n_customers - 1 (limite superior)
   - elementwise_evaluation = True (avaliação individual)
```

**Interpretação**: Cada variável representa a posição de um cliente na permutação. O Pymoo gerará permutações de 0 a n-1.

---

### Método `_evaluate(self, x, out, *args, **kwargs)`

Este é o método chamado pelo Pymoo para avaliar cada indivíduo.

**Parâmetros:**
- `x`: Array numpy de shape (n_customers,) com permutação de índices
- `out`: Dicionário de saída do Pymoo (modificado in-place)

**Algoritmo:**
```python
1. Converte array numpy para lista de inteiros:
   individual = x.astype(int).tolist()
   Exemplo: [0, 5, 12, 1, ...] → índices dos clientes na ordem da permutação

2. Decodifica genótipo em fenótipo:
   solution = decode(individual, self.context)
   → Retorna Solution completa com rotas, métricas, viabilidade

3. Extrai objetivos:
   f1 = solution.total_vehicles  # Objetivo 1: Minimizar veículos
   f2 = solution.total_distance  # Objetivo 2: Minimizar distância

4. Aplica penalização se inviável:
   Se not solution.is_feasible:
     f1 = f1 + PENALTY_V
     f2 = f2 + PENALTY_D
   
   Justificativa: Garante dominância de soluções viáveis sobre inviáveis

5. Retorna objetivos:
   out["F"] = np.array([f1, f2])
```

**Formato de Saída:**
- `out["F"]`: Array numpy de shape (2,) com [f1, f2]
- Pymoo espera que objetivos sejam minimizados (menor é melhor)

---

### Integração com Pymoo

O Pymoo chama `_evaluate()` para cada indivíduo na população. O problema é configurado como:

- **Tipo**: Permutação (valores inteiros de 0 a n-1)
- **Objetivos**: 2 (multi-objetivo)
- **Avaliação**: Elementwise (um por vez, não em lote)

Os operadores genéticos (crossover, mutation) do Pymoo trabalham diretamente com os arrays numpy, e o `_evaluate()` converte para o formato esperado pelo decoder.

---

## Módulo main.py

### Propósito

Script principal que orquestra a execução dos algoritmos NSGA-II e MOEA/D, fornecendo interface de linha de comando e visualização.

---

### Função `run_nsga2(problem, n_gen=100, pop_size=100, verbose=True)`

Executa o algoritmo NSGA-II (Non-dominated Sorting Genetic Algorithm II).

**Parâmetros:**
- `problem`: Instância de `EVRPTWProblem`
- `n_gen`: Número de gerações
- `pop_size`: Tamanho da população
- `verbose`: Se True, exibe progresso durante execução

**Algoritmo:**
```python
1. Configura algoritmo NSGA-II:
   algorithm = NSGA2(
       pop_size=pop_size,
       sampling=PermutationRandomSampling(),  # Gera permutações aleatórias
       crossover=OrderCrossover(),             # Preserva ordem relativa (vital para VRP)
       mutation=InversionMutation(),           # Simula 2-opt local
       eliminate_duplicates=True               # Remove duplicatas
   )

2. Executa otimização:
   res = minimize(
       problem,
       algorithm,
       ('n_gen', n_gen),  # Critério de parada
       verbose=verbose,
       seed=1              # Semente para reprodutibilidade
   )

3. Calcula tempo de execução

4. Exibe estatísticas:
   - Tempo de execução
   - Número de soluções encontradas
   - Melhor f1 (veículos)
   - Melhor f2 (distância)

5. Retorna resultado (res)
```

**Características do NSGA-II:**
- Baseado em **dominância de Pareto**
- Usa **crowding distance** para diversidade
- **OrderCrossover**: Preserva ordem relativa dos clientes (importante para VRP)
- **InversionMutation**: Inverte subsequência (simula 2-opt)

---

### Função `run_moead(problem, n_gen=100, pop_size=100, n_partitions=99, verbose=True)`

Executa o algoritmo MOEA/D (Multi-Objective Evolutionary Algorithm based on Decomposition).

**Parâmetros:**
- `problem`: Instância de `EVRPTWProblem`
- `n_gen`: Número de gerações
- `pop_size`: Tamanho da população (ajustado automaticamente)
- `n_partitions`: Número de partições para direções de referência
- `verbose`: Se True, exibe progresso

**Algoritmo:**
```python
1. Gera direções de referência (Das-Dennis):
   ref_dirs = get_reference_directions("das-dennis", 2, n_partitions=n_partitions)
   → Gera direções uniformemente distribuídas no espaço objetivo
   → Número de direções = (n_partitions + 1) para 2 objetivos

2. Ajusta pop_size:
   actual_pop_size = len(ref_dirs)
   Se pop_size != actual_pop_size:
     Ajusta para corresponder ao número de direções
     (MOEA/D precisa de uma solução por direção)

3. Configura algoritmo MOEA/D:
   algorithm = MOEAD(
       ref_dirs,                    # Direções de referência
       n_neighbors=15,              # Número de vizinhos para reprodução
       prob_neighbor_mating=0.7,    # Probabilidade de acasalar com vizinho
       sampling=PermutationRandomSampling(),
       crossover=OrderCrossover(),
       mutation=InversionMutation()
   )

4. Executa otimização (mesmo padrão do NSGA-II)

5. Exibe estatísticas

6. Retorna resultado
```

**Características do MOEA/D:**
- Baseado em **decomposição**: Divide problema multi-objetivo em subproblemas escalarizados
- Cada direção de referência define um subproblema
- **Vizinhança**: Cada solução evolui considerando apenas seus vizinhos
- Excelente para problemas combinatórios como VRP

**Cálculo de Direções:**
- Para `n_partitions=99` e 2 objetivos: (99+1) = 100 direções
- Direções são pontos no espaço objetivo [0,1] x [0,1] uniformemente distribuídos

---

### Função `main()`

Função principal que processa argumentos de linha de comando e orquestra a execução.

**Argumentos Aceitos:**
- `instance` (obrigatório): Caminho para arquivo de instância
- `--algorithm`: Escolhe algoritmo ('nsga2', 'moead', 'both')
- `--n-gen`: Número de gerações (default: 100)
- `--pop-size`: Tamanho da população (default: 100)
- `--n-partitions`: Partições para MOEA/D (default: 99)
- `--no-verbose`: Desabilita saída verbose
- `--plot`: Gera gráfico de frente de Pareto

**Fluxo de Execução:**
```python
1. Parse de argumentos (argparse)

2. Carrega instância:
   context = parse_instance(args.instance)
   → Exibe informações da instância carregada

3. Cria problema:
   problem = EVRPTWProblem(context)

4. Executa algoritmos conforme escolha:
   Se 'nsga2' ou 'both':
     results['nsga2'] = run_nsga2(...)
   
   Se 'moead' ou 'both':
     results['moead'] = run_moead(...)

5. Visualização (se --plot):
   Cria gráfico Scatter com frentes de Pareto de ambos algoritmos
   Exibe gráfico interativo

6. Mensagem de conclusão
```

---

### Visualização

Se `--plot` for especificado, cria gráfico de dispersão (Scatter Plot) mostrando:

- **Eixo X**: f1 (número de veículos)
- **Eixo Y**: f2 (distância total)
- **Pontos**: Soluções não-dominadas encontradas
- **Legenda**: Diferencia NSGA-II e MOEA/D

**Interpretação**: Soluções no canto inferior esquerdo são melhores (menos veículos e menos distância).

---

## Fluxo de Execução Completo

### Exemplo: Execução de NSGA-II

```
1. Usuário executa:
   python main.py evrptw_instances/r101_21.txt --algorithm nsga2 --n-gen 50

2. main.py:
   a) Parse de argumentos
   b) Chama parse_instance("evrptw_instances/r101_21.txt")
   
3. parser.py:
   a) Lê arquivo
   b) Extrai nós e parâmetros
   c) Cria Context
   d) Retorna para main.py

4. main.py:
   a) Cria EVRPTWProblem(context)
   b) Chama run_nsga2(problem, n_gen=50, ...)

5. run_nsga2():
   a) Configura NSGA2 com PermutationRandomSampling
   b) Chama minimize(problem, algorithm, ...)

6. Pymoo (internamente):
   a) Gera população inicial (100 permutações aleatórias)
   b) Para cada geração:
      - Avalia cada indivíduo chamando problem._evaluate()
      - Aplica seleção, crossover, mutação
      - Atualiza população
   c) Após 50 gerações, retorna resultado

7. problem._evaluate() (chamado para cada indivíduo):
   a) Recebe array numpy: [0, 5, 12, 1, ...]
   b) Converte para lista: [0, 5, 12, 1, ...]
   c) Chama decode([0, 5, 12, 1, ...], context)

8. decoder.decode():
   a) Mapeia índices para objetos Node
   b) Executa heurística construtiva:
      - Para cada cliente na permutação:
        * Verifica capacidade
        * Verifica bateria (com safety buffer)
        * Visita cliente (verifica janelas)
      - Insere recargas quando necessário
      - Cria rotas
   c) Retorna Solution

9. problem._evaluate() (continuação):
   a) Extrai f1 (veículos) e f2 (distância)
   b) Aplica penalização se inviável
   c) Retorna [f1, f2] para Pymoo

10. Pymoo (continuação):
    a) Usa objetivos para classificar soluções
    b) Seleciona melhores para próxima geração
    c) Repete até n_gen gerações

11. run_nsga2():
    a) Exibe estatísticas finais
    b) Retorna resultado

12. main.py:
    a) Exibe mensagem de conclusão
    b) Se --plot, gera gráfico
```

---

### Diagrama de Fluxo de Dados

```
Arquivo .txt
    ↓
[parser.py] parse_instance()
    ↓
Context (depot, stations, customers, parâmetros)
    ↓
[main.py] EVRPTWProblem(context)
    ↓
[Pymoo] Gera população (permutações)
    ↓
[problem.py] _evaluate(individual)
    ↓
[decoder.py] decode(individual, context)
    ↓
Solution (routes, total_vehicles, total_distance, is_feasible)
    ↓
[problem.py] Extrai f1, f2 (aplica penalização se necessário)
    ↓
[Pymoo] Usa objetivos para evolução
    ↓
Resultado final (frente de Pareto)
```

---

## Considerações Finais

### Pontos Fortes da Arquitetura

1. **Separação de Responsabilidades**: Cada módulo tem responsabilidade única e bem definida
2. **Isolamento**: Lógica de otimização (Pymoo) completamente isolada da lógica de negócio (decoder)
3. **Extensibilidade**: Fácil adicionar novos algoritmos ou modificar regras de negócio
4. **Testabilidade**: Cada módulo pode ser testado independentemente
5. **Determinismo**: Decoder é determinístico (mesma entrada = mesma saída)

### Limitações Conhecidas

1. **Heurística Construtiva Simples**: Não usa otimização local avançada
2. **Safety Buffer Conservador**: Pode inserir recargas desnecessárias
3. **Sem Otimização de Rotas**: Não aplica 2-opt ou outras melhorias locais após construção
4. **Penalização Fixa**: Valores de penalização são hardcoded (podem não ser ótimos para todas instâncias)

### Possíveis Melhorias Futuras

1. **Otimização Local**: Aplicar 2-opt após decodificação
2. **Heurísticas Adaptativas**: Ajustar safety buffer baseado em histórico
3. **Penalização Adaptativa**: Calcular penalizações dinamicamente
4. **Paralelização**: Avaliar múltiplos indivíduos em paralelo
5. **Memória de Soluções**: Cachear soluções já avaliadas

---

**Fim da Documentação**
