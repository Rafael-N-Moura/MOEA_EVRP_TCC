# **Especificação Técnica: Inicialização Híbrida e Gerenciamento de População**

## **1\. Contexto e Objetivos**

Para maximizar a eficácia do *Directed Mating* no Problema de Roteamento de Veículos Elétricos (EVRP), o algoritmo deve operar com uma população mista composta por:

1. **Soluções Conservadoras (Viáveis):** Geradas com Safety Buffer e inserção preventiva de estações. Garantem "chão firme" e factibilidade.  
2. **Soluções Arriscadas (Inviáveis/Otimistas):** Geradas sem Safety Buffer, postergando recargas até o limite físico. Fornecem geometrias de rota eficientes e exploram a fronteira da restrição.

**Objetivo da Estratégia:** Garantir que a população inicial seja composta por exatamente 50% de cada tipo e definir como essa diversidade é mantida organicamente ao longo das gerações.

## **2\. Diagnóstico do Problema de Implementação**

### **2.1. O Erro Encontrado (AttributeError: 'Individual' object has no attribute 'astype')**

Tentativas anteriores de modificar a população *após* a inicialização padrão do Pymoo falharam.

* **Causa:** Ao extrair indivíduos de uma Population existente e tentar reavaliá-los, a estrutura de dados interna do Pymoo (objetos Individual vs arrays numpy) causou conflitos de tipagem no método \_evaluate do problema, que espera receber genótipos brutos (arrays).

### **2.2. A Limitação de Design**

Não é viável manter duas listas separadas (self.pop\_viavel, self.pop\_inviavel) durante a execução, pois isso quebraria a arquitetura interna do NSGA2, que espera uma única população em self.pop para operações de *mating*, *survival* e *display*.

## **3\. Estratégia de Inicialização (Solução do Erro)**

Para evitar conflitos de tipagem e garantir a proporção 50/50, a inicialização deve ser feita **desde o nascimento** dos indivíduos, controlando o fluxo de amostragem e avaliação antes que eles sejam encapsulados na estrutura final da população.

### **3.1. Algoritmo de Inicialização (\_initialize\_advance)**

O método \_initialize\_advance será sobrescrito completamente (sem chamar super()) seguindo este fluxo:

1. **Amostragem Pura:** O Sampling gera N genótipos (cromossomos X) brutos.  
2. **Fissionamento:** O array de genótipos é dividido matematicamente em dois lotes (X\_A e X\_B).  
3. **Encapsulamento Temporário:** Criam-se duas populações virgens (Pop\_A e Pop\_B) contendo apenas os genótipos.  
4. **Avaliação Condicionada:**  
   * **Lote A:** O flag do problema é setado para force\_battery\_feasible \= True. O Evaluator processa Pop\_A. Resultado: Soluções com estações inseridas e ![][image1].  
   * **Lote B:** O flag do problema é setado para force\_battery\_feasible \= False. O Evaluator processa Pop\_B. Resultado: Soluções diretas e ![][image2].  
5. **Fusão:** As duas populações avaliadas são fundidas (Population.merge) em uma única self.pop.

### **3.2. Implementação de Referência**

def \_initialize\_advance(self, infills=None, \*\*kwargs):  
    \# 1\. Amostragem dos Genótipos (X)  
    \# Gera N indivíduos (apenas os vetores de permutação)  
    initial\_pop \= self.sampling.do(self.problem, self.pop\_size, \*\*kwargs)  
    X \= initial\_pop.get("X")  
      
    \# 2\. Divisão Matemática (Slicing de Arrays)  
    n\_feasible \= self.pop\_size // 2  
    X\_feasible \= X\[:n\_feasible\]  
    X\_infeasible \= X\[n\_feasible:\]  
      
    \# 3\. Criação de Sub-populações Virgens  
    pop\_feasible \= Population.new("X", X\_feasible)  
    pop\_infeasible \= Population.new("X", X\_infeasible)  
      
    \# 4\. Avaliação Condicionada (Switching de Contexto)  
    \# Salva estado original para restaurar depois  
    original\_flag \= self.problem.force\_battery\_feasible  
      
    try:  
        \# Avalia Grupo A: Modo Seguro (True)  
        self.problem.force\_battery\_feasible \= True  
        self.evaluator.eval(self.problem, pop\_feasible, \*\*kwargs)  
          
        \# Avalia Grupo B: Modo Arriscado (False)  
        self.problem.force\_battery\_feasible \= False  
        self.evaluator.eval(self.problem, pop\_infeasible, \*\*kwargs)  
          
    finally:  
        \# Restaura estado padrão (Geralmente False para evolução)  
        self.problem.force\_battery\_feasible \= original\_flag  
      
    \# 5\. Fusão na População Principal  
    self.pop \= Population.merge(pop\_feasible, pop\_infeasible)  
      
    \# 6\. Inicialização do Arquivo de Ótimos (Opt)  
    self.\_update\_opt\_custom()

