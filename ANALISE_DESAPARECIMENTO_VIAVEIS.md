# Análise: Por Que Estamos Ficando Sem Soluções Viáveis?

## 1. O Problema

Durante a execução do algoritmo, em algum momento (geração 12 no exemplo), todas as soluções viáveis desaparecem da população, resultando em `feasible_mask` sendo todo `False` e `feasible_pop` vazio.

## 2. Definição de Viabilidade

Uma solução é considerada **viável** quando:
- **G2 <= 0**: Não há violação de bateria (déficit de energia = 0)

Uma solução é considerada **inviável** quando:
- **G2 > 0**: Há violação de bateria (déficit de energia > 0)

**Código**:
```python
feasible_mask = pop.get("G")[:, 1] <= 0  # G2 <= 0
```

## 3. Por Que Soluções Viáveis Estão Desaparecendo?

### 3.1. Modo de Avaliação Durante Evolução

**Problema Principal**: Durante a evolução, sempre usamos `force_battery_feasible=False`:

```python
def _advance(self, infills=None, **kwargs):
    # Durante avaliação, sempre usa force_battery_feasible=False
    # para expor violações reais
    if hasattr(self.problem, 'force_battery_feasible'):
        self.problem.force_battery_feasible = False
```

**Consequência**: 
- O decoder **não força** retorno ao depósito quando bateria está baixa
- Soluções podem ter violações de bateria (G2 > 0)
- Se a heurística construtiva não conseguir gerar soluções viáveis naturalmente, **todas** as soluções serão inviáveis

### 3.2. Inicialização Híbrida Pode Não Estar Funcionando

**Código de inicialização**:
```python
def _initialize_advance(self, infills=None, **kwargs):
    # ...
    # Após inicialização, reavalia primeira metade com force_battery_feasible=True
    n_feasible = len(self.pop) // 2
    problem.force_battery_feasible = True
    for i in range(n_feasible):
        if i < len(self.pop):
            self.evaluator.eval(problem, self.pop[i], **kwargs)
    problem.force_battery_feasible = original_flag
```

**Problema Potencial**:
- A primeira metade é reavaliada com `force_battery_feasible=True`, mas isso **não garante** que G2 será 0
- O decoder com `force_battery_feasible=True` apenas **tenta** retornar ao depósito preventivamente, mas se já houver violações acumuladas, G2 ainda pode ser > 0
- Além disso, após a primeira geração, todas as soluções são avaliadas com `force_battery_feasible=False`

### 3.3. Crossover e Mutation Geram Soluções Inviáveis

**Problema**: 
- `OrderCrossover` e `InversionMutation` preservam a estrutura da permutação, mas **não garantem** viabilidade
- Se os pais são inviáveis, os filhos provavelmente também serão inviáveis
- Se a heurística construtiva não consegue gerar soluções viáveis a partir da permutação, todas as soluções serão inviáveis

### 3.4. Sobrevivência Customizada Pode Estar Eliminando Viáveis

**Lógica de sobrevivência**:
```python
# Cota viável: 75% (n_feasible_target = 75)
# Cota inviável: 25% (n_infeasible_target = 25)

# Seleciona viáveis usando Rank & Crowding Distance
n_select_feasible = min(n_feasible_target, len(feasible_sorted))
```

**Problema Potencial**:
- Se há poucas soluções viáveis (ex: 5), mas a cota é 75, selecionamos apenas 5
- Se essas 5 soluções viáveis são **piores** que as inviáveis (em termos de f1), elas podem ser eliminadas pelo non-dominated sorting
- Se todas as soluções viáveis estão em frentes piores que as inviáveis, podem ser eliminadas

### 3.5. Acasalamento Direcionado Pode Estar Reduzindo Viáveis

**Lógica de acasalamento**:
```python
# Pai 1: Do grupo viável
# Pai 2: Do grupo inviável
```

**Problema Potencial**:
- Se há poucas soluções viáveis, elas são usadas repetidamente como Pai 1
- Isso pode causar **convergência prematura** ou **perda de diversidade** nas soluções viáveis
- Se as soluções viáveis são ruins, seus filhos também serão ruins ou inviáveis

## 4. Análise do Fluxo

### Geração 1 (Inicialização):
1. **HybridSampling** gera população inicial
2. Primeira metade é avaliada com `force_battery_feasible=True` → **Algumas viáveis**
3. Segunda metade é avaliada com `force_battery_feasible=False` → **Provavelmente inviáveis**

### Geração 2+ (Evolução):
1. **Todas** as soluções são avaliadas com `force_battery_feasible=False`
2. Crossover entre viável (Pai 1) e inviável (Pai 2) → **Filho provavelmente inviável**
3. Sobrevivência seleciona 75% viáveis + 25% inviáveis
4. Se há poucas soluções viáveis, elas podem ser **piores** que as inviáveis
5. Non-dominated sorting pode eliminar viáveis ruins em favor de inviáveis bons

