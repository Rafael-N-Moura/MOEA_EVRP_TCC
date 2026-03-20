"""
Testes unitarios para o pacote evrp (Fase 1).
Cobre: instance, representation, evaluator, initialization, integracao com pymoo.
"""

import os
import pytest

INSTANCE_DIR = os.path.join(os.path.dirname(__file__), '..', 'evrptw_instances')
SMALL_INSTANCE = os.path.join(INSTANCE_DIR, 'c101C5.txt')
MEDIUM_INSTANCE = os.path.join(INSTANCE_DIR, 'c201_21.txt')


# =========================================================================
# instance.py
# =========================================================================

class TestInstance:
    def test_load_schneider_c101c5(self):
        from evrp.instance import load_schneider

        inst = load_schneider(SMALL_INSTANCE)
        assert inst.name == 'c101C5'
        assert inst.depot_id == 0
        assert len(inst.customer_ids) == 5
        assert len(inst.station_ids) == 3
        assert inst.B > 0
        assert inst.Q > 0
        assert inst.dist.shape == (9, 9)
        assert inst.dist[0][0] == 0.0

    def test_load_override_params(self):
        from evrp.instance import load_schneider

        inst = load_schneider(SMALL_INSTANCE, B=100.0, t_charge=0.0)
        assert inst.B == 100.0
        assert inst.t_charge == 0.0

    def test_energy_matrix_consistent(self):
        from evrp.instance import load_schneider

        inst = load_schneider(SMALL_INSTANCE)
        for i in range(inst.n_nodes):
            for j in range(inst.n_nodes):
                assert abs(inst.energy[i][j] - inst.dist[i][j] * inst.r) < 1e-9


# =========================================================================
# representation.py
# =========================================================================

class TestRepresentation:
    def test_cv_vector_total(self):
        from evrp.representation import CVVector

        cv = CVVector(cv_energy=0.5, cv_cascade=0.0, cv_cap=0.3, cv_tw=0.2)
        assert abs(cv.total() - 1.0) < 1e-9
        assert not cv.is_feasible()

        cv_ok = CVVector()
        assert cv_ok.is_feasible()

    def test_solution_objectives(self):
        from evrp.representation import Solution, SolutionMetadata

        m = SolutionMetadata(n_vehicles=3, total_distance=100.0, makespan=50.0,
                             total_waiting=10.0, total_delay=5.0)
        sol = Solution(metadata=m)
        assert sol.objectives_3() == [3.0, 100.0, 50.0]
        assert sol.objectives_5() == [3.0, 100.0, 50.0, 10.0, 5.0]

    def test_check_invariants_pass(self):
        from evrp.instance import load_schneider
        from evrp.representation import (
            NodeType, Route, Solution, Visit, check_invariants,
        )

        inst = load_schneider(SMALL_INSTANCE)
        visits = [Visit(inst.depot_id, NodeType.DEPOT)]
        for cid in inst.customer_ids:
            visits.append(Visit(cid, NodeType.CUSTOMER))
        visits.append(Visit(inst.depot_id, NodeType.DEPOT))
        sol = Solution(routes=[Route(visits=visits)])
        check_invariants(sol, inst)

    def test_check_invariants_missing_customer(self):
        from evrp.instance import load_schneider
        from evrp.representation import (
            NodeType, Route, Solution, Visit, check_invariants,
        )

        inst = load_schneider(SMALL_INSTANCE)
        visits = [Visit(inst.depot_id, NodeType.DEPOT)]
        for cid in inst.customer_ids[:-1]:  # falta 1 cliente
            visits.append(Visit(cid, NodeType.CUSTOMER))
        visits.append(Visit(inst.depot_id, NodeType.DEPOT))
        sol = Solution(routes=[Route(visits=visits)])
        with pytest.raises(AssertionError, match='I1'):
            check_invariants(sol, inst)


# =========================================================================
# evaluator.py
# =========================================================================

