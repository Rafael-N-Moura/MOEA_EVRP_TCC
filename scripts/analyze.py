"""
analyze.py
==========
Script de análise pós-experimento do TCC — EVRPTW tri-objetivo.

Cada passo é uma função independente que depende do anterior.
Execute sequencialmente:

    python scripts/analyze.py --step 1 --experiment-dir results/main_experiment
    python scripts/analyze.py --step 2 --experiment-dir results/main_experiment
    ...

Ou para rodar todos os passos implementados de uma vez:
    python scripts/analyze.py --all --experiment-dir results/main_experiment
"""

import argparse
import csv
import json
import os
import pickle
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Configuração
# ─────────────────────────────────────────────────────────────────────────────

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

N_MACHINES  = 5
N_RUNS      = 30
N_ALGORITHMS = 3
N_INSTANCES = 50
TOTAL_RUNS  = N_INSTANCES * N_ALGORITHMS * N_RUNS  # 4500

ALGORITHMS = ["nsga2", "smsemoa", "moead_ws"]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def _non_dominated(F: np.ndarray) -> np.ndarray:
    """Filtra soluções não-dominadas (minimização). O(n²) — suficiente para n ≤ 2000."""
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


def _resolve_pkl(experiment_dir: str, machine_id: int, pkl_path_raw: str) -> str:
    """
    Resolve o caminho absoluto de um pickle a partir do pickle_path relativo
    armazenado no CSV.

    pickle_path é relativo a experiment_dir/machine{N}/. Normaliza separadores
    (machine5 gerou paths com backslash no Windows).
    """
    pkl_rel = Path(pkl_path_raw.replace("\\", "/"))
    return os.path.join(experiment_dir, f"machine{machine_id}", str(pkl_rel))


