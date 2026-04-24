#!/usr/bin/env python3
"""
experimento_principal.py
========================
Experimento Principal do TCC — NSGA-II, SMS-EMOA e MOEA/D-WS sobre 50 instâncias
de Solomon (excluindo as 6 usadas no tuning) com as melhores configurações do
tuning_rs_v2.

Modos de operação (espelhando a estrutura do tuning_rs.py):

  Modo 1 — Geração (qualquer máquina, uma vez):
    python scripts/experimento_principal.py --generate
    → gera  results/experimento_principal/all_tasks.json

  Modo 2 — Execução (cada máquina em paralelo):
    python scripts/experimento_principal.py --run --machine-id 1
    python scripts/experimento_principal.py --run --machine-id 2
    python scripts/experimento_principal.py --run --machine-id 3
    python scripts/experimento_principal.py --run --machine-id 4
    python scripts/experimento_principal.py --run --machine-id 5
    → salva  results/experimento_principal/machine{N}/index.csv
             results/experimento_principal/machine{N}/fronts/{alg}__{inst}__run{RR}.pkl

  Modo 3 — Análise (após todas as máquinas terminarem):
    python scripts/experimento_principal.py --analyze
    → lê machine1-5, gera merged_index.csv e experiment_report.md

  Dry-run (verifica pipeline antes do run completo):
    python scripts/experimento_principal.py --run --machine-id 1 --dry-run

Configurações (resultados do tuning_rs_v2):
  NSGA-II  : pc=0.8549, pm=0.3942
  SMS-EMOA : pc=0.1884, pm=0.4551
  MOEA/D   : pc=0.2771, pm=0.6307, n_neighbors=20, prob_neighbor_mating=0.9709,
             decomposition="tchebycheff", ref_dirs_method="energy"

50 instâncias de Solomon (21 clientes, sufixo _21) excluindo as 6 do tuning.
30 runs por algoritmo por instância → 4.500 runs no total.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Threading constraints — ANTES de qualquer numpy import
# ─────────────────────────────────────────────────────────────────────────────
import os
os.environ.setdefault("OMP_NUM_THREADS",     "1")
os.environ.setdefault("MKL_NUM_THREADS",     "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1")
os.environ.setdefault("BLIS_NUM_THREADS",    "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import sys, time, csv, json, pickle, hashlib, argparse, warnings, traceback
from datetime import datetime
from multiprocessing import Pool
import multiprocessing

# Fix para Python >= 3.14 onde "spawn" passa a ser o default em macOS/Linux.
# O "fork" é necessário para que os sub-processos herdem o estado do processo
# principal (ROOT no sys.path, variáveis de ambiente de threading, etc.) sem
# custo de reimportação. Em caso de conflito (método já definido), ignora.
try:
    multiprocessing.set_start_method("fork", force=True)
except RuntimeError:
    pass

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Constantes globais
# ─────────────────────────────────────────────────────────────────────────────

# Número de runs independentes por (algoritmo, instância).
# 30 runs → intervalos de confiança de 95% com ~±5% de margem esperada.
N_RUNS = 30

# Orçamento de avaliações por run (critério de parada).
# 850.000 ≈ limite empírico de convergência observado no tuning v2.
N_EVALS = 850_000

# Tamanho da população — Das-Dennis H=13, 3 objetivos → exatamente 105 pontos.
POP_SIZE = 105

# Intervalo de snapshot da convergência (a cada 10k avaliações).
# Gera ~85 pontos de convergência por run — suficiente para curvas suaves.
CONVERGENCE_INTERVAL = 10_000

# Seed global para geração determinística das seeds por run.
# 44 ≠ tuning_v1 (42), tuning_v2 (43) → runs completamente independentes.
SEED_GLOBAL = 44

# Número de máquinas (espelha MACHINE_WEIGHTS e MACHINE_INFO abaixo).
N_MACHINES = 5

# Workers padrão de fallback (sobrescrito via --n-workers).
N_WORKERS = 10

# ─────────────────────────────────────────────────────────────────────────────
# Configurações dos algoritmos (resultado do tuning_rs_v2)
# ─────────────────────────────────────────────────────────────────────────────
# Cada entrada corresponde à configuração vencedora (melhor rank médio de HV
# sobre as 6 instâncias de tuning) identificada pelo experimento de Random Search.
# Campos MOEA/D ausentes em NSGA-II e SMS-EMOA são mantidos como None para
# manter a estrutura homogênea do dicionário de task.
ALGO_CONFIGS = {
    "nsga2": {
        "algorithm_id":         "nsga2",
        "pc":                   0.8549,
        "pm":                   0.3942,
        "pop_size":             POP_SIZE,
        "eliminate_duplicates": True,
        # Campos exclusivos do MOEA/D — None para NSGA-II
        "n_neighbors":          None,
        "prob_neighbor_mating": None,
        "decomposition":        None,
        "ref_dirs_method":      None,
        "pbi_theta":            None,
    },
    "smsemoa": {
        "algorithm_id":         "smsemoa",
        "pc":                   0.1884,
        "pm":                   0.4551,
        "pop_size":             POP_SIZE,
        "eliminate_duplicates": True,
        "n_neighbors":          None,
        "prob_neighbor_mating": None,
        "decomposition":        None,
        "ref_dirs_method":      None,
        "pbi_theta":            None,
    },
    "moead_ws": {
        "algorithm_id":         "moead_ws",
        "pc":                   0.2771,
        "pm":                   0.6307,
        "pop_size":             POP_SIZE,
        "eliminate_duplicates": False,   # MOEA/D não usa eliminate_duplicates
        "n_neighbors":          20,
        "prob_neighbor_mating": 0.9709,
        "decomposition":        "tchebycheff",
        "ref_dirs_method":      "energy",
        "pbi_theta":            None,    # tchebycheff não usa theta
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Instâncias do experimento principal
# ─────────────────────────────────────────────────────────────────────────────
# Todas as instâncias Solomon com 21 clientes (sufixo _21), EXCLUINDO as 6
# usadas no tuning (c101_21, c201_21, r101_21, r201_21, rc101_21, rc201_21).
# Total: 56 instâncias _21 disponíveis − 6 do tuning = 50 instâncias.
_TUNING_INSTANCES_EXCLUDED = {
    "c101_21", "c201_21", "r101_21", "r201_21", "rc101_21", "rc201_21"
}

# Lista ordenada de todas as _21 disponíveis menos as 6 excluídas.
# A ordem é explícita e estável — não depende de glob/listdir — garantindo
# reprodutibilidade total do task_id assignment.
_ALL_21 = [
    "c102_21", "c103_21", "c104_21", "c105_21", "c106_21",
    "c107_21", "c108_21", "c109_21",
    "c202_21", "c203_21", "c204_21", "c205_21", "c206_21",
    "c207_21", "c208_21",
    "r102_21", "r103_21", "r104_21", "r105_21", "r106_21",
    "r107_21", "r108_21", "r109_21", "r110_21", "r111_21",
    "r112_21",
    "r202_21", "r203_21", "r204_21", "r205_21", "r206_21",
    "r207_21", "r208_21", "r209_21", "r210_21", "r211_21",
    "rc102_21", "rc103_21", "rc104_21", "rc105_21", "rc106_21",
    "rc107_21", "rc108_21",
    "rc202_21", "rc203_21", "rc204_21", "rc205_21", "rc206_21",
    "rc207_21", "rc208_21",
]
assert len(_ALL_21) == 50, f"Esperado 50 instâncias, encontrado {len(_ALL_21)}"
assert not (_TUNING_INSTANCES_EXCLUDED & set(_ALL_21)), \
    "Instâncias do tuning não devem aparecer no experimento principal"

EXPERIMENT_INSTANCES = {
    name: os.path.join(ROOT, "evrptw_instances", f"{name}.txt")
    for name in _ALL_21
}

# ─────────────────────────────────────────────────────────────────────────────
# Informações das máquinas (throughput real medido nos logs do tuning v2)
# ─────────────────────────────────────────────────────────────────────────────
# elapsed_s/run medido nos logs do tuning_rs_v2 (600k evals):
#   maq64/maq67 (Ryzen 9 7950X): ~847s/run  → ~709 evals/s/run
#   maq65       (Ryzen 9 7900X): ~946s/run  → ~634 evals/s/run
#   maq66       (i9-10900F):    ~2499s/run  → ~240 evals/s/run
#   Dell G15    (i5-12500H):    ~1884s/run  → ~318 evals/s/run
#
# Para 850k evals (experimeto principal), ETA por run estimado:
#   maq64/67: ~1200s/run   maq65: ~1340s/run   maq66: ~3540s/run   Dell: ~2670s/run
#
# Pesos proporcionais ao throughput × workers: equalizam o wall-time entre máquinas.
#   Total throughput relativo: maq64(16w) + maq65(12w) + maq66(10w) + maq67(16w) + Dell(8w)
#   maq64: 16/1200 ≈ 0.01333  maq65: 12/1340 ≈ 0.00896  maq66: 10/3540 ≈ 0.00282
#   maq67: 16/1200 ≈ 0.01333  Dell:   8/2670 ≈ 0.00300
#   total ≈ 0.04144
#   pesos: maq64≈0.32  maq65≈0.22  maq66≈0.07  maq67≈0.32  Dell≈0.07  (soma=1.00)
#   Obs: pesos arredondados para 2 casas com ajuste de fechamento na máquina 3.
MACHINE_WEIGHTS = {
    1: 0.32,   # maq64  — Ryzen 9 7950X, 16 workers
    2: 0.22,   # maq65  — Ryzen 9 7900X, 12 workers
    3: 0.07,   # maq66  — i9-10900F,     10 workers
    4: 0.32,   # maq67  — Ryzen 9 7950X, 16 workers
    5: 0.07,   # Dell G15 — i5-12500H,    8 workers
}
assert abs(sum(MACHINE_WEIGHTS.values()) - 1.0) < 1e-9, \
    f"MACHINE_WEIGHTS deve somar 1.0, soma atual: {sum(MACHINE_WEIGHTS.values())}"

MACHINE_INFO = {
    1: ("maq64 (Ryzen 9 7950X, 16c)", 16),
    2: ("maq65 (Ryzen 9 7900X, 12c)", 12),
    3: ("maq66 (i9-10900F, 10c)",     10),
    4: ("maq67 (Ryzen 9 7950X, 16c)", 16),
    5: ("Dell G15 (i5-12500H, 8w)",    8),
}

# ETA por run (s) estimado para 850k evals por máquina (base: logs do tuning v2).
# Usado apenas para exibir estimativa de wall-time no início do --run.
MACHINE_ETA_PER_RUN_S = {
    1: 1200.0,   # maq64/67: ~709 evals/s
    2: 1340.0,   # maq65:    ~634 evals/s
    3: 3540.0,   # maq66:    ~240 evals/s
    4: 1200.0,   # maq67:    ~709 evals/s
    5: 2670.0,   # Dell:     ~318 evals/s
}

# ─────────────────────────────────────────────────────────────────────────────
# Campos do CSV de índice por máquina
# ─────────────────────────────────────────────────────────────────────────────
# Campos expandidos em relação ao tuning (inclui run_idx, n_evals_actual,
# n_f1_layers, timestamp_start/end e pickle_path com histórico de convergência).
CSV_FIELDS = [
    "task_id",
    "algorithm_id",
    "instance",
    "run_idx",
    "seed",
    # Parâmetros do algoritmo (extraídos da ALGO_CONFIGS)
    "pc",
    "pm",
    "n_neighbors",
    "prob_neighbor_mating",
    "decomposition",
    "ref_dirs_method",
    # Orçamento e resultado
    "n_evals_budget",
    "n_evals_actual",
    "n_feasible",
    "n_pareto",
    "n_f1_layers",       # camadas de dominância Pareto (profundidade da frente)
    "hv_local",
    "best_f1",
    "best_f2",
    "best_f3",
    "elapsed_s",
    # Metadados de execução
    "timestamp_start",
    "timestamp_end",
    "status",
    "pickle_path",       # caminho relativo ao out_dir do arquivo .pkl
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _seed(alg_id: str, inst: str, run_idx: int) -> int:
    """
    Seed determinística baseada em (algoritmo, instância, índice do run).

    Diferenças em relação ao tuning_rs.py:
    - Prefixo "main_experiment_" garante espaço de seeds totalmente disjunto
      de "tuning_rs_" (v1) e "tuning_rs_v2_" (v2).
    - Assinatura usa run_idx (int 0..29) em vez de config_idx — no experimento
      principal não há varredura de configurações, apenas repetições.
    - Independente do machine_id: a mesma task (alg, inst, run) produz o mesmo
      resultado em qualquer máquina, tornando reruns reprodutíveis.
    """
    key = f"main_experiment_{alg_id}_{inst}_{run_idx}"
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2 ** 32)


def _get_ref_dirs(method: str, n_points: int = POP_SIZE):
    """
    Retorna direções de referência para MOEA/D.
    Suporta "das-dennis" (H=13 → 105 pontos exatos) e "energy" (n_points direto).
    Tenta a API nova (pymoo >= 0.6) e cai para a API legada se necessário.
    """
    try:
        from pymoo.util.ref_dirs import get_reference_directions
    except ImportError:
        from pymoo.util.reference_direction import get_reference_directions

    if method == "das-dennis":
        # H=13 → C(13+3-1, 3-1) = C(15,2) = 105 pontos — exatamente POP_SIZE
        return get_reference_directions("das-dennis", 3, n_partitions=13)
    elif method == "energy":
        # Energia: especifica n_points diretamente (não garante exato, mas próximo)
        return get_reference_directions("energy", 3, n_points=n_points)
    else:
        raise ValueError(f"ref_dirs_method inválido: {method!r}")


def _non_dominated(F: np.ndarray) -> np.ndarray:
    """
    Filtra soluções não-dominadas (frente de Pareto) usando algoritmo O(n²).
    Adequado para n ≤ 500 (tamanhos típicos de população no experimento).
    Uma solução i é dominada se existe j tal que F[j] ≤ F[i] em todos os
    objetivos e F[j] < F[i] em pelo menos um.
    """
    n = len(F)
    if n == 0:
        return F
    dominated = np.zeros(n, dtype=bool)
    for i in range(n):
        if dominated[i]:
            continue
        for j in range(n):
            if i == j or dominated[j]:
                continue
            if np.all(F[j] <= F[i]) and np.any(F[j] < F[i]):
                dominated[i] = True
                break
    return F[~dominated]


def _hv(F: np.ndarray, ref_point: np.ndarray) -> float:
    """
    Calcula o hypervolume (HV) da frente F em relação a ref_point.
    Filtra automaticamente soluções que não dominam o ponto de referência
    (requisito do algoritmo WFG implementado pelo pymoo).
    Retorna 0.0 se F estiver vazio ou nenhuma solução dominar ref_point.
    """
    if len(F) == 0:
        return 0.0
    from pymoo.indicators.hv import HV
    mask = np.all(F < ref_point, axis=1)
    F_d  = F[mask]
    return float(HV(ref_point=ref_point)(F_d)) if len(F_d) > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Modo 1 — Geração de tarefas
# ─────────────────────────────────────────────────────────────────────────────

def _instance_category(inst_name: str) -> str:
    """
    Retorna a categoria Solomon da instância (C1, C2, R1, R2, RC1, RC2).
    Baseado no prefixo do nome: c1xx → C1, c2xx → C2, r1xx → R1, etc.
    """
    name = inst_name.lower()
    if name.startswith("rc2"):
        return "RC2"
    elif name.startswith("rc1") or name.startswith("rc"):
        return "RC1"
    elif name.startswith("c2"):
        return "C2"
    elif name.startswith("c1") or name.startswith("c"):
        return "C1"
    elif name.startswith("r2"):
        return "R2"
    elif name.startswith("r1") or name.startswith("r"):
        return "R1"
    return "?"


def generate(out_dir: str):
    """
    Gera all_tasks.json com 4.500 tarefas (50 inst × 3 algs × 30 runs).

    Estratégia de distribuição entre máquinas:
      - Distribuição por INSTÂNCIA INTEIRA (não por tarefa individual).
        Isso garante que todos os 30 runs × 3 algoritmos de uma instância
        fiquem na mesma máquina — simplifica eventual análise local e evita
        fragmentação de pickles.
      - Instâncias são embaralhadas deterministicamente (SEED_GLOBAL) antes
        da atribuição → mix equilibrado de categorias por máquina.
      - Atribuição por boundaries cumulativas dos pesos (mesmo algoritmo do
        tuning_rs_v2), mas aplicado sobre instâncias e não sobre tarefas
        individuais.

    Estrutura de cada tarefa (dict):
      task_id, algorithm_id, instance, run_idx, seed,
      pc, pm, n_neighbors, prob_neighbor_mating,
      decomposition, ref_dirs_method, pbi_theta,
      pop_size, eliminate_duplicates,
      n_evals_budget, machine_id
      (out_dir é injetado em run_machine, não persiste no JSON)
    """
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(SEED_GLOBAL)

    # ── 1. Embaralha as instâncias deterministicamente ────────────────────────
    inst_names = list(EXPERIMENT_INSTANCES.keys())   # ordem estável de _ALL_21
    shuffled_idx = rng.permutation(len(inst_names)).tolist()
    inst_shuffled = [inst_names[i] for i in shuffled_idx]

    # ── 2. Calcula boundaries de atribuição de instâncias por máquina ─────────
    # Mesma lógica do tuning_rs_v2: boundaries cumulativas de peso.
    # Cada instância recebe um machine_id baseado em sua posição relativa
    # na lista embaralhada (frac = (pos + 0.5) / n_total).
    boundaries = []
    cumsum = 0.0
    for m_id in sorted(MACHINE_WEIGHTS):
        cumsum += MACHINE_WEIGHTS[m_id]
        boundaries.append((m_id, cumsum))

    n_inst = len(inst_shuffled)
    instance_to_machine: dict[str, int] = {}
    for pos, inst in enumerate(inst_shuffled):
        frac = (pos + 0.5) / n_inst   # +0.5 centra no bin, evita borda superior
        for m_id, bound in boundaries:
            if frac < bound:
                instance_to_machine[inst] = m_id
                break
        else:
            instance_to_machine[inst] = boundaries[-1][0]

    # ── 3. Gera as tarefas (inst × alg × run_idx) ────────────────────────────
    # Ordem de geração: instância → algoritmo → run_idx.
    # O embaralhamento dentro de cada máquina (passo 4) intercala algoritmos.
    ALGORITHMS = ["nsga2", "smsemoa", "moead_ws"]
    tasks_by_machine: dict[int, list] = {m: [] for m in range(1, N_MACHINES + 1)}

    for inst in inst_names:   # itera em ordem estável para task_id determinístico
        m_id = instance_to_machine[inst]
        for alg_id in ALGORITHMS:
            cfg = ALGO_CONFIGS[alg_id]
            for run_idx in range(1, N_RUNS + 1):   # run_idx: 1..30 (1-indexed)
                task = {
                    "task_id":              -1,       # preenchido após shuffle global
                    "algorithm_id":         alg_id,
                    "instance":             inst,
                    "run_idx":              run_idx,
                    "seed":                 _seed(alg_id, inst, run_idx),
                    # Parâmetros do algoritmo (da configuração vencedora do tuning)
                    "pc":                   cfg["pc"],
                    "pm":                   cfg["pm"],
                    "n_neighbors":          cfg["n_neighbors"],
                    "prob_neighbor_mating": cfg["prob_neighbor_mating"],
                    "decomposition":        cfg["decomposition"],
                    "ref_dirs_method":      cfg["ref_dirs_method"],
                    "pbi_theta":            cfg["pbi_theta"],
                    "pop_size":             cfg["pop_size"],
                    "eliminate_duplicates": cfg["eliminate_duplicates"],
                    "n_evals_budget":       N_EVALS,
                    "machine_id":           m_id,
                }
                tasks_by_machine[m_id].append(task)

    # ── 4. Embaralha tarefas DENTRO de cada máquina ───────────────────────────
    # Garante que algoritmos e instâncias se intercalem durante a execução,
    # evitando que todos os runs de uma instância/algoritmo rodarem em sequência
    # (o que poderia causar viés de cache de CPU/disco).
    # Usa seeds derivadas de SEED_GLOBAL + machine_id para reprodutibilidade.
    for m_id in range(1, N_MACHINES + 1):
        rng_m = np.random.default_rng(SEED_GLOBAL + m_id)
        bucket = tasks_by_machine[m_id]
        perm   = rng_m.permutation(len(bucket)).tolist()
        tasks_by_machine[m_id] = [bucket[i] for i in perm]

    # ── 5. Atribui task_id sequencial global (0 a 4499) ──────────────────────
    # Ordem de numeração: máquina 1, máquina 2, ..., máquina 5.
    # Dentro de cada máquina: ordem do embaralhamento do passo 4.
    all_tasks = []
    task_id = 0
    for m_id in range(1, N_MACHINES + 1):
        for task in tasks_by_machine[m_id]:
            task["task_id"] = task_id
            task_id += 1
            all_tasks.append(task)

    assert len(all_tasks) == 50 * 3 * N_RUNS, \
        f"Esperado {50 * 3 * N_RUNS} tasks, gerado {len(all_tasks)}"

    # ── 6. Salva all_tasks.json ───────────────────────────────────────────────
    tasks_path = os.path.join(out_dir, "all_tasks.json")
    with open(tasks_path, "w", encoding="utf-8") as f:
        json.dump(all_tasks, f, indent=2)

    # ── 7. Imprime resumo ─────────────────────────────────────────────────────
    print(f"\n{'='*68}")
    print(f"  EXPERIMENTO PRINCIPAL — GERAÇÃO DE TAREFAS")
    print(f"{'='*68}")
    print(f"  all_tasks.json → {tasks_path}")
    print(f"  Total tasks    : {len(all_tasks)}")
    print(f"  (50 instâncias × 3 algoritmos × {N_RUNS} runs)")
    print()

    # Categorias presentes em cada máquina (para verificação visual de balanceamento)
    CATEGORIES = ["C1", "C2", "R1", "R2", "RC1", "RC2"]

    for m_id in range(1, N_MACHINES + 1):
        name, workers = MACHINE_INFO[m_id]
        eta_per_run   = MACHINE_ETA_PER_RUN_S[m_id]
        my_insts      = sorted({t["instance"]
                                 for t in tasks_by_machine[m_id]})
        n_runs_m      = len(tasks_by_machine[m_id])    # = len(insts) × 3 × 30

        # Contagem de instâncias por categoria
        cat_count: dict[str, list] = {c: [] for c in CATEGORIES}
        for inst in my_insts:
            cat = _instance_category(inst)
            if cat in cat_count:
                cat_count[cat].append(inst)

        # ETA wall-time: tarefas / workers × eta_per_run
        est_wall_h = (n_runs_m / workers) * eta_per_run / 3600

        # Linha de resumo
        cat_str = "  ".join(
            f"{c}:{len(cat_count[c])}" for c in CATEGORIES if cat_count[c]
        )
        print(f"  machine{m_id} — {name}")
        print(f"    instâncias : {len(my_insts):>2}  [{cat_str}]")
        print(f"    runs totais: {n_runs_m:>4}  workers={workers}  ETA≈{est_wall_h:.1f}h")
        print(f"    instâncias : {', '.join(my_insts)}")
        print()

    print(f"  ✅ Próximos passos:")
    print(f"     scp {tasks_path} user@maq65:~/MOEA_EVRP_TCC/results/experimento_principal/")
    print(f"     scp {tasks_path} user@maq66:~/MOEA_EVRP_TCC/results/experimento_principal/")
    print(f"     scp {tasks_path} user@maq67:~/MOEA_EVRP_TCC/results/experimento_principal/")
    print(f"     scp {tasks_path} user@dellg15:~/MOEA_EVRP_TCC/results/experimento_principal/")
    print(f"     (ajuste usuários e paths conforme a máquina de destino)")


# ─────────────────────────────────────────────────────────────────────────────
# Modo 3 — Worker: construção do algoritmo e execução de um run
# ─────────────────────────────────────────────────────────────────────────────

def _build_algorithm(task: dict):
    """
    Constrói o objeto de algoritmo pymoo a partir dos parâmetros fixos da task.

    Usa os operadores canônicos do TCC:
      - OrderCrossover(prob=pc)       — crossover de ordem (OX)
      - FixedInversionMutation(pm)    — mutação por inversão sem double-sampling
      - TWBiasedSampling()            — inicialização enviesada por janelas de tempo

    Para MOEA/D usa ref_dirs "energy" com n_points=POP_SIZE e decomposição
    Tchebicheff (resultado do tuning_rs_v2).
    """
    from pymoo.operators.crossover.ox import OrderCrossover
    from src import TWBiasedSampling, FixedInversionMutation

    crossover = OrderCrossover(prob=task["pc"])
    mutation  = FixedInversionMutation(prob=task["pm"])
    ops = dict(
        sampling  = TWBiasedSampling(),
        crossover = crossover,
        mutation  = mutation,
    )

    alg_id = task["algorithm_id"]
    pop    = task["pop_size"]

    if alg_id == "nsga2":
        from pymoo.algorithms.moo.nsga2 import NSGA2
        return NSGA2(
            pop_size             = pop,
            eliminate_duplicates = True,
            **ops,
        )

    elif alg_id == "smsemoa":
        from pymoo.algorithms.moo.sms import SMSEMOA
        return SMSEMOA(
            pop_size             = pop,
            eliminate_duplicates = True,
            **ops,
        )

    elif alg_id == "moead_ws":
        from pymoo.algorithms.moo.moead import MOEAD
        from pymoo.decomposition.tchebicheff import Tchebicheff

        ref_dirs = _get_ref_dirs(task["ref_dirs_method"], n_points=pop)

        return MOEAD(
            ref_dirs             = ref_dirs,
            n_neighbors          = task["n_neighbors"],
            prob_neighbor_mating = task["prob_neighbor_mating"],
            decomposition        = Tchebicheff(),
            **ops,
        )

    raise ValueError(f"Algoritmo desconhecido: {alg_id!r}")


def run_task(task: dict) -> dict:
    """
    Worker executado em sub-processo pelo Pool.

    Fluxo:
      1. Garante threading constraints no processo filho.
      2. Carrega instância via parse_instance + EVRPTWProblem.
      3. Constrói algoritmo via _build_algorithm.
      4. Executa minimize com ConvergenceCallback(interval=CONVERGENCE_INTERVAL).
      5. Extrai resultados de res.pop (cv, F_real, X) com fallbacks robustos.
      6. Monta pickle completo via build_run_result (experiment_io).
      7. Salva pickle em pickles/{alg}/{inst}/run{NN:02d}.pkl via save_run.
      8. Calcula métricas rápidas (hv_local, n_f1_layers, best_f1/f2/f3).
      9. Retorna summary dict para o processo principal registrar no index.csv.

    Em caso de exceção: captura o erro, imprime traceback e retorna summary
    com status="error" — o Pool nunca trava por falha de um único worker.
    """
    # ── 1. Threading constraints no filho ────────────────────────────────────
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[var] = "1"

    # Garante que o sys.path do filho aponta para o ROOT correto
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, "scripts"))

    # ── Summary padrão para o caso de erro ───────────────────────────────────
    summary = {
        "task_id":      task["task_id"],
        "algorithm_id": task["algorithm_id"],
        "instance":     task["instance"],
        "run_idx":      task["run_idx"],
        "seed":         task["seed"],    # fix: seed presente mesmo em caso de erro
        "status":       "error",
        "error_msg":    "",
        "n_feasible":   0,
        "n_pareto":     0,
        "n_f1_layers":  0,
        "hv_local":     0.0,
        "best_f1":      "",
        "best_f2":      "",
        "best_f3":      "",
        "elapsed_s":    0.0,
        "pickle_path":  "",
        "n_evals_actual": 0,
    }

    try:
        from pymoo.optimize import minimize
        from src import parse_instance, EVRPTWProblem
        from experiment_io import (
            ConvergenceCallback, build_instance_info,
            build_run_result, save_run, get_git_commit,
        )
        from datetime import datetime

        # ── 2. Carrega instância ──────────────────────────────────────────────
        inst_path = EXPERIMENT_INSTANCES[task["instance"]]
        ctx       = parse_instance(inst_path)
        problem   = EVRPTWProblem(ctx, k_max=0)   # sem local search (custo fixo)

        # ── 3. Constrói algoritmo ─────────────────────────────────────────────
        alg = _build_algorithm(task)

        # ── 4. Callback e execução ────────────────────────────────────────────
        cb             = ConvergenceCallback(interval=CONVERGENCE_INTERVAL)
        timestamp_start = datetime.now().isoformat(timespec="seconds")
        t0             = time.perf_counter()

        res = minimize(
            problem,
            alg,
            ("n_eval", task["n_evals_budget"]),
            callback = cb,
            verbose  = False,
            seed     = task["seed"],
        )

        elapsed = time.perf_counter() - t0

        # ── 5. Extrai arrays da população (fallbacks robustos) ─────────────────
        # Usa res.pop em vez de res.opt para compatibilidade com MOEA/D
        # (res.opt pode não propagar _cv/_F_real da mesma forma que NSGA-II).
        cv_arr = res.pop.get("_cv")
        F_real = res.pop.get("_F_real")
        X_all  = res.pop.get("X")

        if cv_arr is None:
            cv_arr = res.pop.get("CV")
        if F_real is None:
            F_real = res.pop.get("F")

        n_evals_actual = (res.algorithm.evaluator.n_eval
                          if hasattr(res, "algorithm") else task["n_evals_budget"])

        # ── 6. Monta o pickle completo via experiment_io ───────────────────────
        git_commit = get_git_commit(repo_path=ROOT)

        metadata = {
            "task_id":        task["task_id"],
            "algorithm_id":   task["algorithm_id"],
            "instance":       task["instance"],
            "run_idx":        task["run_idx"],
            "seed":           task["seed"],
            "n_evals_budget": task["n_evals_budget"],
            "n_evals_actual": n_evals_actual,
            "timestamp_start": timestamp_start,
            "git_commit":     git_commit,
            # timestamp_end e elapsed_seconds são preenchidos por build_run_result
        }

        config = {
            "pc":                   task["pc"],
            "pm":                   task["pm"],
            "n_neighbors":          task.get("n_neighbors"),
            "prob_neighbor_mating": task.get("prob_neighbor_mating"),
            "decomposition":        task.get("decomposition"),
            "ref_dirs_method":      task.get("ref_dirs_method"),
            "pbi_theta":            task.get("pbi_theta"),
            "pop_size":             task["pop_size"],
        }

        # build_run_result usa res.pop internamente via pymoo_result;
        # passamos o resultado do minimize diretamente.
        result = build_run_result(
            metadata      = metadata,
            config        = config,
            instance_info = build_instance_info(ctx),
            pymoo_result  = res,
            callback      = cb,
            elapsed       = elapsed,
        )

        # ── 7. Salva pickle ────────────────────────────────────────────────────
        # out_dir é injetado em run_machine antes de passar a task ao Pool.
        pkl_rel, csv_row = save_run(result, task["out_dir"])

        # ── 8. Métricas rápidas para o summary ────────────────────────────────
        F_nd      = result["pareto_front"]["F"]
        n_feas    = int((cv_arr[:, 0] <= 1e-9).sum()) if cv_arr is not None and len(cv_arr) else 0
        n_nd      = len(F_nd)
        n_f1_lay  = int(len(np.unique(F_nd[:, 0]))) if n_nd > 0 else 0

        # HV local com ref_point próprio (para ranking rápido durante execução)
        ref_local = F_nd.max(axis=0) * 1.1 if n_nd > 0 else np.ones(3)
        hv_local  = _hv(F_nd, ref_local)

        bf1 = float(F_nd[:, 0].min()) if n_nd > 0 else float("nan")
        bf2 = float(F_nd[:, 1].min()) if n_nd > 0 else float("nan")
        bf3 = float(F_nd[:, 2].min()) if n_nd > 0 else float("nan")

        # ── 9. Retorna summary dict ────────────────────────────────────────────
        summary.update({
            "status":         "ok",
            "n_feasible":     n_feas,
            "n_pareto":       n_nd,
            "n_f1_layers":    n_f1_lay,
            "hv_local":       round(hv_local, 2),
            "best_f1":        f"{bf1:.2f}" if not np.isnan(bf1) else "",
            "best_f2":        f"{bf2:.2f}" if not np.isnan(bf2) else "",
            "best_f3":        f"{bf3:.2f}" if not np.isnan(bf3) else "",
            "elapsed_s":      round(elapsed, 1),
            "pickle_path":    pkl_rel,
            "n_evals_actual": n_evals_actual,
            "csv_row":        csv_row,   # linha completa do experiment_io para o CSV
        })

    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        summary["error_msg"] = err
        print(
            f"\n  [ERRO] task_id={task['task_id']} "
            f"{task['algorithm_id']}/{task['instance']}/run{task['run_idx']:02d}: {err}",
            flush=True,
        )
        traceback.print_exc()

    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Modo 4 — Execução na máquina N (run_machine + write_csv_row)
# ─────────────────────────────────────────────────────────────────────────────

def write_csv_row(index_csv: str, summ: dict):
    """
    Appenda uma linha ao index.csv da máquina.

    Prioriza o csv_row completo gerado por experiment_io.save_run (quando
    status=ok), que já contém todos os campos de CSV_FIELDS do experimento
    principal. Para runs com erro, monta a linha manualmente com os campos
    disponíveis no summary dict.

    A função é chamada sequencialmente pelo processo principal após cada
    imap_unordered — não há risco de race condition.
    """
    from experiment_io import mark_run_error

    # Caso erro: delega ao experiment_io para garantir rastreabilidade
    if summ["status"] != "ok":
        mark_run_error(
            index_csv_path = index_csv,
            algorithm_id   = summ["algorithm_id"],
            instance       = summ["instance"],
            run_idx        = summ["run_idx"],
            seed           = summ.get("seed", ""),
            error_msg      = summ.get("error_msg", "unknown error"),
        )
        return

    # Caso ok: o csv_row já foi montado por save_run com todos os campos corretos
    csv_row = summ["csv_row"]
    new_file = not os.path.exists(index_csv)
    with open(index_csv, "a", newline="", encoding="utf-8") as f:
        # Importa CSV_FIELDS do experiment_io para garantir consistência
        from experiment_io import CSV_FIELDS as _EIO_CSV_FIELDS
        w = csv.DictWriter(f, fieldnames=_EIO_CSV_FIELDS)
        if new_file:
            w.writeheader()
        w.writerow({k: csv_row.get(k, "") for k in _EIO_CSV_FIELDS})


def run_machine(machine_id: int, experiment_dir: str,
                n_workers: int, dry_run: bool = False):
    """
    Carrega all_tasks.json, filtra tasks desta máquina, executa com Pool.

    Suporta retomada completa: ao iniciar, lê o index.csv existente e pula
    tasks cujo (algorithm_id, instance, run_idx) já esteja com status=ok.
    Isso permite interromper e retomar sem reprocessar runs concluídos.

    Estrutura de diretórios criada:
      experiment_dir/
        all_tasks.json          ← gerado por --generate (copiado via scp)
        machine{N}/
          index.csv             ← uma linha por run executado nesta máquina
          pickles/
            {alg}/{inst}/
              run{NN:02d}.pkl   ← resultado completo do run

    Em dry-run: executa 1 task com 5.000 avaliações, 1 worker e salva em
    dry_run/ (diretório separado para não contaminar resultados reais).
    """
    # ── Carrega e filtra tasks ────────────────────────────────────────────────
    tasks_path = os.path.join(experiment_dir, "all_tasks.json")
    if not os.path.exists(tasks_path):
        print(f"[ERRO] all_tasks.json não encontrado em {experiment_dir}")
        print(f"  Execute primeiro: python scripts/experimento_principal.py --generate")
        sys.exit(1)

    with open(tasks_path, encoding="utf-8") as f:
        all_tasks = json.load(f)

    my_tasks = [t for t in all_tasks if t["machine_id"] == machine_id]
    if not my_tasks:
        print(f"[ERRO] Nenhuma task encontrada para machine_id={machine_id}")
        print(f"  Verifique se o all_tasks.json foi gerado com --generate correto.")
        sys.exit(1)

    # ── Configura diretórios ──────────────────────────────────────────────────
    out_dir   = os.path.join(experiment_dir, f"machine{machine_id}")
    os.makedirs(out_dir, exist_ok=True)
    index_csv = os.path.join(out_dir, "index.csv")

    # ── Retomada: lê runs já completos do index.csv ───────────────────────────
    # Chave de completude: (algorithm_id, instance, run_idx) com status=ok.
    # Não usa task_id para retomada — permite reordenar sem perder progresso.
    completed: set[tuple] = set()
    if os.path.exists(index_csv):
        try:
            with open(index_csv, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if row.get("status") == "ok":
                        completed.add((
                            row["algorithm_id"],
                            row["instance"],
                            int(row["run_idx"]),
                        ))
            if completed:
                print(f"  Retomada: {len(completed)} runs já completos (serão pulados)")
        except Exception as e:
            print(f"  [AVISO] Não foi possível ler index.csv para retomada: {e}")

    # ── Dry-run: configura execução mínima ────────────────────────────────────
    if dry_run:
        dry_dir    = os.path.join(experiment_dir, "dry_run")
        os.makedirs(dry_dir, exist_ok=True)
        pending     = [my_tasks[0]] if my_tasks else []
        n_evals_eff = 5_000
        n_workers   = 1
        # Injeta out_dir de dry_run para não contaminar resultados reais
        for t in pending:
            t["out_dir"]        = dry_dir
            t["n_evals_budget"] = n_evals_eff
        print(f"  [DRY-RUN] 1 task, {n_evals_eff:,} evals, 1 worker → {dry_dir}")
    else:
        # Filtra apenas os pendentes (não concluídos)
        pending = [
            t for t in my_tasks
            if (t["algorithm_id"], t["instance"], t["run_idx"]) not in completed
        ]
        n_evals_eff = N_EVALS
        # Injeta out_dir e orçamento em cada task pendente
        for t in pending:
            t["out_dir"]        = out_dir
            t["n_evals_budget"] = n_evals_eff

    # ── Cabeçalho do run ──────────────────────────────────────────────────────
    name_m, workers_m = MACHINE_INFO[machine_id]
    # ETA usa throughput real por máquina (medido nos logs do tuning v2)
    eta_per_run_s = MACHINE_ETA_PER_RUN_S[machine_id]
    # Para 850k evals: ETA escalado linearmente do valor medido para 600k evals
    eta_scaled    = eta_per_run_s * (n_evals_eff / N_EVALS)
    est_wall_h    = (len(pending) / n_workers) * eta_scaled / 3600

    total_machine = len(my_tasks)
    total_pending = len(pending)

    print(f"\n{'='*68}")
    print(f"  EXPERIMENTO PRINCIPAL — machine {machine_id}")
    print(f"{'='*68}")
    print(f"  Máquina                  : {name_m}")
    print(f"  Total tasks desta máquina: {total_machine}")
    print(f"  Já completos             : {len(completed)}")
    print(f"  Pendentes                : {total_pending}")
    print(f"  n_evals por run          : {n_evals_eff:,}")
    print(f"  Workers                  : {n_workers}")
    print(f"  ETA estimado             : ~{est_wall_h:.1f}h")
    print(f"  out_dir                  : {out_dir}")
    print(f"  index.csv                : {index_csv}")
    print(f"{'='*68}\n")

    if not pending:
        print("  ✅ Todos os runs concluídos — nada a executar.")
        return

    # ── Cabeçalho da tabela de progresso ─────────────────────────────────────
    print(f"  {'#':>6}  {'Alg':<10}  {'Inst':<12}  {'Run':>3}  "
          f"{'Feas':>5}  {'ND':>4}  {'Lyr':>4}  {'HV_loc':>12}  {'Tempo':>7}  Status")
    print(f"  {'-'*6}  {'-'*10}  {'-'*12}  {'-'*3}  "
          f"{'-'*5}  {'-'*4}  {'-'*4}  {'-'*12}  {'-'*7}  {'-'*22}")

    global_start = time.perf_counter()
    done   = len(completed)
    errors = 0

    # ── Helper de progresso (compartilhado entre Pool e ProcessPoolExecutor) ──
    def _handle_result(summ):
        nonlocal done, errors
        done += 1
        if summ["status"] != "ok":
            errors += 1

        # Registra resultado no CSV
        write_csv_row(index_csv, summ)

        # ETA dinâmico baseado no tempo real decorrido
        elapsed_total = time.perf_counter() - global_start
        frac  = done / total_machine if total_machine > 0 else 1.0
        eta_s = (elapsed_total / frac - elapsed_total) if frac > 0 else 0.0
        eta   = f"{int(eta_s // 3600)}h{int((eta_s % 3600) // 60):02d}m"

        # Linha de progresso
        if summ["status"] == "ok":
            status_str = f"ok  ETA:{eta}"
        else:
            err_short  = summ.get("error_msg", "")[:22]
            status_str = f"ERRO: {err_short}"

        print(
            f"  {done:>6}/{total_machine}  "
            f"{summ['algorithm_id']:<10}  "
            f"{summ['instance']:<12}  "
            f"{summ['run_idx']:>3}  "
            f"{summ['n_feasible']:>5}  "
            f"{summ['n_pareto']:>4}  "
            f"{summ['n_f1_layers']:>4}  "
            f"{summ['hv_local']:>12.0f}  "
            f"{summ['elapsed_s']:>6.0f}s  "
            f"{status_str}",
            flush=True,
        )

    # ── Execução paralela ─────────────────────────────────────────────────────
    # Usa ProcessPoolExecutor em vez de multiprocessing.Pool para evitar
    # BrokenPipeError em Python 3.14 (maq66). ProcessPoolExecutor funciona
    # em Python >= 3.2 e usa implementação de IPC diferente.
    # max_tasks_per_child=1: recicla worker após cada run (evita memory leak).
    from concurrent.futures import ProcessPoolExecutor, as_completed
    ctx = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=n_workers, mp_context=ctx,
                             max_tasks_per_child=1) as exe:
        futures = {exe.submit(run_task, t): t for t in pending}
        for fut in as_completed(futures):
            summ = fut.result()
            _handle_result(summ)

    # ── Resumo final ──────────────────────────────────────────────────────────
    elapsed_total = time.perf_counter() - global_start
    h, rem = divmod(int(elapsed_total), 3600)
    m, s   = divmod(rem, 60)
    print(f"\n  Concluído em {h}h {m:02d}m {s:02d}s  |  "
          f"Erros: {errors}/{total_pending}  |  "
          f"Total ok: {done - errors - len(completed)}/{total_pending}")
    print(f"  index.csv → {index_csv}")


# ─────────────────────────────────────────────────────────────────────────────
# Modo 5 — Análise (stub — a implementar após coleta dos dados)
# ─────────────────────────────────────────────────────────────────────────────

def analyze(experiment_dir: str):
    """
    Análise pós-experimento — implementação pendente.

    Pipeline completo previsto (conforme experimento_principal_parte_5.md):
      1. Merge dos index.csv de todas as máquinas → merged_index.csv
      2. Ref_points globais por instância (90 runs × frentes) → ref_points.json
      3. Recálculo HV com ref_points globais + IGD+ → metrics.csv
      4. Testes estatísticos (Friedman + Nemenyi + Wilcoxon) → statistical_tests.csv
      5. Análise por subgrupo (C/R/RC × 1xx/2xx) + Spearman(tw_ratio, ΔHV)
      6. Curvas de convergência medianas ± IQR → figures/convergence_*.png
      7. Propriedades estruturais (n_f1_layers, spacing, spread) → figures/boxplot_*.png
      8. Relatório completo → experiment_report.md

    Esta função será implementada após a coleta completa dos dados de todas
    as máquinas. Por ora, realiza apenas o Passo 1 (merge + validação) para
    permitir inspeção parcial dos resultados.
    """
    from experiment_io import CSV_FIELDS as _EIO_CSV_FIELDS

    print(f"\n{'='*68}")
    print(f"  EXPERIMENTO PRINCIPAL — ANÁLISE")
    print(f"{'='*68}\n")

    # ── Passo 1 (parcial): merge dos index.csv disponíveis ────────────────────
    all_rows = []
    for m in range(1, N_MACHINES + 1):
        csv_path = os.path.join(experiment_dir, f"machine{m}", "index.csv")
        if not os.path.exists(csv_path):
            print(f"  [AVISO] machine{m}/index.csv não encontrado — pulando")
            continue
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            r["_machine_id"] = m
        all_rows.extend(rows)
        print(f"  machine{m}: {len(rows)} linhas carregadas de {csv_path}")

    ok_rows = [r for r in all_rows if r.get("status") == "ok"]
    print(f"\n  Total linhas : {len(all_rows)}")
    print(f"  Status=ok    : {len(ok_rows)}")

    expected = 50 * 3 * N_RUNS   # 4.500
    missing  = expected - len(ok_rows)
    if missing > 0:
        print(f"  [AVISO] {missing} runs faltando de {expected} esperados")
    else:
        print(f"  ✅ Todos os {expected} runs coletados!")

    # Salva merged_index.csv para inspeção
    if ok_rows:
        merged_path = os.path.join(experiment_dir, "merged_index.csv")
        fields_merged = _EIO_CSV_FIELDS + ["_machine_id"]
        with open(merged_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields_merged)
            w.writeheader()
            for r in ok_rows:
                w.writerow({k: r.get(k, "") for k in fields_merged})
        print(f"\n  merged_index.csv → {merged_path}")

    print(f"\n  ⚠️  Análise completa (passos 2-8) não implementada ainda.")
    print(f"     Implemente após a coleta completa dos dados de todas as máquinas.")
    print(f"     Consulte experimento_principal_parte_5.md para o pipeline completo.")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point — argparse
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description=(
            "Experimento Principal do TCC — NSGA-II, SMS-EMOA e MOEA/D-WS\n"
            "sobre 50 instâncias de Solomon (21 clientes, excluindo as 6 do tuning).\n"
            "Usa as configurações vencedoras do tuning_rs_v2 com 30 runs por (alg, inst)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── Modos mutuamente exclusivos ───────────────────────────────────────────
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--generate", action="store_true",
        help="Gera all_tasks.json com 4500 tarefas distribuídas entre as máquinas.",
    )
    mode.add_argument(
        "--run", action="store_true",
        help="Executa as tarefas desta máquina (requer --machine-id).",
    )
    mode.add_argument(
        "--analyze", action="store_true",
        help="Analisa resultados das 5 máquinas (merge + validação; análise completa pendente).",
    )

    # ── Argumentos complementares ─────────────────────────────────────────────
    ap.add_argument(
        "--machine-id", type=int, choices=list(range(1, N_MACHINES + 1)),
        metavar=f"{{1..{N_MACHINES}}}",
        help=(
            f"ID da máquina (obrigatório com --run). "
            f"1=maq64, 2=maq65, 3=maq66, 4=maq67, 5=Dell G15."
        ),
    )
    ap.add_argument(
        "--experiment-dir",
        default=os.path.join(ROOT, "results", "main_experiment"),
        help=(
            "Diretório raiz do experimento "
            "(default: results/main_experiment)."
        ),
    )
    ap.add_argument(
        "--n-workers", type=int, default=N_WORKERS,
        help=f"Workers paralelos para --run (default: {N_WORKERS}).",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help=(
            "Executa 1 task com 5.000 avaliações e 1 worker. "
            "Salva em dry_run/ para não contaminar resultados reais."
        ),
    )

    args = ap.parse_args()

    # Garante que o diretório raiz existe antes de qualquer modo
    os.makedirs(args.experiment_dir, exist_ok=True)

    # ── Banner de identificação ────────────────────────────────────────────────
    mode_str = (
        "--generate" if args.generate else
        "--run"      if args.run      else
        "--analyze"
    )
    print(f"\n{'='*68}")
    print(f"  EXPERIMENTO PRINCIPAL — EVRPTW TCC")
    print(f"{'='*68}")
    print(f"  Modo         : {mode_str}")
    print(f"  Diretório    : {args.experiment_dir}")
    if args.run:
        print(f"  machine-id   : {args.machine_id}")
        print(f"  n-workers    : {args.n_workers}")
        print(f"  dry-run      : {args.dry_run}")
    print(f"{'='*68}")

    # ── Dispatch ──────────────────────────────────────────────────────────────
    if args.generate:
        generate(args.experiment_dir)

    elif args.run:
        if args.machine_id is None:
            ap.error("--machine-id é obrigatório com --run")
        run_machine(
            machine_id     = args.machine_id,
            experiment_dir = args.experiment_dir,
            n_workers      = args.n_workers,
            dry_run        = args.dry_run,
        )

    elif args.analyze:
        analyze(args.experiment_dir)


if __name__ == "__main__":
    main()

