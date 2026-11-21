# Histórico de entregas do roadmap

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
