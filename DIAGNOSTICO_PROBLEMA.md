# Diagnóstico: Por que apenas 1 solução?

## Resumo do Problema

**Sintoma**: `n_nds = 1` em todas as gerações (apenas 1 solução não-dominada)

**Significado**: Todas as outras soluções na população são dominadas por esta única solução.

## Hipóteses a Investigar

### Hipótese 1: Todas as Permutações Geram a Mesma Solução ⚠️ **MAIS PROVÁVEL**

**Causa**: O decoder pode estar gerando sempre a mesma solução, independente da permutação de entrada.

**Como verificar**:
```bash
python3 test_decoder.py
```

Este script testa o decoder com diferentes permutações e verifica se gera soluções diferentes.

**Se confirmado**: O problema está no decoder - ele não está usando a ordem da permutação corretamente.

### Hipótese 2: Todas as Soluções Têm Valores Idênticos

**Causa**: Diferentes permutações podem estar resultando em `(f1, f2)` idênticos.

**Como verificar**: Execute o teste acima e veja se f1 e f2 variam.

**Se confirmado**: Há um problema na lógica de decodificação ou avaliação.

### Hipótese 3: Penalização Muito Alta

**Causa**: Se todas as soluções são inviáveis e recebem penalização muito alta, todas ficam com valores similares e altos.

**Como verificar**: Adicione logs para ver quantas soluções são viáveis.

### Hipótese 4: Problema com PermutationRandomSampling

**Causa**: O Pymoo pode não estar gerando permutações válidas corretamente.

**Como verificar**: Verifique se as permutações geradas são realmente diferentes.

## Plano de Ação

### Passo 1: Testar o Decoder

Execute:
```bash
python3 test_decoder.py
```

Isso mostrará se diferentes permutações geram soluções diferentes.

### Passo 2: Adicionar Logs na Avaliação

Se o decoder estiver OK, adicione logs em `problem.py` para ver os valores de f1 e f2.

### Passo 3: Verificar Viabilidade

Adicione contador de soluções viáveis vs inviáveis.

## Próximos Passos

1. Execute `test_decoder.py` para verificar se o decoder está funcionando
2. Se o decoder estiver OK, investigue a avaliação
3. Se necessário, adicione mais logs para diagnóstico
