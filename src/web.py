"""Web dashboard: the same statistics, log, controls and settings as the desktop window, in a browser.

A small stdlib HTTP server (no extra dependencies) runs in a daemon thread next to the bot. It serves
assets/web/index.html and a JSON API:

* GET  /api/status            snapshot of the dashboard (dashboard.snapshot) + last log id
* GET  /api/log?since=<id>    new log lines
* GET  /api/settings          tabs with their fields / switches, current values and help texts
* POST /api/settings          {"settings": {key: int}, "options": {key: bool}, "text": {key: str}}
* POST /api/control           {"action": "start" | "stop" | "run_now" | "quit"}  (quit: stop the bot and close
                              the program; used by scripts/web_parar.ps1)
* POST /api/admin/game-source-probe  authorized, read-only snapshot of the active game's DOM
* POST /api/admin/flight-history-probe  authorized, read-only structural history for one aircraft

Safety: by default it only listens on 127.0.0.1. To open it to the local network ([web] host = 0.0.0.0)
a token is required ([web] token in config/secrets.ini); without one the server stays on 127.0.0.1.
POSTs need the X-AM4 header (a cross-site page cannot send it) and, without a token, only local Host
names are accepted (no DNS rebinding). Credentials and Telegram secrets are never sent to the page.
"""
from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import math
import os
import re
import sqlite3
import socket
import threading
import time
import urllib.request
from configparser import ConfigParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional
from urllib.parse import parse_qs, urlparse

import paths
from dashboard import snapshot, recent_verified_money, fleet_summary
from economy import AUTO_GOAL_LABEL, is_auto_goal, load_market, load_market_evidence, load_state
from i18n import language, t, tip
from route_registry import RouteRegistry, endpoint
from hub_registry import HubRegistry
from hub_expansion import HubExpansionRegistry
from engine_catalog import EngineCatalogRegistry
from hub_aircraft_research import HubAircraftResearchRegistry
from owned_hub_research_ingestion import OwnedHubResearchInputsRegistry
from owned_hub_research_feed import build_external_hub_research_queue, build_owned_hub_research_queue
from research_economics_preview import configured_price_assumptions
from route_detail_evidence import RouteDetailRegistry
from hub_recommendations import rank_next_aircraft
from investment_policy import InvestmentPolicy, MODES
from investment_journal import InvestmentJournal
from route_creation import has_pending_creation
from reroute import has_pending_reroute
from investment_plan_bridge import build_aircraft_intent_plan
from expansion_metrics import build_expansion_metrics
from portfolio_planner import compare_portfolio
from portfolio_planner import compare_audited_portfolio
from expansion_economics import rank_expansion_economics
from audited_economics_registry import AuditedEconomicsRegistry
from audited_game_snapshot import replay_research_page, snapshot_summary
from expansion_feasibility import assess_expansion
from settings_schema import ALL_FIELDS, ALL_SWITCHES, OPTION_DEFAULTS, TABS, TEXT_SETTINGS, clamp_settings, parse_int

if TYPE_CHECKING:
    from bot import Bot
    from config import AppConfig
    from logsetup import LogBuffer

log = logging.getLogger("am4bot.app")

PAGE = Path("assets/web/index.html")
COOKIE = "am4token"
MAX_BODY = 64 * 1024


def _local_investment_snapshot() -> dict:
    try:
        return {
            **InvestmentJournal.read_existing(since=time.time() - 86400),
            "read_only": True, "execution_available": False,
        }
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
        return {
            "intents": [], "count": None, "estimated_exposure": None,
            "period_usage": None, "cycle_usage": None, "read_only": True, "execution_available": False,
            "blocking_reasons": ["diario_indisponivel"],
        }


def _local_investment_blockers(journal: dict) -> list[str]:
    reasons = list(journal.get("blocking_reasons", []))
    if journal.get("estimated_exposure") is None or journal.get("count") is None:
        reasons.append("diario_indisponivel")
    elif journal["count"] > 0:
        reasons.append("intencoes_locais_a_conciliar")
    try:
        if has_pending_creation():
            reasons.append("criacao_rota_a_conciliar")
        if has_pending_reroute():
            reasons.append("redirecionamento_a_conciliar")
    except OSError:
        reasons.append("diario_rotas_indisponivel")
    return list(dict.fromkeys(reasons))


def _block_local_investment(portfolio: dict, journal: dict) -> None:
    _block_portfolio(portfolio, _local_investment_blockers(journal))


def _block_portfolio(portfolio: dict, blockers: list[str]) -> None:
    if blockers:
        portfolio["blocking_reasons"] = list(dict.fromkeys([*portfolio["blocking_reasons"], *blockers]))
        portfolio["status"] = "inconclusivo"
        if "decision" in portfolio:
            portfolio["decision"] = "nao_comprar"


