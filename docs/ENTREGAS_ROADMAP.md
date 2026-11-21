# Histórico de entregas do roadmap

## 2026-11-21 — Confiabilidade financeira e cobertura do inventário de hubs

**Roadmap:** `docs/ROADMAP_HUBS_AERONAVES.md`, etapas 2, 3 e 4 (avanço incremental).

### Implementado

- Inventário de bases agora valida a idade de cada estimativa de lucro: apenas a rota atual, com chave correspondente, valor numérico finito e leitura dos últimos três dias entra no agregado. Estimativas antigas, sem data, futuras ou inválidas ficam pendentes e não inflam o total.
- API `GET /api/hubs` expõe `known_aircraft` e `last_fleet_scan` como indicadores da cobertura local, mantendo `partial_fleet` verdadeiro porque o jogo apresenta apenas parte da frota por página. Cada base expõe `estimates_pending`.
- O catálogo parcial de hubs compráveis preserva `observed_at` individual dos aeroportos já vistos. Atualizar uma página renova apenas os aeroportos efetivamente observados nela; os demais continuam envelhecendo. Há leitura compatível para arquivos de catálogo gerados antes dessa mudança.
- A classificação financeira considera a validade temporal do catálogo **por candidato**. A atualização completa remove candidatos ausentes e preserva cenários de pesquisa anteriormente confirmados, sujeitos à validade de sua própria data.
- A API de expansão verifica o saldo no jogo ou no histórico financeiro local com idade máxima de 15 minutos. Um valor antigo ainda pode ser consultado no painel geral, mas faz a viabilidade financeira permanecer `dados_a_confirmar`. `cash_observed_at` informa quando o saldo usado foi conferido.
- A interface **Hubs e Aeronaves** ganhou pesquisa por código, aeroporto, matrícula e modelo, agrupamento de métricas e detalhe expansível das rotas. Apresenta o tamanho do cadastro conhecido, a última página auditada, o número de rotas reconhecidas e estimativas ainda pendentes.
- A interface **Novos hubs** ganhou busca e filtro por situação financeira, detalhamento dos custos da aeronave, hub, rota e hangar, e horários de pesquisa por candidato. Os componentes receberam traduções, controles acessíveis e adaptação para largura reduzida.
- O teste de sintaxe JavaScript do painel passa a validar arquivo temporário com limite de tempo, eliminando o travamento observado no Windows ao usar `node --check -` por stdin.
- Foram adicionados testes para estimativas vencidas, valores inválidos, cobertura parcial, atualizações de catálogo parciais e completas, legado sem horário por aeroporto e validade do saldo.

### Limites e próximas validações

- Os vínculos individuais `home_hub_id` seguem dependendo de prova explícita do jogo; as pontas da rota e o sinal de aeronave estacionada não comprovam sua base de origem.
- Não houve coleta autenticada de novas bases, preços ou demanda nesta etapa. A origem HTML do catálogo de compras e a leitura paginada das aeronaves precisam de validação com a sessão do jogo.
- A validação visual com navegador, tamanhos de tela reais e sessão autenticada permanece pendente. Os componentes funcionam com os contratos de API existentes e não emitem operações de compra.
- Estimativas financeiras de rota excluem reparos e A-check, conforme o modelo do roadmap.

### Validação

- Testes de inventário de hubs, cenários, saldo, rotas e JavaScript executados com sucesso no Windows.
- A suíte `pytest tests -q --ignore=tests/test_instalacao_linux.py` concluiu com sucesso, incluindo o teste sintático JavaScript em arquivo temporário. O teste de instalação específico de Linux exige ambiente POSIX e permanece para homologação nesse sistema.
- `git diff --check` e compilação Python executados sem erros antes do envio ao GitHub.

## 2026-11-21 — Cenários verificáveis para novos hubs

**Roadmap:** `docs/ROADMAP_HUBS_AERONAVES.md`, etapa 3 (estrutura parcial).

### Implementado

