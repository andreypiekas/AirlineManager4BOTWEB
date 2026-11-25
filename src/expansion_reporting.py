"""Read-only A6 expansion reports and durable Telegram alert deduplication.

``build_expansion_report(owned, external, profile_id=..., snapshot_id=...)``
accepts dictionaries or JSON objects. ``owned`` is the output of
``compare_portfolio`` or a hub report containing ``portfolio``. ``external`` is
the output of ``HubExpansionRegistry.snapshot``. Enriched scenarios may also
provide engine_id, engine_label, engine_verified, engine_delta_cost,
aircraft_price_includes_engine, other_fees, reserve and excluded_costs.

The formatter reports unknown costs and unverified evidence explicitly. It
never approves purchases or sends messages. Call ``claim`` on the returned
report, send the claim's ``html`` with Telegram HTML parse mode, and then call
``acknowledge`` with the actual delivery result. Pending claims expire so a
crash cannot permanently silence alerts.
"""
from __future__ import annotations

import html
import json
import math
import re
import secrets
import sqlite3
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from expansion_feasibility import assess_expansion
from hub_expansion import (MAX_AGE_SECONDS, MAX_FINANCIAL_VALUE, excluded_research_costs,
                           native_scenario_identity)
from investment_policy import InvestmentPolicy


MAX_HTML_LENGTH = 3900  # notify.py sends at most 4000 of Telegram's 4096 characters.
DEFAULT_COOLDOWN_SECONDS = 6 * 3600
CLAIM_LEASE_SECONDS = 300
_PROFILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
_SNAPSHOT = re.compile(r"^sha256:[0-9a-f]{64}$")
_HUB_ID = re.compile(r"^[1-9][0-9]{0,11}$")
_MATERIAL_FIELDS = ("hub", "aircraft", "model_id", "engine_id", "motor", "route",
                    "origin_id", "destination_id", "stopover_id", "status", "pending",
                    "excluded", "points", "sources")
_NUMERIC_FIELDS = ("hub_price", "aircraft_price", "engine_cost", "route_fee", "hangar_cost",
                   "other_fees", "reserve", "investment", "cash_required", "profit", "payback")


def _object(data: object, name: str) -> Mapping[str, Any]:
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError as exc:
            raise ValueError(f"{name} deve conter um objeto JSON válido") from exc
    if not isinstance(data, Mapping):
        raise ValueError(f"{name} deve ser um dicionário ou objeto JSON")
    return data


def _number(value: object, *, positive: bool = False) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(number) or abs(number) > MAX_FINANCIAL_VALUE or (positive and number <= 0):
        return None
    return number


def _amount(value: object) -> float | None:
    number = _number(value)
    return number if number is not None and number >= 0 else None


def _timestamp_fresh(value: object, now: float, max_age_seconds: int) -> bool:
    number = _number(value, positive=True)
    return number is not None and 0 <= now - number <= max_age_seconds


def _text(value: object, *, max_length: int = 75) -> str:
    """Limit escaped output by complete HTML entities, never by slicing tags."""
    raw = " ".join(str(value).split()) if value is not None else ""
    raw = raw or "a confirmar"
    escaped = []
    used = 0
    for char in raw:
        entity = html.escape(char, quote=True)
        if used + len(entity) > max_length - 1:
            escaped.append("…")
            break
        escaped.append(entity)
        used += len(entity)
    return "".join(escaped)


def _money(value: float | None) -> str:
    if value is None:
        return "a confirmar"
    number = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"$ {number}"


def _label(value: object) -> str:
    return _text(value, max_length=55)


def _reasons(owned: Mapping[str, Any], portfolio: Mapping[str, Any]) -> list[str]:
    details = []
    hubs = owned.get("hubs")
    if isinstance(hubs, list):
        for hub in hubs:
            if isinstance(hub, Mapping) and isinstance(hub.get("status"), str):
                name = hub.get("code") or hub.get("name") or hub.get("id") or "Hub sem identificação"
                details.append(f"{name}: {hub['status'].replace('_', ' ')}")
    excluded = portfolio.get("excluded")
    if isinstance(excluded, Mapping):
        for reason, count in sorted(excluded.items()):
            if isinstance(reason, str) and type(count) is int and count > 0:
                details.append(f"{reason.replace('_', ' ')} ({count})")
    blockers = portfolio.get("blocking_reasons")
    if isinstance(blockers, list):
        details.extend(item.replace("_", " ") for item in blockers if isinstance(item, str))
    return list(dict.fromkeys(details))


