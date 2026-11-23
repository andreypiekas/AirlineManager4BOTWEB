"""Cached hub and aircraft observations only schedule research, never spending."""

import json

import pytest

from economy import load_market, load_market_evidence
from hub_expansion import HubExpansionRegistry
from owned_hub_research_feed import build_owned_hub_research_queue


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


def test_out_of_range_models_and_conflicting_ids_are_excluded():
    models = [
        {"id": "11", "name": "A320", "range": 1000, "price": 1000},
        {"id": "22", "name": "B737", "range": 2500, "price": 1200},
        {"id": "22", "name": "B737", "range": 3000, "price": 1400},
        {"id": "33", "name": "A380", "range": 15000, "price": 10 ** 1000},
    ]
    report = build_owned_hub_research_queue(
        _inventory(), [_sample()], _market(models=models), now=NOW)
    assert [row["model_id"] for row in report["items"]] == ["33"]
    assert report["items"][0]["catalog_price"] is None
    assert report["items"][0]["final_aircraft_price"] is None


def test_missing_model_range_and_capacity_keep_pending():
    report = build_owned_hub_research_queue(
        _inventory(), [_sample()],
        _market(models=[{"id": "7", "name": "Unknown", "price": 999}]),
        now=NOW)
    item = report["items"][0]
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
