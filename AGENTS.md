# Instruções do repositório

Antes de iniciar qualquer tarefa ou nova conversa neste repositório, leia integralmente `docs/contexto.md`. Depois consulte as seções pertinentes de `docs/ROADMAP_AUTONOMIA_TOTAL.md` e as primeiras entradas de `docs/ENTREGAS_ROADMAP.md`. Busque outras seções pelo título conforme a tarefa avançar.

Durante tarefas longas, atualize `docs/contexto.md` nos checkpoints e antes de uma compactação que puder antecipar. Após compactação ou retomada, releia o arquivo antes de continuar. Ao encaminhar o trabalho para outra conversa, indique apenas esse arquivo como ponto de partida. Mantenha o contexto de trabalho focado no estado atual e na próxima ação.

Use `docs/codex_multipart_commit.md` como índice multiparte. O histórico bruto é um arquivo local opcional, ignorado pelo Git. Quando ele estiver ausente no Codex Cloud, prossiga com os arquivos versionados. Nunca cole, anexe, gere em mensagens ou divida em várias mensagens o contexto completo, o histórico ou o multipart. Informe apenas o checkpoint, os resultados, os caminhos relevantes e eventuais bloqueios.

- Preserve o estado atual do repositório e confira branch, `git status` e `git diff` antes de editar.
- Ao final de cada interação com alterações, crie um commit e envie a branch de trabalho ao GitHub.
- Não desenvolva diretamente em `main`, não faça merge para `main` e não implante em produção sem autorização explícita.
- Não execute compras reais no jogo sem homologação e autorização explícitas, respeitando os gates do roadmap.
- Registre implementação, testes, limitações e homologação em `docs/ENTREGAS_ROADMAP.md` e atualize `docs/contexto.md` para a próxima conversa.
