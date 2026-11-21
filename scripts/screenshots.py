"""Gera capturas reais da interface AM/04, sem acessar o jogo.

Uso em Linux (X11/Xvfb) ou Windows:
    python scripts/screenshots.py
    python scripts/screenshots.py --web-only

Na automação:
    xvfb-run -a -s "-screen 0 1920x1200x24" python scripts/screenshots.py

As telas exibem dados de demonstração e não usam credenciais, cookies,
token, perfil real, servidor externo nem navegação ao Airline Manager.
A execução não inicia os ciclos do bot nem salva configurações.
"""
from __future__ import annotations

import argparse
import logging
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "screenshots"
sys.path.insert(0, str(ROOT / "src"))

import config  # noqa: E402

_get = config.AppConfig.get
_get_bool = config.AppConfig.get_bool
_get_int = config.AppConfig.get_int
APPEARANCE = {"mode": "Dark"}


def _patched_get(self, section, key, fallback=""):
    if (section, key) == ("app", "appearance_mode"):
        return APPEARANCE["mode"]
    if (section, key) == ("settings", "goal_model"):
        return "B737-800"  # Exemplo visual de modelo específico, nunca uma compra real.
    return _get(self, section, key, fallback)


def _patched_get_bool(self, section, key, fallback=False):
    if (section, key) == ("web", "enabled"):
        return False  # A janela desktop não inicia seu próprio painel.
    if (section, key) == ("options", "start_on_launch"):
        return False
    if (section, key) == ("options", "dry_run"):
        return True
    return _get_bool(self, section, key, fallback)


config.AppConfig.get = _patched_get
config.AppConfig.get_bool = _patched_get_bool
config.AppConfig.get_int = (
    lambda self, section, key, fallback=0:
    0 if (section, key) == ("web", "port") else _get_int(self, section, key, fallback)
)
config.AppConfig.save = lambda self: None
config.AppConfig.credentials = property(lambda self: ("demo@example.invalid", "senha-de-exemplo"))
config.AppConfig.telegram = property(lambda self: ("000000000:DEMONSTRACAO", "000000000"))
config.AppConfig.web_token = property(lambda self: "")

SAMPLE_MARKET = [
    {"id": "demo-1", "name": "Cessna 172", "capacity": 4, "price": 125_000,
     "range": 1100, "speed": 200, "fuel": 40, "score": 0.2, "profit": 16_000},
    {"id": "demo-2", "name": "A320-200", "capacity": 180, "price": 14_000_000,
     "range": 5900, "speed": 830, "fuel": 1600, "score": 0.11, "profit": 340_000},
    {"id": "demo-3", "name": "B737-800", "capacity": 189, "price": 25_000_000,
     "range": 5700, "speed": 810, "fuel": 1450, "score": 0.10, "profit": 390_000},
    {"id": "demo-4", "name": "A330-300", "capacity": 295, "price": 58_000_000,
     "range": 9600, "speed": 880, "fuel": 3600, "score": 0.09, "profit": 650_000},
]


SAMPLE_STATS = dict(
    money=18740005, points=140, fuel=19502400, fuel_capacity=21102000,
    fuel_price=520, fuel_buy_at=650, co2=7541000, co2_capacity=10871000,
    co2_price=111, co2_buy_at=140, fleet_size=186, inflight=174,
    parked=6, pending=6, income_day=279800, goal_price=24000000,
    hangar_free=4, hangar_capacity=191, reputation=84,
)
SAMPLE_LOG = [
    ("app", "AM/04 pronto. Painel de demonstração, sem conexão com o jogo."),
    ("bot", "Iniciando verificação da companhia aérea de demonstração…"),
    ("dinero", "Saldo: $18.740.005 | Pontos: 140 | receita líquida estimada: $279.800/dia."),
    ("vuelos", "174 aeronaves em voo; próximo pouso em 03:29."),
    ("marketing", "Reputação: 84% | 3 campanhas ativas."),
    ("mant", "Frota: 186 aeronaves | 4 vagas disponíveis no hangar."),
    ("asientos", "Oficina: aeronave de exemplo | melhoria de velocidade +10% avaliada."),
    ("fuel", "Combustível: preço $520 | limite de compra $650 | operação simulada."),
    ("co2", "CO₂: preço $111 | limite de compra $140 | operação simulada."),
    ("flota", "6 aeronaves aguardando a próxima verificação de rotas."),
    ("bot", "Próxima verificação em 4 min 31 s."),
]


