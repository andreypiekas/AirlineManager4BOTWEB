"""Read-only reroute preflight using fresh, detached aircraft details."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import reroute
from route_registry import endpoint, same_route

log = logging.getLogger("am4bot.rutas")
_GAME_ID = re.compile(r"^[0-9]{1,14}$")


@dataclass(frozen=True)
class ReroutePreflight:
    aircraft_id: str
    route_id: str = ""
    route_confirmed: bool = False
    reason: str = "nao_verificado"
    game_endpoints: tuple[str, ...] = ()


def check_existing_route(bot, aircraft_id: str, record: dict) -> ReroutePreflight:
    """Fetch game details without a live container; never change a route."""
    aircraft_id = str(aircraft_id or "")
    if not _GAME_ID.fullmatch(aircraft_id):
        return ReroutePreflight(aircraft_id, reason="id_aeronave_invalido")
    try:
        live = reroute._live_route(bot, aircraft_id)
    except Exception as exc:  # read-only review cannot stop a full operating cycle
        log.warning("Pré-validação de rota %s indisponível: %s.",
                    aircraft_id, type(exc).__name__)
        return ReroutePreflight(aircraft_id, reason="detalhes_do_jogo_indisponiveis")
    if live is None:
        return ReroutePreflight(aircraft_id, reason="painel_da_aeronave_vazio")
    route_id = str(live.id or "")
    if not _GAME_ID.fullmatch(route_id):
        return ReroutePreflight(aircraft_id, reason="id_da_rota_ambigua_ou_ausente")
    if not live.landed:
        return ReroutePreflight(aircraft_id, route_id=route_id, reason="aeronave_ainda_em_voo")
    if live.paused:
        return ReroutePreflight(aircraft_id, route_id=route_id, reason="rota_pausada")
    codes = tuple(str(v).strip().upper() for v in live.codes)
    if len(codes) != 2:
        return ReroutePreflight(aircraft_id, route_id=route_id, reason="aeroportos_nao_exibidos_nos_detalhes")
    seen = {"origin": endpoint(code=codes[0]), "destination": endpoint(code=codes[1])}
    if not same_route(record, seen):
        return ReroutePreflight(aircraft_id, route_id=route_id,
                                reason="rota_divergente_dos_detalhes", game_endpoints=codes)
    return ReroutePreflight(aircraft_id, route_id=route_id,
                            route_confirmed=True, reason="rota_confirmada",
                            game_endpoints=codes)
