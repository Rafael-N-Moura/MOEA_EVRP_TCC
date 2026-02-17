# **Plano de Implementação: NSGA-II com Directed Mating Focado em Bateria (EVRP)**

## **0\. Contextualização e Motivação**

### **O Problema do EVRP e a "Fronteira da Bateria"**

No Problema de Roteamento de Veículos Elétricos (EVRP), as melhores soluções (aquelas com menor custo e menor número de veículos) frequentemente operam no limite da capacidade da bateria. Uma rota que utiliza 99% da bateria é extremamente eficiente, mas arriscada. Uma rota que utiliza 101% é matematicamente inviável, mas geometricamente contém informações valiosas sobre a ordem ótima de visitação dos clientes.

### **A Limitação do NSGA-II Padrão**

O algoritmo NSGA-II padrão lida com restrições de duas formas principais:

1. **Penalização/Descarte:** Soluções inviáveis (bateria \< 0\) são dominadas por qualquer solução viável. Isso faz com que genes de rotas geometricamente eficientes sejam descartados prematuramente só porque violaram levemente a autonomia.  
2. **Reparo (Decoder Seguro):** Decoders tradicionais "consertam" a inviabilidade adicionando veículos ou recargas, transformando uma rota eficiente (mas inviável) em uma rota segura (mas cara).

### **A Proposta (Directed Mating)**

Este plano visa implementar uma variante do NSGA-II que **preserva intencionalmente soluções inviáveis** (aquelas com bom custo, mas bateria negativa) em um arquivo separado.

* **Estratégia:** Em vez de descartar essas soluções, o algoritmo força o cruzamento (acasalamento) entre soluções "seguras" e soluções "agressivas".  
* **Hipótese:** O cruzamento combinará a viabilidade das rotas seguras com a eficiência das rotas agressivas, convergindo mais rápido para o ótimo global do que a abordagem padrão.

## **1\. Definição Formal do Problema (pymoo.core.problem.Problem)**

A modelagem do problema deve expor as violações de forma contínua, permitindo que o algoritmo diferencie "quase viável" de "totalmente inviável".

### **1.1 Objetivos (Minimização)**

* ![][image1] **(Custo Operacional):** (n\_veiculos \* custo\_fixo) \+ (distancia\_total \* custo\_km)  
* ![][image2] **(Insatisfação):** 1.0 \- (soma\_satisfacao / n\_clientes), onde satisfação deriva do atraso (Soft Constraint).

### **1.2 Restrições Hard (![][image3])**

* ![][image4] **(Capacidade de Carga):** Sempre 0 (tratado pelo decoder via split de rota).  
* ![][image5] **(Bateria/SoC):** energia\_requerida \- bateria\_atual.  
  * Deve retornar o déficit de energia (em kWh positivo) se a bateria ficar negativa.

## **2\. Adaptação do Decoder (CRÍTICO)**

O decoder atual ("Safe Decoder") mascara soluções inviáveis adicionando veículos. Para o TCC funcionar, precisamos de um modo "Relaxed Decoder".

### **2.1 Modificação na Função decode**

Adicionar parâmetro force\_battery\_feasible: bool \= True.

* **Modo True (Seguro/Máscara):** Mantém a lógica atual. Se bateria \< crítica, retorna ao depósito e abre novo veículo.  
  * *Resultado:* Sempre viável (G2=0), mas tende a ter custo (f1) mais alto.  
  * *Uso:* Inicialização (Seeding) e Operadores de Reparo.  
* **Modo False (Relaxado/Transparente):**  
  * **Desativa** a verificação if current\_battery \< ... BATTERY\_THRESHOLD\_CRITICAL.  
  * **Não retorna** ao depósito preventivamente por causa de bateria.  
  * Continua visitando clientes até que a **Capacidade de Carga** estoure.  
  * *Resultado:* Gera rotas com poucos veículos (ótimo f1) mas expõe a violação de bateria (G2 \> 0).  
  * *Uso:* **Padrão durante a evolução (Problem.evaluate)**.

## **3\. Arquitetura do Algoritmo Customizado**