- Novo `src/hub_expansion.py` para registrar, por perfil, um catálogo de aeroportos compráveis com prova de origem `game_purchase_catalog`. Leitura parcial preserva aeroportos de páginas anteriores, e leitura completa substitui o catálogo.
- Cadastro explícito de um cenário por aeroporto, identificado como `game_research`. Exige modelo, rota, prova de demanda e viabilidade, preço do hub, aeronave, taxa de rota e hangar para tornar uma avaliação elegível. Informações ausentes não recebem valores hipotéticos.
- Cálculo de investimento inicial, lucro operacional diário informado pelo cenário, prazo de retorno e disponibilidade financeira acima da reserva. Valores negativos indicam cenário sem lucro, e candidatos acima do caixa são sinalizados.
- Desconsideradas observações com mais de três dias para classificação de viabilidade. Hubs já adquiridos ficam excluídos da lista de compras.
- Nova API autenticada `GET /api/hubs/expansion`, usando o último saldo conhecido, e seção **Novos hubs** na tela de bases com disponibilidade, investimento, retorno e pendências.
- Adicionados cinco testes direcionados em `tests/test_hub_expansion.py`.

### Pendente para homologação real

- Identificar e integrar os elementos da página de compra de hubs e pesquisa de demanda em uma sessão autenticada do jogo. **Nenhuma leitura real de catálogo ou cenário foi realizada nesta entrega.** A API inicia com `Disponibilidade de compra a verificar` até existir observação comprovada.
- Provar o vínculo individual de base para aeronaves, coletar dados das demais páginas da frota e aplicar estimativas de rotas de `route_optimizer.py` aos cenários conferidos no jogo.
- Conferir exibição desktop/celular e consistência do saldo contra uma sessão real. As projeções não incluem reparos ou A-check.

### Validação

- Testes direcionados de cenários, inventário de hubs e configuração visual executados no Windows.
- Código Python compilado e JavaScript da interface verificado separadamente.

## 2026-11-21 — Inventário de hubs, primeira integração

**Roadmap:** `docs/ROADMAP_HUBS_AERONAVES.md`, etapas 1 e 2 (parciais).

### Implementado

- Criado `src/hub_registry.py` para persistir por perfil a última lista não vazia de hubs lida do seletor `#hubSelect` do jogo. São armazenados ID do jogo, nome, código, origem da informação e horário de leitura. Opções sem ID válido e placeholders são ignorados.
- Integrada a captura às consultas de pesquisa de rotas já realizadas pelo bot. A ausência do seletor não apaga as bases previamente identificadas.
- Criada API autenticada de consulta `GET /api/hubs`, sem chamadas adicionais ao navegador do jogo.
- Adicionada a tela **Hubs e Aeronaves** com cartões por base, inclusive bases vazias, estado da última leitura, estimativas e relação das aeronaves com vínculo ainda desconhecido. Funciona com o cadastro local existente e em telas menores.
- Estimativas de lucro passam a registrar a chave da rota e o horário do cálculo. Ao substituir a rota sem nova estimativa, valores anteriores são descartados. Estimativas antigas sem chave correspondente ficam fora do inventário.
- Adicionados testes de captura conservadora, base vazia, ausência de atribuição presumida, invalidação de lucro e rota HTTP.

### Critérios ainda pendentes

- Confirmar em sessão autenticada, com exemplos reais, a cobertura do seletor `#hubSelect` para todas as bases adquiridas e descobrir um campo confiável para a **base de origem individual** de cada aeronave. Enquanto isso, as aeronaves ficam em **Base a confirmar**.
- Confirmar a lista de hubs compráveis e os preços de aquisição disponíveis no jogo. Criar coleta dedicada e recomendações de expansão (etapa 3).
- Adicionar leitura paginada de cobertura de frota e validação visual da tela em desktop/celular com dados reais (etapas 1 e 4).
- Para formar lucro diário por base é necessário confirmar o vínculo individual e revisar validade temporal das estimativas de cada rota.

### Validação

- **27 testes direcionados passaram**, incluindo inventário, registro de rotas, interface, cobertura de traduções e leitura de rotas ICAO/IATA.
- A sintaxe JavaScript do painel passou por `node --check`, e o código Python compilou com `compileall`.
- A execução da suíte integral no Windows foi interrompida após detectar falha em `tests/test_instalacao_linux.py::test_nova_instalacao_eh_simulacao_e_privada` por exigir permissões POSIX `0600` em arquivo Windows. A suíte integral permanece pendente de validação em ambiente Linux.
- A verificação com dados reais depende da sessão autenticada do jogo.
