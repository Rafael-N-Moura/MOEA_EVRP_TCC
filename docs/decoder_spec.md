Especificação do Decodificador — EVRPTW-PR

**Especificação do Decodificador**

*EVRPTW-PR com Gestão de Soluções Inviáveis*





*Objetivos · Cromossomo · Pseudocódigo · Casos Limite*


# **1. Objetivos**
O problema é formulado com **três objetivos**, sendo dois canônicos do EVRPTW-PR e um instrumental de violação agregada. A redução de quatro para três objetivos é motivada pela deterioração da pressão de seleção do NSGA-II em quatro dimensões: com muitos objetivos a proporção de soluções no Front 1 cresce rapidamente, degenerando a seleção para crowding distance puro em um espaço de alta dimensão.

||**Objetivo**|**Definição**|**Papel**|
| :-: | :-: | :-: | :-: |
|**f₁**|Custo total de roteamento|*Σ dist(i,j) · x\_{ij}   para todos os arcos percorridos*|Objetivo canônico primário. Minimizar.|
|**f₂**|Energia total consumida|*Σ r · dist(i,j) · x\_{ij}   onde r é o consumo por unidade de distância*|Objetivo canônico secundário. Minimizar. Cria trade-off real com f₁.|
|**f₃**|Violação agregada|*cv\_energia  +  w · cv\_tw onde w é peso de escala entre as unidades*|Objetivo instrumental. f₃ = 0 define factibilidade completa. Gradiente contínuo e classificável.|

|<p>**Sobre a escolha de f₃ como objetivo único de violação**</p><p>Manter cv\_energia e cv\_tw como dimensões separadas (formulação de 4 objetivos) agrava o problema de dominância do NSGA-II. A agregação em f₃ sacrifica a capacidade de distinguir os dois tipos de violação na seleção, mas preserva o gradiente contínuo que a técnica de inviáveis requer. O peso w deve ser calibrado para que as duas parcelas tenham magnitudes comparáveis na instância utilizada — uma opção inicial simples é w = 1 e normalizar ambos pelo valor máximo observado na população inicial.</p>|
| :- |

As restrições tratadas como **hard constraints** — nunca violadas durante a evolução — são cobertura de todos os clientes (garantida pela representação cromossômica) e capacidade de carga do veículo (garantida por reparo obrigatório no decodificador). Janela de tempo e energia são geridas via f₃.


# **2. Conformação do Cromossomo**
## **2.1 Representação híbrida**
O cromossomo é composto por dois segmentos concatenados. O primeiro é discreto e representa a sequência de visita aos clientes. O segundo é contínuo e representa as decisões de recarga parcial nas estações inseridas pelo decodificador.

|<p>Cromossomo = ( π  |  δ )</p><p></p><p>`  `π  —  Permutação de clientes</p><p>`         `Tipo:    vetor de inteiros, tamanho n</p><p>`         `Domínio: cada elemento ∈ {1, ..., n}, sem repetição</p><p>`         `Papel:   define a ordem em que os clientes são visitados.</p><p>`                  `A divisão em rotas é determinada pelo decodificador</p><p>`                  `com base na capacidade de carga — não há separadores</p><p>`                  `explícitos no cromossomo.</p><p></p><p>`  `δ  —  Quantidades de recarga</p><p>`         `Tipo:    vetor de reais, tamanho R</p><p>`         `Domínio: cada elemento ∈ [0, 1]</p><p>`         `Papel:   δ\_i define a fração de recarga da i-ésima estação</p><p>`                  `inserida pelo decodificador, na ordem de inserção.</p><p>`                  `δ\_i = 0.0 → sem recarga  |  δ\_i = 1.0 → recarga total</p><p></p><p>`  `R  —  Tamanho fixo do vetor δ</p><p>`         `Valor conservador: R = n</p><p>`         `Justificativa: no limite, uma estação pode ser inserida antes</p><p>`         `de cada cliente. Na prática, o número de inserções é muito</p><p>`         `menor. Posições de δ não utilizadas são ignoradas.</p>|
| :- |

