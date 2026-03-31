**Guia de Implementação**

Decodificador · Calibração · Tuning de Parâmetros

_TCC - Comparação de Algoritmos Multi-objetivo no EVRPTW_

NSGA-II · MOEA/D · SMS-EMOA

# **Visão geral dos próximos passos**

Este documento descreve os três passos de implementação que precedem o experimento primário: a construção do decodificador, as execuções exploratórias para calibração do critério de parada e o processo de tuning de parâmetros dos algoritmos. Cada passo é apresentado com nível de detalhe suficiente para implementação direta, incluindo as decisões de design e suas justificativas no contexto da pesquisa.

| **Passo** | **Atividade**             | **Propósito**                                                             | **Saída**                                                 |
| --------- | ------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------------- |
| **1**     | Implementar decodificador | Converter permutação de clientes em vetor de objetivos \[f1, f2, f3\]     | Módulo decoder.py testado e validado                      |
| **2**     | Execuções exploratórias   | Determinar número de avaliações até estabilização do HV                   | Critério de parada fixado por classe de instância         |
| **3**     | Tuning de parâmetros      | Encontrar configuração ótima de cada algoritmo no conjunto de treinamento | Configuração fixa documentada para o experimento primário |

# **Passo 1 - Arquitetura do decodificador**

## **1.1 Papel e contrato do decodificador**

O decodificador é a interface entre os algoritmos evolucionários e o problema EVRPTW. Ele recebe uma permutação de clientes (o cromossomo) e devolve um vetor de três objetivos. Toda a lógica de roteamento, inserção de estações e avaliação de factibilidade fica encapsulada aqui, mantendo os algoritmos completamente agnósticos ao problema.

**Contrato formal:** Decode(π: permutação de n clientes) → \[f1, f2, f3\] ou \[∞, ∞, ∞\]. O retorno é determinístico - a mesma permutação sempre produz o mesmo vetor. Infeasibilidade é sinalizada por \[∞, ∞, ∞\] sem penalidade suave, pois os três algoritmos operam com dominância estrita e soluções infeasíveis são naturalmente eliminadas sem necessidade de tratamento especial.

**Decisão de design:** A determinismo é a propriedade mais crítica para o experimento: garante que diferenças nos resultados entre algoritmos são atribuíveis aos algoritmos, não a variação estocástica do decodificador.

## **1.2 Estrutura de três fases**

O decodificador executa três subrotinas em sequência. O fluxo de dados e as condições de retorno antecipado são:

FUNÇÃO Decode(π):

routes ← Split(π) // Fase 1: particionar por capacidade

se routes = INFEASÍVEL:

retornar \[∞, ∞, ∞\]

expanded ← \[\]

para cada route em routes: // Fase 2: inserir estações

result ← InsertStations(route)

se result = INFEASÍVEL:

retornar \[∞, ∞, ∞\]

expanded.append(result)

retornar Evaluate(expanded) // Fase 3: calcular objetivos

## **1.3 Fase 1 - Split (Prins simplificado)**

O Split usa programação dinâmica de partição com restrição de capacidade, adaptada de Prins (2004). A escolha pelo Prins simplificado - sem verificação de janelas de tempo no loop interno - reduz a complexidade de O(n³/6) para O(n²) sem comprometer a qualidade da partição, pois janelas de tempo serão verificadas por InsertStations em seguida.

**Nota:** Complexidade: O(n²) = 10.000 operações para n=100. O custo de distância incremental é mantido em O(1) por célula da tabela usando atualização incremental dentro do loop j.

FUNÇÃO Split(π):

// Inicialização da DP

V\[0\] ← 0 // custo mínimo para atender 0 clientes

V\[i\] ← ∞ para i = 1..n

P\[i\] ← -1 // predecessor no caminho ótimo

para i ← 1 até n:

carga ← 0

custo_rota ← dist\[depot\]\[π\[i\]\] // trecho depot→primeiro cliente

para j ← i até n:

carga ← carga + demand\[π\[j\]\]

se carga > C: quebrar // corte de capacidade

// Custo incremental: remove retorno anterior, adiciona trecho

// interno e novo retorno ao depot. O(1) por célula.

se j > i:

