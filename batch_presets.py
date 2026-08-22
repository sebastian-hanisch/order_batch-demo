"""
Ein-Klick-Beispielszenarien und Permalink-Logik - dasselbe SETTING_SPECS-
Muster wie bei den anderen Demos: eine Wahrheitsquelle für Wertebereiche,
aus der sowohl die Slider als auch die Permalink-Begrenzung lesen, inklusive
NaN/Infinity-Schutz. apply_preset nimmt (wie in der neuesten Fassung der
Tor-Zuordnung-Demo) ein Dict von SETTING_SPECS-Schlüsseln entgegen statt
positioneller Parameter, damit eine künftige Umsortierung/Erweiterung von
SETTING_SPECS nicht stillschweigend falsche Werte an die Preset-Buttons
verteilt.

`SettingSpec.choices` (auf Nutzeranfrage ergänzt für die Kapazitätsart)
erweitert dasselbe Validierungsprinzip wie `lo`/`hi` auf nicht-numerische
Einstellungen: ein Permalink-Wert, der nicht in `choices` enthalten ist,
wird genauso verworfen wie eine Zahl außerhalb von `lo`/`hi`.
"""

import math
import random
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import streamlit as st

from batch_constants import (
    CAPACITY_MODE_POSITIONS,
    CAPACITY_MODE_VOLUME,
    DEFAULT_AISLE_LENGTH,
    DEFAULT_AISLE_SPACING,
    DEFAULT_BATCH_CAPACITY,
    DEFAULT_BATCH_CAPACITY_VOLUME,
    DEFAULT_COST_PER_HOUR,
    DEFAULT_ITEM_VOLUME_MAX,
    DEFAULT_ITEM_VOLUME_MIN,
    DEFAULT_ITEMS_MAX,
    DEFAULT_ITEMS_MIN,
    DEFAULT_N_AISLES,
    DEFAULT_N_ORDERS,
    DEFAULT_PICK_TIME_S,
    DEFAULT_WALKING_SPEED_MPS,
)


@dataclass(frozen=True)
class SettingSpec:
    url_param: str
    caster: Callable
    default: object
    lo: Optional[float] = None
    hi: Optional[float] = None
    choices: Optional[Tuple] = None


SETTING_SPECS = {
    "n_orders_slider": SettingSpec("n_orders", int, DEFAULT_N_ORDERS, 5, 80),
    "items_min_slider": SettingSpec("items_min", int, DEFAULT_ITEMS_MIN, 1, 10),
    "items_max_slider": SettingSpec("items_max", int, DEFAULT_ITEMS_MAX, 1, 15),
    "item_volume_min_slider": SettingSpec("vol_min", float, DEFAULT_ITEM_VOLUME_MIN, 0.1, 20.0),
    "item_volume_max_slider": SettingSpec("vol_max", float, DEFAULT_ITEM_VOLUME_MAX, 0.1, 30.0),
    "n_aisles_slider": SettingSpec("n_aisles", int, DEFAULT_N_AISLES, 3, 24),
    "aisle_length_slider": SettingSpec("aisle_len", float, DEFAULT_AISLE_LENGTH, 10.0, 80.0),
    "aisle_spacing_slider": SettingSpec("aisle_sp", float, DEFAULT_AISLE_SPACING, 1.5, 8.0),
    "capacity_mode_radio": SettingSpec("cap_mode", str, CAPACITY_MODE_POSITIONS, choices=(CAPACITY_MODE_POSITIONS, CAPACITY_MODE_VOLUME)),
    "capacity_slider": SettingSpec("capacity", int, DEFAULT_BATCH_CAPACITY, 3, 60),
    "capacity_volume_slider": SettingSpec("capacity_vol", float, DEFAULT_BATCH_CAPACITY_VOLUME, 5.0, 300.0),
    "seed_input": SettingSpec("seed", int, 11, 0, 2_000_000_000),
    "walking_speed_slider": SettingSpec("speed", float, DEFAULT_WALKING_SPEED_MPS, 0.6, 2.2),
    "pick_time_slider": SettingSpec("pick_s", float, DEFAULT_PICK_TIME_S, 5.0, 45.0),
    "cost_per_hour_slider": SettingSpec("cost_h", float, DEFAULT_COST_PER_HOUR, 15.0, 60.0),
}


def bounds(state_key):
    spec = SETTING_SPECS[state_key]
    return spec.lo, spec.hi


def apply_preset(values):
    """values: Dict von SETTING_SPECS-Schlüssel (z. B. 'n_orders_slider') auf
    den zu setzenden Wert - iteriert über SETTING_SPECS statt sich auf eine
    feste Positionsreihenfolge zu verlassen (siehe Modul-Docstring)."""
    unknown = set(values) - set(SETTING_SPECS)
    assert not unknown, f"Unbekannte Preset-Schlüssel (kein Eintrag in SETTING_SPECS): {unknown}"
    for state_key in SETTING_SPECS:
        if state_key in values:
            st.session_state[state_key] = values[state_key]
    st.session_state["force_regen"] = True


def randomize_seed():
    """on_click-Callback für den 'Neue Bestellungen generieren'-Button -
    würfelt selbst einen neuen Seed, damit ein Klick immer sichtbar wirkt."""
    st.session_state["seed_input"] = random.randint(0, 2_000_000_000)
    st.session_state["force_regen"] = True


def load_permalink_settings():
    if "permalink_loaded" in st.session_state:
        return
    qp = st.query_params
    applied_any = False
    for state_key, spec in SETTING_SPECS.items():
        if spec.url_param in qp:
            try:
                value = spec.caster(qp[spec.url_param])
                if isinstance(value, float) and not math.isfinite(value):
                    continue
                if spec.choices is not None and value not in spec.choices:
                    continue
                if spec.lo is not None:
                    value = max(spec.lo, value)
                if spec.hi is not None:
                    value = min(spec.hi, value)
                st.session_state[state_key] = value
                applied_any = True
            except (ValueError, TypeError):
                pass
    if applied_any:
        st.session_state["force_regen"] = True
    st.session_state["permalink_loaded"] = True


def init_session_state_defaults():
    for state_key, spec in SETTING_SPECS.items():
        if state_key not in st.session_state:
            st.session_state[state_key] = spec.default


def sync_query_params(n_orders, items_min, items_max, item_volume_min, item_volume_max, n_aisles, aisle_length, aisle_spacing, capacity_mode, capacity, seed, walking_speed, pick_time, cost_per_hour):
    try:
        st.query_params["n_orders"] = str(n_orders)
        st.query_params["items_min"] = str(items_min)
        st.query_params["items_max"] = str(items_max)
        st.query_params["vol_min"] = str(item_volume_min)
        st.query_params["vol_max"] = str(item_volume_max)
        st.query_params["n_aisles"] = str(n_aisles)
        st.query_params["aisle_len"] = str(aisle_length)
        st.query_params["aisle_sp"] = str(aisle_spacing)
        st.query_params["cap_mode"] = str(capacity_mode)
        if capacity_mode == CAPACITY_MODE_VOLUME:
            st.query_params["capacity_vol"] = str(capacity)
        else:
            st.query_params["capacity"] = str(capacity)
        st.query_params["seed"] = str(int(seed))
        st.query_params["speed"] = str(walking_speed)
        st.query_params["pick_s"] = str(pick_time)
        st.query_params["cost_h"] = str(cost_per_hour)
    except Exception:
        pass
