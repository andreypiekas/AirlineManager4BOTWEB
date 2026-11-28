import csv
import importlib.util
import io
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest


@pytest.fixture
def audit(monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("audit_live_demand", scripts / "audit_live_demand.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def snapshot():
    return {
        "source": "game_snapshot",
        "verified": True,
        "hubs": [{"id": "1440", "code": "LAX", "owned": True, "verified": True}],
        "observations": {"route_search_universe": {
            "source": "game_owned_route_search_menus",
            "country_values_by_origin": {"1440": ["Tunisia", "United States"]},
            "destination_catalog": {
                "source": "game_route_arrival_selectors_and_map",
                "airport_ids_by_country": {"United States": ["1440"], "Tunisia": ["432"]},
                "airport_count": 2, "owned_origin_destination_pairs": 1,
            },
        }},
    }


def response(*rows, quota=499):
    return {"status": {"request": "success", "requests_remaining": quota}, "route": {"data": list(rows)}}


def tunis(**changes):
    return {"icao": "DTTA", "iata": "TUN", "economy_class_demand": 1341, "business_class_demand": 514,
            "first_class_demand": 0, **changes}


def test_exports_valid_pairs_and_keeps_execution_disabled(audit, snapshot):
    output = io.StringIO()

    def fetch(icao, deadline):
        assert icao == "KLAX"
        assert deadline > time.monotonic()
        return response(tunis())

    result = audit.collect(snapshot, [], fetch, started=time.monotonic(), seconds=900, writer=csv.writer(output))
    assert result["owned_pairs"] == result["owned_expected_pairs"] == 1
    assert result["requests"] == 1
    assert result["requested_scope_complete"]
    assert result["within_budget"]
    assert not result["verified"]
    assert not result["execution_available"]
    assert not result["residual_today_available"]
    assert list(csv.reader(io.StringIO(output.getvalue()))) == [["1440", "432", "1341", "514", "0"]]


@pytest.mark.parametrize("rows", [
    (tunis(), tunis()),
    (tunis(iata="SFA"),),
    (tunis(economy_class_demand=True),),
    (tunis(first_class_demand=None),),
    (),
])
def test_incomplete_or_ambiguous_demand_does_not_close_scope(audit, snapshot, rows):
    result = audit.collect(snapshot, [], lambda *_: response(*rows), started=time.monotonic(), seconds=900)
    assert result["owned_pairs"] == 0
    assert result["owned_expected_pairs"] == 1
    assert not result["requested_scope_complete"]


def test_quota_stops_before_unqueried_external_origin(audit, snapshot):
    result = audit.collect(snapshot, ["DTTA"], lambda *_: response(tunis(), quota=0),
                           started=time.monotonic(), seconds=900)
    assert result["requests"] == result["unqueried_origins"] == 1
    assert result["external_pairs"] == 0
    assert result["external_expected_pairs"] == 1
    assert not result["requested_scope_complete"]


def test_expired_clock_sends_no_request(audit, snapshot):
    def fetch(*_):
        pytest.fail("request after deadline")

    result = audit.collect(snapshot, [], fetch, started=time.monotonic() - 2, seconds=1)
    assert result["requests"] == 0
    assert not result["within_budget"]
    assert not result["requested_scope_complete"]


def test_verified_origin_and_airport_codes_are_required(audit, snapshot):
    snapshot["hubs"][0]["code"] = "JFK"
    catalog = snapshot["observations"]["route_search_universe"]["destination_catalog"]
    catalog["airport_ids_by_country"]["Spain"] = ["999999999"]
    catalog.update(airport_count=3, owned_origin_destination_pairs=2)

    def fetch(*_):
        pytest.fail("request for unverified origin")

    result = audit.collect(snapshot, [], fetch, started=time.monotonic(), seconds=900)
    assert result["origin_errors"] == {1440: "origin_code_unverified"}
    assert result["unmapped_airport_ids"] == [999999999]
    assert not result["requested_scope_complete"]


def test_fetch_uses_documented_research_query(audit):
    class FakeOpener:
        def open(self, url, *, timeout):
            url = urlsplit(url)
            assert (url.scheme, url.hostname, url.path) == ("https", "www.airlinemanager.com", "/api")
            assert parse_qs(url.query) == {
                "access_token": ["fake-token&"], "fields": ["research"], "dep_icao": ["KLAX"],
                "min_runway": ["0"], "max_distance": ["21000"],
            }
            assert 0 < timeout <= 8
            return io.BytesIO(b'{"status":{"request":"success"}}')

    assert audit.request_research(FakeOpener(), "fake-token&", "KLAX", time.monotonic() + 1) == {
        "status": {"request": "success"},
    }
