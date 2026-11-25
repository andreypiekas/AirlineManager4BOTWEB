# Contexto permanente — AirlineManager4BOTWEB

Leia este arquivo no início de cada tarefa e após toda compactação. Antes de uma compactação previsível, salve aqui o estado atual, a próxima ação e os bloqueios. Atualize o checkpoint vigente em cada entrega e registre detalhes no [histórico](ENTREGAS_ROADMAP.md). Para transferir o trabalho a outra conversa, indique apenas `docs/contexto.md`. Consulte os trechos pertinentes do [roadmap](ROADMAP_AUTONOMIA_TOTAL.md) e as entregas mais recentes.

## Objetivo e estado

- Autonomia de investimentos no Airline Manager 4. Avaliar rota, hub, aeronave, motor e layout antes de recomendar compra. Estudar hubs externos após comprovar o esgotamento das alternativas internas.
- Branch `codex/autonomia-a0-a1-20261122` com PR #46. PR #44 em `33d081b`, com referência distinta da branch. Confira o HEAD local e remoto. Preserve `uv.lock` local.
- Gate **G0**. Compras planejadas estão bloqueadas. Compra real exige homologação e autorização explícita. Preserve a compatibilidade do fluxo legado, e concilie qualquer resposta incerta antes de repetir uma operação.
- A1/A2 revalidam `#accountLow`, inventário e amostras incrementais. Em sessão autenticada, `#acCost` ficou estável nas configurações amostradas do A320-200 e do A380-800. Preço final por variante e base, vínculo permanente aeronave–hub e paginação da frota seguem sem prova.
- A3/A4 têm snapshot auditado e teto pelo menor saldo entre A3, captura e observação viva, com reserva e compromissos deduzidos uma vez. Uma consulta autenticada mostrou 50 rotas com aviso de demanda de evento e sem continuação identificada. O coletor preserva o aviso de qualquer leitura correlacionada. A projeção econômica fica bloqueada para essas amostras. Cobertura e casos completos seguem pendentes.
- A6/A7 compartilham a prova de propriedade no replay, painel e Telegram. Conflito de inventário bloqueia conclusões. Catálogo, demanda e economia de expansão ainda têm cobertura parcial. A5/A8 aguardam homologação do executor e A9 depende de observações reais para calibrar o lucro.
- Validação em 25/11/2026 com 2.205 testes aprovados e 1 ignorado no Windows. A base anterior passou em 16 testes simulados do instalador no Ubuntu via WSL. Homologação integral e instalação real no servidor pendentes.

## Próxima ação

1. Coletar evidências autenticadas somente leitura com um único proprietário da sessão por perfil. Verificar preço final por modelo, motor e hub de entrega, vínculo permanente aeronave–hub e paginação. Obter layout Y/J/F, disponibilidade, demanda residual fora de evento, tarifas, taxa de rota e custos incrementais. Registrar origem, vigência e cobertura. Preço sem prova permanece com `price_verified=false`.
2. No worker (`src/planning_cycle.py`), vincular as provas ao mesmo snapshot via `AuditedEconomicsRegistry.record()` e `record_portfolio_evidence()`. Preservar hipóteses e observações incompletas como parciais. Respeitar os IDs nativos e a identidade da escala.
3. Completar o cenário externo com `HubExpansionRegistry.record_research()`, custos próprios de expansão e prova de esgotamento interno. Seguir a seção 10 do roadmap e os gates G0–G5 para recomendações, simulação e execução.

## Histórico e arquivos

- Os checkpoints anteriores estão no [histórico de entregas](ENTREGAS_ROADMAP.md) e na revisão `8fdab91` deste arquivo no Git.
- O [índice multiparte](codex_multipart_commit.md) aponta para o arquivo bruto compactado localmente. Consulte o índice quando necessário e deixe o bruto fora do contexto da conversa.
- Antes de editar, confira branch, status e diff. Trabalhe na branch de tarefa, registre resultados e limitações, faça commit e push. Merge em `main` e implantação dependem de autorização explícita.