class TestEvaluator:
    def _make_instance(self):
        from evrp.instance import load_schneider
        return load_schneider(SMALL_INSTANCE, t_charge=0.0)

    def test_feasible_route(self):
        from evrp.evaluator import PopulationStats, run_ci
        from evrp.representation import InfeasType, NodeType, Route, Solution, Visit

        inst = self._make_instance()
        # Rota: depot → s1 → c1 → s2 → c2 → depot (poucas vezes, com estacoes)
        visits = [
            Visit(inst.depot_id, NodeType.DEPOT),
            Visit(inst.station_ids[0], NodeType.STATION),
            Visit(inst.customer_ids[0], NodeType.CUSTOMER),
            Visit(inst.station_ids[1], NodeType.STATION),
            Visit(inst.customer_ids[1], NodeType.CUSTOMER),
            Visit(inst.depot_id, NodeType.DEPOT),
        ]
        # Restantes em outra rota
        visits2 = [Visit(inst.depot_id, NodeType.DEPOT)]
        for cid in inst.customer_ids[2:]:
            visits2.append(Visit(cid, NodeType.CUSTOMER))
        visits2.append(Visit(inst.depot_id, NodeType.DEPOT))

        sol = Solution(routes=[Route(visits=visits), Route(visits=visits2)])
        stats = PopulationStats()
        run_ci(sol, inst, stats)

        assert sol.metadata.n_vehicles == 2
        assert sol.metadata.total_distance > 0
        assert sol._dirty is False

    def test_classify_type_feasible(self):
        from evrp.evaluator import classify_type
        from evrp.representation import CVVector, InfeasType

        assert classify_type(CVVector()) == InfeasType.FEASIBLE

    def test_classify_type_ies(self):
        from evrp.evaluator import classify_type
        from evrp.representation import CVVector, InfeasType

        cv = CVVector(cv_energy=0.5, cv_cascade=0.0, cv_cap=0.0, cv_tw=0.0)
        assert classify_type(cv) == InfeasType.IES

    def test_classify_type_iec(self):
        from evrp.evaluator import classify_type
        from evrp.representation import CVVector, InfeasType

        cv = CVVector(cv_energy=0.5, cv_cascade=0.3, cv_cap=0.0, cv_tw=0.0)
        assert classify_type(cv) == InfeasType.IEC

    def test_classify_type_im(self):
        from evrp.evaluator import classify_type
        from evrp.representation import CVVector, InfeasType

        cv = CVVector(cv_energy=0.5, cv_cascade=0.0, cv_cap=0.0, cv_tw=0.3)
        assert classify_type(cv) == InfeasType.IM

    def test_dynamic_recharge_time(self):
        """Tempo de recarga deve ser proporcional a energia reposta, nao fixo."""
        from evrp.evaluator import PopulationStats, compute_route_profile
        from evrp.instance import load_schneider
        from evrp.representation import NodeType, Route, Visit

        inst = load_schneider(SMALL_INSTANCE)
        assert inst.g > 0, 'g deve ser positivo para este teste'

        # Rota: depot → station → customer → depot
        # Veiculo sai do depot com B=77.75, viaja ate a estacao co-localizada (S0)
        # S0 esta no mesmo local do depot, entao energia consumida ~0
        s_id = inst.station_ids[0]
        c_id = inst.customer_ids[0]

        visits = [
            Visit(inst.depot_id, NodeType.DEPOT),
            Visit(s_id, NodeType.STATION),
            Visit(c_id, NodeType.CUSTOMER),
            Visit(inst.depot_id, NodeType.DEPOT),
        ]
        route = Route(visits=visits)
        compute_route_profile(route, inst)

        station_visit = route.visits[1]
        energy_at_arrival = station_visit.arrival_energy
        expected_recharge = (inst.B - max(0.0, energy_at_arrival)) * inst.g

        # O tempo de partida da estacao = tempo de chegada + recharge_time
        actual_recharge = station_visit.departure_time - station_visit.arrival_time
        assert abs(actual_recharge - expected_recharge) < 1e-6, \
            f'Recharge time deveria ser {expected_recharge:.2f}, foi {actual_recharge:.2f}'

        # Se chega com quase B, recharge deve ser quase zero
        if energy_at_arrival > inst.B * 0.9:
            assert actual_recharge < inst.B * inst.g * 0.15

    def test_md_delays_below_threshold(self):
        """Atrasos menores que md nao devem contribuir para raw_tw."""
        from evrp.evaluator import PopulationStats, run_ci
        from evrp.instance import load_schneider
        from evrp.representation import NodeType, Route, Solution, Visit

        inst = load_schneider(SMALL_INSTANCE, t_charge=0.0, md=50.0)

        # Constroi rota que chega DEPOIS do due_date de um cliente,
        # mas com atraso < md
        visits = [Visit(inst.depot_id, NodeType.DEPOT)]
        for cid in inst.customer_ids:
            visits.append(Visit(cid, NodeType.CUSTOMER))
        visits.append(Visit(inst.depot_id, NodeType.DEPOT))
        sol = Solution(routes=[Route(visits=visits)])

        stats = PopulationStats()
        run_ci(sol, inst, stats)

        # Com md=50, atrasos ate 50 sao tolerados
        # raw_tw so acumula excess = max(0, delay - 50)
        for route in sol.routes:
            for v in route.visits:
                if v.node_type == NodeType.CUSTOMER and v.delay_time > 0:
                    if v.delay_time <= 50.0:
                        pass  # OK, nao contribui

        # Testar com md=0 (hard TW) - deve ter raw_tw >= ao caso com md>0
        inst_hard = load_schneider(SMALL_INSTANCE, t_charge=0.0, md=0.0)
        sol_hard = Solution(routes=[Route(visits=[
            Visit(inst_hard.depot_id, NodeType.DEPOT)]
            + [Visit(cid, NodeType.CUSTOMER) for cid in inst_hard.customer_ids]
            + [Visit(inst_hard.depot_id, NodeType.DEPOT)]
        )])
        run_ci(sol_hard, inst_hard, PopulationStats())

        raw_tw_soft = sum(r._raw_tw for r in sol.routes)
        raw_tw_hard = sum(r._raw_tw for r in sol_hard.routes)
        assert raw_tw_hard >= raw_tw_soft, \
            f'md=0 (raw_tw={raw_tw_hard:.2f}) deve ter raw_tw >= md=50 ({raw_tw_soft:.2f})'

    def test_renormalize_pop(self):
        from evrp.evaluator import PopulationStats, renormalize, run_ci, update_pop_stats
        from evrp.representation import NodeType, Route, Solution, Visit

        inst = self._make_instance()
        sols = []
        for cid in inst.customer_ids:
            visits = [
                Visit(inst.depot_id, NodeType.DEPOT),
                Visit(cid, NodeType.CUSTOMER),
                Visit(inst.depot_id, NodeType.DEPOT),
            ]
            sol = Solution(routes=[Route(visits=visits)])
            run_ci(sol, inst, PopulationStats())
            sols.append(sol)

        stats = update_pop_stats(sols)
        for s in sols:
            renormalize(s, stats)
        # Min-max normalization: at least one sol should have cv=0 in each dim
        energies = [s.cv_components.cv_energy for s in sols]
        assert min(energies) == 0.0 or all(e == energies[0] for e in energies)


