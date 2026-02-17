# Solução: Problema de Viabilidade

## Problema Identificado

O decoder está gerando soluções **inviáveis** porque:
1. A heurística construtiva visita clientes na ordem da permutação
2. Quando não há bateria suficiente, tenta ir para uma estação
3. Se não há bateria nem para chegar à estação, marca como violação
4. Isso resulta em **TODAS as soluções sendo inviáveis**

## Consequências

- Todas as soluções recebem penalidade de 100000
- f1 = 100002 (2 veículos + 100000 penalidade)
- Tempo rápido porque todas têm valores similares ruins
- Apenas 13 soluções não-dominadas (todas ruins)

## Soluções Possíveis

### Opção 1: Melhorar Heurística Construtiva (Recomendado)

A heurística atual é muito simples. Podemos:
1. **Forçar retorno ao depósito** quando bateria está baixa
2. **Recarregar preventivamente** antes de ficar sem bateria
3. **Reordenar clientes** dentro de uma rota para melhorar viabilidade

### Opção 2: Penalização Gradual

Em vez de penalidade fixa de 100000, usar penalização proporcional:
- Penalidade = violações * fator
- Isso permite diferenciar soluções com diferentes níveis de violação

### Opção 3: Permitir Soluções Parcialmente Inviáveis

Tratar violações de bateria como "soft constraints" com penalização menor, não como inviabilidade total.

## Implementação Imediata: Penalização Gradual

Vou implementar penalização proporcional para permitir que o algoritmo diferencie soluções com diferentes níveis de violação.
