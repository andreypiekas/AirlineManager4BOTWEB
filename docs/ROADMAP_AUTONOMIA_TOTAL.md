# Roadmap — AM4 Autonomia Total (aeronaves, motores, hubs e rotas)

**Criado em:** 22/11/2026  
**Base de análise:** main, commit cd15a32af2a9ed7c10a78017ce0f90c09b439216  
**Estado deste documento:** planejamento com implementação incremental em andamento. Entregas, testes e pendências de homologação são registrados em [ENTREGAS_ROADMAP.md](ENTREGAS_ROADMAP.md).
**Relação** — complementa [ROADMAP_HUBS_AERONAVES.md](ROADMAP_HUBS_AERONAVES.md) e [ENTREGAS_ROADMAP.md](ENTREGAS_ROADMAP.md). Os requisitos e as pendências da implementação inicial de hubs estão na [PR #44](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/44).

## Estado em 25/11/2026

**Branches permanentes** — `main` e `codex/autonomia-a0-a1-20261122`. A segunda concentra o desenvolvimento da [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46). A implementação inicial da PR #44 está arquivada no commit `33d081b` e serve de referência para a revisão de uma futura promoção.

| Frente | Implementação disponível | Evidência ou trabalho pendente |
| --- | --- | --- |
| A0 | Proteções do G0 e testes automatizados de regressão. | Homologação autenticada e validação da instalação no servidor. |
| A1/A2 | Checkout revalida modelo, motor, base, estabilidade do preço e aviso de saldo. A coleta auditada preserva o aviso de demanda de evento das leituras correlacionadas. | Provar o preço final por modelo, variante e hub de entrega, o vínculo permanente aeronave–hub e a cobertura de rotas. `#acCost` no A320-200 e no A380-800 exibiu valores estáveis nas configurações amostradas. Manter `price_verified=false` onde faltar prova do preço final. |
| A3/A4 | O worker vincula a análise ao snapshot auditado e limita a decisão pelo menor dos três saldos independentes, líquido de compromissos e reserva. O cálculo revalida o prazo das evidências, a prova de cobertura e o checkout do preço final. | Coletar layout Y/J/F, disponibilidade, demanda residual, tarifas, taxa de rota e custos incrementais. Publicar casos completos e cobertura auditada da fila de oportunidades. |
| A6/A7 | Replay externo, painel e Telegram reutilizam a propriedade auditada. Conflitos de inventário impedem a recomendação. | Completar catálogo, demanda e cenários externos com custos próprios de expansão. Demonstrar o esgotamento das opções internas com cobertura auditada antes de recomendar um hub. |
| A5/A8/A9 | Existem contratos de pré-voo, controles de execução e métricas. | Homologar o executor, testar a conciliação após falhas e calibrar o lucro previsto com observações reais. A execução segue bloqueada em G0. |

A última validação registrou 2.205 testes aprovados e 1 ignorado no Windows. A base anterior passou em 16 testes simulados do instalador no Ubuntu via WSL. Evidências e resultados por entrega constam no [histórico de entregas](ENTREGAS_ROADMAP.md). Para retomar, leia o [contexto permanente](contexto.md).

## 1. Visão e regra central

Objetivo: tornar o AirlineManager4BOTWEB capaz de decidir **se, onde, quando e com que configuração investir**, usando dados verificáveis da conta ativa, sem depender de decisões manuais no fluxo normal.

**Inverter a ordem atual:** não comprar primeiro e procurar rota depois. Encontrar oportunidades operacionalmente viáveis por hub/rota, comparar aeronaves e motores em cada uma, calcular retorno e custo total e só então executar a aquisição aprovada pela política.

Fluxo desejado:

1. Conciliar **saldo, reserva, frota atual, aeronaves pendentes, hubs adquiridos, rotas ocupadas, vagas de hangar, modo de jogo e dados de mercado**.
2. Pesquisar rotas ainda disponíveis para cada **hub próprio**, com demanda residual verificável, pistas, alcance e escala se aplicável.
3. Comparar **modelo + motor + hub + rota + configuração Y/J/F**, inclusive alternativas por relação entre lucro incremental, investimento, prazo de retorno e risco.
4. Bloquear candidatos com evidência ausente, antiga, contraditória ou com custo não validado. Não converter falta de dados em lucro zero ou em aprovação.
5. Se existir oportunidade em hub próprio, selecionar a **melhor proposta global**, respeitando caixa, manutenção, limites de gastos e regras do operador.
6. Se **nenhum hub próprio** tiver oportunidade viável após uma varredura com cobertura comprovada, avaliar novos hubs. Enviar ao Telegram um ranking explicável com **hub + aeronave + motor + rota + investimento total + retorno + pendências**. Caso a pesquisa esteja incompleta, reportar **sem conclusão**, não **sem oportunidade**.
7. Inicialmente, compra de hub requer aprovação. No estágio final, oferecer opção independente **Comprar hub automaticamente**, desligada por padrão, com limites estritos e verificação da posse antes da compra da aeronave.
8. Persistir plano, evidências, resultados, falhas, economia real versus projetada e motivo de cada decisão. Nunca criar compra duplicada após timeout ou reinício.

O operador deve poder selecionar modos **Somente analisar**, **Sugerir e pedir aprovação** e **Autônomo dentro de limites**, com interruptores separados para comprar aeronaves e hubs. Controle de desligamento imediato e simulação verdadeira.

## 2. Diagnóstico do código em 22/11/2026

| Área | Base existente | Lacuna verificada / hipótese de validação |
| --- | --- | --- |
| Aquisição de aeronaves | src/fleet.py: buy_aircraft(), save_for_goal(), order_aircraft() | score_models() usa distância hipotética por categoria/modelo, estimativa de demanda fixa em daily_profit(), sem provar rota para o novo avião antes da encomenda. A seleção da oferta por maior score/critério de meta não é otimização global hub/rota/motor. |
| Motores | src/engine_selection.py | Reconhece um grupo select/radio, opções default, fastest, economical ou name; a leitura de velocidade/combustível depende de atributos data-* do HTML e não está homologada para todas as variantes. O modo default não verifica motor final. Falta comparação financeira de cada variante e revalidação do custo/especificações após selecionar. |
| Alocação no hub | src/fleet.py: order_aircraft(); seletor nativo #hubSelection indicado no cabeçalho de fleet.py e em src/game_source_probe.py | A rotina atual de compra não seleciona explicitamente nem confirma #hubSelection; precisa validar que o hub de entrega coincide com o plano. |
| Hubs próprios | src/hub_registry.py; src/hub_recommendations.py; GET /api/hubs; GET /api/hubs/recommendations | Já há validação conservadora de evidências e recomendações **somente leitura**. O vínculo permanente individual aeronave→hub ainda depende de fonte explícita do jogo. |
| Novos hubs | src/hub_expansion.py; src/game_observations.py; GET /api/hubs/expansion | Coleta incremental de preços e demanda, inclusive com controle de validade; ranking ainda depende de cenários financeiros confirmados. Não há rotina integrada de compra de hub no ciclo atual. |
| Pesquisa de demanda | src/fleet.py: search_routes(); src/game_observations.py: collect_owned_hub_demand() | Precisa alimentar cenários novos de forma completa e repetível, inclusive hubs candidatos não adquiridos se a interface real do jogo permitir; não inferir demanda sem fonte. |
| Rentabilidade | src/route_optimizer.py: estimate_route(); src/fleet.py: daily_profit(); src/economy.py | Hoje há modelos de estimativa distintos e margens que não incluem todos os custos; é necessário um contrato único de cálculo, com custos incluídos/excluídos exibidos e comparação com histórico real. |
| Segurança operacional | src/bot.py: can_spend(), confirm_purchase(), dry_run; config/defaults.ini | Há proteção de gasto e confirmação, mas falta transação planejada por candidato, reconciliação por compra/entrega/hub, chave de idempotência, teto por horizonte e fail-closed integrado. |
| Testes | tests/test_engine_selection.py; tests/test_hub_recommendations.py; tests/test_hub_expansion.py; CI Python 3.10/3.13 | Bons testes unitários de decisão. São necessários contratos DOM reais anonimizados, testes end-to-end com compra fictícia, reinício durante confirmação, concorrência e homologação autenticada sem gastar. |

**Atenção:** o padrão atual possui autobuy_aircraft=on e dry_run=off. A evolução não deve ativar automaticamente uma nova política de investimento em instalações existentes. As funcionalidades novas começam **desligadas** e o comportamento legado deve ser explicitamente preservado ou migrado com consentimento.

**Pendência comprovada nos documentos existentes:** não foi identificado de forma inequívoca no jogo o atributo permanente de hub individual de todas as aeronaves. Nunca inferir a base permanente por origem/destino da rota, posição atual ou último hub visitado.

## 3. Arquitetura-alvo (módulos sugeridos)

Camadas separadas, com contratos estáveis:

- **Observadores de jogo:** somente o processo dono do Selenium acessa a sessão autenticada. Produzem observações normalizadas com ID, fonte, horário, contexto, cobertura e validade; nunca acionam compras.
- **Inventário/Snapshot:** composição imutável por perfil de saldo, modo, hubs, aeronaves, motores, hangares, rede, demandas e preços. Estado completo ou explicitamente parcial.
- **Opportunity Discovery:** pesquisa candidatos hub próprio → rota → conjunto de aeronaves/motores elegíveis. Opcionalmente coleta de hubs externos, com limites e retomada.
- **Feasibility Engine:** regras duras de alcance, pista por segmento, escala, capacidade, rotas duplicadas, demanda residual Y/J/F, slots, caixa, reservas, limites do jogo e compatibilidade de entrega.
- **Economics Engine:** estimativa padronizada de lucro incremental e investimento, com componentes, premissas, incerteza e evidências. Reutilizar/centralizar route_optimizer.py em vez de fórmulas paralelas divergentes.
- **Portfolio Planner:** compara alternativas globais e escolhe um plano ordenado com custo de oportunidade; preferir melhor resultado que atenda às políticas e considerar expansão em hub existente antes de aquisição de novo hub.
- **Policy & Approval:** modos analisar/aprovar/autônomo, limites por compra, janela e perfil; travas de segurança, auditoria e confirmação administrativa.
- **Execution Coordinator:** única fila de mutações no jogo: reserva de intenção → revalidação → compra → confirmação independente → reconciliação; um pedido por vez. Sem repetir após estado incerto.
- **Dashboard & Telegram:** relatório de recomendações com transparência de cálculo, dados pendentes, comandos de aprovação identificados por plano, e histórico de compras/recusas.
- **Learning & Calibration:** confronta lucro previsto com receita/custos observados após entrega e voos, ajusta parâmetros com limites e rastreabilidade, sem inventar conhecimento.

Arquivos possíveis (nomes propostos, não criados nesta entrega):

- src/opportunity_models.py, src/opportunity_discovery.py, src/engine_catalog.py
- src/expansion_feasibility.py, src/expansion_economics.py, src/portfolio_planner.py
- src/investment_policy.py, src/investment_journal.py, src/investment_executor.py
- src/hub_purchase.py, src/expansion_reporting.py, src/forecast_calibration.py

Integrar sem duplicar os registros e validações existentes: hub_registry.py, hub_expansion.py, hub_aircraft_research.py, route_registry.py, route_optimizer.py, engine_selection.py, game_observations.py e web.py.

### Contrato de proposta (exemplo; valores ilustrativos, nunca usados como fato do jogo)

~~~json
{
  "plan_id": "uuid-estavel",
  "profile_id": "perfil-isolado",
  "snapshot_id": "hash-de-evidencias",
  "status": "suggested",
  "kind": "aircraft_on_owned_hub",
  "hub": {"id": "123", "owned": true, "verified_at": 0},
  "route": {"origin_id": "123", "destination_id": "456", "stopover_id": null},
  "aircraft": {"model_id": "789", "engine_id": "motor-real-do-jogo"},
  "evidence": {"coverage": "complete", "observed_at": 0, "source": "game"},
  "economics": {
    "aircraft_cost": null,
    "engine_delta_cost": null,
    "hub_cost": 0,
    "route_fee": null,
    "hangar_cost": null,
    "daily_net_profit_estimate": null,
    "payback_days": null,
    "excluded_costs": []
  },
  "policy": {"approved": false, "reasons": []}
}
~~~

Campos desconhecidos = null e bloqueiam a ação se obrigatórios. Usar timestamps reais, não zero, nas propostas operacionais. Definir versionamento do schema e migração por perfil.

## 4. Entregas em ordem de dependências

### Fase A0 — Baseline, contratos e proteção contra regressões (P0)

- Inventariar features existentes, branches e PR #44; não sobrescrever mudanças em curso nem alterar main diretamente.
- Rodar testes e CI; registrar baseline, riscos, fluxo de dados e limitações.
- Definir schema de observação/plano, estados de aquisição, matriz de fontes e critérios de "dados suficientes".
- Introduzir feature flags novas **desligadas**. Planejamento somente leitura até homologação.
- Revisar tratamento de perfil, tokens, logs e isolamentos da sessão.
- **Aceite:** mesmos comportamentos legados sem mudança de compra; CI verde e matriz de evidências publicada.

### Fase A1 — Motores reais e compra por configuração exata (P0)

- Inspecionar, em sessão autenticada e com leitura apenas, modal real de compra de modelos com um, dois e três ou mais motores; registrar fixtures anônimas para cada estrutura encontrada.
- Separar modelo-base de **variante de motor** (identificador estável do jogo, nome, velocidade, consumo, alcance se variar, preço final, disponibilidade e seleção real).
- Não presumir que motor = quantidade de motores físicos. Tratar cada opção apresentada como **variante de propulsão**; confirmar semântica real do jogo.
- Suportar radio/select e outras estruturas somente após confirmação de DOM, revalidação pós-AJAX e confirmação pré-compra.
- Exigir re-leitura do preço da configuração final, ausência de aviso de saldo insuficiente e correspondência entre engine_id solicitado e selecionado.
- Modo padrão só pode ser aceito após leitura da opção final quando houver múltiplas variantes. Ambiguidade bloqueia.
- Testar todas as variantes, seleção explícita, simulação, mudança de preço, reconstrução de DOM e seletores inesperados.
- **Aceite:** nenhuma compra confirma motor/modelo/preço/hub diferentes dos previstos, e nenhuma alteração ocorre no modo análise.
- Progresso em 25/11/2026: o pré-voo planejado reabre o painel atual após duas verificações de preço e bloqueia a encomenda se o jogo exibir aviso de saldo insuficiente. A evidência disponível ainda não confirma a fonte do preço final por modelo, variante e hub. G0 permanece vigente.
- Consulta autenticada ao A380-800 em 25/11/2026: `#engSelection` apresentou três variantes. O valor em `#acCost` ficou estável ao alternar GP7270 e RR Trent 972 e consultar duas bases de entrega. O elemento observado não expôs `data-final-price`. A cotação final vinculada à configuração continua pendente.

### Fase A2 — Hubs, cobertura e dados de rota completos (P0)

- Finalizar inventário real de hubs próprios e status de base por aeronave com fonte explícita. Quando desconhecido, manter "Base a confirmar" sem impedir ranking das bases com dados independentes verificados.
- Auditar paginação dinâmica: 20 posições típicas por página, páginas variáveis, aeronaves chegando durante a auditoria, IDs únicos, totais coerentes, cobertura integral no mesmo snapshot ou marcação **parcial**.
- Completar coleta de preço, pontos, pista, país, disponibilidade e demanda dos hubs candidatos; descobrir se pesquisa de rota pode partir de **hub ainda não comprado**.
- Montar feed de cenários para HubAircraftResearchRegistry.record() e HubExpansionRegistry.record_research(), com fonte e data comprovadas.
- Armazenar mapas de cobertura por hub, rota, modelo e ciclo; expirados não habilitam compra.
- Evidência em 25/11/2026: uma consulta autenticada retornou 50 linhas de pesquisa, todas sinalizadas como demanda de evento, sem controle de continuação identificado. O fim das combinações da amostra continua insuficiente para provar a enumeração de destinos por hub ou o esgotamento interno. A aba de frota consultada exibiu contagens agregadas. Paginação da frota e vínculo por aeronave seguem pendentes.
- **Aceite:** painel mostra evidência e cobertura; ausência de pesquisa de hub externo aparece como impeditivo, não como candidato viável.

### Fase A3 — Otimizador de rotas e rentabilidade por motor (P0)

- Gerar candidatos para cada combinação admissível **hub próprio × rota × modelo × motor × configuração de assentos**; aplicar poda de inviáveis antes de estimar retorno.
- Validar distância, alcance por segmento e escalas, comprimento de pista na unidade oficial do jogo, demanda residual após outras aeronaves, horários/rotação, competição da própria frota e regras de rotas duplicadas.
- Registrar separadamente a demanda ampliada por evento. Se uma leitura correlacionada exibir o aviso, manter o bloqueio da projeção econômica para a amostra.
- Calcular receita diária por Y/J/F e voos possíveis, combustível e CO₂ em preço configurado e cenários de stress. Incluir custos de rota/hangar/aeronave/motor e projetar manutenção, A-check e demais despesas **apenas se houver fórmula/evidência verificada**; caso contrário, marcar como excluídos e aplicar reserva/margem conservadora configurável.
- Reportar lucro incremental, capex, caixa após compra, payback, ROI e sensibilidade (demanda, combustível, CO₂, ocupação), mais confiabilidade da observação.
- Comparar alternativas para diferentes hubs e motores, não só o maior score de modelo.
- **Aceite:** resultado reproduzível por snapshot; nenhuma rota ocupada/inviável ou com demanda desconhecida é elegível; cálculo explicável e testado.

### Fase A4 — Planejamento global de aquisições (P1)

- Progresso em 25/11/2026: a captura produtiva inicializa o registro A3/A4 ativo e invalida os casos anteriores quando muda a identidade da coleta. Uma captura parcial sem casos permanece inconclusiva para investimento, com decisão de não comprar. A alimentação de casos completos e certificação da cobertura ainda dependem das evidências A1–A3; nenhum gate de gasto foi promovido.
- A comparação produtiva passou a exigir saldo A3, saldo da captura e leitura viva verificada. O menor saldo bruto limita os candidatos antes do ranking, descontando compromissos e reserva uma única vez. Divergências ou falta de prova mantêm a decisão inconclusiva, e a leitura posterior ao ranking impede criação de plano com saldo alterado ou regressão temporal. O painel distingue os três valores, o teto bruto e o orçamento líquido, inclusive quando não há candidato A4.

- Gerar ranking **global** dos hubs próprios, cada um com suas melhores oportunidades e com a melhor oportunidade da companhia.
- Antes da compra, descontar pedidos pendentes, aeronaves sem rota, custos/compromissos futuros, limite de hangar, reserva operacional e gasto máximo por ciclo/período.
- Reavaliar modelo/motor se a rota lucrativa só for viável com propulsão diferente; não gastar o orçamento na alternativa inferior sem justificativa.
- Modelar trade-off entre lucro absoluto, lucro por capital, retorno, risco e diversificação. Pesos editáveis e defaults explícitos. Não escolher automaticamente só por payback mínimo.
- **Aceite:** plano mostra por que A venceu B e quando a decisão passa a ser "não comprar".

### Fase A5 — Pré-voo da aquisição e compra segura de aeronave (P1)

- Validar rota e destino antes de abrir a encomenda. Selecionar e confirmar **#hubSelection** explicitamente, compatível com o hub do plano.
- Pré-checagem imediata de caixa, preço, motor, aeroporto-base, capacidade, disponibilidade e snapshot; cancelar se qualquer dado mudou.
- Introduzir journal persistente: PROPOSED → APPROVED → PRECHECKED → SUBMITTED → CONFIRMED ou UNKNOWN/FAILED, com chave de intenção e tentativas.
- Pós-compra, confirmar por sinal independente do jogo: saldo, pedido pendente, matrícula/ID, hub de entrega; não inferir sucesso apenas de clique ou texto de notificação.
- Após timeout, **não repetir compra** até conciliação. No máximo um executor de mutações com lock por perfil.
- Integrar Telegram e painel com plano, motor e hub realmente confirmados.
- **Aceite:** testes de compra correta, compra recusada, timeout e restart sem compra em dobro; modo simulação não faz mutações.

### Fase A6 — "Nenhum hub próprio viável": sugestão de expansão (P1)

- Progresso em 25/11/2026: identidade nativa de modelo/motor/itinerário, integridade das provas econômicas, deduplicação e comparação do investimento com caixa líquido da reserva implementadas e testadas. O painel e o Telegram exigem perfil e snapshot produtivo correspondentes em todas as fontes independentes usadas pelo gate, e preservam timestamps fracionários. Cenários com identidade incompleta, escala não comprovada ou provas contraditórias continuam bloqueados. Os produtores de pesquisa externa e da cobertura vinculada à captura, a coleta real e a homologação seguem pendentes em G0.

- Progresso adicional em 25/11/2026 (A6–A8): o ranking exclui IDs duplicados e hubs próprios, valida montantes, preços, pontos e frescor. Despesas recorrentes excluídas geram projeções condicionais, sem elegibilidade para A8; o painel e o Telegram preservam as ressalvas. O gate produtivo exige declaração explícita das exclusões. Testes simulados aprovados, homologação autenticada pendente.

- Captura A6 em 25/11/2026: o worker incorpora o catálogo externo e as amostras nativas de demanda à mesma identidade de snapshot usada por A3/A4. A propriedade vigente é pré-requisito; candidatos próprios, identidades duplicadas, fontes incompatíveis e observações vencidas são excluídos. Preço e pontos mantêm relógios independentes. O resumo agregado reavalia a validade temporal e permanece parcial e inelegível para compras.
- Replay A6 em 25/11/2026: a API e a interface de pesquisa externa avaliam somente dados da captura produtiva do perfil (inventário, demanda, motores, mercado, saldo, reserva e parâmetros). A paginação é vinculada ao snapshot e às evidências vigentes; expiração ou substituição da captura reinicia o cursor. O caixa acima da reserva é anterior aos compromissos. Captura ausente, antiga ou inválida deixa a pesquisa indisponível. A avaliação continua diagnóstica e parcial; faltam comprovação do esgotamento interno, fontes econômicas nativas completas e gravação produtiva de cenários conclusivos.
- Propriedade A6 em 25/11/2026: painel e Telegram compartilham a prova de hubs próprios da captura auditada. Se o inventário vivo vigente divergir, o gate perde a prova e o ranking diagnóstico exclui os hubs conhecidos pelas duas fontes. A cobertura da frota e o esgotamento dos hubs próprios continuam por comprovar.

- Só entrar nesta fase com varredura dos hubs próprios conclusiva e sem proposta elegível (ou com política explícita de comparar expansão externa mesmo havendo oportunidades).
- Pesquisar novos hubs por regiões e mercados, não apenas selecionar o mais barato. Comparar **hub candidato + modelo/motor + rota(s)**, considerando custo do hub, pontos, aeronave, rota, hangar e reserva.
- Identificar se a pesquisa pré-compra permite calcular demanda confiável. Sem ela, **sugerir com ressalva**, nunca compra automática.
- Produzir ranking Telegram: três melhores candidatos com valor, lucro projetado, prazo, justificativas, pontos exigidos, dados pendentes e motivo de nenhum hub existente ter passado.
- Deduplicar alertas por snapshot, com cooldown e mensagem quando a recomendação mudar significativamente.
- **Aceite:** nenhuma recomendação é fabricada a partir de dados incompletos; operador identifica todas as premissas, custos e obstáculos.

### Fase A7 — Interface Hubs 2.0 e controles de autonomia (P1)

- Corrigir e completar visão de hubs existentes: quantidade **comprovada** de aeronaves, rotas vinculadas, cobertura, lucro observado versus estimado, hangar, caixa disponível e oportunidades.
- Criar visão **Planejador de Expansão**: comparação de hubs, mapas/tabelas de rotas, variantes de motor, custos detalhados, retornos e bloqueios.
- Adicionar controles separados: auto compra de aeronaves com oportunidade validada, auto compra de hubs, preferência de motor/otimização automática, capex máximo, reserva, lucro mínimo, payback máximo, nº de aquisições por dia, modo análise/aprovação/autônomo, alertas Telegram e kill switch.
- Evitar que o switch legado "autobuy_aircraft" ative a nova política sem migração controlada. Não misturar dinheiro do jogo e moeda real.
- APIs autenticadas, autorizadas e separadas para **GET análise** e **POST aprovação/ação**. Proteção contra CSRF/replay quando usar ações remotas.
- Desktop e mobile; dados por perfil; estado e próxima reavaliação visíveis.
- **Aceite:** usuário consegue entender, controlar e impedir qualquer gasto sem tocar no arquivo de configuração.

### Fase A8 — Compra opcional e automática de novos hubs (P2; última etapa de gasto) 

- Implementar seletor + executor de compra real de hubs usando exclusivamente controles comprovados e preço atualizado. Não usar endpoints de mutação não homologados.
- Toggle **auto_buy_hub=off por padrão**, aprovação por plano no modo assistido. Limite financeiro e de pontos independente da compra de aeronave.
- **Transação de duas etapas lógicas:** (1) comprar hub e confirmar propriedade na lista de hubs próprios; (2) revalidar mercado, demanda, aeronave, motor, caixa e hangar e só então propor/encomendar aeronave para o novo hub.
- Se a primeira etapa funcionar mas a segunda falhar, preservar hub adquirido, notificar bloqueio e replanejar sem recomprá-lo.
- Sem compra se catálogos parciais, dados contraditórios, pontos insuficientes, caixa desatualizado, rota pendente, sessão incerta ou hipótese não verificada.
- **Aceite:** simulação integral com falhas injetadas; compra real **somente após aprovação explícita de homologação** e com limites pequenos; nenhum gasto duplo em retomada.

### Fase A9 — Autonomia operacional, calibração e observabilidade (P2)

- Comparar resultado previsto com histórico de cada rota após a entrega e os voos; ajustar premissas apenas com amostras suficientes.
- Replanejar ao chegar aeronave, alterar demanda, ficar sem saldo, surgirem preços melhores, encerrar duplicidade ou variar a frota.
- Relatório diário e por compra no Telegram com "planejado × confirmado × observado", alertas úteis e justificativa para não comprar.
- Métricas: cobertura de dados, oportunidades avaliadas, precisão de previsão, erros de compra, gastos evitados, aquisições verificadas, tempo de detecção e recuperação.
- **Aceite:** operação contínua auditável, sem decisões silenciosas e com degradacão segura após falha.

## 5. Critérios matemáticos, integridade e política de decisão

**Filtros obrigatórios:** fonte autenticada, validade temporal, cobertura adequada, modelo/motor disponíveis, hub comprado ou compra validável, rota não ocupada quando duplicatas bloqueadas, pista suficiente, alcance/escala comprovados, demanda residual suficiente, preço/encargos completos, saldo fresco, reserva protegida e janela de investimento aberta.

**Economia:** investimento total = preço final aeronave+motor + taxa rota + custo de hangar + custo de hub (quando novo) + taxas explícitas. Lucro operacional incremental diário = receita tarifária Y/J/F projetada − combustível − CO₂ − custos recorrentes comprovados. Despesas não comprovadas devem ser destacadas e descontadas por margem de segurança configurada, sem ser apresentadas como números observados. Payback = investimento total / lucro incremental diário somente se lucro > 0. Classificar viabilidade física e financeira separadamente.

**Ranking recomendado:** decisão multiobjetivo, com condições mínimas primeiro (demanda, margem de segurança, payback, saldo), e só depois um score transparente que balanceie lucro incremental, eficiência do capital, risco, confiabilidade e diversificação; permitir pesos configuráveis e comparação lado a lado.

**Invariantes:** (a) nenhuma compra sem plano válido; (b) nenhum plano tem IDs inferidos; (c) cada gasto exige revalidação imediata; (d) automações concorrentes não compartilham a sessão Selenium; (e) saldo e inventário pós-clique não equivalem automaticamente a sucesso; (f) tentativa incerta não se repete; (g) todo plano é específico do perfil; (h) todos os bloqueios têm código de motivo; (i) um novo hub não é adquirido só porque não houve dados suficientes nos hubs atuais.

## 6. Paralelismo — usar o MÁXIMO de agentes úteis

**Diretriz obrigatória de execução:** usar o maior número de agentes independentes que o ambiente realmente disponibilizar, distribuindo trabalhos com interfaces estáveis, sem inventar execuções ou agentes. Maximizar paralelismo útil, não número nominal. Um coordenador integra e faz gate de qualidade. Não bloquear módulos independentes enquanto um outro aguarda homologação.

| Agente/frente | Entrega independente | Arquivos principais | Depende de |
| --- | --- | --- | --- |
| **A — Arquiteto/coordenador** | Contratos, integração, matriz de dependências, revisão de PRs, backlog, política de merge | docs, tests, CI | Imediato |
| **B — Especialista em motores** | Descoberta, seleção e comparação financeira de variantes | engine_selection.py, novo engine_catalog.py | Contrato A0 |
| **C — Especialista em hubs existentes** | Inventário, cobertura, vínculo individual e integridade de perfis | hub_registry.py, route_registry.py | Contrato A0 |
| **D — Especialista em novos hubs** | Preços, países, demanda e cenários de candidatos | hub_expansion.py, game_observations.py | Contrato A0 |
| **E — Especialista em rotas** | Geração/validação de rotas e escalas, ocupação e demanda residual | route_optimizer.py, route_stopover.py, oportunidade | Contrato A0 |
| **F — Modelagem financeira** | Economia por motor/rota, custos, payback, sensibilidade e calibração | economy.py, expansion_economics.py | Contrato A0 |
| **G — Planejador global** | Ranking e seleção do melhor investimento em todos os hubs | portfolio_planner.py, investment_policy.py | Interfaces B–F |
| **H — Executor seguro** | Diário, idempotência, transações, compra aeronave/hub e reconciliação | investment_executor.py, fleet.py, hub_purchase.py | A1, A3, A4 |
| **I — Interface web/mobile** | Hubs 2.0, cockpit, aprovação e transparência | web.py, assets/web/index.html | Contratos A0 |
| **J — Telegram/notificações** | Sugestões, aprovação autorizada, falhas, comparativos e deduplicação | notify.py, expansion_reporting.py | Contratos A0 |
| **K — Qualidade e segurança** | Testes unitários, DOM fixtures, fuzz, race, replay, dry-run, CI, revisão adversarial | tests/, workflows | Imediato |
| **L — Documentação e UX** | README, screenshots, histórico por entrega, instruções e migração | docs/, scripts/screenshots.py | Imediato |

**Regras de concorrência:** um agente = uma branch/PR e um escopo claro; todos podem ler o jogo, mas **um único proprietário do navegador/driver autenticado por perfil** faz leitura ativa sequencial e nenhuma mutação sem gate. Agentes de negócio trabalham com snapshots sanitizados/fixtures. Arquivos compartilhados (fleet.py, bot.py, web.py, defaults.ini, settings_schema.py) ficam sob integração coordenada para evitar colisões. Testes e revisão acontecem em paralelo.

**Ondas recomendadas:**
- **Onda 1:** A, B, C, D, E, F, I, J, K, L podem iniciar em paralelo com mocks e contratos; 1 operador de navegador faz somente sondagem autorizada.
- **Onda 2:** G integra modelos/evidências; H constrói journal + executor em ambiente simulado; I/J integram resultados; K amplia os testes.
- **Onda 3:** homologação A1–A7 em modo análise; habilitar compra de aeronave por plano em canário controlado.
- **Onda 4:** A8 para compra de hubs **somente** após aprovação explícita e evidências reais; depois A9.
- **Limite real:** não presumir que a plataforma executa doze agentes; solicitar o máximo **suportado** e registrar quantidade efetivamente mobilizada.

## 7. Plano de testes, navegador e aprovação de compra

**Sem credenciais em código, fixture, Markdown, log, PR ou Telegram.** Se a validação exigir login, usar sessão de navegador autorizada e fluxo seguro de autenticação apresentado ao usuário. Nunca solicitar senha por comentário do GitHub nem persistir cookies/tokens. Navegação real começa em modo leitura: catálogo de motores, modal de compra, seletor de hub, pesquisa de rota e disponibilidade de hubs. O acesso autenticado e a prova de fonte fazem parte da homologação, não são presumidos nesta documentação.

**Testes mínimos obrigatórios:**

1. Modelos com múltiplas variantes de motor; preço alterado e DOM reconstruído depois de trocar motor; seleção padrão não validada; motor desabilitado.
2. Mesmo modelo em hubs diferentes com demandas distintas; uma rota inviável, outra rentável; a melhor combinação global vence.
3. Hub adquirido mas sem aeronaves; aeronave em trânsito; matrícula alterada; ausência de base permanente; inventário com 20 por página e novas aeronaves durante paginação.
4. Todos hubs próprios avaliados sem lucro vs avaliação parcial; só o primeiro caso habilita a pesquisa de novos hubs como "nenhum viável".
5. Novo hub com compra em pontos; demanda não observável antes da compra; preço/caixa insuficiente; ranking não aprova compra.
6. Compra de hub confirmada, seguida de falha na compra de aeronave; reentrada não recompra hub.
7. Ordem de aeronave enviada mas retorno AJAX incerto; reconciliação posterior, sem duplicação.
8. Ingestão de duas propostas concorrentes; lock por perfil, atualização de saldo e rejeição de snapshot vencido.
9. Dry-run integral sem POST, clique, compra ou mudança no jogo; comandos de aprovação autenticados e anti-replay.
10. Regressões de decolagem, rotas duplicadas, compras de combustível/CO₂, manutenção, atualizações do servidor e interface PT-BR.

CI existente exige Ruff, compileall e pytest em Python 3.10/3.13. Acrescentar smoke tests de JavaScript/DOM quando aplicáveis, testes de navegação com fixtures anônimas, e testes de integração sem dinheiro real do jogo. Não fazer deploy na máquina de produção nem merge automático com testes falhando.

## 8. Gates de liberação

| Gate | Condição | Pode gastar? |
| --- | --- | --- |
| **G0 — Análise** | Código mapeado, contratos e CI aprovados | Não |
| **G1 — Recomendações** | Pesquisa real comprovada; modelos, motores, hubs e rotas explicáveis | Não |
| **G2 — Simulação** | Executor e journal aprovados; falhas/reinícios testados | Não |
| **G3 — Aeronave assistida** | Operador autoriza ensaio real individual; custo/motor/hub/rota verificados | Só aquela compra autorizada |
| **G4 — Aeronave autônoma** | Piloto bem-sucedido, limites configurados, opção habilitada conscientemente | Sim, dentro da política |
| **G5 — Hub autônomo** | Pesquisa externa comprovada; compra de hub e pós-confirmação homologadas; opção separada ligada | Sim, dentro da política |

Não promover para main nem implantar apenas porque o roadmap ou os testes de simulação estão concluídos. Validar a PR #44 e sua relação com as alterações vigentes antes de qualquer merge.

## 9. Definição de pronto por entrega / histórico obrigatório

Em **cada PR** registrar:
- objetivo, módulos afetados, cenário coberto e casos que seguem pendentes;
- evidência de jogo (sanitizada) vs mock, data e perfil sem dados pessoais;
- testes executados, resultados e limitações;
- riscos de regressão e checklist de rollback;
- se houve compra ou não (default: não), comportamento de dry-run e flags;
- arquivos/linhas alterados, commit e link do PR;
- atualização em docs/ENTREGAS_ROADMAP.md ou histórico de implementação vigente, após resolver conflito com outras branches.

Nenhum agente marca uma etapa como concluída por apenas gerar código ou mock. **Entregue**, **testado**, **homologado no jogo** e **implantado** são estados diferentes, exibidos separadamente.

## 10. Próxima sequência de execução

1. **A1/A2.** Investigar em sessão autenticada, somente leitura, o preço final por modelo, motor e hub de entrega, o vínculo permanente aeronave–hub, a paginação e as fontes nativas de layout, demanda e tarifas. Registrar a origem e a vigência de cada observação.
2. **A3/A4.** Com as evidências válidas, publicar casos completos via `AuditedEconomicsRegistry.record()` e cobertura via `record_portfolio_evidence()` no worker que possui a captura. Vincular preço, layout Y/J/F, disponibilidade, demanda residual, tarifas, taxa de rota, custos incrementais e compromissos ao mesmo snapshot e manter os bloqueios quando faltarem dados.
3. **A6/A7.** Completar os produtores de catálogo, demanda e custos externos e persistir cenários via `HubExpansionRegistry.record_research()`. Exigir prova de esgotamento interno com cobertura por hub antes de habilitar recomendações conclusivas no painel e no Telegram.
4. **A5/A8/A9.** Validar pré-voo, conciliação de timeout e reinício, confirmação de propriedade e calibração conforme os gates. A base permanece em G0. Qualquer ensaio real exige avanço de gate, homologação e autorização explícita.
5. Atualizar o contexto e o histórico a cada entrega. Conferir os requisitos e as pendências da PR #44 na revisão da PR #46 antes de qualquer promoção.

### Prompt de execução para um orquestrador multiagente

> Seguir docs/ROADMAP_AUTONOMIA_TOTAL.md integralmente no repositório andreypiekas/AirlineManager4BOTWEB. Usar o número máximo de agentes paralelos realmente disponível, em branches e módulos independentes, com um coordenador para integração e um único proprietário do navegador autenticado por perfil. Priorizar A0, A1, A2 e A3 e usar a PR #44 como referência histórica de hubs na revisão da PR #46. Respeitar os gates G0–G5. Exigir autorização explícita para promoção à main e implantação, e também homologação para compras reais. Em cada entrega, registrar código, testes, evidências, PR e próxima dependência no histórico. Continuar nas frentes independentes disponíveis e manter a validação pendente onde faltarem dados autenticados.
