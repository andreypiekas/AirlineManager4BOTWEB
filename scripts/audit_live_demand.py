"""Measure the official AM4 route research API against a native airport catalog."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, build_opener

if __package__:
    from .audit_bulk_demand import native_scope
else:
    from audit_bulk_demand import native_scope

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from airport_catalog import by_code, by_id  # noqa: E402

ENDPOINT = "https://www.airlinemanager.com/api"
DAILY_LIMIT = 500
MAX_SECONDS = 900
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
DEMAND_FIELDS = ("economy_class_demand", "business_class_demand", "first_class_demand")


class AuditError(Exception):
    """Fixed diagnostic safe to print without the request URL or response body."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request_research(opener, token, icao, deadline):
    query = urlencode({
        "access_token": token,
        "fields": "research",
        "dep_icao": icao,
        "min_runway": 0,
        "max_distance": 21000,
    })
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AuditError("deadline")
    try:
        body = bytearray()
        with opener.open(f"{ENDPOINT}?{query}", timeout=min(remaining, 8)) as response:
            while chunk := response.read1(64 * 1024):
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise AuditError("response_too_large")
                if time.monotonic() >= deadline:
                    raise AuditError("deadline")
        return json.loads(body)
    except HTTPError as error:
        error.close()
        raise AuditError(f"http_{error.code}") from None
    except (OSError, ValueError):
        raise AuditError("unavailable_or_invalid_json") from None


def decode_research(payload, origin, destinations):
    status = payload.get("status") if isinstance(payload, dict) else None
    if not isinstance(status, dict) or status.get("request") != "success":
        raise AuditError("api_rejected")
    quota = status.get("requests_remaining")
    if type(quota) is not int or quota < 0:
        raise AuditError("unknown_quota")
    route = payload.get("route")
    rows = route.get("data") if isinstance(route, dict) else None
    if not isinstance(rows, list):
        raise AuditError("missing_route_data")

    accepted, ambiguous = {}, set()
    rejected = 0
    for row in rows:
        if not isinstance(row, dict):
            rejected += 1
            continue
        code = row.get("icao")
        airport = by_code(code) if isinstance(code, str) else None
        destination = int(airport.game_id) if airport is not None else None
        if (airport is None or code != airport.icao or row.get("iata") != airport.iata
                or destination == origin or destination not in destinations):
            rejected += 1
            continue
        if destination in accepted or destination in ambiguous:
            accepted.pop(destination, None)
            ambiguous.add(destination)
            continue
        demand = tuple(row.get(key) for key in DEMAND_FIELDS)
        if any(type(value) is not int or value < 0 for value in demand):
            rejected += 1
            ambiguous.add(destination)
            continue
        accepted[destination] = demand
    return accepted, quota, len(rows) - len(accepted) - rejected, rejected


