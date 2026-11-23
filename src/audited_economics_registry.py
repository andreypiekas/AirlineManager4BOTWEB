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


_LOCK = threading.RLock()
_MAX_SCENARIOS = 256


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
                or (payload.get("portfolio") is not None
                    and not isinstance(payload["portfolio"], dict))
                or len(payload["cases"]) > _MAX_SCENARIOS):
            return {}, False
        return payload, True

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
        timestamp = snapshot.get("observed_at") if isinstance(snapshot, Mapping) else None
        if (isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))
                or not math.isfinite(timestamp) or timestamp <= 0):
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
                previous = existing.get("observed_at")
                if (isinstance(previous, bool) or not isinstance(previous, (int, float))
                        or not math.isfinite(previous)):
                    return False
                if timestamp < previous or (timestamp == previous
                                           and existing["snapshot_id"] != evaluated["snapshot_id"]):
                    return False
            if existing.get("snapshot_id") == evaluated["snapshot_id"]:
                cases = existing["cases"]
                if any(not isinstance(row, dict) for row in cases):
                    return False
                if entry in cases:
                    return True
                if len(cases) >= _MAX_SCENARIOS:
                    return False
                cases = [*cases, entry]
                portfolio = existing.get("portfolio")
            else:
                cases = [entry]
                portfolio = None
            payload = {
                "schema_version": 1, "profile_id": paths.current().label,
                "snapshot_id": evaluated["snapshot_id"], "observed_at": timestamp,
                "cases": cases, "portfolio": portfolio,
            }
            try:
                serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
                paths.write_atomic(self.path, serialized)
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
        """Persist separately sourced A4 proof, validated again at read time."""
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
            current["portfolio"] = evidence
            try:
                paths.write_atomic(self.path, json.dumps(current, ensure_ascii=False, allow_nan=False))
            except (OSError, TypeError, ValueError, OverflowError):
                return False
        return True

    def snapshot(self, *, now: float | None = None) -> dict[str, Any]:
        """Re-evaluate saved provenance and expose partial coverage explicitly."""
        now = time.time() if now is None else now
        with _LOCK:
            stored, valid = self._read()
        profile_id = paths.current().label
        if not valid or (stored and stored.get("profile_id") != profile_id):
            return {"status": "registro_invalido", "snapshot_id": None,
                    "evaluations": [], "portfolio_evidence": {}, "read_only": True}
        results = []
        for entry in stored.get("cases", []):
            if not isinstance(entry, dict):
                return {"status": "registro_invalido", "snapshot_id": None,
                        "evaluations": [], "portfolio_evidence": {}, "read_only": True}
            try:
                result = evaluate_expansion_economics(
                    entry["snapshot"], entry["candidate"], entry["inputs"], now=now,
                    safety_margin_fraction=entry["safety_margin_fraction"],
                    stress=entry.get("stress"),
                )
            except (KeyError, TypeError, ValueError, OverflowError):
                return {"status": "registro_invalido", "snapshot_id": None,
                        "evaluations": [], "portfolio_evidence": {}, "read_only": True}
            if (result.get("economics_id") != entry.get("economics_id")
                    or result.get("profile_id") != profile_id
                    or result.get("snapshot_id") != stored.get("snapshot_id")):
                return {"status": "registro_invalido", "snapshot_id": None,
                        "evaluations": [], "portfolio_evidence": {}, "read_only": True}
            results.append(result)
        return {
            "status": "registrado" if stored else "sem_avaliacoes",
            "snapshot_id": stored.get("snapshot_id"),
            "evaluations": results,
            "portfolio_evidence": deepcopy(stored.get("portfolio") or {}),
            "read_only": True,
        }
