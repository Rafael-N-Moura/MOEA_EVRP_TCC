"""
Script principal para execução dos algoritmos NSGA-II e MOEA/D
no problema EVRPTW-PR Multi-Objetivo.
"""

import argparse
import time
import sys
import os
from datetime import datetime
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
from pymoo.core.callback import Callback


class TeeOutput:
    """Classe para escrever simultaneamente em arquivo e stdout."""
    def __init__(self, file_path):
        self.file = open(file_path, 'w', encoding='utf-8')
        self.stdout = sys.stdout
    
    def write(self, text):
        self.file.write(text)
        self.file.flush()
        self.stdout.write(text)
    
    def flush(self):
        self.file.flush()
        self.stdout.flush()
    
    def close(self):
        self.file.close()


class NSGA2LoggingCallback(Callback):
    """
    Callback para adicionar logs detalhados ao NSGA2.
    Mostra estatísticas de f1 e f2 a cada geração.
    """
    
    def __init__(self):
        super().__init__()
        self.n_gen = 0
    
    def notify(self, algorithm):
        """Chamado a cada geração após _advance."""
        self.n_gen = algorithm.n_gen
        
        if hasattr(algorithm, 'pop') and algorithm.pop is not None and len(algorithm.pop) > 0:
            pop = algorithm.pop
            
            if pop.has("F"):
                F = pop.get("F")
                f1_values = F[:, 0]  # Custo
                f2_values = F[:, 1]  # Insatisfação
                
                f1_mean = np.mean(f1_values)
                f1_min = np.min(f1_values)
                f1_max = np.max(f1_values)
                f2_mean = np.mean(f2_values)
                f2_min = np.min(f2_values)
                f2_max = np.max(f2_values)
                
                # Verifica viabilidade se houver restrições
                if pop.has("G"):
                    G = pop.get("G")
                    if G.shape[1] >= 2:  # Tem G2 (bateria)
                        g2_values = G[:, 1]
                        n_feasible = np.sum(g2_values <= 0)
                        n_infeasible = len(g2_values) - n_feasible
                        pct_feasible = (n_feasible / len(g2_values)) * 100 if len(g2_values) > 0 else 0.0
                        
                        # Estatísticas separadas para viáveis e inviáveis
                        if n_feasible > 0:
                            feasible_mask = g2_values <= 0
                            F_feasible = F[feasible_mask]
                            f1_feasible_mean = np.mean(F_feasible[:, 0])
                            f1_feasible_min = np.min(F_feasible[:, 0])
                            f2_feasible_mean = np.mean(F_feasible[:, 1])
                            f2_feasible_min = np.min(F_feasible[:, 1])
                        else:
                            f1_feasible_mean = f1_feasible_min = f2_feasible_mean = f2_feasible_min = 0.0
                        
                        if n_infeasible > 0:
                            infeasible_mask = g2_values > 0
                            F_infeasible = F[infeasible_mask]
                            f1_infeasible_mean = np.mean(F_infeasible[:, 0])
                            f1_infeasible_min = np.min(F_infeasible[:, 0])
                            f2_infeasible_mean = np.mean(F_infeasible[:, 1])
                            g2_infeasible_mean = np.mean(g2_values[infeasible_mask])
                            g2_infeasible_min = np.min(g2_values[infeasible_mask])
                            g2_infeasible_max = np.max(g2_values[infeasible_mask])
                        else:
                            f1_infeasible_mean = f1_infeasible_min = f2_infeasible_mean = 0.0
                            g2_infeasible_mean = g2_infeasible_min = g2_infeasible_max = 0.0
                        
                        print(f"Gen {self.n_gen:3d} | Pop: {len(pop):3d} | Viáveis: {n_feasible:3d} ({pct_feasible:5.1f}%) | Inviáveis: {n_infeasible:3d}")
                        if n_feasible > 0:
                            print(f"  └─ Viáveis: f1 médio={f1_feasible_mean:.1f}, min={f1_feasible_min:.1f} | "
                                  f"f2 médio={f2_feasible_mean:.3f}, min={f2_feasible_min:.3f}")
                        if n_infeasible > 0:
                            print(f"  └─ Inviáveis: f1 médio={f1_infeasible_mean:.1f}, min={f1_infeasible_min:.1f} | "
                                  f"f2 médio={f2_infeasible_mean:.3f} | G2 médio={g2_infeasible_mean:.2f}, "
                                  f"min={g2_infeasible_min:.2f}, max={g2_infeasible_max:.2f}")
                    else:
                        # Sem G2, mostra apenas estatísticas gerais
                        print(f"Gen {self.n_gen:3d} | Pop: {len(pop):3d} | f1 médio={f1_mean:.1f}, min={f1_min:.1f}, max={f1_max:.1f} | "
                              f"f2 médio={f2_mean:.3f}, min={f2_min:.3f}, max={f2_max:.3f}")
                else:
                    # Sem restrições, mostra apenas estatísticas gerais
                    print(f"Gen {self.n_gen:3d} | Pop: {len(pop):3d} | f1 médio={f1_mean:.1f}, min={f1_min:.1f}, max={f1_max:.1f} | "
                          f"f2 médio={f2_mean:.3f}, min={f2_min:.3f}, max={f2_max:.3f}")


