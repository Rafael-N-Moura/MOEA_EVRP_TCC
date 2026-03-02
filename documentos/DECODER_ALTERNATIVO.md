Vou gerar um documento detalhado sobre a estratégia de heurística de construção/decodificação de rotas que seja coerente com o contexto de EVRPTW-PR e com a necessidade de gerar inviáveis "úteis" de forma controlada.

***

# Estratégia de Heurística de Construção de Rotas para NSGA-II com Exploração de Inviabilidade no EVRPTW-PR

## 1. Contexto e Desafio Central

No EVRPTW com recarga parcial, a **heurística de construção/decodificação** tem papel duplo:

1. Transformar uma permutação de clientes (genótipo) em rotas completas com inserção de recargas (fenótipo).
2. Determinar se a solução resultante é factível ou inviável em termos de bateria e janelas de tempo.

O desafio específico da variante proposta é que precisamos **gerar deliberadamente dois tipos de soluções**:

- **Soluções factíveis**: respeitam SOC mínimo e janelas de tempo (ou violam minimamente).
- **Soluções inviáveis "úteis"**: violam restrições de forma controlada, permanecendo próximas da fronteira de viabilidade, com boa qualidade em objetivos (distância, atraso).

Como a viabilidade da bateria é determinada pela heurística (via decisões de quando/quanto recarregar), **não podemos simplesmente "desligar" as recargas**, pois isso geraria inviáveis com violação massiva. A estratégia deve parametrizar o comportamento da heurística para produzir diferentes "níveis de agressividade" na gestão de recarga.

***

## 2. Arquitetura Geral: Decodificação Parametrizada

### 2.1. Representação cromossomial

