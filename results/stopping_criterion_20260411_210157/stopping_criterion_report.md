# Relatório de Calibração do Critério de Parada

**Gerado em**: 2026-04-12T03:01:30

## Resultado Principal

**Critério de parada oficial: 1,110,000 avaliações**

- max(N*) = 920,010
- × 120% (margem de segurança) = 1,104,012
- Arredondado para múltiplo de 10,000 → **1,110,000**

## Metodologia

- **Instâncias de calibração**: c101_21, c201_21, r101_21, r201_21, rc101_21, rc201_21
- **Algoritmos**: moead_ws, nsga2, smsemoa
- **Janela móvel**: 50,000 avaliações
- **Threshold ε**: 1.0%
- **Pontos consecutivos**: 3

## Trecho para o TCC

> O critério de parada foi calibrado seguindo um procedimento formal de identificação de estabilidade do hipervolume. Para cada combinação (algoritmo, instância) em um conjunto de 6 instâncias representativas (uma por célula de tipo espacial × série — C-1xx, C-2xx, R-1xx, R-2xx, RC-1xx, RC-2xx), foram executados 5 runs com orçamento estendido. O hipervolume mediano foi calculado a cada 10,000 avaliações. Identificou-se o ponto de estabilização N*(algoritmo, instância) como o primeiro ponto onde a melhoria relativa em janela móvel de 50,000 avaliações fica abaixo de 1% e permanece abaixo nos 3 pontos subsequentes. O critério de parada global foi definido como max{N*(algoritmo, instância)} × 120%, arredondado para o múltiplo de 10,000 mais próximo, garantindo que o algoritmo mais lento na instância mais difícil tenha orçamento suficiente para convergência. O valor obtido foi **1,110,000 avaliações**.

## N* por (Algoritmo, Instância)

| Algoritmo | Instância | N* | Convergiu | HV Final |
|-----------|-----------|---:|-----------|----------|
| moead_ws | c101_21 | 650,055 | ✅ | 862956021.84 |
| moead_ws | c201_21 | 160,020 | ✅ | 1008531021.57 |
| moead_ws | r101_21 | 430,080 | ✅ | 166664273.39 |
| moead_ws | r201_21 | 370,020 | ✅ | 206630516.45 |
| moead_ws | rc101_21 | 490,035 | ✅ | 151065277.60 |
| moead_ws | rc201_21 | 440,055 | ✅ | 450892925.46 |
| nsga2 | c101_21 | 570,045 | ✅ | 1386258808.02 |
| nsga2 | c201_21 | 790,020 | ✅ | 3404735144.68 |
| nsga2 | r101_21 | 840,000 | ✅ | 187064163.09 |
| nsga2 | r201_21 | 590,100 | ✅ | 383246626.71 |
| nsga2 | rc101_21 | 920,010 | ✅ | 171338177.95 |
| nsga2 | rc201_21 | 690,060 | ✅ | 737918653.31 |
| smsemoa | c101_21 | 550,095 | ✅ | 1511663276.01 |
| smsemoa | c201_21 | 570,045 | ✅ | 3179232120.94 |
| smsemoa | r101_21 | 540,015 | ✅ | 187543974.31 |
| smsemoa | r201_21 | 530,040 | ✅ | 440952207.45 |
| smsemoa | rc101_21 | 570,045 | ✅ | 173156691.37 |
| smsemoa | rc201_21 | 620,025 | ✅ | 812040416.65 |

## Comparação Preliminar dos Algoritmos

| Instância | moead_ws | nsga2 | smsemoa | Vencedor |
|-----------|-----|-----|-----|----------|
| c101_21 | 862956021.84 | 1386258808.02 | 1511663276.01 | smsemoa |
| c201_21 | 1008531021.57 | 3404735144.68 | 3179232120.94 | nsga2 |
| r101_21 | 166664273.39 | 187064163.09 | 187543974.31 | smsemoa |
| r201_21 | 206630516.45 | 383246626.71 | 440952207.45 | smsemoa |
| rc101_21 | 151065277.60 | 171338177.95 | 173156691.37 | smsemoa |
| rc201_21 | 450892925.46 | 737918653.31 | 812040416.65 | smsemoa |

**Vitórias**: moead_ws=0, nsga2=1, smsemoa=5

## Robustez do MOEA/D-WS

- HV mediano em 6 instâncias:
  - c101_21: 862956021.84
  - c201_21: 1008531021.57
  - r101_21: 166664273.39
  - r201_21: 206630516.45
  - rc101_21: 151065277.60
  - rc201_21: 450892925.46
- Coef. de variação: 72.4%
- **Variável**: variação elevada — investigar instâncias específicas.

