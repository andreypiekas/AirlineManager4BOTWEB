import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

from native_demand_scan import prepare_requested_scan, run_demand_slice
from native_demand_store import DemandStore, demand_catalog


UNIVERSE = {
    "origin_ids": ["11"],
    "country_values_by_origin": {"11": ["Brazil", "Tunisia"]},
    "destination_catalog": {"map_airport_ids": ["11", "22", "33", "44"],
                            "airport_ids_by_country": {"Brazil": ["11", "22"], "Tunisia": ["33", "44"]}},
}


def result(job, rows):
    origin, country, destination = job
    return {"origin_id": origin, "country": country, "destination_id": destination, "rows": rows}


def row(airport, y=120):
    return {"destination_id": airport, "y": y, "j": 10, "f": 0, "event_demand_boosted": True}


def test_native_demand_requires_request_and_resolves_bulk_omissions_after_restart(tmp_path):
    path = tmp_path / "demand.db"
    store = DemandStore(path)
    assert store.status()["state"] == "pending"
    assert store.pending_work() is None
    assert not path.exists()
    with sqlite3.connect(path):
        pass
    assert store.status()["state"] == "pending"
    assert store.lookup("11", "22") is None

    assert store.request()
    assert store.pending_work() == "catalog"
    assert not store.request()
    assert store.begin("123", demand_catalog(UNIVERSE))
    assert store.pending_work() == "batch"
    brazil, tunisia = jobs = store.jobs(10)
    store.save(jobs, [result(brazil, [row("22")]), result(tunisia, [row("33")])])
    store = DemandStore(path)
    assert store.begin("123", None)
    assert store.status()["observed_pairs"] == 2
    assert store.status()["expected_pairs"] == 3
    assert store.lookup("11", "44") is None
    exact = ("11", "Tunisia", "44")
    assert store.jobs(10) == [exact]
    store.save([exact], [result(exact, [])])
    assert store.status()["state"] == "completed"
    assert store.status()["searched_pairs"] == 3
    assert store.status()["observed_pairs"] == 2
    assert store.pending_work() is None
    assert store.lookup("11", "44") is None
    assert store.lookup("11", "22")["source"] == "game_route_search"
    assert store.lookup("11", "33")["event_demand_boosted"] is True


def test_invalid_batch_is_resumable_and_cannot_mix_companies(tmp_path):
    store = DemandStore(tmp_path / "demand.db")
    assert store.request() and store.begin("123", demand_catalog(UNIVERSE))
    brazil, tunisia = jobs = store.jobs(10)
    store.save(jobs, [result(brazil, [row("33")]), result(tunisia, [row("44", y=-1)])])
    assert store.status()["state"] == "partial"
    assert store.status()["observed_pairs"] == 0
    assert store.request()
    assert not store.begin("321", None)
    assert store.status()["state"] == "partial"
    assert store.request() and store.begin("123", None)
    assert store.jobs(10) == jobs


def test_catalog_needs_exact_origins_and_destination_union():
    assert demand_catalog(UNIVERSE) == (("11",), UNIVERSE["destination_catalog"]["airport_ids_by_country"])
    assert demand_catalog({**UNIVERSE, "origin_ids": ["11", "22"]}) is None
    assert demand_catalog({**UNIVERSE, "country_values_by_origin": {"11": ["Brazil"]}}) is None
    assert demand_catalog({**UNIVERSE, "destination_catalog": {
        **UNIVERSE["destination_catalog"], "map_airport_ids": ["11", "22"],
    }}) is None


def test_worker_requires_consent_and_discards_batch_when_company_changed(tmp_path, monkeypatch):
    store = DemandStore(tmp_path / "demand.db")
    monkeypatch.setattr("native_demand_scan.DemandStore", lambda: store)
    worker = SimpleNamespace(stopping=False, _observation_company_id="123",
                             _require_observation_session=Mock(), _verify_observation_company=Mock())
    prepare_requested_scan(worker, UNIVERSE)
    worker._require_observation_session.assert_not_called()
    assert store.request()
    prepare_requested_scan(worker, UNIVERSE)

    def read(owner, jobs):
        owner._observation_company_id = "456"
        return [result(jobs[0], [row("22")])]

    monkeypatch.setattr("native_demand_scan.read_demand_batch", read)
    run_demand_slice(worker, store)
    assert store.status()["state"] == "partial"
    assert store.lookup("11", "22") is None
