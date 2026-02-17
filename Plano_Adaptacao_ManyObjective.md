# **Plano de Adaptação: De Bi-Objetivo para Many-Objective (6-Obj)**

**Data:** 12 de Fevereiro de 2025  
**Contexto:** Ajuste de Escopo após Reunião de Orientação  
**Autor:** Rafael

## **1\. Contextualização e Justificativa**

Durante a reunião de alinhamento, foi identificada uma limitação na abordagem anterior de combinar múltiplos fatores (Distância \+ Veículos) em funções de custo agregadas.  
**A Crítica:**  
Ao agregar objetivos (ex:Custo \= Nveic \* 1000 \+ Dist) estamos inserindo um viés humano arbitrário (*a priori*) sobre quanto vale um veículo em relação à quilometragem. Em um contexto puramente Multi-Objetivo, o ideal é deixar que o algoritmo descubra os *trade-offs* reais, expondo todas as dimensões conflitantes.  
**A Nova Diretriz:**

1. **Decomposição Total:** Separar os componentes de custo e serviço em objetivos distintos.  
2. **Investigação Many-Objective:** Avaliar o comportamento dos algoritmos ao lidar com **6 objetivos** simultâneos.  
3. **Análise de Performance:** Verificar se o aumento da dimensionalidade inviabiliza o tempo computacional necessário para a validação estatística (30 execuções).

## **2\. Definição dos 6 Objetivos Atômicos**

Para atender à solicitação, o problema EVRPTW-PR será modelado com as seguintes funções objetivo independentes (todas de minimização):

1. ![][image1]: Número de Veículos **(K)**  
   * *Natureza:* Custo de Investimento (CAPEX).  
2. ![][image2]**: Distância Total Percorrida (D)**  
   * *Natureza:* Custo Variável / Desgaste (OPEX).  
3. ![][image3]**: Duração Total das Rotas (T)**  
   * *Natureza:* Custo de Mão de Obra. Soma de (Viagem \+ Serviço \+ Espera \+ Recarga).  
4. ![][image4]: Violação de Janelas de Tempo **(Tw)**  
   * *Natureza:* Nível de Serviço. Soma dos minutos de atraso em cada cliente.  
5. ![][image5]**: Tempo de Espera (W)**  
   * *Natureza:* Eficiência Operacional. Tempo que o motorista fica parado esperando o cliente abrir (ei).  
6. ![][image6]: Tempo de **Recarga (Rc)**  
   * *Natureza:* Eficiência Energética/Operacional. Tempo improdutivo conectado à tomada.

## **3\. Impacto nos Algoritmos (A Inserção do NSGA-III)**

A literatura indica que o **NSGA-II** perde drasticamente a pressão de seleção quando o número de objetivos excede 3 (a maioria da população torna-se não-dominada, transformando a busca em um passeio aleatório).  
**Ação:** Incluir o **NSGA-III** na bateria de testes para o cenário de 6 objetivos.

| Algoritmo | Cenário 2-3 Objetivos | Cenário 6 Objetivos | Justificativa |
| :---- | :---- | :---- | :---- |
| **NSGA-II** | **Baseline** | Teste de Falha | Espera-se que falhe em convergir com 6-obj. |
| **MOEA/D** | Competitivo | Competitivo | Baseado em decomposição, escala bem com dimensões. |
| **NSGA-III** | N/A | **Novo Baseline** | Projetado especificamente para Many-Objective usando *Reference Points*. |

## **4\. Plano de Implementação (Refatoração)**

A arquitetura será atualizada para suportar seleção dinâmica de objetivos.

### **4.1. Atualização do src/model.py**

As classes de dados devem armazenar as métricas de forma granular, não agregada.

* **Alteração:** A classe Solution terá campos individuais para cada uma das 6 métricas (val\_vehicles, val\_distance, val\_duration, etc.).  
* **Alteração:** A classe RouteStep e VehicleRoute devem acumular wait\_time e recharge\_time separadamente.

### **4.2. Atualização do src/decoder.py**

O decodificador precisa calcular e preencher essas novas métricas durante a simulação física.

* **Lógica:** Ao final da construção da rota, somar os tempos de espera e recarga separadamente e popular o objeto Solution.

### **4.3. Criação do src/problem.py (Flexível)**

Substituir a classe estática por uma dinâmica (EVRPFlexProblem).

* **Feature:** O construtor receberá uma lista de strings: objectives=\['vehicles', 'distance', 'delay'\].  
* **Dinâmica:** O método \_evaluate usará essa lista para montar o vetor out\["F"\] dinamicamente. Isso permite rodar o experimento de 2 objetivos e o de 6 sem mudar uma linha de código lógico.

## **5\. Estratégia de Experimentos (Validação)**

Para responder à preocupação do orientador sobre "gargalo de performance", executaremos os testes em fases:

### **Fase A: Validação de Código (Unitária)**

* **Config:** 1 execução, 10 gerações, Instância c101 (Pequena).  
* **Objetivo:** Verificar se as 6 métricas estão sendo calculadas corretamente (ex: se o tempo de recarga não é zero).

### **Fase B: Teste de Carga (Benchmark de Tempo)**

* **Config:** 5 execuções, 100 gerações, Instância r101 (Média).  
* **Comparação:** Rodar NSGA-II (2 objs) vs. NSGA-III (6 objs).  
* **Meta:** Medir o aumento no tempo de processamento. O cálculo dos objetivos no Decodificador é rápido (soma simples), o gargalo pode ser o *sorting* do algoritmo genético em alta dimensão.

### **Fase C: Execução Final (Produção)**

Se a Fase B for bem sucedida (tempo aceitável), rodamos o experimento completo:

