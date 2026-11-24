"""Cached hub and aircraft observations only schedule research, never spending."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from economy import load_market, load_market_evidence
from hub_expansion import HubExpansionRegistry
from market import MarketQuote
from owned_hub_research_feed import build_external_hub_research_queue, build_owned_hub_research_queue


NOW = 1_900_000_000


def _inventory(*, observed_at=NOW):
    return {
        "source": "game_hub_select", "observed_at": observed_at,
        "hubs": [{"id": "2926", "code": "XAP"},
                 {"id": "2941", "code": "GRU"}],
    }


def _market(*, observed_at=NOW, models=None):
    if models is None:
        models = [
            {"id": 11, "name": "A320", "range": 6000,
             "capacity": 180, "price": 1700000},
            {"id": 22, "name": "B737", "range": 7000,
             "capacity": 190, "price": 1900000},
        ]
    return {"source": "bot_aircraft_market_cache", "observed_at": observed_at,
            "fresh": True, "models": models, "engine_prices_verified": False}


def _sample(origin="2926", dest="3139", *, observed_at=NOW, distance=2000):
    return {"source": "game_route_search", "observed_at": observed_at,
            "origin_id": origin, "destination_id": dest, "distance_km": distance,
            "y": 100, "j": 20, "f": 5}


def _fleet_report():
    return {"current_roster_verified": True, "current_roster_observed_at": NOW - 5,
            "current_roster_total": 1, "current_fleet_coverage_verified": True,
            "fleet_coverage": {"source": "game_roster_and_route_audit", "roster_observed_at": NOW - 5,
                               "observed_at": NOW - 3, "total": 1, "routes": 1, "parked": 0, "pending": 0},
            "current_relations": [{"aircraft_id": "1", "game_route_id": 123, "observed_route_id": 123,
                                   "source": "game", "route_data_stale": False, "last_seen": NOW - 4,
                                   "origin": {"code": "SLSA"}, "destination": {"id": "2926", "code": "XAP"}}]}


def test_fleet_route_occupancy_reconciles_inverse_route_and_airport_aliases():
    from research_route_occupancy import FleetRouteOccupancy

    report = _fleet_report()
    occupancy = FleetRouteOccupancy(report, NOW)
    observed = occupancy.evidence("2926", "3139", {"observed_aircraft_on_route": 0})
    assert observed == {"source": "game_roster_and_route_audit", "observed_at": NOW - 5,
                        "expires_at": NOW + 895, "own_aircraft_count": 1,
                        "count_complete": True, "game_count_disagrees": True}
    assert occupancy.evidence("3139", "2926", {"observed_aircraft_on_route": 1})["game_count_disagrees"] is False
    assert occupancy.evidence("2941", "3139", None)["own_aircraft_count"] == 0
    report["current_fleet_coverage_verified"] = False
    partial = FleetRouteOccupancy(report, NOW)
    assert partial.evidence("2941", "3139", None) is None
    assert partial.evidence("3139", "2926", {"observed_aircraft_on_route": 2})["game_count_disagrees"] is False
    assert partial.evidence("3139", "2926", None)["count_complete"] is False


@pytest.mark.parametrize("invalid", ["stale_roster", "stale_route", "wrong_route", "boolean_route",
                                     "missing_airport", "conflicting_airport", "duplicate_aircraft", "missing_identity"])
def test_invalid_fleet_evidence_cannot_create_exact_zero_or_known_match(invalid):
    from research_route_occupancy import FleetRouteOccupancy

    report = _fleet_report()
    row = report["current_relations"][0]
    if invalid == "stale_roster":
        report["current_roster_observed_at"] = NOW - 901
    elif invalid == "stale_route":
        row["last_seen"] = NOW - 3601
    elif invalid == "wrong_route":
        row["observed_route_id"] = 124
    elif invalid == "boolean_route":
        row.update(game_route_id=1, observed_route_id=True)
    elif invalid == "missing_airport":
        row["origin"] = {"code": "?"}
    elif invalid == "conflicting_airport":
        row["origin"] = {"id": "3139", "code": "XAP"}
    elif invalid == "duplicate_aircraft":
        report["current_relations"].append(deepcopy(row))
    else:
        row["aircraft_id"] = ""
    occupancy = FleetRouteOccupancy(report, NOW)
    assert occupancy.evidence("2926", "3139", None) is None
    assert occupancy.evidence("2941", "3139", None) is None


def test_duplicate_route_identity_and_invalid_candidate_pairs_cannot_certify_zero():
    from research_route_occupancy import FleetRouteOccupancy

    report = _fleet_report()
    complete = FleetRouteOccupancy(report, NOW)
    assert complete.evidence("2926", "2926", None) is None
    assert complete.evidence("", "3139", None) is None
    assert complete.evidence_for_endpoints({"id": "999999999999", "code": "XAP"},
                                           {"id": "3139"}) is None
    duplicate = {**report["current_relations"][0], "aircraft_id": "2"}
    report["current_relations"].append(duplicate)
    report["current_roster_total"] = 2
    report["fleet_coverage"].update(total=2, routes=2)
    occupancy = FleetRouteOccupancy(report, NOW)
    assert occupancy.evidence("2926", "3139", None) is None
    assert occupancy.evidence("2941", "3139", None) is None


def test_own_and_external_queues_share_fleet_occupancy_and_block_preview():
    inventory = {**_inventory(), "hub_catalog_fresh": True}
    report = _fleet_report()
    sample = _sample()
    sample["route_detail"] = {"source": "game_route_detail", "observed_at": NOW,
                              "origin_id": "2926", "destination_id": "3139",
                              "origin_runway_ft": 8000, "destination_runway_ft": 5000,
                              "observed_aircraft_on_route": 0}
    kwargs = {"now": NOW, "engines": _preview_engines(), "operating_market_stats": _preview_stats()}
    original = build_owned_hub_research_queue(inventory, [sample], _market(), **kwargs)
    owned = build_owned_hub_research_queue(inventory, [sample], _market(), route_report=report, **kwargs)
    external = {"origin_scope": "external_catalog", "candidate_source": "game_purchase_catalog",
                "candidate_inventory": [{"id": "3139", "code": "SBL", "observed_at": NOW}],
                "samples": [_sample("3139", "2926")]}
    other = build_external_hub_research_queue(inventory, external, _market(), route_report=report, **kwargs)
    assert any(row["economics_preview"] for row in original["items"])
    assert original["layout_fingerprint"] == owned["layout_fingerprint"]
    assert original["snapshot_fingerprint"] != owned["snapshot_fingerprint"]
    for page in (owned, other):
        assert page["items"]
        for item in page["items"]:
            assert item["fleet_occupancy"]["own_aircraft_count"] == 1
            assert "rota_ocupada_frota_propria" in item["pending"]
            assert "demanda_residual_a_confirmar" in item["pending"]
            assert item["economics_preview"] is None
            assert item["daily_net_profit"] is None
            assert item["purchase_eligible"] is False
    assert all("contagem_rota_divergente" in item["pending"] for item in owned["items"])


def test_market_quote_changes_evidence_cursor_without_changing_research_layout():
    inventory = _inventory()
    samples = [_sample()]
    stats = SimpleNamespace(fuel_quote=MarketQuote(600, NOW - 5, NOW + 10), co2_price=105)
    page = build_owned_hub_research_queue(inventory, samples, _market(), now=NOW,
                                         max_items=1, operating_market_stats=stats)
    assert page["operating_market"]["fuel"]["price"] == 600
    assert page["operating_market"]["co2"] is None
    assert page["purchase_eligible"] is False
    expired = build_owned_hub_research_queue(inventory, samples, _market(), now=NOW + 11,
                                            max_items=1, operating_market_stats=stats, offset=1,
                                            expected_fingerprint=page["snapshot_fingerprint"])
    assert expired["operating_market"]["fuel"] is None
    assert expired["cursor_reset"] is True
    assert expired["layout_fingerprint"] == page["layout_fingerprint"]
    external = {"origin_scope": "external_catalog", "candidate_source": "game_purchase_catalog",
                "candidate_inventory": [{"id": "3139", "code": "SBL", "observed_at": NOW}],
                "samples": [_sample("3139", "2926")]}
    other = build_external_hub_research_queue({**inventory, "hub_catalog_fresh": True}, external,
                                              _market(), now=NOW, operating_market_stats=stats)
    assert other["operating_market"] == page["operating_market"]
    assert other["purchase_eligible"] is False


def test_external_queue_keeps_ownership_and_financial_evidence_separate(tmp_path):
    from owned_hub_research_ingestion import OwnedHubResearchInputsRegistry

    inventory = {**_inventory(), "hub_catalog_fresh": True}
    external = {"origin_scope": "external_catalog", "candidate_source": "game_purchase_catalog",
                "candidate_inventory": [{"id": "3139", "code": "SBL", "observed_at": NOW - 10}],
                "samples": [_sample("3139", "2926"), _sample("2926", "3139")]}
    page = build_external_hub_research_queue(inventory, external, _market(), now=NOW,
                                             engines=_engines(), max_items=1)
    assert page["source"] == "derived_external_research_queue"
    assert page["external_hubs"] == page["sampled_hubs"] == page["sampled_routes"] == 1
    assert page["total_candidates"] == 3
    item = page["items"][0]
    assert item["hub_id"] == "3139"
    assert item["evidence"]["hub"] == {"source": "game_purchase_catalog", "observed_at": NOW - 10}
    assert item["evidence"]["ownership"] == {"source": "game_hub_select", "observed_at": NOW}
    assert item["purchase_eligible"] is False
    assert item["final_aircraft_price"] is None and item["daily_net_profit"] is None
    assert {"demanda_externa_a_confirmar", "custo_hub_a_confirmar", "pontos_hub_a_confirmar"} <= set(item["pending"])
    assert OwnedHubResearchInputsRegistry(tmp_path / "inputs.json").record_queue(page, now=NOW) == 0
    next_page = build_external_hub_research_queue(
        inventory, external, _market(), now=NOW, engines=_engines(), max_items=1,
        offset=page["next_offset"], expected_fingerprint=page["snapshot_fingerprint"])
    assert next_page["offset"] == 1 and next_page["items"][0]["engine_id"] == "2"
    acquired = {**inventory, "hubs": [*inventory["hubs"], {"id": "3139", "code": "SBL"}]}
    reset = build_external_hub_research_queue(
        acquired, external, _market(), now=NOW, offset=1,
        expected_fingerprint=page["snapshot_fingerprint"])
    assert reset["cursor_reset"] is True and not reset["items"]
    assert not build_external_hub_research_queue(
        {**inventory, "hub_catalog_fresh": False}, external, _market(), now=NOW)["items"]
    assert not build_external_hub_research_queue(
        inventory, {**external, "candidate_source": "unknown"}, _market(), now=NOW)["items"]


def test_external_cost_preview_is_independent_and_never_authorizes_purchase():
    inventory = {**_inventory(), "hub_catalog_fresh": True}
    candidate = {"id": "3139", "code": "SBL", "observed_at": NOW,
                 "hub_price": 5000, "hub_price_observed_at": NOW - 10,
                 "hub_points": 0, "hub_points_observed_at": NOW - 20}
    external = {"origin_scope": "external_catalog", "candidate_source": "game_purchase_catalog",
                "candidate_inventory": [candidate], "samples": [_sample("3139", "2926")]}

    def page(**kwargs):
        return build_external_hub_research_queue(inventory, external, _market(), now=NOW,
                                                 max_items=1, **kwargs)

    first = page(cash=6000, cash_observed_at=NOW, reserve=2000)
    assert first["external_budget"]["available_before_commitments"] == 4000
    item = first["items"][0]
    cost = item["external_cost_preview"]
    assert cost == {"hub_price": 5000, "hub_price_observed_at": NOW - 10,
                    "hub_points": 0, "hub_points_observed_at": NOW - 20,
                    "hub_only_exceeds_available": True, "total_investment": None,
                    "cash_after_purchase": None, "roi": None, "payback_days": None}
    assert "saldo_insuficiente_para_hub" in item["pending"]
    assert "compromissos_caixa_a_confirmar" in item["pending"]
    assert "pontos_hub_a_confirmar" not in item["pending"]
    assert "custo_hub_a_confirmar" not in item["pending"]
    assert item["purchase_eligible"] is False
    changed = page(cash=9000, cash_observed_at=NOW, reserve=2000, offset=1,
                   expected_fingerprint=first["snapshot_fingerprint"])
    assert changed["cursor_reset"] is True
    assert changed["items"][0]["external_cost_preview"]["hub_only_exceeds_available"] is False
    assert changed["items"][0]["purchase_eligible"] is False
    candidate.update(hub_price=0, hub_points=10, hub_points_conflict_at=NOW)
    reset = page(cash=0, cash_observed_at=NOW, reserve=0, offset=1,
                 expected_fingerprint=changed["snapshot_fingerprint"])
    assert reset["cursor_reset"] is True
    assert reset["items"][0]["external_cost_preview"]["hub_price"] == 0
    assert reset["items"][0]["external_cost_preview"]["hub_points"] is None
    candidate.pop("hub_points_conflict_at")
    candidate["hub_price_observed_at"] = NOW - 3 * 86400 - 1
    stale = page(cash=6000, cash_observed_at=NOW - 901, reserve=1000)
    assert stale["external_budget"]["available_before_commitments"] is None
    item = stale["items"][0]
    assert item["external_cost_preview"]["hub_price"] is None
    assert item["external_cost_preview"]["hub_points"] == 10
    assert item["external_cost_preview"]["hub_only_exceeds_available"] is None
    assert {"saldo_pontos_hub_a_confirmar", "saldo_reserva_a_confirmar",
            "custo_hub_a_confirmar"} <= set(item["pending"])


@pytest.mark.parametrize("price,points", [(False, True), (-1, -1), (float("inf"), 1.5),
                                          (float("nan"), 10_000_001)])
def test_external_cost_preview_rejects_invalid_amounts(price, points):
    candidate = {"id": "3139", "observed_at": NOW, "hub_price": price,
                 "hub_points": points, "hub_price_observed_at": NOW, "hub_points_observed_at": NOW}
    external = {"origin_scope": "external_catalog", "candidate_source": "game_purchase_catalog",
                "candidate_inventory": [candidate], "samples": [_sample("3139", "2926")]}
    result = build_external_hub_research_queue({**_inventory(), "hub_catalog_fresh": True},
                                              external, _market(), now=NOW,
                                              cash=False, cash_observed_at=NOW, reserve=0)
    assert result["external_budget"]["cash"] is None
    assert result["items"][0]["external_cost_preview"]["hub_price"] is None
    assert result["items"][0]["external_cost_preview"]["hub_points"] is None


def test_event_demand_is_persisted_and_blocks_queue(tmp_path, monkeypatch):
    monkeypatch.setattr("hub_expansion.time.time", lambda: NOW)
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    sample = {"arr_id": "3139", "distance": 2000, "y": 100, "j": 20, "f": 5,
              "event_demand_boosted": True}
    assert registry.record_demand("2926", [sample], observed_at=NOW) == 1
    rows = registry.demand_research_snapshot({"2926"}, now=NOW)["samples"]
    assert rows[0]["event_demand_boosted"] is True
    page = build_owned_hub_research_queue(_inventory(), rows, _market(), now=NOW)
    for item in page["items"]:
        assert item["event_demand_boosted"] is True
        assert "demanda_evento_temporario" in item["pending"]
        assert item["purchase_eligible"] is False
    from owned_hub_research_ingestion import OwnedHubResearchInputsRegistry
    inputs = OwnedHubResearchInputsRegistry(tmp_path / "inputs.json")
    assert inputs.record_queue(page, now=NOW) == len(page["items"])
    assert all(row["event_demand_boosted"] is True for row in inputs.snapshot(now=NOW))
    conflict = build_owned_hub_research_queue(
        _inventory(), [rows[0], {k: v for k, v in rows[0].items() if k != "event_demand_boosted"}],
        _market(), now=NOW)
    assert not conflict["items"]


def test_market_cache_preserves_timestamp_and_legacy_reader(tmp_path):
    path = tmp_path / "market.json"
    models = _market()["models"]
    path.write_text(json.dumps({"updated": NOW, "models": models}), encoding="utf-8")
    assert load_market(path) == models
    evidence = load_market_evidence(path, now=NOW + 120)
    assert evidence["models"] == models
    assert evidence["observed_at"] == NOW
    assert evidence["fresh"] is True
    assert evidence["engine_prices_verified"] is False


@pytest.mark.parametrize("stamp", [None, False, True, "1900000000", -1,
                                            NOW + 1, NOW - 3 * 86400 - 1])
def test_market_cache_rejects_invalid_stale_or_future_timestamp(tmp_path, stamp):
    path = tmp_path / "market.json"
    path.write_text(json.dumps({"updated": stamp, "models": _market()["models"]}),
                    encoding="utf-8")
    assert load_market_evidence(path, now=NOW)["fresh"] is False


def test_corrupt_market_is_inconclusive(tmp_path):
    path = tmp_path / "market.json"
    path.write_text("{broken", encoding="utf-8")
    assert load_market_evidence(path, now=NOW)["models"] == []
    assert load_market_evidence(path, now=NOW)["fresh"] is False


def test_research_queue_is_hub_balanced_with_evidence_and_cannot_purchase():
    samples = [_sample(), _sample("2941", "3139"), _sample("2926", "3140")]
    report = build_owned_hub_research_queue(
        _inventory(), samples, _market(), now=NOW, max_items=3)
    assert report["source"] == "derived_research_queue"
    assert report["coverage"] == "partial"
    assert report["read_only"] is True
    assert report["purchase_eligible"] is False
    assert report["sampled_hubs"] == 2
    assert report["sampled_routes"] == 3
    assert report["has_more"] is True
    assert [row["hub_id"] for row in report["items"]] == ["2926", "2941", "2926"]
    for row in report["items"]:
        assert row["observed_demand"] == {"y": 100, "j": 20, "f": 5}
        assert row["evidence"]["route"]["source"] == "game_route_search"
        assert row["evidence"]["model"]["observed_at"] == NOW
        assert row["status"] == "pesquisa_pendente"
        assert row["purchase_eligible"] is False
        assert row["engine_id"] is None
        assert row["final_aircraft_price"] is None
        assert row["daily_net_profit"] is None
        assert "demanda_residual_a_confirmar" in row["pending"]
        assert "cobertura_da_frota_a_confirmar" in row["pending"]


def _engines(*, observed_at=NOW, model="A320", engine_id="1"):
    return {"source": "game_aircraft_order_detail", "models": {"11": {
        "source": "game_aircraft_order_detail", "model_id": "11", "model": model,
        "observed_at": observed_at, "engine_prices_verified": False,
        "model_detail_identity_verified": False,
        "selected_engine_id": engine_id,
        "variants": [
            {"engine_id": engine_id, "label": "Trent <prova>", "available": True,
             "selected": True, "speed": 905, "fuel": 12.1},
            {"engine_id": "2", "label": "Motor indisponível", "available": False,
             "selected": False, "speed": None, "fuel": None},
        ],
    }}}


def test_research_queue_schedules_distinct_engine_variants_across_owned_hubs():
    rows = build_owned_hub_research_queue(
        _inventory(), [_sample(), _sample("2941", "3139")],
        _market(models=[{"id": 11, "name": "A320", "range": 6000,
                         "capacity": 180, "price": 1700000}]),
        engines=_engines(), now=NOW, max_items=4)
    assert [row["hub_id"] for row in rows["items"]] == ["2926", "2941", "2926", "2941"]
    assert [row["engine_id"] for row in rows["items"]] == ["1", "1", "2", "2"]
    assert rows["has_more"] is False
    for row in rows["items"]:
        assert row["evidence"]["engine"]["source"] == "game_aircraft_order_detail"
        assert row["engine_label"]
        assert row["final_aircraft_price"] is None
        assert row["purchase_eligible"] is False
        assert "motor_a_pesquisar" not in row["pending"]
        assert "preco_final_motor_a_confirmar" in row["pending"]
        assert "identidade_modelo_detalhe_a_confirmar" in row["pending"]
        if row["engine_id"] == "2":
            assert "motor_indisponivel" in row["pending"]


@pytest.mark.parametrize("verified", [True, False])
def test_selected_detail_is_exposed_but_only_correlated_metrics_feed_model(verified):
    engines = _engines(observed_at=NOW - 5)
    catalog = engines["models"]["11"]
    catalog["model_detail_identity_verified"] = verified
    catalog["observed_model_id"] = "11" if verified else None
    catalog["variants"][0].update(speed=None, fuel=None)
    metrics = {"speed_kph": 881, "fuel_lbs_per_km": 11.55, "range_km": 5700,
               "capacity_pax": 164, "required_runway_ft": 6500,
               "displayed_cost_usd": 6770196}
    catalog["variant_details"] = {"1": {"observed_at": NOW - 2, "metrics": metrics}}
    page = build_owned_hub_research_queue(_inventory(), [_sample()], _market(),
                                         engines=engines, now=NOW)
    item = next(row for row in page["items"] if row["engine_id"] == "1")
    assert item["engine_detail"] == {"observed_at": NOW - 2, "metrics": metrics,
                                     "model_identity_verified": verified}
    assert item["engine_speed"] == (881 if verified else None)
    assert item["engine_fuel"] == (11.55 if verified else None)
    assert item["range_km"] == (5700 if verified else 6000)
    assert item["capacity"] == (164 if verified else 180)
    assert item["final_aircraft_price"] is None
    assert item["purchase_eligible"] is False
    catalog["variant_details"]["2"] = None
    invalid = build_owned_hub_research_queue(_inventory(), [_sample()], _market(),
                                            engines=engines, now=NOW)
    assert all(row["engine_id"] is None for row in invalid["items"])


@pytest.mark.parametrize("page_size", [1, 2, 3, 4, 7])
def test_research_pages_cover_all_candidates_in_hub_balanced_order(page_size):
    samples = [_sample("2926", str(destination)) for destination in range(3139, 3143)]
    samples.append(_sample("2941", "3250"))
    inventory = _inventory()
    market = _market()
    engines = _engines()
    complete = build_owned_hub_research_queue(
        inventory, samples, market, engines=engines, now=NOW, max_items=200,
    )
    assert complete["total_candidates"] == 15  # 5 routes × (2 engines + 1 model)
    assert [item["hub_id"] for item in complete["items"][:6]] == [
        "2926", "2941", "2926", "2941", "2926", "2941",
    ]
    assert all(item["purchase_eligible"] is False for item in complete["items"])

    seen = []
    offset = 0
    fingerprint = None
    while True:
        page = build_owned_hub_research_queue(
            inventory, samples, market, engines=engines, now=NOW,
            offset=offset, expected_fingerprint=fingerprint, max_items=page_size,
        )
        assert page["offset"] == offset
        assert page["page_size"] == page_size
        assert page["total_candidates"] == 15
        assert page["cursor_reset"] is False
        assert page["snapshot_fingerprint"] == complete["snapshot_fingerprint"]
        assert 0 < len(page["items"]) <= page_size
        seen.extend(page["items"])
        assert page["has_more"] == (len(seen) < 15)
        if not page["has_more"]:
            assert page["next_offset"] is None
            break
        offset = page["next_offset"]
        fingerprint = page["snapshot_fingerprint"]
        assert offset == len(seen)

    assert seen == complete["items"]
    assert len({(item["hub_id"], item["destination_id"], item["model_id"],
                 item["engine_id"]) for item in seen}) == 15


def test_research_cursor_invalidates_changed_or_shrunk_snapshots():
    samples = [_sample(), _sample("2941", "3140")]
    first = build_owned_hub_research_queue(
        _inventory(), samples, _market(), now=NOW, max_items=1,
    )
    assert first["next_offset"] == 1
    next_page = build_owned_hub_research_queue(
        _inventory(), samples[::-1], _market(), now=NOW, max_items=1,
        offset=1, expected_fingerprint=first["snapshot_fingerprint"],
    )
    assert next_page["offset"] == 1
    assert next_page["cursor_reset"] is False

    changed = deepcopy(samples)
    changed[0]["y"] = 300
    refreshed = build_owned_hub_research_queue(
        _inventory(), changed, _market(), now=NOW, max_items=1,
        offset=1, expected_fingerprint=first["snapshot_fingerprint"],
    )
    assert refreshed["cursor_reset"] is True
    assert refreshed["offset"] == 0
    assert refreshed["items"][0]["observed_demand"]["y"] == 300
    assert refreshed["snapshot_fingerprint"] != first["snapshot_fingerprint"]

    for offset in (-1, "1", True):
        invalid = build_owned_hub_research_queue(
            _inventory(), samples, _market(), now=NOW, offset=offset,
            expected_fingerprint=first["snapshot_fingerprint"],
        )
        assert invalid["offset"] == 0
    after_shrink = build_owned_hub_research_queue(
        _inventory(), [_sample()], _market(), now=NOW, max_items=1,
        offset=3, expected_fingerprint=first["snapshot_fingerprint"],
    )
    assert after_shrink["offset"] == 0
    assert after_shrink["cursor_reset"] is True


def test_research_paging_returns_no_candidates_for_stale_inventory():
    report = build_owned_hub_research_queue(
        _inventory(observed_at=NOW - 4 * 86400), [_sample()], _market(),
        now=NOW, offset=3, expected_fingerprint="outdated", max_items=2,
    )
    assert report["items"] == []
    assert report["total_candidates"] == 0
    assert report["next_offset"] is None
    assert report["has_more"] is False
    assert report["cursor_reset"] is True
    assert report["purchase_eligible"] is False


def test_fractional_engine_read_timestamp_is_accepted_without_promoting_purchase():
    engines = _engines(observed_at=NOW - 0.375)
    result = build_owned_hub_research_queue(
        _inventory(), [_sample()], _market(), engines=engines, now=NOW,
    )
    assert [row["engine_id"] for row in result["items"][:2]] == ["1", "2"]
    assert all(row["evidence"]["engine"]["observed_at"] == NOW - 0.375
               for row in result["items"][:2])
    assert result["purchase_eligible"] is False
    assert all(row["purchase_eligible"] is False for row in result["items"])


def test_fractional_live_route_read_reaches_research_queue(tmp_path, monkeypatch):
    read_at = NOW + 0.375
    monkeypatch.setattr("hub_expansion.time.time", lambda: NOW + 0.875)
    monkeypatch.setattr("owned_hub_research_feed.time.time", lambda: NOW + 0.875)
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_demand("2926", [
        {"arr_id": "3139", "distance": 2000, "y": 100, "j": 20, "f": 5},
    ], observed_at=read_at) == 1
    observations = registry.demand_observations({"2926"}, now=NOW + 0.875)
    assert observations[0]["observed_at"] == read_at

    report = build_owned_hub_research_queue(_inventory(), observations, _market())
    assert report["sampled_routes"] == 1
    assert len(report["items"]) == 2
    assert report["items"][0]["evidence"]["route"]["observed_at"] == read_at
    assert report["items"][0]["purchase_eligible"] is False


@pytest.mark.parametrize("timestamp", [
    NOW + 1.5, NOW - 3 * 86400 - 0.5, float("nan"), float("inf"),
    -float("inf"), 10 ** 500, "1900000000.5", True, None,
])
def test_invalid_fractional_route_observations_cannot_enter_queue(timestamp):
    report = build_owned_hub_research_queue(
        _inventory(), [_sample(observed_at=timestamp)], _market(), now=NOW,
    )
    assert report["items"] == []
    assert report["sampled_routes"] == 0
    assert "demanda_dos_hubs_a_pesquisar" in report["blocking_reasons"]


@pytest.mark.parametrize("field", ["inventory", "market", "engine"])
def test_fractional_evidence_timestamp_is_supported_across_sources(field):
    inventory, market, engines = _inventory(), _market(), _engines()
    if field == "inventory":
        inventory["observed_at"] = NOW - 0.25
    elif field == "market":
        market["observed_at"] = NOW - 0.25
    else:
        engines["models"]["11"]["observed_at"] = NOW - 0.25
    report = build_owned_hub_research_queue(
        inventory, [_sample()], market, engines=engines, now=NOW,
    )
    assert report["sampled_routes"] == 1
    assert len(report["items"]) == 3
    assert report["blocking_reasons"] == []


def test_engine_selection_and_confirmed_model_identity_must_match_observation():
    verified = _engines()
    verified["models"]["11"].update(
        observed_model_id="11", model_detail_identity_verified=True,
    )
    result = build_owned_hub_research_queue(
        _inventory(), [_sample()], _market(), engines=verified, now=NOW,
    )
    assert result["items"][0]["engine_id"] == "1"
    assert result["items"][0]["evidence"]["engine"]["observed_model_id"] == "11"
    assert result["items"][0]["evidence"]["engine"]["selected_engine_id"] == "1"
    assert result["items"][0]["evidence"]["engine"]["model_detail_identity_verified"] is True

    for changes in (
        {"observed_model_id": None},
        {"observed_model_id": "22"},
        {"selected_engine_id": "2"},
        {"selected_engine_id": None},
        {"model_detail_identity_verified": "true"},
    ):
        corrupted = deepcopy(verified)
        corrupted["models"]["11"].update(changes)
        report = build_owned_hub_research_queue(
            _inventory(), [_sample()], _market(), engines=corrupted, now=NOW,
        )
        assert report["items"][0]["engine_id"] is None
        assert "motor_a_pesquisar" in report["items"][0]["pending"]


def test_hub_coverage_lists_owned_hubs_even_without_route_samples():
    result = build_owned_hub_research_queue(
        _inventory(), [_sample()], _market(), now=NOW,
    )
    assert result["hub_coverage"] == [
        {"hub_id": "2926", "hub_code": "XAP", "sampled_routes": 1,
         "conflicted_routes": 0, "last_attempt_at": None,
         "last_attempt_status": "unattempted",
         "last_route_observed_at": NOW, "coverage": "partial",
         "status": "pesquisa_iniciada"},
        {"hub_id": "2941", "hub_code": "GRU", "sampled_routes": 0,
         "conflicted_routes": 0, "last_attempt_at": None,
         "last_attempt_status": "unattempted",
         "last_route_observed_at": None, "coverage": "partial",
         "status": "nao_pesquisado"},
    ]
    assert result["sampled_hubs"] == 1
    assert result["sampled_routes"] == 1
    assert result["conflicted_routes"] == 0
    assert result["purchase_eligible"] is False


def test_route_samples_use_single_latest_observation_independent_of_input_order():
    older = _sample(observed_at=NOW - 120)
    older["y"] = 85
    latest = _sample(observed_at=NOW)
    latest["y"] = 130
    for rows in ([older, latest, deepcopy(latest)],
                 [deepcopy(latest), older, latest]):
        report = build_owned_hub_research_queue(
            _inventory(), rows, _market(), now=NOW,
        )
        assert report["sampled_routes"] == 1
        assert report["sampled_hubs"] == 1
        assert report["conflicted_routes"] == 0
        assert len(report["items"]) == 2  # Two models on one unique route.
        assert all(item["observed_demand"]["y"] == 130 for item in report["items"])
        assert all(item["evidence"]["route"]["observed_at"] == NOW
                   for item in report["items"])


def test_conflicting_latest_samples_are_quarantined_without_blocking_other_hubs():
    first = _sample(observed_at=NOW)
    conflict = deepcopy(first)
    conflict["j"] = 90
    other_hub = _sample("2941", "3140")
    for samples in ([first, conflict, other_hub],
                    [other_hub, conflict, first]):
        report = build_owned_hub_research_queue(
            _inventory(), samples, _market(), now=NOW,
        )
        assert report["conflicted_routes"] == 1
        assert report["sampled_routes"] == 1
        assert report["sampled_hubs"] == 1
        assert len(report["items"]) == 2
        assert {item["hub_id"] for item in report["items"]} == {"2941"}
        assert report["hub_coverage"][0]["conflicted_routes"] == 1
        assert report["hub_coverage"][0]["sampled_routes"] == 0
        assert report["hub_coverage"][1]["conflicted_routes"] == 0


@pytest.mark.parametrize("codes", [("XAP", "DTW"), ("DTW", "XAP")])
def test_conflicting_owned_hub_identity_invalidates_pending_research(codes):
    samples = [_sample(), _sample("2941", "3140")]
    baseline = build_owned_hub_research_queue(
        _inventory(), samples, _market(), now=NOW, max_items=1,
    )
    inventory = _inventory()
    inventory["hubs"] = [
        {"id": "2926", "code": code} for code in codes
    ] + [{"id": "2941", "code": "GRU"}]

    report = build_owned_hub_research_queue(
        inventory, samples, _market(), now=NOW, max_items=1,
        offset=1, expected_fingerprint=baseline["snapshot_fingerprint"],
    )
    assert "inventario_hubs_conflitante" in report["blocking_reasons"]
    assert report["items"] == []
    assert report["total_candidates"] == 0
    assert report["cursor_reset"] is True
    assert report["purchase_eligible"] is False


def test_repeated_identical_owned_hub_identity_remains_usable():
    inventory = _inventory()
    inventory["hubs"].append(deepcopy(inventory["hubs"][0]))
    report = build_owned_hub_research_queue(
        inventory, [_sample()], _market(), now=NOW,
    )
    assert report["blocking_reasons"] == []
    assert report["owned_hubs"] == 2
    assert report["sampled_routes"] == 1
    assert len(report["items"]) == 2


def test_newer_observation_resolves_previous_conflict_without_fallback():
    older = _sample(observed_at=NOW - 240)
    first = _sample(observed_at=NOW - 120)
    conflict = deepcopy(first)
    conflict["distance_km"] = 2400
    newer = _sample(observed_at=NOW)
    newer["f"] = 15
    blocked = build_owned_hub_research_queue(
        _inventory(), [older, first, conflict], _market(), now=NOW,
    )
    assert blocked["items"] == []
    assert blocked["conflicted_routes"] == 1
    assert "demanda_dos_hubs_a_pesquisar" in blocked["blocking_reasons"]

    recovered = build_owned_hub_research_queue(
        _inventory(), [conflict, newer, older, first], _market(), now=NOW,
    )
    assert recovered["conflicted_routes"] == 0
    assert recovered["sampled_routes"] == 1
    assert all(item["observed_demand"]["f"] == 15 for item in recovered["items"])


@pytest.mark.parametrize("engines", [
    _engines(observed_at=NOW - 4 * 86400),
    _engines(observed_at=NOW + 1),
    _engines(observed_at=NOW + 0.5),
    _engines(observed_at=float("nan")),
    _engines(observed_at=float("inf")),
    _engines(observed_at=10 ** 500),
    _engines(observed_at=True),
    _engines(model="B737"),
    _engines(engine_id="../../bad"),
    {},
])
def test_engine_evidence_rejected_when_stale_future_mismatched_or_invalid(engines):
    result = build_owned_hub_research_queue(
        _inventory(), [_sample()], _market(), engines=engines, now=NOW)
    assert result["items"]
    assert result["items"][0]["engine_id"] is None
    assert "motor_a_pesquisar" in result["items"][0]["pending"]
    assert result["items"][0]["evidence"]["engine"] is None


@pytest.mark.parametrize("inventory, samples, market, blocker", [
    (_inventory(observed_at=NOW - 4 * 86400), [_sample()], _market(),
     "inventario_hubs_desatualizado"),
    (_inventory(), [_sample()], _market(observed_at=NOW - 4 * 86400),
     "catalogo_aeronaves_desatualizado"),
    (_inventory(), [_sample(observed_at=NOW - 4 * 86400)], _market(),
     "demanda_dos_hubs_a_pesquisar"),
    (_inventory(), [_sample(origin="3555")], _market(),
     "demanda_dos_hubs_a_pesquisar"),
    (_inventory(), [_sample()], _market(models=[]), "modelos_a_pesquisar"),
])
def test_incomplete_inputs_never_become_eligible(inventory, samples, market, blocker):
    report = build_owned_hub_research_queue(inventory, samples, market, now=NOW)
    assert report["items"] == []
    assert blocker in report["blocking_reasons"]
    assert report["purchase_eligible"] is False


def test_out_of_direct_range_models_need_stopover_research_and_conflicting_ids_are_excluded():
    models = [
        {"id": "11", "name": "A320", "range": 1000, "price": 1000},
        {"id": "22", "name": "B737", "range": 2500, "price": 1200},
        {"id": "22", "name": "B737", "range": 3000, "price": 1400},
        {"id": "33", "name": "A380", "range": 15000, "price": 10 ** 1000},
    ]
    report = build_owned_hub_research_queue(
        _inventory(), [_sample()], _market(models=models), now=NOW)
    assert [row["model_id"] for row in report["items"]] == ["11", "33"]
    short_range, direct = report["items"]
    assert short_range["direct_range_sufficient"] is False
    assert "escala_e_trechos_a_confirmar" in short_range["pending"]
    assert short_range["purchase_eligible"] is False
    assert short_range["final_aircraft_price"] is None
    assert direct["direct_range_sufficient"] is True
    assert "escala_e_trechos_a_confirmar" not in direct["pending"]
    assert direct["catalog_price"] is None
    assert direct["final_aircraft_price"] is None


def test_missing_model_range_and_capacity_keep_pending():
    report = build_owned_hub_research_queue(
        _inventory(), [_sample()],
        _market(models=[{"id": "7", "name": "Unknown", "price": 999}]),
        now=NOW)
    item = report["items"][0]
    assert item["direct_range_sufficient"] is None
    assert "alcance_modelo_a_confirmar" in item["pending"]
    assert "capacidade_modelo_a_confirmar" in item["pending"]
    assert item["purchase_eligible"] is False


def test_demand_observations_are_fresh_and_scoped_to_owned_hubs(tmp_path, monkeypatch):
    monkeypatch.setattr("hub_expansion.time.time", lambda: NOW)
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_demand("2926", [
        {"arr_id": "3139", "distance": 2000, "y": 100, "j": 20, "f": 5}]) == 1
    assert registry.record_demand("3555", [
        {"arr_id": "3139", "distance": 1800, "y": 80, "j": 12, "f": 3}]) == 1
    observed = registry.demand_observations({"2926", "2941"}, now=NOW)
    assert len(observed) == 1
    assert observed[0] == _sample()
    observed[0]["y"] = 0
    assert registry.demand_observations({"2926"}, now=NOW)[0]["y"] == 100
    assert registry.demand_observations({"2926"}, now=NOW + 4 * 86400) == []


def test_persisted_attempts_and_conflicts_reach_research_coverage(tmp_path, monkeypatch):
    clock = [NOW + 0.875]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")

    def queue(*, now):
        research = registry.demand_research_snapshot({"2926", "2941"}, now=now)
        assert research["coverage"] == "partial"
        return build_owned_hub_research_queue(
            _inventory(), research["samples"], _market(),
            hub_progress=research["hub_progress"], now=now,
        )

    assert registry.record_demand_attempt("2926")
    attempted = queue(now=clock[0])
    assert attempted["items"] == []
    assert attempted["hub_coverage"][0]["status"] == "pesquisa_inconclusiva"
    assert attempted["hub_coverage"][0]["last_attempt_status"] == "inconclusive"
    assert attempted["hub_coverage"][0]["last_attempt_at"] == NOW
    assert attempted["hub_coverage"][1]["status"] == "nao_pesquisado"

    sample = {"arr_id": "3139", "distance": 2000, "y": 100, "j": 20, "f": 5}
    assert registry.record_demand("2926", [sample], observed_at=NOW + 0.25) == 1
    observed = queue(now=clock[0])
    assert observed["sampled_routes"] == 1
    assert observed["hub_coverage"][0]["status"] == "pesquisa_iniciada"
    assert observed["hub_coverage"][0]["last_attempt_status"] == "samples_observed"

    assert registry.record_demand("2926", [{**sample, "y": 101}],
                                  observed_at=NOW + 0.25) == 0
    conflicted = queue(now=clock[0])
    assert conflicted["sampled_routes"] == 0
    assert conflicted["conflicted_routes"] == 1
    assert conflicted["hub_coverage"][0]["status"] == "pesquisa_inconclusiva"
    assert conflicted["items"] == []

    assert registry.record_demand("2926", [sample], observed_at=NOW + 0.5) == 1
    recovered = queue(now=clock[0])
    assert recovered["sampled_routes"] == 1
    assert recovered["conflicted_routes"] == 0
    assert recovered["items"]
    assert recovered["purchase_eligible"] is False

    aged = queue(now=NOW + 4 * 86400)
    assert aged["sampled_routes"] == 0
    assert aged["hub_coverage"][0]["last_attempt_status"] == "unattempted"
    assert aged["hub_coverage"][0]["status"] == "nao_pesquisado"


def _preview_stats():
    return SimpleNamespace(mode="realista", mode_read_at=NOW - 10,
                           fuel_quote=MarketQuote(600, NOW - 5, NOW + 60),
                           co2_quote=MarketQuote(100, NOW - 5, NOW + 90))


def _preview_engines():
    engines = _engines()
    row = engines["models"]["11"]
    row.update(observed_model_id="11", model_detail_identity_verified=True)
    row["variants"].append({"engine_id": "3", "label": "Motor econômico",
                            "available": True, "selected": False, "speed": 850, "fuel": 8})
    return engines


@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("range_km,origin_ft,dest_ft,expected", [
    (2000, 6500, 6500, ("sufficient", "sufficient", "sufficient")),
    (1999, 6500, 6500, ("short", "sufficient", "sufficient")),
    (2000, 6499, 6500, ("sufficient", "short", "sufficient")),
    (2000, 6500, 6499, ("sufficient", "sufficient", "short")),
])
def test_direct_physical_screening_blocks_shortfall(external, range_km, origin_ft, dest_ft, expected):
    engines = _preview_engines()
    engines["models"]["11"]["variant_details"] = {
        "1": {"observed_at": NOW, "metrics": {"range_km": range_km, "required_runway_ft": 6500}}}
    origin, dest = ("3139", "2926") if external else ("2926", "3139")
    sample = _sample(origin, dest)
    sample["destination_runway_ft"] = dest_ft
    sample["route_detail"] = {"source": "game_route_detail", "observed_at": NOW - 870,
                              "origin_id": origin, "destination_id": dest,
                              "origin_runway_ft": origin_ft, "destination_runway_ft": dest_ft}
    kwargs = dict(engines=engines, now=NOW, operating_market_stats=_preview_stats())
    if external:
        catalog = {"origin_scope": "external_catalog", "candidate_source": "game_purchase_catalog",
                   "candidate_inventory": [{"id": origin, "code": "SBL", "observed_at": NOW}],
                   "samples": [sample]}
        page = build_external_hub_research_queue({**_inventory(), "hub_catalog_fresh": True},
                                                 catalog, _market(), **kwargs)
    else:
        page = build_owned_hub_research_queue(_inventory(), [sample], _market(), **kwargs)
    row = next(item for item in page["items"] if item["engine_id"] == "1")
    proof = row["physical_feasibility"]
    assert tuple(proof["checks"].values()) == expected
    assert proof["expires_at"] == NOW + 30
    assert proof["stopover_research_required"] == (expected[0] == "short")
    assert row["direct_range_sufficient"] == (expected[0] == "sufficient")
    assert row["direct_range_source"] == "observed_variant"
    assert ("escala_e_trechos_a_confirmar" in row["pending"]) == (expected[0] == "short")
    assert ("pista_observada_insuficiente" in row["pending"]) == ("short" in expected[1:])
    assert row["purchase_eligible"] is proof["purchase_eligible"] is proof["game_rules_verified"] is False
    assert row["daily_net_profit"] is None
    if "short" in expected:
        assert proof["status"] == "direct_shortfall"
        assert row["economics_preview"] is None
    else:
        assert proof["status"] == "direct_dimensions_sufficient"
        assert row["economics_preview"]["expires_at"] == NOW + 30


@pytest.mark.parametrize("reason", ["stale", "endpoint", "conflict", "identity", "missing"])
def test_physical_screening_never_substitutes_uncorrelated_runway_or_market_range(reason):
    engines = _preview_engines()
    engine = engines["models"]["11"]
    engine["variant_details"] = {"1": {"observed_at": NOW,
                                      "metrics": {"range_km": 2000, "required_runway_ft": 6500}}}
    sample = _sample()
    sample["destination_runway_ft"] = 6500
    sample["route_detail"] = {"source": "game_route_detail", "observed_at": NOW,
                              "origin_id": "2926", "destination_id": "3139",
                              "origin_runway_ft": 6500, "destination_runway_ft": 6500}
    if reason == "stale":
        sample["route_detail"]["observed_at"] -= 901
    elif reason == "endpoint":
        sample["route_detail"]["origin_id"] = "3139"
    elif reason == "conflict":
        sample["destination_runway_ft"] = 6400
    elif reason == "identity":
        engine.update(model_detail_identity_verified=False, observed_model_id=None)
    else:
        engine.pop("variant_details")
    page = build_owned_hub_research_queue(_inventory(), [sample], _market(), engines=engines, now=NOW)
    row = next(item for item in page["items"] if item["engine_id"] == "1")
    proof = row["physical_feasibility"]
    assert proof["status"] == "unknown"
    assert proof["checks"]["origin_runway"] == proof["checks"]["destination_runway"] == "unknown"
    assert proof["checks"]["range"] == ("unknown" if reason in ("identity", "missing") else "sufficient")
    assert row["purchase_eligible"] is False


@pytest.mark.parametrize("external", [False, True])
def test_stopover_is_exploratory_and_bound_to_the_current_engine(external):
    from owned_hub_research_feed import engine_variants
    from stopover_research import SOURCE, subject_for

    engines = _preview_engines()
    engines["models"]["11"]["variant_details"] = {
        "1": {"observed_at": NOW, "metrics": {"range_km": 1500, "required_runway_ft": 5000}},
        "3": {"observed_at": NOW, "metrics": {"range_km": 1500, "required_runway_ft": 5000}},
    }
    origin, destination = ("3139", "2926") if external else ("2926", "3139")
    sample = _sample(origin, destination)
    model = {"id": "11", "name": "A320"}
    variants, _ = engine_variants(engines, model, NOW)
    subject = subject_for(sample, model, variants[0], NOW)
    assert subject and subject["engine_id"] == "1"
    sample["stopover_research"] = [{**subject, "source": SOURCE, "observed_at": NOW,
        "stop_id": "2941", "map_direct_km": 2000, "first_km": 1200, "second_km": 1300,
        "origin_runway_ft": 6500, "destination_runway_ft": 6500, "stop_runway_ft": 7000,
        "purchase_eligible": False, "game_rules_verified": False}]

    def build(now):
        kwargs = dict(engines=engines, now=now, operating_market_stats=_preview_stats())
        if external:
            catalog = {"origin_scope": "external_catalog", "candidate_source": "game_purchase_catalog",
                       "candidate_inventory": [{"id": origin, "code": "SBL", "observed_at": NOW}],
                       "samples": [sample]}
            return build_external_hub_research_queue({**_inventory(), "hub_catalog_fresh": True},
                                                     catalog, _market(), **kwargs)
        return build_owned_hub_research_queue(_inventory(), [sample], _market(), **kwargs)

    rows = {row["engine_id"]: row for row in build(NOW)["items"]}
    assert rows["1"]["stopover_research"]["stop_id"] == "2941"
    assert "stopover_research" not in rows["3"]
    assert rows["1"]["economics_preview"] is None
    assert "escala_e_trechos_a_confirmar" in rows["1"]["pending"]
    assert rows["1"]["purchase_eligible"] is False
    assert all("stopover_research" not in row for row in build(NOW + 901)["items"])


def test_economic_preview_uses_engine_specific_inputs_and_same_seats_in_stress():
    stats, engines = _preview_stats(), _preview_engines()
    page = build_owned_hub_research_queue(_inventory(), [_sample()], _market(), engines=engines,
                                         now=NOW, operating_market_stats=stats, preview_margin=.15)
    items = {row["engine_id"]: row for row in page["items"]}
    first, second = (items[k]["economics_preview"] for k in ("1", "3"))
    assert first["source"] == "route_optimizer_what_if_v1"
    assert first["demand_basis"] == "observed_total_not_residual"
    assert first["expires_at"] == NOW + 60
    assert first["safety_margin_fraction"] == .15
    assert first["purchase_eligible"] is False
    assert first["mode"] == "realism"
    assert first["range_source"] == first["capacity_source"] == "catalog_model"
    assert items["2"]["economics_preview"] is None
    assert items[None]["economics_preview"] is None
    assert first["layouts"][0]["base"]["fuel_cost_per_day"] > second["layouts"][0]["base"]["fuel_cost_per_day"]
    for row in items.values():
        assert row["daily_net_profit"] is None
        assert row["purchase_eligible"] is False
    for row in first["layouts"]:
        assert sum(row["layout"][key] * weight for key, weight in zip(("y", "j", "f"), (1, 2, 3))) <= 180
        base, stress = row["base"], row["stress"]
        assert stress["fuel_cost_per_day"] == pytest.approx(base["fuel_cost_per_day"] * 1.2, abs=.02)
        assert base["margin_per_day"] == pytest.approx(base["revenue_per_day"] * .15, abs=.02)
        assert base["projected_contribution_per_day"] == pytest.approx(
            base["revenue_per_day"] - base["fuel_cost_per_day"] - base["co2_cost_per_day"] - base["margin_per_day"], abs=.03)
        assert stress["projected_contribution_per_day"] < base["projected_contribution_per_day"]
        for key, amount in stress["passengers_per_day"].items():
            assert amount <= row["layout"][key] * .72 * stress["departures_per_day"] + .02
    assert set(first["excluded_costs"]) == {"maintenance", "a_check", "other_recurring", "capex"}


@pytest.mark.parametrize("catalog_range", [None, 1999])
def test_preview_uses_correlated_variant_range_and_capacity_over_catalog(catalog_range):
    engines, market = _preview_engines(), _market()
    market["models"][0].update(range=catalog_range, capacity=180)
    engines["models"]["11"]["variant_details"] = {
        "1": {"observed_at": NOW, "metrics": {"range_km": 2000, "capacity_pax": 90}}}
    page = build_owned_hub_research_queue(_inventory(), [_sample()], market, engines=engines,
                                         now=NOW, operating_market_stats=_preview_stats())
    rows = {row["engine_id"]: row for row in page["items"]}
    row = rows["1"]
    preview = row["economics_preview"]
    assert row["direct_range_sufficient"] is True
    assert "escala_e_trechos_a_confirmar" not in row["pending"]
    assert "alcance_modelo_a_confirmar" not in row["pending"]
    assert preview["range_km"] == 2000
    assert preview["capacity_pax"] == 90
    assert preview["range_source"] == preview["capacity_source"] == "observed_variant"
    assert all(sum(layout["layout"][key] * weight for key, weight in
                   zip(("y", "j", "f"), (1, 2, 3))) <= 90 for layout in preview["layouts"])
    assert rows["3"]["economics_preview"] is None
    assert row["purchase_eligible"] is False and row["daily_net_profit"] is None


def test_economic_preview_uses_correlated_variant_co2_in_both_scenarios():
    engines = _preview_engines()
    def build():
        page = build_owned_hub_research_queue(_inventory(), [_sample()], _market(), engines=engines,
            now=NOW, operating_market_stats=_preview_stats())
        return {row["engine_id"]: row["economics_preview"] for row in page["items"]}

    baseline = build()
    engines["models"]["11"]["variant_details"] = {
        "1": {"observed_at": NOW, "metrics": {"co2_kg_per_pax_km": .14}},
        "3": {"observed_at": NOW, "metrics": {"co2_kg_per_pax_km": .16}},
    }
    observed = build()
    for engine_id, coefficient in (("1", .14), ("3", .16)):
        before, after = baseline[engine_id], observed[engine_id]
        assert before["co2_rate_source"] == "assumed_default"
        assert before["co2_kg_per_pax_km"] == .18
        assert after["co2_rate_source"] == "observed_variant"
        assert after["co2_kg_per_pax_km"] == coefficient
        assert after["purchase_eligible"] is False
        for original, updated in zip(before["layouts"], after["layouts"]):
            assert original["layout"] == updated["layout"]
            for scenario in ("base", "stress"):
                assert updated[scenario]["co2_cost_per_day"] == pytest.approx(
                    original[scenario]["co2_cost_per_day"] * coefficient / .18, abs=.02)
                assert updated[scenario]["fuel_cost_per_day"] == original[scenario]["fuel_cost_per_day"]


@pytest.mark.parametrize("missing", ["mode", "stale_mode", "future_mode", "fuel", "co2",
                                    "unverified_engine", "event", "occupied", "range", "capacity"])
def test_economic_preview_requires_relevant_observations(missing):
    stats, engines, market, sample = _preview_stats(), _preview_engines(), _market(), _sample()
    if missing == "mode":
        stats.mode = None
    elif missing == "stale_mode":
        stats.mode_read_at = NOW - 901
    elif missing == "future_mode":
        stats.mode_read_at = NOW + 1
    elif missing in ("fuel", "co2"):
        setattr(stats, missing + "_quote", MarketQuote(100, NOW - 120, NOW - 1))
    elif missing == "unverified_engine":
        engines = _engines()
    elif missing == "event":
        sample["event_demand_boosted"] = True
    elif missing == "occupied":
        sample["route_detail"] = {"source": "game_route_detail", "observed_at": NOW,
                                  "origin_id": "2926", "destination_id": "3139",
                                  "origin_runway_ft": 8000, "destination_runway_ft": 5000,
                                  "observed_aircraft_on_route": 1}
    elif missing == "range":
        sample["distance_km"] = 8000
    elif missing == "capacity":
        market["models"][0]["capacity"] = 180.5
    result = build_owned_hub_research_queue(_inventory(), [sample], market, engines=engines,
                                           now=NOW, operating_market_stats=stats)
    assert result["items"]
    assert all(row["economics_preview"] is None for row in result["items"])


def test_external_preview_expiry_and_margin_change_reset_only_evidence_cursor():
    inventory = {**_inventory(), "hub_catalog_fresh": True}
    external = {"origin_scope": "external_catalog", "candidate_source": "game_purchase_catalog",
                "candidate_inventory": [{"id": "3139", "code": "SBL", "observed_at": NOW}],
                "samples": [_sample("3139", "2926")]}
    stats = _preview_stats()
    def build(now, **kwargs):
        return build_external_hub_research_queue(inventory, external, _market(), now=now,
            engines=_preview_engines(), operating_market_stats=stats, max_items=1, **kwargs)
    page = build(NOW)
    assert page["items"][0]["economics_preview"]["purchase_eligible"] is False
    for refreshed in (build(NOW + 60, offset=1, expected_fingerprint=page["snapshot_fingerprint"]),
                      build(NOW, offset=1, expected_fingerprint=page["snapshot_fingerprint"], preview_margin=.2)):
        assert refreshed["cursor_reset"] is True
        assert refreshed["layout_fingerprint"] == page["layout_fingerprint"]
        assert refreshed["items"][0]["daily_net_profit"] is None
    assert build(NOW + 60)["items"][0]["economics_preview"] is None
