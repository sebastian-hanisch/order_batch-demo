"""
Exakter/nahe-exakter Vergleichslöser mit Googles CP-SAT (Open Source,
Apache 2.0, Teil von OR-Tools) - auf Nutzeranfrage ergänzt, um kleine
Instanzen exakt lösen und mit den eigenen Heuristiken vergleichen zu
können.

Nicht die OR-Tools-Routing-Bibliothek (wie in der Tourenplanung-Demo),
sondern der allgemeine Constraint-Solver: das Order-Batching-Problem
(Partitionierung UND Routing gleichzeitig) lässt sich damit sauber als ein
einziges Modell formulieren. Ein erster Versuch mit der Routing-Bibliothek
(jede Position als Routing-Knoten, "gleiches Fahrzeug" für Positionen
derselben Bestellung über eine VehicleVar-Gleichheit erzwungen) scheiterte:
Standard-Konstruktionsheuristiken ignorieren diese Nebenbedingung
(ROUTING_INVALID), ein Workaround über AddPickupAndDelivery-Verkettung
funktionierte nur für Bestellungen mit sehr wenigen Positionen und stürzte
mit der Konstruktionsheuristik PATH_CHEAPEST_ARC bei etwas größeren
Instanzen sogar mit einem echten Segfault ab (empirisch reproduziert).

Modell: Zuordnungsvariablen y[o,k] (Bestellung o -> Batch-Slot k) plus je
Batch-Slot ein Hamiltonkreis über Depot + ALLE Positionen (model.AddCircuit),
wobei nicht diesem Batch zugeteilte Positionen per Selbstschleife
übersprungen werden ("optional node"-Muster) - Positionen sind nur dann
über eine echte Kante verbunden, wenn ihre jeweilige Bestellung diesem
Batch-Slot zugeordnet ist. Kapazität, Zielfunktion (Gesamtdistanz) und eine
einfache Symmetriebrechung (Bestellung i darf nur in Batch-Slot <= i landen)
ergänzen das Modell. Für Batches mit mehreren Positionen ist das exakt
dasselbe Traveling-Salesman-Teilproblem, das sonst Nearest-Neighbor + 2-opt
löst - hier aber exakt statt heuristisch.

Anders als die eigenen Heuristiken skaliert das nicht auf realistische
Instanzgrößen: die Anzahl Bogen-Variablen wächst mit num_batches *
n_items^2, und CP-SAT beweist echte Optimalität nur innerhalb des
Zeitlimits (siehe CPSAT_MAX_TIME_LIMIT) - bei größeren Instanzen liefert es
bestenfalls eine gute, aber nicht nachweislich optimale Lösung (Status
FEASIBLE statt OPTIMAL), im ungünstigsten Fall gar keine (UNKNOWN). Deshalb
zusätzlich CPSAT_MAX_MODEL_SIZE als harte Obergrenze - jenseits davon dauert
bereits der reine Modellaufbau mehrere Sekunden bis Minuten, unabhängig vom
Zeitlimit für die eigentliche Suche.
"""

import time

from batch_constants import EPS
from batch_evaluation import route_distance

CPSAT_SCALE = 100


def estimated_model_size(n_items, num_batches):
    """Grobe Näherung an die Anzahl Bogen-Variablen des CP-SAT-Modells -
    dient als billige Vorab-Abschätzung, ob sich der Modellaufbau überhaupt
    lohnt, ohne ihn tatsächlich zu starten."""
    return num_batches * (n_items + 1) ** 2


