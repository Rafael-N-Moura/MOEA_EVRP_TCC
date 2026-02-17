# **Relatório de Diagnóstico: Explosão Populacional no NSGA-II Customizado**

## **1\. O Problema Identificado**

A análise dos logs de execução revelou a causa raiz tanto da lentidão quanto da baixa qualidade das soluções encontradas pela variante *Directed Mating*.

### **Evidência (Logs)**

* **NSGA-II Padrão:** Tamanho da população final: 100 (Correto)  
* **Sua Implementação:** Tamanho da população final: 10000 (**Erro Crítico**)

### **Análise do Erro**

Em Algoritmos Evolutivos, o operador de **Sobrevivência (Survival)** tem um contrato estrito: ele deve receber uma população combinada de Pais \+ Filhos (geralmente tamanho 2\) e selecionar os N melhores para compor a próxima geração.  
Sua implementação atual não está realizando o "corte" (truncagem). Ela está permitindo que todos (ou a maioria) dos indivíduos sobrevivam de uma geração para a outra. Como o algoritmo rodou por 100 gerações com uma população base de 100, ele acumulou indivíduos até atingir 10.000 (100 \* 100).

### **Consequências no Desempenho**

1. **Lentidão Extrema:** O tempo de execução saltou de 34s para 82s (e só não foi pior porque o Python é eficiente). Algoritmos de ordenação como *Non-Dominated Sorting* têm complexidade quadrática  O(Nˆ2) ou log-linear O(N log N). Processar 10.000 indivíduos é centenas de vezes mais lento que processar 100\.  
2. **Degradação da Qualidade (Custo 6900 vs 5500):** A evolução depende da **Pressão de Seleção**. Para evoluir, os indivíduos ruins *precisam morrer*.  
   * Como ninguém estava morrendo, soluções com custo alto e inviabilidade alta permaneceram na população, diluindo os bons genes.  
   * O algoritmo se comportou como uma "Busca Aleatória" (Random Search) que apenas acumulava novas tentativas, sem refinar as existentes.

## **2\. A Solução Proposta: Implementação de Cotas Rígidas**

Para corrigir isso, a classe Survival deve ser reescrita para garantir matematicamente que a saída tenha exatamente o tamanho pop\_size (ex: 100).

### **A Lógica Correta (Algoritmo de Sobrevivência Híbrida)**

O novo fluxo de sobrevivência deve seguir rigorosamente estes passos a cada geração:

#### **Passo 1: Separação**

Dividir a população combinada (Pais \+ Filhos, total 2N) em dois grupos:

1. **Grupo Viável:** Indivíduos com G \<= 0  (Respeitam bateria).  
2. **Grupo Inviável:** Indivíduos com G \> 0  (Violam bateria).

#### **Passo 2: Definição de Cotas**

Definir quantas vagas cada grupo terá na próxima geração de tamanho N (ex: N \= 100).

* **Cota Inviável (Ninf):** int(pop\_size \* infeasible\_ratio) (Ex: 30 vagas).  
* **Cota Viável (Nfeas):** O restante (Ex: 70 vagas).

#### **Passo 3: Seleção Elite (O "Corte")**

**Para o Grupo Viável:**

* Se houver mais candidatos que vagas (\>70), utilizar o método padrão **Rank & Crowding Distance** para selecionar os 70 melhores. Isso preserva a fronteira de Pareto e a diversidade.  
* Se houver menos, selecionar todos e passar as vagas excedentes para o grupo inviável.

**Para o Grupo Inviável (A Inovação do TCC):**

* **Critério de Seleção:** Aqui não usamos Pareto. Usamos **Elite por Objetivo Único**.  
* Devemos ordenar o Grupo Inviável com base no **Custo (f1)**.  
* Selecionar apenas os Top-30 (ou quantos couberem na cota) que tiverem o menor custo.  
* *Justificativa:* Soluções inviáveis só são úteis se forem excepcionalmente baratas (poucos veículos/curta distância). Uma solução inviável E cara é lixo genético e deve ser descartada imediatamente.

#### **Passo 4: Fusão Final**

Combinar os selecionados dos dois grupos.

* **Verificação de Segurança:** Se len(selecionados) \> pop\_size, truncar a lista. Se len \< pop\_size, completar com indivíduos aleatórios (raro, mas evita crash).

## **3\. Resultados Esperados Pós-Correção**

Ao implementar essa lógica de corte rígido, esperamos observar:

1. **Tempo de Execução:** Deve cair drasticamente (de 82s para \~40-50s), aproximando-se do NSGA-II padrão, pois voltaremos a ordenar apenas 100/200 indivíduos por vez.  
2. **Qualidade da Solução:** O custo (f1) deve cair significativamente. Ao matar as soluções ruins a cada geração, forçamos os sobreviventes (mesmo os inviáveis) a serem de alta qualidade, restaurando a pressão evolutiva.  
3. **Convergência:** O gráfico de hipervolume deve mostrar uma curva ascendente consistente, provando que o algoritmo está aprendendo.