**Design Experimental**

Comparação de Famílias de Algoritmos Multi-objetivo

no contexto do EVRPTW com três objetivos

NSGA-II · MOEA/D · SMS-EMOA

_Instâncias de Schneider - Documento de referência do TCC_

# **1\. Contextualização e escopo**

Este documento compila as decisões de design experimental para o TCC cujo objetivo é comparar o comportamento de três famílias de algoritmos evolucionários multi-objetivo - NSGA-II, MOEA/D e SMS-EMOA - aplicados ao Electric Vehicle Routing Problem with Time Windows (EVRPTW) formulado com três objetivos simultâneos. O benchmark utilizado é o conjunto de instâncias de Schneider, composto por 92 instâncias derivadas dos benchmarks clássicos de Solomon para VRTWs, adaptadas para incluir veículos elétricos com restrições de bateria e estações de recarga.

Cada seção apresenta não apenas a decisão tomada, mas o raciocínio que a fundamenta e as alternativas que foram consideradas e descartadas. Esse registro serve tanto como guia de implementação quanto como material de apoio para a redação da dissertação.

# **2\. Formulação do problema e objetivos**

## **2.1 O problema: EVRPTW**

O EVRPTW é uma extensão do VRPTW clássico na qual todos os veículos são elétricos. As restrições centrais do problema são três:

- Janelas de tempo: cada cliente deve ser atendido dentro de um intervalo \[ReadyTime, DueDate\]. A chegada antecipada implica espera; a chegada tardia é infeasível.
- Capacidade de carga: a soma da demanda dos clientes em uma rota não pode exceder a capacidade do veículo (parâmetro C).
- Autonomia de bateria: o veículo possui capacidade de bateria Q. A taxa de consumo é r (proporcional à distância) e a taxa de recarga inversa é g (tempo por unidade de energia). O modelo adota recarga total - ao visitar uma estação, o veículo recarrega até Q.

**Justificativa:** O modelo de recarga total é o padrão do benchmark de Schneider e foi mantido neste trabalho para compatibilidade com a literatura. Modelos de recarga parcial, embora mais realistas, exigiriam reformulação dos parâmetros das instâncias e impediriam a comparação direta com resultados publicados.

## **2.2 Objetivos de otimização**

A formulação tri-objetivo adotada é:

| **Objetivo** | **Nome**                   | **Definição e justificativa**                                                                                                                                                     |
| ------------ | -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **f1**       | Número de veículos         | Minimizar a frota utilizada. Objetivo inteiro com baixa cardinalidade (tipicamente 2-10 para instâncias grandes), cria estrutura de frente estratificada em camadas discretas.    |
| **f2**       | Distância total percorrida | Minimizar a soma das distâncias de todas as rotas. Equivalente ao consumo de energia com r=1 (padrão nas instâncias). Objetivo contínuo e bem distribuído.                        |
| **f3**       | Makespan                   | Minimizar o tempo de conclusão da última rota (instante em que o último veículo retorna ao depósito). Objetivo contínuo, diretamente afetado pela tightness das janelas de tempo. |

**Decisão:** Justificativa da combinação f1/f2/f3: os três objetivos têm tensões genuínas e não-triviais entre si no EVRPTW. Menos veículos (f1) implica rotas mais longas, aumentando distância (f2) e makespan (f3). Minimizar distância pode exigir espera em janelas de tempo, inflando o makespan. Minimizar makespan pode exigir desvios que aumentam a distância. Nenhum par de objetivos é redundante ou colapsa trivialmente.

**Alternativas descartadas para f3**

Durante o processo de design, o tempo total de recarga foi considerado como terceiro objetivo. Foi descartado por duas razões: (1) com recarga total, o tempo de recarga é proporcional ao número de paradas, tornando f3 altamente correlacionado com f2, o que degrada a frente de Pareto; (2) o tempo de recarga resulta em um objetivo inteiro de baixa cardinalidade similar a f1, sem acrescentar uma dimensão genuinamente nova ao espaço de objetivos.

O tempo total de espera foi considerado como alternativa ao makespan. A escolha pelo makespan se justifica por sua presença mais consolidada na literatura de VRPTW multi-objetivo e por capturar naturalmente o efeito das janelas de tempo sobre o tempo operacional total da frota.

# **3\. Caracterização do benchmark de Schneider**

## **3.1 Estrutura geral**

