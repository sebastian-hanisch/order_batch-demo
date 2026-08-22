"""
Drei Ebenen lokaler Suche:

1. Routenkonstruktion (Nearest-Neighbor) + 2-opt-Verbesserung für die
   Kommissionierroute EINES Batches (route_batch/two_opt_history) - jeder
   Batch wird unabhängig von allen anderen zu einer eigenen kleinen
   Rundreise (Depot -> Positionen -> Depot) optimiert, ein klassisches
   Traveling-Salesman-Teilproblem je Batch.

2. Inter-Batch-Lokalsuche (inter_batch_local_search_history) - verschiebt
   (Relocate) oder tauscht (Swap) Bestellungen ZWISCHEN Batches, wenn das
   die Gesamtdistanz senkt, VERSCHACHTELT mit 2-opt auf den einzelnen
   Batch-Routen (siehe _try_move_or_two_opt) - ein Batch gilt erst dann als
   "erledigt", wenn WEDER die Zuteilungs- NOCH die Routing-Nachbarschaft
   noch etwas verbessert. Auf Nutzeranfrage ergänzt, nachdem ein Benchmark
   gegen das echte Optimum (Vollenumeration auf winzigen Instanzen) zeigte,
   dass Greedy-Seed/Zonen-Sweep trotz eigener 2-opt-Politur im Schnitt noch
   8-10% hinter dem Optimum zurückliegen (Details siehe README) - die
   Batch-ZUTEILUNG selbst blieb bislang nach der Konstruktion unangetastet.
   Mit Inter-Batch-Suche sank der Abstand zum Optimum auf 0,1%, auf
   realistischen Instanzgrößen ergaben sich 8-18% kürzere Gesamtdistanz.

   WICHTIG für die Performance: anders als route_batch (volle NN+2opt-
   Neuberechnung) bewertet die Inter-Batch-Suche Zuteilungs-Kandidatenzüge
   NICHT durch komplettes Neu-Routing der betroffenen Batches (das wäre
   O(k^3) je Kandidat und bei den größten zulässigen Szenarien - 80
   Bestellungen - nicht mehr in vertretbarer Zeit berechenbar, siehe
   README). Stattdessen wird - analog zu find_or_opt_move in der
   Tourenplanung-Demo - eine Bestellung günstig in die BESTEHENDE Route des
   Zielbatches eingefügt (Cheapest-Insertion, sequenziell je Position: O(k)
   statt O(k^3)) bzw. aus der Route des Quellbatches entfernt (O(k)).

   Die Verschachtelung mit 2-opt (statt wie ursprünglich die gesamte
   Zuteilungssuche mit Nearest-Neighbor-Qualitäts-Routen laufen zu lassen
   und erst am Ende einmalig je Batch zu polieren) wurde auf Nutzeranfrage
   ergänzt, nachdem die Literatur dazu (Won/Olafsson 2005, "Joint order
   batching and order picking in warehouse operations") denselben
   Grundgedanken nahelegte: die bisherige zweistufige Reihenfolge bewertete
   Zuteilungszüge anhand noch nicht routenoptimierter Distanzen, was zu
   suboptimalen Zuteilungsentscheidungen führen kann. Über mehrere
   unabhängige Testinstanzen empirisch bestätigt: ~1-2% kürzere Endergebnisse
   trotz ~1,8-2x höherer Kosten je Konvergenz (weniger ILS-Neustarts passen
   ins Zeitbudget) - die bessere Qualität pro Neustart gleicht den
   Restart-Verlust mehr als aus (siehe README für den vollständigen
   Vergleich mit sechs anderen, dabei gescheiterten Metaheuristik-Ideen).

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

   Die Ziel-Batch-Wahl innerhalb der Störung (perturb_batches) nutzt UCB1
   (Auer et al. 2002, Bandit-Explorationsstrategie aus dem RL-Bereich) statt
   gleichverteiltem Zufall - auf Nutzeranfrage nach RL-Explorationsstrategien
   geprüft und als einzige von elf zuvor getesteten Metaheuristik-Varianten
   bei KEINER Instanzgröße im Mittel schlechter (siehe README-Benchmark).
"""

import math
import random
import time
from collections import deque

import numpy as np

