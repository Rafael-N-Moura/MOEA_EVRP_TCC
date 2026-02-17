# **Especificação Técnica: Decodificador Híbrido para EVRPTW-PR**

## **Estratégia de Relaxamento de Restrições e Recarga Parcial Inteligente**

### **1\. Visão Geral e Fundamentação Teórica**

Esta especificação define o comportamento do algoritmo de mapeamento Genótipo-Fenótipo (Decoder) utilizado no BatteryFocusedNSGA2. A abordagem utiliza **Relaxamento de Restrições (Constraint Relaxation)** para permitir que o algoritmo evolutivo explore regiões inviáveis do espaço de busca que contêm informações geométricas valiosas (ex: sequências de clientes ótimas que violam levemente a bateria).

#### **1.1. Dualidade de Modos**

O decoder opera em dois modos distintos, controlados pela flag force\_battery\_feasible:

1. **Modo Conservador (True):** Garante viabilidade estrita (G2 \= 0). Prioriza a segurança operacional, inserindo recargas preventivas e abortando rotas (abrindo novos veículos) se houver risco de ficar ilhado.  
2. **Modo Otimista/Arriscado (False):** Permite inviabilidade (G2 \>= 0). Prioriza a manutenção da sequência do veículo. Se a bateria acabar, o veículo "contrai uma dívida energética" (violação), mas **percorre a distância física real** até a estação, garantindo que o custo (f1) seja comparável ao modo conservador.

### **2\. Definições Críticas**

* **Safety Buffer (Buffer de Segurança):** A capacidade do veículo de sair de um nó (Cliente ou Estação) e chegar à estação de recarga mais próxima desse nó.  
  * Fórmula:

  Ebuffer(N) \= Dist(N, NearestStation(N)) \* ConsumptionRate

* **Look-ahead (Verificação Antecipada):** A verificação feita *antes* de viajar para um destino, assegurando que há energia para (Viagem \+ Buffer do Destino).  
* **Dívida Energética (G2):** A quantidade de energia que o veículo utilizou "além do zero" para completar um trecho físico no Modo Otimista.

### **3\. Lógica de Recarga Parcial Inteligente**

A decisão de "quanto carregar" é crítica para evitar loops (ping-pong) e otimizar o tempo.

#### **3.1. Fórmula de Carga Alvo**

Ao chegar em uma estação S\_atual visando um cliente alvo C\_alvo:  
![][image1]Onde:

* E(S\_atual \-\> C\_alvo): Energia para chegar ao cliente.  
* E\_buffer(C\_alvo): Energia para sair do cliente para a estação mais próxima dele (pode ser a própria S\_atual ou outra S\_prox).  
* Margem: 5% da capacidade total (evita erros de arredondamento).

#### **3.2. Cálculo da Recarga (Delta\_E)**

* **Delta\_E \= min(Q,E\_alvo) \- max(0, E\_atual)**  
* **Restrição Física:** Se  E\_alvo \> Q (Capacidade Máxima), o trecho é fisicamente impossível de ser feito com segurança em uma única perna.  
  * **Modo Conservador:** Retorna erro/infinito (gatilho para abrir novo veículo).  
  * **Modo Otimista:** Carrega até Q (100%) e segue (assumindo que violará na volta).

### **4\. Algoritmo de Decodificação (Fluxo Principal)**

O decoder itera sobre a lista de clientes (cromossomo). Para cada Cliente Alvo:

#### **Passo 1: Restrição de Carga (Hard Constraint)**

* Verificar: Carga Atual \+ Demanda \> Capacidade Veículo?  
  * **SIM:** Retornar ao Depósito \-\> Fechar Veículo \-\> Abrir Novo Veículo.

#### **Passo 2: Decisão de Movimento (Gestão de Energia)**

Calculamos duas energias principais:

1. E\_trip: Energia da Posição Atual \-\> Cliente.  
2. E\_safe: Energia do Buffer do Cliente (Cliente \-\> Estação Mais Próxima).

**Árvore de Decisão:**

1. **Check 1: Consigo chegar no Cliente?** (Bat \>= E\_trip)  
   * **NÃO:** O veículo precisa recarregar **AGORA**.  
     * **Ação:** Desviar para Estação Mais Próxima da Atual.  
     * *Ir para Lógica de Chegada na Estação (Ver Seção 4.1).*  
   * **SIM:** O veículo consegue chegar. Mas conseguirá sair? (Look-ahead)  
