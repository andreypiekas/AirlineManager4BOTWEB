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
      'Identidade do modelo pendente': 'Model identity pending',
      'Velocidade da variante': 'Variant cruise speed',
      'Emissão de CO₂ da variante': 'Variant CO₂ emission',
      'Coeficiente de CO₂ na simulação': 'CO₂ coefficient in simulation',
      'Coeficiente observado': 'Observed coefficient',
      'Hipótese padrão': 'Default assumption',
      'Alcance utilizado na simulação': 'Range used in simulation',
      'Capacidade utilizada na simulação': 'Capacity used in simulation',
      'Variante observada': 'Observed variant',
      'Catálogo do modelo': 'Model catalog',
      'Simulação exploratória com escala': 'Exploratory stopover simulation',
      'Distância utilizada nos custos': 'Distance used for costs',
      'Tarifa estimada pela distância direta': 'Fare estimated from direct distance',
      'Encargos específicos da escala a confirmar': 'Stopover-specific charges unverified',
      'Não confirmado': 'Unverified',
      'Preço exibido no detalhe': 'Displayed detail price',
      'Subtotal indicativo de uma aeronave (sem taxa da rota)': 'Indicative subtotal for one aircraft (excluding route fee)',
      'Preço indicativo da aeronave': 'Indicative aircraft price',
      'Hangar para uma aeronave (cotação atual)': 'Hangar for one aircraft (current quote)',
      'Investimento final a confirmar': 'Final investment requires verification',
      'Triagem física direta': 'Direct physical screening',
      'Escala exploratória': 'Exploratory stopover',
      'Trechos estimados pelo mapa': 'Map-estimated legs',
      'Pista da escala': 'Stopover runway',
      'Regras da escala a confirmar': 'Stopover rules unverified',
      'Dimensões insuficientes': 'Dimensions insufficient',
      'Alcance direto': 'Direct range',
      'Insuficiente': 'Insufficient',
  'Todos os modelos': 'All models',
  'Recomendações exibidas': 'Recommendations shown',
  'Cenários viáveis': 'Viable scenarios',
  'Bases analisadas': 'Hubs analysed',
  'Melhor cenário global comparado': 'Top globally compared scenario',
  'Conclusão do planejamento pendente.': 'Planning conclusion pending.',
  'Intenções de compra em aberto': 'Open purchase intents',
  'Exposição estimada no diário': 'Estimated ledger exposure',
  'Teto de caixa após reservas locais': 'Cash upper bound after local reservations',
  'Limite de 24 horas restante (diário local)': 'Remaining 24-hour spending limit (local ledger)',
  'Aquisições restantes em 24 horas (diário local)': 'Remaining acquisitions in 24 hours (local ledger)',
  'Uso dos limites de 24 horas a confirmar': '24-hour limit usage unverified',
  'Diário de investimentos indisponível.': 'Investment ledger unavailable.',
  'Nenhum cenário global comparável.': 'No globally comparable scenario.',
  'Saldo a confirmar.': 'Cash balance pending verification.',
  'Pesquisas sugeridas': 'Suggested research tasks',
  'Possibilidades': 'Possibilities',
  'Hubs com amostras': 'Hubs with samples',
  'Pesquisa de rota iniciada': 'Route research started',
  'Sem pesquisa de rota': 'No route research',
  'Pesquisa de rota inconclusiva': 'Route research inconclusive',
  'Última tentativa inconclusiva': 'Last inconclusive attempt',
  'Amostras de rotas': 'Route samples',
  'Rotas observadas': 'Observed routes',
  'Último filtro solicitado': 'Last requested search filter',
  'Pesquisa ampla': 'Broad search',
  'Pesquisa configurada': 'Configured search',
  'Pista do destino observada': 'Observed destination runway',
  'Pista da origem no detalhe': 'Origin runway in route details',
  'Pista do destino no detalhe': 'Destination runway in route details',
  'Ocupação da rota': 'Route occupancy',
  'Aeronaves da frota própria na rota': 'Own-fleet aircraft on route',
  'Auditoria completa': 'Complete audit',
  'Mínimo observado': 'Observed minimum',
  'Ocupação da frota própria não confirmada': 'Own-fleet route occupancy not confirmed',
  'Rotas com amostras conflitantes': 'Routes with conflicting samples',
  'Cobertura parcial': 'Partial coverage',
  'Catálogo de encomenda de passageiros': 'Passenger aircraft order catalog',
  'Modelos com identidade confirmada': 'Models with verified identity',
  'Modelos com detalhes de todas as variantes disponíveis': 'Models with details for all available variants',
  'Variantes observadas entre as identificadas': 'Observed variants among identified variants',
  'Lista de modelos a confirmar': 'Model list pending verification',
  'Preços finais não confirmados': 'Final prices unverified',
  'Hangar de passageiros': 'Passenger hangar',
  'Vagas livres': 'Free slots',
  'Ampliação de hangar (cotação exibida)': 'Hangar expansion (displayed quote)',
  'Prazo exibido': 'Displayed duration',
  'Acima do teto de caixa': 'Above cash upper bound',
  'Dentro do teto de caixa': 'Within cash upper bound',
  'Aeronaves pendentes na frota': 'Pending aircraft in fleet',
  'Aguardando entrega': 'Pending delivery',
  'Em manutenção pendente': 'Pending maintenance',
  'Pendências sem classificação': 'Unclassified pending statuses',
  'Aeronaves estacionadas': 'Parked aircraft',
  'Encomendas e compromissos financeiros a conciliar': 'Orders and financial commitments need reconciliation',
  'Conciliação das contagens da frota': 'Fleet count reconciliation',
  'Contagens coincidentes': 'Matching counts',
  'Contagens da frota divergentes': 'Fleet counts differ',
  'Estacionadas na auditoria': 'Parked in audit',
  'Pendentes na auditoria': 'Pending in audit',
  'Contagens agregadas não comprovam identidades ou encomendas': 'Aggregate counts do not verify identities or orders',
  'Identidades da frota conciliadas': 'Fleet identities reconciled',
  'Identidades da frota divergentes': 'Fleet identities differ',
  'Identidades da frota a confirmar': 'Fleet identities need verification',
  'Identidades conciliadas não comprovam encomendas': 'Reconciled identities do not verify orders',
  'Cotação de combustível (USD/1000)': 'Fuel quote (USD/1000)',
  'Cotação de CO₂ (USD/1000)': 'CO₂ quote (USD/1000)',
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
report.engine_order_list_coverage = {status:'partial', listed_model_count:311,
  verified_model_count:7, models_with_all_variant_details:3,
  available_variant_count:12, observed_variant_count:5, final_prices_verified:false};
