"""Screen the native airport catalog against a pinned historical AM4 matrix.

Requires DuckDB for the import. The matrix is never used as verified route
demand or a purchase input.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

DATASET_FILES = {
    "airports.parquet": "93842f6b6aea3c140ec92984b2050ba58cb294bade3336ff97e97046795daf41",
    "routes.parquet": "b43b2ca296f55e827171b950a9a868e095ea12f3477cee0d55d5cd8130a3c4a0",
}
SOURCE = "am4_community_historical_matrix"


def native_scope(snapshot):
    universe = snapshot["observations"]["route_search_universe"]
    catalog = universe["destination_catalog"]
    menus = universe["country_values_by_origin"]
    hubs = [hub["id"] for hub in snapshot["hubs"]
            if hub["owned"] is True and hub["verified"] is True]
    airports = [airport for group in catalog["airport_ids_by_country"].values()
                for airport in group]
    if (catalog["source"] != "game_route_arrival_selectors_and_map"
            or universe["source"] != "game_owned_route_search_menus"
            or not hubs or set(hubs) != menus.keys() or not set(hubs) <= set(airports)
            or len(set(hubs)) != len(hubs) or len(set(airports)) != len(airports)
            or len(airports) != catalog["airport_count"]
            or len(hubs) * (len(airports) - 1) != catalog["owned_origin_destination_pairs"]):
        raise ValueError("Catálogo de origens e destinos inconsistente no snapshot.")
    return sorted(map(int, hubs)), sorted(map(int, airports))


def dataset_file(directory, name):
    path = directory / name
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != DATASET_FILES[name]:
        raise ValueError(f"{name} diverge da revisão auditada.")
    return str(path)


def scan_matrix(directory, origins, destinations):
    import duckdb

    airports_file = dataset_file(directory, "airports.parquet")
    routes_file = dataset_file(directory, "routes.parquet")
    with duckdb.connect() as conn:
        indexed = conn.execute(
            "SELECT id, file_row_number FROM read_parquet(?, file_row_number = true)",
            [airports_file],
        ).fetchall()
        dataset_ids = {airport for airport, _ in indexed}
        size = len(indexed)
        if size != len(dataset_ids):
            raise ValueError("Matriz com índice de aeroportos ambíguo.")
        routes_count, complete_count = conn.execute("""
            SELECT count(*), count(*) FILTER (
                WHERE yd IS NOT NULL AND jd IS NOT NULL AND fd IS NOT NULL AND d > 0 AND isfinite(d)
            )
            FROM read_parquet(?)
            """, [routes_file]).fetchone()
        if routes_count != size * (size - 1) // 2:
            raise ValueError("Número de linhas incompatível com o índice triangular da matriz.")
        full_native_matrix = dataset_ids == set(destinations) and complete_count == routes_count
        # The upstream loader indexes the upper triangle in file order.
        rows = conn.execute("""
            WITH airports AS (
                SELECT id, file_row_number AS idx FROM read_parquet(?, file_row_number = true)
            ), indices AS (
                SELECT a.id AS origin, b.id AS destination,
                       least(a.idx, b.idx) AS lo, greatest(a.idx, b.idx) AS hi
                FROM airports a CROSS JOIN airports b
                WHERE a.id IN (SELECT unnest(?)) AND b.id IN (SELECT unnest(?)) AND a.id <> b.id
            )
            SELECT origin, destination, yd, jd, fd, d
            FROM indices
            JOIN read_parquet(?, file_row_number = true) AS routes
              ON routes.file_row_number = lo * (2 * ? - lo - 1) // 2 + hi - lo - 1
            WHERE yd IS NOT NULL AND jd IS NOT NULL AND fd IS NOT NULL AND d > 0 AND isfinite(d)
            ORDER BY origin, destination
            """, [airports_file, origins, destinations, routes_file, size]).fetchall()
    return rows, full_native_matrix


def install_for_profile(directory, profile_name, snapshot, rows, expected):
    import duckdb

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    import paths
    from historical_routes import HistoricalRoutes

    if profile_name != paths.MAIN_LABEL and not paths.valid_name(profile_name):
        raise ValueError("Nome de perfil inválido.")
    profile = paths.activate(profile_name)
    if not profile.exists():
        raise ValueError("Perfil inexistente.")
    if snapshot["profile_id"] != profile.label or snapshot["schema_version"] != 1:
        raise ValueError("Perfil ou versão incompatível no snapshot auditado.")
    with duckdb.connect() as conn:
        airports = conn.execute("""
            SELECT id, iata, icao, COALESCE(fullname, name), rwy FROM read_parquet(?)
        """, [dataset_file(directory, "airports.parquet")]).fetchall()
    HistoricalRoutes(profile.data / "am4_historical_routes.sqlite3").install(airports, rows, expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="Snapshot auditado do worker")
    parser.add_argument("dataset", type=Path, help="Diretório com os dois arquivos Parquet da revisão auditada")
    parser.add_argument("--export", type=Path, help="Gravar candidatos históricos em um novo CSV")
    parser.add_argument("--install-profile", metavar="PERFIL", help="Instalar a matriz para a pesquisa em Hubs")
    args = parser.parse_args()
    try:
        import duckdb
    except ImportError:
        parser.exit(2, "Instale DuckDB para executar a triagem histórica.\n")
    started = time.monotonic()
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        origins, destinations = native_scope(snapshot)
        rows, full_native_matrix = scan_matrix(args.dataset, origins, destinations)
        expected = len(origins) * (len(destinations) - 1)
        if args.install_profile is not None:
            install_for_profile(args.dataset, args.install_profile, snapshot, rows, expected)
        if args.export is not None:
            with args.export.open("x", encoding="utf-8", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(("origin_id", "destination_id", "historical_daily_y",
                                 "historical_daily_j", "historical_daily_f", "historical_distance_km"))
                writer.writerows(rows)
    except (OSError, TypeError, ValueError, KeyError, duckdb.Error, sqlite3.Error) as error:
        parser.exit(2, f"Falha na triagem histórica: {error}\n")
    print(json.dumps({
        "source": SOURCE,
        "verified": False,
        "execution_available": False,
        "origin_count": len(origins),
        "destination_count": len(destinations),
        "historical_pairs_found": len(rows),
        "expected_pairs": expected,
        "unmatched_pairs": expected - len(rows),
        "installed_profile": args.install_profile,
        "external_origin_count": len(destinations) - len(origins),
        "historical_external_origin_pairs": (
            (len(destinations) - len(origins)) * (len(destinations) - 1) if full_native_matrix else None
        ),
        "seconds": round(time.monotonic() - started, 3),
    }))
    return int(len(rows) != expected)


if __name__ == "__main__":
    raise SystemExit(main())
