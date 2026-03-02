# BatteryFocused NSGA-II vs NSGA-II padrão: pipeline e mecanismos

Este documento descreve as diferenças entre o **NSGA-II padrão** (pymoo) e o **BatteryFocusedNSGA2**, em termos de mecanismos (mating, crowding, ranqueamento, etc.) e o que foi alterado na estrutura do NSGA-II para suportar a dinâmica do **arquivo de inviáveis** (soluções com violação de bateria G2 > 0).

---

## 1. Visão geral dos dois algoritmos

### NSGA-II padrão (pymoo)

- **Objetivo:** Otimização multi-objetivo com população 100% viável (ou com restrições tratadas via penalização/cv no ranqueamento).
- **Fluxo por geração:** (1) Seleção de pais por **torneio binário** (rank, depois crowding); (2) crossover e mutação → offspring; (3) avaliação da offspring; (4) merge população + offspring; (5) **survival** com RankAndCrowding (NDS no merge, depois preenchimento por frente com crowding); (6) atualização de `opt` (não-dominados).
- **Inicialização:** Sampling (ex.: permutações aleatórias) → avaliação única com o mesmo decoder.

### BatteryFocusedNSGA2

- **Objetivo:** Mesmo problema EVRPTW, mas **preservando um conjunto de soluções inviáveis** (G2 > 0) para explorar trade-off custo vs viabilidade e "puxar" inviáveis para a fronteira.
- **Fluxo por geração:** (1) **Rank e crowding** calculados em A_F (e métricas em A_I) para o torneio; (2) Seleção de pais por **torneio binário** com competidores de A_F e A_I (prob. pI(t) de sortear inviável; comparação: ambos factíveis → rank/crowding; um factível → factível ganha; ambos inviáveis → rank/crowding em (f1,f2,G2)/(f1,f2)); (3) crossover e mutação → offspring; (4) **avaliação diferenciada**: filhos de F×F com decoder **conservador**, resto com decoder **agressivo**; (5) merge; (6) **survival** por **dois arquivos** (A_F + A_I); (7) atualização manual de `opt`.
- **Inicialização:** Híbrida: 50% avaliados com decoder conservador, 50% com agressivo (ou 100% conservador no modo baseline).

---

## 2. Mecanismos: onde estão e como diferem

| Mecanismo | NSGA-II (pymoo) | BatteryFocused (modo normal) | BatteryFocused (modo baseline) |
|-----------|------------------|-------------------------------|---------------------------------|
| **Sampling** | Um único sampling; uma única avaliação. | `HybridSampling`: dois lotes; lote 1 com decoder conservador, lote 2 com agressivo. | Todo o lote com decoder conservador. |
| **Seleção de pais** | **TournamentSelection**: torneio binário por rank e crowding. | **BinaryTournamentWithInfeasible**: torneio binário; competidores de A_F (prob 1−pI) e A_I (prob pI(t)). Ambos factíveis → (rank, crowding); um factível → factível ganha; ambos inviáveis → (rank, crowding) em (f1,f2,G2)/(f1,f2). | Igual ao NSGA-II (TournamentSelection). |
| **Crossover / Mutação** | Iguais (ex.: OrderCrossover, InversionMutation). | Mesmos operadores, aplicados no CustomMating. | Mesmos; mating padrão do NSGA2. |
| **Avaliação da offspring** | Toda a offspring com o mesmo decoder. | Split: F×F → decoder conservador; resto → decoder agressivo (máscara `_last_offspring_ff_mask`). | Toda com decoder conservador. |
| **Merge** | `Population.merge(pop, off)`. | Idem. | Idem. |
| **Ranqueamento (NDS)** | NDS no merge inteiro. | Dois NDS separados via `nsga2_survival`: A_F em (f1, f2); A_I em (f1, f2, G2). | Igual ao NSGA-II. |
| **Crowding distance** | Por frente, em F. | A_F: por frente em (f1, f2) — canônico. A_I: por frente em (f1, f2) mesmo com NDS em (f1, f2, G2) — diversidade no espaço de objetivos. | Igual ao NSGA-II. |
| **Survival** | RankAndCrowding: único conjunto de N indivíduos, preenchido por frente + crowding. | **Dois arquivos** via `nsga2_survival`: A_F — pipeline NSGA-II canônico até N_F. A_I — NSGAzinho: NDS (f1,f2,G2), crowding (f1,f2), até N_I. Total = N_F + N_I. Modo baseline: survival padrão. | Igual ao NSGA-II. |
| **Atributos rank/crowding** | Survival atribui rank e crowding à pop resultante. | Antes do mating: `_update_rank_and_crowding_for_mating` calcula rank/crowding para viáveis (NDS em F) e inviáveis (NDS em (f1,f2,G2), crowding em (f1,f2)). | Survival padrão cuida disso. |
| **Atualização de `opt`** | Automática pelo pymoo. | Manual: apenas viáveis (G2 ≤ 0), NDS em F, opt = primeira frente viável. | Mesma lógica manual. |
| **Validação de X** | Não há. | Em vários pontos (`_validate_and_fix_pop_X`). | Idem. |
| **Filtro CV_max** | Não existe. | Descarta G2 > `cv_max_ratio * Q_bat` antes da survival. | Não aplicado (todos viáveis). |

---

## 3. O que foi alterado na estrutura do NSGA-II para o arquivo de inviáveis