renderHubRecommendations(report);
assert.match($('hubResearchQueueStatus').textContent, /Models with verified identity 7\/311/);
assert.match($('hubResearchQueueStatus').textContent, /Models with details for all available variants 3\/311/);
assert.match($('hubResearchQueueStatus').textContent, /Observed variants among identified variants 5\/12/);
assert.match($('hubResearchQueueStatus').textContent, /Final prices unverified/);
report.engine_order_list_coverage = {status:'unverified'};
renderHubRecommendations(report);
assert.match($('hubResearchQueueStatus').textContent, /Model list pending verification/);
delete report.engine_order_list_coverage;
report.fleet_commitment_observations = {status:'observed', passenger_hangar:{capacity:223,occupied:223,free:0,
  upgrade_quotes:{'1':{cost:190835956,duration_seconds:1080},'10':{cost:1908359562,duration_seconds:10740}}},
  pending_fleet:{total:11,maintenance:11,unclassified:0}, parked_count:0};
report.fleet_route_reconciliation = {status:'matched',native_parked_count:0,native_pending_count:11,
  audited_parked_count:0,audited_pending_count:11,unrouted_or_pending_count:11};
renderHubRecommendations(report);
assert.match($('hubResearchQueueStatus').textContent, /Passenger hangar: Free slots 0\/223/);
assert.match($('hubResearchQueueStatus').textContent, /Pending aircraft in fleet: 11 \(Pending maintenance: 11, Pending delivery: Unavailable, Unclassified pending statuses: 0\)/);
report.fleet_commitment_observations.pending_fleet = {total:11,maintenance:9,delivery:2,unclassified:0};
renderHubRecommendations(report);
assert.match($('hubResearchQueueStatus').textContent, /Pending aircraft in fleet: 11 \(Pending maintenance: 9, Pending delivery: 2, Unclassified pending statuses: 0\)/);
assert.match($('hubResearchQueueStatus').textContent, /Parked aircraft: 0/);
assert.match($('hubResearchQueueStatus').textContent, /Orders and financial commitments need reconciliation/);
assert.match($('hubResearchQueueStatus').textContent, /Fleet count reconciliation: Matching counts/);
assert.match($('hubResearchQueueStatus').textContent, /Parked in audit: 0.*Pending in audit: 11/);
assert.match($('hubResearchQueueStatus').textContent, /Aggregate counts do not verify identities or orders/);
assert.match($('hubResearchQueueStatus').textContent, /Fleet identities need verification/);
report.fleet_route_reconciliation.identity_status = 'matched';
renderHubRecommendations(report);
assert.match($('hubResearchQueueStatus').textContent, /Fleet identities reconciled.*Reconciled identities do not verify orders/);
report.fleet_route_reconciliation.identity_status = 'different';
renderHubRecommendations(report);
assert.match($('hubResearchQueueStatus').textContent, /Fleet identities differ/);
report.fleet_route_reconciliation.status = 'different';
renderHubRecommendations(report);
assert.match($('hubResearchQueueStatus').textContent, /Fleet count reconciliation: Fleet counts differ/);
assert.match($('hubResearchQueueStatus').textContent, /Hangar expansion \(displayed quote\) \+1: \$190835956 \(Displayed duration: 00:18:00\)/);
assert.match($('hubResearchQueueStatus').textContent, /Hangar expansion \(displayed quote\) \+10: \$1908359562 \(Displayed duration: 02:59:00\)/);
report.fleet_commitment_observations = {status:'unverified', passenger_hangar:null, pending_fleet:null, parked_count:null};
renderHubRecommendations(report);
assert.match($('hubResearchQueueStatus').textContent, /Passenger hangar: Unavailable/);
assert.match($('hubResearchQueueStatus').textContent, /Parked aircraft: Unavailable/);
assert.doesNotMatch($('hubResearchQueueStatus').textContent, /Hangar expansion/);
delete report.fleet_commitment_observations;
delete report.fleet_route_reconciliation;
renderHubRecommendations(report);
const marketNow = Date.now() / 1000;
const fleetMetrics = document.createElement('div');
const fleetEvidence = {own_aircraft_count:1, count_complete:false, observed_at:marketNow-5, expires_at:marketNow+60};
appendFleetRouteOccupancy(fleetMetrics, {fleet_occupancy:fleetEvidence});
assert.equal(fleetMetrics.children[0].children[0].textContent, 'Own-fleet aircraft on route');
assert.equal(fleetMetrics.children[0].children[1].textContent, '1 · Observed minimum');
appendFleetRouteOccupancy(fleetMetrics, {fleet_occupancy:{...fleetEvidence, own_aircraft_count:0, count_complete:true}});
assert.equal(fleetMetrics.children[1].children[1].textContent, '0 · Complete audit');
appendFleetRouteOccupancy(fleetMetrics, {fleet_occupancy:{...fleetEvidence, expires_at:marketNow-1}});
appendFleetRouteOccupancy(fleetMetrics, {fleet_occupancy:{...fleetEvidence, own_aircraft_count:0}});
assert.equal(fleetMetrics.children.length, 2);
report.candidates[0].fleet_occupancy = {...fleetEvidence, own_aircraft_count:0, count_complete:true};
renderHubRecommendations(report);
assert.equal(researchMetrics($('hubRecommendationsGrid').children[0])['Own-fleet aircraft on route'],
  '0 · Complete audit');
