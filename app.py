"""
Order Batching (Kommissionier-Batchbildung) – interaktive Demo
Sebastian Hanisch - Operations Research und Machine Learning

Interaktive Demo zum Order-Batching-Problem: Kundenbestellungen werden zu
Kommissionier-Batches gruppiert, die je ein Kommissionierer in einer
einzigen Tour durchs Lager abarbeitet, begrenzt durch eine Kapazität. Ziel
ist es, die gesamte Laufdistanz zu minimieren, ohne die Zahl der zu
kommissionierenden Positionen zu verändern - jede Position wird so oder so
genau einmal gepickt, nur wie viele Depot-Rundwege und Gangwechsel dafür
nötig sind, hängt von der Gruppierung ab.

Features:
- Synthetisches Lagerlayout (parallele Gänge zwischen vorderer und hinterer
  Quergasse, das Standardmodell der Kommissionier-Literatur) statt Luftlinie.
- Zwei selbst implementierte Batching-Strategien im Vergleich: Greedy-Seed
  (klassisches Seed-Verfahren) und Zonen-Sweep (sortiert nach Gang-
  Schwerpunkt, analog zum Sweep-Algorithmus der Tourenplanung-Demo).
- Zwei umschaltbare Kapazitätsarten: max. Positionen je Batch (das
  ursprüngliche, in der Literatur übliche Modell) oder max. Volumen je
  Batch (realistischer bei sehr heterogenen Artikelgrößen, z. B. Grocery/
  General-Merchandise-Sortimenten) - auf Nutzeranfrage ergänzt.
- Je Batch eine unabhängig optimierte Kommissionierroute: Nearest-Neighbor-
  Konstruktion + 2-opt-Verbesserung, mit Iterations-Slider und Auto-Play.
- Zusätzlich eine Inter-Batch-Lokalsuche (Bestellungen zwischen Batches
  verschieben/tauschen, per Don't-Look-Bits beschleunigt) plus Iterated
  Local Search obendrauf (gezielte Störung + Neuoptimierung innerhalb eines
  Zeitbudgets), mit eigenem Iterations-Slider - schließt einen Großteil des
  Abstands zum echten Optimum, den 2-opt allein offen lässt (auf
  Nutzeranfrage benchmarkt und ergänzt, siehe README).
- Geschäftliche Kennzahlen: Kommissionierzeit, Personalkosten, Durchsatz
  statt abstrakter Distanzwerte.
- Drei Ein-Klick-Beispielszenarien, Permalink (URL spiegelt die aktuelle
  Konfiguration), PDF-Batchplan-Export, Feedback-Mechanismus.

Lauffähig mit: streamlit run app.py

Code-Struktur: Die eigentliche Logik (Algorithmen, Lagerlayout, PDF-Export,
Visualisierung, Feedback) liegt in den Modulen batch_*.py neben dieser
Datei. app.py enthält nur den Streamlit-Ablauf (Sidebar, Tabs, Vergleich) -
dasselbe Strukturprinzip wie in den anderen Demos des Portfolios.
"""

import numpy as np
import pandas as pd
import streamlit as st

from batch_constants import CAPACITY_MODE_POSITIONS, CAPACITY_MODE_VOLUME
from batch_construction import greedy_seed_batching, singleton_batches, zone_clustering_batching
from batch_evaluation import batch_capacity_excess, batch_capacity_size, classify_comparison, distance_to_business
from batch_feedback import get_feedback_counts, log_feedback
from batch_local_search import iterated_local_search_history, reconcile_per_batch_histories, route_batch
from batch_presets import apply_preset, bounds, init_session_state_defaults, load_permalink_settings, randomize_seed, sync_query_params
from batch_ui_panel import generate_batch_plan_pdf_cached, pdf_cache_key, render_batching_panel
from batch_visualization import build_warehouse_overview_figure
from batch_warehouse import build_distance_matrix, distance_scenario_key


@st.cache_data(show_spinner=False)
def _build_distance_matrix_cached(_aisles, _positions, aisle_spacing, aisle_length, distance_key):
    """Cached Wrapper um build_distance_matrix (Code-Review-Fund, 2026-08-23):
    ohne Cache lief die O(n²)-Distanzmatrix-Berechnung bei JEDEM Rerun neu,
    auch bei Widget-Interaktionen, die sie gar nicht betreffen (z. B.
    Personalkosten-Regler, Feedback-Buttons) - dasselbe Muster wie bei
    _compute_solutions unten, nur eine Ebene früher: `distance_key` trägt
    explizit alles, wovon die Distanzmatrix abhängt (aisles/positions/
    aisle_spacing/aisle_length), Arrays sind wie dort per führendem
    Unterstrich von Streamlits Hashing ausgenommen."""
    return build_distance_matrix(_aisles, _positions, aisle_spacing, aisle_length)


