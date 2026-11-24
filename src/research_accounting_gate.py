"""Bridge captured research to the acquisition accounting contract.

Research identities and observations are useful even when checkout, residual
demand and native seat configuration remain unknown. The same accounting gate
used for complete proposals reports the missing evidence for these hypotheses.
"""
from __future__ import annotations

from expansion_economics import evaluate_expansion_economics
from opportunity_models import DEFAULT_MAX_AGE_SECONDS, native_free_passenger_hangar_cost
from route_detail_evidence import current_detail


def evaluate_research_gate(snapshot, item, *, now, margin, native_reference=None):
    """Evaluate shared prerequisites for all hypothetical layouts of one row."""
    binding = {key: snapshot[key] for key in ("profile_id", "snapshot_id")}

    def evidence(source, stamp, **fields):
        return {**binding, "source": source, "observed_at": stamp,
                "verified": True, **fields}

    def current(stamp):
        return (type(stamp) in (int, float) and stamp > 0
                and 0 <= now - stamp <= DEFAULT_MAX_AGE_SECONDS)

    hub, destination = item["hub_id"], item["destination_id"]
    model, engine = item["model_id"], item["engine_id"]
    route_stamp = item["evidence"]["route"]["observed_at"]
    detail = item.get("engine_detail") or {}
    engine_evidence = item["evidence"].get("engine") or {}
    shop_verified = (detail.get("model_identity_verified") is True
                     and engine_evidence.get("model_detail_identity_verified") is True
                     and engine_evidence.get("observed_model_id") == model
                     and current(detail.get("observed_at"))
                     and current(engine_evidence.get("observed_at")))
    shop_stamp = min(detail["observed_at"], engine_evidence["observed_at"]) if shop_verified else None
    occupancy = item.get("fleet_occupancy") or {}
    occupied = None
    if (current(occupancy.get("observed_at")) and now < occupancy["expires_at"]
            and occupancy.get("game_count_disagrees") is False):
        if occupancy["own_aircraft_count"] > 0:
            occupied = True
        elif occupancy.get("count_complete") is True:
            occupied = False

    physical = item["physical_feasibility"]
    route_detail = current_detail(item.get("route_detail"), hub, destination, now) or {}
    stop = item.get("stopover_research")
    # A positive observation is sufficient to reject an investment. Neither
    # an empty native form nor an empty route detail proves fleet coverage.
    detail_count = route_detail.get("observed_aircraft_on_route")
    if type(detail_count) is int and detail_count > 0:
        occupied = True
    if native_reference and native_reference["aircraft_on_route_range"]["max"] > 0:
        occupied = True
    route = evidence("game_route_search", route_stamp, id_source="game",
                     origin_id=hub, destination_id=destination,
                     stopover_id=stop["stop_id"] if stop else None,
                     distance_km=item["distance_km"], occupied=occupied,
                     available=None, feasible=None, demand_remaining=None,
                     demand_verified=False)
    # Preserve the units of the native read while converting to the v1 contract.
    # The exploratory stopover has no native availability/rules confirmation.
    if shop_verified:
        route["range_km"] = physical["variant_range_km"]
        required = physical["required_runway_ft"]
        route["required_runway_m"] = required * 0.3048 if required is not None else None
    if current(route_detail.get("observed_at")):
        for key in ("origin", "destination"):
            feet = route_detail.get(f"{key}_runway_ft")
            route[f"{key}_runway_m"] = feet * 0.3048 if feet is not None else None
    if stop:
        route["stopover_verified"] = False

    aircraft = {**evidence("game_aircraft_shop", shop_stamp, id_source="game"),
                "verified": shop_verified, "model_id": model, "engine_id": engine,
                "engine_model_id": model if shop_verified else None,
                "available": None}
    costs = {}
    owned = next((row for row in snapshot["hubs"] if row["id"] == hub), None)
    if owned and owned.get("owned") is True and owned.get("verified") is True:
        costs["hub_cost"] = evidence("game_hub_select", owned["observed_at"], hub_id=hub, value=0)
    hangar_cost = native_free_passenger_hangar_cost(snapshot, hub, now=now)
    if hangar_cost is not None:
        costs["hangar_cost"] = hangar_cost
    candidate = {**binding, "schema_version": 1, "kind": "aircraft_on_owned_hub",
                 "hub": {"id": hub}, "route": route, "aircraft": aircraft, "costs": costs}
    inputs = {}
    capacity = detail.get("metrics", {}).get("capacity_pax")
    if shop_verified and capacity is not None:
        inputs["capacity"] = evidence("game_aircraft_shop", shop_stamp,
                                      model_id=model, engine_id=engine, value=capacity)
    for kind, quote in snapshot["observations"]["market_quotes"].items():
        if (kind in ("fuel", "co2") and quote and quote.get("source") == "game_market"
                and quote.get("unit") == "USD/1000" and current(quote.get("observed_at"))
                and now < quote["expires_at"] and type(quote.get("price")) is int
                and quote["price"] > 0):
            inputs[f"{kind}_price_per_1000"] = evidence("game_market", quote["observed_at"],
                                                        value=quote["price"])

    result = evaluate_expansion_economics(snapshot, candidate, inputs, now=now,
                                          safety_margin_fraction=margin)
    layout_evaluations = []
    preview = item.get("economics_preview") or {}
    for row in preview.get("layouts", []):
        layout = row["layout"]
        # Bind the hypothetical configuration to the accounting identity without
        # claiming the shop has confirmed these seats. The provenance validator
        # deliberately rejects this envelope until native evidence is available.
        layout_inputs = {**inputs, "layout": {
            **binding, "source": "route_optimizer_what_if_v1", "verified": False,
            "model_id": model, "engine_id": engine, "value": layout,
        }}
        evaluation = evaluate_expansion_economics(snapshot, candidate, layout_inputs,
                                                 now=now, safety_margin_fraction=margin)
        layout_evaluations.append({
            "configuration_yjf": layout, "configuration_verified": False,
            "economics_id": evaluation["economics_id"], "status": evaluation["status"],
            "blocking_reasons": evaluation["blocking_reasons"],
            "purchase_eligible": False, "read_only": True,
        })
    return {"status": result["status"], "scope": "shared_layout_prerequisites",
            "economics_id": result["economics_id"], "read_only": True,
            "purchase_eligible": False, "blocking_reasons": result["blocking_reasons"],
            "verified_accounting_inputs": sorted(result["provenance"]),
            "verified_capital_costs": {field: {key: value[key] for key in ("value", "source", "observed_at")}
                                       for field, value in costs.items()
                                       if not any(reason["field"] == f"costs.{field}"
                                                  for reason in result["blocking_reasons"])},
            "excluded_costs": result["excluded_costs"],
            "total_investment": result["capital_costs"]["total_investment"],
            "cash_after_purchase": result["cash_after_purchase"],
            "layout_evaluations": layout_evaluations}
