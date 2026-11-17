"""Read-only identification of the AM4 operational audit interlock.

Airline Manager 4 blocks all flight departures during a company audit.
Do not interpret disabled Depart buttons as a Selenium selector failure.
"""
from __future__ import annotations

import logging

from selenium.common.exceptions import WebDriverException

log = logging.getLogger("am4bot.vuelos")

_AUDIT_JS = r"""
const text = document.body ? (document.body.innerText || "") : "";
const audit = /\b(?:your company is subject to audit|company is under audit|compa(?:ñ|n)ia.*auditor[ií]a|companhia.*auditoria)\b/i.test(text);
const suspended = /(?:will not be able to operate your fleet|no pod(?:rá|ra) operar su flota|não pod(?:erá|era) operar sua frota)/i.test(text);
return audit && suspended;
"""


def audit_active(bot) -> bool:
    """Check only visible UI text; do not interact with the audit dialog."""
    js = getattr(bot, "js", None)
    if not callable(js):
        return False
    try:
        return js(_AUDIT_JS) is True
    except WebDriverException as exc:
        log.warning("Não foi possível verificar o aviso de auditoria (%s).",
                    type(exc).__name__)
        return False
