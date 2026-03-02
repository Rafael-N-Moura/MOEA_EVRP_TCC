A seguir está um documento conceitual, em estilo “especificação teórica”, de como implementar uma variante do NSGA‑II para EVRP multiobjetivo com janelas de tempo e recarga parcial, incorporando exploração explícita de inviáveis. Cada decisão é ancorada na literatura correspondente.

***

## 1. Estrutura geral do algoritmo

### 1.1. Bases teóricas

A variante proposta combina:

- Estrutura de seleção e ordenação do **NSGA‑II clássico** (ranking por nondominance + crowding distance) para o arquivo de soluções factíveis. [web.njit](https://web.njit.edu/~horacio/Math451H/download/2002-6-2-DEB-NSGA-II.pdf)
- Conceito de **duas populações/arquivos** (Convergence Archive e Diversity Archive) do C‑TAEA, para separar foco em convergência e diversidade (incluindo regiões inviáveis). [arxiv](https://arxiv.org/abs/1711.07907)
- Ideia de **manter uma fração de indivíduos inviáveis** com bom compromisso custo–violação, inspirada em IDEA e variantes infeasibility‑driven. [openreview](https://openreview.net/forum?id=Gnk8Eu7icl)
- Ideia de **dois pools para VRP**, com um pool principal de soluções (quase) factíveis e um pool de trabalho que aceita inviáveis profundos, do método Deep Infeasibility Exploration para VRPs. [sin.put.poznan](https://sin.put.poznan.pl/publications/details/i48013)

### 1.2. Estrutura em alto nível

1. Inicialização: gerar população \(P_0\) misturando soluções factíveis e algumas propositalmente inviáveis (pela forma de construção).  
2. Em cada geração \(t\):  
   - Avaliar indivíduos em termos de:
     - objetivos \(f_1, f_2\) (por exemplo, distância e atraso),  
     - violação agregada de restrições \(CV(x)\).  
   - Atualizar dois arquivos:
     - **Arquivo factível \(A_F\)** (Convergence Archive).  
     - **Arquivo inviável \(A_I\)** (Diversity Archive de inviáveis).  
   - Aplicar **mating restrito**: selecionar pais de \(A_F\) e \(A_I\) segundo regra inspirada em C‑TAEA.  
   - Aplicar operadores de crossover/mutação e reparo leve.  
   - Reavaliar descendentes e atualizar arquivos.  

***

## 2. Modelo de problema e objetivos

### 2.1. EVRPTW com recarga parcial

- Conjunto de clientes com demandas, localização e janelas de tempo rígidas \([e_i,l_i]\).  
- Frota de EVs com capacidade de carga e bateria \(Q^{bat}\) (SOC máximo), com limite mínimo \(SOC_{min}\).  
- Estaçōes de recarga onde se pode recarregar parcialmente com taxa conhecida. [sciencedirect](https://www.sciencedirect.com/science/article/pii/S1364032121008455)

### 2.2. Objetivos multiobjetivo

Seguindo práticas de EVRPTW e VRPTW multiobjetivo:

- \(f_1(x)\): **distância total percorrida** (ou custo equivalente), objetivo clássico em VRP/EVRP. [theses.liacs](https://theses.liacs.nl/pdf/2023-2024-Al-NassarSSuzan.pdf)
- \(f_2(x)\): **atraso total em janelas de tempo**, \(f_2(x)=\sum_i \max(0,t_i-l_i)\), inspirado em modelos de VRPTW multiobjetivo que usam penalidades de tempo como objetivo separado. [apem-journal](http://apem-journal.org/Archives/2019/APEM14-2_201-212.pdf)

A bateria entra como restrição de viabilidade (via \(CV\)), não como objetivo, para enfatizar a hipótese de ótimos na fronteira de SOC.

***

## 3. Representação e avaliação

### 3.1. Codificação da solução

- Representação padrão de EVRP:  
  - cromossomo como **sequência de clientes** com separadores de veículo,  
  - ou “giant tour” que depois é particionado em rotas com inserção de recargas. [cse.unr](https://www.cse.unr.edu/~sushil/class/gas/papers/AGreedySearchBasedEAForVRP.pdf)
- As recargas podem ser inseridas via:
  - heurística de decodificação (inserindo estações quando SOC ameaça ficar < \(SOC_{min}\)),  
  - ou genes explícitos que representam paradas de recarga (mais pesado para TCC).

### 3.2. Avaliação de objetivos

Para cada indivíduo \(x\):

1. Decodificar cromossomo em rotas com recargas.  
2. Simular o percurso acumulando:
   - distância por arco,  
   - tempo de serviço e viagem,  
   - SOC (consumo e recarga) ao longo da rota.  
3. Calcular:
   - \(f_1(x)\): soma das distâncias percorridas,  
   - \(f_2(x)\): soma dos atrasos \(\max(0,t_i-l_i)\) em todos os clientes. [journals.plos](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0281131)

### 3.3. Violação de restrições

Definir um **constraint violation agregado** \(CV(x)\), como em CMOEAs e IDEA:

- Violação de bateria:
  \[
  CV_{SOC}(x) = \sum_{\text{arcos}} \max(0, SOC_{min}-SOC_{arc})
  \]
- Violação de janelas de tempo tratada como restrição (opcional, se quiser separar de atraso‑objetivo):
  \[
  CV_{TW}(x) = \sum_i \max(0, t_i - l_i - \Delta_{\max}),
  \]
  onde \(\Delta_{\max}\) é um atraso máximo “aceitável” antes de considerar inviável.  
- Outras restrições (capacidade, duração máxima de rota etc.) entram como termos adicionais.

Então:

\[
CV(x) = w_{SOC} CV_{SOC}(x) + w_{TW} CV_{TW}(x) + \dots
\]

Esse tipo de violação agregada é padrão em infeasibility‑driven EAs e em estudos sobre equilíbrio factível/inviável. [egr.msu](https://www.egr.msu.edu/~kdeb/papers/c2018002.pdf)

***

## 4. Organização das populações: dois arquivos

### 4.1. Arquivo factível \(A_F\) (Convergence Archive)

Inspirado no CA do C‑TAEA: [arxiv](https://arxiv.org/pdf/1711.07907.pdf)

- Conteúdo: indivíduos com \(CV(x)\) abaixo de um limiar \(\epsilon_F\) (de preferência zero, ou “quase zero” para permitir pequenas violações transitórias).  
- Tamanho fixo \(N_F\) (por exemplo, igual ao tamanho de população tradicional do NSGA‑II).  
- Atualização:
  - Unir \(A_F\) com a população de descendentes factíveis do passo anterior.  
  - Ordenar por ranking de nondominance em \((f_1,f_2)\).  
  - Dentro de cada front, aplicar crowding distance como em NSGA‑II para preservar diversidade. [sci2s.ugr](https://sci2s.ugr.es/sites/default/files/files/Teaching/OtherPostGraduateCourses/Metaheuristicas/Deb_NSGAII.pdf)
  - Preencher \(A_F\) com os indivíduos dos melhores fronts até atingir \(N_F\).

### 4.2. Arquivo inviável \(A_I\) (Diversity Archive)

Inspirado no DA de C‑TAEA e em IDEA: [core.ac](https://core.ac.uk/download/pdf/189350532.pdf)

- Conteúdo: indivíduos com \(CV(x) > \epsilon_F\).  
- Tamanho fixo \(N_I \approx \alpha N_F\), com \(\alpha\) entre 0,1 e 0,3 (10–30% da população), como sugerido em trabalhos infeasibility‑driven. [academia](https://www.academia.edu/74355006/Performance_of_infeasibility_driven_evolutionary_algorithm_IDEA_on_constrained_dynamic_single_objective_optimization_problems)
- Avaliação interna:
  - Considerar o vetor \((f_1,f_2,CV)\) para ordenação.  
- Atualização:
  - Unir \(A_I\) com os descendentes inviáveis.  
  - Aplicar ranking por nondominance em \((f_1,f_2,CV)\): inviáveis com menor violação e melhor desempenho em objetivos dominam os demais. [colab](https://colab.ws/articles/10.1109%2FCEC.2013.6557723)
  - Dentro de cada front, usar uma medida de diversidade (p.ex. crowding em \((f_1,f_2)\) ou em um grid) para evitar concentração.  
  - Preencher \(A_I\) com os melhores até \(N_I\).

Interpretação: \(A_I\) guarda inviáveis **próximos da fronteira factível** e/ou em regiões de objetivos pouco cobertas pelo \(A_F\), replicando a função de diversidade do DA em C‑TAEA. [arxiv](https://arxiv.org/pdf/1711.07907.pdf)

***

## 5. Seleção de pais (mating restrito)

### 5.1. Ideia de restricted mating do C‑TAEA

No C‑TAEA, o mating selection escolhe pais da CA e da DA de modo a:  
- priorizar CA quando a convergência ainda é fraca,  
- usar DA para fornecer diversidade em regiões pouco exploradas (inclusive inviáveis). [arxiv](https://arxiv.org/abs/1711.07907)

### 5.2. Adaptação para EVRP/EVRPTW

Definir uma regra simples, mas coerente:

1. Definir uma probabilidade dinâmica \(p_F(t)\) de escolher o primeiro pai em \(A_F\) (e \(1-p_F(t)\) em \(A_I\)), por exemplo:  
   - início da execução: \(p_F(0) \approx 0{,}5\), para incentivar bastante mating envolvendo inviáveis (fase tipo “push”).  
   - à medida que as gerações avançam, aumentar \(p_F(t)\) para 0,8–0,9, enfatizando cruzas entre factíveis (fase “pull”).  
   Isso ecoa o espírito de Push‑and‑Pull Search: primeiro empurrar para perto da fronteira ignorando restrições, depois puxar para dentro da região factível. [arxiv](https://arxiv.org/pdf/2103.06382.pdf)

2. Para cada cruzamento:
   - Sortear o primeiro pai de \(A_F\) com probabilidade \(p_F(t)\) (senão de \(A_I\)).  
   - Definir o segundo pai por uma regra de **proximidade em objetivos**:
     - se o primeiro pai veio de \(A_F\), escolher o segundo em \(A_I\) que esteja próximo em \((f_1,f_2)\) ou que seja “melhor” em um dos objetivos, como em restricted mating de C‑TAEA. [arxiv](https://arxiv.org/pdf/1711.07907.pdf)
     - se o primeiro pai veio de \(A_I\), fazer simétrico.

Racional: cruzar um factível (bem comportado) com um inviável de bom custo (que talvez viole SOC/TW) para gerar descendentes que combinem rota “curta” com maior respeito às restrições.

***

## 6. Operadores de crossover e mutação

### 6.1. Base: operadores de VRP

Usar operadores tradicionais de VRP, adaptando a partir de GAs para VRP/EVRP:

- Crossover do tipo:
  - OX, PMX, CX, ou  
  - operadores específicos de VRP como merge‑split, “edge assembly crossover” etc. [sciencedirect](https://www.sciencedirect.com/science/article/pii/S0305054803001588)
- Mutação:
  - swap de clientes,  
  - 2‑opt, Or‑opt, relocate, cross‑exchange, aplicados como mutações estruturadas. [semanticscholar](https://www.semanticscholar.org/paper/An-Or-opt-NSGA-II-algorithm-for-multi-objective-Xu-Fan/d71a6ce8cf4a754e753587712b6be9d7702da6b4)

### 6.2. Permitir geração de inviáveis

Importante: **não restringir** os operadores para manter viabilidade a qualquer custo. Seguindo estudos que mostram que soluções inviáveis podem ser úteis se bem tratadas, é desejável que crossover/mutação possam produzir rotas que:

- extrapolem janelas de tempo,  
- ultrapassem o SOC mínimo,  
- excedam distância/tempo máximo, desde que isso crie novas estruturas de rota interessantes. [arxiv](https://arxiv.org/abs/2203.03512)

Essa escolha é coerente com:

- Deep Infeasibility Exploration em VRP: permitir perturbações que levam a soluções profundamente inviáveis, desde que tragam ganhos de custo e depois sejam “reparadas” quando necessário. [sin.put.poznan](https://sin.put.poznan.pl/publications/details/i48013)
- Estudo de utilidade de inviáveis em EAs: inviáveis podem guiar o algoritmo a regiões onde factíveis de alta qualidade estão “escondidas”. [colab](https://colab.ws/articles/10.1109%2FCEC.2013.6557723)

***

## 7. Estratégias de reparo e restauração de viabilidade

Embora a filosofia seja manter inviáveis, é útil ter reparos leves:

- Heurísticas de **reparo local**:
  - se SOC < \(SOC_{min}\) num trecho, inserir uma recarga na estação mais próxima e recalcular,  
  - se excesso de atraso, tentar reordenar localmente clientes (2‑opt, relocate) para reduzir violação. [sciencedirect](https://www.sciencedirect.com/science/article/pii/S1364032121008455)
- Esses reparos podem ser aplicados:
  - sempre depois de crossover/mutação (heavy repair), ou  
  - apenas com certa probabilidade ou para indivíduos candidatos a entrar em \(A_F\) (repare apenas aqueles com \(CV\) pequeno o suficiente).

A literatura de VRP com deep infeasibility tipicamente mantém um **pool de trabalho** onde se explora soluções muito inviáveis, e só tenta restaurar viabilidade quando uma solução parece promissora em custo. [sin.put.poznan](https://sin.put.poznan.pl/publications/details/i48013)
Sua variante pode replicar isso usando \(A_I\) como “pool de trabalho” e reparos somente quando uma solução está prestes a migrar para \(A_F\) (por exemplo, quando \(CV\) cai abaixo de um limiar).

***

## 8. Controle da fração de inviáveis e do CV

### 8.1. Fração de inviáveis

Como discutido:

- Tamanho de \(A_I\): \(\alpha N_F\), com \(\alpha\) entre 0,1 e 0,3, inspirado em IDEA e na literatura de infeasibility‑driven. [openreview](https://openreview.net/forum?id=Gnk8Eu7icl)
- Pode‑se experimentar:
  - \(\alpha\) fixo,  
  - ou \(\alpha(t)\) decrescente (mais inviáveis no início, menos no fim), seguindo o espírito de PPS (mais “push” no início, mais “pull” no fim). [scholars.cityu.edu](https://scholars.cityu.edu.hk/en/publications/push-and-pull-search-for-solving-constrained-multi-objective-opti/)

### 8.2. Limiar de quase‑viabilidade \(\epsilon_F\)

- Em vez de exigir \(CV=0\) para \(A_F\), pode‑se aceitar \(CV \leq \epsilon_F\) (por exemplo, pequenas violações de janelas) para aumentar robustez e suavizar a transição entre arquivos, técnica usada em métodos que misturam hard e soft constraints. [semanticscholar](https://www.semanticscholar.org/paper/Solving-problems-with-a-mix-of-hard-and-soft-using-Singh-Asafuddoula/f70fa1cbdb345e13311da5326170d112d3533e5e)
- Esse \(\epsilon_F\) pode decrescer ao longo das gerações.

***

## 9. Critérios de parada e avaliação de desempenho

- Critérios de parada: número fixo de gerações ou avaliações, comum em NSGA‑II.  
- Avaliação de desempenho:
  - Medidas de qualidade da frente: hipervolume, IGD, comparando sua variante com um NSGA‑II “tradicional” que usa penalidade simples. [web.njit](https://web.njit.edu/~horacio/Math451H/download/2002-6-2-DEB-NSGA-II.pdf)
  - Medidas específicas de EVRP:
    - distribuição do SOC mínimo observado nas rotas das soluções não dominadas (para verificar a hipótese de “bateria quase esgotada”),  
    - número de clientes atrasados, atrasos médios, etc. [journals.plos](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0281131)

***

## 10. Resumo das origens teóricas de cada componente

- **Dois arquivos \(A_F\)/\(A_I\)**: diretamente inspirado em C‑TAEA (Convergence/Diversity Archive) para CMOPs. [core.ac](https://core.ac.uk/download/pdf/189350532.pdf)
- **Fração controlada de inviáveis e ordenação por \((f_1,f_2,CV)\)**: conceito de Infeasibility Driven Evolutionary Algorithm (IDEA) e trabalhos sobre balancear factíveis/inviáveis. [egr.msu](https://www.egr.msu.edu/~kdeb/papers/c2018002.pdf)
- **Mating restrito entre arquivos**: “restricted mating selection mechanism” de C‑TAEA, adaptado aqui para cruzar factíveis e inviáveis no contexto de EVRP. [arxiv](https://arxiv.org/abs/1711.07907)
- **Permitir operadores que gerem inviáveis**: suportado por estudos sobre utilidade de soluções inviáveis em EAs e pela abordagem Deep Infeasibility Exploration em VRPs, que deliberadamente navega regiões inviáveis para achar melhores soluções. [arxiv](https://arxiv.org/abs/2203.03512)
- **Fase push–pull implícita (mais inviáveis no início, mais factíveis no fim)**: inspirado em Push and Pull Search para CMOPs, que separa fases de exploração sem restrição e exploração com restrição. [arxiv](https://arxiv.org/pdf/2103.06382.pdf)
- **Modelagem de objetivos (distância e atraso)**: segue formulações de VRPTW/EVRPTW multiobjetivo existentes, onde distância/custo e penalidades de tempo são objetivos explícitos. [pmc.ncbi.nlm.nih](https://pmc.ncbi.nlm.nih.gov/articles/PMC9568933/)

Com esse documento, você tem um blueprint teórico coerente para a variante de NSGA‑II no EVRPTW com recarga parcial, sempre com os pontos chave amarrados à literatura de constrained multiobjective EAs e VRP.