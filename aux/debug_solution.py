"""
Script de diagnóstico para verificar por que todas as soluções têm os mesmos valores.
"""

from src.parser import parse_instance
from src.decoder import decode
import random

# Carrega instância
print("Carregando instância...")
context = parse_instance('evrptw_instances/r101_21.txt')
print(f"✓ Instância carregada: {len(context.customers)} clientes")
print(f"  Capacidade veículo: {context.vehicle_capacity}")
print(f"  Capacidade bateria: {context.battery_capacity}")
print(f"  Custo veículo: {context.vehicle_cost}")
print(f"  Custo distância: {context.distance_cost}")
print(f"  Tolerância atraso: {context.delay_tolerance}\n")

# Testa algumas permutações diferentes
n_customers = len(context.customers)
permutations = []

# Permutação 1: ordem original
perm1 = list(range(n_customers))
permutations.append(("Original", perm1))

# Permutação 2: ordem reversa
perm2 = list(reversed(range(n_customers)))
permutations.append(("Reversa", perm2))

# Permutação 3-5: aleatórias
for i in range(3):
    random.seed(42 + i)
    perm = list(range(n_customers))
    random.shuffle(perm)
    permutations.append((f"Aleatória {i+1}", perm))

print("="*70)
print("DIAGNÓSTICO: Análise Detalhada das Soluções")
print("="*70)

results = []
for name, perm in permutations:
    solution = decode(perm, context)
    results.append({
        'name': name,
        'vehicles': solution.total_vehicles,
        'distance': solution.total_distance,
        'cost': solution.total_cost,
        'dissatisfaction': solution.avg_dissatisfaction,
        'feasible': solution.is_feasible,
        'violations': len(solution.violations),
        'customer_satisfactions': []
    })
    
    # Coleta satisfações dos clientes
    for route in solution.routes:
        for step in route.steps:
            if step.node.type.value == 'c':  # Cliente
                results[-1]['customer_satisfactions'].append({
                    'customer_id': step.node.id,
                    'arrival': step.arrival_time,
                    'due_date': step.node.due_date,
                    'delay': max(0, step.arrival_time - step.node.due_date),
                    'satisfaction': step.satisfaction_score
                })

# Exibe resultados
print(f"\n{'Nome':<20} {'Veíc':<6} {'Dist':<10} {'Custo':<12} {'Insat':<8} {'Viável':<8} {'Viol':<6}")
print("-" * 80)

for r in results:
    print(f"{r['name']:<20} {r['vehicles']:<6} {r['distance']:<10.2f} {r['cost']:<12.2f} "
          f"{r['dissatisfaction']:<8.4f} {str(r['feasible']):<8} {r['violations']:<6}")

# Análise detalhada
print("\n" + "="*70)
print("ANÁLISE DETALHADA")
print("="*70)

# Verifica variação
f1_values = [r['cost'] for r in results]
f2_values = [r['dissatisfaction'] for r in results]

print(f"\nVariação de Custo (f1):")
print(f"  Valores únicos: {len(set(f1_values))} / {len(results)}")
print(f"  Range: {min(f1_values):.2f} a {max(f1_values):.2f}")

print(f"\nVariação de Insatisfação (f2):")
print(f"  Valores únicos: {len(set(f2_values))} / {len(results)}")
print(f"  Range: {min(f2_values):.4f} a {max(f2_values):.4f}")

# Análise de satisfação dos clientes
print(f"\nAnálise de Satisfação dos Clientes (primeira solução):")
if results[0]['customer_satisfactions']:
    satisfactions = [c['satisfaction'] for c in results[0]['customer_satisfactions']]
    delays = [c['delay'] for c in results[0]['customer_satisfactions']]
    
    print(f"  Total de clientes: {len(satisfactions)}")
    print(f"  Clientes com atraso: {sum(1 for d in delays if d > 0)}")
    print(f"  Satisfação média: {sum(satisfactions) / len(satisfactions):.4f}")
    print(f"  Satisfação min: {min(satisfactions):.4f}, max: {max(satisfactions):.4f}")
    print(f"  Atraso médio: {sum(delays) / len(delays):.2f}")
    print(f"  Atraso máximo: {max(delays):.2f}")
    
    # Mostra alguns exemplos
    print(f"\n  Exemplos de clientes (primeiros 5):")
    for i, c in enumerate(results[0]['customer_satisfactions'][:5]):
        print(f"    {c['customer_id']}: chegada={c['arrival']:.2f}, due={c['due_date']:.2f}, "
              f"atraso={c['delay']:.2f}, satisfação={c['satisfaction']:.4f}")

# Verifica se todas as soluções têm insatisfação máxima
if all(r['dissatisfaction'] >= 0.99 for r in results):
    print("\n⚠️  PROBLEMA DETECTADO: Todas as soluções têm insatisfação máxima (1.0)")
    print("   Isso significa que todos os clientes estão sendo atendidos com muito atraso.")
    print("   Possíveis causas:")
    print("   1. Tolerância de atraso muito baixa (delay_tolerance muito pequeno)")
    print("   2. Problema no cálculo de satisfação")
    print("   3. Todas as rotas estão violando janelas de tempo severamente")

# Verifica se todas as soluções têm mesmo custo
if len(set(f1_values)) == 1:
    print("\n⚠️  PROBLEMA DETECTADO: Todas as soluções têm o mesmo custo")
    print("   Isso significa que todas têm mesmo número de veículos E mesma distância.")
    print("   Possíveis causas:")
    print("   1. Heurística construtiva sempre gera mesma solução")
    print("   2. Problema na ordem de processamento dos clientes")
    print("   3. Restrições muito restritivas (sempre precisa mesmo número de veículos)")

print("="*70)
