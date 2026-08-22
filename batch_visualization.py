"""
2D-Lagergrundriss mit Plotly: Gänge als vertikale Linien zwischen vorderer
und hinterer Quergasse, Packstation links vorne, Artikelpositionen als
Punkte (farblich nach Batch), Kommissionierrouten als verbundene Linien
Depot -> Positionen -> Depot. Dasselbe Grund-Layout-Muster wie in den 2D-
Demos (Hallengrundriss der Tor-Zuordnung-Demo, Straßennetz der
Tourenplanung-Demo): eine Übersichtsfigur für alle Batches gleichzeitig,
eine Detailfigur für einen einzelnen ausgewählten Batch.
"""

import plotly.graph_objects as go

from batch_constants import AISLE_COLOR, BATCH_COLORS, BATCH_MARKER_SYMBOLS, CROSS_AISLE_COLOR, DEPOT_COLOR
from batch_evaluation import route_leg_distances
from batch_warehouse import aisle_x

MAX_HEIGHT_PX = 620
MIN_HEIGHT_PX = 320


def _batch_style(batch_idx):
    """Farbe UND Marker-Symbol für einen Batch-Index - dieselbe Funktion wird
    von der Übersichts- UND der Detailfigur genutzt, damit ein Batch überall
    gleich aussieht (vorher: die Detailfigur nutzte fest BATCH_COLORS[0],
    unabhängig vom tatsächlich ausgewählten Batch - auf Nutzeranfrage
    behoben). Sobald mehr Batches als Farben existieren, wechselt zusätzlich
    das Symbol (siehe BATCH_MARKER_SYMBOLS in batch_constants.py), damit
    auch dann kein Batch mit einem anderen verwechselbar ist."""
    color = BATCH_COLORS[batch_idx % len(BATCH_COLORS)]
    symbol = BATCH_MARKER_SYMBOLS[(batch_idx // len(BATCH_COLORS)) % len(BATCH_MARKER_SYMBOLS)]
    return color, symbol


def _figure_height(n_aisles, aisle_length, aisle_spacing, width_hint_px=800):
    x_range = n_aisles * aisle_spacing + 2 * aisle_spacing
    y_range = aisle_length + 10
    height = width_hint_px * (y_range / max(x_range, 1e-6))
    return max(MIN_HEIGHT_PX, min(MAX_HEIGHT_PX, height))


def _add_layout_shapes(fig, n_aisles, aisle_length, aisle_spacing):
    depot_x = -aisle_spacing
    for a in range(n_aisles):
        x = aisle_x(a, aisle_spacing)
        fig.add_trace(
            go.Scatter(
                x=[x, x], y=[0, aisle_length], mode="lines",
                line=dict(color=AISLE_COLOR, width=6), hoverinfo="skip", showlegend=False,
            )
        )
    last_x = aisle_x(n_aisles - 1, aisle_spacing) if n_aisles > 0 else 0
    fig.add_trace(
        go.Scatter(
            x=[depot_x, last_x], y=[0, 0], mode="lines",
            line=dict(color=CROSS_AISLE_COLOR, width=3), hoverinfo="skip", showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[0, last_x], y=[aisle_length, aisle_length], mode="lines",
            line=dict(color=CROSS_AISLE_COLOR, width=3), hoverinfo="skip", showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[depot_x], y=[0], mode="markers+text", text=["Depot"], textposition="bottom center",
            marker=dict(size=14, symbol="star", color=DEPOT_COLOR, line=dict(width=1, color="white")),
            hovertext="Packstation (Depot)", hoverinfo="text", showlegend=False,
        )
    )


def build_warehouse_overview_figure(aisles, positions, aisle_length, aisle_spacing, batches, final_routes, width_hint_px=800):
    """Übersicht aller Batches gleichzeitig: Artikelpositionen farblich nach
    Batch, jede Batch-Route als eigene Linie Depot -> Positionen -> Depot."""
    fig = go.Figure()
    n_aisles = int(max(aisles)) + 1 if len(aisles) else 1
    _add_layout_shapes(fig, n_aisles, aisle_length, aisle_spacing)

    depot_x = -aisle_spacing
    for b_idx, (batch, route) in enumerate(zip(batches, final_routes)):
        color, symbol = _batch_style(b_idx)
        route_x = [depot_x] + [aisle_x(aisles[i], aisle_spacing) for i in route] + [depot_x]
        route_y = [0] + [positions[i] for i in route] + [0]
        fig.add_trace(
            go.Scatter(
                x=route_x, y=route_y, mode="lines", line=dict(color=color, width=1.5),
                opacity=0.55, hoverinfo="skip", showlegend=False,
            )
        )
        item_x = [aisle_x(aisles[i], aisle_spacing) for i in batch["items"]]
        item_y = [positions[i] for i in batch["items"]]
        fig.add_trace(
            go.Scatter(
                x=item_x, y=item_y, mode="markers", name=f"Batch {b_idx + 1}",
                marker=dict(size=9, symbol=symbol, color=color, line=dict(width=1, color="white")),
                hovertext=[f"Batch {b_idx + 1}" for _ in item_x], hoverinfo="text",
            )
        )

    fig.update_layout(
        xaxis=dict(autorange=True, title="Gang", zeroline=False),
        yaxis=dict(autorange=True, title="Position im Gang (m)", zeroline=False, scaleanchor="x"),
        height=_figure_height(n_aisles, aisle_length, aisle_spacing, width_hint_px),
        margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h", y=-0.12),
    )
    return fig


def build_batch_detail_figure(aisles, positions, aisle_length, aisle_spacing, batch, route, D, batch_idx=0, width_hint_px=800):
    """Detailansicht eines einzelnen Batches: Positionen in Besuchsreihenfolge
    nummeriert, Route als durchgezogene Linie. `batch_idx` sorgt dafür, dass
    Farbe UND Symbol mit der Übersichtsfigur übereinstimmen (siehe
    _batch_style) - ohne Angabe (Default 0) fällt die Funktion auf die erste
    Palettenfarbe zurück, für Aufrufer, denen der Index egal ist.

    Auf Nutzeranfrage ergänzt, um das Ergebnis nachvollziehbarer zu machen:
    jeder Halt zeigt beim Hover die Distanz DIESES Wegabschnitts (vom Depot
    bzw. vom vorherigen Halt), nicht nur die nummerierte Reihenfolge - so
    lässt sich sehen, WO die Gesamtdistanz eines Batches herkommt (siehe
    route_leg_distances in batch_evaluation.py)."""
    fig = go.Figure()
    n_aisles = int(max(aisles)) + 1 if len(aisles) else 1
    _add_layout_shapes(fig, n_aisles, aisle_length, aisle_spacing)

    depot_x = -aisle_spacing
    color, symbol = _batch_style(batch_idx)
    route_x = [depot_x] + [aisle_x(aisles[i], aisle_spacing) for i in route] + [depot_x]
    route_y = [0] + [positions[i] for i in route] + [0]
    fig.add_trace(
        go.Scatter(
            x=route_x, y=route_y, mode="lines+markers", line=dict(color=color, width=2.5),
            marker=dict(size=8, symbol=symbol, color=color, line=dict(width=1, color="white")),
            hoverinfo="skip", showlegend=False,
        )
    )
    item_x = [aisle_x(aisles[i], aisle_spacing) for i in route]
    item_y = [positions[i] for i in route]
    labels = [str(k + 1) for k in range(len(route))]
    leg_dists = route_leg_distances(route, D)
    hover_texts = [
        f"{k + 1}. Halt - {leg_dists[k]:.0f} m {'vom Depot' if k == 0 else 'vom vorherigen Halt'}"
        for k in range(len(route))
    ]
    fig.add_trace(
        go.Scatter(
            x=item_x, y=item_y, mode="markers+text", text=labels, textposition="top center",
            marker=dict(size=14, symbol=symbol, color=color, line=dict(width=1.5, color="white")),
            hovertext=hover_texts, hoverinfo="text", showlegend=False,
        )
    )

    fig.update_layout(
        xaxis=dict(autorange=True, title="Gang", zeroline=False),
        yaxis=dict(autorange=True, title="Position im Gang (m)", zeroline=False, scaleanchor="x"),
        height=_figure_height(n_aisles, aisle_length, aisle_spacing, width_hint_px),
        margin=dict(l=10, r=10, t=30, b=10),
    )
    return fig
