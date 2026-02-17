# Passos para Executar o Sistema

## ✅ Checklist de Execução

### Passo 1: Instalar Dependências

No terminal, execute:

```bash
cd /Users/rafaelmoura/MOEA_EVRP_TCC
pip3 install -r requirements.txt
```

**Dependências necessárias:**
- `pymoo>=0.6.0` - Biblioteca de algoritmos evolutivos
- `numpy>=1.21.0` - Operações numéricas
- `matplotlib>=3.5.0` - Visualização (opcional, mas recomendado)

**Se houver erro de permissão:**
```bash
pip3 install --user -r requirements.txt
```

**Ou use ambiente virtual (recomendado):**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

### Passo 2: Testar o Parser (Verificação)

Teste se o parser está funcionando:

```bash
python3 -c "from src.parser import parse_instance; ctx = parse_instance('evrptw_instances/rc108C5.txt'); print(f'Clientes: {len(ctx.customers)}, Estações: {len(ctx.stations)}')"
```

**Nota**: Este comando pode falhar se as dependências não estiverem instaladas, mas isso é esperado. O parser em si não precisa delas, mas o `__init__.py` importa módulos que precisam.

---

### Passo 3: Executar Teste Rápido

**Opção A: Instância Muito Pequena (5 clientes) - ~2-5 minutos**

```bash
python3 main.py evrptw_instances/rc108C5.txt --algorithm nsga2 --n-gen 20 --pop-size 30 --no-verbose
```

**Opção B: Instância Pequena (100 clientes) - ~15-30 minutos**

```bash
python3 main.py evrptw_instances/r101_21.txt --algorithm nsga2 --n-gen 50 --pop-size 50
```

---

### Passo 4: Executar Comparação Completa

Para comparar NSGA-II e MOEA/D:

```bash
python3 main.py evrptw_instances/r101_21.txt --algorithm both --n-gen 100 --pop-size 100 --plot
```

---

## 📊 Instâncias Disponíveis

### Instâncias Pequenas (Recomendadas para Teste)

| Arquivo | Clientes | Descrição |
|---------|----------|-----------|
| `rc108C5.txt` | 5 | Muito pequena - Teste rápido |
| `r101_21.txt` | 100 | Pequena - Teste médio |
| `c101_21.txt` | 100 | Pequena - Teste médio |

### Instâncias Grandes (Para Experimentos Finais)

| Arquivo | Clientes | Descrição |
|---------|----------|-----------|
| `r201_21.txt` | 100 | Média |
| `c201_21.txt` | 100 | Média |
| `rc201_21.txt` | 100 | Média |

**Nota**: Todas as instâncias seguem o padrão:
- Prefixo `r`, `c` ou `rc` indica tipo de distribuição
- Número indica tamanho (101 = pequena, 201 = média)
- Sufixo `C5`, `C10`, `C15` indica variações com menos clientes

---

## 🎯 Comandos Recomendados por Cenário

### Cenário 1: Primeiro Teste (Validação Rápida)
```bash
python3 main.py evrptw_instances/rc108C5.txt --algorithm nsga2 --n-gen 10 --pop-size 20 --no-verbose
```
**Tempo estimado**: 2-5 minutos  
**Objetivo**: Verificar se tudo está funcionando

### Cenário 2: Teste Médio (Análise Inicial)
```bash
python3 main.py evrptw_instances/r101_21.txt --algorithm nsga2 --n-gen 50 --pop-size 50
```
**Tempo estimado**: 15-30 minutos  
**Objetivo**: Obter resultados preliminares

### Cenário 3: Comparação Completa
```bash
python3 main.py evrptw_instances/r101_21.txt --algorithm both --n-gen 100 --pop-size 100 --plot
```
**Tempo estimado**: 1-2 horas  
**Objetivo**: Comparar NSGA-II vs MOEA/D com visualização

