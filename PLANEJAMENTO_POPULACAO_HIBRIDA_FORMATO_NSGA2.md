# Planejamento: Garantir Formato Correto da População Híbrida para NSGA-II

## Objetivo

Este documento descreve um planejamento detalhado para garantir que a população com inicialização híbrida (`BatteryFocusedNSGA2`) mantenha o formato correto de `X` (genótipos) em todos os estágios do algoritmo, permitindo que operações do Pymoo (crossover, mutação, avaliação) funcionem corretamente.

## Problema Identificado

Com base na análise em `ANALISE_ERROS_CROSSOVER_X_SHAPE.md`, identificamos que:

1. **Durante a inicialização híbrida**: O atributo `X` dos `Individual` objects pode não estar sendo preservado corretamente como um array numpy 1D com shape `(n_var,)`.

2. **Durante a avaliação**: A atualização de `F` e `G` via `pop.set("F", ...)` e `pop.set("G", ...)` pode não garantir que `X` permaneça no formato correto.

3. **Durante operações de crossover**: O Pymoo espera que `parent.get("X")` retorne um array numpy 1D, mas em alguns casos está retornando escalares ou arrays com shape incorreto.

## Requisitos do Formato X para NSGA-II

### Formato Esperado pelo Pymoo

Para cada `Individual` na `Population`:
- **`individual.X`** deve ser um **array numpy 1D** com shape `(n_var,)`
- **Tipo**: `numpy.ndarray`
- **Dtype**: `int` (para permutações) ou `float` (para variáveis contínuas)
- **Valores**: Genótipo completo do indivíduo (permutação de clientes no nosso caso)

### Exemplo Correto

```python
individual.X  # Shape: (100,), dtype: int64
# Valores: [0, 1, 2, 3, ..., 99] (permutação)
```

### Formato Incorreto (Problemas Identificados)

```python
# PROBLEMA 1: Escalar
individual.X  # Shape: (), dtype: int64, valor: 42

# PROBLEMA 2: Shape incorreto
individual.X  # Shape: (1, 100) ou (100, 1) ao invés de (100,)

# PROBLEMA 3: Não é numpy array
individual.X  # Tipo: list ou tuple
```

## Estratégia de Implementação

### Fase 1: Validação e Correção de X

Criar uma função utilitária que valida e corrige o formato de `X` em uma `Population`:

```python
def _validate_and_fix_pop_X(pop, problem):
    """
    Valida e corrige o atributo X de cada Individual na Population.
    
    Garante que:
    - X é um numpy.ndarray
    - X tem shape (n_var,)
    - X tem dtype apropriado (int para permutações)
    
    Args:
        pop: Population object
        problem: Problem object (para obter n_var)
    
    Returns:
        Population: Nova Population com X corrigido (ou pop original se já estava correto)
    """
    X_list = []
    needs_fix = False
    
    for i, individual in enumerate(pop):
        x_val = individual.X
        
        # Verifica se precisa corrigir
        if not isinstance(x_val, np.ndarray):
            needs_fix = True
            x_val = np.array(x_val)
        
        if x_val.ndim == 0:
            # ERRO CRÍTICO: X é escalar
            raise ValueError(
                f"Individual {i} tem X como escalar: {x_val}. "
                f"Isso indica corrupção grave da estrutura da Population."
            )
        
        if x_val.ndim > 1:
            needs_fix = True
            x_val = x_val.flatten()
        
        if x_val.shape[0] != problem.n_var:
            raise ValueError(
                f"Individual {i} tem X com shape {x_val.shape}, "
                f"esperado ({problem.n_var},). "
                f"Isso indica incompatibilidade entre genótipo e problema."
            )
        
        # Garante dtype int para permutações
        if x_val.dtype != int:
            needs_fix = True
            x_val = x_val.astype(int)
        
        X_list.append(x_val)
    
    # Se não precisa corrigir, retorna pop original
    if not needs_fix:
        return pop
    
    # Recria Population com X corrigido
    X_fixed = np.array(X_list)  # Shape: (len(pop), n_var)
    pop_fixed = Population.new("X", X_fixed)
    
    # Copia todos os outros atributos (F, G, CV, etc.)
    for key in pop.keys():
        if key != "X":  # X já foi corrigido
            if pop.has(key):
                pop_fixed.set(key, pop.get(key))
    
    return pop_fixed
```