Seguindo abordagens consolidadas em EVRP evolutivos: [arxiv](https://arxiv.org/html/2410.19580v1)

- **Genótipo**: permutação de clientes (giant tour ou sequências de clientes separadas por delimitadores de veículo).
- **Fenótipo**: rotas completas com inserção de estações de recarga.

A decodificação acontece por:
- **Split algorithm** com programação dinâmica para particionar o giant tour em rotas viáveis, ou [sciencedirect](https://www.sciencedirect.com/science/article/abs/pii/S0377221724002923)
- **Labeling algorithm** com resource extension functions (REFs) que propagam recursos (tempo, bateria, carga) ao longo da rota. [politesi.polimi](https://www.politesi.polimi.it/retrieve/a81cb05c-7ed8-616b-e053-1605fe0a889a/JacopoPierottiTesi.pdf)

Em ambos os casos, a inserção de recargas pode ser feita via:
- **Greedy station insertion**: quando SOC ameaça violar, inserir a estação mais próxima entre o cliente atual e o próximo, ou [sciencedirect](https://www.sciencedirect.com/science/article/abs/pii/S0968090X16000322)
- **Best/compare-k insertion**: avaliar múltiplas estações candidatas e escolher a que minimiza custo adicional. [surendrark.github](https://surendrark.github.io/assets/files/ESWA_surendra.pdf)

### 2.2. Parametrização por "perfil de recarga"

A ideia central é definir **dois perfis de comportamento** da heurística:

#### Perfil Conservador (C)
- Objetivo: garantir viabilidade com margem de segurança.
- Parâmetros:
  - \(b_{safe}^C\): limiar de SOC para disparar recarga (ex.: 35–40% da capacidade).
  - \(b_{target}^C\): nível mínimo de SOC desejado após recarga para o próximo segmento crítico + buffer grande.
  - \(\delta_{time}^C\): slack de tempo extra considerado nas janelas para acomodar tempos de recarga.

#### Perfil Agressivo (A)
- Objetivo: minimizar tempo/custo de recarga, aceitando risco de violação moderada.
- Parâmetros:
  - \(b_{safe}^A\): limiar mais baixo (ex.: 15–20%).
  - \(b_{target}^A\): recarga mínima necessária + buffer pequeno (resultando em SOC pós-recarga tipo 50–70%).
  - \(\delta_{time}^A\): slack reduzido, priorizando velocidade sobre margem temporal.

Esses perfis controlam:
- **Quando** a heurística decide inserir recarga,
- **Quanto** recarregar (em contexto de recarga parcial),
- **Quanta folga** dar nas janelas de tempo.

***

## 3. Mecânica de Decodificação com Perfis

### 3.1. Algoritmo de decodificação genérico

Pseudocódigo de alto nível (adaptado de ): [sciencedirect](https://www.sciencedirect.com/science/article/abs/pii/S0968090X16000322)

```
Função DecodificarRota(permutação, perfil):
    Entrada: permutação de clientes, perfil ∈ {C, A}
    Saída: lista de rotas com recargas, valores de f1, f2, CV
    
    Inicializar: 
        rotas ← []
        rota_atual ← [depósito]
        SOC_atual ← SOC_max
        tempo_atual ← 0
        carga_atual ← 0
    
    Para cada cliente i na permutação:
        # Verificar se é possível adicionar i à rota_atual
        dist ← distância(último_nó(rota_atual), i)
        consumo ← CalcularConsumo(dist)
        
        Se (SOC_atual - consumo < b_safe[perfil]):
            # Necessita recarga antes de i
            estação ← SelecionarEstação(último_nó, i, perfil)
            quantidade ← CalcularQuantidadeRecarga(estação, i, perfil)
            
            Inserir estação e recarga em rota_atual
            Atualizar SOC_atual, tempo_atual com recarga
            
            Se tempo_atual > janela_i ou SOC_atual < SOC_min:
                # Rota se tornou inviável, registrar violação
                Incrementar CV
        
        Adicionar i a rota_atual
        Atualizar SOC_atual, tempo_atual, carga_atual
        
        Se tempo_atual > l_i:
            CV_TW += (tempo_atual - l_i)
        
        Se carga_atual > capacidade ou tempo_atual > T_max:
            # Iniciar nova rota
            rotas.append(rota_atual)
            rota_atual ← [depósito]
            SOC_atual ← SOC_max
            ...
    
    rotas.append(rota_atual)
    
    Calcular f1 (distância total), f2 (atraso total), CV (violações agregadas)
    Retornar (rotas, f1, f2, CV)
```

### 3.2. Lógica de SelecionarEstação e CalcularQuantidadeRecarga

**SelecionarEstação(último_nó, próximo_cliente, perfil)**:
- Perfil C: escolher estação que minimize tempo total de desvio + recarga, garantindo chegar ao próximo cliente com folga.
- Perfil A: escolher estação mais próxima no caminho, mesmo que não seja ótima, priorizando rapidez. [cse.unr](https://www.cse.unr.edu/~sushil/class/gas/papers/AGreedySearchBasedEAForVRP.pdf)

**CalcularQuantidadeRecarga(estação, próximo_destino, perfil)**:
- Perfil C: 
  \[
  Q_{recarga}^C = \min\{Q^{bat}, \; E_{necessária}(próximos\_N\_clientes) + buffer\_grande\} - SOC_{atual}
  \]
  onde buffer_grande pode ser 20–30% da capacidade ou energia para alcançar próxima estação "segura". [daneshyari](https://daneshyari.com/article/preview/6936502.pdf)
  
- Perfil A:
  \[
  Q_{recarga}^A = E_{necessária}(próximos\_K\_clientes) + buffer\_pequeno - SOC_{atual}
  \]
  com K < N e buffer_pequeno ≈ 5–10% da capacidade. [surendrark.github](https://surendrark.github.io/assets/files/ESWA_surendra.pdf)

Essa parametrização garante que:
- Perfil C tende a gerar soluções viáveis, com SOC raramente abaixo do mínimo.
- Perfil A tende a gerar soluções com SOC transitoriamente abaixo do mínimo em alguns arcos, resultando em \(CV_{SOC}\) pequeno/médio, não gigantesco.

***

## 4. Integração com as Populações Viável e Inviável

### 4.1. Estratégia de atribuição de perfil

Cada indivíduo na população tem uma **tag de perfil** associada que determina como será decodificado:

- Indivíduos destinados ao arquivo factível \(A_F\): sempre decodificados com **Perfil C**.
- Indivíduos destinados ao arquivo inviável \(A_I\): decodificados com **Perfil A**.

Na prática:

**Inicialização (geração 0)**:
- Gerar \(N_F + N_I\) permutações aleatórias ou via heurística construtiva (nearest neighbor, CW, etc.).
- Marcar aleatoriamente uma fração \(\alpha \approx 0.3\) como "candidatos a inviável" → decodificar com Perfil A.
- Marcar os demais como "candidatos a factível" → decodificar com Perfil C.
- Após avaliação, distribuir em \(A_F\) e \(A_I\) conforme \(CV\).

**Gerações subsequentes**:
- Ao gerar descendentes via crossover/mutação:
  - Se ambos os pais vêm de \(A_F\): descendente recebe tag "factível" → decodificar com C.
  - Se ambos de \(A_I\): descendente recebe tag "inviável" → decodificar com A.
  - Se pais de arquivos diferentes (mating dirigido): sortear perfil ou usar heurística (ex.: 50% C, 50% A), ou decodificar inicialmente com A para forçar exploração.

### 4.2. Reavaliação condicional

Para evitar desperdício computacional, pode-se implementar **reavaliação condicional**:

- Se um indivíduo com tag "inviável" (Perfil A) produz \(CV = 0\) após decodificação:
  - ele é automaticamente candidato a \(A_F\);
  - opcionalmente, pode-se redecodificá-lo com Perfil C para ver se melhora os objetivos (mas isso é custoso; só fazer se houver budget).

- Se um indivíduo com tag "factível" (Perfil C) resulta em \(CV > \epsilon_F\):
  - ele vira candidato a \(A_I\), desde que \(CV \leq CV_{max}\).

Isso cria um fluxo dinâmico:
- Perfil A tenta "empurrar" soluções para perto da fronteira.
- Perfil C tenta "puxar" estruturas promissoras para dentro da região viável.

***

## 5. Controle da Qualidade dos Inviáveis: Filtros e Limiares

### 5.1. Limiar máximo de violação (\(CV_{max}\))

Para garantir que \(A_I\) contenha apenas inviáveis "próximos da fronteira", definir:

\[
CV_{max} = k \cdot Q^{bat} \quad \text{ou} \quad CV_{max} = \beta \cdot \overline{CV}_{best,I}
\]

onde:
- \(k\): fração pequena da capacidade de bateria (ex.: 0.1–0.2), representando violação acumulada máxima tolerável.
- \(\beta\): multiplicador do melhor \(CV\) observado em \(A_I\) (ex.: 2–3×).

**Regra de descarte**:
- Se após decodificação com Perfil A, \(CV(x) > CV_{max}\): descartar \(x\), não entra nem em \(A_F\) nem \(A_I\).

Isso evita que inviáveis "absurdos" contaminem o arquivo de diversidade.

### 5.2. Critério de entrada em \(A_I\) baseado em objetivos

Além de \(CV \leq CV_{max}\), exigir que o inviável tenha qualidade competitiva:

- \(f_1(x) \leq \text{quantil}_{p}(f_1, A_F)\) **ou** \(f_2(x) \leq \text{quantil}_{p}(f_2, A_F)\), com \(p \in [0.3, 0.5]\).

Ou seja, só mantém inviáveis que estejam no **top 30–50% de pelo menos um objetivo** comparado ao arquivo factível.

Isso operacionaliza o conceito de "inviável útil": bom em objetivos, pequeno em violação. [ro.ecu.edu](https://ro.ecu.edu.au/cgi/viewcontent.cgi?article=1316&context=ecuworks2013)

***

## 6. Dinâmica ao Longo das Gerações

### 6.1. Fase "Push" (gerações iniciais)

- Objetivo: explorar regiões de baixo custo, mesmo que inviáveis.
- Estratégia:
  - Maior fração de cruzamentos envolvendo Perfil A (ex.: \(p_A(t) = 0.5\) para \(t < T/3\)).
  - \(CV_{max}\) relativamente relaxado (ex.: 0.2 \(\cdot Q^{bat}\)).
  - \(\alpha\) (fração de inviáveis) maior (ex.: 0.3–0.4).

### 6.2. Fase "Pull" (gerações finais)

- Objetivo: consolidar soluções factíveis de alta qualidade.
- Estratégia:
  - Reduzir \(p_A(t)\) para 0.2–0.3 (\(t > 2T/3\)).
  - Apertar \(CV_{max}\) (ex.: 0.1 \(\cdot Q^{bat}\)).
  - Manter \(\alpha\) fixo ou reduzir ligeiramente.
  - Aumentar a probabilidade de redecodificar inviáveis promissores com Perfil C.

### 6.3. Ajuste adaptativo de parâmetros

Inspirado em métodos adaptativos de CMOEAs: [egr.msu](https://www.egr.msu.edu/~kdeb/papers/c2018002.pdf)

- Monitorar a taxa de sucesso de inviáveis (quantos geram descendentes que entram em \(A_F\)):
  - Se taxa muito baixa: relaxar \(b_{safe}^A\) ou \(CV_{max}\) (inviáveis estão muito longe).
  - Se taxa muito alta: apertar \(b_{safe}^A\) ou reduzir \(b_{target}^A\) (inviáveis viraram factíveis demais, pouca exploração).

***

## 7. Tratamento de Casos Limite

### 7.1. Permutação resulta em infactibilidade estrutural

Se após tentativa de inserção de recargas com **ambos** os perfis (C e A), a rota continua inviável por excesso de duração, carga, ou impossibilidade de alcançar próximo cliente:

- Aplicar **reparo estrutural mínimo**:
  - Quebrar rota em duas (split),
  - Reordenar clientes localmente (2-opt, relocate),
  - Inserir estação adicional forçada.
- Se ainda inviável após reparo: marcar como "descartável" (\(CV > CV_{max}\)).

### 7.2. Mesma permutação, dois fenótipos

Uma permutação pode ser avaliada em ambos os perfis para gerar diversidade:

- Decodificar com C → solução factível de referência.
- Decodificar com A → versão "esticada" da mesma estrutura, possivelmente inviável.

Isso cria **pares de soluções** que compartilham estrutura topológica mas diferem em política de recarga, facilitando o crossover dirigido entre \(A_F\) e \(A_I\).

***

## 8. Pseudocódigo Integrado

```
Algoritmo: NSGA-II com Exploração de Inviabilidade via Perfis de Recarga

Inicialização:
    P0 ← GerarPermutaçõesIniciais(NF + NI)
    Para cada x em P0:
        Se aleatório() < α:
            x.perfil ← A
        Senão:
            x.perfil ← C
        (rotas, f1, f2, CV) ← DecodificarRota(x, x.perfil)
        x.objetivos ← (f1, f2)
        x.CV ← CV
    
    AF ← selecionarPorCV(P0, CV ≤ εF, NF)
    AI ← selecionarPorCV_e_objetivos(P0, εF < CV ≤ CVmax, NI)

Para t = 1 até Tmax:
    # Fase push/pull
    pA ← CalcularProbabilidadeAgressiva(t)
    
    # Mating
    Descendentes ← []
    Enquanto |Descendentes| < NF + NI:
        Se aleatório() < pA:
            pai1 ← SelecionarTorneio(AI)
            pai2 ← SelecionarProximidade(AF, pai1)
            perfil_filho ← A
        Senão:
            pai1 ← SelecionarTorneio(AF)
            pai2 ← SelecionarTorneio(AF ∪ AI)
            perfil_filho ← C
        
        filho ← Crossover(pai1, pai2)
        filho ← Mutação(filho)
        filho.perfil ← perfil_filho
        
        (rotas, f1, f2, CV) ← DecodificarRota(filho, filho.perfil)
        filho.objetivos ← (f1, f2)
        filho.CV ← CV
        
        Se CV ≤ CVmax:
            Descendentes.append(filho)
    
    # Atualizar arquivos
    AF ← AtualizarArquivoFactível(AF, Descendentes, NF)
    AI ← AtualizarArquivoInviável(AI, Descendentes, NI)
    
    # Ajuste adaptativo (opcional)
    AjustarParâmetros(AF, AI, taxa_sucesso_inviáveis)

Retornar: Frente de Pareto extraída de AF
```

***

## 9. Justificativa Teórica da Estratégia

### 9.1. Por que perfis parametrizados?

- Trabalhos em EVRPTW-PR mostram que a decisão de **quanto recarregar** é crítica e varia com a estrutura da instância. [sciencedirect](https://www.sciencedirect.com/science/article/abs/pii/S0377221722009389)
- Parametrizar via \(b_{safe}\) e \(b_{target}\) permite:
  - Controlar o risco de violação sem desligar completamente a lógica de recarga.
  - Gerar inviáveis que estão "um arco" ou "uma decisão de recarga" de distância da viabilidade. [asmedigitalcollection.asme](https://asmedigitalcollection.asme.org/mechanicaldesign/article-abstract/146/4/041701/1168951/On-the-Advantages-of-Searching-Infeasible-Regions?redirectedFrom=fulltext)

### 9.2. Por que dois perfis fixos em vez de contínuo?

- Simplicidade de implementação e interpretação para TCC.
- Coerente com literatura de two-archive CMOEAs que separam "convergence-oriented" vs "diversity-oriented". [arxiv](https://arxiv.org/pdf/1711.07907.pdf)
- Perfis podem ser expandidos futuramente (ex.: C, A, e intermediário M), mas dois perfis já capturam a dinâmica principal.

### 9.3. Garantia de "inviáveis próximos da fronteira"

- \(CV_{max}\) limita violação absoluta.
- Critério de objetivos (top 30–50%) garante competitividade.
- Resultado: \(A_I\) funciona como "casca" ao redor de \(A_F\), empurrando busca para regiões de custo baixo mas bateria crítica. [ro.ecu.edu](https://ro.ecu.edu.au/cgi/viewcontent.cgi?article=1316&context=ecuworks2013)

***

## 10. Checklist de Implementação

- [ ] Definir valores iniciais de \(b_{safe}^C\), \(b_{target}^C\), \(b_{safe}^A\), \(b_{target}^A\) por experimentação piloto.
- [ ] Implementar função `DecodificarRota(permutação, perfil)` com lógica de greedy/best station insertion parametrizada.
- [ ] Definir \(CV_{max}\) como fração de \(Q^{bat}\) (ex.: 0.15–0.2).
- [ ] Implementar filtros de entrada em \(A_I\): \(CV \leq CV_{max}\) **e** objetivos competitivos.
- [ ] Definir cronograma de \(p_A(t)\): alto no início (0.5), baixo no fim (0.2).
- [ ] Testar em instância pequena se Perfil A de fato gera \(CV\) moderado (não gigantesco).
- [ ] Validar que crossover entre indivíduos de perfis diferentes gera diversidade útil.
- [ ] Instrumentar código para registrar: taxa de inviáveis úteis por geração, distribuição de \(CV\) em \(A_I\), gap de objetivos entre \(A_F\) e \(A_I\).

***

## 11. Riscos e Mitigações

| Risco                                                               | Mitigação                                                                                           |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Perfil A gera \(CV\) sempre > \(CV_{max}\)                          | Relaxar \(b_{safe}^A\) ou aumentar \(b_{target}^A\); ajustar \(CV_{max}\)                           |
| \(A_I\) dominado por soluções muito parecidas                       | Adicionar crowding em \((f_1, f_2)\) na seleção de \(A_I\)                                          |
| Perfil C gera soluções demasiado conservadoras (rotas muito longas) | Reduzir buffer em \(b_{target}^C\); permitir \(\epsilon_F > 0\)                                     |
| Crossover entre perfis não gera melhoria                            | Testar operadores de recombinação alternativos (OX, PMX, edge-assembly) ou aumentar taxa de mutação |
| Custo computacional de decodificação duplicada                      | Cachear decodificações; só redecodificar quando realmente necessário                                |

***

## 12. Conclusão

A heurística de construção parametrizada por perfis de recarga é o mecanismo central que viabiliza a exploração controlada de inviabilidade no EVRPTW-PR. Ao controlar **quando** e **quanto** recarregar via parâmetros \(b_{safe}\) e \(b_{target}\), a estratégia:

- Evita gerar inviáveis com violação massiva (que seriam inúteis), [egr.msu](https://www.egr.msu.edu/~kdeb/papers/c2018002.pdf)
- Permite criar uma "família" de soluções próximas da fronteira de SOC, [asmedigitalcollection.asme](https://asmedigitalcollection.asme.org/mechanicaldesign/article-abstract/146/4/041701/1168951/On-the-Advantages-of-Searching-Infeasible-Regions?redirectedFrom=fulltext)
- Mantém coerência com o contexto de recarga parcial (não força recargas completas), [daneshyari](https://daneshyari.com/article/preview/6936502.pdf)
- Integra-se naturalmente com a arquitetura de dois arquivos e mating dirigido do NSGA-II proposto.

A dinâmica push-pull ao longo das gerações (mais exploração agressiva no início, mais consolidação no fim) ecoa estratégias bem estabelecidas em CMOEAs e garante que o algoritmo não "esqueça" das regiões inviáveis promissoras, ao mesmo tempo que converge para soluções de alta qualidade na região factível. [scholars.cityu.edu](https://scholars.cityu.edu.hk/en/publications/push-and-pull-search-for-solving-constrained-multi-objective-opti/)