Criaremos a classe BatteryFocusedNSGA2 que estende NSGA2.

### **3.1 Estratégia de Avaliação Híbrida**

O segredo está em como chamamos o decoder dentro do loop evolutivo.

* **Inicialização (Sampling):**  
  * Gerar 50% da população inicial com force\_battery\_feasible=True (para garantir viabilidade inicial).  
  * Gerar 50% com force\_battery\_feasible=False (para explorar limites desde o início).  
* **Avaliação Padrão (Problem.evaluate):**  
  * Deve usar **force\_battery\_feasible=False**.  
  * *Por que?* Precisamos que o algoritmo veja o valor real de G2. Se usarmos True aqui, todas as soluções terão G2 \= 0 e o "Arquivo de Inviáveis" ficará sempre vazio, inutilizando a técnica.  
  * O algoritmo aprenderá sozinho a tornar G2 \= 0 através da pressão de seleção, sem precisar que o decoder force isso artificialmente.

### **3.2 Estratégia de Sobrevivência (InfeasibleSurvival)**

**Parâmetros:**

* infeasible\_ratio: \~20% a 30%.

**Lógica de Seleção:**

1. **Divisão:**  
   * **Grupo A (Viáveis):** G2 \<= 0 (Indivíduos que naturalmente respeitaram a bateria no Modo False).  
   * **Grupo B (Inviáveis):** G2 \> 0 (Indivíduos que estouraram a bateria).  
2. **Cota de Viáveis:** Preencher com Rank & Crowding.  
3. **Cota de Inviáveis:** Preencher com Grupo B ordenado pelo **melhor** ![][image6] **(Menor Custo)**.

### **3.3 Estratégia de Acasalamento (DirectedMatingSelection)**

**Lógica de Seleção de Pais:**

1. **Pai 1:** Selecionado do **Grupo A** (Viável/Seguro).  
2. **Pai 2:** Selecionado do **Grupo B** (Inviável/Eficiente).  
   * Isso cruza uma rota que economiza veículos (mas falha na bateria) com uma rota que respeita a bateria (mas gasta mais veículos).

## **4\. Roteiro de Codificação Ajustado**

1. **Fase 1 (Decoder Relaxado):**  
   * Alterar decode para aceitar flag force\_battery\_feasible.  
   * Testar manualmente: passar o mesmo indivíduo com True (deve dar mais veículos) e False (deve dar bateria negativa).  
2. **Fase 2 (Base Pymoo):**  
   * Classe EVRPProblem fixa o uso de decode(..., force=False).  
   * Rodar NSGA-II padrão. Verificar se ele consegue convergir para G2 \= 0 sozinho.  
3. **Fase 3 (Variante TCC):**  
   * Implementar BatterySurvival e MixedMating.  
   * Validar se soluções com bateria negativa mas poucos veículos estão sendo preservadas no arquivo.  
