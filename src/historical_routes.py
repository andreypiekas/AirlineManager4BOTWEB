"""Profile-local cache for the community's historical passenger demand matrix."""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

import paths

REVISION = "795aaa4be38dc4bb4216d5ea6506896921dff2ae"
MAX_RESULTS = 25


class HistoricalRoutes:
    def __init__(self, database: Path | None = None):
        self.path = database if database is not None else paths.current().data / "am4_historical_routes.sqlite3"

    def install(self, airports, routes, expected_pairs: int) -> None:
        """Publish a complete import, preserving the previous database on failure."""
        if expected_pairs <= 0 or len(routes) != expected_pairs:
            raise ValueError("O catálogo histórico está incompleto para este perfil.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=self.path.parent) as workspace:
            staged = Path(workspace) / self.path.name
            with closing(sqlite3.connect(staged)) as conn, conn:
                conn.execute("PRAGMA foreign_keys = ON")
                conn.executescript("""
                    CREATE TABLE airports (
                        id INTEGER PRIMARY KEY, iata TEXT, icao TEXT,
                        name TEXT NOT NULL, runway_ft INTEGER NOT NULL CHECK (runway_ft >= 0)
                    );
                    CREATE TABLE routes (
                        origin_id INTEGER NOT NULL REFERENCES airports(id),
                        destination_id INTEGER NOT NULL REFERENCES airports(id),
                        y INTEGER NOT NULL CHECK (y >= 0), j INTEGER NOT NULL CHECK (j >= 0),
                        f INTEGER NOT NULL CHECK (f >= 0),
                        distance_km REAL NOT NULL CHECK (distance_km > 0),
                        PRIMARY KEY (origin_id, destination_id),
                        CHECK (origin_id <> destination_id)
                    ) WITHOUT ROWID;
                    CREATE TABLE source (revision TEXT NOT NULL, pair_count INTEGER NOT NULL);
                """)
                conn.executemany("INSERT INTO airports VALUES (?, ?, ?, ?, ?)", airports)
                conn.executemany("INSERT INTO routes VALUES (?, ?, ?, ?, ?, ?)", routes)
                conn.execute("INSERT INTO source VALUES (?, ?)", (REVISION, expected_pairs))
            os.replace(staged, self.path)

    def report(
        self, *, origin_id: int | None = None, max_km: int = 20000, min_runway_ft: int = 0,
        min_y: int = 0, min_j: int = 0, min_f: int = 0,
    ) -> dict:
        report = {
            "available": False, "source": "am4_community_historical_matrix",
            "data_year": 2020, "verified": False, "execution_available": False,
            "origin_id": origin_id, "origins": [], "candidates": [],
        }
        if not self.path.is_file():
            return report
        uri = self.path.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            source = conn.execute("SELECT revision, pair_count FROM source").fetchone()
            if source is None or source["revision"] != REVISION:
                return report
            origins = [dict(row) for row in conn.execute("""
                SELECT id, iata, icao, name FROM airports
                WHERE id IN (SELECT DISTINCT origin_id FROM routes)
                ORDER BY COALESCE(NULLIF(iata, ''), icao), name, id
            """)]
            if origin_id is not None and not any(origin["id"] == origin_id for origin in origins):
                raise ValueError("Selecione um hub da captura auditada.")
            candidates = [dict(row) for row in conn.execute("""
                SELECT a.id, a.iata, a.icao, a.name, a.runway_ft, r.y, r.j, r.f, r.distance_km
                FROM routes AS r JOIN airports AS a ON a.id = r.destination_id
                WHERE r.origin_id = ? AND r.distance_km <= ? AND a.runway_ft >= ?
                    AND r.y >= ? AND r.j >= ? AND r.f >= ?
                ORDER BY (r.y + r.j + r.f) DESC, r.distance_km, a.id
                LIMIT ?
            """, (origin_id, max_km, min_runway_ft, min_y, min_j, min_f, MAX_RESULTS))]
            report.update(source, available=True, origins=origins, candidates=candidates)
            return report
