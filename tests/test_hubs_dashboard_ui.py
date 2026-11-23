"""Responsive hub dashboard controls and their client-side ordering rules."""
from __future__ import annotations

import shutil
import subprocess
from html.parser import HTMLParser

import pytest

from conftest import ROOT


class HubsPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.controls = {}
        self.options = {}
        self.label_depth = 0
        self.active_select = None
        self.script_depth = 0
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if tag == "label":
            self.label_depth += 1
        if tag in ("input", "select") and props.get("id"):
            self.controls[props["id"]] = {**props, "nested_label": self.label_depth > 0}
        if tag == "select":
            self.active_select = props.get("id")
            if self.active_select:
                self.options[self.active_select] = set()
        if tag == "option" and self.active_select is not None:
            self.options[self.active_select].add(props.get("value"))
        if tag == "script" and "src" not in props:
            self.script_depth += 1

    def handle_endtag(self, tag):
        if tag == "label":
            self.label_depth -= 1
        if tag == "select":
            self.active_select = None
        if tag == "script" and self.script_depth:
            self.script_depth -= 1

    def handle_data(self, data):
        if self.script_depth:
            self.scripts.append(data)


def _page():
    page = HubsPage()
    page.feed((ROOT / "assets/web/index.html").read_text(encoding="utf-8"))
    return page


def test_hubs_filters_and_sort_controls_are_labeled_and_target_the_grids():
    page = _page()
    controls = {
        "hubsSearch": "hubsGrid hubsUnconfirmedList",
        "hubsSort": "hubsGrid",
        "hubRecommendationModel": "hubRecommendationsGrid",
        "hubRecommendationSort": "hubRecommendationsGrid",
        "hubExpansionSearch": "hubExpansionGrid",
        "hubExpansionFilter": "hubExpansionGrid",
        "hubExpansionSort": "hubExpansionGrid",
    }
    for identifier, target in controls.items():
        assert page.controls[identifier]["nested_label"], identifier
        assert page.controls[identifier]["aria-controls"] == target

    assert {"name", "profit", "average", "aircraft"} <= page.options["hubsSort"]
    assert {""} <= page.options["hubRecommendationModel"]
    assert {"profit", "payback"} <= page.options["hubRecommendationSort"]
    assert {"recommended", "payback", "profit", "investment", "name"} <= page.options["hubExpansionSort"]

    html = (ROOT / "assets/web/index.html").read_text(encoding="utf-8")
    assert 'id="hubsCoverage"' in html
    assert 'id="hubExpansionCoverage"' in html
    assert 'className = "hub-progress"' in html
    assert 'progress.setAttribute("aria-label"' in html
    assert '"hubsSearch", "hubsSort"' in html
    assert '"hubRecommendationModel", "hubRecommendationSort"' in html
    assert '"hubExpansionSearch", "hubExpansionFilter", "hubExpansionSort"' in html
    assert 'id="hubRecommendationsCount"' in html
    assert '"Filtrar por modelo": "Filter by model"' in html
    assert '"Todos os modelos": "All models"' in html
    assert '"Ordenar recomendações": "Sort recommendations"' in html
    assert '"Nenhuma recomendação corresponde ao modelo selecionado.":' in html
    assert '"Preços de hubs registrados": "Hub prices recorded"' in html
    assert '"Amostras de demanda": "Demand samples"' in html
    assert 'report.demand_fresh_samples' in html
    assert 'report.demand_observed_at' in html
    assert 'nf.format(pricedHubs)' in html
    assert '.hubs-controls { display:grid; grid-template-columns:minmax(0,1fr); }' in html


