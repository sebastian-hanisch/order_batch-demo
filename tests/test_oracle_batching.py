"""Unabhängiges Orakel für Order Batching: (1) Lagerdistanzen gegen einen expliziten Gittergraphen (networkx, Gänge + zwei Quergassen), (2) exaktes Optimum auf winzigen Instanzen per
Held-Karp je Batch und Partitions-DP über alle Bestellungsmengen. Geprüft: Konstruktionen, Inter-Batch-Suche und ILS liefern gültige Partitionen (Kapazität, Positionen), ihre
Gesamtdistanz stimmt mit einer Neuberechnung überein, ist nie unter dem Optimum und nie über dem Startwert der Suche."""

import math

import numpy as np
import pytest

from batch_construction import greedy_seed_batching, singleton_batches, zone_clustering_batching
from batch_evaluation import distance_to_business, route_distance
from batch_local_search import inter_batch_local_search_history, iterated_local_search_history, route_batch
from batch_warehouse import build_distance_matrix


def _held_karp(items, D):
    n = len(items)
    if n == 0:
        return 0.0
    dp = {(1 << i, i): D[0, items[i] + 1] for i in range(n)}
    for mask in range(1, 1 << n):
        for last in range(n):
            if (mask, last) in dp:
                for nxt in range(n):
                    if not mask & (1 << nxt):
                        key, v = (mask | (1 << nxt), nxt), dp[(mask, last)] + D[items[last] + 1, items[nxt] + 1]
                        if v < dp.get(key, math.inf):
                            dp[key] = v
    return min(dp[((1 << n) - 1, i)] + D[items[i] + 1, 0] for i in range(n))


def _exact_optimum(orders, sizes, capacity, D):
    oids = list(orders)
    n = len(oids)
    items = lambda m: [i for b in range(n) if m >> b & 1 for i in orders[oids[b]]]
    tsp, best = {}, {0: 0.0}
    for mask in range(1, 1 << n):
        low, rest, sub, cur = mask & -mask, mask ^ (mask & -mask), mask ^ (mask & -mask), math.inf
        while True:
            m = sub | low
            if bin(m).count("1") == 1 or sum(sizes[i] for i in items(m)) <= capacity + 1e-9:
                if m not in tsp:
                    tsp[m] = _held_karp(items(m), D)
                cur = min(cur, tsp[m] + best[mask ^ m])
            if sub == 0:
                break
            sub = (sub - 1) & rest
        best[mask] = cur
    return best[(1 << n) - 1]


def _instance(rng, n_orders, n_aisles, volume):
    aisles, positions, orders = [], [], {}
    for o in range(n_orders):
        orders[o] = []
        for _ in range(int(rng.integers(1, 4))):
            orders[o].append(len(aisles))
            aisles.append(int(rng.integers(0, n_aisles)))
            positions.append(round(float(rng.uniform(0, 30)), 1))
    aisles, positions = np.array(aisles), np.array(positions)
    sizes = np.round(rng.uniform(1, 4, len(aisles)), 1) if volume else np.ones(len(aisles))
    return orders, aisles, positions, sizes, build_distance_matrix(aisles, positions, 3.0, 30.0)


def _assert_valid(batches, orders, sizes, capacity):
    assert sorted(o for b in batches for o in b["order_ids"]) == sorted(orders)
    for b in batches:
        assert sorted(b["items"]) == sorted(i for o in b["order_ids"] for i in orders[o])
        if len(b["order_ids"]) > 1:
            assert sum(sizes[i] for i in b["items"]) <= capacity + 1e-9


def test_distances_equal_shortest_paths_in_an_explicit_aisle_grid():
    nx = pytest.importorskip("networkx")
    rng = np.random.default_rng(1)
    for _ in range(40):
        n_aisles, length, spacing = int(rng.integers(1, 8)), float(rng.choice([10.0, 30.0, 55.5])), float(rng.choice([1.0, 3.0, 2.5]))
        pts = [(int(rng.integers(0, n_aisles)), float(rng.choice([0.0, length, round(rng.uniform(0, length), 2)]))) for _ in range(int(rng.integers(2, 7)))]
        G = nx.Graph()
        for a in range(n_aisles):
            ps = sorted({0.0, length} | {p for aa, p in pts if aa == a})
            for p, q in zip(ps[:-1], ps[1:]):
                G.add_edge((a, p), (a, q), weight=q - p)
            if a:
                G.add_edge((a - 1, 0.0), (a, 0.0), weight=spacing)
                G.add_edge((a - 1, length), (a, length), weight=spacing)
        D = build_distance_matrix(np.array([a for a, _ in pts]), np.array([p for _, p in pts]), spacing, length)
        for i, pi in enumerate(pts):
            assert D[0, i + 1] == pytest.approx(nx.dijkstra_path_length(G, (0, 0.0), pi))        # Packstation: vorderes Ende von Gang 0
            for j, pj in enumerate(pts):
                assert D[i + 1, j + 1] == pytest.approx(nx.dijkstra_path_length(G, pi, pj))


def test_batching_and_local_search_against_the_exact_optimum_on_tiny_instances():
    rng = np.random.default_rng(3)
    for it in range(14):
        volume = it % 3 == 0
        capacity = 10.0 if volume else 6.0
        orders, aisles, positions, sizes, D = _instance(rng, int(rng.integers(3, 7)), int(rng.integers(2, 7)), volume)
        opt = _exact_optimum(orders, sizes, capacity, D)
        for batches in (greedy_seed_batching(orders, capacity, aisles, positions, 3.0, sizes), zone_clustering_batching(orders, capacity, aisles, positions, 3.0, sizes)):
            _assert_valid(batches, orders, sizes, capacity)
            assert sum(route_batch(b["items"], D)[-1][1] for b in batches) >= opt - 1e-7
            for history in (inter_batch_local_search_history(batches, orders, capacity, sizes, D),
                            iterated_local_search_history(batches, orders, capacity, sizes, D, max_restarts=5, time_budget_s=0.2, seed=it)):
                final_batches, final_routes, total = history[-1]
                _assert_valid(final_batches, orders, sizes, capacity)
                assert all(sorted(r) == sorted(b["items"]) for b, r in zip(final_batches, final_routes))
                assert total == pytest.approx(sum(route_distance(r, D) for r in final_routes))
                assert opt - 1e-7 <= total <= history[0][2] + 1e-7
        _assert_valid(singleton_batches(orders), orders, sizes, capacity)


def test_business_figures_follow_the_definition():
    for dist, n, speed, pick, cost in ((0.0, 0, 1.3, 18.0, 28.0), (1234.5, 40, 1.3, 18.0, 28.0), (500.0, 7, 0.9, 5.5, 31.0)):
        hours, labor, throughput = distance_to_business(dist, n, speed, pick, cost)
        ref = (dist / speed + pick * n) / 3600
        assert hours == pytest.approx(ref) and labor == pytest.approx(ref * cost) and throughput == pytest.approx(n / ref if ref > 0 else 0.0)