def _banner(title: str):
    print(f"\n{'=' * 68}")
    print(f"  {title}")
    print(f"{'=' * 68}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Passo 1 — Merge e validação
# ─────────────────────────────────────────────────────────────────────────────

def step1_merge(experiment_dir: str) -> str:
    """
    Lê os 5 index.csv, concatena e valida:
      1. Contagem: exactamente 4500 linhas status=ok
      2. Unicidade: cada (alg, inst, run_idx) aparece uma vez
      3. Integridade: cada pickle_path referenciado existe

    Saída: {experiment_dir}/merged_index.csv
    Retorna: caminho do merged_index.csv
    """
    _banner("PASSO 1 — MERGE E VALIDAÇÃO")

    # ── Lê todos os CSVs ─────────────────────────────────────────────────────
    all_rows = []
    for m in range(1, N_MACHINES + 1):
        csv_path = os.path.join(experiment_dir, f"machine{m}", "index.csv")
        if not os.path.exists(csv_path):
            print(f"  [AVISO] machine{m}/index.csv não encontrado — pulando")
            continue
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            r["_machine_id"] = str(m)
        all_rows.extend(rows)
        print(f"  machine{m}: {len(rows):>4} linhas carregadas")

    ok_rows = [r for r in all_rows if r.get("status") == "ok"]
    print(f"\n  Total linhas    : {len(all_rows)}")
    print(f"  Status = ok     : {len(ok_rows)}")

    # ── Verificação 1: contagem ───────────────────────────────────────────────
    missing_count = TOTAL_RUNS - len(ok_rows)
    if missing_count > 0:
        print(f"\n  ❌ FALTAM {missing_count} runs de {TOTAL_RUNS} esperados")
    else:
        print(f"  ✅ Contagem correta: {TOTAL_RUNS} runs")

    # ── Verificação 2: unicidade ──────────────────────────────────────────────
    key_counts = Counter(
        (r["algorithm_id"], r["instance"], r["run_idx"])
        for r in ok_rows
    )
    duplicates = {k: v for k, v in key_counts.items() if v > 1}
    if duplicates:
        print(f"\n  ⚠️  {len(duplicates)} triplas duplicadas — mantendo apenas a primeira ocorrência:")
        for k, v in list(duplicates.items())[:10]:
            print(f"       {k[0]}/{k[1]}/run{k[2]}: {v}x")
        # Deduplica: mantém só a primeira ocorrência de cada tripla
        seen = set()
        deduped = []
        for r in ok_rows:
            key = (r["algorithm_id"], r["instance"], r["run_idx"])
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        ok_rows = deduped
        print(f"  → Após deduplicação: {len(ok_rows)} linhas")
    else:
        print(f"  ✅ Unicidade ok: sem duplicatas")

    # ── Verificação 3: integridade dos pickles ────────────────────────────────
    print(f"\n  Verificando existência de pickles...")
    missing_pkls = []
    for r in ok_rows:
        m_id = int(r["_machine_id"])
        pkl_abs = _resolve_pkl(experiment_dir, m_id, r.get("pickle_path", ""))
        if not os.path.exists(pkl_abs):
            missing_pkls.append((r["algorithm_id"], r["instance"], r["run_idx"], pkl_abs))

    if missing_pkls:
        print(f"  ❌ {len(missing_pkls)} pickles não encontrados:")
        for alg, inst, run, path in missing_pkls[:10]:
            print(f"       {alg}/{inst}/run{run}: {path}")
        if len(missing_pkls) > 10:
            print(f"       ... e mais {len(missing_pkls)-10}")
    else:
        print(f"  ✅ Todos os {len(ok_rows)} pickles existem")

    # ── Identifica runs faltantes ─────────────────────────────────────────────
    if missing_count > 0:
        # Determina o conjunto completo esperado
        # (precisamos das 50 instâncias — lemos do all_tasks.json se disponível)
        tasks_path = os.path.join(experiment_dir, "all_tasks.json")
        if os.path.exists(tasks_path):
            with open(tasks_path, encoding="utf-8") as f:
                all_tasks = json.load(f)
            expected = {
                (t["algorithm_id"], t["instance"], str(t["run_idx"]))
                for t in all_tasks
            }
            present = {
                (r["algorithm_id"], r["instance"], r["run_idx"])
                for r in ok_rows
            }
            missing_triples = expected - present
            print(f"\n  Runs faltantes ({len(missing_triples)}):")
            for alg, inst, run in sorted(missing_triples)[:20]:
                print(f"    {alg}/{inst}/run{run}")
            if len(missing_triples) > 20:
                print(f"    ... e mais {len(missing_triples)-20}")
        else:
            print(f"\n  [AVISO] all_tasks.json não encontrado — não é possível listar faltantes")

    # ── Salva merged_index.csv ────────────────────────────────────────────────
    merged_path = os.path.join(experiment_dir, "merged_index.csv")
    if ok_rows:
        fieldnames = [k for k in ok_rows[0].keys()]
        with open(merged_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(ok_rows)
        print(f"\n  ✅ merged_index.csv salvo → {merged_path}")
        print(f"     {len(ok_rows)} linhas, {len(fieldnames)} campos")
    else:
        print(f"\n  ❌ Nenhuma linha ok — merged_index.csv não salvo")

    return merged_path


# ─────────────────────────────────────────────────────────────────────────────
# Passo 2 — Ref_points globais + frentes combinadas
# ─────────────────────────────────────────────────────────────────────────────

def _process_instance_step2(args):
    """
    Worker do ProcessPoolExecutor para o Passo 2.

    Para uma única instância: abre os 90 pickles, concatena as frentes,
    calcula ref_point e frente combinada não-dominada.

    args = (instance, row_list, experiment_dir)
    Retorna: (instance, ref_point_list, combined_F)
    """
    instance, row_list, experiment_dir = args

    all_F_parts = []
    n_ok = 0
    n_empty = 0

    for r in row_list:
        m_id = int(r["_machine_id"])
        pkl_abs = _resolve_pkl(experiment_dir, m_id, r.get("pickle_path", ""))
        try:
            with open(pkl_abs, "rb") as f:
                data = pickle.load(f)
            F = data["pareto_front"]["F"]
            if len(F) > 0:
                all_F_parts.append(F)
                n_ok += 1
            else:
                n_empty += 1
        except Exception as e:
            n_empty += 1

    if not all_F_parts:
        # Nenhuma solução viável em nenhum run — retorna valores nulos
        return instance, None, None, n_ok, n_empty

    all_F = np.vstack(all_F_parts)

    # Ref_point: 1.1 × máximo de cada objetivo
    ref_point = (all_F.max(axis=0) * 1.1).tolist()

    # Frente combinada: união não-dominada de todas as soluções
    combined_F = _non_dominated(all_F)

    return instance, ref_point, combined_F, n_ok, n_empty


def step2_ref_points(experiment_dir: str, n_workers: int = 8) -> str:
    """
    Para cada instância, abre 90 pickles, calcula:
      - ref_point global (max(F) × 1.1)
      - frente combinada não-dominada (para IGD+)

    Saídas:
      {experiment_dir}/ref_points.json
      {experiment_dir}/combined_fronts/{instance}.npy

    Retorna: caminho do ref_points.json
    """
    _banner("PASSO 2 — REF_POINTS GLOBAIS E FRENTES COMBINADAS")

    # ── Carrega merged_index.csv ──────────────────────────────────────────────
    merged_path = os.path.join(experiment_dir, "merged_index.csv")
    if not os.path.exists(merged_path):
        print("  ❌ merged_index.csv não encontrado. Execute o Passo 1 primeiro.")
        sys.exit(1)

    with open(merged_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"  Carregados {len(rows)} runs do merged_index.csv")

    # ── Agrupa linhas por instância ───────────────────────────────────────────
    by_instance = defaultdict(list)
    for r in rows:
        by_instance[r["instance"]].append(r)

    instances = sorted(by_instance.keys())
    print(f"  Instâncias encontradas: {len(instances)}")
    if len(instances) != N_INSTANCES:
        print(f"  ⚠️  Esperado {N_INSTANCES}, encontrado {len(instances)}")

    # ── Cria diretório de saída para frentes combinadas ───────────────────────
    combined_dir = os.path.join(experiment_dir, "combined_fronts")
    os.makedirs(combined_dir, exist_ok=True)

    # ── Processa cada instância em paralelo ───────────────────────────────────
    args_list = [
        (inst, by_instance[inst], experiment_dir)
        for inst in instances
    ]

    ref_points = {}
    n_total_ok    = 0
    n_total_empty = 0
    t0 = time.perf_counter()

    print(f"\n  Abrindo pickles ({len(instances)} instâncias × ~90 runs cada)...")
    print(f"  Workers paralelos: {n_workers}")
    print()

    with ProcessPoolExecutor(max_workers=n_workers) as exe:
        futures = {exe.submit(_process_instance_step2, a): a[0] for a in args_list}
        done = 0
        for fut in as_completed(futures):
            instance, ref_point, combined_F, n_ok, n_empty = fut.result()
            done += 1
            n_total_ok    += n_ok
            n_total_empty += n_empty

            if ref_point is None:
                print(f"  [{done:>2}/{len(instances)}] {instance:<14} ❌ sem soluções viáveis")
                ref_points[instance] = {
                    "ref_point": None,
                    "combined_front_size": 0,
                }
                continue

            # Salva frente combinada como .npy
            npy_path = os.path.join(combined_dir, f"{instance}.npy")
            np.save(npy_path, combined_F)

            ref_points[instance] = {
                "ref_point": ref_point,
                "combined_front_size": int(len(combined_F)),
            }

            elapsed = time.perf_counter() - t0
            eta_s   = elapsed / done * (len(instances) - done)
            eta_str = f"{int(eta_s//60)}m{int(eta_s%60):02d}s"

            print(
                f"  [{done:>2}/{len(instances)}] {instance:<14} "
                f"ref=[{ref_point[0]:>7.2f}, {ref_point[1]:>9.2f}, {ref_point[2]:>9.2f}]  "
                f"combined_front={len(combined_F):>4}  "
                f"pickles={n_ok:>2}  ETA:{eta_str}",
                flush=True,
            )

    # ── Salva ref_points.json ─────────────────────────────────────────────────
    ref_path = os.path.join(experiment_dir, "ref_points.json")
    with open(ref_path, "w", encoding="utf-8") as f:
        json.dump(ref_points, f, indent=2)

    elapsed_total = time.perf_counter() - t0
    print(f"\n  Concluído em {elapsed_total/60:.1f} min")
    print(f"  Pickles processados: {n_total_ok} ok, {n_total_empty} vazios/erros")
    print(f"  ✅ ref_points.json salvo → {ref_path}")
    print(f"  ✅ frentes combinadas    → {combined_dir}/{{instance}}.npy")

    # ── Resumo rápido ─────────────────────────────────────────────────────────
    sizes = [v["combined_front_size"] for v in ref_points.values() if v["combined_front_size"] > 0]
    if sizes:
        print(f"\n  Frente combinada — tamanho:")
        print(f"    mín={min(sizes)}, máx={max(sizes)}, mediana={int(np.median(sizes))}")

    return ref_path


# ─────────────────────────────────────────────────────────────────────────────
# Passo 3 — Recálculo de métricas com ref_point global
# ─────────────────────────────────────────────────────────────────────────────

def _spacing(F: np.ndarray) -> float:
    """
    Spacing: std(d_min) / mean(d_min), onde d_min[i] = distância mínima de i
    ao vizinho mais próximo. Menor é melhor (distribuição mais uniforme).
    """
    if len(F) < 2:
        return 0.0
    from scipy.spatial.distance import cdist
    D = cdist(F, F)
    np.fill_diagonal(D, np.inf)
    d_min = D.min(axis=1)
    mean_d = float(np.mean(d_min))
    return float(np.std(d_min) / mean_d) if mean_d > 0 else 0.0


def _spread(F: np.ndarray) -> float:
    """
    Spread (extensão): soma das distâncias euclidianas entre soluções extremas
    em cada objetivo (distância entre o mínimo e o máximo de cada coluna).
    """
    if len(F) < 2:
        return 0.0
    return float(np.sum(F.max(axis=0) - F.min(axis=0)))


def _process_instance_step3(args):
    """
    Worker do ProcessPoolExecutor para o Passo 3.

    Para cada run da instância: abre o pickle, extrai F_pareto e calcula:
      - HV  (usando ref_point global)
      - IGD+ (usando frente combinada como referência)
      - spacing, spread, n_pareto, n_f1_layers

    args = (instance, row_list, experiment_dir, ref_point, combined_F)
    Retorna: lista de dicts (uma por run) com todas as métricas.
    """
    from pymoo.indicators.hv import HV
    from pymoo.indicators.igd_plus import IGDPlus

    instance, row_list, experiment_dir, ref_point, combined_F = args
    ref_point_arr = np.array(ref_point)
    hv_indicator  = HV(ref_point=ref_point_arr)

    # IGD+ requer pelo menos 1 ponto na frente de referência
    igd_indicator = IGDPlus(combined_F) if len(combined_F) > 0 else None

    results = []
    for r in row_list:
        m_id    = int(r["_machine_id"])
        pkl_abs = _resolve_pkl(experiment_dir, m_id, r.get("pickle_path", ""))
        alg     = r["algorithm_id"]
        inst    = r["instance"]
        run_idx = int(r["run_idx"])

        try:
            with open(pkl_abs, "rb") as f:
                data = pickle.load(f)
            F = data["pareto_front"]["F"]
        except Exception as e:
            results.append({
                "algorithm_id": alg, "instance": inst, "run_idx": run_idx,
                "hv": float("nan"), "igd_plus": float("nan"),
                "spacing": float("nan"), "spread": float("nan"),
                "n_pareto": 0, "n_f1_layers": 0,
                "status": f"error: {e}",
            })
            continue

        n_pareto = len(F)

        if n_pareto == 0:
            results.append({
                "algorithm_id": alg, "instance": inst, "run_idx": run_idx,
                "hv": 0.0, "igd_plus": float("nan"),
                "spacing": 0.0, "spread": 0.0,
                "n_pareto": 0, "n_f1_layers": 0,
                "status": "empty_front",
            })
            continue

        # HV — só conta soluções que estão abaixo do ref_point em todos objetivos
        try:
            mask_hv = np.all(F < ref_point_arr, axis=1)
            F_for_hv = F[mask_hv]
            hv_val = float(hv_indicator(F_for_hv)) if len(F_for_hv) > 0 else 0.0
        except Exception:
            hv_val = 0.0

        # IGD+
        try:
            igd_val = float(igd_indicator(F)) if igd_indicator is not None else float("nan")
        except Exception:
            igd_val = float("nan")

        results.append({
            "algorithm_id": alg,
            "instance":     inst,
            "run_idx":      run_idx,
            "hv":           round(hv_val, 6),
            "igd_plus":     round(igd_val, 6),
            "spacing":      round(_spacing(F), 6),
            "spread":       round(_spread(F), 4),
            "n_pareto":     n_pareto,
            "n_f1_layers":  int(len(np.unique(np.round(F[:, 0])))),
            "status":       "ok",
        })

    return results


def step3_metrics(experiment_dir: str, n_workers: int = 8) -> str:
    """
    Calcula HV, IGD+, spacing, spread, n_pareto, n_f1_layers para cada run.
    Usa ref_point e frente combinada do Passo 2.

    Saída: {experiment_dir}/metrics.csv
    Retorna: caminho do metrics.csv
    """
    _banner("PASSO 3 — MÉTRICAS POR RUN (HV, IGD+, SPACING, SPREAD)")

    # ── Verifica pré-requisitos ───────────────────────────────────────────────
    merged_path   = os.path.join(experiment_dir, "merged_index.csv")
    ref_path      = os.path.join(experiment_dir, "ref_points.json")
    combined_dir  = os.path.join(experiment_dir, "combined_fronts")

    for p in [merged_path, ref_path]:
        if not os.path.exists(p):
            print(f"  ❌ {os.path.basename(p)} não encontrado. Execute os passos anteriores.")
            sys.exit(1)

    with open(merged_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with open(ref_path, encoding="utf-8") as f:
        ref_points = json.load(f)

    print(f"  Carregados {len(rows)} runs do merged_index.csv")

    # ── Agrupa por instância ──────────────────────────────────────────────────
    by_instance = defaultdict(list)
    for r in rows:
        by_instance[r["instance"]].append(r)
    instances = sorted(by_instance.keys())

    # ── Monta args para workers ───────────────────────────────────────────────
    args_list = []
    n_skip = 0
    for inst in instances:
        rp_info = ref_points.get(inst, {})
        ref_point = rp_info.get("ref_point")
        if ref_point is None:
            print(f"  [AVISO] {inst}: ref_point ausente — pulando")
            n_skip += 1
            continue
        npy_path = os.path.join(combined_dir, f"{inst}.npy")
        if not os.path.exists(npy_path):
            print(f"  [AVISO] {inst}: combined_front .npy ausente — pulando")
            n_skip += 1
            continue
        combined_F = np.load(npy_path)
        args_list.append((inst, by_instance[inst], experiment_dir, ref_point, combined_F))

    print(f"  Instâncias a processar: {len(args_list)} ({n_skip} puladas)")
    print(f"  Workers paralelos     : {n_workers}")
    print()

    # ── Executa em paralelo ───────────────────────────────────────────────────
    all_metric_rows = []
    t0   = time.perf_counter()
    done = 0
    n_errors = 0

    print(f"  {'Inst':<14} {'Runs':>4}  {'HV med':>12}  {'IGD+ med':>12}  "
          f"{'Spc med':>8}  {'Spr med':>9}  {'ND med':>6}  {'Lyr med':>7}")
    print(f"  {'-'*14} {'-'*4}  {'-'*12}  {'-'*12}  {'-'*8}  {'-'*9}  {'-'*6}  {'-'*7}")

    with ProcessPoolExecutor(max_workers=n_workers) as exe:
        futures = {exe.submit(_process_instance_step3, a): a[0] for a in args_list}
        for fut in as_completed(futures):
            metric_rows = fut.result()
            inst = futures[fut]
            done += 1

            ok_rows    = [r for r in metric_rows if r["status"] == "ok"]
            err_rows   = [r for r in metric_rows if r["status"] != "ok"]
            n_errors  += len(err_rows)
            all_metric_rows.extend(metric_rows)

            # Resumo por instância
            if ok_rows:
                hvs     = [r["hv"]         for r in ok_rows]
                igds    = [r["igd_plus"]   for r in ok_rows if not np.isnan(r["igd_plus"])]
                spcs    = [r["spacing"]    for r in ok_rows]
                sprs    = [r["spread"]     for r in ok_rows]
                nds     = [r["n_pareto"]   for r in ok_rows]
                lyrs    = [r["n_f1_layers"] for r in ok_rows]

                elapsed = time.perf_counter() - t0
                eta_s   = elapsed / done * (len(args_list) - done)
                eta_str = f"ETA:{int(eta_s//60)}m{int(eta_s%60):02d}s"

                print(
                    f"  {inst:<14} {len(ok_rows):>4}  "
                    f"{np.median(hvs):>12.2f}  "
                    f"{np.median(igds) if igds else float('nan'):>12.4f}  "
                    f"{np.median(spcs):>8.4f}  "
                    f"{np.median(sprs):>9.2f}  "
                    f"{np.median(nds):>6.0f}  "
                    f"{np.median(lyrs):>7.1f}  "
                    f"{eta_str}",
                    flush=True,
                )
            else:
                print(f"  {inst:<14} ❌ todos os runs com erro")

    # ── Salva metrics.csv ─────────────────────────────────────────────────────
    metrics_path = os.path.join(experiment_dir, "metrics.csv")
    fields = ["algorithm_id", "instance", "run_idx",
              "hv", "igd_plus", "spacing", "spread",
              "n_pareto", "n_f1_layers", "status"]

    all_metric_rows.sort(key=lambda r: (r["instance"], r["algorithm_id"], r["run_idx"]))

    with open(metrics_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(all_metric_rows)

    elapsed_total = time.perf_counter() - t0
    n_ok_total = sum(1 for r in all_metric_rows if r["status"] == "ok")

    print(f"\n  Concluído em {elapsed_total/60:.1f} min")
    print(f"  Runs processados : {n_ok_total} ok, {n_errors} erros")
    print(f"  ✅ metrics.csv salvo → {metrics_path}")
    print(f"     {len(all_metric_rows)} linhas, {len(fields)} campos")

    return metrics_path


# ─────────────────────────────────────────────────────────────────────────────
# Passo 4 — Testes estatísticos (Demšar framework)
# ─────────────────────────────────────────────────────────────────────────────

def _holm_bonferroni(p_values: list) -> list:
    """Correção de Holm-Bonferroni para múltiplas comparações.
    Retorna lista de p-valores ajustados na mesma ordem da entrada."""
    n = len(p_values)
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    p_adj = [0.0] * n
    for rank, (orig_i, p) in enumerate(indexed):
        p_adj[orig_i] = min(1.0, p * (n - rank))
    # garante monotonia
    max_so_far = 0.0
    for _, (orig_i, _) in enumerate(indexed):
        p_adj[orig_i] = max(p_adj[orig_i], max_so_far)
        max_so_far = p_adj[orig_i]
    return p_adj


def _demsar_diagram(avg_ranks: dict, cd: float, metric_label: str, out_path: str):
    """Desenha o diagrama de Demšar (critical difference diagram)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    algs = sorted(avg_ranks, key=avg_ranks.get)  # melhor rank (menor) à esquerda
    ranks = [avg_ranks[a] for a in algs]
    n_algs = len(algs)

    fig, ax = plt.subplots(figsize=(10, 2.5 + n_algs * 0.9))
    ax.set_xlim(min(ranks) - cd - 0.5, max(ranks) + cd + 0.5)
    ax.set_ylim(-1.2, n_algs + 1.5)
    ax.axis("off")

    y_positions = {a: n_algs - i for i, a in enumerate(algs)}
    ALG_LABELS = {"nsga2": "NSGA-II", "smsemoa": "SMS-EMOA", "moead_ws": "MOEA/D"}

    # Linha de ranking
    ax.axhline(n_algs + 0.3, color="black", linewidth=2.5)
    for r in np.arange(np.floor(min(ranks)), np.ceil(max(ranks)) + 1):
        ax.plot([r, r], [n_algs + 0.1, n_algs + 0.6], color="black", linewidth=1.5)
        ax.text(r, n_algs + 0.75, f"{r:.0f}", ha="center", va="bottom", fontsize=16)

    # Nomes e pontos
    for a in algs:
        r, y = avg_ranks[a], y_positions[a]
        ax.plot([r, r], [y, n_algs + 0.3], color="steelblue", linewidth=2.0, linestyle="--", alpha=0.6)
        ax.plot(r, n_algs + 0.3, "o", color="steelblue", markersize=11)
        ax.text(r, y - 0.30, ALG_LABELS.get(a, a), ha="center", va="top",
                fontsize=20, fontweight="bold")
        ax.text(r, y - 0.90, f"rank={r:.3f}", ha="center", va="top",
                fontsize=18, color="#1a3a5c")

    # Grupos não-significativos (linha horizontal abaixo)
    pairs = [(algs[i], algs[j]) for i in range(n_algs) for j in range(i+1, n_algs)]
    groups = [(a, b) for a, b in pairs if abs(avg_ranks[a] - avg_ranks[b]) <= cd]
    y_bar = -0.4
    for a, b in groups:
        r_a, r_b = avg_ranks[a], avg_ranks[b]
        ax.plot([r_a, r_b], [y_bar, y_bar], color="black", linewidth=4.5)
        y_bar -= 0.5

    # CD arrow
    r_ref = min(ranks)
    ax.annotate("", xy=(r_ref + cd, n_algs + 1.2), xytext=(r_ref, n_algs + 1.2),
                arrowprops=dict(arrowstyle="<->", color="red", lw=2.5))
    ax.text(r_ref + cd / 2, n_algs + 1.05, f"CD={cd:.3f}",
            ha="center", va="top", color="red", fontsize=18, fontweight="bold")

    ax.set_title(f"Diagrama de Distância Crítica — {metric_label} (α=0.05, n=50)",
                 fontsize=18, pad=18, fontweight="bold")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight", pad_inches=0.02)
    # Also save as PDF (same base name, different extension)
    pdf_path = os.path.splitext(out_path)[0] + ".pdf"
    plt.savefig(pdf_path, bbox_inches="tight", pad_inches=0.02)
    plt.close()


def _run_statistical_analysis(metric_name: str, rows: list, instances: list,
                               figures_dir: str) -> dict:
    """
    Executa Friedman + Nemenyi + Wilcoxon para uma métrica (hv ou igd_plus).
    higher_is_better=True para HV, False para IGD+.
    Retorna dict com todos os resultados.
    """
    from scipy.stats import friedmanchisquare, wilcoxon as wilcoxon_test

    higher_is_better = (metric_name == "hv")
    metric_label = "HV" if higher_is_better else "IGD+"

    # ── 4a: ranking por instância ─────────────────────────────────────────────
    # Para cada instância, rank médio de cada algoritmo sobre as 30 runs
    # rank 1 = melhor (maior HV ou menor IGD+)
    by_inst_alg = defaultdict(lambda: defaultdict(list))
    for r in rows:
        val = float(r[metric_name])
        if not np.isnan(val):
            by_inst_alg[r["instance"]][r["algorithm_id"]].append(val)

    avg_ranks_per_inst = {}   # inst -> {alg: avg_rank}
    for inst in instances:
        alg_vals = by_inst_alg[inst]
        if len(alg_vals) < 2:
            continue
        # Para cada run_idx: rank dos 3 algoritmos
        # Usa medianas das 30 runs para o ranking global
        medians = {a: np.median(v) for a, v in alg_vals.items()}
        sorted_algs = sorted(medians, key=medians.get, reverse=higher_is_better)
        ranks = {a: i + 1 for i, a in enumerate(sorted_algs)}
        avg_ranks_per_inst[inst] = ranks

    # Rank médio global (sobre as 50 instâncias)
    alg_all_ranks = defaultdict(list)
    for inst, ranks in avg_ranks_per_inst.items():
        for alg, r in ranks.items():
            alg_all_ranks[alg].append(r)
    avg_ranks_global = {a: float(np.mean(v)) for a, v in alg_all_ranks.items()}

    print(f"\n  [{metric_label}] Rank médio global:")
    for a, r in sorted(avg_ranks_global.items(), key=lambda x: x[1]):
        print(f"    {a:<14} {r:.4f}")

    # ── 4b: Friedman test ─────────────────────────────────────────────────────
    rank_series = [np.array(alg_all_ranks[a]) for a in ALGORITHMS
                   if a in alg_all_ranks]
    if len(rank_series) >= 2:
        stat, p_friedman = friedmanchisquare(*rank_series)
    else:
        stat, p_friedman = float("nan"), 1.0

    sig = p_friedman < 0.05
    print(f"\n  [{metric_label}] Friedman: χ²={stat:.4f}  p={p_friedman:.6f}  "
          f"{'→ diferença significativa ✅' if sig else '→ sem diferença significativa ❌'}")

    # ── 4c: Nemenyi CD ────────────────────────────────────────────────────────
    k = len(ALGORITHMS)
    n_inst = len(avg_ranks_per_inst)
    q_alpha = 2.343   # tabelado para k=3, α=0.05
    cd = q_alpha * np.sqrt(k * (k + 1) / (6 * n_inst))
    print(f"  [{metric_label}] CD Nemenyi (α=0.05): {cd:.4f}")

    pairs = [
        (ALGORITHMS[i], ALGORITHMS[j])
        for i in range(k) for j in range(i+1, k)
        if ALGORITHMS[i] in avg_ranks_global and ALGORITHMS[j] in avg_ranks_global
    ]
    print(f"  [{metric_label}] Diferenças entre pares vs CD:")
    nemenyi_results = {}
    for a, b in pairs:
        diff = abs(avg_ranks_global[a] - avg_ranks_global[b])
        sig_pair = diff > cd
        label = f"{a}_vs_{b}"
        nemenyi_results[label] = {"diff": round(diff, 4), "cd": round(cd, 4), "significant": bool(sig_pair)}
        print(f"    {a} vs {b}: |Δrank|={diff:.4f} {'> CD ✅' if sig_pair else '≤ CD ❌'}")

    # Diagrama de Demšar
    diag_path = os.path.join(figures_dir, f"cd_{metric_name}.png")
    _demsar_diagram(avg_ranks_global, cd, metric_label, diag_path)
    print(f"  [{metric_label}] Diagrama salvo → {diag_path} (+ .pdf)")

    # ── 4d: Wilcoxon pareado por instância ───────────────────────────────────
    wilcoxon_rows = []
    p_raw_list = []
    pair_meta = []

    for inst in sorted(instances):
        alg_vals = by_inst_alg[inst]
        for a, b in pairs:
            vals_a = alg_vals.get(a, [])
            vals_b = alg_vals.get(b, [])
            if len(vals_a) < 10 or len(vals_b) < 10:
                continue
            # Alinha pelo comprimento mínimo
            n = min(len(vals_a), len(vals_b))
            try:
                stat_w, p_w = wilcoxon_test(vals_a[:n], vals_b[:n], alternative="two-sided")
            except Exception:
                stat_w, p_w = float("nan"), 1.0
            pair_meta.append((inst, f"{a}_vs_{b}", stat_w))
            p_raw_list.append(p_w)

    # Holm-Bonferroni
    p_adj_list = _holm_bonferroni(p_raw_list)

    for (inst, pair_name, stat_w), p_raw, p_adj in zip(pair_meta, p_raw_list, p_adj_list):
        wilcoxon_rows.append({
            "metric":     metric_name,
            "instance":   inst,
            "pair":       pair_name,
            "statistic":  round(stat_w, 4) if not np.isnan(stat_w) else "",
            "p_value":    round(p_raw, 6),
            "p_adjusted": round(p_adj, 6),
            "significant": str(p_adj < 0.05),
        })

    n_sig = sum(1 for r in wilcoxon_rows if r["significant"] == "True")
    print(f"  [{metric_label}] Wilcoxon: {n_sig}/{len(wilcoxon_rows)} pares significativos (p_adj<0.05)")

    return {
        "metric":          metric_name,
        "avg_ranks":       avg_ranks_global,
        "friedman_stat":   round(float(stat), 4),
        "friedman_p":      round(float(p_friedman), 6),
        "friedman_sig":    bool(sig),
        "cd":              round(float(cd), 4),
        "nemenyi":         nemenyi_results,
        "wilcoxon_rows":   wilcoxon_rows,
        "demsar_diagram":  diag_path,
    }


def step4_statistical_tests(experiment_dir: str) -> str:
    """
    Testes estatísticos (Demšar framework) usando metrics.csv.
      4a  Ranking por instância
      4b  Friedman global
      4c  Nemenyi CD + diagrama de Demšar
      4d  Wilcoxon pareado + Holm-Bonferroni
      4e  Repetição com IGD+

    Saídas:
      {experiment_dir}/friedman_results.json
      {experiment_dir}/wilcoxon_tests.csv
      {experiment_dir}/figures/demsar_hv.png
      {experiment_dir}/figures/demsar_igd_plus.png
    """
    _banner("PASSO 4 — TESTES ESTATÍSTICOS (DEMŠAR FRAMEWORK)")

    metrics_path = os.path.join(experiment_dir, "metrics.csv")
    if not os.path.exists(metrics_path):
        print("  ❌ metrics.csv não encontrado. Execute o Passo 3 primeiro.")
        sys.exit(1)

    with open(metrics_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    ok_rows = [r for r in rows if r["status"] == "ok"]
    print(f"  {len(ok_rows)} runs ok carregados")

    instances = sorted({r["instance"] for r in ok_rows})
    figures_dir = os.path.join(experiment_dir, "figures")
    os.makedirs(figures_dir, exist_ok=True)

    # ── 4a-4d: HV ─────────────────────────────────────────────────────────────
    res_hv  = _run_statistical_analysis("hv",       ok_rows, instances, figures_dir)
    # ── 4e: IGD+ ──────────────────────────────────────────────────────────────
    res_igd = _run_statistical_analysis("igd_plus", ok_rows, instances, figures_dir)

    # Concordância HV vs IGD+
    print("\n  Concordância de ranking HV × IGD+:")
    rank_hv  = sorted(res_hv["avg_ranks"],  key=res_hv["avg_ranks"].get)
    rank_igd = sorted(res_igd["avg_ranks"], key=res_igd["avg_ranks"].get)
    ALG_LABELS = {"nsga2": "NSGA-II", "smsemoa": "SMS-EMOA", "moead_ws": "MOEA/D"}
    for pos, (a_hv, a_igd) in enumerate(zip(rank_hv, rank_igd), 1):
        match = "✅" if a_hv == a_igd else "❌"
        print(f"    #{pos}: HV→{ALG_LABELS.get(a_hv, a_hv)}  IGD+→{ALG_LABELS.get(a_igd, a_igd)}  {match}")

    # ── Salva friedman_results.json ───────────────────────────────────────────
    friedman_path = os.path.join(experiment_dir, "friedman_results.json")
    friedman_out = {
        "hv":      {k: v for k, v in res_hv.items()  if k != "wilcoxon_rows"},
        "igd_plus": {k: v for k, v in res_igd.items() if k != "wilcoxon_rows"},
    }
    with open(friedman_path, "w", encoding="utf-8") as f:
        json.dump(friedman_out, f, indent=2)
    print(f"\n  ✅ friedman_results.json → {friedman_path}")

    # ── Salva wilcoxon_tests.csv ──────────────────────────────────────────────
    wilcoxon_path = os.path.join(experiment_dir, "wilcoxon_tests.csv")
    all_wilcoxon = res_hv["wilcoxon_rows"] + res_igd["wilcoxon_rows"]
    w_fields = ["metric", "instance", "pair", "statistic", "p_value", "p_adjusted", "significant"]
    with open(wilcoxon_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=w_fields)
        w.writeheader()
        w.writerows(all_wilcoxon)
    print(f"  ✅ wilcoxon_tests.csv    → {wilcoxon_path}")
    print(f"     {len(all_wilcoxon)} linhas ({len(res_hv['wilcoxon_rows'])} HV + "
          f"{len(res_igd['wilcoxon_rows'])} IGD+)")

    return friedman_path


# ─────────────────────────────────────────────────────────────────────────────
# Passo 5 — Análise por subgrupo
# ─────────────────────────────────────────────────────────────────────────────

def _instance_subgroup(instance: str) -> str:
    """Retorna o subgrupo de uma instância: C1, C2, R1, R2, RC1 ou RC2."""
    name = instance.lower()  # ex: 'c102_21'
    if name.startswith('rc'):
        prefix = 'RC'
        rest = name[2:]
    elif name.startswith('c'):
        prefix = 'C'
        rest = name[1:]
    elif name.startswith('r'):
        prefix = 'R'
        rest = name[1:]
    else:
        return 'UNKNOWN'
    regime = '1' if rest[0] == '1' else '2'
    return f"{prefix}{regime}"


def _friedman_nemenyi_subgroup(alg_hv_by_inst: dict, subgroup_insts: list,
                               metric_label: str) -> dict:
    """Friedman + Nemenyi para um subgrupo. Retorna dict com resultados."""
    from scipy.stats import friedmanchisquare
    k = len(ALGORITHMS)
    alg_ranks = defaultdict(list)
    for inst in subgroup_insts:
        if inst not in alg_hv_by_inst:
            continue
        medians = {a: np.median(v) for a, v in alg_hv_by_inst[inst].items() if v}
        if len(medians) < 2:
            continue
        sorted_algs = sorted(medians, key=medians.get, reverse=(metric_label == 'HV'))
        for rank_i, a in enumerate(sorted_algs, 1):
            alg_ranks[a].append(rank_i)

    avg_ranks = {a: float(np.mean(v)) for a, v in alg_ranks.items() if v}
    n = len(subgroup_insts)

    series = [np.array(alg_ranks[a]) for a in ALGORITHMS if a in alg_ranks]
    if len(series) >= 2 and all(len(s) >= 2 for s in series):
        stat, p = friedmanchisquare(*series)
    else:
        stat, p = float('nan'), 1.0

    q_alpha = 2.343
    cd = q_alpha * np.sqrt(k * (k + 1) / (6 * max(n, 1)))
    return {"avg_ranks": avg_ranks, "friedman_stat": round(float(stat), 4),
            "friedman_p": round(float(p), 6), "cd": round(float(cd), 4),
            "n_instances": n}


def step5_subgroup_analysis(experiment_dir: str) -> None:
    """
    Análise por subgrupo (C1/C2/R1/R2/RC1/RC2):
      - Friedman + Nemenyi por subgrupo (HV e IGD+)
      - Correlação de Spearman entre tw_ratio e delta_HV por par de algoritmos

    Pré-requisitos: merged_index.csv, metrics.csv
    Saídas:
      {experiment_dir}/subgroup_analysis.csv
      {experiment_dir}/spearman_correlations.csv
    """
    from scipy.stats import spearmanr
    _banner("PASSO 5 — ANÁLISE POR SUBGRUPO")

    metrics_path = os.path.join(experiment_dir, "metrics.csv")
    merged_path  = os.path.join(experiment_dir, "merged_index.csv")
    for p in [metrics_path, merged_path]:
        if not os.path.exists(p):
            print(f"  ❌ {os.path.basename(p)} não encontrado. Execute os passos anteriores.")
            sys.exit(1)

    with open(metrics_path, newline='', encoding='utf-8') as f:
        metric_rows = [r for r in csv.DictReader(f) if r['status'] == 'ok']
    with open(merged_path, newline='', encoding='utf-8') as f:
        index_rows = list(csv.DictReader(f))

    # ── Extrai tw_ratio: abre 1 pickle por instância ──────────────────────────
    print("  Extraindo tw_ratio (1 pickle por instância)...")
    by_inst_index = defaultdict(list)
    for r in index_rows:
        by_inst_index[r['instance']].append(r)

    tw_ratio_map = {}
    for inst, rows in by_inst_index.items():
        r = rows[0]
        m_id = int(r['_machine_id'])
        pkl_abs = _resolve_pkl(experiment_dir, m_id, r.get('pickle_path', ''))
        try:
            with open(pkl_abs, 'rb') as f:
                d = pickle.load(f)
            tw_ratio_map[inst] = float(d['instance_info']['tw_ratio'])
        except Exception:
            tw_ratio_map[inst] = float('nan')

    instances_all = sorted(tw_ratio_map.keys())
    subgroups_map = {inst: _instance_subgroup(inst) for inst in instances_all}
    SUBGROUPS = ['C1', 'C2', 'R1', 'R2', 'RC1', 'RC2']

    # ── Prepara HV e IGD+ por instância/algoritmo ─────────────────────────────
    hv_by_inst_alg   = defaultdict(lambda: defaultdict(list))
    igd_by_inst_alg  = defaultdict(lambda: defaultdict(list))
    for r in metric_rows:
        inst, alg = r['instance'], r['algorithm_id']
        hv_by_inst_alg[inst][alg].append(float(r['hv']))
        igd_val = float(r['igd_plus'])
        if not np.isnan(igd_val):
            igd_by_inst_alg[inst][alg].append(igd_val)

    # ── Friedman + Nemenyi por subgrupo ───────────────────────────────────────
    print(f"\n  {'Subgrupo':<6} {'n':>3}  {'Rank SMS':>9} {'Rank NS2':>9} {'Rank MOD':>9}  "
          f"{'F-χ²':>7}  {'p':>8}  {'CD':>6}  {'Sig':>4}")
    print(f"  {'-'*6} {'-'*3}  {'-'*9} {'-'*9} {'-'*9}  {'-'*7}  {'-'*8}  {'-'*6}  {'-'*4}")

    subgroup_rows = []
    ALG_SHORT = {'nsga2': 'NS2', 'smsemoa': 'SMS', 'moead_ws': 'MOD'}

    for sg in SUBGROUPS:
        sg_insts = [i for i in instances_all if subgroups_map[i] == sg]
        for metric_name, by_inst_alg, m_label in [
            ('hv',       hv_by_inst_alg,  'HV'),
            ('igd_plus',  igd_by_inst_alg, 'IGD+'),
        ]:
            res = _friedman_nemenyi_subgroup(by_inst_alg, sg_insts, m_label)
            ar  = res['avg_ranks']
            sig = res['friedman_p'] < 0.05

            rank_sms = ar.get('smsemoa', float('nan'))
            rank_ns2 = ar.get('nsga2',   float('nan'))
            rank_mod = ar.get('moead_ws',float('nan'))
            print(f"  {sg:<6} {res['n_instances']:>3}  "
                  f"{rank_sms:>9.3f} {rank_ns2:>9.3f} {rank_mod:>9.3f}  "
                  f"{res['friedman_stat']:>7.3f}  {res['friedman_p']:>8.4f}  "
                  f"{res['cd']:>6.4f}  {'✅' if sig else '❌'}"
                  f"  [{m_label}]")

            # Nemenyi pares
            for a, b in [('nsga2','smsemoa'),('nsga2','moead_ws'),('smsemoa','moead_ws')]:
                if a in ar and b in ar:
                    diff = abs(ar[a] - ar[b])
                    sig_pair = bool(diff > res['cd'])
                else:
                    diff, sig_pair = float('nan'), False

                # Wilcoxon pareado para o subgrupo
                from scipy.stats import wilcoxon as wilcoxon_test
                vals_a = [np.median(by_inst_alg[i].get(a,[])) for i in sg_insts
                          if by_inst_alg[i].get(a)]
                vals_b = [np.median(by_inst_alg[i].get(b,[])) for i in sg_insts
                          if by_inst_alg[i].get(b)]
                n_w = min(len(vals_a), len(vals_b))
                try:
                    if n_w >= 5:
                        _, p_w = wilcoxon_test(vals_a[:n_w], vals_b[:n_w])
                    else:
                        p_w = float('nan')
                except Exception:
                    p_w = float('nan')

                subgroup_rows.append({
                    'subgroup':        sg,
                    'metric':          metric_name,
                    'n_instances':     res['n_instances'],
                    'pair':            f'{a}_vs_{b}',
                    'rank_a':          round(ar.get(a, float('nan')), 4),
                    'rank_b':          round(ar.get(b, float('nan')), 4),
                    'rank_diff':       round(float(diff), 4),
                    'cd':              res['cd'],
                    'nemenyi_sig':     str(sig_pair),
                    'friedman_stat':   res['friedman_stat'],
                    'friedman_p':      res['friedman_p'],
                    'wilcoxon_p':      round(float(p_w), 6) if not np.isnan(p_w) else '',
                    'wilcoxon_sig':    str(p_w < 0.05) if not np.isnan(p_w) else '',
                })

    # ── Spearman: tw_ratio vs delta_HV por par ────────────────────────────────
    print(f"\n  Correlação de Spearman (tw_ratio × delta_HV mediano):")
    spearman_rows = []
    pairs_alg = [('nsga2','smsemoa'), ('nsga2','moead_ws'), ('smsemoa','moead_ws')]

    for a, b in pairs_alg:
        tw_vals, delta_vals = [], []
        for inst in instances_all:
            tw = tw_ratio_map.get(inst, float('nan'))
            hv_a = hv_by_inst_alg[inst].get(a, [])
            hv_b = hv_by_inst_alg[inst].get(b, [])
            if hv_a and hv_b and not np.isnan(tw):
                delta = np.median(hv_a) - np.median(hv_b)
                tw_vals.append(tw)
                delta_vals.append(delta)

        if len(tw_vals) >= 5:
            rho, p_sp = spearmanr(tw_vals, delta_vals)
        else:
            rho, p_sp = float('nan'), float('nan')

        sig_sp = not np.isnan(p_sp) and p_sp < 0.05
        print(f"    {a} vs {b}: ρ={rho:+.4f}  p={p_sp:.4f}  {'✅' if sig_sp else '❌'}")
        spearman_rows.append({
            'pair':      f'{a}_vs_{b}',
            'metric':    'hv_delta',
            'rho':       round(float(rho), 4) if not np.isnan(rho) else '',
            'p_value':   round(float(p_sp), 6) if not np.isnan(p_sp) else '',
            'significant': str(sig_sp),
            'n':         len(tw_vals),
        })

    # IGD+ delta (menor = melhor → delta = b - a, positivo = a melhor)
    print(f"\n  Correlação de Spearman (tw_ratio × delta_IGD+ mediano):")
    for a, b in pairs_alg:
        tw_vals, delta_vals = [], []
        for inst in instances_all:
            tw = tw_ratio_map.get(inst, float('nan'))
            igd_a = igd_by_inst_alg[inst].get(a, [])
            igd_b = igd_by_inst_alg[inst].get(b, [])
            if igd_a and igd_b and not np.isnan(tw):
                delta = np.median(igd_b) - np.median(igd_a)  # positivo = a melhor
                tw_vals.append(tw)
                delta_vals.append(delta)

        if len(tw_vals) >= 5:
            rho, p_sp = spearmanr(tw_vals, delta_vals)
        else:
            rho, p_sp = float('nan'), float('nan')

        sig_sp = not np.isnan(p_sp) and p_sp < 0.05
        print(f"    {a} vs {b}: ρ={rho:+.4f}  p={p_sp:.4f}  {'✅' if sig_sp else '❌'}")
        spearman_rows.append({
            'pair':      f'{a}_vs_{b}',
            'metric':    'igd_delta',
            'rho':       round(float(rho), 4) if not np.isnan(rho) else '',
            'p_value':   round(float(p_sp), 6) if not np.isnan(p_sp) else '',
            'significant': str(sig_sp),
            'n':         len(tw_vals),
        })

    # ── Salva outputs ─────────────────────────────────────────────────────────
    sg_path = os.path.join(experiment_dir, 'subgroup_analysis.csv')
    sg_fields = ['subgroup','metric','n_instances','pair','rank_a','rank_b',
                 'rank_diff','cd','nemenyi_sig','friedman_stat','friedman_p',
                 'wilcoxon_p','wilcoxon_sig']
    with open(sg_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=sg_fields)
        w.writeheader(); w.writerows(subgroup_rows)

    sp_path = os.path.join(experiment_dir, 'spearman_correlations.csv')
    sp_fields = ['pair','metric','rho','p_value','significant','n']
    with open(sp_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=sp_fields)
        w.writeheader(); w.writerows(spearman_rows)

    print(f"\n  ✅ subgroup_analysis.csv    → {sg_path}")
    print(f"  ✅ spearman_correlations.csv → {sp_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Passo 6 — Convergência
# ─────────────────────────────────────────────────────────────────────────────

def step6_convergence(experiment_dir: str, n_workers: int = 6) -> None:
    """
    Seleciona 6 instâncias representativas (uma por subgrupo, rank mediano em HV).
    Para cada instância abre 90 pickles, extrai convergence_history, recalcula
    HV por snapshot com ref_point global, e plota curvas de convergência.

    Saïdas: figures/convergence_{instance}.png
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from pymoo.indicators.hv import HV

    _banner("PASSO 6 — CONVERGÊNCIA")

    # ── Pré-requisitos ──────────────────────────────────────────────────────
    metrics_path = os.path.join(experiment_dir, "metrics.csv")
    merged_path  = os.path.join(experiment_dir, "merged_index.csv")
    ref_path     = os.path.join(experiment_dir, "ref_points.json")
    for p in [metrics_path, merged_path, ref_path]:
        if not os.path.exists(p):
            print(f"  ❌ {os.path.basename(p)} não encontrado.")
            sys.exit(1)

    with open(metrics_path,  newline='', encoding='utf-8') as f:
        metric_rows = [r for r in csv.DictReader(f) if r['status'] == 'ok']
    with open(merged_path,   newline='', encoding='utf-8') as f:
        index_rows = list(csv.DictReader(f))
    with open(ref_path, encoding='utf-8') as f:
        ref_points = json.load(f)

    figures_dir = os.path.join(experiment_dir, "figures")
    os.makedirs(figures_dir, exist_ok=True)

    # ── Seleciona 6 instâncias representativas (rank mediano em HV) ──────────
    # Para cada subgrupo: ordena instâncias pelo HV mediano global e pega a central
    SUBGROUPS = ['C1', 'C2', 'R1', 'R2', 'RC1', 'RC2']
    hv_med_by_inst = {}
    for r in metric_rows:
        inst = r['instance']
        if inst not in hv_med_by_inst:
            hv_med_by_inst[inst] = []
        hv_med_by_inst[inst].append(float(r['hv']))
    hv_med_by_inst = {k: float(np.median(v)) for k, v in hv_med_by_inst.items()}

    all_instances = sorted(hv_med_by_inst.keys())
    representative = {}  # subgroup -> instance
    for sg in SUBGROUPS:
        sg_insts = sorted(
            [i for i in all_instances if _instance_subgroup(i) == sg],
            key=lambda i: hv_med_by_inst.get(i, 0)
        )
        if sg_insts:
            representative[sg] = sg_insts[len(sg_insts) // 2]  # rank mediano

    print("  Instâncias representativas selecionadas:")
    for sg, inst in sorted(representative.items()):
        print(f"    {sg}: {inst}  (HV med={hv_med_by_inst[inst]:.2e})")

    # índice: (inst, alg, run_idx) -> row do merged_index
    idx_map = {}
    for r in index_rows:
        idx_map[(r['instance'], r['algorithm_id'], int(r['run_idx']))] = r

    ALG_COLORS = {'nsga2': '#2196F3', 'smsemoa': '#4CAF50', 'moead_ws': '#FF5722'}
    ALG_LABELS = {'nsga2': 'NSGA-II', 'smsemoa': 'SMS-EMOA', 'moead_ws': 'MOEA/D'}

    # ── Processa cada instância ───────────────────────────────────────────────
    for sg, inst in sorted(representative.items()):
        rp = ref_points.get(inst, {})
        ref_point_arr = np.array(rp['ref_point'])
        hv_indicator = HV(ref_point=ref_point_arr)

        print(f"\n  [{sg}] {inst} — abrindo pickles...", flush=True)

        # Para cada algoritmo: lista de arrays HV[85] (um por run)
        alg_hv_curves = {alg: [] for alg in ALGORITHMS}
        n_evals_grid = None

        for alg in ALGORITHMS:
            for run_idx in range(30):
                key = (inst, alg, run_idx)
                row = idx_map.get(key)
                if row is None:
                    continue
                m_id = int(row['_machine_id'])
                pkl_abs = _resolve_pkl(experiment_dir, m_id, row.get('pickle_path', ''))
                try:
                    with open(pkl_abs, 'rb') as f:
                        d = pickle.load(f)
                    ch = d.get('convergence_history', [])
                    if not ch:
                        continue

                    hv_curve = []
                    evals_arr = []
                    for snap in ch:
                        F_snap = snap['F_pareto']
                        if len(F_snap) > 0:
                            mask = np.all(F_snap < ref_point_arr, axis=1)
                            F_filt = F_snap[mask]
                            hv_val = float(hv_indicator(F_filt)) if len(F_filt) > 0 else 0.0
                        else:
                            hv_val = 0.0
                        hv_curve.append(hv_val)
                        evals_arr.append(snap['n_eval'])

                    alg_hv_curves[alg].append(hv_curve)
                    if n_evals_grid is None:
                        n_evals_grid = evals_arr
                except Exception:
                    continue

            n_runs = len(alg_hv_curves[alg])
            print(f"    {alg}: {n_runs} runs com convergência", flush=True)

        if n_evals_grid is None:
            print(f"    [AVISO] sem dados de convergência para {inst}")
            continue

        # ── Plota ─────────────────────────────────────────────────────────────
        x = np.array(n_evals_grid) / 1000  # em milhares

        fig, ax = plt.subplots(figsize=(15, 8.5))
        ax.set_facecolor('#f8f9fa')
        fig.patch.set_facecolor('white')

        for alg in ALGORITHMS:
            curves = alg_hv_curves[alg]
            if not curves:
                continue
            # Alinha tamanhos (pega o mínimo de snapshots entre as runs)
            min_len = min(len(c) for c in curves)
            mat = np.array([c[:min_len] for c in curves])
            x_alg = x[:min_len]

            med  = np.median(mat, axis=0)
            q25  = np.percentile(mat, 25, axis=0)
            q75  = np.percentile(mat, 75, axis=0)
            color = ALG_COLORS[alg]

            ax.plot(x_alg, med,   color=color, linewidth=3.5,   label=ALG_LABELS[alg], zorder=3)
            ax.fill_between(x_alg, q25, q75, color=color, alpha=0.20, zorder=2)

        ax.set_xlabel('Avaliações (×1000)', fontsize=26)
        ax.set_ylabel('HV mediano', fontsize=26)
        ax.set_title(f'Convergência de HV — {inst} (subgrupo {sg})', fontsize=28, fontweight='bold')
        ax.legend(fontsize=24, framealpha=0.9)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.ticklabel_format(axis='y', style='sci', scilimits=(0, 0))
        ax.tick_params(axis='both', labelsize=24)

        # Formata eixo X em valores redondos
        ax.set_xlim(x[0], x[-1])
        xticks = np.linspace(0, 850, 9)
        ax.set_xticks(xticks)
        ax.set_xticklabels([f'{int(v)}k' for v in xticks], fontsize=24)

        plt.tight_layout()
        out_path_png = os.path.join(figures_dir, f'convergence_{inst}.png')
        out_path_pdf = os.path.join(figures_dir, f'convergence_{inst}.pdf')
        plt.savefig(out_path_png, dpi=150, bbox_inches='tight', pad_inches=0.02)
        plt.savefig(out_path_pdf, bbox_inches='tight', pad_inches=0.02)
        plt.close()
        print(f"    ✅ figura salva → {out_path_png}")
        print(f"    ✅ figura salva → {out_path_pdf}")

    print(f"\n  ✅ {len(representative)} figuras de convergência salvas em {figures_dir}/ (PNG + PDF)")


# ─────────────────────────────────────────────────────────────────────────────
# Passo 7 — Propriedades estruturais das frentes
# ─────────────────────────────────────────────────────────────────────────────

def step7_structural_properties(experiment_dir: str) -> None:
    """
    Propriedades estruturais das frentes de Pareto:
      - Mediana de n_f1_layers e n_pareto por algoritmo/instância
      - Histogramas de distribuição por camada de f1 (6 instâncias representativas)
      - Vitórias por objetivo (melhor f1, f2, f3) por algoritmo

    Saídas:
      {experiment_dir}/structural_properties.csv
      {experiment_dir}/figures/f1_layers_boxplot.png
      {experiment_dir}/figures/best_per_objective.png
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _banner("PASSO 7 — PROPRIEDADES ESTRUTURAIS DAS FRENTES")

    # ── Pré-requisitos ──────────────────────────────────────────────────
    metrics_path = os.path.join(experiment_dir, "metrics.csv")
    merged_path  = os.path.join(experiment_dir, "merged_index.csv")
    if not os.path.exists(metrics_path) or not os.path.exists(merged_path):
        print("  ❌ metrics.csv ou merged_index.csv não encontrado.")
        sys.exit(1)

    with open(metrics_path, newline='', encoding='utf-8') as f:
        metric_rows = [r for r in csv.DictReader(f) if r['status'] == 'ok']
    with open(merged_path, newline='', encoding='utf-8') as f:
        index_rows = list(csv.DictReader(f))

    figures_dir = os.path.join(experiment_dir, "figures")
    os.makedirs(figures_dir, exist_ok=True)

    # ── Mediana de n_f1_layers e n_pareto por alg × instância ────────────────
    by_inst_alg = defaultdict(lambda: defaultdict(lambda: {'layers': [], 'pareto': []}))
    for r in metric_rows:
        d = by_inst_alg[r['instance']][r['algorithm_id']]
        d['layers'].append(int(r['n_f1_layers']))
        d['pareto'].append(int(r['n_pareto']))

    struct_rows = []
    instances = sorted(by_inst_alg.keys())
    for inst in instances:
        sg = _instance_subgroup(inst)
        for alg in ALGORITHMS:
            if alg not in by_inst_alg[inst]:
                continue
            d = by_inst_alg[inst][alg]
            struct_rows.append({
                'instance':       inst,
                'subgroup':       sg,
                'algorithm_id':   alg,
                'med_n_f1_layers': round(float(np.median(d['layers'])), 1),
                'med_n_pareto':    round(float(np.median(d['pareto'])), 1),
                'std_n_f1_layers': round(float(np.std(d['layers'])), 2),
                'std_n_pareto':    round(float(np.std(d['pareto'])), 2),
            })

    # Resumo global por algoritmo
    print("  Resumo global (mediana sobre as 50 instâncias):")
    print(f"  {'Algoritmo':<14} {'med n_layers':>12}  {'med n_pareto':>12}")
    for alg in ALGORITHMS:
        alg_rows = [r for r in struct_rows if r['algorithm_id'] == alg]
        med_layers = np.median([r['med_n_f1_layers'] for r in alg_rows])
        med_pareto = np.median([r['med_n_pareto']    for r in alg_rows])
        print(f"  {alg:<14} {med_layers:>12.1f}  {med_pareto:>12.1f}")

    # ── Boxplot: n_f1_layers por algoritmo ─────────────────────────────────
    ALG_COLORS = {'nsga2': '#2196F3', 'smsemoa': '#4CAF50', 'moead_ws': '#FF5722'}
    ALG_LABELS = {'nsga2': 'NSGA-II', 'smsemoa': 'SMS-EMOA', 'moead_ws': 'MOEA/D'}
    SUBGROUPS  = ['C1', 'C2', 'R1', 'R2', 'RC1', 'RC2']

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.patch.set_facecolor('white')

    for ax_i, (col, col_label) in enumerate([
        ('med_n_f1_layers', 'Nº camadas f1 (mediana por instância)'),
        ('med_n_pareto',    'Nº soluções Pareto (mediana por instância)'),
    ]):
        ax = axes[ax_i]
        ax.set_facecolor('#f8f9fa')
        data_by_alg = [
            [r[col] for r in struct_rows if r['algorithm_id'] == alg]
            for alg in ALGORITHMS
        ]
        bp = ax.boxplot(data_by_alg, patch_artist=True,
                        medianprops=dict(color='black', linewidth=2))
        for patch, alg in zip(bp['boxes'], ALGORITHMS):
            patch.set_facecolor(ALG_COLORS[alg])
            patch.set_alpha(0.7)
        ax.set_xticks(range(1, len(ALGORITHMS) + 1))
        ax.set_xticklabels([ALG_LABELS[a] for a in ALGORITHMS], fontsize=10)
        ax.set_ylabel(col_label, fontsize=10)
        ax.set_title(col_label, fontsize=11, fontweight='bold')
        ax.grid(True, alpha=0.3, linestyle='--', axis='y')

    plt.suptitle('Propriedades estruturais das frentes de Pareto', fontsize=12, y=1.01)
    plt.tight_layout()
    boxplot_path = os.path.join(figures_dir, 'f1_layers_boxplot.png')
    plt.savefig(boxplot_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"\n  ✅ f1_layers_boxplot.png → {boxplot_path}")

    # ── Vitórias por objetivo ──────────────────────────────────────────────
    # Para cada instância: qual algoritmo tem o menor f1/f2/f3 (best solutions)
    # Lemos diretamente dos pickles (pareto_front F) para cada instância
    # para obter o MELHOR f1/f2/f3 sobre todas as 30 runs do algoritmo.
    idx_by_inst_alg = defaultdict(lambda: defaultdict(list))
    for r in index_rows:
        idx_by_inst_alg[r['instance']][r['algorithm_id']].append(r)

    wins = {alg: {'f1': 0, 'f2': 0, 'f3': 0} for alg in ALGORITHMS}
    print("\n  Calculando vitórias por objetivo (abrindo pickles)...")

    for inst in instances:
        # Para cada algoritmo: melhor f1, f2, f3 sobre todas as 30 runs
        best_f = {alg: {'f1': np.inf, 'f2': np.inf, 'f3': np.inf}
                  for alg in ALGORITHMS}
        for alg in ALGORITHMS:
            for row in idx_by_inst_alg[inst].get(alg, []):
                m_id = int(row['_machine_id'])
                pkl_abs = _resolve_pkl(experiment_dir, m_id, row.get('pickle_path', ''))
                try:
                    with open(pkl_abs, 'rb') as f:
                        d = pickle.load(f)
                    F = d['pareto_front']['F']
                    if len(F) == 0:
                        continue
                    best_f[alg]['f1'] = min(best_f[alg]['f1'], float(F[:, 0].min()))
                    best_f[alg]['f2'] = min(best_f[alg]['f2'], float(F[:, 1].min()))
                    best_f[alg]['f3'] = min(best_f[alg]['f3'], float(F[:, 2].min()))
                except Exception:
                    continue

        for obj in ('f1', 'f2', 'f3'):
            best_val = min(best_f[a][obj] for a in ALGORITHMS if not np.isinf(best_f[a][obj]))
            winners  = [a for a in ALGORITHMS
                        if np.isfinite(best_f[a][obj]) and best_f[a][obj] == best_val]
            # Em caso de empate, conta para todos
            for a in winners:
                wins[a][obj] += 1

    print(f"\n  Vitórias por objetivo (sobre as 50 instâncias):")
    print(f"  {'Algoritmo':<14} {'Win f1 (veíc)':>13} {'Win f2 (dist)':>13} {'Win f3 (atraso)':>15}")
    for alg in ALGORITHMS:
        print(f"  {alg:<14} {wins[alg]['f1']:>13} {wins[alg]['f2']:>13} {wins[alg]['f3']:>15}")

    # Gráfico de vitórias
    fig, ax = plt.subplots(figsize=(13, 7))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('#f8f9fa')

    obj_labels = ['f1 (Nº veículos)', 'f2 (Distância)', 'f3 (Violação TW)']
    x_pos = np.arange(len(obj_labels))
    width = 0.25
    for i, alg in enumerate(ALGORITHMS):
        vals = [wins[alg]['f1'], wins[alg]['f2'], wins[alg]['f3']]
        bars = ax.bar(x_pos + (i - 1) * width, vals,
                      width=width, label=ALG_LABELS[alg],
                      color=ALG_COLORS[alg], alpha=0.85, edgecolor='white')
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, h + 0.3,
                        str(int(h)), ha='center', va='bottom', fontsize=16, fontweight='bold')

    ax.set_xticks(x_pos)
    ax.set_xticklabels(obj_labels, fontsize=20)
    ax.set_ylabel('Nº de vitórias (50 instâncias)', fontsize=20)
    ax.set_title('Vitórias por objetivo — melhor valor encontrado por algoritmo', fontsize=22, fontweight='bold')
    ax.legend(fontsize=18)
    ax.tick_params(axis='y', labelsize=18)
    ax.grid(True, alpha=0.3, axis='y', linestyle='--')
    ax.set_ylim(0, max(
        wins[a][o] for a in ALGORITHMS for o in ('f1','f2','f3')
    ) * 1.2 + 2)

    plt.tight_layout()
    wins_path = os.path.join(figures_dir, 'best_per_objective.png')
    wins_path_pdf = os.path.join(figures_dir, 'best_per_objective.pdf')
    plt.savefig(wins_path, dpi=150, bbox_inches='tight', pad_inches=0.02)
    plt.savefig(wins_path_pdf, bbox_inches='tight', pad_inches=0.02)
    plt.close()
    print(f"  ✅ best_per_objective.png → {wins_path}")
    print(f"  ✅ best_per_objective.pdf → {wins_path_pdf}")

    # ── Salva structural_properties.csv ────────────────────────────────────
    sp_path = os.path.join(experiment_dir, 'structural_properties.csv')
    sp_fields = ['instance','subgroup','algorithm_id',
                 'med_n_f1_layers','std_n_f1_layers','med_n_pareto','std_n_pareto']
    with open(sp_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=sp_fields)
        w.writeheader()
        w.writerows(struct_rows)
    print(f"  ✅ structural_properties.csv → {sp_path}")
    print(f"     {len(struct_rows)} linhas")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Análise pós-experimento — EVRPTW TCC",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--experiment-dir",
        default=os.path.join(ROOT, "results", "main_experiment"),
        help="Diretório raiz do experimento (default: results/main_experiment)",
    )

    step_group = ap.add_mutually_exclusive_group(required=True)
    step_group.add_argument(
        "--step", type=int, choices=[1, 2, 3, 4, 5, 6, 7],
        help="Passo a executar (1–7)",
    )
    step_group.add_argument(
        "--all", action="store_true",
        help="Executa todos os passos sequencialmente",
    )
    ap.add_argument(
        "--n-workers", type=int, default=8,
        help="Workers paralelos para os Passos 2 e 3 (default: 8)",
    )

    args = ap.parse_args()

    print(f"\n{'=' * 68}")
    print(f"  ANÁLISE EVRPTW TCC")
    print(f"{'=' * 68}")
    print(f"  Diretório: {args.experiment_dir}")
    print(f"  Workers  : {args.n_workers}")

    if args.step == 1 or args.all:
        step1_merge(args.experiment_dir)

    if args.step == 2 or args.all:
        step2_ref_points(args.experiment_dir, n_workers=args.n_workers)

    if args.step == 3 or args.all:
        step3_metrics(args.experiment_dir, n_workers=args.n_workers)

    if args.step == 4 or args.all:
        step4_statistical_tests(args.experiment_dir)

    if args.step == 5 or args.all:
        step5_subgroup_analysis(args.experiment_dir)

    if args.step == 6 or args.all:
        step6_convergence(args.experiment_dir, n_workers=args.n_workers)

    if args.step == 7 or args.all:
        step7_structural_properties(args.experiment_dir)


if __name__ == "__main__":
    main()
