"""Read-only AM4 route pagination, using the observed routes.php AJAX contract."""

import json
import re
import shutil
import subprocess

import pytest

from fleet import (_ROUTE_AUDIT_JS, _ROUTES_PAGER_LINKS_JS,
                   audit_routes, audit_routes_live_pages)
from route_registry import RouteRegistry


@pytest.mark.parametrize(
    ("page", "visible", "actions", "expected_offsets", "has_next"),
    [
        (1, 17, ["Ajax('routes.php?start=20&sort=','routeAction',this);"], [20], True),
        (2, 20, ["Ajax('routes.php?start=0&sort=','routeAction',this);",
                 "Ajax('routes.php?start=40&sort=','routeAction',this);"], [0, 40], True),
        (12, 1, ["Ajax('routes.php?start=200&sort=','routeAction',this);"], [200], False),
    ],
)
def test_real_am4_dom_page_identity_and_ajax_links(tmp_path, page, visible,
                                                    actions, expected_offsets, has_next):
    if not shutil.which("node"):
        pytest.skip("Node.js required to execute the AM4 DOM adapters")

    fixture = """
const page = PAGE;
const detailLink = id => ({
  textContent: `PP-${id} - A320`,
  getAttribute: name => name === 'onclick' ?
    `Ajax('fleet_details.php?id=${id}', 'detailsAction')` : null
});
const row = id => ({
  querySelector: selector => selector.includes('fleet_details.php') || selector === 'a' ?
    detailLink(id) : selector === '.col-10 .s-text' ?
    {textContent: 'XAP - GRU', getAttribute: () => null} : null,
  querySelectorAll: () => [],
  getAttribute: () => null
});
const pager = {
  getAttribute: () => null,
  querySelector: selector => selector.includes('.page-item.not-active > .page-link') ?
    {textContent: String(page)} : null,
  querySelectorAll: () => [
    ...(page === 1 ? [] : [{textContent: 'Previous'}]),
    {textContent: String(page)},
    ...(NEXT ? [{textContent: 'Next'}] : [])
  ]
};
const popup = {
  querySelector: selector => selector === '.pagination' ? pager : null,
  getAttribute: () => null
};
const actions = ACTIONS.map(action => ({getAttribute: () => action}));
globalThis.document = {
  querySelector: selector => selector === '#popContent' ? popup : null,
  querySelectorAll: selector => selector.includes('routeMainList') ?
    Array.from({length: VISIBLE}, (_, index) => row(24000000 + page * 100 + index)) :
    selector.includes('.pagination [onclick]') ? actions :
    selector.includes('.row.font-weight-bold') ? [{textContent: '218 Routes'}] : []
};
"""
    fixture = fixture.replace("PAGE", str(page)).replace("VISIBLE", str(visible))
    fixture = fixture.replace("ACTIONS", json.dumps(actions)).replace("NEXT", json.dumps(has_next))
    fixture += ("\nconsole.log(JSON.stringify({rows: (new Function(" +
                json.dumps(_ROUTE_AUDIT_JS) + "))(), links: (new Function(" +
                json.dumps(_ROUTES_PAGER_LINKS_JS) + "))()}));\n")
    path = tmp_path / "am4_live_pager.js"
    path.write_text(fixture, encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True,
                            text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    snapshot = json.loads(result.stdout)
    assert len(snapshot["rows"]) == visible
    assert all(row["scan_page"] == page and row["scan_total_pages"] is None
               and row["scan_has_next"] is has_next for row in snapshot["rows"])
    assert all(row["aircraft_id"].isdigit() for row in snapshot["rows"])
    assert all(not row["home_hub_id"] for row in snapshot["rows"])
    assert [link["offset"] for link in snapshot["links"]] == expected_offsets
    assert all(link["target"] == "routeAction" and "&sort=" in link["url"]
               for link in snapshot["links"])


def test_real_pager_rejects_unrecognized_ajax_targets(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js required to execute the pager adapter")
    handlers = [
        "Ajax('routes.php?start=20&sort=','unknownTarget',this);",
        "Ajax('routes.php?start=20','routeAction',this);",
        "Ajax('bad.php?start=20&sort=','routeAction',this);",
        "Ajax('routes.php?start=20&sort=','routeAction',this);",
    ]
    fixture = "globalThis.document = {querySelectorAll: () => " + json.dumps(handlers)
    fixture += ".map(action => ({getAttribute: () => action}))};\n"
    fixture += "console.log(JSON.stringify((new Function(" + json.dumps(_ROUTES_PAGER_LINKS_JS) + "))()));\n"
    script = tmp_path / "pager_allowlist.js"
    script.write_text(fixture, encoding="utf-8")
    result = subprocess.run(["node", str(script)], capture_output=True,
                            text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [{
        "offset": 20, "target": "routeAction", "url": "routes.php?start=20&sort="
    }]


class LiveRoutesBot:
    stopping = False

    def __init__(self, *, initial_page=1, total_pages=11, fail_after_ajax=None,
                 change_total_after_ajax=None, wrong_page_after_ajax=None,
                 page_counts=None, native_pager=False):
        self.page = initial_page
        self.total_pages = total_pages
        self.fail_after_ajax = fail_after_ajax
        self.change_total_after_ajax = change_total_after_ajax
        self.wrong_page_after_ajax = wrong_page_after_ajax
        self.native_pager = native_pager
        self.page_counts = page_counts if page_counts is not None else {
            1: 14, 11: 3,
        }
        self.navigations = []
        self.failures = 0

    def js(self, script):
        if script == _ROUTES_PAGER_LINKS_JS:
            return [{"offset": (other - 1) * 20,
                     "url": f"routes.php?start={(other - 1) * 20}&sort=",
                     "target": "routeAction"}
                    for other in (self.page - 1, self.page + 1)
                    if 1 <= other <= self.total_pages]
        if script == _ROUTE_AUDIT_JS:
            count = self.page_counts.get(self.page, 20)
            expected_routes = sum(self.page_counts.get(page, 20)
                                  for page in range(1, self.total_pages + 1))
            return [{"aircraft_id": str(24000000 + self.page * 100 + index),
                     "registration": f"PP-{self.page}-{index}", "model": "A320",
                     "origin_code": "XAP", "destination_code": "GRU",
                     "scan_page": self.page,
                     "scan_total_pages": None if self.native_pager else self.total_pages,
                     "scan_has_next": self.page < self.total_pages if self.native_pager else None,
                     "scan_route_count": expected_routes, "home_hub_id": None}
                    for index in range(count)]
        raise AssertionError(f"unexpected read: {script[:40]}")

    def ajax(self, url, target):
        assert target == "routeAction"
        assert re.fullmatch(r"routes\.php\?start=\d+&sort=", url), url
        self.page = int(url.split("start=")[1].split("&")[0]) // 20 + 1
        self.navigations.append((self.page, url, target))
        if self.change_total_after_ajax == self.page:
            self.total_pages += 1
        if self.wrong_page_after_ajax == self.page:
            self.page += 1
        if self.fail_after_ajax == self.page and not self.failures:
            self.failures += 1
            raise TimeoutError("Ajax timed out after the page changed")


def test_live_pages_cover_all_eleven_pages_incrementally_and_restore(tmp_path):
    bot = LiveRoutesBot()
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=11)
    assert registry.snapshot()["scan_coverage"]["observed_pages"] == 1

    for _ in range(4):
        visited = audit_routes_live_pages(bot, registry, pages_per_cycle=3)
        assert 0 < len(visited) <= 3
        assert bot.page == 1

    snapshot = registry.snapshot()
    coverage = snapshot["scan_coverage"]
    assert coverage["total_pages"] == 11
    assert coverage["observed_pages"] == 11
    assert coverage["unique_aircraft"] == 197
    assert coverage["repeated_aircraft_across_pages"] == 0
    # Incremental observations do not constitute a single coherent audit.
    assert coverage["full_page_coverage_verified"] is False
    assert snapshot["last_verified_full_audit"] is None
    assert coverage["partial"] is True
    assert snapshot["total"] == 197
    assert all("home_hub_id" not in row for row in snapshot["relations"])
    assert bot.navigations
    assert all(url.endswith("&sort=") and target == "routeAction"
               for _, url, target in bot.navigations)


def test_all_eleven_pages_can_be_audited_in_one_read_only_cycle(tmp_path):
    bot = LiveRoutesBot(page_counts={1: 15, 2: 20, 3: 20, 4: 18,
                                      5: 19, 6: 19, 7: 20, 8: 19,
                                      9: 19, 10: 19, 11: 16})
    registry = RouteRegistry(tmp_path / "routes.json")

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=11) == list(range(1, 12))
    coverage = registry.snapshot()["scan_coverage"]
    assert bot.page == 1
    assert coverage["expected_routes"] == 204
    assert coverage["observed_pages"] == 11
    assert coverage["unique_aircraft"] == 204
    assert coverage["repeated_aircraft_across_pages"] == 0
    assert coverage["full_page_coverage_verified"] is True
    assert registry.snapshot()["last_verified_full_audit"]["expected_routes"] == 204
    # The full audit rereads every page before certifying the snapshot.
    assert sum(page == 2 for page, _, _ in bot.navigations) >= 2
    assert audit_routes(bot, registry, page=1, total_pages=11)
    assert registry.snapshot()["scan_coverage"]["full_page_coverage_verified"] is False
    assert registry.snapshot()["last_verified_full_audit"]["expected_routes"] == 204


@pytest.mark.parametrize("initial_page", [1, 6, 11])
def test_planning_audits_all_pages_despite_incremental_budget(tmp_path, initial_page):
    bot = LiveRoutesBot(initial_page=initial_page, page_counts={11: 4})
    registry = RouteRegistry(tmp_path / "routes.json")
    visited = audit_routes_live_pages(bot, registry, pages_per_cycle=3, attempt_full=True)
    assert sorted(visited) == list(range(1, 12))
    assert bot.page == initial_page
    assert registry.snapshot()["scan_coverage"]["full_page_coverage_verified"] is True


@pytest.mark.parametrize(("initial_page", "page_two_count"), [(1, 20), (6, 19), (12, 19)])
def test_planning_uses_the_native_last_page_with_underfilled_pages(tmp_path, initial_page,
                                                                  page_two_count):
    bot = LiveRoutesBot(initial_page=initial_page, total_pages=12, native_pager=True,
                        page_counts={1: 17, 2: page_two_count, 12: 1})
    registry = RouteRegistry(tmp_path / "routes.json")

    assert audit_routes_live_pages(bot, registry, attempt_full=True) == list(range(1, 13))
    assert bot.page == initial_page
    coverage = registry.snapshot()["scan_coverage"]
    assert coverage["expected_routes"] == 198 + page_two_count
    assert coverage["observed_pages"] == 12
    assert coverage["full_page_coverage_verified"] is True


def test_incremental_native_pager_never_certifies_its_page_estimate(tmp_path):
    bot = LiveRoutesBot(total_pages=4, native_pager=True, page_counts={1: 17, 2: 2, 3: 2, 4: 1})
    registry = RouteRegistry(tmp_path / "routes.json")

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=3) == [1, 2]
    assert bot.page == 1
    assert registry.snapshot()["last_verified_full_audit"] is None


