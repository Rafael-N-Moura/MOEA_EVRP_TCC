"""
Diagnostico: 100% Viavel + Analise Estrutural

Executa experimentos com 100% da populacao inicial viavel (alpha_V=1.0)
e compara com os resultados existentes (alpha_V=0.40) para isolar a causa
da estagnacao observada em c101_21.

Coleta metricas adicionais:
  - n_truly_feasible: solucoes com raw violations = 0
  - avg_custs_per_route / pct_single_cust_routes: estrutura de rotas
  - offspring census: viabilidade dos filhos apos crossover+mutacao
"""

import json
import os
import time
from dataclasses import asdict

from evrp.instance import load_schneider
from evrp.runner import run_experiment

INST_DIR = 'evrptw_instances'
RESULTS_DIR = 'results'


def run_diagnostic_single(instance_file: str, label: str,
                          N_P: int, N_gen: int, seed: int = 42,
                          t_charge=None, md: float = 0.0,
                          alpha_V: float = 0.40, alpha_E: float = 0.35,
                          algorithm_name: str = 'nsga2'):
    kwargs = dict(md=md)
    if t_charge is not None:
        kwargs['t_charge'] = t_charge

    inst = load_schneider(instance_file, **kwargs)

    print(f'\n{"="*75}')
    print(f'DIAG: {label}')
    print(f'  Inst: {inst.name}, B={inst.B:.2f}, g={inst.g:.4f}')
    print(f'  Algoritmo: {algorithm_name}')
    print(f'  md={inst.md:.1f}, N_P={N_P}, N_gen={N_gen}')
    print(f'  alpha_V={alpha_V}, alpha_E={alpha_E}')
    print(f'{"="*75}')

    t0 = time.time()
    results = run_experiment(
        inst, N_P=N_P, N_gen=N_gen,
        init_params=dict(
            alpha_V=alpha_V, alpha_E=alpha_E,
            beta_s=0.20, p_skip=0.50, seed=seed,
        ),
        algorithm_name=algorithm_name,
        seed=seed,
    )
    elapsed = time.time() - t0
    print(f'Tempo: {elapsed:.1f}s')

    history = results['history']
    census = results['offspring_census']

    # Imprimir evolucao detalhada com metricas diagnosticas
    print(f'\nEvolucao (f1=veiculos, f2=dist, truly_feas, custs/rota):')
    step = max(1, N_gen // 8)
    for m in history[::step]:
        print(f'  Gen {m.generation:4d}: '
              f'bestF1={m.best_f1_feasible:3.0f} bestF2={m.best_f2_feasible:6.0f} '
              f'trulyFeas={m.n_truly_feasible:3d}/{N_P} '
              f'custs/rota={m.avg_custs_per_route:.2f} '
              f'single={m.pct_single_cust_routes:.0%} '
              f'avgRawE={m.avg_raw_energy:.1f}')
    last = history[-1]
    print(f'  Gen {last.generation:4d}: '
          f'bestF1={last.best_f1_feasible:3.0f} bestF2={last.best_f2_feasible:6.0f} '
          f'trulyFeas={last.n_truly_feasible:3d}/{N_P} '
          f'custs/rota={last.avg_custs_per_route:.2f} '
          f'single={last.pct_single_cust_routes:.0%} '
          f'avgRawE={last.avg_raw_energy:.1f}')

    # Imprimir censo de offspring
    if census:
        print(f'\nOffspring Census:')
        for c in census:
            print(f'  Gen {c.generation:4d}: '
                  f'{c.n_offspring} offspring, '
                  f'trulyFeas={c.n_truly_feasible} '
                  f'rawE=0:{c.n_raw_energy_zero} rawTW=0:{c.n_raw_tw_zero} '
                  f'avgRawE={c.avg_raw_energy:.1f} avgRawTW={c.avg_raw_tw:.1f}')

    # Salvar JSON com todas as metricas
    os.makedirs(RESULTS_DIR, exist_ok=True)
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
            'n_IES': m.n_IES, 'n_IM': m.n_IM, 'n_feasible': m.n_feasible,
            'n_truly_feasible': m.n_truly_feasible,
            'avg_custs_per_route': m.avg_custs_per_route,
            'pct_single_cust_routes': m.pct_single_cust_routes,
            'avg_raw_energy': m.avg_raw_energy,
        })
    census_data = [asdict(c) for c in census]

    fname = f'{RESULTS_DIR}/diag_{algorithm_name}_{label}_s{seed}.json'
    with open(fname, 'w') as f:
        json.dump({'history': hist_data, 'census': census_data}, f, indent=2)
    print(f'Salvo em {fname}')

    return results


