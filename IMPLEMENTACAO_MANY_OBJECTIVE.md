# Implementação: Many-Objective (6 Objetivos)

**Data:** 12 de Fevereiro de 2025  
**Status:** ✅ Implementação Completa

## Resumo

Implementação completa da adaptação do sistema EVRPTW-PR de bi-objetivo para many-objective (6 objetivos atômicos), conforme plano de adaptação.

## Mudanças Implementadas

### 1. **src/model.py** ✅

#### RouteStep
- **Adicionado:** `wait_time: float = 0.0` - Tempo de espera (f5)
- **Adicionado:** `recharge_time: float = 0.0` - Tempo de recarga (f6)
- **Adicionado:** `time_window_violation: float = 0.0` - Violação de janela (f4)

#### Solution
- **Adicionados 6 campos atômicos:**
  - `val_vehicles: int = 0` - f1: Número de Veículos (K)
  - `val_distance: float = 0.0` - f2: Distância Total (D)
  - `val_duration: float = 0.0` - f3: Duração Total (T)
  - `val_time_window_violation: float = 0.0` - f4: Violação de Janelas (Tw)
  - `val_wait_time: float = 0.0` - f5: Tempo de Espera (W)
  - `val_recharge_time: float = 0.0` - f6: Tempo de Recarga (Rc)

- **Novo método:** `calculate_all_objectives(context)` - Calcula todos os 6 objetivos granulares

- **Mantido:** Métricas agregadas (`total_cost`, `avg_dissatisfaction`) para compatibilidade

### 2. **src/decoder.py** ✅

#### Atualizações
- **Cálculo de wait_time:** Rastreia tempo de espera quando `arrival_time < ready_time`
- **Cálculo de time_window_violation:** Calcula atraso quando `arrival_time > due_date`
- **Cálculo de recharge_time:** Rastreia tempo de recarga em estações
- **Todos os RouteStep criados** agora incluem os novos campos

#### Mudança Principal
- Substituído `solution.calculate_objectives(context)` por `solution.calculate_all_objectives(context)`

### 3. **src/problem.py** ✅

#### Nova Classe: EVRPFlexProblem
- **Seleção dinâmica de objetivos:** Construtor recebe `objectives: List[str]`
- **Objetivos válidos:** `['vehicles', 'distance', 'duration', 'time_window', 'wait_time', 'recharge_time']`
- **Mapeamento:** `OBJECTIVE_MAP` mapeia nomes para atributos da Solution
- **Avaliação dinâmica:** `_evaluate()` monta vetor de objetivos baseado na lista fornecida

#### Classe Mantida: EVRPTWProblem
- **Compatibilidade:** Mantida para código antigo
- **Herda de EVRPFlexProblem:** Usa objetivos básicos (vehicles, distance)

### 4. **src/__init__.py** ✅

- **Exportado:** `EVRPFlexProblem`, `OBJECTIVE_MAP`, `PENALTY_MULTIPLIER`
- **Mantido:** `EVRPTWProblem` para compatibilidade

### 5. **main.py** ✅

#### Nova Função: run_nsga3()
- Implementa NSGA-III para many-objective
- Usa `get_reference_directions` com método Das-Dennis
- Ajusta `pop_size` automaticamente para corresponder aos pontos de referência

#### Atualizações
- **Novo argumento:** `--objectives` - Permite selecionar quais objetivos usar
- **Novo algoritmo:** `--algorithm nsga3` - Executa NSGA-III
- **Avisos:** Alerta quando NSGA-II é usado com >3 objetivos
- **Visualização:** Suporta apenas 2-3 objetivos (aviso para >3)

## Estrutura dos 6 Objetivos

| Objetivo | Nome            | Atributo                    | Descrição                         |
| -------- | --------------- | --------------------------- | --------------------------------- |
| f1       | `vehicles`      | `val_vehicles`              | Número de Veículos (K)            |
| f2       | `distance`      | `val_distance`              | Distância Total Percorrida (D)    |
| f3       | `duration`      | `val_duration`              | Duração Total das Rotas (T)       |
| f4       | `time_window`   | `val_time_window_violation` | Violação de Janelas de Tempo (Tw) |
| f5       | `wait_time`     | `val_wait_time`             | Tempo de Espera (W)               |
| f6       | `recharge_time` | `val_recharge_time`         | Tempo de Recarga (Rc)             |

## Exemplos de Uso

### Cenário Clássico (2 Objetivos)
```bash
python3 main.py evrptw_instances/r101_21.txt \
    --algorithm nsga2 \
    --n-gen 100 \
    --pop-size 100
```

### Cenário Serviço (3 Objetivos)
```bash
python3 main.py evrptw_instances/r101_21.txt \
    --algorithm nsga2 \
    --objectives vehicles distance time_window \
    --n-gen 100 \
    --pop-size 100
```

### Cenário Many-Objective (6 Objetivos)
```bash
python3 main.py evrptw_instances/r101_21.txt \
    --algorithm nsga3 \
    --objectives vehicles distance duration time_window wait_time recharge_time \
    --n-gen 100 \
    --pop-size 100 \
    --n-partitions 12
```

### Usando Todos os 6 Objetivos (Padrão)
```bash
python3 main.py evrptw_instances/r101_21.txt \
    --algorithm nsga3 \
    --n-gen 100 \
    --pop-size 100
```

## Compatibilidade

- ✅ **Código antigo funciona:** `EVRPTWProblem` mantido
- ✅ **Métricas agregadas mantidas:** `total_cost`, `avg_dissatisfaction`
- ✅ **API consistente:** Mesma interface, novos recursos opcionais

## Próximos Passos

1. **Fase A: Validação de Código**
   - Testar com instância pequena (c101)
   - Verificar se todas as 6 métricas são calculadas corretamente

2. **Fase B: Teste de Carga**
   - Comparar tempo NSGA-II (2 obj) vs NSGA-III (6 obj)
   - Avaliar viabilidade de 30 execuções

3. **Fase C: Execução Final**
   - Cenário Clássico (2 obj): NSGA-II vs MOEA/D
   - Cenário Serviço (3 obj): NSGA-II vs MOEA/D
   - Cenário Many-Obj (6 obj): NSGA-III vs MOEA/D

## Notas Técnicas

### Cálculo de Duração (f3)
- Soma de: tempo de viagem + tempo de serviço + tempo de espera + tempo de recarga
- Para cada step: `departure_time - arrival_time`
- Para cada transição: `arrival_time[next] - departure_time[prev]`

### Cálculo de Violação de Janela (f4)
- Soma de todos os atrasos: `max(0, arrival_time - due_date)`
- Calculado durante decodificação

### Cálculo de Tempo de Espera (f5)
- Soma de: `max(0, ready_time - arrival_time_raw)`
- Calculado quando veículo chega antes de `ready_time`

### Cálculo de Tempo de Recarga (f6)
- Soma de: `recharge_amount * recharge_rate`
- Calculado durante visita a estações

## Status das Tarefas

- ✅ Atualizar Solution em model.py
- ✅ Atualizar RouteStep
- ✅ Atualizar decoder.py
- ✅ Criar EVRPFlexProblem
- ✅ Atualizar main.py com NSGA-III
- ⏳ Criar runner.py (opcional, para experimentos estruturados)
