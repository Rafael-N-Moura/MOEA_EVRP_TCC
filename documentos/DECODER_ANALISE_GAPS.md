# Análise: Decoder atual vs DECODER_ALTERNATIVO.md

## 1. O que já está implementado

### 1.1 Perfis de recarga (§2.2, §3.2)

| Item no doc | Implementação atual |
|-------------|----------------------|
| Dois perfis C e A | ✅ `RechargeProfile`, `PROFILE_CONSERVATIVE`, `PROFILE_AGGRESSIVE` |
| \(b_{safe}^C\) (35–40%) | ✅ `b_safe_ratio=0.35` no conservador |
| \(b_{safe}^A\) (15–20%) | ✅ `b_safe_ratio=0.18` no agressivo |
| Buffer grande C (20–30%) | ✅ `safety_margin_ratio=0.20` |
| Buffer pequeno A (5–10%) | ✅ `safety_margin_ratio=0.08` |
| **Quando** inserir recarga | Parcial: disparo é por `current_battery < total_energy_needed` (total = ida + segurança + buffer do perfil). Não há disparo explícito por “SOC < b_safe” antes de ir ao cliente. |
| **Quanto** recarregar | ✅ `_calculate_recharge_amount(..., profile)` usa `safety_margin_ratio` do perfil |

### 1.2 Seleção de estação (§3.2)

| Item no doc | Implementação atual |
|-------------|----------------------|
| Perfil C: minimizar desvio + recarga | ✅ `prefer_nearest_station=False` → Smart Detour em `_get_best_station` |
| Perfil A: estação mais próxima no caminho | ✅ `prefer_nearest_station=True` → estação mais próxima por distância |

### 1.3 Atribuição de perfil na decodificação (§4.1)

| Item no doc | Implementação atual |
|-------------|----------------------|
| Indivíduos para \(A_F\) decodificados com C | ✅ `force_battery_feasible=True` → `profile = PROFILE_CONSERVATIVE` em `decode()` |
| Indivíduos para \(A_I\) com Perfil A | ✅ `force_battery_feasible=False` e não radical → `profile = PROFILE_AGGRESSIVE` |
| Modo radical (sem estações) | ✅ `use_radical_infeasible=True` → `profile = None`, sem inserção de estações |

### 1.4 Look-ahead e cliente impossível

- Exigência antes de ir ao cliente: `total_energy_needed = energy_to_customer + energy_customer_to_safety + battery_capacity * margin_ratio` (com margin do perfil). ✅
- Cliente impossível: descarte quando `raw_energy_needed = energy_to_customer + energy_customer_to_safety > battery_capacity`. ✅
- Perfil passado em `_recharge_at_station` e `_calculate_recharge_amount` no loop principal. ✅

---

## 2. O que falta em relação ao documento

### 2.1 Trigger por b_safe no loop principal (§3.1, §2.2)

**Doc:** “Se (SOC_atual - consumo < b_safe[perfil]): necessita recarga antes de i”.

**Atual:** O disparo de recarga é só “bateria < total_energy_needed” (onde total já inclui buffer). Não existe um **disparo preventivo** do tipo “recarregar se SOC atual &lt; b_safe × capacidade”, mesmo quando ainda há energia para o próximo cliente.

**Gap:** A função `_should_recharge_preventively()` existe e usa `b_safe`/`b_critical` do perfil, mas **não é chamada** em lugar nenhum do `decode()`. O loop usa apenas `while current_battery < total_energy_needed`. Para alinhar ao doc, seria preciso, antes de ir ao cliente, também checar algo como “se `current_battery < capacity * b_safe` então forçar ida à estação” (perfil conservador recarrega mais cedo).

---

### 2.2 Slack de tempo nas janelas (\(\delta_{time}^C\), \(\delta_{time}^A\)) (§2.2)

**Doc:** Perfil C usa “slack de tempo extra nas janelas para acomodar tempos de recarga”; perfil A usa “slack reduzido”.

