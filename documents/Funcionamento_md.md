
---

### **Como funciona o parâmetro $md$ (Maximum Allowable Delay)**

No contexto das Janelas de Tempo (Time Windows), cada cliente $i$ define um horário em que o veículo pode chegar: o mais cedo possível ($b_i$) e o mais tarde possível ($e_i$).

O **$md$** (Atraso Máximo Permitido) atua como um mecanismo de **flexibilização restrita** para essas janelas de tempo, criando uma restrição "suave" (soft constraint).

Aqui está como ele funciona na prática e na matemática do modelo:

#### 1. A Regra do Atraso

O modelo permite que o veículo chegue *depois* do horário limite do cliente ($e_i$), mas esse atraso tem um teto rigoroso definido pelo **$md$**.

* O tempo de atraso ($dt_i$) de um veículo no cliente é calculado como a diferença entre o horário de chegada ($a_i$) e o horário limite ($e_i$). Se o veículo chegar antes do horário limite, o atraso é zero: $dt_i = \max\{0, a_i - e_i\}$.


* **A Restrição:** O atraso $dt_i$ de qualquer cliente atendido **não pode ser maior** que $md$. A equação matemática no artigo define isso como: $dt_i x_{ij}^k \le md$.



#### 2. Definindo a Viabilidade da Solução

É aqui que o $md$ se conecta com a essência do algoritmo (o uso de soluções inviáveis).

* Se o atraso de todos os clientes em uma rota for **menor ou igual a $md$**, a restrição de tempo foi respeitada.
* Se o atraso de *qualquer* cliente for **maior que $md$**, a solução inteira é classificada como **inviável** (infeasible).



#### 3. Quantificando o "Quão Inviável" a solução é

O algoritmo não descarta a solução só porque ela ultrapassou o $md$. Ele calcula o grau de violação dessa restrição ($CV_{delay}$). O algoritmo soma todos os atrasos que excederam o $md$ usando a fórmula $\max\{0, \text{atraso total do cliente} - md\}$. Soluções que ultrapassam o $md$ apenas um pouquinho recebem uma penalidade leve e são mantidas na população para ajudar a explorar o mapa.



**Em resumo:** O parâmetro **$md$** não é apenas o limite de tolerância do cliente para receber sua entrega atrasada. No ecossistema deste algoritmo, ele é a **linha divisória exata entre uma rota viável e inviável** , servindo como a principal métrica matemática que o algoritmo manipula para forçar a exploração de caminhos que outras IAs ignorariam.