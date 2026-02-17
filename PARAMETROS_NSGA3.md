# Parâmetros para NSGA-III com 6 Objetivos

## Cálculo de Pontos de Referência

Para NSGA-III com **n objetivos** e **n_partitions**, o número de pontos de referência (e população) é dado por:

```
N = C(n_partitions + n_obj - 1, n_obj - 1)
```

Onde `C(n, k)` é a combinação binomial.

### Para 6 Objetivos:

| n_partitions | Fórmula | Pontos de Referência | População |
|--------------|---------|---------------------|-----------|
| 2 | C(7, 5) | 21 | 21 |
| 3 | C(8, 5) | 56 | 56 |
| **4** | **C(9, 5)** | **126** | **126** |
| 5 | C(10, 5) | 252 | 252 |
| 6 | C(11, 5) | 462 | 462 |
| 7 | C(12, 5) | 792 | 792 |

## Parâmetros Recomendados para Teste

### Teste Rápido (Validação)
```bash
python3 main.py evrptw_instances/rc208_21.txt \
    --algorithm nsga3 \
    --objectives vehicles distance duration time_window wait_time recharge_time \
    --n-gen 20 \
    --pop-size 126 \
    --n-partitions 4 \
    --no-verbose
```

**Tempo estimado:** 2-5 minutos

### Teste Realista (Benchmark)
```bash
python3 main.py evrptw_instances/rc208_21.txt \
    --algorithm nsga3 \
    --objectives vehicles distance duration time_window wait_time recharge_time \
    --n-gen 50 \
    --pop-size 126 \
    --n-partitions 4 \
    --no-verbose
```

**Tempo estimado:** 5-15 minutos

### Teste Completo (Produção)
```bash
python3 main.py evrptw_instances/rc208_21.txt \
    --algorithm nsga3 \
    --objectives vehicles distance duration time_window wait_time recharge_time \
    --n-gen 100 \
    --pop-size 126 \
    --n-partitions 4 \
    --no-verbose
```

**Tempo estimado:** 10-30 minutos

## Instâncias Disponíveis

Todas as instâncias `*_21.txt` têm **101 clientes**:
- `rc201_21.txt` até `rc208_21.txt` (instâncias RC)
- `r101_21.txt` até `r211_21.txt` (instâncias R)
- `c101_21.txt` até `c208_21.txt` (instâncias C)

## Escalabilidade

### Para 30 Execuções (Validação Estatística)

**Cenário Conservador (n_gen=50, pop=126):**
- Tempo por execução: ~10 minutos
- Tempo total: ~5 horas

**Cenário Realista (n_gen=100, pop=126):**
- Tempo por execução: ~20 minutos
- Tempo total: ~10 horas

**Cenário Completo (n_gen=200, pop=126):**
- Tempo por execução: ~40 minutos
- Tempo total: ~20 horas

### Recomendações

1. **Fase A (Validação):** Use `n_gen=20` para verificar se tudo funciona
2. **Fase B (Benchmark):** Use `n_gen=50` para medir tempo real
3. **Fase C (Produção):** Use `n_gen=100-200` dependendo do tempo disponível

## Fatores que Afetam o Tempo

1. **Número de Gerações:** Linear (2x gerações ≈ 2x tempo)
2. **Tamanho da População:** Linear (2x população ≈ 2x tempo)
3. **Número de Objetivos:** Impacto no sorting (NSGA-III é eficiente)
4. **Tamanho da Instância:** Impacto no decoder (101 clientes é médio)

## Comparação com NSGA-II

Para **2 objetivos** com NSGA-II:
- População: 100
- Tempo estimado: ~2-5 minutos (50 gerações)

Para **6 objetivos** com NSGA-III:
- População: 126
- Tempo estimado: ~10-15 minutos (50 gerações)

**Aumento:** ~3-5x mais lento (esperado para many-objective)
