Vou descrever as modificações de forma precisa, componente por componente, mostrando o que muda e por quê.

**O problema fundamental do design atual**

Com [∞, ∞, ∞], duas soluções inviáveis são indistinguíveis para o algoritmo. Uma permutação que viola uma janela de tempo por 1 segundo recebe o mesmo tratamento que uma que viola todas as janelas por horas. O algoritmo não tem gradiente para "caminhar em direção à viabilidade" — ele depende inteiramente de gerar soluções viáveis por acaso. Em instâncias com tw_ratio baixo (r101_21 com 0,044), onde o espaço viável é minúsculo, a população inicial pode ser 100% inviável e o algoritmo fica preso indefinidamente.

Com dominância baseada em feasibilidade, soluções inviáveis competem entre si pela menor violação, criando pressão seletiva em direção à região viável. O algoritmo "encontra o caminho" mesmo partindo de uma população inteiramente inviável.

**Princípio da modificação**

O decodificador *nunca mais retorna INFEASÍVEL*. Ele sempre constrói uma solução completa visitando todos os clientes, mesmo que viole restrições no caminho. Além dos três objetivos, ele retorna um escalar de violação total. A comparação entre soluções é delegada ao mecanismo de constraint handling do pymoo, que implementa nativamente o Constrained Domination Principle (CDP) de Deb.

**Modificação 1 — Novo contrato do decodificador**

O contrato antigo era: Decode(π) → [f1, f2, f3] ou [∞, ∞, ∞]. O contrato novo é: Decode(π) → [f1, f2, f3], cv. Os três objetivos são sempre calculados, mesmo para soluções inviáveis — são os valores "reais" que a solução teria se as restrições fossem relaxadas. O valor cv (constraint violation) é um escalar ≥ 0 onde cv = 0 significa solução viável. O pymoo usa cv > 0 para sinalizar inviabilidade e aplica o CDP automaticamente.

**Modificação 2 — Split permanece inalterado**

O Split com restrição de capacidade não precisa mudar. Nas instâncias de Schneider, a demanda máxima por cliente é 50 e a capacidade mínima é 200, então todo cliente cabe individualmente em uma rota. V[n] = ∞ nunca ocorre porque a partição trivial (um cliente por rota) é sempre viável por capacidade. O Split continuará particionando por capacidade como antes.

Se por algum motivo futuro V[n] = ∞ ocorresse, a solução seria fazer uma partição forçada (um cliente por rota) e registrar o excesso de capacidade como violação. Mas para Schneider isso é desnecessário.

**Modificação 3 — InsertStations: acumular violações em vez de abortar**

Essa é a modificação central. O InsertStations atual tem três pontos de retorno INFEASÍVEL que precisam ser eliminados. Vou descrever cada um.

Primeiro ponto: chegada tardia na viagem direta (t_arr > l[dest]). Atualmente retorna INFEASÍVEL. A modificação: registrar a violação tw_violation += max(0, t_arr - l[dest]), mas continuar normalmente. O tempo é atualizado como se o cliente tivesse sido atendido (mesmo com atraso), e a rota continua. O cliente foi visitado — tarde, mas visitado.

Segundo ponto: bateria insuficiente e nenhuma estação candidata é viável. Atualmente retorna INFEASÍVEL. A modificação: quando nenhuma estação do loop satisfaz todas as condições, o decodificador precisa de uma estratégia de fallback. Há duas sub-situações. Se pelo menos uma estação é alcançável com a bateria atual (e1 ≤ bat) mas nenhuma permite chegar ao destino dentro da janela de tempo, o decodificador insere a estação de menor desvio de distância mesmo assim — a violação de janela de tempo será capturada na chegada ao próximo cliente. Se nenhuma estação é sequer alcançável (e1 > bat para todas), o decodificador segue direto para o destino, registrando o déficit de bateria: bat_violation += max(0, e_nec - bat), e reseta a bateria para zero (o veículo "ficou sem bateria" mas a solução continua sendo avaliada).

Terceiro ponto: o filtro de look-ahead (t_out + travel[dest][prox] > l[prox]). Atualmente descarta a estação candidata. A modificação: o look-ahead permanece como *critério de preferência*, não como filtro eliminatório. Se todas as estações falham no look-ahead, a melhor estação pelo score balanceado é inserida mesmo assim — a violação de TW no próximo cliente será capturada quando ele for visitado.

O pseudocódigo revisado do InsertStations fica:

```
FUNÇÃO InsertStations(clientes):
    rota ← [depot]
    t ← 0
    bat ← Q
    ant ← depot
    tw_violation ← 0
    bat_violation ← 0
    dist_acumulada ← 0

    para idx ← 0 até len(clientes) - 1:
        dest ← clientes[idx]
        prox ← clientes[idx+1] se idx+1 < len(clientes), senão depot
        e_nec ← dist[ant][dest] * r

        se bat ≥ e_nec:   // viagem direta possível
            t_arr ← t + travel[ant][dest]
            tw_violation += max(0, t_arr - l[dest])   // ← REGISTRA em vez de abortar
            t ← max(t_arr, e[dest]) + service[dest]
            bat ← bat - e_nec
            dist_acumulada += dist[ant][dest]
            rota.append(dest)
            ant ← dest

        senão:   // precisa de estação
            // Fase A: buscar estações com look-ahead
            candidatas_boas ← []
            candidatas_fallback ← []
            
            para cada s em S \ {S0}:
                e1 ← dist[ant][s] * r
                e2 ← dist[s][dest] * r
                se e1 > bat: continuar          // não alcança s
                se e2 > Q: continuar            // não sai de s até dest
                
                t_s ← t + travel[ant][s]
                bat_s ← bat - e1
                t_rec ← t_s + g * (Q - bat_s)
                t_dest ← t_rec + travel[s][dest]
                bat_dest ← Q - e2
                t_out ← max(t_dest, e[dest]) + service[dest]
                
                desvio_dist ← dist[ant][s] + dist[s][dest] - dist[ant][dest]
                atraso_tempo ← t_dest - (t + travel[ant][dest])
                score ← (desvio_dist / max(dist_acumulada, ε)) 
                       + (atraso_tempo / max(t, ε))
                
                entrada ← {s, score, t_out, bat_dest, t_dest}
                
                se t_out + travel[dest][prox] ≤ l[prox]:
                    candidatas_boas.append(entrada)
                senão:
                    candidatas_fallback.append(entrada)
            
            // Fase B: selecionar estação
            se candidatas_boas não vazio:
                melhor ← candidata de menor score em candidatas_boas
            senão se candidatas_fallback não vazio:
                melhor ← candidata de menor score em candidatas_fallback
            senão:
                // Nenhuma estação alcançável: seguir direto
                deficit ← e_nec - bat
                bat_violation += deficit
                bat ← 0
                t_arr ← t + travel[ant][dest]
                tw_violation += max(0, t_arr - l[dest])
                t ← max(t_arr, e[dest]) + service[dest]
                dist_acumulada += dist[ant][dest]
                rota.append(dest)
                ant ← dest
                continuar
            
            // Inserir estação selecionada
            rota.append(melhor.s)
            rota.append(dest)
            tw_violation += max(0, melhor.t_dest - l[dest])   // ← REGISTRA
            t ← melhor.t_out
            bat ← melhor.bat_dest
            dist_acumulada += dist[ant][melhor.s] + dist[melhor.s][dest]
            ant ← dest

    rota.append(depot)
    retornar rota, tw_violation, bat_violation
```

**Modificação 4 — Evaluate acumula e normaliza a violação**

O Evaluate recebe as violações de cada rota e produz o escalar cv normalizado.

```
FUNÇÃO Evaluate(expanded_routes, tw_violations, bat_violations):
    // Calcular f1, f2, f3 como antes (sem alteração)
    f1 ← len(expanded_routes)
    f2 ← soma das distâncias de todas as rotas
    f3 ← max dos tempos de retorno ao depot
    
    // Agregar violações
    tw_total ← soma(tw_violations)      // soma sobre todas as rotas
    bat_total ← soma(bat_violations)    // soma sobre todas as rotas
    
    // Normalizar para que TW e bateria tenham escala comparável
    // Usa os parâmetros da instância como referência
    tw_norm ← tw_total / horizonte      // violação como fração do horizonte
    bat_norm ← bat_total / Q            // violação como fração da bateria
    
    cv ← tw_norm + bat_norm             // constraint violation total
    
    retornar [f1, f2, f3], cv
```

A normalização é importante: sem ela, uma violação de TW de 100 unidades de tempo teria peso muito diferente de uma violação de bateria de 100 unidades de energia, porque as escalas são diferentes. Dividir pelo horizonte e por Q coloca ambas em escala de "fração do recurso total violado".

**Modificação 5 — Integração com pymoo**

O pymoo implementa nativamente o CDP quando você declara restrições de desigualdade. A modificação na classe Problem é mínima:

```
class EVRPTWProblem(ElementwiseProblem):
    def __init__(self, instance):
        super().__init__(
            n_var=instance.n_clients,
            n_obj=3,
            n_ieq_constr=1,    # ← MUDA: era 0, agora é 1
            xl=0,
            xu=instance.n_clients - 1,
            vtype=int
        )
        self.instance = instance
        self.decoder = Decoder(instance)

    def _evaluate(self, x, out, *args, **kwargs):
        f, cv = self.decoder.decode(x)   # ← MUDA: agora retorna cv
        out["F"] = f                      # [f1, f2, f3]
        out["G"] = [cv]                   # ← NOVO: constraint violation
```

Com n_ieq_constr=1 e out["G"] preenchido, o NSGA-II do pymoo aplica automaticamente o CDP: soluções com G ≤ 0 (viáveis) dominam soluções com G > 0 (inviáveis), e entre inviáveis a de menor G vence. O MOEA/D e SMS-EMOA do pymoo também respeitam essa mecânica.

**Modificação 6 — O que NÃO muda**

O Split continua idêntico. Os operadores genéticos (OX, InversionMutation) continuam idênticos — operam sobre permutações e são agnósticos à viabilidade. O cálculo de f1, f2, f3 continua idêntico. O pré-compute de distâncias continua idêntico. A propriedade de determinismo é preservada — a mesma permutação sempre produz o mesmo (f, cv).

**Verificação de que a modificação é consistente com o design experimental**

O constraint checker da validação (Camada 1 do plano de validação) continua verificando *soluções da frente de Pareto final*. Soluções na frente de Pareto com cv > 0 não deveriam existir se o algoritmo convergiu adequadamente — a presença delas indica que o algoritmo não encontrou soluções viáveis suficientes, o que é informação para a Camada 4 da análise (taxa de viabilidade).

A taxa de viabilidade agora é calculada como: fração de soluções na população final com cv = 0. Isso alimenta diretamente a análise de H3 (instâncias com tw_ratio baixo terão taxa de viabilidade menor).