def print_comparison_table(algorithm_name: str):
    """Tabela comparativa entre resultados existentes e diagnostico."""
    print(f'\n{"="*100}')
    print('TABELA COMPARATIVA')
    print(f'{"="*100}')

    rows = []

    scenarios = [
        ('c201_21_B_realista', 'baseline', 'c201 B (baseline)'),
        ('c201_21_B_100V', 'diag', 'c201 B (100%V)'),
        ('c101_21_A_tcharge0', 'baseline', 'c101 A g=0 (baseline)'),
        ('c101_21_A_100V', 'diag', 'c101 A g=0 (100%V)'),
        ('c101_21_B_realista', 'baseline', 'c101 B (baseline)'),
        ('c101_21_B_100V', 'diag', 'c101 B (100%V)'),
    ]

    header = (f'{"Cenario":<28} {"bestF1i":>7} {"bestF1f":>7} {"bestF2i":>8} '
              f'{"bestF2f":>8} {"trulyF%i":>8} {"trulyF%f":>8} '
              f'{"cust/rota_i":>11} {"cust/rota_f":>11} {"single%f":>8}')
    print(header)
    print('-' * len(header))

    for file_label, src, display in scenarios:
        if src == 'baseline':
            fpath = f'{RESULTS_DIR}/baseline_{algorithm_name}_{file_label}_s42.json'
            try:
                with open(fpath) as f:
                    data = json.load(f)
                first = data[0]
                last = data[-1]
                tf_i = first.get('n_truly_feasible', '?')
                tf_f = last.get('n_truly_feasible', '?')
                cr_i = first.get('avg_custs_per_route', '?')
                cr_f = last.get('avg_custs_per_route', '?')
                sc_f = last.get('pct_single_cust_routes', '?')
                n = last.get('n_feasible', 100)
            except FileNotFoundError:
                print(f'{display:<28} ARQUIVO NAO ENCONTRADO')
                continue
        else:
            fpath = f'{RESULTS_DIR}/diag_{algorithm_name}_{file_label}_s42.json'
            try:
                with open(fpath) as f:
                    raw = json.load(f)
                data = raw['history']
                first = data[0]
                last = data[-1]
                tf_i = first.get('n_truly_feasible', '?')
                tf_f = last.get('n_truly_feasible', '?')
                cr_i = first.get('avg_custs_per_route', '?')
                cr_f = last.get('avg_custs_per_route', '?')
                sc_f = last.get('pct_single_cust_routes', '?')
                n = last.get('n_feasible', 100)
            except FileNotFoundError:
                print(f'{display:<28} ARQUIVO NAO ENCONTRADO')
                continue

        bf1_i = first.get('best_f1', '?')
        bf1_f = last.get('best_f1', '?')
        bf2_i = first['best_f2']
        bf2_f = last['best_f2']

        tf_i_pct = f'{tf_i}/{n}' if tf_i != '?' else '?'
        tf_f_pct = f'{tf_f}/{n}' if tf_f != '?' else '?'
        cr_i_s = f'{cr_i:.2f}' if isinstance(cr_i, (int, float)) else str(cr_i)
        cr_f_s = f'{cr_f:.2f}' if isinstance(cr_f, (int, float)) else str(cr_f)
        sc_f_s = f'{sc_f:.0%}' if isinstance(sc_f, (int, float)) else str(sc_f)
        bf1_i_s = f'{bf1_i:.0f}' if isinstance(bf1_i, (int, float)) else str(bf1_i)
        bf1_f_s = f'{bf1_f:.0f}' if isinstance(bf1_f, (int, float)) else str(bf1_f)

        print(f'{display:<28} {bf1_i_s:>7} {bf1_f_s:>7} {bf2_i:>8.0f} '
              f'{bf2_f:>8.0f} {tf_i_pct:>8} {tf_f_pct:>8} '
              f'{cr_i_s:>11} {cr_f_s:>11} {sc_f_s:>8}')


if __name__ == '__main__':
    algorithms = ['nsga2', 'moead']

    for algorithm_name in algorithms:
        # Exp 1+2+3+4: 100% viavel com metricas diagnosticas
        configs = [
            (f'{INST_DIR}/c201_21.txt', 'c201_21_B_100V', 100, 200,
             dict(md=0.0)),
            (f'{INST_DIR}/c101_21.txt', 'c101_21_A_100V', 100, 200,
             dict(t_charge=0.0, md=0.0)),
            (f'{INST_DIR}/c101_21.txt', 'c101_21_B_100V', 100, 200,
             dict(md=0.0)),
        ]

        for inst_file, label, n_p, n_gen, extra_kwargs in configs:
            run_diagnostic_single(
                inst_file, label,
                N_P=n_p, N_gen=n_gen, seed=42,
                alpha_V=1.0, alpha_E=0.0,
                algorithm_name=algorithm_name,
                **extra_kwargs,
            )

        # Re-executar baselines com novas metricas para comparacao
        print('\n\n' + '=' * 75)
        print(f'Re-executando baselines com metricas diagnosticas ({algorithm_name})...')
        print('=' * 75)

        baselines = [
            (f'{INST_DIR}/c201_21.txt', 'c201_21_B_realista', 100, 200,
             dict(md=0.0)),
            (f'{INST_DIR}/c101_21.txt', 'c101_21_A_tcharge0', 100, 200,
             dict(t_charge=0.0, md=0.0)),
            (f'{INST_DIR}/c101_21.txt', 'c101_21_B_realista', 100, 200,
             dict(md=0.0)),
        ]

        for inst_file, label, n_p, n_gen, extra_kwargs in baselines:
            run_diagnostic_single(
                inst_file, label,
                N_P=n_p, N_gen=n_gen, seed=42,
                alpha_V=0.40, alpha_E=0.35,
                algorithm_name=algorithm_name,
                **extra_kwargs,
            )

        # Tabela comparativa
        print_comparison_table(algorithm_name)