@st.cache_data(show_spinner="Batches werden gebildet und optimiert …")
def _compute_solutions(_orders, _aisles, _positions, capacity, aisle_spacing, aisle_length, _item_sizes, _D, cache_key):
    """Beide Batching-Strategien + die Einzelbestellungs-Baseline einmal
    zentral berechnen und cachen. Ohne Cache liefe dieser Block bei JEDEM
    Rerun neu, auch bei Widget-Interaktionen, die die Batches gar nicht
    betreffen (z. B. Personalkosten-Regler, Feedback-Buttons). Numpy-Arrays
    und das orders-Dict sind per führendem Unterstrich von Streamlits
    Hashing ausgenommen - `cache_key` trägt stattdessen explizit alles, was
    das Ergebnis beeinflusst (inkl. Kapazitätsart und Item-Größen).

    Für Greedy-Seed und Zonen-Sweep läuft nach der Konstruktion zusätzlich
    Iterated Local Search auf Basis der Inter-Batch-Lokalsuche (siehe
    batch_local_search.py: Relocate + Swap per Don't-Look-Bits, danach
    wiederholt gezielt gestört und neu optimiert, solange das Zeitbudget
    reicht) - die zurückgegebenen "batches" sind bereits das Ergebnis
    DANACH, nicht die reine Konstruktion. `ib_history` (die volle
    Umverteilungs-Historie) wird separat mitgegeben, damit das UI-Panel sie
    animieren kann. Feste, unterschiedliche Seeds je Strategie (statt
    Systemzufall) halten das Ergebnis reproduzierbar - wichtig, weil diese
    Funktion gecacht ist: ein Systemzufall würde bei jeder Cache-
    Invalidierung ein anderes Ergebnis liefern, obwohl sich an den Eingaben
    nichts geändert hat. Für die Einzelbestellungs-Baseline ergibt Inter-
    Batch-Suche keinen Sinn (jeder Batch enthält per Definition schon genau
    eine Bestellung)."""
    greedy_construction = greedy_seed_batching(_orders, capacity, _aisles, _positions, aisle_spacing, _item_sizes)
    zone_construction = zone_clustering_batching(_orders, capacity, _aisles, _positions, aisle_spacing, _item_sizes)
    naive_batches = singleton_batches(_orders)

    results = {}
    for key, construction, ils_seed in [("greedy", greedy_construction, 0), ("zone", zone_construction, 1)]:
        ib_history = iterated_local_search_history(construction, _orders, capacity, _item_sizes, _D, seed=ils_seed)
        final_batches, ib_final_routes, _final_total = ib_history[-1]
        # route_batch baut jede Route für die 2-opt-Iterations-Slider-
        # Animation von Grund auf neu auf und kann dabei einen ANDEREN,
        # nicht zwingend so guten lokalen 2-opt-Optimum finden wie die
        # verschachtelte Suche selbst (Code-Review-Fund, 2026-08-22 - siehe
        # reconcile_per_batch_histories) - sonst liefe die angezeigte
        # "Laufdistanz" gegenüber dem tatsächlichen Suchergebnis auseinander.
        per_batch_histories = [route_batch(b["items"], _D) for b in final_batches]
        per_batch_histories = reconcile_per_batch_histories(per_batch_histories, ib_final_routes, _D)
        results[key] = (final_batches, per_batch_histories, ib_history)

    naive_histories = [route_batch(b["items"], _D) for b in naive_batches]
    results["naive"] = (naive_batches, naive_histories)
    return results


st.set_page_config(page_title="Order Batching – Sebastian Hanisch", layout="wide")

st.title("🧺 Order Batching (Kommissionier-Batchbildung)")
st.markdown(
    """
Interaktive Demo zur Batchbildung beim Kommissionieren: Bestellungen werden so zu Batches
gruppiert, dass ein Kommissionierer sie in **einer** Tour durchs Lager abarbeiten kann - begrenzt
durch eine Kapazität (max. Positionen ODER max. Volumen je Batch, umschaltbar). Zwei selbst
implementierte Strategien - **Greedy-Seed-Batching** (klassisches Seed-Verfahren aus der
Batching-Literatur) und **Zonen-Sweep-Batching** (gruppiert nach Lagerbereich) - werden direkt
verglichen und durch eine **verschachtelte Lokalsuche** weiter verbessert: sowohl die
Batch-Zuteilung selbst (Bestellungen zwischen Batches verschieben/tauschen) als auch die Route je
Batch (2-opt), ergänzt um **Iterated Local Search** für gezielte Neustarts. Zielgröße ist die
gesamte Laufdistanz: weniger Weg bedeutet weniger
Kommissionierzeit und mehr Durchsatz, ohne dass sich an der Zahl der zu pickenden Positionen etwas
ändert - Hintergrund dazu im Expander "Wie funktioniert diese Demo?" unten.
"""
)

st.caption("🎯 Schnellstart – ein Beispielszenario laden:")
preset_col1, preset_col2, preset_col3 = st.columns(3)
with preset_col1:
    st.button(
        "📦 Kompaktes Lager", width="stretch",
        on_click=apply_preset, args=({
            "n_orders_slider": 18, "items_min_slider": 2, "items_max_slider": 4,
            "n_aisles_slider": 6, "aisle_length_slider": 20.0, "aisle_spacing_slider": 3.0,
            "capacity_mode_radio": CAPACITY_MODE_POSITIONS, "capacity_slider": 18, "seed_input": 4,
        },),
        help="Kleines Lager, wenige Gänge - viele Bestellungen passen zusammen in einen Batch.",
    )
with preset_col2:
    st.button(
        "🎯 Knappe Batch-Kapazität", width="stretch",
        on_click=apply_preset, args=({
            "n_orders_slider": 30, "items_min_slider": 3, "items_max_slider": 7,
            "n_aisles_slider": 10, "aisle_length_slider": 35.0, "aisle_spacing_slider": 3.0,
            "capacity_mode_radio": CAPACITY_MODE_POSITIONS, "capacity_slider": 10, "seed_input": 9,
        },),
        help="Viele mittelgroße Bestellungen bei knapper Kapazität - zeigt, wie stark die "
        "Batch-Größe die Zahl der nötigen Kommissioniertouren beeinflusst.",
    )
with preset_col3:
    st.button(
        "🛒 Heterogene Artikelgrößen", width="stretch",
        on_click=apply_preset, args=({
            "n_orders_slider": 22, "items_min_slider": 2, "items_max_slider": 6,
            "item_volume_min_slider": 0.3, "item_volume_max_slider": 12.0,
            "n_aisles_slider": 8, "aisle_length_slider": 28.0, "aisle_spacing_slider": 3.0,
            "capacity_mode_radio": CAPACITY_MODE_VOLUME, "capacity_volume_slider": 35.0, "seed_input": 21,
        },),
        help="Stark unterschiedliche Artikelgrößen (z. B. Grocery-Sortiment) mit Volumen- statt "
        "Positionskapazität - zeigt, warum die Kapazitätsart bei heterogenen Sortimenten den "
        "Unterschied macht.",
    )

