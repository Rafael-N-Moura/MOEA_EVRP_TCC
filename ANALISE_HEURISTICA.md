# Análise da Heurística Construtiva

## Problema Identificado

A heurística construtiva atual está gerando **soluções inviáveis** porque:

1. **Visita clientes na ordem da permutação** sem considerar viabilidade energética
2. **Verifica bateria apenas quando já está "tarde demais"** (após decidir visitar cliente)
3. **Não previne violações**, apenas tenta corrigir depois
4. **Resultado:** 238 violações de bateria em uma única solução

## Fluxo Atual da Heurística

```
Para cada cliente na permutação:
  1. Verifica capacidade de carga → Se exceder, abre novo veículo
  2. Calcula distância até cliente
  3. Simula ir para cliente (bateria - distância)
  4. Verifica se tem bateria para chegar ao cliente E ir para estação/depósito
  5. Se NÃO tem → Tenta ir para estação
     - Se não tem bateria para estação → Violação!
  6. Visita cliente
```

## Problemas Identificados

### Problema 1: Verificação Tardia
A heurística só verifica bateria **depois** de decidir visitar o cliente. Se não tem bateria suficiente, já é tarde demais.

### Problema 2: Safety Buffer Insuficiente
O safety buffer verifica se consegue ir do cliente para estação/depósito, mas:
- Não considera que pode precisar recarregar ANTES de visitar o cliente
- Não previne que a bateria fique muito baixa

### Problema 3: Falta de Prevenção
A heurística não previne violações, apenas tenta corrigir depois que já está em uma situação ruim.

### Problema 4: Recarga Mínima
Quando recarrega, recarrega apenas o mínimo necessário. Isso pode levar a situações onde logo depois precisa recarregar novamente.

## Soluções Propostas

### Solução 1: Verificação Preventiva (Recomendado)
Antes de visitar um cliente, verificar se tem bateria suficiente considerando:
- Distância até cliente
- Distância do cliente até estação/depósito mais próxima
- Margem de segurança (buffer)

Se não tem, recarregar ANTES de tentar visitar.

### Solução 2: Recarga Preventiva
Quando bateria está abaixo de um threshold (ex: 30% da capacidade), recarregar preventivamente mesmo que ainda tenha bateria suficiente.

### Solução 3: Retorno ao Depósito Preventivo
Se bateria está muito baixa e não há estação próxima, retornar ao depósito e abrir novo veículo.

### Solução 4: Reordenação Local
Dentro de uma rota, reordenar clientes próximos para minimizar distâncias e violações.

## Implementação Recomendada

Vou implementar uma verificação preventiva mais robusta que:
1. Verifica bateria ANTES de decidir visitar cliente
2. Se não tem bateria suficiente, recarrega ANTES
3. Se não consegue recarregar, retorna ao depósito
4. Usa margem de segurança maior