1. **Cenário Clássico (2 Obj):** f1,f2 (NSGA-II vs MOEA/D).  
2. **Cenário Serviço (3 Obj):** f1,f2,f4 (NSGA-II vs MOEA/D).  
3. **Cenário** Many-Obj **(6 Obj):** Todos (NSGA-III vs MOEA/D).

## **6\. Próximos Passos Imediatos**

1. Refatorar model.py para incluir os 6 campos.  
2. Atualizar decoder.py para calcular as somas granulares.  
3. Implementar EVRPFlexProblem em problem.py.  
4. Configurar o script de execução (runner.py) para instanciar o **NSGA-III** via pymoo.

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABEAAAAYCAYAAAAcYhYyAAAAy0lEQVR4XmNgGFFAEoinAjEbugSxwAKI/wFxDBD/R5MjGoA09kBpigzRRBckBYQzUGC7MhB7AfEJBoghvkDsgaKCCOAPxEUMEANAgQpiF6CoIAGADFmDLkgqABnigy4IBNxA/AFdEBswZcAeqKBEZ86AXQ4DTGfArZCRAbccCvjGgFsh0YaAFO1EF4QCkgxxRheEAqIM0WbArwivISCJT0A8G4jfoskhA4KGREBpDjQ5GPgFxO+A+A0QvwfiZlRpSG5dC8Ts6BIjEAAAxDUvT2yqwREAAAAASUVORK5CYII=>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABEAAAAYCAYAAAAcYhYyAAAA50lEQVR4XmNgGFFAEoinAjEbugSxwAKI/wFxDBD/R5MjGoA09kBpigzRRBckBYQzUGC7MhB7AfEJBoghvkDsgaKCCOAPxEUMEANAgQpiF6CoIAGADFmDLkgqABnigyYmDcQ/oHLJaHIYwJQBe6BORmKD5DOR+BhgOgOmIXJoYjvR+BjgGwMBBUDwGYjPoAsiA5ABIJtwAXYGwpaAFTijCyIBkDwjuiAy0GbAb8t7JPYdJDYYgDR+AuLZQPwWTQ4GrgNxIhRnA/FuVGmIIRFQmgNNDgSMGCByyDgXRQUDJLeuZYAE2kgHAEn5NnL3TV/DAAAAAElFTkSuQmCC>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABEAAAAYCAYAAAAcYhYyAAAA9UlEQVR4XmNgGFFAEoinAjEbugSxwAKI/wFxDBD/R5MjGoA09kBpigzRRBckBYQzUGC7MhB7AfEJBoghvkDsgaKCCOAPxEUMEANAgQpiF6CoIAGADFmDLkgqABnigyYmBsTfgPgTEJeiyWEAUwbsgQryHjOUDZIPQZLDANMZsBvyCohZoWyQfD6SHAYAORmbITCgwgDxEl4AMmAnuiAUNADxIQZIMsALQIY4owuiAbyxp82A3SvsQHwTiX+SAYs6kADIn7OB+C2aHAjYMqBq+gXEu5D4YABSEAGlOdDkYGAbEO9hgGSJi2hyYADKrWsZIM4e6QAAzMw2V1DeEWIAAAAASUVORK5CYII=>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABEAAAAYCAYAAAAcYhYyAAAA2ElEQVR4XmNgGFFAEoinAjEbugSxwAKI/wFxDBD/R5MjGoA09kBpigzRRBckBYQzUGC7MhB7AfEJBoghvkDsgaKCCOAPxEUMEANAgQpiF6CoIAGADFmDLkgqABnigy6IBAiGlykDfkUXGPDLg8F0BtyK9BggqRiXPBx8Y8CtaDuUxiUPByAFO9EFgeAoEpsoQ5zRxBShGAbwGqLNgF3BZCDeB8VHGCBqQGwUABL8BMSzgfgtmhw6wBmwIMEIKM2BJocMZgDxewaIRZ/R5MC5dS0Qs6NLjEAAAJ2mNCFrB552AAAAAElFTkSuQmCC>

[image5]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABEAAAAYCAYAAAAcYhYyAAAA9UlEQVR4XuWTKwvCYBSGj8ULgt0iiEnMgt0iohg1+CNEtNkEk1UM/gCLYrYZ1f+gzWgRsXl5383BvrMJG8Y98LB97znf2Y2JRIosnMG4LgSlAl+wC9+qFhhunH6Pfw0p6jAMbfnj6gVYh3uxhzRhzegIQAv2xR7Al8rzntERAg5Z6TAsHNJQGe9sCQfwBFNm2aQs/i/V+dQ7mDZLXubye0hgHuK/gdkQHmBO1TyweatDMQc/Yd619sDmqg4VG3jRoUNJ/B8lI2bOr3RzrS3YwHABr6pGYnDsWt9hx7W24BCGPCZVzWEEj/AMJ6pmwb91DRO6EEE+kIg2NryeyT0AAAAASUVORK5CYII=>

[image6]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABEAAAAYCAYAAAAcYhYyAAAA+ElEQVR4XmNgGFFAEoinAjEbugSxwAKI/wFxDBD/R5MjGoA09kBpigzRRBckBYQzUGC7MhB7AfEJBoghvkDsgaKCCOAPxEUMEANAgQpiF6CoIAGADFmDLkgqABnigy7IAPEqSO4UugQ6MGXAHqggr7VC2R+BeAqSHAaYzoDdEGQxViQ2VvCNAdMQXahYMxDfAOLJqNKYAKR4J5pYAlScE8rfDMQ5cFksAKTYGU3MHSoOA8VofBSgzYBdkpsBVRyUdjDUgQQ+AfFsIH6LJgcDyJqWAvEsJD4YgBREQGkONDkYEALiP0C8DIjPo8mBASi3rgVidnSJEQgAxqw3aTCNGZ8AAAAASUVORK5CYII=>