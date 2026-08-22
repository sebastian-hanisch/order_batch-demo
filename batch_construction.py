"""
Zwei selbst implementierte Batching-Strategien für das Order-Batching-
Problem: Kundenbestellungen zu Kommissionier-Batches gruppieren, die je ein
Kommissionierer in einer Tour abarbeitet, unter einer Kapazitätsgrenze.

Die Kapazität wird über `item_sizes` übergeben (ein Array, ein Wert je
Position): im Positionen-Modus sind das lauter Einsen (jede Position zählt
1, das ursprüngliche Modell), im Volumen-Modus das tatsächliche Volumen je
Position - auf Nutzeranfrage ergänzt, weil "Positionen" bei sehr
heterogenen Artikelgrößen (z. B. Grocery/General Merchandise) den
tatsächlichen Flaschenhals (Kartonvolumen) nicht abbildet. Beide Strategien
funktionieren für beide Modi unverändert, nur das übergebene Array
unterscheidet sich.

- greedy_seed_batching: klassisches Seed-Verfahren aus der Batching-
  Literatur (z. B. Gademann & van de Velde 2005, "Order batching to
  minimize total travel time in a parallel-aisle warehouse"): startet jeden
  neuen Batch mit der größten noch unverteilten Bestellung ("Seed") und
  füllt ihn greedy mit den Bestellungen auf, deren Positionen dem
  bisherigen Batch-Schwerpunkt am nächsten liegen, bis die Kapazität
  erreicht ist.

- zone_clustering_batching: Sortiert Bestellungen nach ihrem Gang-Schwer-
  punkt (Zonen-Sweep, dasselbe Grundprinzip wie der Sweep-Algorithmus in
  der Tourenplanung-Demo, nur entlang der Gänge statt um ein Depot). Jeder
  neue Batch startet mit der nächsten noch unverteilten Bestellung in dieser
  Sortierreihenfolge (dem räumlich "nächsten" Lagerbereich) und wird danach
  - wie bei greedy_seed_batching - mit der jeweils NÄCHSTGELEGENEN noch
  passenden Bestellung aufgefüllt, bis niemand mehr passt.

  Ursprünglich (auf Nutzeranfrage benchmarkt) packte diese Funktion strikt
  First-Fit in Sortierreihenfolge: sobald die nächste Bestellung in der
  Sortierung nicht mehr passte, wurde der Batch sofort geschlossen, auch
  wenn eine SPÄTERE Bestellung in der Sortierung noch gepasst hätte. Über
  200 Testinstanzen lag das im Schnitt 3,9% hinter Greedy-Seed-Batching
  zurück, in Szenarien mit knapper Batch-Kapazität sogar 9,7% - verschenkte
  Kapazität führt zu unnötig vielen zusätzlichen Depot-Rundwegen. Die jetzige
  Nächste-Passende-Bestellung-Auffüllung senkt den Rückstand im selben
  Benchmark auf nur noch 0,8% im Schnitt (in mehreren Szenarien liegt sie
  jetzt sogar vorn) - der räumliche Sweep bestimmt weiterhin, WO ein neuer
  Batch startet, verschenkt aber keine Kapazität mehr blind an die starre
  Sortierreihenfolge.

Beide geben eine Liste von Batches zurück: [{"order_ids": [...], "items":
[...]}, ...]. "items" enthält 0-basierte Indizes in die globalen
aisles/positions-Arrays. Übersteigt eine einzelne Bestellung bereits die
Kapazität, bildet sie einen eigenen, überfüllten Batch (siehe
batch_capacity_excess in batch_evaluation.py) statt die Konstruktion
abzubrechen - realistischer als ein harter Fehler, echte Bestellungen lassen
sich schließlich nicht teilen.
"""

import numpy as np

from batch_constants import EPS


def _order_stats(orders, aisles, positions, item_sizes):
    """Je Bestellung: Kapazitätsgröße (Summe item_sizes - Positionsanzahl
    ODER Volumen, je nach Modus) und räumlicher Schwerpunkt (Ø Gang,
    Ø Position). Der Schwerpunkt wird bewusst nach PositionsANZAHL
    gewichtet aktualisiert (siehe greedy_seed_batching), nicht nach
    Kapazitätsgröße - eine schwere/großvolumige Einzelposition soll den
    räumlichen Schwerpunkt nicht stärker verschieben als mehrere leichte."""
    cap_sizes, n_items, centroids = {}, {}, {}
    for oid, items in orders.items():
        cap_sizes[oid] = float(sum(item_sizes[i] for i in items))
        n_items[oid] = len(items)
        centroids[oid] = (
            float(np.mean([aisles[i] for i in items])),
            float(np.mean([positions[i] for i in items])),
        )
    return cap_sizes, n_items, centroids