### Fase 2: Modificação de `_initialize_advance`

Modificar `_initialize_advance` para garantir que `X` seja sempre um array numpy 2D correto antes de criar as `Population` objects:

```python
def _initialize_advance(self, infills=None, **kwargs):
    """
    Inicializa população com sampling híbrido seguindo estratégia de fusão.
    
    MODIFICAÇÕES:
    - Valida e corrige X antes de criar Population objects
    - Valida X após cada etapa de avaliação
    - Valida X após merge das populações
    """
    # ... código existente até PASSO 1 ...
    
    # ===== PASSO 1: Amostragem Pura =====
    X = self.sampling.do(problem, self.pop_size, **kwargs)
    
    # VALIDAÇÃO 1: Garante que X retornado pelo sampling está correto
    X = np.array(X, dtype=int)  # Garante numpy array e dtype int
    assert X.ndim == 2, f"X do sampling deve ser 2D, mas tem shape {X.shape}"
    assert X.shape == (self.pop_size, problem.n_var), \
        f"X deve ter shape ({self.pop_size}, {problem.n_var}), mas tem {X.shape}"
    
    # ===== PASSO 2: Fissionamento =====
    n_feasible = self.pop_size // 2
    X_feasible = X[:n_feasible].copy()  # .copy() para evitar views
    X_infeasible = X[n_feasible:].copy()
    
    # VALIDAÇÃO 2: Garante que slices estão corretos
    assert X_feasible.ndim == 2, f"X_feasible deve ser 2D, mas tem shape {X_feasible.shape}"
    assert X_infeasible.ndim == 2, f"X_infeasible deve ser 2D, mas tem shape {X_infeasible.shape}"
    assert X_feasible.shape[0] == n_feasible, \
        f"X_feasible deve ter {n_feasible} linhas, mas tem {X_feasible.shape[0]}"
    assert X_infeasible.shape[0] == (self.pop_size - n_feasible), \
        f"X_infeasible deve ter {self.pop_size - n_feasible} linhas, mas tem {X_infeasible.shape[0]}"
    
    # ===== PASSO 3: Encapsulamento Temporário =====
    pop_feasible = Population.new("X", X_feasible)
    pop_infeasible = Population.new("X", X_infeasible)
    
    # VALIDAÇÃO 3: Verifica que Population objects foram criadas corretamente
    for i, individual in enumerate(pop_feasible):
        assert isinstance(individual.X, np.ndarray), \
            f"pop_feasible[{i}].X não é numpy array: {type(individual.X)}"
        assert individual.X.ndim == 1, \
            f"pop_feasible[{i}].X deve ser 1D, mas tem shape {individual.X.shape}"
        assert individual.X.shape[0] == problem.n_var, \
            f"pop_feasible[{i}].X deve ter shape ({problem.n_var},), mas tem {individual.X.shape}"
    
    for i, individual in enumerate(pop_infeasible):
        assert isinstance(individual.X, np.ndarray), \
            f"pop_infeasible[{i}].X não é numpy array: {type(individual.X)}"
        assert individual.X.ndim == 1, \
            f"pop_infeasible[{i}].X deve ser 1D, mas tem shape {individual.X.shape}"
        assert individual.X.shape[0] == problem.n_var, \
            f"pop_infeasible[{i}].X deve ter shape ({problem.n_var},), mas tem {individual.X.shape}"
    
    # ===== PASSO 4: Avaliação Condicionada =====
    # ... código de avaliação existente ...
    
    # VALIDAÇÃO 4: Após avaliação, verifica que X ainda está correto
    pop_feasible = self._validate_and_fix_pop_X(pop_feasible, problem)
    pop_infeasible = self._validate_and_fix_pop_X(pop_infeasible, problem)
    
    # ===== PASSO 5: Fusão na População Principal =====
    self.pop = Population.merge(pop_feasible, pop_infeasible)
    
    # VALIDAÇÃO 5: Após merge, verifica que X ainda está correto
    self.pop = self._validate_and_fix_pop_X(self.pop, problem)
    
    # ... resto do código ...
```

### Fase 3: Modificação de `_advance`

Modificar `_advance` para validar `X` antes e depois de operações críticas:

```python
def _advance(self, infills=None, **kwargs):
    """
    Avança uma geração do algoritmo.
    
    MODIFICAÇÕES:
    - Valida X antes de chamar mating (crossover)
    - Valida X após criar offspring
    - Valida X após merge de pais e filhos
    - Valida X após survival selection
    """
    # VALIDAÇÃO 1: Antes de qualquer operação, valida pop atual
    self.pop = self._validate_and_fix_pop_X(self.pop, self.problem)
    
    # ... código existente de seleção de pais ...
    
    # VALIDAÇÃO 2: Antes de chamar mating, valida pop novamente
    # (pode ter sido modificada por operações anteriores)
    self.pop = self._validate_and_fix_pop_X(self.pop, self.problem)
    
    # Cria offspring via mating
    off = self.mating.do(self.problem, self.pop, self.n_offsprings, 
                         algorithm=self, random_state=self.random_state, **kwargs)
    
    # VALIDAÇÃO 3: Após criar offspring, valida X dos filhos
    off = self._validate_and_fix_pop_X(off, self.problem)
    
    # Avalia offspring
    off = self.evaluator.eval(self.problem, off, **kwargs)
    
    # VALIDAÇÃO 4: Após avaliação, valida X novamente
    # (avaliação não deve modificar X, mas vamos garantir)
    off = self._validate_and_fix_pop_X(off, self.problem)
    
    # Merge de pais e filhos
    pop = Population.merge(self.pop, off)
    
    # VALIDAÇÃO 5: Após merge, valida X
    pop = self._validate_and_fix_pop_X(pop, self.problem)
    
    # Survival selection
    self.pop = self._infeasible_survival.do(pop, self.pop_size, **kwargs)
    
    # VALIDAÇÃO 6: Após survival, valida X final
    self.pop = self._validate_and_fix_pop_X(self.pop, self.problem)
    
    # ... resto do código ...
```

### Fase 4: Modificação da Avaliação

Criar um wrapper para `problem.evaluate()` que garante que `X` não seja modificado:

```python
def _evaluate_with_X_preservation(self, X, **kwargs):
    """
    Avalia indivíduos garantindo que X não seja modificado.
    
    Args:
        X: Array numpy 2D com shape (n_individuals, n_var) ou Population
    
    Returns:
        dict: Dicionário com 'F' e 'G' (se houver restrições)
    """
    # Se X é Population, extrai array numpy
    if isinstance(X, Population):
        X_array = X.get("X", to_numpy=True)
        # VALIDAÇÃO: Garante que X_array está correto
        X_array = np.array(X_array, dtype=int)
        assert X_array.ndim == 2, f"X_array deve ser 2D, mas tem shape {X_array.shape}"
    else:
        X_array = np.array(X, dtype=int)
        assert X_array.ndim == 2, f"X_array deve ser 2D, mas tem shape {X_array.shape}"
    
    # Avalia usando problem.evaluate()
    out = self.problem.evaluate(X_array, return_as_dictionary=True, **kwargs)
    
    # VALIDAÇÃO: Verifica que X não foi modificado
    # (problem.evaluate() não deve modificar X, mas vamos garantir)
    if isinstance(X, Population):
        X_after = X.get("X", to_numpy=True)
        if not np.array_equal(X_array, X_after):
            print(f"AVISO: X foi modificado durante avaliação! Corrigindo...")
            X.set("X", X_array)
    
    return out
```

### Fase 5: Modificação de `CustomMating._do`

Modificar `CustomMating._do` para validar `X` antes de chamar crossover:

```python
class CustomMating(Mating):
    def _do(self, problem, pop, n_offsprings, **kwargs):
        # VALIDAÇÃO: Antes de qualquer operação, valida pop
        pop = self._validate_and_fix_pop_X(pop, problem)
        
        # ... código de seleção de pais ...
        
        try:
            _off = self.crossover.do(problem, pop, parents, **kwargs)
        except (ValueError, AttributeError, TypeError) as e:
            # Se falhar, tenta corrigir pop e tentar novamente
            print(f"[CUSTOM_MATING] Crossover falhou: {e}. Tentando corrigir Population...")
            pop = self._validate_and_fix_pop_X(pop, problem)
            _off = self.crossover.do(problem, pop, parents, **kwargs)
        
        # VALIDAÇÃO: Após crossover, valida offspring
        _off = self._validate_and_fix_pop_X(_off, problem)
        
        # Aplica mutation
        off = self.mutation.do(problem, _off, **kwargs)
        
        # VALIDAÇÃO: Após mutation, valida offspring
        off = self._validate_and_fix_pop_X(off, problem)
        
        return off
    
    def _validate_and_fix_pop_X(self, pop, problem):
        """Wrapper para função de validação (mesma implementação da Fase 1)"""
        return _validate_and_fix_pop_X(pop, problem)
```

