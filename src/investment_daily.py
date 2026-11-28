"""Opt-in daily investment audit sent from the bot's read-only worker cycle."""
from __future__ import annotations

import logging
import secrets
import sqlite3
import time
from pathlib import Path

from expansion_metrics import build_expansion_metrics
from investment_journal import InvestmentJournal
from investment_policy import InvestmentPolicy
from notify import MAX_LENGTH, esc
from web import WebDashboard

log = logging.getLogger("am4bot.telegram")

_CLAIM_LEASE_SECONDS = 300

_PORTFOLIO_BLOCKER_LABELS = {
    "politica_invalida": "política inválida",
    "cobertura_frota_a_confirmar": "cobertura da frota a confirmar",
    "cobertura_pesquisa_a_confirmar": "cobertura das pesquisas a confirmar",
    "pedidos_pendentes_a_conciliar": "pedidos e compromissos a conciliar",
    "vagas_hangar_a_confirmar": "vagas de hangar a confirmar",
    "hangar_sem_vaga": "hangar sem vaga",
    "aeronaves_sem_rota_a_resolver": "aeronaves sem rota a resolver",
    "contagens_frota_divergentes": "contagens da frota divergentes",
    "aeronaves_sem_rota_a_confirmar": "aeronaves sem rota a confirmar",
    "identidades_frota_divergentes": "identidades da frota divergentes",
    "identidades_frota_a_confirmar": "identidades da frota a confirmar",
    "saldo_disponivel_a_confirmar": "saldo disponível a confirmar",
    "compromissos_invalidos": "compromissos inválidos",
    "reservas_locais_invalidas": "reservas locais inválidas",
    "limites_periodo_invalidos": "limites de gasto do período inválidos",
    "uso_periodo_a_confirmar": "gastos e aquisições do período a confirmar",
    "limite_periodo_esgotado_na_observacao": "limite de gasto esgotado na observação de 24 horas",
    "criterios_planejamento_invalidos": "critérios de planejamento inválidos",
    "cenarios_proprios_pendentes": "cenários de hubs próprios pendentes",
    "pesquisas_conflitantes": "pesquisas conflitantes",
    "diario_indisponivel": "diário de investimentos indisponível",
    "intencoes_locais_a_conciliar": "intenções locais de investimento a conciliar",
    "criacao_rota_a_conciliar": "criação de rota a conciliar",
    "redirecionamento_a_conciliar": "redirecionamento a conciliar",
    "diario_rotas_indisponivel": "diário de rotas indisponível",
    "evidencia_risk_a_confirmar": "evidência de risco a confirmar",
    "evidencia_confidence_a_confirmar": "evidência de confiabilidade a confirmar",
    "evidencia_diversification_a_confirmar": "evidência de diversificação a confirmar",
}


class DailyInvestmentDelivery:
    """Reserve one daily send per profile and acknowledge Telegram delivery."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS investment_daily_delivery (
                profile_id TEXT NOT NULL,
                report_day TEXT NOT NULL,
                claim_id TEXT,
                claimed_at REAL,
                delivered_at REAL,
                PRIMARY KEY (profile_id, report_day)
            )""")

    def claim(self, profile_id: str, report_day: str, *, now: float) -> str | None:
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT claim_id, claimed_at, delivered_at FROM investment_daily_delivery "
                "WHERE profile_id=? AND report_day=?", (profile_id, report_day),
            ).fetchone()
            if row and (row[2] is not None or
                        (row[0] is not None and row[1] is not None
                         and now - row[1] < _CLAIM_LEASE_SECONDS)):
                return None
            token = secrets.token_hex(16)
            conn.execute("""INSERT INTO investment_daily_delivery
                (profile_id, report_day, claim_id, claimed_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(profile_id, report_day) DO UPDATE SET
                    claim_id=excluded.claim_id, claimed_at=excluded.claimed_at""",
                (profile_id, report_day, token, now),
            )
            return token

    def acknowledge(self, profile_id: str, report_day: str, token: str,
                    *, delivered: bool, now: float) -> None:
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if delivered:
                conn.execute("""UPDATE investment_daily_delivery SET
                    claim_id=NULL, claimed_at=NULL, delivered_at=?
                    WHERE profile_id=? AND report_day=? AND claim_id=?""",
                    (now, profile_id, report_day, token),
                )
            else:
                conn.execute("""DELETE FROM investment_daily_delivery
                    WHERE profile_id=? AND report_day=? AND claim_id=? AND delivered_at IS NULL""",
                    (profile_id, report_day, token),
                )