def collect(snapshot, external_codes, fetch, *, started, seconds, writer=None):
    if not isinstance(snapshot, dict) or snapshot.get("source") != "game_snapshot" or snapshot.get("verified") is not True:
        raise AuditError("native_snapshot_unverified")
    owned, airport_ids = native_scope(snapshot)
    destinations = set(airport_ids)
    airport_codes = {}
    for game_id in airport_ids:
        airport = by_id(game_id)
        if airport is not None and by_code(airport.icao) == airport:
            airport_codes[game_id] = airport
    external = set()
    for code in external_codes:
        airport = by_code(code)
        if airport is None or airport.icao != code:
            raise AuditError("unknown_external_icao")
        game_id = int(airport.game_id)
        if game_id not in destinations or game_id in owned:
            raise AuditError("external_icao_outside_requested_scope")
        external.add(game_id)
    origins = owned + sorted(external)
    if len(origins) > DAILY_LIMIT:
        raise AuditError("requested_origins_exceed_daily_quota")

    deadline = started + seconds
    owned_codes = {int(hub["id"]): hub.get("code") for hub in snapshot["hubs"]
                   if hub["owned"] is True and hub["verified"] is True}
    counts = Counter()
    errors = {}
    quota = None
    for origin in origins:
        if time.monotonic() >= deadline or quota == 0:
            break
        airport = airport_codes.get(origin)
        native_code = owned_codes.get(origin)
        if airport is None or (origin in owned_codes and native_code not in (airport.iata, airport.icao)):
            errors[origin] = "origin_code_unverified"
            continue
        counts["requests"] += 1
        try:
            payload = fetch(airport.icao, deadline)
            values, quota, repeated, rejected = decode_research(payload, origin, destinations)
        except AuditError as error:
            errors[origin] = str(error)
            break
        counts["queried_origins"] += 1
        scope = "external" if origin in external else "owned"
        counts[f"{scope}_pairs"] += len(values)
        counts["origins_with_all_pairs"] += len(values) == len(destinations) - 1
        counts["repeated_rows"] += repeated
        counts["rejected_rows"] += rejected
        if writer is not None:
            writer.writerows((origin, destination, *demand) for destination, demand in sorted(values.items()))

    elapsed = time.monotonic() - started
    owned_expected = len(owned) * (len(destinations) - 1)
    external_expected = len(external) * (len(destinations) - 1)
    coverage = (counts["origins_with_all_pairs"] == len(origins)
                and not counts["repeated_rows"] and not counts["rejected_rows"])
    return {
        "source": "am4_official_api_research", "snapshot_id": snapshot.get("snapshot_id"),
        "verified": False, "execution_available": False,
        "residual_today_available": False, "native_crosscheck_required": True,
        "owned_origins": len(owned), "external_origins_requested": len(external),
        "global_external_origins": len(destinations) - len(owned),
        "unqueried_origins": len(origins) - counts["queried_origins"],
        "requests": counts["requests"], "requests_remaining": quota,
        "owned_pairs": counts["owned_pairs"], "owned_expected_pairs": owned_expected,
        "external_pairs": counts["external_pairs"], "external_expected_pairs": external_expected,
        "global_external_expected_pairs": (len(destinations) - len(owned)) * (len(destinations) - 1),
        "unmapped_airport_ids": sorted(destinations - airport_codes.keys()),
        "repeated_rows": counts["repeated_rows"], "rejected_rows": counts["rejected_rows"],
        "origin_errors": errors, "requested_scope_complete": coverage,
        "seconds": round(elapsed, 3), "within_budget": elapsed <= seconds,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="Snapshot auditado do Chrome dedicado")
    parser.add_argument("--seconds", type=int, default=MAX_SECONDS, choices=range(1, MAX_SECONDS + 1),
                        metavar="1..900", help="Orçamento de tempo em segundos")
    parser.add_argument("--external-origin", type=str.upper, action="append", default=[], metavar="ICAO",
                        help="Origem externa adicional do catálogo auditado. Pode ser repetida")
    parser.add_argument("--export", type=Path, help="Gravar pares observados em um novo CSV local")
    args = parser.parse_args()
    token = os.environ.get("AM4_API_ACCESS_TOKEN", "").strip()
    if not token:
        parser.exit(2, "Configure AM4_API_ACCESS_TOKEN no ambiente do processo.\n")

    started = time.monotonic()
    opener = build_opener(NoRedirect())

    def fetch(icao, deadline):
        return request_research(opener, token, icao, deadline)

    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        if args.export is None:
            result = collect(snapshot, args.external_origin, fetch, started=started, seconds=args.seconds)
        else:
            with args.export.open("x", encoding="utf-8", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(("origin_id", "destination_id", "api_demand_y", "api_demand_j", "api_demand_f"))
                result = collect(snapshot, args.external_origin, fetch, started=started, seconds=args.seconds,
                                 writer=writer)
    except AuditError as error:
        parser.exit(2, f"Falha na auditoria oficial: {error}\n")
    except (AttributeError, OSError, KeyError, TypeError, ValueError):
        parser.exit(2, "Catálogo ou destino de exportação inválido.\n")

    print(json.dumps(result))
    return 0 if result["requested_scope_complete"] and result["within_budget"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