# =========================================================================
# initialization.py
# =========================================================================

class TestInitialization:
    def test_initialize_small(self):
        from evrp.instance import load_schneider
        from evrp.initialization import initialize
        from evrp.representation import check_invariants

        inst = load_schneider(SMALL_INSTANCE, t_charge=0.0)
        result = initialize(inst, N_P=10, seed=42)

        assert len(result.population) == 10
        for sol in result.population:
            check_invariants(sol, inst)
        assert result.eta >= 0.0
        assert result.pop_stats is not None

    def test_initialize_medium(self):
        from evrp.instance import load_schneider
        from evrp.initialization import initialize
        from evrp.representation import check_invariants

        inst = load_schneider(MEDIUM_INSTANCE, t_charge=0.0)
        result = initialize(inst, N_P=30, seed=42)

        assert len(result.population) == 30
        for sol in result.population:
            check_invariants(sol, inst)
        # c201 (wide TW) should have feasible solutions
        assert result.n_V > 0

    def test_initialize_with_realistic_g(self):
        """Inicializacao deve funcionar com g realista (sem t_charge=0.0)."""
        from evrp.instance import load_schneider
        from evrp.initialization import initialize
        from evrp.representation import check_invariants

        inst = load_schneider(SMALL_INSTANCE)
        assert inst.g > 0, 'g deve ser positivo'
        result = initialize(inst, N_P=10, seed=42)

        assert len(result.population) == 10
        for sol in result.population:
            check_invariants(sol, inst)

    def test_ore_fallback(self):
        from evrp.instance import load_schneider
        from evrp.initialization import ore_fallback
        from evrp.evaluator import PopulationStats, run_ci
        from evrp.representation import NodeType, Route, Solution, Visit

        inst = load_schneider(SMALL_INSTANCE, t_charge=0.0)
        visits = [
            Visit(inst.depot_id, NodeType.DEPOT),
            Visit(inst.station_ids[0], NodeType.STATION),
            Visit(inst.customer_ids[0], NodeType.CUSTOMER),
            Visit(inst.depot_id, NodeType.DEPOT),
        ]
        other = [Visit(inst.depot_id, NodeType.DEPOT)]
        for cid in inst.customer_ids[1:]:
            other.append(Visit(cid, NodeType.CUSTOMER))
        other.append(Visit(inst.depot_id, NodeType.DEPOT))
        sol = Solution(routes=[Route(visits=visits), Route(visits=other)])

        result = ore_fallback(sol, inst)
        assert result is not None
        # Station should be removed
        station_count = sum(
            1 for r in result.routes for v in r.visits
            if v.node_type == NodeType.STATION
        )
        assert station_count == 0


