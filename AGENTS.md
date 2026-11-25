# Instruções do repositório

Antes de iniciar qualquer tarefa ou nova conversa neste repositório, leia integralmente `docs/contexto.md`. Depois consulte `docs/ROADMAP_AUTONOMIA_TOTAL.md` e as entregas mais recentes em `docs/ENTREGAS_ROADMAP.md`.

Durante tarefas longas, atualize `docs/contexto.md` nos checkpoints e antes de uma compactação que puder antecipar. Após compactação ou retomada, releia o arquivo antes de continuar. Ao encaminhar o trabalho para outra conversa, indique esse arquivo como ponto de partida. Use `docs/codex_multipart_commit.md` como índice multiparte. Preserve o histórico bruto em `docs/codex_multipart_commit.raw.md.gz`, ignorado pelo Git. Mantenha o contexto de trabalho focado no estado atual e na próxima ação. Consulte trechos do histórico sob demanda.

- Preserve o estado atual do repositório e confira branch, `git status` e `git diff` antes de editar.
- Ao final de cada interação com alterações, crie um commit e envie a branch de trabalho ao GitHub.
- Não desenvolva diretamente em `main`, não faça merge para `main` e não implante em produção sem autorização explícita.
- Não execute compras reais no jogo sem homologação e autorização explícitas, respeitando os gates do roadmap.
- Registre implementação, testes, limitações e homologação em `docs/ENTREGAS_ROADMAP.md` e atualize `docs/contexto.md` para a próxima conversa.
