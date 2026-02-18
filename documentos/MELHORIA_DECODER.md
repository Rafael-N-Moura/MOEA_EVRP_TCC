# **Especificação Técnica: Decodificador Híbrido para EVRPTW-PR**

## **Estratégia de Relaxamento de Restrições e Recarga Parcial Inteligente**

### **1\. Visão Geral e Fundamentação Teórica**

Esta especificação define o comportamento do algoritmo de mapeamento Genótipo-Fenótipo (Decoder) utilizado no BatteryFocusedNSGA2. A abordagem utiliza **Relaxamento de Restrições (Constraint Relaxation)** e uma heurística de **Smart Detour** (Desvio Inteligente).

#### **1.1. Dualidade de Modos**

O decoder opera em dois modos distintos, controlados pela flag force\_battery\_feasible:

1. **Modo Conservador (True):** Garante viabilidade estrita (G2 \= 0). Utiliza **Look-ahead (Safety Buffer)** baseado na estação mais próxima para garantir sobrevivência. Insere recargas preventivas utilizando a heurística de menor desvio geométrico.  
2. **Modo Otimista/Arriscado (False):** Permite inviabilidade (G2 \>= 0). Ignora o Safety Buffer na decisão de visita. Se a bateria acabar, utiliza a mesma heurística de menor desvio para o "Resgate", mas computa a distância física percorrida e penaliza o déficit energético em G2.

### **2\. Definições Críticas**

* **Safety Buffer (Sobrevivência):** A energia mínima necessária para não ficar ilhado. Calculada sempre em relação à **Estação Mais Próxima Absoluta**.  
  * *Justificativa:* Usar a "Melhor Estação Geométrica" aqui seria conservador demais, pois abortaria rotas viáveis que apenas não conseguem alcançar a estação ótima.  
* **Smart Detour (Otimização):** Ao decidir onde recarregar, o algoritmo busca a estação que minimiza o desvio triangular (Origem \-\> Estação \-\> Destino), respeitando a autonomia atual.  
* **Dívida Energética (G2):** Energia utilizada "além de zero". O veículo viaja fisicamente, mas a bateria virtual fica negativa.

### **3\. Lógica de Recarga Parcial**

A recarga visa o próximo trecho imediato \+ a segurança subsequente.

#### **Fórmula de Carga Alvo**

Ao chegar em uma estação S\_atual visando um cliente alvo C\_alvo:

* E\_{alvo} \= E(S\_{atual} \\to C\_{alvo}) \+ E\_{buffer\\\_survival}(C\_{alvo}) \+ {Margem}

* Recarrega o suficiente para chegar no cliente e sobreviver (alcançar a estação mais próxima dele).

### **4\. Algoritmo de Decodificação (Fluxo Principal)**

#### **Passo 1: Restrição de Carga (Hard Constraint)**

* Verificar Capacidade de Carga. Se violar, split da rota (Novo Veículo).

#### **Passo 2: Decisão de Movimento (Gestão de Energia)**

1. **Check 1 (Chegada Física):** Consigo chegar no Cliente?  
   * **NÃO:** Precisa recarregar AGORA.  
     * **Ação:** Chamar get\_best\_station(Atual, Cliente).  
     * *Nota:* No modo viável, escolhe a melhor alcançável. No inviável, escolhe a melhor absoluta (assumindo dívida).  
2. **Check 2 (Look-ahead/Saída):** Consigo sair do Cliente para a estação mais próxima dele?  
   * **Modo Conservador:** Se NÃO, risco inaceitável. Desvia para recarga AGORA.  
   * **Modo Otimista:** Se NÃO, aceita o risco. Vai para o cliente (ficará ilhado).

#### **Passo 3: Execução e Resgate**

* Executa movimento.  
* **Apenas Modo Otimista:** Se ficou ilhado no cliente, chama get\_best\_station(Cliente, Proximo\_Destino) para realizar o resgate com dívida.

### **5\. Tratamento de Casos Especiais**

* **Fallback de Estação:** A função de seleção de estação tenta a "Melhor Geométrica". Se a bateria não alcançar, ela faz fallback automático para a "Mais Próxima Alcançável". Se nenhuma for alcançável (Modo Viável Crítico), o decoder aborta a rota.  
* **Justiça Comparativa:** A lógica Smart Detour é aplicada tanto no NSGA-II padrão quanto no modificado, garantindo que a vantagem venha da estratégia evolutiva, não da heurística.