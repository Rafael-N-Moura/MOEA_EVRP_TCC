# Guia de Execução - Primeiros Passos

## Passo 1: Instalar Dependências

Execute no terminal:

```bash
cd /Users/rafaelmoura/MOEA_EVRP_TCC
pip3 install -r requirements.txt
```

Ou, se preferir usar um ambiente virtual (recomendado):

```bash
python3 -m venv venv
source venv/bin/activate  # No macOS/Linux
pip install -r requirements.txt
```

## Passo 2: Testar o Parser (Opcional)

Para verificar se o parser está funcionando corretamente:

```bash
python3 -c "from src import parse_instance; ctx = parse_instance('evrptw_instances/r101_21.txt'); print(f'Clientes: {len(ctx.customers)}, Estações: {len(ctx.stations)}')"
```

## Passo 3: Executar com uma Instância Pequena (Teste Rápido)

Para um teste rápido, use uma instância pequena:

```bash
python3 main.py evrptw_instances/rc108C5.txt --algorithm nsga2 --n-gen 20 --pop-size 30 --no-verbose
```

**Instâncias recomendadas para teste:**
- `rc108C5.txt` - Muito pequena (5 clientes) - Teste rápido
- `r101_21.txt` - Pequena (100 clientes) - Teste médio
- `c101_21.txt` - Pequena (100 clientes) - Teste médio

## Passo 4: Executar Comparação Completa

Para comparar ambos os algoritmos:

```bash
python3 main.py evrptw_instances/r101_21.txt --algorithm both --n-gen 50 --pop-size 50 --plot
```

## Passos Detalhados

### Opção A: Teste Rápido (Instância Pequena)

```bash
# 1. Instalar dependências
pip3 install -r requirements.txt

# 2. Executar NSGA-II com instância pequena
python3 main.py evrptw_instances/rc108C5.txt --algorithm nsga2 --n-gen 20 --pop-size 30

# 3. Ver resultados
# O sistema exibirá:
# - Tempo de execução
# - Número de soluções encontradas
# - Melhor f1 (veículos)
# - Melhor f2 (distância)
```

### Opção B: Teste Completo (Comparação)

```bash
# 1. Instalar dependências
pip3 install -r requirements.txt

# 2. Executar ambos algoritmos
python3 main.py evrptw_instances/r101_21.txt --algorithm both --n-gen 100 --pop-size 100 --plot

# 3. Analisar gráfico de frente de Pareto (se --plot foi usado)
```

## Parâmetros Disponíveis

- `instance`: Caminho para arquivo de instância (obrigatório)
- `--algorithm`: Escolha 'nsga2', 'moead' ou 'both' (default: both)
- `--n-gen`: Número de gerações (default: 100)
- `--pop-size`: Tamanho da população (default: 100)
- `--n-partitions`: Partições para MOEA/D (default: 99)
- `--no-verbose`: Desabilita saída detalhada durante execução
- `--plot`: Gera gráfico de frente de Pareto

## Exemplos de Comandos

### Teste Muito Rápido (5 minutos)
```bash
python3 main.py evrptw_instances/rc108C5.txt --algorithm nsga2 --n-gen 10 --pop-size 20 --no-verbose
```

### Teste Rápido (15-30 minutos)
```bash
python3 main.py evrptw_instances/r101_21.txt --algorithm nsga2 --n-gen 50 --pop-size 50
```

### Execução Completa (1-2 horas)
```bash
python3 main.py evrptw_instances/r101_21.txt --algorithm both --n-gen 200 --pop-size 100 --plot
```

## Solução de Problemas

### Erro: "ModuleNotFoundError: No module named 'pymoo'"
**Solução**: Execute `pip3 install -r requirements.txt`

### Erro: "Depósito não encontrado no arquivo"
**Solução**: Verifique se o arquivo de instância está no formato correto

### Erro: "Permission denied" ao instalar
**Solução**: Use `pip3 install --user -r requirements.txt` ou crie um ambiente virtual

## Próximos Passos

Após executar com sucesso:
1. Analise os resultados (número de veículos vs distância)
2. Compare NSGA-II vs MOEA/D
3. Ajuste parâmetros conforme necessário
4. Execute em múltiplas instâncias para análise estatística