def _external_with_scoped_evidence(external: Mapping[str, Any], profile_id: str,
                                   snapshot_id: str) -> Mapping[str, Any]:
    """Exclude mismatched nested proofs before the feasibility gate ranks rows.

    The input may be backed by a registry snapshot and must remain immutable.
    Missing optional scope metadata stays compatible with historical records.
    """
    rows = external.get("candidates")
    if not isinstance(rows, list):
        return external
    scoped = []
    for row in rows:
        if not isinstance(row, Mapping):
            scoped.append(row)
            continue
        scenario = row.get("scenario")
        costs = scenario.get("costs") if isinstance(scenario, Mapping) else None
        financial = scenario.get("financial") if isinstance(scenario, Mapping) else None
        proofs = (row, scenario, costs, financial, row.get("cost_breakdown"))
        mismatch = any(
            isinstance(proof, Mapping) and (
                proof.get("profile_id") not in (None, profile_id)
                or proof.get("snapshot_id") not in (None, snapshot_id)
            )
            for proof in proofs
        )
        scoped.append({**row, "ranking_conclusive": False} if mismatch else row)
    return {**external, "candidates": scoped}


def _candidate(raw: Mapping[str, Any], external: Mapping[str, Any], now: float,
               max_age_seconds: int, profile_id: str, snapshot_id: str) -> dict | None:
    hub_id = str(raw.get("id") or "")
    if not _HUB_ID.fullmatch(hub_id):
        return None
    scenario = raw.get("scenario") if isinstance(raw.get("scenario"), Mapping) else {}
    pending = set()
    for source in (raw, scenario):
        if source.get("profile_id") is not None and source["profile_id"] != profile_id:
            pending.add("perfil divergente")
        if source.get("snapshot_id") is not None and source["snapshot_id"] != snapshot_id:
            pending.add("snapshot da evidência divergente")
    if external.get("source") != "game_purchase_catalog" or external.get("catalog_complete") is not True:
        pending.add("catálogo externo incompleto ou sem fonte")
    if not _timestamp_fresh(raw.get("observed_at", external.get("observed_at")), now, max_age_seconds):
        pending.add("preço do hub sem data válida")
    if scenario.get("source") != "game_research" or not _timestamp_fresh(
        scenario.get("observed_at"), now, max_age_seconds
    ):
        pending.add("pesquisa do cenário sem evidência recente")
    if raw.get("status") != "viavel":
        pending.add(f"situação informada: {raw.get('status') or 'desconhecida'}")

    model = scenario.get("model")
    identity = native_scenario_identity(scenario)
    if identity is None or identity[-1] is not None:
        pending.add("identidade nativa ou regras de escala a confirmar")
    for field in ("costs", "financial"):
        proof = scenario.get(field)
        if (identity is None or not isinstance(proof, Mapping)
                or native_scenario_identity(proof) != identity):
            pending.add("identidade econômica divergente")
    engine_id = scenario.get("engine_id")
    engine_label = scenario.get("engine_label")
    route = scenario.get("route")
    if not isinstance(model, str) or not model.strip():
        pending.add("modelo a confirmar")
    if not isinstance(engine_id, (str, int)) or isinstance(engine_id, bool) or not str(engine_id).strip():
        pending.add("variante do motor a confirmar")
        engine_id = None
    if scenario.get("engine_verified") is not True:
        pending.add("seleção do motor sem verificação")
    if not isinstance(route, str) or not route.strip():
        pending.add("rota a confirmar")
    if scenario.get("route_feasible") is not True:
        pending.add("viabilidade física da rota a confirmar")
    if scenario.get("demand_verified") is not True:
        pending.add("demanda pré-compra a confirmar")

    hub_price = _amount(raw.get("hub_price"))
    aircraft_price = _amount(scenario.get("aircraft_price"))
    route_fee = _amount(scenario.get("route_fee"))
    hangar_cost = _amount(scenario.get("hangar_price"))
    other_fees = _amount(scenario.get("other_fees"))
    reserve = _amount(scenario.get("reserve"))
    points = raw.get("hub_points")
    if type(points) is not int or points < 0:
        points = None
        pending.add("pontos necessários a confirmar")
    includes_engine = scenario.get("aircraft_price_includes_engine")
    explicit_engine_cost = _amount(scenario.get("engine_delta_cost"))
    if includes_engine is True and explicit_engine_cost not in (None, 0):
        pending.add("preço de motor contraditório")
        engine_cost = None
    elif includes_engine is True:
        engine_cost = 0.0
    elif includes_engine is False:
        engine_cost = explicit_engine_cost
    else:
        engine_cost = None
        pending.add("composição do preço do motor a confirmar")
    costs = {"hub_price": hub_price, "aircraft_price": aircraft_price,
             "engine_cost": engine_cost, "route_fee": route_fee,
             "hangar_cost": hangar_cost, "other_fees": other_fees}
    if any(value is None for value in costs.values()):
        pending.add("custos completos a confirmar")
    if reserve is None:
        pending.add("reserva operacional a confirmar")
    investment = round(sum(costs.values()), 2) if all(v is not None for v in costs.values()) else None
    declared_investment = _amount(raw.get("investment"))
    if declared_investment is not None and investment is not None and abs(declared_investment - investment) > 0.02:
        pending.add("investimento diverge dos componentes")
        investment = None
    cash_required = round(investment + reserve, 2) if investment is not None and reserve is not None else None
    available_cash = _amount(external.get("available_cash"))
    if available_cash is None:
        pending.add("saldo disponível a confirmar")
    elif investment is not None and investment > available_cash:
        pending.add("saldo insuficiente para investimento e reserva")

    profit = _number(scenario.get("profit_per_day"))
    declared_profit = _number(raw.get("profit_per_day"))
    if declared_profit is not None and profit is not None and abs(declared_profit - profit) > 0.02:
        pending.add("projeção de lucro contraditória")
        profit = None
    if profit is None or profit <= 0:
        pending.add("lucro incremental positivo a confirmar")
    payback = round(investment / profit, 1) if investment is not None and profit is not None and profit > 0 else None
    declared_payback = _number(raw.get("payback_days"))
    if (declared_payback is not None and payback is not None
            and abs(declared_payback - payback) > max(0.2, payback * 0.02)):
        pending.add("prazo de retorno contraditório")
        payback = None
    excluded = scenario.get("excluded_costs")
    if not isinstance(excluded, list) or not all(isinstance(value, str) for value in excluded):
        excluded = []
        pending.add("custos excluídos da projeção a confirmar")
    if excluded:
        pending.add("projeção com custos excluídos")
    reported_pending = raw.get("pending")
    if isinstance(reported_pending, list):
        pending.update(item.replace("_", " ") for item in reported_pending if isinstance(item, str))

    return {
        "hub": f"{raw.get('code') or raw.get('name') or hub_id} (ID {hub_id})",
        "hub_id": hub_id, "aircraft": model if isinstance(model, str) else None,
        "model_id": scenario.get("model_id"),
        "engine_id": str(engine_id) if engine_id is not None else None,
        "motor": engine_label or f"ID {engine_id}" if engine_id is not None else None,
        "route": route if isinstance(route, str) else None, "points": points,
        "origin_id": scenario.get("origin_id"),
        "destination_id": scenario.get("destination_id"),
        "stopover_id": scenario.get("stopover_id"),
        **costs, "reserve": reserve, "investment": investment, "cash_required": cash_required,
        "profit": profit, "payback": payback, "pending": sorted(pending),
        "excluded": sorted(set(excluded)), "status": "análise consistente" if not pending else "dados a confirmar",
        "engine_included": includes_engine is True and engine_cost == 0,
    }


