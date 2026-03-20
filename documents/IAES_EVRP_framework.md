**PROPOSTA DE EXTENSÃO DO FRAMEWORK IAS**

para o

**Electric Vehicle Routing Problem**

_Explorando Soluções Inviáveis como Recurso Estratégico no EVRP_

**Documento Técnico de Pesquisa**

_Baseado em Cai et al. (2026) - CMOEA-IAS - e Ou et al. (2024) - CEOA_

# **1\. Introdução e Motivação**

**O Electric Vehicle Routing Problem (EVRP)** representa uma extensão do clássico Vehicle Routing Problem (VRP) que incorpora as restrições operacionais dos veículos elétricos: autonomia limitada de bateria, necessidade de recarga em estações intermediárias e dependência da infraestrutura de carregamento disponível. Estas características introduzem uma nova dimensão de complexidade que vai além das restrições de capacidade e janelas de tempo presentes no VRPTW clássico.

A literatura recente demonstrou que algoritmos evolutivos multi-objetivo (MOEAs) com técnicas sofisticadas de tratamento de restrições (CHTs) são capazes de resolver eficientemente variantes do VRP. Em particular, o framework **_Infeasibility-Aided Strategy (IAS)_**, proposto por Cai et al. (2026) para o MOVRPTW, mostrou que soluções inviáveis - normalmente descartadas - podem ser exploradas estrategicamente como guias de busca em espaços com escassa factibilidade (_sparse feasibility_). O CEOA de Ou et al. (2024) complementou essa visão ao demonstrar a eficácia do balanceamento dinâmico entre objetivos e restrições na seleção ambiental.

Este documento propõe uma extensão sistemática e fundamentada dessas abordagens para o contexto do EVRP, considerando as particularidades estruturais que tornam a inviabilidade energética **qualitativamente diferente** das demais formas de inviabilidade presentes no VRP clássico.

**Tese Central**

No EVRP, soluções energeticamente inviáveis possuem valores de objetivos artificialmente otimistas - uma solução que viola a restrição de bateria pode parecer excelente em distância e tempo precisamente porque omitiu paradas de recarga que seriam necessárias para torná-la viável. Este fenômeno de 'mascaramento de objetivos' exige uma abordagem de tratamento de inviabilidade específica, distinta daquela aplicada a restrições de capacidade ou janelas de tempo.

# **2\. Fundamentos do EVRP e Suas Distinções em Relação ao VRP**

## **2.1 Estrutura do Problema**

O EVRP é formalmente definido sobre um grafo completo _G = (V, E)_, onde _V = {0} ∪ C ∪ S_. O nó 0 representa o depósito, _C = {1, ..., n}_ é o conjunto de clientes e _S = {s₁, ..., sₘ}_ é o conjunto de estações de recarga. A cada aresta _(i, j) ∈ E_ associam-se uma distância _d_{ij}_e um consumo de energia \_e_{ij}_. Cada veículo elétrico possui capacidade de carga \_Q_ e uma bateria de capacidade _B_, com estado de carga inicial plena.

Uma solução do EVRP é um conjunto de rotas onde cada rota começa e termina no depósito, atende a um subconjunto de clientes, pode visitar estações de recarga em posições intermediárias, e deve garantir em todo instante que o nível de carga da bateria permaneça não-negativo.

## **2.2 Mapa de Diferenças: VRP × EVRP**

| **Aspecto**               | **VRP / VRPTW**                           | **EVRP**                                                                           |
| ------------------------- | ----------------------------------------- | ---------------------------------------------------------------------------------- |
| Restrição de veículo      | Capacidade de carga (Q)                   | Capacidade de carga (Q) + Bateria (B)                                              |
| Nós intermediários        | Apenas clientes                           | Clientes + Estações de recarga (S)                                                 |
| Flexibilidade de rota     | Sequência fixa de clientes                | Inserção opcional de estações cria rotas de comprimento variável                   |
| Natureza da inviabilidade | Violação de capacidade ou janela de tempo | Violação energética: ausência ou posição incorreta de estação                      |
| Efeito sobre objetivos    | Inviabilidade geralmente piora objetivos  | Inviabilidade energética frequentemente melhora objetivos aparentes (mascaramento) |
| Espaço de busca           | Permutações de clientes                   | Permutações de clientes intercaladas com inserções de estações                     |
| Correção de inviabilidade | Remoção de clientes ou redistribuição     | Inserção de estações → piora explícita dos objetivos                               |
| Reparo de soluções        | Geralmente simples e local                | Complexo: inserção de estação muda todo o perfil energético da rota                |

## **2.3 A Nova Restrição de Bateria e Suas Implicações**

A restrição de bateria introduz um estado interno ao veículo que evolui dinamicamente ao longo da rota. Para um veículo percorrendo a sequência de nós _v₀ = 0, v₁, v₂, ..., vₖ, vₖ₊₁ = 0_, o nível de carga _b(vⱼ)_ após visitar o nó _vⱼ_ é dado por:

b(vⱼ) = b(vⱼ₋₁) − e(vⱼ₋₁, vⱼ) se vⱼ₋₁ é cliente ou depósito

b(vⱼ) = B se vⱼ₋₁ é estação de recarga (recarga completa)

A restrição de viabilidade energética exige que _b(vⱼ) ≥ 0_ para todo _j_. Quando esta condição é violada em algum ponto da rota, a solução é **energeticamente inviável**. Diferentemente de uma violação de capacidade - que pode ser quantificada pelo excesso de demanda acumulada - uma violação energética indica que o veículo ficaria sem energia em algum trecho da rota, tornando-a fisicamente irrealizável.

