# **Reformulação Teórica: The Bounded Infeasible Archive (IDEA)**

## **1\. Fundamentação Teórica (Baseado em C-TAEA e IDEA)**

De acordo com a literatura de otimização multiobjetivo com restrições severas (CMOPs), a exploração do espaço inviável deve ser controlada para evitar a degradação da busca.

* **O Erro Anterior:** Permitir soluções com alta Violação de Restrição (G2). Tais soluções sofrem mutações catastróficas ao serem submetidas a operadores de reparo, invalidando a premissa memética de que "genótipos inviáveis próximos geram fenótipos viáveis próximos".  
* **A Abordagem Proposta:** Implementar um **Arquivo Inviável Delimitado (epsilon-constrained)**. Apenas indivíduos que violam a restrição dentro de uma margem epsilon estreita são preservados. Dentro desta margem, a avaliação bi-objetivo (f1,f2) é considerada "honesta o suficiente", permitindo a ordenação por dominância de Pareto padrão (NSGA-II) para maximizar a diversidade (Hipervolume).

## **2\. A Mecânica do Filtro (Epsilon Bound)**

Seja Q a capacidade total da bateria do veículo.  
Definimos a tolerância máxima de violação epsilon\_{max} \= Q \\times 0.15 (15%).  
Se uma solução avaliada com force\_battery\_feasible=False resultar em G\_2 \> epsilon\_{max}, ela é considerada **Lixo Evolutivo** (irreparável sem destruição do fenótipo) e é sumariamente descartada.  
Se 0 \< G\_2 \<= epsilon\_{max}, a solução entra para a "Zona de Promessa Inviável".

## **3\. Sobrevivência Multiobjetivo no Arquivo Inviável**

Uma vez filtradas as soluções pela fronteira epsilon:

1. O *Shadow Cost* é abandonado.  
2. A seleção dos 25% sobreviventes inviáveis é feita utilizando o operador *Rank and Crowding* padrão do NSGA-II, avaliando exclusivamente os objetivos (f1,f2).  
3. Isso garante espalhamento ao longo da fronteira (aumentando o f2 e o Hipervolume geral), mas garantindo que todas as soluções armazenadas são "quase viáveis" e facilmente reparáveis no próximo ciclo.

## **4\. Implementação (Alterações em battery\_focused\_nsga2.py)**

A alteração ocorre exclusivamente na classe InfeasibleSurvival. Devemos reverter as alterações anteriores (Shadow Cost / Recarga Fantasma) e aplicar este filtro limpo.  
from pymoo.core.survival import Survival  
from pymoo.core.population import Population  
from pymoo.operators.survival.rank\_and\_crowding import RankAndCrowding  
import numpy as np

class InfeasibleSurvival(Survival):  
    def \_\_init\_\_(self, infeasible\_ratio=0.25, max\_violation\_ratio=0.15):  
        """  
        :param infeasible\_ratio: Porcentagem da população que deve ser inviável (ex: 25%)  
        :param max\_violation\_ratio: Tolerância máxima de violação G2 (ex: 15% da bateria total)  
        """  
        super().\_\_init\_\_(filter\_infeasible=False)  
        self.infeasible\_ratio \= infeasible\_ratio  
        self.max\_violation\_ratio \= max\_violation\_ratio  
        self.survival\_feasible \= RankAndCrowding()  
        self.survival\_infeasible \= RankAndCrowding() \# Usa Pareto padrão para inviáveis\!

    def \_do(self, problem, pop, n\_survive, \*\*kwargs):  
        \# 1\. Extrai G2 (Violação de Bateria)  
        G \= pop.get("G")  
        is\_feasible \= G\[:, 1\] \<= 1e-5  
          
        pop\_feas \= pop\[is\_feasible\]  
        pop\_inf \= pop\[\~is\_feasible\]  
          
        n\_inf\_target \= int(n\_survive \* self.infeasible\_ratio)  
        survivors\_inf \= Population()  
          
        \# 2\. Lógica para Inviáveis (The Bounded Archive)  
        if len(pop\_inf) \> 0:  
            \# Pega a capacidade da bateria do contexto do problema  
            \# Se não estiver acessível facilmente, podemos passar via kwargs ou inferir.  
            \# Assumindo acesso ao context:  
            battery\_cap \= problem.context.battery\_capacity  
            max\_g2\_allowed \= battery\_cap \* self.max\_violation\_ratio  
              
            \# FILTRO EPSILON: Mantém apenas os "quase viáveis"  
            acceptable\_inf\_mask \= pop\_inf.get("G")\[:, 1\] \<= max\_g2\_allowed  
            pop\_inf\_acceptable \= pop\_inf\[acceptable\_inf\_mask\]  
              
            if len(pop\_inf\_acceptable) \<= n\_inf\_target:  
                \# Se após o filtro temos menos do que a cota, levamos todos  
                survivors\_inf \= pop\_inf\_acceptable  
            else:  
                \# Se temos muitos "quase viáveis", usamos RankAndCrowding (Pareto f1, f2)  
                \# O Pymoo RankAndCrowding já usa pop.get("F"), então ele vai olhar  
                \# para o f1 e f2 originais. É perfeito.  
                survivors\_inf \= self.survival\_infeasible.\_do(  
                    problem, pop\_inf\_acceptable, n\_inf\_target, \*\*kwargs  
                )  
                  
        \# 3\. Lógica para Viáveis (Preenche o resto)  
        n\_feas\_target \= n\_survive \- len(survivors\_inf)  
          
        if len(pop\_feas) \> 0:  
            if len(pop\_feas) \<= n\_feas\_target:  
                survivors\_feas \= pop\_feas  
            else:  
                survivors\_feas \= self.survival\_feasible.\_do(  
                    problem, pop\_feas, n\_feas\_target, \*\*kwargs  
                )  
        else:  
            survivors\_feas \= Population()

        \# 4\. Merge Final  
        survivors \= Population.merge(survivors\_feas, survivors\_inf)  
          
        \# Caso extremo de falta de indivíduos (fallback de segurança)  
        if len(survivors) \< n\_survive:  
             \# Completa com inviáveis rejeitados pelo filtro se for ABSOLUTAMENTE necessário  
             shortage \= n\_survive \- len(survivors)  
             rejected\_inf \= pop\_inf\[\~acceptable\_inf\_mask\]  
             if len(rejected\_inf) \> 0:  
                 \# Usa os menos piores em violação  
                 sorted\_rej \= np.argsort(rejected\_inf.get("G")\[:, 1\])  
                 survivors \= Population.merge(survivors, rejected\_inf\[sorted\_rej\[:shortage\]\])

        return survivors

