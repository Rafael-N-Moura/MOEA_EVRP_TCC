"""
Experimento baseline: NSGA-II + CDP e MOEA/D no EVRP.

Fase 1 do IAS-EVRP. Valida a representacao, o CI e a inicializacao
em tres camadas com algoritmos do pymoo (NSGA-II e MOEA/D).

Cenarios:
  A) t_charge=0.0 (referencia, sem custo de recarga)
  B) Recarga dinamica realista (g da instancia), md=0
  C) Recarga dinamica realista (g da instancia), md=10
"""

import json
import os
import time

from evrp.instance import load_schneider
from evrp.runner import run_experiment


def run_single(instance_file: str, label: str,
               N_P: int = 100, N_gen: int = 200, seed: int = 42,
               t_charge=None, md: float = 0.0,
               algorithm_name: str = 'nsga2'):
    """Executa um experimento e imprime diagnosticos."""
    kwargs = dict(md=md)
    if t_charge is not None:
        kwargs['t_charge'] = t_charge

    inst = load_schneider(instance_file, **kwargs)

    print(f'\n{"="*70}')
    print(f'Executando: {label}')
    print(f'  Instancia: {inst.name}')
    print(f'  Algoritmo: {algorithm_name}')
    print(f'  B={inst.B:.2f}, g={inst.g:.4f}, t_charge_max={inst.t_charge:.2f}')
    print(f'  md={inst.md:.1f}, N_P={N_P}, N_gen={N_gen}')
    print(f'{"="*70}')

    t0 = time.time()
    results = run_experiment(
        inst, N_P=N_P, N_gen=N_gen,
        init_params=dict(
            alpha_V=0.40, alpha_E=0.35,
            beta_s=0.20, p_skip=0.50, seed=seed,
        ),
        algorithm_name=algorithm_name,
        seed=seed,
    )
    elapsed = time.time() - t0

    history = results['history']
    ecd_values = [
        m.avg_f2_feasible - m.avg_f2_ies
        for m in history
        if m.n_IES > 0 and m.n_feasible > 0
    ]

    print(f'\n--- Diagnosticos {label} ---')
    print(f'Tempo total: {elapsed:.1f}s')

    if ecd_values:
        print(f'ECD medio: {sum(ecd_values)/len(ecd_values):.1f} '
              f'(positivo = mascaramento)')
        print(f'ECD final: {ecd_values[-1]:.1f}')
    else:
        print('ECD: sem dados (sem IES e viaveis simultaneos)')

    print('\nEvolucao (f1=veiculos, f2=distancia, f3=makespan):')
    step = max(1, N_gen // 4)
    for m in history[::step]:
        print(f'  Gen {m.generation:4d}: FVR={m.fvr:.0%} '
              f'bestF1={m.best_f1_feasible:.0f} bestF2={m.best_f2_feasible:.0f} '
              f'bestF3={m.best_f3_feasible:.0f} IES={m.n_IES} IM={m.n_IM}')
    last = history[-1]
    print(f'  Gen {last.generation:4d}: FVR={last.fvr:.0%} '
          f'bestF1={last.best_f1_feasible:.0f} bestF2={last.best_f2_feasible:.0f} '
          f'bestF3={last.best_f3_feasible:.0f} Pareto={last.n_pareto_feasible}')

    os.makedirs('results', exist_ok=True)
    hist_data = []
    for m in history:
        hist_data.append({
            'gen': m.generation, 'fvr': m.fvr, 'eratio': m.eratio,
            'n_pareto': m.n_pareto_feasible,
            'best_f1': m.best_f1_feasible, 'best_f2': m.best_f2_feasible,
            'best_f3': m.best_f3_feasible,
            'avg_f1_feas': m.avg_f1_feasible, 'avg_f2_feas': m.avg_f2_feasible,
            'avg_f3_feas': m.avg_f3_feasible,
            'avg_f2_ies': m.avg_f2_ies,
            'n_IES': m.n_IES, 'n_IM': m.n_IM,
            'n_feasible': m.n_feasible,
            'n_truly_feasible': m.n_truly_feasible,
            'avg_custs_per_route': m.avg_custs_per_route,
            'pct_single_cust_routes': m.pct_single_cust_routes,
            'avg_raw_energy': m.avg_raw_energy,
        })
    fname = f'results/baseline_{algorithm_name}_{label}_s{seed}.json'
    with open(fname, 'w') as f:
        json.dump(hist_data, f, indent=2)
    print(f'Historico salvo em {fname}')

    return results


if __name__ == '__main__':
    INST_DIR = 'evrptw_instances'

    instances = [
        (f'{INST_DIR}/c101C5.txt', 'c101C5', 30, 50),
        (f'{INST_DIR}/c201_21.txt', 'c201_21', 100, 200),
        (f'{INST_DIR}/c101_21.txt', 'c101_21', 100, 200),
    ]

    scenarios = [
        ('A_tcharge0', dict(t_charge=0.0, md=0.0)),
        ('B_realista', dict(md=0.0)),
        ('C_realista_md10', dict(md=10.0)),
    ]

    algorithms = ['nsga2', 'moead']

    for algorithm_name in algorithms:
        for inst_file, inst_name, n_p, n_gen in instances:
            for scenario_id, scenario_kwargs in scenarios:
                label = f'{inst_name}_{scenario_id}'
                run_single(
                    inst_file, label,
                    N_P=n_p, N_gen=n_gen, seed=42,
                    algorithm_name=algorithm_name,
                    **scenario_kwargs,
                )