def test_planning_over_page_limit_stays_partial(tmp_path):
    bot = LiveRoutesBot(total_pages=26, page_counts={26: 4})
    registry = RouteRegistry(tmp_path / "routes.json")
    assert len(audit_routes_live_pages(bot, registry, pages_per_cycle=3, attempt_full=True)) == 3
    assert bot.page == 1
    assert registry.snapshot()["scan_coverage"]["full_page_coverage_verified"] is False


def test_planning_deadline_discards_capture_and_restores_view(tmp_path, monkeypatch):
    clock = [0]
    monkeypatch.setattr("fleet.time.monotonic", lambda: clock[0])

    class SlowRoutesBot(LiveRoutesBot):
        def ajax(self, url, target):
            super().ajax(url, target)
            clock[0] += 121

    bot = SlowRoutesBot(page_counts={11: 4})
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes_live_pages(bot, registry, attempt_full=True) == []
    assert bot.page == 1
    assert registry.snapshot()["last_verified_full_audit"] is None


def test_same_total_page_movement_during_full_recheck_discards_audit(tmp_path):
    class MovingAircraftBot(LiveRoutesBot):
        shifted = False

        def ajax(self, url, target):
            previous_page = self.page
            super().ajax(url, target)
            if previous_page == 3 and self.page == 2:
                self.shifted = True

        def js(self, script):
            rows = super().js(script)
            if script == _ROUTE_AUDIT_JS and self.shifted:
                if self.page == 1:
                    rows[0]["aircraft_id"] = "24000200"
                elif self.page == 2:
                    rows[0]["aircraft_id"] = "24000100"
            return rows

    bot = MovingAircraftBot(total_pages=3)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=3)
    before = registry.snapshot()

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=3) == []
    assert bot.shifted is True
    assert bot.page == 1
    assert registry.snapshot() == before
    assert registry.snapshot()["last_verified_full_audit"] is None


