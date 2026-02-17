# **Especificação Técnica: Shadow Cost (Custo Sombra)**

## **Mecanismo de Ordenação para o Arquivo de Inviáveis**

### **1\. Definição e Propósito**

No contexto do algoritmo BatteryFocusedNSGA2, o **Shadow Cost** é uma métrica sintética utilizada exclusivamente para **classificar e selecionar** indivíduos dentro da subpopulação inviável durante a etapa de Sobrevivência (InfeasibleSurvival).

#### **O Problema da Comparação Direta**

O objetivo f1 (Custo Total) mede dinheiro/distância. A restrição G2 mede déficit de energia (kWh).

* Solução A (Viável): Custo $1000, Violação 0 kWh.  
* Solução B (Inviável Leve): Custo $950, Violação 2 kWh.  
* Solução C (Inviável Grave): Custo $800, Violação 50 kWh.

Se ordenarmos apenas por f1 (menor é melhor), a Solução C venceria. Porém, a Solução C é provavelmente "lixo genético" (impossível de reparar), enquanto a Solução B é um "diamante bruto".  
**Propósito:** O Shadow Cost converte a violação (G2) em moeda (f1), criando um preço único ajustado que penaliza a inviabilidade proporcionalmente à sua gravidade.

### **2\. Formulação Matemática**

A fórmula geral do Shadow Cost (SC) para um indivíduo i é:  
SC\_i \= f\_{1,i} \+ (\\gamma \\times G\_{2,i})  
Onde:

* f\_1,i: O Custo Operacional Bruto da solução (já incluindo as distâncias percorridas até estações no modo otimista).  
* G\_2,i: O acúmulo total de "Dívida Energética" (kWh que faltaram).  
*  (Gamma): O **Fator de Penalidade** (Preço Sombra).

#### **2.1. Definindo o Fator  (Gamma)**

O valor de Gamma representa: *"Quanto custaria, em dinheiro, resolver magicamente esse déficit de energia?"*  
Para o EVRPTW, Gamma não deve ser um número aleatório. Ele deve ter base física para manter a coerência dimensional.  
**Sugestão de Calibragem:**  
O custo de violar a bateria deve ser, no mínimo, superior ao custo de ter percorrido a distância honestamente.

1. **Custo por km (C\_km):** Definido no Context (ex: R$ 2,00/km).  
2. **Consumo do Veículo (P):** Definido no Context (ex: 0,5 kWh/km).  
3. **Eficiência Inversa:** 1 kWh permite andar 1/P km (ex: 2 km).

Portanto, economizar 1 kWh de bateria "roubando" significa deixar de andar 2 km.  
O custo base dessa energia é: 2 km \* R$2,00 \= R$4,00  
Para desencorajar a violação, aplicamos um multiplicador de severidade (M), geralmente entre 2x e 10x.  
\\gamma \= \\left( \\frac{1}{\\text{Consumo}} \\times \\text{Custo}\_{km} \\right) \\times M

* Se M \= 1: A solução inviável empata com a viável.  
* Se M \> 1: A solução inviável precisa ser *geometricamente muito superior* para compensar a penalidade.

### **3\. Dinâmica de Seleção no InfeasibleSurvival**

Durante a etapa de sobrevivência, o algoritmo deve preencher as vagas destinadas aos inviáveis (ex: 25 vagas).

1. **Isolamento:** Seleciona-se o subconjunto da população onde G2 \> 0\.  
2. **Cálculo:** Para cada indivíduo, calcula-se SC.  
3. **Ordenação:** Ordena-se do menor SC para o maior.  
4. **Seleção:** Os Top-N sobrevivem.

**Exemplo Prático:**

| Solução | Custo Real (f1​) | Violação (G2​) | Penalidade (γ=10) | Shadow Cost | Rank |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **A (Viável)** | 1000 | 0 | 0 | 1000 | N/A (Grupo A) |
| **B (Quase)** | 980 | 1 kWh | 10 | **990** | **1º (Inviável)** |
| **C (Longe)** | 900 | 20 kWh | 200 | 1100 | 3º (Inviável) |
| **D (Médio)** | 950 | 5 kWh | 50 | 1000 | 2º (Inviável) |

