"""
Script de teste para verificar se o decoder gera soluções diferentes
para diferentes permutações em uma instância maior (com novos objetivos: Custo e Insatisfação).
"""

from src.parser import parse_instance
from src.decoder import decode
import random

# Carrega instância maior
print("Carregando instância maior...")
context = parse_instance('evrptw_instances/r101_21.txt')
print(f"✓ Instância carregada: {len(context.customers)} clientes")
print(f"  Capacidade veículo: {context.vehicle_capacity}")
print(f"  Capacidade bateria: {context.battery_capacity}")
print(f"  Custo veículo: {context.vehicle_cost}")
print(f"  Custo distância: {context.distance_cost}")
print(f"  Tolerância atraso: {context.delay_tolerance}\n")

# Gera algumas permutações diferentes
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

print("="*60)
print("TESTE: Decoder com Diferentes Permutações (Instância Maior)")
print("="*60)

results = []
for name, perm in permutations:
    solution = decode(perm, context)
    results.append({
        'name': name,
        'vehicles': solution.total_vehicles,
        'distance': solution.total_distance,
        'cost': solution.total_cost,  # f1: Custo
        'dissatisfaction': solution.avg_dissatisfaction,  # f2: Insatisfação
        'feasible': solution.is_feasible,
        'violations': len(solution.violations)
    })

# Exibe resultados
print(f"\n{'Nome':<25} {'Veíc':<6} {'Dist':<10} {'Custo (f1)':<12} {'Insat (f2)':<10} {'Viável':<8} {'Viol'}")
print("-" * 100)

for r in results:
    print(f"{r['name']:<25} {r['vehicles']:<6} {r['distance']:<10.2f} {r['cost']:<12.2f} "
          f"{r['dissatisfaction']:<10.4f} {str(r['feasible']):<8} {r['violations']}")

# Verifica se há variação
f1_values = [r['cost'] for r in results]
f2_values = [r['dissatisfaction'] for r in results]
vehicles_values = [r['vehicles'] for r in results]
distance_values = [r['distance'] for r in results]

print("\n" + "="*70)
print("ANÁLISE - OBJETIVOS (f1 e f2)")
print("="*70)
print(f"Valores únicos de f1 (custo): {len(set(f1_values))} / {len(results)}")
print(f"Valores únicos de f2 (insatisfação): {len(set(f2_values))} / {len(results)}")
print(f"Range de f1 (custo): {min(f1_values):.2f} a {max(f1_values):.2f}")
print(f"Range de f2 (insatisfação): {min(f2_values):.4f} a {max(f2_values):.4f}")

print("\n" + "="*70)
print("ANÁLISE - MÉTRICAS BÁSICAS")
print("="*70)
print(f"Valores únicos de veículos: {len(set(vehicles_values))} / {len(results)}")
print(f"Valores únicos de distância: {len(set(distance_values))} / {len(results)}")
print(f"Range de veículos: {min(vehicles_values)} a {max(vehicles_values)}")
print(f"Range de distância: {min(distance_values):.2f} a {max(distance_values):.2f}")

# Análise de dominância
print("\n" + "="*70)
print("ANÁLISE DE DOMINÂNCIA (f1 vs f2)")
print("="*70)

# Verifica quantas soluções são não-dominadas
non_dominated = []
for i, r1 in enumerate(results):
    is_dominated = False
    for j, r2 in enumerate(results):
        if i != j:
            # r2 domina r1 se: f1(r2) <= f1(r1) E f2(r2) <= f2(r1) E pelo menos um é estritamente menor
            if (r2['cost'] <= r1['cost'] and r2['dissatisfaction'] <= r1['dissatisfaction'] and 
                (r2['cost'] < r1['cost'] or r2['dissatisfaction'] < r1['dissatisfaction'])):
                is_dominated = True
                break
    if not is_dominated:
        non_dominated.append((i, r1))

print(f"Soluções não-dominadas: {len(non_dominated)} / {len(results)}")
for idx, sol in non_dominated:
    print(f"  - {results[idx]['name']}: Custo={sol['cost']:.2f}, Insatisfação={sol['dissatisfaction']:.4f}")

# Diagnóstico
print("\n" + "="*70)
print("DIAGNÓSTICO")
print("="*70)

if len(set(f1_values)) == 1 and len(set(f2_values)) == 1:
    print("\n⚠️  PROBLEMA CRÍTICO: Todas as permutações geram a mesma solução!")
    print("   Custo e insatisfação idênticos em todas as permutações.")
    print("   Isso explica por que n_nds = 1 sempre.")
    print("   Possíveis causas:")
    print("   1. O decoder não está usando a ordem da permutação corretamente")
    print("   2. Há um bug que faz todas as permutações resultarem na mesma solução")
    print("   3. A heurística construtiva está ignorando a ordem")
elif len(set(f1_values)) == 1:
    print("\n⚠️  PROBLEMA: Todas as permutações geram o mesmo custo (f1)")
    print("   Mas insatisfação varia - isso é parcialmente bom")
    print("   Possível causa: Mesmo número de veículos E mesma distância sempre")
    if len(non_dominated) == 1:
        print("   ⚠️  Apenas 1 solução não-dominada - uma solução domina todas")
elif len(set(f2_values)) == 1:
    print("\n⚠️  PROBLEMA: Todas as permutações geram a mesma insatisfação (f2)")
    print("   Mas custo varia - isso é parcialmente bom")
    if f2_values[0] >= 0.99:
        print("   ⚠️  Insatisfação máxima (1.0) - todos clientes com atrasos muito grandes")
        print("   Solução: Aumentar delay_tolerance ou verificar cálculo de satisfação")
    if len(non_dominated) == 1:
        print("   ⚠️  Apenas 1 solução não-dominada - uma solução domina todas")
elif len(non_dominated) == 1:
    print("\n⚠️  PROBLEMA: Apenas 1 solução não-dominada")
    print("   Isso explica n_nds = 1 no NSGA-II")
    print("   Possível causa: Uma solução domina todas as outras")
    print("   Mesmo com variação em f1 e f2, uma solução é melhor em ambos")
elif len(non_dominated) > 1:
    print(f"\n✓ Múltiplas soluções não-dominadas encontradas ({len(non_dominated)})")
    print("  O decoder está gerando diversidade nos objetivos.")
    print("  Se n_nds ainda for 1 no NSGA-II, o problema pode estar:")
    print("  1. No algoritmo (não está mantendo diversidade)")
    print("  2. Na população inicial (muito pequena ou pouco diversa)")
    print("  3. Nos operadores genéticos (crossover/mutation muito conservadores)")
    print("  4. Na convergência prematura (algoritmo converge muito rápido)")

print("="*70)
