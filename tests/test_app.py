"""
Testsuite für die Order-Batching-Demo. Importiert die Logik-Module direkt
(nicht über die laufende Streamlit-Session) - dasselbe Muster wie in den
anderen Demos, siehe z. B. vrp_demo/tests/test_app.py.
"""

import os
import random
import sys
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_constants import CAPACITY_MODE_POSITIONS, CAPACITY_MODE_VOLUME
from batch_construction import greedy_seed_batching, singleton_batches, zone_clustering_batching
from batch_evaluation import (
    batch_capacity_excess,
    batch_capacity_size,
    capacity_summary_text,
    classify_comparison,
    distance_to_business,
    route_distance,
    solution_totals,
)
from batch_feedback import get_feedback_counts, log_feedback
from batch_local_search import (
    _select_ucb_target,
    _try_moves_from_batch,
    find_two_opt_move,
    inter_batch_local_search_history,
    iterated_local_search_history,
    nearest_neighbor_route,
    perturb_batches,
    reconcile_per_batch_histories,
    route_batch,
    two_opt_history,
)
from batch_ortools_solver import estimated_model_size, recommended_num_batches, solve_with_cpsat
from batch_pdf_export import generate_batch_plan_pdf
from batch_presets import SETTING_SPECS, apply_preset, bounds, load_permalink_settings
from batch_warehouse import aisle_x, build_distance_matrix, depot_distance, item_distance


# ---------------------------------------------------------------------------
# Lagerlayout / Distanzen
# ---------------------------------------------------------------------------

def test_item_distance_same_aisle_is_direct_difference():
    assert item_distance(2, 5.0, 2, 12.0, aisle_spacing=3.0, aisle_length=30.0) == pytest.approx(7.0)


def test_item_distance_different_aisle_takes_shorter_of_front_or_back():
    # Front: 1 + 1 + 3 = 5, Back: 29 + 29 + 3 = 61 -> Front gewinnt
    d = item_distance(0, 1.0, 1, 1.0, aisle_spacing=3.0, aisle_length=30.0)
    assert d == pytest.approx(5.0)
    # Beide nahe der hinteren Quergasse -> Back sollte guenstiger sein
    d_back = item_distance(0, 29.0, 1, 29.0, aisle_spacing=3.0, aisle_length=30.0)
    assert d_back == pytest.approx(5.0)


def test_item_distance_is_symmetric():
    d1 = item_distance(1, 4.0, 5, 22.0, aisle_spacing=3.0, aisle_length=30.0)
    d2 = item_distance(5, 22.0, 1, 4.0, aisle_spacing=3.0, aisle_length=30.0)
    assert d1 == pytest.approx(d2)


def test_depot_distance_zero_at_aisle_zero_front():
    assert depot_distance(0, 0.0, aisle_spacing=3.0) == pytest.approx(0.0)


def test_depot_distance_grows_with_aisle_and_position():
    assert depot_distance(3, 5.0, aisle_spacing=3.0) == pytest.approx(3 * 3.0 + 5.0)


def test_aisle_x_spacing():
    assert aisle_x(0, 3.0) == 0.0
    assert aisle_x(4, 3.0) == pytest.approx(12.0)


def test_build_distance_matrix_shape_and_symmetry():
    aisles = np.array([0, 1, 2])
    positions = np.array([5.0, 10.0, 15.0])
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=30.0)
    assert D.shape == (4, 4)
    assert np.allclose(D, D.T)
    assert np.allclose(np.diag(D), 0.0)


# ---------------------------------------------------------------------------
# Batching-Strategien (Positionen-Kapazität)
# ---------------------------------------------------------------------------

def _sample_orders(n_orders=12, items_min=2, items_max=5, n_aisles=6, aisle_length=25.0, vol_min=1.0, vol_max=4.0, seed=3):
    rng = np.random.default_rng(seed)
    aisles, positions, volumes, order_ids = [], [], [], []
    for oid in range(1, n_orders + 1):
        n_items = int(rng.integers(items_min, items_max + 1))
        for _ in range(n_items):
            aisles.append(int(rng.integers(0, n_aisles)))
            positions.append(float(rng.uniform(0, aisle_length)))
            volumes.append(float(rng.uniform(vol_min, vol_max)))
            order_ids.append(oid)
    aisles = np.array(aisles)
    positions = np.array(positions)
    volumes = np.array(volumes)
    orders = {}
    for idx, oid in enumerate(order_ids):
        orders.setdefault(oid, []).append(idx)
    return orders, aisles, positions, volumes


def _positions_sizes(aisles):
    return np.ones(len(aisles))


def test_greedy_seed_batching_covers_every_order_exactly_once():
    orders, aisles, positions, _volumes = _sample_orders()
    batches = greedy_seed_batching(orders, capacity=15, aisles=aisles, positions=positions, aisle_spacing=3.0, item_sizes=_positions_sizes(aisles))
    covered = [oid for b in batches for oid in b["order_ids"]]
    assert sorted(covered) == sorted(orders.keys())


def test_greedy_seed_batching_respects_capacity_when_possible():
    orders, aisles, positions, _volumes = _sample_orders(items_min=1, items_max=2)
    capacity = 6
    batches = greedy_seed_batching(orders, capacity, aisles, positions, aisle_spacing=3.0, item_sizes=_positions_sizes(aisles))
    for b in batches:
        # Kann nur ueberschritten werden, wenn eine Einzelbestellung bereits
        # groesser als die Kapazitaet ist - hier max. 2 Positionen je Bestellung.
        assert len(b["items"]) <= capacity


