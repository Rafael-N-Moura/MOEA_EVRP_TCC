# Análise do Problema: `algorithm.opt.get("cv").min()` Retornando Erro

## 1. O Que é `opt`?

`algorithm.opt` é um objeto `Population` do Pymoo que armazena as **soluções não-dominadas** encontradas até o momento. É atualizado a cada geração e usado para:

1. **Display/Visualização**: Mostrar estatísticas das melhores soluções encontradas
2. **Análise de Convergência**: Acompanhar a evolução do algoritmo
3. **Resultado Final**: Retornar as melhores soluções ao final da execução

### Características de `opt`:

- **Tipo**: `Population` (mesmo tipo que `self.pop`)
- **Conteúdo**: Apenas soluções **não-dominadas** e **viáveis** (se houver)
- **Atualização**: Atualizado em `_advance()` após sobrevivência
- **Acesso**: `algorithm.opt.get("F")`, `algorithm.opt.get("cv")`, etc.

## 2. Quando `super()._post_advance()` é Chamado?

O método `_post_advance()` é chamado **automaticamente pelo Pymoo** após cada geração:

```
algorithm.run()
  └─> algorithm.next()  (para cada geração)
      └─> algorithm.advance()
          └─> algorithm._advance()  (nossa implementação customizada)
              └─> algorithm._post_advance()  (chamado automaticamente)
                  └─> super()._post_advance()  (chamado por nós)
                      └─> algorithm.display()  (chamado dentro de super())
                          └─> MinimumConstraintViolation.update()
                              └─> algorithm.opt.get("cv").min()  ← ERRO AQUI
```

### Fluxo de Execução:

1. **`_advance()`**: Gera filhos, aplica sobrevivência, atualiza `opt`
2. **`_post_advance()`**: Chamado automaticamente após `_advance()`
   - **Nosso código**: Verifica se `opt` está vazio e tem `cv`
   - **`super()._post_advance()`**: Atualiza display, salva histórico, etc.
   - **Display**: Tenta acessar `opt.get("cv").min()` para mostrar estatísticas

## 3. Por Que o Erro Ainda Ocorre?

### 3.1. O Problema

Mesmo que nossos logs mostrem:
```
[POST_ADVANCE] Opt já tem 'cv' - min: 0.0, max: 0.0
[POST_ADVANCE] Chamando super()._post_advance() - Opt: 4, tem cv: True
```

O Pymoo ainda falha ao acessar `algorithm.opt.get("cv").min()`.

### 3.2. Possíveis Causas

#### Causa 1: `cv` Tem Shape Incorreto

Quando calculamos `cv`:
```python
cv_opt = np.sum(np.maximum(G_opt, 0), axis=1)
self.opt.set("cv", cv_opt)
```

Se `G_opt` tem shape `(4, 2)` (4 soluções, 2 restrições):
- `cv_opt` terá shape `(4,)` ✅ (correto)

Mas se `G_opt` tem shape `(4, 1)` ou `(4,)`:
- `np.sum(..., axis=1)` pode falhar ou retornar shape incorreto ❌

#### Causa 2: `opt` É Modificado Entre Verificação e Uso

O Pymoo pode estar modificando `opt` **dentro** de `super()._post_advance()`:

```python
# Nossa verificação
if self.opt.has("cv"):
    cv_opt = self.opt.get("cv")
    print(f"cv min: {cv_opt.min()}")  # ✅ Funciona

# Mas dentro de super()._post_advance()
super()._post_advance(**kwargs)
    # Pymoo pode estar fazendo:
    # self.opt = self.opt[alguma_filtragem]  ← Remove cv!
    # ou
    # self.opt.set("cv", novo_cv_vazio)  ← cv vazio!
```

#### Causa 3: `cv` Está Vazio Mesmo Que `opt` Não Esteja

Pode acontecer que:
- `len(self.opt) == 4` (4 soluções)
- Mas `self.opt.get("cv")` retorna array vazio `[]`

Isso pode acontecer se:
- `cv` foi calculado incorretamente
- `cv` foi removido em algum lugar
- `cv` tem shape `(0,)` em vez de `(4,)`

## 4. Análise dos Logs

Pelos logs fornecidos:
```
[UPDATE_OPT] Opt criado com 4 soluções da primeira frente viável
[INIT] Passo 6: Opt contém 4/4 soluções viáveis
[INIT] Passo 6: Opt tem 'cv' - min: 0.0, max: 0.0
[POST_ADVANCE] Opt já tem 'cv' - min: 0.0, max: 0.0
[POST_ADVANCE] Chamando super()._post_advance() - Opt: 4, tem cv: True
```

