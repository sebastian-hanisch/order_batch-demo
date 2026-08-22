"""
Drei Ebenen lokaler Suche:

1. Routenkonstruktion (Nearest-Neighbor) + 2-opt-Verbesserung für die
   Kommissionierroute EINES Batches (route_batch/two_opt_history) - jeder
   Batch wird unabhängig von allen anderen zu einer eigenen kleinen
   Rundreise (Depot -> Positionen -> Depot) optimiert, ein klassisches
   Traveling-Salesman-Teilproblem je Batch.

2. Inter-Batch-Lokalsuche (inter_batch_local_search_history) - verschiebt
   (Relocate) oder tauscht (Swap) Bestellungen ZWISCHEN Batches, wenn das
   die Gesamtdistanz senkt. Auf Nutzeranfrage ergänzt, nachdem ein Benchmark
   gegen das echte Optimum (Vollenumeration auf winzigen Instanzen) zeigte,
   dass Greedy-Seed/Zonen-Sweep trotz eigener 2-opt-Politur im Schnitt noch
   8-10% hinter dem Optimum zurückliegen (Details siehe README) - die
   Batch-ZUTEILUNG selbst blieb bislang nach der Konstruktion unangetastet.
   Mit Inter-Batch-Suche sank der Abstand zum Optimum auf 0,1%, auf
   realistischen Instanzgrößen ergaben sich 8-18% kürzere Gesamtdistanz.

   WICHTIG für die Performance: anders als route_batch (volle NN+2opt-
   Neuberechnung) bewertet die Inter-Batch-Suche Kandidatenzüge NICHT durch
   komplettes Neu-Routing der betroffenen Batches (das wäre O(k^3) je
   Kandidat und bei den größten zulässigen Szenarien - 80 Bestellungen -
   nicht mehr in vertretbarer Zeit berechenbar, siehe README). Stattdessen
   wird - analog zu find_or_opt_move in der Tourenplanung-Demo - eine
   Bestellung günstig in die BESTEHENDE Route des Zielbatches eingefügt
   (Cheapest-Insertion, sequenziell je Position: O(k) statt O(k^3)) bzw. aus
   der Route des Quellbatches entfernt (O(k)). Die dabei verwendeten Routen
   sind daher während der Suche nur Nearest-Neighbor-Qualität, nicht
   2-opt-poliert - das kostet keine Zuteilungsqualität (die Suche bewertet
   Zuteilungen weiterhin exakt anhand einer gültigen Route, nur nicht der
   bestmöglichen), macht die Bewertung aber um Größenordnungen billiger.
   Erst das letzte Element der zurückgegebenen Historie wird zusätzlich per
   vollem 2-opt poliert (route_batch je Batch) - der tatsächlich angezeigte
   Endzustand ist also wie gewohnt 2-opt-optimiert.

   Auf Nutzeranfrage ergänzt: Kandidaten-Auswahl per Don't-Look-Bits
   (Bentley 1992, Standardtechnik in TSP/VRP-Lokalsuche) statt vollem
   Rescan aller Batches bei jeder Iteration - eine Warteschlange "noch zu
   prüfender" Batches statt bei jedem Zug wieder bei Batch 0 anzufangen.
   Findet dieselbe Nachbarschaft, nur in anderer Reihenfolge - Geschwindig-
   keitsgewinn ohne systematischen Qualitätsverlust (empirisch 1,2-3,2x
   schneller, größter Gewinn genau bei den größten Instanzen, siehe README).

3. Iterated Local Search (iterated_local_search_history) - baut auf 2. auf:
   nach Erreichen eines lokalen Optimums gezielt stören (ein paar zufällige,
   zulässige Relocates, auch wenn sie kurzfristig verschlechtern) und erneut
   bis zum lokalen Optimum optimieren, wiederholt für ein Zeitbudget statt
   einer festen Anzahl Durchläufe - das lässt kleine Instanzen viele
   Neustarts nutzen, ohne bei großen Instanzen (wo ein einzelner Durchlauf
   schon teuer ist) unbegrenzt Zeit zu verbrauchen. Auf Nutzeranfrage
   benchmarkt: durchweg 1-4,8% kürzere Distanz auf realistischen Instanz-
   größen (siehe README) - im Gegensatz zu allen zuvor geprüften
   Konstruktions-/Clustering-Alternativen (siehe README-Abschnitte dazu)
   der erste Hebel seit der ursprünglichen Inter-Batch-Suche, der einen
   konsistenten zusätzlichen Gewinn brachte.
"""

