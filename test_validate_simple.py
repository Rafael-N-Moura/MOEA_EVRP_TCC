"""
Teste simples para validar a função _validate_and_fix_pop_X.
"""

import numpy as np
from pymoo.core.population import Population
from src.battery_focused_nsga2 import BatteryFocusedNSGA2


class MockProblem:
    """Mock do Problem para testes."""
    def __init__(self, n_var=100):
        self.n_var = n_var


def test_basic():
    """Teste básico: X correto deve ser preservado."""
    print("Teste 1: X correto deve ser preservado")
    problem = MockProblem(n_var=50)
    
    # Cria população com X correto
    X = np.random.permutation(50).reshape(1, 50)
    pop = Population.new("X", X)
    
    # Valida (não deve modificar)
    pop_validated = BatteryFocusedNSGA2._validate_and_fix_pop_X(pop, problem)
    
    # Verifica que é a mesma população (não foi recriada)
    assert pop_validated is pop, "População correta não deveria ser recriada"
    print("  ✓ Passou: X correto foi preservado")
    
    # Verifica que X está correto
    assert isinstance(pop[0].X, np.ndarray)
    assert pop[0].X.ndim == 1
    assert pop[0].X.shape[0] == problem.n_var
    print("  ✓ Passou: X tem formato correto")


def test_wrong_shape():
    """Teste: X com shape incorreto deve gerar ValueError."""
    print("\nTeste 2: X com shape incorreto deve gerar ValueError")
    problem = MockProblem(n_var=50)
    
    # Cria população com X de tamanho incorreto
    X_wrong = np.random.permutation(30).reshape(1, 30)  # Tamanho 30 ao invés de 50
    pop = Population.new("X", X_wrong)
    
    # Tenta validar (deve gerar ValueError)
    try:
        BatteryFocusedNSGA2._validate_and_fix_pop_X(pop, problem)
        print("  ✗ Falhou: Deveria ter gerado ValueError")
        assert False, "Deveria ter gerado ValueError"
    except ValueError as e:
        print(f"  ✓ Passou: ValueError gerado corretamente: {str(e)[:50]}...")


def test_wrong_dtype():
    """Teste: X com dtype incorreto deve ser corrigido."""
    print("\nTeste 3: X com dtype incorreto deve ser corrigido")
    problem = MockProblem(n_var=50)
    
    # Cria população com X float
    X_float = np.random.permutation(50).reshape(1, 50).astype(float)
    pop = Population.new("X", X_float)
    
    # Valida (deve corrigir dtype)
    pop_validated = BatteryFocusedNSGA2._validate_and_fix_pop_X(pop, problem, log_prefix="[TEST] ")
    
    # Verifica que dtype foi corrigido
    assert pop_validated[0].X.dtype == int or pop_validated[0].X.dtype == np.int64 or pop_validated[0].X.dtype == np.int32
    print("  ✓ Passou: dtype foi corrigido para int")
    assert pop_validated is not pop, "População com dtype incorreto deveria ser recriada"
    print("  ✓ Passou: População foi recriada (correto)")


def test_preserves_F_and_G():
    """Teste: F e G devem ser preservados após correção."""
    print("\nTeste 4: F e G devem ser preservados após correção")
    problem = MockProblem(n_var=50)
    
    # Cria população com X float (será corrigido)
    X_float = np.random.permutation(50).reshape(1, 50).astype(float)
    pop = Population.new("X", X_float)
    
    # Adiciona F e G
    F_original = np.array([[100.0, 0.5]])
    G_original = np.array([[0.0, 0.0]])
    pop.set("F", F_original)
    pop.set("G", G_original)
    
    # Valida (deve corrigir X mas preservar F e G)
    pop_validated = BatteryFocusedNSGA2._validate_and_fix_pop_X(pop, problem)
    
    # Verifica que F e G foram preservados
    assert pop_validated.has("F"), "F deveria ser preservado"
    assert pop_validated.has("G"), "G deveria ser preservado"
    assert np.array_equal(pop_validated.get("F"), F_original), "F deveria ser igual ao original"
    assert np.array_equal(pop_validated.get("G"), G_original), "G deveria ser igual ao original"
    print("  ✓ Passou: F e G foram preservados")


def test_multiple_individuals():
    """Teste: Validação com múltiplos indivíduos."""
    print("\nTeste 5: Validação com múltiplos indivíduos")
    problem = MockProblem(n_var=50)
    
    # Cria população com 10 indivíduos
    X = np.array([np.random.permutation(50) for _ in range(10)])
    pop = Population.new("X", X)
    
    # Adiciona F e G
    F = np.random.rand(10, 2) * 100
    G = np.random.rand(10, 2) * 10
    pop.set("F", F)
    pop.set("G", G)
    
    # Valida
    pop_validated = BatteryFocusedNSGA2._validate_and_fix_pop_X(pop, problem)
    
    # Verifica que todos os X estão corretos
    for i in range(len(pop_validated)):
        assert isinstance(pop_validated[i].X, np.ndarray), f"Individual {i} X não é numpy array"
        assert pop_validated[i].X.ndim == 1, f"Individual {i} X não é 1D"
        assert pop_validated[i].X.shape[0] == problem.n_var, f"Individual {i} X shape incorreto"
    
    print(f"  ✓ Passou: Todos os {len(pop_validated)} indivíduos têm X correto")
    
    # Verifica que F e G foram preservados
    assert np.array_equal(pop_validated.get("F"), F)
    assert np.array_equal(pop_validated.get("G"), G)
    print("  ✓ Passou: F e G foram preservados para todos os indivíduos")


if __name__ == "__main__":
    print("=" * 60)
    print("Testes da função _validate_and_fix_pop_X")
    print("=" * 60)
    
    try:
        test_basic()
        test_wrong_shape()
        test_wrong_dtype()
        test_preserves_F_and_G()
        test_multiple_individuals()
        
        print("\n" + "=" * 60)
        print("✓ Todos os testes passaram!")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ Erro durante os testes: {e}")
        import traceback
        traceback.print_exc()
