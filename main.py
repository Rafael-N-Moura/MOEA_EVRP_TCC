"""
Script principal para execução dos algoritmos NSGA-II e MOEA/D
no problema EVRPTW-PR Multi-Objetivo.
"""

import argparse
import time
import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.moo.moead import MOEAD
from pymoo.optimize import minimize
from pymoo.operators.sampling.rnd import PermutationRandomSampling
from pymoo.operators.crossover.ox import OrderCrossover
from pymoo.operators.mutation.inversion import InversionMutation
# Importação de get_reference_directions (necessário apenas para MOEA/D)
# Será importado apenas quando necessário na função run_moead
get_reference_directions = None
from pymoo.visualization.scatter import Scatter

from src import parse_instance, EVRPTWProblem
from src.battery_focused_nsga2 import BatteryFocusedNSGA2


def run_nsga2(problem, n_gen=100, pop_size=100, verbose=True):
    """
    Executa algoritmo NSGA-II.
    
    Args:
        problem: Instância do problema EVRPTWProblem
        n_gen: Número de gerações
        pop_size: Tamanho da população
        verbose: Se True, exibe progresso
        
    Returns:
        Resultado da otimização
    """
    algorithm = NSGA2(
        pop_size=pop_size,
        sampling=PermutationRandomSampling(),
        crossover=OrderCrossover(),  # Preserva ordem relativa (Vital para VRP)
        mutation=InversionMutation(),  # Simula 2-opt
        eliminate_duplicates=True,
        save_history=True  # Salva histórico para análise
    )
    
    print(f"\n{'='*60}")
    print("Executando NSGA-II")
    print(f"{'='*60}")
    print(f"População: {pop_size}")
    print(f"Gerações: {n_gen}")
    print(f"{'='*60}\n")
    
    start_time = time.time()
    res = minimize(
        problem,
        algorithm,
        ('n_gen', n_gen),
        verbose=verbose,
        seed=1
    )
    elapsed_time = time.time() - start_time
    
    print(f"\n{'='*60}")
    print("NSGA-II Finalizado")
    print(f"{'='*60}")
    print(f"Tempo de execução: {elapsed_time:.2f} segundos")
    
    # Verifica se há população completa ou apenas frente de Pareto
    if hasattr(res, 'pop') and res.pop is not None:
        pop_size_actual = len(res.pop)
        print(f"Tamanho da população final: {pop_size_actual}")
    
    print(f"Soluções na frente de Pareto: {len(res.F)}")
    
    if len(res.F) > 0:
        print(f"\nEstatísticas dos Objetivos:")
        print(f"  f1 (custo): min={res.F[:, 0].min():.2f}, max={res.F[:, 0].max():.2f}, média={res.F[:, 0].mean():.2f}")
        print(f"  f2 (insatisfação): min={res.F[:, 1].min():.4f}, max={res.F[:, 1].max():.4f}, média={res.F[:, 1].mean():.4f}")
        
        # Verifica se há soluções únicas
        unique_solutions = len(set([(f1, f2) for f1, f2 in res.F]))
        if unique_solutions < len(res.F):
            print(f"  ⚠️  Atenção: {len(res.F) - unique_solutions} soluções duplicadas encontradas")
        
        # Mostra algumas soluções da frente de Pareto
        if len(res.F) <= 10:
            print(f"\nTodas as soluções da frente de Pareto:")
            for i, (f1, f2) in enumerate(res.F):
                print(f"  Solução {i+1}: Custo={f1:.2f}, Insatisfação={f2:.4f}")
        else:
            print(f"\nPrimeiras 5 soluções da frente de Pareto:")
            for i, (f1, f2) in enumerate(res.F[:5]):
                print(f"  Solução {i+1}: Custo={f1:.2f}, Insatisfação={f2:.4f}")
            print(f"  ... e mais {len(res.F) - 5} soluções")
            
        # Se apenas uma solução, adiciona aviso
        if len(res.F) == 1:
            print(f"\n⚠️  AVISO: Apenas 1 solução encontrada na frente de Pareto!")
            print(f"  Isso pode indicar:")
            print(f"    - Convergência prematura (tente mais gerações)")
            print(f"    - População muito pequena (tente aumentar --pop-size)")
            print(f"    - Problema na avaliação (todas soluções têm mesmo valor)")
            print(f"    - Trade-off entre custo e insatisfação não está sendo explorado")
    else:
        print("⚠️  Nenhuma solução encontrada!")
    
    print(f"{'='*60}\n")
    
    return res


