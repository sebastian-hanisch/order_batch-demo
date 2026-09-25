"""
Bewertungsfunktionen für Batches: Routendistanz, Kapazitätsauslastung sowie
die Umrechnung von Distanz in geschäftliche Kennzahlen (Kommissionierzeit,
Personalkosten, Durchsatz). Gemeinsame Bewertungsgrundlage für beide
Batching-Strategien (Greedy-Seed, Zonen-Sweep) - macht den Vergleich fair.

`item_sizes` (auf Nutzeranfrage ergänzt) macht die Kapazitätsprüfung
kapazitätsart-agnostisch: im Positionen-Modus ist item_sizes ein Array aus
lauter Einsen (jede Position zählt 1, das bisherige Verhalten), im
Volumen-Modus das tatsächliche Volumen je Position - dieselben Funktionen
(`batch_capacity_size`, `batch_capacity_excess`) funktionieren für beide
Modi unverändert, nur das übergebene Array unterscheidet sich."""

from batch_constants import CAPACITY_MODE_POSITIONS, EPS


def route_distance(route, D):
    """Distanz einer Kommissionierroute: Depot (Index 0) -> Artikel in
    Reihenfolge -> Depot. `route` ist eine Liste 0-basierter Artikel-Indizes."""
    if not route:
        return 0.0
    nodes = [0] + [i + 1 for i in route] + [0]
    # D[a, b] statt D[a][b]: echtes 2D-Indexing statt erst eine Zeilen-
    # Ansicht zu erzeugen und darin zu indizieren - spart bei der heissesten
    # inneren Schleife der Inter-Batch-Suche messbar Zeit (siehe README).
    return sum(D[nodes[k], nodes[k + 1]] for k in range(len(nodes) - 1))


def route_leg_distances(route, D):
    """Distanz JEDES einzelnen Wegabschnitts (Depot -> erster Halt -> ... ->
    letzter Halt -> Depot), in Besuchsreihenfolge - die Summe entspricht
    route_distance(route, D). Auf Nutzeranfrage ergänzt, um das Ergebnis
    nachvollziehbarer zu machen: zeigt in der UI (Hover-Text je Halt,
    Rückweg-Distanz in der Bildunterschrift), WO die Gesamtdistanz eines
    Batches tatsächlich anfällt, statt nur die Summe zu nennen. Bewusst als
    eigenständige, einfache Funktion (nicht von route_distance
    wiederverwendet) - route_distance ist ein bereits sorgfältig
    optimierter Hot-Path (siehe README-Benchmark zur numpy-Indexierung),
    den diese rein UI-seitige Ergänzung nicht anfassen soll."""
    if not route:
        return []
    nodes = [0] + [i + 1 for i in route] + [0]
    return [D[nodes[k], nodes[k + 1]] for k in range(len(nodes) - 1)]


def batch_capacity_size(items, item_sizes):
    """Wie stark ein Batch die Kapazität beansprucht, in der aktiven
    Kapazitätseinheit (Anzahl Positionen oder Summe Volumen)."""
    return float(sum(item_sizes[i] for i in items))


def batch_capacity_excess(batch, capacity, item_sizes):
    """Wie stark ein Batch die Kapazität überschreitet (0, wenn er sie
    einhält) - kann bei einer Einzelbestellung auftreten, die für sich
    genommen schon größer als die Batch-Kapazität ist. Toleranz EPS
    deckt sich mit der Akzeptanzschwelle `capacity + EPS` der Inter-Batch-
    Lokalsuche (batch_local_search.py), damit ein Batch, den die Suche als
    zulässig behandelt hat, hier nicht durch Fließkomma-Rundung (z. B. bei
    aufsummierten Volumen) fälschlich als überladen gilt."""
    size = batch_capacity_size(batch["items"], item_sizes)
    return 0.0 if size <= capacity + EPS else size - capacity


