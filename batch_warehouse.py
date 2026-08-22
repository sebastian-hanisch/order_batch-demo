"""
Lagerlayout und Distanzberechnung: parallele Gänge zwischen einer vorderen
und einer hinteren Quergasse (das Standardmodell der Kommissionier-
Literatur, z. B. bei Roodbergen & de Koster für S-Shape/Return/Largest-Gap-
Routing vorausgesetzt), plus eine feste Packstation ("Depot") am linken Ende
der vorderen Quergasse.

Weg zwischen zwei Positionen im selben Gang: einfache Differenz der
Position entlang des Gangs. Weg zwischen zwei Positionen in verschiedenen
Gängen: der Picker muss über eine der beiden Quergassen wechseln - genommen
wird die kürzere der beiden Routen (vorne oder hinten herum). Das ist eine
analytische Formel statt eines Graphen mit networkx (wie im Straßennetz der
Tourenplanung-Demo): bei nur zwei Quergassen an den Gang-Enden lässt sich
der kürzeste Weg direkt berechnen, ein Shortest-Path-Algorithmus auf einem
Gittergraphen käme auf dasselbe Ergebnis, nur langsamer.
"""

import numpy as np


def item_distance(aisle_a, pos_a, aisle_b, pos_b, aisle_spacing, aisle_length):
    """Kürzester Weg zwischen zwei Lagerpositionen. Gleicher Gang: direkte
    Differenz. Unterschiedliche Gänge: Minimum aus dem Weg über die vordere
    und über die hintere Quergasse."""
    if aisle_a == aisle_b:
        return abs(pos_a - pos_b)
    cross = abs(aisle_a - aisle_b) * aisle_spacing
    via_front = pos_a + pos_b + cross
    via_back = (aisle_length - pos_a) + (aisle_length - pos_b) + cross
    return min(via_front, via_back)


def depot_distance(aisle, pos, aisle_spacing):
    """Weg von der Packstation (vorne links, vor Gang 0) zu einer
    Lagerposition: immer über die vordere Quergasse, da die Packstation
    selbst dort liegt - der Umweg über hinten kann nie kürzer sein."""
    return aisle * aisle_spacing + pos


def build_distance_matrix(aisles, positions, aisle_spacing, aisle_length):
    """Distanzmatrix über alle Artikelpositionen plus Depot. Index 0 = Depot
    (Packstation), Index i+1 = Artikel i (0-basiert in `aisles`/`positions`).
    Dasselbe Konventions-Muster wie D in der Tourenplanung-Demo (vrp_network.py)."""
    n = len(aisles)
    D = np.zeros((n + 1, n + 1))
    for i in range(n):
        d = depot_distance(aisles[i], positions[i], aisle_spacing)
        D[0][i + 1] = d
        D[i + 1][0] = d
    for i in range(n):
        for j in range(i + 1, n):
            d = item_distance(aisles[i], positions[i], aisles[j], positions[j], aisle_spacing, aisle_length)
            D[i + 1][j + 1] = d
            D[j + 1][i + 1] = d
    return D


def aisle_x(aisle_idx, aisle_spacing):
    """x-Koordinate eines Gangs für die Visualisierung (Gang 0 bei x=0)."""
    return aisle_idx * aisle_spacing