@pytest.mark.parametrize("drift", [None, "aircraft_id", "route_id", "destination_id"])
def test_full_native_audit_reconciles_moved_rows_and_reversed_routes(tmp_path, drift):
    class ReorderedRoutesBot(LiveRoutesBot):
        shifted = False

        def ajax(self, url, target):
            previous_page = self.page
            super().ajax(url, target)
            if previous_page == 3 and self.page == 2:
                self.shifted = True

        def js(self, script):
            rows = super().js(script)
            if script != _ROUTE_AUDIT_JS:
                return rows
            for row in rows:
                row.update(route_id=int(row["aircraft_id"]) + 1, origin_id="1", destination_id="2")
            if self.shifted and self.page in (1, 2):
                source_page = 3 - self.page
                aircraft_id = str(24000000 + source_page * 100)
                rows[0].update(aircraft_id=aircraft_id, route_id=int(aircraft_id) + 1,
                               registration=f"PP-{source_page}-0", origin_id="2", destination_id="1",
                               origin_code="GRU", destination_code="XAP", in_flight=True)
                if drift and self.page == 2:
                    rows[0][drift] = {
                        "aircraft_id": "24000200",
                        "route_id": rows[1]["route_id"],
                        "destination_id": "3",
                    }[drift]
                rows.reverse()
            return rows

    bot = ReorderedRoutesBot(total_pages=3, native_pager=True, page_counts={1: 2, 2: 3, 3: 1})
    registry = RouteRegistry(tmp_path / "routes.json")
    roster = []
    for page in (1, 2, 3):
        bot.page = page
        roster.extend(bot.js(_ROUTE_AUDIT_JS))
    bot.page = 1
    assert registry.record_game_roster(roster, len(roster))
    before = registry.snapshot()

    visited = audit_routes_live_pages(bot, registry, attempt_full=True)
    assert bot.shifted and bot.page == 1
    if drift:
        assert visited == []
        assert registry.snapshot() == before
        return

    assert visited == [1, 2, 3]
    coverage = registry.snapshot()["scan_coverage"]
    assert coverage["full_page_coverage_verified"] is True
    assert set(coverage["pages"]["1"]["aircraft_ids"]) == {"24000200", "24000101"}
    counts = {"routes": len(roster), "parked": 0, "pending": 0}
    assert registry.confirm_fleet_coverage(roster, before_counts=counts, after_counts=counts,
                                           audited_pages=visited)


