# Diagnóstico: Por que n_nds = 1 após mudança de objetivos

## Problema Observado

Após implementar os novos objetivos (Custo vs. Insatisfação), ainda temos apenas 1 solução na frente de Pareto:

```
f1 (custo): min=110118.06, max=110118.06, média=110118.06  ← TODOS IGUAIS!
f2 (insatisfação): min=1.0000, max=1.0000, média=1.0000  ← TODOS IGUAIS!
```

## Análise

### Problema 1: Insatisfação = 1.0 (Máxima)

**Significado:** Todos os clientes têm satisfação = 0.0, ou seja, todos estão sendo atendidos com atrasos muito grandes.

**Causa Provável:**
- `delay_tolerance = 50.0` pode ser muito baixo
- Se um cliente tem atraso de 100 unidades de tempo:
  - `satisfaction = max(0, 1.0 - (100/50)) = max(0, -1.0) = 0.0`
- Se TODOS os clientes têm atraso > 50, todos terão satisfação 0.0
- Resultado: `avg_dissatisfaction = 1.0 - 0.0 = 1.0`

**Solução:** Aumentar `delay_tolerance` para um valor mais realista (ex: 200.0)

### Problema 2: Custo Idêntico

**Significado:** Todas as soluções têm exatamente o mesmo número de veículos E a mesma distância total.

**Causas Possíveis:**

1. **Heurística Construtiva Muito Determinística:**
   - A ordem da permutação pode não estar afetando significativamente a solução final
   - Restrições muito restritivas podem forçar sempre a mesma estrutura de rotas

2. **Restrições Muito Restritivas:**
   - Capacidade de carga pode forçar sempre o mesmo número de veículos
   - Bateria pode forçar sempre as mesmas recargas nos mesmos lugares

3. **Problema na Ordem de Processamento:**
   - A heurística pode estar ignorando a ordem da permutação em algum ponto

## Soluções Implementadas

### 1. Aumentar Tolerância de Atraso

**Mudança:** `delay_tolerance: 50.0 → 200.0`

**Justificativa:** Permite mais variação na satisfação, criando trade-offs entre custo e satisfação.

**Impacto Esperado:** 
- Clientes com atrasos menores terão satisfação > 0
- Variação na insatisfação entre soluções
- Múltiplas soluções não-dominadas

### 2. Verificar Cálculo de Satisfação

O cálculo está correto:
```python
if arrival_time > customer.due_date:
    delay = arrival_time - customer.due_date
    satisfaction_score = max(0.0, 1.0 - (delay / context.delay_tolerance))
```

Com `delay_tolerance = 200.0`:
- Atraso de 50: `satisfaction = 1.0 - (50/200) = 0.75`
- Atraso de 100: `satisfaction = 1.0 - (100/200) = 0.50`
- Atraso de 200: `satisfaction = 1.0 - (200/200) = 0.0`
- Atraso de 300: `satisfaction = 0.0` (limitado)

## Próximos Passos

1. **Testar com nova tolerância:**
   ```bash
   python3 main.py evrptw_instances/r101_21.txt --algorithm nsga2 --n-gen 100 --pop-size 100
   ```

2. **Se ainda houver problema de custo idêntico:**
   - Verificar se diferentes permutações geram diferentes números de veículos
   - Analisar se restrições estão forçando sempre mesma estrutura
   - Considerar ajustar `vehicle_cost` vs `distance_cost` para criar mais trade-offs

3. **Se insatisfação ainda for 1.0:**
   - Verificar se realmente todos os clientes têm atrasos muito grandes
   - Considerar aumentar ainda mais a tolerância
   - Verificar se há bug no cálculo de satisfação

## Ajustes Adicionais Recomendados

### Ajuste 1: Proporção de Custos

Se custo sempre igual, pode ser que `vehicle_cost` seja muito alto comparado a `distance_cost`, fazendo que número de veículos domine completamente.

**Teste:** Reduzir `vehicle_cost` ou aumentar `distance_cost` para criar mais trade-offs.

### Ajuste 2: Tolerância Adaptativa

Em vez de tolerância fixa, usar tolerância baseada na janela de tempo:
```python
# Tolerância = 50% da janela de tempo
tolerance = (customer.due_date - customer.ready_time) * 0.5
```

Isso tornaria a tolerância mais realista para cada cliente.

## Comandos de Teste

```bash
# Teste 1: Com tolerância aumentada
python3 main.py evrptw_instances/r101_21.txt --algorithm nsga2 --n-gen 100 --pop-size 100

# Teste 2: Com mais gerações para explorar mais
python3 main.py evrptw_instances/r101_21.txt --algorithm nsga2 --n-gen 200 --pop-size 100

# Teste 3: Com população maior
python3 main.py evrptw_instances/r101_21.txt --algorithm nsga2 --n-gen 100 --pop-size 200
```
