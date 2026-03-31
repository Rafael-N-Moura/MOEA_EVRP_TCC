Vou estruturar isso de forma clara e completa para que sirva como guia de implementação.

---

**O que foi implementado anteriormente e por que não funcionou**

A tentativa anterior implementou uma abordagem de Merge → Sort → Re-split. O Clarke-Wright merge fundiu rotas quasi-singleton em rotas maiores respeitando capacidade. Depois, os clientes dentro de cada rota merged foram reordenados por ready_time. Por fim, um re-split com verificação de TW quebrou as rotas longas em sub-rotas viáveis.

O problema é circular: o merge consolida rotas (reduzindo f1), mas o re-split as quebra novamente porque a reordenação por ready_time não garante compatibilidade sequencial de janelas de tempo — dois clientes próximos em ready_time podem estar geograficamente distantes, gerando tempos de viagem que violam as janelas seguintes. O resultado é que a busca local desfaz seu próprio trabalho: de 61 rotas, funde para digamos 15, mas o re-split quebra de volta para 58-60.

Além disso, a abordagem opera em "bloco" — tenta reconstruir todas as rotas de uma vez — em vez de fazer melhorias incrementais. Isso torna impossível controlar a intensidade e dificulta a convergência gradual.

Há também um problema conceitual: a abordagem não re-roda o InsertStations após os movimentos. No EVRPTW, mover um cliente entre rotas altera a necessidade de estações de recarga em ambas as rotas. Qualquer busca local que ignore as estações opera sobre uma representação incompleta do problema.

---

**O que deve ser implementado: relocate inter-rota com recálculo de estações**

O princípio é simples: mover um cliente de cada vez de uma rota para outra, e após cada movimento recalcular as estações de recarga em ambas as rotas afetadas via InsertStations. Não há merge, não há re-split, não há reordenação. As rotas vão sendo consolidadas incrementalmente.

A busca local opera sobre rotas de clientes *sem* estações. As estações são inseridas pelo InsertStations a cada avaliação de movimento candidato. Isso garante que a bateria e as estações são sempre consistentes.

O fluxo revisado do decodificador:

```
FUNÇÃO Decode(π):
    routes ← Split(π)                          // fase 1: particionar por capacidade
    routes ← LocalSearchEVRPTW(routes, K_max)  // fase 2: consolidar rotas (NOVO)
    expanded ← []                               // fase 3: inserir estações
    para cada route em routes:
        result, tw_viol, bat_viol ← InsertStations(route)
        expanded.append(result)
    f, cv ← Evaluate(expanded, tw_viols, bat_viols)  // fase 4: calcular objetivos
    retornar f, cv
```

O pseudocódigo completo da busca local:

```
FUNÇÃO LocalSearchEVRPTW(routes, instance, K_max):
    // Pré-computar o custo (distância total) de cada rota expandida atual
    // Isso é necessário para avaliar se um movimento melhora ou piora
    custos_atuais ← {}
    para cada rota em routes:
        exp ← InsertStations(rota)
        custos_atuais[rota_id] ← distancia_total(exp)
    
    k ← 0                    // contador de movimentos aceitos
    melhorou ← verdadeiro
    
    enquanto melhorou E k < K_max:
        melhorou ← falso
        melhor_economia_global ← 0
        melhor_movimento ← nulo
        
        para cada rota_i em routes:
            para cada idx_c, cliente c em enumerar(rota_i):
                
                // === Avaliar custo de REMOVER c de rota_i ===
                rota_i_sem_c ← cópia de rota_i sem o cliente c
                
                se rota_i_sem_c está vazia:
                    // Rota inteira seria eliminada
                    custo_i_novo ← 0
                senão:
                    exp_i_sem_c ← InsertStations(rota_i_sem_c)
                    se exp_i_sem_c é INFEASÍVEL:
                        // Mesmo com violação gradual, registrar o custo
                        custo_i_novo ← distancia_total(exp_i_sem_c)
                    senão:
                        custo_i_novo ← distancia_total(exp_i_sem_c)
                
                economia_remocao ← custos_atuais[rota_i_id] - custo_i_novo
                
                // === Tentar INSERIR c em cada outra rota ===
                para cada rota_j em routes, rota_j ≠ rota_i:
                    
                    // Verificar capacidade
                    se soma_demanda(rota_j) + demand[c] > C:
                        continuar
                    
                    // Tentar cada posição de inserção em rota_j
                    para pos ← 0 até len(rota_j):
                        rota_j_com_c ← cópia de rota_j com c inserido na posição pos
                        
                        exp_j_com_c ← InsertStations(rota_j_com_c)
                        custo_j_novo ← distancia_total(exp_j_com_c)
                        
                        custo_insercao ← custo_j_novo - custos_atuais[rota_j_id]
                        
                        economia_total ← economia_remocao - custo_insercao
                        
                        se economia_total > melhor_economia_global:
                            melhor_economia_global ← economia_total
                            melhor_movimento ← {
                                cliente: c,
                                rota_origem: rota_i_id,
                                rota_destino: rota_j_id,
                                posicao: pos,
                                rota_i_nova: rota_i_sem_c,
                                rota_j_nova: rota_j_com_c,
                                custo_i_novo: custo_i_novo,
                                custo_j_novo: custo_j_novo
                            }
        
        // === Aplicar o melhor movimento encontrado ===
        se melhor_movimento ≠ nulo:
            mov ← melhor_movimento
            
            // Atualizar rota de origem
            se mov.rota_i_nova está vazia:
                routes.remover(rota com id mov.rota_origem)
                custos_atuais.remover(mov.rota_origem)
            senão:
                routes[mov.rota_origem] ← mov.rota_i_nova
                custos_atuais[mov.rota_origem] ← mov.custo_i_novo
            
            // Atualizar rota de destino
            routes[mov.rota_destino] ← mov.rota_j_nova
            custos_atuais[mov.rota_destino] ← mov.custo_j_novo
            
            k ← k + 1
            melhorou ← verdadeiro
    
    retornar routes
```