def test_greedy_seed_batching_singleton_order_larger_than_capacity_forms_own_batch():
    orders = {1: [0, 1, 2, 3, 4]}  # 5 Positionen, Kapazitaet 3
    aisles = np.array([0, 0, 0, 0, 0])
    positions = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    item_sizes = _positions_sizes(aisles)
    batches = greedy_seed_batching(orders, capacity=3, aisles=aisles, positions=positions, aisle_spacing=3.0, item_sizes=item_sizes)
    assert len(batches) == 1
    assert batches[0]["order_ids"] == [1]
    assert batch_capacity_excess(batches[0], capacity=3, item_sizes=item_sizes) == pytest.approx(2)


def test_zone_clustering_batching_covers_every_order_exactly_once():
    orders, aisles, positions, _volumes = _sample_orders()
    batches = zone_clustering_batching(orders, capacity=15, aisles=aisles, positions=positions, item_sizes=_positions_sizes(aisles), aisle_spacing=3.0)
    covered = [oid for b in batches for oid in b["order_ids"]]
    assert sorted(covered) == sorted(orders.keys())


def test_zone_clustering_batching_respects_capacity_when_possible():
    orders, aisles, positions, _volumes = _sample_orders(items_min=1, items_max=2)
    capacity = 6
    batches = zone_clustering_batching(orders, capacity, aisles, positions, item_sizes=_positions_sizes(aisles), aisle_spacing=3.0)
    for b in batches:
        assert len(b["items"]) <= capacity


def test_zone_clustering_groups_same_aisle_orders_together():
    # Alle Bestellungen liegen im selben Gang -> muessen in einem Batch
    # landen, solange die Kapazitaet reicht.
    orders = {1: [0], 2: [1], 3: [2]}
    aisles = np.array([2, 2, 2])
    positions = np.array([1.0, 2.0, 3.0])
    batches = zone_clustering_batching(orders, capacity=10, aisles=aisles, positions=positions, item_sizes=_positions_sizes(aisles), aisle_spacing=3.0)
    assert len(batches) == 1
    assert sorted(batches[0]["order_ids"]) == [1, 2, 3]


def test_zone_clustering_bestfit_avoids_wasted_capacity_regression():
    # Regression fuer die urspruengliche starre First-Fit-Zuteilung (auf
    # Nutzeranfrage per Benchmark gefunden und behoben, siehe
    # batch_construction.py): sie schloss einen Batch sofort, sobald die
    # naechste Bestellung in Sortierreihenfolge nicht mehr passte, auch wenn
    # eine SPAETERE Bestellung noch gepasst haette. Hier fuehrte das zu 3
    # statt 2 Batches - die jetzige Best-Fit-nach-Naehe-Auffuellung findet
    # die 2-Batch-Loesung.
    orders = {1: [0], 2: [1], 3: [2], 4: [3]}
    aisles = np.array([0, 1, 2, 3])
    positions = np.array([0.0, 0.0, 0.0, 0.0])
    item_sizes = np.array([3.0, 3.0, 2.0, 2.0])
    capacity = 5.0

    batches = zone_clustering_batching(orders, capacity, aisles, positions, item_sizes, aisle_spacing=1.0)
    assert len(batches) == 2


def test_singleton_batches_one_batch_per_order():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=5)
    batches = singleton_batches(orders)
    assert len(batches) == 5
    assert sorted(oid for b in batches for oid in b["order_ids"]) == sorted(orders.keys())


def test_batching_strategies_never_split_an_order_across_batches():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=20, items_min=1, items_max=4)
    item_sizes = _positions_sizes(aisles)
    for batches in [
        greedy_seed_batching(orders, 12, aisles, positions, 3.0, item_sizes),
        zone_clustering_batching(orders, 12, aisles, positions, item_sizes, 3.0),
    ]:
        seen = set()
        for b in batches:
            for oid in b["order_ids"]:
                assert oid not in seen, "Bestellung wurde in mehreren Batches gefunden"
                seen.add(oid)


# ---------------------------------------------------------------------------
# Batching-Strategien (Volumen-Kapazität, auf Nutzeranfrage ergänzt)
# ---------------------------------------------------------------------------

def test_greedy_seed_batching_respects_volume_capacity():
    orders, aisles, positions, volumes = _sample_orders(n_orders=15, items_min=1, items_max=3, vol_min=0.5, vol_max=5.0, seed=5)
    capacity = 12.0
    batches = greedy_seed_batching(orders, capacity, aisles, positions, aisle_spacing=3.0, item_sizes=volumes)
    for b in batches:
        used = batch_capacity_size(b["items"], volumes)
        # Kann nur ueberschritten werden, wenn eine Einzelbestellung fuer sich
        # genommen schon mehr Volumen hat als die Kapazitaet.
        single_order_vols = [batch_capacity_size(orders[oid], volumes) for oid in b["order_ids"]]
        if len(b["order_ids"]) > 1:
            assert used <= capacity + 1e-6
        else:
            assert used == pytest.approx(single_order_vols[0])


def test_zone_clustering_batching_respects_volume_capacity():
    orders, aisles, positions, volumes = _sample_orders(n_orders=15, items_min=1, items_max=3, vol_min=0.5, vol_max=5.0, seed=6)
    capacity = 12.0
    batches = zone_clustering_batching(orders, capacity, aisles, positions, item_sizes=volumes, aisle_spacing=3.0)
    for b in batches:
        if len(b["order_ids"]) > 1:
            assert batch_capacity_size(b["items"], volumes) <= capacity + 1e-6


