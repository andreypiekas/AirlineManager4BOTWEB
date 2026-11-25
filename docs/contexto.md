# Contexto permanente — AirlineManager4BOTWEB

> Leia este arquivo no início de cada nova conversa ou retomada do projeto. Em seguida, leia `docs/ROADMAP_AUTONOMIA_TOTAL.md` e consulte o início de `docs/ENTREGAS_ROADMAP.md` para identificar as entregas mais recentes. Antes de editar, confira `git status`, branch e último commit. Preserve todas as alterações existentes.

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