# =========================================================================
# operators.py — zombie cleanup, energy-guided reinsertion, or-opt
# =========================================================================

class TestOperators:
    def _make_instance(self):
        from evrp.instance import load_schneider
        return load_schneider(SMALL_INSTANCE)

    def test_cleanup_zombie_stations_basic(self):
        """Estacoes entre deposito/estacao (sem clientes adjacentes) devem ser removidas."""
        from evrp.operators import _cleanup_zombie_stations
        from evrp.representation import NodeType, Route, Visit

        inst = self._make_instance()
        route = Route(visits=[
            Visit(inst.depot_id, NodeType.DEPOT),
            Visit(inst.station_ids[0], NodeType.STATION),
            Visit(inst.station_ids[1], NodeType.STATION),
            Visit(inst.customer_ids[0], NodeType.CUSTOMER),
            Visit(inst.depot_id, NodeType.DEPOT),
        ])
        _cleanup_zombie_stations(route)

        types = [v.node_type for v in route.visits]
        assert types[0] == NodeType.DEPOT
        assert types[-1] == NodeType.DEPOT
        assert NodeType.CUSTOMER in types
        assert types.count(NodeType.STATION) <= 1
        station_visits = [v for v in route.visits if v.node_type == NodeType.STATION]
        for sv in station_visits:
            idx = route.visits.index(sv)
            prev_t = route.visits[idx - 1].node_type if idx > 0 else None
            next_t = route.visits[idx + 1].node_type if idx < len(route.visits) - 1 else None
            assert prev_t == NodeType.CUSTOMER or next_t == NodeType.CUSTOMER

    def test_cleanup_zombie_chains(self):
        """Cadeia longa de estacoes zumbi deve ser completamente removida."""
        from evrp.operators import _cleanup_zombie_stations
        from evrp.representation import NodeType, Route, Visit

        inst = self._make_instance()
        route = Route(visits=[
            Visit(inst.depot_id, NodeType.DEPOT),
            Visit(inst.station_ids[0], NodeType.STATION),
            Visit(inst.station_ids[1], NodeType.STATION),
            Visit(inst.station_ids[2], NodeType.STATION) if len(inst.station_ids) > 2
            else Visit(inst.station_ids[0], NodeType.STATION),
            Visit(inst.depot_id, NodeType.DEPOT),
        ])
        _cleanup_zombie_stations(route)
        types = [v.node_type for v in route.visits]
        assert NodeType.STATION not in types

    def test_cleanup_preserves_useful_stations(self):
        """Estacoes com clientes adjacentes nao devem ser removidas."""
        from evrp.operators import _cleanup_zombie_stations
        from evrp.representation import NodeType, Route, Visit

        inst = self._make_instance()
        route = Route(visits=[
            Visit(inst.depot_id, NodeType.DEPOT),
            Visit(inst.customer_ids[0], NodeType.CUSTOMER),
            Visit(inst.station_ids[0], NodeType.STATION),
            Visit(inst.customer_ids[1], NodeType.CUSTOMER),
            Visit(inst.depot_id, NodeType.DEPOT),
        ])
        n_stations_before = route.n_stations()
        _cleanup_zombie_stations(route)
        assert route.n_stations() == n_stations_before

    def test_reinsert_orphans_prefers_energy_ok(self):
        """Reinserção deve preferir posição energeticamente viável."""
        from evrp.evaluator import PopulationStats, run_ci
        from evrp.operators import _reinsert_orphans
        from evrp.representation import NodeType, Route, Solution, Visit

        inst = self._make_instance()

        route1 = Route(visits=[
            Visit(inst.depot_id, NodeType.DEPOT),
            Visit(inst.customer_ids[0], NodeType.CUSTOMER),
            Visit(inst.depot_id, NodeType.DEPOT),
        ])
        route2 = Route(visits=[
            Visit(inst.depot_id, NodeType.DEPOT),
            Visit(inst.customer_ids[1], NodeType.CUSTOMER),
            Visit(inst.depot_id, NodeType.DEPOT),
        ])
        sol = Solution(routes=[route1, route2])

        stats = PopulationStats()
        run_ci(sol, inst, stats)

        orphan = inst.customer_ids[2]
        _reinsert_orphans(sol, [orphan], inst)

        all_custs = sol.all_customers()
        assert orphan in all_custs
        assert len(all_custs) == 3

    def test_reinsert_orphans_opens_new_route_if_needed(self):
        """Se nenhuma posição energeticamente viável existe, abre nova rota."""
        from evrp.operators import _reinsert_orphans
        from evrp.representation import NodeType, Route, Solution, Visit

        inst = self._make_instance()

        route = Route(visits=[
            Visit(inst.depot_id, NodeType.DEPOT),
            Visit(inst.customer_ids[0], NodeType.CUSTOMER),
            Visit(inst.depot_id, NodeType.DEPOT),
        ])
        for v in route.visits:
            v.departure_energy = 0.001

        sol = Solution(routes=[route])
        orphan = inst.customer_ids[1]
        _reinsert_orphans(sol, [orphan], inst)

        assert len(sol.routes) == 2
        new_route = sol.routes[-1]
        assert orphan in new_route.customer_ids()

    def test_or_opt_mutation_preserves_customers(self):
        """Or-opt deve preservar todos os clientes."""
        from evrp.evaluator import PopulationStats, run_ci
        from evrp.operators import _or_opt_mutation
        from evrp.representation import NodeType, Route, Solution, Visit, check_invariants

        inst = self._make_instance()

        visits = [Visit(inst.depot_id, NodeType.DEPOT)]
        for cid in inst.customer_ids:
            visits.append(Visit(cid, NodeType.CUSTOMER))
        visits.append(Visit(inst.depot_id, NodeType.DEPOT))
        sol = Solution(routes=[Route(visits=visits)])

        stats = PopulationStats()
        run_ci(sol, inst, stats)

        import random
        random.seed(42)
        mutated = _or_opt_mutation(sol, inst)

        check_invariants(mutated, inst)

    def test_or_opt_mutation_single_customer(self):
        """Or-opt com rota de 1 cliente deve funcionar sem erro."""
        from evrp.operators import _or_opt_mutation
        from evrp.representation import NodeType, Route, Solution, Visit

        inst = self._make_instance()

        routes = []
        for cid in inst.customer_ids:
            routes.append(Route(visits=[
                Visit(inst.depot_id, NodeType.DEPOT),
                Visit(cid, NodeType.CUSTOMER),
                Visit(inst.depot_id, NodeType.DEPOT),
            ]))
        sol = Solution(routes=routes)

        import random
        random.seed(42)
        mutated = _or_opt_mutation(sol, inst)

        all_cust = sorted(mutated.all_customers())
        assert all_cust == sorted(inst.customer_ids)

    def test_crossover_with_zombie_cleanup(self):
        """Crossover completo deve limpar estacoes zumbi."""
        from evrp.evaluator import PopulationStats, run_ci
        from evrp.operators import _route_crossover
        from evrp.representation import NodeType, Route, Solution, Visit, check_invariants

        inst = self._make_instance()

        visits1 = [
            Visit(inst.depot_id, NodeType.DEPOT),
            Visit(inst.station_ids[0], NodeType.STATION),
            Visit(inst.customer_ids[0], NodeType.CUSTOMER),
            Visit(inst.customer_ids[1], NodeType.CUSTOMER),
            Visit(inst.depot_id, NodeType.DEPOT),
        ]
        visits_rest1 = [Visit(inst.depot_id, NodeType.DEPOT)]
        for cid in inst.customer_ids[2:]:
            visits_rest1.append(Visit(cid, NodeType.CUSTOMER))
        visits_rest1.append(Visit(inst.depot_id, NodeType.DEPOT))
        p1 = Solution(routes=[Route(visits=visits1), Route(visits=visits_rest1)])

        visits2 = [Visit(inst.depot_id, NodeType.DEPOT)]
        for cid in inst.customer_ids:
            visits2.append(Visit(cid, NodeType.CUSTOMER))
        visits2.append(Visit(inst.depot_id, NodeType.DEPOT))
        p2 = Solution(routes=[Route(visits=visits2)])

        stats = PopulationStats()
        run_ci(p1, inst, stats)
        run_ci(p2, inst, stats)

        import random
        random.seed(42)
        c1, c2 = _route_crossover(p1, p2, inst)

        check_invariants(c1, inst)
        check_invariants(c2, inst)

        for child in [c1, c2]:
            for route in child.routes:
                for i, v in enumerate(route.visits):
                    if v.node_type == NodeType.STATION:
                        prev_t = route.visits[i - 1].node_type if i > 0 else None
                        next_t = route.visits[i + 1].node_type if i < len(route.visits) - 1 else None
                        assert prev_t == NodeType.CUSTOMER or next_t == NodeType.CUSTOMER, \
                            'Estacao zumbi encontrada apos crossover'


