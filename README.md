# MOEA-EVRPTW — TCC

Repositório do Trabalho de Conclusão de Curso (TCC) intitulado:

> **Algoritmos Evolutivos Multiobjetivo para o Problema de Roteamento de Veículos Elétricos com Janelas de Tempo**

Implementação e avaliação experimental de três algoritmos evolutivos multiobjetivo — **NSGA-II**, **MOEA/D** e **SMS-EMOA** — aplicados ao *Electric Vehicle Routing Problem with Time Windows* (EVRPTW), com instâncias benchmark de Schneider et al. (2014).

---

## Estrutura do Repositório

```
MOEA_EVRP_TCC/
├── main.py                        # Ponto de entrada rápido (execução de instância única)
├── requirements.txt               # Dependências Python
├── src/                           # Módulo principal do algoritmo
│   ├── decoder.py                 # Decodificador de permutação → rotas EVRPTW
│   ├── fixed_inversion.py         # Operador de mutação por inversão (corrigido)
│   ├── model.py                   # Estruturas de dados do problema
│   ├── parser.py                  # Leitor de instâncias .txt
│   ├── problem.py                 # Definição do problema para pymoo
│   └── sampling.py                # Amostragem inicial da população
├── scripts/                       # Scripts de experimento e análise
│   ├── main_experiment.py         # Experimento principal (36 instâncias × 3 algoritmos × 30 runs)
│   ├── experiment_io.py           # Utilitários de I/O compartilhados
│   ├── analyze.py                 # Análise estatística completa (HV, IGD+, Friedman, Wilcoxon)
│   ├── analyze_metrics.py         # Métricas auxiliares e análise de subgrupos
│   ├── convergence_log.py         # Logging de convergência durante execução
│   ├── make_plots.py              # Geração das figuras do TCC
│   ├── pilot_experiment.py        # Experimento piloto (validação inicial)
│   ├── tuning_rs.py               # Ajuste de hiperparâmetros via Random Search
│   ├── validate.py                # Validação de soluções individuais
│   └── full_validation.py         # Validação completa com auditoria
├── tests/                         # Testes de corretude
│   ├── etapas_123.py              # Testa etapas do decodificador
│   └── validate_auditor.py        # Valida o auditor de soluções
├── evrptw_instances/              # Instâncias benchmark (Schneider et al., 2014)
│   ├── readme.txt                 # Descrição do formato
│   └── *.txt                      # 93 instâncias (C1, C2, R1, R2, RC1, RC2)
├── figures/                       # Figuras de análise exploratória (Pareto 2D e 3D)
└── results/
    └── main_experiment/           # Resultados do experimento principal
        ├── all_tasks.json         # Registro completo de todas as execuções
        ├── merged_index.csv       # Índice consolidado dos resultados brutos
        ├── metrics.csv            # Métricas calculadas (HV, IGD+, Spacing, Spread)
        ├── wilcoxon_tests.csv     # Testes de Wilcoxon par-a-par
        ├── friedman_results.json  # Teste de Friedman e ranking de Nemenyi
        ├── subgroup_analysis.csv  # Análise por subgrupo (C1/C2/R1/R2/RC1/RC2)
        ├── spearman_correlations.csv # Correlações entre propriedades e métricas
        ├── ref_points.json        # Pontos de referência globais para HV e IGD+
        ├── structural_properties.csv # Propriedades estruturais das instâncias
        └── figures/               # Figuras finais usadas no TCC
            ├── best_per_objective.pdf
            ├── cd_hv.pdf
            ├── cd_igd_plus.pdf
            └── convergence_*.pdf
```

---

## Instalação

```bash
pip install -r requirements.txt
```

**Dependências principais:**
- `pymoo >= 0.6.0` — framework de otimização multiobjetivo
- `numpy >= 1.21.0`
- `matplotlib >= 3.5.0`

---

## Uso Rápido

Para executar os três algoritmos em uma instância específica:

```bash
python main.py
```

---

## Reproduzindo o Experimento Principal

O experimento principal executa NSGA-II, MOEA/D e SMS-EMOA em 36 instâncias grandes (`_21.txt`), com 30 execuções independentes cada.

```bash
# Executar o experimento (pode levar várias horas com múltiplas máquinas)
python scripts/main_experiment.py

# Calcular métricas e análise estatística
python scripts/analyze.py

# Gerar figuras
python scripts/make_plots.py
```

Os resultados brutos já estão disponíveis em `results/main_experiment/` para reproduzir apenas a análise.

---

## Instâncias

As instâncias seguem o formato de Schneider et al. (2014), disponíveis publicamente em:
https://www.eur.nl/en/ese/department-technology-and-operations-management/research/evrptw-instances

As instâncias `*_21.txt` (com 21 estações de recarga) foram utilizadas no experimento principal.

---

## Referência

> Schneider, M., Stenger, A., & Goeke, D. (2014). The electric vehicle-routing problem with time windows and recharging stations. *Transportation Science*, 48(4), 500–520.