import random
import time
from collections import deque

from batch_constants import EPS, ILS_MAX_RESTARTS, ILS_PERTURB_STRENGTH, ILS_TIME_BUDGET_S, LOCAL_SEARCH_MAX_MOVES
from batch_evaluation import route_distance


def nearest_neighbor_route(item_indices, D):
    """Baut eine Startroute: von der Packstation aus immer zur nächst-
    gelegenen noch unbesuchten Position springen. Einfache, schnelle
    Konstruktionsheuristik - wird im Anschluss per 2-opt verbessert."""
    unvisited = set(item_indices)
    route = []
    current_node = 0  # Depot
    while unvisited:
        nxt = min(unvisited, key=lambda i: D[current_node, i + 1])
        route.append(nxt)
        unvisited.discard(nxt)
        current_node = nxt + 1
    return route


def find_two_opt_move(route, D):
    """Sucht EINE verbessernde 2-opt-Vertauschung (erste gefundene
    Verbesserung): ein Teilstück der Route wird umgedreht, wenn das die
    Gesamtdistanz senkt."""
    if len(route) < 2:
        return route, False
    base = route_distance(route, D)
    for i in range(len(route) - 1):
        for j in range(i + 1, len(route)):
            cand = route[:i] + route[i : j + 1][::-1] + route[j + 1 :]
            cand_dist = route_distance(cand, D)
            if cand_dist < base - EPS:
                return cand, True
    return route, False


def two_opt_history(route, D, max_moves=LOCAL_SEARCH_MAX_MOVES):
    """Führt wiederholt verbessernde 2-opt-Züge aus, bis kein verbessernder
    Zug mehr existiert (lokales Optimum) oder max_moves erreicht ist. Gibt
    die komplette Verbesserungs-Historie zurück (Liste aus (Routen-Snapshot,
    Distanz)) - treibt den Iterations-Slider samt Auto-Play im UI-Panel, wie
    bei local_search_history() in der Tourenplanung-Demo."""
    current = list(route)
    history = [(list(current), route_distance(current, D))]
    moves = 0
    while moves < max_moves:
        new_route, found = find_two_opt_move(current, D)
        if not found:
            break
        current = new_route
        moves += 1
        history.append((list(current), route_distance(current, D)))
    return history


def route_batch(item_indices, D):
    """Konstruiert und verbessert die Kommissionierroute eines einzelnen
    Batches: Nearest-Neighbor-Start, danach 2-opt bis zum lokalen Optimum.
    Gibt die volle Verbesserungshistorie zurück; history[-1] ist das
    Endergebnis."""
    nn_route = nearest_neighbor_route(item_indices, D)
    return two_opt_history(nn_route, D)


def _remove_items(route, items_to_remove):
    remove_set = set(items_to_remove)
    return [i for i in route if i not in remove_set]


def _cheapest_insertion(route, items_to_insert, D):
    """Fügt Positionen sequenziell an ihrer jeweils günstigsten Stelle in
    eine BESTEHENDE Route ein (Cheapest-Insertion), statt die Route von
    Grund auf neu zu konstruieren - siehe Modul-Docstring für die
    Performance-Begründung."""
    current = list(route)
    for item in items_to_insert:
        nodes = [0] + [i + 1 for i in current] + [0]
        best_delta, best_pos = None, 0
        for pos in range(len(current) + 1):
            a, b = nodes[pos], nodes[pos + 1]
            delta = D[a, item + 1] + D[item + 1, b] - D[a, b]
            if best_delta is None or delta < best_delta:
                best_delta, best_pos = delta, pos
        current = current[:best_pos] + [item] + current[best_pos:]
    return current


