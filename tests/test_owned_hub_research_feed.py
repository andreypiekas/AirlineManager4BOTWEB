"""Cached hub and aircraft observations only schedule research, never spending."""

import json
from copy import deepcopy

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
         "conflicted_routes": 0,
         "last_route_observed_at": NOW, "coverage": "partial",
         "status": "pesquisa_iniciada"},
        {"hub_id": "2941", "hub_code": "GRU", "sampled_routes": 0,
         "conflicted_routes": 0,
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
