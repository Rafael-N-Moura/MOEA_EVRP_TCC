#!/usr/bin/env python3
"""
analyze_metrics.py
==================
Análise pós-hoc das N runs geradas por stopping_criterion.py.

Carrega pickles existentes (sem reexecutar) e calcula múltiplas métricas:
  - HV         : Hipervolume (ref_point = 110% do max por instância)
  - IGD+       : Distância modificada à frente de referência empírica
  - n_pareto   : Número de soluções não-dominadas viáveis
  - n_f1_layers: Camadas distintas de f1 (veículos) na frente
  - best_f1/f2/f3: Melhor valor por objetivo
  - spacing_raw  : Schott (1995) com distância Euclidiana bruta
  - spacing_norm : Schott (1995) com objetivos normalizados pela amplitude
                   da frente de referência (invariante a escala)
  - spread_f{k}  : range de cada objetivo na frente
  - spread_total : soma dos três ranges

Decisões de implementação documentadas:
  [D1] Frente de referência: união de pareto_front["F"] de TODAS as runs
       (todos algoritmos e todos runs), filtrada para não-dominadas.
       Melhor aproximação da frente verdadeira disponível no budget.
       Prática padrão na literatura de comparação de MOEAs.

  [D2] ref_point: 110% do máximo componente-a-componente de todas as
       pareto fronts por instância. Consistente com stopping_criterion.py.

  [D3] IGD+: pymoo.indicators.igd_plus.IGDPlus (pymoo 0.6.x).
       IGD+ penaliza apenas soluções que não dominam as da frente de ref,
       sendo preferível ao IGD clássico para avaliação de Pareto fronts.

  [D4] Spacing (Schott 1995): std dev das distâncias ao vizinho mais
       próximo. Calculado TANTO em escala bruta (spacing_raw, informativo
       por instância) QUANTO normalizado pela amplitude da ref_front por
       objetivo (spacing_norm, permite comparação cross-instância).
       Escala bruta é padrão na literatura EVRPTW/VRP.

  [D5] n_f1_layers: valores únicos de np.round(F[:,0], 6). Como f1
       é número de veículos (inteiro), isso é equivalente a contar
       quantos tamanhos de frota distintos aparecem na frente.

  [D6] tw_ratio extraído de instance_info["tw_ratio"] de cada pickle;
       não codificado manualmente — é o valor real calculado no parser.

Uso:
  # Análise completa:
  python scripts/analyze_metrics.py \\
    --results-dir results/stopping_criterion_20260411_210157

  # Com gráficos matplotlib:
  python scripts/analyze_metrics.py \\
    --results-dir results/stopping_criterion_20260411_210157 --plots

  # Subconjunto (debug):
  python scripts/analyze_metrics.py \\
    --results-dir results/stopping_criterion_20260411_210157 \\
    --algorithms nsga2 smsemoa --instances c101_21 r101_21
"""

import os, sys, csv, json, glob, warnings, argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

warnings.filterwarnings("ignore")

ROOT = str(Path(__file__).parent.parent)
sys.path.insert(0, ROOT)
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np

from experiment_io import load_run, _non_dominated

# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_ALGORITHMS = ["moead_ws", "nsga2", "smsemoa"]
DEFAULT_INSTANCES  = ["c101_21", "c201_21", "r101_21", "r201_21",
                      "rc101_21", "rc201_21"]

# Classificação de instâncias para hipótese H2
INST_TYPE = {
    "c101_21":  "C",  "c201_21":  "C",
    "r101_21":  "R",  "r201_21":  "R",
    "rc101_21": "RC", "rc201_21": "RC",
}

SCALAR_METRICS = [
    "hv", "igd_plus", "n_pareto", "n_f1_layers",
    "best_f1", "best_f2", "best_f3",
    "spacing_raw", "spacing_norm",
    "spread_f1", "spread_f2", "spread_f3", "spread_total",
]


# ─────────────────────────────────────────────────────────────────────────────
# Seção 1 — Carregamento dos pickles
# ─────────────────────────────────────────────────────────────────────────────

def load_all_runs(pickles_dir: str, algorithms: list, instances: list) -> dict:
    """
    Lê todos os pickles de pickles_dir/{alg}/{inst}/run*.pkl.
    Retorna: data[(alg, inst, run_idx)] = run_dict
    """
    data = {}
    errors = 0

    for alg in algorithms:
        for inst in instances:
            inst_dir = os.path.join(pickles_dir, alg, inst)
            if not os.path.isdir(inst_dir):
                print(f"  [AVISO] Não encontrado: {inst_dir}")
                continue
            pkl_files = sorted(glob.glob(os.path.join(inst_dir, "run*.pkl")))
            for pkl_path in pkl_files:
                try:
                    run = load_run(pkl_path)
                    key = (alg, inst, run["metadata"]["run_idx"])
                    data[key] = run
                except Exception as e:
                    print(f"  [ERRO] {pkl_path}: {e}")
                    errors += 1

    print(f"  Carregados: {len(data)} runs  (erros: {errors})")
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Seção 2 — Frentes de referência empíricas
# ─────────────────────────────────────────────────────────────────────────────