## **2.2 Exemplo com n = 6 clientes**

|<p>n = 6 clientes  (IDs 1 a 6)  |  R = 6</p><p></p><p>π = [ 3,  1,  5,  2,  6,  4 ]</p><p>δ = [ 0.9, 0.5, 0.3, 0.8, 0.6, 0.4 ]</p><p></p><p>O decodificador lê π da esquerda para a direita.</p><p>Sempre que insere uma estação de recarga, consome o próximo δ disponível.</p><p></p><p>Exemplo de execução parcial:</p><p></p><p>`  `posição = depósito, SoC = Q, idx\_δ = 0</p><p></p><p>`  `→ Próximo cliente: 3</p><p>`    `Energia necessária para depósito→3: 20 u.e.</p><p>`    `SoC atual: 50 u.e.  →  suficiente. Sem inserção de estação.</p><p>`    `Viaja para 3. SoC = 30.</p><p></p><p>`  `→ Próximo cliente: 1</p><p>`    `Energia necessária para 3→1: 35 u.e.</p><p>`    `SoC atual: 30 u.e.  →  INSUFICIENTE.</p><p>`    `Busca estação alcançável. Encontra estação f2 (desvio mínimo).</p><p>`    `Viaja até f2. SoC = 30 - 12 = 18.</p><p>`    `Recarrega com δ[0] = 0.9:</p><p>`      `energia\_recarregada = 0.9 × (50 - 18) = 28.8</p><p>`      `SoC = 18 + 28.8 = 46.8</p><p>`      `idx\_δ = 1</p><p>`    `Viaja de f2 para cliente 1.</p><p></p><p>`  `→ Próximo cliente: 5</p><p>`    `Energia necessária: 40 u.e.</p><p>`    `SoC atual: 22 u.e.  →  INSUFICIENTE.</p><p>`    `Nenhuma estação alcançável a partir do estado atual.</p><p>`    `cv\_energia += (40 - 22) = 18  ←  déficit registrado.</p><p>`    `Continua mesmo assim. SoC = max(22 - 40, 0) = 0.</p><p>`    `(déficit já foi contabilizado; SoC interno travado em 0)</p><p></p><p>  ... e assim por diante para os clientes restantes.</p>|
| :- |

## **2.3 Propriedades da representação**
- A divisão em rotas é implícita: o decodificador abre nova rota sempre que a capacidade de carga estiver esgotada, sem intervenção do cromossomo.
- Viabilidade é intrínseca ao par (π, δ): dado um decodificador fixo e determinístico, o mesmo cromossomo produz sempre a mesma rota e a mesma avaliação de viabilidade.
- O vetor δ é a variável que controla o gradiente de violação energética: valores baixos de δ produzem inviabilidade paramétrica; a estrutura de π pode produzir inviabilidade estrutural independentemente de δ.
- Operadores genéticos padrão (OX para π, SBX ou perturbação uniforme para δ) são aplicáveis diretamente sem lógica especial de reparo de cromossomo.



# **3. Pseudocódigo Completo do Decodificador**
## **3.1 Dados de entrada**

