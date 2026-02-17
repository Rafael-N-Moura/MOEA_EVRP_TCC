# Problema: Apenas Uma Solução na Frente de Pareto

## Situação

Ao executar o NSGA-II, apenas **1 solução** está sendo retornada na frente de Pareto, quando esperaríamos múltiplas soluções representando diferentes trade-offs entre número de veículos e distância.

## Possíveis Causas

### 1. **Convergência Prematura** (Mais Provável)

O algoritmo pode estar convergindo muito rapidamente para uma única solução dominante.

**Sintomas:**
- Apenas 1 solução após poucas gerações
- Todas as soluções da população têm valores muito similares

**Soluções:**
- **Aumentar número de gerações**: `--n-gen 100` ou mais
- **Aumentar população**: `--pop-size 100` ou mais
- **Aumentar taxa de mutação**: Modificar `mutation` no código
- **Reduzir eliminação de duplicatas**: Pode estar removendo diversidade

### 2. **Problema na Avaliação**

Todas as permutações podem estar resultando em soluções muito similares ou idênticas.

**Sintomas:**
- Todas as soluções têm exatamente os mesmos valores de f1 e f2
- Pouca variação na população

**Soluções:**
- Verificar se o decoder está gerando soluções diferentes
- Adicionar mais diversidade na população inicial
- Verificar se há um bug que faz todas as soluções serem iguais

### 3. **Configuração do Algoritmo**

A configuração atual pode estar favorecendo convergência rápida.

**Soluções:**
- Aumentar diversidade genética
- Ajustar parâmetros de crossover e mutação
- Verificar se `eliminate_duplicates=True` está removendo muita diversidade

## Soluções Recomendadas

### Solução 1: Aumentar Parâmetros de Execução

```bash
# Teste com mais gerações e população maior
python3 main.py evrptw_instances/r101_21.txt --algorithm nsga2 --n-gen 200 --pop-size 100
```

### Solução 2: Modificar Taxa de Mutação

Edite `main.py` e aumente a taxa de mutação:

```python
algorithm = NSGA2(
    pop_size=pop_size,
    sampling=PermutationRandomSampling(),
    crossover=OrderCrossover(),
    mutation=InversionMutation(prob=0.3),  # Aumentar probabilidade
    eliminate_duplicates=False  # Desabilitar para manter diversidade
)
```

### Solução 3: Verificar Diversidade das Soluções

Adicione código para verificar se as soluções estão realmente diferentes:

```python
# Após a execução, verifique:
print(f"Valores únicos de f1: {len(set(res.F[:, 0]))}")
print(f"Valores únicos de f2: {len(set(res.F[:, 1]))}")
```

### Solução 4: Usar Instância Menor para Debug

Teste com instância muito pequena para verificar se o problema é específico:

```bash
python3 main.py evrptw_instances/rc108C5.txt --algorithm nsga2 --n-gen 50 --pop-size 50
```

## Diagnóstico

Execute com verbose para ver o progresso:

```bash
python3 main.py evrptw_instances/r101_21.txt --algorithm nsga2 --n-gen 50 --pop-size 50
```

Observe:
- Se a população inicial tem diversidade
- Se a população está convergindo muito rápido
- Se há muitas soluções inviáveis sendo penalizadas

## Próximos Passos

1. **Execute com parâmetros maiores** e veja se obtém mais soluções
2. **Verifique os valores** de f1 e f2 - se forem muito similares, pode ser problema na avaliação
3. **Teste com instância menor** para isolar o problema
4. **Adicione logs** no decoder para ver se está gerando soluções diferentes

## Comandos de Teste

```bash
# Teste 1: Mais gerações
python3 main.py evrptw_instances/r101_21.txt --algorithm nsga2 --n-gen 200 --pop-size 100

# Teste 2: População maior
python3 main.py evrptw_instances/r101_21.txt --algorithm nsga2 --n-gen 100 --pop-size 200

# Teste 3: Instância menor
python3 main.py evrptw_instances/rc108C5.txt --algorithm nsga2 --n-gen 100 --pop-size 50
```

## Nota Importante

No Pymoo, `res.F` contém apenas as **soluções não-dominadas** da frente de Pareto final. Se todas as soluções convergiram para uma única solução não-dominada, você verá apenas 1 solução. Isso é normal se:

- A solução encontrada é realmente a melhor em ambos os objetivos
- O algoritmo convergiu completamente
- Há pouco trade-off entre os objetivos no problema

Mas em um problema VRP típico, **deve haver trade-off** entre número de veículos e distância, então múltiplas soluções são esperadas.