assert.equal(hubResearchBlocker('ocupacao_da_frota_a_confirmar'), 'Own-fleet route occupancy not confirmed');
delete report.candidates[0].fleet_occupancy;
assert.equal(operatingMarketText({fuel:{price:600, observed_at:marketNow-5, expires_at:marketNow+60},
  co2:{price:100, observed_at:marketNow-60, expires_at:marketNow-1}}),
  'Fuel quote (USD/1000): $600 · CO₂ quote (USD/1000): Unknown');
const previewMetrics = document.createElement('div');
const capitalMetrics = document.createElement('div');
const capitalQuote = {source:'displayed_capital_quotes_v1', purchase_eligible:false,
  expires_at:marketNow+60, aircraft_price_source:'observed_variant',
  components:{aircraft:100,hangar:20,hub:50}, displayed_subtotal:170};
appendCapitalQuotePreview(capitalMetrics, {capital_quote_preview:capitalQuote});
assert.equal(capitalMetrics.children[0].children[1].textContent, '$100 · Observed variant');
assert.equal(capitalMetrics.children[2].children[0].textContent, 'Indicative subtotal for one aircraft (excluding route fee)');
assert.equal(capitalMetrics.children[2].children[1].textContent, '$170');
const partialCapital = document.createElement('div');
appendCapitalQuotePreview(partialCapital, {capital_quote_preview:{...capitalQuote,
  components:{aircraft:100,hangar:null},displayed_subtotal:null}});
