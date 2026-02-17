# Conjecturas: Por que uma solução domina todas as outras?

## Observação Central

Uma solução aparentemente é melhor que todas as outras em **ambos** os objetivos (f1 e f2), resultando em `n_nds = 1`. Isso acontece mesmo com diferentes permutações e diferentes instâncias.

## Conjectura 1: Heurística Construtiva Muito Conservadora

### O Que Acontece

A heurística construtiva processa clientes **sequencialmente na ordem exata da permutação**, sem reordenação ou otimização:

```python
for customer in customer_nodes:  # Ordem fixa da permutação
    # Sempre visita este cliente agora
    # Sempre escolhe estação mais próxima
    # Sempre recarrega mínimo necessário
    # Sempre espera até ready_time se chegar cedo
```

### Por Que Isso Causa Dominância

1. **Sem Flexibilidade:**
   - Não considera visitar outro cliente primeiro se chegar cedo
   - Não considera diferentes estratégias de recarga
   - Não reordena clientes dentro de uma rota

2. **Decisões Sempre Iguais:**
   - Para o mesmo cliente na mesma posição relativa, sempre faz as mesmas escolhas
   - Resultado: Rotas muito similares, independente da permutação

3. **Efeito:**
   - Diferentes permutações geram soluções muito similares
   - Uma solução ligeiramente melhor (menor distância, mesmo número de veículos) domina todas

## Conjectura 2: Restrições Forçam Estrutura Única

### Restrição de Carga

**Comportamento:**
```python
if current_load + customer.demand > vehicle_capacity:
    # Abre novo veículo
```

**Efeito:**
- Se a demanda total e capacidade são fixas, o **número mínimo de veículos é fixo**
- A ordem pode afetar se conseguimos encaixar mais clientes, mas se a capacidade é restritiva, sempre precisamos do mínimo

**Exemplo:**
- Capacidade: 200
- 5 clientes com demanda 50 cada = 250 total
- Mínimo: 2 veículos (250/200 = 1.25)
- Qualquer ordem que tente 1 veículo falhará
- **Resultado:** Sempre 2 veículos, independente da ordem

**Impacto na Dominância:**
- Se todas as soluções têm o mesmo número de veículos, o custo varia apenas com distância
- Se a distância não varia muito, o custo não varia muito
- Uma solução com menor distância domina todas

### Restrição de Bateria (Safety Buffer)

**Comportamento:**
```python
if battery_after_customer < battery_for_safety:
    # Recarrega antes
```

**Efeito:**
- Safety buffer força recargas em pontos específicos
- Se a bateria é limitada, sempre precisa recarregar após X clientes
- Isso cria estruturas de rotas muito similares

**Impacto na Dominância:**
- Todas as rotas têm recargas nos mesmos pontos relativos
- Distâncias são muito similares (mesmas recargas, mesmas rotas)
- Uma solução com ligeiramente menor distância domina

## Conjectura 3: Satisfação Sempre Máxima (Insatisfação = 1.0)

### O Que Observamos

Todas as soluções têm `insatisfação = 1.0`, o que significa que todos os clientes têm `satisfação = 0.0`.

### Por Que Isso Acontece

**Cálculo de Satisfação:**
```python
if arrival_time > customer.due_date:
    delay = arrival_time - customer.due_date
    satisfaction = max(0.0, 1.0 - (delay / delay_tolerance))
```

**Se `delay > delay_tolerance` para todos:**
- Todos têm `satisfaction = 0.0`
- `avg_dissatisfaction = 1.0 - 0.0 = 1.0`
- **Resultado:** f2 sempre 1.0, não há variação

### Por Que Todos Têm Atrasos Grandes?

1. **Heurística não otimiza tempo:**
   - Visita clientes na ordem da permutação
   - Não considera janelas de tempo ao escolher ordem
   - Não reordena para respeitar janelas

2. **Recargas adicionam tempo:**
   - Cada recarga adiciona tempo de viagem + tempo de recarga
   - Isso pode fazer chegar tarde em muitos clientes

3. **Safety buffer conservador:**
   - Pode estar forçando recargas desnecessárias
   - Isso adiciona tempo e atrasos

### Impacto na Dominância

Se `insatisfação = 1.0` sempre:
- f2 não varia
- Problema se torna efetivamente mono-objetivo (apenas f1)
- Uma solução com menor custo domina todas

## Conjectura 4: Proporção de Custos Cria Dominância

### Cálculo de Custo

```python
total_cost = (vehicles * 1000.0) + (distance * 1.0)
```

### Análise

**Se todas têm mesmo número de veículos:**
- Custo base = `vehicles * 1000.0` (constante)
- Variação = `distance * 1.0`
- Se distância varia pouco, custo varia pouco

**Se uma solução tem menor distância:**
- Menor custo (f1)
- Se insatisfação também for menor (ou igual), domina todas

### Por Que Custo Não Varia Muito?

1. **Número de veículos constante:**
   - Restrições forçam sempre o mesmo número mínimo
   - Custo base sempre igual