def test_volume_capacity_can_bind_tighter_than_position_capacity():
    # Ein einzelnes sehr voluminoeses Item fuellt die Kapazitaet im
    # Volumen-Modus bereits fast aus, obwohl es nur 1 Position ist - im
    # Positionen-Modus wuerden problemlos mehr Bestellungen dazupassen.
    orders = {1: [0], 2: [1], 3: [2]}
    aisles = np.array([0, 0, 0])
    positions = np.array([1.0, 2.0, 3.0])
    volumes = np.array([9.0, 1.0, 1.0])
    capacity = 10.0

    batches_by_volume = greedy_seed_batching(orders, capacity, aisles, positions, aisle_spacing=3.0, item_sizes=volumes)
    batches_by_position = greedy_seed_batching(orders, capacity=10, aisles=aisles, positions=positions, aisle_spacing=3.0, item_sizes=_positions_sizes(aisles))

    assert len(batches_by_volume) > len(batches_by_position)


# ---------------------------------------------------------------------------
# Routing (Nearest-Neighbor + 2-opt) je Batch
# ---------------------------------------------------------------------------

def test_nearest_neighbor_route_visits_every_item_exactly_once():
    aisles = np.array([0, 1, 2, 0])
    positions = np.array([5.0, 5.0, 5.0, 20.0])
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=30.0)
    route = nearest_neighbor_route([0, 1, 2, 3], D)
    assert sorted(route) == [0, 1, 2, 3]


def test_two_opt_history_never_worsens_the_start():
    rng = np.random.default_rng(1)
    aisles = rng.integers(0, 5, size=8)
    positions = rng.uniform(0, 25, size=8)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=25.0)
    history = two_opt_history(nearest_neighbor_route(list(range(8)), D), D)
    dists = [h[1] for h in history]
    assert all(dists[i + 1] <= dists[i] + 1e-9 for i in range(len(dists) - 1))


def test_route_batch_history_first_entry_matches_nearest_neighbor():
    aisles = np.array([0, 1, 2])
    positions = np.array([2.0, 2.0, 2.0])
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=20.0)
    history = route_batch([0, 1, 2], D)
    nn_route = nearest_neighbor_route([0, 1, 2], D)
    assert history[0][0] == nn_route


def test_route_batch_empty_items_returns_empty_route():
    D = build_distance_matrix(np.array([]), np.array([]), aisle_spacing=3.0, aisle_length=20.0)
    history = route_batch([], D)
    assert history == [([], 0.0)]


def test_find_two_opt_move_on_already_optimal_two_item_route_finds_nothing():
    aisles = np.array([0, 1])
    positions = np.array([5.0, 5.0])
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=20.0)
    route, found = find_two_opt_move([0, 1], D)
    assert found is False
    assert route == [0, 1]


# ---------------------------------------------------------------------------
# Inter-Batch-Lokalsuche (Relocate + Swap zwischen Batches, auf Nutzeranfrage
# ergaenzt, nachdem ein Benchmark gegen das echte Optimum zeigte, dass reines
# 2-opt je Batch im Schnitt noch 8-10% zurueckliegt - siehe README)
# ---------------------------------------------------------------------------

def _total_distance(batches, D):
    return sum(route_batch(b["items"], D)[-1][1] for b in batches)


def test_inter_batch_search_never_worsens_construction():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=20, items_min=1, items_max=4, seed=11)
    item_sizes = _positions_sizes(aisles)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=25.0)
    capacity = 12

    construction = greedy_seed_batching(orders, capacity, aisles, positions, aisle_spacing=3.0, item_sizes=item_sizes)
    before = _total_distance(construction, D)

    history = inter_batch_local_search_history(construction, orders, capacity, item_sizes, D)
    final_batches = history[-1][0]
    after = _total_distance(final_batches, D)

    assert after <= before + 1e-6


def test_inter_batch_search_respects_capacity():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=20, items_min=1, items_max=3, seed=12)
    item_sizes = _positions_sizes(aisles)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=25.0)
    capacity = 8

    construction = zone_clustering_batching(orders, capacity, aisles, positions, item_sizes, aisle_spacing=3.0)
    history = inter_batch_local_search_history(construction, orders, capacity, item_sizes, D)
    final_batches = history[-1][0]

    for b in final_batches:
        assert batch_capacity_size(b["items"], item_sizes) <= capacity + 1e-6


def test_inter_batch_search_preserves_all_orders_exactly_once():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=18, items_min=1, items_max=3, seed=13)
    item_sizes = _positions_sizes(aisles)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=25.0)
    capacity = 8

    construction = greedy_seed_batching(orders, capacity, aisles, positions, aisle_spacing=3.0, item_sizes=item_sizes)
    history = inter_batch_local_search_history(construction, orders, capacity, item_sizes, D)
    final_batches = history[-1][0]

    covered = sorted(oid for b in final_batches for oid in b["order_ids"])
    assert covered == sorted(orders.keys())
    seen = set()
    for b in final_batches:
        for oid in b["order_ids"]:
            assert oid not in seen, "Bestellung wurde in mehreren Batches gefunden"
            seen.add(oid)


