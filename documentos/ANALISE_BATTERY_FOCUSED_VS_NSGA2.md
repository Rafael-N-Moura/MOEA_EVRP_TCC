# Análise: Por que o Battery-Focused NSGA-II fica pior que o NSGA-II padrão

## Comparação objetiva dos resultados (rc208_21, 100 gerações)

| Métrica | NSGA-II padrão | Battery-Focused | Diferença |
|--------|-----------------|-----------------|-----------|
| **f1 (custo) mínimo** | 4905.50 | 5561.44 | **+13,4% pior** (battery) |
| **f1 médio (pop final)** | 5155.00 | 5730.80 | +11,2% pior |
| **f2 (insatisfação) mínimo** | 0.5643 | 0.6569 | **+16,4% pior** (battery) |
| **f2 médio** | 0.5736 | 0.7214 | +25,8% pior |
| **Soluções na frente de Pareto** | 4 | 13 | battery tem mais pontos, mas piores |
| **Tempo** | 36.26 s | 30.82 s | battery mais rápido (menos eval por gen em parte do fluxo) |
| **Avaliações (n_eval)** | 10 000 | 24 850 | battery usa **~2,5× mais** avaliações |

Conclusão: o Battery-Focused usa **bem mais** avaliações e ainda assim produz **pior** custo e **pior** insatisfação. A técnica, como está, não está funcionando a favor da qualidade.

---

## Por que a técnica não está funcionando

### 1. **Imposto do reparo (repair tax)**

- No modo **inviável** (radical), o decoder não insere paradas de recarga; o custo f1 fica artificialmente menor.
- Ao reparar (reavaliar com `force_battery_feasible=True`), o mesmo genótipo passa a pagar recargas → f1 sobe na ordem de **~6,5%** (como no `compare_feasible_vs_infeasible.py --radical`).
- No Battery-Focused, uma fração grande dos **viáveis** vem de **reparados**. Esses viáveis têm sempre f1 pior que a versão inviável da mesma permutação.
- O NSGA-II padrão **nunca** paga esse imposto: tudo é decodificado já viável, então a busca é direta no espaço de soluções viáveis.

Efeito: o “melhor” que o battery pode entregar em viáveis está limitado por “melhor inviável reparado”, ou seja, sempre há um teto extra de ~6,5% em f1 em relação a uma busca que já opera só no viável.

---

### 2. **Directed mating: só viável × inviável**

- O **Directed Mating** escolhe sempre: **Pai 1 = viável**, **Pai 2 = inviável** (aleatório dentro de cada grupo).
- Consequência: **nunca** há cruzamento **viável × viável**. Os melhores viáveis nunca são combinados entre si.
- Os filhos são gerados a partir de um viável e um inviável; são avaliados com `force_battery_feasible=False` → a grande maioria sai **inviável**. Metade é reparada e vai para o pool viável; a outra metade continua inviável.
- O pool viável é alimentado por: (i) sobrevivência dos melhores entre os 75 viáveis da geração anterior e (ii) **50 reparados** por geração. Ou seja, **2/3 dos viáveis** vêm de reparo (penalizados em f1).

No NSGA-II padrão, pais são escolhidos por torneio em (f1, f2); assim, **bons viáveis podem cruzar com bons viáveis** e gerar filhos viáveis ainda melhores. No Battery-Focused isso não acontece: a pressão de seleção para “melhorar o viável” fica enfraquecida.

---

### 3. **25% da população “fora do jogo”**

- A sobrevivência mantém **75 viáveis** e **25 inviáveis**.
- O resultado final (frente de Pareto reportada) usa **apenas soluções viáveis**. Os 25 inviáveis não entram na solução entregue.
- Ou seja: **25% da população** é gasto em indivíduos que não contribuem diretamente para o output. Do ponto de vista do produto final, o “tamanho efetivo” da população para qualidade viável é 75, não 100.
- Ao mesmo tempo, o algoritmo gasta avaliações e seleção nesses inviáveis, na esperança de que, depois do reparo, eles alimentem o pool viável — mas aí entra o imposto do reparo e a falta de cruzamento viável×viável.

---

### 4. **Desalinhamento entre “melhor inviável” e “melhor viável após reparo”**

- A sobrevivência escolhe os **25 inviáveis** por NDS + crowding em **(f1, f2)** (e o reparo escolhe os 50 por **(G2, f1, f2)**).
- O “melhor” em (f1, f2) no espaço **inviável** não é necessariamente o que vira o **melhor viável** depois do reparo: a ordem em f1 pode mudar quando se troca para o decoder viável (inserção de recargas).
- Assim, podemos estar **reparando** indivíduos que não seriam os melhores viáveis se pudéssemos ver o f1 reparado antes. A heurística “menor G2, depois f1, f2” ajuda, mas não elimina esse desalinhamento.