st.caption(
    "🔗 Die Adresszeile oben spiegelt Ihre aktuelle Konfiguration wider – einfach kopieren, "
    "um ein Szenario zu teilen. Hinweis: manuell in der Positionstabelle bearbeitete Zeilen "
    "sind darin nicht enthalten, nur die Einstellungen, aus denen sie erzeugt werden."
)

load_permalink_settings()
init_session_state_defaults()

with st.sidebar:
    st.header("⚙️ Einstellungen")
    n_orders = st.slider("Anzahl Bestellungen", *bounds("n_orders_slider"), key="n_orders_slider")
    items_min = st.slider("Min. Positionen je Bestellung", *bounds("items_min_slider"), key="items_min_slider")
    items_max = st.slider("Max. Positionen je Bestellung", *bounds("items_max_slider"), key="items_max_slider")
    item_volume_min = st.slider(
        "Min. Volumen je Position (l)", *bounds("item_volume_min_slider"), step=0.1, key="item_volume_min_slider",
        help="Nur relevant, wenn unten als Kapazitätsart 'Volumen' gewählt ist - wird aber immer "
        "mit erzeugt, damit ein Wechsel der Kapazitätsart mitten in einer Sitzung ohne "
        "Neugenerierung der Bestellungen funktioniert.",
    )
    item_volume_max = st.slider("Max. Volumen je Position (l)", *bounds("item_volume_max_slider"), step=0.1, key="item_volume_max_slider")
    seed_lo, seed_hi = bounds("seed_input")
    seed = st.number_input("Zufalls-Seed", min_value=seed_lo, max_value=seed_hi, step=1, key="seed_input")

    st.markdown("**Lagerlayout**")
    n_aisles = st.slider("Anzahl Gänge", *bounds("n_aisles_slider"), key="n_aisles_slider")
    aisle_length = st.slider("Ganglänge (m)", *bounds("aisle_length_slider"), step=1.0, key="aisle_length_slider")
    aisle_spacing = st.slider(
        "Gangabstand (m)", *bounds("aisle_spacing_slider"), step=0.5, key="aisle_spacing_slider",
        help="Abstand zwischen zwei benachbarten Gängen - bestimmt, wie teuer ein Gangwechsel ist. "
        "Wirkt sich NICHT auf die Bestellgenerierung aus, nur auf die berechneten Distanzen.",
    )

    st.markdown("**Batch-Kapazität**")
    capacity_mode = st.radio(
        "Kapazitätsart", [CAPACITY_MODE_POSITIONS, CAPACITY_MODE_VOLUME], key="capacity_mode_radio", horizontal=True,
        help="Positionen: jede Position zählt 1, unabhängig von ihrer Größe - die in der "
        "Batching-Literatur übliche Vereinfachung, realistisch bei einheitlichen Artikelgrößen. "
        "Volumen: jede Position beansprucht ihr tatsächliches Volumen - realistischer bei stark "
        "heterogenen Sortimenten (z. B. Grocery/General Merchandise).",
    )
    if capacity_mode == CAPACITY_MODE_VOLUME:
        capacity = st.slider(
            "Max. Volumen je Batch (l)", *bounds("capacity_volume_slider"), step=1.0, key="capacity_volume_slider",
            help="Wie viel Volumen ein Kommissionierwagen/eine Tote maximal fasst - die zentrale "
            "Nebenbedingung des Order-Batching-Problems in diesem Modus.",
        )
    else:
        capacity = st.slider(
            "Max. Positionen je Batch", *bounds("capacity_slider"), key="capacity_slider",
            help="Wie viele Bestellpositionen ein Kommissionierwagen maximal gleichzeitig fassen "
            "kann - die zentrale Nebenbedingung des Order-Batching-Problems in diesem Modus.",
        )

    st.markdown("**Kommissionier-Kennzahlen**")
    walking_speed = st.slider(
        "Gehgeschwindigkeit (m/s)", *bounds("walking_speed_slider"), step=0.1, key="walking_speed_slider",
        help="Rechnet Laufdistanz in die angezeigte Kommissionierzeit um.",
    )
    pick_time = st.slider(
        "Pickzeit je Position (s)", *bounds("pick_time_slider"), step=1.0, key="pick_time_slider",
        help="Zeit zum Greifen/Scannen einer Position, unabhängig vom Weg dorthin und unabhängig "
        "von der Kapazitätsart - fließt bei JEDER Strategie identisch ein, da jede Position so "
        "oder so genau einmal gepickt wird.",
    )
    cost_per_hour = st.slider(
        "Personalkosten (€/h)", *bounds("cost_per_hour_slider"), step=0.5, key="cost_per_hour_slider",
        help="Vollkostensatz je Arbeitsstunde (Bruttolohn plus Lohnnebenkosten und anteilige "
        "Gemeinkosten), nicht der reine Bruttolohn - deshalb liegt der Wert deutlich über einem "
        "typischen Stundenlohn für Lagerpersonal.",
    )

    st.button(
        "🎲 Neue Bestellungen generieren", width="stretch", on_click=randomize_seed,
        help="Würfelt einen neuen Zufalls-Seed und erzeugt damit ein komplett neues Szenario - "
        "praktisch, ohne selbst eine neue Seed-Zahl eintippen zu müssen.",
    )

sync_query_params(capacity_mode)

if "force_regen" not in st.session_state:
    st.session_state.force_regen = False