**Atual:** Não há parâmetro de slack de tempo no `RechargeProfile` nem uso de \(\delta_{time}\) na lógica de janelas (atraso já entra como objetivo f2, mas não há margem explícita por perfil).

**Gap:** Incluir no perfil algo como `time_slack_ratio` ou `delta_time` e usar na decisão de viabilidade/atraso (ex.: considerar janela estendida em C ao decidir se vai à estação).

---

### 2.3 Look-ahead “próximos N vs K clientes” na quantidade de recarga (§3.2)

**Doc:**  
- C: \(Q_{recarga}^C = \min\{Q^{bat},\; E_{necessária}(próximos\_N\_clientes) + buffer\_grande\} - SOC_{atual}\).  
- A: \(Q_{recarga}^A = E_{necessária}(próximos\_K\_clientes) + buffer\_pequeno - SOC_{atual}\), com K &lt; N.

**Atual:** A quantidade de recarga é calculada só para o **próximo cliente** (estação → cliente → segurança mais próxima) + margem do perfil. Não há look-ahead sobre N ou K clientes à frente.

**Gap:** Opcional para TCC: parametrizar N (C) e K (A) e, em `_calculate_recharge_amount` (ou em uma função de “energia necessária para os próximos n clientes”), usar soma de energia até o n-ésimo cliente + buffer do perfil para definir o alvo de SOC pós-recarga.

---

### 2.4 Tag de perfil por indivíduo (§4.1, §8)

**Doc:** Cada indivíduo tem “tag de perfil” (C ou A); na inicialização uma fração α é “candidata a inviável” (A); nos descendentes, “se ambos pais de \(A_F\) → perfil C; ambos de \(A_I\) → A; pais de arquivos diferentes → sortear ou 50% C / 50% A”.

**Atual:** O perfil é **derivado apenas no momento da decodificação** a partir de `force_battery_feasible` e `use_radical_infeasible` (e, no battery-focused, de quem está sendo avaliado: população inicial 50/50, offspring primeiro inviável depois reparo). Não existe atributo “perfil” no indivíduo nem regra explícita “perfil do filho = f(pais)”.

**Gap:** Para aderência total ao doc seria preciso: (1) armazenar `perfil` (ou “candidato a A_F / A_I”) no indivíduo; (2) na geração de filhos, definir perfil do filho a partir dos arquivos dos pais; (3) chamar `decode(indivíduo, perfil=indivíduo.perfil)` em vez de inferir só por flags do problema. Hoje a inferência indireta (quem é avaliado como viável vs inviável) aproxima o comportamento, mas não é a “tag” descrita no doc.

---

### 2.5 Reavaliação condicional (§4.2)

**Doc:**  
- Se inviável (Perfil A) produz CV = 0 → candidato a \(A_F\); opcionalmente redecodificar com C.  
- Se factível (C) produz CV &gt; ε_F → candidato a \(A_I\) se CV ≤ CV_max.

**Atual:** Não há passo de “reavaliação condicional”: não se tenta decodificar de novo com o outro perfil quando CV=0 ou CV&gt;ε_F. O reparo no battery-focused apenas reavalia com `force_battery_feasible=True` (C) uma parte da offspring, sem a lógica “se já viável com A, opcionalmente tentar C” nem “se C deu violação, considerar para \(A_I\)”.

**Gap:** Implementar (opcionalmente) regras como: (a) inviável com CV=0 → marcar para \(A_F\) e opcionalmente redecodificar com C; (b) viável com CV&gt;ε_F → considerar para \(A_I\) se CV ≤ CV_max.

---

### 2.6 CV_max e descarte de inviáveis (§5.1, §8)

**Doc:** \(CV_{max} = k \cdot Q^{bat}\) (ex. 0.1–0.2); se CV(x) &gt; CV_max após decodificação com A, descartar x (não entra em \(A_F\) nem \(A_I\)).

