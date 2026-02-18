# Análise: Comparação de Condições de Execução - NSGA2 vs BatteryFocusedNSGA2

## Objetivo

Verificar se `NSGA2` e `BatteryFocusedNSGA2` estão sendo executados nas mesmas condições, especialmente se estão usando o mesmo decoder e os mesmos parâmetros de avaliação.

## Análise do Código

### 1. Criação do Problema

#### NSGA2 (linha 361 de `main.py`) - CORRIGIDO
```python
problem_nsga2 = EVRPTWProblem(context, use_constraints=False, force_battery_feasible=True)
```

**Sempre**:
- `use_constraints = False`
- `force_battery_feasible = True` ✅ **CORRIGIDO**: Agora usa `True` (comportamento conservador)

**Resultado**: Problema criado **SEM restrições** (n_constr=0), usando **penalização** no F, e **sempre viável** (decoder força retorno ao depósito quando bateria baixa).

#### BatteryFocusedNSGA2 (linha 376 de `main.py`)
```python
problem_battery = EVRPTWProblem(context, use_constraints=True, force_battery_feasible=False)
```

**Sempre**:
- `use_constraints = True`
- `force_battery_feasible = False`

**Resultado**: Problema criado **COM restrições** (n_constr=2), **sem penalização** no F.

### 2. Diferenças Críticas Identificadas

#### ❌ DIFERENÇA 1: Modo de Tratamento de Violações

**NSGA2** (`use_constraints=False`, `force_battery_feasible=True`):
- **Não calcula G** (restrições)
- **Aplica penalização** no F quando `solution.is_feasible == False`:
  ```python
  if not solution.is_feasible:
      f1 = f1 + PENALTY_COST  # +100000
      f2 = min(1.0, f2 + PENALTY_DISSATISFACTION)  # +1.0
  ```
- Soluções inviáveis têm F muito alto (dominadas por qualquer solução viável)
- **Decoder**: Sempre usa `force_battery_feasible=True` ✅ **CORRIGIDO**: Agora força viabilidade
- **Resultado**: Decoder sempre retorna ao depósito quando bateria baixa, gerando soluções sempre viáveis (mas com custo potencialmente maior)

**BatteryFocusedNSGA2** (`use_constraints=True`):
- **Calcula G** (restrições): `G = [g1, g2]` onde `g2 = solution.battery_violation`
- **Não aplica penalização** no F
- Soluções inviáveis têm `G2 > 0`, mas F pode ser baixo
- **Decoder**: Usa `force_battery_feasible=self.force_battery_feasible` (linha 88 de `problem.py`)
  - Durante evolução: `force_battery_feasible=False` (linha 874 de `battery_focused_nsga2.py`)
  - Durante inicialização: `force_battery_feasible=True` para metade da população (linha 662)

#### ❌ DIFERENÇA 2: Comportamento do Decoder Durante Evolução

**NSGA2**:
- Sempre usa `force_battery_feasible=False` (não muda durante execução)
- Decoder não força retorno ao depósito por bateria baixa
- Todas as soluções podem ter violações de bateria

**BatteryFocusedNSGA2**:
- Durante evolução: `force_battery_feasible=False` (igual ao NSGA2)
- Durante inicialização: `force_battery_feasible=True` para 50% da população
- **Diferença**: População inicial tem 50% de soluções viáveis (G2=0)

#### ✅ SEMELHANÇA: Decoder Durante Evolução

Ambos usam `force_battery_feasible=False` durante a evolução, então o **decoder funciona igual** durante as gerações.

### 3. Impacto nas Comparações

#### Problema 1: Tratamento Diferente de Violações

**NSGA2**:
- Soluções inviáveis têm F penalizado (f1 + 100000, f2 + 1.0)
- NSGA-II trata todas como minimização de F
- Soluções inviáveis são sempre dominadas por soluções viáveis

**BatteryFocusedNSGA2**:
- Soluções inviáveis têm G2 > 0, mas F não é penalizado
- NSGA-II trata como problema com restrições
- Soluções inviáveis podem ter F baixo e ainda serem selecionadas (se tiverem menor G2)

**Consequência**: As comparações não são justas porque:
- NSGA2 força que soluções inviáveis sejam sempre piores (via penalização)
- BatteryFocusedNSGA2 permite que soluções inviáveis com F baixo sejam mantidas

#### Problema 2: População Inicial Diferente

**NSGA2**:
- População inicial: 100% gerada com `force_battery_feasible=False`
- Todas as soluções podem ser inviáveis desde o início

**BatteryFocusedNSGA2**:
- População inicial: 50% com `force_battery_feasible=True`, 50% com `force_battery_feasible=False`
- 50% das soluções são viáveis (G2=0) desde o início

**Consequência**: BatteryFocusedNSGA2 começa com vantagem (tem soluções viáveis desde o início).

### 4. Verificação do Decoder

