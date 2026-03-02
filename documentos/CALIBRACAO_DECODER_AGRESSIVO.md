# Calibração do decoder em modo agressivo

## Objetivos (comparação C vs A em permutações aleatórias)

1. **n_vehicles_A** ≈ 10–30% abaixo de n_vehicles_C (não ~96%).
2. **total_distance_A** ≈ 5–20% menor que total_distance_C.
3. **10–30%** das soluções agressivas com **g2 = 0**.
4. **g2_max**: teto (ex.: 10–20% da energia total do tour); maioria dos agressivos com g2 bem abaixo.

---

## Mudanças estruturais em `src/decoder.py`

### 1. `RechargeProfile`

- **g2_max_ratio** (opcional): se definido, por rota não se permite acumular G2 acima de `g2_max_ratio * Q_bat`; ao superar, faz split (volta ao depósito, novo veículo).
- **max_customers_per_route** (opcional): no modo agressivo, após esse número de clientes na rota atual, força split (objetivo: n_vehicles_A ~10–30% abaixo de C).

### 2. Modo agressivo no `decode()`

- **Recarga preventiva por b_safe:** entra no bloco de recarga quando `current_battery < energy_to_customer` **ou** `current_battery < Q_bat * profile.b_safe_ratio` (SOC baixo).
- **Split antes de ir à estação com dívida:** se `current_route_g2 + deficit_to_station > g2_max_per_route`, faz split e reprocessa o mesmo cliente com novo veículo.
- **Split antes de ir ao cliente com dívida (Passo C):** mesma regra; se ao adicionar o déficit o G2 da rota superaria `g2_max_per_route`, faz split.
- **Split após o cliente:** ao fim do processamento do cliente, se `current_route_g2 > g2_max_per_route` **ou** se `max_customers_per_route` foi atingido, fecha a rota e abre outra.
- **Rastreamento de G2 por rota:** variável `current_route_g2`; zerada ao abrir novo veículo; atualizada em toda adição de dívida (`_travel_with_debt`, recarga com dívida, resgate).

### 3. Loop principal

- Loop **while** com `customer_idx` para permitir **retry** do mesmo cliente após um split (não avançar o índice nesses casos).
- Incremento de `customer_idx` apenas quando o cliente é efetivamente processado ou ignorado (skip).

### 4. Critério de recarga agressivo (ida + volta)

- **total_energy_agg** = energia até o cliente + **max(energia cliente→estação, energia cliente→depósito)** + margem.  
  Garante que, após visitar o cliente, haja energia para voltar ao depósito (ou estação), evitando dívida no retorno.

### 5. Mix viável/inviável (10–30% g2=0, maioria g2 abaixo do teto)

- **Passo C:** no modo agressivo, permitir **viagem com dívida** ao cliente quando `current_route_g2 + deficit ≤ g2_max_per_route` (split só se superar o teto). Assim há soluções com g2 > 0 (inviáveis) controladas pelo teto.
- **return_to_depot:** no modo agressivo, tentar **recarga preventiva** no retorno só quando o déficit é pequeno (≤ 6% da capacidade `Q`); caso contrário registra dívida. Se tentar preventiva e não conseguir alcançar nenhuma estação, também registra dívida. Resultado: parte das soluções com g2 = 0 (viáveis), maioria com g2 > 0 mas abaixo do teto.

### 6. Perfil agressivo atual (`PROFILE_AGGRESSIVE`)

- **b_safe_ratio** = 0.42  
- **safety_margin_ratio** = 0.18  
- **g2_max_ratio** = 0.05 (split por G2 quando rota > 5% Q_bat)  
- **max_customers_per_route** = 3 (100 clientes / 3 ≈ 34 veículos)

---

## Resultados (rc208_21, 100 permutações, seed 42) — calibração atingida

| Métrica        | Conservador (C) | Agressivo (A) | Alvo / observação |
|----------------|------------------|---------------|-------------------|
| n_vehicles     | ~50              | **34**        | ✓ ~32% abaixo de C (objetivo 1) |
| total_distance | ~6086            | **~5453**     | ✓ ~10% menor (objetivo 2) |
| f1             | ~56k             | ~39k          | ✓ ~30% menor (custo) |
| g2             | 0                | **~17.8** (min 0, max ~42.5) | ✓ maioria abaixo do teto (objetivo 4) |
| % g2=0         | 100%             | **~20%**      | ✓ no alvo 10–30% (objetivo 3); restante com g2 > 0 (soluções inviáveis) |
| n_recharges    | ~147             | ~38           | — |

---

## Ajustes opcionais futuros

- **n_vehicles_A:** alterar **max_customers_per_route** (ex.: 4 para menos veículos, 2 para mais).
- **Outras instâncias:** recalibrar **g2_max_ratio**, **max_customers_per_route** e **b_safe_ratio** por instância.

Os parâmetros do perfil agressivo estão em `src/decoder.py` em `PROFILE_AGGRESSIVE`; o script `scripts/compare_decoder_profiles.py` serve para checar os efeitos das mudanças.