def format_investment_daily(metrics: dict, *, date_label: str, planning_enabled: bool,
                            investment_mode: str = "analyze",
                            auto_buy_aircraft: bool = False,
                            auto_buy_hub: bool = False,
                            policy_report: dict | None = None) -> str:
    """Distinguish local plans, independently confirmed orders, and missing facts."""
    policy = policy_report or {
        "planning_enabled": planning_enabled,
        "mode": investment_mode,
        "auto_buy_aircraft": auto_buy_aircraft,
        "auto_buy_hub": auto_buy_hub,
        "valid": True,
        "execution_available": False,
        "legacy_autobuy_aircraft": False,
        "blocking_reasons": [],
    }
    planning_enabled = bool(policy["planning_enabled"])
    investment_mode = str(policy["mode"])
    auto_buy_aircraft = bool(policy["auto_buy_aircraft"])
    auto_buy_hub = bool(policy["auto_buy_hub"])
    policy_valid = bool(policy["valid"])
    execution_available = bool(policy["execution_available"])
    legacy_autobuy_aircraft = bool(policy["legacy_autobuy_aircraft"])
    journal = metrics["journal"]
    coverage = metrics["research_coverage"]
    opportunities = metrics["opportunities"]
    is_simulation = metrics["environment"] == "simulation"
    coverage_status = coverage["status"]

    reasons = []
    if is_simulation:
        reasons.append("simulação ativa")
    if not planning_enabled:
        reasons.append("planejamento de investimentos desligado")
    elif investment_mode == "analyze":
        reasons.append("modo de investimentos somente análise")
    elif investment_mode == "approval":
        reasons.append("aquisições dependem de aprovação")
    elif not auto_buy_aircraft and not auto_buy_hub:
        reasons.append("compras automáticas de hubs e aeronaves desligadas")
    if not policy_valid:
        reasons.append("configuração da política de investimentos inválida")
    if "limites_de_gasto_a_configurar" in policy.get("blocking_reasons", []):
        reasons.append("limites de gasto da política autônoma não configurados")
    if not execution_available:
        reasons.append("executor de compras aguarda homologação G0")
    if coverage_status != "complete":
        reasons.append("pesquisa dos hubs sem cobertura comprovada")
    if opportunities["evaluated_count"] is None:
        reasons.append("avaliação de oportunidades indisponível")
    elif (coverage_status == "complete" and opportunities["eligible_count"] == 0
          and opportunities["status"] == "conclusivo"):
        reasons.append("nenhuma oportunidade elegível na avaliação")
    portfolio_blockers = metrics.get("portfolio_blocking_reasons")
    if portfolio_blockers is not None:
        reasons.extend(_PORTFOLIO_BLOCKER_LABELS[code] for code in portfolio_blockers
                       if code in _PORTFOLIO_BLOCKER_LABELS)
        other_count = sum(code not in _PORTFOLIO_BLOCKER_LABELS for code in portfolio_blockers)
        if other_count == 1:
            reasons.append("1 outro impedimento no planejador")
        elif other_count:
            reasons.append(f"{other_count} outros impedimentos no planejador")
    if not reasons:
        reasons.append("investimento depende da política e da revalidação antes da compra")

    evaluated = opportunities["evaluated_count"]
    eligible = opportunities["eligible_count"]
    evaluations = (f"{evaluated} avaliadas, {eligible} elegíveis"
                   if evaluated is not None and eligible is not None
                   else "não comprovadas")
    hubs_total = coverage["hubs_total"]
    hubs_read = coverage["hubs_pesquisados"]
    hubs = (f"{hubs_read}/{hubs_total} hubs com pesquisa iniciada"
            if hubs_total is not None and hubs_read is not None else "hubs sem medição")
    forecast = metrics["forecast"]
    precision = (f"erro médio diário {forecast['mean_absolute_daily_error']} "
                 f"em {forecast['plans']} planos verificados"
                 if forecast["status"] == "calibracao_verificada"
                 else "sem histórico de voo e contabilidade independentes")

    lines = [
        f"📈 <b>Investimentos — {esc(date_label)}</b>",
        "🧪 Ambiente: simulação" if is_simulation else "🎮 Ambiente: jogo",
        "📋 <b>Planejado (últimas 24h)</b>: "
        f"{journal['created_in_window']} novas intenções. "
        f"Compromissos previstos em aberto: ${journal['pending_planned_cost']:,}.",
        "✅ <b>Confirmado no diário (últimas 24h)</b>: "
        f"{journal['confirmed_in_window']} pedidos com confirmação registrada. "
        f"Custo previsto desses pedidos: ${journal['confirmed_planned_cost_in_window']:,}.",
        "🔍 <b>Observado</b>: gasto efetivo, entregas e lucro real ainda sem "
        "comprovação independente do jogo.",
        f"🧭 Cobertura: {esc(coverage_status)} ({esc(hubs)}).",
        f"✈️ Oportunidades: {esc(evaluations)}.",
        f"📊 Previsões: {esc(precision)}.",
        "⛔ <b>Impedimentos / motivo para não comprar</b>: " + esc("; ".join(reasons)) + ".",
        "🧾 Fonte: diário da nova política de investimento por oportunidade. "
        "Pedidos do fluxo legado não são contabilizados.",
        "⚙️ Compra automática legada de aeronaves: "
        f"{'ATIVA' if legacy_autobuy_aircraft else 'desativada'} (fluxo independente).",
    ]
    audited = metrics.get("audited_opportunities", {})
    if not is_simulation:
        scopes = audited.get("scopes")
        scope_labels = {"hubs": "hubs", "fleet": "frota", "routes": "rotas",
                        "models": "modelos", "engines": "motores", "prices": "preços"}
        verified = (", ".join(label for key, label in scope_labels.items() if scopes.get(key) is True)
                    if scopes is not None else "")
        lines.append("🔎 <b>Cobertura auditada atual</b>: " + esc(verified or "sem escopo comprovado") + ".")
        evaluated = audited.get("evaluated_count")
        eligible = audited.get("eligible_count")
        decision = {"nao_comprar": "compra bloqueada", "sugestao_para_analise": "sugestão para análise"}.get(
            audited.get("decision"), "sem decisão auditada atual")
        if evaluated is not None and eligible is not None:
            decision = f"{evaluated} cenários registrados, {eligible} candidatos A4; {decision}"
        lines.append("📋 <b>Planejamento auditado A3/A4</b>: " + esc(decision) + ".")
        blockers = audited.get("blocking_reasons", [])
        if blockers:
            labels = [_PORTFOLIO_BLOCKER_LABELS[code] for code in blockers if code in _PORTFOLIO_BLOCKER_LABELS]
            unknown = len(blockers) - len(labels)
            if unknown:
                labels.append(f"{unknown} impedimento(s) adicional(is) na análise auditada")
            lines.append("⛔ Bloqueios auditados: " + esc("; ".join(labels)) + ".")
    finance = metrics.get("company_finance_24h", {})
    if not is_simulation and finance.get("status") == "observed" and finance.get("summary"):
        summary = finance["summary"]
        lines.insert(4, "💰 <b>Histórico financeiro da companhia (últimas 24h)</b>: "
                     f"receitas ${summary['income']:,}; despesas ${summary['expenses']:,}; "
                     f"resultado ${summary['result']:,}. "
                     f"Despesas históricas com encomendas ${summary['aircraft_orders']:,} "
                     f"e hubs ${summary['hubs']:,}. "
                     "Valores agregados, sem conciliação dos pedidos ou compromissos futuros.")
    if journal["by_state"].get("UNKNOWN", 0):
        lines.append(f"⚠️ Pedidos aguardando conciliação: {journal['by_state']['UNKNOWN']}.")
    if journal["failed_in_window"]:
        lines.append(f"⚠️ Intenções com falha no período: {journal['failed_in_window']}.")
    detection = journal.get("mean_submission_to_unknown_seconds")
    recovery = journal.get("mean_recovery_seconds")
    if detection is not None:
        lines.append(f"⏱ Diário local: envio → incerteza {detection:.1f}s em "
                     f"{journal['uncertain_submissions_detected']} pedidos.")
    if recovery is not None:
        lines.append(f"⏱ Diário local: incerteza → conciliação {recovery:.1f}s em "
                     f"{journal['reconciliations_from_unknown']} pedidos.")
    return "\n".join(lines)