def _candidate_html(row: Mapping[str, Any], rank: int) -> str:
    motor_cost = "incluído" if row["engine_included"] else _money(row["engine_cost"])
    pending = row["pending"][:5]
    excluded = row["excluded"][:3]
    pending_summary = ", ".join(_text(value, max_length=60) for value in pending) or "nenhuma identificada"
    if len(row["pending"]) > len(pending):
        pending_summary += f" (+{len(row['pending']) - len(pending)} outras)"
    excluded_summary = ", ".join(_label(value) for value in excluded) or "nenhum declarado"
    if len(row["excluded"]) > len(excluded):
        excluded_summary += f" (+{len(row['excluded']) - len(excluded)} outros)"
    sources = row["sources"]
    observed = row["observed_at"]
    evidence_dates = ", ".join(
        f"{label} {time.strftime('%d/%m %H:%M', time.gmtime(observed[key]))}"
        for key, label in (("catalog", "catálogo"), ("research", "pesquisa"),
                           ("prices", "custos"), ("forecast", "projeção"))
    )
    return "\n".join([
        f"<b>{rank}. {_text(row['hub'], max_length=80)}</b> — {_label(row['status'])}",
        f"Aeronave <b>{_label(row['aircraft'])}</b> · Motor <b>{_label(row['motor'])}</b>",
        f"Rota {_text(row['route'], max_length=90)} · Pontos {_label(row['points'])}",
        f"Custos: hub {_money(row['hub_price'])} · aeronave {_money(row['aircraft_price'])} · motor {motor_cost}",
        f"Rota {_money(row['route_fee'])} · hangar {_money(row['hangar_cost'])} · taxas {_money(row['other_fees'])}",
        f"Investimento <b>{_money(row['investment'])}</b> · reserva {_money(row['reserve'])}",
        f"Caixa necessário {_money(row['cash_required'])}",
        f"Lucro/dia projetado {_money(row['profit'])} · retorno estimado {_label(row['payback'])} dias",
        f"Excluídos: {excluded_summary}",
        f"Pendências: {pending_summary}",
        "Fontes verificadas: catálogo {} · pesquisa {} · custos {} · previsão {}".format(
            *(_label(sources[key]) for key in ("catalog", "research", "prices", "forecast"))
        ),
        f"Datas da evidência (UTC): {evidence_dates}",
    ])