**Observações**:
1. ✅ `opt` tem 4 soluções
2. ✅ `opt` tem `cv` com valores válidos (min: 0.0, max: 0.0)
3. ✅ Nossa verificação mostra que `cv` existe e tem valores
4. ❌ Mas o Pymoo ainda falha ao acessar `cv.min()`

**Conclusão**: O problema **não** é que `opt` está vazio ou que `cv` não existe. O problema é que **algo está acontecendo dentro de `super()._post_advance()`** que modifica ou remove `cv`.

## 5. Solução

### 5.1. Verificar Shape de `cv` Antes de Usar

Adicionar verificação mais robusta:

```python
def _post_advance(self, **kwargs):
    # ... código existente ...
    
    # VERIFICAÇÃO ADICIONAL: Garante que cv tem shape correto
    if self.opt.has("cv"):
        cv_opt = self.opt.get("cv")
        # Verifica se cv não está vazio e tem shape correto
        if len(cv_opt) == 0 or cv_opt.shape[0] != len(self.opt):
            print(f"[POST_ADVANCE] AVISO: cv tem shape incorreto! Recalculando...")
            # Recalcula cv
            if self.opt.has("G"):
                G_opt = self.opt.get("G")
                cv_opt = np.sum(np.maximum(G_opt, 0), axis=1)
                self.opt.set("cv", cv_opt)
                print(f"[POST_ADVANCE] cv recalculado - shape: {cv_opt.shape}, min: {cv_opt.min()}, max: {cv_opt.max()}")
    
    # Verificação final antes de chamar super()
    if len(self.opt) == 0:
        raise RuntimeError("Opt está vazio")
    
    # Garante que cv existe e tem valores válidos
    if self.opt.has("cv"):
        cv_opt = self.opt.get("cv")
        if len(cv_opt) == 0:
            # Se cv está vazio, recria
            if self.opt.has("G"):
                G_opt = self.opt.get("G")
                cv_opt = np.sum(np.maximum(G_opt, 0), axis=1)
                self.opt.set("cv", cv_opt)
    
    super()._post_advance(**kwargs)
```

### 5.2. Interceptar Erro e Recriar `cv`

Adicionar try/except para capturar o erro e recriar `cv`:

```python
def _post_advance(self, **kwargs):
    # ... código existente ...
    
    try:
        super()._post_advance(**kwargs)
    except ValueError as e:
        if "zero-size array" in str(e) and "cv" in str(e):
            print(f"[POST_ADVANCE] ERRO: cv está vazio dentro de super()._post_advance()")
            # Recria cv
            if self.opt.has("G"):
                G_opt = self.opt.get("G")
                cv_opt = np.sum(np.maximum(G_opt, 0), axis=1)
                self.opt.set("cv", cv_opt)
                print(f"[POST_ADVANCE] cv recriado - shape: {cv_opt.shape}")
                # Tenta novamente
                super()._post_advance(**kwargs)
            else:
                raise
        else:
            raise
```

### 5.3. Solução Recomendada: Verificação Dupla

Combinar ambas as abordagens:

1. **Verificação antes de chamar `super()`**: Garante que `cv` existe e tem shape correto
2. **Try/except ao redor de `super()`**: Captura erros e recria `cv` se necessário

## 6. Por Que `cv` Fica Vazio Dentro de `super()._post_advance()`?

### 6.1. O Problema Observado

Pelos logs:
```
[POST_ADVANCE] Opt já tem 'cv' - min: 0.0, max: 0.0
[POST_ADVANCE] Chamando super()._post_advance() - Opt: 5, tem cv: True
[POST_ADVANCE] ERRO CAPTURADO: cv está vazio dentro de super()._post_advance()
```

**Conclusão**: O Pymoo está **modificando `opt` dentro de `super()._post_advance()`**, possivelmente:
1. Recriando `opt` a partir de `self.pop` (sem preservar `cv`)
2. Filtrando `opt` e removendo atributos não essenciais
3. Chamando algum método interno que reseta `opt`

### 6.2. Erro Secundário: Shape de `G_opt`

Quando tentamos recalcular `cv` no `except`, encontramos:
```
AxisError: axis 1 is out of bounds for array of dimension 1
```

**Causa**: `G_opt` pode ter shape **1D** (quando `opt` tem apenas 1 indivíduo) ou **2D** (quando tem múltiplos):
- **1D**: `G_opt.shape = (2,)` → `np.sum(..., axis=1)` falha
- **2D**: `G_opt.shape = (5, 2)` → `np.sum(..., axis=1)` funciona

## 7. Solução Implementada

### 7.1. Tratamento de Shape 1D e 2D

