# Contexto permanente — AirlineManager4BOTWEB

> Leia este arquivo no início de cada nova conversa ou retomada do projeto. Em seguida, leia `docs/ROADMAP_AUTONOMIA_TOTAL.md` e consulte o início de `docs/ENTREGAS_ROADMAP.md` para identificar as entregas mais recentes. Antes de editar, confira `git status`, branch e último commit. Preserve todas as alterações existentes.

> Em tarefas longas, registre neste arquivo o estado atual, os resultados, os limites e a próxima ação nos checkpoints e antes de uma compactação previsível. Após uma compactação automática, releia este arquivo antes de continuar. Para uma nova conversa, basta indicar `docs/contexto.md` como ponto de partida. O material multiparte original fica separado em `docs/codex_multipart_commit.md`, arquivo local de histórico bruto preservado fora do commit.

## 1. Identificação do projeto

- Repositório local `E:\DRIVE\github\AirlineManager4BOTWEB`.
- Repositório remoto `https://github.com/andreypiekas/AirlineManager4BOTWEB`.
- Projeto Python de automação do jogo Airline Manager 4, com Selenium, painel web e notificações Telegram.
- Idioma de comunicação e documentação `pt-BR`.
- Objetivo permanente — alcançar autonomia para avaliar e executar investimentos em aeronaves, variantes de motor, hubs e rotas, com dados comprovados, cálculos explicáveis e proteção contra compras incorretas ou duplicadas.

## 2. Instruções obrigatórias de trabalho

1. Ao final de cada interação que alterar o repositório, criar commit e enviar a branch de trabalho ao GitHub. Informar o commit e o resultado do push.
2. Trabalhar na branch de tarefa existente ou em uma branch `codex/*`. Não desenvolver diretamente em `main`.
3. Não fazer merge para `main` nem implantar no servidor de produção sem autorização explícita.
4. Não executar compras reais no jogo. A homologação de compra exige aprovação explícita e segue os gates G0–G5 do roadmap.
5. Preservar alterações locais, arquivos não rastreados e trabalho de outros agentes. Inspecionar `git status` e `git diff` antes de qualquer operação que possa sobrescrever conteúdo.
6. Usar o máximo de agentes independentes que o ambiente realmente disponibilizar quando isso ajudar a avançar frentes paralelas. Um agente por escopo/branch, com integração e revisão centralizadas. Somente um processo pode controlar o navegador autenticado de cada perfil.
7. Não considerar mocks, fixtures ou testes unitários como homologação no jogo. Registrar separadamente o que foi implementado, testado, homologado e implantado.
8. Não incluir credenciais, cookies, tokens, dados pessoais ou conteúdo de sessão em código, fixtures, logs, documentação, issues ou mensagens.
9. Não inferir dados ausentes. IDs, preços, motores, hubs, demanda, cobertura e lucro sem evidência válida devem permanecer desconhecidos e bloquear decisões que dependam deles.
10. Ao retomar, continuar do estado real do repositório. Não reiniciar o trabalho nem pedir ao usuário que repita informações já registradas aqui.

## 3. Objetivo e ordem correta das decisões

O fluxo de autonomia total está descrito integralmente em `docs/ROADMAP_AUTONOMIA_TOTAL.md`. A regra central é avaliar a oportunidade antes de encomendar uma aeronave.

1. Conciliar saldo, reserva, frota, pedidos pendentes, hubs, rotas, hangares, modo de jogo e dados de mercado.
2. Pesquisar oportunidades em cada hub próprio, com demanda residual, alcance, pistas, escalas e ocupação comprovados.
3. Comparar combinações de hub, rota, modelo, variante de motor e configuração de assentos.
4. Calcular investimento, lucro operacional incremental, retorno, riscos e dados excluídos do cálculo.
5. Escolher a melhor oportunidade global respeitando caixa, reserva, manutenção e limites de investimento.
6. Somente após uma varredura completa e conclusiva dos hubs próprios sem oportunidade, avaliar expansão para novos hubs.
7. Inicialmente, compras de hubs exigem aprovação. Compra automática de hub é a última etapa e começa desligada.
8. Persistir evidências, planos, decisões, tentativas e reconciliação. Uma operação incerta nunca pode ser repetida sem conciliação.

Modos finais previstos — somente analisar, sugerir e pedir aprovação, autônomo dentro de limites. Compra de aeronave e compra de hub possuem controles independentes.

## 4. Arquitetura e arquivos principais

