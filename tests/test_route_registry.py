"""Persistent route registry: canonical direction, history and conservative identities."""
import json

from route_registry import RouteRegistry, endpoint, route_key, same_route


def test_direction_does_not_change_route_identity():
    dub = endpoint("101", "DUB", "Dublin")
    gru = endpoint("202", "GRU", "São Paulo")
    a = {"origin": dub, "destination": gru}
    b = {"origin": gru, "destination": dub}
    assert route_key(dub, gru) == route_key(gru, dub)
    assert same_route(a, b)
    assert not same_route(a, {"origin": dub, "destination": endpoint("999", "LHR")})


def test_duplicate_detection_persists_and_preserves_history(tmp_path):
    path = tmp_path / "routes_registry.json"
    registry = RouteRegistry(path)
    dub = endpoint("101", "DUB")
    gru = endpoint("202", "GRU")
    assert registry.record("ac1", "XP-001", "A380", dub, gru, source="criacao_confirmada")
    assert registry.record("ac2", "XP-002", "B777", gru, dub, source="jogo")
    assert not registry.record("ac3", "XP-003", "A320", dub, dub)
    report = RouteRegistry(path).snapshot(allow_duplicates=False)
    assert report["total"] == 2
    assert report["duplicate_routes"] == 1
    assert report["affected_aircraft"] == 2
    assert {item["registration"] for item in report["relations"]} == {"XP-001", "XP-002"}
    assert report["history"][0]["action"] == "rota_registrada"
    assert registry.is_occupied(dub, gru, except_aircraft="ac1")
    assert registry.is_occupied(gru, dub, except_aircraft="ac2")


