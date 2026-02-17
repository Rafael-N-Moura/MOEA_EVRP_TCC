# Diagnóstico: Problema com 6 Objetivos

## Problemas Identificados

### 1. **f1 (vehicles) Constante = 100002.00**

**Sintoma:** Todas as soluções têm exatamente o mesmo valor de f1.

**Análise:**
- Valor 100002 = 2 (veículos) + 100000 (penalidade)
- Isso indica que **TODAS as soluções estão sendo marcadas como inviáveis**
- A penalidade está sendo aplicada incorretamente

### 2. **f5 e f6 com Valores Muito Altos**

**Sintoma:**
- f5 (wait_time): min=100030.66, max=100639.85
- f6 (recharge_time): min=100002.57, max=100050.34

**Análise:**
- Valores têm offset de ~100000
- Sugere que penalidade está sendo aplicada mesmo quando não deveria
- Ou há um problema no cálculo inicial desses valores

### 3. **Tempo Muito Rápido (8.79s)**

**Sintoma:** Execução muito rápida para 50 gerações com 126 indivíduos.

**Análise:**
- Se todas as soluções são inviáveis e têm valores similares
- O algoritmo não consegue diferenciar entre soluções
- Convergência prematura ou falta de diversidade

## Possíveis Causas

### Causa 1: Todas as Soluções Marcadas como Inviáveis

**Verificar:**
- Se `solution.is_feasible` está sendo marcado como `False` incorretamente
- Se há violações físicas (bateria/carga) sendo detectadas quando não deveriam
- Se o decoder está gerando soluções realmente inviáveis

**Código relevante:**
```python
# src/model.py
def add_violation(self, message: str):
    if "Bateria" in message or "carga" in message.lower():
        self.is_feasible = False
```

### Causa 2: Penalidade Aplicada Incorretamente

**Verificar:**
- Se a penalidade está sendo aplicada mesmo para soluções viáveis
- Se há um bug na verificação de `is_feasible`

**Código relevante:**
```python
# src/problem.py
if not solution.is_feasible:
    penalty = PENALTY_MULTIPLIER  # 100000
    objective_values = [v + penalty for v in objective_values]
```

### Causa 3: Problema no Cálculo Inicial

**Verificar:**
- Se `val_wait_time` e `val_recharge_time` estão sendo inicializados corretamente
- Se há um offset sendo adicionado incorretamente

## Ações Recomendadas

1. **Executar script de diagnóstico:**
   ```bash
   python3 debug_solution_6obj.py
   ```
   Isso vai mostrar:
   - Se a solução é viável
   - Valores reais das métricas (sem penalidade)
   - Se há violações sendo detectadas incorretamente

2. **Verificar se há violações:**
   - Contar quantas soluções têm `is_feasible = False`
   - Verificar quais tipos de violações estão sendo detectadas

3. **Verificar cálculo de métricas:**
   - Confirmar que `val_wait_time` e `val_recharge_time` estão sendo calculados corretamente
   - Verificar se não há offset sendo adicionado

## Próximos Passos

1. Executar diagnóstico para identificar causa raiz
2. Corrigir problema de viabilidade (se for o caso)
3. Ajustar cálculo de métricas (se necessário)
4. Re-executar teste e verificar se tempo aumenta e diversidade melhora
