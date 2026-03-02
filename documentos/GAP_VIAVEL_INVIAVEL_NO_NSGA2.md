# Por que o gap viável vs inviável no log do NSGA-II não bate com o compare_feasible_vs_infeasible --radical?

## O que cada um mede

### Script `compare_feasible_vs_infeasible.py --radical`
- **Mesma permutação** decodificada duas vezes: uma com `force_battery_feasible=True`, outra com `False` + `use_radical_infeasible=True`.
- O “gap” é **por indivíduo**: quanto o custo (f1) **sobe** ao reparar aquela permutação.
- Resultado típico: ganho médio dos inviáveis em f1 ≈ **6,5%** (reparo piora f1 em ~6,5% em relação ao inviável).

### Log do BatteryFocusedNSGA2
- São mostradas **médias de dois grupos**:
  - **Viáveis:** média de f1 dos 75 (ou 50) indivíduos **já decodificados como viáveis**.
  - **Inviáveis:** média de f1 dos 25 (ou 50) indivíduos **decodificados como inviáveis**.
- São **genótipos e fenótipos diferentes**: não é “o mesmo indivíduo viável vs inviável”.

## Por que o gap no log diminui ao longo das gerações

- **Geração 1:**  
  - 50 viáveis (iniciais) e 50 inviáveis (iniciais), cada grupo com permutações diferentes.  
  - Aí o gap em **média** pode ficar perto do ~6% (ex.: viável médio 6949, inviável 6530 → ~6%).

- **Gerações seguintes:**  
  - A cada geração, 50 filhos inviáveis são **reparados** (reavaliados com `force_battery_feasible=True`) e passam a contar como **viáveis**.  
  - Sobrevivem 75 viáveis e 25 inviáveis.  
  - Os 75 viáveis passam a ser em boa parte ex-inviáveis reparados (genótipos que já eram bons como inviáveis).  
  - Ou seja: o grupo “viáveis” vai sendo preenchido por “reparados”, cujo f1 é “f1_inviável + custo do reparo (~6,5%)”.  
  - O grupo “inviáveis” são os 25 melhores inviáveis (NDS + crowding em (f1,f2)), também genótipos bons.  
  - Assim, **as médias dos dois grupos convergem em qualidade**: ambos refletem genótipos evoluídos; a diferença de **média** entre os dois grupos deixa de ser “custo do reparo da mesma permutação” e vira algo menor (ex.: ~1% no log).

Resumindo: o **~6,5%** do compare script é “quanto sobe f1 ao reparar **a mesma** permutação”. No NSGA-II, o que o log mostra é “diferença de média entre dois **conjuntos** de indivíduos (viáveis vs inviáveis)”, que vão ficando parecidos em qualidade, então o gap em **média** cai (ex.: 6% → 1%).

## Como ver o “gap do reparo” dentro do run (opcional)

Para aproximar do que o compare script mede, seria preciso, **no momento do reparo**, para cada um dos 50 reparados:

- Guardar f1 **antes** do reparo (inviável) e f1 **depois** (viável).
- Calcular algo como:  
  `gap_medio_reparo = mean((f1_depois - f1_antes) / f1_antes * 100)`  
  e eventualmente logar isso por geração.

Assim você veria no próprio run um “custo médio do reparo” por geração, alinhado à ideia do compare script (mesma permutação: viável vs inviável).