O benchmark contém 92 instâncias distribuídas em três tipos de distribuição espacial de clientes (C, R e RC), dois tamanhos de instância completos (100 clientes - série \_21) e um conjunto de instâncias pequenas e médias derivadas (5, 10 e 15 clientes - sufixos C5, C10 e C15). A tabela abaixo resume a distribuição:

| **Tipo espacial** | **XS (5 cli.)** | **S (10 cli.)** | **M (15 cli.)** | **L (100 cli.)** | **Total** |
| ----------------- | --------------- | --------------- | --------------- | ---------------- | --------- |
| C (clusterizado)  | 4               | 4               | 4               | 17               | **29**    |
| R (aleatório)     | 4               | 4               | 4               | 23               | **35**    |
| RC (misto)        | 4               | 4               | 4               | 16               | **28**    |
| **Total**         | **12**          | **12**          | **12**          | **56**           | **92**    |

## **3.2 Séries 1xx e 2xx: regimes operacionais distintos**

Dentro de cada tipo espacial, as instâncias são organizadas em duas séries que diferem fundamentalmente em três parâmetros simultâneos:

| **Parâmetro**    | **Série 1xx**          | **Série 2xx**           | **Diferença típica** |
| ---------------- | ---------------------- | ----------------------- | -------------------- |
| Capacidade (C)   | 200                    | 700-1000                | 3-5×                 |
| Bateria (Q)      | Menor (60-80)          | Maior (118-273)         | 2-4×                 |
| Taxa recarga (g) | Mais lenta (0.38-3.47) | Mais rápida (0.11-2.29) | até 10×              |
| Janelas de tempo | Mais estreitas         | Mais largas             | variável             |

**Limitação declarada:** Limitação declarada: as séries 1xx e 2xx não variam uma restrição por vez - alteram capacidade, bateria e janelas de tempo simultaneamente. Portanto, qualquer diferença de desempenho entre algoritmos observada entre as séries é atribuível ao regime operacional como um todo, não a uma restrição específica. Esse confundimento é inerente ao benchmark e deve ser declarado explicitamente na seção de limitações da dissertação.

## **3.3 Variação natural de janelas de tempo**

A variação de janelas de tempo dentro de cada série (mantendo os demais parâmetros aproximadamente fixos) é a única fonte isolada de variação de uma única restrição disponível nas instâncias originais. O quadro abaixo apresenta o intervalo de avg_tw (média da largura das janelas de tempo por instância) nas instâncias de 100 clientes:

| **Grupo** | **Instâncias** | **avg_tw mín.** | **avg_tw máx.** | **Razão máx./mín.** |
| --------- | -------------- | --------------- | --------------- | ------------------- |
| C-1xx     | 9              | 62,7            | 854,3           | 13,6×               |
| C-2xx     | 8              | 160,0           | 2492,7          | 15,6×               |
| R-1xx     | 12             | 10,0            | 153,7           | 15,4×               |
| R-2xx     | 11             | 127,6           | 783,7           | 6,1×                |
| RC-1xx    | 8              | 30,0            | 154,2           | 5,1×                |
| RC-2xx    | 8              | 120,0           | 716,9           | 6,0×                |

**Atenção:** Atenção: a amplitude absoluta de avg_tw é muito diferente entre grupos espaciais. O que é classificado como 'Loose' em R-1xx (avg_tw≈154) corresponde aproximadamente ao 'Tight' de C-1xx ou RC-2xx em termos absolutos. Comparações cruzadas de nível de TW entre tipos espaciais devem sempre referenciar valores absolutos, não apenas o nível relativo (Tight/Medium/Loose).

## **3.4 Estrutura de bateria por tipo espacial**

Uma nuance importante do benchmark é que a taxa de recarga inversa g varia sistematicamente entre tipos espaciais, independentemente da série:

- Instâncias C: g ∈ \[2,28; 3,47\] - recarga lenta; a bateria é a restrição mais ativa.
- Instâncias R e RC: g ∈ \[0,11; 0,49\] - recarga até 30 vezes mais rápida que em C; a bateria é substancialmente menos restritiva.

Isso significa que a distribuição espacial não é uma variável neutra em relação à restrição de bateria. Ao comparar algoritmos por tipo espacial, parte de qualquer diferença observada pode ser atribuída à estrutura de bateria, não à distribuição geográfica dos clientes. Esse efeito precisa ser discutido na análise dos resultados.

# **4\. Suíte de experimentos**

## **4.1 Estrutura do design**

O design experimental é um fatorial 3 × 2 × 3: tipo espacial (C, R, RC) × série/regime (1xx, 2xx) × nível de TW (Tight, Medium, Loose). Cada célula do fatorial é representada por uma instância de 100 clientes, resultando em 18 instâncias para o experimento primário.

