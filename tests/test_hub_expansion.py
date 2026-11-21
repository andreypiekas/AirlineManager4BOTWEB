"""Read-only financial scenarios require verified complete data."""
from hub_expansion import HubExpansionRegistry


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


def test_expansion_dashboard_is_only_a_get_endpoint():
    from conftest import ROOT
    page = (ROOT / "assets/web/index.html").read_text(encoding="utf-8")
    web = (ROOT / "src/web.py").read_text(encoding="utf-8")
    assert 'api("/api/hubs/expansion")' in page
    assert 'url.path == "/api/hubs/expansion"' in web
    assert 'id="hubExpansionGrid"' in page
