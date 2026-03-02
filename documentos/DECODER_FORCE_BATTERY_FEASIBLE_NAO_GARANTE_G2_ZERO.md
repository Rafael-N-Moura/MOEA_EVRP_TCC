# Por que `force_battery_feasible=True` pode gerar G2 > 0?

## Expectativa vs. implementação

- **Expectativa:** Com `force_battery_feasible=True`, o decoder sempre inseriria recargas e retornaria ao depósito quando necessário, produzindo **sempre** solução viável (G2 = 0), independente da permutação.

- **Implementação:** `force_battery_feasible=True` faz o decoder **tentar** ser viável (inserir recargas, não viajar “com dívida”), mas em várias situações **estruturais** ou **geométricas** ele ainda registra violação e define **G2 > 0**. Ou seja, **não há garantia** de G2 = 0.

## Onde o decoder define G2 > 0 mesmo com `force_battery_feasible=True`

Trechos em `src/decoder.py` onde `solution.battery_violation` (G2) é aumentado mesmo em modo conservador:

### 1. Cliente impossível (linhas ~799–822)

- **Condição:** `total_energy > context.battery_capacity`, onde `total_energy` = energia para ir ao cliente + energia do cliente até a segurança (estação/depósito).
- **Significado:** O cliente está tão longe (da origem atual e/ou de qualquer estação/depósito) que **nenhum** veículo com aquela bateria consegue atendê-lo e voltar em segurança, mesmo recarregando.
- O decoder não “inventa” viabilidade: marca o déficit e segue (G2 > 0).

### 2. Bateria insuficiente após recarga preventiva (linhas ~823–842)

- **Condição:** Modo conservador, mas a bateria atual já não é suficiente para o próximo trecho (e não se enquadra no “cliente impossível” acima).
- Pode ocorrer quando a lógica de recarga preventiva não cobre algum caso (ex.: sequência de clientes que deixa o veículo sem bateria para o próximo movimento mesmo após recarregar).
- O decoder registra o déficit (G2 > 0).

### 3. Retorno ao depósito: não consegue chegar à estação (linhas ~1046–1062)

- **Condição:** Para retornar ao depósito, o decoder decide ir antes a uma estação para recarregar, mas **a bateria atual não dá para chegar a essa estação**.
- Mesmo em modo conservador, nesse ponto ele não “inventa” energia: registra violação (G2 > 0).

### 4. Retorno ao depósito: não consegue voltar mesmo após recarga (linhas ~1126–1141)

- **Condição:** Depois de recarregar na estação, a bateria **ainda não** é suficiente para chegar ao depósito.
- Pode acontecer se a estação está longe do depósito ou a capacidade de bateria é muito baixa. O decoder registra o déficit (G2 > 0).

## Consequência para o reparo na offspring

Quando enviamos 50 indivíduos para “reparo” (reavaliação com `force_battery_feasible=True`):

- O decoder **tenta** torná-los viáveis (inserir recargas, evitar dívida).
- Se a **permutação** (ordem de clientes) levar a pelo menos uma das situações acima (cliente inalcançável, ou retorno impossível mesmo com recarga), a solução continua com **G2 > 0**.
- Por isso é perfeitamente possível que **0 viáveis** (ou poucos) surjam desses 50: não é bug do algoritmo de reparo, e sim do **decoder** que, por design, não garante G2 = 0 quando a rota é estruturalmente inviável.

## Resumo

| Modo                         | Comportamento                         | G2 = 0 garantido? |
|-----------------------------|----------------------------------------|--------------------|
| `force_battery_feasible=True`  | Insere recargas, evita dívida quando possível | **Não** – só tenta; situações impossíveis geram G2 > 0 |
| `force_battery_feasible=False` | Permite viagem com dívida              | Não – explora rotas inviáveis de propósito |

Para que **toda** reavaliação com `force_battery_feasible=True` resultasse em G2 = 0, seria preciso alterar o decoder (por exemplo: não visitar clientes inalcançáveis, ou tratar retorno ao depósito de forma “virtual”), o que mudaria a definição do problema (quais soluções são consideradas viáveis).

---

## Alterações no decoder: G2 = 0 garantido com `force_battery_feasible=True`

O decoder foi alterado para **nunca** somar G2 em modo conservador. Cada caso passou a ser tratado assim:

| Caso | Tratamento (sem aumentar G2) |
|------|------------------------------|
| **1. Cliente impossível** | Cliente é **descartado**: não é visitado, é adicionado a `solution.skipped_customer_ids`, e o loop segue para o próximo. A insatisfação considera não atendidos como 0 de satisfação. |
| **2. Bateria insuficiente após recarga** | Eliminado pela lógica: um **loop** de recarga preventiva garante `current_battery >= total_energy_needed` (ida + safety) antes de ir a qualquer cliente. Se após recargas ainda não der, faz split (novo veículo) ou descarta o cliente. Se por edge case ainda assim chegar ao Passo C sem bateria, o cliente é descartado (sem G2). |
| **3. Retorno: não consegue chegar à estação** | O safety buffer é aplicado também ao **último** cliente pelo mesmo loop. Se ainda assim em `return_to_depot` não houver bateria para a estação, **não** se soma G2: registra-se o passo de retorno ao depósito com bateria 0. |
| **4. Retorno: não consegue voltar após recarga** | Em vez de somar G2, é feita uma **cadeia de recargas**: vai à próxima estação adequada (`_get_best_station`), recarrega, e repete até ter bateria para chegar ao depósito (com limite de iterações). Sem G2. |

Com isso, **`force_battery_feasible=True` passa a garantir G2 = 0**; soluções podem ter clientes não visitados (`skipped_customer_ids`) ou retorno com bateria 0, mas sem violação de bateria contabilizada.