**Propriedade Crítica: Dependência Posicional**

A viabilidade energética depende da posição relativa das estações de recarga dentro da rota, não apenas de sua presença. Uma solução pode ser energeticamente inviável mesmo possuindo estações de recarga suficientes se estas estiverem mal posicionadas - por exemplo, duas estações consecutivas separadas por um trecho mais longo do que a autonomia da bateria. Esta propriedade posicional cria uma paisagem de inviabilidade muito mais complexa do que a encontrada em restrições de capacidade.

# **3\. O Problema do Mascaramento de Objetivos**

## **3.1 Definição Formal do Mascaramento**

Seja _x_ uma solução candidata para o EVRP multiobjetivo com objetivos _F(x) = (f₁(x), f₂(x), ..., f_M(x))_ (número de veículos, distância total, makespan, etc.). Se _x_ é energeticamente inviável - ou seja, omite estações de recarga necessárias em pontos críticos - define-se a solução reparada correspondente _x̂_ como a versão de _x_ com todas as inserções de estações necessárias para garantir viabilidade energética.

O **efeito de mascaramento** ocorre quando:

F(x) ≺ F(x̂) (i.e., x parece dominar x̂ no espaço de objetivos)

mas _x_ não é viável enquanto _x̂_ é viável. Em outras palavras, a solução inviável _x_ possui valores de objetivos artificialmente melhores porque não paga o custo real das estações de recarga que precisaria visitar.

## **3.2 Por Que o Mascaramento Ocorre**

Considere os objetivos mais diretamente afetados pela inserção de estações de recarga:

- **Distância total (f₂):** Inserir uma estação em posição intermediária adiciona dois deslocamentos extras - cliente_anterior → estação e estação → próximo_cliente - no lugar de cliente_anterior → próximo_cliente. O desvio de rota pode ser significativo dependendo da localização geográfica das estações disponíveis.
- **Makespan (f₃):** Além do tempo de deslocamento adicional, a recarga em si consome tempo (seja recarga completa ou parcial). Modelos com recarga linear adicionam tempo proporcional à carga necessária.
- **Tempo total de espera (f₄):** Se a chegada à estação ocorre antes da abertura da estação (em modelos com janelas de tempo para estações), tempo de espera adicional é incorrido.
- **Número de veículos (f₁):** Em casos extremos, a necessidade de recargas múltiplas pode tornar uma rota tão longa que precisa ser dividida entre veículos adicionais.

Portanto, a solução inviável _x_ exibe valores _f₂(x) < f₂(x̂)_, _f₃(x) < f₃(x̂)_ e possivelmente _f₄(x) < f₄(x̂)_ - ela parece ótima precisamente porque não contabilizou o custo das recargas que tornaria a solução fisicamente realizável.

## **3.3 Implicações para Algoritmos Evolutivos**

**Armadilha dos Algoritmos Convencionais**

Algoritmos que simplesmente penalizam soluções inviáveis somando CV aos objetivos podem inadvertidamente favorecer soluções energeticamente inviáveis com CV pequeno sobre soluções viáveis com objetivos levemente piores. Isso ocorre porque o CV pode ser pequeno (apenas um ou dois trechos sem energia) enquanto o benefício aparente nos objetivos é substancial. O algoritmo converge então para regiões do espaço de busca que são sistematicamente não-realizáveis na prática.

Mais sutilmente, se um algoritmo evolutivo aprende que soluções com 'poucas estações' tendem a ter bons valores de objetivos, pode direcionar a pressão seletiva para eliminar estações das rotas - produzindo populações progressivamente mais inviáveis ao longo da evolução. Este comportamento é o oposto do desejado e é particularmente perigoso em algoritmos baseados em decomposição (como MOEA/D) onde a qualidade escalarizada pode ser enganosa.

Por outro lado, o insight central do CMOEA-IAS - de que soluções inviáveis carregam informação valiosa sobre regiões promissoras do espaço de busca - permanece válido no EVRP, mas deve ser aplicado com **consciência do efeito de mascaramento**. A chave está em distinguir entre o valor _aparente_ de uma solução inviável (seus objetivos mascarados) e seu valor _potencial_ (o que ela indicaria se os objetivos fossem corretamente estimados).

# **4\. Taxonomia da Inviabilidade no EVRP**

Diferentemente do VRPTW, onde as restrições são relativamente homogêneas (capacidade e janela de tempo), o EVRP apresenta múltiplos tipos de inviabilidade com semânticas e implicações distintas. Propomos a seguinte taxonomia:

| **Tipo**                               | **Definição**                                                                                                                  | **Efeito nos Objetivos**                                                                             | **Corrigibilidade**                                                        | **Valor Exploratório**                                                              |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Inviabilidade Energética Simples (IES) | Um único trecho da rota excede a autonomia da bateria; uma estação inserida entre os dois nós do trecho resolveria o problema. | **Alto mascaramento:** f₂ e f₃ subestimados por exatamente o desvio de uma inserção.                 | Alta - inserção local de uma estação                                       | **Muito alto:** a estrutura da rota é quase viável e o desvio de custo é estimável. |
| Inviabilidade Energética Cascata (IEC) | Múltiplos trechos consecutivos sem energia; a ausência de uma estação cria déficit que se propaga.                             | **Mascaramento elevado e difuso:** múltiplos objetivos afetados por múltiplas inserções necessárias. | Média - requer múltiplas inserções e possivelmente reestruturação de rota. | **Médio:** informação estrutural válida mas com custo real difícil de estimar.      |
| Inviabilidade de Capacidade (IC)       | Demanda total da rota excede a capacidade do veículo Q.                                                                        | **Mascaramento baixo:** corrigir por redistribuição de clientes não melhora f₂ ou f₃.                | Alta - redistribuição de clientes                                          | **Alto:** idêntico ao VRPTW - análogo ao uso de IAS em Cai et al. (2026).           |
| Inviabilidade de Janela de Tempo (IJT) | Atraso ou antecipação excessivos em clientes ou no retorno ao depósito.                                                        | **Mascaramento baixo-médio:** corrigir atrasos geralmente requer reordenação ou mais veículos.       | Média                                                                      | **Alto:** idêntico ao CMOEA-IAS original, aplicável diretamente.                    |
| Inviabilidade Mista (IM)               | Combinação de IES/IEC com IC ou IJT simultaneamente.                                                                           | **Mascaramento complexo e difícil de decompor.**                                                     | Baixa - interações entre tipos complicam o reparo.                         | **Baixo-médio:** requer tratamento diferenciado por tipo antes de exploração.       |