def publish_investment_daily(bot, *, now: float | None = None) -> str:
    """Send once after summary_hour, retrying unacknowledged deliveries."""
    cfg = bot.config
    if (not cfg.get_bool("options", "telegram_investment_daily")
            or not cfg.get_bool("options", "telegram")
            or not bot.telegram.enabled):
        return "disabled"

    current = time.time() if now is None else now
    local = time.localtime(current)
    hour = max(0, min(23, cfg.get_int("settings", "summary_hour", 9)))
    if local.tm_hour < hour:
        return "before_hour"
    report_day = time.strftime("%Y-%m-%d", local)
    delivery = DailyInvestmentDelivery(cfg.profile.data / "investment_daily_delivery.sqlite3")
    token = delivery.claim(cfg.profile.label, report_day, now=current)
    if token is None:
        return "suppressed"

    delivered = False
    try:
        simulation = bool(getattr(bot, "dry_run", False))
        journal_name = "investment_simulation.sqlite3" if simulation else "investment_journal.sqlite3"
        journal = InvestmentJournal(cfg.profile.data / journal_name,
                                    profile_id=cfg.profile.label, simulation=simulation)
        dashboard = WebDashboard(bot, cfg, buffer=None)
        try:
            research = dashboard.hub_recommendations()
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
            research = None
            log.warning("Pesquisa de investimento indisponível no resumo diário.")
        try:
            audited = dashboard.audited_expansion() if not simulation else None
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, AttributeError):
            audited = None
            log.warning("Evidência auditada indisponível no resumo diário.")
        metrics = build_expansion_metrics(journal, now=current, window_days=1,
                                          opportunity_report=research, audited_report=audited)
        policy_report = InvestmentPolicy.from_config(cfg).report()
        message = format_investment_daily(
            metrics, date_label=time.strftime("%d/%m/%Y", local),
            planning_enabled=policy_report["planning_enabled"],
            investment_mode=policy_report["mode"],
            auto_buy_aircraft=policy_report["auto_buy_aircraft"],
            auto_buy_hub=policy_report["auto_buy_hub"],
            policy_report=policy_report,
        )
        if not cfg.profile.is_main:
            message = f"[{esc(cfg.profile.label)}] {message}"
        if len(message) > MAX_LENGTH:
            log.warning("Relatório de investimentos excedeu o limite do Telegram.")
            return "oversized"
        delivered, _description = bot.telegram.send_now(message)
        return "delivered" if delivered else "failed"
    except Exception:
        # Telegram transport exceptions can contain token-bearing URLs.
        log.warning("Falha ao compor ou enviar o resumo diário de investimentos.")
        return "failed"
    finally:
        delivery.acknowledge(cfg.profile.label, report_day, token,
                             delivered=delivered, now=time.time())
