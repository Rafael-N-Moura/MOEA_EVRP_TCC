# Plano de implementação — NSGA-II com decoder (π, δ) e restrições de violação

Este documento descreve como implementar a abordagem do **decoder_spec.md** (cromossomo híbrido π|δ) com **dois objetivos** e **duas restrições** (violações cv_energia e cv_tw), **em paralelo** à implementação atual, mantendo o sistema modular e a abordagem anterior intacta.

---

## 1. Visão geral

**Formulação a implementar:**

- **Objetivos:** F = (f₁, f₂)
  - **f₁** = custo total de rota (soma das distâncias dos arcos)
  - **f₂** = folga normalizada em [−1, 0]: **−Σ max(0, l_j − τ_j) / Σ(l_j − e_j)** (τ_j = início de serviço no cliente j; denominador = soma das larguras de janela)

- **Restrições:** G = (g₁, g₂)
  - **g₁** = cv_energia (déficit de energia; ≥ 0 quando há violação)
  - **g₂** = cv_tw (violação de janela de tempo; ≥ 0 quando há atraso)

No Pymoo as restrições são satisfeitas quando **g ≤ 0**. Para que factível corresponda a “nenhuma violação” (cv_energia = 0 e cv_tw = 0), passamos **g₁ = cv_energia** e **g₂ = cv_tw**: assim, factível quando g₁ ≤ 0 e g₂ ≤ 0, ou seja, cv_energia = 0 e cv_tw = 0.

| Componente | Atual (mantido) | Novo (a adicionar) |
|------------|------------------|---------------------|
| **Decoder** | `src/decoder.py` — permutação apenas, perfis C/A, recarga heurística | `src/decoder_infeasible.py` — (π, δ), recarga = δ·(Q−SoC), violação em cv_energia/cv_tw |
| **Problema** | `src/problem.py` — 2 obj (custo, insatisfação), G opcional | `src/problem_2obj_constraints.py` — 2 obj (f₁ custo rota, f₂ folga média), 2 restrições (g₁=cv_energia, g₂=cv_tw) |
| **Objetivos** | f₁ custo, f₂ insatisfação | f₁ custo total de rota, f₂ folga média normalizada |
| **Restrições** | G1 capacidade, G2 bateria (opcional) | g₁ = cv_energia, g₂ = cv_tw (factível quando ambos 0) |
| **Uso** | `main.py` → nsga2, battery-focused, moead | `main.py` → novo modo `--algorithm nsga2-spec` (ou `--formulation spec`) |

A escolha entre as duas abordagens será feita por **argumento de linha de comando**, sem alterar o comportamento atual quando o novo modo não for usado.

---

## 2. Novos arquivos

### 2.1 `src/decoder_infeasible.py`

Responsável por decodificar o cromossomo **(π, δ)** conforme a especificação (docs/decoder_spec.md).

- **Entrada**
  - `pi`: lista de inteiros — permutação dos **índices** dos clientes (0..n-1).
  - `delta`: array ou lista de float, tamanho R (ex.: R = n), cada elemento em [0, 1].
  - `context`: `Context` (mesmo de `src/model.py`).

- **Saída**
  - Objeto que contenha:
    - `routes`: lista de rotas (mesma estrutura de `Route` do model, para reuso de visualização/IO).
    - `f1`: custo total de roteamento (soma das distâncias).
    - `f2`: folga normalizada em [−1, 0]: −Σ max(0, l_j−τ_j) / Σ(l_j−e_j).
    - `cv_energia`: déficit total de energia (≥ 0).
    - `cv_tw`: violação total de janela de tempo (≥ 0).