def _verified_candidate(raw: Mapping[str, Any], external: Mapping[str, Any],
                        profile_id: str, snapshot_id: str) -> dict | None:
    """Format only candidates already independently admitted by the A6 gate."""
    if any(raw.get(key) is not None and raw[key] != expected for key, expected in (
        ("profile_id", profile_id), ("snapshot_id", snapshot_id)
    )):
        return None
    scenario = raw.get("scenario")
    breakdown = raw.get("cost_breakdown")
    if not isinstance(scenario, Mapping) or not isinstance(breakdown, Mapping):
        return None
    costs = scenario.get("costs")
    financial = scenario.get("financial")
    if not isinstance(costs, Mapping) or not isinstance(financial, Mapping):
        return None
    if any(proof.get("profile_id") not in (None, profile_id)
           or proof.get("snapshot_id") not in (None, snapshot_id)
           for proof in (scenario, costs, financial, breakdown)):
        return None
    hub_id = str(raw.get("id") or "")
    if not _HUB_ID.fullmatch(hub_id):
        return None
    excluded = excluded_research_costs(scenario)
    if excluded is None:
        return None
    engine_id = scenario.get("engine_id")
    includes_engine = costs.get("aircraft_price_includes_engine") is True
    pending = ["despesas recorrentes não quantificadas"] if excluded else []
    return {
        "hub": f"{raw.get('code') or raw.get('name') or hub_id} (ID {hub_id})",
        "hub_id": hub_id,
        "aircraft": scenario.get("model"),
        "model_id": scenario.get("model_id"),
        "engine_id": str(engine_id),
        "motor": scenario.get("engine_label") or f"ID {engine_id}",
        "route": scenario.get("route"),
        "origin_id": scenario.get("origin_id"),
        "destination_id": scenario.get("destination_id"),
        "stopover_id": scenario.get("stopover_id"),
        "points": raw.get("hub_points"),
        "hub_price": _amount(breakdown.get("hub_price")),
        "aircraft_price": _amount(breakdown.get("aircraft_price")),
        "engine_cost": _amount(breakdown.get("engine_extra_charged")),
        "route_fee": _amount(breakdown.get("route_fee")),
        "hangar_cost": _amount(breakdown.get("hangar_price")),
        "other_fees": _amount(breakdown.get("other_fees")),
        "reserve": _amount(breakdown.get("reserve")),
        "investment": _amount(raw.get("investment")),
        "cash_required": _amount(breakdown.get("cash_required")),
        "profit": _number(financial.get("profit_per_day"), positive=True),
        "payback": _amount(raw.get("payback_days")),
        "pending": pending,
        "excluded": sorted(set(excluded)),
        "status": "análise consistente" if not pending else "projeção com ressalvas",
        "engine_included": includes_engine,
        "sources": {
            "catalog": external.get("source"), "research": scenario.get("source"),
            "prices": costs.get("source"), "forecast": financial.get("source"),
        },
        "observed_at": {
            "catalog": external.get("observed_at"),
            "research": scenario.get("observed_at"),
            "prices": costs.get("observed_at"),
            "forecast": financial.get("observed_at"),
        },
    }