def test_unrecognized_airport_identity_cannot_create_a_fake_route(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    assert not registry.record("a", "XP", "A320", endpoint(), endpoint("55"))
    assert registry.observe("a", "XP", "A320", at_base=False)
    snap = registry.snapshot()
    assert snap["total"] == 1
    assert snap["relations"][0]["status"] == "rota_nao_identificada"
    assert not registry.is_occupied(endpoint("12"), endpoint("55"))


def test_manual_names_normalize_accents_and_detect_reverse(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    assert registry.record("a", "A", "777", endpoint(name="São Paulo"), endpoint(name="Dublin"))
    assert registry.record("b", "B", "777", endpoint(name="DUBLIN"), endpoint(name="SAO PAULO"))
    assert registry.snapshot()["duplicate_routes"] == 1


def test_id_mismatch_with_same_airport_code_must_not_be_assumed_equal():
    dub = endpoint("123", "DUB")
    invalid = endpoint("998", "DUB")
    gru = endpoint("201", "GRU")
    assert not same_route({"origin": dub, "destination": gru},
                          {"origin": invalid, "destination": gru})


def test_partial_scan_does_not_erase_prior_confirmed_route(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    a, b = endpoint("101"), endpoint("202")
    registry.record("a", "XP-1", "A320", a, b, at_base=True)
    registry.observe("a", "XP-1", "A320", at_base=False)
    row = registry.snapshot()["relations"][0]
    assert row["origin"]["id"] == "101"
    assert row["destination"]["id"] == "202"
    assert row["at_base"] is False
    assert row["status"] == "ativa"


def test_proposal_does_not_overwrite_current_route(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    a, b = endpoint("101"), endpoint("202")
    registry.record("a", "XP", "A320", a, b)
    proposal = {"destination_id": "303", "profit_per_day": 13500}
    assert registry.note("a", "aguardando_aeronave_na_base", proposal=proposal)
    assert registry.snapshot()["relations"][0]["destination"]["id"] == "202"
    assert json.loads(registry.path.read_text(encoding="utf-8"))["aircraft"]["a"]["proposal"] == proposal
    # Reading the same route from the game must not erase a pending proposal.
    registry.record("a", "XP", "A320", a, b, source="jogo")
    assert registry.snapshot()["relations"][0]["proposal"] == proposal
    # A confirmed reroute replaces it and clears the old proposal.
    registry.record("a", "XP", "A320", a, endpoint("303"), source="redirecionamento")
    assert "proposal" not in registry.snapshot()["relations"][0]


def test_web_route_workplace_has_dedicated_navigation():
    from conftest import ROOT
    page = (ROOT / "assets/web/index.html").read_text(encoding="utf-8")
    assert 'id="routesView" hidden' in page
    assert 'href="#routes"' in page
    assert 'id="routesTable"' in page
    assert 'api("/api/routes")' in page
    assert 'api("/api/routes", {action: "register", ...data})' in page


def test_game_observation_required_before_reroute(tmp_path):
    from route_registry import eligible_for_reroute
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    first, last = endpoint("101"), endpoint("202")
    registry.record("a", "XP", "A320", first, last, source="registro_manual", at_base=True)
    assert not eligible_for_reroute(registry.snapshot()["relations"][0])
    registry.record("a", "XP", "A320", first, last, source="game", at_base=True)
    verified = registry.snapshot()["relations"][0]
    assert eligible_for_reroute(verified, now=verified["game_verified_at"] + 30)
    assert not eligible_for_reroute(verified, now=verified["game_verified_at"] + 181)
    registry.observe("a", "XP", "A320", at_base=False)
    assert not eligible_for_reroute(registry.snapshot()["relations"][0])


def test_parked_without_route_invalidates_old_assignment(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    first, last = endpoint("101"), endpoint("202")
    registry.record("a", "XP", "A320", first, last)
    registry.unassign("a", "XP", "A320")
    snapshot = registry.snapshot()
    assert snapshot["relations"][0]["status"] == "sem_rota"
    assert snapshot["duplicate_routes"] == 0
    assert not registry.is_occupied(first, last)
    assert snapshot["history"][0]["action"] == "rota_removida_no_jogo"


def test_full_audit_rejects_duplicate_raw_ids_even_when_dedup_matches_visible(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    run_id = "a" * 32
    first_page = [str(identity) for identity in range(1, 21)]
    second_page = [str(identity) for identity in range(21, 41)]

    registry.record_scan(20, 0, 20, aircraft_ids=first_page + ["1"],
                         page=1, total_pages=2, expected_routes=40,
                         audit_run_id=run_id)
    registry.record_scan(20, 0, 20, aircraft_ids=second_page,
                         page=2, total_pages=2, expected_routes=40,
                         audit_run_id=run_id)

    coverage = RouteRegistry(registry.path).snapshot()["scan_coverage"]
    assert coverage["observed_pages"] == 2
    assert coverage["unique_aircraft"] == 40
    assert coverage["full_page_coverage_verified"] is False
    assert registry.snapshot()["last_verified_full_audit"] is None


def test_full_audit_rejects_partial_route_observations_for_claimed_page(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    run_id = "b" * 32
    first_page = [str(identity) for identity in range(1, 21)]
    second_page = [str(identity) for identity in range(21, 41)]

    registry.record_scan(20, 0, 20, aircraft_ids=first_page,
                         page=1, total_pages=2, expected_routes=40,
                         audit_run_id=run_id,
                         route_observations=[{"aircraft_id": identity} for identity in first_page[:-1]])
    registry.record_scan(20, 0, 20, aircraft_ids=second_page,
                         page=2, total_pages=2, expected_routes=40,
                         audit_run_id=run_id,
                         route_observations=[{"aircraft_id": identity} for identity in second_page])

    coverage = registry.snapshot()["scan_coverage"]
    assert coverage["observed_pages"] == 2
    assert coverage["full_page_coverage_verified"] is False
    assert registry.snapshot()["last_verified_full_audit"] is None


def test_game_roster_rejects_duplicate_numeric_aliases(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    assert not registry.record_game_roster([
        {"aircraft_id": "123", "route_id": 100},
        {"aircraft_id": "0123", "route_id": 100},
    ], expected_total=2)
    assert registry.snapshot()["current_roster_available"] is False


def _scan_audit_page(registry, run_id, page, total_pages, expected_routes, *,
                     ids=None, metadata=None):
    if ids is None:
        first = (page - 1) * 20 + 1
        ids = [str(identity) for identity in
               range(first, min(page * 20, expected_routes) + 1)]
    rows = [{"aircraft_id": identity, **(metadata or {})} for identity in ids]
    registry.record_scan(
        len(ids), 0, len(ids), aircraft_ids=ids,
        page=page, total_pages=total_pages, expected_routes=expected_routes,
        audit_run_id=run_id, route_observations=rows,
    )


def test_complete_stable_audit_keeps_current_snapshot_partial(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    run_id = "c" * 32

    for page in (1, 2, 3):
        _scan_audit_page(registry, run_id, page, 3, 41)

    report = RouteRegistry(registry.path).snapshot()
    assert report["scan_coverage"]["full_page_coverage_verified"] is True
    assert report["last_verified_full_audit"]["audit_run_id"] == run_id
    assert report["last_verified_full_audit"]["unique_aircraft"] == 41
    assert report["partial"] is True
    assert not any("home_hub_id" in row for row in report["relations"])


def test_same_ids_changed_route_evidence_revokes_audit(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    run_id = "c" * 32
    original = {"model": "A320", "observed_route_id": 5}
    _scan_audit_page(registry, run_id, 1, 2, 40, metadata=original)
    _scan_audit_page(registry, run_id, 2, 2, 40, metadata=original)
    assert registry.snapshot()["scan_coverage"]["full_page_coverage_verified"] is True
    _scan_audit_page(registry, run_id, 1, 2, 40, metadata={**original, "observed_route_id": 6})
    _scan_audit_page(registry, run_id, 1, 2, 40, metadata=original)
    report = registry.snapshot()
    assert report["scan_coverage"]["audit_run"]["invalidated"] is True
    assert report["scan_coverage"]["full_page_coverage_verified"] is False
    assert report["last_verified_full_audit"] is None


def test_current_coverage_expires_without_another_scan(tmp_path, monkeypatch):
    clock = [10000]
    monkeypatch.setattr("route_registry.time.time", lambda: clock[0])
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    _scan_audit_page(registry, "c" * 32, 1, 1, 20)
    assert registry.snapshot()["scan_coverage"]["full_page_coverage_verified"] is True
    clock[0] += 3600
    report = registry.snapshot()
    assert report["scan_coverage"]["full_page_coverage_verified"] is False
    assert report["scan_coverage"]["expired"] is True
    assert report["last_verified_full_audit"]["unique_aircraft"] == 20


def test_same_run_page_count_changes_cannot_be_recertified(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    run_id = "d" * 32
    _scan_audit_page(registry, run_id, 1, 2, 40)
    _scan_audit_page(registry, run_id, 2, 3, 60)

    # Even after recollecting every page with matching metadata, the run
    # observed a change in the fleet and cannot prove one coherent snapshot.
    for page in (1, 2, 3):
        _scan_audit_page(registry, run_id, page, 3, 60)
    report = registry.snapshot()
    assert report["scan_coverage"]["observed_pages"] == 3
    assert report["scan_coverage"]["unique_aircraft"] == 60
    assert report["scan_coverage"]["audit_run"]["invalidated"] is True
    assert report["scan_coverage"]["full_page_coverage_verified"] is False
    assert report["last_verified_full_audit"] is None

    # A completely new, consistent run can still establish a historical proof.
    for page in (1, 2, 3):
        _scan_audit_page(registry, "e" * 32, page, 3, 60)
    assert registry.snapshot()["last_verified_full_audit"]["unique_aircraft"] == 60


def test_same_run_route_count_change_with_fixed_page_count_blocks_audit(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    run_id = "f" * 32
    _scan_audit_page(registry, run_id, 1, 3, 45)
    _scan_audit_page(registry, run_id, 2, 3, 50)
    for page in (1, 2, 3):
        _scan_audit_page(registry, run_id, page, 3, 50)

    report = registry.snapshot()
    assert report["scan_coverage"]["observed_pages"] == 3
    assert report["scan_coverage"]["full_page_coverage_verified"] is False
    assert report["last_verified_full_audit"] is None


def test_same_run_invalid_loaded_page_metadata_cannot_be_overwritten(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    run_id = "1" * 32
    _scan_audit_page(registry, run_id, 3, 2, 40)
    for page in (1, 2):
        _scan_audit_page(registry, run_id, page, 2, 40)

    report = registry.snapshot()
    assert report["scan_coverage"]["observed_pages"] == 2
    assert report["scan_coverage"]["audit_run"]["invalidated"] is True
    assert report["scan_coverage"]["full_page_coverage_verified"] is False
    assert report["last_verified_full_audit"] is None


def test_raw_row_metadata_disagreement_blocks_repaired_same_run(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    run_id = "2" * 32
    _scan_audit_page(registry, run_id, 1, 2, 40, metadata={
        "scan_page": 2, "scan_total_pages": 2, "scan_route_count": 40,
    })
    _scan_audit_page(registry, run_id, 1, 2, 40, metadata={
        "scan_page": 1, "scan_total_pages": 2, "scan_route_count": 40,
    })
    _scan_audit_page(registry, run_id, 2, 2, 40, metadata={
        "scan_page": 2, "scan_total_pages": 2, "scan_route_count": 40,
    })

    report = registry.snapshot()
    assert report["scan_coverage"]["observed_pages"] == 2
    assert report["scan_coverage"]["full_page_coverage_verified"] is False
    assert report["last_verified_full_audit"] is None


def test_same_run_page_contents_changing_then_restored_cannot_certify(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    run_id = "3" * 32
    _scan_audit_page(registry, run_id, 1, 2, 40)
    shifted_ids = [str(identity) for identity in range(101, 121)]
    _scan_audit_page(registry, run_id, 1, 2, 40, ids=shifted_ids)
    _scan_audit_page(registry, run_id, 1, 2, 40)
    _scan_audit_page(registry, run_id, 2, 2, 40)

    report = registry.snapshot()
    assert report["scan_coverage"]["repeated_aircraft_across_pages"] == 0
    assert report["scan_coverage"]["audit_run"]["invalidated"] is True
    assert report["scan_coverage"]["full_page_coverage_verified"] is False


def test_page_count_must_match_declared_fleet_size(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    run_id = "4" * 32
    # Three pages can report 10 IDs each, but a 30-aircraft header requires
    # two pages. A plausible unique-ID sum cannot certify contradictory paging.
    for page in (1, 2, 3):
        _scan_audit_page(registry, run_id, page, 3, 30,
                         ids=[str(identity) for identity in
                              range((page - 1) * 10 + 1, page * 10 + 1)])
    report = registry.snapshot()
    assert report["scan_coverage"]["unique_aircraft"] == 30
    assert report["scan_coverage"]["full_page_coverage_verified"] is False
    assert report["last_verified_full_audit"] is None


def test_conflict_after_proof_revokes_only_same_run_certification(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    run_id = "5" * 32
    for page in (1, 2):
        _scan_audit_page(registry, run_id, page, 2, 40)
    assert registry.snapshot()["last_verified_full_audit"]["audit_run_id"] == run_id

    # The already certified run revealed an incompatible count later on.
    _scan_audit_page(registry, run_id, 1, 3, 60)
    assert registry.snapshot()["last_verified_full_audit"] is None

    other_run = "6" * 32
    for page in (1, 2):
        _scan_audit_page(registry, other_run, page, 2, 40)
    _scan_audit_page(registry, "7" * 32, 1, 2, 40)
    report = registry.snapshot()
    assert report["last_verified_full_audit"]["audit_run_id"] == other_run
    assert report["scan_coverage"]["full_page_coverage_verified"] is False
    assert report["partial"] is True


def test_string_page_metadata_cannot_be_full_audit_evidence(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    run_id = "8" * 32
    _scan_audit_page(registry, run_id, "1", 2, 40, ids=[str(i) for i in range(1, 21)])
    _scan_audit_page(registry, run_id, 2, 2, 40)
    assert registry.snapshot()["scan_coverage"]["observed_pages"] == 2
    assert registry.snapshot()["scan_coverage"]["full_page_coverage_verified"] is False


def test_same_page_reordered_ids_do_not_invalidate_verified_run(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    run_id = "9" * 32
    _scan_audit_page(registry, run_id, 1, 2, 40)
    _scan_audit_page(registry, run_id, 1, 2, 40,
                     ids=[str(identity) for identity in range(20, 0, -1)])
    _scan_audit_page(registry, run_id, 2, 2, 40)
    assert registry.snapshot()["scan_coverage"]["full_page_coverage_verified"] is True


def test_interleaved_untagged_scan_cannot_reuse_original_audit_run(tmp_path):
    registry = RouteRegistry(tmp_path / "routes_registry.json")
    run_id = "a" * 32
    _scan_audit_page(registry, run_id, 1, 2, 40)
    registry.record_scan(20, 0, 20, aircraft_ids=[str(i) for i in range(1, 21)],
                         page=1, total_pages=2, expected_routes=40)
    _scan_audit_page(registry, run_id, 2, 2, 40)
    _scan_audit_page(registry, run_id, 1, 2, 40)

    report = registry.snapshot()
    assert report["scan_coverage"]["observed_pages"] == 2
    assert report["scan_coverage"]["full_page_coverage_verified"] is False
    assert report["last_verified_full_audit"] is None
