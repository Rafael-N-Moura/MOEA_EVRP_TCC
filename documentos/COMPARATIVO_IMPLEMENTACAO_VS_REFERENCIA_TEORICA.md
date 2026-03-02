# Comparativo: Implementação vs. Referência Teórica

Este documento confronta a implementação atual do **BatteryFocusedNSGA2** e do problema **EVRPTW-PR** com a especificação teórica em `REFENCIA_TEORICA.md`, indicando **pontos adequados** e **divergências** em relação à literatura de gerenciamento de restrições (C-TAEA, IDEA, Push-Pull, Deep Infeasibility Exploration).

---

## 1. Estrutura geral do algoritmo

### Referência teórica (Seção 1)

- **Dois arquivos explícitos:** Arquivo factível \(A_F\) (Convergence Archive) e Arquivo inviável \(A_I\) (Diversity Archive), inspirados em C-TAEA.
- Fluxo: avaliar → atualizar \(A_F\) e \(A_I\) → mating restrito entre arquivos → crossover/mutação/reparo → reavaliar → atualizar arquivos.

### Implementação atual

- **População única** com **cotas**: uma única população `self.pop` é mantida; a sobrevivência (InfeasibleSurvival) **reserva cotas** (ex.: 75% viáveis, 25% inviáveis) e preenche cada cota com seleção por rank/crowding dentro do grupo. Não há duas estruturas \(A_F\) e \(A_I\) separadas em memória.

| Aspecto | Adequado / Divergente | Detalhe |
|--------|------------------------|--------|
| Separação viável/inviável | **Parcialmente adequado** | A distinção viável/inviável existe (G2 ≤ 0 vs. G2 > 0) e as cotas replicam a ideia de “arquivo de convergência” (viáveis) e “arquivo de diversidade” (inviáveis), mas em uma única população, não em dois arquivos independentes como no C-TAEA. |
| Atualização por geração | **Adequado** | Merge população + offspring e depois sobrevivência que aplica NDS + crowding por grupo está alinhado ao espírito de “atualizar arquivos com descendentes”. |

---

## 2. Modelo de problema e objetivos

### Referência teórica (Seção 2)

- **f₁:** distância total percorrida (ou custo equivalente).
- **f₂:** atraso total em janelas, \(f_2(x) = \sum_i \max(0, t_i - l_i)\).
- Bateria como **restrição** (via CV), não como objetivo.

### Implementação atual

- **f₁:** custo total (veículos × custo_fixo + distância × custo_distância) — compatível com “custo equivalente” à distância.
- **f₂:** **insatisfação média** (0–1), derivada de atrasos: \(S_i = \max(0, 1 - \text{atraso}/\text{tolerância})\), \(f_2 = 1 - \bar{S}\). Não é soma de atrasos; é métrica de satisfação agregada.
- Bateria como restrição (G2), não objetivo — **adequado**.

| Aspecto | Adequado / Divergente | Detalhe |
|--------|------------------------|--------|
| f₁ (custo/distância) | **Adequado** | Custo total é formulação padrão em VRP/EVRP e equivalente em espírito à distância. |
| f₂ (atraso vs. insatisfação) | **Divergente** | Referência: \(f_2 = \sum_i \max(0, t_i - l_i)\). Implementação: f₂ = insatisfação média (0–1). Ambas refletem janelas de tempo, mas a referência usa “soma de atrasos” e a implementação usa “média de satisfação”; escalas e interpretação diferem. |
| Bateria só como restrição | **Adequado** | G2 = violação de bateria; não há terceiro objetivo. |

---

## 3. Representação e avaliação

### Referência teórica (Seção 3)

- Cromossomo: sequência de clientes (ou giant tour) com inserção de recargas via **decodificação heurística** (inserir estações quando SOC < SOC_min).
- Avaliação: decodificar → simular percurso (distância, tempo, SOC) → calcular f₁, f₂ e violações.

### Implementação atual

- Cromossomo: **permutação de clientes** (índices), sem genes de recarga; recargas inseridas no **decoder** (Smart Detour, margem de segurança, force_battery_feasible).
- Avaliação: decode → Solution com rotas, custo, insatisfação, battery_violation → f₁, f₂, G.

| Aspecto | Adequado / Divergente | Detalhe |
|--------|------------------------|--------|
| Representação (sequência de clientes) | **Adequado** | Permutação de clientes está alinhada à “sequência de clientes” da referência. |
| Recargas por heurística no decoder | **Adequado** | Inserção de estações no decoder (e modo “com dívida” quando force_battery_feasible=False) segue a ideia de recargas por heurística, não por genes explícitos. |
| Operadores (OX, inversão) | **Adequado** | Order Crossover e Inversion Mutation são operadores típicos de VRP/permutação citados na literatura. |