custo_rota ← custo_rota

\- dist\[π\[j-1\]\]\[depot\]

\+ dist\[π\[j-1\]\]\[π\[j\]\]

\+ dist\[π\[j\]\]\[depot\]

se V\[i-1\] + custo_rota < V\[j\]:

V\[j\] ← V\[i-1\] + custo_rota

P\[j\] ← i - 1

se V\[n\] = ∞: retornar INFEASÍVEL

// Reconstrução das rotas a partir da tabela de predecessores

routes ← \[\]

j ← n

enquanto j > 0:

i ← P\[j\] + 1

routes.prepend(\[π\[i\], ..., π\[j\]\])

j ← P\[j\]

retornar routes

## **1.4 Fase 2 - InsertStations**

InsertStations recebe uma lista de clientes (rota sem depot e sem estações) e produz a sequência completa com estações inseridas. A lógica é greedy com look-ahead de um passo: para cada segmento onde a bateria é insuficiente, seleciona a estação de menor score balanceado entre impacto em distância e impacto em makespan, verificando que o próximo cliente ainda é alcançável após a inserção.

**Decisão de design:** O critério balanceado é a decisão central desta subrotina. Usar apenas distância criaria viés sistemático em favor de f2, comprimindo a variação em f3 e distorcendo a geometria da frente de Pareto observada pelos algoritmos - o que comprometeria especialmente H2 e H3.

FUNÇÃO InsertStations(clientes):

rota ← \[depot\]

t ← 0 // tempo atual

bat ← Q // bateria atual

ant ← depot

para idx ← 0 até len(clientes) - 1:

dest ← clientes\[idx\]

prox ← clientes\[idx+1\] se idx+1 < len(clientes), senão depot

e_nec ← dist\[ant\]\[dest\] \* r

se bat ≥ e_nec: // viagem direta possível

t_arr ← t + travel\[ant\]\[dest\]

se t_arr > l\[dest\]: retornar INFEASÍVEL

t ← max(t_arr, e\[dest\]) + service\[dest\]

bat ← bat - e_nec

rota.append(dest)

senão: // precisa de estação

melhor_s ← nulo

melhor_score ← ∞

melhor_t ← ∞

melhor_bat ← -∞

para cada s em S \\ {S0}:

e1 ← dist\[ant\]\[s\] \* r

e2 ← dist\[s\]\[dest\] \* r

se e1 > bat: continuar // não alcança s

se e2 > Q: continuar // não sai de s até dest

t_s ← t + travel\[ant\]\[s\]

bat_s ← bat - e1

t_rec ← t_s + g \* (Q - bat_s)

t_dest ← t_rec + travel\[s\]\[dest\]

se t_dest > l\[dest\]: continuar

bat_dest ← Q - e2

t_out ← max(t_dest, e\[dest\]) + service\[dest\]

// Look-ahead: próximo nó ainda é alcançável?

se t_out + travel\[dest\]\[prox\] > l\[prox\]: continuar

// Critério balanceado com normalização relativa

// Evita que diferença de escala entre dist e tempo

// suprima um dos componentes silenciosamente.

// epsilon protege contra divisão por zero no início da rota.

desvio_dist ← dist\[ant\]\[s\] + dist\[s\]\[dest\] - dist\[ant\]\[dest\]

atraso_tempo ← t_dest - (t + travel\[ant\]\[dest\])

dist_acum ← max(dist_acumulada_rota, epsilon)

t_atual ← max(t, epsilon)

score ← (desvio_dist / dist_acum) + (atraso_tempo / t_atual)

se score < melhor_score:

melhor_score ← score

melhor_s ← s

melhor_t ← t_out

melhor_bat ← bat_dest

se melhor_s = nulo: retornar INFEASÍVEL

rota.append(melhor_s)

rota.append(dest)

t ← melhor_t

bat ← melhor_bat

dist_acumulada_rota ← dist_acumulada_rota + dist\[ant\]\[dest\]

ant ← dest

rota.append(depot)

retornar rota

## **1.5 Fase 3 - Evaluate**

Evaluate percorre as rotas expandidas e calcula os três objetivos. A única complexidade aqui é que o makespan é o máximo sobre todos os tempos de retorno ao depot - não a soma.