assert.equal(partialCapital.children.length, 3);
const expiredCapital = document.createElement('div');
appendCapitalQuotePreview(expiredCapital, {capital_quote_preview:{...capitalQuote, expires_at:marketNow-1}});
assert.equal(expiredCapital.children.length, 0);
const preview = {source:'route_optimizer_what_if_v1', purchase_eligible:false,
  expires_at:marketNow+60, safety_margin_fraction:.1, layouts:[{
    layout:{y:10,j:2,f:1}, base:{projected_contribution_per_day:120},
    stress:{projected_contribution_per_day:-20}}]};
appendResearchEconomicsPreview(previewMetrics, {economics_preview:preview});
assert.equal(previewMetrics.children.length, 4);
assert.equal(previewMetrics.children[1].children[1].textContent, '$120 / $-20');
const observedPreview = document.createElement('div');
appendResearchEconomicsPreview(observedPreview, {economics_preview:{...preview,
  co2_kg_per_pax_km:.14, co2_rate_source:'observed_variant'}});
assert.equal(observedPreview.children[3].children[0].textContent, 'CO₂ coefficient in simulation');
assert.equal(observedPreview.children[3].children[1].textContent, '0.14 kg/pax/km · Observed coefficient');
const assumedPreview = document.createElement('div');
appendResearchEconomicsPreview(assumedPreview, {economics_preview:{...preview,
  co2_kg_per_pax_km:.18, co2_rate_source:'assumed_default'}});
assert.equal(assumedPreview.children[3].children[1].textContent, '0.18 kg/pax/km · Default assumption');
const variantPreview = document.createElement('div');
appendResearchEconomicsPreview(variantPreview, {economics_preview:{...preview,
  range_km:2000, range_source:'observed_variant', capacity_pax:180, capacity_source:'catalog_model'}});
assert.equal(variantPreview.children[3].children[0].textContent, 'Range used in simulation');
assert.equal(variantPreview.children[3].children[1].textContent, '2,000 km · Observed variant');
assert.equal(variantPreview.children[4].children[0].textContent, 'Capacity used in simulation');
assert.equal(variantPreview.children[4].children[1].textContent, '180 pax · Model catalog');
const stopoverPreview = document.createElement('div');
appendResearchEconomicsPreview(stopoverPreview, {economics_preview:{...preview,
  route_kind:'exploratory_stopover', game_rules_verified:false,
  travel_distance_km:2500, fare_distance_km:2000}});
assert.equal(stopoverPreview.children[4].children[0].textContent, 'Exploratory stopover simulation');
assert.equal(stopoverPreview.children[4].children[1].textContent, 'Stopover rules unverified');
assert.equal(stopoverPreview.children[5].children[1].textContent, '2,500 km');
assert.equal(stopoverPreview.children[6].children[1].textContent, '2,000 km');
assert.equal(stopoverPreview.children[7].children[0].textContent, 'Stopover-specific charges unverified');
const expiredMetrics = document.createElement('div');
appendResearchEconomicsPreview(expiredMetrics, {economics_preview:{...preview, expires_at:marketNow-1}});
assert.equal(expiredMetrics.children.length, 0);
const engineMetrics = document.createElement('div');
const detailEvidence = {observed_at:marketNow-5, model_identity_verified:false,
  metrics:{speed_kph:881, fuel_lbs_per_km:11.55, required_runway_ft:6500, displayed_cost_usd:6770196}};
