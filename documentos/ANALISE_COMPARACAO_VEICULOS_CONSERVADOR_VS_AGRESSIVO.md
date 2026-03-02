# Análise: diferença no número de veículos entre modo conservador e agressivo

## 1. O que os resultados mostram

No script de comparação (permutações aleatórias, rc208_21, 100 clientes):

| Métrica        | Conservador (C) | Agressivo (A) |
|----------------|-----------------|---------------|
| **n_vehicles** | ~50 (44–56)     | **2** (sempre) |
| f1 (custo)     | ~56k            | ~7k           |
| G2 (violação)  | 0               | ~70           |
| n_recharges    | ~147            | ~77           |

Ou seja: no **conservador** usamos dezenas de veículos; no **agressivo**, sempre 2. Isso é **comportamento esperado do decoder**, não bug. Abaixo está o porquê e em que sentido é (ou não) o que queríamos.

---

## 2. Quando o decoder abre um novo veículo?

No `decoder.py`, um **novo veículo** (fechar rota atual, voltar ao depósito, abrir nova rota) só ocorre nos seguintes pontos.

### 2.1. Por capacidade de carga (ambos os modos)

- **Condição:** `current_load + customer.demand > context.vehicle_capacity`
- **Ação:** `return_to_depot`, fecha rota, `current_vehicle += 1`, novo veículo com bateria e carga zeradas.
- **Onde:** início do loop por cliente (Passo A), tanto em modo conservador quanto agressivo.

Ou seja: **só abrimos novo veículo por “lotação” quando a carga acumulada não cabe mais no veículo.**

### 2.2. Por bateria (apenas modo conservador)

- **Condição:** `force_battery_feasible=True` e, no loop de recarga preventiva, **não conseguimos chegar a nenhuma estação** (nem para recarregar nem para seguir).
- **Detalhe:** em modo conservador chamamos `_recharge_at_station(..., allow_debt=False)`. Se a bateria atual não permite alcançar nenhuma estação, a função devolve a posição/bateria/tempo **inalterados**.
- **Decisão:** se `new_position == current_position` (ficamos “presos”), o decoder:
  - Se **consegue** voltar ao depósito: faz `return_to_depot`, fecha rota, **abre novo veículo** (`current_vehicle += 1`) e continua a permutação a partir do depósito (bateria cheia).
  - Se **não consegue** nem voltar ao depósito: ainda assim chama `return_to_depot` (cadeia de estações), fecha rota, abre novo veículo e marca o cliente como não visitado.

Em resumo: em **modo conservador**, “não tenho bateria para ir a nenhuma estação e preciso recarregar” → **volta ao depósito e abre outro veículo** (para manter G2 = 0). Em **modo agressivo** isso **nunca** acontece: não há abertura de veículo por bateria.

### 2.3. Modo agressivo: nenhum split por bateria

- Com `force_battery_feasible=False`, o bloco do “loop de recarga preventiva” (Passo B) **não é executado**.
- Se não há bateria para o próximo cliente, o decoder pode:
  - Ir a uma estação **com dívida** (`allow_debt=True`) e acumular G2, ou
  - No Passo C, ir direto ao cliente **com dívida** e acumular G2.
- Em nenhum desses casos o código chama `return_to_depot` + `current_vehicle += 1` por causa de bateria.

Conclusão: **no agressivo, novo veículo só abre por capacidade de carga.**

---

## 3. Por que conservador ≈ 50 veículos e agressivo = 2?

- **Permutações aleatórias** tendem a sequências ruins: clientes longe um do outro, longe do depósito e das estações.
- **Conservador:** a cada “bloco” da sequência em que, após recarregar (ou tentar), ainda não dá para ir ao próximo cliente sem violar bateria, o decoder **volta ao depósito e abre outro veículo**. Com sequência ruim isso se repete muitas vezes → muitas rotas curtas → **~1–2 clientes por rota em média** → ~50 veículos para 100 clientes.
- **Agressivo:** bateria não força split. Novo veículo só quando a **carga** enche. Se a capacidade do veículo for grande em relação à demanda total (ex.: 100 clientes com demanda média 20 e capacidade 1000), **só precisamos de 2 veículos por carga** (ex.: ~50 clientes por veículo). Daí **sempre 2 veículos**, com G2 alto e muitas recargas/dívidas na mesma rota.

