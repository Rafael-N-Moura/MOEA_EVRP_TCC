"""
Script de diagnóstico para verificar a taxa de viabilidade das soluções
geradas pela heurística construtiva.

Uso:
    python diagnostico_viabilidade.py <arquivo_instancia> [n_amostras] [seed]

Exemplo:
    python diagnostico_viabilidade.py evrptw_instances/rc208_21.txt 100 42
"""

import random
import sys
from collections import Counter
from typing import Dict
from src import parse_instance
from src.decoder import decode


def analisar_viabilidade(context, n_amostras: int = 100, seed: int = 42) -> Dict:
    """
    Analisa a viabilidade de uma amostra de soluções aleatórias.
    
    Args:
        context: Contexto do problema
        n_amostras: Número de soluções aleatórias para testar
        seed: Semente para reprodutibilidade
    
    Returns:
        Dicionário com estatísticas de viabilidade
    """
    random.seed(seed)
    n_customers = len(context.customers)
    
    # Estatísticas
    stats = {
        'total': 0,
        'viaveis': 0,
        'inviaveis': 0,
        'violacoes_por_tipo': Counter(),
        'violacoes_por_solucao': [],
        'veiculos_distribuicao': Counter(),
        'distancia_stats': {'min': float('inf'), 'max': 0, 'soma': 0, 'viaveis': []},
        'custo_stats': {'min': float('inf'), 'max': 0, 'soma': 0, 'viaveis': []},
        'insatisfacao_stats': {'min': float('inf'), 'max': 0, 'soma': 0, 'viaveis': []},
        'exemplos_inviaveis': []
    }
    
    print(f"Analisando {n_amostras} soluções aleatórias...")
    print("=" * 80)
    
    for i in range(n_amostras):
        # Gera permutação aleatória
        perm = list(range(n_customers))
        random.shuffle(perm)
        
        # Decodifica
        solution = decode(perm, context)
        
        # Atualiza estatísticas
        stats['total'] += 1
        if solution.is_feasible:
            stats['viaveis'] += 1
        else:
            stats['inviaveis'] += 1
            # Guarda exemplo de solução inviável (apenas primeiras 5)
            if len(stats['exemplos_inviaveis']) < 5:
                stats['exemplos_inviaveis'].append({
                    'permutacao': perm[:10],  # Primeiros 10 apenas
                    'violacoes': solution.violations[:5],  # Primeiras 5 violações
                    'veiculos': solution.total_vehicles,
                    'distancia': solution.total_distance
                })
        
        # Conta violações por tipo
        for violation in solution.violations:
            # Categoriza violação
            if 'Bateria' in violation or 'bateria' in violation.lower():
                stats['violacoes_por_tipo']['Bateria'] += 1
            elif 'carga' in violation.lower():
                stats['violacoes_por_tipo']['Carga'] += 1
            elif 'due_date' in violation.lower() or 'atraso' in violation.lower():
                stats['violacoes_por_tipo']['Tempo (soft)'] += 1
            else:
                stats['violacoes_por_tipo']['Outras'] += 1
        
        stats['violacoes_por_solucao'].append(len(solution.violations))
        stats['veiculos_distribuicao'][solution.total_vehicles] += 1
        
        # Estatísticas de distância
        if solution.total_distance < stats['distancia_stats']['min']:
            stats['distancia_stats']['min'] = solution.total_distance
        if solution.total_distance > stats['distancia_stats']['max']:
            stats['distancia_stats']['max'] = solution.total_distance
        stats['distancia_stats']['soma'] += solution.total_distance
        if solution.is_feasible:
            stats['distancia_stats']['viaveis'].append(solution.total_distance)
        
        # Estatísticas de custo
        if solution.total_cost < stats['custo_stats']['min']:
            stats['custo_stats']['min'] = solution.total_cost
        if solution.total_cost > stats['custo_stats']['max']:
            stats['custo_stats']['max'] = solution.total_cost
        stats['custo_stats']['soma'] += solution.total_cost
        if solution.is_feasible:
            stats['custo_stats']['viaveis'].append(solution.total_cost)
        
        # Estatísticas de insatisfação
        if solution.avg_dissatisfaction < stats['insatisfacao_stats']['min']:
            stats['insatisfacao_stats']['min'] = solution.avg_dissatisfaction
        if solution.avg_dissatisfaction > stats['insatisfacao_stats']['max']:
            stats['insatisfacao_stats']['max'] = solution.avg_dissatisfaction
        stats['insatisfacao_stats']['soma'] += solution.avg_dissatisfaction
        if solution.is_feasible:
            stats['insatisfacao_stats']['viaveis'].append(solution.avg_dissatisfaction)
        
        # Progresso
        if (i + 1) % 10 == 0:
            taxa_viabilidade = (stats['viaveis'] / stats['total']) * 100
            print(f"  Processadas {i+1}/{n_amostras} soluções - "
                  f"Viáveis: {stats['viaveis']} ({taxa_viabilidade:.1f}%)")
    
    return stats