def _current_audited_finance_blockers(bot, evaluation: dict, record: dict, journal: dict,
                                      controls: dict, passenger_hangar: dict) -> list[str]:
    """Require the audited snapshot to agree with the current account and ledger."""
    blockers = []
    money, observed_at = recent_verified_money(bot)
    cash = evaluation["provenance"]["cash"]
    if money is None or observed_at is None or observed_at < cash["observed_at"]:
        blockers.append("saldo_vivo_a_confirmar")
    elif money != cash["value"]["available"]:
        blockers.append("saldo_vivo_divergente_a3")
    # A new confirmation may alter the balance, hangar, fleet and spending
    # controls even if the current balance happens to equal the old amount.
    last_confirmed = journal["period_usage"]["last_confirmed_at"]
    if last_confirmed is not None:
        if type(last_confirmed) not in (int, float) or not math.isfinite(last_confirmed):
            blockers.append("diario_indisponivel")
        else:
            evidence = {**record["portfolio_evidence"], "controls": controls}
            timestamps = [row["observed_at_oldest"] for row in record["evaluations"]]
            for group in ("controls", "confidence_evidence", "diversification_evidence"):
                timestamps.extend(proof["observed_at"] for proof in evidence.get(group, {}).values())
            timestamps.append(passenger_hangar["observed_at"])
            if any(last_confirmed > stamp for stamp in timestamps):
                blockers.append("snapshot_anterior_compra_confirmada")
    return blockers


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


class _ExclusiveServer(ThreadingHTTPServer):
    """The port belongs to one program only. On Windows SO_REUSEADDR (http.server's default) lets a second
    program bind a port that is already listening, so a second bot would not notice the first one."""

    allow_reuse_address = os.name != "nt"
    daemon_threads = True

    def server_bind(self) -> None:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def instance_answers(port: int, token: str = "", host: str = "127.0.0.1") -> bool:
    """True when a copy of the bot (desktop app or web mode) answers on this dashboard port."""
    request = urllib.request.Request(f"http://{host}:{port}/api/status", headers={"X-Token": token})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never through a system proxy
    try:
        with opener.open(request, timeout=1.5) as response:
            return "state_key" in json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return False


def other_hosts(cfg: "AppConfig") -> list[str]:
    """[web] remote_instances: other machines that may run the same profiles (for example the Raspberry)."""
    return [host.strip() for host in cfg.get("web", "remote_instances", "").split(",") if host.strip()]


def running_instance(cfg: "AppConfig", include_local: bool = True) -> Optional[str]:
    """Where another copy of this profile's bot already runs ("127.0.0.1" or a remote host), else None.
    Two copies would fight over the same airline (and, on one machine, the same Chrome profile), so the
    second one must not start its bot. *include_local* False skips this machine (our own dashboard)."""
    port, token = cfg.get_int("web", "port", 8744), cfg.web_token
    for host in (["127.0.0.1"] if include_local else []) + other_hosts(cfg):
        if instance_answers(port, token, host):
            return host
    return None


def profile_token(profile: paths.Profile) -> str:
    parser = ConfigParser(interpolation=None)
    parser.read(profile.secrets, encoding="utf-8")
    return parser.get("web", "token", fallback="").strip()


def profile_running(profile: paths.Profile) -> bool:
    return instance_answers(profile.port(), profile_token(profile))


