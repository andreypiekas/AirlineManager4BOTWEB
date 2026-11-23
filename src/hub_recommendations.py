"""Read-only next-aircraft scenarios for hubs verified in the active profile.

Call ``rank_next_aircraft(HubRegistry().snapshot(routes), scenarios,
route_report=routes, cash=cash, cash_observed_at=stamp, reserve=reserve)``.
``scenarios`` is a list of observations for the SAME profile. Each entry uses::

    {
        "hub_id": "123", "model": "A320", "source": "game_research",
        "observed_at": 1800000000, "origin": {"id": "123"},
        "destination": {"id": "456"}, "distance_km": 1200,
        "range_km": 3500, "runway_m": 3000, "required_runway_m": 2200,
        "demand_remaining": 400, "demand_verified": True,
        "range_verified": True, "runway_verified": True,
        "route_feasible": True, "route_available": True,
        "financial": {"source": "route_optimizer", "observed_at": 1800000000,
                      "profit_per_day": 1500},
        "costs": {"source": "game_market", "observed_at": 1800000000,
                  "aircraft_price": 20000, "route_fee": 500,
                  "hangar_price": 0},
    }

``source='game_research'`` means the route, remaining demand, availability,
distance and physical constraints were explicitly read from the game.
``runway_m`` is the shortest runway across the direct route's endpoints. The
``financial`` block names the existing estimator or game observation, while
``costs`` carries separately dated prices. For a stopover, supply
``stopover={"verified": True, "airport_id": "789", "legs_km": [...], "runway_m": ...,
"runway_verified": True}``. Every leg must fit the aircraft range.

The caller supplies recently game-confirmed cash using ``recent_verified_money``
and an independently read RouteRegistry snapshot. No network access or game
actions happen here. Missing, partial, conflicting, and old evidence remains
visible with a pending status instead of becoming a recommendation.

The result includes ``recommendations`` (one best viable route per owned hub),
``candidates`` (all evaluated scenarios), and ``hubs`` (including empty hubs).
"""
from __future__ import annotations

import math
import re
import time
from typing import Iterable, Optional

from route_registry import endpoint, route_key, same_route


MAX_AGE_SECONDS = 3 * 86400
MAX_CASH_AGE_SECONDS = 900
_HUB_ID = re.compile(r"^[1-9][0-9]{0,11}$")
_FINANCIAL_SOURCES = {"route_optimizer", "game_research"}
_COST_SOURCES = {"game_market", "game_research"}
_RESEARCH_EVIDENCE_FIELDS = (
    "source", "observed_at", "engine_id", "engine_label", "distance_km", "range_km", "runway_m",
    "required_runway_m", "demand_remaining", "demand_verified",
    "range_verified", "runway_verified", "route_feasible", "route_available",
    "stopover", "financial", "costs",
)


def _number(value: object, *, positive: bool = False) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    if not math.isfinite(number) or number < 0 or (positive and number == 0):
        return None
    return number


def _profit(value: object) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _recent(stamp: object, now: float, max_age: int) -> bool:
    return (_number(stamp) is not None and 0 <= now - float(stamp) <= max_age)


def _endpoint(raw: object) -> dict:
    """Guard route_registry's canonicalizer against malformed imported rows."""
    if not isinstance(raw, dict):
        return endpoint()
    return endpoint(raw.get("id"), raw.get("code"), raw.get("name"))


def _route_occupied(origin: dict, destination: dict, relations: list[dict]) -> bool:
    candidate_key = route_key(origin, destination)
    for entry in relations:
        previous_origin = entry.get("origin")
        previous_destination = entry.get("destination")
        if (isinstance(previous_origin, dict) and isinstance(previous_destination, dict)
                and same_route({"origin": origin, "destination": destination},
                               {"origin": _endpoint(previous_origin),
                                "destination": _endpoint(previous_destination)})):
            return True
        if candidate_key and entry.get("route_key") == candidate_key:
            return True
    return False