def test_inter_batch_search_final_step_is_two_opt_polished():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=15, items_min=2, items_max=4, seed=14)
    item_sizes = _positions_sizes(aisles)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=25.0)
    capacity = 10

    construction = greedy_seed_batching(orders, capacity, aisles, positions, aisle_spacing=3.0, item_sizes=item_sizes)
    history = inter_batch_local_search_history(construction, orders, capacity, item_sizes, D)
    final_batches, final_routes, final_total = history[-1]

    for r in final_routes:
        _cand, found = find_two_opt_move(r, D)
        assert not found, "Finale Route sollte 2-opt-optimal sein (kein verbessernder Zug mehr)"
    assert final_total == pytest.approx(sum(route_distance(r, D) for r in final_routes))


# ---------------------------------------------------------------------------
# reconcile_per_batch_histories (Code-Review-Fund, 2026-08-22): app.py baut
# die per-Batch-2opt-Animation unabhaengig per route_batch neu auf (fuer den
# UI-Slider) - das kann einen ANDEREN, nicht so guten lokalen 2-opt-Optimum
# treffen wie die verschachtelte Suche selbst, wodurch die angezeigte
# "Laufdistanz" gegenueber dem tatsaechlichen Suchergebnis auseinanderlief.
# ---------------------------------------------------------------------------

def test_reconcile_per_batch_histories_appends_better_final_route():
    import itertools

    D = np.array([
        [0.0, 1.0, 4.0, 1.0],
        [1.0, 0.0, 1.0, 5.0],
        [4.0, 1.0, 0.0, 1.0],
        [1.0, 5.0, 1.0, 0.0],
    ])
    # Ueber alle Permutationen eines 3-Positionen-Batches die tatsaechlich
    # (per route_distance, nicht per Handrechnung) kuerzeste und laengste
    # ermitteln - garantiert eine echte, verifizierte Differenz statt
    # geratener Werte.
    perms = [list(p) for p in itertools.permutations([0, 1, 2])]
    dists = [(perm, route_distance(perm, D)) for perm in perms]
    worse_route, worse_dist = max(dists, key=lambda x: x[1])
    better_route, better_dist = min(dists, key=lambda x: x[1])
    assert better_dist < worse_dist, "Testvoraussetzung: es muss einen echten Unterschied geben"

    per_batch_histories = [[(worse_route, worse_dist)]]
    final_routes = [better_route]

    reconciled = reconcile_per_batch_histories(per_batch_histories, final_routes, D)

    assert reconciled[0][-1] == (better_route, better_dist)
    assert reconciled[0][:-1] == per_batch_histories[0], "Urspruengliche Animation bleibt erhalten, nur ein Schritt wird angehaengt"


def test_reconcile_per_batch_histories_leaves_history_unchanged_when_already_as_good():
    D = np.array([
        [0.0, 1.0, 1.0],
        [1.0, 0.0, 1.0],
        [1.0, 1.0, 0.0],
    ])
    per_batch_histories = [[([0, 1], route_distance([0, 1], D))]]
    final_routes = [[0, 1]]  # identische Route, kein Grund zum Anhaengen

    reconciled = reconcile_per_batch_histories(per_batch_histories, final_routes, D)

    assert reconciled == per_batch_histories


def test_ils_displayed_distance_matches_search_result_after_independent_route_rebuild():
    # Regressionstest fuer den konkreten Code-Review-Fund: app.py baut die
    # Routen fuer die UI unabhaengig per route_batch neu auf (fuer die volle
    # 2opt-Animation) - ohne reconcile_per_batch_histories konnte die daraus
    # summierte Distanz von iterated_local_search_history's eigenem
    # Endergebnis abweichen (immer schlechter, nie besser).
    orders, aisles, positions, _volumes = _sample_orders(n_orders=24, items_min=2, items_max=6, seed=1)
    item_sizes = _positions_sizes(aisles)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=30.0)
    capacity = 15
    construction = greedy_seed_batching(orders, capacity, aisles, positions, aisle_spacing=3.0, item_sizes=item_sizes)

    history = iterated_local_search_history(construction, orders, capacity, item_sizes, D, seed=0)
    final_batches, final_routes, final_total = history[-1]

    per_batch_histories = [route_batch(b["items"], D) for b in final_batches]
    per_batch_histories = reconcile_per_batch_histories(per_batch_histories, final_routes, D)
    displayed_total = sum(h[-1][1] for h in per_batch_histories)

    assert displayed_total == pytest.approx(final_total)


def test_inter_batch_search_history_first_entry_matches_construction():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=10, items_min=1, items_max=3, seed=15)
    item_sizes = _positions_sizes(aisles)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=25.0)
    capacity = 8

    construction = greedy_seed_batching(orders, capacity, aisles, positions, aisle_spacing=3.0, item_sizes=item_sizes)
    history = inter_batch_local_search_history(construction, orders, capacity, item_sizes, D)

    first_covered = sorted(oid for b in history[0][0] for oid in b["order_ids"])
    assert first_covered == sorted(orders.keys())


def test_inter_batch_search_single_batch_finds_no_move():
    # Nur ein Batch -> es gibt kein ZWEITES Batch, in das relociert/getauscht
    # werden koennte - die Suche darf nicht abstuerzen und muss sofort
    # mit einer Historie der Laenge 1 zurueckkehren.
    orders = {1: [0], 2: [1]}
    aisles = np.array([0, 1])
    positions = np.array([1.0, 2.0])
    item_sizes = np.ones(2)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=20.0)
    batches = [{"order_ids": [1, 2], "items": [0, 1]}]

    history = inter_batch_local_search_history(batches, orders, capacity=10, item_sizes=item_sizes, D=D)
    assert len(history) == 1


