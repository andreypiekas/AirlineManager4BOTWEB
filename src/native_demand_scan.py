"""Advance authorized native research on the browser-owning worker thread."""
from __future__ import annotations

import logging
import sqlite3

from selenium.common.exceptions import WebDriverException

from game_observations import collect_owned_route_search_universe
from native_demand_store import DemandStore, demand_catalog
from native_demand_transport import read_demand_batch

log = logging.getLogger(__name__)
_BATCH_SIZE = 16


def _verified_company(bot, expected=None):
    bot._require_observation_session()
    bot._verify_observation_company()
    company = bot._observation_company_id
    if not company or (expected is not None and company != expected):
        raise RuntimeError("Identidade da companhia sem confirmação na pesquisa.")
    return company


def requested_work(store):
    try:
        return store.pending_work()
    except (OSError, sqlite3.Error):
        log.debug("Não foi possível ler a fila da pesquisa de demanda.", exc_info=True)
        return None


def prepare_requested_scan(bot, universe=None):
    store = DemandStore()
    if bot.stopping or requested_work(store) != "catalog":
        return
    try:
        company = _verified_company(bot)
        if universe is None:
            universe = collect_owned_route_search_universe(bot)
        if not bot.stopping:
            _verified_company(bot, company)
            store.begin(company, demand_catalog(universe))
    except (RuntimeError, WebDriverException) as exc:
        if not bot.stopping:
            store.pause("A sessão da companhia não foi confirmada. Confira o Chrome e autorize a retomada.")
            log.warning("Catálogo da pesquisa interrompido (%s).", type(exc).__name__)


def run_demand_slice(bot, store):
    """Validate the company before and after the detached, read-only requests."""
    if bot.stopping:
        return
    try:
        company = _verified_company(bot)
        if not store.begin(company, None):
            return
        jobs = store.jobs(_BATCH_SIZE)
        observations = read_demand_batch(bot, jobs) if jobs else []
        if not bot.stopping:
            _verified_company(bot, company)
            store.save(jobs, observations)
    except (RuntimeError, WebDriverException) as exc:
        if not bot.stopping:
            store.pause("A sessão da companhia não foi confirmada. Confira o Chrome e autorize a retomada.")
            log.warning("Lote da pesquisa interrompido (%s).", type(exc).__name__)
