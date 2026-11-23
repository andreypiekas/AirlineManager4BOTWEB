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


def test_autonomy_metrics_have_accessible_status_and_safe_read_only_renderer():
    html = (ROOT / "assets/web/index.html").read_text(encoding="utf-8")
    assert 'id="investmentMetricsStatus"' in html
    assert 'id="investmentMetricsBody"' in html
    assert 'role="status" aria-live="polite"' in html
    assert 'await api("/api/investment/metrics")' in html
    assert 'await loadInvestmentMetrics()' in html
    assert 'body.replaceChildren()' in html
    assert 'line.textContent = label + ' in html
    assert '"Custo planejado de pedidos confirmados": "Planned cost of confirmed orders"' in html


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
    assert 'report.demand_owned_hubs_attempted' in html
    assert 'report.demand_owned_hubs_inconclusive' in html
    assert 'id="hubDemandProgressList"' in html
    assert 'report.demand_hub_progress' in html
    assert 'nf.format(pricedHubs)' in html
    assert '.hubs-controls { display:grid; grid-template-columns:minmax(0,1fr); }' in html
    assert 'id="hubResearchPolicyStatus"' in html
    assert 'id="hubResearchPolicyReasons"' in html
    assert 'id="hubResearchQueueList"' in html
    assert 'id="hubResearchPrev" type="button"' in html
    assert 'id="hubResearchNext" type="button"' in html
    assert '"Pesquisas anteriores": "Previous research tasks"' in html
    assert '"Próximas pesquisas": "Next research tasks"' in html
    assert 'data-t-aria-label="Bloqueios da política de investimento"' in html
    assert 'data-t-aria-label="Cenários aguardando pesquisa"' in html
    assert 'grid-template-columns:repeat(auto-fit,minmax(min(100%,290px),1fr))' in html
    assert '.hub-research-item .hub-metrics { grid-template-columns:minmax(0,1fr); }' in html
    assert '"Não comprovada no detalhe do jogo": "Not verified in game model details"' in html
    assert '"Preço final da aeronave": "Final aircraft price"' in html
    assert '"Justificativas de bloqueio": "Reasons for blocking"' in html


def test_hubs_dashboard_discloses_historical_audit_without_claiming_current_completeness():
    html = (ROOT / "assets/web/index.html").read_text(encoding="utf-8")
    renderer = html[html.index("function renderHubs(report)"):html.index("function renderHubRecommendations(report)")]
    assert 'const fullAudit = report.last_verified_full_audit;' in renderer
    assert 'fullAudit.unique_aircraft === fullAudit.expected_routes' in renderer
    assert 'tr("Última auditoria integral histórica")' in renderer
    assert 'tr("IDs únicos verificados")' in renderer
    assert 'report.partial_fleet === true' in renderer
    assert '"Última auditoria integral histórica": "Last verified historical full-fleet audit"' in html