---

## 4. Violação de restrições (CV)

### Referência teórica (Seção 3.3)

- **CV agregado:** \(CV_{SOC}(x)\), \(CV_{TW}(x)\) opcional, \(CV(x) = w_{SOC} CV_{SOC} + w_{TW} CV_{TW} + \ldots\).
- Violação de bateria: soma de déficits ao longo dos arcos (ex.: \(\max(0, SOC_{min} - SOC_{arc})\)).

### Implementação atual

- **G1, G2** no Pymoo: G1 = 0 (carga tratada no decoder), **G2 = déficit total de bateria** (solution.battery_violation). O Pymoo deriva **CV** internamente a partir de G (ex.: CV = agg(G)).
- Não há CV_TW explícito; janelas de tempo entram como f₂ (insatisfação) e não como restrição rígida no vetor G.

| Aspecto | Adequado / Divergente | Detalhe |
|--------|------------------------|--------|
| Violação de bateria (G2) | **Adequado** | G2 como déficit de energia é coerente com CV_SOC; magnitude única (total) vs. soma por arco é decisão de modelagem, conceitualmente alinhada. |
| CV agregado multi-termo | **Divergente** | Referência prevê CV = soma ponderada (SOC + TW + …). Implementação usa apenas G2 (e G1=0); não há termo explícito de janelas em G/CV. |
| Janelas como restrição (CV_TW) | **Divergente** | Referência permite CV_TW com \(\Delta_{\max}\); na implementação, atrasos só impactam f₂, não G. |

---

## 5. Arquivo factível \(A_F\) (Convergence Archive)

### Referência teórica (Seção 4.1)

- Conteúdo: \(CV(x) \leq \epsilon_F\) (idealmente 0).
- Tamanho fixo \(N_F\).
- Atualização: unir com descendentes factíveis → **ranking por não-dominância em (f₁, f₂)** → **crowding distance** por frente → preencher até \(N_F\).

### Implementação atual

- Viáveis definidos por **G2 ≤ 0** (equivalente a CV ≤ 0 na prática para bateria).
- Cota viável: \(n\_feasible\_target = n\_select - n\_infeasible\_target\); mínimo de 10% viáveis garantido.
- Seleção de viáveis: **NDS em F (f₁, f₂)** + **crowding distance** por frente → preencher até a cota.

| Aspecto | Adequado / Divergente | Detalhe |
|--------|------------------------|--------|
| Critério de factibilidade (CV ≈ 0) | **Adequado** | G2 ≤ 0 corresponde a “CV abaixo de limiar” (epsilon_F = 0). |
| NDS + crowding em (f₁, f₂) | **Adequado** | Totalmente alinhado à referência e ao NSGA-II clássico. |
| Tamanho fixo / cota | **Adequado** | Cota rígida de viáveis (com mínimo 10%) replica a ideia de arquivo de tamanho controlado. |
| Limiar \(\epsilon_F\) suave | **Divergente** | Referência sugere aceitar CV ≤ ε_F (quase-viáveis no arquivo factível); implementação usa limiar rígido G2 ≤ 0 para “factível”. |

---

## 6. Arquivo inviável \(A_I\) (Diversity Archive)

### Referência teórica (Seção 4.2)

- Conteúdo: \(CV(x) > \epsilon_F\).
- Tamanho: \(N_I \approx \alpha N_F\), \(\alpha \in [0{,}1,\,0{,}3]\).
- **Ordenação:** ranking por **não-dominância em \((f_1, f_2, CV)\)** — inviáveis com menor violação e melhores objetivos dominam.
- Diversidade: crowding (em (f₁, f₂) ou em grid) dentro de cada frente.

### Implementação atual

- Inviáveis: **G2 > 0**.
- **Filtro epsilon (Bounded Archive):** apenas inviáveis com **G2 ≤ Q × max_violation_ratio** (ex.: 15%) entram na disputa; acima disso são “rejeitados” e só usados em fallback (ordenados por G2 crescente).
- Entre os **aceitáveis**: seleção por **NDS + crowding em (f₁, f₂)** apenas — **sem CV na ordenação**.
- Cota inviável: **infeasible_ratio** (ex.: 0,25), alinhada a α.

