#!/usr/bin/env python3
"""
tuning_rs.py
============
Random Search de Hiperparâmetros para NSGA-II, SMS-EMOA e MOEA/D-WS.

Três modos de operação (conforme hypertuning_random_search.md):

  Modo 1 — Geração (qualquer máquina, uma vez):
    python scripts/tuning_rs.py --generate
    → gera  tuning_rs/all_configs.json  (150 configs)
             tuning_rs/all_tasks.json   (900 tasks com machine_id)
    → copiar os 2 JSONs para as outras máquinas via scp/rsync.

  Modo 2 — Execução (cada máquina em paralelo):
    python scripts/tuning_rs.py --run --machine-id 1   # 10 workers, ~5.6h
    python scripts/tuning_rs.py --run --machine-id 2
    python scripts/tuning_rs.py --run --machine-id 3
    python scripts/tuning_rs.py --run --machine-id 4
    → salva  tuning_rs/machine{N}/index.csv
             tuning_rs/machine{N}/fronts/{alg}__{inst}__cfg{NN}.pkl

  Modo 3 — Análise (após todas as máquinas terminarem):
    python scripts/tuning_rs.py --analyze
    → lê machine1-4, gera merged_index.csv, tuning_report.md

  Dry-run (verifica pipeline antes do run completo):
    python scripts/tuning_rs.py --run --machine-id 1 --dry-run

Parâmetros de busca (50 configs independentes por algoritmo):
  NSGA-II   : pc ~ U(0,1),  pm ~ LogU(0.001, 0.30)
  SMS-EMOA  : idem ao NSGA-II, amostras independentes
  MOEA/D-WS : pc, pm + n_neighbors ~ IntU(3,25),
               prob_neighbor_mating ~ U(0,1),
               decomposition ~ Cat(ws, tcheby, pbi),
               ref_dirs_method ~ Cat(das-dennis, energy),
               pbi_theta ~ U(1,10) se decomposition=pbi

Instâncias (6, espelhando o critério de parada):
  c101_21, c201_21, r101_21, r201_21, rc101_21, rc201_21

Seeds: hash SHA-256 de "tuning_rs_{alg}_{cfg_idx}_{inst}" — reprodutíveis,
       independentes do machine_id (mesma seed em qualquer máquina).
"""

