"""Version 1 of the read-only investment opportunity contract.

Consumers supply observations made by the authenticated game reader. This
module has no game, browser, persistence or purchase integration.

Snapshot schema:
    schema_version, profile_id, source="game_snapshot", observed_at,
    verified=True, snapshot_id=fingerprint_snapshot(snapshot), hubs, coverage.

Coverage contains source="game_fleet_scan", profile_id, verified=True,
observed_at, status="complete", observed_pages, expected_pages,
expected_aircraft_count, count_source="game_fleet_total",
observed_aircraft_ids and scopes (hubs/fleet/routes/models/engines/prices).
Zero routed pages with a nonempty fleet require explicit native identity
reconciliation and routed/unrouted counts matching the total.

A candidate references the snapshot with profile_id and snapshot_id, then
supplies kind, hub={"id": ...}, route, aircraft, costs and financial.
Game evidence carries profile_id, observed_at, verified=True and an allowed
source. Identity-bearing evidence also carries id_source="game".
Every cost is a {"value": number, ...evidence} object, including explicit
zeroes. Price evidence is bound to the selected IDs and declares whether
aircraft_cost is the base price or the complete price including its motor.
Candidate evidence carries the snapshot_id, and financial projections bind
hub, route, model and engine IDs. Missing values are represented as None.

The result is a serializable, non-executable proposal. Block codes are stable
API values intended for reporting and later approval gates.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping

from engine_detail import FinalCheckoutPrice, validate_final_checkout_price
from fleet_commitment_observations import MAX_AGE as HANGAR_MAX_AGE, SOURCE as HANGAR_SOURCE, _hangar

SCHEMA_VERSION = 1
DEFAULT_MAX_AGE_SECONDS = 900
_PROFILE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_GAME_ID = re.compile(r"^[1-9][0-9]{0,11}$")
_CHOICE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
_COVERAGE_SCOPES = ("hubs", "fleet", "routes", "models", "engines", "prices")
_COST_SOURCES = {
    "aircraft_cost": "game_aircraft_shop",
    "engine_delta_cost": "game_aircraft_shop",
    "hub_cost": "game_hub_select",
    "route_fee": "game_route_search",
    "hangar_cost": "game_hub_select",
}
_COST_SUBJECTS = {
    "aircraft_cost": ("model_id", "engine_id"),
    "engine_delta_cost": ("model_id", "engine_id"),
    "hub_cost": ("hub_id",),
    "route_fee": ("origin_id", "destination_id"),
    "hangar_cost": ("hub_id",),
}
_COST_FIELDS = tuple(_COST_SOURCES)
_MAX_MONEY = Decimal("1000000000000000")
_CENTS = Decimal("0.01")


def fingerprint_snapshot(snapshot: Mapping[str, Any]) -> str:
    """Content-address a snapshot, excluding its self-referential ID.

    This detects accidental changes to saved observations. It does not
    authenticate the game source. Callers must provide verified provenance.
    """
    contents = {key: value for key, value in snapshot.items() if key != "snapshot_id"}
    payload = json.dumps(contents, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _block(reasons: list[dict[str, str]], code: str, field: str, message: str) -> None:
    entry = {"code": code, "field": field, "message": message}
    if entry not in reasons:
        reasons.append(entry)


def _game_id(value: object) -> bool:
    return isinstance(value, str) and _GAME_ID.fullmatch(value) is not None


def _choice_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and _CHOICE_ID.fullmatch(value) is not None
        and value.casefold() not in {"0", "unknown", "default", "inferred", "unverified", "none", "null"}
    )


def _amount(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        result = Decimal(str(value))
        if not result.is_finite() or abs(result) > _MAX_MONEY:
            return None
        return result
    except (InvalidOperation, ValueError):
        return None


def _number(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value.quantize(_CENTS, rounding=ROUND_HALF_UP))


def _valid_time(value: object, now: float, max_age_seconds: float) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        timestamp = float(value)
    except OverflowError:
        return False
    return math.isfinite(timestamp) and timestamp > 0 and 0 <= now - timestamp <= max_age_seconds


def evidence_is_current(value: Mapping[str, Any], now: float, max_age_seconds: float) -> bool:
    """Honor an explicit expiry in addition to maximum observation age."""
    observed = value.get("observed_at")
    if not _valid_time(observed, now, max_age_seconds):
        return False
    if "expires_at" not in value:
        return True
    expiry = value["expires_at"]
    if type(expiry) not in (int, float):
        return False
    try:
        return math.isfinite(expiry) and observed < expiry and now < expiry
    except OverflowError:
        return False


def _evidence(
    value: object,
    field: str,
    source: str,
    profile_id: object,
    now: float,
    max_age_seconds: float,
    reasons: list[dict[str, str]],
    *,
    identity: bool = False,
    snapshot_id: str | None = None,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _block(reasons, "EVIDENCE_MISSING", field, "Evidência ausente ou inválida.")
        return {}
    if value.get("profile_id") != profile_id or not _PROFILE_ID.fullmatch(str(profile_id or "")):
        _block(reasons, "PROFILE_MISMATCH", field, "Evidência pertence a outro perfil ou a perfil inválido.")
    if snapshot_id is not None and value.get("snapshot_id") != snapshot_id:
        _block(reasons, "EVIDENCE_SNAPSHOT_MISMATCH", field, "Evidência não está vinculada ao snapshot da proposta.")
    if value.get("source") != source:
        _block(reasons, "EVIDENCE_SOURCE_INVALID", field, f"Fonte exigida: {source}.")
    if value.get("verified") is not True or (identity and value.get("id_source") != "game"):
        _block(reasons, "EVIDENCE_UNVERIFIED", field, "Leitura real do jogo não comprovada.")
    if not evidence_is_current(value, now, max_age_seconds):
        _block(reasons, "EVIDENCE_STALE", field, "Observação ausente, futura ou vencida.")
    return value


def _coverage(
    raw: object,
    profile_id: object,
    now: float,
    max_age_seconds: float,
    reasons: list[dict[str, str]],
) -> str:
    coverage = _evidence(raw, "coverage", "game_fleet_scan", profile_id, now, max_age_seconds, reasons)
    status = coverage.get("status")
    if status != "complete":
        _block(reasons, "COVERAGE_INCOMPLETE", "coverage.status", "Varredura parcial ou sem conclusão comprovada.")

    scopes = coverage.get("scopes")
    if not isinstance(scopes, Mapping) or any(scopes.get(scope) is not True for scope in _COVERAGE_SCOPES):
        _block(
            reasons,
            "COVERAGE_INCOMPLETE",
            "coverage.scopes",
            "Hubs, frota, rotas, modelos, motores e preços exigem cobertura explícita.",
        )

    pages = coverage.get("observed_pages")
    expected_pages = coverage.get("expected_pages")
    count = coverage.get("expected_aircraft_count")
    ids = coverage.get("observed_aircraft_ids")
    all_unrouted = (
        coverage.get("native_unrouted_identity_verified") is True
        and type(coverage.get("routed_aircraft_count")) is int
        and coverage["routed_aircraft_count"] == 0
        and type(coverage.get("unrouted_aircraft_count")) is int
        and coverage["unrouted_aircraft_count"] == count
    )
    coherent = (
        type(pages) is int
        and pages >= 0
        and type(expected_pages) is int
        and expected_pages >= 0
        and pages == expected_pages
        and type(count) is int
        and count >= 0
        and coverage.get("count_source") == "game_fleet_total"
        and isinstance(ids, list)
        and len(ids) == count
        and all(_game_id(aircraft_id) for aircraft_id in ids)
        and len(set(ids)) == len(ids)
        and (count == 0 or pages > 0 or all_unrouted)
    )
    if not coherent:
        _block(reasons, "COVERAGE_INCOHERENT", "coverage", "Páginas, total de aeronaves e IDs únicos não conferem com o jogo.")
    return status if isinstance(status, str) else "unknown"


def complete_coverage_snapshot(snapshot: object, *, profile_id: str, snapshot_id: str,
                               now: float, max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS) -> bool:
    """Validate the original fingerprinted snapshot and its full coverage contract."""
    if not isinstance(snapshot, Mapping) or snapshot.get("snapshot_id") != snapshot_id:
        return False
    try:
        if (fingerprint_snapshot(snapshot) != snapshot_id
                or type(snapshot.get("schema_version")) is not int
                or snapshot["schema_version"] != SCHEMA_VERSION):
            return False
    except (TypeError, ValueError, OverflowError):
        return False
    reasons: list[dict[str, str]] = []
    _evidence(snapshot, "snapshot", "game_snapshot", profile_id, now, max_age_seconds, reasons)
    _coverage(snapshot.get("coverage"), profile_id, now, max_age_seconds, reasons)
    return not reasons


def _validate_route(
    raw: object,
    hub_id: object,
    profile_id: object,
    now: float,
    max_age_seconds: float,
    reasons: list[dict[str, str]],
    snapshot_id: str | None,
) -> dict[str, Any]:
    route = _evidence(
        raw, "route", "game_route_search", profile_id, now, max_age_seconds, reasons, identity=True, snapshot_id=snapshot_id
    )
    origin = route.get("origin_id")
    destination = route.get("destination_id")
    stopover = route.get("stopover_id")
    if not _game_id(origin) or not _game_id(destination) or origin == destination:
        _block(reasons, "ROUTE_ID_UNVERIFIED", "route", "Origem e destino precisam de IDs diferentes lidos do jogo.")
    if _game_id(origin) and origin != hub_id:
        _block(reasons, "ROUTE_HUB_MISMATCH", "route.origin_id", "A rota deve partir do hub selecionado.")
    if "stopover_id" not in route or (stopover is not None and (not _game_id(stopover) or stopover in (origin, destination))):
        _block(
            reasons,
            "ROUTE_ID_UNVERIFIED",
            "route.stopover_id",
            "Escala deve ser explicitamente ausente ou possuir ID real distinto.",
        )

    if route.get("available") is not True:
        _block(reasons, "ROUTE_UNAVAILABLE", "route.available", "Disponibilidade da rota não confirmada.")
    if route.get("feasible") is not True:
        _block(reasons, "ROUTE_INFEASIBLE", "route.feasible", "Viabilidade da rota não confirmada.")
    demand = _amount(route.get("demand_remaining"))
    if route.get("demand_verified") is not True or demand is None or demand <= 0:
        _block(reasons, "DEMAND_UNVERIFIED", "route.demand_remaining", "Demanda residual positiva e comprovada é obrigatória.")

    distance = _amount(route.get("distance_km"))
    flight_range = _amount(route.get("range_km"))
    required_runway = _amount(route.get("required_runway_m"))
    origin_runway = _amount(route.get("origin_runway_m"))
    destination_runway = _amount(route.get("destination_runway_m"))
    measures = (distance, flight_range, required_runway, origin_runway, destination_runway)
    if any(value is None or value <= 0 for value in measures):
        _block(
            reasons,
            "ROUTE_PHYSICAL_DATA_UNKNOWN",
            "route",
            "Distância, alcance e pistas precisam de medidas positivas verificadas.",
        )
    # Each known physical constraint can independently rule out a route.
    # Unknown or invalid dimensions still prevent a positive determination.
    if required_runway is not None and required_runway > 0 and any(
        runway is not None and 0 < runway < required_runway
        for runway in (origin_runway, destination_runway)
    ):
        _block(reasons, "ROUTE_PHYSICALLY_INFEASIBLE", "route", "Pista insuficiente em um dos aeroportos.")
    if (stopover is None and distance is not None and flight_range is not None
            and 0 < flight_range < distance):
        _block(reasons, "ROUTE_PHYSICALLY_INFEASIBLE", "route", "Distância direta excede alcance verificado.")

    if stopover is not None:
        legs = route.get("legs_km")
        stopover_runway = _amount(route.get("stopover_runway_m"))
        valid_legs = isinstance(legs, list) and len(legs) == 2 and all((_amount(leg) or Decimal(0)) > 0 for leg in legs)
        verified_stopover = route.get("stopover_verified") is True
        valid_stopover_runway = stopover_runway is not None and stopover_runway > 0
        if not verified_stopover or not valid_legs or not valid_stopover_runway:
            _block(reasons, "STOPOVER_UNVERIFIED", "route.stopover_id", "Escala, trechos e pista exigem leitura explícita.")
        if verified_stopover and (
            (valid_legs and flight_range is not None and flight_range > 0
             and any(_amount(leg) > flight_range for leg in legs))
            or (valid_stopover_runway and required_runway is not None and required_runway > 0
                and stopover_runway < required_runway)
            or (valid_legs and distance is not None and distance > 0
                and sum(_amount(leg) for leg in legs) < distance)
        ):
            _block(reasons, "ROUTE_PHYSICALLY_INFEASIBLE", "route", "Alcance, pista ou distâncias de escala incoerentes.")

    return {
        "origin_id": origin if _game_id(origin) else None,
        "destination_id": destination if _game_id(destination) else None,
        "stopover_id": stopover if stopover is None or _game_id(stopover) else None,
    }


def _validate_aircraft(
    raw: object,
    profile_id: object,
    now: float,
    max_age_seconds: float,
    reasons: list[dict[str, str]],
    snapshot_id: str | None,
) -> dict[str, Any]:
    aircraft = _evidence(
        raw, "aircraft", "game_aircraft_shop", profile_id, now, max_age_seconds, reasons, identity=True, snapshot_id=snapshot_id
    )
    model_id = aircraft.get("model_id")
    engine_id = aircraft.get("engine_id")
    engine_model_id = aircraft.get("engine_model_id")
    if not _choice_id(model_id):
        _block(reasons, "MODEL_ID_UNVERIFIED", "aircraft.model_id", "Modelo requer identificador real da loja do jogo.")
    if not _choice_id(engine_id):
        _block(reasons, "ENGINE_ID_UNVERIFIED", "aircraft.engine_id", "Motor requer identificador próprio da variante observada.")
    if engine_model_id != model_id or not _choice_id(engine_model_id):
        _block(
            reasons,
            "ENGINE_MODEL_MISMATCH",
            "aircraft.engine_model_id",
            "Vínculo entre a variante do motor e o modelo não confere.",
        )
    if aircraft.get("available") is not True:
        _block(
            reasons, "AIRCRAFT_UNAVAILABLE", "aircraft.available", "Disponibilidade da configuração selecionada não comprovada."
        )
    return {"model_id": model_id if _choice_id(model_id) else None, "engine_id": engine_id if _choice_id(engine_id) else None}


def native_free_passenger_hangar_cost(snapshot, hub_id, *, now, max_age_seconds=DEFAULT_MAX_AGE_SECONDS):
    """Evidence of zero incremental hangar expense for one passenger aircraft."""
    observations = snapshot.get("observations")
    commitments = observations.get("fleet_commitments") if isinstance(observations, Mapping) else None
    if (not isinstance(commitments, Mapping) or commitments.get("source") != HANGAR_SOURCE
            or commitments.get("status") not in ("observed", "partial")
            or not _valid_time(commitments.get("observed_at"), now, min(max_age_seconds, HANGAR_MAX_AGE))):
        return None
    hangar = _hangar(commitments.get("passenger_hangar"))
    if hangar is None or hangar["free"] < 1:
        return None
    return {"source": HANGAR_SOURCE, "profile_id": snapshot.get("profile_id"),
            "snapshot_id": snapshot.get("snapshot_id"), "observed_at": commitments["observed_at"],
            "verified": True, "hub_id": hub_id, "value": 0}


def _validate_costs(
    raw: object,
    profile_id: object,
    now: float,
    max_age_seconds: float,
    reasons: list[dict[str, str]],
    snapshot_id: str | None,
    identities: Mapping[str, object],
    snapshot: Mapping[str, Any],
) -> tuple[dict[str, float | None], Decimal | None]:
    costs = raw if isinstance(raw, Mapping) else {}
    values: dict[str, Decimal] = {}
    output: dict[str, float | None] = {}
    for field, source in _COST_SOURCES.items():
        raw_evidence = costs.get(field)
        if field == "hangar_cost" and isinstance(raw_evidence, Mapping) and raw_evidence.get("source") == HANGAR_SOURCE:
            source = HANGAR_SOURCE
            expected = native_free_passenger_hangar_cost(snapshot, identities.get("hub_id"), now=now,
                                                         max_age_seconds=max_age_seconds)
            if expected is None or any(raw_evidence.get(key) != value for key, value in expected.items()):
                _block(reasons, "HANGAR_COST_UNVERIFIED", f"costs.{field}",
                       "Custo de hangar não corresponde à vaga de passageiros observada no snapshot.")
        evidence = _evidence(
            costs.get(field), f"costs.{field}", source, profile_id, now, max_age_seconds, reasons, snapshot_id=snapshot_id
        )
        if (any(identities.get(key) is None or evidence.get(key) != identities[key] for key in _COST_SUBJECTS[field])
                or (field == "route_fee" and evidence.get("stopover_id") != identities.get("stopover_id"))):
            _block(
                reasons,
                "COST_IDENTITY_MISMATCH",
                f"costs.{field}",
                "Preço observado para outra combinação de hub, rota, modelo ou motor.",
            )
        amount = _amount(evidence.get("value"))
        if evidence.get("value") is None:
            _block(reasons, "COST_UNKNOWN", f"costs.{field}", "Custo obrigatório desconhecido, inclusive quando zero é possível.")
        elif amount is None or amount < 0 or (field == "aircraft_cost" and amount == 0) or amount != amount.quantize(_CENTS):
            _block(
                reasons,
                "COST_INVALID",
                f"costs.{field}",
                "Custo deve ser finito, não negativo e ter no máximo duas casas decimais.",
            )
        else:
            values[field] = amount
        output[field] = _number(values.get(field))
    aircraft_evidence = costs.get("aircraft_cost")
    basis = aircraft_evidence.get("price_basis") if isinstance(aircraft_evidence, Mapping) else None
    if basis not in ("base_without_engine", "final_including_engine"):
        _block(
            reasons, "PRICE_BASIS_UNKNOWN", "costs.aircraft_cost", "É obrigatório distinguir preço-base de preço final com motor."
        )
    elif basis == "final_including_engine" and values.get("engine_delta_cost") != Decimal(0):
        _block(
            reasons,
            "COST_DOUBLE_COUNT",
            "costs.engine_delta_cost",
            "Preço final já inclui o motor, portanto seu custo adicional deve ser zero.",
        )
    if basis == "final_including_engine":
        checkout = _evidence(
            aircraft_evidence.get("checkout"), "costs.aircraft_cost.checkout",
            "game_aircraft_checkout", profile_id, now, max_age_seconds, reasons,
            snapshot_id=snapshot_id,
        )
        price = validate_final_checkout_price(
            FinalCheckoutPrice(engine_id=checkout.get("engine_id"),
                               amount_usd=checkout.get("amount_usd"),
                               source=checkout.get("price_source"),
                               status=checkout.get("status"),
                               reason=checkout.get("reason")),
            identities.get("engine_id"),
        )
        if (price.status != "verified" or checkout.get("model_id") != identities.get("model_id")
                or checkout.get("price_includes_engine") is not True
                or price.amount_usd != values.get("aircraft_cost")):
            _block(reasons, "CHECKOUT_PRICE_UNVERIFIED", "costs.aircraft_cost.checkout",
                   "Preco final exige checkout verificado para o modelo, motor e valor selecionados.")
    valid_cost_evidence = not any(reason["field"].startswith("costs.") for reason in reasons)
    total = sum(values.values(), Decimal(0)) if len(values) == len(_COST_FIELDS) and valid_cost_evidence else None
    return output, total


def _validate_financial(
    raw: object,
    profile_id: object,
    now: float,
    max_age_seconds: float,
    reasons: list[dict[str, str]],
    snapshot_id: str | None,
    identities: Mapping[str, object],
) -> Decimal | None:
    financial = _evidence(raw, "financial", "route_optimizer", profile_id, now, max_age_seconds, reasons, snapshot_id=snapshot_id)
    if (any(
        identities.get(key) is None or financial.get(key) != identities[key]
        for key in ("hub_id", "origin_id", "destination_id", "model_id", "engine_id")
    ) or financial.get("stopover_id") != identities.get("stopover_id")):
        _block(
            reasons,
            "PROFIT_IDENTITY_MISMATCH",
            "financial",
            "Projeção pertence a outra combinação de hub, rota, modelo ou motor.",
        )
    profit = _amount(financial.get("value"))
    if financial.get("value") is None:
        _block(reasons, "PROFIT_UNKNOWN", "financial.value", "Projeção líquida ausente.")
    elif profit is None or profit != profit.quantize(_CENTS):
        _block(reasons, "PROFIT_INVALID", "financial.value", "Projeção deve ser finita e ter no máximo duas casas decimais.")
    elif profit <= 0:
        _block(reasons, "PROFIT_NON_POSITIVE", "financial.value", "Retorno líquido precisa ser positivo.")
    excluded = financial.get("excluded_costs")
    if not isinstance(excluded, list) or any(not isinstance(item, str) for item in excluded):
        _block(
            reasons,
            "PROFIT_BASIS_UNKNOWN",
            "financial.excluded_costs",
            "Custos excluídos precisam ser declarados explicitamente, mesmo se vazios.",
        )
    elif excluded:
        _block(
            reasons,
            "PROFIT_INCOMPLETE",
            "financial.excluded_costs",
            "Custos não modelados impedem afirmar lucro líquido validado.",
        )
    if any(reason["field"].startswith("financial") for reason in reasons):
        return None
    return profit


def evaluate_investment(
    snapshot: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    now: float | None = None,
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    """Create an explainable v1 suggestion with no side effects.

    All required costs must carry independently validated provenance.
    Payback is emitted only when every validation gate succeeds.
    """
    reasons: list[dict[str, str]] = []
    now = time.time() if now is None else now
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or now <= 0:
        _block(reasons, "VALIDATION_CLOCK_INVALID", "now", "Horário de avaliação precisa ser válido.")
        now = time.time()
    if (
        isinstance(max_age_seconds, bool)
        or not isinstance(max_age_seconds, (int, float))
        or not math.isfinite(max_age_seconds)
        or max_age_seconds <= 0
    ):
        _block(reasons, "VALIDATION_MAX_AGE_INVALID", "max_age_seconds", "Prazo máximo de evidência precisa ser positivo.")
        max_age_seconds = DEFAULT_MAX_AGE_SECONDS

    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    candidate = candidate if isinstance(candidate, Mapping) else {}
    profile_id = snapshot.get("profile_id")
    if not isinstance(profile_id, str) or _PROFILE_ID.fullmatch(profile_id) is None:
        _block(reasons, "PROFILE_INVALID", "snapshot.profile_id", "Identificador de perfil inválido ou ausente.")
    if candidate.get("profile_id") != profile_id or candidate.get("profile_id") is None:
        _block(reasons, "PROFILE_MISMATCH", "candidate.profile_id", "Proposta precisa identificar o mesmo perfil do snapshot.")
    if snapshot.get("schema_version") != SCHEMA_VERSION or candidate.get("schema_version") != SCHEMA_VERSION:
        _block(reasons, "SCHEMA_UNSUPPORTED", "schema_version", "Snapshot e candidato devem usar a versão 1.")

    snapshot_id = snapshot.get("snapshot_id")
    try:
        expected_id = fingerprint_snapshot(snapshot)
    except (TypeError, ValueError):
        expected_id = None
    if not isinstance(snapshot_id, str) or snapshot_id != expected_id:
        _block(reasons, "SNAPSHOT_ID_INVALID", "snapshot.snapshot_id", "Hash do snapshot não confere com suas evidências.")
    if candidate.get("snapshot_id") != snapshot_id or candidate.get("snapshot_id") is None:
        _block(reasons, "SNAPSHOT_ID_MISMATCH", "candidate.snapshot_id", "Candidato referencia outro snapshot.")

    _evidence(snapshot, "snapshot", "game_snapshot", profile_id, now, max_age_seconds, reasons)
    coverage_status = _coverage(snapshot.get("coverage"), profile_id, now, max_age_seconds, reasons)

    kind = candidate.get("kind")
    if kind not in ("aircraft_on_owned_hub", "aircraft_on_new_hub"):
        _block(reasons, "KIND_UNSUPPORTED", "candidate.kind", "Tipo de investimento desconhecido.")

    hub_reference = candidate.get("hub")
    hub_id = hub_reference.get("id") if isinstance(hub_reference, Mapping) else None
    if not _game_id(hub_id):
        _block(reasons, "HUB_ID_UNVERIFIED", "candidate.hub.id", "Hub exige ID numérico real do jogo.")
    hubs = snapshot.get("hubs")
    matching = [row for row in hubs if isinstance(row, Mapping) and row.get("id") == hub_id] if isinstance(hubs, list) else []
    if len(matching) != 1:
        _block(reasons, "HUB_NOT_UNIQUE", "snapshot.hubs", "Hub deve estar presente exatamente uma vez no snapshot.")
    hub = matching[0] if len(matching) == 1 else {}
    if hub:
        _evidence(hub, "snapshot.hubs", "game_hub_select", profile_id, now, max_age_seconds, reasons, identity=True)
        owned = hub.get("owned")
        if (
            type(owned) is not bool
            or (kind == "aircraft_on_owned_hub" and not owned)
            or (kind == "aircraft_on_new_hub" and owned)
        ):
            _block(reasons, "HUB_OWNERSHIP_MISMATCH", "snapshot.hubs", "Propriedade do hub difere do tipo de investimento.")

    evidence_snapshot_id = snapshot_id if isinstance(snapshot_id, str) else None
    route = _validate_route(candidate.get("route"), hub_id, profile_id, now, max_age_seconds, reasons, evidence_snapshot_id)
    aircraft = _validate_aircraft(candidate.get("aircraft"), profile_id, now, max_age_seconds, reasons, evidence_snapshot_id)
    identities = {
        "hub_id": hub_id,
        "origin_id": route["origin_id"],
        "destination_id": route["destination_id"],
        "stopover_id": route["stopover_id"],
        "model_id": aircraft["model_id"],
        "engine_id": aircraft["engine_id"],
    }
    costs, investment = _validate_costs(
        candidate.get("costs"), profile_id, now, max_age_seconds, reasons, evidence_snapshot_id, identities, snapshot
    )
    profit = _validate_financial(
        candidate.get("financial"), profile_id, now, max_age_seconds, reasons, evidence_snapshot_id, identities
    )

    hub_cost = costs.get("hub_cost")
    if hub and hub_cost is not None:
        if (hub.get("owned") is True and hub_cost != 0) or (hub.get("owned") is False and hub_cost <= 0):
            _block(reasons, "HUB_COST_INCOHERENT", "costs.hub_cost", "Custo do hub deve refletir sua propriedade comprovada.")

    plan_id = None
    identifiers_valid = (
        isinstance(profile_id, str)
        and _PROFILE_ID.fullmatch(profile_id)
        and isinstance(snapshot_id, str)
        and snapshot_id == expected_id
        and _game_id(hub_id)
        and route["origin_id"] is not None
        and route["destination_id"] is not None
        and aircraft["model_id"] is not None
        and aircraft["engine_id"] is not None
    )
    if identifiers_valid:
        try:
            payload = json.dumps(
                {"profile_id": profile_id, "snapshot_id": snapshot_id, "candidate": candidate},
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
            plan_id = "plan-v1-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
        except (TypeError, ValueError):
            _block(reasons, "CANDIDATE_INVALID", "candidate", "Candidato contém valores não serializáveis.")

    # Do not advertise payback for partial, stale, incoherent or unverified plans.
    status = "blocked" if reasons else "suggested"
    payback = _number(investment / profit) if status == "suggested" and investment is not None and profit is not None else None
    economics = {
        **costs,
        "total_investment": _number(investment) if status == "suggested" else None,
        "daily_net_profit_estimate": _number(profit) if status == "suggested" else None,
        "payback_days": payback,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan_id,
        "profile_id": profile_id if isinstance(profile_id, str) else None,
        "snapshot_id": snapshot_id if isinstance(snapshot_id, str) else None,
        "status": status,
        "kind": kind if kind in ("aircraft_on_owned_hub", "aircraft_on_new_hub") else None,
        "hub": {
            "id": hub_id if _game_id(hub_id) else None,
            "owned": hub.get("owned") if type(hub.get("owned")) is bool else None,
        },
        "route": route,
        "aircraft": aircraft,
        "evidence": {"coverage": coverage_status, "source": snapshot.get("source"), "observed_at": snapshot.get("observed_at")},
        "economics": economics,
        "policy": {"approved": False, "read_only": True, "reasons": reasons},
    }
