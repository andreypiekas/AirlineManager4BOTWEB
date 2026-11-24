"""Persistent, read-only engine observations for each aircraft model.

Each model is researched independently inside the authenticated game's order
detail screen. A visible selector proves the engine choices, not their final
purchase price or suitability for a particular route.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
from pathlib import Path
from typing import Optional

import paths
from engine_detail import validate_metrics, validate_operational_requirements, validate_seat_observation
from engine_selection import EngineCatalog

_LOCK = threading.RLock()
_MODEL_ID = re.compile(r"^[1-9][0-9]{0,11}$")
_ENGINE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MAX_AGE_SECONDS = 3 * 86400
SOURCE = "game_aircraft_order_detail"
ROSTER_SOURCE = "game_passenger_order_list"
ROSTER_MAX_AGE_SECONDS = 900
_MAX_EPOCH = 253402300799  # End of year 9999 (UTC).
_UNSET = object()

# The native passenger list has one container, sequential listSection IDs and
# model-specific order-detail handlers. Read every card without changing sort.
MODEL_ROSTER_JS = r"""
const lists = document.querySelectorAll('#acListItems');
if (lists.length !== 1 || !window.jQuery || window.jQuery.active !== 0) return null;
const list = lists[0];
if (list.offsetParent === null || list.querySelector('img[src*="loader"], [aria-busy="true"]')) return null;
const cards = Array.from(list.children);
if (!cards.length || cards.some(el => !el.matches('.acListItem') || el.offsetParent === null)) return null;
return cards.map(el => {
  const matches = Array.from((el.getAttribute('onclick') || '').matchAll(
    /Ajax\('ac_orders\.php\?mode=detail&id=([1-9][0-9]{0,11})&charter=0','acModel',/g));
  const name = el.querySelector('b');
  return {id: matches.length === 1 ? matches[0][1] : null,
          name: name ? name.textContent.trim() : null, section: el.id};
});
"""


def _timestamp(value: object) -> int | float | None:
    """Keep fractional read times while excluding invalid/unbounded epochs."""
    if type(value) not in (int, float) or not 0 < value <= _MAX_EPOCH:
        return None
    return value



def _model_identity(model_id: object, model_name: object) -> tuple[str, str] | None:
    if (not isinstance(model_id, str) or not _MODEL_ID.fullmatch(model_id)
            or not isinstance(model_name, str) or not 0 < len(model_name.strip()) <= 120):
        return None
    return model_id, model_name.strip()


def _roster_models(rows: object) -> list[dict] | None:
    """Validate the exact observed list; never infer a missing model from counts."""
    if not isinstance(rows, list) or not 0 < len(rows) <= 10000:
        return None
    models = []
    sections = set()
    ids = set()
    for row in rows:
        if not isinstance(row, dict):
            return None
        identity = _model_identity(row.get("id"), row.get("name"))
        section = row.get("section")
        if (identity is None or identity[0] in ids or not isinstance(section, str)
                or not re.fullmatch(r"listSection[1-9][0-9]{0,4}", section)
                or section in sections):
            return None
        ids.add(identity[0])
        sections.add(section)
        models.append({"id": identity[0], "name": identity[1], "section": section})
    if sections != {f"listSection{i}" for i in range(1, len(models) + 1)}:
        return None
    return models


def _roster_coverage(state: dict, models: dict, now: object) -> dict:
    pending = {"source": ROSTER_SOURCE, "status": "unverified", "listed_model_count": None,
               "verified_model_count": None, "available_variant_count": None,
               "observed_variant_count": None, "models_with_all_variant_details": None,
               "final_prices_verified": False, "models_expires_at": None, "engines_expires_at": None}
    roster = state.get("roster")
    if not isinstance(roster, dict) or roster.get("source") != ROSTER_SOURCE:
        return pending
    stamp = _timestamp(roster.get("observed_at"))
    rows = _roster_models(roster.get("models"))
    if (stamp is None or _timestamp(now) is None or not 0 <= now - stamp <= ROSTER_MAX_AGE_SECONDS
            or rows is None):
        return pending
    attempts = state.get("attempts")
    attempts = attempts if isinstance(attempts, dict) else {}
    verified = []
    for row in rows:
        model = models.get(row["id"], {})
        attempt = attempts.get(row["id"], {})
        attempt_at = _timestamp(attempt.get("attempted_at")) if isinstance(attempt, dict) else None
        if (model.get("model") == row["name"] and model.get("model_detail_identity_verified") is True
                and isinstance(attempt, dict) and attempt.get("status") == "observed"
                and attempt.get("model") == row["name"] and attempt_at is not None
                and model["observed_at"] <= attempt_at <= now):
            verified.append(model)
    available_count = observed_count = all_details_count = 0
    for model in verified:
        available = {v["engine_id"] for v in model["variants"] if v["available"]}
        observed = available & model["variant_details"].keys()
        available_count += len(available)
        observed_count += len(observed)
        all_details_count += bool(available and available == observed)
    # A complete list is independent from the detail and checkout coverage.
    # Expire the crosswalk when either the native roster or its oldest detail expires.
    models_expires_at = None
    if len(verified) == len(rows):
        models_expires_at = min(stamp + ROSTER_MAX_AGE_SECONDS,
                                min(model["observed_at"] for model in verified) + MAX_AGE_SECONDS)
    engines_expires_at = models_expires_at if all_details_count == len(rows) else None
    return {**pending, "observed_at": stamp, "listed_model_count": len(rows),
            "models_expires_at": models_expires_at, "engines_expires_at": engines_expires_at,
            "verified_model_count": len(verified), "available_variant_count": available_count,
            "observed_variant_count": observed_count,
            "models_with_all_variant_details": all_details_count,
            "status": "details_observed" if all_details_count == len(rows) else "partial"}


def _variant_number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Métrica de motor inválida")
    number = float(value)
    if not math.isfinite(number) or not 0 < number < 1e9:
        raise ValueError("Métrica de motor fora do intervalo permitido")
    return number


def _validated_record(row: object, *, now: int | float) -> dict | None:
    if (not isinstance(row, dict) or row.get("source") != SOURCE
            or _timestamp(now) is None):
        return None
    identity = _model_identity(row.get("model_id"), row.get("model"))
    observed_at = _timestamp(row.get("observed_at"))
    if (identity is None or observed_at is None
            or not 0 <= now - observed_at <= MAX_AGE_SECONDS):
        return None
    if (row.get("selector_type") not in ("select", "radio")
            or not isinstance(row.get("selector_id"), str)
            or not row["selector_id"].strip()):
        return None
    observed_model_id = row.get("observed_model_id")
    if observed_model_id is not None and observed_model_id != identity[0]:
        return None
    identity_verified = observed_model_id == identity[0]
    if (row.get("model_detail_identity_verified", identity_verified) is not identity_verified
            or row.get("engine_prices_verified", False) is not False):
        return None
    variants = row.get("variants")
    if not isinstance(variants, list) or not variants or len(variants) > 100:
        return None
    clean = []
    identifiers = set()
    try:
        for variant in variants:
            if not isinstance(variant, dict):
                return None
            engine_id, label = variant.get("engine_id"), variant.get("label")
            if (not isinstance(engine_id, str) or not _ENGINE_ID.fullmatch(engine_id)
                    or engine_id in identifiers or not isinstance(label, str)
                    or not 0 < len(label.strip()) <= 120
                    or type(variant.get("available")) is not bool
                    or type(variant.get("selected")) is not bool):
                return None
            identifiers.add(engine_id)
            clean.append({
                "engine_id": engine_id,
                "label": label.strip(),
                "available": variant["available"],
                "selected": variant["selected"],
                "speed": _variant_number(variant.get("speed")),
                "fuel": _variant_number(variant.get("fuel")),
            })
    except (OverflowError, ValueError, TypeError):
        return None
    selected = [variant for variant in clean if variant["selected"]]
    selected_id = row.get("selected_engine_id")
    if (len(selected) > 1 or (selected and not selected[0]["available"])
            or (selected[0]["engine_id"] if selected else None) != selected_id):
        return None
    if not selected and len(clean) > 1:
        return None
    # Individual observations belong to the engine actually selected when
    # the detail was read. Legacy catalogs have no such observations.
    raw_details = row.get("variant_details", {})
    if not isinstance(raw_details, dict):
        return None
    variant_details = {}
    available_ids = {v["engine_id"] for v in clean if v["available"]}
    for engine_id, observation in raw_details.items():
        if engine_id not in available_ids or not isinstance(observation, dict):
            return None
        stamp = _timestamp(observation.get("observed_at"))
        metrics = validate_metrics(observation.get("metrics"))
        if (stamp is None or not observed_at <= stamp <= now
                or stamp - observed_at > 300 or metrics is None):
            return None
        variant_details[engine_id] = {"observed_at": stamp, "metrics": metrics}
        seats = validate_seat_observation(observation.get("seat_observation"), metrics.get("capacity_pax"))
        if seats is not None:
            variant_details[engine_id]["seat_observation"] = seats
        requirements = validate_operational_requirements(observation.get("operational_requirements"))
        if requirements is not None:
            variant_details[engine_id]["operational_requirements"] = requirements
    return {
        "source": SOURCE, "model_id": identity[0], "model": identity[1],
        "observed_at": observed_at, "selector_type": row["selector_type"],
        "selector_id": row["selector_id"], "selected_engine_id": selected_id,
        "variants": clean, "engine_prices_verified": False,
        "observed_model_id": observed_model_id,
        "model_detail_identity_verified": identity_verified,
        "variant_details": variant_details,
    }


class EngineCatalogRegistry:
    """Round-robin collection cursor and last good engine catalog per model."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path is not None else paths.current().data / "engine_catalog.json"

    def _load(self) -> dict:
        try:
            result = json.loads(self.path.read_text(encoding="utf-8"))
            return result if isinstance(result, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, state: dict) -> None:
        state["schema_version"] = 1
        paths.write_atomic(self.path, json.dumps(state, indent=2, ensure_ascii=False))

    def revoke_roster(self) -> None:
        with _LOCK:
            state = self._load()
            if "roster" in state:
                del state["roster"]
                self._write(state)

    def record_roster(self, rows: object, *, observed_at: object) -> list[dict] | None:
        models = _roster_models(rows)
        stamp = _timestamp(observed_at)
        if models is None or stamp is None or not 0 <= time.time() - stamp <= ROSTER_MAX_AGE_SECONDS:
            return None
        with _LOCK:
            state = self._load()
            state["roster"] = {"source": ROSTER_SOURCE, "observed_at": stamp, "models": models}
            self._write(state)
        return models

    def next_models(self, models: list[dict], *, per_cycle: int = 2) -> list[dict]:
        """Rotate even after failures; never schedule conflicting model identities."""
        if type(per_cycle) is not int or per_cycle < 1:
            return []
        names = {}
        conflicts = set()
        for model in models if isinstance(models, list) else []:
            identity = (_model_identity(model.get("id"), model.get("name"))
                        if isinstance(model, dict) else None)
            if identity is None:
                continue
            mid, name = identity
            if mid in names and names[mid] != name:
                conflicts.add(mid)
            names[mid] = name
        available = [{"id": mid, "name": name} for mid, name in names.items()
                     if mid not in conflicts]
        if not available:
            return []
        with _LOCK:
            cursor = self._load().get("last_attempted_id")
        start = next((index + 1 for index, model in enumerate(available)
                      if model["id"] == cursor), 0) % len(available)
        ordered = available[start:] + available[:start]
        return ordered[:min(per_cycle, len(ordered), 10)]

    def record_attempt(self, model_id: str, model_name: str, *, success: bool = False) -> bool:
        identity = _model_identity(model_id, model_name)
        if identity is None:
            return False
        with _LOCK:
            state = self._load()
            state["last_attempted_id"] = model_id
            attempts = state.get("attempts")
            attempts = attempts if isinstance(attempts, dict) else {}
            attempts[model_id] = {"model": model_name.strip(),
                                  "attempted_at": int(time.time()),
                                  "status": "observed" if success else "inconclusive"}
            state["attempts"] = attempts
            self._write(state)
        return True

    def record(self, model_id: str, model_name: str, catalog: EngineCatalog, *,
               observed_model_id: str | None = None,
               observed_at: object = _UNSET,
               variant_details: dict | None = None) -> bool:
        """Keep the latest valid DOM observation per model, including after restart."""
        if not isinstance(catalog, EngineCatalog):
            return False
        now = time.time()
        if observed_at is _UNSET:
            observed_at = now  # Legacy callers do not pass the read timestamp.
        candidate = {
            "source": SOURCE, "model_id": model_id, "model": model_name,
            "observed_at": observed_at, "selector_type": catalog.selector_type,
            "selector_id": catalog.selector_id,
            "selected_engine_id": catalog.selected_engine_id,
            "variants": [vars(variant) for variant in catalog.variants],
            "observed_model_id": observed_model_id,
            "variant_details": {} if variant_details is None else variant_details,
        }
        clean = _validated_record(candidate, now=now)
        if clean is None:
            return False
        with _LOCK:
            state = self._load()
            catalogs = state.get("catalogs")
            catalogs = catalogs if isinstance(catalogs, dict) else {}
            previous = _validated_record(catalogs.get(model_id), now=now)
            if previous is not None:
                if (previous["model_detail_identity_verified"]
                        and not clean["model_detail_identity_verified"]):
                    return False  # Recent uncorrelated DOM reads cannot replace verified identity.
                if clean["observed_at"] < previous["observed_at"]:
                    return False
                if clean["observed_at"] == previous["observed_at"]:
                    prior_verified = previous["model_detail_identity_verified"]
                    current_verified = clean["model_detail_identity_verified"]
                    if prior_verified == current_verified and clean != previous:
                        return False  # Contradictory, equally dated evidence.
            catalogs[model_id] = clean
            state["catalogs"] = catalogs
            state["last_attempted_id"] = model_id
            attempts = state.get("attempts")
            attempts = attempts if isinstance(attempts, dict) else {}
            attempts[model_id] = {"model": clean["model"], "attempted_at": now, "status": "observed"}
            state["attempts"] = attempts
            self._write(state)
        return True

    def snapshot(self, *, now: Optional[int | float] = None) -> dict:
        now = time.time() if now is None else now
        with _LOCK:
            state = self._load()
        rows = state.get("catalogs")
        models = {}
        for mid, entry in (rows.items() if isinstance(rows, dict) else []):
            clean = _validated_record(entry, now=now)
            if clean is not None and mid == clean["model_id"]:
                models[mid] = clean
        return {"source": SOURCE, "models": models, "model_count": len(models),
                "coverage": "partial", "order_list_coverage": _roster_coverage(state, models, now),
                "read_only": True}