# Threading constraints — ANTES de qualquer numpy import
import os
os.environ.setdefault("OMP_NUM_THREADS",     "1")
os.environ.setdefault("MKL_NUM_THREADS",     "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1")
os.environ.setdefault("BLIS_NUM_THREADS",    "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import sys, time, csv, json, pickle, hashlib, random, argparse, warnings, traceback
from datetime import datetime
from multiprocessing import Pool

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

N_CONFIGS     = 100       # 100 configs/alg — resolução ~3× maior que o v1
N_MACHINES    = 5         # 5 máquinas: maq64, maq65, maq66, maq67, Dell G15
N_WORKERS     = 10        # workers de fallback (sobrescrito via --n-workers)
POP_SIZE      = 105       # fixo em todos (Das-Dennis H=13, 3 objetivos)
N_EVALS       = 600_000   # 50% mais que v1 — convergência mais próxima do stopping criterion (850k)
SEED_GLOBAL   = 43        # seed diferente do v1 (42) → configs independentes e não-redundantes

# Mapeamento machine_id → (nome, n_workers_recomendado)
# Pesos proporcionais ao throughput esperado com 600k evals/run:
#   machine_id=1 → maq64  (Ryzen 9 7950X, 16c) — ~80 runs/h  peso 28.7%
#   machine_id=2 → maq65  (Ryzen 9 7900X, 12c) — ~60 runs/h  peso 21.6%
#   machine_id=3 → maq66  (i9-10900F, 10c)      — ~27 runs/h  peso  9.7%
#   machine_id=4 → maq67  (Ryzen 9 7950X, 16c) — ~80 runs/h  peso 28.7%
#   machine_id=5 → Dell G15 (i5-12500H, 8w)     — ~32 runs/h  peso 11.3%
# Distribuição proporcional à capacidade equaliza o wall-time (~6.5h em todas)
MACHINE_WEIGHTS = {
    1: 0.287,   # maq64  — Ryzen 9 7950X, 16 workers
    2: 0.216,   # maq65  — Ryzen 9 7900X, 12 workers
    3: 0.097,   # maq66  — i9-10900F, 10 workers
    4: 0.287,   # maq67  — Ryzen 9 7950X, 16 workers
    5: 0.113,   # Dell G15 — i5-12500H, 8 workers (P+E cores híbridos)
}
MACHINE_INFO = {
    1: ("maq64 (Ryzen 9 7950X, 16c)",  16),
    2: ("maq65 (Ryzen 9 7900X, 12c)",  12),
    3: ("maq66 (i9-10900F, 10c)",       10),
    4: ("maq67 (Ryzen 9 7950X, 16c)",  16),
    5: ("Dell G15 (i5-12500H, 8w)",     8),
}

# 6 instâncias representativas — mesmas do critério de parada
TUNING_INSTANCES = {
    "c101_21":  os.path.join(ROOT, "evrptw_instances", "c101_21.txt"),
    "c201_21":  os.path.join(ROOT, "evrptw_instances", "c201_21.txt"),
    "r101_21":  os.path.join(ROOT, "evrptw_instances", "r101_21.txt"),
    "r201_21":  os.path.join(ROOT, "evrptw_instances", "r201_21.txt"),
    "rc101_21": os.path.join(ROOT, "evrptw_instances", "rc101_21.txt"),
    "rc201_21": os.path.join(ROOT, "evrptw_instances", "rc201_21.txt"),
}

# Campos do CSV de índice por máquina
CSV_FIELDS = [
    "task_id", "algorithm_id", "config_idx", "instance", "seed",
    "pc", "pm",
    "n_neighbors", "prob_neighbor_mating", "decomposition",
    "ref_dirs_method", "pbi_theta",
    "n_evals_budget", "n_feasible", "n_pareto",
    "hv_local", "best_f1", "best_f2", "best_f3",
    "elapsed_s", "status", "front_path",
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _seed(alg_id: str, cfg_idx: int, inst: str) -> int:
    """
    Seed determinística baseada em (algoritmo, config, instância).
    Prefixo "tuning_rs_v2_" garante seeds completamente independentes
    do v1 ("tuning_rs_"), da calibração ("calib_") e do piloto ("pilot_").
    Independente do machine_id — a mesma tarefa dá o mesmo resultado
    em qualquer máquina, tornando reruns reprodutíveis.
    """
    key = f"tuning_rs_v2_{alg_id}_{cfg_idx}_{inst}"
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2 ** 32)


def _get_ref_dirs(method: str, n_points: int = POP_SIZE):
    try:
        from pymoo.util.ref_dirs import get_reference_directions
    except ImportError:
        from pymoo.util.reference_direction import get_reference_directions

    if method == "das-dennis":
        # H=13 → 105 pontos exatos para 3 objetivos
        return get_reference_directions("das-dennis", 3, n_partitions=13)
    elif method == "energy":
        # energy-based → especifica n_points diretamente
        return get_reference_directions("energy", 3, n_points=n_points)
    else:
        raise ValueError(f"ref_dirs_method inválido: {method!r}")


def _non_dominated(F: np.ndarray) -> np.ndarray:
    """Filtro não-dominado O(n²) — adequado para n ≤ 500."""
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
    if len(F) == 0:
        return 0.0
    from pymoo.indicators.hv import HV
    mask = np.all(F < ref_point, axis=1)
    F_d  = F[mask]
    return float(HV(ref_point=ref_point)(F_d)) if len(F_d) > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Modo 1 — Geração de configs e tasks
# ─────────────────────────────────────────────────────────────────────────────

def generate(out_dir: str):
    """
    Gera all_configs.json (300 configs) e all_tasks.json (1800 tasks).

    Distribuições de amostragem (centradas nos defaults do pymoo):
      pc  ~ Beta(3, 1.5)  — moda ~0.80, média ~0.67; explora [0.4, 1.0] (default OX = 0.9)
      pm  ~ Beta(3, 1)    — moda  1.00, média  0.75; ~88% acima de 0.5 (default Inv = 1.0)

      [MOEA/D somente]
      n_neighbors          ~ IntUniform(3, 25)
      prob_neighbor_mating ~ Beta(3, 1)        — prioriza alto (default 0.9)
      decomposition        ~ Cat{ws, tcheby, pbi}  uniforme
      ref_dirs_method      ~ Cat{das-dennis, energy}  uniforme
      pbi_theta            ~ Uniform(1.0, 10.0)  [condicional: decomp == pbi]

    Justificativa (banca): distribuições Beta(α>β) concentram amostras próximas
    ao default do operador — prior forte do conhecimento da comunidade — enquanto
    ainda exploram alternativas. Independente de qualquer resultado anterior.
    """
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(SEED_GLOBAL)

    configs = []

    # ── NSGA-II ─────────────────────────────────────────────────────────────
    for i in range(1, N_CONFIGS + 1):
        pc = float(rng.beta(3, 1.5))   # moda ~0.80, média ~0.67 (default OX = 0.9)
        pm = float(rng.beta(3, 1))     # moda  1.00, média  0.75 (default Inv = 1.0)
        configs.append({
            "algorithm_id":         "nsga2",
            "config_idx":           i,
            "pc":                   round(pc, 4),
            "pm":                   round(pm, 4),
            "pop_size":             POP_SIZE,
            "eliminate_duplicates": True,
            # campos MOEA/D — null para NSGA-II
            "n_neighbors":          None,
            "prob_neighbor_mating": None,
            "decomposition":        None,
            "ref_dirs_method":      None,
            "pbi_theta":            None,
        })

    # ── SMS-EMOA ─────────────────────────────────────────────────────────────
    for i in range(1, N_CONFIGS + 1):
        pc = float(rng.beta(3, 1.5))   # moda ~0.80, média ~0.67 (default OX = 0.9)
        pm = float(rng.beta(3, 1))     # moda  1.00, média  0.75 (default Inv = 1.0)
        configs.append({
            "algorithm_id":         "smsemoa",
            "config_idx":           i,
            "pc":                   round(pc, 4),
            "pm":                   round(pm, 4),
            "pop_size":             POP_SIZE,
            "eliminate_duplicates": True,
            "n_neighbors":          None,
            "prob_neighbor_mating": None,
            "decomposition":        None,
            "ref_dirs_method":      None,
            "pbi_theta":            None,
        })

    # ── MOEA/D-WS ────────────────────────────────────────────────────────────
    decomps     = ["weighted-sum", "tchebycheff", "pbi"]
    ref_methods = ["das-dennis", "energy"]
    for i in range(1, N_CONFIGS + 1):
        pc          = float(rng.beta(3, 1.5))    # moda ~0.80  (default OX = 0.9)
        pm          = float(rng.beta(3, 1))      # moda  1.00  (default Inv = 1.0)
        n_nb        = int(rng.integers(3, 26))   # IntUniform [3, 25]
        pnm         = float(rng.beta(3, 1))      # moda 1.0 — prioriza alto (default 0.9)
        decomp      = str(decomps[int(rng.integers(0, 3))])
        ref_method  = str(ref_methods[int(rng.integers(0, 2))])
        pbi_theta   = float(rng.uniform(1.0, 10.0)) if decomp == "pbi" else None
        configs.append({
            "algorithm_id":         "moead_ws",
            "config_idx":           i,
            "pc":                   round(pc, 4),
            "pm":                   round(pm, 4),
            "pop_size":             POP_SIZE,
            "eliminate_duplicates": False,  # MOEA/D não usa
            "n_neighbors":          n_nb,
            "prob_neighbor_mating": round(pnm, 4),
            "decomposition":        decomp,
            "ref_dirs_method":      ref_method,
            "pbi_theta":            round(pbi_theta, 3) if pbi_theta is not None else None,
        })

    # ── Salva configs ─────────────────────────────────────────────────────────
    configs_path = os.path.join(out_dir, "all_configs.json")
    with open(configs_path, "w", encoding="utf-8") as f:
        json.dump(configs, f, indent=2)

    print(f"  all_configs.json → {configs_path}")
    print(f"  Total configs: {len(configs)} "
          f"(nsga2={N_CONFIGS}, smsemoa={N_CONFIGS}, moead_ws={N_CONFIGS})")

    # ── Geração das tasks (config × instância) ────────────────────────────────
    tasks = []
    for cfg in configs:
        for inst_name in TUNING_INSTANCES:
            task = dict(cfg)   # cópia do cfg
            task["task_id"]        = -1   # preenchido após shuffle
            task["instance"]       = inst_name
            task["seed"]           = _seed(cfg["algorithm_id"],
                                           cfg["config_idx"], inst_name)
            task["n_evals_budget"] = N_EVALS
            task["machine_id"]     = -1   # preenchido após shuffle
            tasks.append(task)

    # Embaralhamento determinístico antes de atribuir machine_id.
    # Garante mix equilibrado de algoritmos e instâncias por máquina.
    rng_shuffle = np.random.default_rng(SEED_GLOBAL)
    idx_shuffled = rng_shuffle.permutation(len(tasks)).tolist()
    tasks_shuffled = [tasks[i] for i in idx_shuffled]

    # Distribuição proporcional à capacidade de cada máquina.
    # Round-robin simples (v1) distribui igualmente, mas as máquinas têm
    # velocidades diferentes. Distribuição ponderada equaliza o wall-time.
    boundaries = []
    cumsum = 0.0
    for m_id in sorted(MACHINE_WEIGHTS):
        cumsum += MACHINE_WEIGHTS[m_id]
        boundaries.append((m_id, cumsum))

    n_total = len(tasks_shuffled)
    for pos, task in enumerate(tasks_shuffled):
        task["task_id"] = pos
        frac = (pos + 0.5) / n_total   # +0.5 centra no bin, evita borda superior
        for m_id, bound in boundaries:
            if frac < bound:
                task["machine_id"] = m_id
                break
        else:
            task["machine_id"] = boundaries[-1][0]

    # ── Salva tasks ───────────────────────────────────────────────────────────
    tasks_path = os.path.join(out_dir, "all_tasks.json")
    with open(tasks_path, "w", encoding="utf-8") as f:
        json.dump(tasks_shuffled, f, indent=2)

    print(f"  all_tasks.json  → {tasks_path}")
    print(f"  Total tasks: {len(tasks_shuffled)} "
          f"({N_CONFIGS} configs × 3 algs × {len(TUNING_INSTANCES)} instâncias)")
    print()
    # Throughput estimado por máquina (evals/s medidos no tuning v1 + estimativa Dell)
    # AMD 7950X/7900X: ~700 evals/s/worker. Intel i9: ~354 evals/s/worker.
    # Dell G15 i5-12500H: ~480 evals/s/worker (P-cores) com throttling conservador.
    machine_rate = {1: 700.0, 2: 700.0, 3: 354.0, 4: 700.0, 5: 480.0}
    for m in range(1, N_MACHINES + 1):
        n_m           = sum(1 for t in tasks_shuffled if t["machine_id"] == m)
        name, workers = MACHINE_INFO[m]
        rate          = machine_rate[m]
        est_h         = n_m * (N_EVALS / rate / workers) / 3600
        print(f"    machine{m} ({name}): {n_m:>4} tasks, {workers:>2} workers, ~{est_h:.1f}h")

    print(f"\n  ✅ Próximos passos:")
    print(f"     scp {configs_path} {tasks_path} user@machine2:path/")
    print(f"     scp {configs_path} {tasks_path} user@machine3:path/")
    print(f"     scp {configs_path} {tasks_path} user@machine4:path/")
    print(f"     (ajuste os paths e usuários)")



# ─────────────────────────────────────────────────────────────────────────────
# Worker — executa um único run de tuning
# ─────────────────────────────────────────────────────────────────────────────

def _build_algorithm_from_config(task: dict):
    """
    Constrói o algoritmo pymoo com os parâmetros exatos da configuração amostrada.
    Ponto central de variação vs os experimentos anteriores (pc, pm configuráveis).
    """
    from pymoo.operators.crossover.ox import OrderCrossover
    from src import TWBiasedSampling, FixedInversionMutation

    crossover = OrderCrossover(prob=task["pc"])
    mutation  = FixedInversionMutation(prob=task["pm"])  # fix: sem double-sampling
    ops = dict(
        sampling  = TWBiasedSampling(),
        crossover = crossover,
        mutation  = mutation,
    )

    alg_id = task["algorithm_id"]
    pop    = task["pop_size"]

    if alg_id == "nsga2":
        from pymoo.algorithms.moo.nsga2 import NSGA2
        return NSGA2(pop_size=pop, eliminate_duplicates=True, **ops)

    elif alg_id == "smsemoa":
        from pymoo.algorithms.moo.sms import SMSEMOA
        return SMSEMOA(pop_size=pop, eliminate_duplicates=True, **ops)

    elif alg_id == "moead_ws":
        from pymoo.algorithms.moo.moead import MOEAD

        ref_dirs = _get_ref_dirs(task["ref_dirs_method"], n_points=pop)

        decomp_id = task["decomposition"]
        if decomp_id == "weighted-sum":
            from pymoo.decomposition.weighted_sum import WeightedSum
            decomp = WeightedSum()
        elif decomp_id == "tchebycheff":
            from pymoo.decomposition.tchebicheff import Tchebicheff
            decomp = Tchebicheff()
        elif decomp_id == "pbi":
            from pymoo.decomposition.pbi import PBI
            theta  = task.get("pbi_theta") or 5.0
            decomp = PBI(theta=theta)
        else:
            raise ValueError(f"Decomposição desconhecida: {decomp_id!r}")

        return MOEAD(
            ref_dirs             = ref_dirs,
            n_neighbors          = task["n_neighbors"],
            prob_neighbor_mating = task["prob_neighbor_mating"],
            decomposition        = decomp,
            **ops,
        )

    raise ValueError(f"Algoritmo desconhecido: {alg_id!r}")


def run_task(task: dict) -> dict:
    """
    Worker executado em sub-processo pelo Pool.
    Salva apenas a frente de Pareto compacta (sem convergence_history,
    sem permutações) — suficiente para tuning, menor footprint em disco.
    """
    # Garante restrição de threads no processo filho
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[var] = "1"

    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, "scripts"))

    summary = {
        "task_id":      task["task_id"],
        "algorithm_id": task["algorithm_id"],
        "config_idx":   task["config_idx"],
        "instance":     task["instance"],
        "status":       "error",
        "error_msg":    "",
        "n_feasible":   0,
        "n_pareto":     0,
        "hv_local":     0.0,
        "best_f1":      "",
        "best_f2":      "",
        "best_f3":      "",
        "elapsed_s":    0.0,
        "front_path":   "",
    }

    try:
        from pymoo.optimize import minimize
        from src import parse_instance, EVRPTWProblem
        from experiment_io import ConvergenceCallback

        inst_path = TUNING_INSTANCES[task["instance"]]
        ctx       = parse_instance(inst_path)
        problem   = EVRPTWProblem(ctx, k_max=0)   # sem local search
        alg       = _build_algorithm_from_config(task)
        # Para tuning, usamos um callback mínimo (apenas final) para economizar memória
        cb        = ConvergenceCallback(interval=task["n_evals_budget"] + 1)

        t0  = time.perf_counter()
        res = minimize(problem, alg, ("n_eval", task["n_evals_budget"]),
                       callback=cb, verbose=False, seed=task["seed"])
        elapsed = time.perf_counter() - t0

        # ── Extrai frente viável não-dominada ─────────────────────────────────
        # Usa res.pop (população completa) em vez de res.opt para garantir
        # compatibilidade com MOEA/D, que pode não propagar atributos
        # customizados (_cv, _F_real) para res.opt da mesma forma que NSGA-II.
        cv_arr = res.pop.get("_cv")
        F_real = res.pop.get("_F_real")
        # Fallbacks robustos — caso o algoritmo não preencha os campos customizados
        if cv_arr is None:
            cv_arr = res.pop.get("CV")
        if F_real is None:
            F_real = res.pop.get("F")

        if cv_arr is not None and F_real is not None:
            mask   = cv_arr[:, 0] <= 1e-9
            F_feas = F_real[mask] if mask.any() else np.empty((0, 3))
        else:
            # Fallback final: res.F ótimas (pode incluir inviáveis)
            F_feas = res.F if res.F is not None else np.empty((0, 3))
            mask   = None  # sinaliza que n_feas = n_nd

        F_nd = _non_dominated(F_feas) if len(F_feas) > 0 else np.empty((0, 3))

        n_feas  = int(mask.sum()) if mask is not None else len(F_nd)
        n_nd    = len(F_nd)

        # HV local com ref_point próprio desta run (para seleção rápida por config)
        # ref_point será recalculado globalmente no modo --analyze
        ref_local = F_nd.max(axis=0) * 1.1 if n_nd > 0 else np.ones(3)
        hv_local  = _hv(F_nd, ref_local)

        bf1 = float(F_nd[:, 0].min()) if n_nd > 0 else float("nan")
        bf2 = float(F_nd[:, 1].min()) if n_nd > 0 else float("nan")
        bf3 = float(F_nd[:, 2].min()) if n_nd > 0 else float("nan")

        # ── Salva pickle compacto ─────────────────────────────────────────────
        front_dir = os.path.join(task["out_dir"], "fronts")
        os.makedirs(front_dir, exist_ok=True)
        front_fname = (f"{task['algorithm_id']}__{task['instance']}__"
                       f"cfg{task['config_idx']:03d}.pkl")
        front_path  = os.path.join(front_dir, front_fname)

        compact = {
            "task_id":    task["task_id"],
            "algorithm":  task["algorithm_id"],
            "config_idx": task["config_idx"],
            "instance":   task["instance"],
            "seed":       task["seed"],
            "elapsed_s":  elapsed,
            "n_evals":    task["n_evals_budget"],
            "config":     {k: task[k] for k in
                           ("pc", "pm", "n_neighbors", "prob_neighbor_mating",
                            "decomposition", "ref_dirs_method", "pbi_theta")},
            "pareto_front": {
                "F": F_nd,
                "n_feasible": n_feas,
            },
        }
        with open(front_path, "wb") as fp:
            pickle.dump(compact, fp, protocol=4)

        summary.update({
            "status":     "ok",
            "n_feasible": n_feas,
            "n_pareto":   n_nd,
            "hv_local":   round(hv_local, 2),
            "best_f1":    f"{bf1:.2f}" if not np.isnan(bf1) else "",
            "best_f2":    f"{bf2:.2f}" if not np.isnan(bf2) else "",
            "best_f3":    f"{bf3:.2f}" if not np.isnan(bf3) else "",
            "elapsed_s":  round(elapsed, 1),
            "front_path": os.path.relpath(front_path, task["out_dir"]),
        })

    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        summary["error_msg"] = err
        print(f"\n  [ERRO] task_id={task['task_id']} "
              f"{task['algorithm_id']}/{task['instance']}/cfg{task['config_idx']}: "
              f"{err}")
        traceback.print_exc()

    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Modo 2 — Execução na máquina N
