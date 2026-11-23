"""Persist observed inputs for owned-hub research without certifying purchases.

The route observer, market cache and engine detail collector are independent
sources. Their intersection is useful for planning the next research step, but
does not prove residual demand, final motor price or route profitability.
These entries deliberately retain a different source from verified research.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Optional

import paths
from owned_hub_research_feed import MAX_EVIDENCE_AGE, build_owned_hub_research_queue
from route_registry import endpoint, route_key


_LOCK = threading.RLock()
_GAME_ID = re.compile(r"^[1-9][0-9]{0,11}$")
_MAX_STORED = 2500


def _identity(row: dict) -> tuple | None:
    hub_id = row.get("hub_id")
    model = row.get("model")
    origin, destination = row.get("origin"), row.get("destination")
    if (not isinstance(hub_id, str) or not _GAME_ID.fullmatch(hub_id)
            or not isinstance(model, str) or not model.strip()
            or not isinstance(origin, dict) or not isinstance(destination, dict)):
        return None
    key = route_key(endpoint(origin.get("id"), origin.get("code"), origin.get("name")),
                    endpoint(destination.get("id"), destination.get("code"), destination.get("name")))
    if not key:
        return None
    engine = row.get("engine_id")
    if engine is not None and (not isinstance(engine, str) or not engine):
        return None
    return hub_id, model.strip().casefold(), key, engine


def _recent(value: object, now: float) -> bool:
    return (type(value) in (int, float) and math.isfinite(value)
            and 0 <= now - value <= MAX_EVIDENCE_AGE)


def _fingerprint(value: object) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{24}", value) else None


def _evidence_current(row: dict, now: float) -> bool:
    """Each independent source must still be fresh when a cached row is read."""
    evidence = row.get("research_evidence")
    if not isinstance(evidence, dict):
        return False
    sources = {"hub": "game_hub_select", "route": "game_route_search",
               "model": "bot_aircraft_market_cache"}
    if evidence.get("engine") is not None:
        sources["engine"] = "game_aircraft_order_detail"
    return all(isinstance(evidence.get(key), dict)
               and evidence[key].get("source") == source
               and _recent(evidence[key].get("observed_at"), now)
               for key, source in sources.items())


def _scenario(item: dict, now: float) -> dict | None:
    """Translate the queue's confirmed inputs into an explicitly partial row."""
    if not isinstance(item, dict) or item.get("status") != "pesquisa_pendente":
        return None
    hub_id, destination_id = item.get("hub_id"), item.get("destination_id")
    if (not isinstance(hub_id, str) or not _GAME_ID.fullmatch(hub_id)
            or not isinstance(destination_id, str) or not _GAME_ID.fullmatch(destination_id)
            or hub_id == destination_id):
        return None
    evidence = item.get("evidence")
    if not isinstance(evidence, dict):
        return None
    expected = {"hub": "game_hub_select", "route": "game_route_search",
                "model": "bot_aircraft_market_cache"}
    stamps = []
    for name, source in expected.items():
        proof = evidence.get(name)
        if (not isinstance(proof, dict) or proof.get("source") != source
                or not _recent(proof.get("observed_at"), now)):
            return None
        stamps.append(proof["observed_at"])
    engine = evidence.get("engine")
    if engine is not None:
        if (not isinstance(engine, dict)
                or engine.get("source") != "game_aircraft_order_detail"
                or not _recent(engine.get("observed_at"), now)):
            return None
        stamps.append(engine["observed_at"])
    model = item.get("model")
    pending = item.get("pending")
    if (not isinstance(model, str) or not model.strip() or len(model) > 100
            or not isinstance(pending, list)
            or not all(isinstance(reason, str) for reason in pending)):
        return None
    demand = item.get("observed_demand")
    if (not isinstance(demand, dict)
            or any(type(demand.get(kind)) is not int or demand[kind] < 0
                   for kind in ("y", "j", "f"))):
        return None
    observed = {
        "source": "derived_research_queue", "hub_id": hub_id,
        "model": model.strip(), "model_id": item.get("model_id"),
        "origin": {"id": hub_id, "code": item.get("hub_code") or ""},
        "destination": {"id": destination_id},
        "observed_at": max(stamps), "distance_km": item.get("distance_km"),
        "range_km": item.get("range_km"), "observed_demand": deepcopy(demand),
        "catalog_price": item.get("catalog_price"),
        "engine_label": item.get("engine_label"),
        "engine_available": item.get("engine_available"),
        "research_evidence": deepcopy(evidence),
        "research_pending": sorted(set(pending)),
        # The observed raw demand is NOT demand left after the active fleet.
        "demand_verified": False, "demand_remaining": None,
        "route_available": None, "route_feasible": None,
        "financial": {}, "costs": {},
    }
    if item.get("engine_id") is not None:
        observed["engine_id"] = item["engine_id"]
    return observed if _identity(observed) is not None else None