def test_inter_batch_search_finds_known_relocate_improvement():
    # Handgebaute Instanz mit bewusst suboptimaler Ausgangs-Zuteilung:
    # Bestellungen an den Gaengen 0/2 und 1/3 zusammengefasst statt der
    # raeumlich naheliegenderen 0/1 und 2/3 - eine Umverteilung MUSS hier
    # eine kuerzere Gesamtdistanz finden.
    orders = {1: [0], 2: [1], 3: [2], 4: [3]}
    aisles = np.array([0, 1, 2, 3])
    positions = np.array([0.0, 0.0, 0.0, 0.0])
    item_sizes = np.ones(4)
    D = build_distance_matrix(aisles, positions, aisle_spacing=1.0, aisle_length=10.0)
    suboptimal = [
        {"order_ids": [1, 3], "items": [0, 2]},
        {"order_ids": [2, 4], "items": [1, 3]},
    ]
    before = _total_distance(suboptimal, D)

    history = inter_batch_local_search_history(suboptimal, orders, capacity=2, item_sizes=item_sizes, D=D)
    final_batches = history[-1][0]
    after = _total_distance(final_batches, D)

    assert after < before - 1e-6
    assert len(history) > 1


def test_try_moves_from_batch_returns_unchanged_when_no_second_batch():
    orders = {1: [0]}
    aisles = np.array([0])
    positions = np.array([5.0])
    item_sizes = np.ones(1)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=20.0)
    batches = [{"order_ids": [1], "items": [0]}]
    routes = [[0]]
    dists = [route_distance([0], D)]

    new_batches, new_routes, new_dists, found, touched = _try_moves_from_batch(0, batches, routes, dists, orders, capacity=5, item_sizes=item_sizes, D=D)
    assert found is False
    assert touched == set()
    assert new_batches == batches


def test_try_moves_from_batch_finds_swap_improvement():
    # Dieselbe handgebaute Instanz wie beim Inter-Batch-Regressionstest
    # unten (4 Bestellungen auf einer Linie, suboptimale Zuteilung {0,2}
    # und {1,3} statt der naheliegenderen {0,1} und {2,3}) - bei Kapazitaet
    # 2 sind beide Batches bereits voll, ein Swap ist hier der einzig
    # moegliche verbessernde Zug (Relocate braucht freie Kapazitaet im Ziel).
    orders = {1: [0], 2: [1], 3: [2], 4: [3]}
    aisles = np.array([0, 1, 2, 3])
    positions = np.array([0.0, 0.0, 0.0, 0.0])
    item_sizes = np.ones(4)
    D = build_distance_matrix(aisles, positions, aisle_spacing=1.0, aisle_length=10.0)
    batches = [
        {"order_ids": [1, 3], "items": [0, 2]},
        {"order_ids": [2, 4], "items": [1, 3]},
    ]
    routes = [nearest_neighbor_route(b["items"], D) for b in batches]
    dists = [route_distance(r, D) for r in routes]

    new_batches, new_routes, new_dists, found, touched = _try_moves_from_batch(0, batches, routes, dists, orders, capacity=2, item_sizes=item_sizes, D=D)
    assert found is True
    assert touched == {0, 1}
    assert sum(new_dists) < sum(dists)
    covered = sorted(oid for b in new_batches for oid in b["order_ids"])
    assert covered == [1, 2, 3, 4]


# ---------------------------------------------------------------------------
# Iterated Local Search (Perturbation + Neustarts obendrauf auf die
# Inter-Batch-Suche, auf Nutzeranfrage ergaenzt - durchweg 1-4,8% kuerzere
# Distanz auf realistischen Instanzgroessen, siehe README)
# ---------------------------------------------------------------------------

def test_perturb_batches_preserves_all_orders_exactly_once():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=15, items_min=1, items_max=3, seed=31)
    item_sizes = _positions_sizes(aisles)
    capacity = 8
    construction = greedy_seed_batching(orders, capacity, aisles, positions, aisle_spacing=3.0, item_sizes=item_sizes)

    rng = random.Random(1)
    perturbed, touched, decisions = perturb_batches(construction, orders, capacity, item_sizes, rng, {}, {}, 0, n_moves=3)

    covered = sorted(oid for b in perturbed for oid in b["order_ids"])
    assert covered == sorted(orders.keys())
    seen = set()
    for b in perturbed:
        for oid in b["order_ids"]:
            assert oid not in seen, "Bestellung wurde in mehreren Batches gefunden"
            seen.add(oid)
    assert touched.issubset(set(range(len(perturbed))))
    assert isinstance(decisions, list)


def test_perturb_batches_respects_capacity():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=15, items_min=1, items_max=3, seed=32)
    item_sizes = _positions_sizes(aisles)
    capacity = 8
    construction = greedy_seed_batching(orders, capacity, aisles, positions, aisle_spacing=3.0, item_sizes=item_sizes)

    rng = random.Random(2)
    perturbed, _touched, _decisions = perturb_batches(construction, orders, capacity, item_sizes, rng, {}, {}, 0, n_moves=5)

    for b in perturbed:
        assert batch_capacity_size(b["items"], item_sizes) <= capacity + 1e-6


def test_select_ucb_target_prefers_untried_over_tried_regardless_of_success_rate():
    # UCB1-Kerngarantie: ein noch nie versuchtes (Bestellung, Ziel)-Paar
    # gewinnt immer gegen ein bereits (auch erfolgreich) versuchtes - der
    # Unsicherheits-Bonus ist bei n=0 unendlich.
    ucb_tries = {(1, 0): 20}
    ucb_successes = {(1, 0): 20}  # Batch 0: bisher immer erfolgreich
    chosen = _select_ucb_target(oid=1, candidates_j=[0, 1], ucb_tries=ucb_tries, ucb_successes=ucb_successes, ucb_total=20, c=1.4)
    assert chosen == 1, "Noch nie versuchtes Ziel sollte trotz perfekter Erfolgsbilanz des anderen gewinnen"