| Aspecto | Adequado / Divergente | Detalhe |
|--------|------------------------|--------|
| Tamanho N_I ≈ α N_F | **Adequado** | infeasible_ratio (ex.: 0,25) está na faixa 0,1–0,3 da referência. |
| Limitar inviáveis “próximos da fronteira” | **Adequado** | Filtro G2 ≤ Q×0,15 (Arquivo Inviável Delimitado) está em linha com IDEA/C-TAEA: manter só “quase viáveis” para evitar lixo evolutivo. |
| Ordenação em (f₁, f₂, CV) | **Divergente** | Referência: NDS em **(f₁, f₂, CV)**. Implementação: NDS apenas em **(f₁, f₂)** entre os aceitáveis; CV (G2) não entra no ranking, só no filtro. |
| Diversidade (crowding) | **Adequado** | Crowding em (f₁, f₂) na frente de corte está de acordo com a referência. |

---

## 7. Seleção de pais (mating restrito)

### Referência teórica (Seção 5)

- **Probabilidade dinâmica \(p_F(t)\):** primeiro pai de \(A_F\) com probabilidade \(p_F(t)\), senão de \(A_I\). Sugestão: \(p_F(0) \approx 0{,}5\), aumentar para 0,8–0,9 ao longo das gerações (Push–Pull).
- **Segundo pai por proximidade:** se primeiro de \(A_F\), segundo de \(A_I\) **próximo em (f₁, f₂)** (ou “melhor” em um objetivo); simétrico se primeiro de \(A_I\).

### Implementação atual

- **DirectedMatingSelection:** para cada par de pais, **sempre** Pai 1 = **viável** (aleatório em feasible_indices), Pai 2 = **inviável** (aleatório em infeasible_indices). Não há probabilidade \(p_F(t)\) nem escolha por proximidade em objetivos.

| Aspecto | Adequado / Divergente | Detalhe |
|--------|------------------------|--------|
| Cruzar factíveis com inviáveis | **Adequado** | Ideia de restricted mating (C-TAEA) está presente: um pai viável e um inviável. |
| Probabilidade dinâmica \(p_F(t)\) | **Divergente** | Referência: \(p_F(0) \approx 0{,}5\), depois 0,8–0,9. Implementação: 100% primeiro pai viável, sem fase “push” inicial com mais pais inviáveis. |
| Segundo pai por proximidade em (f₁, f₂) | **Divergente** | Referência: segundo pai escolhido por proximidade ou qualidade em objetivos. Implementação: segundo pai é **aleatório** entre inviáveis, sem métrica de proximidade. |

---

## 8. Operadores e geração de inviáveis

### Referência teórica (Seção 6)

- Crossover (OX, PMX, etc.) e mutação (swap, 2-opt, Or-opt, etc.) **podem gerar inviáveis**; não restringir para manter viabilidade.

### Implementação atual

- **Order Crossover** e **Inversion Mutation**; offspring é avaliado com **force_battery_feasible=False** em 50% dos casos e **True** em 50% (reparo probabilístico). Ou seja, operadores em si não restringem viabilidade; a “restrição” é apenas na **avaliação** (decoder), que pode inserir recargas ou permitir dívida.

| Aspecto | Adequado / Divergente | Detalhe |
|--------|------------------------|--------|
| Operadores não restritos à viabilidade | **Adequado** | Crossover e mutação não garantem viabilidade; inviáveis são gerados naturalmente quando o decoder está em modo “otimista”. |
| Tipos de operadores (OX, inversão) | **Adequado** | Coerente com a referência para VRP baseado em permutação. |

---

## 9. Reparo e restauração de viabilidade

### Referência teórica (Seção 7)

- **Reparo local:** inserir recarga quando SOC < SOC_min; reordenar (2-opt, relocate) para reduzir atraso.
- Aplicar reparo: sempre após crossover/mutação (heavy) **ou** com probabilidade / apenas para candidatos a \(A_F\) (CV pequeno). Pool de trabalho (inviáveis) explorado sem reparo pesado; reparo quando solução está prestes a migrar para \(A_F\).

### Implementação atual

- **Reparo “Lamarckiano” por reavaliação:** 50% dos filhos são **reavaliados** com **force_battery_feasible=True** (decoder insere recargas); 50% com False. Não há alteração do **genótipo** (X); apenas o **fenótipo** (F, G) muda na avaliação. Ou seja, é um “reparo” no sentido de obter um valor F/G mais viável para aquele X, não inserção explícita de genes de recarga.
- Não há reparo local no espaço de rotas (2-opt, relocate) nem critério “reparar só quando CV pequeno”.

