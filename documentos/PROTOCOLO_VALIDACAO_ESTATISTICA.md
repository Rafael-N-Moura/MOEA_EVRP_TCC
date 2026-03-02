# **Protocolo de Validação Estatística: NSGA-II vs BatteryFocused**

## **1. Configuração do Experimento (Setup)**

O objetivo é comparar a robustez e a qualidade de convergência dos dois algoritmos sob restrições severas.

* **Instância:** `evrptw_instances/rc208_21.txt` (Solomon modificada).
* **Restrição de Bateria:** Capacidade **100.0** (cenário tight). O valor é lido do próprio arquivo da instância (linha `Q Vehicle fuel tank capacity /100/`). Opcionalmente pode-se sobrescrever em `run_batch.py` via `BATTERY_CAPACITY_OVERRIDE`.
* **Parâmetros Genéticos:**
  * População: 100  
  * Gerações: 100  
  * **Baseline (NSGA-II):** `use_constraints=False`, `force_battery_feasible=True` (decoder sempre viável).  
  * **Proposta (BatteryFocusedNSGA2):** `use_constraints=True`, `force_battery_feasible=False`; sampling híbrido (50% viável / 50% inviável na inicialização); reparo dinâmico ~50% dos filhos com `force_battery_feasible=True`; sobrevivência de inviáveis por Shadow Cost; directed mating.
* **Sementes (Seeds):** 30 execuções independentes com seeds 0 a 29 (recomendado para o TCC). Para testes rápidos use `--runs 10` ou `--runs 2`.

## **2. Métricas de Avaliação**

Para cada execução *i*, são coletadas:

### **2.1. Métricas de Performance (Negócio)**

1. **Melhor Custo (f1):** Menor custo operacional entre as soluções **viáveis** (CV ≤ 0 e G ≤ tol).
2. **Número de Veículos:** Quantidade de veículos da solução de menor custo viável (obtida decodificando o genótipo X da melhor solução viável).
3. **Taxa de Sucesso (Success):** O algoritmo encontrou *pelo menos uma* solução viável na frente final? (1 = sim, 0 = não).

### **2.2. Métricas de Otimização (Ciência)**

1. **Hipervolume (HV) normalizado:**  
   * Ideal e Nadir globais calculados sobre **todas** as soluções viáveis das 2×N_RUNS execuções (baseline + proposta).  
   * Objetivos normalizados: `(F - ideal) / (nadir - ideal)` (evitando divisão por zero).  
   * Ponto de referência para HV: `[1.1, 1.1]` no espaço normalizado.  
   * Assim o HV é comparável entre execuções.

### **2.3. Métricas Extras (Implementação Atual)**

4. **Tamanho da frente viável (N_feasible):** Número de soluções viáveis na frente de Pareto final por execução (diversidade/robustez da frente).  
5. **Estatísticas descritivas:** Para f1 e HV: média, desvio padrão, min e max por algoritmo.

## **3. Tratamento Estatístico**

1. **Estatística descritiva:** Média, desvio padrão, melhor e pior caso para f1, HV e (quando aplicável) número de veículos.  
2. **Teste de hipótese (Wilcoxon Rank-Sum / ranksums):**  
   * Distribuições de resultados de algoritmos evolutivos em geral não são normais; usa-se teste não paramétrico.  
   * **p-value < 0.05:** diferença estatisticamente significativa (95% de confiança).  
   * Para **f1:** menor é melhor → proposta melhor se média(proposta) < média(baseline) e p < 0.05.  
   * Para **HV:** maior é melhor → proposta melhor se média(proposta) > média(baseline) e p < 0.05.

## **4. Script de Automação: `run_batch.py`**

O script na raiz do projeto (`run_batch.py`) executa as N_RUNS rodadas (NSGA-II e BatteryFocusedNSGA2 com o mesmo seed), extrai as frentes viáveis de `res.opt` (ou `res.pop`), calcula HV global normalizado, melhor f1, número de veículos e taxa de sucesso, aplica Wilcoxon e gera o relatório.

**Uso:**

```bash
# 30 execuções (recomendado para validação final), com HV
python run_batch.py --runs 30

# Instância e número de runs customizados
python run_batch.py --instance evrptw_instances/rc208_21.txt --runs 30

# Teste rápido sem Hipervolume (útil se pymoo.indicators.hv não estiver disponível)
python run_batch.py --runs 10 --no-hv

# Saída verbosa (inclui logs dos algoritmos)
python run_batch.py --runs 2 --verbose
```

**Configurações no script:**

* `INSTANCE_PATH_DEFAULT`: `evrptw_instances/rc208_21.txt`  
* `N_RUNS_DEFAULT`: 30  
* `POP_SIZE`: 100, `N_GEN`: 100  
* `BATTERY_CAPACITY_OVERRIDE`: `None` (usa o valor do arquivo); pode ser definido, e.g. `100.0`, para forçar capacidade.

**Saída:**

* Relatório no terminal: taxa de sucesso, melhor custo (f1), número de veículos, HV (se ativado), tamanho médio da frente viável e resultado do Wilcoxon para f1 e HV.  
* CSV: `resultados_validacao_estatistica.csv` com colunas por run: `Run`, `Seed`, `Best_f1_Base`, `Best_f1_Prop`, `N_vehicles_Base`, `N_vehicles_Prop`, `Success_Base`, `Success_Prop`, `N_feasible_Base`, `N_feasible_Prop`, `HV_Base`, `HV_Prop`.

**Implementação (resumo):**

* **Carregamento:** `parse_instance(instance_path)` (módulo `src`).  
* **Baseline:** `EVRPTWProblem(context, use_constraints=False, force_battery_feasible=True)` + `NSGA2` com `OrderCrossover`, `InversionMutation`, `PermutationRandomSampling`.  
* **Proposta:** `EVRPTWProblem(context, use_constraints=True, force_battery_feasible=False)` + `BatteryFocusedNSGA2` com `infeasible_ratio=0.25`, mesmos crossover e mutação.  
* **Viabilidade:** Frente viável extraída de `res.opt` (ou `res.pop`) com máscara `CV ≤ 0` e `G ≤ 1e-5`.  
* **Número de veículos:** Decodificação do genótipo X da solução de menor f1 viável com `decode(..., force_battery_feasible=True)` e `len(solution.routes)`.

Com isso, a validação estatística fica alinhada ao protocolo e à implementação atual do projeto (instância rc208_21 com bateria 100, métricas de negócio e de otimização, Wilcoxon e CSV de resultados).