|<p>ENTRADAS</p><p>────────────────────────────────────────────────────────────</p><p>Instância:</p><p>`  `C         conjunto de clientes j com atributos:</p><p>`              `(x\_j, y\_j, dem\_j, e\_j, l\_j, s\_j)</p><p>`              `dem = demanda, e = abertura TW, l = fechamento TW</p><p>`              `s   = tempo de serviço</p><p>`  `F         conjunto de estações de recarga f com (x\_f, y\_f)</p><p>`  `d         depósito com (x\_d, y\_d, e\_0, l\_0)</p><p>`  `Q\_carga   capacidade máxima de carga do veículo</p><p>`  `Q\_energy  capacidade máxima da bateria (unidades de energia)</p><p>`  `r         taxa de consumo energético por unidade de distância</p><p>`  `g         taxa de recarga (unidades de energia por unidade de tempo)</p><p>`  `v         velocidade do veículo (unidades de distância por tempo)</p><p></p><p>Cromossomo:</p><p>`  `π         permutação de clientes [c\_1, c\_2, ..., c\_n]</p><p>`  `δ         vetor de recargas [δ\_1, ..., δ\_R], δ\_i ∈ [0,1]</p><p></p><p>Auxiliares:</p><p>`  `dist(a,b) distância euclidiana entre nós a e b</p><p>`  `tempo\_recarga(e) = e / g   (tempo para recarregar e unidades)</p>|
| :- |

## **3.2 Inicialização do estado**

|<p>INICIALIZAÇÃO</p><p>────────────────────────────────────────────────────────────</p><p>rotas         ← []              lista de rotas completas</p><p>rota\_atual    ← [depósito]      rota em construção</p><p></p><p>SoC           ← Q\_energy        bateria cheia</p><p>tempo         ← e\_0             horário de saída do depósito</p><p>carga         ← 0              veículo vazio</p><p>pos           ← depósito</p><p></p><p>idx\_δ         ← 0              próximo δ disponível</p><p></p><p>cv\_energia    ← 0.0</p><p>cv\_tw         ← 0.0</p><p>f1\_custo      ← 0.0</p><p>f2\_energia    ← 0.0</p>|
| :- |

## **3.3 Loop principal — processamento de cada cliente**

|<p>**Nota sobre a ordem das verificações**</p><p>A ordem abaixo é a corrigida em relação à versão anterior: a verificação de capacidade de carga ocorre ANTES de qualquer cálculo de viagem. Isso garante que, quando uma nova rota é aberta, o estado (SoC, tempo, carga) é reiniciado antes do cálculo energético do primeiro arco da nova rota.</p>|
| :- |

