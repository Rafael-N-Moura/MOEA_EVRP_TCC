#!/bin/bash
# Script de teste para NSGA-III com 6 objetivos em instância grande
# Objetivo: Medir tempo de execução para avaliar viabilidade

INSTANCE="evrptw_instances/rc208_21.txt"
ALGORITHM="nsga3"
OBJECTIVES="vehicles distance duration time_window wait_time recharge_time"
N_GEN=50
POP_SIZE=126  # Será ajustado automaticamente para corresponder aos pontos de referência
N_PARTITIONS=4  # Para 6 objetivos: C(4+6-1, 6-1) = C(9,5) = 126 pontos

echo "=========================================="
echo "Teste de Performance: NSGA-III (6 Objetivos)"
echo "=========================================="
echo "Instância: $INSTANCE"
echo "Algoritmo: $ALGORITHM"
echo "Objetivos: $OBJECTIVES"
echo "Gerações: $N_GEN"
echo "População: $POP_SIZE (ajustado para pontos de referência)"
echo "Partições: $N_PARTITIONS"
echo "=========================================="
echo ""

python3 main.py "$INSTANCE" \
    --algorithm "$ALGORITHM" \
    --objectives $OBJECTIVES \
    --n-gen "$N_GEN" \
    --pop-size "$POP_SIZE" \
    --n-partitions "$N_PARTITIONS" \
    --no-verbose

echo ""
echo "=========================================="
echo "Teste concluído!"
echo "=========================================="