def _centroid_distance(c1, c2, aisle_spacing):
    """Grobe Annäherung an die tatsächliche Lager-Distanz zwischen zwei
    Bestell-Schwerpunkten (Manhattan-artig: Gangwechsel kostet
    aisle_spacing je Gang, plus Positionsunterschied im Gang) - dient nur
    als Auswahlkriterium, welche Bestellung als nächstes zum Batch passt,
    nicht als exakte Routendistanz (die liefert erst die 2-opt-Verbesserung
    je Batch, siehe batch_local_search.py)."""
    a1, y1 = c1
    a2, y2 = c2
    return abs(a1 - a2) * aisle_spacing + abs(y1 - y2)


def greedy_seed_batching(orders, capacity, aisles, positions, aisle_spacing, item_sizes):
    cap_sizes, n_items, centroids = _order_stats(orders, aisles, positions, item_sizes)
    remaining = set(orders.keys())
    batches = []

    while remaining:
        seed = max(remaining, key=lambda o: cap_sizes[o])
        remaining.discard(seed)
        batch_orders = [seed]
        batch_items = list(orders[seed])
        batch_n_items = n_items[seed]
        cap_left = capacity - cap_sizes[seed]
        cx, cy = centroids[seed]

        while cap_left > EPS and remaining:
            candidates = [o for o in remaining if cap_sizes[o] <= cap_left + EPS]
            if not candidates:
                break
            best = min(candidates, key=lambda o: _centroid_distance(centroids[o], (cx, cy), aisle_spacing))
            n_before = batch_n_items
            batch_orders.append(best)
            batch_items += orders[best]
            batch_n_items += n_items[best]
            cap_left -= cap_sizes[best]
            remaining.discard(best)
            # Batch-Schwerpunkt aktualisieren (nach Positionsanzahl gewichteter
            # Mittelwert), damit die nächste Auswahl den tatsächlich bereits
            # gewachsenen Batch berücksichtigt statt weiter nur den Seed.
            bx, by = centroids[best]
            cx = (cx * n_before + bx * n_items[best]) / batch_n_items
            cy = (cy * n_before + by * n_items[best]) / batch_n_items

        batches.append({"order_ids": batch_orders, "items": batch_items})

    return batches


def zone_clustering_batching(orders, capacity, aisles, positions, item_sizes, aisle_spacing):
    cap_sizes, n_items, centroids = _order_stats(orders, aisles, positions, item_sizes)
    remaining = sorted(orders.keys(), key=lambda o: centroids[o])
    batches = []

    while remaining:
        seed = remaining.pop(0)
        batch_orders = [seed]
        batch_items = list(orders[seed])
        batch_n_items = n_items[seed]
        cap_used = cap_sizes[seed]
        cx, cy = centroids[seed]

        while True:
            cap_left = capacity - cap_used
            candidates = [o for o in remaining if cap_sizes[o] <= cap_left + EPS]
            if not candidates:
                break
            best = min(candidates, key=lambda o: _centroid_distance(centroids[o], (cx, cy), aisle_spacing))
            n_before = batch_n_items
            batch_orders.append(best)
            batch_items += orders[best]
            batch_n_items += n_items[best]
            cap_used += cap_sizes[best]
            remaining.remove(best)
            bx, by = centroids[best]
            cx = (cx * n_before + bx * n_items[best]) / batch_n_items
            cy = (cy * n_before + by * n_items[best]) / batch_n_items

        batches.append({"order_ids": batch_orders, "items": batch_items})

    return batches


def singleton_batches(orders):
    """Ein Batch je Bestellung, keine Zusammenlegung - repräsentiert die
    unoptimierte Ausgangslage ohne Order-Batching (jede Bestellung wird
    einzeln kommissioniert). Kontrastfolie für die Primäransicht, analog zur
    naiven Baseline in der Tourenplanung-Demo."""
    return [{"order_ids": [oid], "items": list(items)} for oid, items in orders.items()]