def test_same_total_page_movement_during_restoration_discards_full_audit(tmp_path):
    class MovingOnRestoreBot(LiveRoutesBot):
        shifted = False

        def ajax(self, url, target):
            previous_page = self.page
            super().ajax(url, target)
            visited_last_twice = sum(page == 3 for page, _, _ in self.navigations) >= 2
            if visited_last_twice and previous_page == 2 and self.page == 1:
                self.shifted = True

        def js(self, script):
            rows = super().js(script)
            if script == _ROUTE_AUDIT_JS and self.shifted and self.page == 1:
                rows[0]["aircraft_id"] = "24000999"
            return rows

    bot = MovingOnRestoreBot(total_pages=3)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=3)
    before = registry.snapshot()

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=3) == []
    assert bot.shifted is True
    assert bot.page == 1
    assert registry.snapshot() == before


def test_cross_cycle_duplicate_aircraft_cannot_be_full_coverage(tmp_path):
    class DuplicateAcrossPages(LiveRoutesBot):
        def js(self, script):
            rows = super().js(script)
            if script == _ROUTE_AUDIT_JS and self.page == 2:
                rows[0]["aircraft_id"] = "24000100"  # Already present on page 1.
            return rows

    bot = DuplicateAcrossPages(total_pages=3)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=3)
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == [2, 3]
    coverage = registry.snapshot()["scan_coverage"]
    assert coverage["observed_pages"] == 3
    assert coverage["repeated_aircraft_across_pages"] == 1
    assert coverage["full_page_coverage_verified"] is False