def fill(bot) -> None:
    bot.update_stats(**SAMPLE_STATS, campaign_ends=int(time.time()) + 2 * 3600 + 35 * 60)
    for category, message in SAMPLE_LOG:
        logging.getLogger(f"am4bot.{category}").info(message)


def fill_routes() -> None:
    from route_registry import RouteRegistry, endpoint

    registry = RouteRegistry()
    gru, gig, ssa, rec, bsb = [endpoint(code=code) for code in ("GRU", "GIG", "SSA", "REC", "BSB")]
    registry.record("101", "DEMO-01", "B737-800", gru, rec, profit_per_day=476_000)
    registry.record("102", "DEMO-02", "B737-800", rec, gru, profit_per_day=428_000)
    registry.record("103", "DEMO-03", "A320-200", gru, gig, profit_per_day=380_000)
    registry.record("103", "DEMO-03", "A320-200", gru, ssa, profit_per_day=510_000,
                    source="redirecionamento")
    registry.note("102", "proposta_de_troca", proposal={
        "destination": "BSB", "profit_per_day": 552_000, "estimated_gain_per_day": 124_000,
        "calculated_at": int(time.time()),
    })
    registry.record_scan(3, 3, 0)


def fill_hubs(bot) -> None:
    """Build isolated, synthetic hub observations for reproducible UI captures."""
    from hub_registry import HubRegistry
    from hub_expansion import HubExpansionRegistry
    from hub_aircraft_research import HubAircraftResearchRegistry
    from route_registry import RouteRegistry

    HubRegistry().record_options([
        {"id": "111", "text": "Chapecó", "code": "XAP"},
        {"id": "222", "text": "Guarulhos", "code": "GRU"},
        {"id": "333", "text": "Detroit", "code": "DTW"},
    ])
    route_registry = RouteRegistry()
    state = json.loads(route_registry.path.read_text(encoding="utf-8"))
    for aircraft_id, hub_id in {"101": "111", "102": "111", "103": "222"}.items():
        state["aircraft"][aircraft_id].update({
            "home_hub_id": hub_id,
            "home_hub_source": "game",
        })
    route_registry.path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    expansion = HubExpansionRegistry()
    expansion.record_catalog([
        {"id": "444", "name": "Curitiba", "code": "CWB", "hub_price": 1_400_000, "purchasable": True},
        {"id": "555", "name": "Florianópolis", "code": "FLN", "hub_price": 2_100_000, "purchasable": True},
        {"id": "666", "name": "Porto Alegre", "code": "POA", "hub_price": 3_500_000, "purchasable": True},
    ], complete=True)
    for hub_id, route, profit in (("444", "CWB ↔ GRU", 185_000),
                                  ("555", "FLN ↔ XAP", 125_000),
                                  ("666", "POA ↔ DTW", -5_000)):
        expansion.record_research(hub_id, {
            "source": "game_research", "model": "B737-800", "route": route,
            "route_feasible": True, "demand_verified": True,
            "aircraft_price": 8_000_000, "route_fee": 65_000,
            "hangar_price": 200_000, "profit_per_day": profit,
        })
    # Next-aircraft comparisons are also invented solely for this ephemeral
    # screenshot profile. No data or status comes from the real game here.
    observed_at = int(time.time())
    research = HubAircraftResearchRegistry()
    for hub_id, destination_id, destination_code, profit in (
        ("111", "777", "BSB", 310_000),
        ("222", "888", "GIG", 405_000),
    ):
        research.record({
            "hub_id": hub_id, "model": "B737-800", "source": "game_research",
            "observed_at": observed_at,
            "origin": {"id": hub_id},
            "destination": {"id": destination_id, "code": destination_code},
            "distance_km": 950, "range_km": 5700,
            "runway_m": 3200, "required_runway_m": 2400,
            "demand_remaining": 450, "demand_verified": True,
            "range_verified": True, "runway_verified": True,
            "route_feasible": True, "route_available": True,
            "financial": {"source": "route_optimizer", "observed_at": observed_at,
                          "profit_per_day": profit},
            "costs": {"source": "game_market", "observed_at": observed_at,
                      "aircraft_price": 8_000_000, "route_fee": 65_000,
                      "hangar_price": 200_000},
        })
    # The demo balance is synthetic too, and must be considered fresh only
    # inside this isolated screenshot process.
    bot.update_stats(money_read_at=time.time())


