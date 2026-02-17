# Análise de Performance: BatteryFocusedNSGA2 vs NSGA-II Padrão

## Resultados Observados

**Instância**: `rc208_21.txt` (100 clientes, 21 estações)  
**Configuração**: 100 gerações, população 100

| Algoritmo | Tempo de Execução | Diferença |
|-----------|-------------------|-----------|
| NSGA-II Padrão | 34.50 segundos | Baseline |
| BatteryFocusedNSGA2 | 91.36 segundos | **+165% mais lento** |

## Análise dos Gargalos

### 1. Cálculo de Violação de Bateria (G2) - **PRINCIPAL GARGALO**

**Problema**: O método `calculate_battery_violation()` é chamado para **cada solução avaliada** e percorre todas as rotas e todos os passos.

**Custo Computacional**:
- Chamado: 1 vez por solução avaliada
- Em 100 gerações com população 100: ~10.000 chamadas (100 inicial + 100 por geração)
- Cada chamada: O(n_routes × n_steps_per_route)
- Para instância com 100 clientes: ~100-200 passos por solução

**Código atual**:
```python
def calculate_battery_violation(self, context: 'Context'):
    total_deficit = 0.0
    for route in self.routes:
        for step in route.steps:
            distance = current_position.distance_to(step.node)  # Cálculo de distância
            energy_needed = distance * context.consumption_rate
            # ... mais processamento ...
```

**Impacto estimado**: ~40-50% do tempo total

### 2. Sobrevivência Customizada (InfeasibleSurvival)

**Problema**: A sobrevivência customizada faz mais processamento que a padrão:

1. **Separação viáveis/inviáveis**: O(n)
2. **Non-dominated sorting dos viáveis**: O(n²) no pior caso
3. **Cálculo de crowding distance**: O(n × m) onde m = número de objetivos
4. **Múltiplas ordenações**: Viáveis por rank+crowding, inviáveis por custo

**Código atual**:
```python
# Non-dominated sorting
nds = NonDominatedSorting()
fronts = nds.do(feasible_pop.get("F"))  # O(n²)

# Para cada frente, calcula crowding distance
for rank, front_indices in enumerate(fronts):
    cd = calculate_crowding_distance(rank_pop.get("F"))  # O(n × m)
```

**Impacto estimado**: ~20-30% do tempo total

### 3. Acasalamento Direcionado

**Problema**: A cada geração, separa população em viáveis/inviáveis:

```python
feasible_mask = pop.get("G")[:, 1] <= 0
feasible_indices = np.where(feasible_mask)[0]
infeasible_indices = np.where(~feasible_mask)[0]
```

**Impacto estimado**: ~5-10% do tempo total (menor, mas ainda adiciona overhead)

### 4. Cálculo Duplicado de Violação

**Problema**: A violação de bateria pode estar sendo calculada duas vezes:
1. Durante decodificação (para expor G2)
2. Durante cálculo de violação (método `calculate_battery_violation()`)

**Impacto estimado**: ~10-15% do tempo total

## Otimizações Propostas

### Otimização 1: Calcular G2 Durante Decodificação (CRÍTICO)

**Problema**: Atualmente calculamos G2 **depois** de construir toda a solução, percorrendo tudo novamente.

**Solução**: Calcular G2 **durante** a decodificação, acumulando déficits conforme vamos visitando clientes.

**Implementação**:
```python
# No decoder, durante visita ao cliente:
if current_battery < battery_needed:
    deficit = battery_needed - current_battery
    solution.battery_violation += deficit  # Acumula durante decodificação
    current_battery = 0.0
```

**Ganho esperado**: Elimina 100% do custo de `calculate_battery_violation()` → **-40 a -50% do tempo total**

### Otimização 2: Cache de Separação Viáveis/Inviáveis

**Problema**: Separamos viáveis/inviáveis múltiplas vezes por geração (mating + survival).

**Solução**: Calcular uma vez e reutilizar.

**Ganho esperado**: **-5 a -10% do tempo total**

### Otimização 3: Otimizar Sobrevivência Customizada

**Problema**: Fazemos non-dominated sorting e crowding distance mesmo quando não necessário.

**Solução**: 
- Usar implementação otimizada do NSGA2 padrão quando possível
- Calcular crowding distance apenas para frentes grandes (>2 indivíduos)
- Usar numpy operations vetorizadas

**Ganho esperado**: **-10 a -15% do tempo total**

### Otimização 4: Reduzir Cálculo de Crowding Distance

**Problema**: Calculamos crowding distance manualmente, pode ser menos eficiente.

**Solução**: Usar implementação otimizada do pymoo (se disponível) ou vetorizar melhor.

**Ganho esperado**: **-5% do tempo total**

## Análise: Por Que Está Mais Lento?

### Expectativa vs Realidade

**Expectativa Original**: O Directed Mating deveria **acelerar convergência** (menos gerações para convergir), não necessariamente reduzir tempo por geração.

**Realidade**: O algoritmo está mais lento **por geração**, o que compensa qualquer ganho em convergência.

### Conclusões

1. **Overhead de Processamento**: As estratégias customizadas adicionam overhead significativo por geração
2. **Cálculo de G2 Ineficiente**: Principal gargalo - calculado após decodificação completa
3. **Sobrevivência Mais Complexa**: Processa mais informações que a padrão
4. **Trade-off**: O algoritmo pode convergir mais rápido (menos gerações), mas cada geração é mais lenta

### Recomendações

#### Curto Prazo (Implementação Imediata)

1. **Calcular G2 durante decodificação** (Otimização 1)
   - Maior impacto
   - Implementação simples
   - Ganho estimado: -40 a -50% do tempo

2. **Cache de separação viáveis/inviáveis** (Otimização 2)
   - Implementação simples
   - Ganho estimado: -5 a -10% do tempo

#### Médio Prazo

3. **Otimizar sobrevivência customizada** (Otimização 3)
   - Usar implementações mais eficientes
   - Ganho estimado: -10 a -15% do tempo

#### Análise Adicional

4. **Medir convergência real**: 
   - Quantas gerações cada algoritmo precisa para convergir?
   - Se BatteryFocusedNSGA2 convergir em 50 gerações vs NSGA2 em 100, pode compensar
   - Tempo total = tempo_por_geração × n_gerações

5. **Comparar qualidade das soluções**:
   - Se BatteryFocusedNSGA2 encontrar soluções melhores, o tempo extra pode ser justificado
   - Métricas: hipervolume, número de soluções não-dominadas, diversidade

## Próximos Passos

1. **Implementar Otimização 1** (calcular G2 durante decodificação)
2. **Medir convergência**: Comparar número de gerações até convergência
3. **Medir qualidade**: Comparar hipervolume e diversidade das soluções
4. **Decidir trade-off**: Se convergência for muito melhor, pode valer o tempo extra

## Observação Importante

O objetivo do Directed Mating não era necessariamente **reduzir tempo de execução**, mas sim **melhorar convergência** (encontrar melhores soluções em menos gerações). Se o algoritmo convergir em 50 gerações enquanto o NSGA2 precisa de 100, o tempo total seria similar mesmo com cada geração sendo mais lenta.

**Precisamos medir**:
- Número de gerações até convergência
- Qualidade das soluções encontradas
- Trade-off tempo vs qualidade