appendEngineDetail(engineMetrics, {engine_detail:detailEvidence});
assert.equal(engineMetrics.children[0].children[1].textContent, 'Model identity pending');
assert.equal(engineMetrics.children[1].children[0].textContent, 'Variant cruise speed');
assert.equal(engineMetrics.children[1].children[1].textContent, '881 kph');
assert.equal(engineMetrics.children[4].children[0].textContent, 'Displayed detail price');
appendEngineDetail(engineMetrics, {engine_detail:{...detailEvidence, observed_at:marketNow-4*86400}});
assert.equal(engineMetrics.children.length, 5);
const emissionMetrics = document.createElement('div');
appendEngineDetail(emissionMetrics, {engine_detail:{...detailEvidence,
  metrics:{co2_kg_per_pax_km:.16}}});
assert.equal(emissionMetrics.children[1].children[0].textContent, 'Variant CO₂ emission');
assert.equal(emissionMetrics.children[1].children[1].textContent, '0.16 kg/pax/km');
const physicalMetrics = document.createElement('div');
const physical = {source:'observed_direct_dimensions_v1', status:'direct_shortfall', purchase_eligible:false,
  expires_at:marketNow+60, checks:{range:'short', origin_runway:'unknown', destination_runway:'unknown'},
  distance_km:2000, variant_range_km:1999, stopover_research_required:true};
appendPhysicalFeasibility(physicalMetrics, {physical_feasibility:physical});
assert.equal(physicalMetrics.children[0].children[0].textContent, 'Direct physical screening');
assert.equal(physicalMetrics.children[0].children[1].textContent, 'Dimensions insufficient');
assert.equal(physicalMetrics.children[1].children[1].textContent, 'Insufficient · 1,999 / 2,000 km');
appendPhysicalFeasibility(physicalMetrics, {physical_feasibility:{...physical, expires_at:marketNow-1}});
assert.equal(physicalMetrics.children.length, 5);
const stopMetrics = document.createElement('div');
const stop = {source:'game_map_and_leg_details_v1', purchase_eligible:false, game_rules_verified:false,
  expires_at:marketNow+30, stop_id:'2601', stop_code:'ANC', first_km:1200, second_km:1300, stop_runway_ft:7000};
appendPhysicalFeasibility(stopMetrics, {physical_feasibility:physical, stopover_research:stop});
assert.equal(stopMetrics.children[5].children[0].textContent, 'Exploratory stopover');
assert.equal(stopMetrics.children[5].children[1].textContent, 'ANC');
assert.equal(stopMetrics.children[6].children[0].textContent, 'Map-estimated legs');
assert.equal(stopMetrics.children[6].children[1].textContent, '1,200 + 1,300 km');
const expiredStop = document.createElement('div');
appendPhysicalFeasibility(expiredStop, {physical_feasibility:physical,
  stopover_research:{...stop, expires_at:marketNow-1}});
assert.equal(expiredStop.children.length, 5);
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
Object.assign(report.research_queue.hub_coverage[0], {
  last_search_scope:'broad', last_requested_max_distance_km:20000, last_requested_min_runway_ft:0
});
renderHubRecommendations(report);
assert.equal($('hubResearchCoverageList').children[0].textContent,
  'AAA · Route research started · Route samples: 2 · Last requested search filter: Broad search (≤ 20,000 km, ≥ 0 ft) · Partial coverage');
delete report.research_queue.hub_coverage[0].last_search_scope;
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
report.research_queue.hub_coverage[1].status = 'pesquisa_inconclusiva';
report.research_queue.hub_coverage[1].last_attempt_status = 'inconclusive';
report.research_queue.hub_coverage[1].last_attempt_at = 1800000000;
renderHubRecommendations(report);
assert.equal($('hubResearchCoverageList').children[1].textContent,
  '<img src=x> · Route research inconclusive · Route samples: 0' +
  ' · Last inconclusive attempt: ' + hubDate(1800000000) + ' · Partial coverage');