Pontos críticos da implementação que precisam de atenção:

Primeiro, as rotas manipuladas pela busca local contêm *apenas clientes*, sem estações e sem depósito. As estações são inseridas pelo InsertStations a cada avaliação. Isso é fundamental — se as rotas contivessem estações, o relocate teria que lidar com a complexidade de mover/remover/reinserir estações manualmente.

Segundo, o InsertStations já existe e funciona (passou no auditor com zero violações). A busca local é um *consumidor* do InsertStations, não precisa reimplementar lógica de bateria ou recarga.

Terceiro, o critério de aceitação é puramente baseado em distância total (economia_total > 0). A busca local não conhece f1, f2, f3 explicitamente — ela apenas reduz a distância total das rotas afetadas. A redução de f1 acontece naturalmente quando rotas ficam vazias e são eliminadas.

Quarto, o K_max controla a intensidade. Com K_max=0, o decodificador funciona como antes (sem busca local). Isso permite comparação direta entre "com" e "sem" busca local.

Quinto, a complexidade por movimento candidato: avaliar um movimento requer duas chamadas ao InsertStations (uma para a rota de origem, uma para a de destino). Cada chamada é O(n_rota × |S|) onde n_rota é o número de clientes na rota e |S|=21 estações. Para rotas curtas (5-10 clientes), isso é submilissegundo. O número total de movimentos avaliados por iteração é O(n_total × n_rotas × n_max_rota), que para n=100 com ~30 rotas de ~3 clientes cada é da ordem de 100 × 30 × 3 = 9.000 avaliações de InsertStations por iteração da busca local. Com K_max=50 e digamos 10 iterações até convergência, são ~90.000 chamadas ao InsertStations por Decode. Isso pode ser lento — se for, há otimizações possíveis (limitar a busca às K rotas mais próximas geograficamente, usar first-improvement em vez de best-improvement).

---

**Testes de validação — três fases**

**Fase A — A busca local melhora a qualidade sem introduzir bugs?**

Esse teste verifica duas coisas: que f1 cai significativamente e que o auditor continua passando.

Teste A1: rode 5 runs de NSGA-II em c101_21 com pop=100 e 10.000 avaliações (100 gerações), comparando K_max=0 vs K_max=50. Registre para cada run: f1 mínimo na frente de Pareto final, f2 da solução com f1 mínimo, tempo total de execução, e número de soluções viáveis na população final.

O resultado esperado com K_max=0 é f1 ≈ 61 (como observado). Com K_max=50, o f1 deve cair significativamente. Se cair para a faixa de 15-25, a busca local está fazendo seu trabalho. Se cair para 10-15, está excelente. Se ficar acima de 40, a implementação provavelmente tem um problema (o movimento nunca é aceito, ou as rotas não estão sendo recalculadas corretamente).

