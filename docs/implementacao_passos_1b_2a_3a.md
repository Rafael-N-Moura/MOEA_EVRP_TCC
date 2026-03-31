# Implementação dos passos 1b, 2a e 3a — documentação técnica

Este documento descreve o que foi implementado no projeto de TCC (comparação NSGA-II, MOEA/D e SMS-EMOA no EVRPTW multiobjetivo), os problemas encontrados durante o desenvolvimento, como foram tratados e o estado atual dos artefatos gerados.

---

## 1. Contexto e objetivo

Conforme `proximos_passos.md` e `especificacao_tcc.md`, o problema é o **EVRPTW** com **três objetivos** de minimização:

1. **f1** — número de veículos  
2. **f2** — distância total percorrida  
3. **f3** — *makespan* (tempo de conclusão da última rota)

A representação é uma **permutação dos clientes**; um **decodificador em três fases** (Split → InsertStations → Evaluate) transforma o cromossomo em rotas com estações de recarga e calcula os objetivos. Soluções infactíveis recebem uma penalidade finita grande (`1e8` em cada objetivo), para evitar problemas numéricos no pymoo (ver secção 7.2).

Os passos implementados em scripts dedicados são:

| Passo | Descrição resumida | Script |
|-------|-------------------|--------|
| **1b** | Validação do decodificador em 6 instâncias pequenas, com verificação independente de restrições | `scripts/validate.py` |
| **2a** | Calibração do critério de parada via curvas de hipervolume (HV) em execuções exploratórias | `scripts/calibrate.py` |
| **3a** | *Grid search* de hiperparâmetros (72 configurações no total) sobre 6 instâncias de treino | `scripts/tune.py` |

Além disso, foi introduzido o operador de amostragem **`TWBiasedSampling`** (`src/sampling.py`), integrado ao `main.py` e aos três scripts, por motivos descritos na secção 7.3.

---

## 2. Arquivos principais envolvidos

### 2.1 Núcleo do problema

- `src/model.py` — `Context` com matrizes de distância/tempo, índices de nós, etc.  
- `src/decoder.py` — decodificador em três fases; Split com DP estilo Prins **e** verificação de janelas de tempo na extensão de rotas.  
- `src/problem.py` — `EVRPTWProblem` (pymoo) com `n_obj=3`.  
- `src/parser.py` — leitura das instâncias Schneider.  
- `src/sampling.py` — `TWBiasedSampling` (amostragem inicial com viés temporal).  
- `main.py` — execução dos três algoritmos com operadores genéticos e `TWBiasedSampling`.

### 2.2 Scripts experimentais

- `scripts/validate.py` — passo 1b.  
- `scripts/calibrate.py` — passo 2a.  
- `scripts/tune.py` — passo 3a.

### 2.3 Resultados gerados (exemplos)

- `results/calibration/calibration_summary.json` — critérios de parada e metadados por instância.  
- `results/calibration/hv_curves_*.json` — curvas de HV por *run* (para análise visual opcional).  
- `results/tuning/tuning_results.json` — melhores configurações por algoritmo (após execução completa do tuning).

---

## 3. Passo 1b — Validação (`scripts/validate.py`)

### 3.1 O que faz

- Carrega **6 instâncias** de validação: `c101C10`, `c106C15`, `r102C10`, `r102C15`, `rc102C10`, `rc103C15`.  
- Para cada uma, executa **5 runs** de **NSGA-II** (300 gerações, população 100, sementes fixas).  
- Conta soluções **factíveis** (`F < 1e7` em todos os objetivos).  
- Para os melhores indivíduos segundo f1, f2 e f3, executa **`verify_solution`**: reexecuta Split + InsertStations e simula percurso verificando **bateria**, **capacidade**, **janelas de tempo** e **depósito início/fim**.

### 3.2 Uso

```bash
python scripts/validate.py
```

### 3.3 Interpretação

- **f1/f2** podem ser confrontados com melhores soluções conhecidas da literatura Schneider (quando existirem para o mesmo recorte da instância).  
- **f3** costuma não ter BKS publicado da mesma forma; a validação enfatiza **consistência interna** e ausência de violações nas verificações manuais.

---

## 4. Passo 2a — Calibração (`scripts/calibrate.py`)

### 4.1 O que faz

- Instâncias **pequenas** (`c101C10`, `r102C15`): até **50 000** avaliações por *run*.  
- Instâncias **grandes** (`c101_21`, `r101_21`, `r204_21`): até **500 000** avaliações por *run*.  
- **5 runs** por instância, NSGA-II, população 100.  
- **Callback** `FrontRecorder`: a cada **500** avaliações (por limiar progressivo, não por módulo exato — ver secção 7.4), grava a frente não dominada **factível** da população atual.  
- Após todos os *runs*:  
  - `ref_point = 1.1 × max(F)` sobre todas as soluções factíveis acumuladas na instância;  
  - curva de HV por *run*;  
  - **estabilização**: primeiro ponto em que, em janela de 5 000 avaliações, o ganho de HV fica abaixo de **0,5 %** do HV final;  
  - **critério** = estabilização × **1,2**, arredondado para múltiplo de **1 000**, limitado ao máximo de avaliações da instância.  