2. **Check 2 (Look-ahead): Consigo sair do Cliente?** (Bat \>= E\_trip \+ E\_safe)  
   * **SIM:**  
     * **Ação:** Viajar direto para o Cliente.  
   * **NÃO (Risco de Ficar Ilhado):**  
     * **Modo Conservador (True):**  
       * **Ação:** O risco é inaceitável. Desviar para Estação Mais Próxima da Atual (Recarga Preventiva).  
       * *Ir para Lógica de Chegada na Estação.*  
     * **Modo Otimista (False):**  
       * **Ação:** O risco é aceito. Viajar direto para o Cliente.  
       * *Consequência:* O veículo chegará no cliente e ficará ilhado (sem bateria para sair). Isso será resolvido no próximo loop (Passo 3).

#### **Passo 3: Execução do Movimento**

* Atualizar Bateria, Tempo, Distância e Carga.  
* Se chegou no Cliente: Registrar atendimento.

#### **Passo 4: Verificação Pós-Atendimento (Resgate de Ilhados \- Apenas Modo Otimista)**

* *Nota:* Executado imediatamente após atender o cliente, antes de processar o próximo.  
* Verificar: Bat Atual \< Buffer(Local Atual)?  
  * Se SIM, o veículo está ilhado.  
  * **Ação:** Forçar viagem para Estação Mais Próxima do Local Atual.  
  * *Ir para Lógica de Chegada na Estação (com bateria insuficiente).*

### **4.1. Lógica de Chegada na Estação (O Coração da Estratégia)**

Quando o veículo decide (ou é forçado a) ir para uma estação S:

1. Calcula E\_necessaria \= Energia(Local Atual \-\> Estação S).  
2. **Check de Viabilidade de Chegada:**  
   * Bat Atual \>= E\_necessaria?  
     * **SIM:**  
       * Viaja normalmente. Chega com Bat \= Bat \- E\_necessaria.  
     * **NÃO:**  
       * **Modo Conservador (True):**  
         * CRÍTICO: Não consegue chegar nem na estação mais próxima.  
         * **Ação:** Retornar ao Depósito e encerrar rota atual (split). Se não chegar no depósito, penalizar massivamente.  
       * **Modo Otimista (False):**  
         * CRÍTICO: Veículo "morreu" no caminho.  
         * **Ação:** Empurrar o veículo até a estação.  
         * Calcular Déficit \= E\_necessaria \- Bat Atual.  
         * Acumular G2 \+= Déficit.  
         * Viajar fisicamente (somar tempo e distância reais em f1).  
         * Zerar Bat Atual (chegou vazio).  
3. **Execução da Recarga:**  
   * Chamar \_calculate\_smart\_recharge(Bat Atual, S, Proximo\_Cliente).  
   * Atualizar bateria e tempo.  
   * Retornar ao fluxo principal para tentar ir ao Proximo\_Cliente novamente.

### **5\. Tratamento de Edge Cases (Casos de Borda)**

#### **5.1. O Efeito Ioiô (Ping-Pong)**

* **Cenário:** Cliente C2 é remoto. Rota: S1 \-\> C2. O buffer de C2 aponta de volta para S1.  
* **Comportamento:**  
  1. Veículo sai de S1. Smart Recharge carrega o suficiente para ida (S1 \- C2) \+ volta (C2 \-\> S1).  
  2. Vai a C2.  
  3. Ao tentar sair de C2, o decoder verifica o próximo destino. Se não der para chegar, ele vai para a estação mais próxima (S1).  
  4. Rota resultante: S1 \-\> C2 \-\> S1.  
* **Veredito:** Comportamento correto e desejado. O custo extra penaliza a solução, e a evolução decidirá se vale a pena manter C2 nessa rota.

#### **5.2. O Cliente Impossível**

