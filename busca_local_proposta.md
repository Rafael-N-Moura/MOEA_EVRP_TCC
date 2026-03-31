Vou descrever a busca local, seu encaixe no decodificador, e os testes de verificação em sequência.

**Onde a busca local entra no fluxo**

O decodificador atual tem três fases: Split → InsertStations → Evaluate. A busca local entra entre Split e InsertStations. Isso é importante — ela opera sobre rotas *sem* estações, apenas com clientes. As estações são inseridas depois, sobre as rotas já melhoradas. Isso mantém a busca local simples (não precisa lidar com bateria e recarga) e preserva a lógica do InsertStations inalterada.

O fluxo revisado fica:

```
FUNÇÃO Decode(π):
    routes ← Split(π)
    improved ← LocalSearch(routes)       // ← NOVO
    expanded ← []
    para cada route em improved:
        result ← InsertStations(route)
        expanded.append(result)
    f, cv ← Evaluate(expanded)
    retornar f, cv
```

**O operador: relocate inter-rota com verificação de capacidade**

Usamos um único operador — relocate inter-rota — por três razões. Primeiro, é o mais eficaz para o problema central (consolidar rotas quasi-singleton). Segundo, é simples de implementar e auditar. Terceiro, manter um único operador reduz o risco de homogeneização comparado com uma bateria completa de operadores.

O relocate tenta mover um cliente de uma rota para outra. A verificação é apenas de capacidade (demanda total ≤ C), porque janelas de tempo serão tratadas pelo InsertStations e pelo mecanismo de violação. Isso é proposital — se verificássemos TW no relocate, a busca local se tornaria muito restritiva e poucas movimentações seriam aceitas.

```
FUNÇÃO LocalSearch(routes, K_max, instance):
    // K_max: número máximo de movimentos aceitos (controle de intensidade)
    // Estratégia: first-improvement com iteração limitada
    
    melhorou ← verdadeiro
    k ← 0
    
    enquanto melhorou E k < K_max:
        melhorou ← falso
        
        para cada rota_i em routes (da maior para menor em nº clientes):
            para cada cliente c em rota_i:
                melhor_economia ← 0
                melhor_destino ← nulo
                melhor_posicao ← nulo
                
                // Custo de remover c da rota_i
                // c está entre predecessor(c) e successor(c) na rota
                pred ← nó antes de c em rota_i (ou depot se c é primeiro)
                succ ← nó depois de c em rota_i (ou depot se c é último)
                economia_remocao ← dist[pred][c] + dist[c][succ] - dist[pred][succ]
                
                para cada rota_j em routes, rota_j ≠ rota_i:
                    // Verificar capacidade
                    se demanda(rota_j) + demand[c] > C: continuar
                    
                    // Encontrar melhor posição de inserção em rota_j
                    para cada posição p em rota_j:
                        // Inserir c entre nó_p e nó_p+1
                        a ← nó_p (ou depot se início)
                        b ← nó_p+1 (ou depot se fim)
                        custo_insercao ← dist[a][c] + dist[c][b] - dist[a][b]
                        
                        economia_total ← economia_remocao - custo_insercao
                        
                        se economia_total > melhor_economia:
                            melhor_economia ← economia_total
                            melhor_destino ← rota_j
                            melhor_posicao ← p
                
                se melhor_destino ≠ nulo:
                    // First-improvement: aceita e move
                    remover c de rota_i
                    inserir c em melhor_destino na melhor_posicao
                    k ← k + 1
                    melhorou ← verdadeiro
                    
                    // Se rota_i ficou vazia, remover
                    se rota_i está vazia:
                        routes.remover(rota_i)
                    
                    quebrar  // reiniciar o loop externo
    
    retornar routes
```

**Parâmetros e controle de intensidade**

O K_max é o parâmetro crítico. Ele controla quantos movimentos a busca local faz por decodificação. Valores de referência para calibrar: K_max = 10 seria intensidade mínima (consolida as primeiras oportunidades óbvias), K_max = 50 seria intensidade moderada (deve trazer f1 para perto do BKS), e K_max = 200 seria intensidade alta (risco de homogeneização).

A recomendação é começar com K_max = 50 e ajustar com base nos testes que descrevo abaixo.

Note que a busca local usa critério puramente de distância (economia_total > 0) para decidir movimentos. Ela não conhece f3 (makespan) e não otimiza diretamente nenhum objetivo. Isso é proposital: a busca local é uma *heurística de construção de rotas razoáveis*, não um otimizador. O trade-off entre f1, f2 e f3 continua sendo governado pelo algoritmo evolutivo.

**Propriedade de determinismo preservada**

A busca local é determinística — dado o mesmo conjunto de rotas (que vem do mesmo Split, que vem da mesma permutação), ela sempre produz o mesmo resultado. A propriedade Decode(π) ser determinístico é preservada.

**Protocolo de testes — três fases sequenciais**