**Decisão:** Justificativa do fatorial: as três dimensões correspondem diretamente às hipóteses de pesquisa. O tipo espacial testa H2 (geometria da frente e estrutura das rotas). A variação de TW testa H3 (velocidade de convergência e qualidade em diferentes níveis de restrição). A série 1xx vs 2xx testa H4 e Hnova (regime operacional e estrutura de camadas discretas da frente de Pareto).

A seleção de uma instância por célula é intencional: com 31 execuções por célula, o poder estatístico para detectar diferenças entre algoritmos já é adequado. Adicionar uma segunda instância por célula dobraria o orçamento computacional sem incremento proporcional no poder analítico.

## **4.2 Seleção das instâncias primárias**

Dentro de cada célula (grupo espacial × série), as instâncias foram ordenadas por avg_tw crescente. Os níveis Tight, Medium e Loose correspondem às instâncias nas posições aproximadas de 0%, 50% e 100% do intervalo de cada grupo, maximizando a separação entre os níveis:

| **Grupo**  | **Nível TW** | **Instância** | **avg_tw** | **Razão relativa ao Tight** |
| ---------- | ------------ | ------------- | ---------- | --------------------------- |
| **C-1xx**  | Tight        | **c101_21**   | 62,7       | baseline                    |
| **C-1xx**  | Medium       | **c108_21**   | 252,3      | 1 : 4,0                     |
| **C-1xx**  | Loose        | **c104_21**   | 854,3      | 1 : 13,6                    |
| **C-2xx**  | Tight        | **c201_21**   | 160,0      | baseline                    |
| **C-2xx**  | Medium       | **c207_21**   | 695,0      | 1 : 4,3                     |
| **C-2xx**  | Loose        | **c204_21**   | 2492,7     | 1 : 15,6                    |
| **R-1xx**  | Tight        | **r101_21**   | 10,0       | baseline                    |
| **R-1xx**  | Medium       | **r111_21**   | 98,0       | 1 : 9,8                     |
| **R-1xx**  | Loose        | **r108_21**   | 153,7      | 1 : 15,4                    |
| **R-2xx**  | Tight        | **r201_21**   | 127,6      | baseline                    |
| **R-2xx**  | Medium       | **r210_21**   | 429,9      | 1 : 3,4                     |
| **R-2xx**  | Loose        | **r208_21**   | 783,7      | 1 : 6,1                     |
| **RC-1xx** | Tight        | **rc101_21**  | 30,0       | baseline                    |
| **RC-1xx** | Medium       | **rc107_21**  | 94,7       | 1 : 3,2                     |
| **RC-1xx** | Loose        | **rc104_21**  | 154,2      | 1 : 5,1                     |
| **RC-2xx** | Tight        | **rc201_21**  | 120,0      | baseline                    |
| **RC-2xx** | Medium       | **rc207_21**  | 382,0      | 1 : 3,2                     |
| **RC-2xx** | Loose        | **rc204_21**  | 716,9      | 1 : 6,0                     |

## **4.3 Conjunto de validação**

Além do experimento primário, um conjunto de seis instâncias menores é utilizado exclusivamente para validação de implementação - verificar que os algoritmos produzem soluções corretas (sem violação de restrições) e que os valores de função objetivo são compatíveis com os reportados na literatura para as instâncias de Schneider. Para o conjunto de validação, 5 execuções por algoritmo são suficientes.

| **Tipo espacial** | **Tamanho** | **Instância** | **Propósito**                                 |
| ----------------- | ----------- | ------------- | --------------------------------------------- |
| C                 | 10 clientes | **c101C10**   | Verificar rotas clusterizadas com TW apertada |
| C                 | 15 clientes | **c106C15**   | Verificar C com TW média, frota maior         |
| R                 | 10 clientes | **r102C10**   | Verificar rotas aleatórias com TW apertada    |
| R                 | 15 clientes | **r102C15**   | Verificar R com amostra maior de clientes     |
| RC                | 10 clientes | **rc102C10**  | Verificar topologia mista com TW apertada     |
| RC                | 15 clientes | **rc103C15**  | Verificar RC com TW intermediária             |

## **4.4 Análise estendida (opcional)**

As 56 instâncias grandes (todas as \_21) podem ser utilizadas como análise estendida para verificar se os resultados das 18 instâncias primárias generalizam. Para a análise estendida recomenda-se reduzir o número de execuções para 15 (em vez de 31), o que reduz o custo de 5.208 para aproximadamente 2.520 execuções adicionais, mantendo poder estatístico suficiente para detectar concordância ou divergência com o experimento primário.

