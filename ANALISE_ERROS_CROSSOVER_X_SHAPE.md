# Análise Detalhada dos Erros no Crossover - Problema de Shape de X

## Resumo Executivo

O algoritmo `BatteryFocusedNSGA2` está enfrentando erros persistentes durante a operação de crossover (`OrderCrossover`). Os erros indicam que o array `X` (genótipos dos pais) não está sendo construído corretamente pelo Pymoo, resultando em shapes incorretos (2D ao invés de 3D) ou valores escalares ao invés de arrays.

## Erro 1: `ValueError: not enough values to unpack (expected 3, got 2)`

### Localização
- **Arquivo**: `venv/lib/python3.14/site-packages/pymoo/operators/crossover/ox.py`
- **Linha**: 75
- **Código**: `_, n_matings, n_var = X.shape`

### Contexto

O `OrderCrossover._do()` espera receber um array `X` com **3 dimensões**:
- **Dimensão 0**: `n_parents` (número de pais por mating, geralmente 2)
- **Dimensão 1**: `n_matings` (número de matings/cruzamentos)
- **Dimensão 2**: `n_var` (número de variáveis do problema, tamanho do genótipo)

**Shape esperado**: `(n_parents, n_matings, n_var)`, por exemplo `(2, 50, 100)` para 50 matings com genótipos de tamanho 100.

### Fluxo de Construção de X no Pymoo

O array `X` é construído dentro de `Crossover.do()` (arquivo `pymoo/core/crossover.py`):

```python
# Linha 25-26: Se parents é fornecido, transforma pop
if parents is not None:
    pop = [pop[mating] for mating in parents]

# Linha 33: Constrói X a partir dos pais
X = np.swapaxes(np.array([[parent.get("X") for parent in mating] for mating in pop]), 0, 1)
```

**O que acontece**:
1. `parents` é uma lista de listas de índices, por exemplo: `[[0, 1], [2, 3], [4, 5], ...]`
2. `pop[mating]` para cada `mating` em `parents` cria uma nova `Population` contendo os indivíduos correspondentes aos índices
3. `pop` se torna uma **lista de Population objects**, onde cada elemento é uma `Population` com os pais de um mating
4. Para cada `mating` (uma `Population`), itera sobre cada `parent` (um `Individual` dentro dessa `Population`)
5. `parent.get("X")` deve retornar o array numpy do genótipo (shape `(n_var,)`)
6. O resultado final após `np.swapaxes` deve ser `(n_parents, n_matings, n_var)`

### Por que o Erro Ocorre?

O erro `not enough values to unpack (expected 3, got 2)` indica que `X.shape` tem apenas **2 dimensões** ao invés de 3.

**Possíveis causas**:

1. **`pop[mating]` não retorna uma Population correta**:
   - Se `pop[mating]` retorna algo diferente de uma `Population` (por exemplo, uma lista de `Individual` objects diretamente), a estrutura aninhada `[[parent.get("X") for parent in mating] for mating in pop]` pode não funcionar como esperado.

2. **`parent.get("X")` retorna algo inesperado**:
   - Se `parent.get("X")` retorna um escalar, um array 2D, ou um objeto que não é um array numpy, `np.array(...)` pode não criar a estrutura 3D esperada.

3. **Problema na indexação de `pop`**:
   - Se `pop` não é uma `Population` padrão do Pymoo, ou se os índices em `parents` não correspondem corretamente aos indivíduos, `pop[mating]` pode falhar ou retornar algo inesperado.

### Exemplo do Problema

Suponha:
- `pop` tem 100 indivíduos
- `n_matings = 50` (50 cruzamentos)
- `n_parents = 2` (2 pais por mating)
- `n_var = 100` (genótipos de tamanho 100)

**Esperado**:
- `X.shape = (2, 50, 100)`

**O que está acontecendo**:
- `X.shape = (50, 100)` ou `(100, 50)` (2D ao invés de 3D)