def capture_window(app, dest: Path) -> None:
    """Fotografa a interface desktop real, com Win32 ou X11/Xvfb."""
    from PIL import ImageGrab

    app.lift()
    app.update_idletasks()
    app.update()
    time.sleep(0.25)
    app.update()
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        hwnd = ctypes.windll.user32.GetParent(app.winfo_id()) or app.winfo_id()
        bounds = wintypes.RECT()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd, 9, ctypes.byref(bounds), ctypes.sizeof(bounds),
        )
        bbox = (bounds.left, bounds.top, bounds.right, bounds.bottom)
        image = ImageGrab.grab(bbox=bbox, all_screens=True)
    else:
        if not os.environ.get("DISPLAY"):
            raise RuntimeError("Capturas desktop no Linux exigem DISPLAY/Xvfb.")
        x, y = app.winfo_rootx(), app.winfo_rooty()
        bbox = (x, y, x + app.winfo_width(), y + app.winfo_height())
        image = ImageGrab.grab(bbox=bbox, xdisplay=os.environ["DISPLAY"])
    image.save(dest, format="PNG", optimize=True)
    print(f"Capturada: {dest.name} ({image.width}x{image.height})", flush=True)


def desktop_shots(output: Path) -> None:
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        raise RuntimeError("Sem DISPLAY. Execute sob xvfb-run para capturar o desktop no Linux.")

    import app as desktop_app
    from app import App, tab_title

    desktop_app.load_market = lambda: SAMPLE_MARKET

    # Nunca executar automações durante uma captura.
    App.start_bot = lambda self: None
    mapping = (
        ("Mercado", "mercado"),
        ("Frota", "frota"),
        ("Aeronaves", "aeronaves"),
        ("Opções", "opcoes"),
    )
    for mode, tabs in (
        ("Dark", mapping),
        ("Light", mapping[:1]),
    ):
        APPEARANCE["mode"] = mode
        app = App()
        try:
            app.geometry("1480x920+30+30")
            fill(app.bot)
            for _ in range(5):
                app.update()
                time.sleep(0.2)
            app._refresh_goal_panel()
            for tab, stem in tabs:
                app.tabs.set(tab_title(tab))
                app.update()
                time.sleep(0.2)
                suffix = "-light" if mode == "Light" else ""
                capture_window(app, output / f"desktop-{stem}{suffix}.png")
        finally:
            app.destroy()