2. **Distância similar:**
   - Heurística determinística gera rotas similares
   - Mesmas recargas, mesmas estruturas
   - Distâncias muito próximas

3. **Resultado:**
   - Custo varia pouco entre soluções
   - Uma solução ligeiramente melhor domina

## Conjectura 5: Ordem da Permutação Não Afeta Muito

### Por Que a Ordem Não Cria Diversidade?

1. **Heurística sempre faz mesmas escolhas:**
   - Sempre escolhe estação mais próxima
   - Sempre recarrega mínimo necessário
   - Sempre visita na ordem exata

2. **Restrições forçam estrutura:**
   - Sempre precisa do mesmo número de veículos
   - Sempre precisa recarregar nos mesmos pontos
   - Sempre tem mesmas estruturas de rotas

3. **Resultado:**
   - Diferentes permutações geram soluções muito similares
   - Pouca variação em custo e insatisfação
   - Uma solução domina todas

### Exemplo Teórico

**Permutação 1:** [0, 1, 2, 3, 4]
- Veículo 1: 0, 1, 2 (carga cheia)
- Veículo 2: 3, 4
- Distância: 1000

**Permutação 2:** [4, 3, 2, 1, 0]
- Veículo 1: 4, 3, 2 (carga cheia)
- Veículo 2: 1, 0
- Distância: 1050

**Resultado:**
- Mesmo número de veículos (2)
- Distâncias muito similares (1000 vs 1050)
- Custo muito similar (2000 + 1000 = 3000 vs 2000 + 1050 = 3050)
- Se insatisfação também similar, uma domina a outra

## Conjectura 6: Falta de Trade-offs Reais

### O Que É Um Trade-off?

Para ter múltiplas soluções não-dominadas, precisamos de:
- Solução A: Menor custo MAS maior insatisfação
- Solução B: Maior custo MAS menor insatisfação

### Por Que Não Há Trade-offs?

1. **Custo e insatisfação estão correlacionados:**
   - Menor distância → Menor custo E menor tempo → Menor atraso → Menor insatisfação
   - Não há conflito entre objetivos

2. **Heurística não explora trade-offs:**
   - Não considera usar mais veículos para melhorar satisfação
   - Não considera rotas mais longas para respeitar janelas
   - Sempre minimiza distância (implicitamente)

3. **Resultado:**
   - Uma solução que minimiza distância também minimiza atrasos
   - Essa solução domina todas em ambos os objetivos

## Conjectura 7: Convergência para Solução "Ótima" Local

### O Que Acontece

A heurística construtiva pode estar sempre convergindo para a mesma solução "ótima" local:

1. **Estrutura de rotas fixa:**
   - Restrições forçam sempre mesma divisão de clientes
   - Sempre mesmas recargas
   - Sempre mesmas estruturas

2. **Ordem relativa fixa:**
   - Mesmo que a permutação mude, a heurística sempre escolhe ordem similar
   - Exemplo: Sempre visita clientes próximos primeiro (por causa do safety buffer)

3. **Resultado:**
   - Todas as soluções convergem para estrutura muito similar
   - Uma solução ligeiramente melhor domina todas

## Síntese das Conjecturas

### Problema Raiz

A heurística construtiva atual é:
1. **Muito determinística** - sempre faz as mesmas escolhas
2. **Muito conservadora** - não explora alternativas
3. **Muito simples** - não considera trade-offs
4. **Muito restritiva** - restrições forçam estrutura única

### Efeito Cascata

1. Restrições forçam estrutura similar → Mesmo número de veículos
2. Heurística determinística → Mesmas decisões
3. Ordem não afeta muito → Distâncias similares
4. Custo similar → f1 similar
5. Atrasos similares → Insatisfação similar (ou sempre máxima)
6. Uma solução ligeiramente melhor → Domina todas

### Resultado Final

- Não há trade-offs reais entre objetivos
- Não há diversidade suficiente
- Uma solução domina todas
- `n_nds = 1` sempre

## Implicações

### Para o Problema Multi-Objetivo

Se uma solução domina todas em ambos os objetivos:
- O problema efetivamente se torna **mono-objetivo**
- NSGA-II não consegue manter diversidade porque não há diversidade para manter
- Não há frente de Pareto real, apenas uma solução ótima

### Para a Heurística

A heurística atual:
- É adequada para encontrar uma solução
- Não é adequada para gerar diversidade
- Não explora trade-offs
- Sempre converge para soluções muito similares

## Conclusão

A dominância única provavelmente ocorre porque:

1. **A heurística é muito determinística** - sempre faz as mesmas escolhas
2. **As restrições forçam estrutura similar** - mesmo número de veículos, mesmas recargas
3. **A ordem não cria diversidade suficiente** - porque a heurística sempre escolhe as mesmas decisões
4. **Não há trade-offs reais** - uma solução que minimiza distância também minimiza atrasos
5. **Uma solução ligeiramente melhor domina todas** - porque todas são muito similares

**Resultado:** O problema multi-objetivo se torna efetivamente mono-objetivo, e não há diversidade para o NSGA-II explorar.