- Para `r101_21`, calcula se a frente é **trivial** (CV do HV final entre runs &lt; 0,1 %).

### 4.2 Uso

```bash
python scripts/calibrate.py              # todas as instâncias (demorado)
python scripts/calibrate.py --small-only   # só C10/C15 (rápido)
```

Recomenda-se `PYTHONUNBUFFERED=1` para ver o log em tempo real:

```bash
PYTHONUNBUFFERED=1 python scripts/calibrate.py
```

### 4.3 Resumo do `calibration_summary.json` atual (exemplo do repositório)

Valores ilustrativos já presentes em `results/calibration/calibration_summary.json`:

| Instância | Estabilização (evals) | Critério (evals) | Observação |
|-----------|----------------------:|-----------------:|------------|
| c101C10   | 7 000 | 9 000 | — |
| r102C15   | 31 000 | 38 000 | Define `criterion_small` = **38 000** |
| c101_21   | 145 500 | 175 000 | Runs longos (~11 min/run em ambiente de referência) |
| r101_21   | 500 000 | 500 000 | `ref_point: null`, `trivial: true` — ver secção 7.5 |
| r204_21   | 98 500 | 119 000 | Runs muito longos (~34 min/run no mesmo ambiente) |

Campos agregados:

- `criterion_small`: máximo entre critérios das instâncias C10/C15 (ex.: **38 000**).  
- `criterion_large`: máximo entre instâncias `*_21` (ex.: **500 000**, empurrado por `r101_21`).

O script `tune.py` lê `criterion_small` quando o ficheiro existe; caso contrário usa **50 000** como *fallback*.

---

## 5. Passo 3a — Tuning (`scripts/tune.py`)

### 5.1 Desenho experimental

- **6 instâncias de treino** (C15, distintas do conjunto primário do TCC):  
  `c103C15`, `c202C15`, `r102C15`, `r202C15`, `rc103C15`, `rc202C15`.  
- **10 runs** por (configuração × instância), sementes 1001–1010.  
- **72 configurações** no total:  
  - **NSGA-II**: 3 × 4 = 12 (`p_crossover` ∈ {0,7; 0,8; 0,9}, `p_mutation` ∈ {0,05; 0,10; 0,20; 1/n}).  
  - **MOEA/D**: 4 × (3 + 9) = 48 (vizinhança T ∈ {10,15,20,30}; Tchebycheff com 3 `prob_neighbor_mating`; PBI com θ ∈ {1,3,5} e 3 `prob_neighbor_mating`).  
  - **SMS-EMOA**: 12 (mesma grelha que NSGA-II).  

### 5.2 Hipertvolume e ponto de referência

Para **cada algoritmo** e **cada instância**, o ponto de referência do HV é **1,1 × máximo** dos objetivos sobre **todas** as frentes factíveis de **todas** as configurações daquele algoritmo naquela instância — garantindo comparabilidade entre configurações do mesmo algoritmo na mesma instância.

A **métrica de seleção** é a média do HV global entre as 6 instâncias (média das médias por instância).

### 5.3 Uso

```bash
python scripts/tune.py                    # os três algoritmos (várias horas)
python scripts/tune.py --algorithm nsga2
python scripts/tune.py --algorithm moead
python scripts/tune.py --algorithm smsemoa
```

Saída principal: `results/tuning/tuning_results.json`.

### 5.4 Bug corrigido no script (importante)

Havia um **erro lógico**: ao construir o dicionário `results` num loop `for label in fronts`, o campo `"config"` usava a variável `cfg` do **último** elemento de `enumerate(configs)`, pelo que **todas** as entradas guardavam a mesma configuração — inclusive `best_config` no JSON final, que podia **não corresponder** ao `best_label`.

**Correção:** mantém-se um mapa `label_to_cfg[label] = cfg` no primeiro loop e, na fase 3, usa-se `"config": label_to_cfg[label]`.

Se o ficheiro `tuning_results.json` foi gerado **antes** desta correção, **deve ser ignorado** ou o tuning deve ser **reexecutado** para obter `best_config` fiável.

---

## 6. Amostragem `TWBiasedSampling` (`src/sampling.py`)

### 6.1 Motivação

Em instâncias grandes com janelas de tempo apertadas (ex.: `c101_21`), permutações **uniformemente aleatórias** podem ter **taxa de factibilidade ~0 %** após o decodificador. Nesse cenário, a população inicial do EA fica quase toda no platô de penalidade e a pressão seletiva não consegue explorar de forma útil.

### 6.2 Ideia

- **75 %** da população: permutação = `argsort(ready_time + ruído)`, com ruído uniforme em `[−σ, σ]` e **σ** proporcional à **mediana da largura** das janelas de tempo.  
- **25 %**: permutações puramente aleatórias (diversidade).

Isto aumenta fortemente a probabilidade de ordens compatíveis com o Split+TW, sem eliminar variedade.

### 6.3 Integração

`TWBiasedSampling` é usado em `main.py`, `scripts/validate.py`, `scripts/calibrate.py` e `scripts/tune.py` no lugar de `PermutationRandomSampling` puro.