# Nur die Bestellgenerierung tatsächlich beeinflussenden Parameter im
# gen_key - Gangabstand, Kapazität(-sart) und die Kommissionier-Kennzahlen
# wirken sich NICHT auf die erzeugten Positionen aus, nur auf die daraus
# berechneten Distanzen/Kosten (identisches Muster wie in den anderen
# Demos, siehe dortige gen_key-Kommentare).
gen_key = (n_orders, items_min, items_max, item_volume_min, item_volume_max, n_aisles, aisle_length, int(seed))
needs_init = (
    "items_df" not in st.session_state or st.session_state.force_regen
    or st.session_state.get("gen_key_cache") != gen_key
)
if needs_init:
    rng = np.random.default_rng(int(seed))
    lo, hi = min(items_min, items_max), max(items_min, items_max)
    vol_lo, vol_hi = min(item_volume_min, item_volume_max), max(item_volume_min, item_volume_max)
    order_ids, gangs, posns, vols = [], [], [], []
    for oid in range(1, n_orders + 1):
        n_items = int(rng.integers(lo, hi + 1))
        for _ in range(n_items):
            order_ids.append(oid)
            gangs.append(int(rng.integers(1, n_aisles + 1)))
            posns.append(round(float(rng.uniform(0, aisle_length)), 1))
            vols.append(round(float(rng.uniform(vol_lo, vol_hi)), 1))
    st.session_state.items_df = pd.DataFrame(
        {"id": range(1, len(order_ids) + 1), "bestellung": order_ids, "gang": gangs, "position": posns, "volumen": vols}
    )
    st.session_state.gen_key_cache = gen_key
    st.session_state.force_regen = False

st.subheader("📍 Bestellpositionen (direkt editierbar)")
edited = st.data_editor(
    st.session_state.items_df,
    num_rows="dynamic",
    width="stretch",
    column_config={
        "id": st.column_config.NumberColumn("ID", disabled=True),
        "bestellung": st.column_config.NumberColumn("Bestellung", min_value=1, step=1),
        "gang": st.column_config.NumberColumn("Gang", min_value=1, max_value=n_aisles, step=1),
        "position": st.column_config.NumberColumn("Position im Gang (m)", min_value=0.0, max_value=aisle_length, step=1.0),
        "volumen": st.column_config.NumberColumn("Volumen (l)", min_value=0.1, max_value=200.0, step=0.1),
    },
)
edited = edited.dropna(subset=["bestellung", "gang", "position", "volumen"]).reset_index(drop=True)
if edited["id"].isna().any():
    existing_ids = edited["id"].dropna()
    next_id = int(existing_ids.max()) + 1 if not existing_ids.empty else 1
    missing_mask = edited["id"].isna()
    edited.loc[missing_mask, "id"] = range(next_id, next_id + int(missing_mask.sum()))
edited["id"] = edited["id"].astype(int)
edited["bestellung"] = edited["bestellung"].astype(int)
edited["gang"] = edited["gang"].astype(int).clip(lower=1, upper=n_aisles)
edited["position"] = edited["position"].astype(float).clip(lower=0.0, upper=aisle_length)
edited["volumen"] = edited["volumen"].astype(float).clip(lower=0.1, upper=200.0)
st.session_state.items_df = edited

if len(edited) == 0:
    st.warning("Bitte mindestens eine Bestellposition anlegen.")
    st.stop()

aisles = edited["gang"].to_numpy(dtype=int) - 1
positions = edited["position"].to_numpy(dtype=float)
volumes = edited["volumen"].to_numpy(dtype=float)
order_id_col = edited["bestellung"].to_numpy(dtype=int)
item_sizes = np.ones(len(aisles)) if capacity_mode == CAPACITY_MODE_POSITIONS else volumes

orders = {}
for idx, oid in enumerate(order_id_col):
    orders.setdefault(int(oid), []).append(idx)
n_orders_eff = len(orders)

max_order_size = max(batch_capacity_size(items, item_sizes) for items in orders.values())
if max_order_size > capacity:
    unit = "Positionen" if capacity_mode == CAPACITY_MODE_POSITIONS else "l"
    st.warning(
        f"⚠️ Mindestens eine Bestellung hat {max_order_size:.1f} {unit} und übersteigt damit die "
        f"eingestellte Batch-Kapazität ({capacity:.1f} {unit}). Diese Bestellung(en) bilden einen "
        "eigenen, überfüllten Batch - Bestellungen lassen sich nicht aufteilen."
    )

distance_key = distance_scenario_key(aisles, positions, aisle_spacing, aisle_length)
D = _build_distance_matrix_cached(aisles, positions, aisle_spacing, aisle_length, distance_key)

cache_key = distance_key + (
    tuple(order_id_col.tolist()), tuple(np.round(item_sizes, 2).tolist()), capacity_mode, capacity,
)
results = _compute_solutions(orders, aisles, positions, capacity, aisle_spacing, aisle_length, item_sizes, D, cache_key)

METHODS = [
    ("greedy", "Greedy-Seed-Batching", "🌱 Greedy-Seed", "Startet jeden Batch mit der größten noch unverteilten Bestellung und füllt ihn greedy mit den Bestellungen auf, deren Positionen dem Batch-Schwerpunkt am nächsten liegen."),
    ("zone", "Zonen-Sweep-Batching", "🧭 Zonen-Sweep", "Sortiert Bestellungen nach ihrem Gang-Schwerpunkt und packt sie in dieser Reihenfolge First-Fit in Batches - Bestellungen im selben Lagerbereich landen bevorzugt zusammen."),
]

own_candidates = []
for key, label, _tab_label, _caption in METHODS:
    batches, histories, _ib_history = results[key]
    final_routes = [h[-1][0] for h in histories]
    total_dist = sum(h[-1][1] for h in histories)
    cap_excess = sum(batch_capacity_excess(b, capacity, item_sizes) for b in batches)
    own_candidates.append({
        "key": key, "label": label, "batches": batches, "histories": histories,
        "final_routes": final_routes, "total_distance": total_dist, "cap_excess": cap_excess,
    })
best_own = min(own_candidates, key=lambda c: (c["cap_excess"], c["total_distance"]))

