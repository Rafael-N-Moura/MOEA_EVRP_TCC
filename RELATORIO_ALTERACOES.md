# Relatório de Alterações: Migração para Objetivos Custo vs. Satisfação

**Data:** 2024  
**Versão:** 2.0  
**Contexto:** Migração de objetivos (Veículos/Distância) para (Custo/Satisfação)

---

## Resumo Executivo

O sistema foi completamente refatorado para implementar uma abordagem multi-objetivo mais robusta, substituindo os objetivos originais (número de veículos e distância) por **Custo Operacional** e **Nível de Serviço (Satisfação)**. Esta mudança resolve o problema de convergência mono-objetiva quando o número de veículos era constante.

---

## 1. Mudanças nas Estruturas de Dados (src/model.py)

### 1.1. Classe `Context`

**Adições:**
- `vehicle_cost: float = 1000.0` - Custo fixo por veículo utilizado
- `distance_cost: float = 1.0` - Custo por unidade de distância percorrida
- `delay_tolerance: float = 50.0` - Tolerância (em unidades de tempo) para cálculo de decaimento de satisfação

**Justificativa:** Permite configurar os custos operacionais e a sensibilidade a atrasos, tornando o sistema mais flexível para diferentes cenários de negócio.

### 1.2. Classe `RouteStep`

**Adições:**
- `satisfaction_score: float = 1.0` - Score de satisfação do cliente (0.0 a 1.0)

**Justificativa:** Permite rastrear a satisfação individual de cada cliente baseada em atrasos, essencial para calcular a insatisfação média.

### 1.3. Classe `Solution`

**Mudanças:**
- **Removido:** Não há remoções, apenas adições
- **Adicionado:**
  - `total_cost: float = 0.0` - Custo total (f1)
  - `avg_dissatisfaction: float = 0.0` - Insatisfação média (f2)

**Mudanças em Métodos:**
- **Novo método:** `calculate_objectives(context: Context)`
  - Calcula `total_cost = (total_vehicles * vehicle_cost) + (total_distance * distance_cost)`
  - Calcula `avg_dissatisfaction = 1.0 - média(satisfaction_scores)`
  - Deve ser chamado após todas as rotas estarem completas

**Mudanças em `add_violation()`:**
- **Comportamento anterior:** Qualquer violação marcava `is_feasible = False`
- **Comportamento novo:** Apenas violações físicas (bateria/carga) marcam como inviável
- **Violações de tempo:** Não marcam como inviável, apenas são registradas (soft constraint)

**Justificativa:** 
- Separação clara entre violações físicas (hard constraints) e violações de tempo (soft constraints)
- Violações de tempo são tratadas via satisfação, não via penalização

---

## 2. Mudanças no Decoder (src/decoder.py)

### 2.1. Cálculo de Satisfação

**Localização:** Durante visita ao cliente (Passo C)

**Algoritmo Implementado:**
```python
# Verificação de janela de tempo
if arrival_time < customer.ready_time:
    arrival_time = customer.ready_time  # Espera até ready_time

# Calcula satisfação baseada em atraso
satisfaction_score = 1.0
if arrival_time > customer.due_date:
    delay = arrival_time - customer.due_date
    # Si = max(0, 1.0 - (Atraso/Tolerancia))
    satisfaction_score = max(0.0, 1.0 - (delay / context.delay_tolerance))
```

**Comportamento:**
- Se `arrival_time <= due_date`: `satisfaction_score = 1.0` (totalmente satisfeito)
- Se `arrival_time > due_date`: Decaimento linear baseado em `delay_tolerance`
- Exemplo: Se `delay = 25` e `tolerance = 50`, então `satisfaction = 1.0 - (25/50) = 0.5`

**Justificativa:** Modela realisticamente o impacto de atrasos na satisfação do cliente, permitindo trade-offs entre custo e qualidade de serviço.

### 2.2. Registro de Violações de Tempo

**Mudança:**
- **Antes:** Violações de tempo marcavam `solution.is_feasible = False`
- **Agora:** Violações de tempo apenas são registradas em `solution.violations` (informação)
- **Impacto:** Soluções com atrasos não são mais penalizadas como "inviáveis", apenas têm maior insatisfação