FUNÇÃO Evaluate(expanded_routes):

f1 ← len(expanded_routes) // número de veículos

f2 ← 0

retornos ← \[\] // tempo de retorno de cada rota

para cada rota em expanded_routes:

t ← 0

bat ← Q

ant ← depot

para cada p em rota\[1:\]: // exclui depot inicial

f2 ← f2 + dist\[ant\]\[p\]

t ← t + travel\[ant\]\[p\]

bat ← bat - dist\[ant\]\[p\] \* r

t ← max(t, e\[p\])

se p é estação de recarga:

t ← t + g \* (Q - bat)

bat ← Q

senão:

t ← t + service\[p\]

ant ← p

retornos.append(t) // t ao atingir o depot final

f3 ← max(retornos)

retornar \[f1, f2, f3\]

## **1.6 Pré-computação e condições de borda**

Antes de qualquer execução, calcular e armazenar as matrizes de distância e tempo de viagem para todos os pares de nós:

FUNÇÃO Precompute(instância):

para cada par (i, j) de nós (clientes + estações + depot):

dist\[i\]\[j\] ← sqrt((x\[i\]-x\[j\])² + (y\[i\]-y\[j\])²)

travel\[i\]\[j\] ← dist\[i\]\[j\] / v

// Verificar alcançabilidade básica (deve passar em toda instância Schneider)

para cada cliente c:

se dist\[depot\]\[c\] \* r > Q:

ERRO: 'cliente c inalcançável com bateria cheia'

se dist\[c\]\[depot\] \* r > Q:

ERRO: 'cliente c não consegue retornar ao depot'

Condições de borda que precisam de tratamento explícito na implementação:

- Epsilon para normalização: usar epsilon = 1e-6 nos denominadores de dist_acum e t_atual para proteger o início de rotas onde ambos são zero.
- S0 excluído do conjunto de estações candidatas: o nó S0 tem as mesmas coordenadas do depot D0. Inserir S0 no meio de uma rota é semanticamente incorreto - ele só aparece como depot de partida e retorno.
- Rota com um único cliente: tratada naturalmente pelo loop de InsertStations com len(clientes)=1. Verificar que o caso idx=0 com prox=depot funciona sem caso especial.
- V\[n\]=∞ no Split: sinaliza que nenhuma partição por capacidade é viável. Deve retornar INFEASÍVEL, não lançar exceção.

**Implementação:** Validação do decodificador: antes das execuções exploratórias, rodar o conjunto de validação (6 instâncias pequenas) com soluções ótimas conhecidas da literatura e verificar que os valores de f1 e f2 são compatíveis. f3 não tem referência publicada e será validado apenas por consistência interna.

## **1.7 Complexidade consolidada e integração com pymoo**

| **Subrotina**          | **Complexidade** | **Ops (n=100, \|S\|=21)** | **Gargalo**                        |
| ---------------------- | ---------------- | ------------------------- | ---------------------------------- |
| Split                  | O(n²)            | 10.000                    | Loop duplo da DP de partição       |
| InsertStations         | O(n × \|S\|)     | 4.200                     | Varredura de estações por segmento |
| Evaluate               | O(n)             | ~150                      | Percurso das rotas expandidas      |
| **Total por Decode()** | O(n² + n·\|S\|)  | ~14.350                   | Dominado pelo Split                |

No pymoo, o decodificador é integrado como método \_evaluate da classe Problem. A estrutura mínima necessária é:

class EVRPTWProblem(ElementwiseProblem):

def \__init_\_(self, instance):

super().\__init_\_(

n_var=instance.n_clients,

n_obj=3,

n_ieq_constr=0, # restrições tratadas internamente pelo decoder

xl=0,

xu=instance.n_clients - 1,

vtype=int # variáveis inteiras: índices da permutação

)

self.instance = instance

self.decoder = Decoder(instance)

def \_evaluate(self, x, out, \*args, \*\*kwargs):

\# x é um vetor de inteiros representando a permutação

f = self.decoder.decode(x)

out\['F'\] = f # \[f1, f2, f3\] ou \[inf, inf, inf\]