naive_batches, naive_histories = results["naive"]
naive_final_routes = [h[-1][0] for h in naive_histories]
naive_total_dist = sum(h[-1][1] for h in naive_histories)

n_items_total = len(aisles)
naive_hours, naive_cost, naive_throughput = distance_to_business(naive_total_dist, n_items_total, len(naive_batches), walking_speed, pick_time, cost_per_hour)
best_hours, best_cost, best_throughput = distance_to_business(best_own["total_distance"], n_items_total, len(best_own["batches"]), walking_speed, pick_time, cost_per_hour)
dist_saved_pct = 0.0 if naive_total_dist <= 0 else 100 * (naive_total_dist - best_own["total_distance"]) / naive_total_dist
hours_saved = naive_hours - best_hours
cost_saved = naive_cost - best_cost

st.markdown("## 🎯 Ihr optimierter Batchplan")

if best_own["cap_excess"] > 0:
    st.warning(
        "⚠️ Mindestens ein Batch überschreitet die eingestellte Kapazität - Details unten im "
        "jeweiligen Strategie-Tab."
    )

# Vorzeichen über das "+"-Formatspec statt eines hart codierten "-"-Präfix
# (Code-Review-Fund, 2026-08-23): dist_saved_pct/hours_saved/cost_saved
# vergleichen zwei UNABHÄNGIG berechnete Ergebnisse (Batching-Heuristik vs.
# Einzelkommissionierung) ohne formale Garantie, dass Batching immer
# gewinnt - ein hart codiertes "-" hätte bei einem (per Stress-Test über
# 598 Szenarien nie beobachteten, aber nicht ausgeschlossenen) negativen
# Wert ein doppeltes Minuszeichen wie "--7%" erzeugt. `{-x:+.0f}` zeigt
# stattdessen korrekt "-23%" (Ersparnis) oder "+7%" (Mehrweg), abhängig
# vom tatsächlichen Vorzeichen - "Anzahl Touren" braucht das nicht: ein
# Batch enthält immer ≥1 Bestellung, die Batch-Anzahl kann die
# Bestellanzahl also nie übersteigen.
m1, m2, m3, m4 = st.columns(4)
m1.metric("Laufdistanz", f"{best_own['total_distance']:.0f} m", delta=f"{-dist_saved_pct:+.0f}% ggü. Einzelkommissionierung", delta_color="inverse")
m2.metric("Anzahl Touren", f"{len(best_own['batches'])}", delta=f"-{n_orders_eff - len(best_own['batches'])} ggü. Einzelkommissionierung", delta_color="inverse")
m3.metric("Kommissionierzeit", f"{best_hours:.1f} h", delta=f"{-hours_saved:+.1f} h ggü. Einzelkommissionierung", delta_color="inverse")
m4.metric("Personalkosten", f"{best_cost:.0f} €", delta=f"{-cost_saved:+.0f} € ggü. Einzelkommissionierung", delta_color="inverse")

if cost_saved > 0.5:
    st.success(
        f"💶 Gegenüber einer Kommissionierung ohne Batching (jede Bestellung einzeln, "
        f"{n_orders_eff} Touren) sparen Sie hier ca. **{cost_saved:.0f} € Personalkosten** und "
        f"**{hours_saved:.1f} Stunden Kommissionierzeit** - bei gleicher Anzahl gepickter "
        f"Positionen. Hochgerechnet auf regelmäßige Kommissionierwellen summiert sich das schnell."
    )

fig_best = build_warehouse_overview_figure(aisles, positions, aisle_length, aisle_spacing, best_own["batches"], best_own["final_routes"])
st.plotly_chart(fig_best, width="stretch", key="primary_best_plot")

pdf_bytes_best = generate_batch_plan_pdf_cached(
    "Optimierter Batchplan", best_own["batches"], best_own["final_routes"], order_id_col, aisles, positions, D,
    capacity, capacity_mode, item_sizes, walking_speed, pick_time, cost_per_hour,
    pdf_cache_key(order_id_col, aisles, positions, aisle_spacing, aisle_length, item_sizes),
)
st.download_button(
    "📄 Batchplan als PDF herunterladen", data=pdf_bytes_best,
    file_name="batchplan_optimiert.pdf", mime="application/pdf", key="primary_pdf_download",
)

st.caption(
    "Ermittelt mit der besten von zwei eigenen Batching-Strategien für dieses Szenario. Details "
    "zu beiden Strategien und dem direkten Vergleich unten."
)

st.markdown("---")