* **Cenário:** Distância(S \-\> C) \+ Distância(C \-\> S) \> Capacidade da Bateria.  
* **Comportamento:**  
  * \_calculate\_smart\_recharge detecta que Total \> Q.  
  * **Modo Conservador:** Retorna sinal de erro. Decoder aborta C e fecha veículo. Novo veículo tenta e também falha. Cliente fica inviável ou isolado em rota única (se permitido).  
  * **Modo Otimista:** Carrega 100%. Vai até C. Chega. Na saída, fica ilhado. Vai para S acumulando violação G2.  
  * **Resultado:** Solução existe, mas carrega uma violação permanente.

#### **5.3. A "Viagem com Dívida"**

* Garante que o Modo Otimista nunca tenha distância menor que o Modo Conservador para a mesma sequência de visitas.  
* Se o conservador faz A \-\> Estação \-\> B e o otimista faz A \-\> B \-\> Estação (Resgate), as distâncias são triangulares e comparáveis. O otimista paga a "multa" G2 por ter arriscado e falhado.

### **6\. Integração Evolutiva**

#### **6.1. Shadow Cost (Custo Sombra)**

Para seleção de sobreviventes inviáveis, a ordenação utiliza:

* Score \= f1 \+ (GAMA \* G2)  
* Isso impede que soluções que acumulam violações massivas (ex: Clientes Impossíveis) dominem a população.  
* GAMA deve ser calibrado para ser comparável ao custo por km (ex: 10x o custo de combustível).

#### **6.2. Mecanismo de Resgate (Rescue)**

Se a população viável cair abaixo de 10%:

1. Selecionar Elite Inviável (pelo Shadow Cost).  
2. Re-decodificar com force\_battery\_feasible=True.  
3. Isso transformará as rotas ... \-\> Cliente \-\> Estação(Resgate) em ... \-\> Estação(Preventiva) \-\> Cliente.  
4. Inserir na população.

### **7\. Resumo da Lógica para Implementação**

def decode\_step(current\_node, target\_node, mode):  
    \# 1\. Check Carga  
    if load\_violation: return SPLIT\_ROUTE

    \# 2\. Check Energia  
    dist\_target \= dist(current, target)  
    dist\_safe \= dist(target, nearest\_station(target))  
      
    \# Lógica de Decisão  
    must\_recharge \= False  
      
    if mode \== CONSERVATIVE:  
        \# Look-ahead rigoroso  
        if battery \< dist\_target \+ dist\_safe:  
            must\_recharge \= True  
    else: \# OPTIMISTIC  
        \# Look-ahead ignorado (vai até o limite)  
        if battery \< dist\_target:  
            must\_recharge \= True \# Não chega nem fisicamente

    \# 3\. Execução  
    if must\_recharge:  
        station \= nearest\_station(current)  
          
        \# Tenta ir para estação  
        if battery \< dist(current, station):  
            if mode \== CONSERVATIVE:  
                return SPLIT\_ROUTE \# Aborta  
            else:  
                \# Modo Otimista: Vai com dívida  
                G2 \+= (dist(current, station) \- battery)  
                battery \= 0  
                add\_route\_step(station) \# Custo real computado  
        else:  
             add\_route\_step(station) \# Vai normal  
               
        \# Recarrega  
        battery \+= smart\_recharge(target, station)  
        current \= station

    \# 4\. Vai para o Cliente  
    \# No modo otimista, se recarregou 100% e ainda não dá, vai com dívida  
    if battery \< dist(current, target):  
         G2 \+= (dist(current, target) \- battery)  
         battery \= 0  
      
    add\_route\_step(target)  
      
    \# 5\. Check Pós-Atendimento (Apenas Otimista)  
    \# Se ficou ilhado no cliente, força saída para estação  
    if mode \== OPTIMISTIC and battery \< dist\_safe:  
         station \= nearest\_station(target)  
         \# Vai com dívida (pois já sabemos que bat \< dist\_safe)  
         G2 \+= (dist(target, station) \- battery)  
         battery \= 0  
         add\_route\_step(station)  
         battery \+= smart\_recharge(next\_target, station)

Este documento encerra a fase de design da heurística. Ele cobre a geometria, a física da bateria e a estratégia evolutiva de forma coesa.

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAmwAAAA4CAYAAABAFaTtAAAAnUlEQVR4Xu3BMQEAAADCoPVPbQwfoAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA4G8e1gABPeyBXAAAAABJRU5ErkJggg==>