@pytest.mark.parametrize("persistent", [False, True])
def test_full_audit_retries_an_overlapping_page_from_the_start(tmp_path, persistent):
    class OverlappingPageBot(LiveRoutesBot):
        def js(self, script):
            rows = super().js(script)
            visits = [page for page, _, _ in self.navigations].count(2)
            if script == _ROUTE_AUDIT_JS and self.page == 2 and (persistent or visits == 1):
                rows[0]["aircraft_id"] = "24000100"
            return rows

    bot = OverlappingPageBot(total_pages=3, native_pager=True)
    registry = RouteRegistry(tmp_path / "routes.json")

    assert audit_routes_live_pages(bot, registry, attempt_full=True) == ([] if persistent else [1, 2, 3])
    assert [page for page, _, _ in bot.navigations][:3] == [2, 1, 2]
    assert bot.page == 1
    assert (registry.snapshot()["last_verified_full_audit"] is not None) is (not persistent)


def test_changed_route_count_resets_stale_page_coverage(tmp_path):
    bot = LiveRoutesBot(total_pages=3)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=3) == [1, 2, 3]
    assert registry.snapshot()["scan_coverage"]["full_page_coverage_verified"] is True

    bot.page_counts[1] = 15
    assert audit_routes(bot, registry, page=1, total_pages=3)
    coverage = registry.snapshot()["scan_coverage"]
    assert coverage["observed_pages"] == 1
    assert coverage["expected_routes"] == 55
    assert coverage["full_page_coverage_verified"] is False


def test_route_count_change_during_ajax_invalidates_staged_pages(tmp_path):
    class GrowingBot(LiveRoutesBot):
        def ajax(self, url, target):
            super().ajax(url, target)
            if self.page == 2:
                self.page_counts[1] = 15

    bot = GrowingBot(total_pages=3)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=3)

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=3) == []
    assert bot.page == 1
    coverage = registry.snapshot()["scan_coverage"]
    assert coverage["expected_routes"] == 55
    assert coverage["observed_pages"] == 1
    assert coverage["full_page_coverage_verified"] is False


@pytest.mark.parametrize("visible", [1, 7, 14, 19, 20])
def test_partial_first_page_uses_native_offset_not_visible_count(tmp_path, visible):
    """The real 203 Routes count gives 11 pages even when page 1 shows 14 rows."""
    counts = {1: visible, 2: 7, 3: 19}
    bot = LiveRoutesBot(page_counts=counts)
    registry = RouteRegistry(tmp_path / "routes.json")

    assert audit_routes(bot, registry, page=1, total_pages=11)
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == [2, 3]
    assert bot.page == 1

    coverage = registry.snapshot()["scan_coverage"]
    assert coverage["total_pages"] == 11
    assert coverage["observed_pages"] == 3
    assert coverage["unique_aircraft"] == visible + 7 + 19
    assert coverage["pages"]["1"]["visible"] == visible
    assert coverage["pages"]["2"]["visible"] == 7
    assert coverage["pages"]["3"]["visible"] == 19
    # No page offset may be computed using the current number of visible rows.
    assert [url for _, url, _ in bot.navigations[:2]] == [
        "routes.php?start=20&sort=", "routes.php?start=40&sort=",
    ]
    assert all(int(url.split("start=")[1].split("&")[0]) % 20 == 0
               for _, url, _ in bot.navigations)


def test_variable_page_sizes_across_bounded_cycles_preserve_unique_ids(tmp_path):
    counts = {1: 14, 2: 1, 3: 7, 4: 19, 5: 20, 6: 2}
    bot = LiveRoutesBot(total_pages=6, page_counts=counts)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=6)

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == [2, 3]
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == [4, 5]
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == [6, 1]

    snapshot = registry.snapshot()
    coverage = snapshot["scan_coverage"]
    assert coverage["observed_pages"] == coverage["total_pages"] == 6
    assert coverage["unique_aircraft"] == sum(counts.values()) == 63
    assert snapshot["total"] == 63
    assert {int(page): entry["visible"] for page, entry in coverage["pages"].items()} == counts
    assert bot.page == 1

    # More aircraft arrive on a previously verified page while page count stays 6.
    bot.page_counts[1] = 17
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == [2, 3]
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == [1, 4]
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == [5, 6]
    coverage = registry.snapshot()["scan_coverage"]
    assert coverage["observed_pages"] == 6
    assert coverage["pages"]["1"]["visible"] == 17
    assert coverage["unique_aircraft"] == 66
    assert bot.page == 1