def build_ref_fronts(data: dict, instances: list) -> tuple:
    """
    [D1] Para cada instância, une todas as pareto_front["F"] de todos os
    algoritmos e runs, aplica non-dominated filtering e retorna a frente
    de referência empírica.
    [D2] ref_point = 110% do máximo componente-a-componente.

    Retorna:
        ref_fronts[inst] : np.ndarray (n_nd, 3)
        ref_points[inst] : np.ndarray (3,)
    """
    ref_fronts = {}
    ref_points = {}

    for inst in instances:
        all_F = []
        for (alg, i, _), run in data.items():
            if i != inst:
                continue
            F_p = run["pareto_front"]["F"]
            if len(F_p) > 0:
                all_F.append(F_p)

        if not all_F:
            print(f"  [AVISO] Sem frentes para {inst}")
            continue

        combined  = np.vstack(all_F)
        ref_point = combined.max(axis=0) * 1.1   # [D2]
        ref_nd    = _non_dominated(combined)       # [D1]

        ref_fronts[inst] = ref_nd
        ref_points[inst] = ref_point
        print(f"  {inst}: ref_front={len(ref_nd)} sols  "
              f"ref_point=[{', '.join(f'{v:.1f}' for v in ref_point)}]")

    return ref_fronts, ref_points


# ─────────────────────────────────────────────────────────────────────────────
# Seção 3 — Funções de métricas
# ─────────────────────────────────────────────────────────────────────────────

def _compute_hv(F: np.ndarray, ref_point: np.ndarray) -> float:
    from pymoo.indicators.hv import HV
    if len(F) == 0:
        return 0.0
    mask  = np.all(F < ref_point, axis=1)
    F_dom = F[mask]
    if len(F_dom) == 0:
        return 0.0
    try:
        return float(HV(ref_point=ref_point)(F_dom))
    except Exception:
        return 0.0


def _compute_igd_plus(F_approx: np.ndarray, F_ref: np.ndarray) -> float:
    """[D3] IGD+ preferido ao IGD: penaliza soluções dominadas pela ref."""
    if len(F_approx) == 0 or len(F_ref) == 0:
        return float("nan")
    try:
        from pymoo.indicators.igd_plus import IGDPlus
        return float(IGDPlus(F_ref)(F_approx))
    except ImportError:
        try:
            from pymoo.indicators.igd import IGD
            return float(IGD(F_ref)(F_approx))
        except Exception:
            return float("nan")
    except Exception:
        return float("nan")


def _nn_distances(F: np.ndarray) -> np.ndarray:
    """Distância euclidiana ao vizinho mais próximo para cada solução."""
    n = len(F)
    dists = np.full(n, np.inf)
    for i in range(n):
        diff = F - F[i]
        d    = np.sqrt((diff ** 2).sum(axis=1))
        d[i] = np.inf   # ignora self
        dists[i] = d.min()
    return dists


def _spacing(F: np.ndarray) -> float:
    """
    [D4] Spacing de Schott (1995).
    S = sqrt( sum_i (d_bar - d_i)^2 / (n-1) )
    onde d_i é a distância euclidiana ao vizinho mais próximo.
    """
    if len(F) < 2:
        return float("nan")
    dists = _nn_distances(F)
    d_bar = dists.mean()
    return float(np.sqrt(np.sum((d_bar - dists) ** 2) / (len(F) - 1)))


def _compute_spacing_raw(F: np.ndarray) -> float:
    """Spacing em escala bruta — comparação intra-instância."""
    return _spacing(F)


def _compute_spacing_norm(F: np.ndarray, ref_range: np.ndarray) -> float:
    """
    [D4] Spacing normalizado — divide cada objetivo pelo range da
    frente de referência. Permite comparação cross-instância.
    """
    if len(F) < 2:
        return float("nan")
    safe = np.where(ref_range > 0, ref_range, 1.0)
    return _spacing(F / safe)


def _compute_spread(F: np.ndarray) -> dict:
    """Range de cada objetivo e soma total."""
    if len(F) == 0:
        return {"f1": 0.0, "f2": 0.0, "f3": 0.0, "total": 0.0}
    ext = F.max(axis=0) - F.min(axis=0)
    return {"f1": float(ext[0]), "f2": float(ext[1]),
            "f3": float(ext[2]), "total": float(ext.sum())}


def _compute_n_f1_layers(F: np.ndarray) -> int:
    """[D5] Número de valores únicos de f1 (número de veículos)."""
    if len(F) == 0:
        return 0
    return int(len(np.unique(np.round(F[:, 0], 6))))


def _compute_layer_distribution(F: np.ndarray) -> dict:
    """Para cada valor de f1, quantas soluções existem."""
    if len(F) == 0:
        return {}
    vals, counts = np.unique(np.round(F[:, 0], 6), return_counts=True)
    return {int(v): int(c) for v, c in zip(vals, counts)}