**Implementação:** pymoo trata permutações via operadores específicos (PermutationRandomSampling, OrderCrossover, InversionMutation). Esses operadores devem ser usados em todos os algoritmos para garantir que o espaço de busca é idêntico entre NSGA-II, MOEA/D e SMS-EMOA.

# **Passo 2 - Execuções exploratórias e calibração do critério de parada**

## **2.1 Objetivo e instâncias de calibração**

As execuções exploratórias têm um objetivo único: determinar, para cada classe de instância, o número de avaliações da função objetivo a partir do qual o hipervolume estabiliza. Esse número se torna o critério de parada fixo para todas as execuções do experimento primário e do tuning.

As instâncias de calibração são selecionadas como representantes de cada classe de tamanho e de cada regime de dificuldade, usando apenas o conjunto de validação e uma instância \_21 por tipo espacial:

| **Instância** | **Clientes** | **Classe**  | **Propósito**                                                             |
| ------------- | ------------ | ----------- | ------------------------------------------------------------------------- |
| c101C10       | 10           | C pequena   | Estimar tempo por run em instância pequena - upper bound de velocidade    |
| r102C15       | 15           | R média     | Verificar escalabilidade antes de instâncias grandes                      |
| c101_21       | 100          | C-1xx Tight | Instância principal de calibração - TW mais restritiva                    |
| r101_21       | 100          | R-1xx Tight | Verificar se avg_tw=10 produz frente trivial (risco F4)                   |
| r204_21       | 100          | R-2xx Loose | Instância de maior riqueza esperada de frente - lower bound de avaliações |

## **2.2 Protocolo de execução exploratória**

Para cada instância de calibração, executar os seguintes passos em sequência:

- Executar 5 runs independentes com o mesmo algoritmo (usar NSGA-II com parâmetros padrão como referência). Registrar o hipervolume a cada 500 avaliações até um teto de 500.000 avaliações ou 4 horas de CPU, o que ocorrer primeiro.
- Plotar as 5 curvas de HV ao longo das avaliações no mesmo gráfico. Identificar visualmente o ponto de estabilização: o número de avaliações a partir do qual nenhuma das 5 curvas cresce mais de 0,5% do HV final em nenhuma janela de 5.000 avaliações subsequentes.
- Calcular o critério de parada como: ponto de estabilização × 1,2 (margem de segurança de 20%). Arredondar para o múltiplo de 1.000 mais próximo.
- Se r101_21 produzir HV com variância < 0,1% entre runs desde as primeiras avaliações (frente trivial), substituir por r102_21 como representante de R-1xx Tight no experimento primário e documentar a substituição.

\# Estrutura do script de calibração (pseudocódigo Python/pymoo)

instancias_calibracao = \['c101C10', 'r102C15', 'c101_21', 'r101_21', 'r204_21'\]

N_RUNS = 5

MAX_EVALS = 500_000

REGISTRO_A_CADA = 500

para cada instancia em instancias_calibracao:

problema = EVRPTWProblem(instancia)

ref_point = None # calculado ao final sobre todos os runs

historicos = \[\] # uma lista de (evals\[\], hv\[\]) por run

para run em range(N_RUNS):

callback = HVCallback(ref_point, a_cada=REGISTRO_A_CADA)

resultado = minimize(

problema,

NSGA2(pop_size=100, ...),

termination=('n_eval', MAX_EVALS),

seed=SEEDS\[run\],

callback=callback,

verbose=False

)

historicos.append(callback.historico)

\# Após todos os runs: calcular ref_point e recomputar HV

\# ref_point = 1.1 × max(F) em cada objetivo sobre todos os runs

\# Plotar curvas e identificar ponto de estabilização

plotar_curvas_hv(instancia, historicos, ref_point)

criterio = calcular_criterio_parada(historicos, margem=1.2)

print(f'{instancia}: critério de parada = {criterio} avaliações')

## **2.3 Implementação do callback de hipervolume**

O pymoo permite registrar métricas durante a execução via callbacks. O callback de HV deve ser implementado com cálculo eficiente em 3D usando o algoritmo WFG, disponível no módulo pymoo.indicators.hv:

from pymoo.core.callback import Callback

from pymoo.indicators.hv import HV

class HVCallback(Callback):

