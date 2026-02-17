# Análise Detalhada: Erro "zero-size array to reduction operation minimum"

## 1. O Erro

```
ValueError: zero-size array to reduction operation minimum which has no identity
```

**Localização**: `pymoo/util/display/single.py`, linha 11
```python
self.value = algorithm.opt.get("cv").min()
```

**Quando ocorre**: Durante a geração 12, quando o display do pymoo tenta atualizar a coluna `cv_min`.

## 2. Causa Raiz

O erro ocorre porque `algorithm.opt.get("cv")` está retornando um **array vazio** (tamanho 0), e o método `.min()` do numpy não consegue calcular o mínimo de um array vazio sem uma identidade especificada.

### Por que `opt` está vazio?

O problema está na forma como estamos atualizando `opt` (soluções não-dominadas) no método `_advance()`. Quando sobrescrevemos `_advance()`, precisamos garantir que `opt` seja atualizado corretamente, mas há um problema sutil:

1. **Filtragem de soluções viáveis**: Quando filtramos apenas soluções viáveis (`cv == 0`), pode acontecer que:
   - Não haja soluções viáveis na população (`feasible_mask` é todo `False`)
   - `feasible_pop` fica vazio
   - `fronts[0]` pode estar vazio mesmo que `fronts` não esteja

2. **Non-dominated sorting pode retornar frentes vazias**: O método `nds.do()` pode retornar uma lista de frentes onde a primeira frente está vazia, especialmente quando:
   - Há poucas soluções viáveis
   - Todas as soluções são dominadas por outras

3. **Indexação de arrays vazios**: Quando fazemos `feasible_pop[fronts[0]]` e `fronts[0]` está vazio, o resultado é uma população vazia.

## 3. Fluxo do Problema

### Sequência de Eventos (Geração 12):

1. **`_advance()` é chamado**:
   - Gera filhos
   - Combina população (pais + filhos)
   - Aplica sobrevivência customizada
   - Tenta atualizar `opt`

2. **Atualização de `opt`**:
   ```python
   # Filtra soluções viáveis
   feasible_mask = cv == 0
   if np.any(feasible_mask):
       feasible_pop = self.pop[feasible_mask]
       fronts = nds.do(F_feasible)
       if len(fronts) > 0 and len(fronts[0]) > 0:
           self.opt = feasible_pop[fronts[0]]  # ← Pode estar vazio aqui!
   ```

3. **Problema**: Mesmo que `len(fronts) > 0` e `len(fronts[0]) > 0`, pode acontecer que:
   - `fronts[0]` contenha índices que não correspondem a nenhum indivíduo válido
   - `feasible_pop[fronts[0]]` resulte em uma população vazia

4. **`_post_advance()` é chamado**:
   - Chama `super()._post_advance()` que tenta atualizar o display
   - O display tenta acessar `algorithm.opt.get("cv").min()`
   - `opt.get("cv")` retorna array vazio
   - `.min()` falha com `ValueError`

## 4. Por Que Nossas Verificações Não Funcionaram

### Tentativa 1: Verificação após atribuição
```python
if len(self.opt) == 0:
    self.opt = Population.create(self.pop[0])
```
**Problema**: A verificação pode não estar capturando todos os casos onde `opt` fica vazio.

### Tentativa 2: Verificação em `_post_advance()`
```python
def _post_advance(self, **kwargs):
    super()._post_advance(**kwargs)  # ← Display é chamado AQUI
    if len(self.opt) == 0:
        # Muito tarde! Display já tentou acessar opt
```
**Problema**: O display é chamado **dentro** de `super()._post_advance()`, então nossa verificação acontece **depois** do erro.

### Tentativa 3: Múltiplas verificações
**Problema**: Mesmo com múltiplas verificações, `opt` ainda pode ficar vazio se:
- A lógica de atualização tem um bug sutil
- O NSGA2 padrão está resetando `opt` em algum lugar
- Há uma condição de corrida

## 5. Análise do Código Atual

### Código Problemático (linhas 434-443):

```python
if np.any(feasible_mask):
    feasible_pop = self.pop[feasible_mask]
    F_feasible = feasible_pop.get("F")
    fronts = nds.do(F_feasible)
    if len(fronts) > 0 and len(fronts[0]) > 0:
        # Primeira frente = soluções não-dominadas
        self.opt = feasible_pop[fronts[0]]  # ← PROBLEMA AQUI
    else:
        self.opt = feasible_pop  # ← Ou aqui
```

**Problemas identificados**:

1. **`fronts[0]` pode conter índices inválidos**: Se `feasible_pop` tem 3 indivíduos, mas `fronts[0]` contém `[0, 1, 2, 3]`, o índice `3` é inválido.

2. **`feasible_pop` pode estar vazio**: Mesmo que `np.any(feasible_mask)` seja `True`, `feasible_pop` pode estar vazio se todos os indivíduos viáveis foram removidos por algum motivo.

3. **Indexação pode falhar silenciosamente**: Se `fronts[0]` contém índices que não correspondem a `feasible_pop`, a indexação pode retornar uma população vazia sem gerar erro.

## 6. Solução Proposta

### Solução 1: Verificação ANTES de `super()._post_advance()`