|<p>PARA cada cliente c\_j em π:   ← j = 1 até n</p><p></p><p>`  `┌─────────────────────────────────────────────────────────┐</p><p>`  `│ PASSO 1 — VERIFICAR CAPACIDADE DE CARGA                 │</p><p>`  `└─────────────────────────────────────────────────────────┘</p><p></p><p>`  `SE (carga + dem\_j) > Q\_carga:</p><p></p><p>`    `── Fechar rota atual ──</p><p>`    `[chamar SUBROTINA: retornar\_ao\_depósito(pos, SoC, tempo, idx\_δ)]</p><p>`    `← ver Seção 3.4 para a subrotina de retorno</p><p></p><p>`    `rota\_atual.append(depósito)</p><p>`    `rotas.append(rota\_atual)</p><p></p><p>`    `── Abrir nova rota com estado reiniciado ──</p><p>`    `rota\_atual ← [depósito]</p><p>`    `SoC        ← Q\_energy</p><p>`    `tempo      ← e\_0       ← ou tempo de chegada ao depósito se TW é absoluta</p><p>`    `carga      ← 0</p><p>`    `pos        ← depósito</p><p></p><p></p><p>`  `┌─────────────────────────────────────────────────────────┐</p><p>`  `│ PASSO 2 — VERIFICAR ENERGIA E INSERIR ESTAÇÃO SE NECES. │</p><p>`  `└─────────────────────────────────────────────────────────┘</p><p></p><p>`  `energia\_necessária ← r · dist(pos, c\_j)</p><p></p><p>`  `SE energia\_necessária > SoC:</p><p></p><p>`    `melhor\_f   ← null</p><p>`    `menor\_desv ← +∞</p><p></p><p>`    `PARA cada estação f em F:</p><p>`      `e\_pos\_f ← r · dist(pos, f)</p><p>`      `e\_f\_cj  ← r · dist(f, c\_j)</p><p></p><p>`      `SE e\_pos\_f > SoC:  CONTINUAR  ← não alcançamos f com SoC atual</p><p></p><p>`      `soc\_em\_f       ← SoC - e\_pos\_f</p><p>`      `δ\_usar         ← δ[idx\_δ]   se idx\_δ < R  senão 1.0</p><p>`      `soc\_pós\_recarga ← soc\_em\_f + δ\_usar · (Q\_energy - soc\_em\_f)</p><p></p><p>`      `SE soc\_pós\_recarga < e\_f\_cj:  CONTINUAR  ← mesmo recarregando não</p><p>`                                                   `chegamos a c\_j</p><p></p><p>`      `desv ← dist(pos,f) + dist(f,c\_j) - dist(pos,c\_j)</p><p>`      `SE desv < menor\_desv:</p><p>`        `menor\_desv ← desv</p><p>`        `melhor\_f   ← f</p><p></p><p>`    `SE melhor\_f ≠ null:</p><p></p><p>`      `── Viajar até a estação ──</p><p>`      `d\_pos\_f      ← dist(pos, melhor\_f)</p><p>`      `f1\_custo    += d\_pos\_f</p><p>`      `f2\_energia  += r · d\_pos\_f</p><p>`      `SoC         -= r · d\_pos\_f</p><p>`      `tempo       += d\_pos\_f / v</p><p></p><p>`      `── Recarregar ──</p><p>`      `δ\_i          ← δ[idx\_δ]   se idx\_δ < R  senão 1.0</p><p>`      `e\_recarg     ← δ\_i · (Q\_energy - SoC)</p><p>`      `SoC         += e\_recarg</p><p>`      `tempo       += e\_recarg / g</p><p>`      `idx\_δ       += 1</p><p></p><p>`      `rota\_atual.append(melhor\_f)</p><p>`      `pos          ← melhor\_f</p><p></p><p>`    `SENÃO:  ← nenhuma estação alcançável</p><p></p><p>`      `déficit      ← energia\_necessária - SoC</p><p>`      `cv\_energia  += déficit</p><p>`      `← NÃO interromper. A rota continua.</p><p>`      `← SoC permanece negativo conceitualmente mas é travado em 0</p><p>`        `para os cálculos subsequentes da mesma rota.</p><p>`      `SoC          ← 0</p><p></p><p></p><p>`  `┌─────────────────────────────────────────────────────────┐</p><p>`  `│ PASSO 3 — VIAJAR ATÉ O CLIENTE                          │</p><p>`  `└─────────────────────────────────────────────────────────┘</p><p></p><p>`  `d\_pos\_cj    ← dist(pos, c\_j)</p><p>`  `f1\_custo   += d\_pos\_cj</p><p>`  `f2\_energia += r · d\_pos\_cj</p><p>`  `SoC        -= r · d\_pos\_cj</p><p>`  `SoC         ← max(SoC, 0)   ← travar em zero; déficit já contabilizado</p><p>`  `tempo      += d\_pos\_cj / v</p><p>`  `pos         ← c\_j</p><p></p><p></p><p>`  `┌─────────────────────────────────────────────────────────┐</p><p>`  `│ PASSO 4 — VERIFICAR JANELA DE TEMPO                     │</p><p>`  `└─────────────────────────────────────────────────────────┘</p><p></p><p>`  `SE tempo < e\_j:</p><p>`    `tempo ← e\_j     ← veículo espera. Sem penalidade.</p><p></p><p>`  `SE tempo > l\_j:</p><p>`    `cv\_tw += (tempo - l\_j)</p><p></p><p></p><p>`  `┌─────────────────────────────────────────────────────────┐</p><p>`  `│ PASSO 5 — SERVIR O CLIENTE                              │</p><p>`  `└─────────────────────────────────────────────────────────┘</p><p></p><p>`  `tempo += s\_j</p><p>`  `carga += dem\_j</p><p>`  `rota\_atual.append(c\_j)</p><p></p><p>FIM DO LOOP</p>|
| :- |