def test_investment_policy_controls_have_labels_and_separate_endpoints():
    page = _page()
    for identifier in ("investmentPlanning", "investmentAircraft", "investmentHub", "investmentMode",
                       "investmentSingle", "investmentDaily"):
        assert page.controls[identifier]["nested_label"], identifier
    assert {"analyze", "approval", "autonomous"} <= page.options["investmentMode"]
    html = (ROOT / "assets/web/index.html").read_text(encoding="utf-8")
    assert 'id="investmentPolicyFields" disabled' in html
    assert 'id="investmentStop"' in html
    assert '"/api/investment/policy"' in html
    assert '"/api/investment/stop"' in html
    assert 'expected_version: investmentPolicyVersion' in html
    assert '"Controle de autonomia": "Autonomy controls"' in html


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not available")
def test_hub_sorting_handles_partial_profit_data_without_changing_source(tmp_path):
    script = "\n".join(_page().scripts)
    full_script = tmp_path / "dashboard.js"
    full_script.write_text(script, encoding="utf-8")
    syntax = subprocess.run(
        ["node", "--check", str(full_script)],
        capture_output=True, text=True, check=False, timeout=15,
    )
    assert syntax.returncode == 0, syntax.stderr

    helpers = script[script.index("const hubDate ="):script.index("function addHubMetric(")]
    assertions = r"""
const assert = require('node:assert/strict');
const LANG = 'pt_BR';
const nf = new Intl.NumberFormat('pt-BR');
const tr = x => x;
const money = value => String(value);
""" + helpers + r"""
const owned = [
  {id:'3', code:'CCC', aircraft_count:4, estimated_routes:3, estimated_profit_per_day:300},
  {id:'2', code:'BBB', aircraft_count:1, estimated_routes:1, estimated_profit_per_day:200},
  {id:'1', code:'AAA', aircraft_count:5, estimated_routes:0, estimated_profit_per_day:null},
  {id:'4', code:'DDD', aircraft_count:1, estimated_routes:1, estimated_profit_per_day:-10}
];
const codes = rows => rows.map(row => row.code);
assert.deepEqual(codes(sortHubs(owned, 'profit')), ['CCC', 'BBB', 'DDD', 'AAA']);
assert.deepEqual(codes(sortHubs(owned, 'average')), ['BBB', 'CCC', 'DDD', 'AAA']);
assert.deepEqual(codes(sortHubs(owned, 'aircraft')), ['AAA', 'CCC', 'BBB', 'DDD']);
assert.deepEqual(codes(sortHubs(owned, 'name')), ['AAA', 'BBB', 'CCC', 'DDD']);
assert.equal(hubMeanProfit(owned[0]), 100);
assert.equal(hubMeanProfit(owned[2]), null);
assert.deepEqual(codes(owned), ['CCC', 'BBB', 'AAA', 'DDD']);

const candidates = [
  {code:'BBB', payback_days:12, profit_per_day:300, investment:600},
  {code:'AAA', payback_days:null, profit_per_day:null, investment:null},
  {code:'CCC', payback_days:2, profit_per_day:150, investment:200},
  {code:'DDD', payback_days:0, profit_per_day:0, investment:0}
];
assert.deepEqual(codes(sortHubCandidates(candidates, 'recommended')), ['BBB', 'AAA', 'CCC', 'DDD']);
assert.deepEqual(codes(sortHubCandidates(candidates, 'payback')), ['DDD', 'CCC', 'BBB', 'AAA']);
assert.deepEqual(codes(sortHubCandidates(candidates, 'profit')), ['BBB', 'CCC', 'DDD', 'AAA']);
assert.deepEqual(codes(sortHubCandidates(candidates, 'investment')), ['DDD', 'CCC', 'BBB', 'AAA']);
assert.deepEqual(codes(sortHubCandidates(candidates, 'name')), ['AAA', 'BBB', 'CCC', 'DDD']);
assert.deepEqual(codes(candidates), ['BBB', 'AAA', 'CCC', 'DDD']);

assert.deepEqual(hubRecommendationModels([
  {model:'B737'}, {model:' A320 '}, {model:'a320'}, {model:null}
]), ['A320', 'B737']);
assert.deepEqual(hubRecommendationModels(null), []);

const recommendationReport = {
  hubs: [
    {id:'1', code:'AAA', name:'Alpha', status:'viavel',
      recommendation:{hub_id:'1', model:'B737', status:'viavel', profit_per_day:200,
        payback_days:4, route_key:'y'}},
    {id:'2', code:'BBB', name:'Beta', status:'viavel'},
    {id:'3', code:'CCC', name:'Charlie', status:'dados_a_confirmar'},
    {id:'4', code:'DDD', name:'Delta', status:'dados_a_confirmar'}
  ],
  candidates: [
    {hub_id:'2', model:'B737', status:'saldo_insuficiente', profit_per_day:900,
      payback_days:null, route_key:'route-x'},
    {hub_id:'4', model:'A320', status:'dados_a_confirmar', profit_per_day:null,
      payback_days:null, route_key:'pending'},
    {hub_id:'1', model:'B737', status:'viavel', profit_per_day:200, payback_days:4, route_key:'y'},
    {hub_id:'2', model:'A320', status:'viavel', profit_per_day:250, payback_days:9, route_key:'b'},
    {hub_id:'1', model:'A320', status:'viavel', profit_per_day:250, payback_days:9, route_key:'z'},
    {hub_id:'1', model:'A320', status:'viavel', profit_per_day:250, payback_days:9, route_key:'a'}
  ]
};
const recommendationCodes = rows => rows.map(row => row.hub.code);
const recommendationModels = rows => rows.map(row => row.candidate?.model || null);
const byProfit = hubRecommendationRows(recommendationReport, '', 'profit');
assert.deepEqual(recommendationCodes(byProfit), ['AAA', 'BBB', 'CCC', 'DDD']);
assert.deepEqual(recommendationModels(byProfit), ['A320', 'A320', null, 'A320']);
assert.equal(byProfit[0].candidate.route_key, 'a');
const byPayback = hubRecommendationRows(recommendationReport, '', 'payback');
assert.deepEqual(recommendationCodes(byPayback), ['AAA', 'BBB', 'CCC', 'DDD']);
assert.equal(byPayback[0].candidate.model, 'B737');
assert.deepEqual(recommendationCodes(hubRecommendationRows(recommendationReport, ' B737 ', 'profit')),
  ['AAA', 'BBB']);
assert.deepEqual(recommendationCodes(hubRecommendationRows(recommendationReport, 'A320', 'payback')),
  ['AAA', 'BBB', 'DDD']);
assert.deepEqual(hubRecommendationRows(recommendationReport, 'A380', 'profit'), []);
assert.equal(hubRecommendationRows({hubs:[{id:'1', code:'AAA'}], candidates:[]}, '', 'profit')[0].candidate, null);
assert.deepEqual(hubRecommendationRows({hubs:[], candidates:[]}, '', 'profit'), []);
assert.deepEqual(hubRecommendationRows({hubs:[], candidates:null}, '', 'payback'), []);
assert.deepEqual(recommendationReport.candidates.map(row => row.route_key),
  ['route-x', 'pending', 'y', 'b', 'z', 'a']);
const reversed = {...recommendationReport, candidates:[...recommendationReport.candidates].reverse()};
assert.deepEqual(recommendationCodes(hubRecommendationRows(reversed, '', 'profit')), recommendationCodes(byProfit));
assert.deepEqual(recommendationModels(hubRecommendationRows(reversed, '', 'payback')), recommendationModels(byPayback));
"""
    test_script = tmp_path / "sorting.js"
    test_script.write_text(assertions, encoding="utf-8")
    result = subprocess.run(
        ["node", str(test_script)],
        capture_output=True, text=True, check=False, timeout=15,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not available")
def test_hub_recommendations_render_filter_empty_state_and_translations(tmp_path):
    script = "\n".join(_page().scripts)
    helpers = script[script.index("const hubDate ="):script.index("function renderHubs(")]
    renderer = script[script.index("function renderHubRecommendations(report)"):
                      script.index("async function loadHubs()")]
    assertions = r"""
const assert = require('node:assert/strict');
const LANG = 'en';
const nf = new Intl.NumberFormat('en-GB');
const money = value => '$' + String(value);
const translations = {
  'Todos os modelos': 'All models',
  'Recomendações exibidas': 'Recommendations shown',
  'Cenários viáveis': 'Viable scenarios',
  'Bases analisadas': 'Hubs analysed',
  'Melhor cenário global comparado': 'Top globally compared scenario',
  'Conclusão do planejamento pendente.': 'Planning conclusion pending.',
  'Intenções de compra em aberto': 'Open purchase intents',
  'Exposição estimada no diário': 'Estimated ledger exposure',
  'Diário de investimentos indisponível.': 'Investment ledger unavailable.',
  'Nenhum cenário global comparável.': 'No globally comparable scenario.',
  'Saldo a confirmar.': 'Cash balance pending verification.',
  'Nenhuma recomendação corresponde ao modelo selecionado.':
    'No recommendations match the selected model.',
  'Nenhuma base adquirida identificada.': 'No owned hubs identified.'
};
const tr = text => translations[text] || text;
class Element {
  constructor(tag = 'div') {
    this.tag = tag;
    this.children = [];
    this.dataset = {};
    this.value = '';
    this.textContent = '';
    this.className = '';
  }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; this.textContent = ''; }
}
const document = {createElement: tag => new Element(tag)};
const nodes = new Map();
const $ = id => {
  if (!nodes.has(id)) { nodes.set(id, new Element()); }
  return nodes.get(id);
};
const airportLabel = airport => airport?.code || '-';
""" + helpers + "\n" + renderer + r"""
const report = {
  hubs: [{id:'1', code:'AAA', name:'Alpha', status:'viavel'},
         {id:'2', code:'BBB', name:'Beta', status:'dados_a_confirmar'}],
  candidates: [
    {hub_id:'1', model:'B737', status:'viavel', profit_per_day:300,
      payback_days:9, route_key:'one'},
    {hub_id:'1', model:'A320', status:'viavel', profit_per_day:120,
      payback_days:2, route_key:'two'}
  ],
  recommendations: [{hub_id:'1'}], cash_observed_at:null
};
$('hubRecommendationSort').value = 'profit';
renderHubRecommendations(report);
assert.deepEqual($('hubRecommendationModel').children.map(option => option.value), ['', 'A320', 'B737']);
assert.equal($('hubRecommendationModel').children[0].textContent, 'All models');
assert.equal($('hubRecommendationsCount').textContent, 'Recommendations shown: 2 / 2');
assert.equal($('hubRecommendationsGrid').children[0].children[0].textContent, 'AAA · Alpha');
assert.equal($('hubRecommendationsGrid').children[0].children[1].dataset.state, 'viavel');
assert.equal($('hubRecommendationsScope').textContent, 'Cash balance pending verification.');
report.portfolio = {status:'inconclusivo', best:{hub_code:'AAA', model:'A320',
  engine_id:'2', profit_per_day:120}};
renderHubRecommendations(report);
assert.match($('hubRecommendationsScope').textContent,
  /Top globally compared scenario: AAA · A320 \/ 2/);
assert.match($('hubRecommendationsScope').textContent, /Planning conclusion pending/);
report.investment_journal = {count:2, estimated_exposure:15500};
renderHubRecommendations(report);
assert.match($('hubRecommendationsScope').textContent,
  /Open purchase intents: 2 · Estimated ledger exposure: \$15500/);
report.investment_journal = {count:null, estimated_exposure:null};
renderHubRecommendations(report);
assert.match($('hubRecommendationsScope').textContent, /Investment ledger unavailable/);
report.portfolio = {status:'inconclusivo', best:null};
renderHubRecommendations(report);
assert.match($('hubRecommendationsScope').textContent, /No globally comparable scenario/);

$('hubRecommendationModel').value = 'A320';
renderHubRecommendations(report);
assert.equal($('hubRecommendationsGrid').children.length, 1);
assert.equal($('hubRecommendationModel').value, 'A320');
assert.equal($('hubRecommendationsCount').textContent, 'Recommendations shown: 1 / 2');

$('hubRecommendationModel').value = 'A380';
renderHubRecommendations(report);
assert.equal($('hubRecommendationsGrid').children.length, 1);
assert.equal($('hubRecommendationsGrid').children[0].textContent,
  'No recommendations match the selected model.');
assert.equal($('hubRecommendationModel').value, 'A380');

$('hubRecommendationModel').value = '';
renderHubRecommendations({hubs:[], candidates:[], recommendations:[], cash_observed_at:null});
assert.equal($('hubRecommendationsGrid').children[0].textContent, 'No owned hubs identified.');
assert.equal($('hubRecommendationsCount').textContent, 'Recommendations shown: 0 / 0');
"""
    test_script = tmp_path / "recommendations_ui.js"
    test_script.write_text(assertions, encoding="utf-8")
    result = subprocess.run(
        ["node", str(test_script)],
        capture_output=True, text=True, check=False, timeout=15,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not available")
def test_external_expansion_ranking_requires_owned_coverage_and_displays_engine_costs(tmp_path):
    script = "\n".join(_page().scripts)
    helpers = script[script.index("const hubDate ="):script.index("function renderHubs(")]
    renderer = script[script.index("function renderHubExpansion(report)"):
                      script.index("function renderHubRecommendations(report)")]
    assertions = r"""
const assert = require('node:assert/strict');
const LANG = 'en';
const nf = new Intl.NumberFormat('en-GB');
const money = value => '$' + String(value);
const translations = {
  'Motor incluído no preço': 'Engine included in price',
  'Sim': 'Yes', 'Não': 'No',
  'Varredura de hubs próprios inconclusiva': 'Owned-hub scan inconclusive',
  'Priorizar oportunidades nos hubs próprios': 'Prioritize owned hubs',
  'Expansão externa em avaliação': 'External expansion under evaluation',
  'Somente análise. Nenhuma compra autorizada.': 'Read-only. No purchases authorized.'
};
const tr = text => translations[text] || text;
class Element {
  constructor(tag = 'div') {
    this.tag = tag;
    this.children = [];
    this.dataset = {};
    this.value = '';
    this.textContent = '';
    this.className = '';
  }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; this.textContent = ''; }
}
const document = {createElement: tag => new Element(tag)};
const nodes = new Map();
const $ = id => {
  if (!nodes.has(id)) { nodes.set(id, new Element()); }
  return nodes.get(id);
};
const airportLabel = airport => airport?.code || '-';
""" + helpers + "\n" + renderer + r"""
const candidate = {
  id:'789', code:'XAP', name:'Hub <untrusted>', status:'viavel', hub_points:0,
  hub_price:5000, observed_at:1800000000, investment:16550,
  profit_per_day:500, payback_days:33.1, pending:[],
  scenario:{model:'A320', engine_id:'engine-3', engine_label:'Motor <script>',
    route:'XAP ↔ GRU', observed_at:1800000000,
    excluded_costs:['A-check <script>'],
    costs:{aircraft_price_includes_engine:false}},
  cost_breakdown:{hub_price:5000, aircraft_price:10000,
    engine_extra_charged:400, route_fee:1000, hangar_price:100,
    other_fees:50, cash_required:18550}
};
const report = {
  candidates:[candidate], availability_pending:false, catalog_complete:true,
  available_cash:25000, cash:26000, reserve:1000,
  expansion_decision:{status:'avaliacao_expansao', owned_hubs_evaluated:2,
    external_pending_count:0, blocking_reasons:[], top_three:[candidate]}
};
const labels = metrics => Object.fromEntries(metrics.children.map(item =>
  [item.children[0].textContent, item.children[1].textContent]));
renderHubExpansion(report);
assert.match($('hubExpansionDecision').textContent, /External expansion under evaluation/);
assert.match($('hubExpansionDecision').textContent, /Read-only/);
assert.equal($('hubExpansionRanking').children.length, 1);
const ranked = $('hubExpansionRanking').children[0];
assert.equal(ranked.children[0].textContent, '1. XAP · Hub <untrusted>');
const rankedCosts = labels(ranked.children[1]);
assert.equal(rankedCosts['Motor pesquisado'], 'Motor <script>');
assert.equal(rankedCosts['Custo adicional do motor'], '$400');
assert.equal(rankedCosts['Total com reserva'], '$18550');
assert.equal(rankedCosts['Despesas excluídas'], 'A-check <script>');
assert.equal($('hubExpansionGrid').children.length, 1);
const details = $('hubExpansionGrid').children[0].children[3];
assert.equal(labels(details.children[1])['Engine included in price'], 'No');
candidate.scenario.costs.aircraft_price_includes_engine = true;
renderHubExpansion(report);
assert.equal(labels($('hubExpansionGrid').children[0].children[3].children[1])
  ['Engine included in price'], 'Yes');

report.expansion_decision.status = 'inconclusivo';
report.expansion_decision.blocking_reasons = ['cobertura_frota_incompleta'];
renderHubExpansion(report);
assert.match($('hubExpansionDecision').textContent, /Owned-hub scan inconclusive/);
assert.match($('hubExpansionDecision').textContent, /cobertura frota incompleta/);
assert.equal($('hubExpansionRanking').children.length, 0);

report.expansion_decision.status = 'priorizar_hubs_proprios';
renderHubExpansion(report);
assert.match($('hubExpansionDecision').textContent, /Prioritize owned hubs/);
assert.equal($('hubExpansionRanking').children.length, 0);

report.expansion_decision.status = 'avaliacao_expansao';
report.expansion_decision.top_three = [];
renderHubExpansion(report);
assert.match($('hubExpansionRanking').children[0].textContent, /Nenhum candidato externo/);
assert.equal(report.candidates.length, 1);
"""
    test_script = tmp_path / "external_expansion_ui.js"
    test_script.write_text(assertions, encoding="utf-8")
    result = subprocess.run(
        ["node", str(test_script)], capture_output=True, text=True, check=False, timeout=15,
    )
    assert result.returncode == 0, result.stderr