def _try_moves_from_batch(i, batches, routes, dists, orders, capacity, item_sizes, D):
    """Sucht EINEN verbessernden Zug (Relocate oder Swap), an dem Batch i
    beteiligt ist - als Quelle, als Ziel oder als Tauschpartner. Kern der
    Don't-Look-Bits-Suche: statt bei jeder Iteration ALLE Batch-Paare zu
    prüfen (wie in einer naiven Vollsuche), wird nur nach Zügen gesucht, an
    denen der als "auffällig" markierte Batch i beteiligt ist. Gibt bei
    Erfolg zusätzlich zurück, welche Batches durch den Zug verändert wurden
    (damit die Aufrufer-Warteschlange genau diese wieder als prüfenswert
    markieren kann, nicht mehr)."""
    n = len(batches)

    if len(batches[i]["order_ids"]) > 1:
        for oid in batches[i]["order_ids"]:
            order_items = orders[oid]
            order_size = sum(item_sizes[k] for k in order_items)
            for j in range(n):
                if j == i:
                    continue
                target_size = sum(item_sizes[k] for k in batches[j]["items"])
                if target_size + order_size > capacity + EPS:
                    continue
                new_route_i = _remove_items(routes[i], order_items)
                new_dist_i = route_distance(new_route_i, D)
                new_route_j = _cheapest_insertion(routes[j], order_items, D)
                new_dist_j = route_distance(new_route_j, D)
                if (new_dist_i + new_dist_j) < (dists[i] + dists[j]) - EPS:
                    new_batches = [dict(b) for b in batches]
                    new_batches[i] = {
                        "order_ids": [o for o in batches[i]["order_ids"] if o != oid],
                        "items": [k for k in batches[i]["items"] if k not in order_items],
                    }
                    new_batches[j] = {"order_ids": batches[j]["order_ids"] + [oid], "items": batches[j]["items"] + order_items}
                    new_routes = list(routes)
                    new_routes[i], new_routes[j] = new_route_i, new_route_j
                    new_dists = list(dists)
                    new_dists[i], new_dists[j] = new_dist_i, new_dist_j
                    return new_batches, new_routes, new_dists, True, {i, j}

    for j in range(n):
        if j == i or len(batches[j]["order_ids"]) <= 1:
            continue
        for oid in batches[j]["order_ids"]:
            order_items = orders[oid]
            order_size = sum(item_sizes[k] for k in order_items)
            target_size = sum(item_sizes[k] for k in batches[i]["items"])
            if target_size + order_size > capacity + EPS:
                continue
            new_route_j = _remove_items(routes[j], order_items)
            new_dist_j = route_distance(new_route_j, D)
            new_route_i = _cheapest_insertion(routes[i], order_items, D)
            new_dist_i = route_distance(new_route_i, D)
            if (new_dist_i + new_dist_j) < (dists[i] + dists[j]) - EPS:
                new_batches = [dict(b) for b in batches]
                new_batches[j] = {
                    "order_ids": [o for o in batches[j]["order_ids"] if o != oid],
                    "items": [k for k in batches[j]["items"] if k not in order_items],
                }
                new_batches[i] = {"order_ids": batches[i]["order_ids"] + [oid], "items": batches[i]["items"] + order_items}
                new_routes = list(routes)
                new_routes[i], new_routes[j] = new_route_i, new_route_j
                new_dists = list(dists)
                new_dists[i], new_dists[j] = new_dist_i, new_dist_j
                return new_batches, new_routes, new_dists, True, {i, j}

    size_i = sum(item_sizes[k] for k in batches[i]["items"])
    for j in range(n):
        if j == i:
            continue
        size_j = sum(item_sizes[k] for k in batches[j]["items"])
        for oid_i in batches[i]["order_ids"]:
            size_oid_i = sum(item_sizes[k] for k in orders[oid_i])
            for oid_j in batches[j]["order_ids"]:
                size_oid_j = sum(item_sizes[k] for k in orders[oid_j])
                if size_i - size_oid_i + size_oid_j > capacity + EPS:
                    continue
                if size_j - size_oid_j + size_oid_i > capacity + EPS:
                    continue
                new_route_i = _cheapest_insertion(_remove_items(routes[i], orders[oid_i]), orders[oid_j], D)
                new_route_j = _cheapest_insertion(_remove_items(routes[j], orders[oid_j]), orders[oid_i], D)
                new_dist_i = route_distance(new_route_i, D)
                new_dist_j = route_distance(new_route_j, D)
                if (new_dist_i + new_dist_j) < (dists[i] + dists[j]) - EPS:
                    new_batches = [dict(b) for b in batches]
                    new_batches[i] = {
                        "order_ids": [o for o in batches[i]["order_ids"] if o != oid_i] + [oid_j],
                        "items": [k for k in batches[i]["items"] if k not in orders[oid_i]] + orders[oid_j],
                    }
                    new_batches[j] = {
                        "order_ids": [o for o in batches[j]["order_ids"] if o != oid_j] + [oid_i],
                        "items": [k for k in batches[j]["items"] if k not in orders[oid_j]] + orders[oid_i],
                    }
                    new_routes = list(routes)
                    new_routes[i], new_routes[j] = new_route_i, new_route_j
                    new_dists = list(dists)
                    new_dists[i], new_dists[j] = new_dist_i, new_dist_j
                    return new_batches, new_routes, new_dists, True, {i, j}

    return batches, routes, dists, False, set()


