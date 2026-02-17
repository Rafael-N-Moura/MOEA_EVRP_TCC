# **Especificação Técnica: Sistema de Avaliação Multi-Objetivo para EVRP**

**Versão:** 2.0 (Final)  
**Contexto:** TCC \- Otimização de Roteamento de Veículos Elétricos  
**Abordagem:** Custo Operacional vs. Nível de Serviço (Satisfação)  
**Arquitetura:** Simulação Agnóstica (Adapter Pattern)

## **1\. Visão Geral da Arquitetura**

O sistema adota uma arquitetura em camadas para isolar a lógica de otimização (pymoo) da lógica de negócio (Regras do EVRP).

### **1.1. Fluxo de Dados**

1. **Entrada (Genótipo):** Uma permutação de IDs de clientes (ex: \[5, 12, 1, ...\]). O algoritmo genético decide *apenas* a ordem de visita.  
2. **Processamento (Decodificador):** Uma simulação determinística constrói as rotas, gerencia a bateria (inserindo recargas) e calcula os tempos de chegada.  
3. **Saída (Objetivos):**  
   * **f1 (Minimizar Custo):** Combinação linear de Frota e Distância.  
   * **f2 (Minimizar Insatisfação):** Média do decaimento de serviço por atrasos.

### **1.2. Estrutura de Diretórios**

src/  
├── model.py       \# Definição de Dados (Vocabulário do sistema)  
├── parser.py      \# Leitura de Arquivos (Tradutor do Benchmark)  
├── decoder.py     \# Lógica de Negócio (Física, Bateria e Objetivos)  
└── problem.py     \# Adaptador Pymoo (Conexão com os Algoritmos)

## **2\. Detalhamento dos Módulos**

### **Módulo 1: src/model.py (Estruturas de Dados)**

Define classes estritas para garantir consistência e evitar "números mágicos".  
**Classes Imutáveis (Entrada Estática):**

* **Node:** Representa um ponto geográfico.  
  * Atributos: id, type ('c', 'f', 'd'), x, y, demand, ready\_time, due\_date, service\_time.  
* **Context:** Objeto "Deus" contendo o mapa e constantes físicas.  
  * Atributos: nodes, depot, stations, customers.  
  * Física: battery\_capacity (Q), vehicle\_capacity (C), consumption\_rate (r), recharge\_rate (g), velocity (v).  
  * Custos: vehicle\_cost (ex: 1000), distance\_cost (ex: 1.0).

**Classes de Solução (Saída Dinâmica):**

* **RouteStep:** Registro detalhado de uma parada.  
  * Atributos: node\_id, arrival\_time, battery\_level, recharge\_amount, satisfaction\_score.  
* **Solution:** O Fenótipo completo.  
  * Atributos:  
    * routes: Lista de rotas detalhadas.  
    * total\_cost (f1): Valor financeiro total.  
    * avg\_dissatisfaction (f2): Valor entre 0.0 e 1.0.  
    * is\_feasible: True se respeitou carga e bateria (tempo é soft).

### **Módulo 2: src/parser.py (Leitura)**

Converte o arquivo .txt bruto em um objeto Context.  
**Lógica de Parsing:**

1. Ler metadados do rodapé do arquivo Schneider (Q, C, r, g, v).  
2. Ler linhas de nós. Identificar tipo pelo caractere na segunda coluna (d, f, c).  
3. Sanitizar coordenadas e demandas para float.

### **Módulo 3: src/decoder.py (O Core Lógico)**

Implementa a heurística construtiva e a função de avaliação de satisfação.  
**Assinatura:** decode(individual: List\[int\], context: Context) \-\> Solution  
**Algoritmo de Construção:**

1. **Inicialização:** Abre Rota 1 no Depósito.  
2. **Iteração:** Para cada cliente na permutação:  
   * **Restrição de Carga:** Se CargaAtual \+ Demanda \> Capacidade:  
     * Retorna ao depósito. Abre nova rota.  
   * **Restrição de Bateria (Safety Buffer):**  
     * Simula viagem direta. Calcula BateriaRestante.  
     * Teste: BateriaRestante ![][image1] Energia para chegar à estação mais próxima?  
     * **Se FALHAR:**  
       * Encontra estação S mais próxima da posição *atual*.  
       * Insere visita a S.  
       * Calcula recarga necessária (apenas o suficiente para seguir com segurança).  
       * Adiciona tempo de recarga.  
       * Atualiza posição para S.  
   * **Registro do Cliente:**  
     * Calcula tempo de chegada.  
     * Calcula **Satisfação (Si)**:  
       * Se Chegada \<= DueDate: Si \= 1.0.  
       * Se Chegada \> DueDate: Decaimento linear. Ex: 

       Si \= max(0,1.0-(Atraso/Tolerancia)).

     * Adiciona cliente à rota.  