def recommended_num_batches(orders, capacity, item_sizes, slack=1):
    """Enge, aber garantiert zulässige Obergrenze für die Anzahl Batch-Slots:
    die kleinstmögliche Anzahl (Gesamtgröße / Kapazität, aufgerundet) plus
    etwas Spielraum (slack) für ggf. bessere Aufteilungen - eng genug, um
    die Modellgröße klein zu halten, aber nie enger als das theoretische
    Minimum."""
    total_size = sum(sum(item_sizes[i] for i in items) for items in orders.values())
    minimum = max(1, -(-int(round(total_size)) // max(1, int(round(capacity))))) if capacity > 0 else len(orders)
    return min(len(orders), minimum + slack)


def solve_with_cpsat(orders, capacity, item_sizes, D, num_batches, time_limit_s):
    """Löst das Order-Batching-Problem (Zuteilung + Routing gemeinsam) exakt
    bzw. nahe-exakt mit CP-SAT. Gibt (batches, status, wall_time_s) zurück:
    `batches` ist `None`, wenn innerhalb des Zeitlimits nicht einmal eine
    zulässige Lösung gefunden wurde (Status "UNKNOWN"/"INFEASIBLE"),
    ansonsten eine Liste von {"order_ids": [...], "items": [...],
    "route": [...]} - "route" ist bereits die vom Solver gefundene
    Besuchsreihenfolge (0-basierte Item-Indizes), keine weitere 2-opt-
    Politur nötig oder sinnvoll. `status` ist "OPTIMAL" (nachweislich
    optimal), "FEASIBLE" (beste gefundene Lösung, Optimalität nicht
    bewiesen) oder "UNKNOWN"/"INFEASIBLE"."""
    from ortools.sat.python import cp_model

    n_items = len(item_sizes)
    order_ids = list(orders.keys())
    item_order = {}
    for oid, items in orders.items():
        for i in items:
            item_order[i] = oid

    model = cp_model.CpModel()

    y = {}
    for oid in order_ids:
        for k in range(num_batches):
            y[oid, k] = model.NewBoolVar(f"y_{oid}_{k}")
        model.AddExactlyOne(y[oid, k] for k in range(num_batches))

    order_size = {oid: int(round(sum(item_sizes[i] for i in orders[oid]) * CPSAT_SCALE)) for oid in order_ids}
    cap_scaled = int(round(capacity * CPSAT_SCALE))
    for k in range(num_batches):
        model.Add(sum(y[oid, k] * order_size[oid] for oid in order_ids) <= cap_scaled)

    # Symmetriebrechung: Batch-Slots sind untereinander austauschbar - ohne
    # diese Einschränkung würde CP-SAT viele Zeit mit strukturell
    # gleichwertigen Umsortierungen der Slot-Nummerierung verschwenden.
    for oi, oid in enumerate(order_ids):
        for k in range(num_batches):
            if k > oi:
                model.Add(y[oid, k] == 0)

    distance_terms = []
    arc_lits_by_batch = []
    for k in range(num_batches):
        used_k = model.NewBoolVar(f"used_{k}")
        model.AddMaxEquality(used_k, [y[oid, k] for oid in order_ids])

        node_active = {0: used_k}
        for i in range(n_items):
            node_active[i + 1] = y[item_order[i], k]

        arcs = []
        for node, active in node_active.items():
            arcs.append((node, node, active.Not()))

        arc_lits = {}
        for a in range(n_items + 1):
            for b in range(n_items + 1):
                if a == b:
                    continue
                lit = model.NewBoolVar(f"arc_{k}_{a}_{b}")
                model.AddImplication(lit, node_active[a])
                model.AddImplication(lit, node_active[b])
                arcs.append((a, b, lit))
                arc_lits[a, b] = lit
                distance_terms.append(lit * int(round(D[a, b] * CPSAT_SCALE)))

        model.AddCircuit(arcs)
        arc_lits_by_batch.append(arc_lits)

    model.Minimize(sum(distance_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 8
    cp_status = solver.Solve(model)

    if cp_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        status = "INFEASIBLE" if cp_status == cp_model.INFEASIBLE else "UNKNOWN"
        return None, status, solver.WallTime()

    status = "OPTIMAL" if cp_status == cp_model.OPTIMAL else "FEASIBLE"

    batches = []
    for k in range(num_batches):
        arc_lits = arc_lits_by_batch[k]
        next_node = {}
        for (a, b), lit in arc_lits.items():
            if solver.Value(lit):
                next_node[a] = b
        if 0 not in next_node:
            continue  # Batch-Slot ungenutzt (Depot-Selbstschleife aktiv)
        route_items = []
        node = next_node[0]
        while node != 0:
            route_items.append(node - 1)
            node = next_node[node]
        oids = sorted(set(item_order[i] for i in route_items))
        batches.append({"order_ids": oids, "items": route_items, "route": route_items})

    return batches, status, solver.WallTime()


def exact_tsp_single_batch(item_indices, D, time_limit_s):
    """Löst das Traveling-Salesman-Teilproblem EINES bereits feststehenden
    Batches exakt bzw. nahe-exakt mit CP-SAT: ein einzelner Hamiltonkreis
    über Depot + die Positionen dieses Batches (model.AddCircuit) - ohne
    Zuteilungsvariablen, da die Batch-Zusammensetzung hier schon feststeht
    (Spezialfall von solve_with_cpsat, der nur den Routing-Anteil EINES
    Batch-Slots isoliert). Genutzt als optionale Politur-Stufe für ein
    bereits fertiges Ergebnis, siehe apply_exact_tsp_polish.

    Gibt (route, distanz, status) zurück. `status` ist "OPTIMAL"
    (nachweislich optimal), "FEASIBLE" (beste gefundene Lösung, Optimalität
    nicht bewiesen) oder "UNKNOWN" (binnen Zeitlimit keine zulässige Lösung
    gefunden - bei einem Hamiltonkreis über einen vollständigen Graphen
    praktisch nur bei sehr knappem Zeitlimit und großem n überhaupt
    möglich; in diesem Fall wird die Eingabereihenfolge unverändert
    zurückgegeben, apply_exact_tsp_polish behält dann ohnehin die
    bisherige, mindestens ebenso gute heuristische Route)."""
    from ortools.sat.python import cp_model

    n = len(item_indices)
    if n <= 1:
        route = list(item_indices)
        return route, route_distance(route, D), "OPTIMAL"

    model = cp_model.CpModel()
    nodes = list(range(n + 1))

    arc_lits = {}
    arcs = []
    for a in nodes:
        for b in nodes:
            if a == b:
                continue
            lit = model.NewBoolVar(f"arc_{a}_{b}")
            arc_lits[a, b] = lit
            arcs.append((a, b, lit))
    model.AddCircuit(arcs)

    def d_scaled(a, b):
        real_a = 0 if a == 0 else item_indices[a - 1] + 1
        real_b = 0 if b == 0 else item_indices[b - 1] + 1
        return int(round(D[real_a, real_b] * CPSAT_SCALE))

    model.Minimize(sum(arc_lits[a, b] * d_scaled(a, b) for a, b in arc_lits))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 8
    cp_status = solver.Solve(model)

    if cp_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        route = list(item_indices)
        return route, route_distance(route, D), "UNKNOWN"

    next_node = {}
    for (a, b), lit in arc_lits.items():
        if solver.Value(lit):
            next_node[a] = b
    route = []
    node = next_node[0]
    while node != 0:
        route.append(item_indices[node - 1])
        node = next_node[node]

    status = "OPTIMAL" if cp_status == cp_model.OPTIMAL else "FEASIBLE"
    return route, route_distance(route, D), status


def apply_exact_tsp_polish(batches, routes, D, per_batch_time_limit_s, total_time_budget_s):
    """Politur-Stufe NACH einem bereits fertigen Ergebnis (Greedy-Seed/
    Zonen-Sweep + Inter-Batch-Suche + 2-opt, siehe batch_local_search.py):
    löst jede Batch-Route zusätzlich exakt mit CP-SAT
    (exact_tsp_single_batch) und behält je Batch die kürzere der beiden
    Routen - button-gesteuert in app.py, NICHT automatisch (siehe
    CPSAT_POLISH_TOTAL_BUDGET_S in batch_constants.py für die Begründung).

    `total_time_budget_s` deckelt die GESAMTE Politur hart, nicht nur
    einen einzelnen Batch: sobald überschritten, werden die verbleibenden
    Batches unverändert mit ihrer bisherigen heuristischen Route
    übernommen (nie schlechter als vorher, nur eben nicht zusätzlich
    geprüft) - verhindert, dass ein einzelner Klick bei vielen großen
    Batches unbegrenzt lange läuft, unabhängig vom je-Batch-Zeitlimit.

    Gibt (neue Routen, Kennzahlen-Dict) zurück - das Dict enthält u. a.
    "n_improved" (wie viele Batches tatsächlich eine kürzere Route
    bekamen) und "n_not_proven_optimal" (wie viele der TATSÄCHLICH
    geprüften Batches ihr Zeitlimit ausgeschöpft haben, ohne Optimalität
    zu beweisen) - fürs UI, um ehrlich zu kommunizieren, ob das Ergebnis
    nachweislich optimal ist oder nur "so gut wie in der verfügbaren Zeit
    gefunden"."""
    new_routes = list(routes)
    t_start = time.time()
    n_attempted = 0
    n_improved = 0
    n_skipped_budget = 0
    n_not_proven_optimal = 0

    for idx, (b, r) in enumerate(zip(batches, routes)):
        if time.time() - t_start > total_time_budget_s:
            n_skipped_budget = len(batches) - idx
            break
        n_attempted += 1
        current_dist = route_distance(r, D)
        cp_route, cp_dist, status = exact_tsp_single_batch(b["items"], D, per_batch_time_limit_s)
        if status != "OPTIMAL":
            n_not_proven_optimal += 1
        if cp_dist < current_dist - EPS:
            new_routes[idx] = cp_route
            n_improved += 1

    summary = {
        "n_batches": len(batches),
        "n_attempted": n_attempted,
        "n_improved": n_improved,
        "n_skipped_budget": n_skipped_budget,
        "n_not_proven_optimal": n_not_proven_optimal,
        "elapsed_s": time.time() - t_start,
        "total_distance": sum(route_distance(r, D) for r in new_routes),
    }
    return new_routes, summary