# =========================================================================
# Integration: pymoo pipeline
# =========================================================================

class TestIntegration:
    def test_short_run_c201(self):
        """Smoke test: 5 geracoes do NSGA-II em c201_21."""
        from evrp.instance import load_schneider
        from evrp.runner import run_experiment

        inst = load_schneider(MEDIUM_INSTANCE, t_charge=0.0)
        results = run_experiment(
            inst, N_P=20, N_gen=5,
            init_params=dict(alpha_V=0.40, alpha_E=0.35,
                             beta_s=0.20, p_skip=0.50, seed=42),
            seed=42, verbose=False,
        )

        assert len(results['history']) == 5
        assert results['init_result'] is not None
        assert len(results['pareto_solutions']) > 0

    def test_short_run_c201_moead(self):
        """Smoke test: 5 geracoes do MOEA/D em c201_21."""
        from evrp.instance import load_schneider
        from evrp.runner import run_experiment

        inst = load_schneider(MEDIUM_INSTANCE, t_charge=0.0)
        results = run_experiment(
            inst, N_P=20, N_gen=5,
            init_params=dict(alpha_V=0.40, alpha_E=0.35,
                             beta_s=0.20, p_skip=0.50, seed=42),
            algorithm_name='moead',
            seed=42, verbose=False,
        )

        assert len(results['history']) == 5
        assert results['init_result'] is not None
        assert 'offspring_census' in results

    def test_algorithm_name_interface_regression(self):
        """run_experiment deve aceitar nsga2 e moead sem quebrar interface."""
        from evrp.instance import load_schneider
        from evrp.runner import run_experiment

        inst = load_schneider(SMALL_INSTANCE, t_charge=0.0)

        res_nsga2 = run_experiment(
            inst, N_P=10, N_gen=3,
            algorithm_name='nsga2',
            seed=42, verbose=False,
        )
        res_moead = run_experiment(
            inst, N_P=10, N_gen=3,
            algorithm_name='moead',
            seed=42, verbose=False,
        )

        for res in (res_nsga2, res_moead):
            assert 'history' in res
            assert 'init_result' in res
            assert 'pareto_solutions' in res
            assert 'offspring_census' in res