*Nota:* A Solução B tem SC \= 990, que é menor que o custo da viável (1000). Isso significa que ela é uma candidata fortíssima: mesmo pagando a multa, ela é mais eficiente. O algoritmo vai preservá-la e tentar cruzá-la para "legalizar" essa eficiência.

### **4\. Implementação em Python**

Esta lógica deve ser inserida dentro do método \_do da classe InfeasibleSurvival.  
def \_rank\_infeasible\_by\_shadow\_cost(self, infeasible\_pop, n\_select, context):  
    """  
    Seleciona as melhores soluções inviáveis usando Shadow Cost.  
    """  
    \# 1\. Extração dos Dados  
    F \= infeasible\_pop.get("F")\[:, 0\]  \# f1: Custo Total  
    G \= infeasible\_pop.get("G")  
      
    \# Assumindo que G2 (Bateria) é a segunda coluna das restrições  
    \# Se houver outras restrições, foque na de bateria ou some todas  
    G\_battery \= G\[:, 1\]  
      
    \# 2\. Cálculo do Gamma (Dinâmico ou Estático)  
    \# Opção A: Estático baseado no Contexto (Recomendado)  
    \# Custo de 'recuperar' 1 unidade de energia transformando em distância  
    \# Gamma \= (Distância que 1kWh percorre) \* (Custo por Km) \* (Severidade)  
      
    km\_per\_kwh \= 1.0 / context.consumption\_rate  
    base\_energy\_cost \= km\_per\_kwh \* context.distance\_cost  
    severity\_multiplier \= 5.0 \# Calibrável (3.0 a 10.0 costuma funcionar bem)  
      
    gamma \= base\_energy\_cost \* severity\_multiplier  
      
    \# 3\. Cálculo do Shadow Cost  
    shadow\_costs \= F \+ (gamma \* G\_battery)  
      
    \# 4\. Ordenação (Menor Shadow Cost é melhor)  
    sorted\_indices \= np.argsort(shadow\_costs)  
      
    \# 5\. Seleção  
    best\_indices \= sorted\_indices\[:n\_select\]  
      
    return infeasible\_pop\[best\_indices\]

### **5\. Impacto na Convergência**

#### **Por que isso não distorce a Fronteira de Pareto?**

Porque o Shadow Cost **nunca é usado para comparar Viável vs Inviável**.

* Os Viáveis são selecionados por Rank/Crowding (Nicho 1).  
* Os Inviáveis são selecionados por Shadow Cost (Nicho 2).  
* Eles só competem entre si dentro de seus nichos.

#### **A Função de "Ímã"**

O Shadow Cost age como um ímã que puxa a população inviável em direção à fronteira de viabilidade (G=0).

* Soluções com G2 gigante têm Shadow Cost alto e morrem.  
* Soluções com G2 pequeno sobrevivem.  
* Isso garante que o arquivo de inviáveis contenha indivíduos que estão "orbitando" a região viável, prontos para serem reparados ou cruzados.

### **6\. Edge Case: E o Objetivo f2 (Insatisfação)?**

O Shadow Cost foca puramente em f1 (Custo). E se uma solução tiver f1 alto, violação alta, mas f2 (Satisfação) excelente?  
**Decisão de Design:**  
Para o EVRP, a restrição de bateria está muito mais correlacionada com f1 (distância) do que com f2 (tempo/janela).

* Portanto, ignorar f2 no ranking dos inviáveis é aceitável.  
* Queremos que o arquivo de inviáveis forneça "geometrias de rota eficientes". A satisfação do cliente (f2) é secundária nesse filtro específico.  
* Se quisermos considerar, podemos adicionar um termo, mas aumentaria a complexidade sem ganho claro. **Recomendação: Manter foco em f1.**