# Implementação: NSGA-II com Directed Mating Focado em Bateria

## Resumo Executivo

Este documento descreve em detalhes a implementação do algoritmo **BatteryFocusedNSGA2**, uma variante do NSGA-II que utiliza **Directed Mating** para melhorar a convergência em problemas de roteamento de veículos elétricos (EVRP). A implementação preserva intencionalmente soluções inviáveis (com violação de bateria) e força acasalamento entre soluções viáveis e inviáveis para combinar viabilidade com eficiência.

---

## 1. Contexto e Motivação

### 1.1 O Problema da "Fronteira da Bateria"

No EVRP, as melhores soluções frequentemente operam no limite da capacidade da bateria:
- Uma rota que utiliza **99% da bateria** é extremamente eficiente, mas arriscada
- Uma rota que utiliza **101% da bateria** é matematicamente inviável, mas contém informações valiosas sobre a ordem ótima de visitação

### 1.2 Limitações do NSGA-II Padrão

O NSGA-II padrão trata soluções inviáveis de duas formas:
1. **Penalização/Descarte**: Soluções inviáveis são dominadas por qualquer solução viável, fazendo com que genes de rotas eficientes sejam descartados prematuramente
2. **Reparo (Decoder Seguro)**: Decoders tradicionais "consertam" a inviabilidade adicionando veículos ou recargas, transformando rotas eficientes (mas inviáveis) em rotas seguras (mas caras)

### 1.3 A Proposta: Directed Mating

A estratégia proposta:
- **Preserva intencionalmente soluções inviáveis** (aquelas com bom custo, mas bateria negativa) em um arquivo separado
- **Força acasalamento** entre soluções "seguras" (viáveis) e soluções "agressivas" (inviáveis mas eficientes)
- **Hipótese**: O cruzamento combinará a viabilidade das rotas seguras com a eficiência das rotas agressivas, convergindo mais rápido para o ótimo global

---

## 2. Componentes Implementados

### 2.1 Modificação do Decoder (`src/decoder.py`)

#### Parâmetro `force_battery_feasible`

A função `decode()` foi modificada para aceitar o parâmetro `force_battery_feasible: bool = True`:

```python
def decode(individual: List[int], context: Context, force_battery_feasible: bool = True) -> Solution:
```

**Modo True (Seguro/Máscara)**:
- Mantém a lógica atual de recarga preventiva
- Se bateria < threshold crítico (15%), retorna ao depósito e abre novo veículo
- **Resultado**: Sempre viável (G2=0), mas tende a ter custo (f1) mais alto
- **Uso**: Inicialização (Seeding) e Operadores de Reparo

**Modo False (Relaxado/Transparente)**:
- **Desativa** a verificação preventiva de retorno ao depósito por bateria crítica
- **Não retorna** ao depósito preventivamente por causa de bateria
- Continua visitando clientes até que a **Capacidade de Carga** estoure
- **Resultado**: Gera rotas com poucos veículos (ótimo f1) mas expõe a violação de bateria (G2 > 0)
- **Uso**: **Padrão durante a evolução (Problem.evaluate)**

#### Mudança Específica no Código

```python
# Antes:
if current_battery < context.battery_capacity * BATTERY_THRESHOLD_CRITICAL:
    # Retorna ao depósito...

# Depois:
if force_battery_feasible and current_battery < context.battery_capacity * BATTERY_THRESHOLD_CRITICAL:
    # Retorna ao depósito apenas se force_battery_feasible=True
```

### 2.2 Cálculo de Violação de Bateria (`src/model.py`)

#### Novo Campo na Solution

Adicionado campo `battery_violation: float = 0.0` na classe `Solution`:

```python
@dataclass
class Solution:
    # ... campos existentes ...
    battery_violation: float = 0.0  # G2: Déficit de bateria (positivo se violação, 0 se viável)
```

#### Método `calculate_battery_violation()`

Novo método que calcula o déficit de energia (G2):

```python
def calculate_battery_violation(self, context: 'Context') -> float:
    """
    Calcula a violação de bateria (G2) como déficit de energia.
    Retorna valor positivo se há violação, 0 se viável.
    """
    total_deficit = 0.0
    
    for route in self.routes:
        current_battery = context.battery_capacity
        current_position = context.depot
        
        for step in route.steps:
            # Calcula energia necessária
            distance = current_position.distance_to(step.node)
            energy_needed = distance * context.consumption_rate
            
            # Verifica violação
            if current_battery < energy_needed:
                deficit = energy_needed - current_battery
                total_deficit += deficit
                current_battery = 0.0
            else:
                current_battery -= energy_needed
            
            # Atualiza posição
            current_position = step.node
    
    self.battery_violation = total_deficit
    return total_deficit
```

