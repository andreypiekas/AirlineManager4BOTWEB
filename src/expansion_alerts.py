"""Read-only expansion alerts from the same registries used by the web panel."""
from __future__ import annotations

import hashlib
import json
import logging

from expansion_reporting import ExpansionAlertDeduplicator, build_expansion_report
from notify import MAX_LENGTH, esc
from web import WebDashboard

log = logging.getLogger("am4bot.telegram")


def publish_expansion_alert(bot) -> str:
    """Send only proven A6 recommendations, acknowledging actual Telegram delivery.

    Every input comes from persisted game observations. An incomplete survey
    cannot make an external-hub recommendation alertable. All reads happen in
    the bot's worker cycle and never mutate the authenticated game session.
    """
    config = bot.config
    if (not config.get_bool("investment", "planning_enabled")
            or not config.get_bool("options", "telegram_expansion")
            or not config.get_bool("options", "telegram")
            or not bot.telegram.enabled):
        return "disabled"

    dashboard = WebDashboard(bot, config, buffer=None)
    inventory = dashboard.hubs()
    research = dashboard.hub_recommendations()
    external = dashboard.hub_expansion(owned_inventory=inventory, owned_research=research)
    evidence = {"inventory": inventory, "research": research, "external": external}
    canonical = json.dumps(evidence, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False)
    snapshot_id = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    report = build_expansion_report(
        research, external, profile_id=config.profile.label,
        snapshot_id=snapshot_id, owned_inventory=inventory,
        owned_research=research,
        opportunity_coverage=research.get("opportunity_coverage"),
    )
    if not report["alertable"]:
        return report["status"]

    deduplicator = ExpansionAlertDeduplicator(config.profile.data / "expansion_alerts.sqlite3")
    claim = deduplicator.claim(report)
    if claim is None:
        return "suppressed"

    message = claim["html"]
    if not config.profile.is_main:
        message = f"[{esc(config.profile.label)}] {message}"
    if len(message) > MAX_LENGTH:
        # Telegram._post truncates long messages, which can cut HTML or omit
        # candidate costs. Never acknowledge a partial recommendation.
        deduplicator.acknowledge(claim, delivered=False)
        log.warning("Recomendação de expansão excedeu o limite seguro do Telegram.")
        return "oversized"
    delivered, _description = bot.telegram.send_now(message)
    deduplicator.acknowledge(claim, delivered=delivered)
    if delivered:
        log.info("Recomendação de expansão confirmada pelo Telegram (%s).", claim["reason"])
        return "delivered"
    log.warning("Telegram não confirmou a entrega da recomendação de expansão.")
    return "failed"