**Atual:** Em `InfeasibleSurvival` usa-se `max_violation_ratio` (no battery-focused está como `math.inf`, então não há descarte por CV_max). Não há CV_max explícito como fração da capacidade da bateria no decoder nem no algoritmo.

**Gap:** Definir CV_max (ex. 0.15–0.2 × Q_bat) e, após decodificar, descartar ou não inserir em nenhum arquivo indivíduos com CV &gt; CV_max (e, no algoritmo, não colocá-los na população/offspring).

---

### 2.7 Critério de entrada em \(A_I\) por objetivos (§5.2)

**Doc:** Além de CV ≤ CV_max, exigir que o inviável tenha qualidade competitiva:  
\(f_1(x) \leq \text{quantil}_p(f_1, A_F)\) **ou** \(f_2(x) \leq \text{quantil}_p(f_2, A_F)\), p ∈ [0.3, 0.5].

**Atual:** A seleção para \(A_I\) é por NDS em (f1, f2, CV) + crowding, sem filtro por “top 30–50% em pelo menos um objetivo em relação a \(A_F\)”.

**Gap:** Ao preencher \(A_I\), filtrar ou ponderar indivíduos que não atendam a esse critério de quantil em f1 ou f2 em relação ao arquivo factível.

---

### 2.8 Fase Push/Pull e p_A(t) (§6.1, §6.2, §8)

**Doc:**  
- Push: \(p_A(t)=0.5\) no início, CV_max relaxado, α maior.  
- Pull: \(p_A(t)=0.2\)–0.3 no fim, CV_max mais apertado.

**Atual:** No mating restrito já existe probabilidade dinâmica **p_F(t)** (probabilidade de primeiro pai em \(A_F\)), que vai de 0.5 a 0.9 (e portanto 1−p_F é a “probabilidade de usar inviável” no primeiro pai). Não há CV_max dinâmico nem α(t) explícito; o infeasible_ratio é fixo.

**Gap:** Alinhar nomenclatura/comportamento a p_A(t) se desejado; implementar CV_max(t) e eventualmente α(t) conforme fases push/pull.

---

### 2.9 Ajuste adaptativo de parâmetros (§6.3)

**Doc:** Monitorar taxa de sucesso de inviáveis (quantos geram descendentes que entram em \(A_F\)); relaxar ou apertar \(b_{safe}^A\), \(CV_{max}\), etc.

**Atual:** Nenhum ajuste adaptativo de parâmetros do perfil ou de CV_max ao longo das gerações.

**Gap:** Implementar monitoramento e regras para atualizar \(b_{safe}^A\), CV_max (e eventualmente outros) em função da taxa de sucesso dos inviáveis.

---

### 2.10 Reparo estrutural mínimo (§7.1)

**Doc:** Se com ambos os perfis a rota continuar inviável (excesso de duração, carga, impossível alcançar cliente), aplicar reparo mínimo: split, reordenar (2-opt, relocate), inserir estação forçada; se ainda inviável, marcar como descartável (CV &gt; CV_max).

**Atual:** Há split por capacidade e retorno ao depósito com cadeia de estações; não há tentativa explícita “primeiro com C, depois com A” para a mesma permutação nem reparo local (2-opt, relocate) nem “inserir estação adicional forçada” como passo de reparo.

**Gap:** (Avançado) Implementar fluxo “tentar C e A; se ambos falharem, aplicar reparo estrutural; se ainda CV &gt; CV_max, descartar”.

---

### 2.11 Mesma permutação, dois fenótipos (§7.2)

**Doc:** Avaliar a mesma permutação com C e com A para obter par (factível de referência, “esticada” possivelmente inviável), para enriquecer crossover entre \(A_F\) e \(A_I\).

**Atual:** Cada indivíduo é decodificado uma vez por avaliação (com um único perfil determinado por flags/tag). Não há decodificação dupla (C e A) da mesma permutação para gerar dois fenótipos.