def run_battery_focused_nsga2(problem, n_gen=100, pop_size=100, infeasible_ratio=0.25, verbose=True):
    """
    Executa algoritmo NSGA-II com Directed Mating focado em bateria.
    
    Args:
        problem: Instância do problema EVRPTWProblem (deve usar use_constraints=True)
        n_gen: Número de gerações
        pop_size: Tamanho da população
        infeasible_ratio: Proporção de soluções inviáveis a preservar (0.2 a 0.3)
        verbose: Se True, exibe progresso
        
    Returns:
        Resultado da otimização
    """
    algorithm = BatteryFocusedNSGA2(
        pop_size=pop_size,
        infeasible_ratio=infeasible_ratio,
        crossover=OrderCrossover(),
        mutation=InversionMutation(),
        eliminate_duplicates=True
    )
    
    print(f"\n{'='*60}")
    print("Executando NSGA-II com Directed Mating (Bateria)")
    print(f"{'='*60}")
    print(f"População: {pop_size}")
    print(f"Gerações: {n_gen}")
    print(f"Taxa de inviáveis preservados: {infeasible_ratio*100:.1f}%")
    print(f"{'='*60}\n")
    
    start_time = time.time()
    res = minimize(
        problem,
        algorithm,
        ('n_gen', n_gen),
        verbose=verbose,
        seed=1
    )
    elapsed_time = time.time() - start_time
    
    print(f"\n{'='*60}")
    print("NSGA-II com Directed Mating Finalizado")
    print(f"{'='*60}")
    print(f"Tempo de execução: {elapsed_time:.2f} segundos")
    
    if hasattr(res, 'pop') and res.pop is not None:
        pop_size_actual = len(res.pop)
        print(f"Tamanho da população final: {pop_size_actual}")
        
        # Estatísticas de viabilidade
        if hasattr(res.pop, 'get') and res.pop.has("G"):
            G = res.pop.get("G")
            n_feasible = np.sum(G[:, 1] <= 0)  # G2 <= 0
            n_infeasible = len(G) - n_feasible
            print(f"Soluções viáveis: {n_feasible} ({n_feasible/len(G)*100:.1f}%)")
            print(f"Soluções inviáveis: {n_infeasible} ({n_infeasible/len(G)*100:.1f}%)")
    
    print(f"Soluções na frente de Pareto: {len(res.F)}")
    
    if len(res.F) > 0:
        print(f"\nEstatísticas dos Objetivos:")
        print(f"  f1 (custo): min={res.F[:, 0].min():.2f}, max={res.F[:, 0].max():.2f}, média={res.F[:, 0].mean():.2f}")
        print(f"  f2 (insatisfação): min={res.F[:, 1].min():.4f}, max={res.F[:, 1].max():.4f}, média={res.F[:, 1].mean():.4f}")
        
        # Mostra algumas soluções da frente de Pareto
        if len(res.F) <= 10:
            print(f"\nTodas as soluções da frente de Pareto:")
            for i, (f1, f2) in enumerate(res.F):
                print(f"  Solução {i+1}: Custo={f1:.2f}, Insatisfação={f2:.4f}")
        else:
            print(f"\nPrimeiras 5 soluções da frente de Pareto:")
            for i, (f1, f2) in enumerate(res.F[:5]):
                print(f"  Solução {i+1}: Custo={f1:.2f}, Insatisfação={f2:.4f}")
            print(f"  ... e mais {len(res.F) - 5} soluções")
    else:
        print("⚠️  Nenhuma solução encontrada!")
    
    print(f"{'='*60}\n")
    
    return res


