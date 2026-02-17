# **Revisão Técnica: Lógica de Recarga e Preservação de Viabilidade**

Este documento detalha as modificações necessárias na lógica de decodificação para suportar corretamente a inserção de estações de recarga e a estratégia para gerar soluções "quase viáveis" (que visitam estações, mas violam limites ou assumem riscos).

## **1\. Nova Lógica do Decoder: Inserção Otimista com Look-ahead**

Para evitar que veículos fiquem "ilhados" nos clientes, o decoder deve verificar não apenas a chegada ao cliente, mas a capacidade de sair dele para uma estação segura.

### **1.1. O Conceito de "Safety Buffer vs. Direção Arriscada"**

A distinção entre os modos será baseada na prudência:

* **Modo Viável:** Usa um **Safety Buffer**. Garante que sempre consegue sair do cliente para uma estação. Nunca fica ilhado.  
* **Modo Inviável:** Ignora o Safety Buffer. Dirige até o limite para chegar ao cliente. Só para para recarregar se não conseguir chegar no destino. Assume o risco de ficar ilhado no cliente.

### **1.2. Algoritmo Proposto para decode()**

O fluxo deve avaliar a **Chegada** (Passo 2\) e a **Saída** (Passo 3).  
Ao tentar ir de Posição Atual para Cliente:  
**PASSO 1: Verificação de Capacidade de Carga (Restrição Hard)**

* Carga \+ Demanda \> Capacidade?  
  * **SIM:** Retornar ao Depósito \-\> Novo Veículo.

**PASSO 2: Verificação de Chegada (Decisão de Ir ao Cliente)**

* **MODO VIÁVEL (force\_feasible=True): Verificação Dupla (Look-ahead)**  
  * Calcular E\_total \= Energia(Atual-\>Cliente) \+ Energia(Cliente-\>Estação\_Mais\_Próxima).  
  * Bateria Atual \>= E\_total?  
    * **SIM:** Vai direto ao cliente.  
    * **NÃO (Risco de ficar ilhado):**  
      * **AÇÃO:** Desvia para Estação AGORA (Preventivo).  
      * Vai para Estação mais próxima da Posição Atual (seguro pois buffer anterior garantiu).  
      * Recarrega.  
      * Segue para o Cliente.  
* **MODO INVIÁVEL (force\_feasible=False): Verificação Simples (Arriscada)**  
  * Calcular apenas E\_viagem \= Energia(Atual-\>Cliente).  
  * Bateria Atual \>= E\_viagem?  
    * **SIM:** Vai direto ao cliente (Ignora se vai ficar ilhado lá).  
    * **NÃO (Impossível chegar fisicamente):**  
      * **AÇÃO:** Tenta ir para Estação (Corretivo).  
      * Seleciona Estação mais próxima da Posição Atual.  
      * Vai fisicamente até a estação (atualiza distância/tempo).  
      * Bateria \>= Energia(Atual-\>Estação)?  
        * *Sim:* Chegada normal.  
        * *Não:* **Chegada com Dívida**. Acumula G2 \+= (Energia\_Nec \- Bateria). Zera Bateria.  
      * Recarrega e segue para o Cliente.

**PASSO 3: Saída do Cliente (Gestão do Risco Assumido)**

* *Nota: Este passo ocorre imediatamente ao tentar sair do cliente para o próximo destino (ou depósito).*  
* Se o veículo chegou ao cliente no **Modo Inviável** "no cheiro" (sem Safety Buffer), ele pode estar com bateria insuficiente para chegar em qualquer lugar.  
* Ao tentar ir para Próximo Destino:  
  * Verificar Bateria Atual.  
  * Se Bateria \< Energia(Cliente \-\> Próxima Estação):  
    * **AÇÃO (Resgate Físico com Dívida):**  
    * O veículo está ilhado.  
    * Seleciona a **Estação mais próxima** do Cliente atual.  
    * **Viaja fisicamente para a estação**:  
      * Adiciona distância e tempo à rota (custo f1 aumenta real).  
      * Calcula energia necessária para a viagem.  
    * **Calcula Violação**:  
      * Déficit \= Energia Necessária \- Bateria Atual.  
      * Acumular Déficit em G2.  
    * **Recarga**:  
      * Zera bateria (virtualmente pagou a dívida com violação).  
      * Executa recarga para continuar a viagem.

### **1.3. Comparação dos Resultados Geométricos**