## **4.5 Orçamento computacional**

O orçamento total do experimento primário é calculado abaixo. O tempo de execução por run deve ser calibrado empiricamente antes de fixar o critério de parada (ver seção 6.2):

| **Experimento**     | **Execuções** | **1 min/run** | **3 min/run** | **5 min/run** |
| ------------------- | ------------- | ------------- | ------------- | ------------- |
| Primário (18×3×31)  | 1.674         | 27,9 h        | 83,7 h        | 139,5 h       |
| Validação (6×3×5)   | 90            | < 1 h         | < 5 h         | < 8 h         |
| Estendida (56×3×15) | 2.520         | 42,0 h        | 126,0 h       | 210,0 h       |

**Atenção:** Ação necessária antes de fixar o design: executar 5 rodadas exploratórias de qualquer um dos algoritmos em c101_21 e medir o tempo até a estabilização do hipervolume. Esse número ancora o critério de parada e todo o planejamento de cronograma.

# **5\. Hipóteses de pesquisa**

## **5.1 Fundamento teórico das diferenças entre famílias**

As hipóteses são construídas a partir das diferenças estruturais documentadas entre os algoritmos, não de resultados esperados ad hoc. O raciocínio causal de cada hipótese é explicitado para que cada hipótese seja testável e, idealmente, refutável.

| **Algoritmo** | **Mecanismo de seleção**                                                                                              | **Fraqueza estrutural conhecida**                                                                                                                                         |
| ------------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| NSGA-II       | Dominância de Pareto + crowding distance para diversidade. Operação geracional.                                       | Em 3+ objetivos, a fração não-dominada da população cresce rapidamente, enfraquecendo a pressão seletiva. Crowding distance em 3D é estimador de densidade menos preciso. |
| MOEA/D        | Decomposição em subproblemas escalares via vetores de peso. Cada subproblema é resolvido com referência à vizinhança. | Vetores de peso uniformes pressupõem frente de forma regular e convexa. Em frentes irregulares, côncavas ou com regiões esparsas, vetores são desperdiçados.              |
| SMS-EMOA      | Seleção steady-state por contribuição ao hipervolume. Não pressupõe forma da frente.                                  | Convergência mais lenta nas fases iniciais (hipervolume de população aleatória é pouco discriminativo). Custo de cálculo da contribuição em 3D é O(n log n) por geração.  |

## **5.2 Hipóteses**

**H1 - Pressão de seleção em três objetivos (hipótese principal)**

**Enunciado:** Em instâncias grandes (L=100) com três objetivos, NSGA-II produzirá hipervolume final inferior ao SMS-EMOA e ao MOEA/D, porque a fração não-dominada da população cresce a ponto de anular a pressão seletiva.

**Mecanismo causal:** com n=100 soluções em espaço tridimensional de objetivos, a probabilidade de dominância decresce rapidamente e a maioria das soluções acaba na primeira camada de não-dominância, tornando o ranking por dominância não-discriminativo. O crowding distance compensa parcialmente, mas é um estimador de densidade menos preciso em 3D do que em 2D.

**Testabilidade:** hipótese diretamente testável pelo hipervolume médio das 18 instâncias primárias via teste de Friedman com post-hoc de Nemenyi.

**Dimensão coberta:** todas as instâncias primárias.

**H2 - Regularidade da frente e tipo espacial**

**Enunciado:** Instâncias C (clusterizadas) produzem frentes de Pareto mais regulares e convexas, favorecendo MOEA/D. Instâncias R (aleatórias) produzem frentes mais irregulares, favorecendo SMS-EMOA. Instâncias RC apresentam comportamento intermediário.

**Mecanismo causal:** em instâncias C, as rotas ótimas têm comprimentos mais equilibrados entre si devido ao agrupamento geográfico, tornando makespan e distância mais proporcionais e produzindo frentes de geometria mais suave. Em instâncias R, desequilíbrios entre rotas são mais prováveis (um veículo pode ter rota muito mais longa que os outros), criando descontinuidades na frente f2-f3. MOEA/D com vetores uniformes é mais eficiente em frentes regulares; SMS-EMOA se adapta melhor a frentes irregulares por não pressupor sua forma.

**Testabilidade:** hipótese verificável comparando hipervolume por tipo espacial. Requer análise complementar da forma das frentes obtidas para confirmar a regularidade diferencial.

