# Correção: Explosão Populacional no BatteryFocusedNSGA2

## Problema Identificado

A população estava crescendo de 100 para 10.000 indivíduos ao longo das gerações, causando:
- **Lentidão extrema**: Tempo de execução de 34s para 82s (e potencialmente muito pior)
- **Degradação da qualidade**: Custo aumentando de 5500 para 6900
- **Falta de pressão evolutiva**: Soluções ruins não eram eliminadas

### Causa Raiz

O método `InfeasibleSurvival._do()` estava calculando as cotas baseado no **tamanho atual da população** (`len(pop)`), não no **tamanho desejado** (`n_select`).

**Código problemático**:
```python
n = len(pop)  # ❌ ERRADO: usa tamanho atual (200 = 100 pais + 100 filhos)
n_infeasible = int(n * self.infeasible_ratio)  # 200 * 0.25 = 50
n_feasible = n - n_infeasible  # 200 - 50 = 150
```

Isso fazia com que:
- Se `pop` tinha 200 indivíduos (100 pais + 100 filhos), selecionava 150 viáveis + 50 inviáveis = 200
- A população nunca era truncada para 100
- A cada geração, a população crescia: 100 → 200 → 300 → ... → 10.000

## Solução Implementada

### Correção Principal: Cotas Baseadas em `n_select`

**Código corrigido**:
```python
# ✅ CORRETO: Cotas baseadas em n_select (tamanho desejado)
n_infeasible_target = int(n_select * self.infeasible_ratio)  # 100 * 0.25 = 25
n_feasible_target = n_select - n_infeasible_target  # 100 - 25 = 75
```

### Lógica de Corte Rígido Implementada

A nova implementação segue rigorosamente os passos descritos no documento de diagnóstico:

#### Passo 1: Seleção de Viáveis (Rank & Crowding Distance)
- Aplica non-dominated sorting
- Ordena por rank e crowding distance
- **CORTE RÍGIDO**: Seleciona no máximo `n_feasible_target` (75)
- Se há menos viáveis que a cota, ajusta cota de inviáveis

#### Passo 2: Seleção de Inviáveis (Elite por Custo f1)
- Ordena inviáveis por menor custo (f1)
- **CORTE RÍGIDO**: Seleciona no máximo `n_infeasible_target` (25)
- Justificativa: Apenas soluções inviáveis **baratas** são úteis geneticamente

#### Passo 3 e 4: Completar se Necessário
- Se ainda faltam indivíduos, completa com viáveis restantes
- Se ainda faltam, completa com inviáveis restantes

#### Verificação de Segurança Final
- Garante que exatamente `n_select` indivíduos sejam retornados
- Se por algum motivo ainda faltam, completa aleatoriamente (fallback)
- Se selecionou mais que `n_select`, trunca

### Código Completo

```python
def _do(self, pop, n_select, n_parents=1, **kwargs):
    """
    Seleciona exatamente n_select indivíduos da população combinada (pais + filhos).
    
    Implementa lógica de cotas rígidas:
    - Cota inviável: n_select * infeasible_ratio
    - Cota viável: n_select - cota_inviável
    
    Garante que exatamente n_select indivíduos sejam retornados (corte rígido).
    """
    # CRÍTICO: Cotas baseadas em n_select (tamanho desejado), não em len(pop)
    n_infeasible_target = int(n_select * self.infeasible_ratio)
    n_feasible_target = n_select - n_infeasible_target
    
    # Separa em viáveis e inviáveis
    feasible_mask = pop.get("G")[:, 1] <= 0
    feasible_indices = np.where(feasible_mask)[0]
    infeasible_indices = np.where(~feasible_mask)[0]
    
    selected = []
    
    # PASSO 1: Seleção de Viáveis (Rank & Crowding Distance)
    if len(feasible_indices) > 0:
        # ... non-dominated sorting e ordenação por crowding distance ...
        n_select_feasible = min(n_feasible_target, len(feasible_sorted))
        selected_feasible = feasible_indices[feasible_sorted[:n_select_feasible]]
        selected.extend(selected_feasible.tolist())
        
        # Ajusta cota de inviáveis se necessário
        if n_select_feasible < n_feasible_target:
            n_infeasible_target = n_select - len(selected)
    
    # PASSO 2: Seleção de Inviáveis (Elite por Custo f1)
    if len(infeasible_indices) > 0 and len(selected) < n_select:
        f1_values = infeasible_pop.get("F")[:, 0]
        infeasible_sorted = infeasible_indices[np.argsort(f1_values)]
        n_select_infeasible = min(n_infeasible_target, len(infeasible_sorted), n_select - len(selected))
        selected.extend(infeasible_sorted[:n_select_infeasible].tolist())
    
    # PASSO 3 e 4: Completar se necessário
    # ... (código de fallback) ...
    
    # VERIFICAÇÃO FINAL: Garante exatamente n_select
    assert len(selected) == n_select
    
    return selected
```

## Resultados Esperados

Após a correção, esperamos observar:

1. **Tamanho da população final**: Exatamente 100 (não mais 10.000)
2. **Tempo de execução**: Redução de 82s para ~40-50s (aproximando-se do NSGA-II padrão)
3. **Qualidade da solução**: Custo (f1) deve melhorar significativamente
4. **Pressão evolutiva**: Soluções ruins são eliminadas a cada geração
5. **Convergência**: Curva de hipervolume ascendente consistente

## Verificação

Para verificar se a correção funcionou, execute:

```bash
python main.py evrptw_instances/rc208_21.txt --algorithm battery-focused --n-gen 100 --pop-size 100
```

**Verifique nos logs**:
- "Tamanho da população final: 100" (não mais 10.000)
- Tempo de execução reduzido
- Custo (f1) melhorado

## Lições Aprendidas

1. **Contrato de Sobrevivência**: O operador de sobrevivência DEVE retornar exatamente `n_select` indivíduos
2. **Cotas Baseadas em Tamanho Desejado**: Sempre calcular cotas baseado em `n_select`, não em `len(pop)`
3. **Corte Rígido**: Implementar verificação final para garantir que exatamente `n_select` seja retornado
4. **Pressão Evolutiva**: Sem eliminação de soluções ruins, o algoritmo degenera para busca aleatória

## Próximos Passos

1. Testar a correção e verificar resultados
2. Comparar qualidade das soluções com NSGA-II padrão
3. Medir convergência (hipervolume ao longo das gerações)
4. Se necessário, ajustar `infeasible_ratio` para otimizar trade-off
