"""Read-only research queue joining owned hubs, route observations and aircraft.

An observed route, model and motor in the aircraft market are research inputs.
The queue never invents final motor prices or remaining demand and cannot
promote an estimate into HubAircraftResearchRegistry.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import defaultdict
from typing import Optional


MAX_EVIDENCE_AGE = 3 * 86400
_GAME_ID = re.compile(r"^[1-9][0-9]{0,11}$")
_MODEL_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ENGINE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
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


def _fresh_engine_read(raw: object, now: int) -> bool:
    """Engine catalogs preserve the precise time of the stable DOM read."""
    return (type(raw) in (int, float) and 0 < raw <= now
            and now - raw <= MAX_EVIDENCE_AGE)


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


def _engine_variants(engines: dict, model: dict, now: int) -> tuple[list[dict], dict | None]:
    """Reject stale, contradictory or mismatched engine evidence as a whole."""
    if engines.get("source") != "game_aircraft_order_detail":
        return [], None
    catalogs = engines.get("models")
    row = catalogs.get(model["id"]) if isinstance(catalogs, dict) else None
    if (not isinstance(row, dict) or row.get("source") != engines["source"]
            or row.get("model_id") != model["id"]
            or not isinstance(row.get("model"), str)
            or row["model"].strip().casefold() != model["name"].casefold()
            or not _fresh_engine_read(row.get("observed_at"), now)
            or row.get("engine_prices_verified") is not False):
        return [], None
    observed_model_id = row.get("observed_model_id")
    identity_verified = row.get("model_detail_identity_verified", False)
    if (observed_model_id is not None and observed_model_id != model["id"]
            or type(identity_verified) is not bool
            or identity_verified and observed_model_id != model["id"]):
        return [], None
    variants = row.get("variants")
    if not isinstance(variants, list) or not 0 < len(variants) <= 100:
        return [], None
    seen = set()
    result = []
    for item in variants:
        if not isinstance(item, dict):
            return [], None
        engine_id, label = item.get("engine_id"), item.get("label")
        if (not isinstance(engine_id, str) or not _ENGINE_ID.fullmatch(engine_id)
                or engine_id in seen or not isinstance(label, str) or not label.strip()
                or type(item.get("available")) is not bool
                or type(item.get("selected")) is not bool):
            return [], None
        seen.add(engine_id)
        result.append({"engine_id": engine_id, "engine_label": label.strip(),
                       "engine_available": item["available"],
                       "engine_selected": item["selected"],
                       "engine_speed": _positive_number(item.get("speed")),
                       "engine_fuel": _positive_number(item.get("fuel"))})
    if (sum(item["engine_selected"] for item in result) > 1
            or (len(result) > 1 and not any(item["engine_selected"] for item in result))
            or any(item["engine_selected"] and not item["engine_available"] for item in result)
            or row.get("selected_engine_id") != next(
                (item["engine_id"] for item in result if item["engine_selected"]), None
            )):
        return [], None
    return result, {"source": row["source"], "observed_at": row["observed_at"],
                    "observed_model_id": observed_model_id,
                    "selected_engine_id": row.get("selected_engine_id"),
                    "model_detail_identity_verified": identity_verified,
                    "engine_prices_verified": False}


def build_owned_hub_research_queue(
    inventory: dict, route_samples: list[dict], market: dict, *,
    now: Optional[int] = None, max_items: int = 40, engines: Optional[dict] = None,
    offset: int = 0, expected_fingerprint: Optional[str] = None,
) -> dict:
    """Produce bounded, balanced per-hub tasks from independent cached reads.

    The returned items are *always* pending research. All values are read-only
    and the queue cannot be consumed as an approval or purchase order.
    """
    now = int(time.time() if now is None else now)
    max_items = max_items if type(max_items) is int and 1 <= max_items <= 200 else 40
    inventory = inventory if isinstance(inventory, dict) else {}
    market = market if isinstance(market, dict) else {}
    engines = engines if isinstance(engines, dict) else {}
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
    # A route is one research subject, even when cache migration or a partial
    # page read supplies repeated observations. Equally fresh contradictory
    # readings must not silently pick a winner based on input order.
    latest_routes = {}
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
        sample = {
            "origin_id": origin, "destination_id": destination,
            "distance_km": distance, "observed_at": row["observed_at"],
            "demand": {key: row[key] for key in ("y", "j", "f")},
        }
        key = (origin, destination)
        prior = latest_routes.get(key)
        if prior is None or sample["observed_at"] > prior["sample"]["observed_at"]:
            latest_routes[key] = {"sample": sample, "conflict": False}
        elif sample["observed_at"] == prior["sample"]["observed_at"]:
            if sample != prior["sample"]:
                prior["conflict"] = True

    samples_by_hub = defaultdict(list)
    conflicts_by_hub = defaultdict(int)
    for (hub_id, _), observation in latest_routes.items():
        if observation["conflict"]:
            conflicts_by_hub[hub_id] += 1
        else:
            samples_by_hub[hub_id].append(observation["sample"])

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

    # Every page is tied to the same normalized evidence. A refresh between
    # requests invalidates the cursor instead of silently skipping candidates.
    model_options = []
    for model in models:
        variants, engine_evidence = _engine_variants(engines, model, now)
        model_options.extend((model, variant, engine_evidence)
                             for variant in (variants or [None]))
    ordered_hubs = sorted(samples_by_hub, key=int)
    lengths = {hub_id: len(samples_by_hub[hub_id]) * len(model_options)
               for hub_id in ordered_hubs}
    total_candidates = sum(lengths.values()) if not blockers else 0
    fingerprint_data = {
        "hubs": hubs, "inventory_source": inventory.get("source"),
        "inventory_observed_at": inventory.get("observed_at"),
        "market_source": market.get("source"),
        "market_observed_at": market.get("observed_at"),
        "blockers": blockers, "models": models,
        "options": model_options, "routes": dict(samples_by_hub),
        "conflicts": dict(conflicts_by_hub),
    }
    fingerprint = hashlib.sha256(json.dumps(
        fingerprint_data, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()[:24]
    requested_offset = offset if type(offset) is int and offset > 0 else 0
    cursor_reset = requested_offset > 0 and (
        expected_fingerprint != fingerprint or requested_offset >= total_candidates
    )
    offset = requested_offset
    if cursor_reset:
        offset = 0

    queue = []
    if not blockers:
        # Find the round-robin round containing the requested offset without
        # generating the potentially large prefix of earlier research tasks.
        low, high = 0, max(lengths.values())
        while low < high:
            middle = (low + high + 1) // 2
            before = sum(min(middle, length) for length in lengths.values())
            if before <= offset:
                low = middle
            else:
                high = middle - 1
        round_index = low
        skipped_in_round = offset - sum(min(low, length) for length in lengths.values())
        while round_index < max(lengths.values()) and len(queue) < max_items:
            for hub_id in ordered_hubs:
                if round_index >= lengths[hub_id]:
                    continue
                if skipped_in_round:
                    skipped_in_round -= 1
                    continue
                sample_index, model_index = divmod(round_index, len(model_options))
                sample = samples_by_hub[hub_id][sample_index]
                model, variant, engine_evidence = model_options[model_index]
                if len(queue) >= max_items:
                    break
                pending = [item for item in _RESEARCH_PENDING
                           if item != "motor_a_pesquisar" or variant is None]
                # Direct range does not rule out a route with a legal stopover.
                # Keep the combination in the research queue until both legs,
                # stopover runway and the game's actual rules are verified.
                if (model["range_km"] is not None
                        and model["range_km"] < sample["distance_km"]):
                    pending.append("escala_e_trechos_a_confirmar")
                if variant is not None:
                    if not variant["engine_available"]:
                        pending.append("motor_indisponivel")
                    if not engine_evidence["model_detail_identity_verified"]:
                        pending.append("identidade_modelo_detalhe_a_confirmar")
                if model["range_km"] is None:
                    pending.append("alcance_modelo_a_confirmar")
                if model["capacity"] is None:
                    pending.append("capacidade_modelo_a_confirmar")
                queue.append({
                    "hub_id": hub_id, "hub_code": hubs[hub_id]["code"],
                    "destination_id": sample["destination_id"],
                    "distance_km": sample["distance_km"],
                    "direct_range_sufficient": (model["range_km"] >= sample["distance_km"]
                                                if model["range_km"] is not None else None),
                    "observed_demand": sample["demand"],
                    "model_id": model["id"], "model": model["name"],
                    "range_km": model["range_km"], "capacity": model["capacity"],
                    "catalog_price": model["catalog_price"],
                    "engine_id": variant["engine_id"] if variant else None,
                    "engine_label": variant["engine_label"] if variant else None,
                    "engine_available": variant["engine_available"] if variant else None,
                    "engine_selected": variant["engine_selected"] if variant else None,
                    "engine_speed": variant["engine_speed"] if variant else None,
                    "engine_fuel": variant["engine_fuel"] if variant else None,
                    "final_aircraft_price": None,
                    "daily_net_profit": None, "status": "pesquisa_pendente",
                    "pending": pending, "purchase_eligible": False,
                    "evidence": {
                        "hub": {"source": "game_hub_select",
                                "observed_at": inventory["observed_at"]},
                        "route": {"source": "game_route_search",
                                  "observed_at": sample["observed_at"]},
                        "model": {"source": "bot_aircraft_market_cache",
                                  "observed_at": market["observed_at"]},
                        "engine": engine_evidence,
                    },
                })
            round_index += 1

    has_more = offset + len(queue) < total_candidates
    hub_coverage = [
        {"hub_id": hub_id, "hub_code": hubs[hub_id]["code"],
         "sampled_routes": len(samples_by_hub.get(hub_id, ())),
         "conflicted_routes": conflicts_by_hub[hub_id],
         "last_route_observed_at": max(
             (item["observed_at"] for item in samples_by_hub.get(hub_id, ())), default=None
         ),
         "coverage": "partial",
         "status": "pesquisa_iniciada" if samples_by_hub.get(hub_id) else "nao_pesquisado"}
        for hub_id in sorted(hubs, key=int)
    ]
    return {
        "source": "derived_research_queue", "read_only": True,
        "coverage": "partial", "purchase_eligible": False,
        "owned_hubs": len(hubs), "sampled_hubs": len(samples_by_hub),
        "sampled_routes": sum(len(rows) for rows in samples_by_hub.values()),
        "conflicted_routes": sum(conflicts_by_hub.values()),
        "hub_coverage": hub_coverage,
        "market_models": len(models), "market_observed_at": market.get("observed_at"),
        "items": queue, "has_more": has_more,
        "total_candidates": total_candidates, "offset": offset,
        "page_size": max_items,
        "next_offset": offset + len(queue) if has_more else None,
        "snapshot_fingerprint": fingerprint, "cursor_reset": cursor_reset,
        "blocking_reasons": blockers,
    }