def test_investment_policy_controls_have_labels_and_separate_endpoints():
    page = _page()
    for identifier in ("investmentPlanning", "investmentAircraft", "investmentHub", "investmentMode",
                       "investmentSingle", "investmentDaily", "investmentCount",
                       "investmentMinProfit", "investmentPayback"):
        assert page.controls[identifier]["nested_label"], identifier
    for identifier in ("investmentProfitWeight", "investmentEfficiencyWeight",
                       "investmentRiskWeight", "investmentConfidenceWeight",
                       "investmentDiversificationWeight"):
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
    assert ".innerHTML" not in renderer
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
  'Teto de caixa após reservas locais': 'Cash upper bound after local reservations',
  'Diário de investimentos indisponível.': 'Investment ledger unavailable.',
  'Nenhum cenário global comparável.': 'No globally comparable scenario.',
  'Saldo a confirmar.': 'Cash balance pending verification.',
  'Pesquisas sugeridas': 'Suggested research tasks',
  'Possibilidades': 'Possibilities',
  'Hubs com amostras': 'Hubs with samples',
  'Pesquisa de rota iniciada': 'Route research started',
  'Sem pesquisa de rota': 'No route research',
  'Pesquisa de rota inconclusiva': 'Route research inconclusive',
  'Amostras de rotas': 'Route samples',
  'Rotas observadas': 'Observed routes',
  'Rotas com amostras conflitantes': 'Routes with conflicting samples',
  'Cobertura parcial': 'Partial coverage',
  'Pesquisa ainda pendente': 'Research pending',
  'Indisponível': 'Unavailable',
  'Mais possibilidades aguardam pesquisa.': 'Additional possibilities await research.',
  'Somente análise. Nenhuma compra autorizada.': 'Read-only analysis. No purchase authorized.',
  'Execução de investimento bloqueada': 'Investment execution blocked',
  'Modo somente análise': 'Analysis-only mode',
  'Executor aguarda homologação': 'Executor awaiting validation',
  'Modelo pesquisado': 'Researched model',
  'Identidade do modelo': 'Model identity',
  'Confirmada no detalhe do jogo': 'Verified in game model details',
  'Não comprovada no detalhe do jogo': 'Not verified in game model details',
  'Detalhe do modelo não observado': 'Model details not observed',
  'Motor pesquisado': 'Researched engine',
  'Situação do motor': 'Engine status',
  'Motor a pesquisar': 'Engine research pending',
  'Selecionado no jogo': 'Selected in game',
  'Disponível, não selecionado': 'Available, not selected',
  'Preço final da aeronave': 'Final aircraft price',
  'Não verificado': 'Not verified',
  'Custo total': 'Total cost',
  'Lucro líquido diário': 'Daily net profit',
  'Desconhecido': 'Unknown',
  'Retorno estimado': 'Estimated payback',
  'Justificativas de bloqueio': 'Reasons for blocking',
  'Motor ainda não pesquisado no jogo': 'Engine not yet researched in game',
  'Preço final do motor e da aeronave não verificado': 'Final engine and aircraft price unverified',
  'Cobertura da frota não confirmada': 'Fleet coverage unverified',
  'Inventário de hubs desatualizado': 'Hub inventory is outdated',
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
  recommendations: [{hub_id:'1'}], cash_observed_at:null,
  research_queue: {read_only:true, purchase_eligible:false, coverage:'partial',
    sampled_hubs:1, sampled_routes:2, has_more:true,
    hub_coverage:[{hub_id:'1', hub_code:'AAA', sampled_routes:2,
      status:'pesquisa_iniciada', coverage:'partial'},
      {hub_id:'2', hub_code:'<img src=x>', sampled_routes:0,
      status:'nao_pesquisado', coverage:'partial'}],
    items:[{hub_code:'AAA', hub_id:'1', destination_id:'2',
      model:'<script>unsafe</script>', pending:['motor_a_pesquisar']}],
    blocking_reasons:[]},
  investment_policy: {execution_available:false,
    blocking_reasons:['modo_somente_analise', 'executor_aguarda_homologacao']}
};
const researchMetrics = item => Object.fromEntries(item.children[2].children.map(metric =>
  [metric.children[0].textContent, metric.children[1].textContent]));
const researchReasons = item => item.children[3].children[1].children.map(reason => reason.textContent);
$('hubRecommendationSort').value = 'profit';
renderHubRecommendations(report);
assert.equal($('hubResearchQueueStatus').textContent,
  'Suggested research tasks: 1 · Hubs with samples: 1 · Observed routes: 2 · Partial coverage');
assert.equal($('hubResearchPrev').disabled, true);
assert.equal($('hubResearchNext').disabled, true);
Object.assign(report.research_queue, {
  total_candidates:9, offset:4, page_size:2, next_offset:6
});
renderHubRecommendations(report);
assert.equal($('hubResearchQueueStatus').textContent,
  'Suggested research tasks: 1 · Hubs with samples: 1 · Observed routes: 2 · Partial coverage · Possibilities: 9 (5–5)');