**Princípio de Tratamento Diferenciado**

A taxonomia acima revela que IES possui o mais alto valor exploratório e o mais alto efeito de mascaramento simultaneamente. Este aparente paradoxo é a motivação central da extensão proposta: precisamos de mecanismos que reconheçam o potencial estrutural de uma solução IES sem serem enganados pelos seus objetivos mascarados.

# **5\. Framework Proposto: IAS-EVRP**

## **5.1 Visão Geral Arquitetural**

O framework **IAS-EVRP** estende o CMOEA-IAS de Cai et al. (2026) com quatro novos componentes projetados para lidar com as especificidades do EVRP, mantendo a estrutura geral de evolução:

- **Classificador de Inviabilidade (CI):** identifica e classifica o tipo de inviabilidade de cada solução segundo a taxonomia da Seção 4.
- **SIFO-E (SIFO para EVRP):** versão estendida do SIFO que usa objetivos corrigidos para soluções energeticamente inviáveis, eliminando o efeito de mascaramento na seleção.
- **DIMO-E (DIMO para EVRP):** versão estendida do DIMO que gerencia proporções separadas de inviáveis energéticos e não-energéticos, com limiares adaptativos distintos.
- **Operador de Reparo Parcial Guiado (ORPG):** operador de busca local que insere estações de recarga em posições estratégicas sem modificar a estrutura de roteamento dos clientes, gerando soluções viáveis derivadas das inviáveis.

O fluxo geral do IAS-EVRP é:

- **Inicialização:** geração de população mista (viáveis + inviáveis energéticos + inviáveis de capacidade).
- **Para cada geração:** (1) geração de descendentes, (2) classificação por CI, (3) seleção por SIFO-E com objetivos corrigidos, (4) gestão de proporções por DIMO-E, (5) atualização do arquivo externo, (6) busca local por ORPG.
- **Saída:** arquivo com soluções viáveis não-dominadas aproximando a frente de Pareto real do EVRP.

## **5.2 Classificador de Inviabilidade (CI)**

O CI analisa cada solução e produz um vetor de violação multidimensional que discrimina entre os tipos de inviabilidade:

_CV(x) = (CV_energy(x), CV_cascade(x), CV_cap(x), CV_tw(x))_

onde cada componente é normalizado pelo máximo e mínimo da população, análogo à normalização de Ou et al. (2024).

Os componentes são calculados como:

- **CV_energy(x):** soma dos déficits energéticos em trechos individuais onde o nível de bateria ficaria negativo, medido em unidades de energia. Este componente identifica IES.
- **CV_cascade(x):** número de trechos consecutivos deficientes ponderado pelo déficit acumulado - distingue IEC de IES. Uma IES terá CV_cascade ≈ 0 enquanto IEC terá CV_cascade > 0.
- **CV_cap(x):** excesso de demanda acumulada sobre a capacidade Q, análogo ao CEOA.
- **CV_tw(x):** soma dos atrasos que excedem o limite máximo md, análogo ao CMOEA-IAS original.

Uma solução é classificada como: **Viável** se todos os componentes são zero; **IES** se CV_energy > 0 e CV_cascade = 0; **IEC** se CV_cascade > 0; **IC** se CV_cap > 0 (e CV_energy = CV_cascade = 0); **IJT** se CV_tw > 0 (e CV_energy = CV_cascade = CV_cap = 0); **IM** caso contrário.

## **5.3 Estimador de Objetivos Corrigidos (EOC)**

### **5.3.1 Motivação e Princípio**

O componente mais original do IAS-EVRP é o **Estimador de Objetivos Corrigidos (EOC)**. Para soluções energeticamente inviáveis (IES ou IEC), o EOC computa uma estimativa dos objetivos que a solução teria _se fosse reparada de forma ótima_, sem efetivamente executar esse reparo. Esta estimativa substitui os objetivos mascarados nas operações de dominância e densidade do SIFO-E.

### **5.3.2 Estimativa de Custo de Inserção de Estação**

Para cada trecho (i, j) energeticamente deficiente em uma solução x, o EOC identifica o conjunto de estações de recarga candidatas _S_{ij} ⊆ S\_ que poderiam ser inseridas entre i e j para eliminar o déficit. O custo incremental mínimo de inserção é:

δ*dist(i,j) = min*{s ∈ S\_{ij}} { d(i,s) + d(s,j) − d(i,j) }

δ_time(i,j) = δ_dist(i,j)/vel + t_charge(s\*) onde s\* = argmin...

onde _t_charge(s\*)_ é o tempo de recarga na melhor estação. O objetivo corrigido de distância para uma solução IES com conjunto de trechos deficientes _D(x)_ é:

f̃₂(x) = f₂(x) + Σ\_{(i,j) ∈ D(x)} δ_dist(i,j)

Analogamente, _f̃₃(x)_ e _f̃₄(x)_ são corrigidos pelos incrementos de tempo e espera estimados. Esses objetivos corrigidos **não atualizam a solução** - são usados apenas internamente pelo SIFO-E para avaliar qualidade na seleção.

**Propriedade de Corretude Assintótica**

O EOC é um estimador inferior - f̃₂(x) ≤ f₂(x̂) para toda solução x com reparo ótimo x̂ - pois assume que a estação ótima de inserção sempre está disponível na posição ideal. Para casos IES (um único trecho deficiente), a estimativa tende a ser apertada. Para IEC, pode ser otimista quando múltiplas inserções interagem. Esta propriedade garante que o SIFO-E nunca superestime o custo de reparo, sendo conservador a favor das soluções inviáveis como guias de busca.

### **5.3.3 Fator de Confiança da Estimativa**

Para refletir a incerteza da estimativa EOC, especialmente para soluções IEC, introduz-se um **fator de confiança** α(x) ∈ \[0, 1\] que pondera os objetivos corrigidos:

f̂_m(x) = α(x) · f̃_m(x) + (1 − α(x)) · f_m(x)

Para IES, α(x) = 1 (estimativa confiável). Para IEC, α(x) = 1 / (1 + CV_cascade(x)) decresce com a severidade da cascata, fazendo a avaliação convergir para os objetivos mascarados originais quando o reparo seria muito complexo. Este mecanismo previne que soluções IEC severamente inviáveis sejam supervalorizadas.

## **5.4 SIFO-E: SIFO Estendido para EVRP**

O SIFO-E substitui o SIFO original com as seguintes modificações:

- **Avaliação de fitness com objetivos corrigidos:** Para soluções IES e IEC, a relação de dominância estritamente restrita (≺_SCD) é computada usando f̂_m(x) em vez de f_m(x). Soluções viáveis, IC e IJT mantêm seus objetivos originais.
- **Relação de dominância energia-consciente (≺_ECD):** Define-se que x_i ≺_ECD x_j se: (a) x_i é viável e x_j é energeticamente inviável, OU (b) ambos são energeticamente inviáveis e f̂(x_i) domina f̂(x_j) com CV(x_i) ≤ CV(x_j), OU (c) ambos são viáveis e x_i ≺_SCD x_j. Esta relação preserva a capacidade de soluções IES de ficarem não-dominadas em relação a viáveis - mas apenas quando seus objetivos corrigidos f̂ são competitivos.
- **Estimativa de densidade com deslocamento restrito adaptada:** O parâmetro q da função sigmoide (Eq. 19 de Cai et al.) é aplicado separadamente para cada tipo de inviabilidade. Para IES, q evolui mais lentamente (τ_IES > τ_IJT), mantendo a pressão exploratória das soluções IES por mais tempo.
- **Arquivo separado de elite IES:** As melhores soluções IES (por f̂ corrigido) são mantidas em um arquivo auxiliar de tamanho N_E. Quando a população principal esgota a diversidade em regiões promissoras, o arquivo elite IES fornece pontos de partida para o operador ORPG.

**Intuição do SIFO-E**

Uma solução IES que, após correção, teria f̂₂ = 350km representa uma rota estruturalmente eficiente que simplesmente precisa de uma parada de recarga. Uma solução viável com f₂ = 380km é objetivamente pior do ponto de vista real. O SIFO-E permite que a solução IES permaneça não-dominada e guie a busca para regiões onde inserir a estação certa tornará a rota ótima. Sem correção, a solução IES teria f₂ = 310km (mascarado) e seria mantida por razões erradas - ou pior, seria descartada após o CV ser somado.

## **5.5 DIMO-E: DIMO Estendido para EVRP**

O DIMO-E mantém **limiares separados** para cada tipo de inviabilidade, reconhecendo que cada tipo tem impacto e valor exploratório distintos:

_γ_E = (rand(-0.01, 0.01) + η_E) × N_P \[limiar para IES + IEC\]_

_γ_C = (rand(-0.01, 0.01) + η_C) × N_P \[limiar para IC\]_

_γ_T = (rand(-0.01, 0.01) + η_T) × N_P \[limiar para IJT\]_

onde cada η é calculado pela proporção natural do respectivo tipo na população inicial. O DIMO-E opera com três lógicas distintas:

### **5.5.1 Gestão de Soluções IES**

IES são as mais valiosas: soluções com alto potencial e custo de reparo estimável. O DIMO-E as trata com prioridade máxima de preservação. Quando _Inf_IES(P) < γ_E_: remove soluções viáveis de baixa qualidade (dominadas por muitas outras) e gera novas soluções IES via **operador de remoção de estação (ORE)** - retira estações de soluções viáveis selecionadas, criando inviáveis energéticos controlados. Quando _Inf_IES(P) > γ_E_: repara as IES com maior CV_energy via ORPG parcial, mantendo a estrutura de roteamento e inserindo apenas a estação de custo mínimo.

### **5.5.2 Gestão de Soluções IEC**

IEC são tratadas com menor prioridade exploratória devido à estimativa de custo menos confiável. Quando em excesso, as IEC com maior CV_cascade são removidas e substituídas por soluções viáveis geradas pelo operador de inicialização. Quando em déficit, IEC são geradas ocasionalmente por crossover sem verificação energética - permitindo exploração de regiões de longo alcance.