@pytest.mark.parametrize("visible", [0, 21])
def test_empty_or_oversized_ajax_page_is_not_claimed(tmp_path, visible):
    bot = LiveRoutesBot(total_pages=3, page_counts={1: 14, 2: visible, 3: 7})
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=3)

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == []
    coverage = registry.snapshot()["scan_coverage"]
    assert coverage["observed_pages"] == 1
    assert coverage["unique_aircraft"] == 14
    assert bot.page == 1


def test_ajax_waits_for_stable_new_page_before_recording(tmp_path):
    class DelayedRowsBot(LiveRoutesBot):
        def __init__(self):
            super().__init__(total_pages=4)
            self.previous_page = 1
            self.stale_reads = 0

        def ajax(self, url, target):
            self.previous_page = self.page
            super().ajax(url, target)
            self.stale_reads = 3

        def js(self, script):
            if script == _ROUTE_AUDIT_JS and self.stale_reads:
                self.stale_reads -= 1
                displayed = self.page
                self.page = self.previous_page
                try:
                    return super().js(script)
                finally:
                    self.page = displayed
            return super().js(script)

    bot = DelayedRowsBot()
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=4)
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == [2, 3]
    assert bot.page == 1
    assert registry.snapshot()["scan_coverage"]["observed_pages"] == 3


@pytest.mark.parametrize("reorder", [False, True])
def test_ajax_page_number_alone_does_not_prove_new_rows(tmp_path, reorder):
    class RepeatedRowsBot(LiveRoutesBot):
        def js(self, script):
            result = super().js(script)
            if script == _ROUTE_AUDIT_JS and self.page == 2:
                original = self.page
                self.page = 1
                try:
                    result = super().js(script)
                finally:
                    self.page = original
                for row in result:
                    row["scan_page"] = original
                if reorder:
                    result.reverse()
            return result

    bot = RepeatedRowsBot(total_pages=4)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=4)
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == []
    assert bot.page == 1
    assert registry.snapshot()["scan_coverage"]["observed_pages"] == 1


def test_ajax_retries_a_transient_dom_read_error(tmp_path):
    class TemporaryReadErrorBot(LiveRoutesBot):
        failed_reads = 0

        def ajax(self, url, target):
            super().ajax(url, target)
            self.failed_reads = 1

        def js(self, script):
            if script == _ROUTE_AUDIT_JS and self.failed_reads:
                self.failed_reads -= 1
                raise RuntimeError("Route list is being replaced by AJAX")
            return super().js(script)

    bot = TemporaryReadErrorBot(total_pages=3)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=3)
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == [2, 3]
    assert bot.page == 1
    assert registry.snapshot()["scan_coverage"]["observed_pages"] == 3


@pytest.mark.parametrize("invalid", ["duplicate", "changing"])
def test_ajax_rejects_duplicate_or_unstable_rows(tmp_path, invalid):
    class InconsistentRowsBot(LiveRoutesBot):
        reads = 0

        def js(self, script):
            result = super().js(script)
            if script == _ROUTE_AUDIT_JS and self.page == 2:
                if invalid == "duplicate":
                    result[1]["aircraft_id"] = result[0]["aircraft_id"]
                else:
                    self.reads += 1
                    result[0]["registration"] = f"PP-volatile-{self.reads}"
            return result

    bot = InconsistentRowsBot(total_pages=4)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=4)
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == []
    assert bot.page == 1
    assert registry.snapshot()["scan_coverage"]["observed_pages"] == 1


