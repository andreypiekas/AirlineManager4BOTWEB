"""Read-only financial scenarios require verified complete data."""
import json

import pytest

from hub_expansion import MAX_AGE_SECONDS, HubExpansionRegistry


def _candidate(airport_id="123", price=5000):
    return {"id": airport_id, "code": "XAP", "name": "Chapecó",
            "purchasable": True, "hub_price": price}


def _research(**overrides):
    data = {"source": "game_research", "model": "A320", "route": "XAP-GRU",
            "route_feasible": True, "demand_verified": True,
            "aircraft_price": 10000, "route_fee": 1000, "hangar_price": 0,
            "profit_per_day": 2000}
    data.update(overrides)
    return data


def test_unknown_catalog_and_invalid_input_do_not_create_recommendation(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.snapshot()["availability_pending"] is True
    assert not registry.record_catalog([{"id": "123", "hub_price": 5000}])
    assert not registry.record_catalog([_candidate("0")])
    assert registry.snapshot()["candidates"] == []


def test_full_verified_case_calculates_investment_and_payback(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    assert registry.record_research("123", _research())
    result = registry.snapshot(cash=20000, reserve=2000)
    row = result["candidates"][0]
    assert result["available_cash"] == 18000
    assert row["status"] == "viavel"
    assert row["investment"] == 16000
    assert row["payback_days"] == 8
    assert registry.snapshot(cash=15000, reserve=2000)["candidates"][0]["status"] == "saldo_insuficiente"
    assert registry.snapshot(cash=20000, reserve=2000, owned_hub_ids={"123"})["candidates"] == []


def test_missing_prices_bad_demand_and_missing_cash_are_pending(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    registry.record_catalog([_candidate(price=None)])
    registry.record_research("123", _research())
    assert registry.snapshot(cash=50000)["candidates"][0]["status"] == "dados_a_confirmar"
    registry.record_catalog([_candidate(price=5000)])
    registry.record_research("123", _research(demand_verified=False))
    assert registry.snapshot(cash=50000)["candidates"][0]["status"] == "dados_a_confirmar"
    registry.record_research("123", _research())
    assert registry.snapshot()["candidates"][0]["status"] == "dados_a_confirmar"
    assert registry.snapshot(cash=50000, now=9999999999)["candidates"][0]["status"] == "dados_a_confirmar"


def test_loss_and_partial_catalog_merge(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    registry.record_catalog([_candidate(), _candidate("456", 4000)])
    registry.record_research("123", _research(profit_per_day=-300))
    statuses = {r["id"]: r["status"] for r in registry.snapshot(cash=50000)["candidates"]}
    assert statuses == {"123": "sem_lucro", "456": "dados_a_confirmar"}
    registry.record_catalog([_candidate("789", 3000)], complete=False)
    assert len(registry.snapshot(cash=50000)["candidates"]) == 3
    registry.record_catalog([_candidate("789", 3000)], complete=True)
    assert len(registry.snapshot(cash=50000)["candidates"]) == 1


def test_partial_refresh_ages_each_candidate_independently(tmp_path, monkeypatch):
    clock = [1800000000]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    assert registry.record_research("123", _research())

    clock[0] += MAX_AGE_SECONDS + 1
    assert registry.record_catalog([_candidate("456", 3000)], complete=False)
    assert registry.record_research("123", _research())
    assert registry.record_research("456", _research())

    snapshot = registry.snapshot(cash=50000, now=clock[0])
    rows = {row["id"]: row for row in snapshot["candidates"]}
    assert snapshot["observed_at"] == clock[0]
    assert snapshot["catalog_complete"] is False
    assert rows["123"]["observed_at"] == clock[0] - MAX_AGE_SECONDS - 1
    assert rows["123"]["status"] == "dados_a_confirmar"
    assert rows["456"]["observed_at"] == clock[0]
    assert rows["456"]["status"] == "viavel"

    assert registry.record_catalog([_candidate("123", 6000)], complete=False)
    refreshed = {row["id"]: row for row in registry.snapshot(cash=50000, now=clock[0])["candidates"]}
    assert refreshed["123"]["observed_at"] == clock[0]
    assert refreshed["123"]["investment"] == 17000
    assert refreshed["123"]["status"] == "viavel"
    assert refreshed["456"]["observed_at"] == clock[0]


def test_legacy_catalog_timestamp_survives_partial_merge(tmp_path, monkeypatch):
    clock = [1800000000]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    assert registry.record_research("123", _research())

    legacy = json.loads(registry.path.read_text(encoding="utf-8"))
    del legacy["candidates"][0]["observed_at"]
    registry.path.write_text(json.dumps(legacy), encoding="utf-8")
    assert registry.snapshot(cash=50000, now=clock[0])["candidates"][0]["status"] == "viavel"
    assert registry.snapshot(cash=50000, now=clock[0])["candidates"][0]["observed_at"] == clock[0]

    clock[0] += MAX_AGE_SECONDS + 1
    assert registry.record_catalog([_candidate("456")], complete=False)
    assert registry.record_research("123", _research())
    rows = {row["id"]: row for row in registry.snapshot(cash=50000, now=clock[0])["candidates"]}
    assert rows["123"]["observed_at"] == legacy["observed_at"]
    assert rows["123"]["status"] == "dados_a_confirmar"
    assert rows["456"]["observed_at"] == clock[0]
    persisted = json.loads(registry.path.read_text(encoding="utf-8"))
    assert {row["id"]: row["observed_at"] for row in persisted["candidates"]} == {
        "123": legacy["observed_at"], "456": clock[0]}


def test_complete_refresh_discards_unseen_and_updates_seen_candidate(tmp_path, monkeypatch):
    clock = [1800000000]
    monkeypatch.setattr("hub_expansion.time.time", lambda: clock[0])
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate(), _candidate("456")])
    assert registry.record_research("456", _research())

    clock[0] += MAX_AGE_SECONDS + 1
    assert registry.record_catalog([_candidate("456", 7000)], complete=True)
    snapshot = registry.snapshot(cash=50000, now=clock[0])
    assert snapshot["catalog_complete"] is True
    assert len(snapshot["candidates"]) == 1
    row = snapshot["candidates"][0]
    assert row["id"] == "456"
    assert row["observed_at"] == clock[0]
    assert row["hub_price"] == 7000
    assert row["scenario"]["observed_at"] == clock[0] - MAX_AGE_SECONDS - 1
    assert row["status"] == "dados_a_confirmar"

    assert registry.record_research("456", _research())
    assert registry.snapshot(cash=50000, now=clock[0])["candidates"][0]["status"] == "viavel"


def test_conflicting_catalog_duplicates_cannot_replace_verified_evidence(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    original = registry.path.read_bytes()

    assert not registry.record_catalog([_candidate(price=8000), _candidate(price=9000)], complete=True)
    assert registry.path.read_bytes() == original

    assert registry.record_catalog([_candidate(price=8000), _candidate(price=8000)])
    rows = registry.snapshot(cash=50000)["candidates"]
    assert len(rows) == 1
    assert rows[0]["hub_price"] == 8000


def test_partial_catalog_cannot_be_mistaken_for_complete_scan(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate(), _candidate("456")], complete=True)

    # A malformed purchasable option means this is not a proven complete scan.
    assert registry.record_catalog([_candidate("789"), {"id": "INVALID", "purchasable": True}],
                                   complete=True)
    snapshot = registry.snapshot()
    assert {row["id"] for row in snapshot["candidates"]} == {"123", "456", "789"}
    assert snapshot["catalog_complete"] is False

    # Legacy callers must pass the literal boolean True to prune unseen rows.
    assert registry.record_catalog([_candidate("789")], complete="false")
    assert len(registry.snapshot()["candidates"]) == 3


def test_legacy_candidate_types_are_sanitized_and_merged(tmp_path, monkeypatch):
    monkeypatch.setattr("hub_expansion.time.time", lambda: 1800000000)
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    registry.path.write_text(json.dumps({
        "source": "game_purchase_catalog", "observed_at": 1800000000,
        "candidates": [None, "broken", {"id": {"malformed": True}},
                       {"id": 123, "name": 123, "code": ["XAP"], "hub_price": "5000",
                        "scenario": {"source": "game_research", "observed_at": 1800000000,
                                     **{k: v for k, v in _research().items() if k != "source"}}}],
    }), encoding="utf-8")

    rows = registry.snapshot(cash=50000, now=1800000000)["candidates"]
    assert len(rows) == 1
    assert rows[0]["id"] == "123"
    assert isinstance(rows[0]["code"], str)
    assert rows[0]["status"] == "viavel"

    assert registry.record_research("123", _research())
    assert registry.record_catalog([_candidate("456")], complete=False)
    merged = registry.snapshot(cash=50000, now=1800000000)
    assert {row["id"] for row in merged["candidates"]} == {"123", "456"}
    assert next(row for row in merged["candidates"] if row["id"] == "123")["status"] == "viavel"

    registry.path.write_text(json.dumps({"candidates": None}), encoding="utf-8")
    assert registry.snapshot()["availability_pending"] is True
    assert not registry.record_research("123", _research())
    assert registry.record_catalog([_candidate()])


def test_legacy_boolean_research_timestamp_is_not_fresh(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    registry.path.write_text(json.dumps({
        "observed_at": 1, "source": "game_purchase_catalog",
        "candidates": [{"id": "123", "name": "Chapecó", "code": "XAP", "hub_price": 5000,
                        "observed_at": 1,
                        "scenario": {"observed_at": True, **_research()}}],
    }), encoding="utf-8")
    assert registry.snapshot(cash=50000, now=1)["candidates"][0]["status"] == "dados_a_confirmar"


def test_lower_investment_breaks_equal_daily_profit_tie(tmp_path):
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate("123", 9000), _candidate("456", 1000)])
    assert registry.record_research("123", _research())
    assert registry.record_research("456", _research())
    rows = registry.snapshot(cash=50000)["candidates"]
    assert [row["id"] for row in rows] == ["456", "123"]
    assert rows[0]["payback_days"] < rows[1]["payback_days"]


@pytest.mark.parametrize("invalid_timestamp", [None, True, "1800000000", 1800000001])
def test_invalid_or_future_candidate_timestamp_is_not_fresh(tmp_path, monkeypatch, invalid_timestamp):
    monkeypatch.setattr("hub_expansion.time.time", lambda: 1800000000)
    registry = HubExpansionRegistry(tmp_path / "expansion.json")
    assert registry.record_catalog([_candidate()])
    assert registry.record_research("123", _research())
    saved = json.loads(registry.path.read_text(encoding="utf-8"))
    saved["candidates"][0]["observed_at"] = invalid_timestamp
    registry.path.write_text(json.dumps(saved), encoding="utf-8")
    row = registry.snapshot(cash=50000, now=1800000000)["candidates"][0]
    assert row["observed_at"] == invalid_timestamp
    assert row["status"] == "dados_a_confirmar"


def test_expansion_dashboard_is_only_a_get_endpoint():
    from conftest import ROOT
    page = (ROOT / "assets/web/index.html").read_text(encoding="utf-8")
    web = (ROOT / "src/web.py").read_text(encoding="utf-8")
    assert 'api("/api/hubs/expansion")' in page
    assert 'url.path == "/api/hubs/expansion"' in web
    assert 'id="hubExpansionGrid"' in page