| Área | Arquivos principais | Responsabilidade |
| --- | --- | --- |
| Frota e compra de aeronaves | `src/fleet.py`, `src/aircraft_order_hub.py` | Pesquisa, seleção, preparação e confirmação de encomendas. |
| Motores | `src/engine_selection.py`, `src/engine_detail.py` | Catálogo de variantes, seleção e validação do preço final. |
| Hubs próprios | `src/hub_registry.py`, `src/hub_aircraft_research.py` | Inventário por perfil, pesquisa e recomendações por base. |
| Novos hubs | `src/hub_expansion.py`, `src/game_observations.py`, `src/hub_recommendations.py` | Catálogo, evidências, cenários e ranking de expansão. |
| Rotas | `src/route_registry.py`, `src/route_optimizer.py`, `src/route_stopover.py`, `src/fleet.py` | Ocupação, cobertura, escalas, demanda e rentabilidade. |
| Economia e política | `src/economy.py`, `src/investment_policy.py` | Evidências financeiras, limites e gates de execução. |
| Observação do jogo | `src/game_source_probe.py`, `src/game_observations.py` | Diagnóstico somente leitura e coleta com fonte, horário e cobertura. |
| Painel e APIs | `src/web.py`, `assets/web/index.html` | Consultas, recomendações, transparência e controles. |
| Histórico de entregas | `docs/ENTREGAS_ROADMAP.md` | Registro de implementação, testes, pendências e homologação. |

Evitar duplicar registros e motores já existentes. O processo proprietário do Selenium é o único que acessa a sessão autenticada. Os demais módulos trabalham com snapshots e evidências persistidas.

## 5. Regras críticas de segurança e compatibilidade

- `InvestmentPolicy.report()` atualmente informa `execution_available=false` e `release_gate=G0`, pois o executor ainda aguarda homologação.
- O gate da nova política deve bloquear compras planejadas (`plan_requested`) enquanto G0 estiver ativo.
- O fluxo legado de compra deve manter seu comportamento atual até que exista migração explícita e consentida. Não aplicar o novo gate às compras legadas sem uma decisão documentada.
- O fluxo planejado exige ID de hub, preço final positivo e verificado e ID exato da variante de motor. O preço precisa ser lido de fonte final autorizada e permanecer estável durante as verificações.
- `#hubSelection` e `#hubSelect` pertencem a contextos distintos do jogo e podem usar namespaces diferentes de identificadores. Não misturar seus IDs.
- Não inferir o hub permanente de uma aeronave pela origem/destino da rota, posição atual ou último hub visitado. Sem campo explícito, registrar `Base a confirmar`.
- A frota costuma mostrar 20 aeronaves por página, mas a quantidade e o carregamento podem variar. Cobertura incompleta deve continuar marcada como parcial.
- Compra, criação de rota ou outra mutação só é considerada concluída após confirmação independente do jogo. Timeout ou resposta incerta exigem conciliação antes de nova tentativa.
- O modo de simulação não deve enviar mutações ao jogo.

## 6. Estado conhecido do roadmap em 25/11/2026

O histórico detalhado está em `docs/ENTREGAS_ROADMAP.md`. As entregas recentes abrangem A1, A3, A4, A6, A7, A8 e A9, em diferentes níveis de implementação e teste. A maioria permanece no gate G0, sem autorização de execução real.

### Motores e encomenda (A1)

- O catálogo de variantes possui contrato tipado para preço final, identidade do motor, valor, fonte e estado de verificação.
- A seleção e a validação do motor são separadas da validação do preço.
- A leitura autenticada realizada em 23/11 identificou `#engSelection` e `#acCost`, mas ainda não comprovou um preço final associado a cada variante. Portanto, `price_verified=false` mantém compras planejadas bloqueadas.
- A validação final precisa confirmar modelo, motor, base de entrega, preço com motor incluído, estabilidade do checkout e ausência de aviso de saldo insuficiente.

### Hubs e cobertura (A2)

- Há inventário de hubs próprios, recomendações por base, catálogo de hubs externos, observações e cobertura incremental por perfil.
- A origem permanente individual da aeronave ainda não foi comprovada na interface real.
- O carregador real da paginação, catálogo de hubs compráveis, preços e demanda de hubs externos ainda dependem de homologação em sessão autenticada.
- Fixtures e diagnósticos DOM existentes são somente leitura e não substituem evidência da conta real.

### Economia e planejamento (A3/A4/A9)