**Dimensão coberta:** C vs R vs RC (colunas do fatorial).

**H3 - Tightness de janelas de tempo e convergência**

**Enunciado:** Em instâncias com TW muito apertada (Tight), o espaço de soluções feasíveis é pequeno e MOEA/D converge mais rapidamente para a frente factível do que NSGA-II ou SMS-EMOA. Em TW larga (Loose), o espaço factível é rico, a diversidade importa mais do que a convergência rápida, e SMS-EMOA recupera vantagem.

**Mecanismo causal TW apertada:** com poucas soluções feasíveis, a pressão de factibilidade domina a busca. A estrutura de vizinhança da decomposição do MOEA/D guia a busca eficientemente no espaço feasível reduzido. NSGA-II perde potência porque a seleção por dominância é pouco discriminativa em populações majoritariamente infeasíveis. SMS-EMOA sofre nas fases iniciais porque o hipervolume de uma população com poucas soluções feasíveis é pouco informativo.

**Mecanismo causal TW larga:** com espaço feasível amplo, o MOEA/D com vetores uniformes pode subutilizar regiões da frente com geometria irregular. SMS-EMOA, ao adaptar a cobertura via hipervolume, distribui soluções de forma mais eficiente.

**Testabilidade:** comparação cruzada de hipervolume nos três níveis de TW dentro de cada grupo. Complementarmente, análise das curvas de convergência ao longo das avaliações pode discriminar velocidade de convergência nas fases iniciais.

**Dimensão coberta:** Tight vs Medium vs Loose (linhas do fatorial).

**H4 - Regime operacional e curvatura da frente**

**Enunciado:** No regime 1xx (muitos veículos, rotas curtas), os objetivos f1 e f2 têm correlação mais forte, tendendo a 'achatar' a frente em uma dimensão. No regime 2xx, os três objetivos têm tensão mais equilibrada. MOEA/D terá mais dificuldade no regime 1xx (vetores desperdiçados na dimensão achatada) enquanto SMS-EMOA se adapta melhor a ambos.

**Classificação:** hipótese exploratória. O confundimento de variáveis entre séries impede atribuição causal precisa. O argumento da geometria da frente é verificável como análise secundária - se as frentes obtidas mostrarem achatamento sistemático no regime 1xx, a explicação ganha credibilidade.

**Dimensão coberta:** série 1xx vs série 2xx (colunas internas do fatorial).

**Hnova - Estrutura estratificada da frente e cobertura por camadas**

**Enunciado:** A combinação de f1 inteiro (número de veículos) com f2 e f3 contínuos cria uma frente estratificada em camadas - para cada valor de f1, existe uma sub-frente contínua no plano f2-f3. SMS-EMOA produzirá melhor cobertura das camadas de baixo número de veículos (alto valor de hipervolume marginal) do que MOEA/D ou NSGA-II.

**Mecanismo causal:** MOEA/D com vetores uniformes aloca vetores proporcionalmente ao volume - camadas com maior extensão em f2-f3 recebem mais vetores e camadas pequenas ficam sub-representadas. NSGA-II calcula crowding distance entre soluções de camadas diferentes de f1, o que gera distâncias artificialmente grandes sem correspondência com a esparsidade real da frente. SMS-EMOA, ao maximizar contribuição ao hipervolume de forma adaptativa, concentra esforço naturalmente nas regiões de maior contribuição, independentemente da estrutura de camadas.

**Testabilidade:** verificável analisando a distribuição de soluções por valor de f1 nas frentes obtidas por cada algoritmo - sem custo adicional de execuções. Mais pronunciada em instâncias R-2xx e RC-2xx, onde a variação no número ótimo de veículos é maior.

**Dimensão coberta:** todas as instâncias primárias, com foco nas séries 2xx.

# **6\. Protocolo estatístico**

## **6.1 Indicadores de desempenho**

**Hipervolume (HV) - indicador primário**

Mede o volume do espaço de objetivos dominado pela frente aproximada em relação a um ponto de referência. Captura simultaneamente convergência e diversidade num único escalar. É o indicador mais informativo para comparação de algoritmos em problemas com três objetivos e possui propriedades teóricas estabelecidas - maximizar hipervolume é equivalente a encontrar a frente de Pareto verdadeira sob condições suaves.

Definição do ponto de referência: vetor calculado por instância como 110% do pior valor observado em cada objetivo ao longo de todas as execuções de todos os algoritmos naquela instância. O cálculo é retrospectivo e aplicado de forma idêntica para todos os algoritmos. Um ponto de referência diferente por algoritmo ou por execução invalida a comparação.

