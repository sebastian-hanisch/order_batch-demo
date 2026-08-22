"""
Wiederverwendbares Streamlit-UI-Panel für eine einzelne Batching-Strategie
(Greedy-Seed oder Zonen-Sweep): Kennzahlen, Inter-Batch-Umverteilungs-
Historie (Übersicht aller Batches mit eigenem Iterations-Slider), Detail-
ansicht eines ausgewählten Batches mit 2-opt-Iterations-Slider + Auto-Play,
PDF-Export. Wird einmal pro Strategie-Tab in app.py aufgerufen.

Zwei UNABHÄNGIGE Iterations-Slider mit unterschiedlicher fachlicher
Bedeutung:
- Die Inter-Batch-Historie (`ib_history`) zeigt, wie die Bestellungen
  schrittweise zwischen Batches umverteilt werden (Relocate/Swap) - ein
  Fortschritt über die GESAMTE Lösung.
- Der 2-opt-Slider im "Batch im Detail"-Abschnitt bezieht sich dagegen auf
  die Route INNERHALB eines einzelnen, bereits feststehenden Batches - ein
  gemeinsamer Iterationszähler über alle Batches hätte hier keine echte
  fachliche Bedeutung, da jeder Batch unabhängig geroutet wird.
"""

import time

import numpy as np
import streamlit as st

from batch_evaluation import batch_capacity_size, capacity_summary_text, distance_to_business, route_leg_distances
from batch_pdf_export import generate_batch_plan_pdf
from batch_visualization import build_batch_detail_figure, build_warehouse_overview_figure