### **5.5.3 Gestão de IC e IJT**

Idêntica ao DIMO original de Cai et al. (2026). A inviabilidade de capacidade e de janela de tempo são tratadas de forma análoga ao VRPTW, sem as modificações de correção de objetivos.

## **5.6 Operador de Reparo Parcial Guiado (ORPG)**

O ORPG é um operador de busca local especializado que converte soluções IES em soluções viáveis de forma eficiente. Distingue-se de operadores de reparo completos por ser **parcial e guiado**: insere estações de recarga de forma incremental e avaliativa, maximizando o ganho de viabilidade por custo de objetivo.

O procedimento ORPG opera em três passos:

- **Identificação e ordenação de trechos deficientes:** Para cada trecho energeticamente deficiente, computa o custo mínimo de inserção δ_dist(i,j) e o ganho de viabilidade ΔCV_energy(i,j) = energia faltante no trecho. Os trechos são ordenados por razão δ_dist / ΔCV_energy (eficiência energética da inserção).
- **Inserção sequencial por eficiência:** Itera pelos trechos em ordem crescente de custo por unidade de viabilidade recuperada. Para cada trecho, insere a estação de custo mínimo δ_dist, atualiza o perfil energético da rota inteira (pois a inserção afeta os trechos subsequentes via efeito cascata inverso) e recalcula os trechos deficientes restantes.
- **Critério de parada por trade-off:** O ORPG para quando: (a) a solução torna-se viável, ou (b) a próxima inserção necessária excede um limiar de custo θ (evitando reparos caros que destruiriam a qualidade da solução). Soluções parcialmente reparadas são retornadas como IEC de menor severidade e permanecem no pool exploratório.

**Relação ORPG e Arquivo Elite IES**

O ORPG é aplicado preferencialmente às soluções do Arquivo Elite IES a cada iteração, gerando candidatas viáveis de alta qualidade para o arquivo externo. Esta sinergia cria um pipeline: (1) soluções IES promissoras identificadas pelo SIFO-E entram no Arquivo Elite, (2) ORPG as repara gerando viáveis competitivas, (3) viáveis geradas entram no arquivo externo e competem com as de outras origens. O pipeline materializa diretamente a ideia de 'inviáveis como guias para regiões promissoras'.

# **6\. Operadores de Busca Específicos para o EVRP**

## **6.1 Inicialização Adaptada ao EVRP**

A inicialização do IAS-EVRP deve gerar uma população com distribuição intencional entre os tipos de inviabilidade. Propõe-se um esquema de inicialização em três camadas:

- **Camada Viável (α_V × N_P soluções):** Geradas pelo algoritmo de inserção mais próxima com verificação energética completa. Cada rota insere estações de recarga sempre que o nível de bateria cair abaixo de um limiar de segurança β_s × B.
- **Camada IES (α_E × N_P soluções):** Geradas igualmente, mas com β_s = 0 (sem limiar de segurança), permitindo que trechos individuais ultrapassem a autonomia. Produz soluções com violações energéticas simples e isoladas.
- **Camada IEC/IC/IJT (α_R × N_P soluções):** Geradas sem qualquer verificação de restrições. Maximiza diversidade inicial e pode produzir qualquer tipo de inviabilidade.

Os fatores α_V, α_E e α_R são calibrados para refletir a 'dificuldade natural' da instância: em instâncias com muitas estações de recarga e alta densidade, α_V pode ser maior; em instâncias com infraestrutura esparsa, α_E e α_R dominam.

## **6.2 Operador de Crossover com Consciência Energética**

O crossover padrão baseado em rotas (como o de Wang et al. utilizado no CMOEA-IAS) opera trocando rotas inteiras entre soluções. No EVRP, este mecanismo pode inadvertidamente inserir ou remover estações de recarga em posições críticas, gerando soluções IEC severas. Propõe-se uma extensão com **verificação energética pós-crossover**

Após gerar a solução filho pelo crossover padrão, o operador verifica o perfil energético de cada rota. Para trechos deficientes com δ_dist < θ_insert (limiar de inserção barata), a estação ótima é inserida automaticamente. Para trechos com δ_dist ≥ θ_insert, a deficiência é mantida e o filho é classificado como IES para exploração futura. Este mecanismo evita a geração de IEC severas enquanto mantém a diversidade IES.

## **6.3 Operador de Remoção de Estação (ORE)**

O ORE é o complemento do ORPG: converte soluções viáveis em IES de forma controlada. Para uma solução viável x, o ORE:

- Identifica estações de recarga 'folga' - estações visitadas com nível de bateria ainda alto antes e após a visita, indicando que a recarga é conservadora.
- Seleciona probabilisticamente uma estação folga com probabilidade proporcional ao excesso de carga (maior folga = maior probabilidade de remoção).
- Remove a estação e verifica quais trechos tornam-se deficientes. Se apenas um trecho torna-se IES, a solução removida tem alta probabilidade de ser facilmente reparável pelo ORPG.
- Retorna a solução IES resultante para o pool de inviáveis do DIMO-E.

O ORE é fundamental para a etapa do DIMO-E de reposição de IES quando a proporção cai abaixo de γ*E. Ao contrário de gerar IES aleatoriamente, o ORE produz IES \_estruturalmente próximas de soluções viáveis de alta qualidade*, maximizando o valor exploratório do pool de inviáveis.

## **6.4 Busca Local Especifíca para EVRP**

Além do ALSC herdado do MMA-ALSC, o IAS-EVRP inclui uma busca local específica para reposicionamento de estações:

- **Reposicionamento de Estação (RE):** Move uma estação de recarga para uma posição diferente na mesma rota, ou para uma rota diferente, avaliando o impacto em todos os objetivos e na viabilidade energética. Aplicado sobre soluções do arquivo externo.
- **Substituição de Estação (SE):** Troca a estação visitada em uma inserção por uma estação alternativa S' ∈ S, avaliando se S' produz menor desvio de rota com a mesma garantia energética.
- **Fusão de Recargas Consecutivas (FRC):** Se duas estações consecutivas são visitadas na mesma rota, avalia se uma única estação intermediária pode substituir ambas, reduzindo o número de paradas.

# **7\. Algoritmo Completo: IAS-EVRP**

| **Linha** | **Operação**                                | **Descrição**                                       |
| --------- | ------------------------------------------- | --------------------------------------------------- |
| 01        | P₀ ← Inicialização(N_P, α_V, α_E, α_R)      | Gera população inicial com três camadas             |
| 02        | P ← P₀; A ← ∅; A_E ← ∅                      | Inicia arquivo externo e arquivo elite IES          |
| 03        | CI(P₀) → classifica todos os tipos          | Classificador de Inviabilidade na população inicial |
| 04        | Enquanto critério de parada não satisfeito: |                                                     |
| 05        | O ← CrossoverEVRP(P)                        | Crossover com consciência energética                |
| 06        | CI(O) → classifica descendentes             | Classificação dos novos descendentes                |
| 07        | Ô ← EOC(O) → objetivos corrigidos           | Estimador de Objetivos Corrigidos                   |
| 08        | P ← SIFO-E(P ∪ O, Ô)                        | Seleção ambiental com ≺_ECD e objetivos corrigidos  |
| 09        | P ← DIMO-E(P, γ_E, γ_C, γ_T)                | Gestão dinâmica multi-limiar                        |
| 10        | A_E ← AtualizaEliteIES(P, A_E, N_E)         | Mantém arquivo das melhores IES por f̂               |
| 11        | A ← AtualizaArquivo(A, P, ε-dom)            | Atualiza arquivo externo com viáveis                |
| 12        | A ← ALSC(A)                                 | Busca local encadeada multi-objetivo                |
| 13        | A ← BuscaLocalEVRP(A)                       | RE + SE + FRC nas soluções do arquivo               |
| 14        | A ← ORPG(A_E, A)                            | Reparo parcial guiado das elite IES                 |
| 15        | Retorna A                                   | Conjunto de soluções não-dominadas viáveis          |

## **7.1 Análise de Complexidade Computacional**

O custo adicional do IAS-EVRP em relação ao CMOEA-IAS original provém principalmente do EOC e do ORPG:

- **EOC:** Para cada solução inviável, o custo é O(|D(x)| × |S|) para encontrar a melhor estação por trecho deficiente. No pior caso, |D(x)| = O(|C|) e |S| é pequeno, resultando em O(N_P × |C| × |S|) por geração - adição moderada.
- **ORPG:** Executado sobre N_E soluções do arquivo elite, com custo O(|C| × |S|) por solução. Total: O(N_E × |C| × |S|) - comparável à busca local existente.
- **ORE:** O(|S_rota|) por execução, onde |S_rota| é o número de estações na solução - desprezível.
- **DIMO-E:** Adição de três limiares em vez de um. Custo O(N_P) - desprezível.

A complexidade total por iteração do IAS-EVRP é dominada por _O(max{N_P² × log N_P, N_E × |C| × |S|, |A| × D_p × |C|²})_, essencialmente a mesma ordem do CMOEA-IAS original. O overhead do EOC é absorvido dentro do termo N_P² do SIFO-E, que já era o gargalo principal.

# **8\. Questões Críticas de Implementação**

## **8.1 Representação de Soluções**

A representação de soluções no EVRP deve acomodar tanto clientes (atendimento obrigatório) quanto estações de recarga (inserção opcional). Recomenda-se uma representação de **lista de rotas com comprimento variável**, onde cada rota é uma sequência de nós de V = C ∪ S, com marcação de tipo para cada nó (cliente ou estação). As restrições de representação são:

- Cada cliente deve aparecer exatamente uma vez em exatamente uma rota.
- Estações de recarga podem aparecer múltiplas vezes e em múltiplas rotas (sem restrição de unicidade).
- A ordem dos nós dentro de cada rota determina o perfil energético e o perfil de tempo.
- O comprimento das rotas não é fixo - inserções e remoções de estações alteram o comprimento dinamicamente.

## **8.2 Tratamento do Modelo de Recarga**

Diferentes modelos de recarga impactam a complexidade do EOC e do ORPG:

| **Modelo**                 | **Descrição**                                        | **Impacto no EOC**                             | **Impacto no ORPG**                             |
| -------------------------- | ---------------------------------------------------- | ---------------------------------------------- | ----------------------------------------------- |
| Recarga Total              | Bateria sempre carregada ao máximo na estação        | Simples: b após estação = B                    | Inserção única suficiente por trecho            |
| Recarga Parcial Linear     | Carrega por um tempo t, recuperando t × taxa_recarga | Moderado: envolve otimização do tempo de carga | Precisa decidir quanto carregar em cada estação |
| Recarga Parcial Não-linear | Taxa de recarga varia com nível de bateria           | Complexo: requer modelo de carga não-linear    | ORPG mais custoso; pode usar aproximação linear |
| Múltiplos Tipos de Estação | Estações com potências de carga diferentes           | Moderado: seleciona tipo de estação ótimo      | Seleção de tipo integrada à inserção            |

