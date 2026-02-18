# **Plano de Implementação: Probabilidade Dinâmica de Reparo (Dynamic Repair)**

## **1\. Contexto e Motivação**

Até o momento, o algoritmo BatteryFocusedNSGA2 demonstrou capacidade de superar o NSGA-II padrão (Baseline), alcançando um custo viável de **4842** contra **4905** (melhoria de \~1.3%).  
No entanto, observamos nos logs que a população inviável (Modo Otimista) encontra geometrias ainda melhores (custo **4795**), mas o algoritmo falha em converter esse potencial total para a população viável.  
**O Diagnóstico:** Atualmente, a probabilidade de reparo (repair\_prob) é fixa em **0.5 (50%)**.

* Isso significa que, mesmo na Geração 99, metade dos esforços computacionais ainda é gasta tentando encontrar novas soluções inviáveis (Exploração), quando deveríamos estar focados em "legalizar" as melhores geometrias encontradas (Explotação).

**A Solução:** Implementar uma **Taxa de Reparo Dinâmica** que cresce linearmente com o progresso das gerações.

* **Início:** Foco em Inviabilidade (Exploração).  
* **Fim:** Foco em Viabilidade (Convergir para o ótimo real).

## **2\. A Estratégia Dinâmica**

A probabilidade de um filho ser avaliado no Modo Viável (force=True) deixará de ser estática e seguirá uma função linear baseada na geração atual.

### **Fórmula**

P\_{repair}(t) \= P\_{start} \+ \\left( \\frac{t}{T\_{max}} \\right) \\times (P\_{end} \- P\_{start})

Onde:

* t: Geração atual (n\_gen).  
* T\_{max}: Número máximo de gerações.  
* P\_{start}: Probabilidade inicial (Sugerido: **0.1** ou 10%).  
* P\_{end}: Probabilidade final (Sugerido: **0.9** ou 90%).

### **Comportamento Esperado**

1. **Geração 0-20:** P\_{repair} \\approx 0.1 \\to 0.25. A população será inundada de soluções inviáveis agressivas. O "Arquivo de Inviáveis" descobrirá atalhos geométricos rapidamente.  
2. **Geração 20-80:** Transição. O algoritmo começa a equilibrar a busca.  
3. **Geração 80-100:** P\_{repair} \\approx 0.75 \\to 0.9. Quase todos os filhos gerados passarão pelo Decoder Conservador. Isso pegará as melhores sequências inviáveis sobreviventes e inserirá estações nelas, massificando a população viável com rotas otimizadas.

       