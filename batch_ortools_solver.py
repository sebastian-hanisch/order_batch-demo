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

from batch_constants import EPS

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