- **Implementação**
  - Seguir o pseudocódigo da Seção 3 do decoder_spec (inicialização, loop por cliente, Passos 1–5, subrotina retornar_ao_depósito, fechamento).
  - Ordem estrita: **Passo 1 (capacidade)** antes de qualquer cálculo de energia; depois Passo 2 (energia e inserção de estação com próximo δ), Passo 3 (viagem ao cliente), Passo 4 (TW), Passo 5 (serviço).
  - Casos limite: idx_δ ≥ R → δ_usar = 1.0; SoC travado em 0 após déficit; não corrigir δ quando recarga insuficiente; retorno ao depósito após l_0 → acumular em cv_tw (Opção A).
  - Reutilizar `Context`, `Node`, `Route` (e, se conveniente, `RouteStep`) de `src/model.py`. Pode-se definir um **dataclass local** para o retorno (ex.: `DecodedSolutionInfeasible`) com `f1, f2, routes, cv_energia, cv_tw` para não poluir `Solution` do modelo atual.

- **Dependências**
  - Apenas `src/model.py` (Context, Node, Route, NodeType) e parâmetros já presentes no Context (battery_capacity, vehicle_capacity, consumption_rate, recharge_rate, velocity, depot, stations, customers). Nenhuma dependência de `src/decoder.py`.

### 2.2 `src/problem_2obj_constraints.py`

Problema Pymoo com **2 objetivos** (f₁, f₂), **2 restrições** (g₁, g₂) e **variáveis mistas** (permutação + contínuo).

- **Herança**
  - `pymoo.core.problem.ElementwiseProblem`. Variáveis: um único array X de forma (n + R,): primeiras n posições = permutação dos índices (0..n-1), últimas R = δ ∈ [0, 1].

- **Dimensões**
  - `n_var = n_customers + R`, com R = n_customers (valor conservador da spec).
  - `n_obj = 2`.
  - `n_constr = 2` (g₁ = cv_energia, g₂ = cv_tw).

- **Objetivos**
  - **f₁**: custo total de rota (soma das distâncias).
  - **f₂**: folga normalizada −Σ max(0, l_j−τ_j) / Σ(l_j−e_j) ∈ [−1, 0].

- **Restrições** (Pymoo: satisfeitas quando g ≤ 0)
  - **g₁** = cv_energia (valor ≥ 0; factível quando 0).
  - **g₂** = cv_tw (valor ≥ 0; factível quando 0).  
  Assim, `out["G"] = np.array([cv_energia, cv_tw])`. Factível ⟺ cv_energia = 0 e cv_tw = 0.  
  *Nota:* No Pymoo a restrição é satisfeita quando **g ≤ 0**. Por isso passamos g₁ = cv_energia e g₂ = cv_tw (e não −cv_energia/−cv_tw): quando não há violação, cv = 0 e g = 0 ≤ 0; quando há violação, cv > 0 e g > 0, logo a restrição fica violada.

- **Avaliação**
  - Extrair de `x`: `pi = x[:n].astype(int)`, `delta = x[n:]` (clip em [0,1] se necessário).
  - Chamar `decode_infeasible(pi, delta, context)`.
  - Preencher `out["F"] = np.array([f1, f2])` e `out["G"] = np.array([cv_energia, cv_tw])`.
  - Tratar `Individual`/`x.X` como em `problem.py` atual para compatibilidade com Pymoo.

- **Parâmetros**
  - `context`: Context.

- **Bounds**
  - `xl = [0]*n + [0.0]*R`, `xu = [n-1]*n + [1.0]*R`. Os operadores híbridos garantem π permutação válida e δ ∈ [0, 1].

---

## 3. Representação do indivíduo e operadores

O Pymoo espera um vetor de decisão. Estratégia recomendada:

- **X** tem shape `(n + R,)`:
  - `X[0:n]`: permutação dos índices dos clientes (0 a n-1), sem repetição.
  - `X[n:n+R]`: valores em [0, 1] para δ.

### 3.1 Sampling híbrido

- **Classe**: ex. `HybridPermutationDeltaSampling` em `src/sampling_hybrid.py` (ou dentro de `problem_3obj.py` se for o único uso).
- Gera população inicial:
  - Para cada indivíduo: amostrar permutação aleatória de 0..n-1 (como `PermutationRandomSampling` só na parte π); amostrar R valores uniformes em [0, 1] para δ.
- Implementar `_do(self, problem, n_samples, **kwargs)` retornando array de forma `(n_samples, n + R)`.

### 3.2 Crossover híbrido

