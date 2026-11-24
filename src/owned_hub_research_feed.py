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

from engine_detail import validate_metrics
from route_detail_evidence import current_detail
from market import recent_market_quotes
from research_economics_preview import research_economics_preview, research_mode
from research_physical_feasibility import assess_direct_route
from research_route_occupancy import FleetRouteOccupancy
from stopover_research import current_stopover, subject_for

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


def _fresh(raw: object, now: float) -> bool:
    timestamp = _positive_number(raw)
    return timestamp is not None and 0 <= now - timestamp <= MAX_EVIDENCE_AGE


def _fresh_engine_read(raw: object, now: float) -> bool:
    """Engine catalogs preserve the precise time of the stable DOM read."""
    return _fresh(raw, now)


def _nonnegative_money(raw: object) -> Optional[float]:
    if type(raw) in (int, float) and raw == 0:
        return 0.0
    return _positive_number(raw)


def _external_cost_evidence(row: dict, now: float) -> dict:
    result = {}
    for field in ("hub_price", "hub_points"):
        value = row.get(field)
        value = (_nonnegative_money(value) if field == "hub_price" else
                 value if type(value) is int and 0 <= value <= 10_000_000 else None)
        stamp = row.get(f"{field}_observed_at")
        if (value is not None and _fresh(stamp, now)
                and row.get(f"{field}_conflict_at") is None):
            result.update({field: value, f"{field}_observed_at": stamp})
    return result


def _external_budget(cash: object, observed_at: object, reserve: object, now: float) -> dict:
    stamp = _positive_number(observed_at)
    cash = _nonnegative_money(cash) if stamp is not None and 0 <= now - stamp <= 900 else None
    reserve = _nonnegative_money(reserve)
    return {"cash": cash, "cash_observed_at": stamp if cash is not None else None,
            "reserve": reserve,
            "available_before_commitments": max(0.0, cash - reserve)
            if cash is not None and reserve is not None else None}


def _external_cost_preview(hub: dict, budget: dict) -> dict:
    price = hub.get("hub_price")
    available = budget.get("available_before_commitments")
    return {"hub_price": price, "hub_price_observed_at": hub.get("hub_price_observed_at"),
            "hub_points": hub.get("hub_points"),
            "hub_points_observed_at": hub.get("hub_points_observed_at"),
            "hub_only_exceeds_available": price > available
            if price is not None and available is not None else None,
            "total_investment": None, "cash_after_purchase": None,
            "roi": None, "payback_days": None}


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


def engine_variants(engines: dict, model: dict, now: float) -> tuple[list[dict], dict | None]:
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
    details = row.get("variant_details", {})
    if not isinstance(details, dict):
        return [], None
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
        detail = details.get(engine_id)
        metrics = None
        if engine_id in details:
            if (not isinstance(detail, dict) or not item["available"]
                    or not _fresh_engine_read(detail.get("observed_at"), now)
                    or not 0 <= detail["observed_at"] - row["observed_at"] <= 300):
                return [], None
            metrics = validate_metrics(detail.get("metrics"))
            if metrics is None:
                return [], None
        speed, fuel = _positive_number(item.get("speed")), _positive_number(item.get("fuel"))
        if identity_verified and metrics:
            # Prefer actual selected-form values, but never use conflicting
            # option attributes to compute a variant's economic preview.
            for field, old in (("speed_kph", speed), ("fuel_lbs_per_km", fuel)):
                if field in metrics and old is not None and metrics[field] != old:
                    return [], None
            speed = metrics.get("speed_kph", speed)
            fuel = metrics.get("fuel_lbs_per_km", fuel)
        result.append({"engine_id": engine_id, "engine_label": label.strip(),
                       "engine_available": item["available"],
                       "engine_selected": item["selected"],
                       "engine_speed": speed, "engine_fuel": fuel,
                       "engine_detail": ({"observed_at": detail["observed_at"], "metrics": metrics,
                                          "model_identity_verified": identity_verified}
                                         if metrics is not None else None)})
    if not details.keys() <= seen:
        return [], None
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
    now: Optional[float] = None, max_items: int = 40, engines: Optional[dict] = None,
    offset: int = 0, expected_fingerprint: Optional[str] = None,
    hub_progress: Optional[list[dict]] = None,
    operating_market_stats: Optional[object] = None,
    preview_margin: float = 0.10,
    route_report: Optional[dict] = None,
) -> dict:
    return _build_hub_research_queue(
        inventory, route_samples, market, now=now, max_items=max_items, engines=engines,
        offset=offset, expected_fingerprint=expected_fingerprint, hub_progress=hub_progress,
        operating_market_stats=operating_market_stats, preview_margin=preview_margin,
        route_report=route_report)