### 2.3. Cálculo de Objetivos Finais

**Localização:** Final da função `decode()`

**Adição:**
```python
# Após calcular rotas
solution.__post_init__()  # Calcula veículos e distância
solution.calculate_objectives(context)  # Calcula custo e insatisfação
```

**Justificativa:** Separação clara entre métricas básicas (veículos, distância) e objetivos finais (custo, insatisfação).

---

## 3. Mudanças no Adaptador Pymoo (src/problem.py)

### 3.1. Constantes de Penalização

**Mudanças:**
- **Removido:**
  - `PENALTY_V = 100` (penalidade para veículos)
  - `PENALTY_D = 10000` (penalidade para distância)
- **Adicionado:**
  - `PENALTY_COST = 100000` (penalidade para custo em violações físicas)
  - `PENALTY_DISSATISFACTION = 1.0` (penalidade para insatisfação)

**Justificativa:** Penalizações agora refletem os novos objetivos e são aplicadas apenas para violações físicas graves.

### 3.2. Objetivos Retornados

**Mudança:**
```python
# ANTES:
f1 = solution.total_vehicles
f2 = solution.total_distance

# AGORA:
f1 = solution.total_cost
f2 = solution.avg_dissatisfaction
```

**Justificativa:** Objetivos agora representam trade-offs reais entre custo operacional e qualidade de serviço.

### 3.3. Tratamento de Inviabilidade

**Mudança:**
- **Antes:** Qualquer violação (incluindo tempo) aplicava penalização
- **Agora:** Apenas violações físicas (bateria/carga) aplicam penalização
- **Violações de tempo:** Já são refletidas em `avg_dissatisfaction`, não precisam penalização adicional

**Justificativa:** Alinhado com a nova filosofia de soft constraints para tempo.

---

## 4. Mudanças na Interface (main.py)

### 4.1. Mensagens de Saída

**Mudanças em todas as funções de exibição:**

**Antes:**
```
f1 (veículos): min=X, max=Y
f2 (distância): min=X, max=Y
Solução 1: X veículos, Y distância
```

**Agora:**
```
f1 (custo): min=X.XX, max=Y.YY
f2 (insatisfação): min=X.XXXX, max=Y.YYYY
Solução 1: Custo=X.XX, Insatisfação=Y.YYYY
```

**Justificativa:** Interface reflete os novos objetivos e usa formatação apropriada (decimais para custo, 4 casas para insatisfação).

---

## 5. Mudanças no Parser (src/parser.py)

**Status:** Nenhuma mudança necessária

**Justificativa:** Os custos têm valores padrão (`vehicle_cost=1000.0`, `distance_cost=1.0`, `delay_tolerance=50.0`), então não precisam ser lidos do arquivo. Futuras extensões podem adicionar parsing de custos se necessário.

---

## 6. Impacto nas Funcionalidades

### 6.1. Comportamento do Algoritmo

**Antes:**
- Quando número de veículos era constante, problema se tornava mono-objetivo (apenas distância)
- Resultado: `n_nds = 1` sempre

**Agora:**
- Custo combina veículos e distância, sempre variando
- Insatisfação varia baseada em atrasos
- Resultado esperado: Múltiplas soluções não-dominadas (`n_nds > 1`)

### 6.2. Trade-offs Explorados

**Antes:**
- Trade-off: Menos veículos vs. Mais distância
- Problema: Quando veículos constantes, sem trade-off

**Agora:**
- Trade-off: Menor custo vs. Maior satisfação
- Sempre há trade-off, pois:
  - Menor custo pode exigir mais veículos ou rotas mais longas
  - Maior satisfação pode exigir mais veículos (menos carga por veículo) ou rotas mais longas (para respeitar janelas)

### 6.3. Interpretação dos Resultados

**Frente de Pareto Agora Representa:**
- **Eixo X (Custo):** Quanto a empresa gasta (veículos + distância)
- **Eixo Y (Insatisfação):** Quão insatisfeitos os clientes estão (0.0 = totalmente satisfeito, 1.0 = totalmente insatisfeito)

