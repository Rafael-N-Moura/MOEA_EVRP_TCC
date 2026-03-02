# Seleção de pais: NSGA-II (pymoo) vs BatteryFocused (torneio com inviáveis)

## 1. Papel do `RANK_INFEASIBLE_BASE = 10000`

### O que ele faz

- **Viáveis (A_F):** recebem `rank` 0, 1, 2, … (frente do NDS em F). Logo **sempre** `rank < 10000`.
- **Inviáveis (A_I):** recebem `rank = 10000 + frente` (frente do NDS em (f1, f2, G2)). Logo **sempre** `rank >= 10000`.

Na função `wins(c1, c2)` usamos `rank[c] < RANK_INFEASIBLE_BASE` para decidir se o indivíduo é factível. Assim:

- **Sim:** a constante serve **só** para garantir que, no torneio, **nenhum inviável ganhe de um viável**.  
  Qualquer viável tem rank 0, 1, 2, … e qualquer inviável tem rank ≥ 10000, então na comparação “menor rank ganha” o viável sempre vence.

- **Não é** um “rank real” dos inviáveis no mesmo espaço dos viáveis. Os inviáveis têm seu próprio NDS em (f1, f2, G2); o `10000` apenas **desloca** esse rank para um intervalo que nunca se mistura com o dos viáveis, permitindo uma **única** comparação lexicográfica (rank, crowding) para os três casos (F×F, F×I, I×I) sem tratamentos especiais adicionais.

Resumo: **RANK_INFEASIBLE_BASE existe para codificar “factível sempre melhor que inviável” na mesma lógica de “menor rank, depois maior crowding”.**

---

## 2. Como o NSGA-II do pymoo faz seleção de pais

Fonte: `pymoo/algorithms/moo/nsga2.py` e `pymoo/operators/selection/tournament.py`.

### Torneio binário

- Para cada “vaga” de pai, são sorteados **dois** competidores na população (permutação aleatória, sem reposição por torneio).
- O **vencedor** é decidido por uma função de comparação que recebe a população e os índices dos dois competidores.

### Lógica da comparação (binary_tournament no NSGA2)

```text
Para cada torneio (a, b):
  a_cv, b_cv = CV de a e b  (constraint violation; viável ⇒ CV = 0)
  rank_a, cd_a = pop[a].get("rank", "crowding")
  rank_b, cd_b = pop[b].get("rank", "crowding")

  Se (a_cv > 0 ou b_cv > 0):   # pelo menos um inviável
    Vencedor = compare(a, a_cv, b, b_cv, method='smaller_is_better', return_random_if_equal=True)
    → Quem tem CV menor ganha; se empatar, sorteio.

  Senão:   # ambos factíveis
    Se tournament_type == 'comp_by_rank_and_crowding':
      Vencedor = compare(a, rank_a, b, rank_b, method='smaller_is_better')  # return_random_if_equal=False
    Se tournament_type == 'comp_by_dom_and_crowding':
      rel = Dominator.get_relation(a_f, b_f)  # 1 = a domina b, -1 = b domina a, 0 = não-dominados
      Se rel == 1: Vencedor = a
      Se rel == -1: Vencedor = b
      (Se rel == 0, S[i] fica nan e cai no desempate abaixo)

  Se ainda não há vencedor (S[i] é nan):
    Vencedor = compare(a, cd_a, b, cd_b, method='larger_is_better', return_random_if_equal=True)
    → Maior crowding ganha; se empatar, sorteio.
```

- **Default do NSGA2 no pymoo:** `tournament_type = 'comp_by_dom_and_crowding'`, ou seja, entre factíveis usa **dominância** primeiro e, se não houver dominância, **crowding** (e em caso de empate de crowding, **sorteio**).
- **Rank/crowding:** quando usa `comp_by_rank_and_crowding`, entre factíveis: menor rank ganha; empate de rank → desempate por crowding; empate de crowding → sorteio (por causa de `return_random_if_equal=True` na chamada de crowding).

### Função `compare`