**Fase A — A busca local melhora a qualidade de solução?**

Rode 5 runs de NSGA-II em c101_21 com 30.000 avaliações, comparando K_max = 0 (sem busca local, baseline atual) vs K_max = 50. Para cada configuração, registre: f1 mínimo e mediano na frente de Pareto final, f2 da solução com f1 mínimo, taxa de viabilidade da população final, e tempo por avaliação.

Os resultados esperados são: com K_max=0, f1 mínimo ~41 (como observado). Com K_max=50, f1 mínimo deve cair para a faixa de 10-18 (próximo ao BKS de 12).

Se f1 não cair significativamente, aumente K_max para 100. Se ainda não cair, o problema não é falta de intensidade — é que o Split está gerando rotas tão ruins que o relocate não consegue corrigir. Nesse caso, teríamos que repensar o Split.

Se o tempo por avaliação ficar proibitivo (>1 segundo para n=100), reduza K_max ou implemente a busca local com lista de vizinhança reduzida (só tentar inserir c nas K rotas mais próximas geograficamente, não em todas).

Rode o mesmo teste em r201_21 (regime 2xx, BKS m=3) e rc101_21 (que anteriormente produzia zero viáveis).

**Fase B — Os algoritmos continuam distinguíveis?**

Esse é o teste central para sua preocupação de homogeneização. Rode 10 runs de cada algoritmo (NSGA-II, MOEA/D, SMS-EMOA) em c101_21 com K_max=50 e 50.000 avaliações. Registre o HV mediano e desvio padrão para cada algoritmo.

O critério de sucesso é: os HVs medianos dos três algoritmos são *diferentes* (teste de Kruskal-Wallis com p < 0.10) ou, no mínimo, os desvios padrão são > 0 (não convergiram para a mesma frente).

Se os HVs forem indistinguíveis, reduza K_max para 20 e repita. Se continuarem indistinguíveis com K_max=20, isso na verdade indica que a instância c101_21 pode não ser discriminativa o suficiente — teste em r201_21 ou rc201_21 que têm espaço de soluções mais rico.

Se com K_max=20 os algoritmos diferem mas com K_max=50 convergem, use K_max=20 — o objetivo não é maximizar qualidade, é viabilizar a comparação.

**Fase C — Sanity check das hipóteses**

Esse teste verifica que o setup com busca local produz dados interpretáveis para suas hipóteses. Rode 10 runs de cada algoritmo em três instâncias: c101_21 (C-1xx, tw_ratio baixo), r201_21 (R-2xx, tw_ratio alto) e rc201_21 (RC-2xx, tw_ratio intermediário). Com K_max calibrado na Fase B e 50.000 avaliações.

Para Hnova (frentes estratificadas): nas frentes de r201_21 e rc201_21 (regime 2xx onde BKS tem f1=3-4), verifique que existem soluções com valores diferentes de f1. Se a frente tiver apenas um valor de f1, Hnova não é testável.

Para Hconv (dinâmica temporal): plote as curvas de convergência dos três algoritmos em c101_21. Verifique que as curvas têm formatos diferentes. Se SMS-EMOA tem curva com formato visivelmente diferente de NSGA-II, Hconv é testável.

Para H3 (efeito de TW): compare os rankings dos algoritmos entre c101_21 (tw_ratio=0.051) e c104_21 (tw_ratio=0.691, se possível). Se o ranking muda, H3 é testável. Se é idêntico, a busca local pode estar dominando a influência da TW — considerar reduzir K_max.

**Resultado possível: K_max ótimo diferente por instância**

É possível que K_max=50 funcione bem para instâncias 2xx (espaço fácil) mas seja insuficiente para 1xx (espaço restrito). Nesse caso, a decisão correta é usar um *K_max único* para todas as instâncias — não adaptar por instância. A razão é que K_max variável criaria a pergunta "as diferenças entre algoritmos são causadas pelos algoritmos ou pelo K_max diferente?". Com K_max fixo, a busca local é uma constante do experimento, não uma variável.

**Resumo da sequência de ação**

Primeiro, implemente o relocate inter-rota no decodificador com K_max como parâmetro. Segundo, rode a Fase A para verificar que a qualidade melhora. Terceiro, rode a Fase B para calibrar K_max no ponto onde os algoritmos diferem. Quarto, rode a Fase C para verificar que as hipóteses são testáveis. Quinto, fixe K_max e documente-o como parâmetro do decodificador (não do algoritmo) na metodologia.

A justificativa no TCC segue naturalmente: "O decodificador incorpora uma fase de busca local limitada (relocate inter-rota com K_max=X movimentos) para produzir soluções na faixa de qualidade compatível com a literatura. A intensidade foi calibrada empiricamente para preservar a distinguibilidade entre algoritmos (verificada por teste de Kruskal-Wallis)."

Quer discutir algum aspecto antes de implementar?