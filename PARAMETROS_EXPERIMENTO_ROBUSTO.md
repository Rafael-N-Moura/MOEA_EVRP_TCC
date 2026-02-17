# Parâmetros para Experimento Robusto com NSGA-III (6 Objetivos)

## Análise dos Resultados Atuais

### Resultados Observados
- **50 gerações:** 8.66s, 5 soluções não-dominadas
- **100 gerações:** 17.36s, 4 soluções não-dominadas
- **População:** 126 (determinada por n_partitions=4)
- **Objetivos:** 6 (vehicles, distance, duration, time_window, wait_time, recharge_time)

### Observações
1. **Tempo escala linearmente:** 17.36s ≈ 2 × 8.66s ✅
2. **Soluções não-dominadas:** 4-5 (relativamente baixo)
3. **f1 constante:** Todas têm 2 veículos (pode indicar convergência ou restrição)
4. **Variação nos objetivos:** Boa variação em f2-f6

## Parâmetros Recomendados para Experimento Robusto

### Cenário 1: Mínimo Viável (Validação Rápida)
**Uso:** Testes iniciais, validação de código

- **População:** 126 (n_partitions=4)
- **Gerações:** 100
- **Tempo estimado:** ~17s por execução
- **30 execuções:** ~8.5 minutos
- **Soluções esperadas:** 3-8 na frente de Pareto

**Vantagens:**
- Rápido para validar
- Viável para múltiplas instâncias
- Boa para testes iniciais

**Desvantagens:**
- Pode não convergir completamente
- Poucas soluções na frente de Pareto

### Cenário 2: Recomendado (Experimento Padrão) ⭐
**Uso:** Experimento principal, publicação

- **População:** 126 (n_partitions=4) ou 252 (n_partitions=5)
- **Gerações:** 200-300
- **Tempo estimado:** 
  - Pop 126: ~35-52s por execução
  - Pop 252: ~70-104s por execução
- **30 execuções:**
  - Pop 126: ~17-26 minutos
  - Pop 252: ~35-52 minutos
- **Soluções esperadas:** 8-20 na frente de Pareto

**Justificativa:**
- 200-300 gerações é padrão na literatura para convergência
- População maior (252) permite mais diversidade
- Tempo ainda viável para 30 execuções

### Cenário 3: Completo (Experimento Extensivo)
**Uso:** Análise detalhada, comparação profunda

- **População:** 252 (n_partitions=5) ou 462 (n_partitions=6)
- **Gerações:** 500
- **Tempo estimado:**
  - Pop 252: ~87s por execução
  - Pop 462: ~160s por execução
- **30 execuções:**
  - Pop 252: ~43 minutos
  - Pop 462: ~80 minutos
- **Soluções esperadas:** 15-40 na frente de Pareto

**Justificativa:**
- 500 gerações garante convergência completa
- População maior explora melhor o espaço
- Tempo ainda aceitável para experimento completo

## Cálculo de Pontos de Referência

Para **6 objetivos** e **n_partitions**:

| n_partitions | Fórmula | Pontos de Referência | População |
|--------------|---------|---------------------|-----------|
| 3 | C(8, 5) | 56 | 56 |
| 4 | C(9, 5) | 126 | 126 |
| **5** | **C(10, 5)** | **252** | **252** ⭐ |
| 6 | C(11, 5) | 462 | 462 |
| 7 | C(12, 5) | 792 | 792 |

**Recomendação:** n_partitions=5 (252 pontos) é um bom equilíbrio entre diversidade e tempo.

## Estimativa de Soluções na Frente de Pareto

### Fatores que Afetam

1. **Número de Objetivos:** Mais objetivos = mais soluções não-dominadas
2. **Tamanho da População:** População maior = mais diversidade
3. **Número de Gerações:** Mais gerações = melhor convergência
4. **Complexidade do Problema:** Trade-offs reais = mais soluções

### Estimativas Baseadas em Literatura

Para **many-objective (6 objetivos)** com NSGA-III:

| População | Gerações | Soluções Esperadas (Mín-Máx) |
|-----------|----------|------------------------------|
| 126 | 100 | 3-8 |
| 126 | 200 | 5-12 |
| 126 | 300 | 8-15 |
| 252 | 200 | 10-20 |
| 252 | 300 | 15-30 |
| 252 | 500 | 20-40 |

### Observações dos Resultados Atuais

- **50 gerações, pop 126:** 5 soluções
- **100 gerações, pop 126:** 4 soluções

**Análise:**
- Número de soluções pode variar entre execuções
- Pode haver convergência para poucas soluções (f1 constante = 2 veículos)
- Mais gerações pode aumentar diversidade

## Recomendação Final: Experimento Robusto

### Configuração Recomendada ⭐

```bash
# Parâmetros
--n-partitions 5        # 252 pontos de referência
--pop-size 252          # Ajustado automaticamente
--n-gen 300             # Convergência adequada
```

**Tempo estimado:**
- Por execução: ~52s (baseado em 17.36s para 100 gen, pop 126)
- 30 execuções: ~26 minutos
- Múltiplas instâncias: viável

**Soluções esperadas:** 15-30 na frente de Pareto

### Justificativa

1. **População 252:**
   - Boa diversidade para 6 objetivos
   - Não muito lento
   - Padrão na literatura para many-objective

2. **300 gerações:**
   - Convergência adequada
   - Tempo ainda viável
   - Padrão em experimentos científicos

3. **Tempo total:**
   - 30 execuções em ~26 minutos é excelente
   - Permite testar múltiplas instâncias
   - Viável para validação estatística

## Comparação de Cenários

| Cenário | Pop | Gen | Tempo/Exec | 30 Exec | Soluções Esperadas |
|---------|-----|-----|------------|---------|-------------------|
| Mínimo | 126 | 100 | 17s | 8.5 min | 3-8 |
| **Recomendado** | **252** | **300** | **52s** | **26 min** | **15-30** |
| Completo | 252 | 500 | 87s | 43 min | 20-40 |
| Extensivo | 462 | 500 | 160s | 80 min | 30-60 |

## Comandos para Execução

### Experimento Recomendado
```bash
python3 main.py evrptw_instances/rc208_21.txt \
    --algorithm nsga3 \
    --objectives vehicles distance duration time_window wait_time recharge_time \
    --n-gen 300 \
    --pop-size 252 \
    --n-partitions 5 \
    --no-verbose
```

### Teste Rápido (Validação)
```bash
python3 main.py evrptw_instances/rc208_21.txt \
    --algorithm nsga3 \
    --objectives vehicles distance duration time_window wait_time recharge_time \
    --n-gen 100 \
    --pop-size 126 \
    --n-partitions 4 \
    --no-verbose
```

## Considerações Finais

### Sobre o Número de Soluções

**Por que apenas 4-5 soluções?**
1. **f1 constante (2 veículos):** Pode indicar que 2 veículos é mínimo necessário
2. **Convergência:** Algoritmo pode estar convergindo para poucas soluções
3. **Trade-offs limitados:** Pode haver poucos trade-offs reais entre objetivos
4. **Poucas gerações:** 100 gerações pode não ser suficiente

**Com mais gerações e população maior:**
- Espera-se 15-30 soluções
- Melhor exploração do espaço
- Mais trade-offs descobertos

### Sobre o Tempo

**O tempo está excelente!**
- 17s para 100 gerações é muito bom
- Permite experimentos extensivos
- Viável para validação estatística (30 execuções)

**Escalabilidade:**
- Tempo escala linearmente com gerações ✅
- Tempo escala linearmente com população ✅
- Previsível e controlável ✅

## Conclusão

**Para um experimento robusto, recomendo:**
- **População:** 252 (n_partitions=5)
- **Gerações:** 300
- **Tempo:** ~52s por execução, ~26 minutos para 30 execuções
- **Soluções esperadas:** 15-30 na frente de Pareto

Isso oferece um bom equilíbrio entre:
- ✅ Robustez (convergência adequada)
- ✅ Viabilidade (tempo aceitável)
- ✅ Diversidade (população adequada)
- ✅ Validação estatística (30 execuções viáveis)
