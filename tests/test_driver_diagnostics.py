"""O ChromeDriver deve registrar falhas sem expor o arquivo de log."""
from __future__ import annotations

import os
import stat
from types import SimpleNamespace

import pytest
from selenium.webdriver.chrome.service import Service as SeleniumService

import driver


@pytest.mark.parametrize("explicito", [False, True], ids=["sistema", "AM4"])
@pytest.mark.parametrize("herdar_driver", [False, True], ids=["sem-SE", "com-SE"])
def test_selenium_real_inicia_binario_selecionado(tmp_path, monkeypatch, caplog, explicito, herdar_driver):
    selecionado, navegador, herdado = (tmp_path / nome for nome in ("chromedriver", "chrome", "outro-chromedriver"))
    for executavel in (selecionado, navegador, herdado):
        executavel.touch()
        executavel.chmod(0o700)
    monkeypatch.setattr(driver.paths, "current", lambda: SimpleNamespace(data=tmp_path))
    if explicito:
        monkeypatch.setenv("AM4_CHROMEDRIVER_BINARY", str(selecionado))
        monkeypatch.setenv("AM4_CHROME_BINARY", str(navegador))
    else:
        monkeypatch.delenv("AM4_CHROMEDRIVER_BINARY", raising=False)
        monkeypatch.delenv("AM4_CHROME_BINARY", raising=False)
        monkeypatch.setattr(driver, "_system_chrome", lambda: (str(selecionado), str(navegador)))
    if herdar_driver:
        monkeypatch.setenv("SE_CHROMEDRIVER", str(herdado))
    else:
        monkeypatch.delenv("SE_CHROMEDRIVER", raising=False)
    ambiente = dict(os.environ)
    caminhos = []

    def interceptar_processo(self, path):
        # Keep the real Chrome constructor, DriverFinder and Service.start: Selenium
        # can read SE_CHROMEDRIVER again after Service construction. Stop before Popen.
        caminhos.append(path)
        assert dict(os.environ) == ambiente
        self.process = None
        raise RuntimeError("inicializacao interceptada antes do processo")

    monkeypatch.setattr(SeleniumService, "_start_process", interceptar_processo)
    with caplog.at_level("INFO", logger="am4bot.app"):
        with pytest.raises(RuntimeError, match="inicializacao interceptada"):
            driver.create_driver("https://example.invalid", headless=True)

    assert caminhos == [str(selecionado)]
    assert dict(os.environ) == ambiente
    if herdar_driver:
        assert "SE_CHROMEDRIVER herdado" in caplog.text
        assert str(herdado) not in caplog.text
    assert f"Falha ao iniciar ChromeDriver ({selecionado})" in caplog.text


def test_sem_binario_local_preserva_descoberta_do_selenium(monkeypatch):
    monkeypatch.setattr(driver, "_selected_chrome", lambda: (None, None))
    monkeypatch.setenv("SE_CHROMEDRIVER", "/driver-herdado")
    chamadas = []
    instancia = SimpleNamespace(
        set_page_load_timeout=lambda valor: chamadas.append(valor),
        get=lambda url: chamadas.append(url),
    )

    def abrir_chrome(*, options):
        assert not options.binary_location
        assert os.environ["SE_CHROMEDRIVER"] == "/driver-herdado"
        return instancia

    monkeypatch.setattr(driver.webdriver, "Chrome", abrir_chrome)
    assert driver.create_driver("https://example.invalid", headless=True) is instancia
    assert chamadas == [60, "https://example.invalid"]


def test_log_do_chromedriver_tem_permissao_privada(tmp_path, monkeypatch):
    monkeypatch.setattr(driver.paths, "current", lambda: SimpleNamespace(data=tmp_path))
    arquivo, caminho = driver._open_driver_log()
    assert arquivo is not None
    try:
        arquivo.write(b"falha de inicializacao\n")
    finally:
        arquivo.close()
    assert caminho == tmp_path / "logs/chromedriver.log"
    assert caminho.read_bytes() == b"falha de inicializacao\n"
    if os.name != "nt":
        assert stat.S_IMODE(caminho.stat().st_mode) == 0o600


def test_log_existente_com_permissoes_inseguras_eh_corrigido(tmp_path, monkeypatch):
    monkeypatch.setattr(driver.paths, "current", lambda: SimpleNamespace(data=tmp_path))
    pasta = tmp_path / "logs"
    pasta.mkdir()
    log = pasta / "chromedriver.log"
    log.write_bytes(b"anterior\n")
    if os.name != "nt":
        log.chmod(0o644)
    arquivo, caminho = driver._open_driver_log()
    assert arquivo is not None
    arquivo.write(b"novo\n")
    arquivo.close()
    assert caminho.read_bytes() == b"anterior\nnovo\n"
    if os.name != "nt":
        assert stat.S_IMODE(log.stat().st_mode) == 0o600


def test_driver_redireciona_saida_snap_e_fecha_descritor(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(driver.paths, "current", lambda: SimpleNamespace(data=tmp_path))
    monkeypatch.setattr(driver, "_selected_chrome", lambda: ("/usr/bin/chromedriver", "/usr/bin/chromium-browser"))
    instancia = {}

    class Service:
        def __init__(self, executable_path, log_output):
            assert executable_path == "/usr/bin/chromedriver"
            instancia["output"] = log_output

    def falhar(*, service, options):
        assert options.binary_location == "/usr/bin/chromium-browser"
        service_output = instancia["output"]
        service_output.write(b"snap: sem sessao de usuario\n")
        raise RuntimeError("Service unexpectedly exited. Status code was: 1")

    monkeypatch.setattr(driver, "_SelectedChromeService", Service)
    monkeypatch.setattr(driver.webdriver, "Chrome", falhar)

    with pytest.raises(RuntimeError, match="Status code was: 1"):
        driver.create_driver("https://example.com", headless=True)

    arquivo = tmp_path / "logs/chromedriver.log"
    assert arquivo.read_bytes() == b"snap: sem sessao de usuario\n"
    assert instancia["output"].closed
    assert str(arquivo) in caplog.text


def test_erro_ao_abrir_log_nao_impede_a_inicializacao(tmp_path, monkeypatch):
    monkeypatch.setattr(driver.paths, "current", lambda: SimpleNamespace(data=tmp_path))
    destino = tmp_path / "logs"
    destino.write_text("arquivo em vez de pasta", encoding="utf-8")
    arquivo, caminho = driver._open_driver_log()
    assert arquivo is None
    assert caminho == destino / "chromedriver.log"