def build_external_hub_research_queue(
    ownership: dict, external: dict, market: dict, *,
    now: Optional[float] = None, max_items: int = 40, engines: Optional[dict] = None,
    offset: int = 0, expected_fingerprint: Optional[str] = None,
    cash: Optional[float] = None, cash_observed_at: Optional[float] = None,
    reserve: Optional[float] = None,
    operating_market_stats: Optional[object] = None,
    preview_margin: float = 0.10,
    route_report: Optional[dict] = None,
) -> dict:
    """Join external catalog evidence with route and engine research, never owned inputs."""
    now = _positive_number(time.time() if now is None else now) or 0.0
    ownership = ownership if isinstance(ownership, dict) else {}
    external = external if isinstance(external, dict) else {}
    owned_rows = ownership.get("hubs")
    ownership_verified = (
        ownership.get("source") == "game_hub_select"
        and ownership.get("hub_catalog_fresh") is True
        and _fresh(ownership.get("observed_at"), now)
        and isinstance(owned_rows, list) and bool(owned_rows)
        and all(isinstance(row, dict) and isinstance(row.get("id"), str)
                and _GAME_ID.fullmatch(row["id"]) for row in owned_rows)
        and len({row["id"] for row in owned_rows}) == len(owned_rows))
    candidates = external.get("candidate_inventory")
    catalog_verified = (ownership_verified and external.get("origin_scope") == "external_catalog"
                        and external.get("candidate_source") == "game_purchase_catalog"
                        and isinstance(candidates, list))
    owned_ids = {row["id"] for row in owned_rows} if ownership_verified else set()
    hubs = []
    if catalog_verified:
        for row in candidates:
            if (isinstance(row, dict) and isinstance(row.get("id"), str)
                    and _GAME_ID.fullmatch(row["id"]) and row["id"] not in owned_ids
                    and _fresh(row.get("observed_at"), now)):
                hubs.append(row)
    inventory = {"source": "game_purchase_catalog" if catalog_verified else None,
                 "observed_at": max((row["observed_at"] for row in hubs), default=None),
                 "hubs": hubs, "ownership_observed_at": ownership.get("observed_at")
                 if ownership_verified else None}
    return _build_hub_research_queue(
        inventory, external.get("samples", []), market, now=now, max_items=max_items,
        engines=engines, offset=offset, expected_fingerprint=expected_fingerprint,
        hub_progress=external.get("hub_progress"), external=True,
        external_budget=_external_budget(cash, cash_observed_at, reserve, now),
        operating_market_stats=operating_market_stats, preview_margin=preview_margin,
        route_report=route_report)