- Existem estimativas de rotas, custos de combustível e CO₂, pesquisa econômica retomável, evidências contábeis por snapshot, custos incrementais de hangar e limites de capital/pontos por perfil.
- Existem registros e relatórios para confrontar estimativas e observações. Custos não comprovados, como reparos e A-check, continuam explicitamente excluídos.
- A integração global ainda precisa assegurar que todas as combinações relevantes de hub, rota, modelo, motor e assentos sejam comparadas com cobertura suficiente antes de recomendar investimento.

### Expansão e interface (A6/A7/A8)

- Há ranking e filtros para hubs externos, limites independentes de capital e pontos, APIs de consulta e interface de hubs/recomendações.
- A compra de hub ainda não está homologada e permanece desligada. A confirmação de propriedade deve ocorrer antes de qualquer proposta de aeronave para a nova base.
- Os controles de autonomia devem deixar claro o modo, limites, próxima reavaliação, evidências e motivo de bloqueio.

### Pendências externas

- Homologação autenticada e somente leitura dos seletores reais, variantes de motor, preços, hub de entrega, vínculo permanente aeronave–hub, paginação, pesquisa de demanda e catálogo de novos hubs.
- Testes de integração com reinício, timeout, concorrência e idempotência do executor.
- Comparação do lucro previsto com dados reais observados após voos e calibração com amostras suficientes.
- Nenhuma dessas pendências pode ser marcada como homologada apenas com testes simulados.

## 7. Checkpoint de trabalho de 25/11/2026

- Branch de trabalho `codex/autonomia-a0-a1-20261122`. Referência anterior à entrega: `c202382` (`feat(a1): vincular preço final à variante do motor`). Consulte `git log -1 --oneline` e `git status --short --branch` para a referência atual; o hash do commit que contém este documento não pode constar no próprio commit.
- `AGENTS.md` orienta toda nova conversa a ler este contexto e o roadmap, preservar alterações e enviar as entregas ao GitHub.
- `uv.lock` já existia como arquivo não rastreado; permanece preservado e fora da entrega.

### Implementações desta rodada

- A3/A1: `src/fleet.py` usa tarifas automáticas Y/J/F e distância nativa do formulário para recalcular a rentabilidade da rota direta. Bloqueia pagamento de taxa quando o lucro é desconhecido, não finito ou não positivo. A estimativa de mercado é apenas ordenação. A política G0 permanece restrita às compras planejadas, mantendo o fluxo legado conforme o roadmap. A fórmula de `route_optimizer.estimate_route()` ainda contém aproximações operacionais e não constitui contabilidade A3 completa.
- A3/A4: `src/audited_economics_registry.py` vincula a certificação de cobertura às IDs dos casos econômicos efetivamente revisados. Alterações no conjunto de casos, remoções ou registros legados sem vínculo invalidam a cobertura; registros idempotentes preservam a certificação. Ao ultrapassar o limite de armazenamento, o snapshot fica persistentemente truncado e não pode ser recertificado, mesmo após releitura. Um novo snapshot válido reinicia esse estado. Evidências financeiras independentes são preservadas.
- A2: `src/owned_hub_research_ingestion.py`, `src/hub_aircraft_research.py`, `src/hub_recommendations.py` e o planejador separam alternativas por ID nativo do modelo, inclusive modelos homônimos. Registros antigos mantêm identidade por nome; uma evidência sem ID só suprime pesquisa por ID quando o nome identifica uma alternativa única no conjunto observado. A existência de homônimos reais no catálogo permanece a confirmar.
- A0/A3/A4: `src/opportunity_models.py`, `src/expansion_economics.py` e `src/portfolio_planner.py` exigem que lucro, taxa de rota, demanda, tarifas e demais observações dependentes do itinerário correspondam à escala proposta. Evidências de outra escala ou sem a escala exigida bloqueiam a avaliação. Rotas diretas continuam compatíveis com evidências antigas sem escala. O ranking auditado preserva alternativas com escalas distintas. `src/investment_plan_bridge.py` bloqueia a conversão de itinerários com escala em intenção até existir suporte explícito no executor e homologação.
- As duas auditorias independentes (colisão A2 de modelos homônimos e falta de vínculo A0 da escala) foram reproduzidas com dados simulados e corrigidas nos fluxos acima. Nenhuma compra real ou implantação foi realizada.

### Validações