def compute_all_metrics(run: dict, ref_front: np.ndarray,
                        ref_point: np.ndarray,
                        ref_range: np.ndarray) -> dict:
    """Calcula todas as métricas para um único run."""
    F_p = run["pareto_front"]["F"]

    hv      = _compute_hv(F_p, ref_point)
    igdp    = _compute_igd_plus(F_p, ref_front)
    n_nd    = len(F_p)
    n_lay   = _compute_n_f1_layers(F_p)
    lay_d   = _compute_layer_distribution(F_p)
    spread  = _compute_spread(F_p)
    sp_raw  = _compute_spacing_raw(F_p)
    sp_norm = _compute_spacing_norm(F_p, ref_range)

    best_f1 = float(F_p[:, 0].min()) if n_nd > 0 else float("nan")
    best_f2 = float(F_p[:, 1].min()) if n_nd > 0 else float("nan")
    best_f3 = float(F_p[:, 2].min()) if n_nd > 0 else float("nan")

    return {
        "hv":           hv,
        "igd_plus":     igdp,
        "n_pareto":     n_nd,
        "n_f1_layers":  n_lay,
        "layer_dist":   lay_d,    # dict — só para JSON
        "best_f1":      best_f1,
        "best_f2":      best_f2,
        "best_f3":      best_f3,
        "spacing_raw":  sp_raw,
        "spacing_norm": sp_norm,
        "spread_f1":    spread["f1"],
        "spread_f2":    spread["f2"],
        "spread_f3":    spread["f3"],
        "spread_total": spread["total"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Seção 4 — Agregação
# ─────────────────────────────────────────────────────────────────────────────

def aggregate(all_metrics: dict, algorithms: list, instances: list) -> dict:
    """
    Agrega métricas escalares: mediana, IQR, média, std, CV.
    Retorna agg[(alg, inst)] = dict
    """
    agg = {}

    for alg in algorithms:
        for inst in instances:
            run_keys = sorted(k for k in all_metrics if k[0] == alg and k[1] == inst)
            if not run_keys:
                continue

            runs_m = [all_metrics[k] for k in run_keys]
            row    = {"n_runs": len(runs_m)}

            for m in SCALAR_METRICS:
                vals = np.array([rm[m] for rm in runs_m
                                 if not np.isnan(float(rm.get(m, float("nan"))))])
                if len(vals) == 0:
                    for suf in ("median", "iqr", "mean", "std", "cv"):
                        row[f"{m}_{suf}"] = float("nan")
                    continue

                q25, q75 = np.percentile(vals, [25, 75])
                mean_v   = float(np.mean(vals))
                std_v    = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
                row[f"{m}_median"] = float(np.median(vals))
                row[f"{m}_iqr"]    = float(q75 - q25)
                row[f"{m}_mean"]   = mean_v
                row[f"{m}_std"]    = std_v
                row[f"{m}_cv"]     = (std_v / mean_v) if mean_v != 0 else float("nan")

            agg[(alg, inst)] = row

    return agg


# ─────────────────────────────────────────────────────────────────────────────
# Seção 5 — Verificação de hipóteses
# ─────────────────────────────────────────────────────────────────────────────

def _get(agg, alg, inst, metric):
    return agg.get((alg, inst), {}).get(f"{metric}_median", float("nan"))


def verify_hypotheses(agg: dict, data: dict, algorithms: list,
                      instances: list) -> dict:
    res = {}

    # ── H1: SMS-EMOA HV > NSGA-II em quantas instâncias? ────────────────────
    h1 = []
    for inst in instances:
        sms  = _get(agg, "smsemoa",  inst, "hv")
        nsga = _get(agg, "nsga2",    inst, "hv")
        h1.append({"inst": inst, "smsemoa": sms, "nsga2": nsga,
                   "wins": sms > nsga})
    res["H1"] = {
        "description": "SMS-EMOA HV mediano > NSGA-II HV mediano",
        "count":       sum(r["wins"] for r in h1),
        "total":       len(h1),
        "details":     h1,
    }

    # ── Hnova: SMS-EMOA mais camadas de f1? ──────────────────────────────────
    hnova = []
    for inst in instances:
        sms  = _get(agg, "smsemoa",  inst, "n_f1_layers")
        nsga = _get(agg, "nsga2",    inst, "n_f1_layers")
        moe  = _get(agg, "moead_ws", inst, "n_f1_layers")
        hnova.append({"inst": inst, "smsemoa": sms, "nsga2": nsga, "moead_ws": moe,
                      "wins": (sms > nsga) and (sms > moe)})
    res["Hnova"] = {
        "description": "SMS-EMOA n_f1_layers > NSGA-II e > MOEA/D-WS",
        "count":       sum(r["wins"] for r in hnova),
        "total":       len(hnova),
        "details":     hnova,
    }

    # ── Hdelay: MOEA/D-WS best_f3 < ambos? ──────────────────────────────────
    hdelay = []
    for inst in instances:
        moe  = _get(agg, "moead_ws", inst, "best_f3")
        nsga = _get(agg, "nsga2",    inst, "best_f3")
        sms  = _get(agg, "smsemoa",  inst, "best_f3")
        hdelay.append({"inst": inst, "moead_ws": moe, "nsga2": nsga, "smsemoa": sms,
                       "wins": (moe < nsga) and (moe < sms)})
    res["Hdelay"] = {
        "description": "MOEA/D-WS best_f3 mediano < NSGA-II e < SMS-EMOA",
        "count":       sum(r["wins"] for r in hdelay),
        "total":       len(hdelay),
        "details":     hdelay,
    }

    # ── H2: razão HV_moead / HV_smsemoa maior em C que em R? ────────────────
    ratios = {}
    for inst in instances:
        moe = _get(agg, "moead_ws", inst, "hv")
        sms = _get(agg, "smsemoa",  inst, "hv")
        if sms > 0 and not np.isnan(moe):
            ratios[inst] = moe / sms

    def _mean_by_type(t):
        vals = [v for k, v in ratios.items() if INST_TYPE.get(k) == t]
        return float(np.mean(vals)) if vals else float("nan")

    mean_C  = _mean_by_type("C")
    mean_R  = _mean_by_type("R")
    mean_RC = _mean_by_type("RC")

    res["H2"] = {
        "description": "MOEA/D-WS HV / SMS-EMOA HV: razão média em C > R?",
        "ratios":      ratios,
        "mean_C":      mean_C,
        "mean_R":      mean_R,
        "mean_RC":     mean_RC,
        "supported":   (mean_C > mean_R) if not np.isnan(mean_C + mean_R) else None,
    }

    # ── H3: tendência com tw_ratio ────────────────────────────────────────────
    # [D6] tw_ratio extraído do pickle; ranqueia MOEA/D-WS por HV
    tw_data = []
    for inst in instances:
        # Pega tw_ratio do primeiro run disponível
        tw = float("nan")
        for (alg, i, _), run in data.items():
            if i == inst:
                tw = run["instance_info"].get("tw_ratio", float("nan"))
                break
        moe_hv  = _get(agg, "moead_ws", inst, "hv")
        sms_hv  = _get(agg, "smsemoa",  inst, "hv")
        nsga_hv = _get(agg, "nsga2",    inst, "hv")
        rank_moe = sum(1 for h in [sms_hv, nsga_hv] if h > moe_hv) + 1
        tw_data.append({"inst": inst, "tw_ratio": tw, "moead_ws_hv": moe_hv,
                        "rank_moead_ws": rank_moe})
    tw_data.sort(key=lambda x: x["tw_ratio"])
    res["H3"] = {
        "description": "Tendência MOEA/D-WS rank vs tw_ratio (Spearman não aplicável n=6)",
        "details":     tw_data,
    }

    # ── Hrobustez: MOEA/D-WS tem maior CV de HV? ─────────────────────────────
    cv_by_alg = {}
    for alg in algorithms:
        cvs   = [agg.get((alg, inst), {}).get("hv_cv", float("nan"))
                 for inst in instances]
        valid = [v for v in cvs if not np.isnan(v)]
        cv_by_alg[alg] = float(np.mean(valid)) if valid else float("nan")

    max_cv_alg = max(
        (a for a in algorithms if not np.isnan(cv_by_alg.get(a, float("nan")))),
        key=lambda a: cv_by_alg[a],
        default=None
    )
    res["Hrobustez"] = {
        "description":    "MOEA/D-WS tem maior CV de HV (std/mean) que os demais",
        "mean_cv_by_alg": cv_by_alg,
        "max_cv_alg":     max_cv_alg,
        "supported":      max_cv_alg == "moead_ws",
    }

    return res


# ─────────────────────────────────────────────────────────────────────────────
# Seção 6 — Outputs
# ─────────────────────────────────────────────────────────────────────────────

def save_metrics_csv(agg: dict, algorithms: list, instances: list, path: str):
    """CSV consolidado: 1 linha por (alg, inst), colunas para cada métrica."""
    stat_cols = [f"{m}_{s}" for m in SCALAR_METRICS
                 for s in ("median", "iqr", "mean", "std", "cv")]
    fieldnames = ["algorithm_id", "instance", "n_runs"] + stat_cols

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for alg in algorithms:
            for inst in instances:
                row = agg.get((alg, inst), {})
                if not row:
                    continue
                line = {"algorithm_id": alg, "instance": inst}
                line.update(row)
                w.writerow(line)
    print(f"  metrics_summary.csv → {path}")


def save_convergence_curves(data: dict, ref_points: dict,
                             algorithms: list, instances: list, out_dir: str):
    """
    Para cada (alg, inst): mediana de HV por snapshot ao longo do tempo.
    Salva em convergence_curves/{alg}_{inst}.json
    (formato compatível com stopping_criterion.py)
    """
    from pymoo.indicators.hv import HV

    os.makedirs(out_dir, exist_ok=True)

    for alg in algorithms:
        for inst in instances:
            ref = ref_points.get(inst)
            if ref is None:
                continue

            curves = []
            for (a, i, _), run in data.items():
                if a != alg or i != inst:
                    continue
                hist = run.get("convergence_history", [])
                if not hist:
                    continue
                evals = [s["n_eval"] for s in hist]
                hvs   = []
                for s in hist:
                    F_p  = s["F_pareto"]
                    mask = np.all(F_p < ref, axis=1) if len(F_p) else np.array([], dtype=bool)
                    F_dom = F_p[mask] if len(F_p) else F_p
                    try:
                        hv_v = float(HV(ref_point=ref)(F_dom)) if len(F_dom) > 0 else 0.0
                    except Exception:
                        hv_v = 0.0
                    hvs.append(hv_v)
                curves.append((evals, hvs))

            if not curves:
                continue

            # Alinha pelo comprimento mínimo
            min_len   = min(len(c[0]) for c in curves)
            eval_pts  = curves[0][0][:min_len]
            hv_matrix = np.array([c[1][:min_len] for c in curves])
            med_hv    = np.median(hv_matrix, axis=0).tolist()

            path = os.path.join(out_dir, f"{alg}_{inst}.json")
            with open(path, "w") as jf:
                json.dump({"algorithm_id": alg, "instance": inst,
                           "eval_points": eval_pts, "hv_median": med_hv,
                           "n_runs": len(curves),
                           "ref_point": ref.tolist()}, jf)

    print(f"  convergence_curves/ → {out_dir}")


def _fmt(v, fmt=".2f"):
    if isinstance(v, float) and np.isnan(v):
        return "nan"
    try:
        return format(v, fmt)
    except Exception:
        return str(v)


def save_report(agg: dict, hyp: dict, algorithms: list, instances: list,
                path: str):
    """Relatório Markdown completo com todas as tabelas e verificação de hipóteses."""
    ts = datetime.now().isoformat(timespec="seconds")

    def md_table_row(cells):
        return "| " + " | ".join(str(c) for c in cells) + " |"

    def winner_row(inst, metric, prefer_min=False):
        """Retorna (dict linha, alg vencedor)."""
        vals = {alg: _get(agg, alg, inst, metric) for alg in algorithms}
        valid = {a: v for a, v in vals.items() if not np.isnan(v)}
        if not valid:
            win = "—"
        elif prefer_min:
            win = min(valid, key=valid.get)
        else:
            win = max(valid, key=valid.get)
        return vals, win

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Relatório de Análise de Métricas Pós-Hoc\n\n")
        f.write(f"**Gerado em**: {ts}\n\n")
        f.write(f"**Algoritmos**: {', '.join(algorithms)}\n\n")
        f.write(f"**Instâncias**: {', '.join(instances)}\n\n")

        # ── Decisões metodológicas ────────────────────────────────────────────
        f.write("## Decisões Metodológicas\n\n")
        f.write("| Decisão | Opção escolhida | Justificativa |\n")
        f.write("|---------|-----------------|---------------|\n")
        f.write("| Frente de referência | União não-dominada de TODAS as runs | "
                "Prática padrão — melhor aprox. da frente verdadeira no budget |\n")
        f.write("| Ref point | 110% do max por instância | "
                "Consistente com stopping_criterion.py |\n")
        f.write("| IGD+ vs IGD | IGDPlus (pymoo 0.6) | "
                "IGD+ penaliza soluções dominadas pela referência |\n")
        f.write("| Spacing | Schott (1995) Euclidiana | "
                "raw: intra-inst; norm: cross-inst (÷ range ref_front) |\n")
        f.write("| n_f1_layers | unique(round(F[:,0],6)) | "
                "f1=n_veículos é inteiro; conta frotas distintas |\n")
        f.write("| tw_ratio | Extraído de instance_info do pickle | "
                "Evita hardcoding; usa valor real do parser |\n\n")

        # ── Seção HV ─────────────────────────────────────────────────────────
        f.write("## HV Mediano (+ IQR)\n\n")
        f.write(md_table_row(["Instância"] +
                              [f"{a} med (IQR)" for a in algorithms] +
                              ["Vencedor"]) + "\n")
        f.write(md_table_row(["---"] * (len(algorithms) + 2)) + "\n")
        wins_hv = {a: 0 for a in algorithms}

        for inst in instances:
            vals, win = winner_row(inst, "hv", prefer_min=False)
            iqrs = {a: agg.get((a, inst), {}).get("hv_iqr", float("nan"))
                    for a in algorithms}
            wins_hv[win] = wins_hv.get(win, 0) + 1
            cells = [inst] + [f"{_fmt(vals[a], '.0f')} ({_fmt(iqrs[a], '.0f')})"
                               for a in algorithms] + [win]
            f.write(md_table_row(cells) + "\n")

        f.write(f"\n**Vitórias**: "
                + ", ".join(f"{a}={wins_hv.get(a,0)}" for a in algorithms) + "\n\n")

        # ── IGD+ ─────────────────────────────────────────────────────────────
        f.write("## IGD+ Mediano (+ IQR)\n\n")
        f.write("> Menor é melhor. IGD+ mede proximidade à frente de referência empírica.\n\n")
        f.write(md_table_row(["Instância"] +
                              [f"{a} med (IQR)" for a in algorithms] +
                              ["Vencedor"]) + "\n")
        f.write(md_table_row(["---"] * (len(algorithms) + 2)) + "\n")
        wins_igd = {a: 0 for a in algorithms}

        for inst in instances:
            vals, win = winner_row(inst, "igd_plus", prefer_min=True)
            iqrs = {a: agg.get((a, inst), {}).get("igd_plus_iqr", float("nan"))
                    for a in algorithms}
            wins_igd[win] = wins_igd.get(win, 0) + 1
            cells = [inst] + [f"{_fmt(vals[a])} ({_fmt(iqrs[a])})"
                               for a in algorithms] + [win]
            f.write(md_table_row(cells) + "\n")

        f.write(f"\n**Vitórias**: "
                + ", ".join(f"{a}={wins_igd.get(a,0)}" for a in algorithms) + "\n\n")

        # ── n_f1_layers ───────────────────────────────────────────────────────
        f.write("## Camadas Distintas de f1 (n_f1_layers)\n\n")
        f.write("> Número de frotas distintas na frente de Pareto. Maior = maior cobertura.\n\n")
        f.write(md_table_row(["Instância"] + algorithms + ["Vencedor"]) + "\n")
        f.write(md_table_row(["---"] * (len(algorithms) + 2)) + "\n")

        for inst in instances:
            vals, win = winner_row(inst, "n_f1_layers", prefer_min=False)
            f.write(md_table_row([inst] + [_fmt(vals[a], ".1f") for a in algorithms]
                                  + [win]) + "\n")
        f.write("\n")

        # ── best_f3 ───────────────────────────────────────────────────────────
        f.write("## Best f3 (atraso total mínimo)\n\n")
        f.write("> Menor é melhor. Verifica hipótese Hdelay: MOEA/D-WS encontra menor f3?\n\n")
        f.write(md_table_row(["Instância"] + algorithms + ["Vencedor (min)"]) + "\n")
        f.write(md_table_row(["---"] * (len(algorithms) + 2)) + "\n")

        for inst in instances:
            vals, win = winner_row(inst, "best_f3", prefer_min=True)
            f.write(md_table_row([inst] + [_fmt(vals[a]) for a in algorithms]
                                  + [win]) + "\n")
        f.write("\n")

        # ── Spacing normalizado ───────────────────────────────────────────────
        f.write("## Spacing Normalizado (Schott 1995)\n\n")
        f.write("> Menor = distribuição mais uniforme. Normalizado pela amplitude "
                "da ref_front (cross-instância comparável).\n\n")
        f.write(md_table_row(["Instância"] + algorithms + ["Melhor (min)"]) + "\n")
        f.write(md_table_row(["---"] * (len(algorithms) + 2)) + "\n")

        for inst in instances:
            vals, win = winner_row(inst, "spacing_norm", prefer_min=True)
            f.write(md_table_row([inst] + [_fmt(vals[a]) for a in algorithms]
                                  + [win]) + "\n")
        f.write("\n")

        # ── Spread total ──────────────────────────────────────────────────────
        f.write("## Spread Total (Amplitude da Frente)\n\n")
        f.write("> Maior = frente cobre mais do espaço de objetivos.\n\n")
        f.write(md_table_row(["Instância"] + algorithms + ["Vencedor"]) + "\n")
        f.write(md_table_row(["---"] * (len(algorithms) + 2)) + "\n")

        for inst in instances:
            vals, win = winner_row(inst, "spread_total", prefer_min=False)
            f.write(md_table_row([inst] + [_fmt(vals[a], ".0f") for a in algorithms]
                                  + [win]) + "\n")
        f.write("\n")

        # ── Verificação de hipóteses ──────────────────────────────────────────
        f.write("## Verificação das Hipóteses\n\n")

        def write_hyp(name):
            h    = hyp[name]
            cnt  = h.get("count", "?")
            tot  = h.get("total", "?")
            desc = h.get("description", "")
            sup  = "✅ suportada" if cnt >= (tot // 2 + 1) else "❌ não suportada"
            f.write(f"### {name}: {desc}\n\n")
            f.write(f"**Resultado**: {cnt}/{tot} instâncias — {sup}\n\n")

        write_hyp("H1")
        # Tabela detalhe H1
        f.write(md_table_row(["Instância", "SMS-EMOA HV", "NSGA-II HV", "SMS-EMOA vence?"]) + "\n")
        f.write(md_table_row(["---", "---", "---", "---"]) + "\n")
        for r in hyp["H1"]["details"]:
            f.write(md_table_row([r["inst"], _fmt(r["smsemoa"], ".0f"),
                                   _fmt(r["nsga2"], ".0f"),
                                   "✅" if r["wins"] else "❌"]) + "\n")
        f.write("\n")

        write_hyp("Hnova")
        f.write(md_table_row(["Instância", "SMS-EMOA", "NSGA-II", "MOEA/D-WS", "SMS vence?"]) + "\n")
        f.write(md_table_row(["---"] * 5) + "\n")
        for r in hyp["Hnova"]["details"]:
            f.write(md_table_row([r["inst"],
                                   _fmt(r["smsemoa"], ".1f"), _fmt(r["nsga2"], ".1f"),
                                   _fmt(r["moead_ws"], ".1f"),
                                   "✅" if r["wins"] else "❌"]) + "\n")
        f.write("\n")

        write_hyp("Hdelay")
        f.write(md_table_row(["Instância", "MOEA/D-WS f3", "NSGA-II f3", "SMS-EMOA f3",
                               "MOEA/D vence?"]) + "\n")
        f.write(md_table_row(["---"] * 5) + "\n")
        for r in hyp["Hdelay"]["details"]:
            f.write(md_table_row([r["inst"],
                                   _fmt(r["moead_ws"]), _fmt(r["nsga2"]),
                                   _fmt(r["smsemoa"]),
                                   "✅" if r["wins"] else "❌"]) + "\n")
        f.write("\n")

        # H2
        h2   = hyp["H2"]
        sup2 = "✅ suportada" if h2.get("supported") else "❌ não suportada"
        f.write(f"### H2: {h2['description']}\n\n")
        f.write(f"**Resultado**: razão média C={_fmt(h2['mean_C'])}, "
                f"R={_fmt(h2['mean_R'])}, RC={_fmt(h2['mean_RC'])} — {sup2}\n\n")
        f.write(md_table_row(["Instância", "Tipo", "Razão MOEA/D÷SMS-EMOA"]) + "\n")
        f.write(md_table_row(["---", "---", "---"]) + "\n")
        for inst, ratio in sorted(h2["ratios"].items()):
            f.write(md_table_row([inst, INST_TYPE.get(inst, "?"), _fmt(ratio)]) + "\n")
        f.write("\n")

        # H3
        h3 = hyp["H3"]
        f.write(f"### H3: {h3['description']}\n\n")
        f.write(md_table_row(["Instância", "tw_ratio", "MOEA/D-WS HV", "Rank MOEA/D-WS"]) + "\n")
        f.write(md_table_row(["---"] * 4) + "\n")
        for r in h3["details"]:
            f.write(md_table_row([r["inst"], _fmt(r["tw_ratio"], ".4f"),
                                   _fmt(r["moead_ws_hv"], ".0f"),
                                   f"{r['rank_moead_ws']}/3"]) + "\n")
        f.write("\n")

        # Hrobustez
        hr  = hyp["Hrobustez"]
        sup = "✅ suportada" if hr["supported"] else "❌ não suportada"
        f.write(f"### Hrobustez: {hr['description']}\n\n")
        f.write(f"**Resultado**: {sup}  (alg. com maior CV: **{hr['max_cv_alg']}**)\n\n")
        f.write(md_table_row(["Algoritmo", "CV médio de HV (std/mean)"]) + "\n")
        f.write(md_table_row(["---", "---"]) + "\n")
        for alg, cv in hr["mean_cv_by_alg"].items():
            f.write(md_table_row([alg, _fmt(cv, ".4f")]) + "\n")
        f.write("\n")

    print(f"  metrics_report.md   → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Plots opcionais
# ─────────────────────────────────────────────────────────────────────────────

def generate_plots(curves_dir: str, algorithms: list, instances: list,
                   plots_dir: str):
    try:
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors
    except ImportError:
        print("  [AVISO] matplotlib não disponível — plots pulados")
        return

    os.makedirs(plots_dir, exist_ok=True)
    colors = {"moead_ws": "#e07b39", "nsga2": "#4477aa", "smsemoa": "#228833"}
    labels = {"moead_ws": "MOEA/D-WS", "nsga2": "NSGA-II", "smsemoa": "SMS-EMOA"}

    for inst in instances:
        fig, ax = plt.subplots(figsize=(9, 5))
        for alg in algorithms:
            jpath = os.path.join(curves_dir, f"{alg}_{inst}.json")
            if not os.path.exists(jpath):
                continue
            with open(jpath) as jf:
                c = json.load(jf)
            ax.plot(c["eval_points"], c["hv_median"],
                    color=colors.get(alg, "gray"),
                    label=labels.get(alg, alg), linewidth=2)

        ax.set_title(f"Convergência de HV — {inst}", fontsize=13)
        ax.set_xlabel("Avaliações")
        ax.set_ylabel("HV mediano")
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        out = os.path.join(plots_dir, f"convergence_{inst}.png")
        fig.savefig(out, dpi=150)
        plt.close(fig)
        print(f"    {os.path.basename(out)}")

    print(f"  plots/ → {plots_dir}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Análise pós-hoc de métricas múltiplas — EVRPTW TCC"
    )
    ap.add_argument("--results-dir", required=True,
                    help="Diretório com pickles/ e index.csv (output do stopping_criterion.py)")
    ap.add_argument("--algorithms", nargs="+", default=DEFAULT_ALGORITHMS)
    ap.add_argument("--instances",  nargs="+", default=DEFAULT_INSTANCES)
    ap.add_argument("--plots", action="store_true",
                    help="Gera gráficos de convergência (requer matplotlib)")
    ap.add_argument("--out-dir", default=None,
                    help="Diretório de saída (padrão: mesma pasta de results-dir)")
    args = ap.parse_args()

    results_dir = args.results_dir
    pickles_dir = os.path.join(results_dir, "pickles")
    out_dir     = args.out_dir or results_dir

    if not os.path.isdir(pickles_dir):
        print(f"[ERRO] Diretório pickles não encontrado: {pickles_dir}")
        sys.exit(1)

    ts = datetime.now().isoformat(timespec="seconds")
    print("=" * 72)
    print("ANÁLISE DE MÉTRICAS PÓS-HOC — EVRPTW TCC")
    print("=" * 72)
    print(f"  {ts}")
    print(f"  results_dir : {results_dir}")
    print(f"  Algoritmos  : {args.algorithms}")
    print(f"  Instâncias  : {args.instances}")

    # ── 1. Carregamento ───────────────────────────────────────────────────────
    print(f"\n{'─'*72}")
    print("SEÇÃO 1 — Carregamento")
    print(f"{'─'*72}")
    data = load_all_runs(pickles_dir, args.algorithms, args.instances)
    if not data:
        print("[ERRO] Nenhum run carregado.")
        sys.exit(1)

    # ── 2. Frentes de referência ──────────────────────────────────────────────
    print(f"\n{'─'*72}")
    print("SEÇÃO 2 — Frentes de Referência (union não-dominada)")
    print(f"{'─'*72}")
    ref_fronts, ref_points = build_ref_fronts(data, args.instances)

    # Amplitude por instância (para spacing_norm)
    ref_ranges = {}
    for inst, rf in ref_fronts.items():
        r = rf.max(axis=0) - rf.min(axis=0)
        ref_ranges[inst] = np.where(r > 0, r, 1.0)

    # ── 3. Cálculo de métricas por run ─────────────────────────────────────────
    print(f"\n{'─'*72}")
    print("SEÇÃO 3 — Cálculo de Métricas por Run")
    print(f"{'─'*72}")
    all_metrics = {}
    for key, run in data.items():
        alg, inst, run_idx = key
        if inst not in ref_fronts:
            continue
        m = compute_all_metrics(run, ref_fronts[inst], ref_points[inst],
                                ref_ranges[inst])
        all_metrics[key] = m
        print(f"  {alg:<10} {inst:<12} run{run_idx}  "
              f"HV={m['hv']:.0f}  IGD+={_fmt(m['igd_plus'])}  "
              f"n_nd={m['n_pareto']}  f1_layers={m['n_f1_layers']}")

    # ── 4. Agregação ──────────────────────────────────────────────────────────
    print(f"\n{'─'*72}")
    print("SEÇÃO 4 — Agregação (mediana + IQR)")
    print(f"{'─'*72}")
    agg = aggregate(all_metrics, args.algorithms, args.instances)

    for alg in args.algorithms:
        print(f"\n  [{alg}]")
        for inst in args.instances:
            row = agg.get((alg, inst), {})
            if not row:
                continue
            print(f"    {inst:<12}  HV={_fmt(row.get('hv_median'), '.0f')} "
                  f"(IQR={_fmt(row.get('hv_iqr'), '.0f')})  "
                  f"IGD+={_fmt(row.get('igd_plus_median'))}  "
                  f"f1_layers={_fmt(row.get('n_f1_layers_median'), '.1f')}  "
                  f"best_f3={_fmt(row.get('best_f3_median'), '.1f')}")

    # ── 5. Hipóteses ──────────────────────────────────────────────────────────
    print(f"\n{'─'*72}")
    print("SEÇÃO 5 — Verificação das Hipóteses")
    print(f"{'─'*72}")
    hyp = verify_hypotheses(agg, data, args.algorithms, args.instances)

    for name, h in hyp.items():
        sup = h.get("supported")
        cnt = h.get("count")
        tot = h.get("total")
        if cnt is not None:
            result = f"{cnt}/{tot}"
        elif sup is not None:
            result = "suportada" if sup else "não suportada"
        else:
            result = "N/A (n=6)"
        icon = "✅" if (sup or (cnt is not None and cnt > tot // 2)) else "❌"
        print(f"  {icon} {name:<12}: {h['description'][:60]}  → {result}")

    # ── 6. Curvas de convergência ─────────────────────────────────────────────
    print(f"\n{'─'*72}")
    print("SEÇÃO 6 — Curvas de Convergência e Outputs")
    print(f"{'─'*72}")
    curves_dir = os.path.join(out_dir, "convergence_curves")
    save_convergence_curves(data, ref_points, args.algorithms, args.instances, curves_dir)

    # CSV consolidado
    csv_path = os.path.join(out_dir, "metrics_summary.csv")
    save_metrics_csv(agg, args.algorithms, args.instances, csv_path)

    # Relatório Markdown
    md_path = os.path.join(out_dir, "metrics_report.md")
    save_report(agg, hyp, args.algorithms, args.instances, md_path)

    # Plots opcionais
    if args.plots:
        plots_dir = os.path.join(out_dir, "plots")
        generate_plots(curves_dir, args.algorithms, args.instances, plots_dir)

    print(f"\n{'='*72}")
    print("Análise concluída.")
    print(f"{'='*72}")


if __name__ == "__main__":
    main()
