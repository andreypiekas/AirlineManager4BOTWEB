"""Rolling coverage of the changing, partially visible game route list."""

import json
import shutil
import subprocess

import pytest

import route_registry
from fleet import _ROUTE_AUDIT_JS, audit_routes, audit_routes_rolling
from route_registry import RouteRegistry
from route_registry import endpoint


def _row(aircraft_id, page=1, total_pages=4, destination="GRU"):
    return {
        "aircraft_id": str(aircraft_id),
        "registration": f"PP-{aircraft_id}",
        "model": "A320",
        "origin_code": "XAP",
        "destination_code": destination,
        "scan_page": page,
        "scan_total_pages": total_pages,
    }


class ChangingPageBot:
    def __init__(self, pages):
        self.pages = pages
        self.current_page = 1
        self.visited = []

    def js(self, _script):
        return [_row(aircraft_id, page=self.current_page, total_pages=len(self.pages))
                for aircraft_id in self.pages[self.current_page]]

    def load_page(self, page):
        self.current_page = page
        self.visited.append(page)
        return True


def test_scan_tracks_unique_aircraft_across_bounded_rolling_pages(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    bot = ChangingPageBot({1: [101, 102], 2: [102, 103], 3: [104], 4: [105]})

    assert audit_routes(bot, registry) is True  # existing fast one-page path
    first = registry.snapshot()
    assert first["scan_coverage"]["observed_pages"] == 1
    assert first["scan_coverage"]["unique_aircraft"] == 2
    assert first["scan_coverage"]["partial"] is True
    assert first["partial"] is True

    assert audit_routes_rolling(bot, registry, total_pages=4,
                                load_page=bot.load_page, pages_per_cycle=2) == [2, 3]
    second = RouteRegistry(registry.path).snapshot()
    assert second["scan_coverage"]["observed_pages"] == 3
    assert second["scan_coverage"]["unique_aircraft"] == 4

    assert audit_routes_rolling(bot, registry, total_pages=4,
                                load_page=bot.load_page, pages_per_cycle=2) == [4, 1]
    final = registry.snapshot()
    assert final["scan_coverage"]["observed_pages"] == 4
    assert final["scan_coverage"]["total_pages"] == 4
    assert final["scan_coverage"]["unique_aircraft"] == 5
    assert final["total"] == 5
    assert {row["aircraft_id"] for row in final["relations"]} == {
        "101", "102", "103", "104", "105",
    }
    assert bot.visited == [2, 3, 4, 1]


def test_arrivals_change_page_positions_without_pruning_known_aircraft(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    bot = ChangingPageBot({1: [101], 2: [102, 103]})
    audit_routes(bot, registry)
    assert audit_routes_rolling(bot, registry, total_pages=2,
                                load_page=bot.load_page, pages_per_cycle=2) == [2, 1]

    # A newly arrived aircraft shifts the visible positions of older rows.
    bot.pages[1] = [104, 101]
    bot.pages[2] = [102]
    assert audit_routes_rolling(bot, registry, total_pages=2,
                                load_page=bot.load_page, pages_per_cycle=2) == [2, 1]
    report = registry.snapshot()
    assert report["total"] == 4
    assert {r["aircraft_id"] for r in report["relations"]} == {
        "101", "102", "103", "104",
    }
    # Coverage describes the latest observed pages, not the entire known roster.
    assert report["scan_coverage"]["unique_aircraft"] == 3
    assert report["scan_coverage"]["partial"] is True


def test_page_mismatch_is_ignored_without_changing_routes(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    bot = ChangingPageBot({1: [101], 2: [202]})

    def incorrect_loader(_page):
        bot.current_page = 2
        return True

    # Requested page 1, but the game's active pager still shows page 2.
    assert audit_routes_rolling(bot, registry, total_pages=2,
                                load_page=incorrect_loader) == []
    assert registry.snapshot()["total"] == 0
    assert registry.snapshot()["last_scan"] is None


def test_empty_or_inconsistent_page_is_not_counted_as_rolling_coverage(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")

    class Bot:
        rows = []

        def js(self, _script):
            return self.rows

    bot = Bot()
    assert audit_routes_rolling(bot, registry, total_pages=2,
                                load_page=lambda _: True) == []
    assert registry.snapshot()["scan_coverage"] is None

    bot.rows = [_row(101, page=1), _row(102, page=2)]
    assert audit_routes(bot, registry) is False
    assert registry.snapshot()["total"] == 0


def test_rolling_audit_requires_explicit_page_and_total_evidence(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")

    class Bot:
        def __init__(self, row):
            self.row = row

        def js(self, _script):
            return [self.row]

    for missing_field in ("scan_page", "scan_total_pages"):
        row = _row(101, page=1, total_pages=2)
        row[missing_field] = None
        assert audit_routes_rolling(Bot(row), registry, total_pages=2,
                                    load_page=lambda _page: True) == []
        assert registry.snapshot()["total"] == 0
        assert registry.snapshot()["scan_coverage"] is None


def test_audit_persists_complete_page_in_one_atomic_write(tmp_path, monkeypatch):
    registry = RouteRegistry(tmp_path / "routes.json")
    assert registry.record("101", "PP-101", "A320", endpoint(code="XAP"),
                           endpoint(code="GRU"), profit_per_day=125)

    writes = []
    original_save = registry._save

    def capture_save(data):
        writes.append(data["last_scan"].copy())
        original_save(data)

    monkeypatch.setattr(registry, "_save", capture_save)

    class Bot:
        def js(self, _script):
            unverified = _row(102, destination="")
            unverified["origin_code"] = ""
            return [_row(101, destination="FLN"), unverified, _row(101, destination="FLN")]

    assert audit_routes(Bot(), registry)
    assert len(writes) == 1
    assert {key: writes[0][key] for key in ("visible", "identified", "missing_airports")} == {
        "visible": 3, "identified": 1, "missing_airports": 1,
    }

    snapshot = registry.snapshot()
    assert snapshot["total"] == 2
    assert snapshot["scan_coverage"]["unique_aircraft"] == 2
    aircraft = {row["aircraft_id"]: row for row in snapshot["relations"]}
    assert aircraft["101"]["destination"]["code"] == "FLN"
    assert "profit_per_day" not in aircraft["101"]
    assert aircraft["102"]["status"] == "rota_nao_identificada"
    assert sum(item["action"] == "rota_alterada" for item in snapshot["history"]) == 1


def test_duplicate_ids_on_one_page_only_record_once(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")

    class Bot:
        def js(self, _script):
            return [_row(101), _row(101), _row(102)]

    assert audit_routes(Bot(), registry)
    report = registry.snapshot()
    assert report["last_scan"]["visible"] == 3
    assert report["last_scan"]["identified"] == 2
    assert report["scan_coverage"]["unique_aircraft"] == 2
    assert report["total"] == 2


def test_invalid_ids_and_excessive_page_counts_do_not_expand_coverage(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.record_scan(3, 0, 3, aircraft_ids=["100", "100", "registration", "x"],
                         page=1, total_pages=4)
    assert registry.snapshot()["scan_coverage"]["unique_aircraft"] == 1
    assert registry.next_scan_pages(1000) == []
    assert registry.next_scan_pages(4, limit=0) == []
    assert registry.next_scan_pages(100, limit=999) == [1, 2, 3, 4, 5]


def test_game_dom_pagination_is_read_with_the_route_rows(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js is required to validate the embedded route-page JavaScript")
    game_dom = """
const link = {
  textContent: "PP-101 - A320",
  getAttribute: name => name === "onclick" ?
    "Ajax('fleet_details.php?id=101', 'detailsAction')" : null
};
const routeLabel = {textContent: "XAP - GRU", getAttribute: () => null};
const row = {
  querySelector: selector => selector.includes("fleet_details.php") || selector === "a" ?
    link : selector === ".col-10 .s-text" ? routeLabel : null,
  querySelectorAll: () => [],
  getAttribute: () => null
};
const pagination = {
  getAttribute: name => name === "data-total-pages" ? "4" : null,
  querySelector: selector => selector.includes("active") ? {textContent: "2"} : null
};
const popup = {
  querySelector: selector => selector === ".pagination" ? pagination : null,
  getAttribute: () => null
};
globalThis.document = {
  querySelector: selector => selector === "#popContent" ? popup : null,
  querySelectorAll: selector => selector.includes("routeMainList") ? [row] : []
};
"""
    js = tmp_path / "game_dom.js"
    js.write_text(game_dom + "\nconsole.log(JSON.stringify((new Function(" +
                  json.dumps(_ROUTE_AUDIT_JS) + "))()));\n", encoding="utf-8")
    result = subprocess.run(["node", str(js)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)
    assert len(rows) == 1
    assert rows[0]["aircraft_id"] == "101"
    assert rows[0]["scan_page"] == 2
    assert rows[0]["scan_total_pages"] == 4


def test_stale_pages_and_changed_pagination_reset_coverage(tmp_path, monkeypatch):
    registry = RouteRegistry(tmp_path / "routes.json")
    clock = {"at": 100}
    monkeypatch.setattr(route_registry.time, "time", lambda: clock["at"])
    registry.record_scan(1, 1, 0, aircraft_ids=["101"], page=1, total_pages=2)
    clock["at"] += 10
    registry.record_scan(1, 1, 0, aircraft_ids=["102"], page=2, total_pages=2)
    assert registry.snapshot()["scan_coverage"]["unique_aircraft"] == 2

    clock["at"] += 10
    registry.record_scan(1, 1, 0, aircraft_ids=["103"], page=1, total_pages=3)
    changed = registry.snapshot()["scan_coverage"]
    assert changed["total_pages"] == 3
    assert changed["observed_pages"] == 1
    assert changed["unique_aircraft"] == 1

    clock["at"] += 3601
    registry.record_scan(1, 1, 0, aircraft_ids=["104"], page=2, total_pages=3)
    expired = registry.snapshot()["scan_coverage"]
    assert expired["observed_pages"] == 1
    assert expired["unique_aircraft"] == 1
