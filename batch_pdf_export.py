"""
Erzeugt einen einsatzfähigen Kommissionier-Batchplan als downloadbares PDF
(in-memory, kein Zwischenspeichern auf Disk nötig) - dasselbe Muster wie in
den anderen Demos (siehe z. B. vrp_pdf_export.py).
"""

import time

from batch_constants import CAPACITY_MODE_POSITIONS, DEFAULT_COST_PER_HOUR, DEFAULT_PICK_TIME_S, DEFAULT_WALKING_SPEED_MPS
from batch_evaluation import batch_capacity_size, capacity_summary_text, distance_to_business, solution_totals


def generate_batch_plan_pdf(label, batches, final_routes, order_ids_by_item, aisles, positions, D, capacity, capacity_mode, item_sizes, walking_speed_mps=DEFAULT_WALKING_SPEED_MPS, pick_time_s=DEFAULT_PICK_TIME_S, cost_per_hour=DEFAULT_COST_PER_HOUR):
    """Ein PDF mit einer Zusammenfassungsseite und einer Positions-Tabelle je
    Batch, in der von der Route vorgegebenen Kommissionier-Reihenfolge.
    `order_ids_by_item` bildet einen Artikel-Index auf seine Bestellnummer
    ab (für die Tabellenspalte "Bestellung"). Im Volumen-Kapazitätsmodus
    bekommt die Tabelle zusätzlich eine Volumen-Spalte je Position."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    total_dist = solution_totals(final_routes, D)
    n_items_total = sum(len(r) for r in final_routes)
    total_hours, total_cost, throughput = distance_to_business(total_dist, n_items_total, len(batches), walking_speed_mps, pick_time_s, cost_per_hour)
    show_volume = capacity_mode != CAPACITY_MODE_POSITIONS

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"Kommissionier-Batchplan - {label}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, f"Erstellt: {time.strftime('%d.%m.%Y %H:%M')} Uhr", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Zusammenfassung", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Anzahl Batches: {len(batches)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Anzahl Bestellungen: {sum(len(b['order_ids']) for b in batches)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Anzahl Positionen: {n_items_total}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Kapazitätsart: {capacity_mode}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Gesamte Laufdistanz: {total_dist:.0f} m", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Geschätzte Kommissionierzeit: {total_hours:.1f} h", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Geschätzte Personalkosten: {total_cost:.0f} EUR (bei {cost_per_hour:.2f} EUR/h)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Durchsatz: {throughput:.0f} Positionen/h", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    for b_idx, (batch, route) in enumerate(zip(batches, final_routes)):
        cap_used = batch_capacity_size(batch["items"], item_sizes)
        summary = capacity_summary_text(len(batch["items"]), cap_used, capacity, capacity_mode)
        util_pct = 100 * cap_used / capacity if capacity > 0 else 0.0
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(
            0, 8,
            f"Batch {b_idx + 1}  ({len(batch['order_ids'])} Bestellungen, {summary}, {util_pct:.0f}% Auslastung)",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )

        if show_volume:
            headers = ["#", "Bestellung", "Gang", "Position (m)", "Volumen (l)"]
            widths = [10, 34, 26, 32, 28]
        else:
            headers = ["#", "Bestellung", "Gang", "Position (m)"]
            widths = [12, 40, 30, 40]
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(235, 235, 235)
        for h, w in zip(headers, widths):
            pdf.cell(w, 7, h, border=1, fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.ln(7)

        pdf.set_font("Helvetica", "", 9)
        for i, item in enumerate(route):
            row = [str(i + 1), str(order_ids_by_item[item]), str(int(aisles[item]) + 1), f"{positions[item]:.1f}"]
            if show_volume:
                row.append(f"{item_sizes[item]:.1f}")
            for val, w in zip(row, widths):
                pdf.cell(w, 6, val, border=1, new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.ln(6)
        pdf.ln(5)

    return bytes(pdf.output())
