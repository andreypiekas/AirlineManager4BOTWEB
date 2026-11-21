from types import SimpleNamespace

import pytest

import fleet
import route_registry
from route_registry import RouteRegistry, endpoint


@pytest.mark.parametrize(
    "maintenance,status,empty,archive",
    [
        (["22356162"], ["22356162"], True, True),
        (["22356162"], [], True, False),
        ([], ["22356162"], True, False),
        (["22356162", "22751922"], ["22356162"], True, False),
        (["22356162"], ["22356162", "22751922"], True, False),
        (["22356162"], ["22356162"], False, False),
    ],
)
def test_archive_duplicate_only_after_live_absence_is_corroborated(
    tmp_path, monkeypatch, maintenance, status, empty, archive,
):
    registry = RouteRegistry(tmp_path / "routes.json")
    with monkeypatch.context() as stale:
        stale.setattr(route_registry.time, "time", lambda: 100)
        for aircraft_id in ("22356162", "22751922"):
            registry.record(aircraft_id, aircraft_id, "A340", endpoint(code="DTW"), endpoint(code="ULN"))
    monkeypatch.setattr(route_registry.time, "time", lambda: 400)
    monkeypatch.setattr(fleet, "aircraft_details_missing", lambda bot, aircraft_id: empty)
    bot = SimpleNamespace(
        recent_fleet=lambda max_age: [SimpleNamespace(id=aircraft_id) for aircraft_id in maintenance],
        js=lambda script: status,
        stopping=False,
    )

    fleet.reconcile_missing_duplicate_aircraft(bot, registry)

    report = registry.snapshot()
    assert report["duplicate_routes"] == (0 if archive else 1)
    if archive:
        assert [row["aircraft_id"] for row in report["relations"]] == ["22356162"]
        assert report["history"][0]["action"] == "aeronave_fora_da_frota"
        assert report["history"][0]["aircraft_id"] == "22751922"
