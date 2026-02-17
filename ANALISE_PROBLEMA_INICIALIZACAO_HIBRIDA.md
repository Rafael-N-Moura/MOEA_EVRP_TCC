# Análise: Problema na Inicialização Híbrida da População

## 1. Contexto

O algoritmo `BatteryFocusedNSGA2` foi projetado para iniciar com uma população híbrida:
- **50% viáveis**: Avaliadas com `force_battery_feasible=True` (modo conservador)
- **50% inviáveis**: Avaliadas com `force_battery_feasible=False` (modo arriscado)

Isso garante diversidade inicial e permite que o algoritmo explore tanto soluções seguras quanto soluções eficientes desde o início.

## 2. O Problema Identificado

### 2.1. Sintoma

Ao executar o algoritmo, o log mostrava:
```
Gen   0 | Pop: 100 | Viáveis:   0 (  0.0%) | Inviáveis: 100 [Inicial]
```

**Esperado**: `Viáveis: 50 (50.0%)`

**Obtido**: `Viáveis: 0 (0.0%)`

### 2.2. Causa Raiz

O problema estava na implementação de `_initialize_advance()`:

```python
def _initialize_advance(self, infills=None, **kwargs):
    # ...
    # Chama inicialização padrão
    super()._initialize_advance(infills=infills, **kwargs)
    
    # Após inicialização, reavalia primeira metade com force_battery_feasible=True
    n_feasible = len(self.pop) // 2
    problem.force_battery_feasible = True
    for i in range(n_feasible):
        if i < len(self.pop):
            self.evaluator.eval(problem, self.pop[i], **kwargs)
```

**Problema**: 
1. `super()._initialize_advance()` já avaliava **toda** a população com `force_battery_feasible=False` (valor padrão do problema)
2. A tentativa de reavaliar apenas a primeira metade não estava funcionando corretamente
3. Resultado: toda a população ficava inviável

## 3. Tentativa de Correção e Novo Erro

### 3.1. Primeira Tentativa

Tentamos criar populações separadas e avaliá-las:

```python
# Extrai arrays X da população
X_all = self.pop.get("X")

# Avalia primeira metade com force_battery_feasible=True
X_feasible = X_all[:n_feasible]
feasible_pop = Population.new("X", X_feasible)
self.evaluator.eval(problem, feasible_pop, **kwargs)
```

### 3.2. O Erro

```
AttributeError: 'Individual' object has no attribute 'astype'
```

**Stack trace**:
```
File "src/problem.py", line 66, in _evaluate
    individual = x.astype(int).tolist()
                 ^^^^^^^^
AttributeError: 'Individual' object has no attribute 'astype'
```

### 3.3. Por Que o Erro Aconteceu?

O método `_evaluate()` do `EVRPTWProblem` espera receber um **array numpy**:

```python
def _evaluate(self, x, out, *args, **kwargs):
    # x é esperado como array numpy
    individual = x.astype(int).tolist()  # ← Falha se x não é array numpy
    solution = decode(individual, self.context, ...)
    # ...
```

**O que aconteceu**:
1. Criamos uma `Population` com `Population.new("X", X_feasible)`
2. Passamos essa `Population` para `self.evaluator.eval(problem, feasible_pop, **kwargs)`
3. O evaluator do pymoo **itera** sobre a população e passa cada **objeto `Individual`** para `problem._evaluate()`
4. `_evaluate()` tenta chamar `.astype()` em um objeto `Individual`, que não tem esse método
5. **Erro!**

**Fluxo do Erro**:
```
Population.new("X", X_feasible)
    ↓
self.evaluator.eval(problem, feasible_pop, ...)
    ↓
[Para cada Individual na Population]
    ↓
problem._evaluate(Individual, out, ...)  ← Individual não é array numpy!
    ↓
individual = x.astype(int).tolist()  ← AttributeError!
```