def _inter_batch_search_dlb(batches, orders, capacity, item_sizes, D, max_moves=LOCAL_SEARCH_MAX_MOVES):
    """Reine Inter-Batch-Lokalsuche bis zum lokalen Optimum, per Don't-Look-
    Bits (Bentley 1992): eine Warteschlange "auffälliger" (seit der letzten
    Prüfung veränderter) Batches statt bei jeder Iteration wieder bei Batch 0
    von vorn zu beginnen. Ein Batch verlässt die Warteschlange, sobald von
    ihm aus kein verbessernder Zug mehr gefunden wird, und kommt erst
    zurück, wenn ein SPÄTERER Zug ihn tatsächlich verändert. OHNE
    abschließende 2-opt-Politur (siehe inter_batch_local_search_history /
    iterated_local_search_history, die diese Funktion als billigen Kern
    verwenden - eine Politur bei jedem Iterated-Local-Search-Neustart wäre
    verschwendete Rechenzeit für Zwischenergebnisse, die am Ende doch
    verworfen werden)."""
    current_batches = [dict(b) for b in batches]
    current_routes = [nearest_neighbor_route(b["items"], D) for b in current_batches]
    current_dists = [route_distance(r, D) for r in current_routes]
    history = [(current_batches, list(current_routes), sum(current_dists))]

    n = len(current_batches)
    active = deque(range(n))
    in_active = set(range(n))
    moves = 0

    while active and moves < max_moves:
        i = active.popleft()
        in_active.discard(i)
        new_batches, new_routes, new_dists, found, touched = _try_moves_from_batch(
            i, current_batches, current_routes, current_dists, orders, capacity, item_sizes, D
        )
        if not found:
            continue
        current_batches, current_routes, current_dists = new_batches, new_routes, new_dists
        moves += 1
        history.append((current_batches, list(current_routes), sum(current_dists)))
        for b in touched | {i}:
            if b not in in_active:
                active.append(b)
                in_active.add(b)

    return history


def _polish_final_batches(batches, D):
    """Poliert jeden Batch einmalig per vollem 2-opt (route_batch) - teuer
    genug, um es NICHT bei jedem Zwischenschritt/Neustart zu wiederholen,
    sondern nur einmal auf das tatsächliche Endergebnis anzuwenden."""
    polished_routes = [route_batch(b["items"], D)[-1][0] for b in batches]
    return polished_routes, sum(route_distance(r, D) for r in polished_routes)


def inter_batch_local_search_history(batches, orders, capacity, item_sizes, D, max_moves=LOCAL_SEARCH_MAX_MOVES):
    """Sucht bis zum ersten lokalen Optimum der Inter-Batch-Nachbarschaft
    (Relocate + Swap, Don't-Look-Bits) und poliert danach jeden finalen
    Batch per 2-opt. Gibt die komplette Historie zurück: eine Liste aus
    (Batches-Snapshot, Routen-Snapshot, Gesamtdistanz) - treibt den
    Zuteilungs-Iterations-Slider samt Auto-Play im UI-Panel. Für die
    stärkere, um Iterated Local Search erweiterte Variante siehe
    iterated_local_search_history."""
    history = _inter_batch_search_dlb(batches, orders, capacity, item_sizes, D, max_moves)
    final_batches, _final_routes, _final_total = history[-1]
    polished_routes, polished_total = _polish_final_batches(final_batches, D)
    history[-1] = (final_batches, polished_routes, polished_total)
    return history


