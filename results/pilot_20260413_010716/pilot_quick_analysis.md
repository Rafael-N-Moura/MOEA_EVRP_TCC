# Análise Rápida do Experimento Piloto
**Gerado em**: 2026-04-13T07:29:38
**Algoritmos**: nsga2, moead_ws, smsemoa
**Instâncias**: c101_21, c104_21, r110_21, r201_21

## HV Mediano (+ IQR)
| Instância | nsga2 med (IQR) | moead_ws med (IQR) | smsemoa med (IQR) | Vencedor |
|---|---|---|---|---|
| c101_21 | 1579570750 (228181900) | 909984292 (150324770) | 1591358833 (164850757) | smsemoa |
| c104_21 | 460976292 (27179390) | 338893787 (49265523) | 443033818 (41173282) | nsga2 |
| r110_21 | 17413258 (2029431) | 14736880 (2408258) | 17552451 (1056860) | smsemoa |
| r201_21 | 523268230 (64305606) | 217666000 (52545238) | 531154229 (23939151) | smsemoa |

**Vitórias**: nsga2=1, moead_ws=0, smsemoa=3

## IGD+ Mediano (+ IQR)
> Menor é melhor.

| Instância | nsga2 med (IQR) | moead_ws med (IQR) | smsemoa med (IQR) | Vencedor |
|---|---|---|---|---|
| c101_21 | 403.95 (281.41) | 1036.86 (307.41) | 324.84 (305.21) | smsemoa |
| c104_21 | 178.50 (103.60) | 288.10 (115.41) | 98.13 (120.76) | smsemoa |
| r110_21 | 88.27 (53.19) | 129.40 (68.51) | 69.23 (43.14) | smsemoa |
| r201_21 | 389.19 (228.90) | 604.90 (289.11) | 275.31 (133.13) | smsemoa |

**Vitórias**: nsga2=0, moead_ws=0, smsemoa=4

## Tamanho da Frente e Diversidade
| Instância | Algoritmo | n_pareto med | n_f1_layers med |
|---|---|---|---|
| c101_21 | nsga2 | 91.5 | 10.5 |
| c101_21 | moead_ws | 68.0 | 5.0 |
| c101_21 | smsemoa | 94.5 | 8.0 |
| c104_21 | nsga2 | 79.0 | 7.0 |
| c104_21 | moead_ws | 45.5 | 4.5 |
| c104_21 | smsemoa | 82.0 | 6.0 |
| r110_21 | nsga2 | 70.5 | 7.0 |
| r110_21 | moead_ws | 70.5 | 7.0 |
| r110_21 | smsemoa | 70.0 | 7.0 |
| r201_21 | nsga2 | 105.0 | 7.0 |
| r201_21 | moead_ws | 58.0 | 4.0 |
| r201_21 | smsemoa | 105.0 | 6.0 |

## Wilcoxon Signed-Rank (bilateral, α=0.05)
> Comparação de HV mediano por instância.
> p < 0.05 → diferença estatisticamente significativa.

| Instância | Par | p-valor | Significativo? |
|---|---|---|---|
| c101_21 | smsemoa vs nsga2 | 0.8457 | ❌ |
| c101_21 | smsemoa vs moead_ws | 0.0020 | ✅ |
| c101_21 | nsga2 vs moead_ws | 0.0020 | ✅ |
| c104_21 | smsemoa vs nsga2 | 0.7695 | ❌ |
| c104_21 | smsemoa vs moead_ws | 0.0020 | ✅ |
| c104_21 | nsga2 vs moead_ws | 0.0020 | ✅ |
| r110_21 | smsemoa vs nsga2 | 0.2754 | ❌ |
| r110_21 | smsemoa vs moead_ws | 0.0039 | ✅ |
| r110_21 | nsga2 vs moead_ws | 0.0098 | ✅ |
| r201_21 | smsemoa vs nsga2 | 0.4922 | ❌ |
| r201_21 | smsemoa vs moead_ws | 0.0020 | ✅ |
| r201_21 | nsga2 vs moead_ws | 0.0020 | ✅ |

## Tempo por Run
- Mediana: **30.9 min** (1855s)
- Mín: 20.3 min  |  Máx: 46.3 min
- Estimativa experimento principal (56inst × 3alg × 30runs ÷ 10workers): **~260h**