assert.equal($('hubResearchPrev').disabled, false);
assert.equal($('hubResearchNext').disabled, false);
report.research_queue.next_offset = null;
renderHubRecommendations(report);
assert.equal($('hubResearchNext').disabled, true);
delete report.research_queue.total_candidates;
delete report.research_queue.offset;
delete report.research_queue.page_size;
delete report.research_queue.next_offset;
renderHubRecommendations(report);
assert.equal($('hubResearchPolicyStatus').textContent,
  'Read-only analysis. No purchase authorized. · Investment execution blocked');
assert.deepEqual($('hubResearchPolicyReasons').children.map(reason => reason.textContent),
  ['Analysis-only mode', 'Executor awaiting validation']);
assert.deepEqual($('hubResearchCoverageList').children.map(item => item.textContent), [
  'AAA · Route research started · Route samples: 2 · Partial coverage',
  '<img src=x> · No route research · Route samples: 0 · Partial coverage'
]);
report.research_queue.conflicted_routes = 2;
report.research_queue.hub_coverage[0].conflicted_routes = 1;
report.research_queue.hub_coverage[1].conflicted_routes = 1;
renderHubRecommendations(report);
assert.equal($('hubResearchQueueStatus').textContent,
  'Suggested research tasks: 1 · Hubs with samples: 1 · Observed routes: 2 · Routes with conflicting samples: 2 · Partial coverage');
assert.deepEqual($('hubResearchCoverageList').children.map(item => item.textContent), [
  'AAA · Route research started · Route samples: 2 · Routes with conflicting samples: 1 · Partial coverage',
  '<img src=x> · Route research inconclusive · Route samples: 0 · Routes with conflicting samples: 1 · Partial coverage'
]);
delete report.research_queue.conflicted_routes;
delete report.research_queue.hub_coverage[0].conflicted_routes;
delete report.research_queue.hub_coverage[1].conflicted_routes;
renderHubRecommendations(report);
assert.equal($('hubResearchQueueList').children.length, 2);
const withoutEngine = $('hubResearchQueueList').children[0];
assert.equal(withoutEngine.children[0].textContent, 'AAA ↔ 2');
assert.equal(withoutEngine.children[1].textContent, 'Research pending');
assert.deepEqual(researchMetrics(withoutEngine), {
  'Researched model':'<script>unsafe</script>',
  'Model identity':'Model details not observed',
  'Researched engine':'Engine research pending',
  'Engine status':'Engine research pending',
  'Final aircraft price':'Not verified',
  'Total cost':'Unknown',
  'Daily net profit':'Unknown', 'ROI':'Unknown', 'Estimated payback':'Unknown'
});
assert.equal(withoutEngine.children[3].children[0].textContent, 'Reasons for blocking (1)');
assert.deepEqual(researchReasons(withoutEngine), ['Engine not yet researched in game']);
assert.equal($('hubResearchQueueList').children[1].textContent,
  'Additional possibilities await research.');
report.research_queue.items[0].engine_id = '2';
report.research_queue.items[0].engine_label = '<img src=x onerror=alert(1)>';
report.research_queue.items[0].engine_available = false;
report.research_queue.items[0].engine_selected = false;
report.research_queue.items[0].engine_evidence = {model_detail_identity_verified:false};
report.research_queue.items[0].pending = ['motor_indisponivel', 'preco_final_motor_a_confirmar',
  '<svg/onload=alert(1)>'];
renderHubRecommendations(report);
const unavailable = $('hubResearchQueueList').children[0];
assert.equal(researchMetrics(unavailable)['Model identity'], 'Not verified in game model details');
assert.equal(researchMetrics(unavailable)['Researched engine'],
  '<img src=x onerror=alert(1)> (2)');
assert.equal(researchMetrics(unavailable)['Engine status'], 'Unavailable');
assert.deepEqual(researchReasons(unavailable), ['Variante de motor indisponível no jogo',
  'Final engine and aircraft price unverified', '<svg/onload=alert(1)>']);