def build_expansion_report(
    owned_report: Mapping[str, Any] | str,
    external_report: Mapping[str, Any] | str,
    *,
    profile_id: str,
    snapshot_id: str,
    now: float | None = None,
    max_age_seconds: int = MAX_AGE_SECONDS,
    compare_even_if_owned: bool = False,
    owned_inventory: Mapping[str, Any] | None = None,
    owned_research: Mapping[str, Any] | None = None,
    opportunity_coverage: Mapping[str, Any] | None = None,
    policy: InvestmentPolicy | None = None,
    require_snapshot_scope: bool = False,
) -> dict:
    """Prepare a top-three Telegram HTML analysis without granting approval.

    Incomplete owned-hub coverage blocks the assertion that no owned hub can
    buy an aircraft. Explicit ``compare_even_if_owned`` permits a separate
    external comparison only when the owned portfolio itself is conclusive.
    """
    if not isinstance(profile_id, str) or not _PROFILE.fullmatch(profile_id):
        raise ValueError("profile_id inválido")
    if not isinstance(snapshot_id, str) or not _SNAPSHOT.fullmatch(snapshot_id):
        raise ValueError("snapshot_id inválido")
    if type(max_age_seconds) is not int or max_age_seconds <= 0:
        raise ValueError("max_age_seconds inválido")
    now = time.time() if now is None else _number(now)
    if now is None or now <= 0:
        raise ValueError("now inválido")
    owned = _object(owned_report, "owned_report")
    external = _object(external_report, "external_report")
    portfolio = owned.get("portfolio", owned)
    portfolio = _object(portfolio, "portfolio")
    for data in (owned, portfolio, external, owned_inventory, owned_research, opportunity_coverage):
        if data is None:
            continue
        if not isinstance(data, Mapping):
            raise ValueError("evidência deve ser um objeto")
        if data.get("profile_id") is not None and data["profile_id"] != profile_id:
            raise ValueError("dados de outro perfil")
        if data.get("snapshot_id") is not None and data["snapshot_id"] != snapshot_id:
            raise ValueError("dados de outro snapshot")

    decision = assess_expansion(
        owned_inventory, owned_research, portfolio,
        _external_with_scoped_evidence(external, profile_id, snapshot_id),
        coverage=opportunity_coverage, now=now,
        max_age_seconds=max_age_seconds, profile_id=profile_id,
        snapshot_id=snapshot_id,
        policy=policy,
        require_snapshot_scope=require_snapshot_scope,
    )
    # Incomplete external catalog evidence cannot invalidate an otherwise
    # conclusive owned-hub sweep. Keep its independent outcome visible.
    external_only_blocker = decision["blocking_reasons"] == ["catalogo_expansao_incompleto_ou_vencido"]
    complete = (decision["status"] in ("avaliacao_expansao", "priorizar_hubs_proprios")
                or external_only_blocker)
    none_owned = (decision["status"] == "avaliacao_expansao"
                  or external_only_blocker and decision["owned_eligible_count"] == 0)
    reasons = list(dict.fromkeys([*decision["blocking_reasons"], *_reasons(owned, portfolio)]))
    if none_owned:
        owned_summary = "Hubs próprios: nenhuma proposta elegível na comparação concluída."
    elif complete:
        owned_summary = "Hubs próprios: há alternativas elegíveis na comparação."
    else:
        owned_summary = "Hubs próprios: cobertura inconclusiva, sem conclusão sobre oportunidades."
    if not reasons:
        reasons = ["motivos individuais não informados no relatório de origem"]

    candidates = []
    invalid_count = 0
    if decision["status"] == "avaliacao_expansao":
        for raw in decision["top_three"]:
            item = _verified_candidate(raw, external, profile_id, snapshot_id)
            if item is None:
                invalid_count += 1
            else:
                candidates.append(item)

    alertable = none_owned and bool(candidates)

    if not complete:
        status = "inconclusivo"
    elif not none_owned:
        status = "expansao_nao_indicada"
    elif not candidates:
        status = "pesquisa_externa_pendente"
    elif any(candidate["pending"] for candidate in candidates):
        status = "recomendacoes_condicionais"
    else:
        status = "recomendacoes_para_analise"

    lines = ["<b>Planejamento de expansão · AM4</b>", owned_summary]
    lines.append("Motivos/obstáculos: " + "; ".join(_text(reason, max_length=75) for reason in reasons[:4]))
    if len(reasons) > 4:
        lines[-1] += f" (+{len(reasons) - 4} outros)"
    if compare_even_if_owned and not none_owned:
        lines.append("Comparação externa aguardando política de cobertura independente.")
    if not none_owned:
        lines.append("Ranking externo suspenso até conclusão da análise dos hubs próprios ou comparação explícita.")
    elif external_only_blocker:
        lines.append("Catálogo externo incompleto ou vencido. Pesquisa de expansão pendente.")
    elif not candidates:
        lines.append("Nenhuma recomendação externa verificável com a pesquisa recebida.")
    else:
        lines.append("<b>Top 3 hubs externos em estudo</b>")
        lines.append("Critério do ranking: lucro diário por capital investido, com desempate por lucro e custo.")
        lines.extend(_candidate_html(candidate, rank) for rank, candidate in enumerate(candidates, 1))
        if policy is not None:
            count = decision["hub_limit_selection"]["eligible_count"]
            lines.append(f"Hubs dentro dos limites individuais de capital e pontos: {count}.")
    if invalid_count:
        lines.append(f"Registros externos sem identificação válida: {invalid_count}.")
    if decision["external_pending_count"]:
        lines.append(f"Cenários externos com evidência pendente: {decision['external_pending_count']}.")
        obstacles = []
        rows = external.get("candidates")
        for raw in rows if isinstance(rows, list) else []:
            pending = raw.get("pending") if isinstance(raw, Mapping) else None
            if isinstance(pending, list):
                obstacles.extend(item.replace("_", " ") for item in pending if isinstance(item, str))
        obstacles = list(dict.fromkeys(obstacles))
        if obstacles:
            lines.append("Impedimentos externos declarados: " + ", ".join(
                _text(item, max_length=65) for item in obstacles[:3]
            ))
    lines.append("<i>Somente análise. Nenhuma compra aprovada ou executada.</i>")
    message = "\n\n".join(lines)
    if len(message) > MAX_HTML_LENGTH:
        # Optional descriptions can be shortened without cutting HTML tags.
        lines[2] = "Motivos/obstáculos: " + _text(reasons[0], max_length=65) + f" (+{len(reasons) - 1} outros)"
        message = "\n\n".join(lines)
    if len(message) > MAX_HTML_LENGTH:
        raise ValueError("relatório excedeu o limite seguro do Telegram")

    material = {
        "status": status, "owned_summary": owned_summary, "owned_reasons": reasons,
        "candidates": [{key: item[key] for key in (*_MATERIAL_FIELDS, *_NUMERIC_FIELDS)} for item in candidates],
        "invalid_count": invalid_count,
    }
    if policy is not None:
        material["hub_limit_selection"] = decision["hub_limit_selection"]
    return {"profile_id": profile_id, "snapshot_id": snapshot_id, "status": status,
            "html": message, "candidates": candidates, "material": material,
            "alertable": alertable, "read_only": True, "approved": False,
            "purchase_allowed": False, "expansion_decision": decision}