class OwnedHubResearchInputsRegistry:
    """Bounded per-profile durable cache of pending input combinations."""

    def __init__(self, path: Optional[Path] = None):
        self.path = (Path(path) if path is not None else
                     paths.current().data / "owned_hub_research_inputs.json")

    def _load(self) -> dict:
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return saved if isinstance(saved, dict) else {}

    def cursor(self) -> int:
        return self.cursor_state()[0]

    def cursor_state(self) -> tuple[int, str | None]:
        """Return the offset together with the evidence snapshot it belongs to."""
        offset, fingerprint, _ = self.pagination_state()
        return offset, fingerprint

    def pagination_state(self) -> tuple[int, str | None, str | None]:
        with _LOCK:
            saved = self._load()
        cursor = saved.get("next_offset")
        return (cursor if type(cursor) is int and cursor >= 0 else 0,
                _fingerprint(saved.get("snapshot_fingerprint")),
                _fingerprint(saved.get("layout_fingerprint")))

    def snapshot(self, *, verified: Optional[list[dict]] = None,
                 now: Optional[float] = None) -> list[dict]:
        """Verified scenarios always have priority for the same investment."""
        now = time.time() if now is None else now
        identities = {_identity(item) for item in (verified or [])
                      if isinstance(item, dict) and item.get("source") == "game_research"}
        with _LOCK:
            rows = self._load().get("items")
        return deepcopy([
            row for row in rows if isinstance(row, dict)
            and row.get("source") == "derived_research_queue"
            and _identity(row) is not None and _identity(row) not in identities
            and _recent(row.get("observed_at"), now)
            and _evidence_current(row, now)
        ]) if isinstance(rows, list) else []

    def record_queue(self, page: dict, *, now: Optional[float] = None) -> int:
        """Commit one bounded research page and its progress atomically."""
        now = time.time() if now is None else now
        if (not isinstance(page, dict) or page.get("source") != "derived_research_queue"
                or page.get("read_only") is not True
                or not isinstance(page.get("items"), list)):
            return 0
        fingerprint = _fingerprint(page.get("snapshot_fingerprint"))
        layout_fingerprint = _fingerprint(page.get("layout_fingerprint"))
        if fingerprint is None or layout_fingerprint is None:
            return 0
        converted = [_scenario(item, now) for item in page["items"]]
        converted = [row for row in converted if row is not None]
        with _LOCK:
            saved = self._load()
            old = saved.get("items")
            records = {}
            # A changed hub/route/model/engine set invalidates all accumulated
            # pages. Reusing them would expose candidates absent from the new
            # catalogue until their independent evidence eventually expired.
            same_layout = saved.get("layout_fingerprint") == layout_fingerprint
            for row in old if same_layout and isinstance(old, list) else []:
                if (isinstance(row, dict) and row.get("source") == "derived_research_queue"
                        and _recent(row.get("observed_at"), now)
                        and _evidence_current(row, now)):
                    identity = _identity(row)
                    if identity is not None:
                        records[identity] = row
            for row in converted:
                identity = _identity(row)
                previous = records.get(identity)
                if previous is None or row["observed_at"] >= previous["observed_at"]:
                    # Equal-time contradictions are quarantined: every
                    # derived row is pending until independent validation.
                    if (previous is not None and row["observed_at"] == previous["observed_at"]
                            and row != previous):
                        row["research_pending"] = sorted(set([
                            *row["research_pending"], "pesquisas_conflitantes"
                        ]))
                    records[identity] = row
            items = sorted(records.values(), key=lambda row: (
                -row["observed_at"], str(_identity(row))
            ))[:_MAX_STORED]
            offset = page.get("next_offset")
            next_offset = offset if type(offset) is int and offset >= 0 else 0
            updated = {"version": 3, "items": items,
                       "next_offset": next_offset, "snapshot_fingerprint": fingerprint,
                       "layout_fingerprint": layout_fingerprint}
            if updated != saved:
                paths.write_atomic(self.path, json.dumps(updated, ensure_ascii=False, indent=2))
        return len(converted)


def ingest_owned_hub_research_inputs(*, per_cycle: int = 40) -> int:
    """Compose already-cached observations after the bot's read-only probes."""
    from economy import load_market_evidence
    from engine_catalog import EngineCatalogRegistry
    from hub_expansion import HubExpansionRegistry
    from hub_registry import HubRegistry
    from route_registry import RouteRegistry

    routes = RouteRegistry().snapshot()
    inventory = HubRegistry().snapshot(routes)
    hubs = {row["id"] for row in inventory.get("hubs", [])
            if isinstance(row, dict) and isinstance(row.get("id"), str)}
    demand = HubExpansionRegistry().demand_research_snapshot(hubs)
    market = load_market_evidence()
    engines = EngineCatalogRegistry().snapshot()
    parameters = {"engines": engines, "hub_progress": demand["hub_progress"],
                  "max_items": per_cycle}
    first = build_owned_hub_research_queue(
        inventory, demand["samples"], market, **parameters,
    )
    registry = OwnedHubResearchInputsRegistry()
    cursor, previous_fingerprint, previous_layout = registry.pagination_state()
    if cursor and cursor < first["total_candidates"]:
        # Reading a fresh price or a new demand sample changes the evidence
        # fingerprint every cycle. Continue fairly when candidate ordering is
        # stable; reset when a route, model, motor or hub was added/removed.
        expected = (first["snapshot_fingerprint"]
                    if previous_fingerprint is not None and previous_layout is not None
                    and previous_layout == first["layout_fingerprint"]
                    else previous_fingerprint)
        page = build_owned_hub_research_queue(
            inventory, demand["samples"], market,
            offset=cursor, expected_fingerprint=expected,
            **parameters,
        )
    else:
        page = first
    return registry.record_queue(page)
