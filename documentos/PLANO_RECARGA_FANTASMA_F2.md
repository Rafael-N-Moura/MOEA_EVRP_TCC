# **Otimização Multiobjetivo Estrita: O Mecanismo de "Recarga Fantasma"**

## **1\. O Problema da Avaliação Temporal Assíncrona**

No EVRPTW, a omissão de uma visita a uma estação de recarga no modo inviável (Constraint Relaxation) produz dois efeitos distintos:

1. **Efeito Espacial (Desejado):** Reduz a distância percorrida (f1), revelando a sequência geométrica ótima dos clientes.  
2. **Efeito Temporal (Indesejado/Ilusório):** Antecipa o horário de chegada a todos os clientes subsequentes, mascarando os atrasos reais e gerando um valor de satisfação (f2) falsamente otimizado. Ao ser reparada, a inserção da estação gera propagação de atraso (delay propagation), destruindo o f2.

## **2\. A Solução: Recarga Fantasma (Ghost Recharge)**

A solução consiste em desacoplar o espaço do tempo no modelo de avaliação inviável.  
Permite-se a violação espacial (o veículo não viaja até à estação), mas impõe-se a consistência temporal (o relógio do veículo avança como se tivesse carregado a energia deficitária).

### **2.1. Lógica Matemática**

Quando um veículo no modo force\_battery\_feasible \= False avança para o alvo com bateria insuficiente para garantir o *Safety Buffer*:

1. Calcula-se a energia "em dívida": E\_{divida} \= (E\_{viagem} \+ E\_{buffer}) \- Bateria\_{atual}  
2. Calcula-se o tempo fantasma de recarga: T\_{ghost} \= E\_{divida} / Taxa\\\_Recarga  
3. Adiciona-se T\_{ghost} ao current\_time **antes** de calcular o atraso no cliente.

Desta forma, se uma solução inviável apresentar um bom f2, é porque a sequência de clientes é genuinamente resiliente a atrasos, e não porque o veículo "viajou no tempo".

## **3\. Implementação Técnica**

### **Parte 1: Ajuste no Decoder (src/decoder.py)**

No bloco onde o veículo decide avançar para o cliente.  
**Onde alterar:** Dentro de move\_to\_node, logo antes de calcular a chegada ao target\_node.  
\# ... (código existente do decoder) ...  
\# \--- EXECUÇÃO DO MOVIMENTO FINAL PARA O ALVO \---  
dist\_target \= current\_node.distance\_to(target\_node)  
travel\_time \= dist\_target / context.velocity

\# NOVA LÓGICA: RECARGA FANTASMA (Apenas Modo Inviável)  
ghost\_time\_penalty \= 0.0

if not force\_battery\_feasible:  
    \# Verifica se o veículo "saltou" uma recarga que seria obrigatória no modo viável  
    energy\_needed\_total \= energy\_trip \+ energy\_buffer\_dest  
      
    if current\_battery \< energy\_needed\_total:  
        \# Calcula a energia que ele 'deveria' ter carregado para estar seguro  
        energy\_debt \= energy\_needed\_total \- current\_battery  
        \# Converte essa dívida em tempo de recarga (simulação)  
        ghost\_time\_penalty \= energy\_debt / context.recharge\_rate

\# Aplica o tempo fantasma ao relógio ANTES de chegar ao cliente  
arr\_time \= current\_time \+ travel\_time \+ ghost\_time\_penalty  
arrival\_battery \= current\_battery \- energy\_trip

\# ... (restante do código: cálculo de atraso, start\_service, etc) ...  
