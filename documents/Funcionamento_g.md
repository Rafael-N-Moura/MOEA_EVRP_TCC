O parâmetro **`g inverse refueling rate`** (taxa inversa de reabastecimento) representa o **tempo necessário para recarregar uma única unidade de bateria** (ou combustível) do veículo elétrico.

Na formulação clássica do EVRPTW proposta por Schneider et al. (2014), assume-se geralmente uma política de recarga total (*full recharge policy*). Isso significa que, sempre que um veículo visita uma estação de recarga, a bateria é recarregada até a sua capacidade máxima. O tempo que o veículo passa na estação não é fixo; ele é proporcional à quantidade de energia que precisa ser reposta.

### Como funciona o cálculo

Para calcular o tempo exato gasto na estação de recarga, o modelo utiliza a seguinte lógica matemática:

Seja $Q$ a capacidade máxima da bateria e $q$ o nível de carga com o qual o veículo chega à estação. A quantidade de bateria consumida e que precisa ser reposta é $(Q - q)$. O tempo de recarga é calculado multiplicando essa quantidade pelo parâmetro $g$:

$$Tempo_{recarga} = (Q - q) \times g$$

**Exemplo prático com os dados da sua instância:**

* A capacidade máxima da bateria ($Q$) é **77.75**.
* A taxa inversa de recarga ($g$) é **0.39**.
* Se o veículo chega à estação com **27.75** de bateria restante, ele precisa repor **50.0** unidades ($77.75 - 27.75$).
* O tempo consumido apenas para a recarga física será: $50.0 \times 0.39 = 19.5$ unidades de tempo.

### Por que "taxa inversa"?

Uma taxa de recarga comum seria expressa em "unidades de energia por minuto" (por exemplo, recarregar 2.56 unidades de bateria por minuto). A taxa *inversa* é literalmente o inverso matemático dessa fração ($1 / 2.56 \approx 0.39$), expressando **"minutos por unidade de energia"**.

Essa inversão é usada para facilitar a formulação linear do problema: em vez de dividir a energia necessária pela taxa de recarga para encontrar o tempo, o modelo permite que você simplesmente multiplique a energia necessária por $g$.

### Impacto nas Janelas de Tempo (Time Windows)

No contexto do EVRPTW, esse parâmetro é essencial para a viabilidade da rota. O tempo de recarga avança o relógio da rota do veículo. Se a taxa inversa for alta (demora muito para recarregar), o veículo gastará muito tempo na estação de recarga e correrá o risco de violar o `DueDate` (o limite superior da janela de tempo) do próximo cliente que precisa ser visitado.