def \__init_\_(self, ref_point, a_cada=500):

super().\__init_\_()

self.ref_point = ref_point

self.a_cada = a_cada

self.historico = \[\] # lista de (n_evals, hv_valor)

self.indicador = None

def notify(self, algorithm):

n_evals = algorithm.evaluator.n_eval

se n_evals % self.a_cada != 0: retornar

\# Filtrar soluções feasíveis (F < inf em todos os objetivos)

F = algorithm.pop.get('F')

feasible = F\[np.all(F < 1e10, axis=1)\]

se len(feasible) == 0: retornar

\# Na primeira chamada, inicializar o indicador com ref_point

se self.indicador é None:

self.indicador = HV(ref_point=self.ref_point)

hv_val = self.indicador.do(feasible)

self.historico.append((n_evals, hv_val))

**Atenção:** O ponto de referência para o callback exploratório é provisório: usar 1,1 × o pior valor observado nos primeiros 10.000 runs de cada instância. O ponto de referência definitivo para o experimento primário será calculado retrospectivamente sobre todos os runs de todos os algoritmos.

## **2.4 Interpretação dos resultados e decisões de saída**

As execuções exploratórias produzem quatro decisões concretas antes do experimento primário:

| **Decisão**                      | **Como determinada**                                                 |
| -------------------------------- | -------------------------------------------------------------------- |
| Critério de parada em avaliações | Máximo entre os critérios de todas as instâncias \_21 testadas × 1,2 |
| Substituição de r101_21          | Se variância do HV < 0,1% desde o início → substituir por r102_21    |
| Estimativa de tempo total        | Tempo médio por run em c101_21 × 1.674 execuções primárias           |
| Ponto de referência provisório   | 1,1 × max(F) por objetivo sobre todas as instâncias \_21 testadas    |

# **Passo 3 - Tuning de parâmetros dos algoritmos**

## **3.1 Princípio e escopo**

O tuning busca a configuração de parâmetros que maximiza a qualidade média das soluções (hipervolume médio) de cada algoritmo sobre o conjunto de treinamento. O resultado é uma configuração fixa por algoritmo, aplicada uniformemente em todas as 18 instâncias do experimento primário.

**Unidade de tuning:** por algoritmo, não por instância. Tuning por instância eliminaria o objeto de comparação da pesquisa ao entregar a cada algoritmo configuração otimizada com conhecimento prévio dos dados de teste.

**pop_size fixo em 100:** O tamanho de população é fixado em 100 para todos os algoritmos. Isso elimina uma variável de confundimento que não é de interesse experimental e garante que o custo computacional por geração é comparável entre os três algoritmos.

## **3.2 Conjunto de treinamento**

Seis instâncias de tamanho médio (C15), uma por célula do fatorial tipo espacial × série. Essas instâncias têm a mesma estrutura de restrições que as \_21 mas são computacionalmente acessíveis para a quantidade de configurações a testar:

| **Instância** | **Clientes** | **Representa** | **Razão da escolha**               |
| ------------- | ------------ | -------------- | ---------------------------------- |
| c103C15       | 15           | C-1xx          | TW intermediária em C clusterizado |
| c202C15       | 15           | C-2xx          | TW larga, capacidade alta em C     |
| r102C15       | 15           | R-1xx          | TW estreita em R aleatório         |
| r202C15       | 15           | R-2xx          | TW larga, capacidade alta em R     |
| rc103C15      | 15           | RC-1xx         | TW estreita em RC misto            |
| rc202C15      | 15           | RC-2xx         | TW larga em RC misto               |

**Decisão de design:** As instâncias de treinamento são distintas das 18 instâncias do experimento primário. Essa separação é fundamental: usar instâncias de teste para tuning contamina os resultados com conhecimento prévio dos dados que se quer avaliar.

## **3.3 Espaços de parâmetros**

Os parâmetros sujeitos a tuning são os específicos de cada algoritmo - excluindo pop_size, que é fixo. Os intervalos foram definidos com base na literatura para problemas combinatórios de porte médio:

**NSGA-II**

