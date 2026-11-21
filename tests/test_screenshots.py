"""Contratos da documentação e do gerador de capturas AM/04.

Os testes não abrem Chrome nem iniciam o bot; o workflow de capturas executa
o navegador isoladamente e valida cada imagem depois de gravada.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/screenshots.py"
README = ROOT / "README.md"


def generated_names() -> tuple[str, ...]:
    parsed = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    return next(
        ast.literal_eval(node.value)
        for node in parsed.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "GENERATED"
                for target in node.targets)
    )


def test_capturas_atuais_documentadas_no_readme():
    names = generated_names()
    docs = README.read_text(encoding="utf-8")
    assert len(names) == len(set(names))
    assert set(names) == {path.name for path in (ROOT / "screenshots").glob("*.png")}
    assert "web-visao-geral.png" in names
    assert "web-mobile-config.png" in names
    assert "desktop-mercado-light.png" in names
    assert "web-rotas.png" in names
    assert "web-config-telegram.png" in names
    for name in names:
        assert docs.count(f"screenshots/{name}") == 1, f"Confira a referência a {name} no README"


def test_documentacao_nao_utiliza_arquivos_obsoletos():
    docs = README.read_text(encoding="utf-8")
    assert "screenshots/web-mercado.png" not in docs
    assert "screenshots/web-flota.png" not in docs
    assert "screenshots/desktop-aviones.png" not in docs
    assert "As capturas históricas abaixo" not in docs
    assert "## Interface — AM/04 Torre de Controle" in docs
    assert "## Instalação fácil no Raspberry Pi OS e Ubuntu" in docs


def test_gerador_usa_navegacao_atual_e_nao_aciona_o_bot():
    script = SCRIPT.read_text(encoding="utf-8")
    assert 'window.location.hash = \'#parameters\'' in script
    assert 'driver.find_elements(By.CSS_SELECTOR, "#tabs button")[tab].click()' in script
    assert 'App.start_bot = lambda self: None' in script
    assert 'bot.start = lambda: None' in script
    assert 'config.AppConfig.save = lambda self: None' in script
    assert 'config.AppConfig.web_token = property(lambda self: "")' in script
    assert 'demo@example.invalid' in script
    assert 'os.chdir(demo)' in script
    assert 'web.server.server_address[1]' in script
    assert "GENERATED =" in script
    assert 'if caminho.name not in GENERATED:' in script


def test_logs_de_demonstração_são_portugueses():
    script = SCRIPT.read_text(encoding="utf-8")
    for phrase in (
        "Revisando la aerolínea", "Reputación", "Asientos cambiados",
        "Precio fuel", "me adelanto por el", "contraseña-de-ejemplo",
    ):
        assert phrase not in script
    assert "AM/04 pronto." in script


def test_readme_utiliza_o_nome_canonico_do_repositorio():
    docs = README.read_text(encoding="utf-8")
    assert "github.com/andreypiekas/AirlineManager4BOTWEB" in docs