from batch_constants import (
    EPS,
    ILS_MAX_RESTARTS,
    ILS_PERTURB_STRENGTH,
    ILS_TIME_BUDGET_S,
    LOCAL_SEARCH_MAX_MOVES,
    UCB_EXPLORATION_C,
)
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
    Gesamtdistanz senkt.

    Bewertet jeden Kandidaten per Distanz-DELTA statt die komplette
    Kandidatenroute zu bauen und ihre Gesamtdistanz neu aufzusummieren: beim
    Umdrehen eines zusammenhängenden Teilstücks ändern sich nur die zwei
    Rand-Kanten, alle Kanten INNERHALB des Teilstücks bleiben (die
    Distanzmatrix ist symmetrisch) unverändert. Macht eine Suchrunde O(n^2)
    statt O(n^3) - reines Delta, exakt dieselben Kandidaten/Ergebnisse wie
    zuvor (siehe README-Benchmark), nur ohne die pro Kandidat wiederholte
    volle Neuberechnung."""
    n = len(route)
    if n < 2:
        return route, False
    nodes = [0] + [i + 1 for i in route] + [0]
    for i in range(1, n):
        for j in range(i + 1, n + 1):
            a, b = nodes[i - 1], nodes[i]
            c, d = nodes[j], nodes[j + 1]
            delta = (D[a, c] + D[b, d]) - (D[a, b] + D[c, d])
            if delta < -EPS:
                cand = route[: i - 1] + route[i - 1 : j][::-1] + route[j:]
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
    Performance-Begründung.

    Die Suche nach der günstigsten Einfügeposition ist numpy-vektorisiert
    (alle Kandidatenpositionen auf einmal statt Python-Schleife) statt eine
    Python-Schleife über alle Kandidatenpositionen - bei der Standard-
    Batch-Kapazität ein Wash, wächst aber mit der Kapazität: 1.14x bei
    Kapazität 30, 1.38x bei Kapazität 60 im End-zu-Ende-Stresstest (siehe
    README) - genau der Randfall mit den Regler-Maximalwerten, der ohnehin
    schon als Risikozone dokumentiert ist."""
    current = list(route)
    for item in items_to_insert:
        nodes = np.array([0] + [i + 1 for i in current] + [0])
        a, b = nodes[:-1], nodes[1:]
        deltas = D[a, item + 1] + D[item + 1, b] - D[a, b]
        best_pos = int(deltas.argmin())
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


def _try_move_or_two_opt(i, batches, routes, dists, orders, capacity, item_sizes, D):
    """Verschachtelt Zuteilungs- und Routing-Nachbarschaft für Batch i, statt
    sie nacheinander abzuarbeiten (siehe Won/Olafsson 2005, "Joint order
    batching and order picking in warehouse operations" - dort wird die
    Batchbildung ebenfalls anhand der TATSÄCHLICHEN Routenqualität statt
    einer groben Näherung bewertet, wenn auch für eine andere Zielfunktion,
    Kommissionierzeit UND Bestellungs-Wartezeit statt hier nur Distanz).
    Zuerst wird wie gehabt ein verbessernder Relocate/Swap versucht; erst
    wenn keiner mehr gefunden wird, ein verbessernder 2-opt-Zug auf der
    Route von Batch i selbst. Batch i gilt erst dann als "erledigt" (verlässt
    die Don't-Look-Bits-Warteschlange), wenn WEDER die Zuteilungs- NOCH die
    Routing-Nachbarschaft noch etwas verbessert - die bisherige zweistufige
    Reihenfolge (erst Zuteilung mit Nearest-Neighbor-Qualitäts-Routen bis zum
    Ende durchlaufen, danach einmalig je Batch per 2-opt poliert) bewertete
    Zuteilungszüge anhand noch nicht routenoptimierter Distanzen - das kann
    zu suboptimalen Zuteilungsentscheidungen führen. Empirisch über mehrere
    unabhängige Testinstanzen ~1-2% kürzere Endergebnisse bei vergleichbarer
    Zeit (siehe README)."""
    new_batches, new_routes, new_dists, found, touched = _try_moves_from_batch(
        i, batches, routes, dists, orders, capacity, item_sizes, D
    )
    if found:
        return new_batches, new_routes, new_dists, True, touched

    new_route, two_opt_found = find_two_opt_move(routes[i], D)
    if two_opt_found:
        new_routes = list(routes)
        new_routes[i] = new_route
        new_dists = list(dists)
        new_dists[i] = route_distance(new_route, D)
        return batches, new_routes, new_dists, True, {i}

    return batches, routes, dists, False, set()