### 3.1 Inicialização

- **Alteração:** Fissionamento em dois lotes (viável / inviável) e avaliação condicionada: um lote com decoder conservador, outro com agressivo. Fusão em uma única população.
- **Diferença:** O NSGA-II usa um único decoder. Aqui, já na geração 0, parte da população é deliberadamente inviável (G2 > 0).

### 3.2 Seleção de pais (mating)

- **Alteração:** TournamentSelection substituído por **BinaryTournamentWithInfeasible**: torneio binário como no NSGA-II, mas com competidores podendo vir de A_F ou A_I. Probabilidade **pI(t)** de sortear competidor inviável (maior no início, menor no fim). Requer rank e crowding calculados antes do mating.
- **Diferença:** No NSGA-II, o torneio usa só a população (com cv). No BatteryFocused, a pool mistura viáveis e inviáveis via pI(t), com regras explícitas para cada caso (factível vs inviável, inviável vs inviável).
- **Exceção (baseline):** TournamentSelection do NSGA-II mantido.

### 3.3 Avaliação da offspring (decoder duplo)

- **Alteração:** F×F → decoder conservador; F×I/I×F → decoder agressivo.
- **Diferença:** No NSGA-II, todos os filhos usam o mesmo decoder.

### 3.4 Sobrevivência e arquivos A_F / A_I

- **Alteração:** Em vez de um único RankAndCrowding no merge, usa-se `nsga2_survival` em duas partições:
  - **A_F (Convergence Archive):** Pipeline NSGA-II canônico: NDS em (f1, f2), acumular frentes até N_F, crowding na frente parcial. Mesma lógica de `RankAndCrowding._do` do pymoo.
  - **A_I (Diversity Archive):** NSGAzinho: pool único (todos os inviáveis do merge, sem pré-filtro de qualidade), NDS em **(f1, f2, G2)** para ranking (favorece inviáveis próximos de factibilidade), crowding em **(f1, f2)** para diversidade (evita clones nos objetivos), acumular frentes até N_I.
  - Total = N_F + N_I = pop_size.
- **Diferença:** No NSGA-II, o survival é um único NDS no merge. Aqui, a população é particionada; A_F usa o pipeline NSGA-II canônico; A_I usa um pipeline análogo com NDS e crowding em espaços diferentes (deliberado).

### 3.5 Ranqueamento (NDS)

- **NSGA-II:** Um NDS no merge (objetivos F). As frentes são globais.
- **BatteryFocused (dois arquivos):** Dois NDS separados via `nsga2_survival`: (1) **A_F**: NDS em (f1, f2), pipeline NSGA-II canônico até N_F. (2) **A_I**: NDS em (f1, f2, G2), pipeline NSGA-II até N_I. Não há frente única misturando viáveis e inviáveis.

### 3.6 Crowding distance

- **Fórmula:** A mesma (distância normalizada por objetivo, extremos com infinito), implementada em `calculate_crowding_distance`.
- **Uso:** No NSGA-II, aplicada em F no merge. No BatteryFocused: **A_F** usa crowding em (f1, f2) — canônico; **A_I** usa crowding em **(f1, f2)** mesmo que o NDS seja em (f1, f2, G2) — deliberado para medir diversidade no espaço de objetivos reais. Crowding é **por arquivo/grupo**, não sobre o merge inteiro.

### 3.7 Atualização de `opt`

- **Alteração:** Atualização manual: apenas viáveis (G2 ≤ 0), NDS em F, opt = primeira frente viável; fallbacks para nunca deixar opt vazio.
- **Diferença:** No NSGA-II, opt inclui todos os não-dominados. Aqui, opt é restrito a viáveis.

### 3.8 Outros pontos

- **Filtro CV_max:** Descarte de inviáveis com G2 > teto antes da survival.
- **Validação de X:** Garantia de forma e tipo dos genótipos em vários passos.
- **Modo baseline:** Com `all_conservative_init=True`, mating e survival voltam a ser os do NSGA-II, toda offspring com decoder conservador. Comparação justa com NSGA-II "puro".

---

## 4. Resumo: o que é igual e o que é diferente

**Igual ao NSGA-II (ou equivalente):**

- Crossover e mutação (operadores).
- Merge população + offspring.
- Fórmula de crowding distance (objetivo space, extremos infinito).
- Uso de NDS para definir frentes.
- Pipeline de A_F: exatamente NSGA-II canônico em (f1, f2).
- **No modo baseline:** sampling, mating, survival, avaliação — tudo igual ao NSGA-II.

**Diferente do NSGA-II (para suportar inviáveis):**

- Inicialização em dois lotes (conservador / agressivo) e fusão.
- Seleção de pais por **torneio binário** com competidores de A_F e A_I (pI(t)); comparação por (rank, crowding) quando ambos factíveis, factível ganha de inviável, e entre inviáveis por (f1,f2,G2) e diversidade em (f1,f2).
- Avaliação da offspring em dois modos (conservador vs agressivo) conforme origem F×F ou F×I/I×F.
- Survival por dois arquivos (A_F, A_I): A_F com pipeline NSGA-II canônico em (f1, f2); A_I com NSGAzinho (NDS em (f1, f2, G2), crowding em (f1, f2)).
- Atualização manual de `opt` apenas sobre viáveis.
- Filtro CV_max e validação explícita de X.