**Características**:
- Percorre todas as rotas e todos os passos
- Calcula déficit de energia quando bateria < energia necessária
- Retorna soma total de déficits (valor positivo = violação, 0 = viável)

### 2.3 Modificação do Problema (`src/problem.py`)

#### Novos Parâmetros no Construtor

```python
def __init__(self, context: Context, use_constraints: bool = False, force_battery_feasible: bool = False):
    self.use_constraints = use_constraints
    self.force_battery_feasible = force_battery_feasible
    # ...
    n_constr = 2 if use_constraints else 0  # 2 restrições: G1 (carga), G2 (bateria)
```

#### Modo com Restrições

Quando `use_constraints=True`, o problema expõe violações como restrições (G):

```python
if self.use_constraints:
    # G1: Capacidade de carga (sempre 0, tratado pelo decoder)
    g1 = 0.0
    
    # G2: Violação de bateria (déficit de energia)
    g2 = solution.battery_violation
    
    out["F"] = np.array([f1, f2])
    out["G"] = np.array([g1, g2])
```

**Vantagens**:
- Permite que o algoritmo diferencie "quase viável" de "totalmente inviável"
- Soluções com G2 pequeno (violação leve) podem ser preservadas
- Soluções com G2 grande (violação grave) são descartadas

### 2.4 Algoritmo Customizado (`src/battery_focused_nsga2.py`)

#### 2.4.1 HybridSampling

Classe que gera população inicial híbrida:

```python
class HybridSampling(Sampling):
    def _do(self, problem, n_samples, **kwargs):
        # Gera permutações aleatórias
        X = self.base_sampling._do(problem, n_samples, **kwargs)
        
        # Marca primeira metade para usar force_battery_feasible=True
        n_feasible = n_samples // 2
        feasible_mask = np.zeros(n_samples, dtype=bool)
        feasible_mask[:n_feasible] = True
        
        # Armazena máscara no problema
        problem._sampling_feasible_mask = feasible_mask
        
        return X
```

**Estratégia**:
- **50% da população inicial**: Gerada com `force_battery_feasible=True` (garante viabilidade inicial)
- **50% da população inicial**: Gerada com `force_battery_feasible=False` (explora limites desde o início)

#### 2.4.2 InfeasibleSurvival

Estratégia de sobrevivência que preserva soluções inviáveis:

```python
class InfeasibleSurvival(Selection):
    def __init__(self, infeasible_ratio: float = 0.25):
        self.infeasible_ratio = infeasible_ratio  # ~20% a 30%
```

**Lógica de Seleção**:

1. **Divisão da População**:
   - **Grupo A (Viáveis)**: G2 <= 0 (respeitaram a bateria)
   - **Grupo B (Inviáveis)**: G2 > 0 (estouraram a bateria)

2. **Cota de Viáveis**:
   - Preenche com Rank & Crowding Distance (método padrão do NSGA-II)
   - Seleciona soluções não-dominadas com maior diversidade

3. **Cota de Inviáveis**:
   - Preenche com Grupo B ordenado por **menor custo (f1)**
   - Preserva soluções inviáveis mas eficientes (poucos veículos, baixa distância)

**Parâmetro `infeasible_ratio`**:
- Valor recomendado: 0.20 a 0.30 (20% a 30% da população)
- Balanceia exploração (inviáveis) com exploração (viáveis)

#### 2.4.3 DirectedMatingSelection

Estratégia de acasalamento direcionado:

```python
class DirectedMatingSelection(Selection):
    def _do(self, pop, n_select, n_parents=2, **kwargs):
        # Separa em viáveis e inviáveis
        feasible_indices = np.where(pop.get("G")[:, 1] <= 0)[0]
        infeasible_indices = np.where(pop.get("G")[:, 1] > 0)[0]
        
        selected = []
        for i in range(n_select):
            # Pai 1: Do grupo viável
            parent1_idx = np.random.choice(feasible_indices)
            
            # Pai 2: Do grupo inviável
            parent2_idx = np.random.choice(infeasible_indices)
            
            selected.append([parent1_idx, parent2_idx])
        
        return np.array(selected)
```

**Estratégia**:
- **Pai 1**: Selecionado do **Grupo A** (Viável/Seguro)
- **Pai 2**: Selecionado do **Grupo B** (Inviável/Eficiente)
- **Resultado**: Cruza rota que economiza veículos (mas falha na bateria) com rota que respeita a bateria (mas gasta mais veículos)