def test_select_ucb_target_prefers_higher_success_rate_once_all_tried():
    ucb_tries = {(1, 0): 10, (1, 1): 10}
    ucb_successes = {(1, 0): 8, (1, 1): 2}
    chosen = _select_ucb_target(oid=1, candidates_j=[0, 1], ucb_tries=ucb_tries, ucb_successes=ucb_successes, ucb_total=20, c=0.0)
    assert chosen == 0, "Ohne Explorationsbonus (c=0) sollte die hoehere Erfolgsrate gewinnen"


def test_iterated_local_search_never_worse_than_plain_local_search():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=20, items_min=1, items_max=4, seed=33)
    item_sizes = _positions_sizes(aisles)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=25.0)
    capacity = 12
    construction = greedy_seed_batching(orders, capacity, aisles, positions, aisle_spacing=3.0, item_sizes=item_sizes)

    plain_history = inter_batch_local_search_history(construction, orders, capacity, item_sizes, D)
    plain_dist = plain_history[-1][2]

    ils_history = iterated_local_search_history(construction, orders, capacity, item_sizes, D, max_restarts=10, time_budget_s=5.0, seed=0)
    ils_dist = ils_history[-1][2]

    assert ils_dist <= plain_dist + 1e-6


def test_iterated_local_search_respects_time_budget():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=20, items_min=1, items_max=4, seed=34)
    item_sizes = _positions_sizes(aisles)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=25.0)
    capacity = 12
    construction = greedy_seed_batching(orders, capacity, aisles, positions, aisle_spacing=3.0, item_sizes=item_sizes)

    t0 = time.time()
    iterated_local_search_history(construction, orders, capacity, item_sizes, D, max_restarts=1000, time_budget_s=0.3, seed=0)
    elapsed = time.time() - t0
    # Grosszuegige Toleranz: das Zeitbudget wird nur ZWISCHEN Neustarts
    # geprueft, ein einzelner Neustart darf es also leicht ueberschreiten.
    assert elapsed < 3.0


def test_iterated_local_search_preserves_all_orders_and_capacity():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=18, items_min=1, items_max=3, seed=35)
    item_sizes = _positions_sizes(aisles)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=25.0)
    capacity = 9
    construction = greedy_seed_batching(orders, capacity, aisles, positions, aisle_spacing=3.0, item_sizes=item_sizes)

    history = iterated_local_search_history(construction, orders, capacity, item_sizes, D, max_restarts=10, time_budget_s=5.0, seed=0)
    final_batches = history[-1][0]

    covered = sorted(oid for b in final_batches for oid in b["order_ids"])
    assert covered == sorted(orders.keys())
    for b in final_batches:
        assert batch_capacity_size(b["items"], item_sizes) <= capacity + 1e-6


def test_iterated_local_search_final_step_is_two_opt_polished():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=15, items_min=2, items_max=4, seed=36)
    item_sizes = _positions_sizes(aisles)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=25.0)
    capacity = 10
    construction = greedy_seed_batching(orders, capacity, aisles, positions, aisle_spacing=3.0, item_sizes=item_sizes)

    history = iterated_local_search_history(construction, orders, capacity, item_sizes, D, max_restarts=10, time_budget_s=5.0, seed=0)
    final_batches, final_routes, final_total = history[-1]

    for r in final_routes:
        _cand, found = find_two_opt_move(r, D)
        assert not found, "Finale Route sollte 2-opt-optimal sein (kein verbessernder Zug mehr)"


# ---------------------------------------------------------------------------
# Bewertung / Geschaeftliche Kennzahlen
# ---------------------------------------------------------------------------

def test_route_distance_empty_route_is_zero():
    D = np.zeros((3, 3))
    assert route_distance([], D) == 0.0


def test_route_distance_includes_depot_round_trip():
    aisles = np.array([0])
    positions = np.array([10.0])
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=20.0)
    assert route_distance([0], D) == pytest.approx(20.0)  # 10 hin + 10 zurueck


def test_batch_capacity_size_positions_mode_equals_item_count():
    item_sizes = np.ones(5)
    assert batch_capacity_size([0, 1, 2], item_sizes) == pytest.approx(3.0)


def test_batch_capacity_size_volume_mode_sums_volumes():
    item_sizes = np.array([1.5, 2.0, 3.0])
    assert batch_capacity_size([0, 2], item_sizes) == pytest.approx(4.5)


def test_batch_capacity_excess_zero_when_within_capacity():
    batch = {"order_ids": [1], "items": [0, 1, 2]}
    item_sizes = np.ones(3)
    assert batch_capacity_excess(batch, capacity=5, item_sizes=item_sizes) == 0


def test_batch_capacity_excess_positive_when_volume_exceeds_capacity():
    batch = {"order_ids": [1], "items": [0, 1]}
    item_sizes = np.array([6.0, 6.0])
    assert batch_capacity_excess(batch, capacity=10.0, item_sizes=item_sizes) == pytest.approx(2.0)


def test_capacity_summary_text_positions_mode_omits_redundant_count():
    text = capacity_summary_text(n_items=8, cap_used=8.0, capacity=15, capacity_mode=CAPACITY_MODE_POSITIONS)
    assert text == "8/15 Positionen"