| **Parâmetro**           | **Valores candidatos**    | **Justificativa**                        |
| ----------------------- | ------------------------- | ---------------------------------------- |
| p_crossover (OX)        | \[0.7, 0.8, 0.9\]         | OX com pc alto é padrão para permutações |
| p_mutation (realocação) | \[0.05, 0.10, 0.20, 1/n\] | 1/n é o valor teórico; testar vizinhança |

**Total de configurações NSGA-II:** 3 × 4 = 12

**MOEA/D**

| **Parâmetro**        | **Valores candidatos** | **Justificativa**                                 |
| -------------------- | ---------------------- | ------------------------------------------------- |
| n_neighbors (T)      | \[10, 15, 20, 30\]     | Controla escopo da busca por vizinhança           |
| decomposition        | \[Tchebycheff, PBI\]   | Tchebycheff mais robusto para frentes irregulares |
| theta (só PBI)       | \[1, 3, 5\]            | Controla pressão de convergência vs diversidade   |
| prob_neighbor_mating | \[0.7, 0.9, 1.0\]      | Fração de reprodução dentro da vizinhança         |

**Total de configurações MOEA/D:** 4 × (1×3 + 1×3×3) = 4 × 12 = 48

**SMS-EMOA**

| **Parâmetro**           | **Valores candidatos**    | **Justificativa**           |
| ----------------------- | ------------------------- | --------------------------- |
| p_crossover (OX)        | \[0.7, 0.8, 0.9\]         | Mesmo raciocínio do NSGA-II |
| p_mutation (realocação) | \[0.05, 0.10, 0.20, 1/n\] | Mesmo raciocínio do NSGA-II |

**Total de configurações SMS-EMOA:** 3 × 4 = 12

**Total geral de configurações:** 12 + 48 + 12 = 72 configurações

## **3.4 Protocolo de tuning**

Para cada configuração de cada algoritmo:

- Executar 10 runs independentes em cada uma das 6 instâncias de treinamento, usando o critério de parada calibrado no Passo 2.
- Calcular o HV de cada run usando o ponto de referência calculado sobre todos os runs de todas as configurações daquele algoritmo naquela instância (calculado retrospectivamente após todos os runs).
- Calcular o HV médio por instância (média dos 10 runs). Calcular o HV médio global como média ponderada igualitária sobre as 6 instâncias.
- Selecionar a configuração com maior HV médio global como configuração definitiva do algoritmo.
- Em caso de empate (diferença < 0,1% entre configurações), preferir a de menor variância entre instâncias - configuração mais robusta.

\# Estrutura do script de tuning (pseudocódigo)

CONFIGS_NSGA2 = produto_cartesiano(\[0.7,0.8,0.9\], \[0.05,0.10,0.20,'1/n'\])

CONFIGS_MOEAED = produto_cartesiano(N_NEIGHBORS, DECOMP, THETA, PROB_NEIGH)

CONFIGS_SMSEMOA = produto_cartesiano(\[0.7,0.8,0.9\], \[0.05,0.10,0.20,'1/n'\])

N_RUNS_TUNING = 10

INSTANCIAS_TRAIN = \['c103C15','c202C15','r102C15','r202C15','rc103C15','rc202C15'\]

para algoritmo, configs em \[(NSGA2, CONFIGS_NSGA2), ...\]:

resultados = {} # config → {instancia → \[hv_run_1, ..., hv_run_10\]}

para config em configs:

resultados\[config\] = {}

para instancia em INSTANCIAS_TRAIN:

hvs = \[\]

para run em range(N_RUNS_TUNING):

res = minimize(

EVRPTWProblem(instancia),

algoritmo(\*\*config, pop_size=100),

termination=('n_eval', CRITERIO_PARADA),

seed=SEEDS\[run\]

)

hvs.append(hv_da_frente(res.F))

resultados\[config\]\[instancia\] = hvs

\# Calcular HV médio global por configuração

for config in configs:

hv_medios = \[mean(resultados\[config\]\[inst\]) for inst in INSTANCIAS_TRAIN\]

score\[config\] = mean(hv_medios)

melhor_config = argmax(score)

print(f'Melhor config {algoritmo.\__name_\_}: {melhor_config}')

print(f'HV médio global: {score\[melhor_config\]:.6f}')

## **3.5 Custo computacional do tuning**