class WebDashboard:
    def __init__(self, bot: "Bot", cfg: "AppConfig", buffer: "LogBuffer",
                 restart_in: Callable[[], Optional[int]] = lambda: None,
                 start_bot: Optional[Callable[[], None]] = None,
                 on_quit: Optional[Callable[[], None]] = None):
        self.bot = bot
        self.cfg = cfg
        self.buffer = buffer
        self.restart_in = restart_in
        self.start_bot = start_bot or bot.start
        self.on_quit = on_quit
        self.server: Optional[ThreadingHTTPServer] = None
        self.url = ""

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> bool:
        host = self.cfg.get("web", "host", "127.0.0.1") or "127.0.0.1"
        port = self.cfg.get_int("web", "port", 8744)
        if not _is_loopback(host) and not self.cfg.web_token:
            log.warning("Web: para permitir acesso pela rede local, configure [web] token em config/secrets.ini; "
                        "por enquanto, somente 127.0.0.1 será utilizado.")
            host = "127.0.0.1"
        try:
            self.server = _ExclusiveServer((host, port), self._handler())
        except OSError as exc:
            if running_instance(self.cfg):
                log.warning("Já existe outro Airline Manager 4 Bot em execução (painel web em http://127.0.0.1:%s/).", port)
            else:
                log.warning("Web: não foi possível abrir a porta %s (%s).", port, exc.strerror or exc)
            return False
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, name="am4web", daemon=True).start()
        shown = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        self.url = f"http://{shown}:{port}/"
        log.info("Painel web em %s%s", self.url, " (acessível também pela rede local mediante token)" if not _is_loopback(host) else "")
        return True

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    # ------------------------------------------------------------------ data
    def status(self) -> dict:
        data = snapshot(self.bot, self.cfg, load_state(), load_market(), self.restart_in())
        data["profile"] = None if self.cfg.profile.is_main else self.cfg.profile.label
        lines = self.buffer.since(0)
        data["log_last"] = lines[-1]["id"] if lines else 0
        return data

    def routes(self) -> dict:
        """Thread-safe report; this endpoint never operates the Selenium driver."""
        report = RouteRegistry().snapshot(
            allow_duplicates=self.cfg.get_bool("options", "allow_duplicate_routes", False),
        )
        stats_reader = getattr(self.bot, "stats", None)
        if callable(stats_reader):
            report["fleet_counts"] = fleet_summary(stats_reader())
        return report

    def hubs(self) -> dict:
        """Serve the last game-confirmed inventory without opening Selenium."""
        report = HubRegistry().snapshot(self.routes())
        report["fleet_counts"] = fleet_summary(self.bot.stats())
        return report

    def hub_expansion(self, *, owned_inventory: dict | None = None,
                      owned_research: dict | None = None) -> dict:
        """Compare candidate hubs against a recently verified balance."""
        if owned_inventory is None:
            owned_inventory = self.hubs()
        owned = {hub["id"] for hub in owned_inventory["hubs"]}
        cash, observed_at = recent_verified_money(self.bot)
        report = HubExpansionRegistry().snapshot(
            cash=cash,
            reserve=self.cfg.get_int("settings", "cash_reserve", 0),
            owned_hub_ids=owned,
            external_ownership_verified=owned_inventory.get("hub_catalog_fresh") is True,
        )
        report["cash_observed_at"] = observed_at
        if owned_research is None:
            recommendations_reader = getattr(self, "hub_recommendations", None)
            owned_research = recommendations_reader() if callable(recommendations_reader) else {}
        report["expansion_decision"] = assess_expansion(
            owned_inventory,
            owned_research,
            owned_research.get("portfolio") if isinstance(owned_research, dict) else None,
            report,
            coverage=owned_research.get("opportunity_coverage")
            if isinstance(owned_research, dict) else None,
        )
        return report

    def external_hub_research(self, *, research_offset: int = 0,
                              research_fingerprint: str | None = None) -> dict:
        """Serve external combinations from independent, read-only cached evidence."""
        routes = RouteRegistry().snapshot()
        inventory = HubRegistry().snapshot()
        owned = {hub["id"] for hub in inventory.get("hubs", [])
                 if isinstance(hub, dict) and isinstance(hub.get("id"), str)}
        external = HubExpansionRegistry().external_demand_snapshot(owned)
        cash, observed_at = recent_verified_money(self.bot)
        stats_reader = getattr(self.bot, "stats", None)
        return build_external_hub_research_queue(
            inventory, external, load_market_evidence(),
            engines=EngineCatalogRegistry().snapshot(), offset=research_offset,
            expected_fingerprint=research_fingerprint,
            cash=cash, cash_observed_at=observed_at,
            reserve=self.cfg.get_int("settings", "cash_reserve", 0),
            operating_market_stats=stats_reader() if callable(stats_reader) else None,
            preview_margin=max(0, min(100, self.cfg.get_int("investment", "preview_margin_pct", 10))) / 100,
            configured_prices=configured_price_assumptions(self.cfg),
            route_report=routes,
        )

    def hub_recommendations(self, *, research_offset: int = 0,
                            research_fingerprint: str | None = None) -> dict:
        """Rank proven research for owned hubs using independent cached reads."""
        routes = self.routes()
        cash, observed_at = recent_verified_money(self.bot)
        inventory = HubRegistry().snapshot(routes)
        verified_scenarios = HubAircraftResearchRegistry().snapshot()
        pending_inputs = OwnedHubResearchInputsRegistry().snapshot(verified=verified_scenarios)
        engines = EngineCatalogRegistry().snapshot()
        # Replace embedded proofs with the independent route-detail registry.
        # A failed subsequent read must revoke any previously cached detail.
        details = RouteDetailRegistry().enrich([
            {"origin_id": row["origin"].get("id") if isinstance(row.get("origin"), dict) else None,
             "destination_id": row["destination"].get("id") if isinstance(row.get("destination"), dict) else None}
            for row in verified_scenarios
        ])
        verified_scenarios = [
            {**{key: value for key, value in row.items() if key != "route_detail"},
             **({"route_detail": sample["route_detail"]} if "route_detail" in sample else {})}
            for row, sample in zip(verified_scenarios, details)
        ]
        report = rank_next_aircraft(
            inventory,
            [*verified_scenarios, *pending_inputs],
            route_report=routes,
            cash=cash,
            cash_observed_at=observed_at,
            reserve=self.cfg.get_int("settings", "cash_reserve", 0),
            engine_catalog=engines,
        )
        report["research_ingestion"] = {
            "saved_verified_scenarios": len(verified_scenarios),
            "saved_pending_inputs": len(pending_inputs),
            "coverage": "partial", "read_only": True,
        }
        report["engine_order_list_coverage"] = engines.get("order_list_coverage")
        report["fleet_commitment_observations"] = inventory.get("fleet_commitment_observations")
        report["fleet_route_reconciliation"] = inventory.get("fleet_route_reconciliation")
        report["finance_observations"] = inventory.get("finance_observations")
        owned_ids = {hub["id"] for hub in inventory.get("hubs", [])
                     if isinstance(hub, dict) and isinstance(hub.get("id"), str)}
        demand_snapshot = HubExpansionRegistry().demand_research_snapshot(owned_ids)
        stats_reader = getattr(self.bot, "stats", None)
        report["research_queue"] = build_owned_hub_research_queue(
            inventory,
            demand_snapshot["samples"],
            load_market_evidence(),
            engines=engines,
            hub_progress=demand_snapshot["hub_progress"],
            offset=research_offset,
            expected_fingerprint=research_fingerprint,
            operating_market_stats=stats_reader() if callable(stats_reader) else None,
            preview_margin=max(0, min(100, self.cfg.get_int("investment", "preview_margin_pct", 10))) / 100,
            configured_prices=configured_price_assumptions(self.cfg),
            route_report=routes,
        )
        investment_policy = InvestmentPolicy.from_config(self.cfg)
        report["investment_policy"] = investment_policy.report()
        report["investment_journal"] = _local_investment_snapshot()
        report["portfolio"] = compare_portfolio(
            report,
            known_local_commitments=report["investment_journal"]["estimated_exposure"],
            local_period_usage=report["investment_journal"].get("period_usage"),
            max_daily_spend=(investment_policy.max_daily_spend
                             if investment_policy.enabled and investment_policy.max_daily_spend > 0 else None),
            max_acquisitions_per_day=(investment_policy.max_acquisitions_per_day
                                      if investment_policy.enabled and investment_policy.max_acquisitions_per_day > 0 else None),
            max_single_investment=(investment_policy.max_single_investment
                                   if investment_policy.enabled and investment_policy.max_single_investment > 0
                                   else None),
            min_daily_profit=investment_policy.min_daily_profit if investment_policy.enabled else 0,
            max_payback_days=(investment_policy.max_payback_days
                              if investment_policy.enabled and investment_policy.max_payback_days > 0
                              else None),
            profit_weight=investment_policy.profit_weight,
            efficiency_weight=investment_policy.efficiency_weight,
            return_weight=investment_policy.return_weight,
            risk_weight=investment_policy.risk_weight,
            confidence_weight=investment_policy.confidence_weight,
            diversification_weight=investment_policy.diversification_weight,
            policy_valid=investment_policy.valid,
        )
        _block_local_investment(report["portfolio"], report["investment_journal"])
        return report

    def investment_metrics(self) -> tuple[int, dict]:
        """Expose local investment history and proven research without game mutations."""
        try:
            journal = InvestmentJournal()
            try:
                research = self.hub_recommendations()
            except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
                research = None
            return HTTPStatus.OK, build_expansion_metrics(
                journal, opportunity_report=research,
            )
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "read_only": True,
                "status": "diario_indisponivel",
                "message": "Não foi possível auditar o diário de investimentos.",
            }

    def audited_expansion(self) -> dict:
        """Expose A3/A4 accounting from independently stored game evidence."""
        record = AuditedEconomicsRegistry().snapshot()
        policy = InvestmentPolicy.from_config(self.cfg)
        proof = record["portfolio_evidence"]
        evaluations = record["evaluations"]
        game_snapshot = snapshot_summary()
        snapshot_id = record["snapshot_id"] or game_snapshot.get("snapshot_id") or ""
        matching_capture = (game_snapshot["status"] == "parcial" and bool(snapshot_id)
                            and game_snapshot.get("snapshot_id") == snapshot_id)
        scopes = game_snapshot.get("scopes", {}) if matching_capture else {}
        fleet_verified = scopes.get("fleet") is True
        research_verified = (proof.get("research_coverage_verified") is True
                             and all(scopes.get(scope) is True for scope in
                                     ("hubs", "routes", "models", "engines", "prices")))
        stored_controls = proof.get("controls")
        controls = dict(stored_controls) if isinstance(stored_controls, dict) else {}
        controls.pop("unrouted_aircraft_count", None)
        if fleet_verified and game_snapshot.get("unrouted_aircraft_control") is not None:
            controls["unrouted_aircraft_count"] = game_snapshot["unrouted_aircraft_control"]
        passenger_hangar = game_snapshot.get("passenger_hangar_control") if matching_capture else None
        journal = _local_investment_snapshot()
        portfolio = compare_audited_portfolio(
            evaluations,
            profile_id=paths.current().label,
            snapshot_id=snapshot_id,
            controls=controls,
            passenger_hangar=passenger_hangar,
            confidence_evidence=proof.get("confidence_evidence"),
            diversification_evidence=proof.get("diversification_evidence"),
            fleet_coverage_verified=fleet_verified,
            research_coverage_verified=research_verified,
            commitments_verified=proof.get("commitments_verified") is True,
            current_cash_reserve=self.cfg.get_int("settings", "cash_reserve", -1),
            max_daily_spend=policy.max_daily_spend,
            max_cycle_spend=policy.max_cycle_spend,
            max_acquisitions_per_day=policy.max_acquisitions_per_day,
            local_journal=journal,
            max_single_investment=(policy.max_single_investment
                                   if policy.enabled and policy.max_single_investment > 0 else None),
            min_daily_profit=policy.min_daily_profit,
            max_payback_days=policy.max_payback_days or None,
            profit_weight=policy.profit_weight,
            efficiency_weight=policy.efficiency_weight,
            return_weight=policy.return_weight,
            risk_weight=policy.risk_weight,
            confidence_weight=policy.confidence_weight,
            diversification_weight=policy.diversification_weight,
            policy_valid=policy.valid and policy.enabled,
        )
        if record["status"] == "registro_invalido":
            portfolio["blocking_reasons"].append("registro_a3_invalido")
            portfolio["status"] = "inconclusivo"
            portfolio["decision"] = "nao_comprar"
        _block_local_investment(portfolio, journal)
        # A fresh capture supersedes the economic proof even when the balance
        # is unchanged. Keep historical evaluations visible for diagnosis.
        if game_snapshot["status"] == "registro_invalido":
            _block_portfolio(portfolio, ["coleta_jogo_invalida"])
        elif game_snapshot["status"] == "expirado":
            _block_portfolio(portfolio, ["coleta_jogo_expirada"])
        elif game_snapshot["status"] == "sem_coleta":
            _block_portfolio(portfolio, ["coleta_jogo_ausente"])
        elif (record["snapshot_id"]
              and game_snapshot.get("snapshot_id") != record["snapshot_id"]):
            _block_portfolio(portfolio, ["snapshot_a3_divergente_coleta"])
        purchase_plan = None
        purchase_plan_blockers = []
        if portfolio.get("decision") == "sugestao_para_analise":
            winner = portfolio.get("best")
            economics_id = winner.get("economics_id") if isinstance(winner, dict) else None
            matches = [
                row for row in evaluations
                if isinstance(row, dict) and isinstance(economics_id, str)
                and row.get("economics_id") == economics_id
            ]
            if len(matches) != 1:
                purchase_plan_blockers.append("economia_a3_vencedora_ausente_ou_ambigua")
            else:
                try:
                    finance_blockers = _current_audited_finance_blockers(
                        self.bot, matches[0], record, journal, controls, passenger_hangar,
                    )
                except (AttributeError, ValueError, TypeError, KeyError):
                    finance_blockers = ["conciliacao_financeira_a_confirmar"]
                _block_portfolio(portfolio, finance_blockers)
                purchase_plan_blockers.extend(finance_blockers)
                if not finance_blockers:
                    try:
                        purchase_plan = build_aircraft_intent_plan(portfolio, matches[0])
                    except (ValueError, TypeError, KeyError) as exc:
                        purchase_plan_blockers.append(str(exc))
        else:
            purchase_plan_blockers.extend(portfolio.get("blocking_reasons") or [])
            if not purchase_plan_blockers:
                purchase_plan_blockers.append("nenhum_plano_elegivel")
        ranking = rank_expansion_economics(evaluations)
        return {
            "status": record["status"], "snapshot_id": record["snapshot_id"],
            "profile_id": paths.current().label,
            "game_observation_snapshot": game_snapshot,
            "evaluation_count": len(evaluations),
            "evaluations": evaluations,
            "a3_ranking": ranking,
            "portfolio": portfolio,
            "purchase_plan_preview": purchase_plan,
            "purchase_plan_blockers": purchase_plan_blockers,
            "read_only": True, "execution_available": False,
        }

    def game_source_probe(self) -> tuple[int, dict]:
        """Ask the bot worker to read its own game session during an idle wait."""
        return self._admin_probe_result(self.bot.request_game_source_probe)

    def flight_history_probe(self, aircraft_id: str) -> tuple[int, dict]:
        """Inspect one aircraft's history through the existing Selenium owner."""
        return self._admin_probe_result(lambda: self.bot.request_flight_history_probe(aircraft_id))

    @staticmethod
    def _admin_probe_result(request: Callable[[], tuple[str, Optional[dict]]]) -> tuple[int, dict]:
        try:
            result, report = request()
            if result == "ok" and isinstance(report, dict):
                return HTTPStatus.OK, {"ok": True, "report": report}
            if result == "busy":
                return HTTPStatus.CONFLICT, {
                    "ok": False, "message": "Bot ocupado. Tente novamente entre os ciclos."
                }
            if result == "timeout":
                return HTTPStatus.GATEWAY_TIMEOUT, {
                    "ok": False, "message": "Tempo limite do diagnóstico excedido."
                }
        except Exception:
            # The HTTP boundary never logs exceptions or sensitive driver details.
            pass
        return HTTPStatus.SERVICE_UNAVAILABLE, {
            "ok": False, "message": "Não foi possível consultar a sessão atual."
        }

    def update_routes(self, payload: dict) -> tuple[bool, str]:
        """Manual registry corrections are auditable and never change routes in-game."""
        if payload.get("action") != "register":
            return False, "Ação de controle de rotas desconhecida."
        aircraft_id = str(payload.get("aircraft_id") or "").strip()[:64]
        registration = str(payload.get("registration") or "").strip()[:80]
        model = str(payload.get("model") or "").strip()[:100]
        origin = endpoint(str(payload.get("origin_id") or "")[:20],
                          str(payload.get("origin_code") or "")[:12],
                          str(payload.get("origin_name") or "")[:100])
        destination = endpoint(str(payload.get("destination_id") or "")[:20],
                               str(payload.get("destination_code") or "")[:12],
                               str(payload.get("destination_name") or "")[:100])
        if not aircraft_id or not RouteRegistry().record(
            aircraft_id, registration, model, origin, destination, source="registro_manual"
        ):
            return False, "Informe a identificação da aeronave e ambos os aeroportos."
        return True, "Relação registrada no controle local. A rota no jogo não foi alterada."

    def settings(self) -> dict:
        cfg = self.cfg
        tabs = []
        for name, icon, fields, switches in TABS:
            tabs.append({
                "key": name, "name": t(name), "icon": icon,
                "fields": [{"key": k, "label": t(label), "value": cfg.get_int("settings", k), "help": tip(k) or ""}
                           for k, label in fields],
                "switches": [{"key": k, "label": t(label), "help": tip(k) or "",
                              "value": cfg.get_bool("options", k, OPTION_DEFAULTS.get(k, False))}
                             for k, label in switches],
            })
        goal = cfg.get("settings", "goal_model")
        # Expor todos os modelos encontrados no mercado, inclusive aeronaves
        # pequenas: a seleção de compra não pode ficar limitada a 100 assentos.
        model_names = sorted({m["name"].strip() for m in load_market()
                              if isinstance(m.get("name"), str) and m["name"].strip()},
                             key=str.casefold)
        text = [{"key": k, "label": t(label), "help": tip(k) or "",
                 "value": t(AUTO_GOAL_LABEL) if k == "goal_model" and is_auto_goal(goal) else cfg.get("settings", k)}
                for k, label in TEXT_SETTINGS]
        return {"tabs": tabs, "text": text, "goal_options": [t(AUTO_GOAL_LABEL)] + model_names,
                "aircraft_options": model_names, "auto_goal_label": t(AUTO_GOAL_LABEL),
                "lang": language()}

    def investment_settings(self) -> dict:
        """Per-profile controls for the separate, gated investment workflow."""
        return {
            "policy": InvestmentPolicy.from_config(self.cfg).report(),
            "version": self.cfg.version,
            "cash_reserve": self.cfg.get_int("settings", "cash_reserve", 0),
            "engine_preference": self.cfg.get("settings", "engine_preference", "default"),
        }

    def update_investment_settings(self, payload: dict) -> tuple[bool, str]:
        """Validate the entire policy before an atomic per-profile config save."""
        fields = {"planning_enabled", "mode", "auto_buy_aircraft", "auto_buy_hub",
                  "max_single_investment", "max_daily_spend", "max_cycle_spend", "max_acquisitions_per_day",
                  "min_daily_profit", "max_payback_days", "profit_weight", "efficiency_weight",
                  "return_weight", "risk_weight", "confidence_weight", "diversification_weight"}
        values = payload.get("policy")
        version = payload.get("expected_version")
        if (not isinstance(values, dict) or set(values) != fields
                or type(version) is not int):
            return False, "Política incompleta ou versão inválida. Atualize o painel."
        for key in ("planning_enabled", "auto_buy_aircraft", "auto_buy_hub"):
            if type(values[key]) is not bool:
                return False, f"{key} deve ser verdadeiro ou falso."
        if not isinstance(values["mode"], str) or values["mode"] not in MODES:
            return False, "Modo de investimento inválido."
        for key, upper in (("max_single_investment", 10**15), ("max_daily_spend", 10**15),
                           ("max_cycle_spend", 10**15),
                           ("max_acquisitions_per_day", 100), ("min_daily_profit", 10**15),
                           ("max_payback_days", 3650), ("profit_weight", 100),
                           ("efficiency_weight", 100), ("return_weight", 100), ("risk_weight", 100),
                           ("confidence_weight", 100), ("diversification_weight", 100)):
            amount = values[key]
            if type(amount) is not int or amount < 0 or amount > upper:
                return False, f"{key} deve ser um inteiro entre 0 e {upper}."
        if not any(values[key] for key in ("profit_weight", "efficiency_weight", "return_weight", "risk_weight",
                                               "confidence_weight", "diversification_weight")):
            return False, "Configure pelo menos um peso positivo para o ranking."
        with self.cfg._lock:
            if version != self.cfg.version:
                return False, "Configurações alteradas em outra sessão. Atualize antes de salvar."
            for key in fields:
                value = values[key]
                self.cfg.set("investment", key, "on" if value is True else "off" if value is False else value)
            self.cfg.save()
        log.info("Política de investimento do perfil salva pelo painel (gate G0).")
        return True, "Política salva. Execução de compras permanece indisponível em G0."

    def stop_investment(self) -> tuple[bool, str]:
        """Disable new investment and the existing automatic aircraft buyer."""
        with self.cfg._lock:
            self.cfg.set("investment", "planning_enabled", "off")
            self.cfg.set("investment", "auto_buy_aircraft", "off")
            self.cfg.set("investment", "auto_buy_hub", "off")
            self.cfg.set("options", "autobuy_aircraft", "off")
            self.cfg.save()
        log.warning("Novas aquisições de aeronaves/hubs suspensas manualmente pelo painel.")
        return True, "Novas compras de aeronaves e hubs suspensas, incluindo a compra automática legada."

    def update_settings(self, payload: dict) -> tuple[bool, str]:
        known_fields = {k for k, _ in ALL_FIELDS}
        known_switches = {k for k, _ in ALL_SWITCHES}
        numbers: dict[str, int] = {}
        for key, raw in (payload.get("settings") or {}).items():
            value = parse_int(raw)
            if key not in known_fields or value is None:
                return False, t("«{key}» deve ser um número inteiro.", key=key)
            numbers[key] = value
        options = payload.get("options") or {}
        texts = payload.get("text") or {}
        unknown = [k for k in options if k not in known_switches] + [k for k in texts if k not in dict(TEXT_SETTINGS)]
        if unknown:
            return False, t("Configuração desconhecida: «{key}».", key=unknown[0])
        if numbers:
            current = {k: self.cfg.get_int("settings", k) for k in ("cycle_min_minutes", "cycle_max_minutes")}
            numbers = clamp_settings({**current, **numbers})
        for key, value in numbers.items():
            self.cfg.set("settings", key, value)
        for key, value in options.items():
            self.cfg.set("options", key, "on" if value else "off")
            if key in ("auto_marketing", "marketing_eco"):
                self.bot.marketing_next_check = 0.0
        if "engine_preference" in texts:
            try:
                from engine_selection import validate_preference
                texts["engine_preference"] = validate_preference(str(texts["engine_preference"]))
            except ValueError as exc:
                return False, str(exc)
        for key, value in texts.items():
            value = str(value).strip()[:80]
            self.cfg.set("settings", key, "auto" if key == "goal_model" and is_auto_goal(value) else value)
        self.cfg.save()
        log.info("Configurações salvas pelo painel web.")
        return True, t("Salvo.")

    def control(self, action: str) -> tuple[bool, str]:
        if action == "telegram_test":
            from notify import Telegram
            self.cfg.reload_secrets()
            token, chat_id = self.cfg.telegram
            if not token or not chat_id:
                return False, t("Telegram não configurado: informe bot_token e chat_id em config/secrets.ini.")
            ok, detail = Telegram(token, chat_id).send_now("✅ <b>Teste AM/04</b>: notificações conectadas.")
            if not ok:
                log.warning("Teste do Telegram falhou: %s", detail)
            return (True, t("Mensagem de teste enviada ao Telegram.")) if ok else (
                False, t("Não foi possível enviar a mensagem. Consulte os registros do servidor.")
            )
        if action == "start":
            if self.bot.is_alive():
                return False, t("O bot já está em execução.")
            self.start_bot()
            return True, t("Iniciando o bot ...")
        if action == "stop":
            if not self.bot.is_alive():
                return False, t("O bot já está parado.")
            log.info("Interrompendo após a etapa atual (pelo painel web) ...")
            self.bot.stop()
            return True, t("Parando ...")
        if action == "run_now":
            self.bot.run_now()
            return True, t("Verificando agora.")
        if action == "quit" and self.on_quit is not None:
            log.info("Fechando o programa (solicitação pelo painel web) ...")
            self.on_quit()
            return True, t("Fechando ...")
        return False, t("Ação desconhecida.")

    # ------------------------------------------------------------------ HTTP
    def _handler(self):
        dashboard = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "AM4Bot"

            def log_message(self, *_args) -> None:  # keep HTTP noise out of the bot log
                pass

            # -- access control
            def _allowed(self, *, require_token: bool = False,
                         allow_query_token: bool = True) -> bool:
                token = dashboard.cfg.web_token
                if token:
                    query = (parse_qs(urlparse(self.path).query).get("token", [""])[0]
                             if allow_query_token else "")
                    cookies = dict(part.strip().split("=", 1) for part in (self.headers.get("Cookie") or "").split(";")
                                   if "=" in part)
                    given = query or cookies.get(COOKIE, "") or self.headers.get("X-Token", "")
                    return hmac.compare_digest(given.encode(), token.encode())
                if require_token:
                    return False
                host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
                return _is_loopback(host)

            def _send(self, status: int, body: bytes, content_type: str, extra: Optional[dict] = None) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                for key, value in (extra or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)

            def _json(self, data, status: int = 200) -> None:
                self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

            def _deny(self) -> None:
                self._send(HTTPStatus.FORBIDDEN, "Acesso negado: abra a página com ?token=...".encode("utf-8"),
                           "text/plain; charset=utf-8")

            def do_GET(self) -> None:  # noqa: N802 - http.server API
                if not self._allowed():
                    return self._deny()
                url = urlparse(self.path)
                if url.path in ("/", "/index.html"):
                    extra = {}
                    token = dashboard.cfg.web_token
                    if token:
                        extra["Set-Cookie"] = f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000"
                    try:
                        body = PAGE.read_bytes()
                    except OSError:
                        return self._send(HTTPStatus.NOT_FOUND, b"assets/web/index.html not found", "text/plain")
                    return self._send(200, body, "text/html; charset=utf-8", extra)
                if url.path == "/api/status":
                    return self._json(dashboard.status())
                if url.path == "/api/log":
                    since = parse_int(parse_qs(url.query).get("since", ["0"])[0]) or 0
                    return self._json({"lines": dashboard.buffer.since(since)})
                if url.path == "/api/settings":
                    return self._json(dashboard.settings())
                if url.path == "/api/investment/policy":
                    return self._json(dashboard.investment_settings())
                if url.path == "/api/investment/metrics":
                    status, report = dashboard.investment_metrics()
                    return self._json(report, status)
                if url.path == "/api/investment/audited-expansion":
                    return self._json(dashboard.audited_expansion())
                if url.path == "/api/investment/audited-expansion/research":
                    params = parse_qs(url.query)
                    raw_offset = params.get("research_offset", ["0"])[0]
                    offset = int(raw_offset) if raw_offset.isdecimal() and len(raw_offset) <= 9 else 0
                    return self._json(replay_research_page(
                        offset=offset, expected_snapshot=params.get("snapshot_id", [None])[0],
                        expected_fingerprint=params.get("research_snapshot", [None])[0],
                    ))
                if url.path == "/api/routes":
                    return self._json(dashboard.routes())
                if url.path == "/api/hubs":
                    return self._json(dashboard.hubs())
                if url.path == "/api/hubs/expansion":
                    return self._json(dashboard.hub_expansion())
                if url.path == "/api/hubs/expansion/research":
                    params = parse_qs(url.query)
                    raw_offset = params.get("research_offset", ["0"])[0]
                    research_offset = (int(raw_offset) if raw_offset.isdecimal()
                                       and len(raw_offset) <= 9 else 0)
                    return self._json(dashboard.external_hub_research(
                        research_offset=research_offset,
                        research_fingerprint=params.get("research_snapshot", [None])[0],
                    ))
                if url.path == "/api/hubs/recommendations":
                    params = parse_qs(url.query)
                    raw_offset = params.get("research_offset", ["0"])[0]
                    research_offset = (int(raw_offset) if raw_offset.isdecimal()
                                       and len(raw_offset) <= 9 else 0)
                    if research_offset:
                        return self._json(dashboard.hub_recommendations(
                            research_offset=research_offset,
                            research_fingerprint=params.get("research_snapshot", [None])[0],
                        ))
                    return self._json(dashboard.hub_recommendations())
                self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain")

            def do_POST(self) -> None:  # noqa: N802 - http.server API
                path = urlparse(self.path).path
                admin_probe = path in ("/api/admin/game-source-probe", "/api/admin/flight-history-probe")
                policy_action = path in ("/api/investment/policy", "/api/investment/stop")
                if (not self._allowed(require_token=admin_probe,
                                      allow_query_token=not (admin_probe or policy_action))
                        or self.headers.get("X-AM4") != "1"):
                    return self._deny()
                length = parse_int(self.headers.get("Content-Length", "0")) or 0
                if length > MAX_BODY:
                    return self._json({"ok": False, "message": "Solicitação muito grande."}, 413)
                try:
                    payload = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    return self._json({"ok": False, "message": "JSON inválido."}, 400)
                if not isinstance(payload, dict):
                    return self._json({"ok": False, "message": "JSON inválido."}, 400)
                if admin_probe:
                    if path == "/api/admin/game-source-probe":
                        if payload:
                            return self._json({"ok": False, "message": "Envie um objeto JSON vazio."}, 400)
                        status, report = dashboard.game_source_probe()
                    else:
                        aircraft_id = payload.get("aircraft_id")
                        if (set(payload) != {"aircraft_id"} or type(aircraft_id) is not str
                                or re.fullmatch(r"[1-9][0-9]{0,13}", aircraft_id) is None):
                            return self._json({"ok": False, "message": "Informe um ID de aeronave válido."}, 400)
                        status, report = dashboard.flight_history_probe(aircraft_id)
                    return self._json(report, status)
                if path == "/api/settings":
                    ok, message = dashboard.update_settings(payload)
                elif path == "/api/investment/policy":
                    ok, message = dashboard.update_investment_settings(payload)
                elif path == "/api/investment/stop":
                    if payload:
                        return self._json({"ok": False, "message": "Envie um objeto JSON vazio."}, 400)
                    ok, message = dashboard.stop_investment()
                elif path == "/api/routes":
                    ok, message = dashboard.update_routes(payload)
                elif path == "/api/control":
                    ok, message = dashboard.control(str(payload.get("action", "")))
                else:
                    return self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain")
                self._json({"ok": ok, "message": message}, 200 if ok else 400)

        return Handler