def test_capacity_summary_text_volume_mode_shows_both_count_and_volume():
    text = capacity_summary_text(n_items=8, cap_used=17.3, capacity=20.0, capacity_mode=CAPACITY_MODE_VOLUME)
    assert "8 Positionen" in text
    assert "17.3/20.0 l" in text


def test_distance_to_business_pick_time_dominates_when_distance_is_zero():
    hours, cost, throughput = distance_to_business(
        total_distance_m=0.0, n_items=10, n_batches=2, walking_speed_mps=1.3, pick_time_s=18.0, cost_per_hour=28.0,
    )
    assert hours == pytest.approx(10 * 18.0 / 3600.0)
    assert cost == pytest.approx(hours * 28.0)
    assert throughput == pytest.approx(10 / hours)


def test_distance_to_business_zero_items_zero_hours_zero_throughput():
    hours, cost, throughput = distance_to_business(0.0, 0, 0, 1.3, 18.0, 28.0)
    assert hours == 0.0
    assert cost == 0.0
    assert throughput == 0.0


def test_solution_totals_sums_across_batches():
    aisles = np.array([0, 1])
    positions = np.array([5.0, 5.0])
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=20.0)
    total = solution_totals([[0], [1]], D)
    assert total == pytest.approx(route_distance([0], D) + route_distance([1], D))


def test_classify_comparison_identifies_tie_within_threshold():
    candidates = [
        {"key": "a", "label": "A", "total_distance": 100.0},
        {"key": "b", "label": "B", "total_distance": 100.5},
    ]
    result = classify_comparison(candidates, tie_threshold_pct=1.0)
    assert result["all_tied"] is True
    assert result["is_tied"] is True


def test_classify_comparison_identifies_clear_winner():
    candidates = [
        {"key": "a", "label": "A", "total_distance": 100.0},
        {"key": "b", "label": "B", "total_distance": 150.0},
    ]
    result = classify_comparison(candidates, tie_threshold_pct=1.0)
    assert result["all_tied"] is False
    assert result["best"]["key"] == "a"
    assert result["worst"]["key"] == "b"


# ---------------------------------------------------------------------------
# Batching reduziert typischerweise die Gesamtdistanz gegenueber Einzelbestellungen
# ---------------------------------------------------------------------------

def test_batching_reduces_total_distance_versus_singleton_baseline():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=20, items_min=2, items_max=5, n_aisles=8, seed=7)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=25.0)

    naive_batches = singleton_batches(orders)
    naive_dist = sum(route_batch(b["items"], D)[-1][1] for b in naive_batches)

    greedy_batches = greedy_seed_batching(orders, capacity=15, aisles=aisles, positions=positions, aisle_spacing=3.0, item_sizes=_positions_sizes(aisles))
    greedy_dist = sum(route_batch(b["items"], D)[-1][1] for b in greedy_batches)

    assert greedy_dist < naive_dist


# ---------------------------------------------------------------------------
# CP-SAT-Vergleichsloeser (batch_ortools_solver.py) - auf Nutzeranfrage
# ergaenzt fuer einen exakten/nahe-exakten Vergleich auf kleinen Instanzen.
# Alle Tests halten die Instanzen bewusst winzig (<=8 Positionen), damit die
# Testsuite schnell bleibt - siehe Modul-Docstring fuer die Modellgroesse.
# ---------------------------------------------------------------------------

def test_estimated_model_size_formula():
    assert estimated_model_size(n_items=5, num_batches=3) == 3 * 6 * 6


def test_recommended_num_batches_never_below_theoretical_minimum():
    orders = {1: [0, 1, 2], 2: [3, 4, 5], 3: [6, 7]}
    item_sizes = np.ones(8)
    # Gesamtgroesse 8, Kapazitaet 3 -> mindestens ceil(8/3)=3 Batches
    n = recommended_num_batches(orders, capacity=3, item_sizes=item_sizes, slack=0)
    assert n >= 3


def test_recommended_num_batches_never_exceeds_order_count():
    orders = {1: [0], 2: [1]}
    item_sizes = np.ones(2)
    n = recommended_num_batches(orders, capacity=100, item_sizes=item_sizes, slack=5)
    assert n <= len(orders)


def test_solve_with_cpsat_matches_known_optimum_on_tiny_instance():
    # Handnachvollziehbare Instanz: 3 Bestellungen, Kapazitaet 3.
    orders = {1: [0], 2: [1], 3: [2, 3]}
    aisles = np.array([0, 1, 2, 3])
    positions = np.array([2.0, 2.0, 2.0, 2.0])
    item_sizes = np.ones(4)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=20.0)

    batches, status, wall_time = solve_with_cpsat(orders, capacity=3, item_sizes=item_sizes, D=D, num_batches=3, time_limit_s=10)

    assert status == "OPTIMAL"
    assert batches is not None
    total = sum(route_distance(b["route"], D) for b in batches)
    assert total == pytest.approx(34.0, abs=0.5)


def test_solve_with_cpsat_covers_every_order_exactly_once():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=6, items_min=1, items_max=2, n_aisles=4, aisle_length=15.0, seed=21)
    item_sizes = _positions_sizes(aisles)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=15.0)

    batches, status, wall_time = solve_with_cpsat(orders, capacity=4, item_sizes=item_sizes, D=D, num_batches=6, time_limit_s=10)

    assert batches is not None
    covered = sorted(oid for b in batches for oid in b["order_ids"])
    assert covered == sorted(orders.keys())
    seen = set()
    for b in batches:
        for oid in b["order_ids"]:
            assert oid not in seen, "Bestellung wurde in mehreren Batches gefunden"
            seen.add(oid)