## Plano de Implementação Detalhado

### Etapa 1: Criar Função de Validação (Prioridade: ALTA)

**Arquivo**: `src/battery_focused_nsga2.py`

**Ação**:
1. Implementar função `_validate_and_fix_pop_X(pop, problem)` como método estático ou função utilitária
2. Adicionar logs detalhados quando correções são necessárias
3. Adicionar assertions para detectar problemas cedo

**Teste**:
- Criar teste unitário que verifica correção de `X` escalar
- Criar teste unitário que verifica correção de `X` com shape incorreto
- Criar teste unitário que verifica preservação de `X` quando já está correto

### Etapa 2: Modificar `_initialize_advance` (Prioridade: ALTA)

**Arquivo**: `src/battery_focused_nsga2.py`

**Ação**:
1. Adicionar validações após cada passo crítico (PASSO 1, 2, 3, 4, 5)
2. Chamar `_validate_and_fix_pop_X()` após criar `pop_feasible` e `pop_infeasible`
3. Chamar `_validate_and_fix_pop_X()` após avaliação de cada lote
4. Chamar `_validate_and_fix_pop_X()` após merge das populações

**Teste**:
- Executar inicialização e verificar logs de validação
- Verificar que não há erros de `X` escalar ou shape incorreto
- Verificar que população inicial tem formato correto

### Etapa 3: Modificar `_advance` (Prioridade: ALTA)

**Arquivo**: `src/battery_focused_nsga2.py`

**Ação**:
1. Adicionar validação no início de `_advance`
2. Adicionar validação antes de chamar `mating.do()`
3. Adicionar validação após criar `off`
4. Adicionar validação após avaliar `off`
5. Adicionar validação após merge de `pop` e `off`
6. Adicionar validação após survival selection

**Teste**:
- Executar algumas gerações e verificar logs
- Verificar que não há erros de `X` escalar ou shape incorreto
- Verificar que crossover funciona corretamente

### Etapa 4: Modificar `CustomMating._do` (Prioridade: MÉDIA)

**Arquivo**: `src/battery_focused_nsga2.py`

**Ação**:
1. Adicionar validação no início de `_do`
2. Adicionar validação antes de chamar `crossover.do()`
3. Adicionar validação após criar `_off`
4. Adicionar validação após aplicar mutation
5. Melhorar tratamento de exceções com validação antes de retry

**Teste**:
- Executar crossover e verificar que não há erros de shape
- Verificar que fallback funciona corretamente quando necessário

### Etapa 5: Criar Wrapper de Avaliação (Prioridade: BAIXA)

**Arquivo**: `src/battery_focused_nsga2.py`

**Ação**:
1. Implementar `_evaluate_with_X_preservation()` se necessário
2. Usar em `_initialize_advance` e `_advance` se `problem.evaluate()` estiver modificando `X`

**Teste**:
- Verificar que `X` não é modificado durante avaliação
- Se `X` for modificado, verificar que wrapper corrige automaticamente

## Estratégia de Logging

Adicionar logs detalhados para rastrear quando e por que `X` precisa ser corrigido:

```python
def _validate_and_fix_pop_X(pop, problem, log_prefix=""):
    """
    Valida e corrige X com logging detalhado.
    """
    X_list = []
    needs_fix = False
    fix_reasons = []
    
    for i, individual in enumerate(pop):
        x_val = individual.X
        original_type = type(x_val)
        original_shape = x_val.shape if hasattr(x_val, 'shape') else 'N/A'
        
        # ... validações ...
        
        if needs_fix:
            fix_reasons.append(
                f"Individual {i}: {original_type} {original_shape} -> "
                f"numpy.ndarray ({x_val.shape})"
            )
    
    if needs_fix:
        print(f"{log_prefix}[FIX_X] Corrigidos {len(fix_reasons)} indivíduos:")
        for reason in fix_reasons[:5]:  # Mostra apenas os 5 primeiros
            print(f"{log_prefix}  - {reason}")
        if len(fix_reasons) > 5:
            print(f"{log_prefix}  ... e mais {len(fix_reasons) - 5} indivíduos")
    
    # ... resto da função ...
```