**Gap:** Opcional: para um subconjunto de indivíduos (ex. filhos de mating viável×inviável), decodificar duas vezes (C e A) e usar ambos pontos no arquivo ou na seleção.

---

### 2.12 return_to_depot e perfil

**Atual:** `return_to_depot()` usa `BATTERY_SAFETY_MARGIN` fixo (5%) e `_get_best_station(..., force_battery_feasible=True)` sem `prefer_nearest_station`. Não recebe `profile`.

**Gap:** Para consistência total com perfis, `return_to_depot` poderia receber `profile` e usar `profile.safety_margin_ratio` e `profile.prefer_nearest_station` (e repassar para `_get_best_station` e para o cálculo de recarga no retorno).

---

### 2.13 Checklist do documento (§10)

- [x] Definir \(b_{safe}^C\), \(b_{target}^C\), \(b_{safe}^A\), \(b_{target}^A\) — feito (via safety_margin_ratio e b_safe_ratio).
- [x] Implementar DecodificarRota(permutação, perfil) com inserção parametrizada — feito (decode + profile).
- [ ] Definir CV_max como fração de Q_bat — **não implementado** (usa-se max_violation_ratio=inf).
- [ ] Filtros de entrada em \(A_I\): CV ≤ CV_max **e** objetivos competitivos — **parcial** (só NDS+crowding, sem CV_max nem quantil).
- [x] Cronograma p_A(t) — **parcial** (existe p_F(t) no mating; não há CV_max(t) nem α(t)).
- [x] Perfil A gera CV moderado — observado em testes (--no-radical).
- [ ] Instrumentar: taxa de inviáveis úteis, distribuição de CV em \(A_I\), gap \(A_F\)–\(A_I\) — **não implementado**.

---

## 3. Resumo: prioridade dos gaps

| Prioridade | Item | Esforço |
|------------|------|--------|
| Alta | Trigger por b_safe no loop (ou usar `_should_recharge_preventively`) | Baixo |
| Alta | CV_max (fração de Q_bat) e descarte de inviáveis | Baixo |
| Média | return_to_depot usar perfil (margem + prefer_nearest) | Baixo |
| Média | Critério de entrada em \(A_I\) por quantil em f1/f2 | Médio |
| Média | Tag de perfil no indivíduo e perfil do filho = f(pais) | Médio |
| Baixa | δ_time no perfil (slack de tempo) | Médio |
| Baixa | Look-ahead N/K clientes na quantidade de recarga | Médio |
| Baixa | Reavaliação condicional (CV=0 com A → tentar C; C com CV&gt;ε → \(A_I\)) | Médio |
| Baixa | Push/Pull: CV_max(t), α(t) | Baixo/Médio |
| Baixa | Ajuste adaptativo de parâmetros | Alto |
| Baixa | Reparo estrutural mínimo (§7.1) | Alto |
| Baixa | Mesma permutação dois fenótipos (§7.2) | Médio |
| Baixa | Instrumentação (taxa inviáveis úteis, distribuição CV, gap) | Baixo |

---

## 4. Conclusão

O decoder já cobre a **núcleo** do DECODER_ALTERNATIVO: dois perfis (C e A), parametrização por b_safe, b_critical, safety_margin e escolha de estação (Smart Detour vs mais próxima), atribuição de perfil por modo (viável/inviável/radical) e look-ahead básico (um cliente + segurança + buffer).  

Os principais **gaps** para alinhar ao documento são: (1) usar b_safe como disparo preventivo de recarga (ou integrar `_should_recharge_preventively` no loop); (2) introduzir CV_max e descarte; (3) critério de entrada em \(A_I\) por objetivos; (4) consistência de perfil em `return_to_depot`. O restante (reavaliação condicional, tag por indivíduo, δ_time, look-ahead N/K, push-pull dinâmico, adaptativo, reparo e dois fenótipos) são extensões opcionais para aproximar ainda mais o texto do doc.