```python
def _post_advance(self, **kwargs):
    # GARANTE que opt não está vazio ANTES de chamar super()
    if not hasattr(self, 'opt') or len(self.opt) == 0:
        from pymoo.core.population import Population
        if len(self.pop) > 0:
            self.opt = Population.create(self.pop[0])
        else:
            self.opt = Population()
    
    # Agora chama super() - display vai funcionar
    super()._post_advance(**kwargs)
```

### Solução 2: Corrigir lógica de atualização de `opt`

```python
# Garantir que fronts[0] não está vazio E que os índices são válidos
if len(fronts) > 0 and len(fronts[0]) > 0:
    # Verificar se os índices são válidos
    valid_indices = [idx for idx in fronts[0] if 0 <= idx < len(feasible_pop)]
    if len(valid_indices) > 0:
        self.opt = feasible_pop[valid_indices]
    else:
        # Fallback: usa toda feasible_pop
        self.opt = feasible_pop if len(feasible_pop) > 0 else self.pop[:1]
```

### Solução 3: Usar método padrão do NSGA2 para atualizar `opt`

Em vez de atualizar `opt` manualmente, podemos chamar o método padrão do NSGA2 que já faz isso corretamente:

```python
def _advance(self, infills=None, **kwargs):
    # ... nossa lógica customizada ...
    
    # Atualiza opt usando método padrão do NSGA2
    # Isso garante compatibilidade com o display
    try:
        # Chama método padrão para atualizar opt
        super()._advance(infills=infills, **kwargs)
        # Mas isso vai sobrescrever nossa sobrevivência customizada!
    except:
        # Fallback: atualização manual
        pass
```

**Problema**: Isso sobrescreveria nossa sobrevivência customizada.

## 7. Solução Recomendada

A melhor solução é **combinar** as soluções 1 e 2:

1. **Corrigir a lógica de atualização de `opt`** para garantir que nunca fique vazio
2. **Adicionar verificação em `_post_advance()` ANTES de chamar `super()`**

### Implementação:

```python
def _advance(self, infills=None, **kwargs):
    # ... código existente ...
    
    # Atualização de opt com verificações robustas
    if len(self.pop) > 0:
        F = self.pop.get("F")
        if self.pop.has("G"):
            G = self.pop.get("G")
            cv = np.sum(np.maximum(G, 0), axis=1)
            feasible_mask = cv == 0
            
            if np.any(feasible_mask):
                feasible_pop = self.pop[feasible_mask]
                # GARANTE que feasible_pop não está vazio
                if len(feasible_pop) > 0:
                    F_feasible = feasible_pop.get("F")
                    fronts = nds.do(F_feasible)
                    
                    if len(fronts) > 0 and len(fronts[0]) > 0:
                        # Verifica se índices são válidos
                        valid_indices = [idx for idx in fronts[0] if 0 <= idx < len(feasible_pop)]
                        if len(valid_indices) > 0:
                            self.opt = feasible_pop[valid_indices]
                        else:
                            self.opt = feasible_pop
                    else:
                        self.opt = feasible_pop
                else:
                    # Se feasible_pop está vazio, usa toda população
                    fronts = nds.do(F)
                    if len(fronts) > 0 and len(fronts[0]) > 0:
                        self.opt = self.pop[fronts[0]]
                    else:
                        self.opt = self.pop
            else:
                # Sem soluções viáveis, usa toda população
                fronts = nds.do(F)
                if len(fronts) > 0 and len(fronts[0]) > 0:
                    self.opt = self.pop[fronts[0]]
                else:
                    self.opt = self.pop
    
    # VERIFICAÇÃO FINAL: Garante que opt nunca fique vazio
    if not hasattr(self, 'opt') or len(self.opt) == 0:
        from pymoo.core.population import Population
        if len(self.pop) > 0:
            self.opt = Population.create(self.pop[0])
        else:
            self.opt = Population()

def _post_advance(self, **kwargs):
    # GARANTE que opt não está vazio ANTES de chamar super()
    if not hasattr(self, 'opt') or len(self.opt) == 0:
        from pymoo.core.population import Population
        if len(self.pop) > 0:
            self.opt = Population.create(self.pop[0])
        else:
            self.opt = Population()
    
    # Agora chama super() - display vai funcionar
    super()._post_advance(**kwargs)
```

## 8. Por Que Isso Deve Funcionar

1. **Verificação de índices válidos**: Garante que `fronts[0]` contém apenas índices válidos
2. **Verificação de `feasible_pop`**: Garante que não tentamos indexar uma população vazia
3. **Verificação final em `_advance()`**: Garante que `opt` nunca fique vazio após atualização
4. **Verificação em `_post_advance()` ANTES de `super()`**: Garante que `opt` não está vazio quando o display tenta acessá-lo

## 9. Alternativa: Desabilitar Display Temporariamente

Se a solução acima ainda não funcionar, podemos desabilitar o display temporariamente para testar se o algoritmo funciona:

```python
res = minimize(
    problem,
    algorithm,
    ('n_gen', n_gen),
    verbose=False,  # Desabilita display
    seed=1
)
```

Isso permitiria testar se o algoritmo funciona corretamente, mesmo que o display tenha problemas.

## 10. Conclusão

O erro ocorre porque `opt` está ficando vazio em algum momento, e o display do pymoo tenta acessar `opt.get("cv").min()` sem verificar se `opt` está vazio. A solução é garantir que `opt` **sempre** tenha pelo menos um indivíduo, com verificações robustas em múltiplos pontos do código.