### Geração N (Problema):
1. Todas as soluções viáveis foram eliminadas (eram ruins)
2. Apenas soluções inviáveis restam
3. `feasible_mask` é todo `False`
4. `feasible_pop` está vazio
5. Erro ao tentar acessar `opt.get("cv")` quando `opt` está vazio

## 5. Por Que Soluções Viáveis São "Ruins"?

### 5.1. Trade-off Viabilidade vs Custo

**Soluções Viáveis** (G2 = 0):
- **Custo alto**: Muitos veículos, muitas recargas, rotas longas
- **Garantem** que não há violação de bateria
- **Tendem a ser conservadoras**

**Soluções Inviáveis** (G2 > 0):
- **Custo baixo**: Poucos veículos, poucas recargas, rotas curtas
- **Violam** bateria, mas são **eficientes**
- **Tendem a ser agressivas**

### 5.2. Dominância de Pareto

Se uma solução inviável tem:
- **f1 (custo) menor** que uma solução viável
- **f2 (insatisfação) menor ou igual** que uma solução viável

Então a solução inviável **domina** a solução viável, e a viável é eliminada pelo non-dominated sorting.

### 5.3. Exemplo Numérico

```
Solução Viável A:  f1=6000, f2=0.5, G2=0.0
Solução Inviável B: f1=5500, f2=0.4, G2=10.0
```

**Análise de Dominância**:
- B tem f1 menor (melhor) e f2 menor (melhor)
- **B domina A** (mesmo sendo inviável)
- A é eliminada

## 6. Soluções Propostas

### Solução 1: Garantir Mínimo de Soluções Viáveis

Modificar a sobrevivência para **garantir** que sempre haja pelo menos X% de soluções viáveis:

```python
# Garante mínimo de 10% de soluções viáveis
min_feasible = max(1, int(n_select * 0.10))
if len(feasible_indices) > 0:
    # Seleciona pelo menos min_feasible viáveis
    n_select_feasible = max(min_feasible, min(n_feasible_target, len(feasible_sorted)))
```

### Solução 2: Proteger Melhores Soluções Viáveis

Mesmo que sejam dominadas, preservar as **melhores** soluções viáveis:

```python
# Sempre preserva pelo menos as top-K soluções viáveis
if len(feasible_indices) > 0:
    # Ordena viáveis por f1 (custo)
    feasible_f1 = feasible_pop.get("F")[:, 0]
    top_feasible = feasible_indices[np.argsort(feasible_f1)[:min_feasible]]
    # Garante que essas estão em selected
```

### Solução 3: Reavaliar Periódicamente com `force_battery_feasible=True`

A cada N gerações, reavaliar algumas soluções com `force_battery_feasible=True` para "reparar" soluções inviáveis:

```python
if self.n_gen % 10 == 0:  # A cada 10 gerações
    # Reavalia 10% da população com force_battery_feasible=True
    n_repair = int(self.pop_size * 0.10)
    repair_indices = np.random.choice(len(self.pop), n_repair, replace=False)
    original_flag = self.problem.force_battery_feasible
    self.problem.force_battery_feasible = True
    for idx in repair_indices:
        self.evaluator.eval(self.problem, self.pop[idx], **kwargs)
    self.problem.force_battery_feasible = original_flag
```

### Solução 4: Usar Penalização em Vez de Restrições

Em vez de usar restrições (G), usar penalização no f1:

```python
# Adiciona penalização proporcional a G2
if g2 > 0:
    f1 = f1 + g2 * PENALTY_FACTOR  # Penalização proporcional
```

Isso garante que soluções inviáveis sempre sejam piores que viáveis, mesmo que tenham custo menor.

### Solução 5: Melhorar Heurística Construtiva

Melhorar o decoder para gerar mais soluções viáveis naturalmente, mesmo com `force_battery_feasible=False`:

- Recarga preventiva mais agressiva
- Melhor seleção de estações de recarga
- Reordenação de clientes dentro de rotas

## 7. Recomendação Imediata

**Implementar Solução 1 + Solução 2**: Garantir que sempre haja pelo menos 10% de soluções viáveis na população, e proteger as melhores soluções viáveis mesmo que sejam dominadas.

Isso garante que:
1. Sempre há soluções viáveis na população
2. As melhores soluções viáveis são preservadas
3. O algoritmo pode "aprender" a gerar soluções viáveis melhores ao longo do tempo

## 8. Conclusão

O desaparecimento de soluções viáveis ocorre porque:

1. **Durante evolução, todas as soluções são avaliadas com `force_battery_feasible=False`**
2. **Soluções viáveis tendem a ter custo mais alto** (são conservadoras)
3. **Soluções inviáveis podem dominar viáveis** se tiverem custo menor
4. **Non-dominated sorting elimina soluções viáveis dominadas**
5. **Após algumas gerações, todas as viáveis foram eliminadas**

A solução é **garantir preservação mínima** de soluções viáveis, mesmo que sejam dominadas, para manter diversidade e permitir que o algoritmo evolua soluções viáveis melhores.