Para o caso geral com recarga parcial, o EOC pode usar recarga total como estimativa conservadora (superestima o tempo de carga, portanto os objetivos corrigidos são conservadoramente pessimistas) - o que mantém a propriedade de estimador inferior discutida na Seção 5.3.2.

## **8.3 Calibração dos Parâmetros τ_IES e τ_IJT**

O parâmetro τ da sigmoide controla quando a pressão seletiva muda de favorável a inviáveis para favorável a viáveis. No IAS-EVRP, τ é diferenciado por tipo:

- **τ_IES ∈ \[0.30, 0.45\]:** IES são mantidas por mais tempo como guias exploratórios, pois têm alto valor e custo estimável. Um τ maior significa que a transição para pressão sobre viáveis é mais tardia.
- **τ_IEC ∈ \[0.15, 0.25\]:** IEC têm valor exploratório médio; a transição é mais rápida para evitar que soluções com estimativas imprecisas distorçam a seleção.
- **τ_IJT ∈ \[0.20, 0.30\]:** Igual ao valor padrão τ = 0.25 do CMOEA-IAS - restrições de janela de tempo no EVRP têm comportamento análogo ao VRPTW.

Recomenda-se análise de sensibilidade empírica análoga à realizada por Cai et al. (2026) para o parâmetro τ original, testando τ_IES ∈ {0.25, 0.35, 0.45} e τ_IEC ∈ {0.10, 0.20, 0.30} em um conjunto representativo de instâncias EVRP com diferentes densidades de estações.

# **9\. Métricas de Avaliação Específicas para o EVRP**

Além das métricas padrão (IGD, HV, NR, ONVG, C-metric) utilizadas no CMOEA-IAS, o IAS-EVRP requer métricas adicionais que capturem aspectos específicos do EVRP:

| **Métrica**                         | **Definição**                                                                           | **O Que Mede**                                    |
| ----------------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------- |
| FVR (Feasible Visit Rate)           | Proporção de soluções do arquivo final que são energeticamente viáveis                  | Qualidade energética do arquivo - idealmente 100% |
| ECD (Energy Correction Delta)       | Diferença média entre f₂(x) e f̂₂(x) para IES no arquivo de elite                        | Magnitude do mascaramento explorado pelo EOC      |
| RSE (Repair Success Rate)           | Proporção de soluções IES do arquivo elite convertidas em viáveis pelo ORPG por geração | Efetividade do pipeline IES → Viável              |
| SCI (Station Coverage Index)        | Número médio de estações distintas utilizadas nas soluções viáveis do arquivo           | Diversidade de infraestrutura explorada           |
| ERatio (Energy Infeasibility Ratio) | Proporção de soluções IES na população ao longo das gerações                            | Dinâmica do DIMO-E - deve oscilar em torno de γ_E |

A métrica ECD é particularmente importante para validar a hipótese central do trabalho: se ECD é grande (soluções IES têm objetivos mascarados muito melhores que os corrigidos), o mecanismo de correção está capturando um fenômeno real e relevante. Se ECD ≈ 0, as soluções IES não possuem mascaramento significativo e o IAS-EVRP degrada graciosamente ao comportamento do CMOEA-IAS original.

# **10\. Instâncias e Protocolo Experimental Sugerido**

## **10.1 Conjuntos de Instâncias Recomendados**

| **Conjunto**                              | **Origem**                               | **Características**                                      | **Relevância para IAS-EVRP**                         |
| ----------------------------------------- | ---------------------------------------- | -------------------------------------------------------- | ---------------------------------------------------- |
| Schneider et al. (2014)                   | Benchmark padrão EVRP                    | 25-100 clientes, mono-objetivo, estações uniformes       | Baseline para validação de operadores básicos        |
| Schiffer & Walther (2017)                 | EVRP com estações variáveis e capacidade | Variabilidade de infraestrutura de recarga               | Testa sensibilidade à densidade de estações          |
| Pelletier et al. (2019)                   | EVRP com recarga parcial não-linear      | Modelo de bateria realista                               | Valida EOC com estimativa conservadora               |
| Instâncias Sintéticas Esparsas (proposta) | Derivadas de Gutiérrez et al. (2011)     | Baixa densidade de estações (sparse feasibility elevada) | Cenário ideal para validar IAS-EVRP vs. IAS original |
| Instâncias Multi-objetivo EVRP            | Extensão de Cai et al. (2026) para EVRP  | 5 objetivos: f₁-f₅ do VRPTW + função de carga            | Avaliação completa com múltiplas métricas            |

## **10.2 Algoritmos Comparadores Recomendados**

- **CMOEA-IAS (Cai et al., 2026):** baseline direto, para isolar a contribuição das extensões EVRP-específicas.
- **CEOA (Ou et al., 2024):** baseline de priorização dinâmica de restrições, adaptado para EVRP.
- **NSGA-II-EVRP:** baseline clássico com penalização de inviáveis, para medir ganho do framework IAS.
- **EVRP-GA (Schneider et al., 2014):** algoritmo de referência específico para EVRP mono-objetivo, para contextualização.
- **IAS-EVRP sem EOC (ablação):** variante que usa objetivos mascarados no SIFO-E, para medir o impacto da correção de objetivos isoladamente.
- **IAS-EVRP sem ORPG (ablação):** variante sem o pipeline de reparo, para medir o impacto do ORPG isoladamente.

**Experimento Crucial: Validação do Mascaramento**