def test_fleet_growth_restarts_coverage_and_revisits_all_pages(tmp_path):
    bot = LiveRoutesBot(total_pages=4)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=4)
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == [2, 3]
    assert registry.snapshot()["scan_coverage"]["observed_pages"] == 3

    bot.total_pages = 5
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == [1, 2]
    resized = registry.snapshot()["scan_coverage"]
    assert resized["total_pages"] == 5
    assert resized["observed_pages"] == 2
    assert resized["partial"] is True

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == [3, 4]
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == [5, 1]
    final = registry.snapshot()["scan_coverage"]
    assert final["observed_pages"] == 5
    assert final["total_pages"] == 5
    assert final["partial"] is True
    assert bot.page == 1


def test_restore_original_page_when_starting_in_middle(tmp_path):
    bot = LiveRoutesBot(initial_page=4, total_pages=6)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=4, total_pages=6)
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == [1, 2]
    assert bot.page == 4
    assert bot.navigations[-1][0] == 4
    assert registry.snapshot()["scan_coverage"]["observed_pages"] == 3


def test_stopping_during_navigation_restores_without_new_coverage(tmp_path):
    class StoppingBot(LiveRoutesBot):
        def ajax(self, url, target):
            super().ajax(url, target)
            if self.page == 2 and not self.stopping:
                self.stopping = True

    bot = StoppingBot(total_pages=6)
    registry = RouteRegistry(tmp_path / "routes.json")
    for page in (1, 2, 3):
        bot.page = page
        assert audit_routes(bot, registry, page=page, total_pages=6)
    bot.page = 1

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == []
    assert bot.page == 1
    assert registry.snapshot()["scan_coverage"]["observed_pages"] == 3


def test_single_page_audits_without_ajax(tmp_path):
    bot = LiveRoutesBot(total_pages=1)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes_live_pages(bot, registry, pages_per_cycle=3) == [1]
    assert registry.snapshot()["scan_coverage"]["observed_pages"] == 1
    assert bot.navigations == []


def test_timeout_after_navigation_restores_original_page_without_false_coverage(tmp_path):
    bot = LiveRoutesBot(fail_after_ajax=2)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=11)

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=3) == []
    assert bot.page == 1
    assert bot.navigations[0][0] == 2
    assert bot.navigations[-1][0] == 1
    assert registry.snapshot()["scan_coverage"]["observed_pages"] == 1


def test_changed_total_or_page_identity_never_records_unverified_pages(tmp_path):
    for options in ({"change_total_after_ajax": 2}, {"wrong_page_after_ajax": 2}):
        bot = LiveRoutesBot(**options)
        registry = RouteRegistry(tmp_path / f"{next(iter(options))}.json")
        assert audit_routes(bot, registry, page=1, total_pages=11)
        assert audit_routes_live_pages(bot, registry, pages_per_cycle=3) == []
        assert bot.page == 1
        assert registry.snapshot()["scan_coverage"]["observed_pages"] == 1


def test_shrinking_fleet_discards_outdated_scan_coverage(tmp_path):
    class ShrinkingBot(LiveRoutesBot):
        def ajax(self, url, target):
            super().ajax(url, target)
            if self.page == 2:
                self.total_pages = 3

    bot = ShrinkingBot(total_pages=4)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=4)
    assert audit_routes_live_pages(bot, registry) == []
    assert bot.page == 1
    assert registry.snapshot()["scan_coverage"]["observed_pages"] == 1

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == [2, 3]
    new_coverage = registry.snapshot()["scan_coverage"]
    assert new_coverage["total_pages"] == 3
    assert new_coverage["observed_pages"] == 3


def test_missing_aircraft_id_prevents_claiming_a_page(tmp_path):
    class MissingIdentityBot(LiveRoutesBot):
        def js(self, script):
            result = super().js(script)
            if script == _ROUTE_AUDIT_JS and self.page == 2:
                result[0]["aircraft_id"] = ""
            return result

    bot = MissingIdentityBot()
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=11)
    assert audit_routes_live_pages(bot, registry) == []
    assert bot.page == 1
    assert registry.snapshot()["scan_coverage"]["observed_pages"] == 1


def test_scan_does_not_persist_non_numeric_aircraft_ids_or_unproven_home(tmp_path):
    registry = RouteRegistry(tmp_path / "routes.json")
    registry.record_scan(2, 0, 2, aircraft_ids=["unknown", "123"], page=1,
                         total_pages=1, route_observations=[
                             {"aircraft_id": "unknown", "registration": "PP-?",
                              "home_hub_id": "2926"},
                             {"aircraft_id": "123", "registration": "PP-123",
                              "home_hub_id": None},
                         ])
    snapshot = registry.snapshot()
    assert snapshot["total"] == 1
    assert snapshot["relations"][0]["aircraft_id"] == "123"
    assert "home_hub_id" not in snapshot["relations"][0]