**IGD+ (Inverted Generational Distance Plus) - indicador secundário**

Mede a distância média das soluções de uma frente de referência até a frente aproximada, penalizando convergência e diversidade de forma assimétrica correta. A frente de referência é construída como a união de todas as soluções não-dominadas encontradas por todos os algoritmos em todas as execuções de uma mesma instância. IGD+ é preferível ao IGD clássico por ser compatível com a dominância de Pareto e mais robusto a frentes de formas irregulares.

**Justificativa:** Indicadores não recomendados como primários: spread e spacing capturam apenas diversidade e são insensíveis à posição da frente no espaço de objetivos. Dois algoritmos podem ter spread idêntico com frentes em regiões completamente diferentes do espaço.

## **6.2 Número de execuções e critério de parada**

Número de execuções: 31 execuções independentes por algoritmo por instância no experimento primário. O valor 31 garante graus de liberdade suficientes para o teste de Wilcoxon detectar diferenças com tamanho de efeito médio a α=0,05. Cada execução utiliza uma semente aleatória distinta e pré-definida (documentada para reprodutibilidade).

Critério de parada: número máximo de avaliações da função objetivo - não tempo de parede. O uso de tempo como critério favorece a implementação mais eficiente em detrimento do algoritmo mais capaz, introduzindo viés de implementação. O número de avaliações deve ser idêntico para os três algoritmos em cada instância.

**Calibração:** executar 5 rodadas exploratórias de um dos algoritmos em c101_21 (instância representativa de tamanho L). Plotar a curva de hipervolume ao longo das avaliações. O critério de parada adequado é quando a curva estabilizar, acrescido de uma margem de segurança de 20%. Valores típicos na literatura para instâncias de 100 clientes situam-se entre 100.000 e 300.000 avaliações, mas a calibração específica para a representação e operadores utilizados é obrigatória.

## **6.3 Testes estatísticos**

**Comparação múltipla entre os três algoritmos**

- Teste de Friedman: equivalente não-paramétrico da ANOVA para medidas repetidas. Hipótese nula: as medianas dos indicadores são iguais para os três algoritmos. Referência metodológica: Demšar (2006), framework padrão para comparação de múltiplos algoritmos em múltiplas instâncias.
- Post-hoc de Nemenyi: identifica quais pares de algoritmos diferem significativamente após rejeição da hipótese nula do Friedman.

**Comparação pareada entre dois algoritmos**

- Teste de Wilcoxon signed-rank (não-paramétrico, amostras pareadas): adequado porque hipervolume de metaheurísticas raramente segue distribuição normal. Mais potente que Mann-Whitney para comparações pareadas. Nível de significância: α = 0,05.

**Controle de múltiplos testes**

- Correção de Holm-Bonferroni: aplicada ao conjunto de todos os testes pareados realizados. Uniformemente mais potente que a correção de Bonferroni simples, mantendo o controle da taxa de erro familiar (FWER).

**Tamanho de efeito**

- Estatística A12 de Vargha-Delaney: mede a probabilidade de que uma execução aleatória do algoritmo A produza resultado melhor que uma execução aleatória do algoritmo B. Interpretação: A12 > 0,71 = efeito grande; A12 > 0,64 = médio; A12 > 0,56 = pequeno. Reportar junto com p-valores para separar significância estatística de relevância prática.

**Justificativa:** Motivação para reportar tamanho de efeito: com 31 execuções, é possível obter significância estatística para diferenças minúsculas e praticamente irrelevantes entre algoritmos. O A12 complementa o p-valor, indicando se a diferença detectada é operacionalmente relevante.

## **6.4 Configuração de parâmetros dos algoritmos**

Os parâmetros dos algoritmos serão configurados com os valores padrão reportados nos respectivos artigos originais. Isso é suficiente para um TCC e evita o custo e a complexidade de um procedimento de tuning automático (como irace ou SMAC). Os seguintes parâmetros devem ser explicitados na seção de metodologia da dissertação:

- Tamanho da população: 100 indivíduos para todos os algoritmos (compatibilidade de comparação).
- NSGA-II: probabilidade de crossover, probabilidade de mutação, parâmetro de distribuição do SBX e da mutação polinomial (valores típicos: pc=0,9; pm=1/n; ηc=20; ηm=20).
- MOEA/D: número de vetores de peso (igual ao tamanho da população = 100); tamanho da vizinhança T=20; método de geração de vetores de peso (Simplex Lattice Design para 3 objetivos).
- SMS-EMOA: parâmetros herdados do NSGA-II para operadores genéticos; seleção steady-state por contribuição mínima ao hipervolume (algoritmo WFG para cálculo em 3D).