Um experimento indispensável é comparar os valores de f₂(x) com f̂₂(x) = f₂(x̂) (obtidos por reparo efetivo) para todas as soluções IES da população ao longo das gerações. Se o IAS-EVRP sem EOC converge mais lentamente ou para soluções piores, confirma-se que o mascaramento prejudicava a seleção e que o EOC é necessário. Se não houver diferença significativa, o efeito de mascaramento é empiricamente irrelevante para as instâncias testadas - resultado igualmente valioso e honesto.

# **11\. Limitações e Direções de Pesquisa Futura**

## **11.1 Limitações Inerentes à Proposta**

- **Precisão do EOC em IEC:** O estimador de objetivos corrigidos é preciso para IES mas apenas aproximado para IEC. Em instâncias com alta densidade de violações em cascata, o EOC pode sistematicamente subestimar ou superestimar o custo real de reparo, distorcendo a seleção.
- **Dependência da densidade de estações:** Em instâncias com densidade de estações muito alta, a distinção entre IES e rotas viáveis com estações 'desnecessárias' torna-se tênue, e o ORE pode gerar IES trivialmente reparáveis que não contribuem com diversidade real.
- **Escalabilidade do ORPG:** Para instâncias muito grandes (|C| > 500), o custo do ORPG pode tornar-se proibitivo se o arquivo elite IES for grande. Limitar N_E ou usar ORPG probabilístico pode ser necessário.
- **Modelo de recarga único:** A proposta foi desenvolvida primariamente com recarga total em mente. Extensões para recarga parcial requerem modificações no EOC e no ORPG.

## **11.2 Direções Futuras**

- **EOC baseado em aprendizado:** Usar redes neurais ou modelos de regressão treinados online para estimar f̂(x) de forma mais precisa, especialmente para casos IEC onde a estimativa analítica é limitada.
- **DIMO-E adaptativo por fase:** Diferentes estágios da evolução podem requerer diferentes proporções de IES - exploração ampla no início, refinamento focado no final. Um DIMO-E com γ_E variável ao longo das gerações pode capturar essa dinâmica.
- **Integração com aprendizado por reforço:** Usar RL para aprender a política ótima de inserção de estações, substituindo o EOC heurístico por um estimador treinado por interações com o ambiente de simulação.
- **Extensão para EVRP com incerteza:** Considerar demanda incerta ou disponibilidade de estações estocástica, onde a inviabilidade energética tem distribuição de probabilidade - ampliando o conceito de CV para CV esperado.
- **Generalização para outros VRP elétricos:** Aplicar o framework IAS-EVRP ao E-VRPTW (com janelas de tempo), ao E-VRP com múltiplos depósitos e ao drone delivery routing, onde restrições energéticas análogas existem.

# **12\. Síntese e Conclusão**

Este documento propôs o framework **IAS-EVRP**, uma extensão sistemática da Infeasibility-Aided Strategy de Cai et al. (2026) para o Electric Vehicle Routing Problem. As principais contribuições conceituais são:

- **Taxonomia de Inviabilidade do EVRP:** Distinção formal entre IES, IEC, IC e IJT, com caracterização do valor exploratório e do efeito de mascaramento de cada tipo.
- **Conceito de Mascaramento de Objetivos:** Formalização do fenômeno pelo qual soluções energeticamente inviáveis exibem objetivos artificialmente otimistas, e sua implicação para algoritmos evolutivos que não distinguem viabilidade energética.
- **Estimador de Objetivos Corrigidos (EOC):** Mecanismo analítico de baixo custo para corrigir o mascaramento sem executar o reparo efetivo, mantendo a eficiência computacional do framework.
- **SIFO-E e DIMO-E:** Extensões dos operadores centrais do IAS que incorporam consciência energética na seleção e na gestão de proporções de inviáveis.
- **Pipeline IES → Viável via ORPG:** Materialização concreta da ideia de 'inviáveis como guias' através do reparo parcial e guiado das melhores soluções energeticamente inviáveis.

**Mensagem Central**

No EVRP, não basta incorporar soluções inviáveis ao processo evolutivo - é preciso incorporá-las com correção. Uma solução IES que percorre 300km sem recarregar (impossível com bateria de 250km de autonomia) não é melhor do que uma viável que percorre 330km com uma parada de recarga: é apenas uma promessa de que, se a estação certa for inserida no lugar certo, 330km podem se tornar 320km. O IAS-EVRP é projetado para reconhecer e explorar exatamente essas promessas.

**Referências Principais**

\[1\] Cai, Y., Zheng, H., Liang, B., Zhou, Y., & Tian, H. (2026). Constrained multi-objective evolutionary algorithm with an infeasibility-aided strategy for the vehicle routing problem with time windows. Applied Soft Computing, 190, 114597.

\[2\] Ou, J., Liu, X., Xing, L., Lv, J., Hu, Y., Zheng, J., Zou, J., & Li, M. (2024). Solving many-objective delivery and pickup vehicle routing problem with time windows with a constrained evolutionary optimization algorithm. Expert Systems With Applications, 255, 124712.

\[3\] Schneider, M., Stenger, A., & Goeke, D. (2014). The electric vehicle-routing problem with time windows and recharging stations. Transportation Science, 48(4), 500-520.

\[4\] Schiffer, M., & Walther, G. (2017). The electric location routing problem with time windows and partial recharging. European Journal of Operational Research, 260(3), 995-1013.

\[5\] Pelletier, S., Jabali, O., & Laporte, G. (2019). The electric vehicle routing problem with energy consumption uncertainty. Transportation Research Part B, 126, 225-255.

\[6\] Deb, K., Pratap, A., Agarwal, S., & Meyarivan, T. (2002). A fast and elitist multiobjective genetic algorithm: NSGA-II. IEEE Transactions on Evolutionary Computation, 6(2), 182-197.