Teste A2: rode o auditor independente em *todas* as soluções da frente de Pareto final de cada run do teste A1 com K_max=50. Zero violações é o critério de passagem. Se alguma solução violar bateria, TW ou capacidade, há bug na integração entre busca local e InsertStations.

Teste A3: repita A1 em r201_21 (regime 2xx, BKS m=3, espaço mais fácil) e rc101_21 (que produzia zero viáveis sem busca local). Para r201_21, f1 deve cair para a faixa de 3-8. Para rc101_21, verificar se a busca local permite que soluções viáveis apareçam.

Teste A4 (determinismo): gere uma permutação fixa de 100 clientes. Rode Decode com K_max=50 duas vezes com a mesma permutação. Os vetores [f1, f2, f3, cv] devem ser idênticos. Repita com 10 permutações diferentes.

Teste A5 (tempo): registre o tempo médio por chamada ao Decode com K_max=50 em c101_21. Se ultrapassar 1 segundo, implementar a otimização de vizinhança reduzida: para cada cliente, avaliar inserção apenas nas 5 rotas cujo centróide geográfico está mais próximo do cliente. Isso reduz o número de avaliações de InsertStations por ordem de magnitude.

**Fase B — Os três algoritmos produzem resultados distinguíveis?**

Esse é o teste central para a preocupação de homogeneização.

Teste B1: rode 10 runs de cada algoritmo (NSGA-II, MOEA/D, SMS-EMOA) em c101_21 com K_max calibrado na Fase A e 30.000 avaliações. Registre o HV mediano e desvio padrão para cada algoritmo. Calcule: os HVs medianos são diferentes entre pelo menos dois algoritmos (teste de Kruskal-Wallis, p < 0.10)? Os desvios padrão são > 0 para os três? Se ambas as condições forem satisfeitas, os algoritmos são distinguíveis e K_max está adequado.

Teste B2: se B1 falhar (HVs indistinguíveis), reduza K_max para 20 e repita. Se continuar indistinguível, reduza para 10. Se com K_max=10 ainda forem iguais, teste em r201_21 ou rc201_21 que têm espaço de soluções mais rico.

Teste B3: se B1 passar, aumente K_max para 100 e repita. Se os algoritmos continuarem distinguíveis, use K_max=100 (melhor qualidade sem perder diferenciação). Se ficarem indistinguíveis, volte ao K_max da Fase A. O objetivo é encontrar o maior K_max que preserve a distinguibilidade.

Teste B4: para o K_max final escolhido, verifique que o HV do MOEA/D é diferente do SMS-EMOA (não apenas NSGA-II diferente dos outros). Se MOEA/D ≈ SMS-EMOA mas ambos ≠ NSGA-II, você ainda tem material para H1 mas não para H2/H3. Isso é aceitável mas deve ser documentado.

**Fase C — O setup produz dados interpretáveis para as hipóteses?**

Teste C1 (frentes estratificadas, Hnova): rode 10 runs de NSGA-II em r201_21 com K_max final e 50.000 avaliações. Nas frentes de Pareto finais, conte o número de valores distintos de f1. Se houver pelo menos 3 valores distintos, Hnova é testável. Se a frente tiver apenas um valor de f1, a busca local está convergindo todos os indivíduos para a mesma camada — considerar reduzir K_max ou ajustar a instância.

Teste C2 (convergência, Hconv): rode 1 run de cada algoritmo em c101_21 com K_max final, registrando HV a cada 5.000 avaliações. Plote as três curvas. Verifique que SMS-EMOA tem forma de curva visivelmente diferente dos outros dois (crescimento mais lento no início, convergência similar ou superior no final). Se as três curvas forem indistinguíveis em formato, Hconv não é testável nessa instância — testar em r201_21.

Teste C3 (efeito de TW, H3): rode 10 runs de cada algoritmo em c101_21 (tw_ratio=0.051, muito restrita) e c104_21 (tw_ratio=0.691, muito larga). Compare os rankings dos algoritmos entre as duas instâncias. Se o ranking muda (por exemplo, MOEA/D melhor em c101_21 mas SMS-EMOA melhor em c104_21), H3 é testável. Se o ranking é idêntico, a busca local pode estar dominando a influência da TW.

Teste C4 (viabilidade): verifique a taxa de viabilidade nas populações finais de r101_21 (tw_ratio=0.044, a mais restrita). Se com K_max>0 a taxa de viabilidade subiu significativamente comparado a K_max=0, a busca local está ajudando a encontrar a região viável.

---