def capacity_summary_text(n_items, cap_used, capacity, capacity_mode):
    """Menschlich lesbare Auslastungs-Angabe für Batch-Labels/PDF, abhängig
    vom aktiven Kapazitätsmodus. Im Volumen-Modus wird zusätzlich die
    Positionsanzahl genannt (weiterhin relevant für die Pickzeit), im
    Positionen-Modus wäre das redundant."""
    if capacity_mode == CAPACITY_MODE_POSITIONS:
        return f"{n_items}/{capacity:.0f} Positionen"
    return f"{n_items} Positionen, {cap_used:.1f}/{capacity:.1f} l"


def solution_totals(final_routes, D):
    """Gesamtdistanz über alle Batches einer Strategie (Summe der einzelnen,
    unabhängig voneinander optimierten Batch-Routen)."""
    return sum(route_distance(r, D) for r in final_routes)


def distance_to_business(total_distance_m, n_items, walking_speed_mps, pick_time_s, cost_per_hour):
    """Rechnet Gesamtdistanz + Gesamtzahl kommissionierter Positionen in
    Kommissionierzeit (h), Personalkosten (€) und Durchsatz (Positionen/h)
    um. Die Pickzeit selbst (pick_time_s * n_items) ist über alle
    Batching-Strategien hinweg identisch - jede Position wird so oder so
    genau einmal gepickt. Nur die Laufzeit unterscheidet sich, abhängig
    davon, wie viele Depot-Rundwege und wie viel Gangwechsel eine Strategie
    verursacht - genau das macht Batching wirtschaftlich relevant."""
    walk_time_s = total_distance_m / walking_speed_mps if walking_speed_mps > 0 else 0.0
    pick_time_total_s = pick_time_s * n_items
    total_hours = (walk_time_s + pick_time_total_s) / 3600.0
    labor_cost = total_hours * cost_per_hour
    throughput_per_hour = n_items / total_hours if total_hours > 0 else 0.0
    return total_hours, labor_cost, throughput_per_hour


def _relative_gap_pct(candidate, best):
    """Relative Distanz-Differenz von `candidate` zu `best` in Prozent -
    gegen eine Best-Distanz nahe 0 abgesichert (sonst Division durch
    (fast) 0). Aus classify_comparison herausgezogen (Code-Review-Fund,
    2026-08-23, dritte Runde): dieselbe Berechnung stand vorher zweimal
    im Funktionskörper (einmal für den schlechtesten, einmal für den
    zweitbesten Kandidaten) - ein künftiger Fix an der EPS-Absicherung
    oder der Vorzeichen-Richtung hätte leicht in einer der beiden Kopien
    vergessen werden können, was all_tied/top_two_tied inkonsistent
    zueinander hätte werden lassen."""
    if best["total_distance"] <= EPS:
        return 0.0
    return 100 * (candidate["total_distance"] - best["total_distance"]) / best["total_distance"]


def classify_comparison(candidates, tie_threshold_pct=1.0):
    """Stuft einen Methodenvergleich als eindeutig/unentschieden ein, anhand
    der relativen Differenz zur jeweils besten Gesamtdistanz - vermeidet eine
    Aussage wie 'X liegt vorn', wenn der Unterschied praktisch im Rauschen
    liegt (dasselbe Muster wie in der Packungsoptimierung-Demo)."""
    ranked = sorted(candidates, key=lambda c: c["total_distance"])
    best, worst = ranked[0], ranked[-1]
    all_tied = _relative_gap_pct(worst, best) <= tie_threshold_pct
    top_two_tied = False
    if len(ranked) > 2 and not all_tied:
        top_two_tied = _relative_gap_pct(ranked[1], best) <= tie_threshold_pct
    return {
        "ranked": ranked, "best": best, "worst": worst,
        "all_tied": all_tied, "top_two_tied": top_two_tied,
        "is_tied": all_tied or top_two_tied,
    }