| Cenário | Decoder Viável (Conservador) | Decoder Inviável (Arriscado) |
| :---- | :---- | :---- |
| **Situação** | Bateria dá para ir ao cliente, mas não sobra para sair dele. | Bateria dá para ir ao cliente, mas não sobra para sair dele. |
| **Ação Imediata** | Detecta risco. **Desvia para estação ANTES** do cliente. | Ignora risco. **Vai até o cliente**. Fica ilhado. |
| **Consequência** | Chega no cliente com tanque cheio (após recarga). | Precisa ir à estação **APÓS** visitar o cliente para poder sair. |
| **Resultado** | Rota: Atual \-\> Estação \-\> Cliente | Rota: Atual \-\> Cliente \-\> Estação (com Dívida) |
| **Custo (f1)** | Paga pela distância real do desvio. | Paga pela distância real do desvio (pós-atendimento). |
| **Violação (G2)** | Zero. | Positiva (Déficit do trajeto Cliente-\>Estação). |

## **2\. Estratégia de Sobrevivência Atualizada**

Com essa mudança, o "Shadow Cost" continua essencial.

### **2.1. Ordenação do Grupo Inviável**

Score \= f1 \+ (gama \* G2)

* O f1 da solução inviável incluirá a viagem de resgate (Cliente \-\> Estação).  
* O f1 da solução viável incluirá a viagem preventiva (Atual \-\> Estação \-\> Cliente).  
* As distâncias são comparáveis. O G2 penaliza o fato de que a solução inviável usou energia que não tinha para chegar na estação de resgate.

### **2.2. Preservação de Viabilidade (Rescue Mechanism)**

**Lógica:**

1. Se len(viáveis) \< 10%:  
2. Pegue os melhores Inviáveis (Arriscados).  
3. "Repare-os": Re-decodificar com force\_feasible=True.  
   * **O que acontece no reparo:** O decoder viável olhará para a mesma sequência de clientes. Quando encontrar o ponto onde o inviável arriscou (e ficou ilhado), o viável detectará a falha no Safety Buffer e inserirá a estação **antes** do cliente.  
   * Isso transforma a rota ... \-\> Cliente \-\> Estação \-\> ... (Inviável) em ... \-\> Estação \-\> Cliente \-\> ... (Viável).  
   * A "mutação" geométrica ocorre naturalmente pela lógica do decoder.

## **3\. Resumo das Ações para Implementação**

1. **Refatorar decoder.py**:  
   * **Implementar check\_safety\_buffer(node)**: Verifica se Bateria \>= Dist(Node, Estação\_Mais\_Proxima).  
   * **Lógica Principal (Pseudo-código)**:  
     \# Antes de ir para o cliente  
     dist\_cli \= dist(atual, cliente)  
     dist\_safe \= dist(cliente, estacao\_prox\_cliente)

     if force\_feasible:  
         \# Modo Viável: Safety Buffer  
         if bateria \< dist\_cli \+ dist\_safe:  
             ir\_para\_estacao\_agora(nearest\_from\_current) \# Recarga Preventiva  
     else:  
         \# Modo Inviável: Sem Buffer  
         if bateria \< dist\_cli:  
             \# Não chega nem no cliente \-\> Vai pra estação agora  
             ir\_para\_estacao\_agora\_com\_divida(nearest\_from\_current)  
         \# Se bateria dá pro cliente, vai (e assume risco)

     ir\_para\_cliente()

     \# Ao sair do cliente (para o próximo loop)  
     if bateria \< dist(cliente, estacao\_prox\_cliente):  
         \# Ficou ilhado \-\> Vai pra estação agora  
         ir\_para\_estacao\_agora\_com\_divida(nearest\_from\_cliente)

2. **Implementar "Viagem com Dívida"**:  
   * Sempre que o veículo precisar ir a uma estação e não tiver bateria:  
     * Adiciona distância e tempo reais à rota.  
     * G2 \+= (Energia\_Nec \- Bateria)  
     * Bateria \= 0  
     * Executa recarga.  
3. **Sobrevivência**:  
   * Manter ordenação por f1 \+ penalty \* G2.  
   * Implementar injeção de viáveis se contagem \< 10%.

Essa abordagem fecha o ciclo lógico: o modo inviável não é apenas "ignorar estações", é "postergar estações até que seja impossível continuar", criando geometrias agressivas que testam os limites da bateria.