# ─────────────────────────────────────────────────────────────────────────────

def write_csv_row(index_csv: str, task: dict, summ: dict):
    """Appends one row to index.csv (thread-safe via Pool ordering)."""
    is_new = not os.path.exists(index_csv)
    with open(index_csv, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if is_new:
            w.writeheader()
        row = {
            "task_id":              task["task_id"],
            "algorithm_id":         task["algorithm_id"],
            "config_idx":           task["config_idx"],
            "instance":             task["instance"],
            "seed":                 task["seed"],
            "pc":                   task["pc"],
            "pm":                   task["pm"],
            "n_neighbors":          task.get("n_neighbors") or "",
            "prob_neighbor_mating": task.get("prob_neighbor_mating") or "",
            "decomposition":        task.get("decomposition") or "",
            "ref_dirs_method":      task.get("ref_dirs_method") or "",
            "pbi_theta":            task.get("pbi_theta") or "",
            "n_evals_budget":       task["n_evals_budget"],
            "n_feasible":           summ["n_feasible"],
            "n_pareto":             summ["n_pareto"],
            "hv_local":             summ["hv_local"],
            "best_f1":              summ["best_f1"],
            "best_f2":              summ["best_f2"],
            "best_f3":              summ["best_f3"],
            "elapsed_s":            summ["elapsed_s"],
            "status":               summ["status"],
            "front_path":           summ["front_path"],
        }
        w.writerow(row)


def run_machine(machine_id: int, tuning_dir: str, n_workers: int,
                n_evals_override: int = None, dry_run: bool = False):
    """
    Carrega all_tasks.json, filtra tasks para esta máquina, executa com Pool.
    Suporta retomada: pula tasks com status=ok já no index.csv.
    """
    tasks_path = os.path.join(tuning_dir, "all_tasks.json")
    if not os.path.exists(tasks_path):
        print(f"[ERRO] all_tasks.json não encontrado em {tuning_dir}")
        print(f"  Execute primeiro: python scripts/tuning_rs.py --generate")
        sys.exit(1)

    with open(tasks_path, encoding="utf-8") as f:
        all_tasks = json.load(f)

    my_tasks = [t for t in all_tasks if t["machine_id"] == machine_id]
    out_dir   = os.path.join(tuning_dir, f"machine{machine_id}")
    os.makedirs(out_dir, exist_ok=True)
    index_csv = os.path.join(out_dir, "index.csv")

    # ── Retomada: lê runs já completos ───────────────────────────────────────
    completed = set()
    if os.path.exists(index_csv):
        with open(index_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("status") == "ok":
                    completed.add(int(row["task_id"]))
        if completed:
            print(f"  Retomada: {len(completed)} tasks já completas (serão puladas)")

    # Em dry-run: executa apenas 1 task com orçamento reduzido
    if dry_run:
        pending = [my_tasks[0]] if my_tasks else []
        n_evals_eff = 5_000
        n_workers   = 1
        print(f"  [DRY-RUN] 1 task, {n_evals_eff} evals, 1 worker")
    else:
        pending      = [t for t in my_tasks if t["task_id"] not in completed]
        n_evals_eff  = n_evals_override or N_EVALS

    # Injeta configurações de execução em cada task
    for t in pending:
        t["out_dir"]        = out_dir
        t["n_evals_budget"] = n_evals_eff

    total_machine = len(my_tasks)
    total_pending = len(pending)

    est_s_per_run  = n_evals_eff / 354.0   # ~354 evals/s (calibrado do piloto, i9-10900F)
    # NOTA: ETA conservador para máquinas AMD (maq1,2,4) e Dell (maq5) — ~700 e ~480 evals/s/worker.
    est_wall_h     = total_pending * est_s_per_run / n_workers / 3600

    print(f"\n{'='*68}")
    print(f"  TUNING RS — machine {machine_id}")
    print(f"{'='*68}")
    print(f"  Total tasks desta máquina : {total_machine}")
    print(f"  Pendentes                 : {total_pending}")
    print(f"  Already done              : {len(completed)}")
    print(f"  n_evals por run           : {n_evals_eff:,}")
    print(f"  Workers                   : {n_workers}")
    print(f"  ETA estimado              : ~{est_wall_h:.1f}h")
    print(f"  Saída                     : {out_dir}")
    print(f"{'='*68}\n")

    if not pending:
        print("  Todos os tasks concluídos.")
        return

    print(f"  {'#':>6}  {'Alg':<10}  {'Inst':<10}  {'Cfg':>4}  "
          f"{'Feas':>5}  {'ND':>4}  {'HV_local':>14}  {'Tempo':>7}  Status")
    print(f"  {'-'*6}  {'-'*10}  {'-'*10}  {'-'*4}  "
          f"{'-'*5}  {'-'*4}  {'-'*14}  {'-'*7}  {'-'*20}")

    global_start = time.perf_counter()
    done = len(completed)
    errors = 0

    with Pool(processes=n_workers) as pool:
        for summ in pool.imap_unordered(run_task, pending):
            done += 1
            if summ["status"] != "ok":
                errors += 1

            # Escreve linha no CSV da máquina
            task_dict = next(t for t in pending if t["task_id"] == summ["task_id"])
            write_csv_row(index_csv, task_dict, summ)

            elapsed_total = time.perf_counter() - global_start
            frac  = done / total_machine if total_machine > 0 else 1.0
            eta_s = (elapsed_total / frac - elapsed_total) if frac > 0 else 0.0
            eta   = f"{int(eta_s//3600)}h{int((eta_s%3600)//60):02d}m"

            status_str = (f"ERRO: {summ['error_msg'][:25]}"
                          if summ["status"] != "ok"
                          else f"ok  ETA:{eta}")

            print(f"  {done:>6}/{total_machine}  "
                  f"{summ['algorithm_id']:<10}  "
                  f"{summ['instance']:<10}  "
                  f"{summ['config_idx']:>4}  "
                  f"{summ['n_feasible']:>5}  "
                  f"{summ['n_pareto']:>4}  "
                  f"{summ['hv_local']:>14.0f}  "
                  f"{summ['elapsed_s']:>6.0f}s  "
                  f"{status_str}")

    elapsed_total = time.perf_counter() - global_start
    h, rem = divmod(int(elapsed_total), 3600)
    m, s   = divmod(rem, 60)
    print(f"\n  Concluído em {h}h {m:02d}m {s:02d}s  |  Erros: {errors}/{total_pending}")
    print(f"  index.csv → {index_csv}")


# ─────────────────────────────────────────────────────────────────────────────
# Modo 3 — Análise
# ─────────────────────────────────────────────────────────────────────────────

def analyze(tuning_dir: str):
    """
    Merge dos 4 index.csv → análise de importância e configuração vencedora.

    Pipeline:
      1. Merge dos CSVs em merged_index.csv
      2. Ref_points globais por instância (máx entre TODOS os runs × 1.1)
      3. Recálculo do HV com ref_points consistentes (requer abrir pickles)
      4. Ranking das 50 configs por algoritmo (média de ranks sobre 6 instâncias)
      5. Importância marginal de cada parâmetro (acima vs abaixo da mediana)
      6. Geração do tuning_report.md
    """
    print(f"\n{'='*68}")
    print("  TUNING RS — ANÁLISE")
    print(f"{'='*68}\n")

    # ── 1. Merge ──────────────────────────────────────────────────────────────
    all_rows = []
    for m in range(1, N_MACHINES + 1):
        csv_path = os.path.join(tuning_dir, f"machine{m}", "index.csv")
        if not os.path.exists(csv_path):
            print(f"  [AVISO] machine{m}/index.csv não encontrado — pulando")
            continue
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            r["machine_id"] = m
            r["front_dir"]  = os.path.join(tuning_dir, f"machine{m}", "fronts")
        all_rows.extend(rows)

    ok_rows = [r for r in all_rows if r.get("status") == "ok"]
    print(f"  Total rows carregadas : {len(all_rows)}")
    print(f"  Status=ok             : {len(ok_rows)}")

    missing = 1800 - len(ok_rows)   # 100 configs × 3 algs × 6 instâncias = 1800
    if missing > 0:
        print(f"  [AVISO] {missing} tasks faltando — resultados parciais")

    # Salva merged
    merged_path = os.path.join(tuning_dir, "merged_index.csv")
    with open(merged_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS + ["machine_id"])
        w.writeheader()
        for r in ok_rows:
            w.writerow({k: r.get(k, "") for k in CSV_FIELDS + ["machine_id"]})
    print(f"  merged_index.csv → {merged_path}")

    # ── 2. Ref_points globais por instância ───────────────────────────────────
    print("\n  Calculando ref_points globais...")
    F_by_inst: dict[str, list] = {inst: [] for inst in TUNING_INSTANCES}

    for r in ok_rows:
        inst     = r["instance"]
        pkl_path = os.path.join(r["front_dir"], os.path.basename(r["front_path"]))
        if not os.path.exists(pkl_path):
            continue
        try:
            with open(pkl_path, "rb") as fp:
                d = pickle.load(fp)
            F = d["pareto_front"]["F"]
            if len(F) > 0:
                F_by_inst[inst].append(F)
        except Exception as e:
            print(f"  [AVISO] Erro ao ler {pkl_path}: {e}")

    ref_points: dict[str, np.ndarray] = {}
    for inst, Fs in F_by_inst.items():
        if Fs:
            combined = np.vstack(Fs)
            ref_points[inst] = combined.max(axis=0) * 1.1
            print(f"    {inst}: ref_point = {ref_points[inst].round(1).tolist()}")
        else:
            print(f"    {inst}: sem dados — pulando")

    # ── 3. Recálculo HV consistente ───────────────────────────────────────────
    print("\n  Recalculando HV com ref_points globais...")
    hv_data: dict[tuple, float] = {}  # (alg, config_idx, inst) → hv

    for r in ok_rows:
        alg      = r["algorithm_id"]
        cfg_idx  = int(r["config_idx"])
        inst     = r["instance"]
        pkl_path = os.path.join(r["front_dir"], os.path.basename(r["front_path"]))
        ref      = ref_points.get(inst)
        if ref is None or not os.path.exists(pkl_path):
            continue
        try:
            with open(pkl_path, "rb") as fp:
                d = pickle.load(fp)
            F   = d["pareto_front"]["F"]
            hv  = _hv(F, ref)
            hv_data[(alg, cfg_idx, inst)] = hv
        except Exception:
            pass

    # ── 4. Rank médio por config (menor = melhor) ─────────────────────────────
    print("\n  Calculando ranks...")
    algs = ["nsga2", "smsemoa", "moead_ws"]
    insts = list(TUNING_INSTANCES.keys())

    # Para cada alg: dict config_idx → lista de ranks sobre instâncias
    rank_results: dict[str, dict[int, list]] = {}
    for alg in algs:
        cfg_indices = list(range(1, N_CONFIGS + 1))
        rank_results[alg] = {ci: [] for ci in cfg_indices}

        for inst in insts:
            if inst not in ref_points:
                continue
            # HVs desta inst para este alg
            hvs = {ci: hv_data.get((alg, ci, inst), 0.0)
                   for ci in cfg_indices}
            # Rank (1=melhor): ordena decrescente de HV, 1=maior
            sorted_cfgs = sorted(cfg_indices, key=lambda ci: hvs[ci], reverse=True)
            for rank, ci in enumerate(sorted_cfgs, start=1):
                rank_results[alg][ci].append(rank)

    # Rank médio por config
    mean_ranks: dict[str, list] = {}
    for alg in algs:
        mr = []
        for ci in range(1, N_CONFIGS + 1):
            ranks = rank_results[alg][ci]
            mr.append((float(np.mean(ranks)) if ranks else float("nan"), ci))
        mr.sort()   # menor rank médio primeiro
        mean_ranks[alg] = mr

    # ── 5. Importância marginal dos parâmetros ────────────────────────────────
    print("  Calculando importância marginal dos parâmetros...")

    def marginal_importance(alg: str, param: str,
                            cfg_rows: list[dict]) -> dict:
        """
        Importância para parâmetros NUMÉRICOS.
        Divide em acima/abaixo da mediana e compara HV médio.
        """
        vals = []
        hvs  = []
        for r in cfg_rows:
            v = r.get(param)
            if v in (None, "", "None"):
                continue
            try:
                v_f = float(v)
            except (ValueError, TypeError):
                continue
            ci     = int(r["config_idx"])
            hv_avg = float(np.mean([hv_data.get((alg, ci, inst), 0.0)
                                    for inst in insts if inst in ref_points]))
            vals.append(v_f)
            hvs.append(hv_avg)

        if len(vals) < 4:
            return {"type": "numeric", "n": len(vals), "diff_pct": float("nan")}

        median_v = float(np.median(vals))
        high     = [h for v, h in zip(vals, hvs) if v >= median_v]
        low      = [h for v, h in zip(vals, hvs) if v < median_v]

        hv_high = float(np.mean(high)) if high else 0.0
        hv_low  = float(np.mean(low))  if low  else 0.0
        base    = max(hv_high, hv_low, 1.0)
        diff    = (hv_high - hv_low) / base * 100.0

        return {
            "type":     "numeric",
            "n":        len(vals),
            "median_v": round(median_v, 4),
            "hv_high":  round(hv_high, 0),
            "hv_low":   round(hv_low,  0),
            "diff_pct": round(diff, 2),
        }

    def categorical_importance(alg: str, param: str,
                               cfg_rows: list[dict]) -> dict:
        """
        Importância para parâmetros CATEGÓRICOS (decomposition, ref_dirs_method).
        Agrupa por categoria e compara HV médio entre grupos.
        Retorna dict com HV médio por categoria e Δ% entre melhor e pior grupo.
        """
        cat_hvs: dict[str, list] = {}   # categoria → lista de HV médios
        for r in cfg_rows:
            v = r.get(param)
            if v in (None, "", "None"):
                continue
            ci     = int(r["config_idx"])
            hv_avg = float(np.mean([hv_data.get((alg, ci, inst), 0.0)
                                    for inst in insts if inst in ref_points]))
            cat_hvs.setdefault(str(v), []).append(hv_avg)

        if not cat_hvs:
            return {"type": "categorical", "categories": {}, "diff_pct": float("nan")}

        cat_means = {cat: float(np.mean(hvs)) for cat, hvs in cat_hvs.items()}
        best_hv   = max(cat_means.values())
        worst_hv  = min(cat_means.values())
        base      = max(best_hv, 1.0)
        diff      = (best_hv - worst_hv) / base * 100.0

        return {
            "type":       "categorical",
            "categories": {cat: {"n": len(cat_hvs[cat]),
                                  "hv_mean": round(cat_means[cat], 0)}
                           for cat in sorted(cat_means)},
            "best_cat":   max(cat_means, key=cat_means.__getitem__),
            "worst_cat":  min(cat_means, key=cat_means.__getitem__),
            "diff_pct":   round(diff, 2),
        }

    importance: dict[str, dict] = {}
    for alg in algs:
        cfg_rows_alg = [r for r in ok_rows if r["algorithm_id"] == alg]
        # Parâmetros numéricos — todos os algoritmos
        params_numeric = ["pc", "pm"]
        if alg == "moead_ws":
            params_numeric += ["n_neighbors", "prob_neighbor_mating", "pbi_theta"]
        imp = {p: marginal_importance(alg, p, cfg_rows_alg)
               for p in params_numeric}
        # Parâmetros categóricos — MOEA/D somente
        if alg == "moead_ws":
            imp["decomposition"]   = categorical_importance(alg, "decomposition",   cfg_rows_alg)
            imp["ref_dirs_method"] = categorical_importance(alg, "ref_dirs_method", cfg_rows_alg)
        importance[alg] = imp

    # ── 6. Relatório Markdown ─────────────────────────────────────────────────
    print("  Gerando tuning_report.md...")
    ts  = datetime.now().isoformat(timespec="seconds")
    md  = []
    md += [f"# Relatório de Hypertuning — Random Search\n\n"]
    md += [f"**Gerado em**: {ts}  \n"]
    md += [f"**Instâncias**: {', '.join(insts)}  \n"]
    md += [f"**Configs por algoritmo**: {N_CONFIGS}  \n"]
    md += [f"**N_evals por run**: {N_EVALS:,}  \n"]
    md += [f"**Total runs OK**: {len(ok_rows)} / 1800  \n\n---\n"]

    for alg in algs:
        md += [f"\n## {alg.upper()}\n"]

        # Melhor config
        best_rank, best_ci = mean_ranks[alg][0]
        best_row = next((r for r in ok_rows
                         if r["algorithm_id"] == alg
                         and int(r["config_idx"]) == best_ci), None)

        md += [f"\n### Configuração Vencedora (rank médio = {best_rank:.1f})\n\n"]
        md += [f"```\nconfig_idx: {best_ci}\n"]
        if best_row:
            for f_ in ("pc", "pm", "n_neighbors", "prob_neighbor_mating",
                       "decomposition", "ref_dirs_method", "pbi_theta"):
                v = best_row.get(f_, "")
                if v not in (None, ""):
                    md += [f"{f_}: {v}\n"]
        md += ["```\n"]

        # Top 5 — colunas expandidas para MOEA/D
        md += [f"\n### Top 5 Configurações\n\n"]
        if alg == "moead_ws":
            md += ["| Rank | cfg_idx | pc | pm | n_neighbors | prob_nm | decomposition | ref_dirs | HV médio | rank médio |\n"]
            md += ["|---|---|---|---|---|---|---|---|---|---|\n"]
        else:
            md += ["| Rank | cfg_idx | pc | pm | HV médio | rank médio |\n"]
            md += ["|---|---|---|---|---|---|\n"]

        for rank_pos, (r_avg, ci) in enumerate(mean_ranks[alg][:5], start=1):
            hv_avg = float(np.mean([hv_data.get((alg, ci, inst), 0.0)
                                    for inst in insts if inst in ref_points]))
            row_r = next((r for r in ok_rows
                          if r["algorithm_id"] == alg
                          and int(r["config_idx"]) == ci), {})
            if alg == "moead_ws":
                md += [f"| {rank_pos} | {ci} | "
                       f"{row_r.get('pc','')} | {row_r.get('pm','')} | "
                       f"{row_r.get('n_neighbors','')} | {row_r.get('prob_neighbor_mating','')} | "
                       f"{row_r.get('decomposition','')} | {row_r.get('ref_dirs_method','')} | "
                       f"{hv_avg:.0f} | {r_avg:.1f} |\n"]
            else:
                md += [f"| {rank_pos} | {ci} | "
                       f"{row_r.get('pc','')} | {row_r.get('pm','')} | "
                       f"{hv_avg:.0f} | {r_avg:.1f} |\n"]

        # Importância marginal — trata numérico e categórico separadamente
        md += [f"\n### Importância Marginal dos Parâmetros\n\n"]
        md += ["**Parâmetros numéricos** (acima vs abaixo da mediana):\n\n"]
        md += ["| Parâmetro | Mediana | HV (≥ mediana) | HV (< mediana) | Δ% |\n"]
        md += ["|---|---|---|---|---|\n"]
        for pm_name, imp in importance.get(alg, {}).items():
            if imp.get("type") != "numeric":
                continue
            diff_str = (f"{imp['diff_pct']:+.1f}%"
                        if not np.isnan(imp.get("diff_pct", float("nan")))
                        else "n/a")
            md += [f"| {pm_name} | {imp.get('median_v','')} | "
                   f"{imp.get('hv_high','')} | {imp.get('hv_low','')} | "
                   f"{diff_str} |\n"]

        # Tabela categórica — MOEA/D somente
        cat_params = [(pm_name, imp) for pm_name, imp in importance.get(alg, {}).items()
                      if imp.get("type") == "categorical"]
        if cat_params:
            md += ["\n**Parâmetros categóricos** (HV médio por categoria):\n\n"]
            for pm_name, imp in cat_params:
                diff_str = (f"{imp['diff_pct']:+.1f}%"
                            if not np.isnan(imp.get("diff_pct", float("nan")))
                            else "n/a")
                md += [f"**{pm_name}** — Δ%(melhor vs pior) = {diff_str}  "
                       f"(melhor: `{imp.get('best_cat','')}`)\n\n"]
                md += ["| Categoria | N configs | HV médio |\n"]
                md += ["|---|---|---|\n"]
                for cat, info in imp.get("categories", {}).items():
                    md += [f"| {cat} | {info['n']} | {info['hv_mean']:.0f} |\n"]
                md += ["\n"]

    md += [f"\n---\n\n"]
    md += ["## Metodologia\n\n"]
    md += ["- Todas as 300 configurações foram geradas deterministicamente "
           "(seed=43) antes da execução.\n"]
    md += [f"- Cada configuração foi avaliada em {len(insts)} instâncias "
           f"({N_EVALS:,} avaliações cada).\n"]
    md += ["- Critério de seleção: **rank médio** sobre as instâncias "
           "(menor = melhor).\n"]
    md += ["- HV calculado com ref_point **global** (máx sobre todos os runs "
           "× 1.1 por instância).\n"]
    md += ["- Importância marginal: diferença percentual de HV entre configs "
           "acima e abaixo da mediana do parâmetro.\n"]
    md += [f"\n### Nota sobre dimensionalidade:\n"]
    md += ["NSGA-II e SMS-EMOA têm 2 parâmetros livres (pc, pm); "
           "MOEA/D-WS tem 6. Isso implica que com o mesmo número de "
           "amostras (100), o MOEA/D-WS cobre um espaço 3× maior, "
           "reduzindo a probabilidade de encontrar a configuração ótima. "
           "Esta maior complexidade de configuração é um custo real da "
           "decomposição escalar e deve ser documentada no TCC.\n"]

    report_path = os.path.join(tuning_dir, "tuning_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.writelines(md)

    print(f"\n  tuning_report.md → {report_path}")

    # Resumo no console
    print(f"\n{'─'*68}")
    for alg in algs:
        best_rank, best_ci = mean_ranks[alg][0]
        print(f"  {alg:<12} → config_idx={best_ci:>3},  "
              f"rank médio={best_rank:.1f}")
    print(f"{'─'*68}")
    print(f"\n  ✅ Análise concluída: {report_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Hypertuning por Random Search — EVRPTW TCC"
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate",   action="store_true",
                      help="Gera all_configs.json e all_tasks.json")
    mode.add_argument("--run",        action="store_true",
                      help="Executa tasks desta máquina")
    mode.add_argument("--analyze",    action="store_true",
                      help="Analisa resultados das 5 máquinas")

    ap.add_argument("--machine-id",  type=int, choices=[1, 2, 3, 4, 5],
                    help="ID da máquina (obrigatório com --run): "
                         "1=maq64, 2=maq65, 3=maq66, 4=maq67, 5=DellG15")
    ap.add_argument("--tuning-dir",  default=os.path.join(ROOT, "results", "tuning_rs_v2"),
                    help="Diretório raiz do experimento de tuning")
    ap.add_argument("--n-workers",   type=int, default=N_WORKERS,
                    help=f"Workers paralelos (padrão: {N_WORKERS})")
    ap.add_argument("--n-evals",     type=int, default=None,
                    help=f"Avaliações por run (padrão: {N_EVALS:,})")
    ap.add_argument("--n-machines",  type=int, default=N_MACHINES,
                    help=f"Número de máquinas (padrão: {N_MACHINES})")
    ap.add_argument("--dry-run",     action="store_true",
                    help="1 task, 5k evals, 1 worker — verifica pipeline (~30s)")
    args = ap.parse_args()

    os.makedirs(args.tuning_dir, exist_ok=True)

    print(f"\n{'='*68}")
    print(f"  HYPERTUNING RANDOM SEARCH — EVRPTW TCC")
    print(f"{'='*68}")
    print(f"  Modo       : {'--generate' if args.generate else '--run' if args.run else '--analyze'}")
    print(f"  Diretório  : {args.tuning_dir}")
    print(f"{'='*68}")

    if args.generate:
        generate(args.tuning_dir)

    elif args.run:
        if args.machine_id is None:
            print("[ERRO] --machine-id é obrigatório com --run")
            sys.exit(1)
        run_machine(
            machine_id       = args.machine_id,
            tuning_dir       = args.tuning_dir,
            n_workers        = args.n_workers,
            n_evals_override = args.n_evals,
            dry_run          = args.dry_run,
        )

    elif args.analyze:
        analyze(args.tuning_dir)


if __name__ == "__main__":
    main()