## **4\. Estratégia de Gerenciamento Pós-Inicialização**

Após a geração 0, o algoritmo não mantém listas separadas. A população torna-se **Heterogênea e Implícita**.

### **4.1. Conceito de População Única Heterogênea**

Existe apenas um objeto self.pop. A distinção entre "Viável" e "Inviável" é dinâmica e baseada puramente nos valores de restrição (G) de cada indivíduo naquele instante.

* **Identidade Dinâmica:** Um indivíduo não "é" do tipo A ou B. Ele "está" viável ou inviável. Uma mutação pode transformar um pai inviável em um filho viável e vice-versa.

### **4.2. Ciclo de Vida Evolutivo**

O gerenciamento da proporção e da diversidade ocorre através dos operadores customizados que filtram a população única:

1. **Seleção (Mating):**  
   * O operador DirectedMating recebe self.pop misturado.  
   * Ele aplica uma máscara booleana (pop.G\[:, 1\] \<= 0\) para identificar quem é viável *agora*.  
   * Seleciona um pai de cada grupo (cruzamento direcionado).  
2. **Reprodução e Avaliação:**  
   * Os filhos são gerados e avaliados **sempre no modo False (Arriscado)**.  
   * *Justificativa:* Não forçamos o comportamento dos filhos. Se eles herdaram a genética "segura" (visitas a estações), serão viáveis naturalmente. Se herdaram a "ousadia", serão inviáveis.  
3. **Sobrevivência (Survival):**  
   * O operador InfeasibleSurvival recebe a população expandida (Pais \+ Filhos).  
   * Ele aplica novamente a máscara para separar os grupos.  
   * **Gestão de Cotas:** Garante que X% da próxima geração venha do grupo viável e Y% do grupo inviável.  
   * **Mecanismo de Resgate:** Se o grupo viável estiver em extinção (\<10%), ele ativa o "Reparo de Emergência" (reavaliando os melhores inviáveis com force=True) para reinjetar viabilidade.

### **4.3. Resumo do Fluxo**

| Etapa | Estado da População | Ação de Gerenciamento |
| :---- | :---- | :---- |
| **Geração 0** | Separada artificialmente | Avaliação forçada 50% True / 50% False. |
| **Geração 1+** | Misturada | Avaliação padrão (False). |
| **Mating** | Virtualmente Separada | Seleção cruzada baseada em G2. |
| **Survival** | Virtualmente Separada | Corte por cotas e injeção de viabilidade (se necessário). |

Esta abordagem resolve os erros técnicos (tipagem) e alinha o algoritmo com a filosofia de design do Pymoo, onde a inteligência está nos operadores, não na estrutura de dados.

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADoAAAAYCAYAAACr3+4VAAAAHElEQVR4Xu3BAQ0AAADCoPdPbQ43oAAAAAAAeDIV2AAB+NqtVQAAAABJRU5ErkJggg==>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADoAAAAYCAYAAACr3+4VAAACAklEQVR4Xu2XPUgcURSFrwr+BUUsBAlYCDYBTWERtFHQQrAIpDBVREwKiQjpgoVIEGxsrARBsLAL0U4RxDIkCEIikoBKQkhhIQRREEElnst7o3fve7M7s7skuzoffKzvnJ2Z93Z+3CVKSLiTPIRv4DxsFnmn+LuoWYJ/4T7shy1wDh7CDtsVIhPwBJ7Bl6pz4EVcwAe6AONk+h1dxGQbHsAqXeTAN7ghxrvwoxincEmZzxb3z3SYJatkzkCjLmJSS/55c1anw2NblOlC4dthriyQ+ZDbdBGRL+SfF2e87xtabfhLhiH4dpgvpsjsv08XGeBtfPNy8isb1MjwP/KazHxe6CIEZ0EWJ3eCAmCazJyqdeEhbP5O7gSCp7AHdsFu2Eup9/EymW35KZrp/o7CIpmn/iNdpCFs/k7OgyMZCEbhJN1u9BaW2m4zeBMYJv/BorJO5oHYoIsIOAuyOLkTeOB+z5N9VuM49zlfAV/hT1ipujickn/+nH2XAf+z5bBChoIxMv1zXQj4LPsO5oMX9Rt+giWqy4YB8h+bs3ZfyAaXZUCT6NLxg8x34ii810Ee4PmNiPGMzbzwPRcs6o99fWe7D8GbPAzCWR3+Y/jrJM93i8ztcE75uVpueEy3n2Q5hV/+RU09XIFD8BVcS2nD4V9EUS0IgstcGoUnMUxISLgHXAM1zolM9uhtMwAAAABJRU5ErkJggg==>