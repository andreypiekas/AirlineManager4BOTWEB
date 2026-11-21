"""Persistent per-profile aircraft/route registry and undirected duplicate detection.

Only confirmed actions, explicit game attributes or deliberate manual corrections
can change a route assignment. A missing aircraft on a paginated game page does
not prove removal. The registry is a cache/audit trail, not game authority.
"""
from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Optional

import paths
from airport_catalog import same_airport_identity

_LOCK = threading.RLock()
_MAX_HISTORY = 1500
_SCAN_WINDOW_SECONDS = 3600
_MAX_SCAN_PAGES = 250
_MAX_PAGE_AIRCRAFT = 40
_MAX_PAGES_PER_CYCLE = 5
_MAX_LIVE_AUDIT_PAGES = 25
_GAME_AIRCRAFT_ID_RE = re.compile(r"^[0-9]{1,14}$")
_AIRPORT_ID_RE = re.compile(r"^\d{1,12}$")
_IATA_RE = re.compile(r"^[A-Z]{3,4}$")
# The route-card DOM hook is a candidate until a reader supplies the exact,
# per-aircraft element evidence. Neither route endpoint is proof of home base.
HOME_HUB_EVIDENCE = "route_card:data-home-hub-id"


def registry_file() -> Path:
    return paths.current().data / "routes_registry.json"


def _normalize(raw: object) -> str:
    text = unicodedata.normalize("NFKD", str(raw or ""))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).strip().upper().split())


def endpoint(airport_id: object = "", code: object = "", name: object = "") -> dict:
    """Create a conservative endpoint identity, preferring game's stable airport ID."""
    ident = str(airport_id or "").strip()
    code_norm = _normalize(code)
    if not _AIRPORT_ID_RE.fullmatch(ident):
        ident = ""
    if not _IATA_RE.fullmatch(code_norm):
        code_norm = ""
    name_norm = _normalize(name)
    return {"id": ident, "code": code_norm, "name": str(name or "").strip(),
            "normalized_name": name_norm}


def endpoint_matches(a: dict, b: dict) -> bool:
    """Compare game IDs and verified IATA/ICAO aliases, never names when IDs conflict."""
    if a.get("id") and b.get("id"):
        return a["id"] == b["id"]
    if same_airport_identity(a, b):
        return True
    if (not a.get("id") and not b.get("id") and
            not a.get("code") and not b.get("code")):
        an, bn = a.get("normalized_name"), b.get("normalized_name")
        return bool(an and bn and an == bn)
    return False


def route_key(origin: dict, destination: dict) -> Optional[str]:
    """Canonical A↔B signature, independent of direction, only if both endpoints exist."""
    def code(value: dict) -> str:
        if value.get("id"):
            return "id:" + value["id"]
        if value.get("code"):
            return "code:" + value["code"]
        if value.get("normalized_name"):
            return "name:" + value["normalized_name"]
        return ""
    first, second = code(origin), code(destination)
    if not first or not second or first == second:
        return None
    return " ↔ ".join(sorted((first, second)))


def same_route(first: dict, second: dict) -> bool:
    a, b = first.get("origin", {}), first.get("destination", {})
    c, d = second.get("origin", {}), second.get("destination", {})
    return bool((endpoint_matches(a, c) and endpoint_matches(b, d)) or
                (endpoint_matches(a, d) and endpoint_matches(b, c)))


def reroute_block_reason(row: dict, now: Optional[float] = None,
                         *, verified_hub: bool = False) -> Optional[str]:
    """Return the exact reason a duplicate cannot be moved safely.

    The maintenance `at_base` flag means 'at a company base' and does not
    identify WHICH base; verified_hub merely establishes that an airport of
    the existing route appears in the player's hub selector. Neither is a
    proven, per-aircraft origin for a new routing action.
    """
    now = time.time() if now is None else now
    if row.get("source") != "game":
        return "rota_nao_confirmada_no_jogo"
    if row.get("at_base") is False:
        return "aeronave_fora_da_base"
    if row.get("at_base") is not True:
        return "localizacao_nao_confirmada"
    origin, destination = row.get("origin") or {}, row.get("destination") or {}
    both_ids = bool(origin.get("id") and destination.get("id"))
    verified_code_pair = bool(
        verified_hub and origin.get("code") and destination.get("code")
    )
    if not (both_ids or verified_code_pair):
        return "aeroportos_nao_confirmados"
    for stamp in ("game_verified_at", "grounded_confirmed_at"):
        recorded = row.get(stamp)
        if not isinstance(recorded, (int, float)):
            return "comprovacao_desatualizada"
        elapsed = now - recorded
        if elapsed < 0 or elapsed >= 180:
            return "comprovacao_desatualizada"
    return None


