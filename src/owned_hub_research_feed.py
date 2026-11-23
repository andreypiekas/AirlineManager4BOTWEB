"""Read-only research queue joining owned hubs, route observations and aircraft.

An observed route and a model in the aircraft market are research inputs, not
an actionable investment scenario. The queue never assigns an engine, invents
remaining demand or promotes an estimate into HubAircraftResearchRegistry.
"""
from __future__ import annotations

import math
import re
import time
from collections import defaultdict, deque
from itertools import product
from typing import Optional


MAX_EVIDENCE_AGE = 3 * 86400
_GAME_ID = re.compile(r"^[1-9][0-9]{0,11}$")
_MODEL_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_RESEARCH_PENDING = [
    "motor_a_pesquisar",
    "preco_final_motor_a_confirmar",
    "demanda_residual_a_confirmar",
    "disponibilidade_da_rota_a_confirmar",
    "pista_a_confirmar",
    "configuracao_assentos_a_confirmar",
    "taxa_rota_a_confirmar",
    "custo_hangar_a_confirmar",
    "lucro_incremental_a_calcular",
    "cobertura_da_frota_a_confirmar",
]


def _positive_number(raw: object) -> Optional[float]:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    try:
        number = float(raw)
    except OverflowError:
        return None
    return number if math.isfinite(number) and number > 0 else None


def _fresh(raw: object, now: int) -> bool:
    return (type(raw) is int and raw > 0
            and 0 <= now - raw <= MAX_EVIDENCE_AGE)


def _models(raw: object) -> list[dict]:
    """Keep only uniquely identified, noncontradictory catalog entries."""
    if not isinstance(raw, list):
        return []
    by_id = {}
    conflicts = set()
    for item in raw:
        if not isinstance(item, dict) or isinstance(item.get("id"), bool):
            continue
        model_id = str(item.get("id") or "").strip()
        name = item.get("name")
        if not _MODEL_ID.fullmatch(model_id) or not isinstance(name, str) or not name.strip():
            continue
        normalized = {
            "id": model_id, "name": name.strip(),
            "range_km": _positive_number(item.get("range")),
            "capacity": _positive_number(item.get("capacity")),
            "catalog_price": _positive_number(item.get("price")),
        }
        if model_id in by_id and by_id[model_id] != normalized:
            conflicts.add(model_id)
        by_id[model_id] = normalized
    return sorted((row for mid, row in by_id.items() if mid not in conflicts),
                  key=lambda row: (row["name"].casefold(), row["id"]))


def build_owned_hub_research_queue(
    inventory: dict, route_samples: list[dict], market: dict, *,
    now: Optional[int] = None, max_items: int = 40,
) -> dict:
    """Produce bounded, balanced per-hub tasks from independent cached reads.

    The returned items are *always* pending research. All values are read-only
    and the queue cannot be consumed as an approval or purchase order.
    """
    now = int(time.time() if now is None else now)
    max_items = max_items if type(max_items) is int and 1 <= max_items <= 200 else 40
    inventory = inventory if isinstance(inventory, dict) else {}
    market = market if isinstance(market, dict) else {}
    inventory_fresh = (inventory.get("source") == "game_hub_select"
                       and _fresh(inventory.get("observed_at"), now))
    market_fresh = (market.get("source") == "bot_aircraft_market_cache"
                    and market.get("fresh") is True
                    and _fresh(market.get("observed_at"), now))

    hubs = {}
    for raw in inventory.get("hubs", []) if isinstance(inventory.get("hubs"), list) else []:
        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
            hub_id = raw["id"]
            if _GAME_ID.fullmatch(hub_id):
                hubs[hub_id] = {"id": hub_id, "code": str(raw.get("code") or "")}

    models = _models(market.get("models")) if market_fresh else []
    samples_by_hub = defaultdict(list)
    for row in route_samples if isinstance(route_samples, list) else []:
        if not isinstance(row, dict) or row.get("source") != "game_route_search":
            continue
        origin, destination = row.get("origin_id"), row.get("destination_id")
        if (origin not in hubs or not isinstance(destination, str)
                or not _GAME_ID.fullmatch(destination) or origin == destination
                or not _fresh(row.get("observed_at"), now)):
            continue
        distance = _positive_number(row.get("distance_km"))
        if (distance is None or distance > 25000
                or any(type(row.get(key)) is not int or not 0 <= row[key] <= 100_000_000
                       for key in ("y", "j", "f"))):
            continue
        samples_by_hub[origin].append({
            "origin_id": origin, "destination_id": destination,
            "distance_km": distance, "observed_at": row["observed_at"],
            "demand": {key: row[key] for key in ("y", "j", "f")},
        })

    for rows in samples_by_hub.values():
        rows.sort(key=lambda row: (int(row["destination_id"]), -row["observed_at"]))

    blockers = []
    if not inventory_fresh:
        blockers.append("inventario_hubs_desatualizado")
    if not market_fresh:
        blockers.append("catalogo_aeronaves_desatualizado")
    if not models:
        blockers.append("modelos_a_pesquisar")
    if not samples_by_hub:
        blockers.append("demanda_dos_hubs_a_pesquisar")

    queue = []
    if not blockers:
        streams = deque((hub_id, iter(product(samples_by_hub[hub_id], models)))
                        for hub_id in sorted(samples_by_hub, key=int))
        while streams and len(queue) <= max_items:
            hub_id, stream = streams.popleft()
            try:
                sample, model = next(stream)
            except StopIteration:
                continue
            streams.append((hub_id, stream))
            if model["range_km"] is not None and model["range_km"] < sample["distance_km"]:
                continue
            pending = _RESEARCH_PENDING.copy()
            if model["range_km"] is None:
                pending.append("alcance_modelo_a_confirmar")
            if model["capacity"] is None:
                pending.append("capacidade_modelo_a_confirmar")
            queue.append({
                "hub_id": hub_id, "hub_code": hubs[hub_id]["code"],
                "destination_id": sample["destination_id"],
                "distance_km": sample["distance_km"],
                "observed_demand": sample["demand"],
                "model_id": model["id"], "model": model["name"],
                "range_km": model["range_km"], "capacity": model["capacity"],
                "catalog_price": model["catalog_price"],
                "engine_id": None, "final_aircraft_price": None,
                "daily_net_profit": None, "status": "pesquisa_pendente",
                "pending": pending, "purchase_eligible": False,
                "evidence": {
                    "hub": {"source": "game_hub_select",
                            "observed_at": inventory["observed_at"]},
                    "route": {"source": "game_route_search",
                              "observed_at": sample["observed_at"]},
                    "model": {"source": "bot_aircraft_market_cache",
                              "observed_at": market["observed_at"]},
                },
            })

    has_more = len(queue) > max_items
    return {
        "source": "derived_research_queue", "read_only": True,
        "coverage": "partial", "purchase_eligible": False,
        "owned_hubs": len(hubs), "sampled_hubs": len(samples_by_hub),
        "sampled_routes": sum(len(rows) for rows in samples_by_hub.values()),
        "market_models": len(models), "market_observed_at": market.get("observed_at"),
        "items": queue[:max_items], "has_more": has_more,
        "blocking_reasons": blockers,
    }
