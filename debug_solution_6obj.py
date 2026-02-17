"""
Script de diagnóstico para verificar se as 6 métricas estão sendo calculadas corretamente.
"""

from src.parser import parse_instance
from src.decoder import decode
import random

# Carrega instância
print("Carregando instância...")
context = parse_instance('evrptw_instances/rc208_21.txt')
print(f"✓ Instância carregada: {len(context.customers)} clientes\n")

# Testa algumas permutações
n_customers = len(context.customers)
random.seed(42)
perm = list(range(n_customers))
random.shuffle(perm)

print("="*80)
print("TESTE: Decodificação com 6 Objetivos")
print("="*80)

solution = decode(perm, context)

print(f"\nMétricas Básicas:")
print(f"  Veículos: {solution.total_vehicles}")
print(f"  Distância: {solution.total_distance:.2f}")
print(f"  Viável: {solution.is_feasible}")
print(f"  Violações: {len(solution.violations)}")

print(f"\n6 Objetivos Atômicos:")
print(f"  f1 (vehicles): {solution.val_vehicles}")
print(f"  f2 (distance): {solution.val_distance:.2f}")
print(f"  f3 (duration): {solution.val_duration:.2f}")
print(f"  f4 (time_window): {solution.val_time_window_violation:.2f}")
print(f"  f5 (wait_time): {solution.val_wait_time:.2f}")
print(f"  f6 (recharge_time): {solution.val_recharge_time:.2f}")

print(f"\nMétricas Agregadas (compatibilidade):")
print(f"  Custo total: {solution.total_cost:.2f}")
print(f"  Insatisfação média: {solution.avg_dissatisfaction:.4f}")

# Verifica se há problemas
print(f"\n" + "="*80)
print("DIAGNÓSTICO")
print("="*80)

if solution.val_vehicles == 0:
    print("⚠️  PROBLEMA: val_vehicles = 0 (nenhum veículo?)")
elif solution.val_vehicles > 100:
    print(f"⚠️  SUSPEITO: val_vehicles = {solution.val_vehicles} (muito alto?)")

if solution.val_distance == 0:
    print("⚠️  PROBLEMA: val_distance = 0 (nenhuma distância?)")

if solution.val_duration == 0:
    print("⚠️  PROBLEMA: val_duration = 0 (nenhuma duração?)")

if solution.val_wait_time > 100000:
    print(f"⚠️  PROBLEMA: val_wait_time = {solution.val_wait_time:.2f} (muito alto, possível offset?)")

if solution.val_recharge_time > 100000:
    print(f"⚠️  PROBLEMA: val_recharge_time = {solution.val_recharge_time:.2f} (muito alto, possível offset?)")

if not solution.is_feasible:
    print(f"⚠️  SOLUÇÃO INVIÁVEL: {len(solution.violations)} violações")
    print("   Primeiras 5 violações:")
    for v in solution.violations[:5]:
        print(f"     - {v}")

# Análise detalhada das rotas
print(f"\n" + "="*80)
print("ANÁLISE DETALHADA DAS ROTAS")
print("="*80)
print(f"Total de rotas: {len(solution.routes)}")

total_wait = 0.0
total_recharge = 0.0
total_duration_calc = 0.0

for i, route in enumerate(solution.routes[:3]):  # Primeiras 3 rotas
    print(f"\nRota {i+1} (Veículo {route.vehicle_id}):")
    print(f"  Steps: {len(route.steps)}")
    print(f"  Distância: {route.total_distance:.2f}")
    
    route_wait = sum(step.wait_time for step in route.steps)
    route_recharge = sum(step.recharge_time for step in route.steps)
    total_wait += route_wait
    total_recharge += route_recharge
    
    print(f"  Wait time (soma steps): {route_wait:.2f}")
    print(f"  Recharge time (soma steps): {route_recharge:.2f}")
    
    if route.steps:
        first = route.steps[0]
        last = route.steps[-1]
        route_duration = last.arrival_time - first.departure_time
        total_duration_calc += route_duration
        print(f"  Duração (last.arrival - first.departure): {route_duration:.2f}")

print(f"\nSoma manual:")
print(f"  Total wait_time: {total_wait:.2f} (Solution: {solution.val_wait_time:.2f})")
print(f"  Total recharge_time: {total_recharge:.2f} (Solution: {solution.val_recharge_time:.2f})")
print(f"  Total duration (primeiras 3 rotas): {total_duration_calc:.2f}")

if abs(total_wait - solution.val_wait_time) > 0.01:
    print(f"⚠️  DISCREPÂNCIA: wait_time calculado diferente!")
if abs(total_recharge - solution.val_recharge_time) > 0.01:
    print(f"⚠️  DISCREPÂNCIA: recharge_time calculado diferente!")

print("="*80)
