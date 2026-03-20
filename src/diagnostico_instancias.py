"""
Diagnóstico de instâncias para EVRPTW-PR (decoder_infeasible).
Responde três perguntas antes de qualquer experimento:
  1. FR: A instância tem proporção de inviáveis suficiente para a técnica fazer sentido?
  2. Distribuição de CV: Os inviáveis carregam informação útil ou são majoritariamente irrecuperáveis?
  3. Regime: Classificação final (DENSO, MODERADO_*, ESPARSO_*) e expectativa para a técnica.

A pergunta estrutural (fronteira factível fragmentada?) requer execução do algoritmo
completo e fica como placeholder no retorno.
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import replace
from itertools import combinations
import numpy as np

from .decoder_infeasible import decode_infeasible, decode_registrar_soc_minimo
from .model import Context


def calcular_Q_alvo(context: Context) -> Dict[str, float]:
    """
    Quantifica a relação Q/r vs distâncias típicas da instância.

    Uma troca de dois clientes altera arcos com ordem de grandeza ~2*dist_p75.
    Para que existam inviáveis marginais (déficit < 10% Q), é necessário
    Q > 20 * dist_p75 (com r=1). Para FR local razoável, Q > 10 * dist_p75.

    Retorna Q_fr_local, Q_marginais, dist_p75 e estatísticas de distância.
    """
    clientes = context.customers
    coords = [(c.x, c.y) for c in clientes]

    distancias: List[float] = []
    for (x1, y1), (x2, y2) in combinations(coords, 2):
        distancias.append(np.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2))
    distancias_arr = np.array(distancias)

    dist_media = float(np.mean(distancias_arr))
    dist_p75 = float(np.percentile(distancias_arr, 75))
    dist_p90 = float(np.percentile(distancias_arr, 90))

    # Para que uma troca (extra ≈ 2*dist_p75) produza déficit < 10% de Q:
    #   2 * dist_p75 * r < 0.10 * Q  =>  Q > 20 * dist_p75 (com r=1)
    r = context.consumption_rate
    if r <= 0:
        r = 1.0
    Q_para_marginais_existirem = 20 * dist_p75 * r
    Q_para_FR_local_razoavel = 10 * dist_p75 * r

    Q_atual = context.battery_capacity
    fator = Q_para_marginais_existirem / Q_atual if Q_atual > 0 else float("inf")

    return {
        "dist_media": dist_media,
        "dist_p75": dist_p75,
        "dist_p90": dist_p90,
        "Q_atual": Q_atual,
        "Q_fr_local": Q_para_FR_local_razoavel,
        "Q_marginais": Q_para_marginais_existirem,
        "fator_aumento_necessario": fator,
    }


def criar_variacao_Q(context_original: Context, Q_novo: float) -> Context:
    """
    Cria uma cópia do contexto com capacidade de bateria alterada.
    Mesma topologia (clientes, estações, janelas, demandas); apenas Q muda.
    Precedente: Hiermann et al. (2016), Desaulniers et al. (2016) — sensibilidade em Q.
    """
    return replace(context_original, battery_capacity=Q_novo)


def _construir_greedy(context: Context, rng: np.random.Generator) -> Optional[Tuple[List[int], List[float]]]:
    """
    Tenta construir uma solução base factível (cv_energia=0) por heurísticas greedy.
    Estratégias: (1) π por distância ao depósito; (2) π por ready_time; (3) π aleatório.
    Em todas, δ = 1.0 (recarga total). Retorna (pi, delta) ou None.
    """
    n = len(context.customers)
    depot = context.depot
    customers = context.customers
    max_tentativas = 30

    delta = [1.0] * n
    ordem_dist = sorted(range(n), key=lambda j: depot.distance_to(customers[j]))
    sol = decode_infeasible(ordem_dist, delta, context)
    if sol.cv_energia == 0:
        return (ordem_dist, delta)

    ordem_tw = sorted(range(n), key=lambda j: customers[j].ready_time)
    sol = decode_infeasible(ordem_tw, delta, context)
    if sol.cv_energia == 0:
        return (ordem_tw, delta)

    for _ in range(max_tentativas):
        pi = rng.permutation(n).tolist()
        sol = decode_infeasible(pi, delta, context)
        if sol.cv_energia == 0:
            return (pi, delta)
    return None


def medir_fr_local(
    context: Context,
    n_solucoes_base: int = 20,
    n_vizinhos: int = 50,
    rng: Optional[np.random.Generator] = None,
) -> Dict[str, Any]:
    """
    Mede FR e marginais na vizinhança de soluções factíveis (perturbação pequena em π e δ).
    Relevante para CMOEAs, que operam perto das soluções já encontradas.
    """
    if rng is None:
        rng = np.random.default_rng()
    n = len(context.customers)
    Q = context.battery_capacity
    if Q <= 0:
        Q = 1.0

    resultados_por_base: List[Dict[str, float]] = []
    max_tentativas_base = max(n_solucoes_base * 3, 50)
    bases_obtidas = 0

    for _ in range(max_tentativas_base):
        if bases_obtidas >= n_solucoes_base:
            break
        par = _construir_greedy(context, rng)
        if par is None:
            continue
        pi_base, delta_base = par
        sol_base = decode_infeasible(pi_base, delta_base, context)
        if sol_base.cv_energia > 0:
            continue
        bases_obtidas += 1

        cvs_vizinhos: List[float] = []
        for _ in range(n_vizinhos):
            pi_viz = pi_base.copy()
            if len(pi_viz) >= 2:
                i = rng.integers(0, len(pi_viz) - 1)
                pi_viz[i], pi_viz[i + 1] = pi_viz[i + 1], pi_viz[i]
            delta_viz = [
                max(0.0, min(1.0, d + rng.normal(0, 0.05)))
                for d in delta_base
            ]
            sol_viz = decode_infeasible(pi_viz, delta_viz, context)
            cvs_vizinhos.append(sol_viz.cv_energia)

        cvs_norm = [cv / Q for cv in cvs_vizinhos]
        factiveis = sum(1 for cv in cvs_vizinhos if cv == 0)
        marginais = sum(1 for cv in cvs_norm if 0 < cv < 0.10)
        graves = sum(1 for cv in cvs_norm if cv >= 0.10)

        resultados_por_base.append({
            "fr_local": factiveis / n_vizinhos,
            "marginais_locais": marginais / n_vizinhos,
            "graves_locais": graves / n_vizinhos,
        })

    if not resultados_por_base:
        return {
            "n_bases_usadas": 0,
            "sem_solucao_base_factivel": True,
            "fr_local_medio": None,
            "marginais_locais_medio": None,
            "graves_locais_medio": None,
            "por_base": [],
        }

    fr_medio = sum(r["fr_local"] for r in resultados_por_base) / len(resultados_por_base)
    marg_medio = sum(r["marginais_locais"] for r in resultados_por_base) / len(resultados_por_base)
    graves_medio = sum(r["graves_locais"] for r in resultados_por_base) / len(resultados_por_base)

    return {
        "n_bases_usadas": len(resultados_por_base),
        "sem_solucao_base_factivel": False,
        "fr_local_medio": fr_medio,
        "marginais_locais_medio": marg_medio,
        "graves_locais_medio": graves_medio,
        "por_base": resultados_por_base,
    }


def medir_fr(
    context: Context,
    n_amostras: int,
    rng: np.random.Generator,
) -> Dict[str, float]:
    """
    Mede Feasibility Rate com cromossomos genuinamente aleatórios:
    permutação uniforme de clientes e δ uniforme em [0, 1].
    """
    n = len(context.customers)
    R = n

    factivel_energia = 0
    factivel_total = 0

    for _ in range(n_amostras):
        pi = rng.permutation(n).tolist()
        delta = rng.uniform(0.0, 1.0, size=R).tolist()

        sol = decode_infeasible(pi, delta, context)

        if sol.cv_energia == 0:
            factivel_energia += 1
        if sol.cv_energia == 0 and sol.cv_tw == 0:
            factivel_total += 1

    return {
        "fr_energia": factivel_energia / n_amostras,
        "fr_total": factivel_total / n_amostras,
    }


def medir_distribuicao_cv(
    context: Context,
    n_amostras: int,
    rng: np.random.Generator,
) -> Dict[str, Any]:
    """
    Mede a distribuição de CV entre os inviáveis.
    Proporção de marginais (CV pequeno) indica se inviáveis são informativos para o DA.
    """
    n = len(context.customers)
    R = n
    Q = context.battery_capacity

    cvs_energia: list = []
    cvs_tw: list = []

    for _ in range(n_amostras):
        pi = rng.permutation(n).tolist()
        delta = rng.uniform(0.0, 1.0, size=R).tolist()

        sol = decode_infeasible(pi, delta, context)

        if sol.cv_energia > 0:
            cvs_energia.append(sol.cv_energia)
        if sol.cv_tw > 0:
            cvs_tw.append(sol.cv_tw)

    out: Dict[str, Any] = {}

    # --- Energia ---
    if not cvs_energia:
        out["sem_inviaveis_energeticos"] = True
        out["n_inviaveis_energeticos"] = 0
        out["proporcao_marginais"] = 0.0
    else:
        cvs_energia_arr = np.array(cvs_energia)
        cvs_norm = cvs_energia_arr / Q if Q > 0 else cvs_energia_arr
        out["sem_inviaveis_energeticos"] = False
        out["n_inviaveis_energeticos"] = len(cvs_energia_arr)
        out["cv_energia_mediana_norm"] = float(np.median(cvs_norm))
        out["cv_energia_p25_norm"] = float(np.percentile(cvs_norm, 25))
        out["cv_energia_p75_norm"] = float(np.percentile(cvs_norm, 75))
        out["cv_energia_p90_norm"] = float(np.percentile(cvs_norm, 90))
        out["proporcao_marginais"] = float(np.mean(cvs_norm < 0.10))

    # --- TW (análogo) ---
    tw_ref = sum(
        context.customers[j].due_date - context.customers[j].ready_time
        for j in range(n)
    )
    if not cvs_tw:
        out["sem_inviaveis_tw"] = True
        out["n_inviaveis_tw"] = 0
        out["proporcao_marginais_tw"] = 0.0
    else:
        cvs_tw_arr = np.array(cvs_tw)
        cvs_tw_norm = cvs_tw_arr / tw_ref if tw_ref > 0 else cvs_tw_arr
        out["sem_inviaveis_tw"] = False
        out["n_inviaveis_tw"] = len(cvs_tw_arr)
        out["cv_tw_mediana_norm"] = float(np.median(cvs_tw_norm))
        out["cv_tw_p25_norm"] = float(np.percentile(cvs_tw_norm, 25))
        out["cv_tw_p75_norm"] = float(np.percentile(cvs_tw_norm, 75))
        out["cv_tw_p90_norm"] = float(np.percentile(cvs_tw_norm, 90))
        out["proporcao_marginais_tw"] = float(np.mean(cvs_tw_norm < 0.10))

    return out


def _verificar_tensao_energetica_dados(
    context: Context,
    n_solucoes: int,
    rng: np.random.Generator,
    Q_factor: float,
) -> Dict[str, Any]:
    """
    Calcula estatísticas de SoC mínimo em soluções factíveis (greedy).
    Retorna dict com resultado (True/False/None), p10, mediana, minimo, n_feasible, Q_usado.
    """
    ctx = criar_variacao_Q(context, context.battery_capacity * Q_factor) if Q_factor != 1.0 else context
    Q_usado = ctx.battery_capacity
    socs_minimos: List[float] = []
    for _ in range(n_solucoes):
        par = _construir_greedy(ctx, rng)
        if par is None:
            continue
        pi, delta = par
        soc_min = decode_registrar_soc_minimo(pi, delta, ctx)
        if soc_min is not None:
            socs_minimos.append(soc_min / Q_usado)
    if not socs_minimos:
        return {
            "resultado": None,
            "p10": None,
            "mediana": None,
            "minimo": None,
            "n_feasible": 0,
            "Q_usado": Q_usado,
            "Q_factor": Q_factor,
        }
    p10 = float(np.percentile(socs_minimos, 10))
    return {
        "resultado": not (p10 > 0.25),
        "p10": p10,
        "mediana": float(np.median(socs_minimos)),
        "minimo": float(np.min(socs_minimos)),
        "n_feasible": len(socs_minimos),
        "Q_usado": Q_usado,
        "Q_factor": Q_factor,
    }


def verificar_tensao_energetica(
    context: Context,
    n_solucoes: int = 50,
    rng: Optional[np.random.Generator] = None,
    Q_factor: float = 1.0,
) -> Optional[bool]:
    """
    Analisa o perfil de SoC nas melhores soluções factíveis (greedy).
    Se o SoC mínimo nunca for baixo (p10 normalizado > 0.25), a topologia não tem
    tensão energética e modificações de Q ou estações não criam marginais genuínos.
    Retorna True se tensão presente, False se sem tensão, None se nenhuma solução factível.

    Q_factor: multiplicador da capacidade de bateria só para esta análise (ex.: 1.5).
              Use quando com Q original o greedy não encontrar factíveis (resultado None).
    """
    if rng is None:
        rng = np.random.default_rng()
    dados = _verificar_tensao_energetica_dados(context, n_solucoes, rng, Q_factor)
    if dados["n_feasible"] == 0:
        print("Nenhuma solução factível encontrada.")
        if Q_factor == 1.0:
            print("Sugestão: com Q original o greedy pode falhar. Tente Q_factor=1.5 ou 2.0:")
            print("  verificar_tensao_energetica(context, n_solucoes=50, Q_factor=1.5)")
        return None
    if Q_factor != 1.0:
        print(f"(Análise com Q = {Q_factor}× Q_original = {dados['Q_usado']:.2f})\n")
    print("SoC mínimo nas boas soluções (normalizado por Q):")
    print(f"  mediana: {dados['mediana']:.3f}")
    print(f"  p10:     {dados['p10']:.3f}")
    print(f"  mínimo:  {dados['minimo']:.3f}")
    if dados["resultado"] is False:
        print("\nCONCLUSÃO: Topologia sem tensão energética.")
        print("As boas soluções operam com folga energética confortável.")
        print("Modificações de Q ou estações não vão criar marginais genuínos.")
        print("Caminho A não é viável para essa instância.")
        return False
    print("\nCONCLUSÃO: Tensão energética presente.")
    print("Existe potencial para criar marginais com modificações.")
    print("Caminho A pode ser viável — prosseguir com diagnóstico local.")
    return True


def classificar_regime(
    fr_energia: float,
    proporcao_marginais: float,
) -> Dict[str, str]:
    """
    Classifica o regime da instância e a expectativa para a técnica de inviáveis.
    """
    if fr_energia > 0.50:
        return {
            "regime": "DENSO",
            "expectativa": "Técnica de inviáveis tem baixo benefício esperado. CDP deve ser suficiente.",
        }

    if fr_energia > 0.20:
        if proporcao_marginais > 0.40:
            return {
                "regime": "MODERADO_FAVORAVEL",
                "expectativa": "Condições parcialmente satisfeitas. Benefício possível mas não garantido.",
            }
        else:
            return {
                "regime": "MODERADO_DESFAVORAVEL",
                "expectativa": "Inviáveis existem mas são majoritariamente irrecuperáveis. Benefício improvável.",
            }

    # fr_energia <= 0.20
    if proporcao_marginais > 0.40:
        return {
            "regime": "ESPARSO_FAVORAVEL",
            "expectativa": "Condições favoráveis identificadas. Técnica tem alto potencial nessa instância.",
        }
    else:
        return {
            "regime": "ESPARSO_DESFAVORAVEL",
            "expectativa": "Região factível estreita mas inviáveis são estruturalmente graves. Benefício incerto.",
        }


def diagnosticar_instancia(
    context: Context,
    n_amostras: int = 1000,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Diagnóstico completo da instância antes de qualquer experimento.

    Responde:
      1. FR: proporção de inviáveis suficiente para a técnica fazer sentido?
      2. Distribuição de CV: inviáveis informativos ou irrecuperáveis?
      3. Regime: classificação e expectativa.

    A pergunta estrutural (fronteira factível fragmentada?) requer o algoritmo
    completo e fica como nota no retorno.
    """
    rng = np.random.default_rng(seed)

    resultados: Dict[str, Any] = {
        "feasibility_rate_energia": None,
        "feasibility_rate_total": None,
        "fr_local": None,
        "marginais_locais_medio": None,
        "cv_energia_distribuicao": None,
        "cv_tw_distribuicao": None,
        "proporcao_marginais": None,
        "proporcao_marginais_tw": None,
        "regime": None,
        "expectativa": None,
        "fronteira_fragmentada": None,
        "n_amostras": n_amostras,
        "seed": seed,
    }

    # --- Diagnóstico 1: Feasibility Rate ---
    fr = medir_fr(context, n_amostras, rng)
    resultados["feasibility_rate_energia"] = fr["fr_energia"]
    resultados["feasibility_rate_total"] = fr["fr_total"]

    # --- Diagnóstico local (vizinhança de soluções factíveis) ---
    fr_local = medir_fr_local(
        context,
        n_solucoes_base=min(20, n_amostras // 10),
        n_vizinhos=50,
        rng=rng,
    )
    resultados["fr_local"] = fr_local
    resultados["marginais_locais_medio"] = fr_local.get("marginais_locais_medio")

    # --- Diagnóstico 2: Distribuição de CV ---
    dist_cv = medir_distribuicao_cv(context, n_amostras, rng)

    resultados["proporcao_marginais"] = dist_cv.get("proporcao_marginais", 0.0)
    resultados["proporcao_marginais_tw"] = dist_cv.get("proporcao_marginais_tw", 0.0)

    resultados["cv_energia_distribuicao"] = {
        "sem_inviaveis": dist_cv.get("sem_inviaveis_energeticos", False),
        "n_inviaveis": dist_cv.get("n_inviaveis_energeticos", 0),
        "mediana_norm": dist_cv.get("cv_energia_mediana_norm"),
        "p25_norm": dist_cv.get("cv_energia_p25_norm"),
        "p75_norm": dist_cv.get("cv_energia_p75_norm"),
        "p90_norm": dist_cv.get("cv_energia_p90_norm"),
    }
    resultados["cv_tw_distribuicao"] = {
        "sem_inviaveis": dist_cv.get("sem_inviaveis_tw", False),
        "n_inviaveis": dist_cv.get("n_inviaveis_tw", 0),
        "mediana_norm": dist_cv.get("cv_tw_mediana_norm"),
        "p25_norm": dist_cv.get("cv_tw_p25_norm"),
        "p75_norm": dist_cv.get("cv_tw_p75_norm"),
        "p90_norm": dist_cv.get("cv_tw_p90_norm"),
    }

    # --- Diagnóstico 3: Classificação do regime ---
    regime_out = classificar_regime(
        resultados["feasibility_rate_energia"],
        resultados["proporcao_marginais"],
    )
    resultados["regime"] = regime_out["regime"]
    resultados["expectativa"] = regime_out["expectativa"]

    # Pergunta estrutural: requer execução do algoritmo para análise de conectividade
    resultados["fronteira_fragmentada"] = (
        "Requer execução do algoritmo completo para análise de conectividade da fronteira factível."
    )

    return resultados