def run_nsga2(problem, n_gen=100, pop_size=100, verbose=True, instance_name=None, save_front=False, seed=1):
    """
    Executa algoritmo NSGA-II.

    Args:
        problem: Instância do problema EVRPTWProblem
        n_gen: Número de gerações
        pop_size: Tamanho da população
        verbose: Se True, exibe progresso
        instance_name: Nome da instância (para nomear o arquivo de log)
        save_front: Se True, salva res.F em logs/nsga2_<instance>_<timestamp>_front.npz
        seed: Semente aleatória para reprodutibilidade (permutações iniciais e operadores)

    Returns:
        Resultado da otimização
    """
    # Cria arquivo de log
    if instance_name is None:
        instance_name = "unknown"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"logs/nsga2_{instance_name}_{timestamp}.txt"
    
    # Cria diretório de logs se não existir
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    save_front_path = log_file.replace('.txt', '_front.npz') if save_front else None

    # Redireciona output para arquivo e terminal
    original_stdout = sys.stdout
    tee = TeeOutput(log_file)
    sys.stdout = tee
    
    try:
        print(f"\n{'='*80}")
        print("EXECUTANDO NSGA-II")
        print(f"{'='*80}")
        print(f"Logs sendo salvos em: {log_file}")
        print(f"{'='*80}")
        print(f"População: {pop_size}")
        print(f"Gerações: {n_gen}")
        print(f"{'='*80}\n")
        
        algorithm = NSGA2(
            pop_size=pop_size,
            sampling=PermutationRandomSampling(),
            crossover=OrderCrossover(),  # Preserva ordem relativa (Vital para VRP)
            mutation=InversionMutation(),  # Simula 2-opt
            eliminate_duplicates=True,
            save_history=True  # Salva histórico para análise
        )
        
        # Adiciona callback para logs detalhados
        callback = NSGA2LoggingCallback()
        
        start_time = time.time()
        res = minimize(
            problem,
            algorithm,
            ('n_gen', n_gen),
            verbose=verbose,
            seed=seed,
            callback=callback
        )
        elapsed_time = time.time() - start_time
    
        print(f"\n{'='*80}")
        print("NSGA-II FINALIZADO")
        print(f"{'='*80}")
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
        
        print(f"\n{'='*80}")
        print(f"Logs salvos em: {log_file}")
        print(f"{'='*80}\n")
        
        if save_front_path and len(res.F) > 0:
            np.savez(save_front_path, F=res.F)
            print(f"✓ Frente de Pareto salva em: {save_front_path}")
        
        return res
    finally:
        # Restaura stdout original
        sys.stdout = original_stdout
        tee.close()
        print(f"✓ Logs do NSGA2 salvos em: {log_file}")


def run_battery_focused_nsga2(problem, n_gen=100, pop_size=100, infeasible_ratio=0.25, feasible_mating_ratio=0.7, test_all_feasible=False, verbose=True, instance_name=None, save_front=False, seed=1):
    """
    Executa algoritmo NSGA-II com Directed Mating focado em bateria.
    
    Args:
        problem: Instância do problema EVRPTWProblem (deve usar use_constraints=True)
        n_gen: Número de gerações
        pop_size: Tamanho da população
        infeasible_ratio: Proporção de soluções inviáveis a preservar (0.2 a 0.3)
        feasible_mating_ratio: Proporção de cruzamentos viável-viável (ex.: 0.7); resto viável-inviável
        test_all_feasible: Se True, 100% viável (init e offspring conservador, N_I=0) para teste de integridade
        verbose: Se True, exibe progresso
        instance_name: Nome da instância (para nomear o arquivo de log)
        save_front: Se True, salva res.F em logs/battery_focused_nsga2_<instance>_<timestamp>_front.npz
    
    Returns:
        Resultado da otimização
    """
    # Cria arquivo de log
    if instance_name is None:
        instance_name = "unknown"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"logs/battery_focused_nsga2_{instance_name}_{timestamp}.txt"
    
    # Cria diretório de logs se não existir
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    save_front_path = log_file.replace('.txt', '_front.npz') if save_front else None
    
    # Redireciona output para arquivo e terminal
    original_stdout = sys.stdout
    tee = TeeOutput(log_file)
    sys.stdout = tee
    
    try:
        print(f"\n{'='*80}")
        print("EXECUTANDO NSGA-II COM DIRECTED MATING (BATERIA)")
        print(f"{'='*80}")
        print(f"Logs sendo salvos em: {log_file}")
        print(f"{'='*80}")
        print(f"População: {pop_size}")
        print(f"Gerações: {n_gen}")
        print(f"Taxa de inviáveis preservados: {infeasible_ratio*100:.1f}%")
        print(f"Cruzamentos viável-viável: {feasible_mating_ratio*100:.0f}%")
        if test_all_feasible:
            print("Modo: test_all_feasible (100% viável, decoder conservador sempre; pipeline dois arquivos com N_I=0)")
        print(f"{'='*80}\n")
        
        algorithm = BatteryFocusedNSGA2(
            pop_size=pop_size,
            infeasible_ratio=infeasible_ratio,
            feasible_mating_ratio=feasible_mating_ratio,
            test_all_feasible=test_all_feasible,
            all_conservative_init=False,
            crossover=OrderCrossover(),
            mutation=InversionMutation(),
            eliminate_duplicates=True
        )
        
        start_time = time.time()
        res = minimize(
            problem,
            algorithm,
            ('n_gen', n_gen),
            verbose=verbose,
            seed=seed
        )
        elapsed_time = time.time() - start_time
    
        print(f"\n{'='*80}")
        print("NSGA-II COM DIRECTED MATING FINALIZADO")
        print(f"{'='*80}")
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
        
        print(f"\n{'='*80}")
        print(f"Logs salvos em: {log_file}")
        print(f"{'='*80}\n")
        
        if save_front_path and len(res.F) > 0:
            np.savez(save_front_path, F=res.F)
            print(f"✓ Frente de Pareto salva em: {save_front_path}")
        
        return res
    finally:
        # Restaura stdout original
        sys.stdout = original_stdout
        tee.close()
        print(f"✓ Logs do BatteryFocusedNSGA2 salvos em: {log_file}")