## **3.4 Subrotina: retornar ao depósito**

Esta subrotina é chamada tanto ao fechar uma rota por capacidade (Passo 1) quanto ao fechar a última rota ao final do loop. Ela reutiliza a mesma lógica de inserção de estação do Passo 2, com destino = depósito.

|<p>SUBROTINA retornar\_ao\_depósito(pos, SoC, tempo, idx\_δ):</p><p>────────────────────────────────────────────────────────────</p><p>`  `energia\_necessária ← r · dist(pos, depósito)</p><p></p><p>`  `SE energia\_necessária > SoC:</p><p></p><p>`    `melhor\_f   ← null</p><p>`    `menor\_desv ← +∞</p><p></p><p>`    `PARA cada estação f em F:</p><p>`      `e\_pos\_f ← r · dist(pos, f)</p><p>`      `e\_f\_dep ← r · dist(f, depósito)</p><p></p><p>`      `SE e\_pos\_f > SoC:  CONTINUAR</p><p></p><p>`      `soc\_em\_f        ← SoC - e\_pos\_f</p><p>`      `δ\_usar          ← δ[idx\_δ]  se idx\_δ < R  senão 1.0</p><p>`      `soc\_pós\_recarga ← soc\_em\_f + δ\_usar · (Q\_energy - soc\_em\_f)</p><p></p><p>`      `SE soc\_pós\_recarga < e\_f\_dep:  CONTINUAR</p><p></p><p>`      `desv ← dist(pos,f) + dist(f,depósito) - dist(pos,depósito)</p><p>`      `SE desv < menor\_desv:</p><p>`        `menor\_desv ← desv</p><p>`        `melhor\_f   ← f</p><p></p><p>`    `SE melhor\_f ≠ null:</p><p>`      `d\_pos\_f      ← dist(pos, melhor\_f)</p><p>`      `f1\_custo    += d\_pos\_f</p><p>`      `f2\_energia  += r · d\_pos\_f</p><p>`      `SoC         -= r · d\_pos\_f</p><p>`      `tempo       += d\_pos\_f / v</p><p></p><p>`      `δ\_i     ← δ[idx\_δ]  se idx\_δ < R  senão 1.0</p><p>`      `e\_recarg ← δ\_i · (Q\_energy - SoC)</p><p>`      `SoC     += e\_recarg</p><p>`      `tempo   += e\_recarg / g</p><p>`      `idx\_δ   += 1</p><p></p><p>`      `rota\_atual.append(melhor\_f)</p><p>`      `pos ← melhor\_f</p><p></p><p>`    `SENÃO:</p><p>`      `déficit     ← energia\_necessária - SoC</p><p>`      `cv\_energia += déficit</p><p>`      `SoC         ← 0</p><p></p><p>`  `── Viajar ao depósito ──</p><p>`  `d\_pos\_dep   ← dist(pos, depósito)</p><p>`  `f1\_custo   += d\_pos\_dep</p><p>`  `f2\_energia += r · d\_pos\_dep</p><p>`  `SoC        -= r · d\_pos\_dep</p><p>`  `SoC         ← max(SoC, 0)</p><p>`  `tempo      += d\_pos\_dep / v</p><p>`  `pos         ← depósito</p><p></p><p>FIM DA SUBROTINA</p>|
| :- |

## **3.5 Fechamento e retorno**

