"""Durable queue and observed Daily demand from the native AM4 search."""
from __future__ import annotations

import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import paths
from opportunity_models import DEFAULT_MAX_AGE_SECONDS

_ID = re.compile(r"[1-9][0-9]{0,11}")
_COMPANY_ID = re.compile(r"[1-9][0-9]{0,13}")
_ACTIVE = ("queued", "running")
_ATTEMPTS = 2
_SCHEMA = """
CREATE TABLE IF NOT EXISTS scan (
    id INTEGER PRIMARY KEY CHECK (id = 1), state TEXT NOT NULL,
    company_id TEXT, updated_at REAL NOT NULL, error TEXT
);
CREATE TABLE IF NOT EXISTS partitions (
    origin_id TEXT NOT NULL, country TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'open', attempts INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (origin_id, country)
);
CREATE TABLE IF NOT EXISTS targets (
    origin_id TEXT NOT NULL, country TEXT NOT NULL, destination_id TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'open', attempts INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (origin_id, destination_id)
);
CREATE INDEX IF NOT EXISTS partition_queue ON partitions (state, attempts, origin_id, country);
CREATE INDEX IF NOT EXISTS target_queue ON targets (state, attempts, origin_id, country, destination_id);
CREATE INDEX IF NOT EXISTS target_partition ON targets (origin_id, country);
CREATE TABLE IF NOT EXISTS demand (
    origin_id TEXT NOT NULL, destination_id TEXT NOT NULL,
    y INTEGER NOT NULL, j INTEGER NOT NULL, f INTEGER NOT NULL,
    distance_km REAL, runway_ft INTEGER,
    event_demand_boosted INTEGER, observed_at REAL NOT NULL,
    PRIMARY KEY (origin_id, destination_id)
);
"""


def _valid_id(value):
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def demand_catalog(universe):
    """Use only a country selector catalog reconciled against the native map."""
    universe = universe or {}
    catalog = universe.get("destination_catalog") or {}
    countries = catalog.get("airport_ids_by_country")
    menus = universe.get("country_values_by_origin")
    if not countries or not menus or set(universe.get("origin_ids") or ()) != set(menus):
        return None
    if any(set(menu) != set(countries) for menu in menus.values()):
        return None
    destinations = [airport for ids in countries.values() for airport in ids]
    if (len(set(destinations)) != len(destinations)
            or sorted(destinations) != catalog.get("map_airport_ids")
            or not set(menus) <= set(destinations)
            or not all(_valid_id(airport) for airport in destinations)
            or any(not isinstance(country, str) or not country for country in countries)):
        return None
    return tuple(menus), countries