def perturb_batches(batches, orders, capacity, item_sizes, rng, n_moves=ILS_PERTURB_STRENGTH):
    """Verschiebt n_moves zufällige, zulässige Bestellungen in einen anderen
    (noch passenden) Batch - OHNE Bewertung, auch wenn das die Distanz
    kurzfristig verschlechtert. Diversifikation für Iterated Local Search:
    ohne eine solche Störung würde die nachfolgende Lokalsuche immer wieder
    im selben lokalen Optimum landen, aus dem sie gestartet ist."""
    batches = [dict(b) for b in batches]
    for _ in range(n_moves):
        if len(batches) < 2:
            break
        i = rng.randrange(len(batches))
        if len(batches[i]["order_ids"]) <= 1:
            continue
        oid = rng.choice(batches[i]["order_ids"])
        order_items = orders[oid]
        order_size = sum(item_sizes[k] for k in order_items)
        candidates_j = [
            j for j in range(len(batches))
            if j != i and sum(item_sizes[k] for k in batches[j]["items"]) + order_size <= capacity + EPS
        ]
        if not candidates_j:
            continue
        j = rng.choice(candidates_j)
        batches[i] = {"order_ids": [o for o in batches[i]["order_ids"] if o != oid], "items": [k for k in batches[i]["items"] if k not in order_items]}
        batches[j] = {"order_ids": batches[j]["order_ids"] + [oid], "items": batches[j]["items"] + order_items}
    return [b for b in batches if b["order_ids"]]


def iterated_local_search_history(batches, orders, capacity, item_sizes, D, max_restarts=ILS_MAX_RESTARTS, time_budget_s=ILS_TIME_BUDGET_S, perturb_strength=ILS_PERTURB_STRENGTH, seed=None, max_moves=LOCAL_SEARCH_MAX_MOVES):
    """Inter-Batch-Lokalsuche (siehe inter_batch_local_search_history) plus
    Iterated Local Search: nach dem ersten lokalen Optimum wiederholt gezielt
    stören (perturb_batches) und erneut bis zum lokalen Optimum optimieren,
    das beste je gefundene Ergebnis behalten. Begrenzt durch ein ZEITBUDGET
    statt einer festen Neustart-Zahl (siehe batch_constants.py) - skaliert
    sich dadurch automatisch mit der Instanzgröße: bei kleinen Instanzen
    passen viele Dutzend Neustarts in das Budget, bei großen (wo schon ein
    einzelner Durchlauf teuer ist) nur wenige oder gar keiner, ohne das für
    sehr große Instanzen ohnehin bekannte Zeitrisiko zusätzlich zu
    verschärfen (siehe README).

    Die zurückgegebene Historie enthält die komplette erste Konvergenz
    (identisch zu inter_batch_local_search_history) plus einen zusätzlichen
    Eintrag für jeden Neustart, der eine neue beste Lösung gefunden hat -
    nicht-verbessernde Neustarts (die meisten) werden nicht mitprotokolliert,
    damit die Historie eine sauber monotone "bester Stand"-Kurve bleibt statt
    jede verworfene Störung mit anzuzeigen."""
    rng = random.Random(seed)
    history = _inter_batch_search_dlb(batches, orders, capacity, item_sizes, D, max_moves)
    best_batches, best_routes, best_dist = history[-1]

    t_start = time.time()
    for _ in range(max_restarts):
        if time.time() - t_start > time_budget_s:
            break
        perturbed = perturb_batches(best_batches, orders, capacity, item_sizes, rng, perturb_strength)
        cand_history = _inter_batch_search_dlb(perturbed, orders, capacity, item_sizes, D, max_moves)
        cand_batches, cand_routes, cand_dist = cand_history[-1]
        if cand_dist < best_dist - EPS:
            best_batches, best_routes, best_dist = cand_batches, cand_routes, cand_dist
            history.append((best_batches, best_routes, best_dist))

    polished_routes, polished_total = _polish_final_batches(best_batches, D)
    history[-1] = (best_batches, polished_routes, polished_total)
    return history