- Suíte Windows antes das últimas correções: 2.116 aprovados e 1 ignorado.
- Testes direcionados A0/A2/A3/A4/A5: 340 aprovados. Após a extensão A2 ao registro de observações confirmadas e ajustes de ordenação: 186 aprovados.
- Ruff e `git diff --check` aprovados. Suíte Windows consolidada: 2.121 aprovados e 1 ignorado (131,60 s; testes de instalação Linux excluídos; últimas alterações A2 validadas também em testes direcionados).
- Homologação autenticada e instalação POSIX ainda pendentes; testes simulados não substituem evidência da conta real.

## 8. Próxima sequência de trabalho

1. Continuar a integração produtiva do A3/A4. A captura do worker já inicializa o registro auditado A3, inclusive quando parcial, por meio de `AuditedEconomicsRegistry.begin_capture()`. `record()` e `record_portfolio_evidence()` ainda não possuem produtores de casos completos/cobertura verificada em produção. Separar a construção das observações, avaliação e gravação de casos elegíveis, sempre vinculados à mesma captura. `research_accounting_gate.evaluate_research_gate()` ainda fornece somente pré-requisitos parciais e hipóteses de assentos não verificadas; preservar esses bloqueios.
2. Continuar A6: integrar produtor de cenários externos em `HubExpansionRegistry.record_research()`, comprovar escopo de captura de ponta a ponta e revisar robustez numérica. A identidade nativa e a correção de reserva foram entregues no checkpoint 11.
3. Obter evidências autenticadas somente leitura dos preços de cada variante, disponibilidade e preço de rota, demanda residual, layout efetivo, tarifas, custo recorrente, inventário de hubs, cobertura e vínculo permanente aeronave–hub. Sem esses dados, não ativar os gates de compra.
4. Integrar A4/A5 e o executor conforme o roadmap, com conciliação de timeout/reinício e limites de investimento, e estender o contrato de execução para escalas quando houver suporte comprovado. Continuar A6–A9 (expansão externa, Telegram, compra de hub, interface e calibração).
5. Registrar cada entrega em `docs/ENTREGAS_ROADMAP.md`, atualizar este contexto e fazer commit e push da branch de trabalho. Na próxima conversa, leia este arquivo e continue do estado real do Git, sem repetir as correções já confirmadas.

## 9. Comandos de referência no Windows

```powershell
git status --short --branch
git log -5 --oneline --decorate
git diff --check
.\.venv\Scripts\python.exe -m ruff check src scripts tests
.\.venv\Scripts\python.exe -m pytest -q --ignore=tests/test_instalacao_linux.py
git push origin HEAD
```

O teste `tests/test_instalacao_linux.py` requer ambiente POSIX e deve ser validado no Linux/WSL conforme o registro de entregas.

## 10. Checkpoint posterior de 25/11/2026 — integração da captura A3/A4

- Base anterior: `c32f929` (`feat(autonomia): preservar identidade economica e cobertura auditada`). Branch permanece `codex/autonomia-a0-a1-20261122`; verificar o HEAD remoto/local e preservar `uv.lock` não rastreado.
- `src/audited_economics_registry.py` vincula a captura produtiva ao registro ativo antes da pesquisa. Uma nova captura válida substitui os casos e controles anteriores, mesmo sem cenários completos. O arquivo representa a captura ativa, não um histórico permanente; não confundir com o journal de investimentos.
- Validação de fingerprint, perfil, origem, versão, horário de captura e de observação. Rejeita coletas antigas, concorrentes de mesmo horário com identidade distinta, temporais inválidas e metadados divergentes dos casos; preserva registros legados sem `captured_at` e repetição idempotente. Uma captura sem `observed_at` é válida apenas como observação parcial vazia. Cobertura nunca pode ser certificada com zero casos. Escritas privadas e atômicas.
- `src/planning_cycle.py` inicializa o registro após captura produtiva e antes de avaliar a pesquisa; dry-run continua fora da publicação A3. `src/expansion_metrics.py` reconhece a captura identificada sem avaliações como `sem_avaliacoes`, com zero casos e decisão `nao_comprar`.
- A fixture de paginação agora avança o relógio a cada nova captura de conteúdo distinto e preserva repetições intencionais da mesma captura. Testes de regressão cobrem metadados temporais adulterados, cobertura vazia, casos antigos e registro posterior de caso completo.
- Validação direcionada: 56 testes aprovados (19,55 s); suíte Windows com 2.130 coletados, 2.129 aprovados e 1 ignorado, sem falhas (instalação Linux excluída); Ruff e `git diff --check` aprovados. A tentativa de delegar a auditoria independente A6 encontrou o limite de agentes do ambiente; a análise inicial está registrada no item 8.
- G0 permanece vigente. A fonte produtiva de casos econômicos completos segue pendente de disponibilidade de rota, demanda residual, configuração nativa Y/J/F, tarifas, preço final por motor, taxa de rota e custos recorrentes. Nenhuma homologação autenticada, transação ou implantação foi realizada nesta entrega.