class DemandStore:
    def __init__(self, path=None):
        self.path = paths.current().data / "native_demand.sqlite3" if path is None else Path(path)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5)

    @staticmethod
    def _initialized(db):
        return db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'scan'").fetchone()

    def status(self):
        status = {
            "state": "pending", "processed_partitions": 0, "total_partitions": 0,
            "observed_pairs": 0, "recent_observed_pairs": 0, "searched_pairs": 0, "expected_pairs": 0,
            "updated_at": None, "error": None,
        }
        if not self.path.is_file():
            return status
        with closing(self._connect()) as db:
            db.execute("BEGIN")
            if not self._initialized(db):
                return status
            scan = db.execute("SELECT state, updated_at, error FROM scan WHERE id = 1").fetchone()
            if scan is None:
                return status
            status["state"], status["updated_at"], status["error"] = scan
            partitions = dict(db.execute("SELECT state, count(*) FROM partitions GROUP BY state"))
            targets = dict(db.execute("SELECT state, count(*) FROM targets GROUP BY state"))
            now = time.time()
            status["recent_observed_pairs"] = db.execute("""
                SELECT count(*) FROM demand JOIN targets USING (origin_id, destination_id)
                WHERE targets.state = 'observed' AND demand.observed_at BETWEEN ? AND ?
                """, (now - DEFAULT_MAX_AGE_SECONDS, now)).fetchone()[0]
        status["processed_partitions"] = sum(partitions.values()) - partitions.get("open", 0)
        status["total_partitions"] = sum(partitions.values())
        status["observed_pairs"] = targets.get("observed", 0)
        status["searched_pairs"] = targets.get("empty", 0) + status["observed_pairs"]
        status["expected_pairs"] = sum(targets.values())
        return status

    def pending_work(self):
        if not self.path.is_file():
            return None
        with closing(self._connect()) as db:
            if not self._initialized(db):
                return None
            row = db.execute("""SELECT EXISTS(SELECT 1 FROM partitions) FROM scan
                                WHERE id = 1 AND state IN ('queued', 'running')""").fetchone()
        return ("batch" if row[0] else "catalog") if row is not None else None

    def request(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("BEGIN IMMEDIATE;" + _SCHEMA + "COMMIT;")
            db.execute("BEGIN IMMEDIATE")
            scan = db.execute("SELECT state FROM scan WHERE id = 1").fetchone()
            if scan and scan[0] in _ACTIVE:
                return False
            if scan is None:
                db.execute("INSERT INTO scan (id, state, updated_at) VALUES (1, 'queued', ?)", (time.time(),))
            else:
                if scan[0] == "completed":
                    db.execute("DELETE FROM partitions")
                    db.execute("DELETE FROM targets")
                else:
                    db.execute("UPDATE partitions SET state = 'open', attempts = 0 WHERE state IN ('open', 'failed')")
                    db.execute("UPDATE targets SET state = 'open', attempts = 0 WHERE state IN ('open', 'failed')")
                self._state(db, "queued")
        return True

    def begin(self, company_id, catalog):
        """Claim the request on the browser-owning thread and initialize its catalog once."""
        if not isinstance(company_id, str) or not _COMPANY_ID.fullmatch(company_id):
            raise ValueError("Companhia da pesquisa indisponível.")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            scan = db.execute("SELECT state, company_id FROM scan WHERE id = 1").fetchone()
            if scan is None or scan[0] not in _ACTIVE:
                return False
            if scan[1] not in (None, company_id):
                self._state(db, "partial", "A companhia atual difere da companhia desta pesquisa.")
                return False
            if not db.execute("SELECT 1 FROM partitions LIMIT 1").fetchone():
                if catalog is None:
                    self._state(db, "partial", "O catálogo de aeroportos do jogo não pôde ser conciliado.")
                    return False
                origins, countries = catalog
                db.executemany("INSERT INTO partitions (origin_id, country) VALUES (?, ?)",
                               ((origin, country) for origin in origins for country in countries))
                db.executemany("INSERT INTO targets (origin_id, country, destination_id) VALUES (?, ?, ?)",
                               ((origin, country, airport) for origin in origins
                                for country, ids in countries.items() for airport in ids if airport != origin))
                db.execute("""DELETE FROM demand WHERE NOT EXISTS (
                    SELECT 1 FROM targets WHERE targets.origin_id = demand.origin_id
                    AND targets.destination_id = demand.destination_id)""")
            db.execute("UPDATE scan SET company_id = ? WHERE id = 1", (company_id,))
            self._state(db, "running")
            return True

    def jobs(self, limit):
        with closing(self._connect()) as db:
            partitions = db.execute("""
                SELECT origin_id, country, '0' FROM partitions WHERE state = 'open'
                ORDER BY attempts, origin_id, country LIMIT ?
                """, (limit,)).fetchall()
            if partitions:
                return partitions
            return db.execute("""
                SELECT origin_id, country, destination_id FROM targets WHERE state = 'open'
                ORDER BY attempts, origin_id, country, destination_id LIMIT ?
                """, (limit,)).fetchall()

    def save(self, jobs, results):
        """Record one batch transactionally, including exact searches that return no demand."""
        by_job = {}
        for result in results or ():
            if isinstance(result, dict):
                key = (result.get("origin_id"), result.get("country"), result.get("destination_id"))
                if all(isinstance(value, str) for value in key):
                    by_job[key] = None if key in by_job else result.get("rows")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            now = time.time()
            failed = 0
            for origin, country, destination in jobs:
                rows = by_job.get((origin, country, destination))
                if not self._save_job(db, origin, country, destination, rows, now):
                    failed += 1
            if jobs and failed == len(jobs):
                self._state(db, "partial", "O jogo não retornou um lote válido. Autorize a retomada para tentar de novo.")
                return
            if db.execute("SELECT 1 FROM partitions WHERE state = 'open' LIMIT 1").fetchone() or db.execute(
                    "SELECT 1 FROM targets WHERE state = 'open' LIMIT 1").fetchone():
                self._state(db, "running")
            elif db.execute("SELECT 1 FROM targets WHERE state = 'failed' LIMIT 1").fetchone():
                self._state(db, "partial", "Há pares sem resposta válida. Autorize a retomada para tentar de novo.")
            else:
                self._state(db, "completed")

    def _save_job(self, db, origin, country, destination, rows, now):
        bulk = destination == "0"
        expected = {value for value, in db.execute(
            "SELECT destination_id FROM targets WHERE origin_id = ? AND country = ?",
            (origin, country))} if bulk else {destination}
        observed = {}
        if isinstance(rows, list) and len(rows) <= (50 if bulk else 1):
            for row in rows:
                if not isinstance(row, dict):
                    break
                airport = row.get("destination_id")
                demand = tuple(row.get(key) for key in "yjf")
                event = row.get("event_demand_boosted")
                if (not _valid_id(airport) or airport not in expected or airport in observed
                        or any(type(value) is not int or not 0 <= value <= 100_000_000 for value in demand)
                        or (event is not None and type(event) is not bool)):
                    break
                distance = row.get("distance_km")
                runway = row.get("runway_ft")
                if type(distance) not in (int, float) or not 0 < distance <= 25_000:
                    distance = None
                if type(runway) is not int or not 0 < runway <= 30_000:
                    runway = None
                observed[airport] = (*demand, distance, runway, event)
            else:
                self._save_observations(db, origin, observed, now)
                if bulk:
                    db.execute("UPDATE partitions SET state = 'done' WHERE origin_id = ? AND country = ?",
                               (origin, country))
                elif not observed:
                    db.execute("UPDATE targets SET state = 'empty' WHERE origin_id = ? AND destination_id = ?",
                               (origin, destination))
                    db.execute("DELETE FROM demand WHERE origin_id = ? AND destination_id = ?", (origin, destination))
                return True
        if bulk:
            db.execute("""UPDATE partitions SET attempts = attempts + 1,
                          state = CASE WHEN attempts + 1 >= ? THEN 'failed' ELSE 'open' END
                          WHERE origin_id = ? AND country = ?""", (_ATTEMPTS, origin, country))
        else:
            db.execute("""UPDATE targets SET attempts = attempts + 1,
                          state = CASE WHEN attempts + 1 >= ? THEN 'failed' ELSE 'open' END
                          WHERE origin_id = ? AND destination_id = ?""", (_ATTEMPTS, origin, destination))
        return False

    @staticmethod
    def _save_observations(db, origin, observed, now):
        db.executemany("""
            INSERT INTO demand (origin_id, destination_id, y, j, f, distance_km, runway_ft,
                                event_demand_boosted, observed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(origin_id, destination_id) DO UPDATE SET y = excluded.y, j = excluded.j,
                f = excluded.f, distance_km = excluded.distance_km, runway_ft = excluded.runway_ft,
                event_demand_boosted = excluded.event_demand_boosted,
                observed_at = excluded.observed_at
            """, ((origin, airport, *values, now) for airport, values in observed.items()))
        db.executemany("UPDATE targets SET state = 'observed' WHERE origin_id = ? AND destination_id = ?",
                       ((origin, airport) for airport in observed))

    def lookup(self, origin_id, destination_id):
        if not self.path.is_file():
            return None
        with closing(self._connect()) as db:
            if not self._initialized(db):
                return None
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM demand WHERE origin_id = ? AND destination_id = ?",
                             (origin_id, destination_id)).fetchone()
        if row is None:
            return None
        result = dict(row)
        event = result["event_demand_boosted"]
        result["event_demand_boosted"] = bool(event) if event is not None else None
        return {**result, "source": "game_route_search"}

    def pause(self, message):
        with closing(self._connect()) as db, db:
            db.execute("""UPDATE scan SET state = 'partial', updated_at = ?, error = ?
                          WHERE id = 1 AND state IN ('queued', 'running')""", (time.time(), message))

    @staticmethod
    def _state(db, state, error=None):
        db.execute("UPDATE scan SET state = ?, updated_at = ?, error = ? WHERE id = 1",
                   (state, time.time(), error))