| **Algoritmo** | **Configs** | **Runs total** | **Execuções** | **Obs.**                                |
| ------------- | ----------- | -------------- | ------------- | --------------------------------------- |
| NSGA-II       | 12          | 10             | 720           | 12 × 6 inst. × 10 runs                  |
| MOEA/D        | 48          | 10             | 2.880         | 48 × 6 inst. × 10 runs                  |
| SMS-EMOA      | 12          | 10             | 720           | 12 × 6 inst. × 10 runs                  |
| **Total**     | **72**      | -              | **4.320**     | Instâncias de 15 clientes: segundos/run |

Para instâncias de 15 clientes com o critério de parada calibrado para instâncias de 100, o tuning completo deve ser executado em poucas horas de CPU mesmo em hardware modesto. O MOEA/D, com 48 configurações, domina o custo e pode ser paralelizado trivialmente por configuração.

## **3.6 O que documentar e reportar**

O processo de tuning inteiro precisa estar documentado na dissertação com detalhe suficiente para reprodutibilidade. Os seguintes elementos são obrigatórios:

- Conjunto de treinamento completo (as seis instâncias e o motivo de escolha de cada uma).
- Espaço de parâmetros de cada algoritmo (todos os valores candidatos testados).
- Número de runs por configuração por instância (10) e critério de seleção da configuração vencedora.
- Tabela com HV médio global das top-5 configurações de cada algoritmo - para mostrar robustez da escolha e que pequenas variações de parâmetro não dominam os resultados.
- Configuração definitiva adotada para o experimento primário, com todos os valores explicitados.
- Sementes usadas no tuning (documentadas para reprodutibilidade, mas diferentes das sementes do experimento primário para evitar contaminação).

**Decisão de design:** Separação de sementes: usar um conjunto de sementes para o tuning (ex.: seeds 1001-1010 por run) e um conjunto separado para o experimento primário (seeds 1-31). Isso garante que nenhuma execução do tuning é idêntica a nenhuma execução do experimento primário.

## **3.7 Análise de sensibilidade paramétrica mínima**

Além de reportar a configuração vencedora, executar uma análise de sensibilidade parcial: variar cada parâmetro individualmente ao redor do valor ótimo enquanto os outros são fixados no ótimo. Isso verifica se a escolha é robusta ou se pequenas variações mudam substancialmente o resultado.

Critério de robustez: se a variação de ±1 nível em qualquer parâmetro mudar o HV médio global em menos de 1%, o algoritmo é robusto à escolha de parâmetros naquele intervalo. Se a variação for maior, declarar que o algoritmo é sensível ao parâmetro e discutir a implicação para a comparabilidade dos resultados.

# **Resumo - Ordem de execução e dependências**

Os três passos têm dependências sequenciais estritas. A ordem abaixo deve ser respeitada:

| **Seq.** | **Atividade**                                         | **Entrada necessária**             | **Saída que desbloqueia**                  |
| -------- | ----------------------------------------------------- | ---------------------------------- | ------------------------------------------ |
| **1a**   | Implementar decoder.py                                | Instâncias de Schneider carregadas | Todos os passos seguintes                  |
| **1b**   | Validar decodificador (conjunto de 6)                 | decoder.py funcional               | Confiança para calibração e tuning         |
| **2a**   | Execuções exploratórias (5 instâncias)                | decoder.py validado                | Critério de parada fixado                  |
| **2b**   | Decisão sobre r101_21 vs r102_21                      | Curvas de HV de r101_21            | Suite primária finalizada (18 instâncias)  |
| **3a**   | Grid search de tuning (72 configs × 6 inst × 10 runs) | Critério de parada do Passo 2      | Configuração definitiva por algoritmo      |
| **3b**   | Análise de sensibilidade paramétrica                  | Resultado do grid search           | Documentação de robustez das configurações |
| **→**    | **EXPERIMENTO PRIMÁRIO**                              | Passos 1-3 completos               | 18 inst × 3 alg × 31 runs → resultados     |

**Nota:** A única decisão que pode ser tomada antes de implementar o decodificador é a representação de solução - que já está definida como permutação de clientes com operadores OX e realocação. Todo o resto depende de ver o decodificador funcionando nas instâncias reais.