## 11. Checkpoint de 25/11/2026 — A6, identidade econômica e integridade financeira

- Base anterior `e778291`. Branch `codex/autonomia-a0-a1-20261122`; PR #44 preservada. Confira a referência efetivamente publicada com `git log -1 --oneline` e `git ls-remote origin refs/heads/codex/autonomia-a0-a1-20261122`. O arquivo `uv.lock` permanece fora do commit.
- `src/hub_expansion.py`: identidade nativa de modelo, motor, origem, destino e escala. Escala explicitamente nula identifica rota direta; ausência ou ID inválido impede comprovação. Modelos homônimos, motores e itinerários distintos permanecem separados. Evidências contraditórias na mesma data são preservadas e bloqueiam conclusões até observação posterior; dados históricos incompletos permanecem consultáveis.
- `src/expansion_feasibility.py`: valida identidade das provas financeiras, custos, composição do preço do motor, valores finitos e consistência de escopo quando informado. Escalas permanecem bloqueadas para seleção. O investimento é comparado ao caixa disponível já líquido da reserva; o valor exigido em caixa bruto continua investimento mais reserva.
- `src/expansion_reporting.py` inclui IDs nativos na deduplicação e aplica a mesma interpretação de caixa. `src/web.py` informa o perfil ao gate de expansão. A ausência de metadados de escopo ainda é compatível com registros históricos; o vínculo obrigatório ao snapshot produtivo segue pendente.
- Validação: Ruff, compileall, 308 testes direcionados A6 e suíte Windows consolidada (2.158 testes coletados, execução concluída com código 0; instalação Linux excluída), além de git diff --check. Rollback por reversão do commit da entrega.
- Próxima ação: integrar a alimentação produtiva A3/A4 a partir de observações reais da mesma captura. Investigar `src/planning_cycle.py`, `src/research_accounting_gate.py` e `src/audited_economics_registry.py`. Registrar os motivos de bloqueio quando faltar demanda residual, layout nativo, tarifas, preço final por motor, taxa de rota, custos recorrentes ou compromissos; não promover hipóteses. Investigar o produtor A2/A6 de `record_research()`, o escopo no painel, timestamps fracionários e valores extremos do ranking.
- G0 continua vigente. Nenhuma compra real, implantação ou homologação autenticada realizada nesta entrega. As fases A0–A9 permanecem em desenvolvimento ou homologação, conforme o roadmap.

## 12. Checkpoint de 25/11/2026 — A6/A7, gate de escopo produtivo e relógio do Telegram

- Base anterior `a2b40f0`. Branch `codex/autonomia-a0-a1-20261122`, PR #44. Preservar `uv.lock` não rastreado. Consultar `git log -1 --oneline` e a referência remota para verificar o commit que contém este checkpoint.
- `src/expansion_feasibility.py`: o modo `require_snapshot_scope=True` exige perfil e identidade válida da captura no inventário, pesquisa, portfólio, cobertura geral e de cada hub, catálogo externo e cenário, custos e lucro. Registros históricos continuam consultáveis pelo contrato de análise anterior. Nenhuma fonte recebe um ID presumido. Contradições de escopo nos hubs próprios também invalidam a análise histórica.
- `src/web.py`: `hub_expansion()` obtém a identidade atual por `snapshot_summary()` (fingerprint, perfil e vigência verificados) e publica `planning_snapshot_id`. O ID é uma referência da captura, sem certificar automaticamente os dados independentes. `src/expansion_alerts.py` usa esse ID real, em vez de gerar um hash dos relatórios, aplica o mesmo gate estrito e suprime alertas sem evidência válida. A deduplicação continua baseada no conteúdo material. `src/expansion_reporting.py` evita truncar frações de segundo ao revalidar as evidências.
- Validação: 333 testes direcionados aprovados; suíte Windows com 2.161 testes coletados e código de saída 0 (instalação Linux excluída); Ruff, compileall e git diff --check aprovados. Rollback por reversão do commit da entrega. Duas auditorias independentes concluídas; uma delegação adicional retornou timeout.
- Auditoria A3/A4 (188 testes): saldo, combustível, CO₂, hangar e reserva disponíveis; preço final por motor, demanda residual, tarifas, compromissos futuros e cobertura integral pendentes. Próxima melhoria: usar saldo verificado como teto independente, sem considerar saldo suficiente como aprovação.
- Auditoria A6 (333 testes): reproduziu inclusão de hub próprio no ranking externo, candidato vencido/preço conflitante, timestamp futuro que impede recuperação, investimento zero, perda de custos excluídos, divergência de limites numéricos e duplicidades no Top 3; também identificou divergência de pontos entre candidato e composição de custos. Corrigir em entrega independente com regressões.
- Retomada prioritária A3/A4: localizar fontes nativas efetivas de checkout (preço final e variante), disponibilidade, layout, tarifas, demanda residual, custos recorrentes e compromissos financeiros. O registro econômico ainda não possui produtor de casos completos. O worker deve ser o único produtor de evidência, e o replay/painel continuam somente leitura. Investigar os produtores de `AuditedEconomicsRegistry.record()`, `record_portfolio_evidence()` e `HubExpansionRegistry.record_research()`, vincular as fontes no momento da coleta e manter a cobertura parcial até prova integral. Não preencher evidências ausentes nem promover registros legados. A6 exige essa associação para habilitar recomendações; a atual falta de produtores continua bloqueando conclusões positivas.
- G0 vigente. Nenhuma compra real, homologação autenticada, promoção para main ou implantação nesta entrega. Registrar resultados, limites, rollback e próximo checkpoint em todos os três documentos e publicar a branch de trabalho.