def run_moead(problem, n_gen=100, pop_size=100, n_partitions=99, verbose=True):
    """
    Executa algoritmo MOEA/D.
    
    Args:
        problem: Instância do problema EVRPTWProblem
        n_gen: Número de gerações
        pop_size: Tamanho da população (deve ser compatível com n_partitions)
        n_partitions: Número de partições para direções de referência
        verbose: Se True, exibe progresso
        
    Returns:
        Resultado da otimização
    """
    # Importa get_reference_directions quando necessário
    global get_reference_directions
    if get_reference_directions is None:
        try:
            from pymoo.util.reference_direction import get_reference_directions
        except (ImportError, AttributeError):
            try:
                from pymoo.util.ref_dirs import get_reference_directions
            except (ImportError, AttributeError):
                import pymoo.util.reference_direction as ref_dir
                get_reference_directions = getattr(ref_dir, 'get_reference_directions', None)
                if get_reference_directions is None:
                    raise ImportError(
                        "Não foi possível importar get_reference_directions do pymoo.\n"
                        "Isso é necessário para MOEA/D.\n"
                        "Tente atualizar: pip install --upgrade pymoo\n"
                        "Ou use apenas NSGA-II: --algorithm nsga2"
                    )
    
    # Gera direções de referência (Das-Dennis)
    ref_dirs = get_reference_directions("das-dennis", 2, n_partitions=n_partitions)
    
    # Ajusta pop_size para corresponder ao número de direções
    actual_pop_size = len(ref_dirs)
    if pop_size != actual_pop_size:
        print(f"Aviso: Ajustando pop_size de {pop_size} para {actual_pop_size} "
              f"(número de direções de referência)")
        pop_size = actual_pop_size
    
    algorithm = MOEAD(
        ref_dirs,
        n_neighbors=15,
        prob_neighbor_mating=0.7,
        sampling=PermutationRandomSampling(),
        crossover=OrderCrossover(),
        mutation=InversionMutation()
    )
    
    print(f"\n{'='*60}")
    print("Executando MOEA/D")
    print(f"{'='*60}")
    print(f"População: {pop_size}")
    print(f"Gerações: {n_gen}")
    print(f"Direções de referência: {len(ref_dirs)}")
    print(f"{'='*60}\n")
    
    start_time = time.time()
    res = minimize(
        problem,
        algorithm,
        ('n_gen', n_gen),
        verbose=verbose,
        seed=1
    )
    elapsed_time = time.time() - start_time
    
    print(f"\n{'='*60}")
    print("MOEA/D Finalizado")
    print(f"{'='*60}")
    print(f"Tempo de execução: {elapsed_time:.2f} segundos")
    print(f"Soluções na frente de Pareto: {len(res.F)}")
    
    if len(res.F) > 0:
        print(f"\nEstatísticas dos Objetivos:")
        print(f"  f1 (custo): min={res.F[:, 0].min():.2f}, max={res.F[:, 0].max():.2f}, média={res.F[:, 0].mean():.2f}")
        print(f"  f2 (insatisfação): min={res.F[:, 1].min():.4f}, max={res.F[:, 1].max():.4f}, média={res.F[:, 1].mean():.4f}")
        
        # Mostra algumas soluções da frente de Pareto
        if len(res.F) <= 10:
            print(f"\nTodas as soluções da frente de Pareto:")
            for i, (f1, f2) in enumerate(res.F):
                print(f"  Solução {i+1}: Custo={f1:.2f}, Insatisfação={f2:.4f}")
        else:
            print(f"\nPrimeiras 5 soluções da frente de Pareto:")
            for i, (f1, f2) in enumerate(res.F[:5]):
                print(f"  Solução {i+1}: Custo={f1:.2f}, Insatisfação={f2:.4f}")
            print(f"  ... e mais {len(res.F) - 5} soluções")
    else:
        print("⚠️  Nenhuma solução encontrada!")
    
    print(f"{'='*60}\n")
    
    return res