**Hipótese**: O cruzamento combinará:
- A **viabilidade** das rotas seguras (do Pai 1)
- A **eficiência** das rotas agressivas (do Pai 2)
- Gerando filhos que são **viáveis E eficientes**

#### 2.4.4 BatteryFocusedNSGA2

Classe principal que integra todas as estratégias:

```python
class BatteryFocusedNSGA2(NSGA2):
    def __init__(
        self,
        pop_size=100,
        infeasible_ratio=0.25,
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
        **kwargs
    ):
        # Inicializa com sampling híbrido
        self._hybrid_sampling = HybridSampling()
        self._infeasible_survival = InfeasibleSurvival(infeasible_ratio)
        self._directed_mating = DirectedMatingSelection()
        
        super().__init__(
            pop_size=pop_size,
            sampling=self._hybrid_sampling,
            crossover=crossover,
            mutation=mutation,
            **kwargs
        )
```

**Fluxo de Execução**:

1. **Inicialização (`_initialize_advance`)**:
   - Usa `HybridSampling` para gerar população inicial
   - Primeira metade avaliada com `force_battery_feasible=True`
   - Segunda metade avaliada com `force_battery_feasible=False`

2. **Avanço de Geração (`_advance`)**:
   - Durante evolução, sempre usa `force_battery_feasible=False`
   - Seleciona pais usando `DirectedMatingSelection`
   - Gera filhos via crossover e mutação
   - Aplica `InfeasibleSurvival` para manter população

---

## 3. Integração no Sistema

### 3.1 Modificações no `main.py`

#### Nova Função `run_battery_focused_nsga2()`

```python
def run_battery_focused_nsga2(problem, n_gen=100, pop_size=100, infeasible_ratio=0.25, verbose=True):
    algorithm = BatteryFocusedNSGA2(
        pop_size=pop_size,
        infeasible_ratio=infeasible_ratio,
        crossover=OrderCrossover(),
        mutation=InversionMutation()
    )
    # ... execução ...
```

#### Novo Argumento de Linha de Comando

```python
parser.add_argument(
    '--algorithm',
    type=str,
    choices=['nsga2', 'moead', 'battery-focused', 'both'],
    default='both',
    help='Algoritmo a executar. battery-focused = NSGA-II com Directed Mating'
)
```

#### Uso

```bash
python main.py evrptw_instances/rc208_21.txt --algorithm battery-focused --n-gen 100 --pop-size 100
```

### 3.2 Configuração do Problema

Para usar o algoritmo `battery-focused`, o problema deve ser criado com:

```python
problem = EVRPTWProblem(
    context,
    use_constraints=True,      # Usa restrições (G) em vez de penalização
    force_battery_feasible=False  # Permite violações durante evolução
)
```

---

## 4. Fluxo de Dados

### 4.1 Durante Inicialização

```
1. HybridSampling gera permutações aleatórias
2. Primeira metade (50%):
   - decode(individual, context, force_battery_feasible=True)
   - Resultado: Soluções viáveis (G2=0), mas com custo alto
3. Segunda metade (50%):
   - decode(individual, context, force_battery_feasible=False)
   - Resultado: Soluções inviáveis (G2>0), mas com custo baixo
```

### 4.2 Durante Evolução

```
1. DirectedMatingSelection seleciona pais:
   - Pai 1: Viável (G2 <= 0)
   - Pai 2: Inviável (G2 > 0)
2. Crossover e Mutação geram filhos
3. Filhos avaliados com force_battery_feasible=False
4. InfeasibleSurvival mantém:
   - 75% viáveis (melhores por Rank & Crowding)
   - 25% inviáveis (melhores por custo f1)
```

### 4.3 Cálculo de Violação

```
Para cada rota:
  Para cada passo:
    Se bateria_atual < energia_necessária:
      déficit = energia_necessária - bateria_atual
      total_deficit += déficit
      bateria_atual = 0.0
    Senão:
      bateria_atual -= energia_necessária

G2 = total_deficit  # Positivo = violação, 0 = viável
```

---

## 5. Comparação com NSGA-II Padrão

### 5.1 NSGA-II Padrão

- **Tratamento de Inviáveis**: Penalização alta (100000) ou descarte
- **Sampling**: 100% aleatório
- **Sobrevivência**: Apenas Rank & Crowding Distance
- **Acasalamento**: Aleatório ou por torneio
- **Resultado**: Soluções inviáveis são descartadas rapidamente

### 5.2 BatteryFocusedNSGA2