- `method='smaller_is_better'`: vence quem tem valor **menor**; se iguais, retorna `None` (a menos que `return_random_if_equal=True`, aí sorteia entre a e b).
- `method='larger_is_better'`: vence quem tem valor **maior**; mesma regra de empate.

Consequência: no NSGA-II padrão, **sempre que há empate em crowding** o desempate é **aleatório**.

---

## 3. Equivalência: BatteryFocused vs NSGA-II

### Onde é equivalente (população só viável ou comparação entre viáveis)

| Aspecto | NSGA-II (pymoo) | BatteryFocused (ambos factíveis) |
|--------|------------------|----------------------------------|
| Estrutura | Torneio binário, dois competidores por vaga | Igual |
| Critério 1 | Rank (menor ganha) ou dominância (comp_by_dom_and_crowding) | Rank (menor ganha) em F |
| Critério 2 | Crowding (maior ganha) | Crowding (maior ganha) |
| Ordem | Primeiro rank/dominância, depois crowding | Primeiro rank, depois crowding |

Para **dois competidores factíveis**, a nossa lógica é a mesma do NSGA-II no modo **rank+crowding**: menor rank ganha; se rank igual, maior crowding ganha. A única diferença é o **empate exato em crowding**: no pymoo há sorteio; no nosso código fazemos `c1 if crowding[c1] >= crowding[c2] else c2`, ou seja, **desempate determinístico** (preferência por c1 quando iguais). Então, **equivalente em critérios; pequena diferença só no desempate por crowding**.

### Onde difere por construção (inviáveis e pool de competidores)

| Aspecto | NSGA-II (pymoo) | BatteryFocused |
|--------|------------------|----------------|
| Quem entra no torneio | Toda a população (ou só viáveis se não houver CV) | **Pool misto:** cada competidor sorteado de A_F com prob. (1−pI) e de A_I com prob. pI(t) |
| Factível vs Inviável | Compara por **CV** (menor CV ganha). Factível tem CV=0 ⇒ factível sempre ganha | **Explícito:** “factível ganha”. Implementado via rank (factível &lt; 10000, inviável ≥ 10000) ⇒ mesmo efeito que “menor CV” |
| Inviável vs Inviável (pymoo) | Compara só **CV** (menor ganha); não usa rank/crowding em F | **Nosso:** NDS em (f1, f2, G2) + crowding em (f1, f2) ⇒ rank e diversidade entre inviáveis |

Ou seja:

- **RANK_INFEASIBLE_BASE** só garante que, na nossa comparação única (rank, crowding), **inviável nunca ganhe de viável**, espelhando o comportamento do pymoo (CV menor ganha ⇒ CV=0 ganha de CV>0).
- O NSGA-II padrão **não** ranqueia inviáveis por (f1, f2, G2) nem usa crowding em (f1, f2) no torneio; só usa CV. Nosso torneio entre dois inviáveis é **uma extensão** (mais rica) em relação ao NSGA-II clássico.

### Resumo de equivalência

- **População viável (A_F) tratada como no NSGA-II:** sim: mesmo torneio binário, mesmo critério (rank depois crowding). Única diferença: desempate exato em crowding é determinístico (c1) no nosso e aleatório no pymoo.
- **Factível sempre ganha de inviável:** sim; no pymoo por CV (0 &lt; qualquer CV), no nosso por rank (todos viáveis &lt; 10000 &lt; todos inviáveis). O `RANK_INFEASIBLE_BASE` é exatamente o truque numérico que implementa isso.
- **Equivalência “bit a bit” com o NSGA-II:** não total: (1) pool de competidores é misto (pI(t)) em vez de toda a população; (2) entre inviáveis usamos rank/diversidade em (f1,f2,G2)/(f1,f2), não só CV; (3) empate em crowding entre factíveis: nós determinístico, pymoo aleatório.

---

## 4. Referências de código (pymoo)

- `pymoo/algorithms/moo/nsga2.py`: `binary_tournament`, uso de `compare`, tratamento de CV e de rank/crowding.
- `pymoo/operators/selection/tournament.py`: `TournamentSelection`, `compare(a, a_val, b, b_val, method, return_random_if_equal, random_state)`.