def eligible_for_reroute(row: dict, now: Optional[float] = None,
                         *, verified_hub: bool = False) -> bool:
    """Compatibility check for read-only planning. Not proof of safe live rerouting."""
    return reroute_block_reason(row, now, verified_hub=verified_hub) is None

def _state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "aircraft": {}, "history": []}
    if not isinstance(data, dict) or not isinstance(data.get("aircraft", {}), dict):
        return {"version": 1, "aircraft": {}, "history": []}
    data.setdefault("history", [])
    return data


class RouteRegistry:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else registry_file()

    def _save(self, data: dict) -> None:
        paths.write_atomic(self.path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))

    @staticmethod
    def _record_in(data: dict, aircraft_id: str, registration: str, model: str,
                   origin: dict, destination: dict, *, source: str = "game",
                   profit_per_day: Optional[float] = None, at_base: Optional[bool] = None,
                   stopover: Optional[dict] = None, now: int) -> None:
        previous = data["aircraft"].get(aircraft_id, {})
        entry = dict(previous)
        key = route_key(origin, destination)
        entry.update({
            "aircraft_id": aircraft_id,
            "registration": str(registration or previous.get("registration") or aircraft_id),
            "model": str(model or previous.get("model") or "?"),
            "origin": origin,
            "destination": destination,
            "route_key": key,
            "source": source,
            "status": "ativa" if previous.get("route_key") != key else previous.get("status", "ativa"),
            "last_seen": now,
        })
        if profit_per_day is not None:
            entry["profit_per_day"] = round(float(profit_per_day), 2)
            entry["profit_route_key"] = key
            entry["profit_estimated_at"] = now
        elif previous.get("route_key") != key:
            entry.pop("profit_per_day", None)
            entry.pop("profit_route_key", None)
            entry.pop("profit_estimated_at", None)
        if stopover is not None:
            entry["stopover"] = stopover
        if at_base is not None:
            entry["at_base"] = bool(at_base)
            if at_base and source == "game":
                entry["grounded_confirmed_at"] = now
            elif not at_base:
                entry.pop("grounded_confirmed_at", None)
        if source in ("game", "redirecionamento"):
            entry["game_verified_at"] = now
        if not previous or previous.get("route_key") != key:
            entry["assigned_at"] = now
            entry.pop("proposal", None)
            if stopover is None:
                entry.pop("stopover", None)
            data["history"].append({
                "at": now, "aircraft_id": aircraft_id,
                "registration": entry["registration"],
                "action": "rota_registrada" if not previous else "rota_alterada",
                "previous": previous.get("route_key"), "route": key, "source": source,
            })
            data["history"] = data["history"][-_MAX_HISTORY:]
        data["aircraft"][aircraft_id] = entry

    @staticmethod
    def _observe_in(data: dict, aircraft_id: str, registration: str, model: str,
                    at_base: Optional[bool], now: int) -> None:
        previous = data["aircraft"].get(aircraft_id, {})
        entry = dict(previous)
        entry.update({
            "aircraft_id": aircraft_id,
            "registration": str(registration or previous.get("registration") or aircraft_id),
            "model": str(model or previous.get("model") or "?"),
            "last_seen": now,
        })
        if not previous:
            entry["status"] = "rota_nao_identificada"
        if at_base is not None:
            entry["at_base"] = bool(at_base)
            if at_base:
                entry["grounded_confirmed_at"] = now
            else:
                entry.pop("grounded_confirmed_at", None)
        data["aircraft"][aircraft_id] = entry

    def record(self, aircraft_id: str, registration: str, model: str,
               origin: dict, destination: dict, *, source: str = "game",
               profit_per_day: Optional[float] = None, at_base: Optional[bool] = None,
               stopover: Optional[dict] = None) -> bool:
        """Record a verified route; never overwrite another aircraft's identity."""
        aircraft_id = str(aircraft_id or "").strip()
        if not aircraft_id or route_key(origin, destination) is None:
            return False
        with _LOCK:
            data = _state(self.path)
            self._record_in(data, aircraft_id, registration, model, origin, destination,
                            source=source, profit_per_day=profit_per_day, at_base=at_base,
                            stopover=stopover, now=int(time.time()))
            self._save(data)
            return True

    def observe(self, aircraft_id: str, registration: str = "", model: str = "",
                at_base: Optional[bool] = None) -> bool:
        """Register an aircraft seen on the current routes page even if no route can be verified."""
        aircraft_id = str(aircraft_id or "").strip()
        if not aircraft_id:
            return False
        with _LOCK:
            data = _state(self.path)
            self._observe_in(data, aircraft_id, registration, model, at_base, int(time.time()))
            self._save(data)
            return True

    def unassign(self, aircraft_id: str, registration: str = "", model: str = "") -> bool:
        """A verified entry in the game's 'without route' list clears stale assignment."""
        aircraft_id = str(aircraft_id or "").strip()
        if not aircraft_id:
            return False
        with _LOCK:
            data = _state(self.path)
            previous = data["aircraft"].get(aircraft_id, {})
            row = dict(previous)
            if previous.get("route_key"):
                data["history"].append({
                    "at": int(time.time()), "aircraft_id": aircraft_id,
                    "registration": registration or row.get("registration", ""),
                    "action": "rota_removida_no_jogo", "previous": row["route_key"],
                })
                data["history"] = data["history"][-_MAX_HISTORY:]
            for field in ("origin", "destination", "stopover", "route_key", "proposal", "profit_per_day",
                          "profit_route_key", "profit_estimated_at",
                          "game_verified_at"):
                row.pop(field, None)
            row.update({
                "aircraft_id": aircraft_id,
                "registration": registration or row.get("registration", aircraft_id),
                "model": model or row.get("model", "?"),
                "status": "sem_rota",
                "at_base": True,
                "last_seen": int(time.time()),
                "grounded_confirmed_at": int(time.time()),
            })
            data["aircraft"][aircraft_id] = row
            self._save(data)
            return True

    def retire_missing_assignment(self, aircraft_id: str, *, expected_route: str) -> bool:
        """Archive a route whose aircraft was confirmed absent from the live fleet."""
        with _LOCK:
            data = _state(self.path)
            row = data["aircraft"].get(aircraft_id)
            if not row or not expected_route or row.get("route_key") != expected_route:
                return False
            data["history"].append({
                "at": int(time.time()), "aircraft_id": aircraft_id,
                "registration": row.get("registration", aircraft_id),
                "action": "aeronave_fora_da_frota", "previous": expected_route,
            })
            data["history"] = data["history"][-_MAX_HISTORY:]
            del data["aircraft"][aircraft_id]
            self._save(data)
            return True

    def mark_plan_attempt(self, aircraft_id: str) -> bool:
        """Rotate planning fairly even for aircraft with no viable alternative.

        Only the attempted aircraft is timestamped. Deferred rows retain their
        old priority, so an impossible route does not starve the entire queue.
        """
        with _LOCK:
            data = _state(self.path)
            entry = data["aircraft"].get(str(aircraft_id))
            if not entry:
                return False
            entry["last_planned_at"] = int(time.time())
            self._save(data)
            return True

    def note(self, aircraft_id: str, status: str, *, proposal: Optional[dict] = None) -> bool:
        """Save reroute status/profit proposal without changing the verified route."""
        with _LOCK:
            data = _state(self.path)
            entry = data["aircraft"].get(str(aircraft_id))
            if not entry:
                return False
            changed = entry.get("status") != status or entry.get("proposal") != proposal
            if not changed:
                return True
            entry["status"] = status
            if proposal is None:
                entry.pop("proposal", None)
            else:
                entry["proposal"] = proposal
            data["history"].append({
                "at": int(time.time()), "aircraft_id": str(aircraft_id),
                "registration": entry.get("registration", ""),
                "action": status, "proposal": proposal,
            })
            data["history"] = data["history"][-_MAX_HISTORY:]
            self._save(data)
            return True

    def record_scan(self, visible: int, identified: int, missing_airports: int, *,
                    aircraft_ids: Optional[list[str]] = None,
                    page: Optional[int] = None,
                    total_pages: Optional[int] = None,
                    expected_routes: Optional[int] = None,
                    audit_run_id: Optional[str] = None,
                    route_observations: Optional[list[dict]] = None) -> int:
        """Persist the audit outcome even if no aircraft route was identified.

        When route observations are supplied, update the visible aircraft and
        scan coverage in one atomic file write. Without them, preserve existing
        assignments. Coverage remains a rolling, partial observation.
        """
        with _LOCK:
            data = _state(self.path)
            now = int(time.time())
            if route_observations is not None:
                identified = 0
                processed: set[str] = set()
                for row in route_observations:
                    if not isinstance(row, dict):
                        continue
                    identity = str(row.get("aircraft_id") or "").strip()
                    if not _GAME_AIRCRAFT_ID_RE.fullmatch(identity) or identity in processed:
                        continue
                    processed.add(identity)
                    registration = row.get("registration") or identity
                    model = row.get("model") or ""
                    origin = row.get("origin") or {}
                    destination = row.get("destination") or {}
                    at_base = row.get("at_base")
                    if route_key(origin, destination) is not None:
                        self._record_in(data, identity, registration, model, origin, destination,
                                        at_base=at_base, now=now)
                        identified += 1
                    else:
                        self._observe_in(data, identity, registration, model, at_base, now)
                    home = str(row.get("home_hub_id") or "").strip()
                    if re.fullmatch(r"[1-9][0-9]{0,11}", home):
                        entry = data["aircraft"][identity]
                        proven_before = entry.get("home_hub_evidence") == HOME_HUB_EVIDENCE
                        if proven_before and entry.get("home_hub_id") != home:
                            # A conflicting observation cannot silently replace
                            # a previously proven, permanent aircraft assignment.
                            entry["home_hub_conflict_id"] = home
                            entry["home_hub_conflict_at"] = now
                            continue
                        if entry.get("home_hub_id") != home:
                            for key in ("home_hub_verified_at", "home_hub_evidence",
                                        "home_hub_evidence_aircraft_id"):
                                entry.pop(key, None)
                        entry["home_hub_id"] = home
                        entry["home_hub_source"] = "game"
                        entry["home_hub_observed_at"] = now
                        if (row.get("home_hub_evidence") == HOME_HUB_EVIDENCE
                                and row.get("home_hub_evidence_aircraft_id") == identity):
                            entry["home_hub_evidence"] = HOME_HUB_EVIDENCE
                            entry["home_hub_evidence_aircraft_id"] = identity
                            entry["home_hub_verified_at"] = now
            data["last_scan"] = {
                "at": now,
                "visible": max(0, int(visible)),
                "identified": max(0, int(identified)),
                "missing_airports": max(0, int(missing_airports)),
            }
            if aircraft_ids is not None:
                page = self._valid_page(page)
                total_pages = self._valid_page(total_pages)
                if type(expected_routes) is not int or not 0 < expected_routes <= 50000:
                    expected_routes = None
                if not isinstance(audit_run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", audit_run_id):
                    audit_run_id = None
                if total_pages and page and page > total_pages:
                    page = None
                coverage = data.get("scan_coverage")
                updated_at = coverage.get("updated_at") if isinstance(coverage, dict) else None
                if not isinstance(updated_at, (int, float)) or now < updated_at or \
                        now - updated_at >= _SCAN_WINDOW_SECONDS or \
                        (total_pages and coverage.get("total_pages") not in (None, total_pages)) or \
                        coverage.get("expected_routes") != expected_routes:
                    coverage = {"pages": {}, "sequence": 0, "total_pages": total_pages,
                                "expected_routes": expected_routes}
                pages = coverage.get("pages")
                if not isinstance(pages, dict):
                    pages = {}
                pages = {
                    number: entry for number, entry in pages.items()
                    if isinstance(entry, dict) and isinstance(entry.get("at"), (int, float))
                    and 0 <= now - entry["at"] < _SCAN_WINDOW_SECONDS
                    and number.isdigit() and 1 <= int(number) <= _MAX_SCAN_PAGES
                }
                if total_pages:
                    coverage["total_pages"] = total_pages
                recorded_ids = list(dict.fromkeys(
                    str(aircraft_id).strip() for aircraft_id in aircraft_ids
                    if _GAME_AIRCRAFT_ID_RE.fullmatch(str(aircraft_id).strip())
                ))[:_MAX_PAGE_AIRCRAFT]
                observation = {
                    **data["last_scan"], "aircraft_ids": recorded_ids,
                }
                if audit_run_id:
                    observation["audit_run_id"] = audit_run_id
                if page:
                    coverage["sequence"] = max(0, int(coverage.get("sequence") or 0)) + 1
                    observation["sequence"] = coverage["sequence"]
                    pages[str(page)] = observation
                else:
                    coverage["unknown_page"] = observation
                coverage["pages"] = pages
                all_ids = {
                    aircraft_id for entry in pages.values()
                    for aircraft_id in entry.get("aircraft_ids", [])
                }
                page_rows = [pages.get(str(number)) for number in range(1, (total_pages or 0) + 1)]
                combined_ids = [aircraft_id for entry in pages.values()
                                for aircraft_id in entry.get("aircraft_ids", [])]
                repeated_ids = len(combined_ids) - len(set(combined_ids))
                complete = (audit_run_id is not None and expected_routes is not None
                            and total_pages is not None
                            and len(pages) == total_pages and repeated_ids == 0
                            and len(combined_ids) == expected_routes
                            and total_pages == (expected_routes + 19) // 20
                            and all(isinstance(entry, dict)
                                    and entry.get("audit_run_id") == audit_run_id
                                    and 0 < entry.get("visible", 0) <= 20
                                    and len(entry.get("aircraft_ids", [])) == entry["visible"]
                                    for entry in page_rows))
                if complete:
                    data["last_verified_full_audit"] = {
                        "at": now, "audit_run_id": audit_run_id,
                        "expected_routes": expected_routes,
                        "total_pages": total_pages, "unique_aircraft": len(combined_ids),
                    }
                unknown = coverage.get("unknown_page")
                unknown_at = unknown.get("at") if isinstance(unknown, dict) else None
                if isinstance(unknown_at, (int, float)) and \
                        0 <= now - unknown_at < _SCAN_WINDOW_SECONDS:
                    all_ids.update(unknown.get("aircraft_ids", []))
                else:
                    coverage.pop("unknown_page", None)
                coverage.update({
                    "updated_at": now,
                    "window_seconds": _SCAN_WINDOW_SECONDS,
                    "observed_pages": len(pages),
                    "unique_aircraft": len(all_ids),
                    "expected_routes": expected_routes,
                    "repeated_aircraft_across_pages": repeated_ids,
                    "full_page_coverage_verified": complete,
                    "partial": True,
                })
                data["scan_coverage"] = coverage
            self._save(data)
            return identified

    @staticmethod
    def _valid_page(raw: object) -> Optional[int]:
        if isinstance(raw, bool) or not re.fullmatch(r"[1-9][0-9]{0,2}", str(raw or "")):
            return None
        number = int(raw)
        return number if number <= _MAX_SCAN_PAGES else None

    def next_scan_pages(self, total_pages: int, *, limit: int = 2,
                        max_pages: int = _MAX_PAGES_PER_CYCLE) -> list[int]:
        """Choose the least recently observed pages without clearing the roster.

        A page number is only a position in a changing list. Callers must
        verify which page actually loaded before recording its observations.
        """
        total = self._valid_page(total_pages)
        if total is None or limit <= 0:
            return []
        count = min(int(limit), max(0, int(max_pages)), _MAX_LIVE_AUDIT_PAGES, total)
        with _LOCK:
            coverage = _state(self.path).get("scan_coverage") or {}
        pages = coverage.get("pages", {}) if coverage.get("total_pages") == total else {}
        if not isinstance(pages, dict):
            pages = {}
        now = int(time.time())

        def freshness(page: int) -> tuple[int, int]:
            entry = pages.get(str(page)) or {}
            observed_at = entry.get("at") if isinstance(entry, dict) else None
            if not isinstance(observed_at, (int, float)) or \
                    now < observed_at or now - observed_at >= _SCAN_WINDOW_SECONDS:
                return 0, page
            return max(0, int(entry.get("sequence") or 0)), page

        return sorted(range(1, total + 1), key=freshness)[:count]

    def claim_experimental_departure(self, aircraft_id: str) -> bool:
        """One-shot pilot interlock across cycles/restarts, never auto-reset.

        A crash or timeout after issuing a game order must not lead to
        repeated departures. Claim is persisted *before* the network call.
        """
        if not re.fullmatch(r"[0-9]{1,14}", str(aircraft_id or "")):
            return False
        with _LOCK:
            data = _state(self.path)
            if data.get("experimental_departure_pilot"):
                return False
            data["experimental_departure_pilot"] = {
                "at": int(time.time()),
                "aircraft_id": str(aircraft_id),
                "status": "claimed_before_request",
            }
            self._save(data)
            return True

    def finish_experimental_departure(self, aircraft_id: str, status: str) -> bool:
        """Record confirmation or uncertainty; the one-shot latch stays armed."""
        with _LOCK:
            data = _state(self.path)
            pilot = data.get("experimental_departure_pilot")
            if not isinstance(pilot, dict) or pilot.get("aircraft_id") != str(aircraft_id):
                return False
            pilot["status"] = str(status)[:100]
            pilot["finished_at"] = int(time.time())
            self._save(data)
            return True

    def record_dispatch_summary(self, summary: dict) -> None:
        """Persist a bounded dispatch decision summary for the read-only panel."""
        safe = {
            "at": int(summary.get("at") or time.time()),
            "ready_seen": max(0, int(summary.get("ready_seen") or 0)),
            "approved": max(0, int(summary.get("approved") or 0)),
            "blocked": max(0, int(summary.get("blocked") or 0)),
            "native_individual": max(0, int(summary.get("native_individual") or 0)),
            "not_supported": max(0, int(summary.get("not_supported") or 0)),
            "departed": max(0, int(summary.get("departed") or 0)),
            "rejected": max(0, int(summary.get("rejected") or 0)),
            "status": str(summary.get("status") or "")[:80],
            "target_id": str(summary.get("target_id") or "")[:20],
            "mode": str(summary.get("mode") or "seletivo")[:24],
            "simulation": bool(summary.get("simulation", False)),
            "duplicates_known": max(0, int(summary.get("duplicates_known") or 0)),
            "blocked_aircraft": [
                {
                    "id": str(row.get("id") or "")[:20],
                    "registration": str(row.get("registration") or "")[:60],
                    "reason": str(row.get("reason") or "")[:90],
                }
                for row in (summary.get("blocked_aircraft") or [])[:40]
                if isinstance(row, dict)
            ],
        }
        with _LOCK:
            data = _state(self.path)
            data["last_dispatch"] = safe
            self._save(data)

    def snapshot(self, *, allow_duplicates: bool = True) -> dict:
        with _LOCK:
            data = deepcopy(_state(self.path))
        rows = list(data["aircraft"].values())
        rows.sort(key=lambda r: (r.get("registration", ""), r.get("aircraft_id", "")))
        duplicates: list[list[dict]] = []
        visited: set[str] = set()
        for row in rows:
            identity = row.get("aircraft_id", "")
            if identity in visited or not route_key(row.get("origin", {}), row.get("destination", {})):
                continue
            group = [other for other in rows if same_route(row, other)]
            if len(group) > 1:
                duplicates.append(group)
                visited.update(entry["aircraft_id"] for entry in group)
        duplicate_ids = {entry["aircraft_id"] for group in duplicates for entry in group}
        for row in rows:
            row["duplicate"] = row.get("aircraft_id") in duplicate_ids
        return {
            "relations": rows,
            "duplicates": [{"route": group[0].get("route_key"), "aircraft": [
                {"id": r.get("aircraft_id"), "registration": r.get("registration")} for r in group
            ]} for group in duplicates],
            "history": data["history"][-80:][::-1],
            "total": len(rows), "duplicate_routes": len(duplicates),
            "affected_aircraft": len(duplicate_ids),
            "allow_duplicates": bool(allow_duplicates),
            "last_scan": data.get("last_scan"),
            "scan_coverage": data.get("scan_coverage"),
            "last_verified_full_audit": data.get("last_verified_full_audit"),
            "last_dispatch": data.get("last_dispatch"),
            "experimental_departure_pilot": data.get("experimental_departure_pilot"),
            "partial": True,  # the game may expose only a page of the fleet at a time
        }

    def is_occupied(self, origin: dict, destination: dict, except_aircraft: str = "") -> bool:
        if route_key(origin, destination) is None:
            return False
        with _LOCK:
            records = _state(self.path)["aircraft"].values()
        return any(
            str(row.get("aircraft_id")) != str(except_aircraft)
            and same_route({"origin": origin, "destination": destination}, row)
            for row in records
        )