## 13. Checkpoint de 25/11/2026 — A6/A7/A8, integridade econômica

- Base anterior: `b8d9d42`. Branch `codex/autonomia-a0-a1-20261122`, PR #44. Verificar HEAD e referência remota; preservar `uv.lock` não rastreado.
- `src/hub_expansion.py`, `src/expansion_feasibility.py` e `src/expansion_reporting.py`: limite financeiro uniforme de 10^15, consistência monetária, rejeição de hubs próprios e IDs duplicados, conflito de preços/pontos, frescor e recuperação de observações futuras. Preservação das exclusões de despesas recorrentes em todas as provas, com projeções condicionais inelegíveis para compra. O gate produtivo exige declaração explícita no cenário ou lucro. O painel PT/EN e o Telegram exibem as ressalvas; alterações materiais nas exclusões geram atualização.
- Validação: 375 testes direcionados e 2.192 aprovados na suíte Windows consolidada, 1 ignorado (134,67 s, instalação Linux excluída); Ruff, compileall e git diff --check aprovados. Rollback por reversão do commit. G0 vigente, sem compra, homologação autenticada ou implantação.
- Próxima frente A3/A4: aplicar teto financeiro independente antes do ranking global, usando saldo autenticado da captura e observação viva verificável como fontes distintas. A escolha atual precede `_current_audited_finance_blockers()` em `WebDashboard.audited_expansion()`. Preservar validação posterior, divergência A3/observação viva, reservas e compromissos sem desconto duplo. Saldo maior não aumenta orçamento auditado; saldo ausente ou divergente não certifica elegibilidade. Revisar `src/portfolio_planner.py`, `src/web.py`, `src/audited_game_snapshot.py`, `src/dashboard.py` e seus testes.
- Continuar integração produtiva de `AuditedEconomicsRegistry.record()`, `record_portfolio_evidence()` e `HubExpansionRegistry.record_research()` no worker. Evidências reais ainda pendentes: preço final por motor, disponibilidade e demanda residual, layout Y/J/F, tarifas, taxa da rota, despesas recorrentes, compromissos financeiros futuros, cobertura de hubs e vínculo permanente aeronave–hub. Painel e replay somente leitura; sem cobertura integral, manter decisão inconclusiva.

## 14. Checkpoint de 25/11/2026 — A3/A4, teto financeiro independente