def test_solve_with_cpsat_respects_capacity():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=6, items_min=1, items_max=2, n_aisles=4, aisle_length=15.0, seed=22)
    item_sizes = _positions_sizes(aisles)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=15.0)
    capacity = 4

    batches, status, wall_time = solve_with_cpsat(orders, capacity, item_sizes, D, num_batches=6, time_limit_s=10)

    assert batches is not None
    for b in batches:
        assert sum(item_sizes[i] for i in b["items"]) <= capacity + 1e-6


def test_solve_with_cpsat_route_visits_every_item_of_its_batch_once():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=5, items_min=1, items_max=2, n_aisles=4, aisle_length=15.0, seed=23)
    item_sizes = _positions_sizes(aisles)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=15.0)

    batches, status, wall_time = solve_with_cpsat(orders, capacity=4, item_sizes=item_sizes, D=D, num_batches=5, time_limit_s=10)

    assert batches is not None
    for b in batches:
        assert sorted(b["route"]) == sorted(b["items"])


def test_solve_with_cpsat_single_order_single_batch():
    orders = {1: [0, 1]}
    aisles = np.array([0, 1])
    positions = np.array([3.0, 3.0])
    item_sizes = np.ones(2)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=15.0)

    batches, status, wall_time = solve_with_cpsat(orders, capacity=5, item_sizes=item_sizes, D=D, num_batches=1, time_limit_s=5)

    assert status == "OPTIMAL"
    assert len(batches) == 1
    assert batches[0]["order_ids"] == [1]


# ---------------------------------------------------------------------------
# PDF-Export
# ---------------------------------------------------------------------------

def test_generate_batch_plan_pdf_produces_valid_pdf_bytes_positions_mode():
    orders, aisles, positions, _volumes = _sample_orders(n_orders=6, items_min=1, items_max=3, seed=2)
    item_sizes = _positions_sizes(aisles)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=25.0)
    batches = greedy_seed_batching(orders, capacity=8, aisles=aisles, positions=positions, aisle_spacing=3.0, item_sizes=item_sizes)
    histories = [route_batch(b["items"], D) for b in batches]
    final_routes = [h[-1][0] for h in histories]
    order_ids_by_item = np.zeros(len(aisles), dtype=int)
    for oid, items in orders.items():
        for i in items:
            order_ids_by_item[i] = oid

    pdf_bytes = generate_batch_plan_pdf("Test", batches, final_routes, order_ids_by_item, aisles, positions, D, capacity=8, capacity_mode=CAPACITY_MODE_POSITIONS, item_sizes=item_sizes)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 500


def test_generate_batch_plan_pdf_produces_valid_pdf_bytes_volume_mode():
    orders, aisles, positions, volumes = _sample_orders(n_orders=6, items_min=1, items_max=3, seed=2)
    D = build_distance_matrix(aisles, positions, aisle_spacing=3.0, aisle_length=25.0)
    batches = greedy_seed_batching(orders, capacity=10.0, aisles=aisles, positions=positions, aisle_spacing=3.0, item_sizes=volumes)
    histories = [route_batch(b["items"], D) for b in batches]
    final_routes = [h[-1][0] for h in histories]
    order_ids_by_item = np.zeros(len(aisles), dtype=int)
    for oid, items in orders.items():
        for i in items:
            order_ids_by_item[i] = oid

    pdf_bytes = generate_batch_plan_pdf("Test", batches, final_routes, order_ids_by_item, aisles, positions, D, capacity=10.0, capacity_mode=CAPACITY_MODE_VOLUME, item_sizes=volumes)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 500


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

def test_feedback_log_and_count_roundtrip(tmp_path):
    feedback_file = tmp_path / "feedback_log.csv"
    assert log_feedback("up", feedback_file=str(feedback_file)) is True
    assert log_feedback("down", feedback_file=str(feedback_file)) is True
    up, down = get_feedback_counts(feedback_file=str(feedback_file))
    assert up == 1
    assert down == 1


def test_feedback_counts_zero_when_file_missing(tmp_path):
    missing = tmp_path / "does_not_exist.csv"
    assert get_feedback_counts(feedback_file=str(missing)) == (0, 0)


def test_log_feedback_returns_false_on_write_failure(tmp_path):
    bad_path = tmp_path / "no_such_dir" / "feedback_log.csv"
    assert log_feedback("up", feedback_file=str(bad_path)) is False


# ---------------------------------------------------------------------------
# Presets / Permalink
# ---------------------------------------------------------------------------

def test_setting_specs_defaults_are_within_bounds():
    for key, spec in SETTING_SPECS.items():
        if spec.lo is not None:
            assert spec.lo <= spec.default
        if spec.hi is not None:
            assert spec.default <= spec.hi
        if spec.choices is not None:
            assert spec.default in spec.choices


def test_bounds_returns_lo_hi_tuple():
    lo, hi = bounds("n_orders_slider")
    assert lo < hi


def test_apply_preset_rejects_unknown_keys():
    with pytest.raises(AssertionError):
        apply_preset({"not_a_real_setting": 5})


def test_capacity_mode_spec_has_exactly_two_choices():
    spec = SETTING_SPECS["capacity_mode_radio"]
    assert spec.choices == (CAPACITY_MODE_POSITIONS, CAPACITY_MODE_VOLUME)
