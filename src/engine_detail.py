"""Strict parsing of the selected engine's displayed order-detail metrics."""
from __future__ import annotations

import math
import re
import unicodedata


# Both the catalog collector and checkout probe must identify the same loaded
# detail response. The native inline assignment is independent of the catalog
# header, which changes before the asynchronous detail is replaced.
MODEL_DETAIL_IDENTITY_JS = r"""(panel => {
  const id = panel.getAttribute('data-model-id');
  const scripts = typeof panel.querySelectorAll === 'function' ? panel.querySelectorAll('script') : [];
  const scriptIds = Array.from(scripts).flatMap(el =>
    Array.from(String(el.textContent || '').matchAll(
      /\bacId\s*=\s*([1-9][0-9]{0,11})\s*;/g), match => match[1]));
  const scriptId = scriptIds.length ? scriptIds[0] : null;
  if (scriptIds.some(value => value !== scriptId) ||
      (id !== null && scriptId !== null && id !== scriptId)) return null;
  return {attribute_present: id !== null, model_id: id, script_model_id: scriptId};
})"""


def _normalize(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c)).casefold().strip()


# Only documented units are accepted. In particular a price in the detail
# panel is an advertised amount, never a verified final checkout total.
_FIELDS = {
    "speed_kph": (("cruise speed", "velocidade de cruzeiro"), "kph|km/h", 10000),
    "capacity_pax": (("capacity", "capacidade"), "pax", 10000),
    "required_runway_ft": (("runway required", "pista necessaria"), "ft", 50000),
    "range_km": (("range", "alcance"), "km", 100000),
    "fuel_lbs_per_km": (("consumption", "consumo"), "lbs/km", 10000),
    "co2_kg_per_pax_km": (("co2 emission", "co₂ emission", "emissao de co2", "emissao de co₂"),
                          "kg/pax/km", 100),
    "a_check_cost_usd": (("a-check",), None, 10**12),
    "maintenance_interval_hours": (("maint check", "verificacao de manutencao"),
                                   "hours?|horas?", 100000),
    "displayed_cost_usd": ((), None, 10**12),
}
_INTEGER_FIELDS = {"capacity_pax", "required_runway_ft", "range_km",
                   "a_check_cost_usd", "maintenance_interval_hours", "displayed_cost_usd"}


def _number(text: object, unit: str | None, maximum: int) -> float | None:
    if not isinstance(text, str):
        return None
    # Grouped thousands and optional decimal fraction in the observed game format.
    number = r"(?:[1-9]\d{0,2}(?:,\d{3})+|\d+)(?:\.\d+)?"
    pattern = (rf"({number})\s*(?:{unit})" if unit
               else rf"\$?\s*({number})")
    match = re.fullmatch(pattern, text.strip(), re.IGNORECASE)
    if not match:
        return None
    value = float(match[1].replace(",", ""))
    return value if math.isfinite(value) and 0 < value <= maximum else None


def validate_metrics(raw: object) -> dict | None:
    """Validate normalized storage without accepting booleans or extra fields."""
    if not isinstance(raw, dict) or not raw or not raw.keys() <= _FIELDS.keys():
        return None
    clean = {}
    for key, value in raw.items():
        maximum = _FIELDS[key][2]
        if type(value) not in (int, float) or not 0 < value <= maximum:
            return None
        if key in _INTEGER_FIELDS:
            if int(value) != value:
                return None
            value = int(value)
        clean[key] = value
    return clean


def parse_displayed_metrics(raw: object) -> dict | None:
    """Read labelled rows and the dedicated displayed cost as partial evidence."""
    if not isinstance(raw, dict) or not isinstance(raw.get("rows"), list):
        return None
    rows = raw["rows"]
    if len(rows) > 100:
        return None
    result = {}
    for field, (labels, unit, maximum) in _FIELDS.items():
        if field == "displayed_cost_usd":
            values = raw.get("costs", [])
            if not isinstance(values, list):
                return None
        else:
            values = [row[1] for row in rows if isinstance(row, list) and len(row) == 2
                      and isinstance(row[0], str) and _normalize(row[0]) in labels]
        if len(values) > 1:
            return None
        if not values:
            continue
        value = _number(values[0], unit, maximum)
        if value is None:
            return None
        result[field] = value
    return validate_metrics(result)


def validate_seat_observation(raw: object, capacity: object) -> dict | None:
    """A native form reading, distinct from a confirmed purchasable layout."""
    if (not isinstance(raw, dict) or raw.keys() != {"source", "y", "j", "f"}
            or raw["source"] not in ("hidden_native_template", "visible_native_form")
            or type(capacity) is not int or not 0 < capacity <= 10000):
        return None
    if any(type(raw[key]) is not int or not 0 <= raw[key] <= capacity for key in ("y", "j", "f")):
        return None
    if raw["y"] + 2 * raw["j"] + 3 * raw["f"] != capacity:
        return None
    return dict(raw)


def parse_seat_observation(raw: object, capacity: object) -> dict | None:
    if not isinstance(raw, dict) or raw.keys() != {"source", "y", "j", "f"}:
        return None
    values = {"source": raw["source"]}
    for key in ("y", "j", "f"):
        value = raw[key]
        if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]{0,4})", value):
            return None
        values[key] = int(value)
    return validate_seat_observation(values, capacity)