def imprimir_relatorio(stats: Dict, context):
    """Imprime relatório detalhado das estatísticas."""
    print("\n" + "=" * 80)
    print("RELATÓRIO DE VIABILIDADE")
    print("=" * 80)
    
    # Resumo geral
    print(f"\n📊 RESUMO GERAL")
    print(f"  Total de soluções testadas: {stats['total']}")
    print(f"  Soluções viáveis: {stats['viaveis']} ({stats['viaveis']/stats['total']*100:.1f}%)")
    print(f"  Soluções inviáveis: {stats['inviaveis']} ({stats['inviaveis']/stats['total']*100:.1f}%)")
    
    if stats['inviaveis'] > 0:
        print(f"\n⚠️  ATENÇÃO: {stats['inviaveis']} soluções inviáveis detectadas!")
        print(f"   Taxa de inviabilidade: {stats['inviaveis']/stats['total']*100:.1f}%")
    
    # Violações
    print(f"\n🔍 ANÁLISE DE VIOLAÇÕES")
    total_violacoes = sum(stats['violacoes_por_solucao'])
    print(f"  Total de violações: {total_violacoes}")
    print(f"  Média de violações por solução: {total_violacoes/stats['total']:.2f}")
    
    if stats['violacoes_por_solucao']:
        max_violacoes = max(stats['violacoes_por_solucao'])
        min_violacoes = min(stats['violacoes_por_solucao'])
        print(f"  Mínimo de violações: {min_violacoes}")
        print(f"  Máximo de violações: {max_violacoes}")
    
    print(f"\n  Tipos de violações:")
    for tipo, count in stats['violacoes_por_tipo'].most_common():
        porcentagem = (count / total_violacoes * 100) if total_violacoes > 0 else 0
        print(f"    {tipo}: {count} ({porcentagem:.1f}%)")
    
    # Distribuição de veículos
    print(f"\n🚛 DISTRIBUIÇÃO DE VEÍCULOS")
    for n_veiculos in sorted(stats['veiculos_distribuicao'].keys()):
        count = stats['veiculos_distribuicao'][n_veiculos]
        porcentagem = (count / stats['total']) * 100
        print(f"  {n_veiculos} veículo(s): {count} soluções ({porcentagem:.1f}%)")
    
    # Estatísticas de métricas
    print(f"\n📈 ESTATÍSTICAS DE MÉTRICAS (TODAS AS SOLUÇÕES)")
    print(f"  Distância:")
    print(f"    Mínima: {stats['distancia_stats']['min']:.2f}")
    print(f"    Máxima: {stats['distancia_stats']['max']:.2f}")
    print(f"    Média: {stats['distancia_stats']['soma']/stats['total']:.2f}")
    
    print(f"  Custo:")
    print(f"    Mínimo: {stats['custo_stats']['min']:.2f}")
    print(f"    Máximo: {stats['custo_stats']['max']:.2f}")
    print(f"    Média: {stats['custo_stats']['soma']/stats['total']:.2f}")
    
    print(f"  Insatisfação:")
    print(f"    Mínima: {stats['insatisfacao_stats']['min']:.4f}")
    print(f"    Máxima: {stats['insatisfacao_stats']['max']:.4f}")
    print(f"    Média: {stats['insatisfacao_stats']['soma']/stats['total']:.4f}")
    
    # Estatísticas apenas de soluções viáveis
    if stats['viaveis'] > 0:
        print(f"\n✅ ESTATÍSTICAS DE MÉTRICAS (APENAS SOLUÇÕES VIÁVEIS)")
        if stats['distancia_stats']['viaveis']:
            dist_viaveis = stats['distancia_stats']['viaveis']
            print(f"  Distância:")
            print(f"    Mínima: {min(dist_viaveis):.2f}")
            print(f"    Máxima: {max(dist_viaveis):.2f}")
            print(f"    Média: {sum(dist_viaveis)/len(dist_viaveis):.2f}")
        
        if stats['custo_stats']['viaveis']:
            custo_viaveis = stats['custo_stats']['viaveis']
            print(f"  Custo:")
            print(f"    Mínimo: {min(custo_viaveis):.2f}")
            print(f"    Máximo: {max(custo_viaveis):.2f}")
            print(f"    Média: {sum(custo_viaveis)/len(custo_viaveis):.2f}")
        
        if stats['insatisfacao_stats']['viaveis']:
            insat_viaveis = stats['insatisfacao_stats']['viaveis']
            print(f"  Insatisfação:")
            print(f"    Mínima: {min(insat_viaveis):.4f}")
            print(f"    Máxima: {max(insat_viaveis):.4f}")
            print(f"    Média: {sum(insat_viaveis)/len(insat_viaveis):.4f}")
    
    # Exemplos de soluções inviáveis
    if stats['exemplos_inviaveis']:
        print(f"\n❌ EXEMPLOS DE SOLUÇÕES INVIÁVEIS")
        for i, exemplo in enumerate(stats['exemplos_inviaveis'], 1):
            print(f"\n  Exemplo {i}:")
            print(f"    Veículos: {exemplo['veiculos']}")
            print(f"    Distância: {exemplo['distancia']:.2f}")
            print(f"    Primeiros clientes: {exemplo['permutacao']}")
            print(f"    Primeiras violações:")
            for violacao in exemplo['violacoes']:
                print(f"      - {violacao[:100]}")  # Limita tamanho
    
    # Diagnóstico
    print(f"\n🔬 DIAGNÓSTICO")
    taxa_inviabilidade = (stats['inviaveis'] / stats['total']) * 100
    
    if taxa_inviabilidade > 50:
        print(f"  ⚠️  PROBLEMA CRÍTICO: Mais de 50% das soluções são inviáveis!")
        print(f"     A heurística construtiva precisa ser melhorada urgentemente.")
    elif taxa_inviabilidade > 20:
        print(f"  ⚠️  ATENÇÃO: Mais de 20% das soluções são inviáveis.")
        print(f"     Considere melhorar a heurística construtiva.")
    elif taxa_inviabilidade > 0:
        print(f"  ℹ️  Algumas soluções inviáveis detectadas, mas taxa aceitável.")
    else:
        print(f"  ✅ Todas as soluções são viáveis!")
    
    # Verifica tipo de violação mais comum
    if stats['violacoes_por_tipo']:
        tipo_mais_comum = stats['violacoes_por_tipo'].most_common(1)[0]
        if tipo_mais_comum[0] == 'Bateria':
            print(f"\n  🔋 Violações de bateria são as mais comuns ({tipo_mais_comum[1]} ocorrências).")
            print(f"     Sugestão: Melhorar estratégia de recarga preventiva.")
        elif tipo_mais_comum[0] == 'Carga':
            print(f"\n  📦 Violações de carga são as mais comuns ({tipo_mais_comum[1]} ocorrências).")
            print(f"     Sugestão: Verificar lógica de abertura de novos veículos.")
    
    print("\n" + "=" * 80)


def main():
    """Função principal"""
    if len(sys.argv) < 2:
        print("Uso: python diagnostico_viabilidade.py <arquivo_instancia> [n_amostras] [seed]")
        print("\nExemplo:")
        print("  python diagnostico_viabilidade.py evrptw_instances/rc208_21.txt 100 42")
        sys.exit(1)
    
    arquivo_instancia = sys.argv[1]
    n_amostras = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 42
    
    print("=" * 80)
    print("DIAGNÓSTICO DE VIABILIDADE - HEURÍSTICA CONSTRUTIVA")
    print("=" * 80)
    print(f"\nInstância: {arquivo_instancia}")
    print(f"Amostras: {n_amostras}")
    print(f"Seed: {seed}")
    
    # Carrega instância
    try:
        print(f"\nCarregando instância...")
        context = parse_instance(arquivo_instancia)
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
        sys.exit(1)
    
    # Analisa viabilidade
    stats = analisar_viabilidade(context, n_amostras, seed)
    
    # Imprime relatório
    imprimir_relatorio(stats, context)
    
    print("\n✓ Diagnóstico concluído!")


if __name__ == '__main__':
    main()