assert.equal($('hubResearchQueueList').children.length, 2);
const withoutEngine = $('hubResearchQueueList').children[0];
assert.equal(withoutEngine.children[0].textContent, 'AAA ↔ 2');
assert.equal(withoutEngine.children[1].textContent, 'Research pending');
assert.deepEqual(researchMetrics(withoutEngine), {
  'Researched model':'<script>unsafe</script>',
  'Model identity':'Model details not observed',
  'Researched engine':'Engine research pending',
  'Engine status':'Engine research pending',
  'Observed destination runway':'Not verified',
  'Origin runway in route details':'Not verified',
  'Destination runway in route details':'Not verified',
  'Route occupancy':'Not verified',
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
  destination_runway_ft:5013,
  route_detail:{origin_runway_ft:6749,destination_runway_ft:5013,occupied_aircraft:null},
  evidence:{engine:{model_detail_identity_verified:true}},
  final_aircraft_price:123456, daily_net_profit:123, roi:0.42, payback_days:10,
  pending:['preco_final_motor_a_confirmar', 'cobertura_da_frota_a_confirmar']});
renderHubRecommendations(report);
const selected = $('hubResearchQueueList').children[1];
assert.equal(researchMetrics(selected)['Model identity'], 'Verified in game model details');
assert.equal(researchMetrics(selected)['Researched engine'], 'Trent <prova> (1)');
assert.equal(researchMetrics(selected)['Engine status'], 'Selected in game');
assert.equal(researchMetrics(selected)['Observed destination runway'], '5,013 ft');
assert.equal(researchMetrics(selected)['Origin runway in route details'], '6,749 ft');
assert.equal(researchMetrics(selected)['Destination runway in route details'], '5,013 ft');
assert.equal(researchMetrics(selected)['Route occupancy'], 'Not verified');
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
report.portfolio.local_period_limits = {estimated_exposure:15500, acquisition_count:2,
  remaining_spend:500, remaining_acquisitions:0};
report.portfolio.hangar_expansion = {required:true, displayed_quotes:[
  {additional_slots:1,cost:1000,fits_budget_upper_bound:true},
  {additional_slots:10,cost:10000,fits_budget_upper_bound:false}]};
renderHubRecommendations(report);
assert.match($('hubRecommendationsScope').textContent,
  /Open purchase intents: 2 · Estimated ledger exposure: \$15500/);
assert.match($('hubRecommendationsScope').textContent,
  /Cash upper bound after local reservations: \$4500/);