def main():
    """Função principal"""
    parser = argparse.ArgumentParser(
        description='Executa algoritmos NSGA-II e MOEA/D para EVRPTW-PR'
    )
    parser.add_argument(
        'instance',
        type=str,
        help='Caminho para arquivo de instância (.txt)'
    )
    parser.add_argument(
        '--algorithm',
        type=str,
        choices=['nsga2', 'moead', 'battery-focused', 'both'],
        default='both',
        help='Algoritmo a executar (default: both). battery-focused = NSGA-II com Directed Mating'
    )
    parser.add_argument(
        '--n-gen',
        type=int,
        default=100,
        help='Número de gerações (default: 100)'
    )
    parser.add_argument(
        '--pop-size',
        type=int,
        default=100,
        help='Tamanho da população (default: 100)'
    )
    parser.add_argument(
        '--n-partitions',
        type=int,
        default=99,
        help='Número de partições para MOEA/D (default: 99)'
    )
    parser.add_argument(
        '--no-verbose',
        action='store_true',
        help='Desabilita saída verbose durante execução'
    )
    parser.add_argument(
        '--plot',
        action='store_true',
        help='Gera gráfico de frente de Pareto'
    )
    
    args = parser.parse_args()
    
    # Carrega instância
    print(f"Carregando instância: {args.instance}")
    try:
        context = parse_instance(args.instance)
        print(f"✓ Instância carregada com sucesso")
        print(f"  - Depósito: {context.depot.id}")
        print(f"  - Estações: {len(context.stations)}")
        print(f"  - Clientes: {len(context.customers)}")
        print(f"  - Capacidade bateria (Q): {context.battery_capacity}")
        print(f"  - Capacidade veículo (C): {context.vehicle_capacity}")
        print(f"  - Taxa consumo (r): {context.consumption_rate}")
        print(f"  - Taxa recarga (g): {context.recharge_rate}")
        print(f"  - Velocidade (v): {context.velocity}")
    except Exception as e:
        print(f"✗ Erro ao carregar instância: {e}")
        return
    
    # Cria problema
    # Para battery-focused, usa restrições em vez de penalização
    use_constraints = args.algorithm == 'battery-focused'
    problem = EVRPTWProblem(context, use_constraints=use_constraints, force_battery_feasible=False)
    
    # Executa algoritmos
    results = {}
    
    if args.algorithm in ['nsga2', 'both']:
        results['nsga2'] = run_nsga2(
            problem,
            n_gen=args.n_gen,
            pop_size=args.pop_size,
            verbose=not args.no_verbose
        )
    
    if args.algorithm == 'battery-focused':
        # Cria problema com restrições para battery-focused
        problem_battery = EVRPTWProblem(context, use_constraints=True, force_battery_feasible=False)
        results['battery-focused'] = run_battery_focused_nsga2(
            problem_battery,
            n_gen=args.n_gen,
            pop_size=args.pop_size,
            infeasible_ratio=0.25,
            verbose=not args.no_verbose
        )
    
    if args.algorithm in ['moead', 'both']:
        results['moead'] = run_moead(
            problem,
            n_gen=args.n_gen,
            pop_size=args.pop_size,
            n_partitions=args.n_partitions,
            verbose=not args.no_verbose
        )
    
    # Visualização
    if args.plot:
        plot = Scatter()
        if 'nsga2' in results:
            plot.add(results['nsga2'].F, label="NSGA-II", s=30, alpha=0.6)
        if 'moead' in results:
            plot.add(results['moead'].F, label="MOEA/D", s=30, alpha=0.6, marker="x")
        plot.show()
    
    print("\nExecução concluída!")


if __name__ == '__main__':
    main()