def test_identical_pager_links_can_appear_more_than_once(tmp_path):
    class DuplicatePagerBot(LiveRoutesBot):
        def js(self, script):
            links = super().js(script)
            if script == _ROUTES_PAGER_LINKS_JS:
                return links + [dict(links[0])]
            return links

    bot = DuplicatePagerBot(total_pages=3)
    registry = RouteRegistry(tmp_path / "routes.json")

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == [1, 2]
    assert bot.page == 1
    assert registry.snapshot()["scan_coverage"]["observed_pages"] == 2


def test_conflicting_pager_links_cannot_select_an_ajax_url(tmp_path):
    class ConflictingPagerBot(LiveRoutesBot):
        def js(self, script):
            links = super().js(script)
            if script == _ROUTES_PAGER_LINKS_JS and self.page == 1:
                links.append({"offset": 20, "target": "routeAction",
                              "url": "routes.php?start=20&sort=desc"})
            return links

    bot = ConflictingPagerBot(total_pages=3)
    registry = RouteRegistry(tmp_path / "routes.json")

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == []
    assert bot.navigations == []
    assert registry.snapshot()["scan_coverage"] is None


def test_growth_while_navigating_invalidates_staged_page_coverage(tmp_path):
    bot = LiveRoutesBot(total_pages=3, change_total_after_ajax=3)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=3)

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == []
    assert bot.page == 1
    coverage = registry.snapshot()["scan_coverage"]
    assert coverage["total_pages"] == 4
    assert coverage["observed_pages"] == 1
    assert set(coverage["pages"]) == {"1"}


def test_growth_on_restoration_invalidates_staged_page_coverage(tmp_path):
    class GrowOnRestoreBot(LiveRoutesBot):
        def ajax(self, url, target):
            from_page = self.page
            super().ajax(url, target)
            if from_page != 1 and self.page == 1:
                self.total_pages += 1

    bot = GrowOnRestoreBot(total_pages=3)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=3)

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == []
    assert bot.page == 1
    coverage = registry.snapshot()["scan_coverage"]
    assert coverage["total_pages"] == 4
    assert coverage["observed_pages"] == 1
    assert set(coverage["pages"]) == {"1"}


def test_unrestored_view_does_not_count_scanned_pages(tmp_path):
    class RefusesRestoreBot(LiveRoutesBot):
        def ajax(self, url, target):
            if "start=0&" in url and self.page != 1:
                raise TimeoutError("restoration failed before changing pages")
            return super().ajax(url, target)

    bot = RefusesRestoreBot(total_pages=3)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=3)

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=1) == []
    assert bot.page == 2
    coverage = registry.snapshot()["scan_coverage"]
    assert coverage["observed_pages"] == 1
    assert set(coverage["pages"]) == {"1"}


def test_overlapping_aircraft_between_pages_invalidates_cycle(tmp_path):
    class ShiftedRowsBot(LiveRoutesBot):
        def js(self, script):
            rows = super().js(script)
            if script == _ROUTE_AUDIT_JS and self.page == 2:
                rows[0]["aircraft_id"] = "24000100"  # Also visible on page 1.
            return rows

    bot = ShiftedRowsBot(total_pages=3)
    registry = RouteRegistry(tmp_path / "routes.json")

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == []
    assert bot.page == 1
    assert registry.snapshot()["scan_coverage"] is None


def test_timeout_on_later_ajax_does_not_publish_staged_pages(tmp_path):
    bot = LiveRoutesBot(total_pages=4, fail_after_ajax=3)
    registry = RouteRegistry(tmp_path / "routes.json")
    assert audit_routes(bot, registry, page=1, total_pages=4)

    assert audit_routes_live_pages(bot, registry, pages_per_cycle=2) == []
    assert bot.page == 1
    coverage = registry.snapshot()["scan_coverage"]
    assert coverage["observed_pages"] == 1
    assert set(coverage["pages"]) == {"1"}