- **Classe**: ex. `HybridCrossover` em `src/crossover_hybrid.py`.
- **π**: Order Crossover (OX) entre os segmentos `x1[:n]` e `x2[:n]` (como hoje).
- **δ**: crossover contínuo entre `x1[n:]` e `x2[n:]` — ex. SBX (Simulated Binary Crossover) ou média/combinação convexa com chance 0.5; manter valores em [0, 1].
- Entrada: matriz de pais (2, n+R); saída: 2 filhos (2, n+R).

### 3.3 Mutação híbrida

- **Classe**: ex. `HybridMutation` em `src/mutation_hybrid.py`.
- **π**: Inversion Mutation (ou mesma mutação do decoder atual) aplicada só em `x[:n]`.
- **δ**: perturbação em uma ou mais posições de `x[n:]` — ex. substituir por valor uniforme em [0, 1] com probabilidade `pm` por gene, ou Gaussian com sigma pequeno e clip em [0, 1].
- Aplicar mutação independente às duas partes.

### 3.4 Eliminação de duplicatas

- Para variáveis mistas, `eliminate_duplicates` do Pymoo pode comparar o array inteiro. Se quiser considerar duplicata só pela permutação π, pode-se usar um `Repair` ou callback que, em caso de duplicata (ex.: mesmo π), perturba levemente δ. Opcional numa primeira versão; usar `eliminate_duplicates=True` com comparação padrão de X.

---

## 4. Integração com o resto do sistema

### 4.1 `src/__init__.py`

- Exportar as novas entradas públicas:
  - `decode_infeasible` (e, se existir, o dataclass de retorno) de `decoder_infeasible`.
  - `EVRPTWProblem2ObjConstraints` (ou nome escolhido) de `problem_2obj_constraints`.
- Manter todas as exportações atuais (`decode`, `EVRPTWProblem`, etc.) inalteradas.

Exemplo:

```python
from .decoder import decode
from .problem import EVRPTWProblem, PENALTY_COST, PENALTY_DISSATISFACTION
from .decoder_infeasible import decode_infeasible   # novo
from .problem_2obj_constraints import EVRPTWProblem2ObjConstraints   # novo

__all__ = [
    ...
    'decode_infeasible',
    'EVRPTWProblem2ObjConstraints',
]
```

### 4.2 `main.py`

- Adicionar opção de algoritmo ou de formulação:
  - **Opção A**: `--algorithm nsga2-spec` (recomendado para clareza).
  - **Opção B**: `--formulation spec` mantendo `--algorithm nsga2`, e internamente escolher problema/decoder conforme formulação.
- Quando o modo spec for escolhido:
  - Criar `context` com `parse_instance(args.instance)` (igual).
  - Instanciar `EVRPTWProblem2ObjConstraints(context)`.
  - Usar `NSGA2` com:
    - `sampling=HybridPermutationDeltaSampling()`
    - `crossover=HybridCrossover()`
    - `mutation=HybridMutation()`
    - `eliminate_duplicates=True`
  - Chamar `minimize(problem_spec, algorithm, ('n_gen', n_gen), ...)`.
- **Callbacks e logs**: o `NSGA2LoggingCallback` atual já suporta restrições G (f1, f2 e G1, G2). Para o novo problema, usar o mesmo callback: F tem 2 colunas (f1, f2), G tem 2 colunas (g₁=cv_energia, g₂=cv_tw). Factível quando g₁ ≤ 0 e g₂ ≤ 0 (ou seja, cv_energia = 0 e cv_tw = 0). O callback pode mostrar proporção de factíveis e estatísticas de f1/f2 separadas para factíveis e inviáveis.
- **Salvamento de frente**: ao salvar `res.F` em `.npz`, duas colunas (f1, f2); opcionalmente salvar também `res.G` para análise de violação. Scripts de comparação de frentes continuam em 2D (f1×f2).

### 4.3 Battery-focused e MOEA/D

- **BatteryFocusedNSGA2** e **MOEA/D** continuam usando `EVRPTWProblem` e `decode` atuais. Nenhuma alteração neles até que se queira uma variante “battery-focused spec” ou “MOEA/D spec” no futuro.
- Assim, a abordagem anterior permanece 100% disponível.