def run_moead(problem, n_gen=100, pop_size=100, n_partitions=99, verbose=True, seed=1):
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
        seed=seed
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
    parser.add_argument(
        '--no-radical',
        action='store_true',
        help='Decoder não radical (com estações no modo inviável). Para battery-focused e, se rodar nsga2, mesmo decoder. Default: radical no battery-focused'
    )
    parser.add_argument(
        '--save-front',
        action='store_true',
        help='Salva a frente de Pareto (res.F) em .npz em logs/ para comparação com compare_pareto_fronts.py'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=1,
        help='Semente aleatória para reprodutibilidade (default: 1). Use a mesma seed em nsga2 e battery-focused para mesmas permutações iniciais.'
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
    
    # Cria problemas para cada algoritmo
    # NSGA-II padrão: usa penalização e force_battery_feasible=True (comportamento conservador)
    # BatteryFocusedNSGA2: usa restrições e force_battery_feasible=False (permite violações durante evolução)
    results = {}
    
    if args.algorithm in ['nsga2', 'both']:
        # NSGA-II padrão: sempre viável (force_battery_feasible=True). Com --no-radical: mesmo decoder não radical do battery-focused
        kwargs_nsga2 = dict(context=context, use_constraints=False, force_battery_feasible=True)
        if getattr(args, 'no_radical', False):
            kwargs_nsga2['use_radical_infeasible'] = False
        problem_nsga2 = EVRPTWProblem(**kwargs_nsga2)
        # Extrai nome da instância para o arquivo de log
        instance_name = os.path.splitext(os.path.basename(args.instance))[0]
        results['nsga2'] = run_nsga2(
            problem_nsga2,
            n_gen=args.n_gen,
            pop_size=args.pop_size,
            verbose=not args.no_verbose,
            instance_name=instance_name,
            save_front=getattr(args, 'save_front', False),
            seed=args.seed
        )
    
    if args.algorithm == 'battery-focused':
        # BatteryFocusedNSGA2: dinâmica com dois perfis do decoder (DECODER_ALTERNATIVO)
        # A_F (convergence): decodificação com perfil conservador (force_battery_feasible=True)
        # A_I (diversity): decodificação com perfil agressivo (--no-radical) ou radical (sem estações)
        use_radical = not args.no_radical
        problem_battery = EVRPTWProblem(
            context, use_constraints=True, force_battery_feasible=False,
            use_radical_infeasible=use_radical
        )
        if not args.no_verbose:
            decoder_inv = "agressivo (com estações)" if not use_radical else "radical (sem estações)"
            print(f"Battery Focused: população={args.pop_size}, gerações={args.n_gen}, decoder A_F=conservador, A_I={decoder_inv}")
        # Extrai nome da instância para o arquivo de log
        instance_name = os.path.splitext(os.path.basename(args.instance))[0]
        results['battery-focused'] = run_battery_focused_nsga2(
            problem_battery,
            n_gen=args.n_gen,
            pop_size=args.pop_size,
            infeasible_ratio=0.30,
            feasible_mating_ratio=0.7,
            test_all_feasible=False,
            verbose=not args.no_verbose,
            instance_name=instance_name,
            save_front=getattr(args, 'save_front', False),
            seed=args.seed
        )
    
    if args.algorithm in ['moead', 'both']:
        # MOEA/D: usa penalização e force_battery_feasible=True (comportamento conservador, igual ao NSGA-II)
        problem_moead = EVRPTWProblem(context, use_constraints=False, force_battery_feasible=True)
        results['moead'] = run_moead(
            problem_moead,
            n_gen=args.n_gen,
            pop_size=args.pop_size,
            n_partitions=args.n_partitions,
            verbose=not args.no_verbose,
            seed=args.seed
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