**Nota metodológica para o TCC:** se a especificação exigir “amostragem aleatória pura”, documente explicitamente esta escolha como **pré-processamento / inicialização informada pelo problema** necessária para factibilidade em instâncias realistas, ou alinhe com o orientador.

---

## 7. Problemas encontrados e como foram resolvidos

### 7.1 Split sem verificação de janelas de tempo (fase inicial do projeto)

- **Sintoma:** taxa de factibilidade **0 %** em instâncias como `c101C10` com uma única rota por capacidade, mas infactível no tempo.  
- **Causa:** o pseudocódigo em `proximos_passos.md` para o Split considerava sobretudo **capacidade**; TW só apareciam implicitamente nas fases seguintes.  
- **Resolução:** inclusão de verificação **`t_arr > due[cj]`** no laço da DP do Split, mantendo complexidade O(n²) com atualização incremental dos tempos de partida.

### 7.2 `np.inf` nos objetivos e pymoo

- **Sintoma:** `RuntimeWarning` (operações inválidas) no cálculo de *crowding distance* e métricas.  
- **Causa:** `inf - inf` e semelhantes.  
- **Resolução:** penalidade **finita** `_INFEASIBLE = (1e8, 1e8, 1e8)`; filtro de factibilidade com `F < 1e7`.

### 7.3 Factibilidade nula em `c101_21` com amostragem aleatória

- **Sintoma:** após poucas milhares de avaliações, **nenhuma** solução factível na população final.  
- **Causa:** ordem aleatória dos 100 clientes raramente produz sequências compatíveis com TW apertadas após Split + recargas.  
- **Resolução:** `TWBiasedSampling` (secção 6).

### 7.4 Callback de calibração sem *checkpoints* (`n_eval % 500`)

- **Sintoma:** “0 checkpoints” e mensagem “Nenhuma solução factível” no resumo agregado, apesar de haver indivíduos factíveis na última geração.  
- **Causa:** com `eliminate_duplicates` e outros detalhes do avaliador, `n_eval` **não** coincide necessariamente com múltiplos exatos de 500 em cada `notify`.  
- **Resolução:** `FrontRecorder` passou a usar **limiar progressivo** (`_next_threshold += interval`) em vez de `n_evals % interval == 0`.

### 7.5 `r101_21`: frente trivial / sem ponto de referência

- **Sintoma:** `ref_point: null`, `trivial: true`, critério no teto (500 000 evals).  
- **Interpretação provável:** combinação de instância + decodificador + penalidade faz com que **não** se acumulem soluções factíveis nos *checkpoints* da mesma forma que nas outras, ou a frente colapsa num ponto.  
- **Ação sugerida no TCC:** seguir a recomendação já prevista no script — **substituir `r101_21` por `r102_21`** (ou outra instância R com TW menos degenerada) no experimento primário, e discutir com o orientador.

### 7.6 Saída Python bufferizada em *jobs* longos

- **Sintoma:** ficheiros de log aparentemente vazios durante minutos.  
- **Resolução:** executar com `PYTHONUNBUFFERED=1` ou `python -u`.

### 7.7 Custo computacional

- Calibração completa e tuning completo são **horas a dias** dependendo da máquina.  
- **Sugestão:** não correr calibração completa e tuning pesado em paralelo no mesmo CPU se quiser tempos previsíveis.

---

## 8. Estado atual e próximos passos sugeridos

1. **Validação (1b):** script pronto; basta reexecutar após alterações no `decoder`.  
2. **Calibração (2a):** script pronto; interpretar `r101_21` com cautela e considerar troca de instância.  
3. **Tuning (3a):** script corrigido quanto a `best_config`; **reexecutar** MOEA/D e SMS-EMOA se ainda não existirem no JSON, e **reexecutar** NSGA-II se o JSON antigo estiver inconsistente.  
4. **Documentação metodológica:** registrar no texto do TCC a inicialização `TWBiasedSampling` e o critério de parada efetivo usado (38 000 vs 175 000 vs 500 000 conforme classe de instância).  
5. **Alinhar `proximos_passos.md`:** atualizar o pseudocódigo do Split para mencionar explicitamente a **verificação de TW** na DP, para não induzir regressões futuras.

---

## 9. Referência rápida de comandos

```bash
# Validação
PYTHONUNBUFFERED=1 python scripts/validate.py

# Calibração (rápida / completa)
PYTHONUNBUFFERED=1 python scripts/calibrate.py --small-only
PYTHONUNBUFFERED=1 python scripts/calibrate.py

# Tuning (por partes)
PYTHONUNBUFFERED=1 python scripts/tune.py --algorithm nsga2
PYTHONUNBUFFERED=1 python scripts/tune.py --algorithm moead
PYTHONUNBUFFERED=1 python scripts/tune.py --algorithm smsemoa
```

---

*Documento gerado para acompanhar a implementação experimental do TCC. Última atualização alinhada ao repositório com `calibration_summary.json`, correção em `scripts/tune.py` e presença de `src/sampling.py`.*
