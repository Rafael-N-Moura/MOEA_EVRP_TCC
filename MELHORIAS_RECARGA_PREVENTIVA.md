# Melhorias na Estratégia de Recarga Preventiva

## Problemas Identificados na Versão Anterior

1. **Verificação Tardia**: A heurística só verificava bateria DEPOIS de decidir visitar o cliente
2. **Recarga Mínima**: Recarregava apenas o mínimo necessário, sem margem de segurança
3. **Falta de Prevenção**: Não havia recarga preventiva quando bateria estava baixa mas ainda suficiente
4. **Cálculo Ineficiente**: Cálculo de energia necessário era feito múltiplas vezes de forma redundante
5. **Sem Opção de Retorno**: Não considerava retornar ao depósito quando bateria muito baixa

## Melhorias Implementadas

### 1. Funções Auxiliares para Cálculo de Energia

#### `_calculate_energy_needed(from_node, to_node, context)`
- Calcula energia necessária para ir de um nó a outro
- Centraliza o cálculo de distância × consumo

#### `_calculate_total_energy_for_customer(current_position, customer, context)`
- Calcula energia total necessária ANTES de visitar cliente
- Retorna: (energia_para_cliente, energia_total_com_seguranca)
- Considera safety buffer: energia para ir do cliente até estação/depósito mais próximo

### 2. Recarga Preventiva Inteligente

#### `_should_recharge_preventively(current_battery, battery_capacity, energy_needed)`
Decide se deve recarregar preventivamente baseado em 3 critérios:

1. **Threshold Preventivo (30%)**: Se bateria < 30% da capacidade, recarrega
2. **Energia Insuficiente**: Se bateria atual < energia necessária, recarrega
3. **Bateria Crítica Após Tarefa**: Se após visitar cliente bateria ficaria < 15%, recarrega

#### `_calculate_recharge_amount(...)`
Calcula recarga com margem de segurança:
- Energia necessária: estação → cliente → segurança
- Adiciona margem de segurança de 20% da capacidade
- Garante que após recarga há energia suficiente + buffer

### 3. Função de Recarga Robusta

#### `_recharge_at_station(...)`
- Encontra estação mais próxima
- Verifica se consegue chegar à estação
- Calcula recarga necessária com margem de segurança
- Retorna novo estado (posição, bateria, tempo)
- Se não consegue chegar à estação, retorna estado atual (será tratado como violação)

### 4. Verificação Preventiva Antes de Visitar Cliente

**Fluxo Melhorado:**
```
Para cada cliente:
  1. Calcula energia total necessária ANTES de decidir visitar
  2. Verifica se precisa recarregar preventivamente
  3. Se sim, recarrega na estação mais próxima
  4. Verifica se bateria está crítica (< 15%)
     - Se sim e próximo cliente está longe, considera retornar ao depósito
  5. Visita cliente (com verificação final de bateria)
```

### 5. Opção de Retorno ao Depósito Preventivo

Quando bateria está crítica (< 15%) e:
- Tem energia para retornar ao depósito
- Próximo cliente precisa de mais de 80% da bateria atual

→ Retorna ao depósito e abre novo veículo com bateria cheia

## Parâmetros Configuráveis

```python
BATTERY_THRESHOLD_PREVENTIVE = 0.30  # 30% - Recarrega preventivamente
BATTERY_THRESHOLD_CRITICAL = 0.15     # 15% - Considera retornar ao depósito
BATTERY_SAFETY_MARGIN = 0.20          # 20% - Margem de segurança após recarga
```

## Impacto Esperado

1. **Redução de Violações**: Verificação preventiva deve reduzir drasticamente violações de bateria
2. **Mais Soluções Viáveis**: Margem de segurança garante que soluções sejam viáveis
3. **Melhor Exploração**: Soluções viáveis permitem melhor exploração do espaço de busca
4. **Possível Aumento de Veículos**: Retorno preventivo ao depósito pode aumentar número de veículos, mas garante viabilidade

## Próximos Passos

1. Testar com script de diagnóstico para verificar redução de violações
2. Ajustar parâmetros se necessário (thresholds, margem de segurança)
3. Analisar trade-off entre viabilidade e número de veículos
4. Considerar otimizações adicionais se ainda houver muitas violações