```python
# Lida com shape 1D ou 2D
if G_opt.ndim == 1:
    # G_opt é 1D (um único indivíduo) - cria array 1D com um valor
    cv_opt = np.array([np.sum(np.maximum(G_opt, 0))])
elif G_opt.ndim == 2:
    # G_opt é 2D (múltiplos indivíduos) - soma ao longo do axis 1
    cv_opt = np.sum(np.maximum(G_opt, 0), axis=1)
```

### 7.2. Recriação de `opt` Se Ficou Vazio

Se `opt` ficou vazio dentro de `super()._post_advance()`, recriamos a partir de `self.pop`:

```python
if len(self.opt) == 0:
    # Recria opt a partir da população
    # Filtra soluções viáveis e pega até 5
    feasible_pop = self.pop[feasible_mask]
    self.opt = feasible_pop[:min(5, len(feasible_pop))]
    # Garante que opt tem cv
    # ...
```

### 7.3. Try/Except Robusto

O `except` agora:
1. Verifica se `opt` foi modificado (tamanho mudou)
2. Recria `opt` se necessário
3. Recalcula `cv` lidando com shape 1D ou 2D
4. Tenta novamente chamar `super()._post_advance()`

## 8. Implementação Final

A solução implementada:
1. **Verifica shape de `cv` antes de chamar `super()`**
2. **Recalcula `cv` se necessário, lidando com shape 1D ou 2D**
3. **Captura erros e recria `opt` se foi modificado pelo Pymoo**
4. **Recalcula `cv` após recriar `opt`, lidando com shape 1D ou 2D**
5. **Tenta novamente chamar `super()._post_advance()`**

Isso garante que o display do Pymoo sempre tenha acesso a `cv` válido, mesmo que o Pymoo modifique `opt` internamente.

## 9. Por Que `opt` Fica Vazio Dentro de `super()._post_advance()`?

### 9.1. O Problema Observado

Pelos logs mais recentes:
```
[POST_ADVANCE] Chamando super()._post_advance() - Opt: 3, tem cv: True
[POST_ADVANCE] ERRO CAPTURADO: cv está vazio dentro de super()._post_advance()
  Opt após erro: tamanho=0, tem G=True, tem cv=True
```

**Observação crítica**: `opt` tinha 3 soluções antes de chamar `super()`, mas ficou **vazio (tamanho=0)** dentro de `super()._post_advance()`.

### 9.2. Por Que Isso Acontece?

O NSGA2 padrão do Pymoo pode estar:

1. **Limpando `opt` em certas condições**: O método `_post_advance()` padrão pode verificar se `opt` está "válido" e limpá-lo se não atender certos critérios.

2. **Recriando `opt` a partir de `self.pop`**: O NSGA2 padrão pode estar chamando `self._update_opt()` dentro de `_post_advance()`, que pode retornar uma população vazia em certas condições.

3. **Filtrando `opt` de forma agressiva**: O NSGA2 padrão pode estar filtrando `opt` para manter apenas soluções "válidas" e, em certas condições, isso resulta em uma população vazia.

### 9.3. Solução: Recriar `opt` Se Ficou Vazio

A solução implementada:

1. **Salva tamanho de `opt` antes de chamar `super()`**: Para detectar se foi modificado
2. **Captura erro e verifica se `opt` ficou vazio**: Se `opt` ficou vazio, recria a partir de `self.pop`
3. **Recria `opt` usando non-dominated sorting**: Garante que `opt` contenha soluções não-dominadas
4. **Garante que `opt` tem `G`**: `cv` será calculado automaticamente pelo Pymoo
5. **Tenta novamente chamar `super()._post_advance()`**: Após recriar `opt`

### 9.4. Importante: `cv` É Read-Only

**CRÍTICO**: `cv` é uma **propriedade read-only** no Pymoo. Não podemos usar `opt.set("cv", ...)`. O Pymoo calcula `cv` automaticamente a partir de `G` quando necessário.

**Solução**: Garantir que `opt` tenha `G` correto e deixar o Pymoo calcular `cv` automaticamente.

### 9.5. Implementação Final

A solução final:
1. **Remove todas as tentativas de definir `cv` diretamente**
2. **Garante que `opt` tenha `G` correto**
3. **Recria `opt` se ficou vazio dentro de `super()._post_advance()`**
4. **Usa non-dominated sorting para recriar `opt` corretamente**
5. **Tenta novamente chamar `super()._post_advance()` após recriar `opt`**

Isso garante que o display do Pymoo sempre tenha acesso a `opt` não-vazio com `G` correto, permitindo que o Pymoo calcule `cv` automaticamente.