Isso sugere que a estrutura `[[parent.get("X") for parent in mating] for mating in pop]` está resultando em um array 2D ao invés de 3D, possivelmente porque:
- `pop` (após `pop = [pop[mating] for mating in parents]`) não é uma lista de `Population` objects como esperado
- Ou `parent.get("X")` está retornando algo que não é um array 1D

## Erro 2: `ValueError: X é escalar para individual`

### Localização
- **Arquivo**: `src/battery_focused_nsga2.py`
- **Linha**: 416 (dentro do fallback do `CustomMating._do`)

### Contexto

Quando o primeiro erro ocorre, o código tenta um **fallback** para reconstruir a `Population` manualmente:

```python
# Extrai X manualmente de cada Individual na pop
X_list = []
for individual in pop:
    x_val = individual.X  # ou individual.get("X")
    # ...
    if x_val.ndim == 0:
        raise ValueError(f"X é escalar para individual")
```

### Por que o Erro Ocorre?

O erro `X é escalar para individual` indica que `individual.X` (ou `individual.get("X")`) está retornando um **escalar** (um único número) ao invés de um **array numpy** com shape `(n_var,)`.

**Possíveis causas**:

1. **`Individual.X` não está inicializado corretamente**:
   - Se o `Individual` foi criado de forma incorreta, o atributo `X` pode conter um escalar ao invés de um array.

2. **Problema na criação da Population**:
   - Se a `Population` foi criada usando `Population.new("X", X_array)` onde `X_array` tem shape incorreto, os `Individual` objects podem ter `X` como escalar.

3. **Problema na indexação**:
   - Se `pop[mating]` retorna algo inesperado, os `Individual` objects podem não ter o atributo `X` corretamente definido.

### Exemplo do Problema

**Esperado**:
```python
individual.X  # Shape: (100,), dtype: int64, valores: [0, 1, 2, ..., 99]
```

**O que está acontecendo**:
```python
individual.X  # Shape: (), dtype: int64, valor: 42 (escalar)
```

## Análise da Causa Raiz

### Hipótese Principal

O problema parece estar relacionado à forma como a `Population` é manipulada no `BatteryFocusedNSGA2`, especialmente durante:

1. **Inicialização Híbrida** (`_initialize_advance`):
   - A população inicial é criada manualmente com `Population.new("X", X_feasible)` e `Population.new("X", X_infeasible)`
   - Depois é fundida com `Population.merge(feasible_pop, infeasible_pop)`
   - Os `Individual` objects resultantes podem não ter o atributo `X` corretamente definido como um array numpy

2. **Avaliação Customizada**:
   - A avaliação é feita manualmente usando `problem.evaluate(X_slice, ...)` e depois atualizando `pop.set("F", ...)` e `pop.set("G", ...)`
   - Isso pode não garantir que `X` permaneça como um array numpy em cada `Individual`

3. **Manipulação de `pop` durante `_advance`**:
   - Durante `_advance`, a população pode ser modificada de formas que não preservam a estrutura correta de `X`

### Evidências

1. **O erro só ocorre após a geração 0**:
   - A geração 0 (inicialização) funciona corretamente
   - O erro ocorre na geração 1, quando o crossover é chamado pela primeira vez
   - Isso sugere que algo na manipulação da população durante `_advance` está corrompendo a estrutura de `X`

2. **O fallback também falha**:
   - Mesmo tentando extrair `X` manualmente de cada `Individual`, encontramos `X` como escalar
   - Isso indica que o problema está na estrutura dos `Individual` objects, não apenas na forma como `crossover.do()` os acessa

## Soluções Propostas

### Solução 1: Garantir que X seja sempre um array numpy durante a inicialização

Modificar `_initialize_advance` para garantir que `X` seja sempre um array numpy:

```python
# Após criar X_feasible e X_infeasible
X_feasible = np.array(X_feasible, dtype=int)
X_infeasible = np.array(X_infeasible, dtype=int)

# Garantir shape correto
assert X_feasible.ndim == 2, f"X_feasible deve ser 2D, mas tem shape {X_feasible.shape}"
assert X_infeasible.ndim == 2, f"X_infeasible deve ser 2D, mas tem shape {X_infeasible.shape}"

# Criar Population
feasible_pop = Population.new("X", X_feasible)
infeasible_pop = Population.new("X", X_infeasible)
```

### Solução 2: Validar e corrigir X antes do crossover

Adicionar validação e correção de `X` antes de chamar `crossover.do()`:

```python
def _validate_and_fix_pop_X(pop, problem):
    """Valida e corrige o atributo X de cada Individual na Population."""
    X_list = []
    for i, individual in enumerate(pop):
        x_val = individual.X
        if not isinstance(x_val, np.ndarray):
            x_val = np.array(x_val)
        if x_val.ndim == 0:
            # Se for escalar, isso é um erro grave
            raise ValueError(f"Individual {i} tem X como escalar: {x_val}")
        if x_val.ndim > 1:
            x_val = x_val.flatten()
        if x_val.shape[0] != problem.n_var:
            raise ValueError(f"Individual {i} tem X com shape {x_val.shape}, esperado ({problem.n_var},)")
        X_list.append(x_val)
    
    # Recria Population com X correto
    X_fixed = np.array(X_list)
    pop_fixed = Population.new("X", X_fixed)
    # Copia outros atributos
    if pop.has("F"):
        pop_fixed.set("F", pop.get("F"))
    if pop.has("G"):
        pop_fixed.set("G", pop.get("G"))
    if pop.has("CV"):
        pop_fixed.set("CV", pop.get("CV"))
    return pop_fixed
```

### Solução 3: Usar o Mating padrão do Pymoo

Em vez de criar um `CustomMating`, usar o `Mating` padrão do Pymoo e apenas customizar a seleção:

```python
from pymoo.core.mating import Mating

# Usar Mating padrão com seleção customizada
self.mating = Mating(
    selection=self._directed_mating,
    crossover=crossover,
    mutation=mutation
)
```

Isso garante que o Pymoo use sua lógica interna testada para construir `X` corretamente.

### Solução 4: Investigar a causa raiz na manipulação de pop

Adicionar logs detalhados para rastrear quando e como `X` se torna escalar:

```python
# Em _advance, antes de chamar mating
print(f"[DEBUG] Antes de mating - pop[0].X shape: {pop[0].X.shape}, type: {type(pop[0].X)}")
print(f"[DEBUG] Antes de mating - pop[0].X.ndim: {pop[0].X.ndim}")

# Após cada operação que modifica pop
# Verificar se X ainda é um array numpy
```

## Recomendações Imediatas

1. **Adicionar validação robusta de `X`** antes de qualquer operação de crossover
2. **Investigar a causa raiz** adicionando logs detalhados em `_advance` e `_initialize_advance`
3. **Considerar usar o Mating padrão do Pymoo** ao invés de `CustomMating`, customizando apenas a seleção
4. **Testar com uma população simples** para isolar o problema (criar uma `Population` manualmente e verificar se `crossover.do()` funciona)

## Conclusão

O problema está relacionado à forma como o atributo `X` (genótipo) é armazenado e acessado nos objetos `Individual` da `Population`. O Pymoo espera que `X` seja sempre um array numpy 1D com shape `(n_var,)`, mas em algum momento durante a execução do `BatteryFocusedNSGA2`, `X` está se tornando um escalar ou um array com shape incorreto.

A causa raiz provavelmente está na manipulação manual da população durante `_initialize_advance` e `_advance`, onde a estrutura dos `Individual` objects pode não estar sendo preservada corretamente.

A solução mais robusta seria garantir que `X` seja sempre validado e corrigido antes de qualquer operação que dependa dele (crossover, mutação, avaliação), ou usar as classes padrão do Pymoo (`Mating`) que já têm essa validação interna.