|<p>FECHAMENTO</p><p>────────────────────────────────────────────────────────────</p><p>── Fechar última rota ──</p><p>[chamar SUBROTINA: retornar\_ao\_depósito(pos, SoC, tempo, idx\_δ)]</p><p></p><p>rota\_atual.append(depósito)</p><p>rotas.append(rota\_atual)</p><p></p><p>── Calcular f₃ ──</p><p>w     ← peso de escala (calibrado por instância)</p><p>f3    ← cv\_energia + w · cv\_tw</p><p></p><p>RETORNAR:</p><p>`  `rotas                 estrutura física de todas as rotas</p><p>`  `f1 = f1\_custo         distância total</p><p>`  `f2 = f2\_energia       energia total consumida</p><p>`  `f3 = f3              violação agregada (0 = totalmente factível)</p><p>`  `cv\_energia           componente energética de f3 (para diagnóstico)</p><p>`  `cv\_tw                componente temporal de f3  (para diagnóstico)</p>|
| :- |




# **4. Casos Limite**
Os casos abaixo cobrem situações que ocorrem com frequência na prática e que, se não tratadas explicitamente, produzem comportamento incorreto ou resultados não-comparáveis entre execuções.

## **Caso 1 — idx\_δ esgota antes do fim da decodificação**
Ocorre quando o número de inserções de estação supera R. Com R = n é improvável, mas possível em instâncias muito densas com recarga parcial baixa.

|<p>SE idx\_δ >= R:</p><p>`  `δ\_usar ← 1.0     ← recarga total como fallback</p><p>`                    `← garante que a decodificação não aborta</p><p>`                    `← o comportamento é conservador: melhor errar</p><p>`                       `para factível do que deixar o veículo parado</p>|
| :- |

|<p>**Por que recarga total e não zero?**</p><p>Um fallback de δ = 0 faria o veículo recarregar zero energia, tornando a inserção inútil e possivelmente acumulando déficit desnecessário. O fallback de δ = 1.0 é conservador e garante continuidade da rota. Se R = n, esse caso não deve ocorrer em condições normais — sua ocorrência é um sinal de que a instância tem uma topologia incomum e vale registrar como dado de diagnóstico.</p>|
| :- |

## **Caso 2 — δ\_i resulta em recarga insuficiente para alcançar o destino**
A estação é selecionada com base na verificação de que, após recarregar com δ[idx\_δ], o veículo consegue alcançar o próximo destino (Passo 2). Se δ é muito baixo, a estação pode não passar nessa verificação e ser descartada como candidata.

|<p>Na seleção de estação (Passo 2), a verificação:</p><p></p><p>`  `soc\_pós\_recarga ← soc\_em\_f + δ\_usar · (Q\_energy - soc\_em\_f)</p><p>`  `SE soc\_pós\_recarga < e\_f\_cj:  CONTINUAR</p><p></p><p>já elimina esses candidatos. O δ baixo resulta em nenhuma</p><p>estação qualificada → déficit registrado em cv\_energia.</p><p></p><p>NÃO corrigir δ automaticamente.</p><p>← Corrigir δ seria equivalente a um decoder inteligente que</p><p>`  `elimina inviabilidade paramétrica, destruindo o gradiente de</p><p>`  `violação que a técnica de inviáveis depende.</p>|
| :- |

|<p>**Ponto central do trabalho**</p><p>A decisão de não corrigir δ automaticamente é a escolha de design mais importante do decodificador. É ela que preserva a inviabilidade paramétrica como informação genuína sobre trade-offs de recarga, tornando os inviáveis informativos para o arquivo de diversidade. Esta escolha deve ser explicitamente justificada e documentada no texto do TCC, pois é a principal resposta à crítica de que "um decoder inteligente resolveria o problema".</p>|
| :- |

## **Caso 3 — SoC vai abaixo de zero**
Quando há déficit energético e o decodificador continua a rota, os cálculos subsequentes de consumo subtrairiam de um SoC negativo, acumulando déficit incorretamente.

