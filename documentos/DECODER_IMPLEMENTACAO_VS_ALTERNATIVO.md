# Análise detalhada: decoder.py vs DECODER_ALTERNATIVO.md

Este documento mapeia **o que já está implementado** em `src/decoder.py` e **o que ainda falta** em relação à especificação do `documentos/DECODER_ALTERNATIVO.md`. A numeração de seções segue o documento de referência.

---

## 1. Contexto e representação (§1, §2.1)

| Item no doc | Status | Detalhes no decoder.py |
|-------------|--------|-------------------------|
| Genótipo = permutação de clientes | ✅ | `decode(individual: List[int], ...)` — lista de IDs/índices de clientes. |
| Fenótipo = rotas com estações de recarga | ✅ | `Solution` com `routes`, cada `Route` com `RouteStep` (depot, clientes, estações). |
| Decodificação por heurística construtiva (greedy insertion) | ✅ | Loop cliente a cliente; quando precisa recarregar, chama `_recharge_at_station` → `_get_best_station` (greedy / best detour). |
| Split por capacidade de carga | ✅ | Se `current_load + demand > vehicle_capacity`, fecha rota com `return_to_depot`, abre novo veículo. |

**Conclusão:** Representação e fluxo geral de decodificação estão alinhados ao doc.

---

## 2. Parametrização por perfil de recarga (§2.2)

### 2.2 Perfil Conservador (C) e Agressivo (A)

| Parâmetro no doc | Doc | Implementado em decoder.py | Status |
|------------------|-----|-----------------------------|--------|
| \(b_{safe}^C\) (35–40%) | Limiar SOC para disparar recarga | `PROFILE_CONSERVATIVE.b_safe_ratio = 0.35` | ✅ |
| \(b_{safe}^A\) (15–20%) | Limiar mais baixo | `PROFILE_AGGRESSIVE.b_safe_ratio = 0.18` | ✅ |
| \(b_{target}^C\) / buffer grande (20–30%) | Nível mínimo pós-recarga + buffer | Não existe campo `b_target`; usa `safety_margin_ratio=0.20` como buffer pós-recarga no cálculo de quantidade | ⚠️ Parcial |
| \(b_{target}^A\) / buffer pequeno (5–10%) | Recarga mínima + buffer pequeno | `safety_margin_ratio=0.08` no agressivo | ✅ (como buffer) |
| \(\delta_{time}^C\) | Slack de tempo extra nas janelas | Não existe no `RechargeProfile` nem na lógica de janelas | ❌ |
| \(\delta_{time}^A\) | Slack reduzido | Idem | ❌ |

**Resumo:**  
- **Quando** recarregar: controlado por `b_safe` (e por `total_energy_needed`). ✅  
- **Quanto** recarregar: controlado por `safety_margin_ratio` em `_calculate_recharge_amount` e no loop. ✅  
- **Folga nas janelas:** \(\delta_{time}\) não implementada. ❌  

**Onde no código:**  
- `RechargeProfile`: `b_safe_ratio`, `b_critical_ratio`, `safety_margin_ratio`, `prefer_nearest_station`.  
- Não há: `b_target_ratio`, `delta_time` ou equivalente.

---

## 3. Mecânica de decodificação com perfis (§3)

### 3.1 Algoritmo genérico e trigger de recarga

| Item no doc | Status | Detalhes |
|-------------|--------|----------|
| Pseudocódigo “Para cada cliente i” + decisão de recarga | ✅ | Loop `for customer in customer_nodes` com passo A (capacidade), B (energia/recarga), C (visita), D (resgate). |
| **“Se (SOC_atual - consumo < b_safe[perfil]): necessita recarga antes de i”** | ✅ | Loop `while need_recharge`: `need_recharge = current_battery < total_energy_needed` **ou** `_should_recharge_preventively(..., profile)` quando há perfil. `_should_recharge_preventively` usa `b_safe` e `b_critical`. |
| SelecionarEstação(último_nó, próximo_cliente, perfil) | ✅ | `_get_best_station(..., prefer_nearest_station=profile.prefer_nearest_station)`: C → Smart Detour, A → estação mais próxima. |
| CalcularQuantidadeRecarga(estação, próximo_destino, perfil) | ✅ | `_calculate_recharge_amount(..., profile)` usa `profile.safety_margin_ratio`; chamado em `_recharge_at_station` e no retorno ao depósito. |
| Cliente impossível (energia ida+volta > capacidade) | ✅ | `raw_energy_needed > context.battery_capacity` → `solution.skipped_customer_ids.append(customer.id)`, não visita, não altera G2. |
| Retorno ao depósito com perfil | ✅ | `return_to_depot(..., profile=profile)` usa `margin_ratio` do perfil e `prefer_nearest_station` em todas as chamadas a `_get_best_station` internas. |

### 3.2 Look-ahead “próximos N vs K clientes”