def _build_hub_research_queue(
    inventory: dict, route_samples: list[dict], market: dict, *,
    now: Optional[float] = None, max_items: int = 40, engines: Optional[dict] = None,
    offset: int = 0, expected_fingerprint: Optional[str] = None,
    hub_progress: Optional[list[dict]] = None, external: bool = False,
    external_budget: Optional[dict] = None,
    operating_market_stats: Optional[object] = None,
    preview_margin: float = 0.10,
    route_report: Optional[dict] = None,
) -> dict:
    """Produce bounded, balanced per-hub tasks from independent cached reads.

    The returned items are *always* pending research. All values are read-only
    and the queue cannot be consumed as an approval or purchase order.
    """
    # The route observer saves a subsecond timestamp from its stable DOM read.
    # Truncating the clock or accepting integers only drops valid live samples.
    now = _positive_number(time.time() if now is None else now) or 0.0
    operating_market = recent_market_quotes(operating_market_stats, now)
    mode_key = research_mode(operating_market_stats, now)
    fleet_occupancy = FleetRouteOccupancy(route_report, now)
    max_items = max_items if type(max_items) is int and 1 <= max_items <= 200 else 40
    inventory = inventory if isinstance(inventory, dict) else {}
    market = market if isinstance(market, dict) else {}
    engines = engines if isinstance(engines, dict) else {}
    external_budget = external_budget or {}
    hub_source = "game_purchase_catalog" if external else "game_hub_select"
    inventory_fresh = (inventory.get("source") == hub_source
                       and _fresh(inventory.get("observed_at"), now))
    market_fresh = (market.get("source") == "bot_aircraft_market_cache"
                    and market.get("fresh") is True
                    and _fresh(market.get("observed_at"), now))

    hubs = {}
    conflicted_hub_ids = set()
    for raw in inventory.get("hubs", []) if isinstance(inventory.get("hubs"), list) else []:
        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
            hub_id = raw["id"]
            if _GAME_ID.fullmatch(hub_id):
                hub = {"id": hub_id, "code": str(raw.get("code") or "")}
                if external:
                    hub["observed_at"] = raw["observed_at"]
                    hub.update(_external_cost_evidence(raw, now))
                if hub_id in hubs and hubs[hub_id] != hub:
                    conflicted_hub_ids.add(hub_id)
                hubs[hub_id] = hub
    for hub_id in conflicted_hub_ids:
        hubs.pop(hub_id)

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
        if row.get("event_demand_boosted") is True:
            sample["event_demand_boosted"] = True
        runway = row.get("destination_runway_ft")
        if type(runway) is int and 0 < runway <= 30000:
            sample["destination_runway_ft"] = runway
        detail = current_detail(row.get("route_detail"), origin, destination, now,
                                expected_runway=sample.get("destination_runway_ft"))
        if detail:
            sample["route_detail"] = detail
        if isinstance(row.get("stopover_research"), list):
            sample["stopover_research"] = [proof for proof in row["stopover_research"]
                                           if isinstance(proof, dict)]
        occupancy = fleet_occupancy.evidence(origin, destination, detail)
        if occupancy is not None:
            sample["fleet_occupancy"] = occupancy
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

    attempts_by_hub = {}
    for row in hub_progress if isinstance(hub_progress, list) else []:
        if not isinstance(row, dict) or row.get("hub_id") not in hubs:
            continue
        hub_id = row["hub_id"]
        attempt_at = row.get("last_attempt_at")
        attempt_status = row.get("last_attempt_status")
        recent_attempt = (_fresh(attempt_at, now)
                          and attempt_status in ("inconclusive", "samples_observed"))
        count = row.get("conflicted_routes")
        if type(count) is int and 0 <= count <= 5000:
            conflicts_by_hub[hub_id] = max(conflicts_by_hub[hub_id], count)
        attempts_by_hub[hub_id] = {
            "last_attempt_at": attempt_at if recent_attempt else None,
            "last_attempt_status": attempt_status if recent_attempt else "unattempted",
        }
        distance = row.get("last_requested_max_distance_km")
        runway = row.get("last_requested_min_runway_ft")
        scope = row.get("last_search_scope")
        if (recent_attempt and scope in ("configured", "broad")
                and type(distance) is int and 300 <= distance <= 25000
                and type(runway) is int and 0 <= runway <= 30000
                and (scope != "broad" or (distance, runway) == (20000, 0))):
            attempts_by_hub[hub_id].update({
                "last_search_scope": scope, "last_requested_max_distance_km": distance,
                "last_requested_min_runway_ft": runway,
            })

    blockers = []
    if not inventory_fresh:
        blockers.append("catalogo_hubs_externos_a_confirmar" if external else "inventario_hubs_desatualizado")
    if conflicted_hub_ids:
        blockers.append("inventario_hubs_conflitante")
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
        variants, engine_evidence = engine_variants(engines, model, now)
        for variant in (variants or [None]):
            detail = variant.get("engine_detail") if variant else None
            if detail and detail["model_identity_verified"]:
                metrics = detail["metrics"]
                effective_model = {**model,
                                   "range_km": metrics.get("range_km", model["range_km"]),
                                   "capacity": metrics.get("capacity_pax", model["capacity"])}
            else:
                effective_model = model
            model_options.append((effective_model, variant, engine_evidence))
    ordered_hubs = sorted(samples_by_hub, key=int)
    lengths = {hub_id: len(samples_by_hub[hub_id]) * len(model_options)
               for hub_id in ordered_hubs}
    total_candidates = sum(lengths.values()) if not blockers else 0
    fingerprint_data = {
        "hubs": hubs, "inventory_source": inventory.get("source"),
        "inventory_observed_at": inventory.get("observed_at"),
        **({"ownership_observed_at": inventory.get("ownership_observed_at"),
            "external_budget": external_budget} if external else {}),
        "market_source": market.get("source"),
        "market_observed_at": market.get("observed_at"),
        **({"operating_market": operating_market} if any(operating_market.values()) else {}),
        **({"preview_mode": mode_key, "preview_margin": preview_margin,
            "mode_read_at": operating_market_stats.mode_read_at} if mode_key else {}),
        "blockers": blockers, "models": models,
        "options": model_options, "routes": dict(samples_by_hub),
        "conflicts": dict(conflicts_by_hub),
        "attempts": attempts_by_hub,
    }
    fingerprint = hashlib.sha256(json.dumps(
        fingerprint_data, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()[:24]
    # A background ingest may continue through refreshed prices, demand or
    # timestamps when the ordered candidate identities are unchanged. The
    # interactive UI still uses the stricter evidence fingerprint above.
    layout_data = {
        **({"origin_scope": "external_catalog"} if external else {}),
        "hub_identifiers": [(hub_id, hubs[hub_id]["code"]) for hub_id in sorted(hubs, key=int)],
        "hub_routes": {hub_id: [route["destination_id"] for route in samples_by_hub[hub_id]]
                       for hub_id in ordered_hubs},
        "model_engines": [(model["id"], model["name"],
                           variant["engine_id"] if variant else None,
                           variant["engine_label"] if variant else None)
                          for model, variant, _ in model_options],
    }
    layout_fingerprint = hashlib.sha256(json.dumps(
        layout_data, ensure_ascii=False, sort_keys=True,
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
                physical = assess_direct_route(sample, variant, engine_evidence,
                                               max_evidence_age=MAX_EVIDENCE_AGE)
                subject = subject_for(sample, model, variant, now)
                stopover = next((proof for raw in sample.get("stopover_research", [])
                                 if (proof := current_stopover(raw, subject, sample, now))), None)
                if "short" in (physical["checks"]["origin_runway"],
                               physical["checks"]["destination_runway"]):
                    pending.append("pista_observada_insuficiente")
                if external:
                    preview = _external_cost_preview(hubs[hub_id], external_budget)
                    pending.extend(["demanda_externa_a_confirmar", "compromissos_caixa_a_confirmar"])
                    if preview["hub_price"] is None:
                        pending.append("custo_hub_a_confirmar")
                    if preview["hub_points"] is None:
                        pending.append("pontos_hub_a_confirmar")
                    elif preview["hub_points"] > 0:
                        pending.append("saldo_pontos_hub_a_confirmar")
                    if external_budget.get("available_before_commitments") is None:
                        pending.append("saldo_reserva_a_confirmar")
                    if preview["hub_only_exceeds_available"] is True:
                        pending.append("saldo_insuficiente_para_hub")
                if sample.get("event_demand_boosted") is True:
                    pending.append("demanda_evento_temporario")
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
                occupancy = sample.get("fleet_occupancy")
                if occupancy:
                    if occupancy["own_aircraft_count"] > 0:
                        pending.append("rota_ocupada_frota_propria")
                    if occupancy["game_count_disagrees"]:
                        pending.append("contagem_rota_divergente")
                economics = None
                if physical["status"] != "direct_shortfall":
                    economics = research_economics_preview(
                        sample, model, variant, engine_evidence, operating_market, mode_key, preview_margin)
                if economics is not None:
                    economics["expires_at"] = min(economics["expires_at"],
                                                  operating_market_stats.mode_read_at + 900,
                                                  physical["expires_at"],
                                                  engine_evidence["observed_at"] + MAX_EVIDENCE_AGE,
                                                  market["observed_at"] + MAX_EVIDENCE_AGE)
                    if occupancy:
                        economics["expires_at"] = min(economics["expires_at"], occupancy["expires_at"])
                queue.append({
                    "hub_id": hub_id, "hub_code": hubs[hub_id]["code"],
                    "destination_id": sample["destination_id"],
                    "distance_km": sample["distance_km"],
                    "direct_range_sufficient": (model["range_km"] >= sample["distance_km"]
                                                if model["range_km"] is not None else None),
                    "observed_demand": sample["demand"],
                    "event_demand_boosted": sample.get("event_demand_boosted"),
                    "destination_runway_ft": sample.get("destination_runway_ft"),
                    "route_detail": sample.get("route_detail"),
                    "fleet_occupancy": occupancy,
                    "model_id": model["id"], "model": model["name"],
                    "range_km": model["range_km"], "capacity": model["capacity"],
                    "catalog_price": model["catalog_price"],
                    "engine_id": variant["engine_id"] if variant else None,
                    "engine_label": variant["engine_label"] if variant else None,
                    "engine_available": variant["engine_available"] if variant else None,
                    "engine_selected": variant["engine_selected"] if variant else None,
                    "engine_speed": variant["engine_speed"] if variant else None,
                    "engine_fuel": variant["engine_fuel"] if variant else None,
                    "engine_detail": variant["engine_detail"] if variant else None,
                    "physical_feasibility": physical,
                    **({"stopover_research": stopover} if stopover else {}),
                    "final_aircraft_price": None,
                    **({"external_cost_preview": preview} if external else {}),
                    "economics_preview": economics,
                    "daily_net_profit": None, "status": "pesquisa_pendente",
                    "pending": pending, "purchase_eligible": False,
                    "evidence": {
                        "hub": {"source": hub_source,
                                "observed_at": hubs[hub_id]["observed_at"] if external else inventory["observed_at"]},
                        **({"ownership": {"source": "game_hub_select",
                                          "observed_at": inventory["ownership_observed_at"]}}
                           if external else {}),
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
         "last_attempt_at": attempts_by_hub.get(hub_id, {}).get("last_attempt_at"),
         "last_attempt_status": attempts_by_hub.get(hub_id, {}).get("last_attempt_status", "unattempted"),
         **{key: value for key, value in attempts_by_hub.get(hub_id, {}).items()
            if key.startswith("last_requested_") or key == "last_search_scope"},
         "last_route_observed_at": max(
             (item["observed_at"] for item in samples_by_hub.get(hub_id, ())), default=None
         ),
         "coverage": "partial",
         "status": ("pesquisa_iniciada" if samples_by_hub.get(hub_id)
                    else "pesquisa_inconclusiva"
                    if (conflicts_by_hub[hub_id]
                        or attempts_by_hub.get(hub_id, {}).get("last_attempt_status") == "inconclusive")
                    else "nao_pesquisado")}
        for hub_id in sorted(hubs, key=int)
    ]
    return {
        "source": "derived_external_research_queue" if external else "derived_research_queue", "read_only": True,
        "coverage": "partial", "purchase_eligible": False,
        **({"external_hubs": len(hubs), "origin_scope": "external_catalog",
            "external_budget": external_budget} if external else {"owned_hubs": len(hubs)}),
        "sampled_hubs": len(samples_by_hub),
        "sampled_routes": sum(len(rows) for rows in samples_by_hub.values()),
        "conflicted_routes": sum(conflicts_by_hub.values()),
        "hub_coverage": hub_coverage,
        "market_models": len(models), "market_observed_at": market.get("observed_at"),
        "operating_market": operating_market,
        "items": queue, "has_more": has_more,
        "total_candidates": total_candidates, "offset": offset,
        "page_size": max_items,
        "next_offset": offset + len(queue) if has_more else None,
        "snapshot_fingerprint": fingerprint, "cursor_reset": cursor_reset,
        "layout_fingerprint": layout_fingerprint,
        "blocking_reasons": blockers,
    }