def web_shots(output: Path) -> None:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    from bot import Bot
    from logsetup import LogBuffer, setup_logging
    import web as web_module
    from web import WebDashboard

    web_module.load_market = lambda: SAMPLE_MARKET

    cfg = config.AppConfig()
    buffer = LogBuffer()
    setup_logging(cfg, buffer)
    bot = Bot(cfg)
    bot.start = lambda: None
    web = WebDashboard(bot, cfg, buffer)
    if not web.start():
        raise RuntimeError("Servidor de demonstração não pôde iniciar; nenhuma imagem foi publicada.")
    url = f"http://127.0.0.1:{web.server.server_address[1]}/"

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--hide-scrollbars")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--force-device-scale-factor=1")
    options.add_argument("--window-size=1536,940")
    driver = None
    try:
        # Mantém as capturas livres da linha operacional da porta de testes.
        web.buffer = LogBuffer()
        setup_logging(cfg, web.buffer)
        fill(bot)
        fill_routes()
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 25)

        def navigate(*, mobile=False, tab=None, routes=False, hubs=False, new_hubs=False):
            width, height = (430, 1120) if mobile else (1536, 1280 if tab is not None or routes or hubs or new_hubs else 940)
            driver.set_window_size(width, height)
            driver.get(url)
            wait.until(lambda d: d.find_element(By.ID, "kMoney").text not in ("", "—"))
            if tab is not None:
                driver.execute_script("window.location.hash = '#parameters'")
                wait.until(lambda d: d.find_element(By.ID, "settingsView").is_displayed())
                wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#tabs button")) > tab)
                driver.find_elements(By.CSS_SELECTOR, "#tabs button")[tab].click()
            if routes:
                driver.find_element(By.CSS_SELECTOR, 'a[href="#routes"]').click()
                wait.until(lambda d: "DEMO-02" in d.find_element(By.ID, "routeDuplicates").text)
            if hubs or new_hubs:
                driver.find_element(By.CSS_SELECTOR, 'a[href="#hubs"]').click()
                wait.until(lambda d: "Chapecó" in d.find_element(By.ID, "hubsGrid").text)
                if new_hubs:
                    wait.until(lambda d: "Curitiba" in d.find_element(By.ID, "hubExpansionGrid").text)
                    driver.execute_script('document.getElementById("hubExpansionStatus").closest(".hub-card").scrollIntoView({block:"start"})')
            if mobile and tab is not None:
                driver.execute_script("document.getElementById('settingsView').scrollIntoView()")
            elif not new_hubs:
                driver.execute_script("window.scrollTo(0, 0)")
            time.sleep(0.6)

        def shot(name, *, mobile=False, tab=None, routes=False, hubs=False, new_hubs=False):
            navigate(mobile=mobile, tab=tab, routes=routes, hubs=hubs, new_hubs=new_hubs)
            dest = output / name
            if not driver.save_screenshot(str(dest)):
                raise RuntimeError(f"Falha ao salvar captura: {name}")
            print(f"Capturada: {dest.name}", flush=True)

        fill_hubs(bot)
        shot("web-visao-geral.png")
        for index, tab in enumerate(("mercado", "frota", "aeronaves", "opcoes", "telegram")):
            shot(f"web-config-{tab}.png", tab=index)
        shot("web-rotas.png", routes=True)
        shot("web-hubs.png", hubs=True)
        shot("web-novos-hubs.png", new_hubs=True)
        shot("web-mobile.png", mobile=True)
        shot("web-mobile-config.png", mobile=True, tab=0)
        shot("web-hubs-mobile.png", mobile=True, hubs=True)
    finally:
        if driver is not None:
            driver.quit()
        web.stop()


GENERATED = (
    "desktop-mercado.png", "desktop-frota.png", "desktop-aeronaves.png",
    "desktop-opcoes.png", "desktop-mercado-light.png",
    "web-visao-geral.png", "web-config-mercado.png", "web-config-frota.png",
    "web-config-aeronaves.png", "web-config-opcoes.png", "web-config-telegram.png",
    "web-rotas.png",
    "web-hubs.png", "web-novos-hubs.png", "web-hubs-mobile.png",
    "web-mobile.png", "web-mobile-config.png",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Atualiza capturas de demonstração do AM/04.")
    parser.add_argument("--web-only", action="store_true",
                        help="Gera apenas as telas web, sem dependências gráficas do desktop.")
    args = parser.parse_args()
    generated = tuple(name for name in GENERATED if not args.web_only or name.startswith("web-"))
    original_dir = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="am4-capturas-") as directory:
        demo = Path(directory)
        output = demo / "screenshots"
        output.mkdir()
        (demo / "config").mkdir()
        shutil.copyfile(ROOT / "config/defaults.ini", demo / "config/defaults.ini")
        shutil.copytree(ROOT / "assets", demo / "assets")
        os.chdir(demo)
        try:
            if not args.web_only:
                desktop_shots(output)
            web_shots(output)
        finally:
            logging.shutdown()
            os.chdir(original_dir)

        faltando = [name for name in generated if not (output / name).is_file()]
        if faltando:
            raise RuntimeError("Capturas ausentes: " + ", ".join(faltando))
        OUT.mkdir(exist_ok=True)
        for name in generated:
            shutil.copyfile(output / name, OUT / name)

    # Limpa capturas obsoletas apenas após gerar a nova série completa.
    if not args.web_only:
        for caminho in OUT.glob("*.png"):
            if caminho.name not in GENERATED:
                caminho.unlink()
                print(f"Removida captura antiga: {caminho.relative_to(ROOT)}", flush=True)
    print(f"Capturas AM/04 atualizadas: {len(generated)} arquivos.", flush=True)


if __name__ == "__main__":
    main()