report.research_queue.items.push({hub_code:'BBB', destination_id:'9', model:'A320',
  engine_id:'1', engine_label:'Trent <prova>', engine_available:true, engine_selected:true,
  evidence:{engine:{model_detail_identity_verified:true}},
  final_aircraft_price:123456, daily_net_profit:123, roi:0.42, payback_days:10,
  pending:['preco_final_motor_a_confirmar', 'cobertura_da_frota_a_confirmar']});
renderHubRecommendations(report);
const selected = $('hubResearchQueueList').children[1];
assert.equal(researchMetrics(selected)['Model identity'], 'Verified in game model details');
assert.equal(researchMetrics(selected)['Researched engine'], 'Trent <prova> (1)');
assert.equal(researchMetrics(selected)['Engine status'], 'Selected in game');
assert.equal(researchMetrics(selected)['Final aircraft price'], 'Not verified');
assert.equal(researchMetrics(selected)['Total cost'], 'Unknown');
assert.equal(researchMetrics(selected)['ROI'], 'Unknown');
assert.equal(researchMetrics(selected)['Estimated payback'], 'Unknown');
assert.deepEqual(researchReasons(selected),
  ['Final engine and aircraft price unverified', 'Fleet coverage unverified']);
assert.equal($('hubResearchQueueList').children.length, 3);
report.research_queue.items[1].engine_selected = false;
renderHubRecommendations(report);
assert.equal(researchMetrics($('hubResearchQueueList').children[1])['Engine status'],
  'Available, not selected');
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
report.portfolio.budget_upper_bound = 4500;
renderHubRecommendations(report);
assert.match($('hubRecommendationsScope').textContent,
  /Open purchase intents: 2 · Estimated ledger exposure: \$15500/);
assert.match($('hubRecommendationsScope').textContent,
  /Cash upper bound after local reservations: \$4500/);
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
assert.equal($('hubResearchCoverageList').children.length, 0);
assert.equal($('hubResearchQueueList').children[0].textContent, 'Research pending');
renderHubRecommendations({hubs:[], candidates:[], recommendations:[],
  research_queue: {items: [], blocking_reasons: ['inventario_hubs_desatualizado']}});