with st.expander("🔧 Wie wir das erreichen – vollständiger Strategievergleich", expanded=False):
    tab_labels = [m[2] for m in METHODS] + ["📊 Vergleich"]
    tabs = st.tabs(tab_labels)

    summaries = {}
    for (key, label, _tab_label, caption), tab in zip(METHODS, tabs[: len(METHODS)]):
        with tab:
            st.caption(caption)
            batches, histories, ib_history = results[key]
            summaries[key] = render_batching_panel(
                key, label, batches, histories, ib_history, order_id_col, aisles, positions, aisle_length,
                aisle_spacing, D, capacity, capacity_mode, item_sizes, walking_speed, pick_time, cost_per_hour,
            )

    tab_compare = tabs[len(METHODS)]

    with tab_compare:
        st.markdown("### Strategievergleich")
        comp_candidates = [summaries[m[0]] for m in METHODS]
        comp_rows = [{
            "Strategie": s["label"],
            "Laufdistanz": f"{s['total_distance']:.0f} m",
            "Anzahl Batches": s["n_batches"],
            "Ø Auslastung": f"{s['avg_utilization_pct']:.0f} %",
            "Kommissionierzeit": f"{s['total_hours']:.1f} h",
            "Personalkosten": f"{s['total_cost']:.0f} €",
            "Kapazität überschritten": "ja" if s["infeasible"] else "nein",
        } for s in comp_candidates]
        st.dataframe(pd.DataFrame(comp_rows), width="stretch", hide_index=True)
        st.caption(
            "Alle Kandidaten werden mit derselben Bewertungsfunktion auf demselben Lagerlayout "
            "verglichen - fair vergleichbar, auch wenn die Gruppierungsprinzipien sehr "
            f"unterschiedlich arbeiten. Kapazitätsart: {capacity_mode}. Kommissionierzeit/Kosten "
            f"basieren auf {walking_speed:.1f} m/s, {pick_time:.0f}s Pickzeit je Position und "
            f"{cost_per_hour:.2f} €/h (einstellbar in der Seitenleiste)."
        )

        classification = classify_comparison(comp_candidates)
        if classification["is_tied"]:
            st.info(
                "➡️ Die Kandidaten liegen hier praktisch gleichauf (Unterschied unter 1%) - kein "
                "klarer Gewinner für dieses Szenario."
            )
        else:
            winner = classification["best"]
            st.markdown(f"➡️ **{winner['label']}** liegt hier vorn (kürzeste Laufdistanz).")
            loser = classification["worst"]
            if loser["total_distance"] > 0:
                w_hours, w_cost, _ = distance_to_business(winner["total_distance"], n_items_total, winner["n_batches"], walking_speed, pick_time, cost_per_hour)
                l_hours, l_cost, _ = distance_to_business(loser["total_distance"], n_items_total, loser["n_batches"], walking_speed, pick_time, cost_per_hour)
                if l_cost - w_cost > 0.5:
                    st.markdown(
                        f"💶 Im Vergleich zu '{loser['label']}' spart '{winner['label']}' hier ca. "
                        f"**{l_cost - w_cost:.0f} € Personalkosten** und **{l_hours - w_hours:.1f} Stunden "
                        "Kommissionierzeit**."
                    )

        st.markdown("**Finale Batch-Aufteilungen im direkten Vergleich**")
        cols = st.columns(len(comp_candidates))
        for col, s in zip(cols, comp_candidates):
            with col:
                st.caption(f"{s['label']} (final)")
                fig_c = build_warehouse_overview_figure(aisles, positions, aisle_length, aisle_spacing, s["batches"], s["final_routes"], width_hint_px=380)
                st.plotly_chart(fig_c, width="stretch", key=f"compare_{s['key']}_plot")