| Item no doc | Status | Detalhes |
|-------------|--------|----------|
| **C:** \(Q_{recarga}^C = \min\{Q^{bat},\; E_{necessária}(próximos\_N\_clientes) + buffer\_grande\} - SOC_{atual}\) | ❌ | `_calculate_recharge_amount` e `_calculate_total_energy_for_customer` consideram apenas **o próximo cliente** (estação → cliente → segurança). Não há soma de energia para N clientes à frente. |
| **A:** \(Q_{recarga}^A = E_{necessária}(próximos\_K\_clientes) + buffer\_pequeno - SOC_{atual}\), K < N | ❌ | Mesmo: look-ahead de um único cliente. |

**Onde no código:**  
- `_calculate_recharge_amount`: usa `_calculate_total_energy_for_customer(best_station, customer, context)[1]` e `safety_margin_ratio`.  
- Não existe função “energia necessária para os próximos n clientes” nem parâmetros N/K no perfil.

---

## 4. Integração com populações A_F e A_I (§4)

A atribuição de perfil e a reavaliação condicional são definidas no **algoritmo** (ex.: `battery_focused_nsga2.py`), não no decoder. O decoder apenas **recebe** flags e aplica o perfil.

| Item no doc | Onde implementado | Status |
|-------------|-------------------|--------|
| Decodificar com C para candidatos a \(A_F\) | Problema/algoritmo passa `force_battery_feasible=True` → decoder usa `PROFILE_CONSERVATIVE` | ✅ (fora do decoder) |
| Decodificar com A para candidatos a \(A_I\) | `force_battery_feasible=False` e não radical → `PROFILE_AGGRESSIVE` | ✅ (fora do decoder) |
| Modo radical (sem estações) | `use_radical_infeasible=True` → `profile = None`, não insere estações | ✅ |
| Tag de perfil por indivíduo | Doc: “cada indivíduo tem tag de perfil”. No decoder o perfil é **inferido** por `force_battery_feasible` e `use_radical_infeasible`, não há atributo `individual.profile` | ⚠️ Fora do decoder; decoder não recebe “tag” explícita |
| Reavaliação condicional (CV=0 com A → candidato a \(A_F\); CV>ε com C → candidato a \(A_I\)) | Lógica de arquivos e reparo no algoritmo | ⚠️ Fora do decoder |

**No decoder especificamente:**  
- Entrada: `force_battery_feasible`, `use_radical_infeasible`.  
- Perfil derivado internamente: C / A / None.  
- Não há: parâmetro `profile=` na assinatura de `decode()` para receber tag explícita do indivíduo.

---

## 5. Controle de qualidade dos inviáveis (§5)

CV_max, descarte e critério de entrada em \(A_I\) por objetivos são tratados no **algoritmo** (battery_focused_nsga2), não no decoder.

| Item no doc | Onde | Status |
|-------------|------|--------|
| \(CV_{max} = k \cdot Q^{bat}\), descartar se CV > CV_max | `battery_focused_nsga2.py`: filtro pós-merge com `_cv_max_ratio` | ✅ (fora do decoder) |
| Entrada em \(A_I\): \(f_1 \leq \text{quantil}_p(f_1, A_F)\) ou \(f_2 \leq \text{quantil}_p(f_2, A_F)\) | `_update_two_archives`: filtro por quantil 0.5 nos factíveis | ✅ (fora do decoder) |

O **decoder** apenas calcula a solução e acumula G2 (CV de bateria); não decide descarte nem entrada em arquivos.

---

## 6. Tratamento de casos limite (§7)

### 7.1 Infactibilidade estrutural e reparo

| Item no doc | Status | Detalhes no decoder |
|-------------|--------|----------------------|
| Se com **ambos** os perfis a rota continua inviável (excesso duração, carga, cliente inalcançável) | Parcial | Carga: split (novo veículo). Bateria: se não consegue chegar à estação, retorna ao depósito (split) ou descarta cliente; em modo inviável permite dívida. |
| **Reparo estrutural mínimo**: split, reordenar (2-opt, relocate), estação adicional forçada | ❌ | Não há 2-opt nem relocate nem “inserir estação adicional forçada” como reparo. Apenas split (fechar rota e abrir nova). |
| Se ainda inviável após reparo: marcar como descartável (CV > CV_max) | ⚠️ | Descarte por CV_max é feito no algoritmo após decodificação, não no decoder. |

### 7.2 Mesma permutação, dois fenótipos

| Item no doc | Status | Detalhes |
|-------------|--------|----------|
| Decodificar mesma permutação com C → solução de referência; com A → versão “esticada”, possivelmente inviável | ❌ | O decoder é chamado **uma vez** por indivíduo com um único perfil (derivado das flags). Não há chamada dupla (C e A) para a mesma permutação no fluxo atual. |

Para implementar: o algoritmo poderia, para um subconjunto de indivíduos, chamar `decode(ind, ..., force_battery_feasible=True)` e `decode(ind, ..., force_battery_feasible=False, use_radical_infeasible=False)` e usar os dois fenótipos (ex.: um em A_F e um em A_I).

---

## 8. Funções e pontos específicos do decoder.py

### Implementado

