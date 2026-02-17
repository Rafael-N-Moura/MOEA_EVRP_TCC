# Análise do Problema: Por que n_nds = 1?

## Resultados do Teste do Decoder

### Instância Pequena (5 clientes)
- **f1 (veículos)**: Sempre 1 (faz sentido - apenas 5 clientes)
- **f2 (distância)**: Varia de 286.95 a 368.09 ✅

**Conclusão**: O decoder está funcionando corretamente! Diferentes permutações geram diferentes distâncias.

## Por que n_nds = 1 então?

### Explicação: Dominância quando f1 é constante

Quando todas as soluções têm o **mesmo número de veículos (f1)**, a dominância funciona assim:

- Solução A: (f1=1, f2=300)
- Solução B: (f1=1, f2=350)
- Solução C: (f1=1, f2=280)

**Análise de dominância**:
- C domina A e B (mesmo f1, menor f2)
- A domina B (mesmo f1, menor f2)
- **Resultado**: Apenas C é não-dominada → `n_nds = 1`

### O Problema Real

Para ter múltiplas soluções não-dominadas, precisamos de **trade-offs**:
- Solução 1: (f1=2, f2=200) - Mais veículos, menos distância
- Solução 2: (f1=1, f2=300) - Menos veículos, mais distância

Essas duas soluções são **não-dominadas** entre si porque:
- Solução 1 tem mais veículos MAS menos distância
- Solução 2 tem menos veículos MAS mais distância
- Nenhuma domina a outra

## Por que não estamos vendo trade-offs?

### Hipótese 1: Instância muito pequena
- Com apenas 5 clientes, sempre precisa de 1 veículo
- Não há espaço para trade-offs

**Solução**: Testar com instância maior (100 clientes)

### Hipótese 2: Algoritmo não explora soluções com mais veículos
- O NSGA-II pode estar convergindo apenas para soluções com mínimo de veículos
- Não está explorando soluções com mais veículos mas menos distância

**Solução**: 
- Aumentar população
- Aumentar taxa de mutação
- Verificar se há bias na população inicial

### Hipótese 3: Decoder sempre minimiza veículos
- A heurística construtiva pode estar sempre tentando usar o mínimo de veículos
- Não explora soluções com mais veículos

**Solução**: Modificar decoder para permitir mais flexibilidade

## Próximos Passos

1. **Testar com instância maior** (`r101_21.txt` com 100 clientes)
   ```bash
   python3 test_decoder_larger.py
   ```

2. **Verificar se há soluções com diferentes números de veículos**
   - Se todas têm f1 igual → problema de exploração
   - Se há variação em f1 → problema pode ser no algoritmo

3. **Analisar população inicial do NSGA-II**
   - Verificar se há diversidade inicial
   - Verificar se operadores genéticos estão funcionando

4. **Adicionar logs na avaliação**
   - Ver distribuição de f1 e f2 na população
   - Identificar se há convergência prematura

## Comando para Teste

```bash
python3 test_decoder_larger.py
```

Isso testará com 100 clientes e mostrará se há variação em f1 (número de veículos).
