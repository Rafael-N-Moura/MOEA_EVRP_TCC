# **Especificação Técnica: Sistema de Avaliação Agnóstico para EVRPTW-PR**

**Versão:** 1.0  
**Contexto:** TCC \- Análise Comparativa Multi-Objetivo (NSGA-II vs MOEA/D)  
**Autor:** Rafael  
**Orientador:** Prof. Dr. Aluizio Araújo

## **1\. Visão Geral da Arquitetura**

O sistema foi projetado seguindo o padrão de **Simulação por Caixa Preta** (Black-Box Simulation). Isso garante o isolamento total entre a lógica de otimização (Algoritmos Evolutivos) e a lógica de negócio (Regras Físicas do EVRP).

### **1.1. Fluxo de Dados**

1. **Entrada (Genótipo):** Uma permutação de inteiros representando a sequência de visitas aos clientes (ex: \[5, 12, 1, ...\]).  
2. **Processamento (Decodificador):** Simulação determinística que transforma a sequência em rotas, inserindo recargas e novos veículos conforme necessário.  
3. **Saída (Fenótipo):** Objetivos numéricos (f1: Veículos, f2: Distância) e métricas de violação.

### **1.2. Estrutura de Diretórios**

projeto\_tcc/  
├── data/                  \# Arquivos .txt (Schneider)  
├── src/  
│   ├── \_\_init\_\_.py  
│   ├── model.py           \# Estruturas de Dados (Dataclasses)  
│   ├── parser.py          \# Leitura de Arquivos (Tradutor)  
│   ├── decoder.py         \# Lógica de Negócio (Física/Bateria)  
│   └── problem.py         \# Adaptador Pymoo (Interface)  
├── main.py                \# Script de Execução  
└── requirements.txt       \# pymoo, numpy

## **2\. Detalhamento dos Módulos**

### **Módulo 1: src/model.py**

Define o "vocabulário" do sistema. Classes imutáveis para dados estáticos e classes ricas para dados dinâmicos.  
**Classes Principais:**

* **Node (Frozen):** Representa um ponto no mapa.  
  * id: Identificador (String).  
  * type: 'c' (Cliente), 'f' (Estação), 'd' (Depósito).  
  * demand, ready\_time, due\_date, service\_time: Restrições locais.  
* **Context:** Objeto global contendo o mapa e as constantes físicas.  
  * battery\_capacity (Q): Energia Máxima.  
  * vehicle\_capacity (C): Carga Máxima.  
  * consumption\_rate (r): Taxa de descarga.  
  * recharge\_rate (g): Taxa de recarga.  
  * velocity (v): Velocidade média.  
* **RouteStep:** Registro detalhado de uma parada (para auditoria).  
  * arrival\_time, departure\_time, battery\_arrival, recharge\_amount.  
* **Solution:** O resultado final.  
  * routes: Lista de rotas.  
  * total\_vehicles (f1), total\_distance (f2).  
  * is\_feasible: Booleano global.

### **Módulo 2: src/parser.py**

Responsável por converter o texto bruto do benchmark em objetos Context.  
**Responsabilidades:**

1. **Sanitização:** Ler arquivos .txt ignorando linhas em branco e cabeçalhos irrelevantes.  
2. **Extração de Parâmetros:** Ler as últimas linhas do arquivo Schneider para capturar Q, C, r, g e v. Se não existirem, aplicar defaults (r = 1.0, v = 1.0).  
3. **Categorização:** Separar a lista de nós em depot, stations e customers.

### **Módulo 3: src/decoder.py (O Core Lógico)**

Implementa a heurística construtiva e o tratamento de restrições.  
**Entrada:** individual (Lista int) e context.  
**Algoritmo de Decodificação:**

1. **Inicialização:** Abre Veículo 1 no Depósito.  
2. **Iteração:** Para cada customer\_id na permutação:  
   * **Passo A (Carga):** Se CargaAtual \+ Demanda \> CapacidadeMax:  
     * Retorna ao depósito. Fecha Veículo k. Abre Veículo k+1 .  
   * **Passo B (Viabilidade Energética \- Safety Buffer):**  
     * Simula ir para o cliente. Calcula BateriaRestante.  
     * *Teste:* BateriaRestante >= Distância para a estação mais próxima (ou depósito)?  
     * **Se FALHAR:**  
       * Encontra Estação S mais próxima da posição *atual*.  
       * Insere visita a S.  
       * Calcula RecargaNecessaria \= (Energia até Cliente \+ Margem de Segurança) \- BateriaAtual.  
       * Executa Recarga (consome Tempo).  
       * Atualiza Posição para S.  
   * **Passo C (Janelas de Tempo):**  
     * Calcula Chegada. Se Chegada \< Ready: Espera.  
     * Se Chegada \> Due: Marca Solution.is\_feasible \= False, registra violação, mas **mantém a visita** (para permitir aprendizado/penalização).  
3. **Finalização:** Último veículo retorna ao depósito. Calcula métricas finais.

### **Módulo 4: src/problem.py (Adaptador Pymoo)**

Conecta a lógica de negócio à biblioteca de otimização.  
**Implementação:** Herda de pymoo.core.problem.ElementwiseProblem.  
**Lógica de Avaliação (\_evaluate):**

1. Chama decoder.decode(x).  
2. Recupera f1 (Veículos) e f2 (Distância).  
3. **Aplicação de Penalidade:**  
   * Se solution.is\_feasible \== False:  
   * f1 = f1 + PENALTY_V (ex: 100).  
   * f2 = f2 + PENALTY_D (ex: 10.000).  
   * *Justificativa:* Isso garante que soluções inviáveis sejam dominadas por soluções viáveis na seleção do NSGA-II.  
4. Retorna out\["F"\] \= \[f1, f2\].

## **3\. Configuração dos Experimentos (Main)**

Como instanciar e rodar os algoritmos comparativos.

### **3.1. Algoritmo A: NSGA-II**

Padrão de indústria baseada em dominância.  
algorithm \= NSGA2(  
    pop\_size=100,  
    sampling=PermutationRandomSampling(),  
    crossover=OrderCrossover(),  \# Preserva ordem relativa (Vital para VRP)  
    mutation=InversionMutation(), \# Simula 2-opt  
    eliminate\_duplicates=True  
)

### **3.2. Algoritmo B: MOEA/D**

Baseado em decomposição. Excelente para problemas combinatórios.  
ref\_dirs \= get\_reference\_directions("das-dennis", 2, n\_partitions=99)  
algorithm \= MOEAD(  
    ref\_dirs,  
    n\_neighbors=15,  
    prob\_neighbor\_mating=0.7,  
    sampling=PermutationRandomSampling(),  
    crossover=OrderCrossover(),  
    mutation=InversionMutation()  
)  
