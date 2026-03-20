"""
Comparacao NSGA-II vs MOEA/D com populacao inicial 100% camada V (alpha_V=1.0).

Uso:
  python run_compare_100V.py

Roda N_P=100, N_gen=200, seed=42, cenario B (g realista) em c201_21 e c101_21.
Salva JSON em results/compare_100V_<inst>_<algo>_s42.json
"""

import json
import os
import time

from evrp.instance import load_schneider
from evrp.runner import run_experiment

INIT_100V = dict(alpha_V=1.0, alpha_E=0.0, beta_s=0.20, p_skip=0.50, seed=42)
N_P, N_GEN, SEED = 100, 200, 42
RESULTS_DIR = 'results'


def hist_to_list(history):
    return [
        {
            'gen': m.generation,
            'fvr': m.fvr,
            'best_f1': m.best_f1_feasible,
            'best_f2': m.best_f2_feasible,
            'best_f3': m.best_f3_feasible,
            'avg_f2_feas': m.avg_f2_feasible,
            'n_feasible': m.n_feasible,
            'n_truly_feasible': m.n_truly_feasible,
            'avg_custs_per_route': m.avg_custs_per_route,
            'pct_single_cust_routes': m.pct_single_cust_routes,
            'avg_raw_energy': m.avg_raw_energy,
            'n_pareto': m.n_pareto_feasible,
        }
        for m in history
    ]


def run_pair(inst_file: str, label: str, md: float = 0.0, t_charge=None):
    kwargs = dict(md=md)
    if t_charge is not None:
        kwargs['t_charge'] = t_charge
    inst = load_schneider(inst_file, **kwargs)

    print(f'\n{"="*80}')
    print(f'{label} | {inst.name} | N_P={N_P}, N_gen={N_GEN}, alpha_V=1.0')
    print(f'{"="*80}')

    out = {}
    for algo in ('nsga2', 'moead'):
        print(f'\n--- {algo.upper()} ---')
        t0 = time.time()
        res = run_experiment(
            inst,
            N_P=N_P,
            N_gen=N_GEN,
            init_params=INIT_100V,
            algorithm_name=algo,
            seed=SEED,
            verbose=True,
        )
        elapsed = time.time() - t0
        last = res['history'][-1]
        print(f'Tempo: {elapsed:.1f}s')
        print(
            f'Final: bestF1={last.best_f1_feasible:.0f} bestF2={last.best_f2_feasible:.0f} '
            f'bestF3={last.best_f3_feasible:.0f} trulyFeas={last.n_truly_feasible}/{N_P} '
            f'avgRawE={last.avg_raw_energy:.1f} cust/rota={last.avg_custs_per_route:.2f} '
            f'single={last.pct_single_cust_routes:.0%}'
        )

        fname = f'{RESULTS_DIR}/compare_100V_{algo}_{label}_s{SEED}.json'
        os.makedirs(RESULTS_DIR, exist_ok=True)
        with open(fname, 'w') as f:
            json.dump(
                {
                    'algorithm': algo,
                    'label': label,
                    'instance': inst.name,
                    'N_P': N_P,
                    'N_gen': N_GEN,
                    'init': INIT_100V,
                    'elapsed_s': elapsed,
                    'history': hist_to_list(res['history']),
                },
                f,
                indent=2,
            )
        print(f'Salvo: {fname}')
        out[algo] = res

    # Resumo lado a lado
    h_n = out['nsga2']['history'][-1]
    h_m = out['moead']['history'][-1]
    print(f'\n>>> RESUMO {label}')
    print(
        f'NSGA-II: bestF1={h_n.best_f1_feasible:.0f} bestF2={h_n.best_f2_feasible:.0f} '
        f'bestF3={h_n.best_f3_feasible:.0f} trulyFeas={h_n.n_truly_feasible}'
    )
    print(
        f'MOEA/D:  bestF1={h_m.best_f1_feasible:.0f} bestF2={h_m.best_f2_feasible:.0f} '
        f'bestF3={h_m.best_f3_feasible:.0f} trulyFeas={h_m.n_truly_feasible}'
    )


if __name__ == '__main__':
    run_pair('evrptw_instances/c201_21.txt', 'c201_21_B', md=0.0)
    run_pair('evrptw_instances/c101_21.txt', 'c101_21_B', md=0.0)
