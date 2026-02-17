# Explicação dos Logs do Pymoo

## Tabela de Progresso

A tabela gerada durante a execução mostra o progresso do algoritmo evolutivo:

```
n_gen  |  n_eval  | n_nds  |      eps      |   indicator  
```

### Colunas

#### 1. `n_gen` (Número da Geração)
- **Significado**: Geração atual do algoritmo
- **Exemplo**: `1`, `2`, `3`, ..., `100`
- **Interpretação**: Quantas vezes a população foi evoluída

#### 2. `n_eval` (Número de Avaliações)
- **Significado**: Total de indivíduos avaliados até o momento
- **Cálculo**: `n_gen × pop_size × 2` (geralmente, pois cada geração avalia população + filhos)
- **Exemplo**: Geração 1 com pop_size=100 → ~200 avaliações
- **Interpretação**: Quantas vezes a função `_evaluate()` foi chamada

#### 3. `n_nds` (Número de Soluções Não-Dominadas) ⚠️ **CRÍTICO**
- **Significado**: Quantas soluções estão na frente de Pareto atual
- **Valor esperado**: Múltiplas soluções (ex: 5, 10, 20+)
- **Valor observado**: **Sempre 1** ❌
- **Interpretação**: 
  - Se `n_nds = 1`: Apenas uma solução não é dominada por nenhuma outra
  - Isso é **anormal** para um problema multi-objetivo
  - Indica que todas as outras soluções são dominadas por esta única solução

#### 4. `eps` (Épsilon - Indicador de Convergência)
- **Significado**: Medida de melhoria entre gerações
- **Valores**:
  - `0.000000E+00`: Nenhuma melhoria (convergência estagnada)
  - Valores positivos: Melhoria detectada
- **Interpretação**: 
  - `0.0`: Algoritmo não está melhorando
  - Valores grandes: Melhoria significativa

#### 5. `indicator` (Tipo de Indicador)
- **Significado**: Tipo de métrica usada para medir progresso
- **Valores possíveis**:
  - `ideal`: Melhoria em relação ao ponto ideal
  - `f`: Melhoria em relação à frente de Pareto anterior
  - `-`: Primeira geração (sem comparação)

## Análise do Problema Atual

### Observações Críticas dos Seus Logs

1. **`n_nds = 1` em TODAS as gerações** ⚠️ **PROBLEMA PRINCIPAL**
   - Isso é **muito anormal** para um problema multi-objetivo
   - Indica que apenas 1 solução não é dominada por nenhuma outra
   - Todas as outras soluções na população são dominadas por esta única
   - **Significado**: Em cada geração, há apenas 1 solução na frente de Pareto

2. **`eps = 0.000000E+00` frequente**
   - Muitas gerações sem melhoria (estagnação)
   - Algoritmo não está encontrando soluções melhores
   - Quando `eps = 0`, significa que a frente de Pareto não melhorou

3. **`eps` com valores positivos ocasionais**
   - Indica que ocasionalmente uma solução melhor é encontrada
   - Mas ainda assim, apenas 1 solução não-dominada permanece
   - Os valores positivos mostram que há alguma exploração, mas não diversidade

### Interpretação dos Seus Resultados

```
n_gen  |  n_eval  | n_nds  |      eps      |   indicator  
    100 |    20000 |      1 |  0.000000E+00 |             f
```

**Tradução:**
- Após 100 gerações e 20.000 avaliações
- Apenas **1 solução não-dominada** foi encontrada
- Nenhuma melhoria na última geração (`eps = 0`)
- Indicador `f` significa comparação com frente anterior (sem melhoria)

### Possíveis Causas

#### Causa 1: Todas as Soluções Têm Valores Idênticos
- Se todas as permutações resultam em `(f1, f2)` idênticos
- Então todas são equivalentes, e apenas 1 é mantida
- **Verificação**: Ver se f1 e f2 variam entre soluções

#### Causa 2: Problema no Decoder
- O decoder pode estar gerando sempre a mesma solução
- Independente da permutação de entrada
- **Verificação**: Testar decoder com diferentes permutações

#### Causa 3: Problema na Avaliação
- A função `_evaluate()` pode ter um bug
- Todas as soluções recebem os mesmos valores
- **Verificação**: Adicionar logs na avaliação

#### Causa 4: Penalização Muito Alta
- Se todas as soluções são inviáveis e recebem penalização
- Todas ficam com valores muito altos e similares
- **Verificação**: Ver quantas soluções são viáveis

## Próximos Passos de Investigação

1. **Verificar se f1 e f2 variam** entre soluções
2. **Testar decoder** com diferentes permutações
3. **Adicionar logs** na função de avaliação
4. **Verificar viabilidade** das soluções