- Base anterior `bd18259`; branch `codex/autonomia-a0-a1-20261122`, PR #44. Conferir HEAD local/remoto e preservar `uv.lock` não rastreado. G0 continua vigente.
- `src/audited_game_snapshot.py` publica prova do saldo bruto vinculada à captura, com montante inteiro não negativo e observação válida, não posterior à coleta. `src/portfolio_planner.py` exige, no fluxo produtivo, saldo capturado e saldo vivo recente, com identidade e ordem temporal consistentes. O menor dos três saldos brutos (A3, captura, vivo) limita as alternativas antes da normalização e ranking. Deduz compromissos e reserva uma única vez; respeita também os tetos por ciclo, período e diário local. Saldo independente maior não amplia o orçamento A3; ausência de evidência mantém orçamento desconhecido e divergência bloqueia decisão conclusiva.
- `src/web.py` fornece as leituras ao planejador e revalida o saldo antes de criar a prévia. Rejeita tipos inválidos, divergências e regressão temporal frente às provas anteriores. `assets/web/index.html` mostra três saldos, teto bruto e orçamento líquido em PT/EN mesmo sem alternativas A4; zero e valor não confirmado ficam distintos, e o ranking bloqueado é apresentado como diagnóstico.
- Validação direcionada: 159 testes aprovados, Ruff, compileall e git diff --check aprovados. Suíte Windows consolidada após as alterações de interface e revalidação: 2.194 aprovados e 1 ignorado (131,99 s; instalação Linux excluída). Homologação autenticada e instalação Linux continuam pendentes. Nenhuma transação real ou implantação executada. Rollback por reversão do commit desta entrega.
- Próxima frente: a inspeção de `src/planning_cycle.py` confirma que `_research_summary()` percorre somente avaliações bloqueadas e hipóteses de layouts; `src/research_accounting_gate.py` monta provas parciais, mantendo disponibilidade, demanda residual, confirmação nativa de layout e viabilidade desconhecidas. Conectar produtores produtivos às fontes reais, revisar `src/native_route_quotes.py` e as observações de checkout, preservando a identidade da captura e sem publicar hipóteses como provas. Não certifica cobertura a partir de amostras. A tentativa de delegar uma auditoria adicional retornou `agent thread limit reached`.

## 15. Checkpoint de 25/11/2026 — A6, captura auditada da pesquisa externa

- Base anterior `d0583e8`; branch `codex/autonomia-a0-a1-20261122`, PR #44. G0 vigente. Preservar `uv.lock` não rastreado.
- O patch pendente de `src/audited_game_snapshot.py` foi finalizado: `capture_game_snapshot()` usa os registros externos existentes do perfil e incorpora `external_route_research` antes do fingerprint. Exige propriedade vigente, catálogo `game_purchase_catalog`, escopo `external_catalog`, IDs não ambíguos, origem e destino válidos, amostras nativas com demanda válida e horários vigentes. Exclui hubs já próprios. Preço e pontos têm relógios independentes; valores ausentes, vencidos, conflitantes ou futuros não são renovados por outras leituras. O resumo expõe somente contagens atuais, cobertura parcial e inelegibilidade para compra. Capturas anteriores continuam válidas. O diagnóstico não certifica pesquisa completa nem prova econômica.
- Testes: suíte Windows com 2.199 coletados, 2.198 aprovados e 1 ignorado (instalação Linux excluída). Após proteção contra overflow de timestamp, `tests/test_audited_game_snapshot.py` e `tests/test_hub_expansion.py`, 118 aprovados. Ruff, compileall e `git diff --check` aprovados. Homologação autenticada e instalação POSIX pendentes. Rollback por reversão do commit desta entrega.
- Próximas ações: (1) obter fontes nativas conclusivas para preço final modelo+motor+hub, layout efetivamente aplicável, disponibilidade de rota, demanda residual, tarifas, taxas e custos recorrentes incrementais; manter o checkout com `price_verified=False` enquanto a semântica do preço não for comprovada, sem acionar Order ou Configuration; (2) integrar casos A3 completos ao `AuditedEconomicsRegistry.record()` no worker proprietário da sessão, vinculado à captura; (3) conciliar compromissos financeiros e cobertura de A4; (4) consumir o bloco `external_route_research` na avaliação A6 e integrar cenários completos a `HubExpansionRegistry.record_research()`, sem misturar registros independentes nem presumir esgotamento interno; (5) seguir as etapas restantes A5–A9, critérios de homologação e gates do roadmap. O painel de pesquisa externa ainda consulta registros independentes. O objetivo de autonomia total permanece ativo e incompleto.

## 16. Checkpoint de 25/11/2026 — A6, replay da captura auditada