4. **Fase 4 (Comparação):**  
   * Baseline (NSGA-II Padrão): Vai descartar rapidamente as soluções de bateria negativa.  
   * Proposta (Directed Mating): Vai guardar as soluções de bateria negativa para cruzar.

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABEAAAAYCAYAAAAcYhYyAAAApklEQVR4XmNgGAWkAkkgngrEbOgSxAILIP4HxDFA/B9NjmgA0tgDpSkyRBNdkBQQzkCB7cpA7AXEJxgghvgCsQeKCiKAPxAXMUAMAAUqiF2AooIEADJkDbogqQBkiA+6ICnAlIGCQIWB6QxUMOQbAxUMARmwE12QVAAyxBldkBSgzUCBV0AaPwHxbCB+iyZHNAAZEgGlOdDkiAag3LoWiNnRJYYWAABl7SJDT5ALZQAAAABJRU5ErkJggg==>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABEAAAAYCAYAAAAcYhYyAAAA50lEQVR4XmNgGFFAEoinAjEbugSxwAKI/wFxDBD/R5MjGoA09kBpigzRRBckBYQzUGC7MhB7AfEJBoghvkDsgaKCCOAPxEUMEANAgQpiF6CoIAGADFmDLkgqABnigyYmDcQ/oHLJaHIYwJQBe6BORmKD5DOR+BhgOgOmIXJoYjvR+BjgGwMBBUDwGYjPoAsiA5ABIJtwAXYGwpaAFTijCyIBkDwjuiAy0GbAb8t7JPYdJDYYgDR+AuLZQPwWTQ4GrgNxIhRnA/FuVGmIIRFQmgNNDgSMGCByyDgXRQUDJLeuZYAE2kgHAEn5NnL3TV/DAAAAAElFTkSuQmCC>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA8AAAAYCAYAAAAlBadpAAAAyklEQVR4XmNgGJZAGogLgHgmECshiVshsTHAYiD+D8S3gdgbiFWBeBoQPwdiS6gcVgCS+A3E3OgSQFDJAJG/hC4BAn8Y8JgKBSD5IHTBD1AJZnQJNIBhuC5U8CG6BBaAofkvVJAXXYIYANKIYSKxAJ9mfyB2BmJ7IHYAYhcGtHABaXyNLIAEsoG4ngFhQTkQMyErwGczDIDkb6ELgsA1BogkO7oEFOQyQOTD0SVgAGY7ipOAQA5JDi/Yy4BQ+A5KN0Ll1sAUjYIhBwDP2zLKnm6VTgAAAABJRU5ErkJggg==>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABcAAAAYCAYAAAARfGZ1AAABEElEQVR4XmNgGAVkAGkgLgDimUCshCRuhcQmGSwG4v9AfBuIvYFYFYinAfFzILaEypEFQBp/AzE3ugQQVDJA5C+hSxAD/jAQdhVIPghdkBD4wADRyIwugQYIWY4BdBkgmh6iS2ABJBv+lwGiiRddghoAZDDJLiIW4DPcH4idgdgeiB2A2IUBM16ygNgLTQwOQAa/RheEgmwgrmdAOKAciJmgcjZAnA4Vx2s4LpfDAEj+FrogFOA1/BoDRAE7ugQU5DJA5MPRJaAAr+EgAHM9zMswIIckhwuA5EDFBF6wlwFh0Dso3QiVWwNThAWA1PmiC1ILgAz3QxekFgAZHoAuSCkAlesfgfgtFH9FlR4F9AYAkyFBKMNFHocAAAAASUVORK5CYII=>

[image5]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABcAAAAYCAYAAAARfGZ1AAABHElEQVR4XmNgGAVkAGkgLgDimUCshCRuhcQmGSwG4v9AfBuIvYFYFYinAfFzILaEypEFQBp/AzE3ugQQVDJA5C+hSxAD/jAQdhVIPghdkBD4wADRyIwugQYIWY4BdBkgmh6iS2ABJBv+lwGiiRddghoAZDDJLiIW4DPcH4idgdgeiB2A2IUBNV7WMkD03kEThwOQ5Gt0QSjIBuJ6BoQDyoGYCSq3F6YICJIYcDgQn8thACR/C4vYCTQ+Rrxdg0qwo0tAQS4DRD4cXQIJgHyD04Ew18O8DANySHL4wD0GSBmEE4DCEGbQOyjdCJVbA1OEBcQB8QR0QWoAfSDOgLLZGHAHLclACIjXAXECEKcA8TYUWQoBLAiR8SgYQAAAn+xFhVQBeYYAAAAASUVORK5CYII=>

[image6]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABEAAAAYCAYAAAAcYhYyAAAAy0lEQVR4XmNgGFFAEoinAjEbugSxwAKI/wFxDBD/R5MjGoA09kBpigzRRBckBYQzUGC7MhB7AfEJBoghvkDsgaKCCOAPxEUMEANAgQpiF6CoIAGADFmDLkgqABnigy4IBNxA/AFdEBswZcAeqKBEZ86AXQ4DTGfArZCRAbccCvjGgFsh0YaAFO1EF4QCkgxxRheEAqIM0WbArwivISCJT0A8G4jfoskhA4KGREBpDjQ5GPgFxO+A+A0QvwfiZlRpSG5dC8Ts6BIjEAAAxDUvT2yqwREAAAAASUVORK5CYII=>