- **Tratamento de Inviáveis**: Preservação intencional (25% da população)
- **Sampling**: Híbrido (50% viável, 50% inviável)
- **Sobrevivência**: Rank & Crowding + Inviáveis por custo
- **Acasalamento**: Direcionado (viável × inviável)
- **Resultado**: Soluções inviáveis eficientes são preservadas e cruzadas com viáveis

---

## 6. Parâmetros Configuráveis

### 6.1 Parâmetros do Algoritmo

- **`pop_size`**: Tamanho da população (padrão: 100)
- **`infeasible_ratio`**: Proporção de inviáveis a preservar (padrão: 0.25 = 25%)
- **`n_gen`**: Número de gerações

### 6.2 Parâmetros do Problema

- **`use_constraints`**: Se True, usa restrições (G) em vez de penalização
- **`force_battery_feasible`**: Se True, força viabilidade no decoder

### 6.3 Parâmetros do Decoder

- **`BATTERY_THRESHOLD_PREVENTIVE`**: 30% - Recarrega preventivamente
- **`BATTERY_THRESHOLD_CRITICAL`**: 15% - Considera retornar ao depósito
- **`BATTERY_SAFETY_MARGIN`**: 20% - Margem de segurança após recarga

---

## 7. Resultados Esperados

### 7.1 Vantagens

1. **Melhor Convergência**: Acasalamento direcionado combina viabilidade com eficiência
2. **Preservação de Informação**: Soluções inviáveis eficientes não são descartadas
3. **Exploração de Limites**: Algoritmo explora fronteira da bateria desde o início
4. **Diversidade**: População mantém mix de viáveis e inviáveis

### 7.2 Trade-offs

1. **Possível Aumento de Tempo**: Mais processamento para gerenciar inviáveis
2. **Parâmetros Sensíveis**: `infeasible_ratio` precisa ser ajustado
3. **Complexidade**: Algoritmo mais complexo que NSGA-II padrão

---

## 8. Como Usar

### 8.1 Execução Básica

```bash
python main.py evrptw_instances/rc208_21.txt --algorithm battery-focused --n-gen 100 --pop-size 100
```

### 8.2 Comparação com NSGA-II Padrão

```bash
# NSGA-II Padrão
python main.py evrptw_instances/rc208_21.txt --algorithm nsga2 --n-gen 100

# Battery-Focused NSGA-II
python main.py evrptw_instances/rc208_21.txt --algorithm battery-focused --n-gen 100
```

### 8.3 Ajuste de Parâmetros

Para ajustar a proporção de inviáveis, modifique o código em `main.py`:

```python
results['battery-focused'] = run_battery_focused_nsga2(
    problem_battery,
    n_gen=args.n_gen,
    pop_size=args.pop_size,
    infeasible_ratio=0.30,  # Ajuste aqui (0.20 a 0.30 recomendado)
    verbose=not args.no_verbose
)
```

---

## 9. Validação e Testes

### 9.1 Verificação de Funcionamento

1. **Verificar se há soluções inviáveis preservadas**:
   - Durante execução, verificar estatísticas de viabilidade
   - Deve haver ~25% de soluções inviáveis na população

2. **Verificar acasalamento direcionado**:
   - Verificar se pais são selecionados de grupos diferentes
   - Pai 1 deve ser viável, Pai 2 deve ser inviável

3. **Verificar convergência**:
   - Comparar com NSGA-II padrão
   - Verificar se há melhoria na frente de Pareto

### 9.2 Métricas de Avaliação

- **Taxa de Viabilidade**: % de soluções viáveis na população final
- **Diversidade**: Número de soluções não-dominadas
- **Convergência**: Comparação com NSGA-II padrão
- **Tempo de Execução**: Comparação com NSGA-II padrão

---

## 10. Conclusão

A implementação do **BatteryFocusedNSGA2** com **Directed Mating** representa uma abordagem inovadora para lidar com restrições de bateria no EVRP. Ao preservar soluções inviáveis eficientes e forçar acasalamento com soluções viáveis, o algoritmo busca combinar o melhor dos dois mundos: viabilidade e eficiência.

A implementação está completa e pronta para uso, com todas as funcionalidades descritas no plano original implementadas e integradas no sistema existente.

---

## Referências

- Documento original: `aux/Plano de Implementação_ EVRP com Directed Mating para Bateria.md`
- Código fonte:
  - `src/decoder.py`: Decoder com modo relaxado
  - `src/model.py`: Cálculo de violação de bateria
  - `src/problem.py`: Problema com restrições
  - `src/battery_focused_nsga2.py`: Algoritmo customizado
  - `main.py`: Integração e execução