with st.expander("Wie funktioniert diese Demo?"):
    st.markdown(
        """
**Die Problemstellung:** Beim Kommissionieren wird für jede Bestellung eine Liste von
Lagerpositionen abgelaufen und gepickt. Ohne Batching bedeutet das: eine eigene Tour je
Bestellung. Beim **Order Batching** werden mehrere Bestellungen zu einem gemeinsamen Batch
zusammengefasst, den ein Kommissionierer in **einer** Tour abarbeitet - begrenzt durch eine
Kapazität. Das Grundproblem geht auf frühe Arbeiten wie Elsayed (1981) zurück und ist seitdem
in der Warehousing-Literatur gut dokumentiert; das hier verwendete Modell (paralleles
Gang-Layout, Minimierung der gesamten Laufzeit) folgt insbesondere Gademann & van de Velde (2005).

**Lagerlayout:** Parallele Gänge zwischen einer vorderen und einer hinteren Quergasse - das in
der Kommissionier-Literatur übliche Grundmodell (z. B. bei Roodbergen & de Koster für
S-Shape-/Return-/Largest-Gap-Routing vorausgesetzt). Der Weg zwischen zwei Positionen in
unterschiedlichen Gängen führt immer über eine der beiden Quergassen - genommen wird die
kürzere der beiden Routen (vorne oder hinten herum). Die Packstation liegt fest vorne links.

**Zwei Kapazitätsarten:** Die klassische Vereinfachung in der Batching-Literatur zählt jede
Position gleich (max. Positionen je Batch) - realistisch, solange die Artikel im Sortiment
ähnlich groß sind. Bei stark heterogenen Artikelgrößen (z. B. Grocery/General Merchandise, wo
eine Position eine einzelne Tüte Gewürz oder eine Kiste Getränke sein kann) ist das Volumen der
tatsächliche Flaschenhals - deshalb lässt sich hier zwischen beiden Kapazitätsarten umschalten.
Beide Batching-Strategien und die 2-opt-Verbesserung funktionieren für beide Modi identisch, nur
die Kapazitätsprüfung rechnet je nach Modus mit Positionsanzahl oder Volumensumme.

**Greedy-Seed-Batching:** Ein klassisches Seed-Verfahren: startet jeden neuen Batch mit der
größten noch unverteilten Bestellung und füllt ihn greedy mit den Bestellungen auf, deren
Positionen dem bisherigen Batch-Schwerpunkt am nächsten liegen, bis die Kapazität erreicht ist.

**Zonen-Sweep-Batching:** Sortiert alle Bestellungen nach ihrem Gang-Schwerpunkt (analog zum
Sweep-Algorithmus der Tourenplanung-Demo, nur entlang der Gänge statt um ein Depot) und packt
sie in dieser Reihenfolge First-Fit in Batches. Bestellungen im selben Lagerbereich landen
dadurch bevorzugt im selben Batch, was Gangwechsel reduziert.

**Verschachtelte Zuteilungs- und Routen-Suche:** Nach der ersten Batch-Bildung ist noch zweierlei
offen: welche Bestellungen zusammen in einem Batch landen, UND in welcher Reihenfolge ein Batch
seine Positionen abläuft (ein eigenständiges kleines Rundreiseproblem je Batch). Ein Benchmark
gegen das echte Optimum (Vollenumeration auf winzigen Instanzen) zeigt, dass Greedy-Seed/Zonen-Sweep
allein im Schnitt noch 8-10% zurückliegen: eine Inter-Batch-Suche verschiebt
(Relocate) oder tauscht (Swap) Bestellungen zwischen Batches, wenn das die
Gesamtdistanz senkt - VERSCHACHTELT mit 2-opt-Zügen auf den einzelnen Batch-Routen, statt beides
nacheinander abzuarbeiten. Ein Batch gilt erst dann als "fertig", wenn WEDER eine bessere Zuteilung
NOCH eine bessere Route mehr gefunden wird. Grund für die Verschachtelung: bewertet man Zuteilungs-
Entscheidungen anhand einer noch nicht routenoptimierten Distanz, können suboptimale Entscheidungen
entstehen - derselbe Grundgedanke wie bei Won & Olafsson (2005), "Joint order batching and order
picking in warehouse operations". Kandidaten werden dabei per Don't-Look-Bits ausgewählt (eine
Warteschlange "auffälliger" Batches statt eines vollen Rescans bei jeder Iteration), was bei
größeren Instanzen bis zu 3x schneller ist, ohne das Ergebnis systematisch zu verschlechtern. Im
Optimum-Benchmark sank der Abstand dadurch auf 0,1%; auf realistischen Instanzgrößen ergaben sich
insgesamt rund 10-25% kürzere Gesamtdistanz gegenüber reiner Konstruktion ohne jede Verbesserung
(konsolidierter Stufen-Benchmark, Details siehe README).

**Iterated Local Search:** Reine Lokalsuche stoppt beim ERSTEN lokalen Optimum und kann es nicht
wieder verlassen - deshalb wird nach Erreichen eines lokalen Optimums gezielt
gestört (ein paar zufällige, zulässige Bestellungen werden verschoben, auch wenn das kurzfristig
verschlechtert) und danach erneut bis zum lokalen Optimum optimiert - wiederholt, solange ein
Zeitbudget reicht, das beste je gefundene Ergebnis wird behalten. Bei kleinen Instanzen passen so
viele Dutzend Neustarts in das Budget, bei großen (wo schon ein einzelner Durchlauf teuer ist) nur
wenige - das Zeitbudget skaliert sich also automatisch mit der Instanzgröße. Welches Ziel-Batch eine
verschobene Bestellung bekommt, wird dabei nicht rein zufällig gewählt, sondern per UCB1 (eine
Bandit-Explorationsstrategie aus dem Reinforcement-Learning-Bereich, Auer et al. 2002): jede
(Bestellung, Ziel)-Kombination bekommt einen Score aus bisheriger Erfolgsrate plus einem
Unsicherheits-Bonus für wenig ausprobierte Kombinationen. Ergebnis: durchweg kürzere Distanz auf
realistischen Instanzgrößen (Details zu beiden Erweiterungen und den zahlreichen geprüften, aber
wieder verworfenen Alternativen - u. a. Tabu Search, Simulated Annealing, Ant/Bee-Colony-Ideen -
siehe README).

**Warum die Pickzeit konstant bleibt:** Jede Position wird unabhängig von der Batching-Strategie
UND unabhängig von der Kapazitätsart genau einmal gepickt - die reine Pickzeit (Greifen/Scannen)
ist deshalb über alle Strategien und Modi identisch. Was sich unterscheidet, ist ausschließlich
die Laufzeit: wie viele Depot-Rundwege und Gangwechsel eine Gruppierung verursacht. Genau das
macht Order Batching wirtschaftlich relevant.

**In echten Projekten** kämen meist weitere Nebenbedingungen dazu (mehrere Kommissionierer
gleichzeitig im Lager, Kommissionierwellen mit Zeitfenstern, kombinierte Gewichts- UND
Volumengrenzen statt einer einzelnen Kapazitätsart) - das Grundprinzip aus Batch-Bildung und
Routenoptimierung je Batch bleibt aber dasselbe.
"""
    )