**Soluções Ideais:**
- **Canto inferior esquerdo:** Baixo custo E alta satisfação (ideal, mas raro)
- **Canto inferior direito:** Alto custo MAS alta satisfação (premium)
- **Canto superior esquerdo:** Baixo custo MAS baixa satisfação (econômico)
- **Canto superior direito:** Alto custo E baixa satisfação (evitar)

---

## 7. Compatibilidade e Migração

### 7.1. Compatibilidade com Código Existente

**Quebrada:** Sim, mudanças são incompatíveis com versão anterior

**Razão:** Objetivos mudaram completamente (de veículos/distância para custo/insatisfação)

### 7.2. Dados Mantidos

**Mantidos para Análise:**
- `total_vehicles` - Ainda calculado e disponível
- `total_distance` - Ainda calculado e disponível
- `routes` - Estrutura completa mantida
- `violations` - Lista de violações mantida

**Justificativa:** Permite análise detalhada mesmo com novos objetivos.

### 7.3. Migração de Resultados Anteriores

**Não aplicável:** Resultados anteriores (veículos/distância) não podem ser convertidos diretamente para custo/insatisfação, pois:
- Custo requer `vehicle_cost` e `distance_cost` (não disponíveis antes)
- Insatisfação requer cálculo de satisfação por cliente (não calculado antes)

---

## 8. Testes e Validação

### 8.1. Testes Necessários

1. **Teste de Satisfação:**
   - Verificar que clientes sem atraso têm `satisfaction_score = 1.0`
   - Verificar decaimento linear para atrasos
   - Verificar que `satisfaction_score >= 0.0`

2. **Teste de Custo:**
   - Verificar que `total_cost = (vehicles * vehicle_cost) + (distance * distance_cost)`
   - Verificar que custo aumenta com mais veículos
   - Verificar que custo aumenta com mais distância

3. **Teste de Trade-offs:**
   - Executar algoritmo e verificar `n_nds > 1`
   - Verificar que soluções na frente de Pareto têm diferentes trade-offs

### 8.2. Validação Esperada

**Após mudanças:**
- Múltiplas soluções não-dominadas (`n_nds > 1`)
- Trade-offs claros entre custo e insatisfação
- Soluções com diferentes números de veículos exploradas

---

## 9. Melhorias Implementadas

### 9.1. Separação de Hard vs. Soft Constraints

**Antes:** Todas as violações eram tratadas igualmente

**Agora:**
- **Hard constraints:** Bateria e carga (marcam como inviável)
- **Soft constraints:** Janelas de tempo (afetam satisfação, não viabilidade)

**Benefício:** Modelo mais realista e flexível.

### 9.2. Modelagem de Satisfação

**Antes:** Violações de tempo eram apenas penalizadas

**Agora:** Satisfação modelada como decaimento linear baseado em atraso

**Benefício:** Permite análise quantitativa de qualidade de serviço.

### 9.3. Objetivos Sempre Variáveis

**Antes:** Quando veículos constantes, problema mono-objetivo

**Agora:** Custo sempre varia (combina veículos e distância)

**Benefício:** Garante exploração de trade-offs mesmo em cenários restritivos.

---

## 10. Próximos Passos Recomendados

1. **Executar testes** com novas configurações
2. **Ajustar parâmetros** (`vehicle_cost`, `distance_cost`, `delay_tolerance`) conforme necessário
3. **Validar** que `n_nds > 1` em execuções
4. **Analisar** frente de Pareto para garantir trade-offs significativos
5. **Documentar** valores de parâmetros usados nos experimentos

---

## 11. Arquivos Modificados

1. `src/model.py` - Estruturas de dados
2. `src/decoder.py` - Lógica de decodificação e satisfação
3. `src/problem.py` - Adaptador Pymoo
4. `main.py` - Interface de saída

## 12. Arquivos Não Modificados

1. `src/parser.py` - Mantido como está (custos têm defaults)
2. `src/__init__.py` - Mantido como está

---

**Fim do Relatório**