def render_batching_panel(prefix, label, batches, histories, ib_history, order_ids_by_item, aisles, positions, aisle_length, aisle_spacing, D, capacity, capacity_mode, item_sizes, walking_speed_mps, pick_time_s, cost_per_hour):
    final_routes = [h[-1][0] for h in histories]
    total_dist = sum(h[-1][1] for h in histories)
    n_items_total = sum(len(r) for r in final_routes)
    n_orders_total = sum(len(b["order_ids"]) for b in batches)
    n_batches = len(batches)
    cap_used = [batch_capacity_size(b["items"], item_sizes) for b in batches]
    avg_util_pct = 100 * float(np.mean([u / capacity for u in cap_used])) if n_batches and capacity > 0 else 0.0
    overloaded = [i for i, u in enumerate(cap_used) if u > capacity]

    total_hours, total_cost, throughput = distance_to_business(total_dist, n_items_total, n_batches, walking_speed_mps, pick_time_s, cost_per_hour)

    if overloaded:
        st.warning(
            f"⚠️ {len(overloaded)} Batch(es) überschreiten die Kapazität ({capacity:.1f}) - "
            "mindestens eine Einzelbestellung ist für sich genommen größer als die eingestellte "
            "Batch-Kapazität und kann nicht aufgeteilt werden."
        )

    ib_construction_dist = ib_history[0][2]
    ib_saved_pct = 0.0 if ib_construction_dist <= 0 else 100 * (ib_construction_dist - total_dist) / ib_construction_dist

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Laufdistanz", f"{total_dist:.0f} m", delta=f"-{ib_saved_pct:.1f}% ggü. reiner Konstruktion", delta_color="inverse")
    m2.metric("Anzahl Batches", f"{n_batches} (für {n_orders_total} Bestellungen)")
    m3.metric("Ø Auslastung", f"{avg_util_pct:.0f} %")
    m4.metric("Kommissionierzeit", f"{total_hours:.1f} h")
    st.caption(
        f"ℹ️ Personalkosten: {total_cost:.0f} € (bei {cost_per_hour:.2f} €/h) · Durchsatz: "
        f"{throughput:.0f} Positionen/h · {pick_time_s:.0f}s Pickzeit je Position, "
        f"{walking_speed_mps:.1f} m/s Gehgeschwindigkeit (einstellbar in der Seitenleiste)."
    )

    st.markdown("**Batch-Zuteilung optimieren (Bestellungen zwischen Batches verschieben/tauschen)**")
    n_ib_steps = len(ib_history)
    if n_ib_steps > 1:
        ib_auto_play = st.checkbox("▶️ Umverteilung automatisch abspielen", key=f"{prefix}_ib_auto")
        ib_step = st.slider(
            "Zuteilungs-Iteration", 0, n_ib_steps - 1, n_ib_steps - 1, key=f"{prefix}_ib_step",
            help="0 = direkt nach der Konstruktion (Greedy-Seed bzw. Zonen-Sweep), Maximum = nach "
            "Inter-Batch-Lokalsuche + Iterated Local Search. Zwischenschritte zeigen jeden Zug der "
            "ersten Konvergenz sowie jeden Neustart, der eine neue beste Lösung gefunden hat - "
            "verworfene (nicht-verbessernde) Neustarts werden nicht einzeln angezeigt.",
        )
    else:
        ib_auto_play = False
        ib_step = 0
        st.info("Die Inter-Batch-Suche hat keine verbessernde Umverteilung gefunden.")

    ib_batches_snap, ib_routes_snap, ib_dist_snap = ib_history[ib_step]
    ib_plot_slot = st.empty()
    fig_overview = build_warehouse_overview_figure(aisles, positions, aisle_length, aisle_spacing, ib_batches_snap, ib_routes_snap)
    ib_plot_slot.plotly_chart(fig_overview, width="stretch", key=f"{prefix}_overview_plot_{ib_step}")
    st.caption(
        f"Gesamtdistanz beim angezeigten Schritt: {ib_dist_snap:.0f} m "
        f"(nach reiner Konstruktion: {ib_construction_dist:.0f} m)."
    )

    if ib_auto_play:
        for s in range(n_ib_steps):
            snap_batches, snap_routes, _snap_dist = ib_history[s]
            f = build_warehouse_overview_figure(aisles, positions, aisle_length, aisle_spacing, snap_batches, snap_routes)
            ib_plot_slot.plotly_chart(f, width="stretch", key=f"{prefix}_ib_auto_{s}")
            time.sleep(0.15)

    st.markdown("**Batch im Detail**")
    batch_labels = [
        f"Batch {i + 1} ({len(b['order_ids'])} Bestellungen, {capacity_summary_text(len(b['items']), cap_used[i], capacity, capacity_mode)})"
        for i, b in enumerate(batches)
    ]
    batch_choice = st.selectbox("Batch auswählen", batch_labels, key=f"{prefix}_batch_select")
    batch_idx = batch_labels.index(batch_choice)
    batch = batches[batch_idx]
    history = histories[batch_idx]
    n_steps = len(history)

    # Auf Nutzeranfrage ergänzt, um nachvollziehbarer zu machen, WARUM genau
    # diese Bestellungen zusammen im selben Batch gelandet sind: die
    # räumliche Streuung (wie viele Gänge werden angelaufen?) - Bestellungs-
    # und Positionsanzahl stehen bereits im Dropdown-Label oben, deshalb hier
    # bewusst nicht wiederholt.
    batch_aisles = [aisles[i] for i in batch["items"]]
    min_aisle, max_aisle = min(batch_aisles), max(batch_aisles)
    aisle_span = max_aisle - min_aisle + 1
    span_word = "Gang" if aisle_span == 1 else "Gängen"
    st.caption(
        f"📍 Die Positionen dieses Batches liegen in {aisle_span} {span_word} "
        f"(Gang {min_aisle + 1} bis {max_aisle + 1}) - je enger räumlich beieinander, desto kürzer die Route."
    )

    if n_steps > 1:
        auto_play = st.checkbox("▶️ 2-opt-Verbesserung automatisch abspielen", key=f"{prefix}_auto_{batch_idx}")
        step = st.slider(
            "Verbesserungs-Iteration", 0, n_steps - 1, n_steps - 1, key=f"{prefix}_step_{batch_idx}",
            help="0 = Nearest-Neighbor-Startroute, Maximum = nach 2-opt-Verbesserung (lokales Optimum).",
        )
    else:
        auto_play = False
        step = 0
        st.info("Die 2-opt-Verbesserung hat für diesen Batch keine bessere Reihenfolge gefunden.")

    route_snapshot, dist_snapshot = history[step]
    fig_detail = build_batch_detail_figure(aisles, positions, aisle_length, aisle_spacing, batch, route_snapshot, D, batch_idx=batch_idx)
    plot_slot = st.empty()
    plot_slot.plotly_chart(fig_detail, width="stretch", key=f"{prefix}_detail_plot_{batch_idx}_{step}")
    return_leg = route_leg_distances(route_snapshot, D)[-1] if route_snapshot else 0.0
    st.caption(
        f"Distanz dieses Batches beim angezeigten Schritt: {dist_snapshot:.0f} m (Start: {history[0][1]:.0f} m) "
        f"· Rückweg vom letzten Halt zum Depot: {return_leg:.0f} m - Distanz je Zwischenhalt siehe Hover-Text im Plot."
    )

    if auto_play:
        for s in range(n_steps):
            snap, _ = history[s]
            f = build_batch_detail_figure(aisles, positions, aisle_length, aisle_spacing, batch, snap, D, batch_idx=batch_idx)
            plot_slot.plotly_chart(f, width="stretch", key=f"{prefix}_auto_{batch_idx}_{s}")
            time.sleep(0.15)

    pdf_bytes = generate_batch_plan_pdf(label, batches, final_routes, order_ids_by_item, aisles, positions, D, capacity, capacity_mode, item_sizes, walking_speed_mps, pick_time_s, cost_per_hour)
    st.download_button(
        "📄 Batchplan als PDF herunterladen", data=pdf_bytes,
        file_name=f"batchplan_{prefix}.pdf", mime="application/pdf", key=f"{prefix}_pdf_download",
    )

    return {
        "key": prefix, "label": label, "total_distance": total_dist, "n_batches": n_batches,
        "n_orders": n_orders_total, "avg_utilization_pct": avg_util_pct, "total_hours": total_hours,
        "total_cost": total_cost, "throughput": throughput, "final_routes": final_routes,
        "batches": batches, "infeasible": len(overloaded) > 0,
    }