---

### 5. **Mais avaliações, pior resultado**

- NSGA-II: **10 000** avaliações (100 por geração).
- Battery-Focused: **24 850** avaliações (100 offspring + 50 reparos por geração → 250 por geração após a primeira).
- Ou seja, o Battery-Focused usa **cerca de 2,5× mais** avaliações e ainda assim:
  - f1 mínimo **13% pior**,
  - f2 mínimo **16% pior**.

Isso indica que o problema não é falta de avaliações, e sim que a **estratégia de busca** (manter inviáveis, directed mating, reparo em massa) está **desviando** a busca de regiões boas do espaço **viável**.

---

### 6. **Espaço de busca diferente**

- **NSGA-II padrão:** todo mundo é decodificado com `force_battery_feasible=True`. O espaço de objetivos (f1, f2) é **um só** (só viáveis). Seleção e diversidade são consistentes com o que se reporta.
- **Battery-Focused:** convivem dois fenótipos (viável vs inviável) e dois decoders (com e sem recargas). O “melhor” em (f1, f2) no conjunto da população pode ser **inviável**; o que entregamos é só o viável. A seleção favorece bons (f1, f2) em geral, mas muitos desses bons são inviáveis que, ao reparar, pioram. Ou seja, a pressão de seleção não está alinhada ao objetivo final (só viáveis de qualidade).

---

## Resumo das causas

| Causa | Efeito |
|-------|--------|
| **Imposto do reparo (~6,5% em f1)** | Viáveis vindos de reparo ficam sempre piores que a versão inviável; limita o quanto o pool viável pode melhorar. |
| **Directed mating só viável×inviável** | Nunca cruza dois bons viáveis; enfraquece a exploração do espaço viável. |
| **25% inviáveis na população** | Parte do esforço evolutivo não contribui diretamente para a frente de Pareto reportada. |
| **Critério de reparo (G2, f1, f2)** | “Melhor inviável” em (f1, f2) não é garantia de “melhor viável após reparo”. |
| **Mais avaliações em espaço “errado”** | Muitas avaliações em inviáveis e em reparos não se traduzem em ganho na qualidade dos viáveis. |

---

## Sugestões de mudança (para tentar fazer a técnica ajudar)

1. **Permitir acasalamento viável×viável**
   - Parte dos cruzamentos (ex.: 50%) usar **dois pais viáveis** (torneio entre viáveis); a outra parte manter viável×inviável. Assim, o algoritmo pode **explorar** o espaço viável diretamente e ainda usar inviáveis como “reserva” de genes.

2. **Reduzir a dependência do reparo**
   - Garantir que uma fração dos filhos seja avaliada **já como viável** (ex.: filhos de viável×viável sempre com `force_battery_feasible=True`), para não depender só de “reparar os 50 menores G2”.

3. **Ajustar cotas**
   - Testar menos inviáveis (ex.: 15% em vez de 25%) para ver se, com mais viáveis, a qualidade da frente de Pareto melhora.

4. **Critério de reparo**
   - Considerar reparar também por “melhor f1 após reparo estimado” (se houver proxy barata) ou reparar um subconjunto maior e depois escolher os melhores viáveis resultantes, em vez de só (G2, f1, f2) no espaço inviável.

5. **Comparação justa em avaliações**
   - Rodar o NSGA-II padrão com o **mesmo número de avaliações** que o Battery-Focused (ex.: 24 850). Se mesmo assim o NSGA-II padrão ganhar, a conclusão de que a estratégia atual do battery está prejudicando a qualidade fica ainda mais forte.

---

## Conclusão

A ideia de usar inviáveis como “reserva” de soluções baratas e depois reparar é razoável em teoria, mas na implementação atual:

- O **imposto do reparo** e o fato de **nunca cruzar dois viáveis** impedem que o pool viável atinja a qualidade do NSGA-II que opera só no viável.
- O uso de **mais avaliações** e de **25% de população inviável** não se reverte em ganho na frente de Pareto (apenas viáveis), e sim em resultado pior.

Por isso os resultados do NSGA-II padrão continuam melhores que os da variação Battery-Focused neste experimento. As mudanças sugeridas acima podem ajudar a alinhar a técnica ao objetivo final (Pareto de soluções viáveis de alta qualidade).