## **6.5 Requisitos de reprodutibilidade**

Para que os resultados sejam verificáveis por outros pesquisadores, os seguintes dados devem ser documentados e, idealmente, disponibilizados em repositório público:

- Sementes aleatórias de cada execução (ou gerador e estado inicial).
- Valores exatos de todos os parâmetros de cada algoritmo.
- Hardware utilizado (CPU, RAM, sistema operacional) para contextualização do tempo de execução.
- Ponto de referência utilizado no cálculo do hipervolume, por instância.
- Frente de referência utilizada no cálculo do IGD+, por instância.
- Código-fonte das implementações dos três algoritmos.

# **7\. Análise crítica do design**

Esta seção apresenta uma avaliação crítica do design experimental descrito nas seções anteriores, identificando fragilidades residuais, riscos e recomendações de mitigação. A análise é feita na perspectiva de um revisor externo ou banca examinadora.

## **7.1 Pontos sólidos do design**

- O fatorial 3×2×3 cobre as dimensões relevantes de forma balanceada e conectada às hipóteses. Cada hipótese tem pelo menos uma dimensão do fatorial diretamente associada.
- A escolha de indicadores (HV primário + IGD+ secundário) é metodologicamente robusta e alinhada com a prática corrente da área.
- O protocolo estatístico (Friedman + Nemenyi + Wilcoxon + Holm-Bonferroni + A12) cobre os três níveis de análise necessários: comparação múltipla, comparação pareada e tamanho de efeito.
- A separação entre experimento primário (18 instâncias) e análise estendida (56 instâncias) equilibra rigor com viabilidade de TCC.
- A limitação do confundimento nas séries 1xx/2xx está declarada explicitamente, o que é mais forte metodologicamente do que ignorá-la.

## **7.2 Fragilidades residuais e mitigações**

**F1 - Uma instância por célula do fatorial**

O design usa uma única instância por célula do fatorial. Se uma instância for atípica (um outlier no espaço de dificuldade do grupo), os resultados daquela célula serão não-representativos e isso não será detectável sem repetição. Com 31 runs do mesmo algoritmo na mesma instância, você captura a variância estocástica do algoritmo mas não a variância entre instâncias de mesma dificuldade.

**Atenção:** Mitigação: a análise estendida com as 56 instâncias cumpre exatamente esse papel - permite verificar se os resultados das 18 instâncias primárias generalizam. Se o orçamento computacional permitir, adicionar uma segunda instância por célula no experimento primário fortaleceria consideravelmente o design. Alternativamente, reportar explicitamente essa limitação na dissertação e usar a análise estendida como argumento de generalidade.

**F2 - Desequilíbrio de amplitude absoluta de TW entre grupos**

O nível 'Loose' de R-1xx (avg_tw≈154) tem valor absoluto similar ao 'Tight' de C-1xx (avg_tw≈63 a 188). Isso significa que 'Loose' em R-1xx não é comparável a 'Loose' em C-1xx em termos de dificuldade absoluta. Se os resultados forem apresentados por nível de TW sem essa ressalva, a análise será enganosa.

**Atenção:** Mitigação: (1) na análise dos resultados, apresentar sempre os valores absolutos de avg_tw ao lado dos níveis categóricos; (2) não fazer comparações do tipo 'algoritmo X supera Y em instâncias Loose' sem especificar o grupo espacial; (3) considerar normalizar os níveis de TW por alguma métrica de dificuldade relativa (por exemplo, razão entre avg_tw e o horizonte total de tempo da instância) para comparações cruzadas. Essa normalização não é trivial mas aumentaria a comparabilidade.

**F3 - Ausência de análise de correlação entre objetivos**

As hipóteses H2 e H4 dependem da geometria da frente de Pareto (regularidade, achatamento, presença de descontinuidades). O design atual não inclui nenhuma análise preliminar da correlação entre os objetivos nas instâncias selecionadas. Se f2 e f3 forem altamente correlacionados em todas as instâncias, a frente será quase bidimensional independentemente do tipo espacial ou regime, e H2 e H4 perderão poder discriminativo.

**Atenção:** Mitigação: antes de iniciar o experimento principal, executar uma análise exploratória de correlação entre f1, f2 e f3 numa amostra das instâncias selecionadas (5-10 runs exploratórios por instância são suficientes). Se a correlação f2-f3 for alta (|r| > 0,85) em um grupo específico, ajustar a seleção de instâncias ou declarar a limitação antecipadamente.

