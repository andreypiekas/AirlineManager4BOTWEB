"""Manual admin probe controls keep game-source data private and opt-in."""

from __future__ import annotations

import shutil
import subprocess
from html.parser import HTMLParser

import pytest

from conftest import ROOT


PAGE = ROOT / "assets/web/index.html"


class ProbeMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.elements: dict[str, tuple[str, dict[str, str | None]]] = {}
        self.inputs: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get("id") == "gameSourceProbePanel":
            self.inside = True
        if self.inside:
            if attributes.get("id"):
                self.elements[attributes["id"]] = tag, attributes
            if tag in {"input", "textarea", "select"}:
                self.inputs.append(tag)

    def handle_endtag(self, tag):
        if tag == "details" and self.inside:
            self.inside = False


def page_script() -> str:
    html = PAGE.read_text(encoding="utf-8")
    return html.split("<script>", 1)[1].split("</script>", 1)[0]


def test_diagnostic_is_accessible_collapsed_and_without_secret_fields():
    html = PAGE.read_text(encoding="utf-8")
    parser = ProbeMarkup()
    parser.feed(html)

    panel_tag, panel = parser.elements["gameSourceProbePanel"]
    button_tag, button = parser.elements["gameSourceProbeRun"]
    result_tag, result = parser.elements["gameSourceProbeResults"]
    status_tag, status = parser.elements["gameSourceProbeStatus"]
    assert panel_tag == "details" and "open" not in panel
    assert button_tag == "button" and button["type"] == "button"
    assert button["aria-controls"] == "gameSourceProbeResults"
    assert result_tag == "div" and "hidden" in result
    assert status_tag == "p" and status["role"] == "status"
    assert status["aria-live"] == "polite" and status["aria-atomic"] == "true"
    assert not parser.inputs

    script = page_script()
    assert 'api("/api/admin/game-source-probe", {}, true)' in script
    assert '$(' + '"gameSourceProbeRun"' + ').addEventListener("click", runGameSourceProbe)' in script
    assert "setInterval(runGameSourceProbe" not in script
    assert "setTimeout(runGameSourceProbe" not in script
    assert "location.search" not in script
    assert '"Diagnóstico de fontes do jogo": "Game source diagnostics"' in html
    assert '"Acesso negado. Verifique a autorização no painel.":' in html
    assert '"Paginação sem conflito identificado": "No pagination conflict detected"' in html
    assert ".hub-probe-grid { grid-template-columns:minmax(0,1fr); }" in html
    assert "if (gameSourceProbeReport)" in script


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not available")
def test_probe_js_syntax_and_manual_runtime_safety(tmp_path):
    script = page_script()
    full_script = tmp_path / "dashboard.js"
    full_script.write_text(script, encoding="utf-8")
    syntax = subprocess.run(
        ["node", "--check", str(full_script)], capture_output=True, text=True,
        timeout=15, check=False,
    )
    assert syntax.returncode == 0, syntax.stderr

    api = script[script.index("async function api("):script.index("// ------------------------------------------------------------------ status tiles")]
    probe = script[
        script.index("// ------------------------------------------------------------------ manual, read-only game source diagnostics"):
        script.index("// ------------------------------------------------------------------ end manual game source diagnostics")
    ]
    harness = r"""
const assert = require('node:assert/strict');
class Element {
  constructor() {
    this.children = []; this.dataset = {}; this.attributes = {};
    this.hidden = false; this.disabled = false; this.textContent = '';
    this.listeners = {};
  }
  replaceChildren(...children) { this.children = children; }
  append(...children) { this.children.push(...children); }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
}
const nodes = new Map();
const $ = id => {
  if (!nodes.has(id)) nodes.set(id, new Element());
  return nodes.get(id);
};
const document = {createElement: () => new Element()};
const translations = {
  'Fontes visíveis': 'Visible sources', 'Elementos': 'Elements',
  'IDs distintos': 'Unique IDs', 'Com ID': 'With ID',
  'Página': 'Page', 'de': 'of', 'Estado do jogo': 'Game state',
  'Verificação concluída.': 'Check completed.',
  'Bases adquiridas no seletor': 'Owned hubs in selector'
};
let lang = 'pt_BR';
const tr = text => lang === 'en' ? (translations[text] || text) : text;
const requests = [];
const fetch = (path, options) => new Promise((resolve, reject) => {
  requests.push({path, options, resolve, reject});
});
const response = (status, data) => ({status, ok: status >= 200 && status < 300,
                                    json: async () => data});
""" + api + probe + r"""
const allText = element => [element.textContent,
  ...element.children.flatMap(child => [allText(child)])].join(' ');
(async () => {
  $('gameSourceProbeResults').hidden = true;
  assert.equal(requests.length, 0);
  assert.equal($('gameSourceProbeRun').listeners.click, runGameSourceProbe);
  const first = $('gameSourceProbeRun').listeners.click();
  assert.equal(requests.length, 1);
  assert.equal($('gameSourceProbeRun').disabled, true);
  assert.equal($('gameSourceProbePanel').attributes['aria-busy'], 'true');
  assert.equal($('gameSourceProbeStatus').dataset.state, 'pending');
  await runGameSourceProbe();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].path, '/api/admin/game-source-probe');
  assert.deepEqual(requests[0].options, {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-AM4': '1'},
    body: '{}'
  });

  const privateValue = '<img src=x onerror=steal_token()> PASSWORD_TOKEN';
  const report = {
    sources: {
      owned_hub_options: {count: 4, numeric_id_count: 2, id_parseable_nodes: 3,
        numeric_ids: ['1', privateValue], selector: privateValue},
      fleet_routes: {count: 1, numeric_id_count: 1, id_parseable_nodes: 1},
      arbitrary_secret: {count: 200, numeric_id_count: privateValue}
    },
    status_data: {count: 3, numeric_id_count: 1, token: privateValue},
    pagination: {current_page: 2, total_pages: 5, evidence_conflict: false,
      evidence: {popup_present: true, active_page_numeric: true, token: privateValue}}
  };
  requests[0].resolve(response(200, {ok: true, report}));
  await first;
  assert.equal($('gameSourceProbeRun').disabled, false);
  assert.equal($('gameSourceProbeResults').hidden, false);
  assert.equal($('gameSourceProbeStatus').dataset.state, 'success');
  assert.equal($('gameSourceProbePanel').attributes['aria-busy'], undefined);
  assert.equal($('gameSourceProbeSummary').textContent, 'Fontes visíveis: 2 / 8');
  assert.equal($('gameSourceProbePagination').textContent,
    'Página 2 de 5 · Paginação sem conflito identificado');
  assert.match(allText($('gameSourceProbeSources')), /Com ID: 3 \/ 4/);
  assert.match($('gameSourceProbeEvidence').textContent, /Janela da frota/);
  assert.doesNotMatch(allText($('gameSourceProbeSources')), /PASSWORD_TOKEN|<img/);
  assert.doesNotMatch($('gameSourceProbeEvidence').textContent, /PASSWORD_TOKEN/);

  lang = 'en';
  renderGameSourceProbe(report);
  assert.equal($('gameSourceProbeSummary').textContent, 'Visible sources: 2 / 8');
  assert.equal($('gameSourceProbePagination').textContent,
    'Page 2 of 5 · Paginação sem conflito identificado');
  assert.match(allText($('gameSourceProbeSources')), /Owned hubs in selector/);
  lang = 'pt_BR';

  const errors = [
    [403, 'Acesso negado. Verifique a autorização no painel.'],
    [409, 'O jogo está ocupado. Tente novamente.'],
    [504, 'Tempo esgotado. Verifique se o jogo está carregado.'],
    [503, 'Sessão do jogo indisponível. Verifique o bot.']
  ];
  for (const [code, expected] of errors) {
    const pending = runGameSourceProbe();
    requests.at(-1).resolve(response(code, {ok: false, message: privateValue}));
    await pending;
    assert.equal($('gameSourceProbeStatus').textContent, expected);
    assert.equal($('gameSourceProbeStatus').dataset.state, 'error');
    assert.equal($('gameSourceProbeResults').hidden, true);
    assert.equal($('gameSourceProbeRun').disabled, false);
  }
  const brokenResponse = runGameSourceProbe();
  requests.at(-1).resolve(response(200, {ok: true, report: {sources: {}}}));
  await brokenResponse;
  assert.equal($('gameSourceProbeStatus').textContent,
    'Não foi possível verificar as fontes do jogo.');
  assert.equal($('gameSourceProbeResults').hidden, true);
  const offline = runGameSourceProbe();
  requests.at(-1).reject(new Error(privateValue));
  await offline;
  assert.equal($('gameSourceProbeStatus').textContent,
    'Não foi possível verificar as fontes do jogo.');
  assert.equal($('gameSourceProbeRun').disabled, false);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    runtime_script = tmp_path / "probe_ui.js"
    runtime_script.write_text(harness, encoding="utf-8")
    runtime = subprocess.run(
        ["node", str(runtime_script)], capture_output=True, text=True,
        timeout=15, check=False,
    )
    assert runtime.returncode == 0, runtime.stderr
