"""Sample an existing aircraft's native route quote before fleet management allocates it."""
from __future__ import annotations

import logging

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from airport_catalog import game_code
from helpers import game_whole_number
from hub_expansion import HubExpansionRegistry
from hub_registry import HubRegistry
from native_route_quotes import native_route_quotes, record_native_route_quote
from reroute import read_direct_form
from route_detail_evidence import validated_detail
from route_registry import endpoint
from route_stopover import parked_specs, read_route_fares, research_details

log = logging.getLogger("am4bot.rutas")

_PARKED_AIRCRAFT_LIMIT = 3
_DESTINATIONS_PER_AIRCRAFT = 3


def _eligible_detail(bot, aircraft_id, sample, hub_code):
    origin, dest = sample["origin_id"], sample["destination_id"]
    raw = research_details(bot, origin, dest)
    detail = validated_detail(raw, origin, dest, expected_runway=sample.get("destination_runway_ft"),
                              hub_code=hub_code)
    if not detail or detail.get("observed_aircraft_on_route") != 0:
        return None
    ids = raw.get("capable_aircraft_ids")
    if (not isinstance(ids, list) or any(not isinstance(value, str) for value in ids)
            or len(ids) != detail.get("observed_capable_aircraft") or len(set(ids)) != len(ids)
            or aircraft_id not in ids):
        return None
    return detail


def _read_preview(bot, aircraft_id, sample):
    origin_id, dest_id = sample["origin_id"], sample["destination_id"]
    origin = endpoint(origin_id, code=game_code(origin_id))
    dest = endpoint(dest_id, code=game_code(dest_id))
    previous = bot.js("const previous = typeof arrId === 'undefined' ? null : arrId;"
                      "arrId = arguments[0]; return previous;", int(dest_id))
    try:
        panel = bot.ajax(f"new_route_info.php?id={aircraft_id}&airportId={dest_id}&mode=res",
                         "newRouteInfo", timeout=8)
        form = read_direct_form(bot, aircraft_id, origin, dest, include_consumption=True)
        if not form or abs(form[0] - sample["distance_km"]) > 5 or bot.stopping:
            return None
        auto = panel.find_elements(By.ID, "introAuto")
        if len(auto) != 1:
            return None
        auto[0].click()

        def ready(_driver):
            if bot.stopping:
                return True
            buttons = panel.find_elements(By.CSS_SELECTOR, "#btnCreateNewRoute:not(.not-active):not([disabled])")
            return read_route_fares(bot) if len(buttons) == 1 else None

        fares = WebDriverWait(bot.driver, 5).until(ready)
        if (bot.stopping or read_direct_form(bot, aircraft_id, origin, dest, include_consumption=True) != form
                or read_route_fares(bot) != fares):
            return None
        return form, fares
    finally:
        bot.js("$('#newRouteInfo').hide(); arrId = arguments[0];", previous)


def collect_parked_route_quote(bot, parked_ids, *, refresh_demand: bool = False) -> bool:
    """Read at most one preview from verified Parked inventory and owned-hub research."""
    inventory = HubRegistry().snapshot()
    if not parked_ids or not inventory.get("hub_catalog_fresh") or bot.stopping:
        return False
    hubs = {hub["id"]: hub.get("code") for hub in inventory["hubs"]}
    aircraft_limit = _PARKED_AIRCRAFT_LIMIT if refresh_demand else 1
    refreshed_origins = set() if refresh_demand else None
    for aircraft_id in sorted(parked_ids, key=int)[:aircraft_limit]:
        if bot.stopping:
            break
        try:
            if _collect_aircraft_quote(bot, aircraft_id, hubs, refreshed_origins):
                log.info("Tarifas e taxa de uma aeronave estacionada observadas na prévia nativa.")
                return True
        except WebDriverException:
            log.debug("A prévia de rota da aeronave %s não pôde ser conferida neste ciclo.", aircraft_id)
    return False


def _collect_aircraft_quote(bot, aircraft_id, hubs, refreshed_origins):
    specs = parked_specs(bot, aircraft_id)
    origin = specs.get("id") if specs else None
    limit = game_whole_number(specs.get("range")) if specs else None
    if origin not in hubs or not limit or bot.stopping:
        return False
    quoted = {row["destination_id"] for row in native_route_quotes(bot)
              if row["aircraft_id"] == aircraft_id and row["origin_id"] == origin
              and row["stopover_id"] is None}
    demand = HubExpansionRegistry()
    samples = demand.demand_research_snapshot({origin})["samples"]
    if not samples and refreshed_origins is not None and origin not in refreshed_origins:
        from game_observations import collect_owned_hub_demand

        refreshed_origins.add(origin)
        try:
            collected = collect_owned_hub_demand(bot, origin_id=origin)
        finally:
            if not bot.stopping:
                bot.open_popup("routes_main.php", "Routes", "nav_routes")
        if not collected or bot.stopping:
            return False
        samples = demand.demand_research_snapshot({origin})["samples"]
    candidates = [sample for sample in samples if sample["origin_id"] == origin
                  and sample["destination_id"] not in quoted and sample["distance_km"] <= limit
                  and not sample.get("route_detail_conflict")
                  and sample.get("route_detail", {}).get("observed_aircraft_on_route", 0) == 0]
    candidates.sort(key=lambda sample: -sample["distance_km"])
    for sample in candidates[:_DESTINATIONS_PER_AIRCRAFT]:
        if bot.stopping:
            break
        detail = _eligible_detail(bot, aircraft_id, sample, hubs[origin])
        if not detail:
            continue
        quote = _read_preview(bot, aircraft_id, sample)
        if not quote or bot.stopping:
            return False
        again = _eligible_detail(bot, aircraft_id, sample, hubs[origin])
        if not again or bot.stopping:
            return False
        (distance, fee, occupied, fuel, co2_rate), fares = quote
        daily = detail.get("observed_daily_demand")
        daily_counts = tuple(daily[key] for key in "yjf") if daily == again.get("observed_daily_demand") and daily else None
        today = detail.get("observed_today_demand")
        today_counts = tuple(today[key] for key in "yjf") if today == again.get("observed_today_demand") and today else None
        return record_native_route_quote(
            bot, aircraft_id=aircraft_id, origin_id=origin, destination_id=sample["destination_id"],
            distance=distance, fee=fee, occupied=occupied, fares=fares, total_demand=daily_counts,
            today_demand=today_counts, fuel_lbs_per_leg=fuel, co2_kg_per_pax_km=co2_rate,
            research_distance_km=sample["distance_km"],
            event_demand_boosted=any(row.get("event_demand_boosted") is True for row in (detail, again, sample)),
        )
    return False