| Aspecto | Adequado / Divergente | Detalhe |
|--------|------------------------|--------|
| Inserção de recarga quando necessário | **Parcialmente adequado** | O decoder, quando force_battery_feasible=True, insere recargas; isso atua como “reparo” na avaliação, mas não como operador de reparo no genótipo. |
| Reparo com probabilidade | **Adequado** | 50% reparo / 50% exploração está na linha de “reparo probabilístico” da referência. |
| Reparo apenas para CV pequeno | **Divergente** | Referência sugere reparar quando solução está prestes a entrar em \(A_F\). Implementação aplica reparo a 50% dos filhos independentemente do CV. |
| Reparo local (2-opt, relocate para atraso) | **Divergente** | Não implementado; só existe “reparo” via reavaliação com decoder conservador. |

---

## 10. Controle da fração de inviáveis e limiares

### Referência teórica (Seção 8)

- **α:** \(N_I = \alpha N_F\), α ∈ [0,1; 0,3]; pode ser **α(t)** decrescente (mais inviáveis no início, Push–Pull).
- **ε_F:** aceitar CV ≤ ε_F em \(A_F\); ε_F pode decrescer ao longo das gerações.

### Implementação atual

- **infeasible_ratio** fixo (ex.: 0,25); **não há α(t)** dinâmico.
- **ε_F:** factibilidade rígida (G2 ≤ 0); não há ε_F suave para o arquivo factível.
- **Epsilon para inviáveis:** max_violation_ratio (ex.: 0,15) limita quais inviáveis entram no “arquivo” (G2 ≤ Q×0,15); não é ε_F, é limite superior de violação para inviáveis aceitáveis.

| Aspecto | Adequado / Divergente | Detalhe |
|--------|------------------------|--------|
| α na faixa 0,1–0,3 | **Adequado** | infeasible_ratio = 0,25 está dentro do intervalo. |
| α(t) decrescente (Push–Pull) | **Divergente** | Não implementado; proporção de inviáveis é constante. |
| ε_F suave / decrescente | **Divergente** | Não implementado; factibilidade é G2 ≤ 0 fixo. |

---

## 11. Resumo por componente

| Componente | Adequado à referência | Principais divergências |
|-----------|------------------------|--------------------------|
| Estrutura (dois arquivos) | Parcial | População única com cotas em vez de \(A_F\) e \(A_I\) separados. |
| Objetivo f₁ | Sim | — |
| Objetivo f₂ | Parcial | Insatisfação média (0–1) em vez de soma de atrasos. |
| Violação (G2, CV) | Parcial | Só bateria em G; sem CV agregado multi-termo nem CV_TW. |
| Arquivo factível (NDS + crowding) | Sim | Sem ε_F suave. |
| Arquivo inviável (tamanho, filtro ε) | Sim | Ordenação em (f₁, f₂) apenas, não em (f₁, f₂, CV). |
| Mating restrito | Parcial | Sem \(p_F(t)\) e sem segundo pai por proximidade. |
| Operadores | Sim | — |
| Reparo | Parcial | Reparo por reavaliação (50%); sem reparo local em rotas, sem “reparar só quando CV pequeno”. |
| α e ε dinâmicos | Não | α e ε_F fixos; sem Push–Pull explícito na fração. |

---

## 12. Recomendações para alinhamento futuro (opcional)

1. **f₂:** Se desejar aderência estrita à referência, considerar definir f₂ como soma de atrasos \(\sum_i \max(0, t_i - l_i)\) (mantendo ou não a insatisfação para análise).
2. **Arquivo inviável:** Incluir **CV (ou G2)** como terceiro “objetivo” na ordenação dos inviáveis: NDS em **(f₁, f₂, G2)** para alinhar à referência (IDEA/C-TAEA).
3. **Mating:** Introduzir **p_F(t)** (ex.: 0,5 → 0,9) e escolha do **segundo pai por proximidade** em (f₁, f₂) no outro arquivo.
4. **Push–Pull:** Implementar **infeasible_ratio(t)** decrescente (ex.: 0,3 no início, 0,1 no fim).
5. **Reparo:** Opção de reparo apenas para indivíduos com G2 abaixo de um limiar (candidatos a viáveis), ou reparo local (2-opt/relocate) para atrasos, se for de interesse.

---

*Documento gerado com base em `documentos/REFENCIA_TEORICA.md` e na implementação em `src/battery_focused_nsga2.py`, `src/problem.py` e `src/decoder.py`.*