Ou seja: a diferença abismal de veículos vem de:
1. **Conservador:** split por **bateria** (muitas vezes em permutações ruins).
2. **Agressivo:** split **só por carga** (e na rc208_21 a carga só exige 2 veículos).

---

## 4. Isso é o comportamento que queríamos?

### 4.1. Em relação ao documento (DECODER_ALTERNATIVO)

- **Perfil C:** gerar soluções **factíveis** (G2 = 0). O decoder faz isso ao custo de **quebrar rota e abrir novo veículo** sempre que não há como continuar sem violar bateria. **Está alinhado ao doc.**
- **Perfil A:** gerar soluções **inviáveis mas úteis** (G2 moderado, boa qualidade em f1/f2). O decoder nunca abre veículo por bateria, só por carga; a violação vai para G2. **Também alinhado.**

Ou seja: **em termos de “C = viável, A = inviável controlado”, o comportamento está correto.**

### 4.2. O que pode não ser o que queríamos (comparação “justa”)

Se a intenção era comparar **só a política de recarga** na **mesma estrutura de rotas** (mesmo número de veículos, mesma ordem de visita), então:

- **Hoje não estamos comparando isso.** Estamos comparando:
  - C: **muitas rotas curtas e viáveis** (split frequente por bateria).
  - A: **poucas rotas longas e inviáveis** (sem split por bateria, só por carga).
- Ou seja: **estrutura de solução diferente** (número de veículos, tamanho das rotas), não apenas “mesma rota, recarga C vs A”.

Para uma comparação “mesma estrutura, só recarga diferente” seria necessário, por exemplo:
- Fixar as rotas (ex.: uma partição fixa dos clientes por veículo) e, dentro de cada rota, comparar C vs A; ou
- Usar permutações “boas” (ex.: saída de um construtor ou do próprio NSGA-II) em que o conservador não precise fazer dezenas de splits por bateria.

---

## 5. Resumo e recomendações

| Pergunta | Resposta |
|----------|----------|
| O decoder está errado? | Não. Ele abre novo veículo por **carga** (C e A) e, só no **conservador**, por **bateria** quando fica “preso”. |
| Por que C ≈ 50 e A = 2? | C faz muitos splits por bateria em sequências ruins; A só faz split por carga, e na instância 2 veículos bastam por carga. |
| É o que o documento pede? | Sim: C viável (G2=0), A inviável (G2>0); o custo em C é muitas rotas. |
| A comparação é “justa”? | Depende do objetivo: se for “mesma rota, outra política de recarga”, não — as estruturas (nº de veículos) são diferentes. |

**Recomendações:**

1. **Documentar no TCC** que, no modo conservador, a garantia de viabilidade (G2=0) leva a **split por bateria** e portanto a mais veículos em permutações ruins; no agressivo, não há split por bateria, apenas por carga.
2. **Para comparação “recharge policy only”:** rodar o comparativo com permutações de **boas soluções** (ex.: elites do NSGA-II com decoder conservador) ou com **partição fixa de clientes por veículo** e comparar só a gestão de recarga em cada rota.
3. **Opcional no decoder:** registrar em log quando um novo veículo é aberto **por bateria** (ex.: contador “splits por bateria”) para relatórios e análises.

Assim, a diferença abismal no número de veículos é **comportamento esperado e coerente com o desenho atual**; o que pode ser ajustado é o **contexto da comparação** (permutações aleatórias vs. soluções estruturadas) conforme o objetivo do experimento.