|<p>Após registrar déficit e continuar (Passo 2, ramo SENÃO):</p><p>`  `SoC ← 0</p><p></p><p>Após cada arco percorrido (Passo 3 e subrotina de retorno):</p><p>`  `SoC ← max(SoC - r · dist(pos, destino), 0)</p><p></p><p>Isso garante:</p><p>`  `(a) o déficit de cada arco é contabilizado uma única vez,</p><p>`      `no momento em que é detectado</p><p>`  `(b) os arcos seguintes partem de SoC = 0, representando</p><p>`      `o pior caso realista (veículo chegou com bateria zerada)</p><p>`  `(c) os valores de f2\_energia acumulam corretamente o consumo</p><p>`      `físico, independente da viabilidade</p>|
| :- |

## **Caso 4 — Nenhuma rota aberta quando capacidade estoura no primeiro cliente**
Se o primeiro cliente de π tem demanda maior que Q\_carga, a verificação do Passo 1 tenta fechar a rota atual, que ainda é [depósito] — não há clientes para visitar antes de retornar.

|<p>SE rota\_atual == [depósito] e capacidade estoura:</p><p>`  `← situação impossível se a instância for válida:</p><p>`    `toda instância bem formada tem dem\_j <= Q\_carga para todo j</p><p></p><p>SE verificado durante validação da instância:</p><p>`  `Rejeitar instância como malformada antes de executar o algoritmo.</p><p></p><p>Defesa: as instâncias Schneider garantem esta propriedade por</p><p>construção. Não é necessário tratar em runtime, mas vale</p><p>adicionar uma asserção durante o carregamento da instância.</p>|
| :- |

## **Caso 5 — Dois ou mais clientes consecutivos sem nenhuma estação no caminho**
A rota pode acumular múltiplos déficits em arcos consecutivos. O decodificador trava SoC em 0 após o primeiro déficit, portanto os arcos seguintes contribuem com déficit igual ao consumo completo de cada arco.

|<p>Arco 1: SoC = 5,  consumo = 20  → déficit = 15, SoC ← 0</p><p>Arco 2: SoC = 0,  consumo = 18  → déficit = 18, SoC ← 0</p><p>Arco 3: SoC = 0,  consumo = 12  → déficit = 12, SoC ← 0</p><p></p><p>cv\_energia total = 15 + 18 + 12 = 45</p><p></p><p>Este comportamento é correto e desejável:</p><p>`  `→ cv\_energia reflete fielmente a gravidade da inviabilidade</p><p>`  `→ cromossomos com estrutura muito ruim acumulam cv\_energia alto</p><p>`     `e são naturalmente menos preferidos no arquivo DA</p><p>`  `→ o gradiente de violação é monotônico com a distância à fronteira</p>|
| :- |

## **Caso 6 — Veículo chega antes da abertura da janela de tempo (espera)**

|<p>SE tempo\_chegada < e\_j:</p><p>`  `tempo ← e\_j    ← aguarda abertura. Nenhuma penalidade em f3.</p><p></p><p>Observação: o tempo de espera aumenta o tempo total da rota,</p><p>o que pode propagar violações de TW para clientes posteriores.</p><p>Esse efeito é capturado naturalmente pelo cálculo sequencial de</p><p>tempo — não é necessário nenhum tratamento especial.</p>|
| :- |

## **Caso 7 — Veículo retorna ao depósito fora da janela de tempo do depósito**

|<p>O depósito tem janela [e\_0, l\_0].</p><p>O retorno após l\_0 é uma violação de TW do depósito.</p><p></p><p>Opção A (mais comum na literatura Schneider):</p><p>`  `Tratar como violação de TW do cliente, acumulando em cv\_tw.</p><p>`  `cv\_tw += max(0, tempo\_retorno - l\_0)</p><p></p><p>Opção B (mais restritiva):</p><p>`  `Tratar como restrição hard: se a rota retorna após l\_0,</p><p>`  `forçar nova rota (não aplicável — já estamos no retorno).</p><p>`  `Na prática, Opção A é padrão nas instâncias Schneider.</p>|
| :- |


*— fim da especificação —*
Especificação Técnica — EVRPTW-PR com Gestão de Soluções Inviáveis