- Base anterior `002a941`; branch `codex/autonomia-a0-a1-20261122`. Preservar `uv.lock` não rastreado e verificar HEAD local/remoto. A referência `refs/pull/44/head` estava em `33d081b` antes desta entrega, divergente da branch de trabalho; verificar a associação da PR antes de qualquer promoção.
- O worker captura a reserva operacional junto das evidências; `replay_external_research_page()` valida perfil, fingerprint e vigência e reconstrói as entradas da pesquisa externa sem consultar registros vivos. Diferentemente do replay histórico interno, a análise externa reavalia vigência com o relógio atual. O cursor incorpora ID da captura e fingerprint da fila; alterações de evidências ou da captura provocam reinício. Mantém preço e pontos independentes, zero observado, saldo capturado e orçamento anterior aos compromissos. A pesquisa externa permanece parcial e inelegível para compra.
- `WebDashboard.external_hub_research()` delega ao replay; o GET mantém seus parâmetros. A UI PT/EN limpa os resultados e desabilita a paginação quando a captura está indisponível. Não há fallback para registros independentes. Testes cobrem a expiração com itens efetivamente presentes, mudança de cursor, ausência, captura legada, adulteração, reserva auditada anterior e isolamento por perfil.
- Validação direcionada final: 222 aprovados, incluindo testes de interface JavaScript; suíte Windows consolidada: 2.200 aprovados e 1 ignorado (138,41 s; instalação Linux excluída). Ruff, compileall e git diff --check aprovados. G0 vigente, sem transação ou implantação. Homologação autenticada e instalação Linux pendentes. Rollback por reversão do commit desta entrega.
- Próxima frente: concluir produção de evidências nativas A3/A4, com preço final modelo/motor/hub, layout Y/J/F, disponibilidade, demanda residual, tarifas, taxa de rota e despesas recorrentes. `planning_cycle._research_summary()` ainda agrega somente avaliações bloqueadas, `research_accounting_gate` registra provas parciais e `native_route_quotes` referencia aeronaves existentes, sem provar tarifas/taxas de aeronaves futuras. Vincular casos completos ao `AuditedEconomicsRegistry.record()` e cobertura ao `record_portfolio_evidence()` no worker proprietário. Para A6, construir cenário externo com custos próprios de aquisição do hub e fontes completas, gravá-lo via `HubExpansionRegistry.record_research()` e demonstrar esgotamento interno. Continuar A5–A9 e homologação do roadmap. O objetivo global permanece ativo, sem autorização de compras reais.

## 17. Checkpoint de 25/11/2026 — A1, A6 e persistência do contexto

- Base `e355bd3` na branch `codex/autonomia-a0-a1-20261122`. G0 vigente. PR #44 e arquivos locais `uv.lock` e `docs/codex_multipart_commit.md` preservados. O apêndice bruto duplicado foi removido daqui após conferir a equivalência com o arquivo multiparte separado.
- A1 reabre o painel do modelo e revalida `#accountLow` após duas leituras do preço final. Regressão reproduzida sem clique de compra. Na evidência registrada, o A320-200 mudou de velocidade e consumo conforme a variante sem mudar `#acCost`; a amostra do A380-800 não expôs uma fonte explícita de preço final. A prova por modelo, motor e hub continua pendente.
- A6 deriva `owned_inventory` do snapshot auditado e compartilha a prova com replay, painel e Telegram. A validação exige perfil, origem, IDs únicos e observações vigentes. Divergência entre inventários vigentes invalida a prova e exclui da lista diagnóstica os hubs de ambos. Inventário vivo vencido não invalida propriedade capturada e vigente. O escopo de frota segue parcial.
- Validação: 176 testes direcionados A1 e 433 testes direcionados da versão integrada A1/A6. Suíte Windows consolidada com 2.204 aprovados e 1 ignorado (134,79 s, instalação Linux excluída). Os 16 testes simulados do instalador passaram no Ubuntu via WSL. Ruff, compileall e `git diff --check` aprovados. Instalação real no servidor e homologação autenticada pendentes. Nenhuma compra ou implantação realizada. Rollback por reversão do commit da entrega.
- Próxima frente: investigar fontes nativas somente leitura de preço final efetivo por variante e hub, layout Y/J/F, disponibilidade de rota, demanda residual, tarifas, taxa de rota, custos recorrentes incrementais e vínculo permanente aeronave–hub. O produtor de casos completos A3 ainda não chama `AuditedEconomicsRegistry.record()` e a cobertura A4 ainda não chama `record_portfolio_evidence()`; `planning_cycle._research_summary()` agrega somente hipóteses e bloqueios. Vincular casos e cobertura ao snapshot no worker proprietário depois de coletar provas válidas. Para A6, alimentar `HubExpansionRegistry.record_research()` com custos externos e demonstrar esgotamento interno. Continuar A5–A9 conforme os gates. O objetivo de autonomia total continua em andamento.