- **`RechargeProfile`** com `b_safe_ratio`, `b_critical_ratio`, `safety_margin_ratio`, `prefer_nearest_station`.  
- **`PROFILE_CONSERVATIVE`** e **`PROFILE_AGGRESSIVE`** com valores alinhados ao doc.  
- **`_get_best_station`**: Smart Detour vs estação mais próxima via `prefer_nearest_station`.  
- **`_should_recharge_preventively`**: usa `b_safe` e `b_critical`; chamada no loop do decode para trigger por SOC.  
- **`_calculate_recharge_amount`**: margem por perfil; look-ahead apenas **um** cliente.  
- **`_recharge_at_station`**: recebe `profile`, repassa para `_get_best_station` e `_calculate_recharge_amount`; modo dívida quando `allow_debt=True`.  
- **`decode()`**:  
  - Deriva perfil de `force_battery_feasible` e `use_radical_infeasible`.  
  - Loop com trigger por `total_energy_needed` e por `_should_recharge_preventively` (b_safe).  
  - Cliente impossível (raw_energy > capacity) descartado sem alterar G2.  
  - `return_to_depot(..., profile=profile)` em todos os pontos de retorno.  
- **`return_to_depot`**: parâmetro `profile`; usa `margin_ratio` e `prefer_nearest_station` em todas as escolhas de estação e margens de segurança (incluindo cadeia de recargas).  
- **Modo radical**: `profile=None`, sem inserção de estações; viagem com dívida quando necessário.  
- **Split por capacidade** e **split por bateria** (retorno ao depósito e novo veículo).

### Não implementado (no decoder)

1. **\(\delta_{time}\) (slack de tempo por perfil)**  
   - Não existe no `RechargeProfile`.  
   - Janelas são usadas para espera e para cálculo de atraso/satisfação; não há “janela estendida” por perfil para decisão de recarga.

2. **Look-ahead N (C) e K (A) clientes na quantidade de recarga**  
   - Recarga é calculada com base apenas no próximo cliente (+ buffer do perfil).  
   - Não há parâmetros N/K nem função de energia para os próximos n clientes.

3. **Parâmetro explícito `b_target`**  
   - Efeito de “target pós-recarga” é obtido indiretamente pelo buffer (`safety_margin_ratio`).  
   - Não há campo `b_target_ratio` no perfil.

4. **Reparo estrutural (2-opt, relocate, estação forçada)**  
   - Nenhum desses passos existe no decoder; apenas split de rota por capacidade/bateria.

5. **Decodificação dupla (C e A) da mesma permutação**  
   - Não é feita dentro do decoder; seria no chamador (algoritmo).

6. **Assinatura `decode(..., profile=...)`**  
   - Perfil é sempre inferido; não há opção de passar a tag de perfil explicitamente (útil se no futuro o indivíduo carregar `individual.profile`).

---

## 9. Tabela resumo: documento vs decoder.py

| Seção / Item | Implementado | Parcial | Não implementado |
|--------------|--------------|---------|-------------------|
| §2.1 Representação (genótipo/fenótipo) | ✅ | | |
| §2.2 Perfis C e A (b_safe, buffer) | ✅ | | |
| §2.2 \(\delta_{time}^C\), \(\delta_{time}^A\) | | | ❌ |
| §3.1 Trigger recarga por b_safe | ✅ | | |
| §3.1 Algoritmo genérico (loop, recarga, visita) | ✅ | | |
| §3.2 SelecionarEstação por perfil | ✅ | | |
| §3.2 CalcularQuantidadeRecarga por perfil | ✅ | | |
| §3.2 Look-ahead N/K clientes | | | ❌ |
| §4.1 Atribuição C/A por flags (fora do decoder) | ✅ | | |
| §4.1 Tag de perfil no indivíduo | | ⚠️ (inferida, não explícita) | |
| §5 CV_max e filtro A_I (fora do decoder) | ✅ | | |
| §7.1 Reparo estrutural (2-opt, relocate, estação forçada) | | | ❌ |
| §7.2 Mesma permutação, dois fenótipos (C e A) | | | ❌ |
| return_to_depot com perfil | ✅ | | |
| Cliente impossível (raw_energy > capacity) | ✅ | | |

---

## 10. Recomendações para alinhamento futuro

1. **Opcional:** Adicionar ao `RechargeProfile`:
   - `delta_time` (ou `time_slack_ratio`) e usar na lógica de janelas/atraso se quiser diferenciar C e A no tempo.
   - `look_ahead_n` (C) e `look_ahead_k` (A) e, em `_calculate_recharge_amount` (ou função auxiliar), energia para os próximos n clientes + buffer.
2. **Opcional:** Assinatura `decode(..., profile: Optional[RechargeProfile] = None)`; se `profile` for passado, usá-lo em vez de derivar de flags (permite tag por indivíduo).
3. **Opcional:** No algoritmo, para alguns indivíduos, chamar decode duas vezes (C e A) e usar ambos os fenótipos nos arquivos.
4. **Opcional:** Reparo estrutural (2-opt, relocate, inserção forçada de estação) em módulo separado ou no final do decode quando a rota ficar inviável mesmo após split.

Com isso, o documento fica como referência clara do que o decoder já cobre e do que ainda pode ser estendido para aderência total ao DECODER_ALTERNATIVO.md.