assert.match($('hubRecommendationsScope').textContent, /Remaining 24-hour spending limit \(local ledger\): \$500/);
assert.match($('hubRecommendationsScope').textContent, /Remaining acquisitions in 24 hours \(local ledger\): 0/);
assert.match($('hubRecommendationsScope').textContent, /Hangar expansion \(displayed quote\) \+1: \$1000 · Within cash upper bound/);
assert.match($('hubRecommendationsScope').textContent, /Hangar expansion \(displayed quote\) \+10: \$10000 · Above cash upper bound/);
report.investment_journal = {count:null, estimated_exposure:null};
report.portfolio.local_period_limits = {estimated_exposure:null, acquisition_count:null};
renderHubRecommendations(report);
assert.match($('hubRecommendationsScope').textContent, /Investment ledger unavailable/);
assert.match($('hubRecommendationsScope').textContent, /24-hour limit usage unverified/);
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
def test_audited_expansion_planner_renders_economics_and_blocks_invalid_data(tmp_path):
    script = "\n".join(_page().scripts)
    translations = script[script.index("const EN = {"):script.index("let LANG =")]
    helpers = script[script.index("const hubDate ="):script.index("function renderHubs(")]
    renderer = script[script.index("function renderPurchasePlanPreview(audited, hubs)"):
                      script.index("async function loadHubs()")]
    assert ".innerHTML" not in renderer
    assertions = r"""
const assert = require('node:assert/strict');
const nf = new Intl.NumberFormat('en-GB');
const money = value => '$' + String(value);
""" + translations + r"""
let LANG = 'en';
const tr = value => EN[value] || value;
class Element {
  constructor(tag = 'div') {
    this.tag = tag;
    this.children = [];
    this.dataset = {};
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
""" + helpers + "\n" + renderer + r"""
const identity = {hub_id:'1', origin_id:'AAA', destination_id:'BBB',
  model_id:'<script>unsafe</script>', engine_id:'Trent <demo>'};
const proof = {economics_id:'a3-01', identity, snapshot_id:'snap-1',
  observed_at_oldest:1800000000, safety_margin_fraction:0.15,
  cash_after_purchase:12500,
  configuration_yjf:{y:120,j:20,f:2},
  components:{daily_net_profit_estimate:700, revenue_per_day:1250,
    fuel_cost_per_day:110, co2_cost_per_day:10, known_recurring_cost_per_day:20,
    payback_days:15, roi_365d_percent:200},
  capital_costs:{total_investment:10500, aircraft_cost:9000,
    engine_delta_cost:200, route_fee:300, hangar_cost:400, hub_cost:0, other_fees:600},
  sensitivity:{fuel_price:{multiplier:1.2,daily_net_profit_estimate:655}}};
const a4 = {economics_id:'a3-01', identity, configuration_yjf:proof.configuration_yjf,
  profit_per_day:700, investment:10500, payback_days:15,
  roi_365d_percent:200, score:0.78,
  score_components:{profit:0.4, capital_efficiency:0.38}};
const report = {read_only:true, execution_available:false,
  status:'registrado', profile_id:'principal', snapshot_id:'snap-1',
  evaluation_count:1, evaluations:[proof], a3_ranking:{alternatives:[proof]},
  portfolio:{read_only:true, execution_available:false,
    status:'comparacao_concluida', decision:'sugestao_para_analise',
    alternatives:[a4], best:a4, why_best:{score_difference:0.1},
    budget_after_reservations_and_limits:30000,
    blocking_reasons:[], excluded:{cenario_nao_validado:1}}};
const hubs = [{id:'1', code:'AAA', name:'Alpha'}];
assert.equal(EN['Planejador de Expansão'], 'Expansion Planner');
renderAuditedExpansionPlanner(report, hubs);
assert.equal($('hubPurchasePlanPanel').dataset.state, 'blocked');
assert.equal($('hubPurchasePlanStatus').textContent,
  'Preview unavailable. Review the blockers below.');
assert.equal($('hubPurchasePlanBlockers').children[0].textContent,
  'Plan preview missing from the API response.');
assert.match($('hubExpansionPlannerStatus').textContent,
  /Profile principal · A3 evaluations: 1 · A4 alternatives: 1 · Analysis only/);
assert.match($('hubExpansionPlannerExplanation').textContent,
  /Best global alternative · 1 \/ <script>unsafe<\/script> \/ Trent <demo>/);
assert.match($('hubExpansionPlannerExplanation').textContent, /Excluded scenarios/);
assert.match($('hubExpansionPlannerExplanation').textContent,
  /Scenario awaiting validation \(1\)/);
const card = $('hubExpansionPlannerGrid').children[0];
assert.equal(card.children[0].textContent, 'AAA · Alpha');
assert.equal(card.children[1].dataset.state, 'viavel');
assert.equal(card.children[1].textContent, 'A4 global ranking');
const details = card.children[3];
const metrics = Object.fromEntries(details.children[1].children.map(item =>
  [item.children[0].textContent, item.children[1].textContent]));
assert.equal(metrics['Model'], '<script>unsafe</script>');
assert.equal(metrics['Researched engine'], 'Trent <demo>');
assert.equal(metrics['Y/J/F configuration'], '120 / 20 / 2');
assert.equal(metrics['Incremental profit/day'], '$700');
assert.equal(metrics['Total investment'], '$10500');
assert.equal(metrics['Aircraft price'], '$9000');
assert.equal(metrics['Additional engine cost'], '$200');
assert.equal(metrics['Cash after purchase'], '$12500');
assert.equal(metrics['Safety margin'], '15%');
assert.equal(metrics['A4 score'], '0.78');
assert.match(details.children[2].textContent, /Oldest evidence: /);
assert.match(details.children[2].textContent, /Snapshot: snap-1/);
assert.match(details.children[3].textContent, /Score breakdown: profit 0.4/);
assert.match(details.children[4].textContent, /Stress scenarios: fuel price ×1.2 → \$655/);

report.purchase_plan_preview = {
  hub_id:'1', model_id:'A380-800 <model>', engine_id:'Trent XWB <variant>',
  origin_id:'AAA', destination_id:'BBB', checkout_cost:9200,
  estimated_cost:10500,
  capital_costs:{total_investment:10500, aircraft_cost:9000,
    engine_delta_cost:200, route_fee:300, hangar_cost:400,
    hub_cost:0, other_fees:600}
};
report.purchase_plan_blockers = [];
renderAuditedExpansionPlanner(report, hubs);
assert.equal($('hubPurchasePlanPanel').dataset.state, 'available');
assert.equal($('hubPurchasePlanStatus').textContent,
  'Preview available for analysis. No purchase has been authorized.');
const previewMetrics = Object.fromEntries([
  ...$('hubPurchasePlanIdentity').children,
  ...$('hubPurchasePlanCosts').children,
].map(item => [item.children[0].textContent, item.children[1].textContent]));
assert.equal(previewMetrics['Exact model'], 'A380-800 <model>');
assert.equal(previewMetrics['Exact engine'], 'Trent XWB <variant>');
assert.equal(previewMetrics['Selected hub'], 'AAA · Alpha · 1');
assert.equal(previewMetrics['Exact route'], 'AAA ↔ BBB');
assert.equal(previewMetrics['Checkout cost'], '$9200');
assert.equal(previewMetrics['Total investment'], '$10500');

report.purchase_plan_preview = null;
report.purchase_plan_blockers = ['motor_a_pesquisar', 'preco_final_motor_a_confirmar'];
renderAuditedExpansionPlanner(report, hubs);
assert.equal($('hubPurchasePlanPanel').dataset.state, 'blocked');
assert.deepEqual($('hubPurchasePlanBlockers').children.map(item => item.textContent), [
  'Engine not yet researched in game',
  'Final engine and aircraft price unverified',
]);

report.portfolio.status = 'inconclusivo';
report.portfolio.decision = 'nao_comprar';
report.portfolio.alternatives = [];
report.portfolio.best = null;
report.portfolio.blocking_reasons = ['demanda_residual_a_confirmar',
  'evidencia_pending_orders_incremental_a_confirmar',
  'cobertura_pesquisa_a_confirmar', 'compromissos_a_conciliar'];
report.portfolio.excluded = {orcamento_global_insuficiente_ou_desconhecido:2};
renderAuditedExpansionPlanner(report, hubs);
assert.match($('hubExpansionPlannerStatus').textContent, /Purchase blocked/);
assert.equal($('hubExpansionPlannerBlockers').children[0].textContent,
  'Remaining route demand unverified');
assert.deepEqual($('hubExpansionPlannerBlockers').children.slice(1)
  .map(item => item.textContent), [
    'Pending orders evidence unverified',
    'Research coverage unverified',
    'Cash commitments require reconciliation',
  ]);
assert.match($('hubExpansionPlannerExplanation').textContent,
  /Insufficient or unknown global budget \(2\)/);
assert.match($('hubExpansionPlannerExplanation').textContent, /Verified A3 calculations/);
assert.equal($('hubExpansionPlannerGrid').children[0].children[1].textContent,
  'A3 economics analysis');

report.status = 'registro_invalido';
renderAuditedExpansionPlanner(report, hubs);
assert.equal($('hubExpansionPlannerStatus').textContent,
  'Audited analysis unavailable. Purchases blocked.');
assert.deepEqual($('hubExpansionPlannerBlockers').children.map(item => item.textContent),
  ['Invalid economics registry']);
assert.equal($('hubExpansionPlannerGrid').children.length, 0);
renderAuditedExpansionPlanner(null, hubs);
assert.equal($('hubExpansionPlannerGrid').children.length, 0);

report.status = 'registrado';
report.portfolio.read_only = false;
renderAuditedExpansionPlanner(report, hubs);
assert.equal($('hubExpansionPlannerGrid').children.length, 0);
report.portfolio.read_only = true;
report.portfolio.alternatives = [null, {identity:{hub_id:'1'}, economics_id:'malformed'}];
renderAuditedExpansionPlanner(report, hubs);
assert.equal($('hubExpansionPlannerGrid').children.length, 1);
assert.equal($('hubExpansionPlannerGrid').children[0].children[3].children[0].textContent,
  '#1 · No data / No data · ? ↔ ?');
"""
    test_script = tmp_path / "audited_expansion_planner.js"
    test_script.write_text(assertions, encoding="utf-8")
    result = subprocess.run(["node", str(test_script)], capture_output=True,
                            text=True, check=False, timeout=15)
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
