# **Plano de Correção: Implementação de Reparo Lamarckiano e Ajuste de Shadow Cost**

## **1\. Diagnóstico do Problema**

A análise dos logs de execução (battery\_focused\_nsga2\_rc208\_21\_20260217\_102449.txt) revelou uma falha crítica na dinâmica evolutiva do algoritmo, caracterizada pelo fenômeno de **"Estagnação da População Viável"**.

### **1.1. Evidências (Logs)**

* **Geração 0:** População Viável tem custo mínimo de **6883.3**.  
* **Geração 100:** População Viável mantém custo mínimo de **6883.3**.  
* **População Inviável:** Evoluiu significativamente (Custo caiu de 6579 para 5821), mas acumulou violação (G2 subiu de 66 para 97).

### **1.2. Causa Raiz**

O método \_advance estava configurado para avaliar **100% dos filhos** no Modo Otimista (force\_battery\_feasible=False).

1. Como o Modo Otimista ignora o *Safety Buffer*, os filhos tendem a consumir toda a bateria e acumular pequenas dívidas energéticas (G2 \> 0).  
2. Consequentemente, quase nenhum filho nasce estritamente viável (G2 \= 0).  
3. O operador de Sobrevivência (Elitismo) preserva os pais viáveis da Geração 0 porque eles dominam os filhos no critério de viabilidade, impedindo a renovação da população segura.

## **2\. Estratégia de Solução: Reparo Probabilístico (Lamarckiano)**

Para transferir o material genético de alta qualidade (geometria de rota) da população inviável para a viável, implementaremos um mecanismo de **Reparo Probabilístico** durante a avaliação dos filhos.

### **2.1. Conceito**

Ao invés de deixar a genética decidir sozinha a viabilidade, o algoritmo forçará o fenótipo de uma parcela dos filhos a se adaptar às restrições de segurança.

* **Genótipo (Herdado):** Sequência de clientes otimizada (vinda do cruzamento Viável x Inviável).  
* **Fenótipo Reparado:** O Decoder, operando em modo True, inserirá recargas preventivas nessa sequência, transformando uma rota "arriscada" em uma rota "segura e eficiente".

### **2.2. Mecânica**

* **Probabilidade de Reparo (P\_repair):** 50% (0.5).  
* **Fluxo:**  
  * 50% dos filhos são avaliados com force\_battery\_feasible=True (Tentativa de gerar novos Viáveis).  
  * 50% dos filhos são avaliados com force\_battery\_feasible=False (Exploração de novos limites Inviáveis).

### **4\. Alterações no Shadow Cost**

Ajuste na calibração do **Shadow Cost** para evitar que violações baratas dominem a população inviável.

#### **Diagnóstico Econômico**

Atualmente, economizar R$ 1000 custa 100 unidades de violação (G2). Isso dá uma taxa de R$ 10/unidade. Se o gamma for baixo (ex: 5.0), o algoritmo prefere violar.

#### **Alteração Recomendada**

Aumentar a severidade da punição para garantir que a solução inviável só sobreviva se for geometricamente excepcional.  
\# Dentro do método de cálculo do Shadow Cost (ou \_rank\_infeasible)  
\# Aumentar de 5.0 (ou valor atual) para 20.0 ou mais.

severity\_multiplier \= 20.0  \# Aumentado para desencorajar violações triviais  
gamma \= base\_energy\_cost \* severity\_multiplier

