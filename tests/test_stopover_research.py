from types import SimpleNamespace

import pytest

import stopover_research as research

NOW = 1800000000
SAMPLE = {"source": "game_route_search", "origin_id": "2891", "destination_id": "1440",
          "distance_km": 17000, "observed_at": NOW, "destination_runway_ft": 12000}
MODEL = {"id": "11"}
VARIANT = {"engine_id": "9", "engine_available": True,
           "engine_detail": {"model_identity_verified": True, "observed_at": NOW,
                             "metrics": {"range_km": 14500, "required_runway_ft": 5500}}}
MAP = {"direct": 17000, "candidates": [{"id": "2601", "first": 14000, "second": 3500}]}
LEGS = {("2891", "2601"): {"codes": ["ULA", "ANC"], "runways": ["6562ft", "11584ft"]},
        ("2601", "1440"): {"codes": ["ANC", "LAX"], "runways": ["11584ft", "12000ft"]}}


def test_research_reads_both_legs_and_revokes_after_failed_refresh(tmp_path, monkeypatch):
    registry = research.StopoverResearchRegistry(tmp_path / "stopovers.json")
    subject = research.subject_for(SAMPLE, MODEL, VARIANT, NOW)
    assert subject
    clock = [NOW]
    calls = []
    monkeypatch.setattr(research.time, "time", lambda: clock[0])

    def details(bot, origin, destination):
        calls.append((origin, destination))
        return LEGS[origin, destination]

    monkeypatch.setattr(research, "research_details", details)
    bot = SimpleNamespace(js=lambda *args: MAP)
    assert research.collect_stopover(bot, registry, [(subject, SAMPLE)]) == 1
    assert calls == [("2891", "2601")] * 2 + [("2601", "1440")] * 2
    raw = registry.enrich([SAMPLE], NOW)[0]["stopover_research"][0]
    proof = research.current_stopover(raw, subject, SAMPLE, NOW)
    assert proof["stop_id"] == "2601"
    assert proof["stop_code"] == "ANC"
    assert proof["stop_runway_ft"] == 11584
    assert proof["game_rules_verified"] is proof["purchase_eligible"] is False
    assert research.current_stopover(raw, subject, SAMPLE, NOW + 901) is None
    assert research.current_stopover(raw, {**subject, "engine_id": "10"}, SAMPLE, NOW) is None
    assert research.current_stopover(raw, subject, {**SAMPLE, "destination_runway_ft": 11999}, NOW) is None
    assert research.current_stopover({**raw, "observed_at": NOW - 1}, subject, SAMPLE, NOW) is None
    conflicting = {**raw, "stop_runway_ft": 11583}
    assert research.select_current_stopover({**SAMPLE, "stopover_research": [raw, conflicting]},
                                           MODEL, VARIANT, NOW) is None
    assert research.select_current_stopover({**SAMPLE, "stopover_research": [raw, raw]},
                                           MODEL, VARIANT, NOW) == proof
    clock[0] += 1
    bot.js = lambda *args: []
    assert research.collect_stopover(bot, registry, [(subject, SAMPLE)]) == 0
    assert "stopover_research" not in registry.enrich([SAMPLE], clock[0])[0]


@pytest.mark.parametrize("changes", [
    {"codes": ["LAX", "ANC"]}, {"runways": ["11583ft", "12000ft"]},
    {"runways": ["11584ft", "5499ft"]}, {"runways": ["11584ft", "11999ft"]},
])
def test_inconsistent_second_leg_is_never_saved(tmp_path, monkeypatch, changes):
    registry = research.StopoverResearchRegistry(tmp_path / "stopovers.json")
    monkeypatch.setattr(research.time, "time", lambda: NOW)
    subject = research.subject_for(SAMPLE, MODEL, VARIANT, NOW)
    monkeypatch.setattr(research, "research_details", lambda bot, origin, dest: {
        **LEGS[origin, dest], **(changes if origin == "2601" else {})})
    assert research.collect_stopover(SimpleNamespace(js=lambda *args: MAP), registry, [(subject, SAMPLE)]) == 0
    assert "stopover_research" not in registry.enrich([SAMPLE], NOW)[0]


def test_map_must_be_stable_and_each_leg_fit_variant(tmp_path, monkeypatch):
    registry = research.StopoverResearchRegistry(tmp_path / "stopovers.json")
    monkeypatch.setattr(research.time, "time", lambda: NOW)
    subject = research.subject_for(SAMPLE, MODEL, VARIANT, NOW)
    monkeypatch.setattr(research, "research_details", lambda *args: pytest.fail("unexpected detail read"))
    invalid = {"direct": 17000, "candidates": [{"id": "2601", "first": 14501, "second": 3500}]}
    reads = iter((MAP, invalid))
    assert research.collect_stopover(SimpleNamespace(js=lambda *args: next(reads)), registry, [(subject, SAMPLE)]) == 0
    assert research.collect_stopover(SimpleNamespace(js=lambda *args: invalid), registry, [(subject, SAMPLE)]) == 0
    assert research.collect_stopover(SimpleNamespace(js=lambda *args: {**MAP, "direct": 16000}),
                                     registry, [(subject, SAMPLE)]) == 0


def test_registry_rotates_subjects_and_suggestions(tmp_path):
    registry = research.StopoverResearchRegistry(tmp_path / "stopovers.json")
    subject = research.subject_for(SAMPLE, MODEL, VARIANT, NOW)
    other = {**subject, "engine_id": "10"}
    subjects = [(subject, SAMPLE), (other, SAMPLE)]
    selected = [registry.reserve(iter(subjects), NOW + i) for i in range(4)]
    assert [row[0]["engine_id"] for row in selected] == ["10", "9", "10", "9"]
    assert [row[2] for row in selected] == [0, 0, 2, 2]


def test_uncorrelated_or_expired_variant_cannot_initiate_research():
    assert research.subject_for(SAMPLE, MODEL, {**VARIANT, "engine_available": False}, NOW) is None
    assert research.subject_for(SAMPLE, MODEL, {**VARIANT, "engine_detail": {
        **VARIANT["engine_detail"], "model_identity_verified": False}}, NOW) is None
    assert research.subject_for(SAMPLE, MODEL, VARIANT, NOW + 3 * 86400 + 1) is None