**F4 - Risco de frentes de Pareto vazias ou triviais em instâncias Tight**

Instâncias com TW muito apertada (especialmente r101_21 com avg_tw=10,0) podem ter um espaço feasível tão restrito que todos os algoritmos convergem para a mesma frente ou para soluções muito similares. Nesse caso, as 31 execuções produzirão distribuições de HV idênticas e os testes estatísticos não terão o que medir.

**Atenção:** Mitigação: incluir r101_21 nas execuções exploratórias de calibração. Se a frente obtida for trivial (poucas soluções não-dominadas ou hipervolume com variância próxima de zero entre execuções), considerar substituir por r102_21 (avg_tw=56,5) como 'Tight' para R-1xx, que ainda representa TW apertada mas com maior riqueza de frente. A seleção atual de r101_21 foi baseada em maximizar a separação dos níveis - se isso comprometer a riqueza da frente, o critério de seleção deve ser revisado.

**F5 - Falta de hipótese de framing teórico explícito para MOEA/D vs SMS-EMOA**

H1 prediz que NSGA-II será inferior aos outros dois, mas não há hipótese explícita sobre o ordenamento esperado entre MOEA/D e SMS-EMOA. Se os resultados mostrarem MOEA/D ≈ SMS-EMOA, não haverá base teórica para discutir por que isso ocorre. Sem essa hipótese, metade da comparação principal fica sem ancoragem teórica.

**Justificativa:** Mitigação: as hipóteses H2 e H3 já estabelecem predições sobre quando MOEA/D ou SMS-EMOA devem ter vantagem (C vs R para H2; Tight vs Loose para H3). Essas predições implicitamente postulam que MOEA/D > SMS-EMOA em instâncias C-Tight e SMS-EMOA > MOEA/D em instâncias R-Loose. Tornar essas predições explícitas no texto da dissertação fortalece a ancoragem teórica sem adicionar hipóteses formais novas.

**F6 - Configuração de parâmetros por valores padrão**

Usar valores padrão da literatura para os algoritmos é pragmaticamente justificável para um TCC, mas introduz o risco de que um algoritmo esteja mal configurado para as características específicas do EVRPTW. Um NSGA-II com parâmetros sub-ótimos para o problema pode ser derrotado não por limitações estruturais do algoritmo mas por configuração inadequada.

**Justificativa:** Mitigação: ao menos executar uma análise de sensibilidade paramétrica mínima para cada algoritmo em uma instância representativa (por exemplo, variar o tamanho da população entre 50, 100 e 200 para verificar robustez). Se resultados mudarem significativamente, tuning mais cuidadoso é necessário. Declarar essa limitação explicitamente na metodologia da dissertação.

## **7.3 Pontos que requerem decisão antes de implementar**

Os seguintes pontos permanecem em aberto e precisam ser resolvidos antes de iniciar a implementação:

- Representação de solução e operadores genéticos: a escolha afeta diretamente o tempo de execução por run e, portanto, o critério de parada calibrado. Deve ser fixada antes do experimento exploratório de calibração.
- Tratamento de infeasibilidade: como penalizar ou reparar soluções que violam restrições durante a busca. A estratégia escolhida afeta a velocidade de convergência, especialmente em instâncias Tight.
- Versão específica dos algoritmos: NSGA-II original (Deb et al., 2002) ou variante? MOEA/D com TCHE ou com PBI como função de escalarização? SMS-EMOA com seleção por contribuição de hipervolume exata ou aproximada? Cada escolha deve ser justificada e referenciada.

## **7.4 Avaliação geral**

O design experimental, com as mitigações indicadas, é metodologicamente sólido e adequado para um TCC. Os principais riscos são gerenciáveis com execuções exploratórias antes do experimento principal. As fragilidades residuais (uma instância por célula, desequilíbrio de amplitude de TW, ausência de análise prévia de correlação) são tratáveis como limitações declaradas na dissertação, o que é metodologicamente honesto e aceitável. O design produza resultados interpretáveis, hipóteses testáveis e contribuição identificável para a literatura de comparação de algoritmos multi-objetivo aplicados ao EVRPTW.

**Decisão:** Decisão de design mais importante antes de avançar: definir a representação de solução e executar o experimento exploratório de calibração em c101_21. Esse único passo desbloqueará o critério de parada, o orçamento computacional preciso e o cronograma realista para o TCC.