### Cenário 4: Execução Longa (Resultados Finais)
```bash
python3 main.py evrptw_instances/r101_21.txt --algorithm both --n-gen 200 --pop-size 100 --plot
```
**Tempo estimado**: 2-4 horas  
**Objetivo**: Resultados para análise estatística

---

## 📈 Interpretação dos Resultados

### Saída Esperada

```
Carregando instância: evrptw_instances/r101_21.txt
✓ Instância carregada com sucesso
  - Depósito: D0
  - Estações: 21
  - Clientes: 100
  - Capacidade bateria (Q): 62.14
  - Capacidade veículo (C): 200.0
  - Taxa consumo (r): 1.0
  - Taxa recarga (g): 0.48
  - Velocidade (v): 1.0

============================================================
Executando NSGA-II
============================================================
População: 50
Gerações: 50
============================================================

[Progresso do algoritmo...]

============================================================
NSGA-II Finalizado
============================================================
Tempo de execução: 245.32 segundos
Soluções encontradas: 50
Melhor f1 (veículos): 15
Melhor f2 (distância): 1234.56
============================================================
```

### Métricas Importantes

- **f1 (veículos)**: Número mínimo de veículos necessários
- **f2 (distância)**: Distância total percorrida
- **Soluções encontradas**: Tamanho da frente de Pareto
- **Tempo de execução**: Performance do algoritmo

### Frente de Pareto

Se usar `--plot`, será exibido um gráfico onde:
- **Eixo X**: Número de veículos (f1)
- **Eixo Y**: Distância total (f2)
- **Pontos**: Soluções não-dominadas
- **Objetivo**: Encontrar soluções no canto inferior esquerdo (menos veículos E menos distância)

---

## 🔧 Solução de Problemas

### Erro: "ModuleNotFoundError: No module named 'pymoo'"
**Causa**: Dependências não instaladas  
**Solução**: Execute `pip3 install -r requirements.txt`

### Erro: "Permission denied" ao instalar
**Causa**: Permissões do sistema  
**Solução**: Use `pip3 install --user -r requirements.txt` ou crie ambiente virtual

### Erro: "Depósito não encontrado no arquivo"
**Causa**: Arquivo de instância corrompido ou formato incorreto  
**Solução**: Verifique se o arquivo está no formato Schneider correto

### Erro: "ValueError: invalid literal for int()"
**Causa**: Problema no parsing do arquivo  
**Solução**: Verifique se o arquivo não está corrompido

### Execução muito lenta
**Causa**: Instância grande ou muitos parâmetros  
**Solução**: 
- Use instâncias menores para teste
- Reduza `--n-gen` e `--pop-size`
- Use `--no-verbose` para reduzir I/O

---

## 📝 Próximos Passos Após Execução

1. **Analisar Resultados**
   - Compare f1 (veículos) vs f2 (distância)
   - Identifique trade-offs na frente de Pareto

2. **Comparar Algoritmos**
   - Execute com `--algorithm both`
   - Compare qualidade e diversidade das soluções

3. **Ajustar Parâmetros**
   - Experimente diferentes `--n-gen` e `--pop-size`
   - Para MOEA/D, ajuste `--n-partitions`

4. **Executar em Múltiplas Instâncias**
   - Execute em diferentes instâncias
   - Colete dados para análise estatística

5. **Salvar Resultados**
   - Os resultados podem ser salvos manualmente
   - Considere adicionar funcionalidade de exportação

---

## 💡 Dicas

- **Comece pequeno**: Use `rc108C5.txt` para primeiro teste
- **Use `--no-verbose`**: Reduz I/O e acelera execução
- **Monitore memória**: Instâncias grandes podem consumir muita RAM
- **Salve logs**: Redirecione saída para arquivo: `python3 main.py ... > resultado.log 2>&1`
- **Execute em background**: Use `nohup` ou `screen` para execuções longas

---

**Boa execução! 🚀**