with st.expander("📐 Mathematische Formulierung"):
    st.markdown(
        r"""
**Gegeben:**

- Bestellungen $O = \{1, \dots, m\}$, jede Bestellung $o$ mit einer Menge von Positionen
  $P_o \subset I$ ($I$ = alle Lagerpositionen aller Bestellungen zusammen)
- eine Kapazitätsgröße $s_i \geq 0$ je Position $i \in I$ (im Positionen-Modus $s_i = 1$ für
  alle $i$, im Volumen-Modus das tatsächliche Volumen) sowie eine Kapazität $Q$ (`capacity`)
- eine Distanzfunktion $d(i, j)$ zwischen zwei Lagerpositionen bzw. zum Depot (0), abgeleitet
  aus dem Gang-/Quergassen-Layout (`item_distance`/`depot_distance` in `batch_warehouse.py`)

**Gesucht:** eine Partition der Bestellungen in Batches $B_1, \dots, B_k$ (jede Bestellung in
genau einem Batch) mit $\sum_{o \in B_v} \sum_{i \in P_o} s_i \leq Q$ für jeden Batch $v$, sowie
für jeden Batch eine Besuchsreihenfolge seiner Positionen $R_v$, die die gesamte Laufdistanz
minimiert:
"""
    )
    st.latex(
        r"\min \; \sum_{v=1}^{k} \Big[\, d(0,\,R_v(1)) "
        r"+ \sum_{t=1}^{|R_v|-1} d(R_v(t),\,R_v(t+1)) + d(R_v(|R_v|),\,0) \,\Big]"
    )
    st.latex(
        r"\text{u. d. N.} \quad \bigcup_{v=1}^{k} B_v = O, \qquad "
        r"\sum_{o \in B_v} \sum_{i \in P_o} s_i \leq Q \;\;\forall v"
    )
    st.markdown(
        r"""
Das Problem zerfällt in zwei gekoppelte Teilentscheidungen: **welche** Bestellungen in denselben
Batch kommen (eine Partitionierung unter einer Kapazitätsnebenbedingung - strukturell verwandt
mit Bin Packing, das bereits für sich NP-schwer ist, mit $s_i$ als Item-Gewicht im Bin-Packing-
Sinn), und **in welcher Reihenfolge** die Positionen eines Batches abgelaufen werden (ein
Traveling-Salesman-Problem je Batch, ebenfalls NP-schwer). Beide Entscheidungen beeinflussen sich
gegenseitig: welche Gruppierung eine kurze Route ermöglicht, hängt von den Positionen der
beteiligten Bestellungen ab - eine gemeinsame exakte Lösung ist bei realistischen
Instanzgrößen praktisch nicht mehr berechenbar. Die erste Gruppierung entsteht deshalb konstruktiv
in einem separaten ersten Schritt (Greedy-Seed bzw. Zonen-Sweep); die anschließende lokale Suche
verfeinert Zuteilung UND Route dagegen VERSCHACHTELT (siehe unten), statt beide Entscheidungen
strikt nacheinander zu optimieren.

**2-opt-Nachbarschaft je Batch:** Für eine feste Route $R$ eines Batches entsteht durch Umkehren
eines Teilstücks $[i, j]$ eine benachbarte Route $R'$. Ein Zug wird ausgeführt, wenn er die
Batch-Distanz senkt:
"""
    )
    st.latex(r"\text{Kosten}(R') < \text{Kosten}(R)")
    st.markdown(
        r"""
**Inter-Batch-Nachbarschaft:** Ergänzt um Relocate- und Swap-Nachbarschaft zwischen zwei Batches
$u, v$: Relocate verschiebt eine Bestellung $o \in B_u$ nach $B_v$ (zulässig, wenn
$\sum_{i \in P_o} s_i + \sum_{o' \in B_v} \sum_{i \in P_{o'}} s_i \leq Q$ gilt), Swap tauscht je
eine Bestellung $o_u \in B_u$ und $o_v \in B_v$. Ein Zug wird ausgeführt, wenn er die Summe der
beiden betroffenen Batch-Distanzen senkt - aus Performance-Gründen bewertet anhand einer
Cheapest-Insertion-Einfügung in die bestehende Route statt eines vollen Neu-Routings je Kandidat
(Details und die Benchmark-Zahlen dazu in `batch_local_search.py` und im README). Diese
Nachbarschaft verbessert genau die Einschränkung, die die reine 2-opt-Suche offen lässt: sie kann
die Batch-ZUTEILUNG selbst verändern, nicht nur die Route innerhalb eines Batches.

**Verschachtelung statt Reihenfolge:** Beide Nachbarschaften laufen nicht unabhängig nacheinander,
sondern gemeinsam: ein Batch gilt erst dann als "fertig", wenn WEDER die 2-opt- NOCH die
Inter-Batch-Nachbarschaft noch einen verbessernden Zug findet. Der Grund: würde man erst bis zum
2-opt-Optimum routen und danach unangetastet die Inter-Batch-Suche starten (wie ursprünglich
umgesetzt), würden Zuteilungs-Kandidatenzüge anhand noch nicht routenoptimierter Distanzen bewertet
- das kann zu suboptimalen Zuteilungsentscheidungen führen (empirisch bestätigt, siehe README). Das
Ergebnis ist ein **lokales** Optimum bezüglich der VEREINIGTEN Nachbarschaftsstruktur, weiterhin
ohne Garantie für die global beste Lösung.

**Grenze reiner Lokalsuche:** Auch die vereinigte Nachbarschaft stoppt beim ERSTEN lokalen Optimum
- es gibt keinen Mechanismus, es wieder zu verlassen, selbst wenn ein besseres lokales Optimum nur
einen ungünstigen Zwischenschritt entfernt läge. Iterated Local Search adressiert genau das: eine
Störung $p$ (ein paar zufällige, zulässige Relocates) erzeugt aus einer Lösung $\pi$ eine
benachbarte Startlösung $p(\pi)$, auf die erneut die verschachtelte Suche angewendet wird.
Wiederholt für ein Zeitbudget statt eine feste Anzahl Wiederholungen, das beste je gefundene
$\pi^*$ wird behalten - eine einfache, aber in der Metaheuristik-Literatur gut etablierte Form der
Diversifikation (Lourenço, Martin & Stützle 2003), ohne die Zusatzkomplexität einer vollständigen
Metaheuristik wie Simulated Annealing oder Tabu
Search.
"""
    )

st.markdown("---")

st.markdown("#### War diese Demo hilfreich für Sie?")
if st.session_state.get("feedback_given"):
    vote_text = "👍 positiv" if st.session_state["feedback_given"] == "up" else "👎 negativ"
    st.success(f"Danke für Ihr Feedback ({vote_text})! 🙏")
    up_count, down_count = get_feedback_counts()
    if up_count + down_count > 0:
        st.caption(f"Bisherige Stimmen: {up_count} 👍 / {down_count} 👎")
elif st.session_state.get("feedback_error"):
    st.warning("⚠️ Ihr Feedback konnte nicht gespeichert werden. Bitte versuchen Sie es später erneut.")
else:
    fb_col1, fb_col2 = st.columns(2)
    with fb_col1:
        if st.button("👍 Ja", key="feedback_up_btn", width="stretch"):
            if log_feedback("up"):
                st.session_state["feedback_given"] = "up"
            else:
                st.session_state["feedback_error"] = True
            st.rerun()
    with fb_col2:
        if st.button("👎 Nein", key="feedback_down_btn", width="stretch"):
            if log_feedback("down"):
                st.session_state["feedback_given"] = "down"
            else:
                st.session_state["feedback_error"] = True
            st.rerun()

st.caption(
    "Diese Demo ist Teil des Portfolios von Sebastian Hanisch – Operations Research "
    "und Machine Learning. Interesse an einer maßgeschneiderten Lösung für Ihr "
    "Unternehmen? [Kontakt aufnehmen](#)"
)
