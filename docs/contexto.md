# Contexto permanente — AirlineManager4BOTWEB

Leia este arquivo no início de cada tarefa e após toda compactação. Antes de uma compactação previsível, salve aqui o estado atual, a próxima ação e os bloqueios. Atualize o checkpoint vigente em cada entrega e registre detalhes no [histórico](ENTREGAS_ROADMAP.md). Para transferir o trabalho a outra conversa, indique apenas `docs/contexto.md`. Consulte os trechos pertinentes do [roadmap](ROADMAP_AUTONOMIA_TOTAL.md) e as entregas mais recentes.

## Objetivo e estado

- Autonomia de investimentos no Airline Manager 4. Avaliar rota, hub, aeronave, motor e layout antes de recomendar compra. Estudar hubs externos após comprovar o esgotamento das alternativas internas.
- Branches permanentes `main` e `codex/autonomia-a0-a1-20261122`. Desenvolva na segunda, acompanhada pela PR #46. A PR #44 em `33d081b` é referência histórica para a promoção de hubs. O [histórico](ENTREGAS_ROADMAP.md) registra a recuperação das branches arquivadas. Preserve `uv.lock` local e o trabalho ainda aberto em `AirlineManager4BOTWEB-a3-route`.
- Gate **G0**. Compras planejadas estão bloqueadas. Compra real exige homologação e autorização explícita. Preserve a compatibilidade do fluxo legado, e concilie qualquer resposta incerta antes de repetir uma operação.
- A1/A2 revalidam `#accountLow`, inventário e amostras incrementais. Em sessão autenticada, `#acCost` ficou estável nas configurações amostradas do A320-200 e do A380-800. Preço final por variante e base, vínculo permanente aeronave–hub e paginação da frota seguem sem prova.
- A3/A4 têm snapshot auditado e teto pelo menor saldo entre A3, captura e observação viva, com reserva e compromissos deduzidos uma vez. A PR #47 reforçou a validade da evidência, a cobertura verificável e o checkout do preço final. Uma consulta autenticada mostrou 50 rotas com aviso de demanda de evento e sem continuação identificada. O coletor preserva o aviso de qualquer leitura correlacionada. A projeção econômica fica bloqueada para essas amostras. Cobertura e casos completos seguem pendentes.
- A6/A7 compartilham a prova de propriedade no replay, painel e Telegram. Conflito de inventário bloqueia conclusões. Catálogo, demanda e economia de expansão têm cobertura parcial. A5 incorporou proteções para recuperar a execução simulada. A5/A8 aguardam homologação do executor e A9 depende de observações reais para calibrar o lucro.
- Validação da consolidação em 25/11/2026 com suíte Windows, casos adicionais de expiração e 16 testes simulados do instalador no Ubuntu via WSL. Homologação integral e instalação real no servidor pendentes.
- Último checkpoint de trabalho. A revisão A3/A4 e A6/A7 localizou a composição do snapshot em `src/audited_game_snapshot.py`, o registro A3/A4 em `src/audited_economics_registry.py`, a fila de pesquisa própria em `src/owned_hub_research_ingestion.py` e o registro externo em `src/hub_expansion.py`. Os 228 testes direcionados passaram. Retome pela integração no worker e use fixtures onde faltarem dados autenticados, preservando os bloqueios do G0.

## Próxima ação

1. Coletar evidências autenticadas somente leitura com um único proprietário da sessão por perfil. Verificar preço final por modelo, motor e hub de entrega, vínculo permanente aeronave–hub e paginação. Obter layout Y/J/F, disponibilidade, demanda residual fora de evento, tarifas, taxa de rota e custos incrementais. Registrar origem, vigência e cobertura. Preço sem prova permanece com `price_verified=false`.
2. No worker (`src/planning_cycle.py`), vincular as provas ao mesmo snapshot via `AuditedEconomicsRegistry.record()` e `record_portfolio_evidence()`. Preservar hipóteses e observações incompletas como parciais. Respeitar os IDs nativos e a identidade da escala.
3. Completar o cenário externo com `HubExpansionRegistry.record_research()`, custos próprios de expansão e prova de esgotamento interno. Seguir a seção 10 do roadmap e os gates G0–G5 para recomendações, simulação e execução.

## Histórico e arquivos

- Os checkpoints anteriores estão no [histórico de entregas](ENTREGAS_ROADMAP.md) e na revisão `8fdab91` deste arquivo no Git.
- O [índice multiparte](codex_multipart_commit.md) aponta para o arquivo bruto compactado localmente. O Codex Cloud consegue retomar pela branch de desenvolvimento apenas com os documentos versionados. Se o bruto estiver ausente, siga normalmente. Faça a transição de conversa pelo caminho deste arquivo, sem copiar seu conteúdo, o histórico ou o multipart para o chat.
- No launcher local Codex Web GPT 6.2.0, deixe **Settings → Bigger Context (experimental)** desativado. Essa opção gera o envio em partes que pode falhar por tamanho no `<codex_multipart_commit>`. Após mudar a opção, reinicie o Codex para atualizar o catálogo e retome em uma conversa nova na branch de desenvolvimento com `Leia docs/contexto.md e continue a próxima ação do roadmap.` O Codex Cloud também pode retomar com essa mesma instrução.
- Antes de editar, confira branch, status e diff. Trabalhe na branch de tarefa, registre resultados e limitações, faça commit e push. Merge em `main` e implantação dependem de autorização explícita.
