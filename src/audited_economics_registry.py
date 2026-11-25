"""Durable, per-profile A3 evidence for the read-only A4 expansion planner.

Store the source observation bundle, then re-run the A3 evaluator on every
read. A previously valid estimate cannot acquire a fresh timestamp merely
because the dashboard reloaded it. A4 coverage and reservation evidence is
stored separately, with the same immutable game snapshot identity.
"""
from __future__ import annotations

import json
import math
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import paths
from expansion_economics import evaluate_expansion_economics
from opportunity_models import DEFAULT_MAX_AGE_SECONDS, complete_coverage_snapshot, fingerprint_snapshot


_LOCK = threading.RLock()
_MAX_SCENARIOS = 256


def _positive_timestamp(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value > 0
    except OverflowError:
        return False


def _record_timestamp(record):
    return record.get("captured_at", record.get("observed_at"))


def _valid_record_times(record, now):
    captured = _record_timestamp(record)
    observed = record.get("observed_at")
    return (_positive_timestamp(now) and _positive_timestamp(captured) and captured <= now
            and ((observed is None and "captured_at" in record and not record.get("cases"))
                 or (_positive_timestamp(observed) and observed <= captured)))


class AuditedEconomicsRegistry:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else paths.current().data / "audited_expansion.json"

    def _read(self) -> tuple[dict[str, Any], bool]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}, True
        except (OSError, ValueError):
            return {}, False
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            return {}, False
        if (not isinstance(payload.get("cases"), list)
                or not isinstance(payload.get("profile_id"), str)
                or not isinstance(payload.get("snapshot_id"), str)
                or type(payload.get("research_storage_truncated", False)) is not bool
                or (payload.get("portfolio") is not None
                    and not isinstance(payload["portfolio"], dict))
                or len(payload["cases"]) > _MAX_SCENARIOS):
            return {}, False
        return payload, True

    def begin_capture(self, snapshot: Mapping[str, Any], *, now: float | None = None) -> bool:
        """Bind the active register to a worker capture, including a partial capture.

        A capture establishes only identity and ordering. It cannot certify any
        opportunity, coverage or financial commitment by itself.
        """
        now = time.time() if now is None else now
        try:
            captured = snapshot["observations"]["captured_at"]
            snapshot_id = snapshot["snapshot_id"]
            observed = snapshot["observed_at"]
            if (type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != 1
                    or snapshot["source"] != "game_snapshot"
                    or snapshot["profile_id"] != paths.current().label
                    or not _positive_timestamp(captured) or not _positive_timestamp(now)
                    or (observed is not None and (not _positive_timestamp(observed) or observed > captured))
                    or not 0 <= now - captured <= DEFAULT_MAX_AGE_SECONDS
                    or snapshot_id != fingerprint_snapshot(snapshot)):
                return False
        except (KeyError, TypeError, ValueError, OverflowError):
            return False
        with _LOCK:
            existing, valid = self._read()
            if not valid or (existing and existing["profile_id"] != paths.current().label):
                return False
            if existing:
                if self.snapshot(now=now)["status"] == "registro_invalido":
                    return False
                previous = _record_timestamp(existing)
                if not _positive_timestamp(previous) or captured < previous:
                    return False
                if existing["snapshot_id"] == snapshot_id:
                    return captured == previous and observed == existing.get("observed_at")
                if captured == previous:
                    return False
            payload = {
                "schema_version": 1, "profile_id": paths.current().label,
                "snapshot_id": snapshot_id, "observed_at": observed,
                "captured_at": captured, "cases": [], "portfolio": None,
                "research_storage_truncated": False,
            }
            try:
                paths.write_atomic(self.path, json.dumps(payload, ensure_ascii=False, allow_nan=False),
                                   private=True)
            except (OSError, TypeError, ValueError, OverflowError):
                return False
        return True

    def record(self, snapshot: Mapping[str, Any], candidate: Mapping[str, Any],
               inputs: Mapping[str, Any], *, now: float | None = None,
               safety_margin_fraction: float = 0.10,
               stress: Mapping[str, float] | None = None) -> bool:
        """Accept one fully validated A3 case for the active game profile.

        Distinct observations of the same opportunity remain separate so the
        A3 ranker can quarantine contradictions. Older or same-time competing
        snapshots cannot overwrite a more recent research pass.
        """
        now = time.time() if now is None else now
        try:
            evaluated = evaluate_expansion_economics(
                snapshot, candidate, inputs, now=now,
                safety_margin_fraction=safety_margin_fraction, stress=stress,
            )
        except (TypeError, ValueError, OverflowError):
            return False
        if (evaluated.get("status") != "evaluated"
                or evaluated.get("profile_id") != paths.current().label
                or not isinstance(evaluated.get("snapshot_id"), str)
                or not evaluated["snapshot_id"]):
            return False
        observed_at = snapshot.get("observed_at")
        observations = snapshot.get("observations")
        captured_at = observations.get("captured_at") if isinstance(observations, Mapping) else None
        timestamp = captured_at if captured_at is not None else observed_at
        if (not _positive_timestamp(now) or not _positive_timestamp(observed_at)
                or not _positive_timestamp(timestamp)
                or (isinstance(observations, Mapping) and "captured_at" in observations and captured_at is None)
                or not observed_at <= timestamp <= now):
            return False
        entry = {
            "economics_id": evaluated["economics_id"],
            "snapshot": deepcopy(snapshot), "candidate": deepcopy(candidate),
            "inputs": deepcopy(inputs), "safety_margin_fraction": safety_margin_fraction,
            "stress": deepcopy(stress),
        }
        with _LOCK:
            existing, valid = self._read()
            if not valid or (existing and existing["profile_id"] != paths.current().label):
                return False
            if existing and self.snapshot(now=now)["status"] == "registro_invalido":
                return False
            if existing:
                previous = _record_timestamp(existing)
                if not _positive_timestamp(previous):
                    return False
                if timestamp < previous or (timestamp == previous
                                           and existing["snapshot_id"] != evaluated["snapshot_id"]):
                    return False
            if existing.get("snapshot_id") == evaluated["snapshot_id"]:
                if timestamp != _record_timestamp(existing) or observed_at != existing.get("observed_at"):
                    return False
                cases = existing["cases"]
                if any(not isinstance(row, dict) for row in cases):
                    return False
                if entry in cases:
                    return True
                portfolio = deepcopy(existing.get("portfolio"))
                if portfolio is not None:
                    # Coverage applies to the exact set reviewed by the planner.
                    portfolio["research_coverage_verified"] = False
                    portfolio.pop("research_case_ids", None)
                if len(cases) >= _MAX_SCENARIOS:
                    if not existing.get("research_storage_truncated", False) or portfolio != existing.get("portfolio"):
                        existing["portfolio"] = portfolio
                        existing["research_storage_truncated"] = True
                        try:
                            paths.write_atomic(self.path, json.dumps(existing, ensure_ascii=False, allow_nan=False),
                                               private=True)
                        except (OSError, TypeError, ValueError, OverflowError):
                            return False
                    return False
                cases = [*cases, entry]
                truncated = existing.get("research_storage_truncated", False)
            else:
                cases = [entry]
                portfolio = None
                truncated = False
            payload = {
                "schema_version": 1, "profile_id": paths.current().label,
                "snapshot_id": evaluated["snapshot_id"], "observed_at": observed_at,
                "cases": cases, "portfolio": portfolio, "research_storage_truncated": truncated,
            }
            if captured_at is not None:
                payload["captured_at"] = captured_at
            try:
                serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
                paths.write_atomic(self.path, serialized, private=True)
            except (OSError, TypeError, ValueError, OverflowError):
                return False
        return True

    def record_portfolio_evidence(self, *, snapshot_id: str,
                                  controls: Mapping[str, Any],
                                  hub_capacity: Mapping[str, Any],
                                  fleet_coverage_verified: bool = False,
                                  research_coverage_verified: bool = False,
                                  commitments_verified: bool = False,
                                  confidence_evidence: Mapping[str, Any] | None = None,
                                  diversification_evidence: Mapping[str, Any] | None = None) -> bool:
        """Persist separately sourced A4 proof, validated again at read time.

        The legacy hub_capacity field is retained for stored-record compatibility.
        The planner now requires the current company-wide passenger hangar capture.
        """
        if (not isinstance(controls, Mapping) or not isinstance(hub_capacity, Mapping)
                or not all(type(value) is bool for value in (
                    fleet_coverage_verified, research_coverage_verified, commitments_verified))
                or not isinstance(confidence_evidence or {}, Mapping)
                or not isinstance(diversification_evidence or {}, Mapping)):
            return False
        evidence = {
            "controls": deepcopy(dict(controls)),
            "hub_capacity": deepcopy(dict(hub_capacity)),
            "fleet_coverage_verified": fleet_coverage_verified,
            "research_coverage_verified": research_coverage_verified,
            "commitments_verified": commitments_verified,
            "confidence_evidence": deepcopy(dict(confidence_evidence or {})),
            "diversification_evidence": deepcopy(dict(diversification_evidence or {})),
        }
        with _LOCK:
            current, valid = self._read()
            if (not valid or not current or current["profile_id"] != paths.current().label
                    or current["snapshot_id"] != snapshot_id):
                return False
            if self.snapshot()["status"] == "registro_invalido":
                return False
            if research_coverage_verified and (not current["cases"] or current.get("research_storage_truncated", False)):
                return False
            if research_coverage_verified:
                evidence["research_case_ids"] = sorted(row["economics_id"] for row in current["cases"])
            current["portfolio"] = evidence
            try:
                paths.write_atomic(self.path, json.dumps(current, ensure_ascii=False, allow_nan=False), private=True)
            except (OSError, TypeError, ValueError, OverflowError):
                return False
        return True

    def snapshot(self, *, now: float | None = None) -> dict[str, Any]:
        """Re-evaluate saved provenance and expose partial coverage explicitly."""
        now = time.time() if now is None else now
        with _LOCK:
            stored, valid = self._read()
        profile_id = paths.current().label
        if not valid or (stored and (stored.get("profile_id") != profile_id
                                    or not _valid_record_times(stored, now))):
            return {"status": "registro_invalido", "snapshot_id": None,
                    "evaluations": [], "portfolio_evidence": {}, "read_only": True}
        results = []
        coverage_snapshot = None
        for entry in stored.get("cases", []):
            if not isinstance(entry, dict):
                return {"status": "registro_invalido", "snapshot_id": None,
                        "evaluations": [], "portfolio_evidence": {}, "read_only": True}
            try:
                source = entry["snapshot"]
                observed = source.get("observed_at")
                observations = source.get("observations")
                captured = observations.get("captured_at", observed) if isinstance(observations, Mapping) else observed
                if (not _positive_timestamp(observed) or not _positive_timestamp(captured)
                        or observed != stored.get("observed_at") or captured != _record_timestamp(stored)):
                    raise ValueError("Metadados temporais divergentes.")
                result = evaluate_expansion_economics(
                    entry["snapshot"], entry["candidate"], entry["inputs"], now=now,
                    safety_margin_fraction=entry["safety_margin_fraction"],
                    stress=entry.get("stress"),
                )
            except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
                return {"status": "registro_invalido", "snapshot_id": None,
                        "evaluations": [], "portfolio_evidence": {}, "read_only": True}
            if (result.get("economics_id") != entry.get("economics_id")
                    or result.get("profile_id") != profile_id
                    or result.get("snapshot_id") != stored.get("snapshot_id")):
                return {"status": "registro_invalido", "snapshot_id": None,
                        "evaluations": [], "portfolio_evidence": {}, "read_only": True}
            results.append(result)
            if coverage_snapshot is None and complete_coverage_snapshot(
                source, profile_id=profile_id, snapshot_id=stored["snapshot_id"], now=now
            ):
                coverage_snapshot = source
        portfolio = deepcopy(stored.get("portfolio") or {})
        portfolio.pop("coverage_snapshot", None)
        if portfolio.get("research_coverage_verified") is True:
            case_ids = sorted(result["economics_id"] for result in results)
            if (not results or stored.get("research_storage_truncated", False)
                    or portfolio.get("research_case_ids") != case_ids):
                portfolio["research_coverage_verified"] = False
        # Coverage depends on the original fingerprinted snapshot.
        if coverage_snapshot is not None:
            portfolio["coverage_snapshot"] = deepcopy(coverage_snapshot)
        elif portfolio:
            portfolio["fleet_coverage_verified"] = False
            portfolio["research_coverage_verified"] = False
        return {
            "status": "registrado" if results else "sem_avaliacoes",
            "snapshot_id": stored.get("snapshot_id"),
            "evaluations": results,
            "portfolio_evidence": portfolio,
            "read_only": True,
        }
