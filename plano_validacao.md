**Nível 1 — O decodificador produz soluções fisicamente válidas?**

Esse é o teste mais fundamental. Você precisa de um módulo *separado* do decodificador — um "auditor" independente — que recebe as rotas expandidas (com estações já inseridas) e verifica cada restrição mecanicamente. Se o auditor e o decodificador foram escritos por pessoas (ou modelos) diferentes, isso dá garantia forte de que um bug em um seria detectado pelo outro.

O auditor verifica, para cada rota: a bateria nunca fica negativa em nenhum ponto (simulando o consumo arco a arco); nenhum cliente é atendido após seu DueDate (t_chegada ≤ l[cliente]); a demanda total da rota não excede C; a rota começa e termina no depósito; o tempo de recarga está correto (g × (Q - bat_na_chegada) em cada estação). Para o conjunto de rotas: cada cliente aparece em exatamente uma rota; f1 = número de rotas; f2 = soma de todas as distâncias arco a arco; f3 = max dos tempos de retorno ao depósito.

O teste concreto: gere 1.000 permutações aleatórias para c101C5 (5 clientes — instantâneo). Para cada uma, rode o decodificador, depois rode o auditor na solução produzida. Se qualquer verificação falhar em qualquer permutação, há bug. Repita para r102C10 e rc103C15. Esse teste sozinho pega a maioria dos bugs de implementação.

**Nível 2 — Os valores numéricos batem com o Schneider?**

O paper de Schneider tem soluções ótimas (CPLEX) para as 36 instâncias pequenas na Table 3. Esses valores são ouro para validação. O teste é: para cada instância pequena, rode o NSGA-II com população grande (200) e muitas avaliações (50.000) por 5 runs. Na frente de Pareto resultante, identifique a solução com menor f2 entre as que têm f1 mínimo. Compare com a Table 3 do Schneider:

Para c101C5: Schneider obtém m=2, L=257.75. Sua solução deve ter pelo menos uma solução na frente com f1=2. O f2 correspondente deve ser ≥ 257.75 (ou muito próximo — uma margem de 1-2% é aceitável dado o decodificador greedy). Se f2 for *menor* que 257.75 com o mesmo número de veículos, há bug — seu decodificador está calculando distância errada ou violando alguma restrição silenciosamente.

Para c101C10: m=3, L=393.76. Para r102C10: m=3, L=249.19. Para r102C15: m=5, L=413.93. Para rc103C15: m=4, L=397.67. E assim por diante para todas as 36 instâncias pequenas.

Há uma nuance importante: o Schneider usa uma metaheurística dedicada (VNS/TS) altamente otimizada para EVRPTW mono-objetivo. Seu decodificador é greedy com inserção de estações por score balanceado, alimentado por algoritmos multiobjetivo genéricos. É esperado que suas soluções tenham f2 algo acima do BKS. O que *não* é aceitável: f1 sistematicamente maior que o BKS (significaria que o Split ou o InsertStations estão gerando rotas demais) ou f2 dramaticamente acima (>20% — significaria que a inserção de estações está fazendo desvios absurdos).

Concretamente, eu separaria os resultados em três categorias. "Verde": f1 = f1_BKS e f2 está até 10% acima do BKS — implementação provavelmente correta. "Amarelo": f1 = f1_BKS mas f2 está 10-20% acima — implementação possivelmente correta mas decodificador subótimo; investigar o InsertStations. "Vermelho": f1 > f1_BKS sistematicamente ou f2 > 20% acima — provável bug no Split, no InsertStations ou no cálculo de distâncias.

**Nível 3 — As instâncias grandes também são consistentes?**

A Table 4 do Schneider tem BKS para todas as 56 instâncias de 100 clientes. Rode 5 runs de NSGA-II em 6 instâncias representativas: c101_21 (BKS: m=12, L=1053.83), c201_21 (m=4, L=645.16), r101_21 (m=18, L=1670.80), r201_21 (m=3, L=1264.82), rc101_21 (m=16, L=1731.07), rc201_21 (m=4, L=1444.94). 

A mesma lógica de Verde/Amarelo/Vermelho se aplica. Nas instâncias grandes, a margem aceitável para f2 é maior (até 15-20%) porque o espaço de busca é muito maior e o decodificador greedy tem mais impacto. Mas f1 deve estar próximo — se Schneider encontra 12 veículos para c101_21 e você consistentemente encontra 15+, algo está errado.

**Nível 4 — Os três algoritmos funcionam diferentemente?**

Esse teste verifica se a integração com pymoo está correta para os três algoritmos (não apenas NSGA-II). Rode 5 runs de cada algoritmo (NSGA-II, MOEA/D, SMS-EMOA) em c101C10 com 20.000 avaliações. Verifique três coisas. Primeira: os três algoritmos produzem frentes de Pareto com soluções viáveis (o auditor do Nível 1 não encontra violações em nenhuma solução de nenhuma frente). Segunda: os HVs são positivos e finitos para os três. Terceira: os resultados são *diferentes* entre algoritmos — se NSGA-II, MOEA/D e SMS-EMOA produzem HVs idênticos, provavelmente o pymoo está usando o mesmo algoritmo internamente (erro de configuração).

**Nível 5 — Smoke tests das hipóteses (sanity checks)**

Esses testes não validam a implementação — validam se o setup experimental produz resultados interpretáveis antes de investir nas 5.040 execuções. São baratos e informativos.

Teste de frente tri-objetivo: rode 10 runs de NSGA-II em r201_21 (instância com regime 2xx onde a variação de f1 deve ser maior). Plote as frentes obtidas em 3D. Verifique que: existem soluções com valores diferentes de f1 (a frente é estratificada — relevante para Hnova); f2 e f3 não são perfeitamente correlacionados (a frente não colapsa em 2D — relevante para H2); existe variação entre runs (o HV tem desvio padrão > 0 — relevante para Hrobustez).

Teste de convergência: rode 1 run de cada algoritmo em c101_21 com registro de HV a cada 5.000 avaliações. Plote as três curvas. Verifique que: o HV cresce ao longo do tempo para os três (estão convergindo, não estagnados); SMS-EMOA tem curva com formato diferente dos outros dois (relevante para Hconv); a curva estabiliza em algum ponto (valida o critério de parada).

Teste de viabilidade: rode 5 runs de NSGA-II em r101_21 (tw_ratio=0,044, a mais restrita). Verifique a taxa de viabilidade na população final. Se for > 50%, o tratamento de infeasibilidade está funcionando. Se for 0%, verifique se o mecanismo de dominância baseada em feasibilidade está implementado corretamente — com [∞,∞,∞] a população ficaria presa; com violação gradual, deveria convergir para viabilidade.