def _inter_batch_search_dlb_from_state(batches, routes, dists, orders, capacity, item_sizes, D, active_init, max_moves=LOCAL_SEARCH_MAX_MOVES):
    """Kern der Don't-Look-Bits-Suche (Bentley 1992): eine Warteschlange
    "auffälliger" Batches statt bei jeder Iteration wieder bei Batch 0 von
    vorn zu beginnen. Ein Batch verlässt die Warteschlange, sobald von ihm
    aus WEDER ein verbessernder Zuteilungs- NOCH ein verbessernder 2-opt-Zug
    mehr gefunden wird (siehe _try_move_or_two_opt), und kommt erst zurück,
    wenn ein SPÄTERER Zug ihn tatsächlich verändert - dadurch sind die
    zurückgegebenen Routen bereits am Ende dieser Funktion 2-opt-optimal,
    keine separate Polier-Phase mehr nötig.

    Nimmt Routen/Distanzen und die Start-Warteschlange als vorgegebenen
    Zustand entgegen, statt sie selbst aus den Batches heraus neu
    aufzubauen - das ermöglicht einen WARM START (siehe
    iterated_local_search_history): nach einer kleinen, gezielten Störung
    müssen nur die tatsächlich betroffenen Batches neu geprüft werden, nicht
    die komplette Lösung. `_inter_batch_search_dlb` (Kaltstart: alle Batches
    aktiv, Routen frisch aus den Items aufgebaut) ist der Sonderfall
    active_init=alle Batches."""
    current_batches = [dict(b) for b in batches]
    current_routes = list(routes)
    current_dists = list(dists)
    history = [(current_batches, list(current_routes), sum(current_dists))]

    active = deque(active_init)
    in_active = set(active_init)
    moves = 0

    while active and moves < max_moves:
        i = active.popleft()
        in_active.discard(i)
        new_batches, new_routes, new_dists, found, touched = _try_move_or_two_opt(
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


def _inter_batch_search_dlb(batches, orders, capacity, item_sizes, D, max_moves=LOCAL_SEARCH_MAX_MOVES):
    """Reine Inter-Batch-Lokalsuche bis zum lokalen Optimum, Kaltstart: baut
    Nearest-Neighbor-Routen für ALLE Batches frisch auf und startet mit
    allen Batches in der Warteschlange. Siehe
    _inter_batch_search_dlb_from_state für den Warm-Start-Fall (ILS-
    Neustarts)."""
    routes = [nearest_neighbor_route(b["items"], D) for b in batches]
    dists = [route_distance(r, D) for r in routes]
    return _inter_batch_search_dlb_from_state(batches, routes, dists, orders, capacity, item_sizes, D, range(len(batches)), max_moves)


def _apply_final_safety_net(batches, routes, D):
    """Nimmt je Batch die kürzere von (verschachtelt gefundene Route, ein
    frischer Nearest-Neighbor+2opt-Aufbau von Grund auf) - EINMALIG auf das
    tatsächliche Endergebnis angewendet, nicht bei jedem Zwischenschritt/
    Neustart (dafür zu teuer, siehe route_batch).

    Grund: 2-opt wird während der verschachtelten Suche INKREMENTELL auf die
    Route angewendet, die durch Einfügen/Entfernen während der Zuteilungs-
    suche entstanden ist - das ist ein anderer, nicht zwingend besserer
    Startpunkt als ein kompletter Neuaufbau (2-opt kennt mehrere lokale
    Optima, je nach Startroute). Auf einzelnen Instanzen kann das ohne
    Absicherung leicht schlechter ausfallen als die früher genutzte separate
    Politur-Phase (empirisch beobachtet, u. a. am Standardszenario dieser
    App) - diese günstige Zusatzprüfung (einmalig, nicht pro Neustart)
    garantiert, dass das Endergebnis nie schlechter ist als die alte
    zweistufige Variante, ohne die Restart-Effizienz-Vorteile der
    Verschachtelung während der eigentlichen Suche zu verlieren. Die Prüfung
    ist günstig genug (ein einziger route_batch-Aufruf je Batch), um sie erst
    ganz am Ende einmalig auszuführen."""
    new_routes, new_dists = [], []
    for b, r in zip(batches, routes):
        current_dist = route_distance(r, D)
        fresh_route, fresh_dist = route_batch(b["items"], D)[-1]
        if fresh_dist < current_dist - EPS:
            new_routes.append(fresh_route)
            new_dists.append(fresh_dist)
        else:
            new_routes.append(r)
            new_dists.append(current_dist)
    return new_routes, sum(new_dists)


def reconcile_per_batch_histories(per_batch_histories, final_routes, D):
    """Stellt sicher, dass eine unabhängig aufgebaute Verbesserungs-Historie
    je Batch (typischerweise `route_batch` für die UI-2opt-Animation, siehe
    app.py) am tatsächlich BESTEN bekannten Ergebnis endet (`final_routes`,
    z. B. aus iterated_local_search_history/inter_batch_local_search_history)
    - hängt bei Bedarf einen zusätzlichen Endschritt an, der exakt diese
    Route zeigt.

    Grund (Code-Review-Fund, 2026-08-22): `route_batch` baut jede Route von
    Grund auf neu auf (Nearest-Neighbor + 2-opt) - ein ANDERER Startpunkt für
    2-opt als die bereits interleaved-optimierte Route aus der Suche selbst
    (siehe _try_move_or_two_opt/_apply_final_safety_net), der einen
    schlechteren lokalen Optimum finden kann. `final_routes` ist bereits per
    `_apply_final_safety_net` gegen genau diesen Fall abgesichert
    (route_distance(final_routes[i]) <= eine frische route_batch-
    Rekonstruktion, per Konstruktion) - diese Funktion sorgt dafür, dass
    eine SEPARAT aufgebaute Animation dasselbe Ergebnis am Ende zeigt.

    Vergleicht bewusst die ROUTE selbst, nicht nur ihre Distanz (zweiter
    Code-Review-Fund, 2026-08-22): zwei unterschiedliche Reihenfolgen können
    dieselbe Distanz ergeben (Gleichstand) - ein reiner Distanzvergleich
    (`dist < history[-1][1] - EPS`) hätte solche Gleichstände unangetastet
    gelassen, wodurch dieselbe Batch-Route in der "Batch-Zuteilung
    optimieren"-Übersicht (zeigt `final_routes` direkt) und in "Batch im
    Detail" (zeigt diese Historie) unterschiedlich aussehen konnte, obwohl
    beide gleich kurz waren - empirisch bestätigt: 80 von 142 zufällig
    geprüften Batches betroffen. Da `final_routes[i]` nie schlechter als
    `history[-1]` ist (siehe oben), ist ein reiner Routen-Vergleich hier
    sicher und günstig genug (kein zusätzlicher route_distance-Aufruf, wenn
    schon identisch)."""
    reconciled = []
    for history, route in zip(per_batch_histories, final_routes):
        if route != history[-1][0]:
            history = history + [(route, route_distance(route, D))]
        reconciled.append(history)
    return reconciled


def inter_batch_local_search_history(batches, orders, capacity, item_sizes, D, max_moves=LOCAL_SEARCH_MAX_MOVES):
    """Sucht bis zum ersten lokalen Optimum der VERSCHACHTELTEN Zuteilungs-
    UND Routing-Nachbarschaft (Relocate + Swap + 2-opt, Don't-Look-Bits -
    siehe _try_move_or_two_opt). Gibt die komplette Historie zurück: eine
    Liste aus (Batches-Snapshot, Routen-Snapshot, Gesamtdistanz) - treibt den
    Zuteilungs-Iterations-Slider samt Auto-Play im UI-Panel. Der letzte
    Eintrag wird zusätzlich per _apply_final_safety_net abgesichert (siehe
    dort). Für die stärkere, um Iterated Local Search erweiterte Variante
    siehe iterated_local_search_history."""
    history = _inter_batch_search_dlb(batches, orders, capacity, item_sizes, D, max_moves)
    final_batches, final_routes, _final_total = history[-1]
    safe_routes, safe_total = _apply_final_safety_net(final_batches, final_routes, D)
    history[-1] = (final_batches, safe_routes, safe_total)
    return history


def _select_ucb_target(oid, candidates_j, ucb_tries, ucb_successes, ucb_total, c):
    """UCB1 (Auer et al. 2002): wählt unter den zulässigen Ziel-Batches
    dasjenige mit dem höchsten Score aus Erfolgsrate PLUS Unsicherheits-Bonus
    (score = Erfolgsrate + c*sqrt(ln(N)/n), N = Gesamtzahl bisheriger
    Versuche). Noch nie für diese Bestellung probierte Ziele bekommen
    score=∞ (Standard-UCB1-Initialisierung: erst alles mindestens einmal
    versuchen) - das erste unbesuchte Ziel in Iterationsreihenfolge gewinnt
    dabei immer, ein simpler, aber korrekter Kurzschluss (Ties werden sonst
    nie durch einen späteren ebenfalls-unbesuchten Kandidaten ersetzt)."""
    best_j, best_score = None, None
    for j in candidates_j:
        n = ucb_tries.get((oid, j), 0)
        if n == 0:
            return j
        s = ucb_successes.get((oid, j), 0)
        score = (s / n) + c * math.sqrt(math.log(ucb_total + 1) / n)
        if best_score is None or score > best_score:
            best_score, best_j = score, j
    return best_j


def perturb_batches(batches, orders, capacity, item_sizes, rng, ucb_tries, ucb_successes, ucb_total, n_moves=ILS_PERTURB_STRENGTH, ucb_c=UCB_EXPLORATION_C):
    """Verschiebt n_moves zufällige, zulässige Bestellungen in einen anderen
    (noch passenden) Batch - OHNE Bewertung, auch wenn das die Distanz
    kurzfristig verschlechtert. Diversifikation für Iterated Local Search:
    ohne eine solche Störung würde die nachfolgende Lokalsuche immer wieder
    im selben lokalen Optimum landen, aus dem sie gestartet ist.

    Die QUELL-Bestellung wird weiterhin gleichverteilt zufällig gewählt
    (eine gezielte "schlechteste zuerst"-Auswahl wurde geprüft und verworfen,
    siehe README - sie schränkt die Vielfalt der ausprobierten Züge ein).
    Die ZIEL-Batch-Wahl dagegen nutzt UCB1 (siehe _select_ucb_target,
    Auer et al. 2002) statt gleichverteiltem Zufall - im Gegensatz zur
    ebenfalls verworfenen reinen Erfolgs-Verstärkung (Pheromon-Zielwahl,
    siehe README) verhindert der explizite Unsicherheits-Bonus, dass sich
    die Auswahl auf wenige "bewährte" Ziele einpendelt. `ucb_tries`/
    `ucb_successes` (Dicts, Schlüssel (Bestellung, Ziel-Batch)) und
    `ucb_total` (Gesamtzahl bisheriger Versuche) werden vom Aufrufer über
    alle ILS-Neustarts hinweg mitgeführt und nach jedem Neustart aktualisiert
    (siehe iterated_local_search_history) - hier nur gelesen, nicht selbst
    verändert.

    Gibt zusätzlich zurück, WELCHE Batch-Indizes tatsächlich verändert
    wurden (für den Warm-Start in iterated_local_search_history: nur diese
    Batches müssen nach der Störung neu geprüft werden, alle anderen
    übernehmen ihre Route/Distanz unverändert aus der vorherigen besten
    Lösung) sowie die Liste der getroffenen (Bestellung, Ziel-Batch)-
    Entscheidungen (für die UCB1-Aktualisierung nach dem Neustart). Leere
    Batches werden am Ende herausgefiltert; die zurückgegebenen Indizes
    werden dabei passend umgerechnet - auch wenn dieser Fall dank der
    "len(order_ids) <= 1: continue"-Absicherung nie eintritt (ein Batch mit
    nur einer Bestellung wird nie als Quelle gewählt, kann also nie leer
    zurückbleiben), kostet die Absicherung nichts und macht die Funktion
    robust gegen künftige Änderungen an dieser Regel."""
    batches = [dict(b) for b in batches]
    touched = set()
    decisions = []
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
        j = _select_ucb_target(oid, candidates_j, ucb_tries, ucb_successes, ucb_total, ucb_c)
        batches[i] = {"order_ids": [o for o in batches[i]["order_ids"] if o != oid], "items": [k for k in batches[i]["items"] if k not in order_items]}
        batches[j] = {"order_ids": batches[j]["order_ids"] + [oid], "items": batches[j]["items"] + order_items}
        touched.update({i, j})
        decisions.append((oid, j))
    kept = [(idx, b) for idx, b in enumerate(batches) if b["order_ids"]]
    new_batches = [b for _, b in kept]
    index_map = {old: new for new, (old, _) in enumerate(kept)}
    touched_remapped = {index_map[t] for t in touched if t in index_map}
    return new_batches, touched_remapped, decisions


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
    jede verworfene Störung mit anzuzeigen.

    WARM START je Neustart (siehe README-Benchmark): perturb_batches
    verändert i.d.R. nur 2-4 der vielen Batches. Für alle anderen, von der
    Störung unberührten Batches wird Route + Distanz unverändert aus der
    aktuell besten Lösung übernommen, statt sie per Nearest-Neighbor neu
    aufzubauen - und die Don't-Look-Bits-Warteschlange startet direkt mit
    genau den berührten Batches statt mit allen. Das spart nicht nur
    Rechenzeit (die Suche muss nicht erst durch lauter bereits optimale
    Batches "durchlaufen"), sondern findet auch tendenziell bessere
    Ergebnisse: eine kalt bei Batch 0 gestartete Suche verbraucht ihr
    First-Improvement-Zugbudget oft an längst optimierten Batches, bevor sie
    überhaupt bei der eigentlichen Störungsstelle ankommt.

    UCB1-ZIELWAHL (siehe README-Benchmark): `ucb_tries`/`ucb_successes`
    zählen über ALLE Neustarts hinweg, wie oft welches (Bestellung,
    Ziel-Batch)-Paar in perturb_batches gewählt wurde und wie oft das zu
    einer neuen besten Lösung führte - nach jedem Neustart aktualisiert,
    unabhängig davon, ob er selbst verbessert hat (auch Fehlschläge zählen
    als "Versuch", nur nicht als "Erfolg")."""
    rng = random.Random(seed)
    history = _inter_batch_search_dlb(batches, orders, capacity, item_sizes, D, max_moves)
    best_batches, best_routes, best_dist = history[-1]
    best_dists = [route_distance(r, D) for r in best_routes]

    ucb_tries, ucb_successes, ucb_total = {}, {}, 0
    t_start = time.time()
    for _ in range(max_restarts):
        if time.time() - t_start > time_budget_s:
            break
        perturbed, touched, decisions = perturb_batches(
            best_batches, orders, capacity, item_sizes, rng, ucb_tries, ucb_successes, ucb_total, perturb_strength
        )

        cand_routes, cand_dists = [], []
        for idx, b in enumerate(perturbed):
            if idx in touched or idx >= len(best_routes):
                r = nearest_neighbor_route(b["items"], D)
                cand_routes.append(r)
                cand_dists.append(route_distance(r, D))
            else:
                cand_routes.append(best_routes[idx])
                cand_dists.append(best_dists[idx])

        active_init = touched if touched else range(len(perturbed))
        cand_history = _inter_batch_search_dlb_from_state(
            perturbed, cand_routes, cand_dists, orders, capacity, item_sizes, D, active_init, max_moves
        )
        cand_batches, cand_routes, cand_dist = cand_history[-1]
        improved = cand_dist < best_dist - EPS
        for oid, j in decisions:
            ucb_tries[(oid, j)] = ucb_tries.get((oid, j), 0) + 1
            if improved:
                ucb_successes[(oid, j)] = ucb_successes.get((oid, j), 0) + 1
        ucb_total += 1
        if improved:
            best_batches, best_routes, best_dist = cand_batches, cand_routes, cand_dist
            best_dists = [route_distance(r, D) for r in best_routes]
            history.append((best_batches, best_routes, best_dist))

    safe_routes, safe_total = _apply_final_safety_net(best_batches, best_routes, D)
    history[-1] = (best_batches, safe_routes, safe_total)
    return history