def _material_changed(previous: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    if any(previous.get(key) != current.get(key) for key in
           ("status", "owned_summary", "owned_reasons", "invalid_count", "hub_limit_selection")):
        return True
    old_rows, new_rows = previous.get("candidates"), current.get("candidates")
    if not isinstance(old_rows, list) or not isinstance(new_rows, list) or len(old_rows) != len(new_rows):
        return True
    for old, new in zip(old_rows, new_rows):
        if not isinstance(old, Mapping) or not isinstance(new, Mapping):
            return True
        if any(old.get(key) != new.get(key) for key in _MATERIAL_FIELDS):
            return True
        for field in _NUMERIC_FIELDS:
            a, b = old.get(field), new.get(field)
            if a is None or b is None:
                if a != b:
                    return True
                continue
            a_value, b_value = _number(a), _number(b)
            if a_value is None or b_value is None:
                return True
            if abs(a_value - b_value) >= max(1.0, abs(a_value) * 0.05):
                return True
    return False


class ExpansionAlertDeduplicator:
    """SQLite-backed, per-profile alert claims with explicit delivery acknowledgement."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS expansion_alerts (
                profile_id TEXT PRIMARY KEY,
                last_snapshot_id TEXT,
                last_material_json TEXT,
                last_sent_at REAL,
                claim_id TEXT,
                claimed_at REAL,
                pending_snapshot_id TEXT,
                pending_material_json TEXT
            )""")

    def claim(self, report: Mapping[str, Any], *, now: float | None = None,
              cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS) -> dict | None:
        """Atomically reserve an alert, or suppress it during a claim/cooldown.

        A material change bypasses the cooldown. A mere snapshot ID change
        does not, since fresh evidence with the same decision is not news.
        """
        if report.get("alertable") is not True:
            return None
        profile_id, snapshot_id = report.get("profile_id"), report.get("snapshot_id")
        if not isinstance(profile_id, str) or not _PROFILE.fullmatch(profile_id):
            raise ValueError("profile_id inválido")
        if not isinstance(snapshot_id, str) or not _SNAPSHOT.fullmatch(snapshot_id):
            raise ValueError("snapshot_id inválido")
        if not isinstance(report.get("html"), str) or len(report["html"]) > MAX_HTML_LENGTH:
            raise ValueError("html inválido")
        material = _object(report.get("material"), "material")
        if type(cooldown_seconds) is not int or cooldown_seconds < 0:
            raise ValueError("cooldown_seconds inválido")
        now = time.time() if now is None else _number(now)
        if now is None or now <= 0:
            raise ValueError("now inválido")

        material_json = json.dumps(material, ensure_ascii=False, sort_keys=True, allow_nan=False)
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT last_material_json, last_sent_at, claim_id, claimed_at "
                "FROM expansion_alerts WHERE profile_id=?", (profile_id,),
            ).fetchone()
            if row and row[2] is not None and row[3] is not None and now - row[3] < CLAIM_LEASE_SECONDS:
                return None
            previous = json.loads(row[0]) if row and row[0] else None
            changed = previous is not None and _material_changed(previous, material)
            if (previous is not None and not changed and row[1] is not None
                    and now - row[1] < cooldown_seconds):
                return None
            reason = "mudanca_material" if changed else "primeiro_alerta" if previous is None else "cooldown_expirado"
            claim_id = secrets.token_hex(16)
            conn.execute("""INSERT INTO expansion_alerts
                (profile_id, claim_id, claimed_at, pending_snapshot_id, pending_material_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET
                    claim_id=excluded.claim_id, claimed_at=excluded.claimed_at,
                    pending_snapshot_id=excluded.pending_snapshot_id,
                    pending_material_json=excluded.pending_material_json""",
                (profile_id, claim_id, now, snapshot_id, material_json))
        prefix = "<b>Atualização relevante na expansão</b>\n" if changed else ""
        return {"profile_id": profile_id, "claim_id": claim_id, "snapshot_id": snapshot_id,
                "reason": reason, "html": prefix + report["html"]}

    def acknowledge(self, claim: Mapping[str, Any], *, delivered: bool, now: float | None = None) -> bool:
        """Finalize a matching claim after Telegram confirms or rejects delivery."""
        profile_id, claim_id = claim.get("profile_id"), claim.get("claim_id")
        if not isinstance(profile_id, str) or not _PROFILE.fullmatch(profile_id):
            raise ValueError("profile_id inválido")
        if not isinstance(claim_id, str) or not re.fullmatch(r"[0-9a-f]{32}", claim_id):
            raise ValueError("claim_id inválido")
        if type(delivered) is not bool:
            raise ValueError("delivered deve ser booleano")
        now = time.time() if now is None else _number(now)
        if now is None or now <= 0:
            raise ValueError("now inválido")
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if delivered:
                cursor = conn.execute("""UPDATE expansion_alerts SET
                    last_snapshot_id=pending_snapshot_id,
                    last_material_json=pending_material_json,
                    last_sent_at=?, claim_id=NULL, claimed_at=NULL,
                    pending_snapshot_id=NULL, pending_material_json=NULL
                    WHERE profile_id=? AND claim_id=?""", (now, profile_id, claim_id))
            else:
                cursor = conn.execute("""UPDATE expansion_alerts SET
                    claim_id=NULL, claimed_at=NULL,
                    pending_snapshot_id=NULL, pending_material_json=NULL
                    WHERE profile_id=? AND claim_id=?""", (profile_id, claim_id))
            return cursor.rowcount == 1