#### Uso do Decoder em `problem.py` (linha 88)

```python
solution = decode(individual, self.context, force_battery_feasible=self.force_battery_feasible)
```

**Ambos usam o mesmo decoder**, mas com valores diferentes de `force_battery_feasible`:
- **NSGA2**: Sempre `False` (não muda)
- **BatteryFocusedNSGA2**: `True` na inicialização (50% da população), `False` durante evolução

### 5. Recomendações para Comparação Justa

#### Opção 1: NSGA2 também com Restrições

Modificar `main.py` para que NSGA2 também use `use_constraints=True`:

```python
# Cria problema COM restrições para ambos
problem = EVRPTWProblem(context, use_constraints=True, force_battery_feasible=False)

if args.algorithm in ['nsga2', 'both']:
    results['nsga2'] = run_nsga2(problem, ...)  # Usa mesmo problema

if args.algorithm == 'battery-focused':
    results['battery-focused'] = run_battery_focused_nsga2(problem, ...)  # Usa mesmo problema
```

**Vantagem**: Ambos usam o mesmo tratamento de violações (restrições G).

**Desvantagem**: NSGA2 padrão não foi projetado para trabalhar com restrições, pode ter comportamento diferente.

#### Opção 2: BatteryFocusedNSGA2 também com Penalização

Modificar `main.py` para que BatteryFocusedNSGA2 também use `use_constraints=False`:

```python
# Cria problema SEM restrições para ambos
problem = EVRPTWProblem(context, use_constraints=False, force_battery_feasible=False)

if args.algorithm in ['nsga2', 'both']:
    results['nsga2'] = run_nsga2(problem, ...)

if args.algorithm == 'battery-focused':
    results['battery-focused'] = run_battery_focused_nsga2(problem, ...)
```

**Vantagem**: Ambos usam o mesmo tratamento de violações (penalização).

**Desvantagem**: Perde a funcionalidade principal do BatteryFocusedNSGA2 (trabalhar com restrições e preservar inviáveis).

#### Opção 3: Comparação Separada (Recomendada)

Manter as diferenças, mas documentar claramente:

1. **NSGA2 com Penalização**: Para comparação com algoritmos que não usam restrições
2. **BatteryFocusedNSGA2 com Restrições**: Para demonstrar a estratégia de Directed Mating

E criar uma terceira opção:

3. **NSGA2 com Restrições**: Para comparação justa com BatteryFocusedNSGA2

### 6. Resumo das Diferenças

| Aspecto | NSGA2 | BatteryFocusedNSGA2 |
|---------|-------|---------------------|
| **use_constraints** | `False` | `True` |
| **Tratamento de violações** | Penalização no F | Restrições G |
| **force_battery_feasible (evolução)** | `True` ✅ **CORRIGIDO** (sempre) | `False` (durante evolução) |
| **force_battery_feasible (inicialização)** | `True` ✅ **CORRIGIDO** (sempre) | `True` (50% da população) |
| **Decoder** | Mesmo decoder | Mesmo decoder |
| **População inicial viável** | 0% (pode ser) | 50% (garantido) |
| **n_constr** | 0 | 2 |

## Conclusão

**Os algoritmos NÃO estão sendo executados nas mesmas condições:**

1. ❌ **Tratamento de violações diferente**: 
   - NSGA2 usa **penalização** no F (`use_constraints=False`)
   - BatteryFocusedNSGA2 usa **restrições G** (`use_constraints=True`)

2. ❌ **Comportamento do decoder diferente**:
   - NSGA2: `force_battery_feasible=True` → **Sempre viável** (decoder força retorno ao depósito)
   - BatteryFocusedNSGA2: `force_battery_feasible=False` durante evolução → **Permite violações** (decoder não força retorno)

3. ❌ **População inicial diferente**: 
   - NSGA2: 100% sempre viável (devido a `force_battery_feasible=True`)
   - BatteryFocusedNSGA2: 50% viável (inicialização híbrida)

4. ✅ **Decoder é o mesmo**: Ambos usam a mesma função `decode()`, mas com parâmetros diferentes

### Impacto nas Comparações

**NSGA2** (comportamento conservador):
- Sempre gera soluções viáveis (G2=0 ou penalizadas se inviáveis)
- Custo pode ser maior (mais veículos devido a retornos preventivos)
- Não explora soluções inviáveis com custo baixo

**BatteryFocusedNSGA2** (comportamento exploratório):
- Permite soluções inviáveis durante evolução (G2>0)
- Pode gerar soluções com custo menor (menos veículos)
- Explora trade-off entre viabilidade e custo

**Recomendação**: As diferenças são **intencionais** e fazem parte do design do BatteryFocusedNSGA2. Para comparação justa, seria necessário criar uma versão do NSGA2 que também use restrições (`use_constraints=True`) e `force_battery_feasible=False`, mas isso mudaria completamente o comportamento do NSGA2 padrão.
