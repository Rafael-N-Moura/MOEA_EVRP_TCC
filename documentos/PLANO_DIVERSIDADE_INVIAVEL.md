# **Plano de Melhoria: Sobrevivência Multiobjetivo no Arquivo de Inviáveis**

## **1\. O Problema da "Miopia de Custo"**

A análise dos resultados estatísticos mostrou que o algoritmo BatteryFocused é um "Especialista em Custo" (f1), mas falha em manter a diversidade da fronteira de Pareto (f2), resultando em baixo Hipervolume.  
**Causa Raiz:** O operador InfeasibleSurvival utiliza uma classificação escalar baseada no *Shadow Cost* (f1 \+ GAMMA \* G2). Isso ignora completamente o valor do objetivo f2 (Satisfação). Soluções que exploram inviabilidade para atender melhor as janelas de tempo (mas custam mais caro) são descartadas sumariamente.

## **2\. A Solução: Pareto Penalizado**

Para restaurar a diversidade e melhorar o Hipervolume, o critério de sobrevivência dos inviáveis deve considerar o trade-off entre Custo Penalizado e Satisfação.

### **2.1. Lógica Proposta**

Ao selecionar os N sobreviventes do Grupo Inviável:

1. **Construção dos Objetivos Virtuais (F\_virt):**  
   * Para cada indivíduo i:  
     * Obj\_1 \= f\_1,i \+ (GAMMA \* G\_2,i  
     * Obj\_2 \= f\_2,i  
2. **Classificação Não-Dominada (NDS):**  
   * Aplicar o algoritmo de *Non-Dominated Sorting* sobre F\_virt.  
   * Isso identificará "Frentes de Pareto Inviáveis".  
   * A Frente 1 conterá tanto os "Inviáveis mais baratos" quanto os "Inviáveis mais pontuais".  
3. **Seleção por Crowding Distance:**  
   * Se houver mais indivíduos na frente do que vagas, usar a distância de aglomeração para manter a diversidade *dentro* do espaço inviável.

## **3\. Implementação Técnica (src/battery\_focused\_nsga2.py)**

Alterar o método \_do da classe InfeasibleSurvival.

### **Código Antigo (Escalar)**

\# (Simplificado)  
shadow\_costs \= F\[:, 0\] \+ (gamma \* G\[:, 1\])  
sorted\_idx \= np.argsort(shadow\_costs)  
survivors \= pop\[sorted\_idx\[:n\_select\]\]

### **Código Novo (Pareto)**

Precisamos importar o RankAndCrowding para usar internamente.  
from pymoo.util.nds.non\_dominated\_sorting import NonDominatedSorting  
from pymoo.util.crowding\_distance import calculate\_crowding\_distance  
from pymoo.operators.survival.rank\_and\_crowding import RankAndCrowding

class InfeasibleSurvival(Survival):  
    def \_\_init\_\_(self, infeasible\_ratio=0.25):  
        super().\_\_init\_\_(filter\_infeasible=False)  
        self.infeasible\_ratio \= infeasible\_ratio  
        \# RankAndCrowding padrão para o grupo viável  
        self.survival\_feasible \= RankAndCrowding() 

    def \_do(self, problem, pop, n\_survive, \*\*kwargs):  
        \# 1\. Separação (Igual ao atual)  
        G \= pop.get("G")  
        \# Considera viável se G2 (Bateria) \<= epsilon  
        is\_feasible \= G\[:, 1\] \<= 1e-5  
          
        pop\_feas \= pop\[is\_feasible\]  
        pop\_inf \= pop\[\~is\_feasible\]  
          
        \# 2\. Definição de Cotas (Igual ao atual)  
        n\_inf\_target \= int(n\_survive \* self.infeasible\_ratio)  
          
        \# Se não tem inviáveis suficientes, pega todos eles  
        if len(pop\_inf) \< n\_inf\_target:  
            survivors \= pop\_inf  
            n\_remaining \= n\_survive \- len(pop\_inf)  
            \# Completa o resto com viáveis  
            if len(pop\_feas) \> 0:  
                survivors \= Population.merge(survivors, self.survival\_feasible.\_do(problem, pop\_feas, n\_remaining))  
          
        else:  
            \# Caso padrão: Temos inviáveis sobrando. Precisamos filtrar.  
              
            \# \--- AQUI MUDA A LÓGICA \---  
              
            \# 1\. Prepara Objetivos Virtuais para os Inviáveis  
            F\_inf \= pop\_inf.get("F")  
            G\_inf \= pop\_inf.get("G")  
              
            \# Contexto para Gamma (Você pode pegar do problem ou fixar)  
            \# Exemplo fixo ou calculado  
            gamma \= 5.0 \# Mantenha o valor que estava funcionando (2.0 ou 5.0)  
              
            \# Cria matriz (N, 2\)  
            \# Coluna 0: Custo Penalizado  
            \# Coluna 1: Insatisfação Original (f2)  
            F\_penalized \= np.column\_stack(\[  
                F\_inf\[:, 0\] \+ (gamma \* G\_inf\[:, 1\]),  
                F\_inf\[:, 1\]  
            \])  
              
            \# 2\. Aplica Rank & Crowding "Manual" nestes objetivos virtuais  
            \# Usamos a classe RankAndCrowding do pymoo, mas "enganamos" ela   
            \# passando F\_penalized como se fossem os objetivos reais.  
              
            \# Hack: Criamos uma população temporária apenas para ordenação  
            pop\_temp \= Population.new("F", F\_penalized)  
            \# Copia outros atributos para manter a integridade se necessário,   
            \# mas RankAndCrowding só olha para F.  
              
            \# O Survival retorna os índices ou a população filtrada  
            \# Mas o RankAndCrowding.\_do espera 'problem' para saber n\_obj, etc.  
            \# Vamos fazer manualmente via NDS para ter controle total.  
              
            nds \= NonDominatedSorting()  
            fronts \= nds.do(F\_penalized)  
              
            selected\_inf\_indices \= \[\]  
              
            for front in fronts:  
                if len(selected\_inf\_indices) \+ len(front) \<= n\_inf\_target:  
                    selected\_inf\_indices.extend(front)  
                else:  
                    \# Frente de corte (precisa de Crowding Distance)  
                    n\_missing \= n\_inf\_target \- len(selected\_inf\_indices)  
                      
                    \# Calcula crowding distance apenas para essa frente usando F\_penalized  
                    crowding\_of\_front \= calculate\_crowding\_distance(F\_penalized\[front\])  
                      
                    \# Ordena por CD descendente  
                    sorted\_front \= np.argsort(crowding\_of\_front)\[::-1\]  
                    best\_of\_front \= \[front\[i\] for i in sorted\_front\[:n\_missing\]\]  
                      
                    selected\_inf\_indices.extend(best\_of\_front)  
                    break  
              
            survivors\_inf \= pop\_inf\[selected\_inf\_indices\]  
              
            \# 3\. Completa com Viáveis  
            n\_feas\_target \= n\_survive \- len(survivors\_inf)  
            if len(pop\_feas) \> 0:  
                survivors\_feas \= self.survival\_feasible.\_do(problem, pop\_feas, n\_feas\_target)  
                survivors \= Population.merge(survivors\_inf, survivors\_feas)  
            else:  
                survivors \= survivors\_inf

        return survivors  
