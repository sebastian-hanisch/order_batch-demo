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

`render_exact_polish_section` (optionale CP-SAT-Politur) ist bewusst
eigenständig statt Teil von render_batching_panel: auf Nutzeranfrage auch
für das oben zusammengefasste Hauptergebnis in app.py aufrufbar, ohne dafür
den gesamten Strategie-Tab-Inhalt mit aufzubauen.
"""

import time

import numpy as np
import streamlit as st

from batch_constants import CPSAT_COOLDOWN_BUFFER, CPSAT_POLISH_TIME_LIMIT_MAX_S, CPSAT_POLISH_TOTAL_BUDGET_S
from batch_evaluation import batch_capacity_size, capacity_summary_text, distance_to_business, route_leg_distances
from batch_ortools_solver import apply_exact_tsp_polish
from batch_pdf_export import generate_batch_plan_pdf
from batch_visualization import build_batch_detail_figure, build_warehouse_overview_figure


def render_exact_polish_section(prefix, label, batches, final_routes, total_dist, order_ids_by_item, aisles, positions, aisle_length, aisle_spacing, D, capacity, capacity_mode, item_sizes, walking_speed_mps, pick_time_s, cost_per_hour):
    """Button-gesteuerte, optionale CP-SAT-Politur-Sektion (siehe
    batch_ortools_solver.py: apply_exact_tsp_polish) - löst jede Batch-Route
    ZUSÄTZLICH exakt und behält je Batch die kürzere. Eigenständige Funktion
    (nicht Teil von render_batching_panel), damit sie sowohl je Strategie-Tab
    als auch für das oben zusammengefasste Hauptergebnis (der jeweils
    bessere von beiden Strategien, siehe app.py) aufgerufen werden kann, ohne
    den gesamten Tab-Inhalt (Umverteilungs-Historie, Batch-Detail-Slider)
    zu duplizieren. `prefix` muss über alle Aufrufe hinweg eindeutig sein
    (eigener Session-State-Namespace je Aufrufstelle)."""
    st.markdown("**🎯 Touren exakt nachschärfen (optional)**")
    st.caption(
        "Löst jede der oben gezeigten Batch-Routen ZUSÄTZLICH exakt mit CP-SAT (statt "
        "Nearest-Neighbor + 2-opt) und behält je Batch die kürzere Route - die Batch-Zuteilung "
        "selbst (welche Bestellung in welchem Batch landet) bleibt dabei unverändert, nur die "
        "Reihenfolge innerhalb jeder Route wird ggf. nachgeschärft. Wegen der Rechenzeit "
        "button-gesteuert, nicht automatisch."
    )
    polish_time_limit = st.slider(
        "Zeitlimit je Batch (Sekunden)", 1, CPSAT_POLISH_TIME_LIMIT_MAX_S, CPSAT_POLISH_TIME_LIMIT_MAX_S,
        key=f"{prefix}_polish_time_limit",
        help=f"Zusätzlich hart auf {CPSAT_POLISH_TOTAL_BUDGET_S}s über ALLE Batches zusammen "
        "gedeckelt, unabhängig von diesem Regler - bei vielen großen Batches werden die "
        "verbleibenden dann unverändert mit ihrer bisherigen Route übernommen.",
    )
    # Der Key muss ALLES enthalten, wovon D (die Distanzmatrix) abhängt - nicht
    # nur aisle_spacing/aisle_length (Code-Review-Fund, 2026-08-23), sondern
    # auch aisles/positions selbst: die Batch-ITEM-INDIZES allein reichen nicht,
    # da ein direktes Bearbeiten einer Gang-/Positions-Zelle in der Bestell-
    # positionstabelle (st.data_editor) die Zeilen-Indizes unverändert lassen
    # kann (kein Regenerieren, siehe gen_key in app.py), aber D trotzdem
    # ändert - ein zweiter Fund derselben Bug-Klasse, live im Code nachvoll-
    # zogen, nicht separat reproduziert. Ohne all das hätte eine Änderung, die
    # zufällig dieselbe Batch-Zuteilung ergibt, ein bereits veraltetes
    # Politur-Ergebnis (falsche Distanz, aus dem alten D berechnet) weiter als
    # gültig angezeigt.
    polish_key = (
        tuple(tuple(b["items"]) for b in batches), polish_time_limit,
        tuple(aisles.tolist()), tuple(np.round(positions, 2).tolist()), aisle_spacing, aisle_length,
    )

    cooldown_state_key = f"{prefix}_polish_last_solve_time"
    if cooldown_state_key not in st.session_state:
        st.session_state[cooldown_state_key] = 0.0

    polish_clicked = st.button("🎯 Touren exakt nachschärfen", key=f"{prefix}_polish_btn")
    if polish_clicked:
        since_last = time.time() - st.session_state[cooldown_state_key]
        if since_last < CPSAT_COOLDOWN_BUFFER:
            st.warning(f"⏳ Bitte noch {CPSAT_COOLDOWN_BUFFER - since_last:.0f}s warten, bevor Sie erneut nachschärfen.")
        else:
            with st.spinner(f"CP-SAT schärft die Touren nach (bis zu {polish_time_limit}s je Batch)..."):
                polished_routes, polish_summary = apply_exact_tsp_polish(
                    batches, final_routes, D, polish_time_limit, CPSAT_POLISH_TOTAL_BUDGET_S,
                )
            st.session_state[cooldown_state_key] = time.time()
            st.session_state[f"{prefix}_polish_result"] = {
                "routes": polished_routes, "summary": polish_summary, "key": polish_key,
            }

    polish_result = st.session_state.get(f"{prefix}_polish_result")
    if polish_result is not None and polish_result["key"] == polish_key:
        polish_summary = polish_result["summary"]
        polished_routes = polish_result["routes"]
        saved_pct = 0.0 if total_dist <= 0 else 100 * (total_dist - polish_summary["total_distance"]) / total_dist

        if polish_summary["n_skipped_budget"] > 0:
            st.warning(
                f"⏱️ Zeitbudget ({CPSAT_POLISH_TOTAL_BUDGET_S}s) ausgeschöpft - "
                f"{polish_summary['n_skipped_budget']} von {polish_summary['n_batches']} Batches "
                "unverändert übernommen."
            )
        if polish_summary["n_improved"] == 0:
            st.info(
                "Keine Batch-Route ließ sich verbessern - die 2-opt-Lösung war für alle geprüften "
                "Batches bereits nachweislich optimal oder zumindest ebenso gut."
            )
        else:
            st.success(f"✅ {polish_summary['n_improved']} von {polish_summary['n_attempted']} geprüften Batches wurden kürzer.")
        if polish_summary["n_not_proven_optimal"] > 0:
            st.caption(
                f"⚠️ Bei {polish_summary['n_not_proven_optimal']} von {polish_summary['n_attempted']} geprüften "
                "Batches konnte Optimalität innerhalb des Zeitlimits nicht bewiesen werden (bestmögliche in "
                "der Zeit gefundene Lösung, ggf. mit mehr Zeit noch verbesserbar)."
            )

        pm1, pm2, pm3 = st.columns(3)
        pm1.metric(
            "Laufdistanz nach Politur", f"{polish_summary['total_distance']:.0f} m",
            delta=f"-{saved_pct:.1f} %" if saved_pct > 0 else None, delta_color="inverse",
        )
        pm2.metric("Geprüfte Batches", f"{polish_summary['n_attempted']}/{polish_summary['n_batches']}")
        pm3.metric("Rechenzeit", f"{polish_summary['elapsed_s']:.1f} s")

        fig_polish = build_warehouse_overview_figure(aisles, positions, aisle_length, aisle_spacing, batches, polished_routes)
        st.plotly_chart(fig_polish, width="stretch", key=f"{prefix}_polish_plot")

        pdf_bytes_polish = generate_batch_plan_pdf(
            f"{label} + CP-SAT-Politur", batches, polished_routes, order_ids_by_item, aisles, positions, D,
            capacity, capacity_mode, item_sizes, walking_speed_mps, pick_time_s, cost_per_hour,
        )
        st.download_button(
            "📄 Nachgeschärften Batchplan als PDF herunterladen", data=pdf_bytes_polish,
            file_name=f"batchplan_{prefix}_polished.pdf", mime="application/pdf", key=f"{prefix}_polish_pdf_download",
        )
    elif polish_result is not None:
        st.info("⚠️ Die Eingaben haben sich seit dieser Politur geändert - bitte erneut nachschärfen.")


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

    render_exact_polish_section(
        prefix, label, batches, final_routes, total_dist, order_ids_by_item, aisles, positions,
        aisle_length, aisle_spacing, D, capacity, capacity_mode, item_sizes, walking_speed_mps,
        pick_time_s, cost_per_hour,
    )

    return {
        "key": prefix, "label": label, "total_distance": total_dist, "n_batches": n_batches,
        "n_orders": n_orders_total, "avg_utilization_pct": avg_util_pct, "total_hours": total_hours,
        "total_cost": total_cost, "throughput": throughput, "final_routes": final_routes,
        "batches": batches, "infeasible": len(overloaded) > 0,
    }