## Estratégia de Testes

### Teste 1: Validação de X após Inicialização

```python
def test_initialize_advance_X_format():
    """Testa que X está no formato correto após _initialize_advance"""
    algorithm = BatteryFocusedNSGA2(pop_size=100)
    problem = EVRPTWProblem(...)
    algorithm.setup(problem, verbose=False)
    algorithm._initialize_advance()
    
    # Verifica que todos os X estão corretos
    for i, individual in enumerate(algorithm.pop):
        assert isinstance(individual.X, np.ndarray), f"Individual {i} X não é numpy array"
        assert individual.X.ndim == 1, f"Individual {i} X não é 1D"
        assert individual.X.shape[0] == problem.n_var, f"Individual {i} X shape incorreto"
```

### Teste 2: Validação de X após Crossover

```python
def test_crossover_X_format():
    """Testa que X está no formato correto após crossover"""
    algorithm = BatteryFocusedNSGA2(pop_size=100)
    problem = EVRPTWProblem(...)
    algorithm.setup(problem, verbose=False)
    algorithm._initialize_advance()
    
    # Avança uma geração
    algorithm._advance()
    
    # Verifica que todos os X estão corretos
    for i, individual in enumerate(algorithm.pop):
        assert isinstance(individual.X, np.ndarray), f"Individual {i} X não é numpy array"
        assert individual.X.ndim == 1, f"Individual {i} X não é 1D"
        assert individual.X.shape[0] == problem.n_var, f"Individual {i} X shape incorreto"
```

### Teste 3: Validação de X após Múltiplas Gerações

```python
def test_multiple_generations_X_format():
    """Testa que X permanece correto após múltiplas gerações"""
    algorithm = BatteryFocusedNSGA2(pop_size=100)
    problem = EVRPTWProblem(...)
    algorithm.setup(problem, verbose=False)
    algorithm._initialize_advance()
    
    # Avança 10 gerações
    for gen in range(10):
        algorithm._advance()
        
        # Verifica que todos os X estão corretos
        for i, individual in enumerate(algorithm.pop):
            assert isinstance(individual.X, np.ndarray), \
                f"Gen {gen}, Individual {i} X não é numpy array"
            assert individual.X.ndim == 1, \
                f"Gen {gen}, Individual {i} X não é 1D"
            assert individual.X.shape[0] == problem.n_var, \
                f"Gen {gen}, Individual {i} X shape incorreto"
```

## Cronograma de Implementação

1. **Semana 1**: Etapas 1 e 2 (Função de validação + `_initialize_advance`)
2. **Semana 2**: Etapas 3 e 4 (`_advance` + `CustomMating._do`)
3. **Semana 3**: Etapa 5 (Wrapper de avaliação, se necessário) + Testes
4. **Semana 4**: Refinamento, otimização e documentação

## Métricas de Sucesso

1. **Zero erros de `X` escalar**: Não deve haver nenhum `ValueError: X é escalar para individual`
2. **Zero erros de shape incorreto**: Não deve haver nenhum `ValueError: not enough values to unpack (expected 3, got 2)`
3. **Crossover funciona**: `OrderCrossover` deve funcionar sem erros em todas as gerações
4. **Performance aceitável**: Validações não devem adicionar mais de 5% de overhead

## Conclusão

Este planejamento fornece uma estratégia abrangente para garantir que a população híbrida mantenha o formato correto de `X` em todos os estágios do algoritmo. A implementação deve ser feita de forma incremental, com testes após cada etapa, para garantir que os problemas sejam resolvidos sem introduzir novos bugs.

A chave é **validar e corrigir proativamente** em vez de apenas tratar erros quando ocorrem. Isso garante que a estrutura da `Population` esteja sempre no formato esperado pelo Pymoo, permitindo que todas as operações (crossover, mutação, avaliação) funcionem corretamente.