### 4.4 Scripts e testes

- Scripts que usam `decode` e `EVRPTWProblem` (ex.: `run_batch.py`, `scripts/compare_decoder_profiles.py`, `scripts/feasibility_proportion_random.py`) permanecem como estão.
- Novos scripts (opcional, em fase posterior):
  - Teste de `decode_infeasible` com (π, δ) fixos para validar contra o pseudocódigo.
  - Teste de `EVRPTWProblem2ObjConstraints` com população pequena e 1–2 gerações para checar forma de F, G e factibilidade (g₁ = g₂ = 0).
  - `scripts/compare_pareto_fronts.py` (ou variante) para frentes f1×f2 (factíveis ou todas).

---

## 5. Modelo de dados (reuso e extensão)

- **Context, Node, Route, NodeType**: reutilizar de `src/model.py` sem alteração.
- **Solution** (atual): usada pelo decoder atual e pelo problema atual; não precisa ser modificada.
- **Retorno do decoder inviável**: usar um dataclass dedicado em `decoder_infeasible.py`, por exemplo:

  - `routes`: list de `Route` (ou estrutura equivalente com sequência depósito–clientes/estações–depósito) para compatibilidade com qualquer visualização/export que use rotas.
  - `f1`, `f2`, `cv_energia`, `cv_tw`.

Assim, o `model.py` permanece estável e o novo decoder não depende do significado de `total_cost`/`avg_dissatisfaction`/`battery_violation` do `Solution` atual.

---

## 6. Ordem sugerida de implementação

1. **decoder_infeasible.py**  
   Implementar a lógica da spec (passos 1–5, subrotina retorno, casos limite). Testes unitários ou script mínimo com uma instância pequena e (π, δ) fixos para validar f1, f2, cv_energia e cv_tw contra o pseudocódigo.

2. **problem_2obj_constraints.py**  
   Definir `EVRPTWProblem2ObjConstraints` com n_var = n+R, n_obj = 2, n_constr = 2, e `_evaluate` chamando `decode_infeasible` e preenchendo F = [f1, f2] e G = [cv_energia, cv_tw]. Testar com sampling “na mão” (permutação aleatória + δ aleatório) antes de plugar operadores híbridos.

3. **Sampling / Crossover / Mutação híbridos**  
   Implementar em módulos separados (ex.: `sampling_hybrid.py`, `crossover_hybrid.py`, `mutation_hybrid.py`) ou em um único módulo `src/operators_hybrid.py`. Garantir que π permaneça permutação válida e δ ∈ [0, 1].

4. **Integração em main.py**  
   Adicionar `--algorithm nsga2-spec` (ou equivalente), criação de `EVRPTWProblem2ObjConstraints`, NSGA2 com operadores híbridos, e uso do callback existente para 2 objetivos + 2 restrições.

5. **__init__.py**  
   Exportar `decode_infeasible` e `EVRPTWProblem2ObjConstraints`.

6. **Ajustes finos**  
   Documentação no TCC sobre a escolha de não corrigir δ (Caso 2 da spec); análise de proporção de factíveis na frente.

---

## 7. Resumo de arquivos

| Ação | Arquivo |
|------|---------|
| Manter sem alteração de contrato | `src/decoder.py`, `src/problem.py`, `src/model.py`, `src/parser.py` |
| Criar | `src/decoder_infeasible.py` |
| Criar | `src/problem_2obj_constraints.py` |
| Criar | `src/sampling_hybrid.py` (ou `operators_hybrid.py`) |
| Criar | `src/crossover_hybrid.py` (ou no mesmo módulo) |
| Criar | `src/mutation_hybrid.py` (ou no mesmo módulo) |
| Alterar (export + nova entrada) | `src/__init__.py` |
| Alterar (nova opção + ramo spec) | `main.py` |

Com isso, a implementação atual permanece intacta e a nova abordagem (2 objetivos f₁/f₂, 2 restrições g₁=cv_energia e g₂=cv_tw, cromossomo π|δ) fica disponível de forma modular e integrada ao fluxo principal.