assert.equal($('hubResearchQueueList').children[0].textContent, 'Hub inventory is outdated');
assert.equal($('hubResearchPolicyReasons').children.length, 0);
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
def test_research_pagination_disregards_out_of_order_http_responses(tmp_path):
    script = "\n".join(_page().scripts)
    loader = script[script.index("async function loadHubRecommendations()"):script.index(
        'for (const id of ["hubRecommendationModel", "hubRecommendationSort"])'
    )]
    assertions = r"""
const assert = require('node:assert/strict');
let researchPageOffset = 0;
let researchPageFingerprint = null;
let researchRequestSequence = 0;
let hubRecommendationsReport = null;
const nodes = new Map();
const $ = id => {
  if (!nodes.has(id)) {
    nodes.set(id, {disabled:false, textContent:'', events:{},
      addEventListener(name, handler) { this.events[name] = handler; },
      replaceChildren() { this.textContent = ''; }});
  }
  return nodes.get(id);
};
const calls = [];
const api = path => new Promise((resolve, reject) => calls.push({path, resolve, reject}));
const renders = [];
const renderHubRecommendations = report => {
  renders.push(report);
  $('hubResearchPrev').disabled = !report.research_queue.offset;
  $('hubResearchNext').disabled = report.research_queue.next_offset == null;
};
const tr = text => text;
""" + loader + r"""
const report = (offset, next_offset) => ({
  hubs:[], candidates:[], research_queue: {
    offset, next_offset, page_size:2, total_candidates:5,
    snapshot_fingerprint:'snapshot-a', items:[]
  }
});
async function run() {
  const initial = loadHubRecommendations();
  assert.equal(calls[0].path, '/api/hubs/recommendations');
  calls[0].resolve(report(0, 2));
  await initial;
  assert.equal($('hubResearchNext').disabled, false);

  $('hubResearchNext').events.click();
  assert.equal(calls[1].path,
    '/api/hubs/recommendations?research_offset=2&research_snapshot=snapshot-a');
  assert.equal($('hubResearchNext').disabled, true);
  const latest = loadHubRecommendations();
  calls[2].resolve(report(2, 4));
  await latest;
  calls[1].resolve(report(0, 2));
  await Promise.resolve();
  assert.equal(renders.length, 2);
  assert.equal(hubRecommendationsReport.research_queue.offset, 2);
  assert.equal(researchPageOffset, 2);
  assert.equal($('hubResearchPrev').disabled, false);

  $('hubResearchNext').events.click();
  assert.equal(calls[3].path,
    '/api/hubs/recommendations?research_offset=4&research_snapshot=snapshot-a');
  const refresh = loadHubRecommendations();
  calls[4].resolve(report(0, 2)); // Evidence changed; server reset the cursor.
  await refresh;
  calls[3].reject(new Error('stale failure'));
  await Promise.resolve();
  assert.equal(hubRecommendationsReport.research_queue.offset, 0);
  assert.equal(researchPageOffset, 0);
  assert.equal(renders.length, 3);
}
run().catch(error => { console.error(error); process.exitCode = 1; });
"""
    filename = tmp_path / "research_pagination.js"
    filename.write_text(assertions, encoding="utf-8")
    result = subprocess.run(
        ["node", str(filename)], capture_output=True, text=True, check=False, timeout=15,
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
  'Hubs próprios pesquisados': 'Owned hubs researched',
  'tentativas inconclusivas': 'inconclusive attempts',
  'Rotas com demanda contraditória': 'Routes with conflicting demand',
  'Aguardando nova leitura para liberar os dados.':
    'Awaiting a new read to release the evidence.',
  'rotas em quarentena': 'quarantined routes',
  'Cobertura de demanda parcial; respostas vazias não comprovam ausência de rotas.':
    'Partial demand coverage; empty responses do not prove there are no routes.',
  'última pesquisa inconclusiva': 'last research inconclusive',
  'pesquisa ainda não iniciada': 'research not started',
  'destinos amostrados': 'sampled destinations',
  'última tentativa': 'last attempt',
  'recentes': 'recent',
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
  demand_owned_hubs_total:3, demand_owned_hubs_attempted:2,
  demand_owned_hubs_inconclusive:1, demand_coverage:'partial', demand_conflicts:1,
  demand_hub_progress:[
    {hub_id:'2926', last_attempt_at:1800000000, last_attempt_status:'inconclusive',
     sample_count:1, fresh_sample_count:0, conflict_count:1, coverage:'partial'},
    {hub_id:'2941', last_attempt_at:null, last_attempt_status:'unattempted',
     sample_count:0, fresh_sample_count:0, coverage:'partial'}],
  expansion_decision:{status:'avaliacao_expansao', owned_hubs_evaluated:2,
    external_pending_count:0, blocking_reasons:[], top_three:[candidate]}
};
const labels = metrics => Object.fromEntries(metrics.children.map(item =>
  [item.children[0].textContent, item.children[1].textContent]));
renderHubExpansion(report);
assert.match($('hubExpansionScope').textContent, /Owned hubs researched: 2 \/ 3/);
assert.match($('hubExpansionScope').textContent, /1 inconclusive attempts/);
assert.match($('hubExpansionScope').textContent, /Partial demand coverage/);
assert.match($('hubExpansionScope').textContent, /Routes with conflicting demand: 1/);
assert.match($('hubExpansionScope').textContent, /Awaiting a new read to release the evidence/);
assert.equal($('hubDemandProgressList').children.length, 2);
assert.match($('hubDemandProgressList').children[0].textContent,
  /#2926 · last research inconclusive · sampled destinations: 1 \(0 recent\)/);
assert.match($('hubDemandProgressList').children[0].textContent, /quarantined routes: 1/);
assert.match($('hubDemandProgressList').children[1].textContent,
  /#2941 · research not started · sampled destinations: 0/);
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
