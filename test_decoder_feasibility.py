"""
Script de teste para diagnosticar por que o decoder gera soluções inviáveis
mesmo com force_battery_feasible=True.
"""

import sys
import os
from datetime import datetime
import numpy as np
from src.parser import parse_instance
from src.decoder import decode
from src.model import Context

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

def test_decoder_feasibility(instance_path: str, n_tests: int = 10, log_file: str = None):
    """
    Testa a viabilidade do decoder com force_battery_feasible=True.
    
    Args:
        instance_path: Caminho para a instância
        n_tests: Número de testes a realizar
        log_file: Caminho do arquivo de log (opcional, será gerado automaticamente se None)
    """
    # Gera nome do arquivo de log se não fornecido
    if log_file is None:
        instance_name = os.path.splitext(os.path.basename(instance_path))[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = f"logs/test_decoder_feasibility_{instance_name}_{timestamp}.txt"
    
    # Cria diretório de logs se não existir
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Redireciona output para arquivo e terminal
    tee = TeeOutput(log_file)
    sys.stdout = tee
    
    try:
        print("=" * 80)
        print("TESTE DE VIABILIDADE DO DECODER")
        print("=" * 80)
        print(f"\nLogs sendo salvos em: {log_file}")
        print("=" * 80)
        
        # Carrega instância
        print(f"\n[1] Carregando instância: {instance_path}")
        try:
            context = parse_instance(instance_path)
            print(f"✓ Instância carregada:")
            print(f"  - Clientes: {len(context.customers)}")
            print(f"  - Estações: {len(context.stations)}")
            print(f"  - Capacidade bateria: {context.battery_capacity}")
            print(f"  - Taxa consumo: {context.consumption_rate}")
            print(f"  - Taxa recarga: {context.recharge_rate}")
        except Exception as e:
            print(f"✗ Erro ao carregar instância: {e}")
            return
        
        # Testa múltiplos indivíduos
        print(f"\n[2] Testando {n_tests} indivíduos com force_battery_feasible=True")
        print("-" * 80)
        
        n_feasible = 0
        n_infeasible = 0
        infeasible_details = []
        
        for i in range(n_tests):
            # Gera permutação aleatória
            n_customers = len(context.customers)
            individual = np.random.permutation(n_customers).tolist()
            
            print(f"\n[Teste {i+1}/{n_tests}]")
            print(f"  Indivíduo: {individual[:10]}..." if len(individual) > 10 else f"  Indivíduo: {individual}")
            
            # Decodifica com force_battery_feasible=True e debug ativado para o primeiro teste inviável
            debug_mode = (i == 0) or (n_infeasible == 0 and i < 2)  # Debug no primeiro ou nos 2 primeiros se todos viáveis
            try:
                solution = decode(individual, context, force_battery_feasible=True, debug=debug_mode)
                
                # Verifica viabilidade
                is_feasible = solution.battery_violation <= 0.0
                g2 = solution.battery_violation
                
                if is_feasible:
                    n_feasible += 1
                    print(f"  ✓ VIÁVEL (G2 = {g2:.2f})")
                    print(f"    - Veículos: {solution.total_vehicles}")
                    print(f"    - Distância: {solution.total_distance:.2f}")
                    print(f"    - Custo: {solution.total_cost:.2f}")
                    print(f"    - Insatisfação: {solution.avg_dissatisfaction:.3f}")
                else:
                    n_infeasible += 1
                    print(f"  ✗ INVIÁVEL (G2 = {g2:.2f})")
                    print(f"    - Veículos: {solution.total_vehicles}")
                    print(f"    - Distância: {solution.total_distance:.2f}")
                    print(f"    - Custo: {solution.total_cost:.2f}")
                    print(f"    - Insatisfação: {solution.avg_dissatisfaction:.3f}")
                    
                    # Analisa violações
                    if solution.violations:
                        print(f"    - Violações encontradas:")
                        for violation in solution.violations[:3]:  # Mostra apenas as 3 primeiras
                            print(f"      * {violation}")
                        if len(solution.violations) > 3:
                            print(f"      ... e mais {len(solution.violations) - 3} violações")
                    
                    # Analisa rotas
                    print(f"    - Rotas: {len(solution.routes)}")
                    for route_idx, route in enumerate(solution.routes[:2]):  # Mostra apenas as 2 primeiras
                        print(f"      Rota {route.vehicle_id}: {len(route.steps)} passos")
                        # Verifica passos da rota para encontrar problema
                        for step_idx, step in enumerate(route.steps):
                            if step.battery_arrival < 0 or step.battery_departure < 0:
                                print(f"        Passo {step_idx}: {step.node.id} - Bateria negativa!")
                                print(f"          Arrival: {step.battery_arrival:.2f}, Departure: {step.battery_departure:.2f}")
                    
                    infeasible_details.append({
                        'individual': individual,  # Salva o indivíduo completo
                        'g2': g2,
                        'violations': solution.violations,
                        'routes': len(solution.routes)
                    })
            
            except Exception as e:
                print(f"  ✗ ERRO durante decodificação: {e}")
                import traceback
                traceback.print_exc()
                n_infeasible += 1
        
        # Estatísticas finais
        print("\n" + "=" * 80)
        print("RESUMO DOS TESTES")
        print("=" * 80)
        print(f"Total de testes: {n_tests}")
        print(f"Viáveis: {n_feasible} ({n_feasible/n_tests*100:.1f}%)")
        print(f"Inviáveis: {n_infeasible} ({n_infeasible/n_tests*100:.1f}%)")
        
        if n_infeasible > 0:
            print(f"\nAnálise das soluções inviáveis:")
            g2_values = [d['g2'] for d in infeasible_details]
            print(f"  - G2 médio: {np.mean(g2_values):.2f}")
            print(f"  - G2 mínimo: {np.min(g2_values):.2f}")
            print(f"  - G2 máximo: {np.max(g2_values):.2f}")
            
            # Conta tipos de violações
            violation_types = {}
            for detail in infeasible_details:
                for violation in detail['violations']:
                    if 'Bateria insuficiente' in violation:
                        violation_types['Bateria insuficiente'] = violation_types.get('Bateria insuficiente', 0) + 1
                    elif 'Não consegue' in violation:
                        violation_types['Não consegue'] = violation_types.get('Não consegue', 0) + 1
                    elif 'Cliente impossível' in violation:
                        violation_types['Cliente impossível'] = violation_types.get('Cliente impossível', 0) + 1
            
            if violation_types:
                print(f"  - Tipos de violações:")
                for vtype, count in violation_types.items():
                    print(f"    * {vtype}: {count}")
        
        print("\n" + "=" * 80)
        
        # Teste detalhado de um caso específico
        if n_infeasible > 0 and infeasible_details:
            print("\n[3] TESTE DETALHADO - Primeira solução inviável")
            print("-" * 80)
            test_individual = infeasible_details[0]['individual']
            print(f"Indivíduo: {test_individual[:10]}..." if len(test_individual) > 10 else f"Indivíduo: {test_individual}")
            print(f"  (Total de clientes: {len(test_individual)})")
            print("\nDecodificando com logs detalhados...")
            
            # Adiciona flag para ativar logs detalhados no decoder
            # (precisamos modificar o decoder para aceitar um parâmetro de debug)
            solution = decode(test_individual, context, force_battery_feasible=True, debug=True)
            print(f"\nResultado:")
            print(f"  - G2: {solution.battery_violation:.2f}")
            print(f"  - Viável: {solution.battery_violation <= 0.0}")
            print(f"  - Violações: {len(solution.violations)}")
            if solution.violations:
                for violation in solution.violations:
                    print(f"    * {violation}")
    
    finally:
        # Restaura stdout original e fecha arquivo
        sys.stdout = tee.stdout
        tee.close()
        print(f"\n✓ Logs salvos em: {log_file}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python test_decoder_feasibility.py <caminho_instancia> [n_tests]")
        print("Exemplo: python test_decoder_feasibility.py evrptw_instances/rc208_21.txt 10")
        sys.exit(1)
    
    instance_path = sys.argv[1]
    n_tests = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    # Tenta encontrar o arquivo em diferentes locais
    import os
    if not os.path.exists(instance_path):
        # Tenta em evrptw_instances/
        alt_path = os.path.join("evrptw_instances", os.path.basename(instance_path))
        if os.path.exists(alt_path):
            instance_path = alt_path
            print(f"Arquivo encontrado em: {instance_path}")
        else:
            # Tenta em instances/
            alt_path = os.path.join("instances", os.path.basename(instance_path))
            if os.path.exists(alt_path):
                instance_path = alt_path
                print(f"Arquivo encontrado em: {instance_path}")
            else:
                print(f"✗ Erro: Arquivo não encontrado: {sys.argv[1]}")
                print(f"  Tentado: {sys.argv[1]}")
                print(f"  Tentado: {os.path.join('evrptw_instances', os.path.basename(instance_path))}")
                print(f"  Tentado: {os.path.join('instances', os.path.basename(instance_path))}")
                sys.exit(1)
    
    test_decoder_feasibility(instance_path, n_tests)