def _ordering(row: dict) -> tuple:
    """Stable even when pagination delivers scenarios in different orders."""
    profit = row.get("profit_per_day")
    return (-profit if profit is not None else float("inf"),
            row["investment"] if row["investment"] is not None else float("inf"),
            row["hub_code"], row["hub_id"], row["model"].casefold(),
            row["engine_id"] or "", row["engine_label"] or "",
            row["route_key"] or "", -(_number(row.get("observed_at")) or 0),
            row["model"],
            *(row[side][field] for side in ("origin", "destination")
              for field in ("id", "code", "name", "normalized_name")),
            str(row["financial_source"]), str(row["costs_source"]),
            tuple(row["pending"]))


def rank_next_aircraft(
    hub_inventory: dict,
    scenarios: Iterable[dict],
    *,
    route_report: Optional[dict] = None,
    cash: object = None,
    cash_observed_at: object = None,
    reserve: object = 0,
    now: Optional[float] = None,
    model: Optional[str] = None,
) -> dict:
    """Rank one viable next-aircraft scenario per owned hub without writes.

    Parameters are in-memory snapshots from the active profile. ``model`` can
    restrict all hubs to the same aircraft model for an apples-to-apples view.
    Inventory/route reads and evidence blocks must be independent game reads.
    Three-day research/pricing freshness and 15-minute balance freshness are
    enforced. Unknown occupied routes on partial fleet pages require explicit
    ``route_available=True`` game research before a viable recommendation.
    """
    now = time.time() if now is None else float(now)
    inventory = hub_inventory if isinstance(hub_inventory, dict) else {}
    raw_hubs = inventory.get("hubs")
    hubs_by_id = {}
    for hub in raw_hubs if isinstance(raw_hubs, list) else []:
        if isinstance(hub, dict):
            hub_id = str(hub.get("id") or "")
            if _HUB_ID.fullmatch(hub_id):
                hubs_by_id[hub_id] = {
                    "id": hub_id,
                    "code": str(hub.get("code") or ""),
                    "name": str(hub.get("name") or ""),
                    "aircraft_count": hub.get("aircraft_count", 0),
                }
    inventory_fresh = (inventory.get("source") == "game_hub_select"
                       and _recent(inventory.get("observed_at"), now, MAX_AGE_SECONDS))
    balance_fresh = _recent(cash_observed_at, now, MAX_CASH_AGE_SECONDS)
    cash_value = _number(cash) if balance_fresh else None
    reserve_value = _number(reserve)
    available = (max(0.0, cash_value - reserve_value)
                 if cash_value is not None and reserve_value is not None else None)

    relations = route_report.get("relations") if isinstance(route_report, dict) else None
    relations_known = (isinstance(relations, list)
                       and all(isinstance(item, dict) for item in relations))
    known_routes = relations if relations_known else []
    candidates = []
    observations_by_route = {}
    raw_scenarios = scenarios if isinstance(scenarios, Iterable) and not isinstance(
        scenarios, (str, bytes, dict)) else []
    for scenario in raw_scenarios:
        if not isinstance(scenario, dict):
            continue
        hub_id = str(scenario.get("hub_id") or "")
        hub = hubs_by_id.get(hub_id)
        if hub is None:
            continue
        aircraft_model = str(scenario.get("model") or "").strip()
        if model is not None and aircraft_model.casefold() != model.strip().casefold():
            continue
        # A propulsion variant is an independent investment alternative.
        # Older research without an engine_id retains its original grouping.
        engine_id = scenario.get("engine_id")
        engine_id = engine_id.strip() if isinstance(engine_id, str) else None
        engine_id = engine_id or None
        engine_label = scenario.get("engine_label")
        engine_label = engine_label.strip() if isinstance(engine_label, str) else None
        engine_label = engine_label or None
        origin = _endpoint(scenario.get("origin"))
        destination = _endpoint(scenario.get("destination"))
        key = route_key(origin, destination)
        financial = scenario.get("financial") if isinstance(scenario.get("financial"), dict) else {}
        costs = scenario.get("costs") if isinstance(scenario.get("costs"), dict) else {}
        profit = _profit(financial.get("profit_per_day"))
        cost_parts = [_number(costs.get(field)) for field in
                      ("aircraft_price", "route_fee", "hangar_price")]
        cost_total = sum(cost_parts) if all(v is not None for v in cost_parts) else None
        investment = round(cost_total, 2) if _number(cost_total) is not None else None
        missing = []
        if not inventory_fresh:
            missing.append("inventario_hubs_desatualizado")
        if not (scenario.get("source") == "game_research"
                and _recent(scenario.get("observed_at"), now, MAX_AGE_SECONDS)):
            missing.append("pesquisa_desatualizada")
        if not (financial.get("source") in _FINANCIAL_SOURCES
                and _recent(financial.get("observed_at"), now, MAX_AGE_SECONDS)
                and profit is not None):
            missing.append("projecao_financeira_a_confirmar")
        if not (costs.get("source") in _COST_SOURCES
                and _recent(costs.get("observed_at"), now, MAX_AGE_SECONDS)
                and investment is not None):
            missing.append("custos_a_confirmar")
        if engine_id is not None:
            # A model's base price and a projection for another propulsion
            # variant cannot authorize a recommendation for this engine.
            if (costs.get("engine_id") != engine_id
                    or costs.get("aircraft_price_includes_engine") is not True):
                missing.append("preco_motor_a_confirmar")
            if financial.get("engine_id") != engine_id:
                missing.append("lucro_motor_a_confirmar")
        if not aircraft_model:
            missing.append("modelo_a_confirmar")
        if not (key and (origin["id"] == hub_id or destination["id"] == hub_id)
                and (origin["id"] or origin["code"])
                and (destination["id"] or destination["code"])):
            missing.append("rota_da_base_a_confirmar")
        if scenario.get("demand_verified") is not True or _number(scenario.get("demand_remaining")) is None:
            missing.append("demanda_a_confirmar")
        if scenario.get("range_verified") is not True or _number(scenario.get("range_km"), positive=True) is None:
            missing.append("alcance_a_confirmar")
        if scenario.get("runway_verified") is not True or any(
                _number(scenario.get(field), positive=True) is None
                for field in ("runway_m", "required_runway_m")):
            missing.append("pista_a_confirmar")
        if _number(scenario.get("distance_km"), positive=True) is None:
            missing.append("distancia_a_confirmar")
        if type(scenario.get("route_feasible")) is not bool:
            missing.append("viabilidade_a_confirmar")
        if not relations_known:
            missing.append("ocupacao_da_frota_a_confirmar")
        if type(scenario.get("route_available")) is not bool:
            missing.append("disponibilidade_da_rota_a_confirmar")
        if available is None:
            missing.append("saldo_ou_reserva_a_confirmar")
        if (investment is not None and profit is not None and profit > 0
                and _number(investment / profit) is None):
            missing.append("prazo_retorno_a_confirmar")

        # Numeric checks complement game flags, preventing contradictory input
        # from being shown as viable. Stopovers must be individually verified.
        infeasible = scenario.get("route_feasible") is False
        remaining = _number(scenario.get("demand_remaining"))
        if remaining is not None and remaining == 0:
            infeasible = True
        runway = _number(scenario.get("runway_m"), positive=True)
        required_runway = _number(scenario.get("required_runway_m"), positive=True)
        if runway is not None and required_runway is not None and runway < required_runway:
            infeasible = True
        distance = _number(scenario.get("distance_km"), positive=True)
        aircraft_range = _number(scenario.get("range_km"), positive=True)
        stopover = scenario.get("stopover")
        if stopover is not None:
            if not isinstance(stopover, dict) or stopover.get("verified") is not True:
                missing.append("escala_a_confirmar")
            else:
                legs = stopover.get("legs_km")
                stopover_runway = _number(stopover.get("runway_m"), positive=True)
                stopover_id = str(stopover.get("airport_id") or "")
                if (not _HUB_ID.fullmatch(stopover_id)
                        or stopover_id in (origin["id"], destination["id"])
                        or not isinstance(legs, list) or len(legs) != 2
                        or any(_number(leg, positive=True) is None for leg in legs)
                        or stopover.get("runway_verified") is not True
                        or stopover_runway is None):
                    missing.append("escala_a_confirmar")
                elif aircraft_range is not None:
                    if any(float(leg) > aircraft_range for leg in legs):
                        infeasible = True
                    if distance is not None and sum(legs) < distance:
                        infeasible = True
                    if required_runway is not None and stopover_runway < required_runway:
                        infeasible = True
        elif distance is not None and aircraft_range is not None and distance > aircraft_range:
            infeasible = True

        occupied = bool(key and relations_known and _route_occupied(origin, destination, known_routes))
        if occupied:
            status = "rota_ocupada"
        elif missing:
            status = "dados_a_confirmar"
        elif scenario.get("route_available") is False:
            status = "rota_indisponivel"
        elif infeasible:
            status = "rota_inviavel"
        elif profit is not None and profit <= 0:
            status = "sem_lucro"
        elif investment is not None and available is not None and investment > available:
            status = "saldo_insuficiente"
        else:
            status = "viavel"
        return_days = (investment / profit if investment is not None and profit is not None
                       and profit > 0 else None)
        candidate = {
            "hub_id": hub_id, "hub_code": hub["code"], "hub_name": hub["name"],
            "model": aircraft_model, "engine_id": engine_id, "engine_label": engine_label,
            "route_key": key,
            "origin": origin, "destination": destination,
            "observed_at": _number(scenario.get("observed_at")),
            "profit_per_day": round(profit, 2) if profit is not None else None,
            "investment": investment,
            "payback_days": round(return_days, 1)
            if status == "viavel" and _number(return_days) is not None else None,
            "status": status, "pending": sorted(set(missing)),
            "financial_source": financial.get("source"), "costs_source": costs.get("source"),
        }
        candidates.append(candidate)
        if key and aircraft_model:
            identity = (hub_id, aircraft_model.casefold(), key, engine_id)
            observations_by_route.setdefault(identity, []).append((candidate, scenario))

    # A later game observation replaces an earlier one for the same hub,
    # aircraft model and undirected route. Conflicting observations with the
    # exact same timestamp cannot establish which research is authoritative.
    for observations in observations_by_route.values():
        if len(observations) < 2:
            continue
        latest = max(
            row["observed_at"] if row["observed_at"] is not None else float("-inf")
            for row, _ in observations
        )
        latest_observations = [
            scenario for row, scenario in observations
            if (row["observed_at"] if row["observed_at"] is not None
                else float("-inf")) == latest
        ]
        conflicting = any(
            scenario.get(field) != latest_observations[0].get(field)
            for scenario in latest_observations[1:]
            for field in _RESEARCH_EVIDENCE_FIELDS
        )
        for row, _ in observations:
            observed_at = row["observed_at"]
            reason = ("pesquisa_substituida"
                      if observed_at is None or observed_at < latest else
                      "pesquisas_conflitantes" if conflicting else None)
            if reason:
                row["pending"] = sorted(set([*row["pending"], reason]))
                if row["status"] == "viavel":
                    row["status"] = "dados_a_confirmar"
                    row["payback_days"] = None

    status_rank = {"viavel": 0, "saldo_insuficiente": 1, "sem_lucro": 2,
                   "rota_inviavel": 3, "rota_ocupada": 4,
                   "rota_indisponivel": 5, "dados_a_confirmar": 6}
    candidates.sort(key=lambda row: (status_rank[row["status"]], _ordering(row)))
    best_by_hub = {}
    for row in candidates:
        if row["status"] == "viavel" and row["hub_id"] not in best_by_hub:
            best_by_hub[row["hub_id"]] = row
    recommendations = sorted(best_by_hub.values(), key=_ordering)
    hubs = []
    for hub in sorted(hubs_by_id.values(), key=lambda h: (h["code"], h["id"])):
        hub_scenarios = [row for row in candidates if row["hub_id"] == hub["id"]]
        hubs.append({**hub, "recommendation": best_by_hub.get(hub["id"]),
                     "scenario_count": len(hub_scenarios),
                     "status": (best_by_hub[hub["id"]]["status"] if hub["id"] in best_by_hub
                                else hub_scenarios[0]["status"] if hub_scenarios else "dados_a_confirmar")})
    return {"recommendations": recommendations, "candidates": candidates, "hubs": hubs,
            "cash": cash_value, "cash_observed_at": _number(cash_observed_at),
            "reserve": reserve_value, "available_cash": available,
            "inventory_observed_at": _number(inventory.get("observed_at")),
            "partial_fleet": bool(inventory.get("partial_fleet", True)),
            "source": inventory.get("source"), "read_only": True}