3. **Fechamento:** Retorna ao depósito.  
4. **Cálculo Final de Objetivos:**  
   * F1 \= (Nveic \* CustoVeic) \+ (Disttotal \* CustoDist)  
   * F2 \= 1.0 \- Média(Si de todos os clientes)

### **Módulo 4: src/problem.py (Adaptador Pymoo)**

Conecta sua lógica à biblioteca de otimização.  
**Implementação:** Herda de pymoo.core.problem.ElementwiseProblem.  
**Construtor:**

* Define n\_var \= número de clientes.  
* Define n\_obj \= 2\.  
* Define xl \= 0, xu \= n\_var (embora para permutação isso seja ignorado pelos operadores, a classe exige).

**Método \_evaluate(x, out, ...):**

1. **Input:** x é um np.array de inteiros (permutação).  
2. **Chamada:** sol \= decoder.decode(x, context).  
3. **Output:**  
   * out\["F"\] \= \[sol.total\_cost, sol.avg\_dissatisfaction\]  
4. **Tratamento de Inviabilidade:**  
   * Neste novo modelo, violações de tempo não geram inviabilidade, apenas custo alto em f2.  
   * Apenas violações físicas (se houver bug no código que quebre bateria) marcariam is\_feasible=False.

## **3\. Configuração dos Algoritmos (src/main.py)**

Como instanciar os algoritmos para este modelo discreto.

### **Configuração Comum**

Todos os algoritmos usarão operadores específicos para permutação (Vital para não gerar rotas inválidas como \[1, 1, 2\]).  
from pymoo.operators.sampling.rnd import PermutationRandomSampling  
from pymoo.operators.crossover.ox import OrderCrossover  
from pymoo.operators.mutation.inversion import InversionMutation

\# Configuração Padrão  
sampling \= PermutationRandomSampling()  
crossover \= OrderCrossover()  
mutation \= InversionMutation()

### **Algoritmo 1: NSGA-II**

algorithm \= NSGA2(  
    pop\_size=100,  
    sampling=sampling,  
    crossover=crossover,  
    mutation=mutation,  
    eliminate\_duplicates=True  
)

### **Algoritmo 2: MOEA/D**

Requer definição de vetores de referência.  
from pymoo.util.ref\_dirs import get\_reference\_directions  
ref\_dirs \= get\_reference\_directions("das-dennis", 2, n\_partitions=99)

algorithm \= MOEAD(  
    ref\_dirs,  
    n\_neighbors=15,  
    prob\_neighbor\_mating=0.7,  
    sampling=sampling,  
    crossover=crossover,  
    mutation=mutation  
)

## **4\. Output Esperado para Análise**

O sistema deve exportar os dados prontos para os gráficos do TCC.  
**Arquivo: pareto\_results.csv**  
Colunas:

1. Algorithm (NSGA-II / MOEA-D)  
2. Run\_ID (1 a 30\)  
3. F1\_TotalCost (Eixo X)  
4. F2\_Dissatisfaction (Eixo Y \- Nível de Serviço)  
5. Vehicle\_Count (Dado extra para análise)  
6. Total\_Distance (Dado extra para análise)

Este formato permite gerar facilmente o gráfico de fronteira onde o eixo X é "Dinheiro" e o eixo Y é "Qualidade de Serviço".

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA8AAAAXCAYAAADUUxW8AAAAiElEQVR4XmNgGAVkAVcg/g/EWegSpABrBogh3egSpABVIP4JxMvQJUgBIkD8HogPoUuQAjiA+D4QXwNiZjQ5ooAYEH8A4h3oEviAOhD/AuKF6BL4gB0DJOTb0CXwgUgGMuI8lwGiyQ9dghBoAGIjdMHBD6SB2JtIbAHVAwegZGhOJNaE6hmqAADk7RfSbVOfYwAAAABJRU5ErkJggg==>