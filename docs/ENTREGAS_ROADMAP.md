# Histórico de entregas do roadmap

## 2026-11-24 — Autonomia Total A1/A2/A7, cobertura independente dos hubs de entrega (G0)

- A leitura autenticada do gerenciamento `hubs.php` encontrou 30 linhas com o manipulador nativo de consulta `hub_details.php`, todas com IDs únicos. O conjunto coincide integralmente com as 30 opções do formulário de entrega e não possui IDs em comum com o seletor de aeroportos da pesquisa. A inspeção do detalhe de um hub revelou o nome com país, mas não uma associação explícita entre os dois namespaces. A camada de mapa inspecionada também não forneceu essa associação. Nenhuma ação de alteração, abandono ou compra foi acionada.
- O ciclo de planejamento ganhou um coletor independente e somente leitura. Ele consulta o gerenciamento antes e depois de abrir um modelo de aeronave, com leituras duplas estáveis, identidade explícita do modelo, ausência de carregamento e janela máxima de 120 segundos. Conjuntos duplicados, mudanças no inventário ou seletores incompletos invalidam a observação. A cobertura distingue conjuntos coincidentes e divergentes e contabiliza opções desabilitadas.
- O registro por perfil guarda apenas contagens agregadas, expira em até 15 minutos e é revogado antes de nova tentativa. A API `/api/hubs` e o painel PT/EN exibem a cobertura sem publicar IDs de entrega. A igualdade dos conjuntos gerenciados e de entrega não certifica a correspondência individual com o aeroporto de pesquisa, a disponibilidade de cada entrega ou a base permanente da aeronave. O pré-checkout continua exigindo evidência independente dessa correspondência, e G0 permanece ativo.
- Validação Windows: 130 testes direcionados aprovados, incluindo execução JavaScript do contrato DOM sintético, diferenças de conjunto, opções desabilitadas, ausência de IDs persistidos, expiração, isolamento por perfil, revogação e pré-checkout. Ruff, compilação Python e `git diff --check` aprovados. A execução integrada do coletor Selenium em sessão autenticada permanece pendente.

## 2026-11-24 — Autonomia Total A1/A2/A5, identidade do aeroporto e da entrega (G0)

- A comparação autenticada dos seletores `#hubSelect` (pesquisa) e `#hubSelection` (encomenda de A380-800) encontrou 30 opções em cada um, zero IDs iguais e zero rótulos textuais exatamente iguais entre os conjuntos. A pesquisa inclui país no rótulo; o formulário de encomenda usa outra representação. O seletor da pesquisa só expôs o atributo `value` nas opções. A relação individual não foi comprovada; quantidade, ordem e semelhança do nome não constituem prova de correspondência.
- O pré-checkout separa o aeroporto do planejamento e o identificador de entrega. Exige uma correspondência explícita de fonte independente, vinculada ao perfil e ao snapshot, com validade máxima de 120 segundos e relações unívocas. Ausência, expiração, conflito, origem simulada em operação real ou seleção divergente bloqueiam a validação. A simulação também utiliza IDs de namespaces distintos e evidência explícita.
- A navegação adicional não revelou uma relação nativa explícita; a leitura do gerenciamento de bases adquiridas permanece pendente. Os nomes das fontes de correspondência definem o contrato para uma futura coleta homologada. Nenhum vínculo real foi inferido, nenhum ID de entrega da conta foi registrado nesta documentação e nenhuma encomenda foi realizada. A execução planejada permanece indisponível em G0.
- Validação Windows: 131 testes direcionados aprovados, incluindo pré-checkout, divergência, correspondência ausente/ambígua/vencida, isolamento por perfil e snapshot, simulação de execução e expansão em duas etapas. Ruff, compilação Python e `git diff --check` aprovados.

## 2026-11-24 — Autonomia Total A1/A5, identidade do checkout e seletor de entrega (G0)

- No detalhe autenticado do A380-800 (modelo 2), o painel não possuía `data-model-id`, mas continha a declaração nativa `acId`. Foram observadas 30 opções de entrega, uma única selecionada. A troca reversível entre as duas primeiras opções preservou o ID do modelo, a variante 7 e o preço exibido de US$ 215.629.503. A seleção inicial foi restaurada.
- O diagnóstico de checkout e o coletor passaram a compartilhar a leitura da identidade nativa do detalhe. IDs conflitantes invalidam a correlação. O diagnóstico também distingue o botão `#btnPurchaseIntroA`, observado no formulário autenticado, de `#btnPurchaseIntro`, que não estava presente nessa tela.
- O preço de `#acCost` continua sendo apenas o valor exibido: o formulário observado não tinha atributos `data-final-price` ou `data-total-price`. A seleção reversível de entrega não comprova a aquisição, o preço final ou a disponibilidade de hangar. A execução planejada permanece bloqueada pelo gate G0. Nenhum botão de encomenda foi acionado. A homologação do coletor Selenium integrado continua pendente.
- Validação Windows: 193 testes de diagnóstico, detalhe e catálogo de motores e 79 testes de observações e seleção do hub aprovados. Ruff, compilação Python e `git diff --check` aprovados.

## 2026-11-24 — Autonomia Total A1/A3/A7, emissão de CO₂ por variante (G0)

- Em sessão autenticada, a seleção reversível de motores do A320-200 (modelo 5, motores 9 e 10) exibiu 0,14 kg/pax/km nas duas variantes. O A380-800 (modelo 2, motores 5, 6 e 7) exibiu 0,16 kg/pax/km nas três variantes. A identidade nativa `acId` permaneceu estável em cada modelo. A fixture anonimizada registra também as velocidades e consumos distintos das cinco variantes.
- O coletor aceita a emissão apenas com unidade explícita `kg/pax/km`, rejeita valores inválidos ou conflitantes e preserva a métrica no detalhe por variante. A simulação exploratória utiliza o coeficiente observado com identidade correlacionada no cenário base e no stress. Na ausência dessa evidência, mantém a hipótese de 0,18 kg/pax/km. O painel PT/EN mostra o valor e sua origem.
- O fator de combustível, os pesos por classe, as tarifas, a ocupação e as rotações continuam premissas exploratórias. A demanda residual e a fórmula operacional completa de CO₂, manutenção, A-check, outros custos recorrentes e investimento ainda exigem validação. A contribuição estimada não certifica lucro líquido, elegibilidade ou retorno de compra. G0 permanece ativo; nenhuma aquisição foi executada.
- Validação Windows: suíte ampla com 1.768 testes aprovados e 1 ignorado (excluído `tests/test_instalacao_linux.py`, requisito POSIX). Após inclusão da fixture final, 190 testes direcionados aprovados, incluindo parsing PT/EN, unidades e conflito, simulação base/stress e painel. Ruff, compilação Python e `git diff --check` aprovados.

## 2026-11-24 — Autonomia Total A1/A3, identidade da aeronave no detalhe de motores (G0)

- Em sessão autenticada, os detalhes de catálogo de A380-800, Cessna 172 e A320-200 apresentaram a declaração nativa `var acId = 2;`, `var acId = 12;` e `var acId = 5;`, respectivamente, dentro de `#acModel`. O cabeçalho do catálogo muda antes de o carregamento terminar; durante a transição observada não havia declaração no painel. O ID permaneceu correto durante as trocas reversíveis de motor do A380 e A320.
- O coletor extrai exclusivamente o identificador numérico da resposta, junto às opções e especificações da mesma leitura DOM. A dupla leitura estável continua obrigatória. Divergências entre declarações, atributo de modelo e ID solicitado invalidam a observação. Ausência de ambas as fontes mantém a identidade sem confirmação. O registro existente conserva os dados por variante e permite que as filas e o ranking usem dimensões com identidade correlacionada.
- No A380-800 foram observados GP7270 (ID 5, 964 km/h, 22,89 lbs/km), RR Trent 970 (ID 6, 917 km/h, 18,90 lbs/km) e RR Trent 972 (ID 7, 1.049 km/h, 22,26 lbs/km). Os três exibiram US$ 215.629.503 e alcance de 14.500 km. A observação confirma a associação entre o detalhe e o modelo, sem confirmar o preço final, a aquisição ou as regras econômicas do jogo. Ainda falta executar o coletor integrado em sessão autenticada e ampliar a cobertura dos modelos. G0 continua ativo.
- Validação Windows: 47 testes direcionados aprovados; suíte ampla com 1.764 testes aprovados e 1 ignorado, excluído `tests/test_instalacao_linux.py` (requisito POSIX). Ruff, compilação Python e `git diff --check` aprovados. Nenhuma compra foi realizada.

## 2026-11-24 — Autonomia Total A2/A3/A7, escalas exploratórias no ranking persistido (G0)

- O ranking de hubs próprios reconsulta o registro independente de escalas por perfil. Candidatos de pesquisa derivados exibem aeroporto intermediário, trechos e pistas quando a evidência corresponde à rota e à variante atuais. O seletor de evidência é compartilhado com as filas de hubs próprios e externos.
- A prova perde validade após expiração, atualização dos dados da rota ou do motor, nova tentativa de escala inconclusiva ou divergência entre provas atuais. A divergência entre a pista observada no detalhe direto e a pesquisa também suprime a evidência. Nenhum diagnóstico transitório é promovido a cenário de viabilidade persistido.
- A escala exploratória continua com elegibilidade de compra e regras do jogo não verificadas. O ranking mantém a pendência de confirmação dos trechos, sem atribuir rentabilidade nem emitir recomendação de compra a partir dessa observação. Permanecem pendentes a homologação autenticada da identidade dos modelos, regras de escala, custos integrais e cobertura global.
- Validação Windows: suíte ampla com 1.759 testes aprovados e 1 ignorado, excluído `tests/test_instalacao_linux.py` (POSIX). Após os ajustes finais de consistência, 212 testes direcionados aprovados, incluindo integração entre registro, ingestão, ranking, filas e interface, isolamento por variante, expiração e divergências. Ruff, compilação Python e `git diff --check` aprovados.

## 2026-11-24 — Autonomia Total A2/A3/A7, pesquisa exploratória de escalas por variante (G0)

- O ciclo de planejamento pesquisa escalas para combinações de hub, rota, modelo e motor com alcance direto insuficiente e dimensões da variante correlacionadas. A busca usa duas leituras estáveis do mapa do jogo e compara a distância direta com a pesquisa da rota antes de consultar os detalhes de cada trecho. As duas respostas de cada trecho precisam concordar, inclusive quanto à identidade dos aeroportos, unidade de pista e comprimento da pista intermediária observado pelos dois lados.
- A pesquisa fica limitada a uma combinação por escopo (hubs próprios e candidatos externos) e duas sugestões por combinação em cada ciclo. Os registros independentes por perfil e escopo alternam hubs, combinações e sugestões; novas tentativas invalidam imediatamente a evidência anterior, inclusive quando inconclusivas. A validade máxima da evidência de escala é de 15 minutos, limitada também pela validade dos dados de rota e motor.
- As filas PT/EN apresentam o aeroporto intermediário, as distâncias estimadas pelo mapa e a pista observada, com as regras do jogo ainda pendentes. A evidência é vinculada à identidade e aos dados atuais da variante e não é reutilizada para outro motor. Não altera o fluxo operacional de criação de rotas e não libera simulação econômica direta, disponibilidade, demanda residual ou elegibilidade de aquisição.
- Permanecem pendentes a homologação autenticada da leitura do mapa e dos dois detalhes, a correlação da identidade exata de modelos no formulário, a distância oficial dos trechos, regras por modo, custos e viabilidade da escala no fluxo de aquisição. O registro exploratório não certifica escala no formulário de uma aeronave futura. G0 permanece ativo.
- Validação Windows: 1.758 testes aprovados e 1 ignorado, excluído `tests/test_instalacao_linux.py` (requisito POSIX). A validação direcionada final aprovou 124 testes, incluindo filas próprias e externas, incompatibilidades de pista/alcance, identidade de motor, expiração, revogação, rodízio e apresentação em inglês. Ruff, compilação Python, execução JavaScript do coletor com mapa sintético e `git diff --check` aprovados.

## 2026-11-23 — Autonomia Total A3/A7, dimensões atuais no ranking de aquisição (G0)

- O ranking de hubs próprios reutiliza a normalização do catálogo de motores e recalcula a triagem física por modelo, motor e par de aeroportos. O painel passa a mostrar alcance e pistas, validade da evidência e pendências também nos candidatos persistidos. Um motor explicitamente indisponível com identidade confirmada ou uma dimensão observada insuficiente impede a recomendação até a confirmação correspondente.
- A leitura do painel usa o mesmo snapshot de motores no ranking e na fila de pesquisa. Para cenários verificados, o registro independente do detalhe da rota substitui a cópia eventualmente persistida; uma nova tentativa inconclusiva ou a expiração remove a prova anterior. Contagens independentes de aeronaves na rota também participam da análise de ocupação, sem apagar divergências observadas no cenário.
- A insuficiência de alcance direto admite reconciliação com uma escala já verificada, somente quando a identidade do aeroporto intermediário, os dois trechos e o comprimento da pista são compatíveis com a variante observada. A triagem dimensional não certifica as regras do jogo, demanda residual, custos ou elegibilidade de compra. Os cenários legados continuam sujeitos às provas originais de viabilidade, disponibilidade e ocupação.
- Permanecem pendentes a coleta autenticada dos dados de escala e a confirmação das regras por modo, a identidade exata dos modelos no detalhe, a cobertura integral e os custos necessários ao cálculo de rentabilidade. G0 continua ativo, sem aquisição real.
- Validação Windows: 1.748 testes aprovados e 1 ignorado, excluído `tests/test_instalacao_linux.py` (requisito POSIX). A suíte direcionada passou com 244 testes, cobrindo incompatibilidade de pista/alcance, escala, motor indisponível, identidade divergente, evidência expirada, revogação de prova e integração com o painel. Ruff, compilação Python e `git diff --check` aprovados.

## 2026-11-23 — Autonomia Total A3/A7, triagem física por variante e rota (G0)

- As filas de pesquisa de hubs próprios e externos comparam o alcance observado da variante com a distância da rota e a pista exigida com os comprimentos de origem e destino. Cada comparação tem estado independente (suficiente, insuficiente ou desconhecido). O cálculo exige identidade correlacionada do modelo e da variante e evidência atual do detalhe da rota; alcance genérico de catálogo e pista da pesquisa não substituem essas provas.
- Uma insuficiência física observada suprime a simulação econômica da rota direta. Alcance insuficiente indica necessidade de pesquisar escalas e trechos, que continuam sem homologação. A triagem é dimensional e conservadora, independentemente do modo do jogo; ainda não prova disponibilidade, viabilidade pelas regras do jogo nem elegibilidade de compra. A simulação hipotética permanece possível com dimensões desconhecidas e as pendências são exibidas.
- A API apresenta as três comparações, medidas observadas, origem e validade da evidência. O painel PT/EN mostra a triagem e sinaliza observações insuficientes. A validade da contribuição hipotética também respeita os prazos dos dados físicos e dos catálogos. A ingestão mantém a verificação física pendente no ranking persistido, sem perpetuar um diagnóstico de pista transitório.
- Permanecem pendentes a confirmação autenticada da identidade de modelo/variante, as regras de pista por modo, a disponibilidade e viabilidade de escalas, a demanda residual, a cobertura e os custos completos. Nenhuma compra foi executada. O próximo avanço é correlacionar observações físicas atuais ao ranking auditado e comprovar os dados de escalas e as regras no jogo.
- Validação Windows: suíte ampla com 1.741 aprovados e 1 ignorado, excluído `tests/test_instalacao_linux.py` (requisito POSIX). Após o ajuste final de expiração e ingestão, a suíte direcionada passou com 127 testes, incluindo alcance e pista, dados ausentes/vencidos/conflitantes, descarte de diagnóstico transitório e interface. Ruff, compilação Python e `git diff --check` aprovados.

## 2026-11-23 — Autonomia Total A1/A3/A7, especificações observadas por variante de motor (G0)

- O detalhe autenticado do A320-200 exibiu CFM56-5 (ID 10, 881 kph e 11,55 lbs/km) e IAE V2500 (ID 9, 798 kph e 10,67 lbs/km). A seleção reversível mostrou 164 pax, alcance de 5.700 km, pista de 6.500 ft, A-check de $524.690, intervalo de 360 horas e preço exibido de $6.770.196 em ambas as variantes. A fixture contém somente esses dados técnicos e não inclui informações da conta.
- O coletor combina identidade do detalhe, seleção e especificações em leituras estáveis. Pode percorrer até dez opções do seletor nativo observado, sem clicar em Order; se a seleção não provocar atualização observável das métricas, o detalhe da variante permanece pendente. Unidades inesperadas, campos duplicados, timestamps inválidos e variantes desconhecidas são rejeitados. Observações incompletas são mantidas como parciais.
- O registro por perfil persiste cada detalhe com seu próprio horário. As filas de hubs próprios e externos apresentam alcance, capacidade, velocidade, consumo, pista, preço exibido, A-check e intervalo de manutenção quando observados. Somente a identidade explicitamente correlacionada permite alimentar o cálculo exploratório com métricas do detalhe; conflito com atributos da opção invalida a evidência. O painel PT/EN sinaliza a identidade pendente e não apresenta observações vencidas.
- A leitura autenticada anterior não encontrou ID inequívoco do modelo no painel, e o preço exibido ainda não comprova o total final de checkout. Permanecem pendentes a homologação do novo coletor com o DOM real, a confirmação de outras variantes, a fórmula de manutenção, demanda residual, cobertura e demais custos. Nenhuma aquisição foi executada. O objetivo de autonomia integral continua em andamento.
- Validação Windows: suíte ampla com 1.726 aprovados e 1 ignorado (excluído o teste de instalação Linux por permissões POSIX), antes dos últimos ajustes da fila e interface. A execução direcionada final aprovou 221 testes, incluindo a fixture de variantes, divergência de seleção, persistência, fila, dados não correlacionados e apresentação em inglês. Ruff, compilação Python e verificação do diff aprovados.

## 2026-11-23 — Autonomia Total A3/A7, ocupação auditada no ranking de aeronaves (G0)

- O ranking de cenários para hubs próprios reutiliza a mesma evidência de ocupação das filas de pesquisa. Uma recomendação viável exige auditoria completa e recente da frota com zero aeronaves na rota, além de disponibilidade e demanda residual verificadas independentemente. Uma relação histórica, uma lista vazia ou uma indicação isolada de cobertura não certificam uma rota livre.
- Uma rota com ocupação positiva observada é rejeitada mesmo em uma auditoria parcial. Identidades repetidas, aeroportos conflitantes, auditoria vencida ou incompleta e divergência com contagem recente do jogo deixam a ocupação pendente. A auditoria atual completa pode substituir relações históricas de aeronaves que já saíram da rota.
- A API retorna a contagem da frota própria e a validade da evidência por candidato. O painel PT/EN exibe a contagem auditada ou o mínimo observado e traduz as pendências. O ranking recalcula ocupação a cada consulta, sem promover as observações exploratórias a cenários verificados.
- Permanecem pendentes homologação autenticada, obtenção de demanda residual e custos completos, identidade do modelo no detalhe dos motores e integração das evidências ao planejamento global auditado. G0 permanece ativo, sem execução de aquisição.
- Validação Windows: 1.718 testes aprovados e 1 ignorado pela própria suíte, excluindo `tests/test_instalacao_linux.py` (permissões POSIX). A validação direcionada aprovou 222 testes, incluindo auditorias incompletas, relações históricas, aliases e identidades conflitantes. A revisão final da interface PT/EN passou nos 9 testes do painel. Ruff, compilação Python e `git diff --check` aprovados.

## 2026-11-23 — Autonomia Total A2/A3/A7, ocupação de rotas pela frota própria (G0)

- As pesquisas de hubs próprios e externos cruzam as combinações de aeroportos com o roster atual e as relações de rotas da frota do perfil. O par de aeroportos é independente do sentido da rota e admite códigos IATA/ICAO resolvidos de forma inequívoca. Identidades conflitantes, relações vencidas ou aeronaves duplicadas impedem a certificação de ausência de ocupação.
- Uma observação parcial permite informar o mínimo positivo encontrado. A contagem exata, inclusive zero, exige roster recente e auditoria de todas as rotas atribuídas, com cobertura e contagens consistentes. A evidência expira em até 15 minutos do roster e antes, caso uma observação de rota vença.
- O painel PT/EN mostra a contagem da frota própria separadamente da contagem observada no jogo. Ocupação positiva ou divergência entre contagens bloqueia a simulação econômica exploratória; a divergência exige confirmação da semântica do contador do jogo. A validade da simulação também fica limitada à validade da evidência de ocupação, quando disponível.
- As alterações da evidência invalidam o cursor de pesquisa, preservando a identidade das combinações. A demanda residual, disponibilidade da rota e lucro líquido continuam sem confirmação e nenhuma aquisição é autorizada. Ainda são necessárias homologação autenticada do cruzamento e integração das demais evidências exigidas pelo planejamento de aquisições.
- Validação Windows: 1.710 testes aprovados e 1 ignorado pela própria suíte, excluindo `tests/test_instalacao_linux.py` (permissões POSIX). Regressões cobrem rotas inversas, aliases IATA/ICAO, auditoria parcial e completa, evidência vencida e conflitante, duplicidades, bloqueio da simulação própria/externa, cursores e apresentação em inglês. Ruff, compilação Python, sintaxe JavaScript e `git diff --check` aprovados.

## 2026-11-23 — Autonomia Total A3/A7, simulação econômica por motor e rota (G0)

- As filas próprias e externas calculam cenários exploratórios por variante com identidade de modelo confirmada, capacidade inteira, velocidade, consumo, alcance direto, modo de jogo recém-observado e cotações operacionais atuais. Dados de eventos ou contagem positiva de aeronaves na rota suprimem a simulação. A demanda observada é total e ainda exige verificação de demanda residual e ocupação.
- O cálculo apresenta alternativas de assentos Y/J/F, receita tarifária estimada, voos/dia teóricos fracionários, combustível, CO₂, margem sobre receita e contribuição diária. O stress usa os mesmos assentos, +20% em cada cotação e −10% em demanda e ocupação. As premissas são ocupação de 80%, tarifas aproximadas do modo de jogo, 6 minutos de turnaround, fator de combustível 0,94 e CO₂ de 0,18 por passageiro equivalente/km. Pista, horários, custos finais e taxas ainda precisam de confirmação.
- A margem de segurança da simulação é configurável por perfil em `[investment] preview_margin_pct` (padrão 10%, intervalo 0–100). Manutenção, A-check, outras despesas e investimento inicial estão explicitamente excluídos. A contribuição diária não constitui lucro líquido, ROI, payback ou recomendação de compra.
- A API e o painel PT/EN mostram a simulação separadamente da avaliação financeira verificada; a simulação expira com o modo ou com a primeira cotação vencida. Alterações das evidências ou da margem invalidam o cursor interativo sem alterar a identidade das combinações. As filas permanecem pendentes e inelegíveis para compra.
- Permanecem pendentes a confirmação autenticada dos seletores/tarifas e premissas, a demanda residual, cobertura, viabilidade física e custos recorrentes, bem como a integração ao registro auditado de economia. Nenhuma aquisição foi executada.
- Validação Windows: 1.700 testes aprovados e 1 ignorado, excluindo o teste de instalação Linux (permissões POSIX). Os testes cobrem variantes de motor, margem, stress com a mesma configuração de assentos, entradas ausentes ou vencidas, eventos, ocupação observada, cursores e apresentação da contribuição no painel. O teste de interface atualizado passou também em execução direcionada (9 aprovados). Ruff, compilação Python, sintaxe JavaScript e verificação do diff aprovados.

## 2026-11-23 — Autonomia Total A3/A7, cotações operacionais de combustível e CO₂ (G0)

- Com planejamento e coleta de mercado ativos, o ciclo consulta os dois mercados mesmo quando as compras automáticas estão desativadas. Os modos de compra são independentes e as regras existentes continuam disponíveis quando habilitadas.
- A cotação operacional utiliza o preço do seletor dedicado e duas leituras consistentes do temporizador da janela. Cada mercado possui horário próprio, expiração conservadora (máximo de 15 minutos) e invalidação em caso de nova leitura inconclusiva. Preço histórico, limite configurado e leitura genérica do painel não são utilizados como cotação observada.
- As filas de pesquisa de hubs próprios e externos expõem cotações em USD por mil unidades, fonte e validade na API autenticada. A interface PT/EN diferencia cotações atuais de valores desconhecidos. O cursor de evidência considera a cotação, preservando a identidade das combinações para a ingestão de pesquisas pendentes.
- As cotações estão disponíveis em memória por instância do bot. Ainda são necessárias a homologação dos seletores e temporizadores em sessão autenticada, a composição com consumo e demanda residual comprovados, a validação de taxas recorrentes e a integração completa ao cálculo de lucro, retorno e decisão de compra. Nenhuma compra real foi executada.
- Validação Windows: 1.688 testes aprovados e 1 ignorado pela própria suíte, excluindo `tests/test_instalacao_linux.py` (permissões POSIX). Os testes cobrem validade independente, preços ambíguos, mudança de janela, modo de consulta sem compra, combinações de opções, paginação e apresentação PT/EN. Ruff, compilação Python, sintaxe JavaScript e `git diff --check` aprovados.

## 2026-11-23 — Autonomia Total A3/A6/A7, evidências financeiras de hubs externos (G0)

- O catálogo externo agora fornece preço em dinheiro e custo em pontos com horários independentes, excluindo cada valor vencido ou conflitante. Valores explicitamente iguais a zero continuam válidos; atualização de preço não renova a validade do custo em pontos.
- A fila externa e a API autenticada cruzam essas observações com o saldo recente (até 15 minutos) e a reserva configurada. Se apenas o preço do hub exceder o caixa acima da reserva, o candidato recebe um bloqueio financeiro explícito. A comparação é um limite superior de disponibilidade antes dos compromissos; saldo de pontos, compromissos, preço final da aeronave, taxas, retorno e investimento total seguem pendentes de evidência.
- O painel PT/EN apresenta preço, pontos e caixa acima da reserva antes de compromissos, com valores desconhecidos distintos de zero. Mudanças no saldo ou nos custos invalidam o cursor de pesquisa, sem alterar o contrato da fila própria. Nenhuma combinação da fila externa autoriza aquisição.
- Regressões cobrem valores zero, inválidos, vencidos ou conflitantes, atualização independente, mudança de saldo, paginação, exclusão de hubs adquiridos e integração HTTP autenticada. Ainda é necessária a homologação das observações financeiras reais e a composição auditada dos demais custos, demanda residual, cobertura e retorno. Nenhuma compra foi executada.
- Suíte Windows: 1.673 testes aprovados e 1 ignorado pela própria suíte, excluindo `tests/test_instalacao_linux.py` (permissões POSIX). Ruff, compilação Python, sintaxe JavaScript e `git diff --check` aprovados.

## 2026-11-23 — Autonomia Total A2/A6/A7, combinações e detalhes de rotas externas (G0)

- A coleta incremental de hubs externos passou a pesquisar um detalhe independente de rota por ciclo de planejamento, com pistas dos dois aeroportos e contagem observada quando disponível. O registro, a rotação e a validade são separados dos hubs próprios. Hubs adquiridos deixam de alimentar a pesquisa externa.
- A fila externa cruza candidatos recentes do catálogo de compra, inventário confirmado de propriedade, demanda observada, modelos e variantes de motores. A paginação distribui combinações entre hubs e reinicia quando a evidência muda. O histórico de pesquisa próprio permanece compatível e a ingestão financeira própria rejeita filas externas.
- A API autenticada `GET /api/hubs/expansion/research` e o painel PT/EN exibem combinações, demanda Y/J/F observada, detalhes de pista, eventos temporários e bloqueios de viabilidade. O preço final, custo total e lucro permanecem desconhecidos enquanto não confirmados. A cobertura é parcial e nenhuma combinação autoriza compra.
- Regressões exercitam a separação dos registros, aquisição posterior de hub, propriedade desatualizada, origem do catálogo, variantes de motores, paginação e autenticação. Suíte Windows: 1.666 testes aprovados, 1 ignorado pela própria suíte, excluindo `tests/test_instalacao_linux.py` (permissões POSIX). Após preservar as impressões digitais da fila própria, 75 testes direcionados também passaram. Ruff, compilação Python, sintaxe JavaScript e `git diff --check` aprovados.
- Permanecem pendentes a homologação autenticada das consultas diretas externas, a semântica da demanda residual, a cobertura completa, os custos finais e a integração de cenários externos à decisão financeira auditada. Nenhuma compra real foi executada.

## 2026-11-23 — Autonomia Total A6/A7, pesquisa incremental de hubs externos (G0)

- O planejador pesquisa até um aeroporto externo por ciclo quando `collect_market_observations` e `investment.planning_enabled` estão ativos. A seleção exige uma lista estável e válida dos hubs próprios e candidatos recentes do catálogo de compra. O seletor de hubs é conferido novamente após a pesquisa e os IDs, valores e limites dos resultados são correlacionados antes de persistir qualquer amostra.
- Cada perfil utiliza um registro separado de demanda externa, com cursor, tentativas inconclusivas, alternância de filtros e prazo de validade independentes. Um hub adquirido deixa de aparecer na pesquisa externa e suas observações anteriores não são promovidas ao registro dos hubs próprios.
- A API e o painel PT/EN exibem a quantidade de candidatos pesquisados, amostras recentes e última tentativa por candidato. Inventários de propriedade vencidos ou ausentes deixam a classificação externa pendente. A cobertura permanece parcial e os dados observacionais não constituem cenário financeiro nem liberam aquisições.
- A pesquisa autenticada por `Custom departure` já foi observada na entrega anterior. O coletor reutiliza a consulta de rotas existente e exige que todas as linhas retornem o aeroporto externo selecionado. A aceitação dessa chamada direta pelo jogo, a abrangência dos filtros, a demanda residual, os detalhes independentes de rota e o cálculo completo de viabilidade externa seguem pendentes de homologação. Nenhuma compra foi realizada.
- Os testes cobrem a separação de registros, validade do catálogo, retomada após reinício, exclusão após aquisição, ausência ou mudança de propriedade, resultados com origem divergente e preservação do aviso de demanda temporária.
- Suíte Windows: 1.663 testes aprovados e 1 ignorado pela própria suíte, excluindo `tests/test_instalacao_linux.py` (permissões POSIX). Ruff, compilação Python e `git diff --check` aprovados.

## 2026-11-23 — Autonomia Total A2/A3, demanda de evento e contagem de aeronaves na rota (G0)

- Na sessão autenticada foi observado o aviso `Demand is currently boosted due to a special event` e a linha `A/C on route`, com duas células e contagem zero, na rota XAP–SBL. A leitura agora identifica explicitamente o aviso e associa a contagem ao rótulo, sem depender da posição da tabela. O valor permanece uma observação até conciliação com a frota completa; ausência de aviso não confirma demanda normal.
- O aviso explícito percorre a persistência de demanda, a fila de combinações, o cache de pesquisa e os rankings de hubs próprios e externos. Cenários com demanda de evento ficam pendentes, inclusive na revalidação de expansão. O painel PT/EN apresenta o evento e a contagem observada separadamente da ocupação verificada. Leituras contraditórias no mesmo instante não constituem uma base financeira.
- A pesquisa autenticada também demonstrou que `Custom departure` permite selecionar país e aeroporto ainda não adquirido e obter rotas daquele aeroporto. A coleta automatizada e a validação da cobertura de hubs externos continuam pendentes, assim como a conciliação de uma rota ocupada, a demanda residual e a normalização financeira. Nenhuma compra foi realizada.
- Regressões exercitam o aviso explícito, valores inválidos, persistência, conflitos, bloqueio de compra e contagem vinculada ao rótulo. Suíte Windows: 1.658 testes aprovados, 1 ignorado pela própria suíte, excluindo `tests/test_instalacao_linux.py` (permissões POSIX). Ruff, compilação Python e `git diff --check` aprovados.

## 2026-11-23 — Autonomia Total A2/A3, evidência independente dos detalhes de rota (G0)

**Objetivo:** complementar as amostras de demanda com as pistas dos dois aeroportos, vinculando a leitura ao par de IDs pesquisado e preservando a incerteza sobre a ocupação da rota.

### Implementação e evidências

- `src/route_detail_evidence.py` reutiliza a leitura desacoplada de `route_research_route.php`, sem executar scripts do fragmento. Exige duas respostas idênticas, dois códigos na ordem solicitada, correspondência IATA/ICAO com o catálogo auxiliar, concordância com o código do hub quando disponível e medidas positivas em pés, até 30.000 ft. Se a pesquisa já trouxe a pista do destino, exige concordância entre as fontes.
- O proprietário da sessão Selenium pesquisa até dois pares por ciclo, com `collect_market_observations` e `investment.planning_enabled` ativos e inventário de hubs recente. A seleção alterna hubs e destinos com base nas tentativas persistidas por perfil. Uma tentativa inconclusiva invalida o detalhe anterior e libera a rotação para os demais pares, inclusive após reinício. A evidência independente expira após 15 minutos.
- O cache de demanda, a fila de pesquisa, a materialização de combinações e o painel PT/EN incorporam os detalhes com ID, origem, horário e validade próprios. Pistas de origem e destino aparecem separadamente da pista observada na pesquisa de demanda. A leitura de cenários armazenados consulta o registro atual para retirar evidências vencidas ou invalidadas.
- O número localizado na primeira célula da tabela do detalhe não possui semântica autenticada inequívoca. Ocupação, disponibilidade, demanda residual e compatibilidade do modelo continuam desconhecidas ou pendentes. A evidência permanece restrita à pesquisa e não autoriza compras.

### Verificação, limites e reversão

- Regressões cobrem ordem dos aeroportos, aliases IATA/ICAO, unidades e limites das pistas, divergência entre fontes, rotação, persistência, respostas instáveis, expiração e invalidação da evidência nos cenários. O teste do painel inclui traduções e estados desconhecidos.
- Suíte Windows: 1.654 testes aprovados, 1 ignorado pela própria suíte, excluindo `tests/test_instalacao_linux.py` (permissões POSIX). Ruff em `src`, `tests` e `scripts`, compilação Python e `git diff --check` aprovados.
- **Gate G0.** As estruturas do detalhe foram verificadas com respostas simuladas nesta entrega. A estrutura exata e os rótulos do fragmento autenticado, a semântica de ocupação, o universo de rotas, a demanda residual, os custos e a viabilidade final seguem pendentes. Nenhuma compra real, implantação ou merge na `main` foi executado.
- Reversão pelo commit desta entrega na branch `codex/autonomia-a0-a1-20261122`, considerando dependências posteriores.

## 2026-11-23 — Autonomia Total A2/A3, ampliação da pesquisa de rotas por hub (G0)

**Objetivo:** aumentar o universo observado para comparar aeronaves de alcances e requisitos de pista diferentes, mantendo a procedência dos dados e a rotação entre hubs próprios.

### Implementação e evidências

- Com `investment.planning_enabled=on`, a pesquisa de demanda alterna, individualmente por hub, entre os filtros configurados e uma solicitação ampla de até 20.000 km com pista mínima de 0 ft. O cursor persiste antes da consulta, inclusive após tentativas inconclusivas e reinícios. Amostras de outras consultas não completam a tentativa do planejador. Os filtros registrados identificam os parâmetros enviados, cuja aceitação e abrangência ainda dependem de homologação autenticada.
- `src/game_observations.py` correlaciona a pista informada em `data-rwy` com a mesma rota e os demais valores da leitura estável. Pistas ausentes ou inválidas permanecem desconhecidas; uma pista positiva contraditória invalida o lote. A pesquisa rejeita resultados incompatíveis com os limites solicitados quando a informação está disponível.
- A observação de pista do destino segue pelo registro de demanda, pela fila de pesquisa, pelo cache de combinações e pelo painel PT/EN. O painel também identifica o último filtro solicitado para cada hub. As combinações permanecem pendentes de confirmação das pistas dos dois extremos, dos requisitos do modelo e motor, da demanda residual, da disponibilidade da rota e dos custos.
- Os testes cobrem a rotação em dois hubs, persistência após reinício, tentativas inconclusivas, amostras de consultas independentes, correlação de pista e a propagação da evidência sem autorizar aquisição.

### Verificação, limites e reversão

- 244 testes direcionados de pesquisa e 9 testes do painel aprovados. Suíte Windows: 1.642 aprovados, 1 ignorado pela própria suíte, excluindo `tests/test_instalacao_linux.py` (permissões POSIX). Ruff em `src`, `tests` e `scripts`, compilação Python e `git diff --check` aprovados.
- **Gate G0.** A pesquisa continua com cobertura parcial, sem prova de exaustão do mercado ou de demanda residual. A validação desta entrega usa dados simulados. Permanecem pendentes a homologação dos limites e da paginação do jogo, as especificações das variantes de motor e a confirmação de viabilidade e retorno por combinação. Nenhuma compra real, implantação ou merge na `main` foi executado.
- Reversão pelo commit desta entrega na branch `codex/autonomia-a0-a1-20261122`, considerando dependências posteriores.

## 2026-11-23 — Autonomia Total A2, conciliação integral da frota e dos hubs (G0)

**Objetivo:** correlacionar a auditoria de rotas com o inventário atual do jogo antes de admitir que a rede existente foi integralmente identificada.

### Implementação e evidências

- `src/fleet.py` e `src/route_registry.py`: leituras do inventário antes e depois da auditoria integral são correlacionadas por identidade, matrícula e ID de rota. A certificação exige contagens coerentes de aeronaves com rota, estacionadas e pendentes, todas as páginas verificadas e evidência individual compatível. Valores ausentes de ID de rota são tratados como informação incompleta. A observação do inventário expira em 15 minutos e a auditoria em uma hora; a última auditoria histórica fica separada da prova vigente.
- A prova é revogada antes de mutações de compra ou alteração de rota e quando há evidências incompatíveis. Leituras de detalhes e atualizações compatíveis podem preservá-la sem renovar seu prazo. Recuperação de redirecionamento pendente impede nova certificação.
- `src/hub_registry.py` distingue cobertura da frota atual e cobertura do vínculo permanente por hub. A segunda exige catálogo de hubs vigente (até três dias) e evidência explícita de base para cada aeronave. `src/hub_recommendations.py` utiliza somente relações atuais para ocupação de rotas quando a cobertura é comprovada, mantendo tratamento conservador em pesquisas parciais. O painel exibe os estados e as contagens correspondentes em português e inglês.
- Os testes exercitam divergências entre leituras, registros pendentes, expiração, alterações de rota, preservação compatível da prova e ausência de evidência de base permanente.

### Verificação, limites e reversão

- 399 testes direcionados aprovados. Suíte Windows: 1.638 aprovados, 1 ignorado pela própria suíte, excluindo `tests/test_instalacao_linux.py` (permissões POSIX). Ruff em `src`, `tests` e `scripts`, compilação Python e `git diff --check` aprovados.
- **Gate G0.** Os contratos desta entrega foram verificados por testes com observações simuladas. A homologação autenticada da conciliação e a fonte individual de base permanente ainda são necessárias. A pesquisa integral de oportunidades por hub, rota, modelo e motor segue pendente. Nenhuma compra real, implantação ou merge na `main` foi executado.
- Reversão pelo commit desta entrega na branch `codex/autonomia-a0-a1-20261122`, considerando dependências posteriores.

## 2026-11-23 — Autonomia Total A2, cobertura de rotas no ciclo de planejamento (G0)

**Objetivo:** tornar a tentativa de auditoria integral parte da operação normal do planejador, com validade temporal e detecção de alterações nas evidências mesmo quando os IDs permanecem iguais.

### Implementação e evidências

- `src/fleet.py`: com `investment.planning_enabled=on`, a auditoria tenta percorrer todas as páginas quando existem até 25, independentemente do orçamento incremental padrão de três páginas. A ordem de navegação parte da página atual, visita as demais e realiza uma releitura em ordem inversa antes de restaurar a tela inicial. Para frotas com mais de 25 páginas, permanece a coleta parcial. O prazo de 120 segundos é conferido entre navegações e antes de publicar o lote, inclusive após a restauração; chamadas de navegação já iniciadas dependem dos seus próprios timeouts. Cancelamentos ou expiração descartam o lote.
- `src/route_registry.py`: a impressão digital das observações estáveis por página inclui identidade, matrícula, modelo, extremos da rota, ID da rota e evidência de base. Mudanças durante a mesma auditoria invalidam a prova, inclusive se a observação voltar ao estado anterior. A ordem dos IDs e o estado momentâneo de voo não alteram essa impressão. O snapshot deixa de apresentar cobertura integral atual após a janela de uma hora, preservando separadamente a última auditoria integral histórica.
- Regressões comprovam o fluxo com 11 páginas e início em posições diferentes, a coleta parcial acima do limite de páginas, a restauração após prazo vencido, a revogação de evidência com os mesmos IDs e a expiração sem nova coleta.

### Verificação, limites e reversão

- 143 testes direcionados aprovados. Suíte Windows: 1.625 aprovados, 1 ignorado pela própria suíte, excluindo `tests/test_instalacao_linux.py` (permissões POSIX). Ruff em `src`, `tests` e `scripts`, compilação Python e `git diff --check` aprovados.
- **Gate G0.** A cobertura integral de páginas de rotas ainda precisa ser correlacionada ao inventário atual do jogo, incluindo aeronaves estacionadas e pendentes, antes de habilitar decisões de aquisição. As evidências de base permanente, o catálogo de hubs candidatos e a pesquisa externa permanecem pendentes. A validação desta entrega utiliza cenários de teste, sem nova homologação autenticada de paginação.
- Reversão pelo commit desta entrega na branch `codex/autonomia-a0-a1-20261122`, considerando dependências posteriores.

## 2026-11-23 — Autonomia Total A1/A3, seletor autenticado de motores e custos operacionais (G0)

**Objetivo:** reconhecer o controle real de variantes no formulário de aeronaves e impedir pesquisa ou classificação de rotas com preços operacionais inválidos.

### Implementação e evidências

- **A1:** inspeção autenticada somente leitura em Routes > Order > Aircraft details confirmou `#acModel select#engSelection`, sem nome ou rótulo associado, com IDs de opções estáveis observados na sessão. Cessna 172 e B737-800 apresentaram uma variante cada, A320-200 apresentou duas e A380-800 apresentou três (GP7270, RR Trent 970 e RR Trent 972). A fixture anonimizada `tests/fixtures/am4_order_engines_20261123.json` registra as quatro estruturas e os preços exibidos, sem dados de conta. A opção de motor não contém atributos individuais de velocidade/consumo; as métricas do painel não podem ser atribuídas às variantes não selecionadas.
- `src/engine_selection.py` reconhece o seletor nativo mesmo sem nome/rótulo. `src/game_source_probe.py` reconhece o controle e a estrutura `#acCost` cujo símbolo monetário fica no elemento pai; o diagnóstico continua expondo somente contagens e indicadores de formato, sem publicar valores da conta. A presença de preço exibido não prova preço final incluindo motor, nem a identidade completa do checkout.
- **A3:** `src/route_optimizer.py` centraliza a validação de preços operacionais positivos, finitos e inferiores a 100.000 por mil unidades, rejeitando booleanos e valores ausentes ou malformados. `src/fleet.py` adia a criação, a substituição de rotas duplicadas e a busca de escalas se esses preços forem inválidos; os mesmos preços são utilizados durante a classificação. `src/route_registry.py` rejeita booleanos no registro de margem observada.
- Regressões verificam a leitura do JavaScript de produção com as estruturas observadas, variantes sem métricas próprias, ausência de confirmação de preço integral e bloqueio de pesquisas com custos inválidos. O teste de diagnóstico de duplicidades fornece preços válidos para preservar a verificação independente de identificação da base.

### Verificação, limites e reversão

- Testes direcionados de A1/A3, seleção de base, escala e registros de rota aprovados. Suíte Windows: 1.618 testes aprovados, 1 ignorado pela própria suíte, com exclusão de `tests/test_instalacao_linux.py`, que depende de permissões POSIX. Ruff (`src`, `tests`, `scripts`), `compileall src` e `git diff --check` aprovados.
- **Gate G0.** Nenhuma opção de motor ou base foi alterada durante a inspeção, nenhuma compra foi executada. O preço final por variante, identidade do modelo e do hub correlacionada ao checkout, e revalidação autenticada pós-AJAX permanecem pendentes. Os custos operacionais configurados/legados ainda não substituem a prova temporal de preços observados necessária à política autônoma. Não houve Telegram real, implantação ou merge na `main`.
- Reversão pelo commit desta entrega na branch `codex/autonomia-a0-a1-20261122`, considerando dependências posteriores.

## 2026-11-23 — Autonomia Total A1/A5, variante exata e pré-checagem de checkout (G0)

**Objetivo:** vincular a preparação de uma encomenda planejada à variante de motor e base aprovadas e exigir evidência estável do preço final antes de considerar a operação viável.

### Implementação e evidências

- `src/engine_selection.py`: o ID explícito do motor tem precedência sobre a preferência geral. Ausência, duplicidade ou indisponibilidade interrompem a seleção; após eventual atualização do formulário, a variante, a disponibilidade, as métricas e a seleção são conferidas novamente. O comportamento legado sem ID explícito permanece preservado.
- `src/fleet.py`: a encomenda planejada exige ID válido de base, ID de motor e preço inteiro positivo. O gate G0 impede uma encomenda real antes de abrir o formulário. A simulação verifica a seleção efetiva e exige duas leituras coerentes do preço integral modelo + motor, do modelo aberto, da base e do estado AJAX. Qualquer divergência bloqueia o resultado; o preço-base do catálogo não substitui o preço final.
- `tests/test_engine_selection.py` e `tests/test_aircraft_order_hub.py`: testes de variante explícita, disponibilidade, reconstrução do formulário, divergências de preço/identidade/base, gate antes da abertura e integração simulada dos leitores reais de motor, base e diagnóstico de checkout. O teste integrado usa respostas DOM sintéticas, incluindo tentativa de inserir um preço supostamente confirmado no diagnóstico; nenhum clique de compra, mudança de motor/base ou confirmação é permitido.

### Verificação, limites e reversão

- Testes direcionados (163), Ruff em `src`, `tests` e `scripts`, compilação Python e `git diff --check` aprovados. A suíte Windows integral concluiu com código 0 após as alterações finais, com um teste ignorado pela própria suíte e exclusão do teste de instalação que depende de permissões POSIX.
- **Gate G0.** O diagnóstico autenticado ainda não foi homologado para provar preço final, variação de preço por motor ou identidade integral de checkout. `probe_game_sources()` continua retornando `price_verified=false`; o caso positivo isolado testa o contrato com dados artificiais. Não houve compra, envio real ao Telegram, implantação ou merge na `main`.
- A leitura real dos modelos com uma, duas e três ou mais variantes e a integração do executor A5 com journal e confirmação independente permanecem pendentes. O fluxo legado conserva sua política de compra independente. Reversão pelo commit desta entrega na branch `codex/autonomia-a0-a1-20261122`, observando dependências posteriores.

## 2026-11-23 — Autonomia Total A9, notificações de transições do investimento (G0)

**Objetivo:** informar individualmente as etapas de cada intenção de investimento sem perder eventos após reinícios ou falhas de transporte.

### Implementação e evidências

- **Diário por evento:** `InvestmentJournal` agora permite consultar o último evento, listar transições em ordem e recuperar um evento por ID, com isolamento por perfil. O conteúdo da mensagem distingue propostas, aprovação, pré-checagem, submissão, confirmação independente, resultado incerto e falha. O valor exibido é expressamente **previsto**, sem atribuir gasto real a um clique.
- **Entrega resiliente:** `src/investment_events.py` implementa cursor SQLite por **perfil e modo real/simulação**, com reivindicação exclusiva, lease de 300 segundos, confirmação somente após sucesso de `send_now()`, reenvio após falha e no máximo um evento por ciclo. A primeira ativação inicia no último evento existente, evitando disparo retrospectivo de todo o histórico. Transições posteriores são entregues em ordem.
- **Configuração e integração:** nova opção `telegram_investment_events=off` em `config/defaults.ini`, exposta na aba Telegram com ajuda PT-BR/EN. A integração em `src/bot.py` requer simultaneamente a opção e o Telegram global habilitados. As mensagens de simulação são identificadas e usam seu próprio diário e cursor.
- **Testes:** `tests/test_investment_events.py` verifica ordenação, conteúdo, retry após falha/exceção/reinício, claim concorrente e vencido, isolamento de perfil e de modo, alternância real/simulação, seleção de evento e inatividade com opção desabilitada. `tests/test_telegram_filters.py` cobre o novo controle desligado por padrão.

### Verificação, limites e reversão

- Testes direcionados aprovados, incluindo journal, relatório diário e filtros de Telegram. Suíte completa de Windows com exclusão apenas do instalador POSIX, Ruff, `compileall src` e `git diff --check` verificados nesta entrega.
- **Gate G0.** Fixtures de journal e cliente Telegram simulado. Não houve mensagem real, compra de aeronave/hub, implantação ou merge na `main`. Sem observação autenticada, a notificação informa estados registrados no journal, que ainda não comprovam compra/entrega/lucro real por si sós. Resposta perdida após envio remoto pode gerar notificação duplicada no retry. Eventos já existentes antes da ativação ficam fora da primeira remessa.
- A entrega é reversível por commit na branch `codex/autonomia-a0-a1-20261122`, observadas dependências posteriores. PR #46 permanece em rascunho, PR #44 preservada. A prioridade técnica seguinte é homologar o preço final do checkout após a seleção real do motor e validar a cobertura A1/A2 no jogo autenticado, sem autorizar gasto a partir de fixtures.

## 2026-11-23 — Autonomia Total A9, relatório diário de investimentos (G0)

**Objetivo:** disponibilizar uma prestação de contas diária do planejamento de investimentos, das intenções registradas e das evidências ainda ausentes.

### Implementação e evidências

- **A9 — `src/investment_daily.py`:** novo relatório Telegram por perfil, emitido após `summary_hour` e no máximo uma vez por dia. Apresenta intenções e compromissos previstos, confirmações registradas no diário, cobertura da pesquisa, oportunidades avaliadas, calibração disponível e motivos para não comprar. Gasto efetivo, entregas e lucro real continuam desconhecidos sem confirmação independente do jogo.
- **Integridade da entrega:** `DailyInvestmentDelivery` persiste uma reivindicação SQLite por perfil/data, utiliza lease de 300 segundos e só confirma a entrega quando `send_now()` retorna sucesso. Falhas e exceções liberam a reivindicação para nova tentativa. O relatório identifica separadamente o estado do autobuyer legado e informa que esse fluxo não integra os totais do novo diário.
- **Política:** o relatório utiliza `InvestmentPolicy.report()` para mostrar modo, validade, limites ausentes e bloqueio do executor no gate G0. Modos `approval` e `autonomous` são descritos com seus impedimentos reais.
- **Configuração:** `telegram_investment_daily=off` por padrão, com controle na aba Telegram e descrições em português e inglês. A execução depende também do Telegram global estar habilitado.
- **Regressões — `tests/test_investment_daily.py`, `tests/test_investment_policy.py` e `tests/test_telegram_filters.py`:** envio diário idempotente após reinício, isolamento por perfil, recuperação de lease, falha e reenvio, ambiente de simulação, origem dos valores, dados indisponíveis, política inválida, modo de aprovação, limites autônomos e estado independente do autobuyer legado.

### Verificação, limites e reversão

- Testes direcionados e suíte Windows completa aprovados, com exclusão apenas de `tests/test_instalacao_linux.py`, que depende de permissões POSIX. Ruff em `src` e `tests`, `compileall src` e `git diff --check` aprovados.
- **Gate G0.** A confirmação de envio depende da resposta do cliente Telegram. Se a mensagem chegar ao Telegram e a resposta se perder, uma nova tentativa após o lease pode duplicá-la. O relatório cobre o diário da nova política por oportunidade e não audita compras do fluxo legado. Não há comprovação independente de gasto, entrega de aeronave ou lucro real.
- Nenhum envio real ao Telegram, compra no jogo, alteração de configuração produtiva, implantação ou merge em `main`. A flag permanece desligada por padrão. Reversão pelo commit desta entrega após verificar dependências do novo módulo e da configuração.

## 2026-11-23 — Autonomia Total A4/A6/A7, exaustão comprovada e reenvio de alerta (G0)

**Objetivo:** impedir que a comparação de oportunidades próprias marque uma pesquisa inconclusiva como esgotada e manter o fluxo de notificações de expansão recuperável após exceções de transporte.

### Implementação e evidências

- **A4/A6 — `src/portfolio_planner.py`:** `compare_portfolio()` inclui motivos de bloqueio quando a pesquisa de um hub próprio permanece pendente, omite a lista explícita de pendências, contém identidade/custos inválidos ou encontra resultados contraditórios para a mesma oportunidade. Somente negativas com `pending=[]` e status conclusivo (`saldo_insuficiente`, `sem_lucro`, `rota_inviavel`, `rota_ocupada`, `rota_indisponivel`) podem contribuir para uma comparação encerrada sem oportunidade. A6 só pode interpretar exaustão de hubs próprios com cobertura e evidências completas.
- **A6 — `src/hub_expansion.py`:** observações explícitas de `purchasable=false` passam a ser persistidas por ID de aeroporto e horário, inclusive em páginas parciais e catálogos sem opção comprável. Essa evidência elimina opções positivas mais antigas, resiste a reinício e somente é revogada por uma leitura positiva estritamente posterior. Dados negativos com ID inválido impedem classificação de varredura completa. Um catálogo completo e fresco contendo apenas indisponibilidades é tratado como cobertura conhecida.
- **A7 — `src/expansion_alerts.py`:** se `send_now()` lançar exceção, a reivindicação de deduplicação é liberada para nova tentativa, retorna `failed` e registra advertência sem incluir a exceção, que pode carregar endereço e token privado. A deduplicação ainda confirma o envio somente após resposta de sucesso do cliente.
- **Regressões — `tests/test_portfolio_planner.py`, `tests/test_hub_expansion.py` e `tests/test_expansion_alerts.py`:** cenários próprios pendentes, omissão de `pending`, negativas conclusivas, conflito de pesquisas, atualização de disponibilidade de hubs entre páginas e reinícios, reativação após nova observação, conflito temporal e falha de Telegram seguida de reenvio e supressão após entrega, inclusive quando o conteúdo sofreu alteração material.

### Verificação, limites e reversão

- Testes locais de regressão aprovados, com verificação da suíte Windows, Ruff, `compileall` e `git diff --check` nesta entrega.
- **Gate G0.** As provas são de dados e clientes simulados. Permanecem pendentes inventário, demanda, checkout e confirmação autenticados no jogo, além de homologação de alertas reais. Uma resposta perdida após entrega remota pode provocar notificação duplicada na tentativa seguinte.
- Nenhuma compra real, envio ao Telegram, implantação, habilitação de gasto automático ou merge em `main`. PR #46 continua como rascunho, preservando a PR #44. Reversão pelo commit correspondente na branch `codex/autonomia-a0-a1-20261122` após conferir dependências.

## 2026-11-23 — Autonomia Total A2/A8, inventário inequívoco e transação simulada em duas etapas (G0)

**Objetivo:** impedir que IDs contraditórios de hubs próprios alimentem a pesquisa de oportunidades e exercer a sequência de expansão hub → nova pesquisa → aeronave com reconciliação entre as etapas.

### Implementação e evidências

- **A2 — `src/owned_hub_research_feed.py`:** a fila detecta o mesmo ID de hub próprio associado a códigos divergentes dentro de um inventário, descarta essa identidade e registra `inventario_hubs_conflitante`. A pesquisa fica bloqueada até um inventário coerente, inclusive quando há outros hubs válidos. Repetições idênticas de ID/código continuam permitidas.
- **A8 — `src/hub_purchase.py`:** `SimulatedExpansionCoordinator` utiliza o mesmo `InvestmentJournal` e a política de investimento nas duas fases. A compra simulada do hub segue a confirmação independente existente. Uma chamada posterior de aquisição simulada de aeronave exige uma intenção de hub já `CONFIRMED`, pesquisa com novo `snapshot_id`, prova atual de propriedade vinculada ao perfil e ao hub e checkout de aeronave revalidado pelo executor A5. A intenção de hub sobrevive ao reinício, sem reenviar a aquisição.
- **Testes — `tests/test_owned_hub_research_feed.py` e `tests/test_hub_purchase.py`:** conflitos de identidade e invalidação do cursor, duplicatas benignas, bloqueio da segunda fase após timeout e com snapshot antigo, aprovação separada, reinício idempotente e recusa de aeronave depois da compra confirmada do hub.

### Verificação, limites e reversão

- A suíte Windows completa (`python -m pytest -q tests --ignore=tests/test_instalacao_linux.py`) terminou com código 0, excluindo apenas o teste de instalador que depende de permissões POSIX. Testes dirigidos de A8 (16), Ruff em `src`/`tests`, `compileall src` e `git diff --check` também aprovados.
- Gate **G0**. A orquestração usa gateways SQLite simulados e exige prova explícita de posse e nova observação. A homologação autenticada da compra de hub, confirmação da propriedade, pesquisa pós-compra e configuração da aeronave ainda é necessária antes de qualquer gasto real ou autonomia G3–G5.
- Nenhuma compra real, Telegram, implantação, alteração de configuração produtiva ou merge na `main`. A PR #44 segue separada. Reverter o commit desta entrega na branch `codex/autonomia-a0-a1-20261122` após verificar dependências. Os registros de simulação são isolados por perfil e a [PR de acompanhamento #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46) permanece em rascunho.

## 2026-11-23 — Autonomia Total A1/A4/A5/A6/A7, prévia de aquisição e integridade de catálogo (G0)

**Objetivo:** conectar a melhor oportunidade global auditada aos contratos de intenção e pré-compra, distinguindo o preço de aeronave + motor das despesas futuras que consomem o orçamento total.

### Implementação e evidências

- **`src/investment_plan_bridge.py`:** conversão somente leitura do vencedor A4 e sua avaliação A3 correspondente em uma proposta persistível. Exige ranking global conclusivo, identidade e snapshot idênticos, proveniência A3 válida no tempo, custos completos, ausência de custos recorrentes desconhecidos e valores monetários inteiros na unidade do jogo. Rejeita centavos ou unidade ambígua, custo de hub em proposta para hub próprio, divergência financeira e fonte obsoleta.
- **`src/investment_journal.py`:** contrato opcional e durável `capital_costs` + `checkout_cost`. `estimated_cost` continua representando o **investimento total**, incluindo rota, hangar e demais despesas, para reserva e limites de compra por dia. As parcelas são inteiras, somam exatamente o total e o checkout corresponde exatamente à aeronave + variação do motor. Intenções antigas sem discriminação preservam o valor único original. O journal permanece exclusivo por perfil, idempotente e resiliente a reinícios.
- **`src/investment_preflight.py`:** comparação independente do preço do formulário com `checkout_cost` e checagem de saldo/reserva/compromissos contra `estimated_cost` total. Um checkout correto não permite comprar quando faltam recursos para as despesas já previstas. A validação ainda requer preço de motor incluído e identidade/snapshot/rota/hub atualizados.
- **A1 — `src/engine_catalog.py`:** uma leitura posterior sem identidade comprovada do detalhe do modelo não substitui um catálogo anteriormente associado a um ID de modelo verificado, mesmo que seu timestamp seja mais recente. Uma nova leitura pode atualizar o registro quando a identidade volta a ser confirmada. A regra persiste após reinício do registry.
- **`src/aircraft_order_hub.py`, `src/engine_selection.py` e `src/fleet.py`:** confirmação adicional da seleção pós-AJAX de base e variante de motor. No fluxo explícito `hub_id`, a pré-validação também exige diagnóstico da tela de checkout com modelo/hub correlacionados, atualização concluída e preço verificado. O caminho sem `hub_id` mantém sua compatibilidade com chamadas existentes.
- **A5/A7 — `src/web.py` e `assets/web/index.html`:** o GET autenticado da análise global relaciona o vencedor A4 a exatamente uma avaliação A3 e expõe uma prévia de intenção com modelo, motor, hub, rota, preço de checkout e composição do investimento. Se o vínculo estiver ausente, ambíguo ou inválido, a API retorna impedimentos. A interface apresenta os dados ou os motivos de bloqueio e mantém `read_only=true` e `execution_available=false`.
- **A6 — `src/hub_expansion.py`:** IDs repetidos no mesmo lote com elegibilidade de compra contraditória invalidam o lote sem substituir o catálogo persistido. Valores de elegibilidade ausentes ou não booleanos deixam a cobertura incompleta. A persistência de evidência negativa entre páginas distintas ainda precisa ser tratada.
- **Testes:** `tests/test_investment_plan_bridge.py` percorre ponte A3/A4, persistência/reinício, simulação de compra, teto diário, caixa insuficiente para capital total, divergência de preço, dados vencidos e custos inválidos. `tests/test_aircraft_order_hub.py` amplia as regressões da leitura do checkout pós-seleção. `tests/test_engine_catalog.py` verifica preservação da identidade comprovada contra leituras posteriores não correlacionadas, inclusive após reinício. `tests/test_audited_economics_registry.py` cobre o endpoint autenticado e os bloqueios por avaliação A3 ausente ou ambígua. `tests/test_hub_expansion.py` cobre contradições de elegibilidade. `tests/test_hubs_dashboard_ui.py` executa o renderizador da prévia, os custos e os bloqueios com Node.

### Verificação, limites e reversão

- **Gate G0.** Testes locais e simuladores validam contratos e idempotência. O preço de checkout, a estrutura AJAX, a moeda/unidade exata e os vínculos de rota/base ainda precisam de homologação autenticada. A prévia é somente leitura e não habilita executor. Nenhuma compra no jogo foi executada, nenhuma nova política foi habilitada no servidor e os gates G1–G5 permanecem pendentes.
- Esta entrega **não** conecta o adaptador a um executor de compra real. A comparação no painel segue apenas como sugestão, sujeita à aprovação e à verificação independente no checkout. Custos A3 fracionários são bloqueados até prova da unidade real do jogo.
- Reversão pelo commit desta entrega na branch de autonomia, após conferir dependências. A inclusão de campos opcionais no JSON de uma intenção não altera o schema SQLite anterior, e registros antigos mantêm compatibilidade.

## 2026-11-23 — Autonomia Total A5, validação da base de entrega da aeronave (G0)

**Objetivo:** garantir que cada encomenda esteja vinculada a uma base comprovada no formulário do jogo e permitir que um plano indique explicitamente a base de entrega.

### Implementação e evidências

- **`src/aircraft_order_hub.py`:** leitura estrita de `#hubSelection`, com validação de seletor único, estado habilitado, opções sem IDs duplicados, seleção única e correspondência entre o valor atual e a opção selecionada. A seleção explícita dispara eventos `input` e `change`, aguarda a atualização e relê o DOM para confirmar o ID final. A simulação valida a disponibilidade da base sem modificar o formulário.
- **`src/fleet.py`:** `order_aircraft()` aceita `hub_id` opcional. Quando um plano informa a base, o fluxo seleciona e confirma esse ID antes de continuar. No fluxo legado, a base atualmente selecionada precisa ser comprovada. Alterações de motor ou base fazem o fragmento `#acModel` ser relido antes de prosseguir, e o resumo da encomenda registra o ID da base.
- **`tests/test_aircraft_order_hub.py`:** cobre seleção atual, seleção explícita, simulação sem mutação, seletor ausente/ambíguo/desabilitado, IDs duplicados, opção indisponível, falha de confirmação e bloqueio da encomenda quando a base não pode ser verificada.

### Verificação, limitações e reversão

- Testes direcionados de base e motorização aprovados. Suíte Windows completa aprovada com exclusão apenas de `tests/test_instalacao_linux.py`, que depende de permissões POSIX. Ruff em `src` e `tests`, `compileall` e `git diff --check` aprovados.
- **Gate G0.** A validação automatizada usa fixtures DOM. O seletor `#hubSelection` consta do diagnóstico de fonte do jogo, mas ainda falta homologar a seleção em sessão autenticada e confirmar como cada variante de formulário reage aos eventos. Nenhuma compra real foi executada. O caminho continua sujeito aos gates A1/A2/A3/A4 e ao pré-voo completo A5.
- Sem compra no jogo, alteração de configuração de produção, Telegram, implantação ou merge em `main`. Reversão por commit desta entrega após verificar dependências em `fleet.py`.
- **Código publicado:** [`4c61128`](https://github.com/andreypiekas/AirlineManager4BOTWEB/commit/4c61128deb72a38e447a39abe729fdd910f15e34), na [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-23 — Autonomia Total A5/A8, recuperação comprovada de executor após encerramento do processo (G0)

**Objetivo:** permitir a conciliação segura de uma compra simulada após a morte do processo que detinha o bloqueio do perfil, preservando o diário de intenção e a regra de tentativa única.

### Implementação e evidências

- **`src/investment_journal.py`:** cada novo bloqueio de executor armazena PID e hostname. `release_stale_executor()` usa a API de processos do sistema operacional e libera, em transação SQLite, somente um bloqueio do mesmo host cujo processo comprovadamente terminou. Um processo vivo, PID inacessível, host diferente ou registro legado sem metadados mantém a exclusividade. A migração das duas colunas ocorre sob `BEGIN IMMEDIATE` para evitar corrida entre inicializações concorrentes.
- **`src/investment_executor.py` e `src/hub_purchase.py`:** os executores simulados tentam recuperar bloqueio obsoleto antes de adquirir exclusividade para iniciar ou conciliar uma intenção. Compras já marcadas `SUBMITTED`/`UNKNOWN` continuam sendo resolvidas exclusivamente por consulta independente ao pedido/posse persistido, sem nova submissão.
- **`tests/test_investment_journal.py`, `tests/test_investment_executor.py` e `tests/test_hub_purchase.py`:** verificam processo vivo versus encerrado, recuperação após término real de subprocesso, host diferente, migração concorrente do schema legado, reinício com pedido simulado persistido e confirmação sem repetição da compra.

### Verificação, limitações e reversão

- Testes direcionados, suíte Windows sem o teste de instalação Linux específico de permissões POSIX, Ruff, `compileall` e `git diff --check` executados nesta entrega. A prova de término do subprocesso utiliza o sistema operacional do executor local; gateway e pedidos são simulados.
- **Gate G0.** A recuperação automática exige o mesmo hostname e metadados de processo. PID reutilizado, PID inacessível, mudança de host e bloqueios de versões antigas permanecem conservadoramente retidos para recuperação explícita. A simulação não comprova seletores, pedidos ou propriedade do jogo real. A5 e A8 ainda dependem de reconciliação autenticada, verificação da configuração final e homologação para liberar qualquer gasto. Gates G1–G5 pendentes.
- Sem alteração de configuração de produção, compra no jogo, Telegram, implantação ou merge na `main`. Branch `codex/autonomia-a0-a1-20261122`, commit [`90fd00f`](https://github.com/andreypiekas/AirlineManager4BOTWEB/commit/90fd00fa97469dd5a144dbfcfcbdd6fbc9723bd4) e [PR de acompanhamento #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46) em rascunho, preservando a PR #44. A reversão exige inspecionar os usos do diário e reverter o commit correspondente. Novas colunas opcionais do SQLite podem permanecer após a reversão sem afetar leitores legados.

## 2026-11-23 — Autonomia Total A8, bloqueio de recompra de hub no simulador (G0)

**Objetivo:** garantir que uma segunda intenção, outro processo ou uma retomada após falha não consiga registrar novamente a aquisição de um hub já reservado como adquirido no armazenamento simulado.

### Implementação e evidências

- **`src/hub_purchase.py`:** `SimulatedHubGateway.read_checkout()` consulta a posse persistida por perfil e ID do hub e força `before_owned=true` e `can_purchase=false` quando já existe aquisição registrada. `submit_order()` valida que o hub enviado corresponde ao checkout e, dentro de `BEGIN IMMEDIATE`, consulta a posse antes de inserir. A transação serializa intenções concorrentes que usem o mesmo armazenamento, inclusive quando possuem `intent_key` diferentes.
- A proteção mantém o isolamento por perfil. Registros recusados continuam permitindo uma nova intenção, enquanto resultados confirmados, enviados com timeout ou interrompidos após o envio bloqueiam outra aquisição do mesmo hub.
- **`tests/test_hub_purchase.py`:** novos cenários para intenção diferente após reinício, confirmação/timeout/crash, submissão direta, concorrência entre gateways, isolamento por perfil e nova tentativa após recusa.

### Verificação, limites e reversão

- Testes direcionados de hub, executor e diário de investimento aprovados. Suíte Windows completa aprovada com exclusão do teste de instalação Linux que depende de permissões POSIX. Ruff em `src` e `tests`, `compileall` e `git diff --check` aprovados.
- **Gate G0.** A8 continua sem seletor ou executor de compra real homologado. Permanecem pendentes a evidência autenticada de preço e posse, controles comprovados do jogo, fluxo de confirmação independente e aprovação explícita de homologação. Nenhuma compra real é habilitada por esta entrega.
- Sem alteração de configuração de produção, compra no jogo, implantação ou merge em `main`. Reversão por commit desta entrega após verificar as dependências.

## 2026-11-23 — Autonomia Total A1/A2/A3/A7/A9, validações conservadoras e diagnóstico de histórico (G0)

**Objetivo:** fortalecer a consistência de escolhas e registros de investimento e disponibilizar uma sondagem manual, somente leitura, da estrutura do histórico de voos. Entrega incremental vinculada a `docs/ROADMAP_AUTONOMIA_TOTAL.md`.

### Implementação

- **A1 — `src/engine_selection.py`:** após a troca de variante, a preferência é resolvida novamente sobre o conjunto relido no jogo. Mudança de identificador, velocidade ou consumo da opção efetivamente escolhida bloqueia a confirmação da configuração. Ampliados os testes de reconstrução de opções e alteração da preferência durante a leitura.
- **A2 — `src/owned_hub_research_ingestion.py`:** a persistência de uma página de pesquisa usa comparação de cursor, fingerprint do snapshot e fingerprint do catálogo sob lock. Um resultado calculado antes de outra ingestão ter avançado ou trocado o catálogo é descartado, evitando que a gravação concorrente substitua estado mais recente. Foram incluídos testes de corrida, recuperação e continuidade.
- **A3 — `src/expansion_economics.py`:** o ranking auditável rejeita custos ou componentes malformados e resultados em que ROI anual informado diverge do ROI recalculado com lucro diário e investimento total. Os testes cobrem divergência, alteração adversarial e desempates.
- **A9 — `src/game_source_probe.py` e `src/bot.py`:** consulta manual da estrutura de `fleet_details.php` por ID positivo explícito. A sessão Selenium continua restrita ao worker do bot, e a consulta compartilha a fila com o diagnóstico já existente, respeitando a janela ociosa. São retornadas somente contagens e indicadores sanitizados sobre linhas, candidatos a identificador, timestamps e possível paginação. Os indicadores `flight_identity_verified`, `complete_history_verified` e `financial_ledger_verified` permanecem falsos: o diagnóstico **não é** uma fonte contábil nem comprova completude para calibração.
- **A7 — `src/web.py` e `assets/web/index.html`:** endpoint `POST /api/admin/flight-history-probe`, com autorização existente, `X-AM4`, corpo JSON estrito e bloqueio de token por URL. A nova seção colapsada do painel recebe um ID explícito, mostra o relatório sanitizado em português/inglês e não faz consultas automáticas. O DOM utiliza `textContent` para dados variáveis.
- **Qualidade — `tests/test_engine_selection.py`, `tests/test_owned_hub_research_ingestion.py`, `tests/test_expansion_economics.py`, `tests/test_game_source_probe.py`, `tests/test_bot_game_source_probe.py`, `tests/test_game_source_probe_web.py`, `tests/test_game_source_probe_ui.py`:** testes de contratos, concorrência, erros, permissões, restrição do worker, sanitização do HTML, interação e tradução de interface.

### Verificação e limites

- Testes direcionados dos sete módulos de regressão aprovados durante o desenvolvimento. Ruff (`src` e `tests`), compilação Python e `git diff --check` aprovados nesta rodada; a suíte Windows geral foi executada separadamente, excluindo apenas o teste do instalador que depende de permissões POSIX.
- **Gate G0 com fixtures/DOM simulado.** Não houve validação com histórico real autenticado, nem prova de IDs únicos de voo, timestamps absolutos, paginação exaustiva ou custos financeiros conciliáveis. Portanto A9 ainda não pode recalibrar previsões automaticamente. Permanecem pendentes os aceites completos de A1–A9 e gates G1–G5, incluindo seleção final do motor, base/hub de entrega, demanda, cobertura, executor idempotente e política de gasto em ambiente real.
- Nenhuma compra no jogo, alteração de configuração de investimento, mensagem Telegram, implantação no servidor ou merge em `main`. A PR #44 permanece separada. Para reverter, inspecionar as dependências da branch e reverter o commit desta entrega. Se a consulta falhar, o painel mantém a falha visível e nenhum diagnóstico autoriza gastos.

## 2026-11-23 — Autonomia Total A2, invalidação de candidatos de catálogos anteriores (G0)

**Objetivo:** impedir que a pesquisa paginada mantenha candidatos removidos do catálogo de aeronaves, motores, hubs ou destinos após uma alteração estrutural, mesmo enquanto a evidência antiga ainda esteja dentro do prazo de validade.

### Implementação e evidências

- **`src/owned_hub_research_feed.py`:** o identificador do layout inclui IDs e códigos dos hubs, IDs e nomes dos modelos, além dos IDs e rótulos das variantes de motor. O identificador continua estável quando muda apenas preço, demanda ou horário da observação, permitindo percorrer páginas sem reiniciar a cada ciclo.
- **`src/owned_hub_research_ingestion.py`:** a gravação da página reaproveita candidatos de ciclos anteriores somente se o layout persistido corresponder ao layout recebido. Uma alteração de composição descarta as páginas da geração anterior e repovoa a pesquisa progressivamente.
- **`tests/test_owned_hub_research_ingestion.py`:** regressões para descarte de modelos removidos, inclusão de novo modelo, continuidade após alteração apenas de preço e sensibilidade a renomeação de hub e modelo. A retomada entre ciclos e após reinício continua coberta.

### Verificação, limitações e reversão

- Testes direcionados de ingestão e feed aprovados (65). Ruff, `compileall src` e `git diff --check` aprovados. Suíte Windows geral executada com exclusão do teste de instalação Linux específico de POSIX.
- **Gate G0 com fixtures e caches simulados.** A pesquisa derivada permanece somente leitura e com compra inelegível. Ainda faltam evidência autenticada de demanda residual, preço final por variante, disponibilidade de rota, vínculo permanente da frota e cobertura conclusiva dos hubs. Gates G1–G5 e os critérios completos das fases A2–A9 permanecem pendentes.
- Sem compra no jogo, envio de Telegram, implantação em produção ou merge na `main`. Reversão por commit específico na branch de autonomia, após verificar dependências. A PR #44 segue independente.

## 2026-11-23 — Autonomia Total A3/A4/A7, detalhamento auditável do planejador (G0)

**Objetivo:** tornar a comparação global de investimentos legível no painel, incluindo as premissas econômicas, alternativas por hub e os motivos que impedem decisões quando a pesquisa estiver inconclusiva.

### Implementação

- **`assets/web/index.html`:** novo painel expansível **Planejador de Expansão** na área **Próxima aeronave por base**, consumindo a API autenticada `GET /api/investment/audited-expansion`. Exibe ranking A4 por hub, origem/destino, modelo, motor, assentos Y/J/F, investimento total, lucro diário incremental, payback, ROI, score, diferença para a segunda opção, caixa disponível, custo de aeronave e motor, taxas, hangar, receita, combustível, CO₂, margem de segurança, cenários de stress, horário da evidência e identificador do snapshot.
- A ausência de alternativas A4 mantém os resultados financeiros auditados A3 visíveis com indicação explícita de que o planejamento global continua pendente. Bloqueios e exclusões da política A4 são apresentados com descrições em português e inglês, inclusive compromissos não conciliados, evidências vencidas ou ausentes, cobertura incompleta, limites esgotados e hangar sem vaga.
- Dados inválidos, resposta sem garantias de somente leitura e registros financeiros inválidos bloqueiam a apresentação de uma decisão positiva. Valores externos são apresentados como texto para evitar interpretação de HTML fornecido pelo jogo.
- **`tests/test_hubs_dashboard_ui.py`:** teste de renderização em DOM simulado com Node, cobrindo ranking A4, decomposição de custos, score, evidência, stress, tradução de bloqueios e exclusões, fallback A3, registros inválidos e campos ausentes.

### Verificação, pendências e reversão

- Testes dirigidos do painel e do registro auditável aprovados (17). Ruff, compilação Python e `git diff --check` aprovados. Suíte Windows geral executada com exclusão do instalador Linux específico de POSIX.
- **Gate G0 com fixtures e DOM simulado.** A coleta autenticada ainda precisa provar demanda residual, variantes e preços finais dos motores, disponibilidade das rotas, cobertura integral, compromissos e slots dos hubs. As fases A2–A9 e gates G1–G5 seguem em desenvolvimento e homologação. A consulta não autoriza gasto.
- Sem compra no jogo, envio de Telegram, implantação em produção ou merge em `main`. Para reversão, examinar dependências e reverter o commit correspondente na branch de autonomia. A PR #44 permanece independente.

## 2026-11-23 — Autonomia Total A3/A4/A7, registro auditável de oportunidades (G0)

**Objetivo:** persistir evidências financeiras por perfil e apresentar no painel o planejamento global sem revalidar artificialmente observações vencidas.

### Implementação

- **`src/audited_economics_registry.py`:** registro atômico `audited_expansion.json` por perfil, com `snapshot_id`, evidência de cenário, motor, rota, custos e margem utilizados por `evaluate_expansion_economics`. Cada leitura recalcula a avaliação com o horário corrente, mantendo bloqueios por expiração. Casos conflitantes permanecem auditáveis e inelegíveis; conteúdo adulterado e perfis divergentes são recusados.
- **`src/audited_economics_registry.py`:** evidências independentes de caixa, compromissos, cobertura e capacidade do hub podem ser associadas ao mesmo snapshot de A3. A4 revalida a origem e os identificadores desses controles antes de classificar propostas.
- **`src/web.py`:** novo `GET /api/investment/audited-expansion`, protegido pela autenticação existente, expõe avaliações, ranking A3, análise de portfólio A4 e motivos para `nao_comprar`, com `read_only=true` e `execution_available=false`.
- **`assets/web/index.html`:** seção **Próxima aeronave por base** apresenta resumo A3/A4, melhor combinação hub/modelo/motor/lucro quando houver evidência suficiente e aviso de compra bloqueada quando inconclusiva.
- **`tests/test_audited_economics_registry.py`:** oito cenários de idempotência, expiração, conflito, armazenamento inválido, isolamento entre perfis, vínculos de cobertura, autenticação HTTP e bloqueio conservador.

### Verificação, limites e reversão

- Suíte Windows `rtk bypass python -m pytest tests -q --ignore=tests/test_instalacao_linux.py` aprovada (saída final 100%, código 0). `python -m ruff check src tests` e `python -m compileall -q src` aprovados. Testes direcionados do painel e economia também aprovados.
- **Gate G0 com fixtures.** O registro ainda precisa de produtor autenticado de cenários completos, inclusive demanda residual, preço final por variante de motor, cobertura conclusiva e compromissos. O endpoint começa sem oportunidades aprovadas até que essas provas existam. A2–A9 e G1–G5 seguem pendentes, respeitados os seus critérios integrais.
- Não houve compra real, chamada de Telegram, implantação no servidor nem merge em `main`. Reverter o commit desta entrega na branch de autonomia após examinar dependências, mantendo a PR #44 separada. Não habilitar execução de investimentos a partir desta consulta.

## 2026-11-23 — Autonomia Total A2, rotação contínua com evidências renovadas (G0)

**Objetivo:** evitar que as leituras periódicas de preço, demanda ou motores reiniciem indefinidamente a pesquisa de um catálogo grande e impeçam a avaliação dos candidatos posteriores.

### Implementação e evidências

- **`src/owned_hub_research_feed.py`:** além do fingerprint completo de evidências usado pela paginação da interface, o feed expõe `layout_fingerprint` calculado pela ordem das identidades dos hubs, destinos, modelos e variantes de motor. Preço, demanda, horários e progresso de observação continuam alterando o fingerprint estrito da interface.
- **`src/owned_hub_research_ingestion.py`:** a retomada automática persiste os dois fingerprints. Ao renovar evidências mantendo a mesma ordem de combinações, o ciclo avança para a próxima página. Mudanças de composição, catálogo de motores, destinos ou modelos reiniciam no começo, evitando pular identidades novas. O cache antigo continua legível e se atualiza na próxima ingestão.
- **`tests/test_owned_hub_research_ingestion.py`:** regressão com alteração de preço e horário durante a varredura, seguida da inclusão de novo modelo, comprovando a rotação e o reinício seguro.

### Validação e limites

- Testes dirigidos (87), Ruff e compilação Python aprovados. Suíte geral Windows executada com exclusão do teste específico POSIX.
- **Gate G0 com fixtures.** Cobertura parcial continua sem comprovação de esgotamento das oportunidades reais. Faltam demanda residual, precificação final por motor, coleta externa autenticada e gates G1–G5. Nenhuma ação de compra, implantação ou merge na `main`.

## 2026-11-23 — Autonomia Total A2/A3/A7, ingestão persistente da pesquisa dos hubs próprios (G0)

**Objetivo:** conectar as observações já coletadas no ciclo do bot à análise da próxima aeronave, mantendo a distinção entre dados brutos para pesquisa e cenário comprovado de compra.

### Implementação e evidências

- **`src/owned_hub_research_ingestion.py`:** novo registro por perfil agrega páginas de `hub × rota × modelo × variante de motor` produzidas a partir de hubs próprios, demanda observada, cache de modelos e catálogo de motores. Preserva fonte, horários, evidências e pendências, com limite de armazenamento, atualização idempotente, retomada do cursor e expiração individual de cada origem de evidência.
- O cursor persistido passa a carregar o fingerprint da pesquisa. O registro conserva evidência por página e aceita migração de arquivos legados sem fingerprint. Contradições de mesmo horário ficam identificadas como pesquisas conflitantes até observação posterior. A retomada entre atualizações frequentes foi aprimorada na entrega seguinte.
- **`src/bot.py`:** ingestão acontece no ciclo regular após os coletores de demanda ou motores, quando as respectivas opções estão habilitadas, usando somente caches previamente observados. A ingestão não navega no jogo e não submete compras.
- **`src/hub_recommendations.py` e `src/web.py`:** `GET /api/hubs/recommendations` combina pesquisas verificadas com registros pendentes sem duplicar uma mesma combinação comprovada. Expõe fonte, demanda bruta, evidência, contagem de entradas e pendências. Pesquisas derivadas permanecem com `demand_remaining=null`, `financial={}`, `costs={}` e bloqueio `pesquisa_complementar_a_confirmar`.
- **`tests/test_owned_hub_research_ingestion.py`:** cobre isolamento de perfis, idempotência, validade temporal de provas independentes, conflitos, prioridade da pesquisa verificada, atualização do fingerprint, retomada e compatibilidade com cache legado.

### Validação e limites

- Testes direcionados de ingestão, feed e ranking aprovados, totalizando 87 testes. Ruff (`src`, `tests`), compilação Python e `git diff --check` passaram. A suíte geral Windows foi executada separadamente.
- **Gate G0 com fixtures simuladas.** Ainda faltam coleta autenticada e comprovação de demanda residual, custos totais, preço final de motor, disponibilidade de rota e cobertura conclusiva dos hubs. A2–A9 e gates G1–G5 permanecem pendentes. Nenhuma pesquisa derivada autoriza compra.
- Nenhuma aquisição no jogo, mensagem Telegram, implantação no servidor ou merge na `main`. A PR #44 segue separada.

## 2026-11-23 — Autonomia Total A2/A6, consistência de pesquisa externa e horários (G0)

**Objetivo:** impedir que amostras atrasadas ou contraditórias de rota/modelo/motor autorizem uma sugestão de expansão e preservar a precisão temporal dos dados no gate A6.

### Implementação e evidências

- **`src/hub_expansion.py`:** a pesquisa externa mantém somente a observação mais recente de cada combinação hub, modelo, motor e rota. Replays atrasados não substituem evidência nova. Leituras divergentes no mesmo instante são persistidas em quarentena por combinação, sinalizadas como `pesquisa_externa_conflitante` e resolvidas apenas por coleta posterior. As demais combinações continuam avaliáveis, preservando a leitura de estado legado.
- **`src/expansion_feasibility.py`:** A6 valida horários inteiros ou fracionários numéricos e finitos sem truncar milissegundos; horários inválidos, futuros ou expirados impedem a conclusão correspondente. O relógio padrão usa a precisão de `time.time()`.
- **`tests/test_hub_expansion.py` e `tests/test_expansion_feasibility.py`:** regressões de atraso de pesquisa externa, contradição após reinício, recuperação, isolamento por motor, substituição de cenário antigo persistido, provas fracionárias, horários inválidos e validade temporal por origem de evidência.

### Validação, pendências e reversão

- Testes dirigidos de A2/A6, suíte Windows `python -m pytest tests -q --ignore=tests/test_instalacao_linux.py`, Ruff, `compileall src` e `git diff --check` executados nesta entrega. O teste de instalação Linux requer ambiente POSIX.
- **Gate G0, com fixtures simuladas.** Ainda não existe produtor homologado para pesquisa de demanda residual em hubs externos nem certificação autenticada de cobertura completa e configuração final de motor. Fases A2–A9 e gates G1–G5 permanecem pendentes; nenhum resultado deste código habilita gasto no jogo.
- Nenhuma compra real, envio Telegram, implantação ou merge em `main`. Reversão pelo commit desta entrega na branch de autonomia, considerando dependências. PR #44 independente.

## 2026-11-23 — Autonomia Total A2, proveniência e quarentena do preço dos hubs (G0)

**Objetivo:** impedir que preços e pontos lidos antes de uma atualização do jogo substituam evidências mais recentes, preservando a rastreabilidade individual de cada campo e a cobertura real do catálogo.

### Implementação e evidências

- **`src/game_observations.py`:** a consulta do hub selecionado e a varredura incremental dos aeroportos encaminham o horário da segunda leitura estável do DOM. O horário registrado representa a coleta, inclusive quando o processamento posterior sofre atraso.
- **`src/hub_expansion.py`:** o catálogo aceita horários numéricos fracionários válidos e rejeita timestamps inválidos, futuros ou expirados. Preço e pontos possuem versões temporais independentes, protegidas contra respostas fora de ordem. Dados antigos podem atualizar um campo ainda mais antigo sem reduzir a validade de outro já atualizado.
- Contradições de preço ou pontos observadas no **mesmo instante** são colocadas em quarentena persistente. O ranking sinaliza os motivos `preco_hub_conflitante` e `pontos_hub_conflitantes` e mantém a compra inelegível até leitura comprovadamente posterior.
- Uma varredura completa atrasada não descarta aeroportos encontrados depois dela nem reivindica cobertura total. Uma página antiga também não restaura aeroportos excluídos por varredura completa mais nova. Os registros legados conservam a interface anterior.
- **`tests/test_hub_expansion.py` e `tests/test_game_observations.py`:** simulam ordem temporal, precisão subsegundo, conflitos e recuperação após reinício, independência de preço/pontos, timestamps inválidos, cobertura de varreduras completas e passagem do horário real pelos dois coletores.

### Validação, pendências e reversão

- Testes direcionados de catálogo e observações, suíte Windows `python -m pytest tests -q --ignore=tests/test_instalacao_linux.py`, Ruff (`src`, `tests`), compilação de `src` e `git diff --check` foram executados. O teste de instalação Linux exige ambiente POSIX.
- **Gate G0, somente fixtures e verificações locais.** A homologação autenticada de preços, pontos, rotas, demanda residual, motor final e custos permanece pendente. As fases A2–A9 e gates G1–G5 não estão concluídos. As mudanças não habilitam compra real.
- Sem execução de compra, mensagens Telegram, deploy no servidor ou merge na `main`. Reversão pelo commit desta entrega na branch de autonomia, conferidas as dependências. A PR #44 permanece independente.

## 2026-11-23 — Autonomia Total A2/A7, pesquisas inconclusivas e timestamps precisos (G0)

**Objetivo:** fazer as observações reais de demanda com precisão subsegundo chegarem à fila de investigação e explicitar por hub pesquisas sem resultado ou com demanda contraditória.

### Implementação e evidências

- **`src/owned_hub_research_feed.py`:** timestamps numéricos finitos de inventário, pesquisa de rota, mercado e motor são aceitos com precisão fracionária, desde que recentes. A fila conserva o horário da amostra e continua gerando apenas tarefas de investigação, com `purchase_eligible=false`.
- **`src/hub_expansion.py`:** `demand_research_snapshot()` lê amostras de demanda, tentativas de pesquisa e conflitos persistidos sob a mesma trava. Cada hub próprio tem horário/estado da tentativa mais recente e quantidade de rotas conflitantes. O método legado `demand_observations()` continua fornecendo só a lista de amostras.
- **`src/web.py` e `assets/web/index.html`:** `GET /api/hubs/recommendations` encaminha o progresso persistido ao feed, e o painel informa a última tentativa inconclusiva, pesquisas iniciadas e conflitos. Mudanças de evidência invalidam o cursor de paginação por fingerprint.
- **`tests/test_owned_hub_research_feed.py`, `tests/test_hub_aircraft_research.py` e `tests/test_hubs_dashboard_ui.py`:** testam caminho de timestamp fracionário até a fila, validade temporal, persistência de tentativas/conflitos, resolução e expiração, integração com a API e renderização segura da mensagem.

### Validação, pendências e reversão

- A suíte Windows `python -m pytest tests -q --ignore=tests/test_instalacao_linux.py` passou com código zero. Testes direcionados após as alterações finais também passaram. Ruff, `compileall src` e `git diff --check` concluíram sem falhas. O teste de instalação depende de ambiente POSIX.
- **Gate G0 com dados simulados.** G1–G5 continuam dependentes de observações reais de rota, demanda **residual**, cobertura conclusiva por hub e configuração final de motor e preço. A2–A9 permanecem parcialmente implementadas. Nenhuma amostra de tráfego bruto habilita compra.
- Sem aquisição no jogo, Telegram, implantação ou merge em `main`. Reversão pelo commit desta entrega na branch de autonomia após conferir dependências. A PR #44 permanece independente.

## 2026-11-23 — Autonomia Total A2/A7, proveniência temporal e quarentena da demanda (G0)

**Objetivo:** impedir que leituras de pesquisa de rota processadas fora de ordem substituam demanda mais recente e tornar contradições visíveis sem alimentar o planejamento com dados disputados.

### Implementação e evidências

- **`src/game_observations.py`:** a pesquisa de hubs próprios encaminha o horário da segunda leitura estável do DOM à persistência, preservando a data real da observação mesmo após atraso no processamento.
- **`src/hub_expansion.py`:** `record_demand()` aceita `observed_at` comprovado, preserva timestamps fracionários, recusa épocas inválidas/futuras/expiradas e compara a versão de cada rota antes de gravar. Uma amostra atrasada não altera destinos mais recentes, mas outros destinos legítimos de um lote parcial podem ser acrescentados. O cursor da tentativa só é marcado como observado se essa leitura não anteceder uma tentativa posterior.
- Demandas contraditórias no **mesmo instante** entram em quarentena por rota, inclusive após reinício, e deixam de aparecer no feed e no ranking. Um registro posterior comprovado libera a rota. Dados legados com timestamps inteiros continuam válidos. Persistências com amostra e marcador conflitante são interpretadas conservadoramente.
- **`assets/web/index.html`:** o painel de hubs próprios mostra o total de rotas com demanda contraditória e a quantidade em quarentena por hub, com tradução PT-BR/EN.
- **`tests/test_game_observations.py` e `tests/test_hubs_dashboard_ui.py`:** cenários simulados de leituras retardadas, substituições por destino, replay obsoleto, timestamps inválidos, conflito simultâneo, reinício, resolução posterior e exibição no painel.

### Validação, limites e reversão

- Testes direcionados de observações, fila e painel passaram. A suíte Windows `python -m pytest tests -q --ignore=tests/test_instalacao_linux.py` concluiu com código zero. Ruff (`src`, `tests`), `compileall src` e `git diff --check` passaram. O teste de instalação Linux depende de ambiente POSIX.
- **Gate G0, validação com fixtures.** Ainda faltam observações homologadas de demanda residual, cobertura integral por hub/rota/modelo/motor e preços finais no jogo autenticado. G1–G5 permanecem pendentes, assim como os demais requisitos de A2–A9. Demandas observadas continuam representando tráfego bruto, sem autorizar compra.
- Sem compra real, notificação Telegram, implantação ou merge em `main`. Reversão pelo commit desta entrega na branch de autonomia, considerando commits posteriores. A PR #44 permanece independente.

## 2026-11-23 — Autonomia Total A2/A3/A7, paginação consistente das pesquisas dos hubs (G0)

**Objetivo:** permitir investigar todas as combinações observadas de hub próprio × rota × modelo × variante de motor, inclusive quando o número de possibilidades ultrapassa o limite inicial de 40 itens, sem omissões nem duplicação entre páginas.

### Implementação e evidências

- **`src/owned_hub_research_feed.py`:** a fila de pesquisa agora suporta `offset` e fingerprint de evidência, com salto para a rodada adequada de alternância entre hubs. Retorna `total_candidates`, `page_size`, `next_offset` e `cursor_reset`. Mudança ou redução do snapshot invalida a posição antiga e reinicia na primeira página.
- **`src/web.py`:** `GET /api/hubs/recommendations` encaminha `research_offset` e `research_snapshot` para o feed. Requisições continuam autenticadas e somente leitura; parâmetros fora do limite são tratados como início da pesquisa.
- **`assets/web/index.html`:** o painel oferece navegação anterior/próxima, mostra a quantidade total de possibilidades e a faixa apresentada, conserva o cursor entre consultas periódicas e descarta respostas HTTP atrasadas que poderiam sobrescrever uma página recente. Traduções em inglês incluídas.
- **`tests/test_owned_hub_research_feed.py`, `tests/test_investment_policy_web.py`, `tests/test_hubs_dashboard_ui.py` e `tests/test_hub_aircraft_research.py`:** novas verificações para páginas de tamanho variável, hubs com cargas desiguais, motores múltiplos, unicidade, invalidação por mudança de evidência, controles acessíveis, ordem de respostas HTTP e autenticação do endpoint.

### Validação, limites e reversão

- Testes direcionados passaram. A suíte Windows `python -m pytest tests -q --ignore=tests/test_instalacao_linux.py` terminou com código zero. Ruff e `compileall` passaram. O cenário Linux permanece dependente de ambiente POSIX.
- **Gate G0, com provas simuladas.** A paginação permite consultar pesquisas pendentes, mas ainda falta observação autenticada e validada de todos os hubs, motores, preços finais e demanda residual. G1–G5 permanecem pendentes. Todas as propostas dessa fila mantêm `purchase_eligible=false`.
- A entrega é reversível por commit da branch de autonomia, observadas as dependências subsequentes. Nenhuma compra real, envio Telegram, implantação ou merge em `main` foi realizado. A PR #44 permanece independente.

## 2026-11-23 — Autonomia Total A2, invalidação de auditoria dinâmica da frota (G0)

**Objetivo:** impedir que paginação móvel e alterações simultâneas da frota produzam uma certificação falsa de cobertura completa.

### Implementação e evidência

- **`src/route_registry.py`:** exige coerência entre página atual, total de páginas, contagem anunciada e limite de 20 aeronaves. Um identificador de execução de auditoria é invalidado permanentemente se os totais, IDs, tamanho de página ou metadados de linhas mudam durante a mesma varredura. Um novo identificador inicia uma auditoria independente.
- Certificações históricas comprovadas permanecem disponíveis para consultas posteriores. Se for constatada contradição posterior na mesma execução anteriormente certificada, essa certificação é revogada. `partial` continua explicitamente verdadeiro para o snapshot corrente, sem inferência de hub-base por aeronave.
- **`tests/test_route_registry.py`:** cobre página incompleta, variação de número de páginas, mudança de quantidade de aeronaves sem mudança de total de páginas, linhas com metadados divergentes, reobservação alterada da mesma página, retomada segura e novo ciclo íntegro.

### Validação, pendências e reversão

- Validação local com fixtures simuladas e testes de regressão no Windows. A confirmação de cobertura na sessão real, com aeronaves chegando durante a paginação, continua pendente.
- **Gate G0.** A2 exige ainda prova real de paginação dinâmica e inventário das bases. G1–G5 seguem pendentes. Nenhuma ação no jogo, Telegram, implantação ou merge em `main` foi efetuada. Reversão pelo commit de integração na branch de autonomia, conferindo dependências posteriores.

## 2026-11-23 — Autonomia Total A1/A2, fidelidade temporal do catálogo de motores (G0)

**Objetivo:** preservar a observação autenticável da variante exata durante processamento tardio, sem perder motores válidos da fila de pesquisa quando a leitura do DOM tem precisão subsegundo.

### Implementação e evidência

- **`src/game_observations.py`:** a segunda leitura estável do DOM agora captura e encaminha o horário real da leitura, inclusive se o processamento posterior for atrasado. O registro continua sendo uma leitura de catálogo, sem submissão de compra.
- **`src/engine_catalog.py`:** aceita timestamps numéricos finitos e precisos, rejeita épocas inválidas, futuras ou expiradas, impede que observações antigas substituam uma leitura mais nova após reinício e prioriza identidade do modelo explicitamente verificada em conflitos de mesmo instante. Contradições equivalentes não substituem o catálogo anterior, mantendo as variantes por modelo.
- **`src/owned_hub_research_feed.py`:** reconhece horário fracionário recente de catálogo de motores, preservando a validação inteira já aplicada às outras fontes de observação. Variante, preço final e demanda seguem pendentes até comprovação específica.
- **`tests/test_engine_catalog.py` e `tests/test_owned_hub_research_feed.py`:** testes cobrem atrasos, reinício, conflitos no mesmo instante, motor com três opções, timestamps inválidos e conexão do catálogo fracionário ao feed.

### Validação, pendências e reversão

- Testes dirigidos de motor, observações e fila concluídos com código zero; Ruff (`src`, `tests`) e `compileall src` passaram. A homologação de leitura real, preços finais e correspondência com o seletor do jogo segue pendente.
- **Gate G0.** Apenas fixtures e testes locais. G1–G5 permanecem pendentes. Nenhuma compra, mensagem Telegram, implantação ou merge em `main` foi realizada.
- **Reversão:** reverter o commit desta entrega na branch de autonomia após avaliar dependências. A PR #44 permanece independente.

## 2026-11-23 — Autonomia Total A2/A3, pesquisa de rotas com escala potencial (G0)

**Objetivo:** não descartar precocemente combinações hub × rota × modelo que excedem o alcance direto, mas podem ser viáveis após pesquisa de escala intermediária.

### Implementação e evidência

- **`src/owned_hub_research_feed.py`:** combinações fora do alcance direto permanecem na fila com `direct_range_sufficient=false` e pendência `escala_e_trechos_a_confirmar`. Alcance desconhecido é `null`, preservando a pendência existente. Alcance suficiente é `true`.
- **`tests/test_owned_hub_research_feed.py`:** valida a preservação de modelos com alcance insuficiente, a exclusão de IDs contraditórios e a ausência de autorização de compra para todas essas linhas.

### Validação, pendências e reversão

- Testes dirigidos da fila concluídos com código zero. Ainda precisam ser pesquisados escala permitida, comprimento de pista, alcance por trecho e viabilidade econômica. A fila segue somente leitura e `purchase_eligible=false`.
- **Gate G0.** A evidência é simulada, sem pesquisa real de escala. G1–G5 seguem pendentes, sem alteração de comportamento de compra. Reversão pelo commit desta entrega na branch de autonomia.

## 2026-11-23 — Autonomia Total A2/A3, persistência temporal e quarentena de cenários (G0)

**Objetivo:** impedir que pesquisas assíncronas ou páginas do jogo entregues fora de ordem substituam evidências mais recentes e que duas leituras contraditórias com o mesmo horário produzam uma recomendação de compra.

### Implementação e evidência

- **`src/hub_aircraft_research.py`:** o armazenamento por perfil, hub, rota não direcionada, modelo e variante explícita de motor passou a comparar o `observed_at` da pesquisa antes da substituição. Uma amostra atrasada ou com horário ausente/inválido é ignorada se existe pesquisa mais recente, sem regravar o arquivo. Leituras equivalentes do mesmo instante são idempotentes mesmo com direção invertida da rota ou diferença de maiúsculas no nome do modelo.
- Quando duas amostras divergem em evidência de pesquisa, custos ou projeção e compartilham o timestamp mais recente, o registro conserva ambas (no máximo duas). **`rank_next_aircraft()`** já identifica `pesquisas_conflitantes` e bloqueia a recomendação. Uma nova observação cronologicamente posterior substitui o conjunto em conflito. As variantes de motor e perfis continuam isolados.
- **`tests/test_hub_aircraft_research.py`:** regressões verificam atraso, horários ausentes/inválidos, idempotência, contradição persistida após reabrir o registro, bloqueio efetivo no ranking e liberação após nova pesquisa.

### Validação, pendências e reversão

- Testes direcionados `test_hub_aircraft_research.py` e `test_hub_recommendations.py` passaram. A suíte Windows `pytest tests -q --ignore=tests/test_instalacao_linux.py` concluiu com código zero. Ruff (`src`, `tests`), `compileall src` e `git diff --check` passaram em 23/11/2026. Os testes do instalador Linux permanecem para ambiente POSIX.
- **Gate G0.** As leituras são simuladas e os cenários armazenados continuam sem coleta real completa de demanda residual, modelo, motor, custo final ou autorização de aquisição. G1–G5 seguem pendentes. Nenhuma compra, mensagem Telegram, implantação ou merge em `main` foi realizado.
- **Risco e reversão:** registros da mesma combinação podem conter duas linhas quando existir contradição no mesmo instante. Clientes devem respeitar o bloqueio já implementado no ranking. Reverter esta entrega pela branch de autonomia caso seja necessário restaurar a política anterior de substituição. A PR #44 permanece independente.
- **Paralelismo:** duas tentativas de mobilizar agentes para motores e cobertura da frota foram recusadas pelo limite de threads do ambiente. A implementação desta entrega foi executada pelo coordenador.

## 2026-11-23 — Autonomia Total A1/A5, correlação do checkout e recibos exclusivos (G0)

**Objetivo:** reduzir o risco de confirmar uma configuração observada em painéis diferentes e de usar a mesma encomenda para conciliar duas intenções de investimento.

### Implementação e evidências

- **`src/game_source_probe.py`:** `aircraft_checkout_diagnostics.model_hub_correlated` só fica verdadeiro quando existe um painel único `#acModel` com ID de modelo explícito, o seletor de hub consistente está contido nesse painel e o estado AJAX está comprovadamente ocioso, sem carregador ou `aria-busy`. O sanitizador valida essas condições novamente e trata respostas contraditórias como inconclusivas. A sondagem continua somente leitura e `price_verified` permanece falso.
- **`tests/test_game_source_probe.py`:** novos cenários Node.js e Python cobrem hub fora do painel do modelo, múltiplos painéis, ausência/atividade de jQuery, carregamento, modelo inválido, seleção ausente e campos falsificados ou com tipos incompatíveis.
- **`src/investment_journal.py`:** sob transação SQLite `BEGIN IMMEDIATE`, uma confirmação de aeronave consulta comprovantes `CONFIRMED` anteriores do mesmo perfil. Um `purchase_id` já vinculado a outra intenção é recusado. A regra também protege a conciliação após timeout e reinício.
- **`tests/test_investment_journal.py` e `tests/test_investment_executor.py`:** validam a recusa de comprovante reutilizado, a preservação do estado `SUBMITTED`/`UNKNOWN`, a retomada e duas compras simuladas que usam recibos diferentes.

### Limites e reversão

- **G0.** A prova é de DOM simulado, journal SQLite e gateway de simulação. Identidade, hub, motor, preço final e recibo ainda dependem de homologação com uma conta autenticada. A compra real permanece fora do executor novo. G1–G5 continuam pendentes.
- Reverter o commit desta entrega na branch de autonomia após inspecionar commits dependentes. Nenhum clique de compra, Telegram, implantação ou merge em `main` foi executado.

## 2026-11-23 — Autonomia Total A2/A7, integridade e cobertura das pesquisas por rota (G0)

**Objetivo:** fazer a fila de estudos de hubs representar cada rota observada uma única vez, sem inflar pesquisas por dados duplicados ou escolher arbitrariamente entre observações contraditórias.

### Implementação e evidências

- **`src/owned_hub_research_feed.py`:** agrupa as observações válidas por par `hub próprio × destino`. Leituras repetidas com os mesmos dados são deduplicadas. Leituras com horários diferentes usam apenas a mais recente. Se duas observações diferentes têm o mesmo horário máximo, a rota fica em quarentena até chegar observação mais nova, mantendo as demais rotas pesquisáveis. A seleção independe da ordem das amostras recebidas.
- O resultado `research_queue` agora expõe `conflicted_routes` total e por hub, além de contar `sampled_routes` por rota única. Corrigida também a contagem de `sampled_hubs`, que era inflada ao criar entradas vazias para hubs sem pesquisa durante a montagem de `hub_coverage`.
- **`assets/web/index.html`:** a tela de hubs informa quantas rotas têm amostras conflitantes. Uma base com conflito e nenhuma amostra aproveitável aparece como **Pesquisa de rota inconclusiva**. Traduções PT-BR/inglês incluídas. Valores e nomes continuam inseridos como texto.
- **`src/hub_registry.py` e `assets/web/index.html`:** a API de hubs também encaminha a última auditoria integral histórica comprovada pelo registro de rotas. O painel apresenta sua data e total de IDs únicos, mantendo o inventário atual explicitamente parcial. A ausência do campo em registros anteriores é aceita.
- **`tests/test_owned_hub_research_feed.py` e `tests/test_hubs_dashboard_ui.py`:** cobrem duplicatas idênticas, observações novas/antigas fora de ordem, conflitos no mesmo timestamp, recuperação por leitura posterior, continuidade da pesquisa em outros hubs, contagem de bases efetivamente amostradas e apresentação dos conflitos.
- **`tests/test_hub_registry.py`:** comprova que um histórico de auditoria integral não altera `partial_fleet` nem transforma registros antigos em contagem atual.

### Validação, pendências e reversão

- Testes direcionados dos dois arquivos e suíte Windows com exclusão do instalador específico POSIX concluíram com código de saída zero em 23/11/2026. Ruff, `compileall` de `src` e `git diff --check` passaram. A prova é de testes locais com fixtures simuladas, sem coleta adicional autenticada do jogo.
- **G0 — entrega local testada, aguardando homologação.** A cobertura continua parcial. Demanda bruta não comprova demanda residual, disponibilidade de rota, vínculo de base nem lucro real. A1, demais dependências A2/A3 e gates G1–G5 permanecem pendentes. Nenhuma compra, mutação no jogo, Telegram, implantação ou merge na `main` foi efetuado.
- **Compatibilidade e reversão:** campos de conflito são aditivos e a UI aceita respostas antigas que não os incluam. A fila continua somente leitura com `purchase_eligible=false`. Reverter o commit desta entrega na branch `codex/autonomia-a0-a1-20261122`, observando dependências posteriores; a PR #44 permanece sob avaliação independente.

## 2026-11-23 — Autonomia Total A1, snapshot atômico de identidade e motores (G0)

**Objetivo:** impedir que substituições AJAX do formulário de encomenda misturem variantes de uma aeronave com a identidade observada em outra leitura.

### Implementação e evidências

- **`src/game_observations.py`:** o catálogo de motores passou a ler `data-model-id` e grupos `select`/`radio` em uma única execução síncrona de JavaScript. O script reutiliza a inspeção de motores empregada no fluxo existente, exige painel `#acModel` único e descarta estados com carregador ou atividade AJAX. O conjunto completo de identidade e opções precisa coincidir nas duas leituras antes da gravação.
- Quando há `data-model-id`, a coleta exige correspondência exata com o modelo solicitado. Ausência da identidade explícita continua registrada como evidência pendente; divergência ou troca de motor entre leituras impede a substituição do catálogo anterior. A pesquisa apenas lê o formulário e não seleciona motor nem envia pedidos.
- **`tests/test_engine_catalog.py`:** regressões simulam mudança do modelo ou das opções durante o intervalo entre leituras, respostas estáveis divergentes e preservação dos registros. Um teste executa o JavaScript real em Node.js contra DOM simulado com motores, troca de identidade, carregador e AJAX ativo.

### Verificação, limites e reversão

- Testes direcionados do catálogo/seleção e suíte Windows excluindo o instalador POSIX concluíram com código de saída zero em 23/11/2026. Ruff em `src scripts tests`, compilação Python em `src scripts` e `git diff --check` também concluíram sem erros. O teste de instalação Linux permanece para ambiente POSIX.
- **Gate G0.** Os cenários exercitam objetos e DOM simulados. A presença e semântica de `data-model-id` no jogo, o preço final de cada motor, a escolha de `#hubSelection`, a demanda residual e a confirmação independente de uma encomenda continuam sem homologação autenticada. Não houve compra, alteração de configuração, envio Telegram, implantação ou merge na `main`.
- A alteração está restrita à coleta somente leitura e aos testes, mantendo o fluxo de compra legado. A reversão pode ser feita pelo commit correspondente da branch `codex/autonomia-a0-a1-20261122`, com conferência das dependências posteriores.

## 2026-11-23 — Autonomia Total A1/A5, diagnóstico estrutural do checkout de aeronaves (G0)

**Objetivo:** localizar com segurança possíveis fontes do preço final e da configuração de motor no formulário de encomenda, facilitando a homologação da etapa que ainda impede uma compra baseada em plano.

### Implementação e evidência

- **`src/game_source_probe.py`:** a sondagem administrativa de somente leitura do DOM passa a incluir `aircraft_checkout_diagnostics`. O retorno identifica o número de painéis `#acModel`, o ID numérico explícito do modelo quando o painel é único, contagens de `select`/`radio`, controles com nome relacionado a motor, botão de compra e alerta de saldo. Registra também contagens de nós com atributos `data-price`, `data-final-price`, `data-total-price` ou identificadores/classes que mencionem preço/custo, além da presença de formato de moeda e de atributos de preço estritamente numéricos.
- A observação inspeciona apenas a tela já aberta pelo processo proprietário do Selenium. Valores monetários, etiquetas livres, matrícula, HTML, credenciais, cookies e demais atributos não são retornados. O sanitizador Python aplica uma lista fixa de campos e seletores, limita contagens e força `price_verified=false` inclusive em respostas adulteradas.
- **`tests/test_game_source_probe.py`:** regressões executam o JavaScript sobre um DOM de exemplo em Node.js com candidatos de preço, seletores de motor, texto confidencial simulado e campos de identificação. Testes adicionais rejeitam IDs contraditórios, números inválidos, valores arbitrários e tentativas de injetar campos extras na resposta.

### Verificação, pendências e reversão

- Testes direcionados, suíte Windows, Ruff, compilação e `git diff --check` são validados no ambiente local antes do commit desta entrega.
- **G0 — instrumento de diagnóstico testado com dados simulados.** Seletores de preço são hipóteses estruturais a confirmar em sessão autenticada. Contagens de candidatos e indicadores de moeda não certificam preço final nem vínculo ao motor selecionado. É necessário comparar a configuração real antes/depois da seleção, revalidar o checkout e cruzar modelo, motor, hub, caixa e pedido com observações independentes. G1–G5 continuam pendentes.
- Nenhum pedido, clique de compra, implantação, notificação Telegram ou merge foi executado. `main` e PR #44 permanecem preservadas. Reversão pelo commit desta entrega na branch de autonomia, observando dependências posteriores.

## 2026-11-23 — Autonomia Total A1/A5, confirmação da seleção de hub na sondagem DOM (G0)

**Objetivo:** obter um sinal de leitura consistente do hub selecionado no formulário de encomenda de aeronaves, para apoiar a futura pré-validação do destino de entrega do plano.

### Implementação e evidência

- **`src/game_source_probe.py`:** a sondagem existente da sessão Selenium, já restrita ao processo proprietário do navegador, passa a retornar `aircraft_order_hub_selection` com quantidade de seletores, opções, opções efetivamente selecionadas, estado e ID numérico do hub quando a seleção visível é consistente. Confere o valor atual de `#hubSelection` com a propriedade DOM `option.selected`, a unicidade do seletor e da opção, e a disponibilidade do controle. Seleções ausentes, duplicadas, desabilitadas, sem ID válido ou inconsistentes permanecem inconclusivas. O sanitizador Python valida os limites, elimina atributos não autorizados e mantém separadamente a evidência de `statusData`.
- **`tests/test_game_source_probe.py`:** exercita a seleção atual, atributo HTML `selected` desatualizado, opção divergente, IDs duplicados, controles desabilitados, múltiplos seletores e respostas maliciosas. A sondagem somente lê elementos DOM e retorna um objeto limitado. O endpoint administrativo existente continua sendo a entrada autenticada para execução no trabalhador dono do Selenium.

### Verificação, limites e reversão

- Testes da sondagem, do fluxo no trabalhador, da API administrativa e regressões gerais no Windows, além de Ruff, compileall e `git diff --check`, são executados antes da publicação desta entrega.
- **G0 — contrato de diagnóstico local.** As propriedades foram verificadas contra DOM simulado em Node.js. O seletor real do jogo, a atribuição de hub após troca de motor e a confirmação do destino de entrega ainda exigem observação autenticada. O campo `dom_consistent` confirma apenas a coerência da seleção presente na tela. Nenhuma compra é liberada, e a confirmação independente do pedido, do motor e do preço continua pendente.
- Não houve compra, envio de Telegram, implantação, alteração da `main` ou da PR #44. Reverter o commit desta entrega na branch de autonomia, verificando dependências posteriores.

## 2026-11-23 — Autonomia Total A9, métricas operacionais auditáveis no painel (G0)

**Objetivo:** visualizar a evolução das intenções de investimento e a cobertura da pesquisa de oportunidades por perfil, conservando como desconhecidos os resultados reais que ainda não possuem fonte autenticada independente.

### Implementação e evidências

- **`src/investment_journal.py`:** `audit_metrics()` produz uma leitura consistente e isolada por perfil das intenções persistidas, seus estados, tipos, tentativas, custo **planejado** reservado e confirmado na janela e eventos de recuperação de estados incertos. O diário local comprova transições de intenção, mas não comprova despesa, entrega ou lucro no jogo.
- **`src/expansion_metrics.py`:** `build_expansion_metrics()` combina o diário com a cobertura registrada pela pesquisa de hubs, total de alternativas avaliadas pelo planejador e relatórios conclusivos do contrato de calibração. Perfis diferentes e planos duplicados não contribuem para precisão financeira. Campos sem evidência conservam `null` e causas de bloqueio explícitas.
- **`src/web.py` e `assets/web/index.html`:** `GET /api/investment/metrics` exige a autenticação existente e disponibiliza métricas somente leitura. A aba **Hubs e Aeronaves** apresenta intenções, reservas previstas, cobertura de pesquisa e precisão ainda pendente, com traduções PT-BR/inglês e apresentação por `textContent`.
- **`tests/test_expansion_metrics.py`, `tests/test_investment_policy_web.py` e `tests/test_hubs_dashboard_ui.py`:** regressões de reinício e isolamento por perfil, janela temporal, estados incertos e reconciliação, pesquisa parcial, calibração verificada e duplicada, autenticação HTTP e renderização da interface.

### Testes, limitações e reversão

- Testes direcionados das métricas, journal, política HTTP e sintaxe da interface, além de Ruff, compilação Python e `git diff --check` executados localmente. A suíte Windows geral exclui o instalador específico de Linux e é conferida antes do commit.
- **G0 — implementação local.** As métricas de submissão e de custo são obtidas exclusivamente do diário local. Não há ainda observações autenticadas de entrega, valor efetivamente desembolsado, voos individuais, razão financeira completa ou gasto evitado. Não há calibração conectada ao ciclo de produção e nenhum valor desses campos é inventado pelo painel. A cobertura de pesquisa continua dependente da coleta e homologação A1/A2/A3, portanto G1–G5 permanecem pendentes.
- Não houve compra real, envio Telegram, implantação, merge na `main` ou alteração da PR #44. A política permanece desligada por padrão. Reverter o commit desta entrega na branch de autonomia, considerando eventuais dependências posteriores.

## 2026-11-23 — Autonomia Total A8, aquisição simulada de hub em duas etapas (G0)

**Objetivo:** demonstrar, sem acessar o jogo, a reserva durável de uma intenção de compra de hub e a reconciliação independente de propriedade antes do planejamento de uma aeronave para a nova base.

### Implementação e fontes

- **`src/hub_purchase.py`:** `SimulatedHubExecutor` usa o diário persistente `InvestmentJournal` no ambiente de simulação, lock por perfil, limites por compra/dia, aprovação explícita ou flag separada de hub, pré-validação imediata do hub selecionado, custo final, caixa, reserva e pontos. `SimulatedHubGateway` mantém um registro local de resultados simulados em SQLite para provar retomada sem reenviar a compra. Resultado incerto fica `UNKNOWN`/`SUBMITTED` até conciliação, sem novo envio. `validate_aircraft_after_hub()` só libera a **etapa de análise** da aeronave após `CONFIRMED`, novo snapshot, identidade de perfil/hub e inventário de hubs próprio com cobertura completa e timestamp posterior à confirmação.
- **`tests/test_hub_purchase.py`:** sete cenários de testes exercitam aprovação, seleção, preço, saldo, pontos, isolamento, recusa, timeout, queda de processo, retomada sem compra duplicada, propriedade verificada e bloqueio de planejamento com inventário parcial/antigo.

### Gates e limitações

- **G0 — contrato simulado, testado localmente.** O gateway é fictício e não possui Selenium, integração HTTP, acesso ao jogo ou execução de compra real. A etapa dois produz somente o resultado `ready` para pesquisa e validação futura. Ainda faltam coleta real de preços/seleção do hub, confirmação de posse pós-compra no jogo, recálculo da demanda, rotas, motor e caixa, e autorização individual para o estágio G5.
- **Reversão:** remover `src/hub_purchase.py` e `tests/test_hub_purchase.py` ou reverter o commit desta entrega. Os defaults de investimento, o código legado de compras e as opções de produção permanecem inalterados. Nenhuma compra, implantação ou envio Telegram foi executado.

## 2026-11-23 — Autonomia Total, rastreio por hub, auditoria global A4 e relatórios A6 (G0)

**Objetivo:** conectar os contratos de evidência de A1/A2 com um planejador de portfólio global baseado nos resultados auditados de A3 e tornar o relatório de expansão A6 verificável e seguro para publicação futura.

### Implementação e fontes

- **A1/A2 — `src/owned_hub_research_feed.py`:** a fila rejeita catálogos com divergência entre `model_id` e `observed_model_id`, indicação inválida de identidade verificada ou `selected_engine_id` incompatível com a variante selecionada. A evidência do motor expõe os IDs observados sem transformar preço desconhecido em aprovação. O mapa `hub_coverage` relaciona todos os hubs próprios, inclusive aqueles sem amostra, com contagem, última observação e situação individual. Todas as coberturas seguem `partial`.
- **A2/A7 — `assets/web/index.html`:** a fila de pesquisas apresenta cobertura por hub e quantidade de rotas observadas, com estados distintos para pesquisa iniciada e ausente. Os nomes provenientes das observações são inseridos com `textContent`, e a interface inclui os textos PT-BR/inglês.
- **A4 — `src/portfolio_planner.py`:** `compare_audited_portfolio()` classifica alternativas globais de A3 por hub, rota, modelo, variante de motor e configuração Y/J/F, apresenta melhor proposta por base e motivo da classificação. O orçamento é limitado por caixa comprovado, compromissos incrementais reconciliados, reserva, limite por compra, gasto de ciclo/período e vagas verificadas. Exige procedência vinculada a perfil/snapshot, validade temporal, varredura e pesquisa comprovadas. Combina lucro, eficiência do capital, retorno e dimensões opcionais de risco, confiança e diversificação com pesos explícitos. Ausência ou contradição de provas resulta em comparação inconclusiva e decisão `nao_comprar`.
- **A6 — `src/expansion_reporting.py`:** relatório somente leitura separa varredura conclusiva de hubs próprios, catálogo externo insuficiente e recomendações externas comprovadas. Até três alternativas exibem hub, modelo, motor, rota, custos, retorno, fontes e horário UTC das observações. Evidência aninhada de outro perfil ou snapshot não pode entrar no ranking. Um catálogo externo incompleto gera `pesquisa_externa_pendente`, sem aviso de recomendação. A deduplicação de mensagens ignora simples atualização do horário e percebe alteração relevante de fonte.

### Testes, gates e limites

- Regressões acrescentadas em `tests/test_owned_hub_research_feed.py`, `tests/test_hubs_dashboard_ui.py`, `tests/test_portfolio_planner.py` e `tests/test_expansion_reporting.py`. A suíte Windows completa com exclusão do instalador POSIX, Ruff, compilação Python e `git diff --check` finalizaram com código de saída zero em 23/11/2026.
- **G0 — implementação testada localmente.** A4 ainda requer produtores de observações reais para caixa, compromissos futuros, vagas, demanda residual e custos. A6 requer inventário externo verificável e varredura própria conclusiva. A identidade do modelo/motor, o preço após seleção, a associação permanente de base, `#hubSelection` e a pesquisa de rotas ainda dependem de verificação em sessão autenticada. Nenhuma homologação no jogo, compra, mensagem Telegram, implantação, promoção à `main` ou alteração da PR #44 foi realizada nesta entrega.
- **Compatibilidade e reversão:** o comparador existente `compare_portfolio()` permanece disponível aos chamadores atuais e o comparador auditado é uma entrada adicional. Novas decisões continuam somente leitura com `execution_available=false`. A política `[investment]` permanece desligada por padrão. Reverter pelo commit da branch `codex/autonomia-a0-a1-20261122`, verificando dependências posteriores. Arquivos envolvidos são os quatro módulos e quatro testes descritos acima, além deste histórico.

## 2026-11-23 — Autonomia Total, economia auditável, conciliação segura, painel e calibração A3/A5/A7/A9 (G0)

**Escopo:** aprofundar os módulos independentes do planejador global, ampliar a resistência do executor simulado a concorrência e reinício e deixar evidentes os impedimentos na interface.

### Implementação

- **A3:** `src/expansion_economics.py` calcula, em memória e em modo somente leitura, investimento por componente, receita Y/J/F, combustível, CO₂, custos recorrentes observados, margem conservadora, caixa após a aquisição, lucro líquido diário, ROI e payback. A função `evaluate_expansion_economics()` cruza identidade, perfil, snapshot, procedência, idade e unidades dos insumos com o avaliador de viabilidade existente. Custos recorrentes desconhecidos, demanda residual não comprovada ou divergência entre cálculo e pesquisa financeira bloqueiam a conclusão. `rank_expansion_economics()` compara cenários completos entre hubs, rotas, motores e assentos com desempate determinístico, descartando identidades contraditórias.
- **A5:** `InvestmentJournal` rejeita planos com perfil divergente e permite recuperar estados `SUBMITTED` apenas sob guarda exclusiva comprovada, colocando-os em `UNKNOWN` sem repetir pedidos. `SimulatedInvestmentExecutor.reconcile()` adquire o bloqueio antes de recuperar, verifica a existência da intenção e devolve o estado confirmado por outra execução quando uma transição concorrente já terminou. Testes exercitam múltiplas threads, timeout, reinício, corrida de confirmação e modo análise sem mutações.
- **A7:** a fila de pesquisa de hubs próprios apresenta cartões responsivos por rota/modelo/motor, identidade do detalhe do jogo, estado de seleção da variante, custos e retornos ainda não comprovados, razões individuais do bloqueio e restrições da política. O conteúdo de origem externa é renderizado como texto, com rótulos PT-BR e inglês. Os números permanecem desconhecidos até aparecer evidência verificável.
- **A9:** `src/forecast_calibration.py` oferece `compare_forecast()` para confrontar previsão e desempenho diário quando entrega, intenção, confirmação de compra, voos independentes e razão financeira do jogo estiverem vinculados ao mesmo perfil, aeronave, motor, hub e rota. Exige janelas completas e consecutivas e fonte de custos identificável. Resultados inconclusivos não geram métricas ou ajuste. A calibração ainda não foi conectada ao ciclo automático.

### Testes, cobertura e próximas dependências

- Incluídos testes específicos dos contratos financeiros, da calibração, da interface e de idempotência do executor. A validação de integração usa a suíte Windows com exclusão do arquivo de instalação específico de Linux, Ruff, compilação e `git diff --check`.
- **Gate G0 permanece ativo.** Os novos cálculos e a comparação de previsões são contratos puros e dependem de produtores de evidência real que ainda precisam ser integrados e homologados. É necessário comprovar demanda residual, custo final após escolha do motor, `#hubSelection`, base permanente individual, cobertura integral e saldo/pedidos em sessão autenticada. A fonte atual de histórico não apresenta os IDs independentes de voos e o livro completo de custos exigidos pela calibração. A compra real de aeronaves e hubs continua condicionada aos gates G3–G5.
- A PR #44 apresenta conflitos de integração nos arquivos `README.md`, `assets/web/index.html`, `src/fleet.py`, `src/web.py` e `tests/test_settings_workspace.py`. Ela e a `main` permanecem preservadas para reconciliação própria. Nenhuma compra no jogo ou implantação no servidor integra esta entrega. Para reversão, usar `git revert` do commit correspondente, considerando eventuais commits dependentes.

## 2026-11-23 — Correlação explícita da identidade do modelo no catálogo de motores A1 (G0)

**Objetivo:** impedir que uma resposta AJAX de detalhe pertencente a outro modelo seja atribuída ao pedido pesquisado, preservando os dados comprovados anteriormente.

- A coleta read-only relê de forma estável `#acModel[data-model-id]` ao lado das variantes de motor. Quando o atributo existe e coincide exatamente com o ID solicitado no mercado, registra `observed_model_id` e `model_detail_identity_verified=true`. Ausência do atributo mantém a identidade pendente e a fila de investimentos bloqueada. Valor divergente, inválido ou instável descarta a nova leitura integralmente, sem substituir o último catálogo válido.
- O registro persistente valida a correlação entre `model_id`, `observed_model_id` e a flag de verificação. Snapshots legados sem atributo continuam utilizáveis com `model_detail_identity_verified=false`. Em todos os casos, `engine_prices_verified=false` e `purchase_eligible=false` continuam obrigatórios.
- Novas regressões cobrem correspondência, ausência, divergência e corrupção da evidência em disco. Verificação local com testes direcionados de catálogo e feed, Ruff e `git diff --check` aprovada.
- **Estado G0.** A presença de `data-model-id` é uma possibilidade prevista no diagnóstico DOM. Ainda falta observar seu preenchimento em sessão autenticada, confirmar o preço final por variante, selecionar o hub explicitamente e comprovar a demanda residual. Nenhuma compra, implantação, merge ou alteração da `main` foi realizada. Reversão por `git revert` do commit desta entrega após conferir dependências.

## 2026-11-23 — Autonomia Total, catálogo incremental de variantes de motor A1/A2/A3 (G0)

**Objetivo:** alimentar a fila de pesquisa dos hubs próprios com opções de motores observadas no formulário de cada modelo, sem inferir preço de aquisição e sem executar compras.

### Implementação

- Novo `EngineCatalogRegistry` por perfil, em `engine_catalog.json`, com validação de IDs e seleção, persistência atômica, validade de três dias e rotação incremental entre modelos, inclusive após tentativas inconclusivas.
- `collect_aircraft_engine_catalog()` consulta até `engine_models_per_cycle` modelos por ciclo na sessão Selenium já utilizada pelo bot. A leitura de modelos e motores é repetida para evitar registrar DOM instável. O processo abre as telas existentes de pesquisa e detalhe, lê `select`/`radio` e encerra o popup. Nenhuma opção de motor é selecionada e nenhum pedido é enviado.
- `build_owned_hub_research_queue()` combina hubs próprios, destinos, modelos e variantes observadas. Cada tarefa expõe ID e nome do motor, disponibilidade, velocidade/consumo quando informados e pendências individuais. Evidência vencida, conflitante ou ausente resulta em pesquisa pendente. Todos os cenários permanecem `purchase_eligible=false`.
- `GET /api/hubs/recommendations` utiliza o catálogo por perfil. O painel mostra as variantes e seu estado de disponibilidade, com texto protegido e tradução PT-BR/inglês.
- A coleta usa o interruptor independente `collect_engine_catalog=off` por padrão. O limite pode ser configurado na aba Aeronaves de 1 a 10 modelos por ciclo, com valor padrão 2. Testes cobrem estrutura de seleção, disponibilidade, dados inválidos, idempotência da consulta, rotação, preservação do histórico, perfis e apresentação do painel.

### Testes, limites e reversão

- Validação local em Windows com `python -m pytest -q --ignore=tests/test_instalacao_linux.py`, `python -m ruff check src scripts tests`, `python -m compileall -q src scripts` e `git diff --check`. Testes do instalador Linux continuam separados para execução POSIX.
- **G0, implementação local testada.** O AJAX de detalhe do modelo é conhecido no código existente, mas ainda falta confirmar em sessão autenticada a identidade exibida no formulário, múltiplos motores por modelo e a forma de obter o preço final após a escolha. Os campos `model_detail_identity_verified=false` e `engine_prices_verified=false` registram essas limitações. Faltam igualmente prova da demanda residual, custos completos, associação de base e cobertura conclusiva da frota para avançar A3–A9.
- Não houve compra no jogo, implantação, notificação externa, merge na `main` ou alteração da PR #44. A nova política de investimento segue desligada. Caso seja necessário reverter, usar `git revert` no commit desta entrega após conferir dependências posteriores.

## 2026-11-23 — Autonomia Total, fila observável de pesquisa por hub próprio A2/A3 (G0)

**Escopo:** transformar observações já disponíveis de hubs próprios, destinos pesquisados e catálogo de aeronaves em uma fila reproduzível de combinações para pesquisa posterior, com limites explícitos de evidência.

### Implementado

- `load_market_evidence()` expõe a data real de leitura e a validade de três dias do catálogo de aeronaves, preservando o contrato anterior de `load_market()`. O preço do modelo em cache permanece uma referência de catálogo e não equivale ao preço confirmado da variante de motor.
- `HubExpansionRegistry.demand_observations()` fornece amostras recentes de demanda dos hubs comprovadamente adquiridos, filtrando por identidade, origem e idade. Não altera o registro de amostras e mantém a pesquisa original sem tratar tráfego bruto como demanda residual.
- `build_owned_hub_research_queue()` produz uma fila determinística com alternância entre hubs, verificando identidades, distância, alcance conhecido, idade das fontes e modelos contraditórios. Restringe a quantidade de itens e informa quando há mais possibilidades. Cada combinação registra a origem e o horário da evidência, além das pendências de motor, preço final, demanda residual, pista, rota, configuração de assentos, encargos, rentabilidade e cobertura da frota.
- `GET /api/hubs/recommendations` inclui `research_queue`. A seção **Próxima aeronave por base** exibe as combinações pendentes e a cobertura parcial em um painel expansível. As mensagens são exibidas como texto e possuem tradução PT-BR/inglês.
- Testes específicos cobrem catálogo ausente, desatualizado, futuro e corrompido, observações restritas a hubs próprios, entradas contraditórias, valores numéricos extremos, limites de fila, alternância entre bases e invariantes de compra desabilitada. Teste JavaScript verifica a visualização dos pendentes e o tratamento de texto não confiável.

### Validação e pendências

- Verificações locais de pytest Windows, Ruff, compileall e `git diff --check` acompanham esta entrega.
- **G0 ativo.** A fila constitui tarefas de pesquisa, com `coverage=partial`, `read_only=true` e `purchase_eligible=false`. Ela não grava cenários completos automaticamente, não prova rotas livres, demanda residual, compatibilidade de pista ou preço por motor e não habilita nenhuma compra. Para fechar A2/A3, falta conectar leitores reais do jogo para esses campos, persistir cenários com dados financeiros verificáveis e homologar o fluxo em sessão autenticada.
- Nenhuma compra, alteração no jogo, envio de Telegram, implantação no servidor, merge na `main` ou alteração da PR #44 faz parte desta entrega. As flags de compra da nova política continuam desligadas.

## 2026-11-23 — Autonomia Total, releitura integral contra movimentação de aeronaves A2 (G0)

**Escopo:** impedir que a contagem constante de rotas produza um falso certificado de cobertura quando aeronaves trocam de página durante a auditoria.

### Implementado

- `audit_routes_live_pages()` relê todas as páginas de uma varredura integral antes de persistir qualquer registro do lote. Confere identidade e conteúdo das linhas contra a primeira leitura, inclusive da página inicial após sua restauração, e descarta o lote completo se houver divergência ou falha de navegação.
- Auditorias incrementais continuam parciais; a segunda passagem é exigida quando o ciclo reuniu todas as páginas. Testes reproduzem troca de aeronaves entre páginas e durante a restauração mantendo a mesma quantidade de rotas. Verificam que o registro anterior permanece intacto. O cenário estável de 11 páginas confirma que a releitura realmente ocorreu.

### Validação e limitações

- Testes direcionados de auditoria paginada e registro de rotas aprovados em Windows. A suíte Windows, análise estática e compilação são executadas antes do commit.
- **G0 permanece ativo.** Duas passagens coerentes reduzem falsos positivos observáveis, mas a interface paginada não oferece snapshot transacional garantido. São necessárias evidências em sessão autenticada para homologar a cobertura e assegurar o uso das rotas no planejamento. Não houve compras, implantação, merge na `main` ou alteração da PR #44.

## 2026-11-23 — Autonomia Total, consistência de motores, auditoria e custos A1/A2/A3 (G0)

**Escopo:** fechar ambiguidades encontradas na seleção de motores, na certificação de cobertura da frota e na estimativa de lucro com preços de mercado incompletos.

### Implementado

- **A1:** a preferência `default` passa a ler o motor efetivamente selecionado em controles `select` ou `radio`, sem alterar o formulário. Quando não há seleção comprovada, o comprador interrompe a encomenda. Preferências por maior velocidade ou menor consumo agora exigem desempate determinístico por métrica observada; empate integral ou ausência da métrica necessária bloqueiam a escolha.
- **A2:** a auditoria de páginas registra `page_ids_verified` e só certifica uma página com uma identificação única e válida por linha visível. Capturas com IDs duplicados, malformados ou com lista parcial de observações deixam a cobertura inconclusiva, mesmo que a deduplicação produza uma contagem aparentemente correta. IDs numéricos com zero à esquerda deixam de ser aceitos como identidades inequívocas de aeronave.
- **A3:** `estimate_route()` recusa lucro projetado quando o preço de combustível ou de CO₂ é nulo, ausente ou não positivo. `rank_candidates()` também interrompe a classificação nesses casos, evitando uma seleção por demanda que pareça financeiramente comprovada. A classificação legada por demanda com modelo não cadastrado continua disponível quando ambos os preços são válidos.
- Testes de regressão cobrem seleção padrão, indisponibilidade de motores, empates, dados faltantes, páginas duplicadas, alias numérico, observações parciais e custos desconhecidos.

### Validação e limitações

- As verificações foram executadas em Windows com `python -m pytest -q --ignore=tests/test_instalacao_linux.py`, `python -m ruff check src scripts tests`, `python -m compileall -q src scripts` e `git diff --check`. A suíte POSIX fica a cargo do ambiente Linux. Os testes de regressão utilizam HTML/observações simulados.
- **G0 permanece ativo:** falta validar o seletor real de cada modelo, o preço final após mudança de motor, o hub de entrega e a cobertura da frota com a sessão autenticada. Um modelo cujo modal não exponha um seletor identificável será bloqueado pelo novo comportamento `default`; essa compatibilidade precisa ser homologada antes de implantação. A auditoria de páginas ainda não prova consistência atômica se a frota variar durante a pesquisa. Estimativas econômicas continuam dependentes de demanda, capacidade e custos comprovados.
- Não houve compra real, envio ao Telegram, implantação, merge na `main` ou alteração da PR #44. As novas flags de investimento permanecem desligadas. Reversão pelo `git revert` do commit associado, após conferir dependências posteriores.

## 2026-11-23 — Autonomia Total, mapa de progresso de demanda por hub A2 (G0)

**Escopo:** tornar a pesquisa incremental auditável individualmente para cada hub próprio, inclusive quando uma tentativa não produz dados válidos.

### Implementado

- `HubExpansionRegistry.snapshot()` agora apresenta `demand_hub_progress` ordenado por ID de hub, com última tentativa, situação observada, quantidade de destinos amostrados, quantidade de amostras ainda válidas e horário da última amostra confirmada. Cada item informa `coverage=partial`. Tentativas sem resultados permanecem separadas de amostras já verificadas, inclusive após expiração ou reinício.
- A seção de novos hubs inclui painel expansível de pesquisa por base, mostrando o ID e a situação de cada uma. Entradas ainda não pesquisadas e últimas buscas inconclusivas são identificadas sem converter ausência de dados em demanda inexistente. Conteúdo dinâmico é exibido como texto, preservando segurança contra HTML não confiável. Traduções PT-BR/inglês foram incluídas.
- Os testes de snapshot verificam ordem determinística, tentativas inconclusivas, amostras preservadas e envelhecidas. O teste JavaScript do painel verifica os estados por hub e a apresentação dos dados.

### Validação e limitações

- Testes direcionados de observação, expansão e interface aprovados em Windows, além de Ruff e `git diff --check`. A suíte geral e a compilação fazem parte da validação do commit desta entrega.
- **G0 continua ativo.** O mapa indica somente o progresso das buscas e as amostras confirmadas, sem evidência de cobertura completa de todas as rotas, opções de aeronave ou motores. Não houve compra, alteração do jogo, notificação enviada, implantação no servidor, merge na `main` ou mudança na PR #44. Reversão por `git revert` do commit, observadas as dependências posteriores.

## 2026-11-23 — Autonomia Total, rotação resiliente de demanda dos hubs próprios A2 (G0)

**Escopo:** corrigir a pesquisa incremental dos hubs próprios para que respostas inconclusivas ou interrupções no Selenium não mantenham o mesmo hub como prioridade indefinidamente.

### Implementado

- `src/hub_expansion.py` persiste um cursor de pesquisa por hub em `route_demand_attempts`, com horário, sequência monotônica e situação `inconclusive` ou `samples_observed`. O cursor é gravado antes da consulta AJAX e o sucesso posterior atualiza o mesmo registro de forma atômica. A rotação considera a tentativa mais recente e as amostras verificadas antigas, com desempate determinístico mesmo em ciclos executados no mesmo segundo. Registros legados continuam legíveis.
- `src/game_observations.py` reutiliza o registro para selecionar e pesquisar um hub por ciclo. Pesquisa vazia, DOM instável, inconsistência entre consulta e resultado ou exceção mantêm as amostras verificadas anteriores e avançam o cursor. Nenhuma ausência de resultado é convertida em demanda zero.
- O snapshot de expansão informa quantidade de hubs próprios, hubs tentados, tentativas inconclusivas, hubs com amostras e amostras recentes. O painel Hubs apresenta o progresso e avisa que a **cobertura de demanda continua parcial**, inclusive após consultar todos os hubs uma vez. As traduções PT-BR/inglês foram adicionadas.
- Testes exercitam alternância e persistência após reinício, empates de horário, expiração e preservação de amostras, dados de cursor inválidos, pesquisa inconclusiva, interrupção da pesquisa e renderização do painel.

### Validação e limites

- Testes direcionados de `test_game_observations.py`, `test_hub_expansion.py` e `test_hubs_dashboard_ui.py` aprovados em Windows. A suíte completa para Windows, Ruff, compilação e `git diff --check` acompanham o commit desta entrega.
- **Estado G0 — implementado e testado localmente, não homologado no jogo.** A alternância corrige a justiça do agendamento, mas ainda falta comprovar que cada consulta cobre todas as rotas relevantes do hub, que a leitura dos hubs externos é possível e que existe uma varredura conclusiva no mesmo snapshot. `demand_coverage` permanece `partial` e não autoriza recomendar ausência de oportunidades nem executar compras.
- Não houve compras reais, envio a Telegram, implantação, merge na `main` nem alteração da PR #44. As novas flags de investimento permanecem desligadas. Arquivos desta entrega: `src/hub_expansion.py`, `src/game_observations.py`, `assets/web/index.html`, `tests/test_game_observations.py`, `tests/test_hubs_dashboard_ui.py` e este histórico. Reversão por `git revert` do commit associado, após conferir dependências posteriores.

## 2026-11-23 — Autonomia Total, avisos de expansão A6 no ciclo (G0)

**Escopo:** integrar ao ciclo do bot o relatório conservador de expansão para novos hubs, com envio condicional pelo Telegram e controle durável de duplicidade por perfil.

### Implementado

- Novo interruptor `telegram_expansion=off` em `[options]`, disponível no painel de configurações Telegram e nas ajudas PT-BR/inglês. Exige também `planning_enabled` e Telegram geral habilitados. O ciclo reutiliza os relatórios existentes de hubs próprios, pesquisa e expansão, evitando uma segunda leitura desnecessária dos mesmos snapshots.
- `src/expansion_alerts.py` compõe o hash do snapshot de evidências e usa a verificação A6 de `build_expansion_report`. Pesquisa incompleta, cobertura parcial ou falta de recomendação comprovada não geram mensagem. A deduplicação persistida em SQLite registra tentativas, respeita alterações materiais e cooldown e só confirma a entrega após retorno positivo do cliente Telegram.
- Mensagens incluem o perfil quando aplicável. Antes do envio, a integração confere o limite de 4.000 caracteres imposto pelo cliente existente. Uma atualização que ultrapassa o limite permanece sem confirmação e não é enviada truncada, preservando integridade de custos e tags HTML.
- `Telegram.send_now()` aceita `silent` opcional e mantém o comportamento público anterior por padrão. Falha de envio não bloqueia as demais rotinas do ciclo.

### Evidência e dependências

- Validação com mocks de relatórios e Telegram, incluindo flags desligadas, cobertura inconclusiva, deduplicação, alteração material, falha seguida de nova tentativa, isolamento de perfil, atualização grande e compatibilidade de `send_now`. A suíte de testes Windows excluindo apenas `tests/test_instalacao_linux.py`, Ruff e compilação foram executadas com sucesso.
- **Estado G0, implementação testada localmente.** Não houve envio a Telegram real, homologação de pesquisas completas no jogo, compra de aeronave ou hub, implantação no servidor, alteração da `main` ou da PR #44. Se uma mensagem alcançar a API, mas o cliente perder a resposta, a nova tentativa pode repetir o aviso. A confirmação de entrega é a resposta observada do Telegram, sem garantia de entrega exatamente uma vez.
- A6 depende da comprovação de cobertura de todos os hubs próprios e cenários externos completos por hub, modelo, motor, rota e custos. A coleta atual de demanda e preços não produz sozinha esses cenários. A flag permanece desligada, com reversão possível pelo `git revert` do commit desta entrega após conferir alterações posteriores.

## 2026-11-23 — Autonomia Total, limites adicionais A7 e pontuação global A4 (G0)

**Escopo:** completar a configuração de critérios de rentabilidade e de priorização de compras no painel Hubs e ampliar a reserva de intenções no executor fictício.

### Implementado

- Política `[investment]` por perfil com quantidade máxima de aquisições em 24 horas, lucro diário mínimo e payback máximo. Os números têm limites e validação estrita no arquivo de configuração, na API de gravação e no formulário Hubs, com traduções PT-BR/inglês. Zero nos critérios de lucro e payback significa ausência do filtro; zero na quantidade máxima impede a execução simulada.
- Pesos individuais de lucro absoluto, eficiência de capital, risco, confiança e diversificação configuráveis e persistidos por perfil. Defaults 60/40/0/0/0 preservam a classificação anterior. O comparador global expõe contribuições de pontuação e só utiliza risco/confiança/diversificação quando há evidência normalizada, recente, vinculada à mesma origem, hub e, quando pertinente, rota, modelo e motor. Evidência opcional ausente exclui o candidato afetado e mantém a comparação inconclusiva.
- A consulta de recomendações aplica os critérios salvos. Configuração inválida é explicitamente sinalizada na comparação como `politica_invalida`. Cenários duplicados com observações contraditórias são descartados de forma conservadora.
- O diário de intenções calcula aquisições reservadas e confirmadas por perfil. O executor **simulado** barra uma nova intenção quando o limite de aquisições ou de gasto da janela de 24 horas foi atingido, inclusive com reservas ainda abertas.
- O ranking de A4 incorpora a exposição das intenções abertas do diário como obrigação local conhecida. Cenários acima do caixa restante após essas reservas são excluídos. O relatório e o painel expõem somente um **teto superior** de caixa, mantendo a conciliação de outras compras, entregas e compromissos do jogo como pendente. Falha na leitura do diário é sinalizada ao planejador.
- Testes ampliados para leitura de defaults, configuração HTTP e formulário, critérios globais, prova de métricas opcionais e limitação de aquisições fictícias.

### Validação e dependências

- Validados em Windows em 23/11/2026: `rtk bypass python -m pytest -q --ignore=tests/test_instalacao_linux.py` (100%, exit code 0), `python -m ruff check src scripts tests`, `python -m compileall -q src scripts` e `git diff --check` (todos com exit code 0). O teste do instalador POSIX foi excluído apenas por incompatibilidade de plataforma. O executor permanece fictício, o portfólio permanece somente leitura e o gate de liberação segue em **G0**.
- Não existe ainda uma fonte real homologada que forneça índices de risco, confiança e diversificação. Pesos positivos nesses critérios deixam candidatos sem evidência pendentes. Continuam necessárias a auditoria completa dos hubs próprios e da frota, cálculo econômico comprovado, seleção autenticada de motor e `#hubSelection`, reconciliação com compras do jogo, aprovação e envio pelo Telegram, compra efetiva de aeronave e de hub e calibração A9. Não houve compra, implantação ou merge na `main`.

## 2026-11-23 — Autonomia Total, política de investimento no painel A7 (G0)

**Escopo:** primeira entrega de controles de investimento por perfil na aba Hubs, sem conectar o planejador à execução real, em `codex/autonomia-a0-a1-20261122`.

### Implementado

- `GET /api/investment/policy` apresenta modo, limites em dinheiro do jogo, preferências legadas, versão da configuração e motivos do bloqueio G0. `POST /api/investment/policy` exige perfil autenticado, cabeçalho de ação, valores inteiros e booleanos estritos, campos completos e revisão otimista para impedir sobrescrita de outra sessão. Alterações são persistidas em `[investment]` e ficam isoladas da compra legada.
- A aba Hubs recebe formulário com habilitação de planejamento, compras independentes de aeronaves e hubs, modos somente analisar/aprovar/autônomo, tetos por compra e por dia, status do bloqueio e acesso aos demais parâmetros. O formulário suporta PT-BR/inglês, telas menores e evita converter campos numéricos vazios em gasto zero.
- `POST /api/investment/stop` desliga planejamento e as duas novas opções de compra, além de `options.autobuy_aircraft`, sob o mesmo lock de configuração. A rotina legada `order_aircraft()` confere novamente essa última chave imediatamente antes do clique de encomenda para respeitar uma suspensão durante a pesquisa do mercado. A interrupção é persistida por perfil.
- Testes HTTP reais validam autenticação, recusa de token na query para ações financeiras, entradas inválidas, concorrência de versão, persistência e parada. Testes de interface e de encomenda validam controles e ausência de clique após suspender compras.

### Validação e próximas dependências

- Validar com `python -m pytest -q --ignore=tests/test_instalacao_linux.py`, `python -m ruff check src scripts tests`, `python -m compileall -q src` e `git diff --check` em Windows. A exclusão do instalador POSIX corresponde à plataforma de execução. Testes de interface também utilizam Node.js quando disponível.
- **Permanece G0:** opção de gasto nova não aciona o jogo mesmo quando o operador a habilita. A7 ainda requer visão financeira completa, alertas e aprovações específicas. Ausência de fontes reais A1–A6 e homologação do executor A5 bloqueiam G1–G5. O botão de suspensão cobre **novas compras de aeronaves e hubs**, incluindo o comprador legado. Outras automações de gasto têm controles na aba Parâmetros.
- Nenhuma compra real, implantação, merge na `main` ou mudança na PR #44. Reversão por `git revert` do commit associado após conferir dependências posteriores.

## 2026-11-23 — Autonomia Total, avaliação de expansão A6 (G0)

**Escopo:** investigar novos hubs somente após demonstrar cobertura completa e recente de oportunidades nos hubs próprios, na branch `codex/autonomia-a0-a1-20261122`.

### Implementado

- `src/hub_expansion.py` preserva cenários legados e recebe múltiplas combinações independentes de hub, rota, modelo e variante de motor. Cada opção exige evidência específica e recente de preço, pontos, demanda externa, viabilidade de rota, custo por componente e resultado financeiro. O motor é identificado pelo ID real informado na pesquisa, sem inferência pelo nome.
- `src/expansion_feasibility.py` considera a prova de varredura completa dos hubs próprios, a integridade do catálogo externo e a disponibilidade financeira antes de emitir uma avaliação de expansão. A conclusão permanece `inconclusivo` quando faltar cobertura ou comprovação. O relatório pode priorizar os hubs já adquiridos ou classificar oportunidades externas com evidências válidas.
- `src/expansion_reporting.py` gera um resumo HTML para Telegram com até três candidatos, custos e obstáculos, além de um mecanismo SQLite de reivindicação e confirmação de alerta para deduplicação por conteúdo e intervalo. O relatório ainda não é enviado automaticamente ao Telegram.
- `GET /api/hubs/expansion` expõe a decisão e o painel Hubs apresenta ranking, custos de hub/aeronave/motor/rota/hangar, retorno e justificativas. A interface distingue explicitamente preço com e sem motor incluído.
- Testes unitários cobrem custo de motor, evidências divergentes/desatualizadas, cobertura, priorização de hubs próprios, ordenação e deduplicação. Teste Node.js exercita o renderizador real de expansão, inclusive texto não confiável, estados inconclusivos e traduções.

### Validação e pendências

- Verificados em Windows: testes direcionados de expansão e painel (117 aprovações), `ruff check src scripts tests`, `compileall` e `git diff --check`. A suíte pytest Windows sem o teste de instalação POSIX terminou com sucesso e um teste ignorado. A verificação não constitui homologação do jogo.
- **G0 permanece ativo.** A prova de varredura autenticada e conclusiva de todos os hubs próprios (`game_hub_opportunity_scan`) ainda não é emitida pelo leitor atual. Também faltam dados reais da pesquisa de hubs externos, validação de preços e variantes em sessão autenticada e integração do envio Telegram. Ranking conclusivo e autorização de gastos dependem dessas evidências.
- Nenhuma compra real, envio Telegram, implantação no servidor, alteração da `main` ou da PR #44 ocorreu. As novas opções `[investment]` permanecem desligadas por padrão. A reversão requer `git revert` deste commit após conferir dependências posteriores.

## 2026-11-22 — Autonomia Total, execução simulada e recuperação A5 (G0)

**Escopo:** exercitar a cadeia de compras de aeronaves em ambiente isolado, com limites e conciliação, na branch `codex/autonomia-a0-a1-20261122`.

### Implementado

- **Executor simulado A5:** `src/investment_executor.py` percorre a aprovação da política, a reserva da intenção, a pré-checagem, o claim de envio e a confirmação de pedido. O gateway fictício modela aprovação, recusa, timeout e falha após o envio. Nenhum navegador, API do jogo ou comprador legado é acionado. A simulação aceita exclusivamente `simulation_checkout` e provas `simulation_order_list` ou `simulation_order_rejection`.
- **Separação persistente dos ambientes:** `InvestmentJournal(simulation=True)` usa, por padrão, `investment_simulation.sqlite3`, com metadado de ambiente que impede abrir um diário de jogo como simulado e vice-versa. Bancos de dados anteriores permanecem legíveis na modalidade real. A prova da simulação não pode confirmar uma compra real.
- **Exclusividade entre executores:** lock transacional por perfil em SQLite, com token de proprietário. A reivindicação de `SUBMITTED` exige esse lock e impede novo envio se houver outro pedido `UNKNOWN` ou `SUBMITTED` no perfil. Não existe expiração automática que libere o lock de um processo potencialmente ainda ativo.
- **Caminho único de submissão:** a transição genérica do diário não aceita `PRECHECKED → SUBMITTED`. A mudança exige `claim_submission()` sob o lock exclusivo do perfil, impedindo contornar a proteção por um chamador do diário.
- **Recuperação após falha:** uma queda simulada deixa o pedido `SUBMITTED` e o lock preservados. Após confirmar que o executor anterior parou, a rotina explícita de retomada libera o token conhecido, move envios pendentes para `UNKNOWN` e consulta o livro de pedidos fictícios. A confirmação posterior não executa um segundo envio. O gateway pode persistir esse livro em SQLite separado, permitindo reconstruir o leitor após reinício.
- **Recusa verificável e orçamento:** `SUBMITTED/UNKNOWN → FAILED` exige recusa e ausência de pedido comprovadas, recentes e compatíveis com perfil, hub, modelo, motor e rota. Os compromissos abertos e os pedidos confirmados nas últimas 24 horas entram no limite financeiro da política. Compra individual, saldo, compromissos, reserva e checkout continuam sujeitos à validação.
- **Livro fictício independente:** pedidos simulados aceitos e recusas simuladas usam registros distintos em SQLite. Uma tentativa com timeout pode ser posteriormente reconciliada como aceita ou recusada conforme o registro persistido, mesmo após reconstrução do leitor. Uma ordem aceita nunca é convertida artificialmente em recusa pela alteração do estado do gateway.
- **Tentativa novamente após dados corrigidos:** um plano `APPROVED` cuja pré-checagem falhou pode ser reavaliado com observação nova. Pedidos já submetidos, confirmados, recusados ou incertos não voltam a ser enviados.

### Validação e pendências

- Testes de simulação verificam confirmação, recusa comprovada, timeout, queda com livro de pedidos persistido, reinício, revalidação, isolamento de ambientes/perfis, lock concorrente, falta de comprovação de checkout e limites de gasto. A verificação de sintaxe, Ruff e a suíte Windows sem o teste de instalação POSIX acompanham esta entrega.
- **G0 continua ativo.** A5 ainda depende de observação autenticada e homologação do seletor `#hubSelection`, variantes de motor, custo final e confirmação independente no jogo. O executor de produção, botões de aprovação, autorizações remotas, integração Telegram e compra de hubs permanecem pendentes. Os testes demonstram a consistência do protocolo fictício e não autorizam G1/G2 ou gastos reais.
- Sem implantação no servidor e sem alteração da `main` ou da PR #44. A próxima integração técnica deve conectar os leitores autenticados somente leitura e provar a revalidação pós-AJAX antes de habilitar qualquer caminho de compra.

## 2026-11-22 — Autonomia Total, diário A5 e pré-checagem simulada (G0)

**Escopo:** iniciar a proteção transacional de futuras aquisições em `codex/autonomia-a0-a1-20261122`, mantendo execução real indisponível.

### Implementado

- **Diário persistente por perfil:** `src/investment_journal.py` mantém intenções em SQLite, com transações `BEGIN IMMEDIATE`, eventos auditáveis, identidade determinística de alvo e transições `PROPOSED → APPROVED → PRECHECKED → SUBMITTED → CONFIRMED` ou `UNKNOWN/FAILED`. Para aeronaves, o alvo é a combinação hub/rota. Uma escolha diferente de modelo, motor, custo ou snapshot para a mesma rota exige conciliação antes de reservar uma segunda intenção. Para hub, a identidade é seu ID. O registro é idempotente e conta submissões únicas.
- **Recuperação conservadora:** intenções `SUBMITTED` são colocadas em `UNKNOWN` quando a rotina explícita de recuperação é acionada após reinício. A retomada não libera uma segunda submissão. Confirmação de aeronave exige evidência recente da lista de pedidos do jogo com ID de compra, perfil, base, rota, modelo e motor iguais ao plano. A confirmação de hub requer evidência de alteração na propriedade do hub. O histórico armazena apenas campos de prova permitidos, evitando informações de sessão.
- **Pré-compra A5 inicial:** `src/investment_preflight.py` valida, sem mutações, identidade de perfil, snapshot recente, seleção confirmada de hub, origem/destino, modelo, motor, disponibilidade, demanda, capacidade, preço final com motor, caixa, reserva e compromissos verificados. Divergências ou ausências bloqueiam o sinal de pré-checagem. A função depende de evidências fornecidas por um futuro leitor de checkout autenticado.
- **Consulta operacional:** `GET /api/hubs/recommendations` inclui o estado somente leitura do diário, suas intenções em aberto e exposição estimada. Falha ao abrir o SQLite é representada por exposição **desconhecida**, preservando o relatório e sinalizando o impedimento. O painel de hubs apresenta contagem/exposição ou indisponibilidade. A exposição do diário é informativa e ainda não substitui a conciliação integral dos compromissos no planejador A4.
- **Testes simulados:** registro, replay, conflitos de plano, isolamento entre perfis, concorrência por uma única submissão, timeout/restart, quarentena, recusa e aceitação de provas independentes específicas ao plano, conservação da exposição e falhas de checkout por preço, motor, hub, caixa, compromissos e idade. Testes de API e renderização verificam a nova consulta.

### Pendências para avançar os gates

- O **G0 permanece ativo**. Não existe executor conectado ao botão de compra, confirmação autenticada de `#hubSelection` ou leitor de checkout homologado. Os testes utilizam observações simuladas, sem prova de compra real. Falta executar e homologar os fluxos de compra correta, compra recusada, timeout e retorno pós-restart com uma camada de execução simulada e com dados reais observados. `G1` e `G2` não foram liberados.
- O diário reserva apenas intenções locais. Antes de permitir gastos, o coordenador deverá conciliar caixa, pedidos pendentes, histórico de compras, alvos já presentes no jogo, limites e reservas financeiras. A transição para `PRECHECKED` deverá ser controlada pelo pré-voo integrado e a aprovação dependerá da política efetiva. O caso `UNKNOWN` exige reconciliação externa antes de qualquer nova tentativa.
- Nenhuma compra de aeronave/hub, implantação no servidor, alteração na `main` ou na PR #44 foi realizada. As flags `[investment]` permanecem desligadas por padrão. A reversão pode ser feita por `git revert` do commit desta entrega, após revisar dependências.

## 2026-11-22 — Autonomia Total, comparação global A4 inicial (G0)

**Escopo:** comparação somente leitura de oportunidades de compra entre todos os hubs e variantes de motor pesquisados. Continuação da branch `codex/autonomia-a0-a1-20261122`.

### Implementado

- **Planejador de portfólio:** `src/portfolio_planner.py` compara todos os candidatos físicos e financeiramente viáveis do relatório de hubs, incluindo múltiplos motores do mesmo modelo. O ranking usa lucro incremental diário normalizado (peso 60%) e lucro por capital normalizado (peso 40%), desempate determinístico e exposição das métricas para auditoria. Pode ser chamado com limites opcionais de lucro mínimo, payback e investimento por compra.
- **Integridade da comparação:** exclui cenários sem preço, lucro, IDs de rota/hub ou motor confirmados, duplicações contraditórias, custos inválidos e cenários fora dos limites conhecidos. A provisão de compromissos pendentes é subtraída do caixa apenas quando sua origem é explicitamente confirmada. Dados desconhecidos deixam a conclusão `inconclusivo`; nenhuma recomendação é tratada como autorização para gastar.
- **Web/API:** `GET /api/hubs/recommendations` agora inclui `portfolio`, com melhor cenário provisório, alternativas, pontuação, orçamento, exclusões e bloqueios de cobertura da pesquisa, frota ou compromissos. O painel de hubs mostra o melhor cenário global comparado e sinaliza conclusão pendente. A contagem foi renomeada para **Cenários viáveis** para diferenciar viabilidade de aprovação de compra.
- **Testes:** cenários entre hubs e motores, ordem de pesquisa embaralhada, repetição e conflito de observações, limitação de caixa após compromissos, limites financeiros, evidência desconhecida e renderização em Node.js. A comparação preserva os dados de entrada e permanece `read_only=true` com `execution_available=false`.

### Limites e próximos critérios

- A comparação utiliza os valores estimados pelos leitores/rankings existentes. **Dados de jogo autenticados para cobertura integral de pesquisa, custo final por motor e compromissos financeiros ainda não foram integrados**. Portanto a API atual retorna conclusão `inconclusivo`, inclusive quando exibe uma melhor alternativa provisória. Pesos são defaults do módulo e ainda não estão expostos nos ajustes do painel.
- Ausência de dados de hub externo, rota, hangar, despesas recorrentes ou pedidos pendentes não pode fundamentar a decisão final de compra. A otimização de múltiplas aquisições, concorrência pelo mesmo mercado, gerador de oportunidades, revalidação pré-compra e journal transacional permanecem pendentes nas fases A2–A5.
- Implementação local em G0, com cenários simulados. Nenhuma compra real, implantação, alteração na `main` ou alteração na PR #44 foi realizada. Reversão pelo commit desta entrega, preservando as flags `[investment]` desativadas.

## 2026-11-22 — Autonomia Total, primeira onda A0/A1/A2/A3 (G0)

**Escopo:** implementação incremental do `ROADMAP_AUTONOMIA_TOTAL.md` em `codex/autonomia-a0-a1-20261122`, preservando a `main` e a PR #44.

### Implementado

- **Contrato A0:** `src/opportunity_models.py` define a versão 1 da proposta de investimento somente leitura, com identidade de perfil e snapshot, hash reproduzível, cobertura comprovada por escopo, origem e prazo das evidências, IDs de hub/rota/modelo/motor, custos explícitos e motivos estruturados de bloqueio. Dados desconhecidos permanecem ausentes e impedem o estado `suggested`. Mesmo uma proposta sugerida retorna `approved=false` e não possui caminho de execução.
- **Política A0:** `src/investment_policy.py` expõe separadamente os modos `analyze`, `approval` e `autonomous`, limites por aquisição/dia e os interruptores independentes de aeronave e hub. As novas opções `[investment]` começam desativadas. `GET /api/hubs/recommendations` informa a política e mantém `execution_available=false` no gate G0. A antiga opção `[options] autobuy_aircraft` conserva seu valor e fluxo anteriores.
- **Motores A1:** `src/engine_selection.py` disponibiliza inventário somente leitura das variantes reais que o HTML explicita em `select` ou `radio`, identificadas pelo valor da opção, nome, disponibilidade, seleção e métricas observadas. A seleção explícita é revalidada após o evento de mudança, inclusive quando o DOM foi recriado. Divergências, opções desabilitadas, seletor ambíguo ou métricas ausentes causam bloqueio.
- **Pesquisa A2:** `src/hub_aircraft_research.py` distingue a mesma aeronave/rota/hub por `engine_id`, preserva os registros legados sem identificador, rejeita IDs malformados e mantém persistência isolada por perfil.
- **Ranking A3 inicial:** `src/hub_recommendations.py` avalia motores diferentes como candidatos independentes, com desempate estável. Uma variante explicitamente identificada só pode ser elegível quando o lucro e o preço final da aeronave estão vinculados ao mesmo `engine_id`, com confirmação de que o preço inclui o motor. Dados de outro motor não habilitam recomendação. O painel mostra a variante e informa que a nova política permanece em análise.

### Evidência, testes e limitações

- Os cenários dos testes são **simulados**. Nenhum novo modelo/motor/preço, hub de entrega ou compra foi homologado nesta onda em uma sessão autenticada do jogo. Nenhuma compra real, implantação ou alteração na `main` foi executada.
- Os testes dirigidos cobrem contrato de evidência, custos desconhecidos, vínculos entre motor/modelo e snapshot, registros por perfil, catálogo, troca de motor e inconsistências pós-AJAX, ranking e política desligada. `python -m ruff check src scripts tests`, `python -m compileall -q src scripts` e `git diff --check` passaram no Windows. A suíte completa Windows foi executada com exclusão do teste de instalação dependente de permissões POSIX em `tests/test_instalacao_linux.py`.
- A pesquisa atual ainda depende de captura comprovada de demanda residual, cobertura completa da frota e preço específico de cada motor. Não há seleção/validação real do hub de entrega `#hubSelection`, re-leitura de preço pós-AJAX ou confirmação de compra por identificadores independentes.
- A seleção de motor `default` do comprador legado permanece como antes, sem o contrato novo de pré-compra. Uma mudança nesse caminho exige validação do DOM e proteção de preço/hub para não introduzir regressão no comportamento que já está em produção.
- A transição G0→G1 depende de observações reais e recentes por modelo/motor/hub/rota. A0/A1/A2/A3 têm **implementação parcial testada localmente**, sem status de homologação ou implantação. O próximo bloco independente compreende integração dos leitores autenticados, geração de oportunidades verificáveis, orçamento de caixa e seleção de hub antes da compra.

### Rastreabilidade e reversão

- Branch de integração `codex/autonomia-a0-a1-20261122`. Commits de módulos incorporados `c678175` (motores), `0f62592` (pesquisa por motor) e `17482ad` (contrato de oportunidade). Demais ajustes de política, ranking, painel e testes acompanham o commit de integração.
- A reversão desta onda é feita por `git revert` dos commits da branch, após revisar dependências. Os dados existentes permanecem legíveis e as novas flags estão desligadas por padrão. PR #44 continua independente, sujeita a revisão antes de qualquer merge.

## 2026-11-21 — Visão geral operacional e registros compactos

### Implementado

- A **Visão geral** ganhou uma faixa de indicadores de alta densidade para rendimento diário estimado, rotas identificadas na frota atual, duplicidades comprovadas, decolagens confirmadas no último despacho e prazo até o próximo ciclo. Todos os dados vêm das APIs existentes `GET /api/status` e `GET /api/routes`.
- O resumo de rotas só divulga contagens quando o cadastro da frota atual está verificado pelo jogo. A identificação exige ID de rota válido, origem e destino disponíveis e auditoria vigente da associação individual. O painel diferencia a frota conferida do **cadastro histórico acumulado** e indica quando a leitura ficou desatualizada.
- A atualização do resumo ocorre a cada **60 segundos** enquanto a Visão geral está aberta e reutiliza respostas da página **Rotas e Aeronaves**. A telemetria principal continua com ciclo de dois segundos. A exibição do último despacho inclui o horário da avaliação e sinaliza simulações.
- Os registros operacionais usam linhas menores, colunas compactas e uma mensagem de uma linha com reticências. Um clique ou acionamento pelo teclado expande individualmente a mensagem completa, preservando filtros, cores de severidade e rolagem automática.
- O layout se adapta a telas grandes, intermediárias e celulares. Há destaque visual para duplicidades confirmadas. As novas informações receberam traduções em inglês.

### Validação e limites

- Testes estáticos garantem a presença dos indicadores e a compactação expansível do log. Um teste executa a lógica real em Node.js e verifica que dados históricos ou frota desatualizada não são divulgados como rotas/duplicidades atuais.
- A cobertura de origem e destino depende da auditoria incremental das páginas do jogo. A faixa informa quantas rotas foram identificadas entre os vínculos atuais e não pressupõe cobertura integral. O rendimento diário é uma estimativa proveniente do status existente.
- Não houve atualização da aplicação no servidor nesta entrega. A implantação deve ser realizada separadamente após validação da `main`.

## 2026-11-21 — Frota real, rotas atuais e resultado dos voos

### Diagnóstico autenticado

- A sessão real de Airline Manager 4 confirmou **218 aeronaves únicas** em `window.statusData`. O registro acumulado do bot continha **255 IDs históricos**, incluindo aeronaves que já não constam da frota. Os contadores previamente verificados eram 205 com rota, 0 estacionadas e 13 pendentes. A leitura da sessão atual confirmou novamente os 218 IDs.
- A propriedade `statusData[id].routeId` vincula uma aeronave ao ID da sua rota. No HTML de uma página real de rotas, `routeMainList36893058` foi observado como identificador de rota, e o link `fleet_details.php?id=24523917` identifica a aeronave correspondente. O rótulo `DEL - BTT` é exposto em `.col-10 .s-text`. Essa distinção impede associar rotas a aeronaves erradas.
- A página autenticada `fleet_details.php?id=21758643` exibiu histórico individual com pares de aeroportos, consumo em libras, cotas de CO₂, valor monetário e horário relativo. Foram observados registros `TAS-GRU`, `589,009 Quotas`, `248,356 Lbs` e `$1,277,380`. O significado contábil exato do valor monetário ainda depende de homologação.

### Implementação

- `src/fleet.py` captura a lista completa de aeronaves de `statusData` apenas quando sua cardinalidade corresponde aos contadores confirmados pelo jogo. Associa a matrícula ao ID da aeronave e seu `routeId`, conservando o cadastro histórico separadamente. A auditoria de páginas grava o `routeId` observado em cada cartão para comprovar origem e destino.
- `src/route_registry.py` mantém a última frota validada, com idade máxima de 15 minutos para a confirmação atual. A visão **Frota do jogo** lista exclusivamente esses IDs. Origem, destino e lucro da rota são exibidos apenas após correspondência entre ID de rota observado no cartão e ID atual da aeronave. Mudanças de rota ocultam dados anteriores até a próxima auditoria. A cobertura de páginas continua incremental.
- A coleta financeira consulta em modo leitura o histórico individual de até **oito aeronaves por ciclo**, em rotação por última leitura. Persiste valor monetário do último voo, uso de combustível, cotas de CO₂ e **margem operacional estimada** pela diferença entre valor informado e custos aos preços atuais do estoque. Soma também as margens de voos datados nas **últimas 24 horas**, com quantidade de voos, sem imputar dias ou registros ausentes.
- A tela **Rotas e Aeronaves** permite alternar entre **Frota do jogo** e **Cadastro histórico**. Apresenta total atual, cadastro histórico, situação da auditoria, duplicidades atuais, rota, resultado estimado de 24h quando disponível e margem do último voo. O painel distingue valores efetivamente lidos de cálculos aproximados. A área de duplicidades respeita o filtro escolhido.
- `src/hub_registry.py` usa a frota real quando sua lista está disponível. `src/web.py` incorpora os contadores verificados no relatório `/api/routes` sem acessar o navegador do jogo.

### Validação e limites conhecidos

- Testes para reconciliação de frota, IDs duplicados/inválidos, mudança de rota, histórico preservado, valores monetários, total das últimas 24 horas, JavaScript do histórico e duplicidades por escopo. Suíte Windows completa excluindo o teste específico de permissões POSIX, Ruff, compilação e validação de diffs executados.
- O **lucro operacional estimado** considera o valor exibido no histórico, combustível e CO₂ aos preços de consulta. Não inclui manutenção, A-check ou outras despesas. A coluna de resultado diário informa quando usa a soma histórica dos voos nas últimas 24 horas, sem a confundir com uma projeção de rota.
- Novas rotas podem permanecer **a confirmar** até a auditoria da página correspondente. O registro histórico de 255 IDs permanece acessível para diagnóstico. A identificação da base individual de todas as aeronaves segue pendente de prova explícita no jogo.
- Implantação realizada no servidor `192.168.101.234` no commit `aa65ec47086db2d92b62b235e25c6e0cf6456dc7`. Antes da troca, o serviço foi interrompido para backup integral em `/home/piekas/am4bot-backups/20261121T231402Z-pre-aa65ec4/`. O arquivo de 269.782.561 bytes passou pela verificação SHA-256, pela inspeção do TAR e foi gravado com permissão `0600`. O serviço `am4bot@principal` reiniciou com estado `active`, sem reinícios adicionais.
- **Homologação autenticada da primeira execução após a implantação:** `GET /api/routes` retornou 218 linhas na frota atual, 218 IDs no cadastro confirmado, `current_roster_verified=true` e contadores 205 com rota, 0 estacionadas, 13 pendentes. O cadastro histórico permaneceu em 255. Já havia **71 relações com origem e destino confirmados** e **8 históricos financeiros persistidos**, com valores de último voo e resultado estimado de 24h. O log registrou `Histórico financeiro: 8/8 aeronaves com leitura válida`. As **147 relações sem trajetos comprovados** aguardam novas páginas auditadas em ciclos seguintes, e as demais leituras financeiras progridem pela rotação de oito aeronaves.
- A conferência visual em diferentes resoluções e a conclusão da cobertura das 11 páginas em uma passagem estável continuam pendentes. Uma nova leitura pode apresentar contagem diferente de 218 se a frota mudar.

## 2026-11-21 — Confirmação operacional da coleta e acompanhamento no painel

### Evidências de execução autenticada

- Na versão `2d395f8`, implantada após backup integral no servidor `192.168.101.234`, o log do serviço `am4bot@principal` confirmou **3/3 preços de hubs persistidos no mesmo ciclo**. A API posterior mostrou **9 aeroportos candidatos com preço** e **1.000 amostras de demanda**, contra 550 antes das correções. O cursor de catálogo avançou pelo Brasil; coleta de preços e de demanda segue ativada.
- A API autenticada retornou **218 aeronaves na frota** com contagem verificada e atual. Composição do jogo no instante da consulta: **205 aeronaves com rota**, **0 estacionadas** e **13 entregas pendentes**. A lista de rotas tinha **255 IDs históricos**, que não representam aeronaves atualmente possuídas. O seletor do jogo informou **30 hubs adquiridos**.
- A auditoria de rotas tinha **11 das 11 páginas observadas ao longo de ciclos diferentes**, com **192 IDs únicos** e **13 IDs repetidos entre páginas**. Como aeronaves mudam de posição durante a paginação, `full_page_coverage_verified=False`. A prova de uma passagem integral estável e o hub de origem individual continuam pendentes.
- Configuração observada: coleta de mercado e auditoria ativas, **3 preços de hubs** e **3 páginas de frota** por ciclo, ciclos normalmente a cada **5 a 10 minutos**, podendo antecipar conforme a operação. A pesquisa de demanda amostra uma base adquirida por ciclo.

### Melhoria desta entrega

- A tela **Novos hubs** passa a exibir quantos candidatos têm preço de compra registrado, o total de amostras persistidas de demanda, quantas seguem recentes e a data da última pesquisa. Os dados são lidos da API já existente e não executam ações no jogo.
- As traduções em inglês e verificações estáticas da interface foram atualizadas.

### Pendências de homologação

- Confirmar a cobertura contínua da coleta em outros países, a base individual de cada aeronave e uma auditoria completa em uma única passagem estável. O total verificado da frota permanece separado do cadastro histórico.

## 2026-11-21 — Correção da coleta de preços na página autenticada de hubs

**Diagnóstico real:** o jogo abre `hubs_new.php`, preenche `#hubAirportSelector` após carregar o país e substitui `#airportInfo` via `airport_info.php?mode=hub&id=<aeroporto>`. Dentro dessa resposta há uma linha `<tr id="hubCostInfo">` cujo segundo `<td>` separa o valor em dólares dos pontos por `<br>`. O `textContent` dessa linha une os valores, por exemplo `$ 11,520,00020 Points`, inviabilizando a análise numérica anterior. A resposta também contém a atribuição `arrId = <id>` no script do aeroporto selecionado.

### Correção aplicada

- `src/game_observations.py` coleta o preço e os pontos separadamente a partir dos nós de texto da célula do custo. Exige valor monetário inteiro e pontos válidos, preservando o bloqueio para números fracionários ou ambíguos.
- Valida o ID da resposta AJAX (`arrId`) contra o ID selecionado, rejeitando dados da seleção anterior. A coleta continua exigindo duas leituras DOM idênticas e detecta elementos em carregamento. Requisições AJAX em outras partes da página deixam de impedir uma leitura já correlacionada e estável.
- Na primeira execução dessa correção no Zentria, o log registrou `id_conflict` durante a troca rápida de aeroportos. A tentativa com resposta vazia encerrava imediatamente e avançava para outro aeroporto enquanto a requisição anterior ainda carregava. Agora cada tentativa aguarda até 20 leituras com pausa interrompível de 0,2 segundo para receber o novo ID antes de avançar. Um teste verifica duas leituras AJAX vazias seguidas de uma resposta válida.
- Diagnósticos de preços passam a inspecionar a mesma estrutura de célula e o ID da resposta. Um novo teste reproduz o HTML observado com dólar e pontos separados, a seleção anterior e atividade AJAX simultânea.

### Homologação

- Em consulta autenticada e somente de leitura, foram confirmados os seletores, o endpoint e o formato de custo para aeroportos brasileiros, inclusive IDs `2914`, `2933`, `2927` e `2966`. O exemplo `2966` trouxe custo em dólares e pontos e `arrId` correspondente.
- Testes direcionados `test_game_observations.py` e `test_dashboard_fleet_total.py`, compilação e Ruff concluídos com sucesso no Windows.
- A persistência de preços precisa ser confirmada no próximo ciclo do serviço com a versão atualizada. Nenhuma compra foi realizada pelo diagnóstico.

## 2026-11-21 — Contagem real da frota e diagnóstico da coleta de hubs

**Motivo:** divergência entre o total do painel, a quantidade efetiva do jogo e os vínculos cadastrados no inventário de bases.

### Evidências operacionais antes do ajuste

- No servidor `192.168.101.234`, o serviço `am4bot@principal` estava ativo no commit `3035aac3`. As configurações reais tinham `collect_market_observations=on` e `audit_route_pages=on`, com três aeroportos pesquisados para preço e três páginas de rotas auditadas por ciclo; a pesquisa de demanda processa uma base adquirida por ciclo. Os ciclos são agendados em intervalo configurado de cinco a dez minutos, podendo antecipar conforme os eventos monitorados.
- O jogo exibia **204 rotas**, **0 aeronaves estacionadas sem rota** e **14 aeronaves pendentes de entrega**. O total representado por esses contadores é **218 aeronaves** no instante da leitura. A lista de manutenção do bot continha entre 204 e 205 aeronaves em leituras diferentes. Os indicadores têm instantes e coberturas distintos, logo a lista de manutenção não é a fonte do total da companhia.
- Havia **30 hubs adquiridos** e **550 amostras de demanda** persistidas. A lista de rotas mantinha **254 IDs históricos**, embora o cabeçalho atual mostrasse 204 rotas. O catálogo de compra tinha **zero preços confirmados** e cursor de varredura avançando pelo Brasil. Os registros históricos não comprovam 254 aeronaves ativas.
- A auditoria incremental tinha observações de 10 das 11 páginas de rotas, acumuladas em ciclos distintos, com 186 IDs únicos, dois IDs repetidos entre páginas observadas e `full_page_coverage_verified=False`. A frota pode mudar de posição entre leituras. Não existe prova de cobertura integral em uma única execução.

### Correções do código

- `src/fleet.py` faz uma leitura conjunta dos três contadores do próprio popup de rotas, exigindo números válidos. A captura salva `route_count`, `parked`, `pending` e horário. A leitura incompleta invalida a confirmação anterior, com aviso no log, para o painel não divulgar uma soma antiga como comprovada.
- `src/dashboard.py` calcula a frota completa a partir de rotas, estacionadas e entregas pendentes quando os três números são confirmados. Mantém aviso de contagem parcial ou desatualizada quando apropriado. `src/bot.py` aplica a composição ao relatório do Telegram apenas com comprovação atual válida.
- `src/web.py` expõe os contadores confirmados na API de hubs. A interface web e a desktop exibem a composição do total. A tela **Hubs e Aeronaves** diferencia o total lido do jogo dos **254 registros históricos de rotas**, e trata a lista sem base confirmada como registros sob investigação.
- `src/game_observations.py` registra indicadores estruturais seguros quando a seleção de um aeroporto termina sem preço confirmado, incluindo presença dos elementos, correlação do aeroporto, carregamento AJAX e formato de preço/pontos. Nenhum conteúdo de credencial, cookie ou HTML é registrado. O diagnóstico deve permitir identificar o bloqueio efetivo em ciclo autenticado posterior.
- Testes exercitam a captura conjunta dos contadores, mudanças de página, leitura inválida, expiração do dado e a diferença entre total atual e histórico do registro de rotas.

### Critérios ainda abertos

- Confirmar no servidor a nova contagem do painel durante um ciclo autenticado, observar os diagnósticos de preço e corrigir o seletor ou o formato conforme as evidências resultantes. O preço de compra ainda não foi persistido em execução real.
- Localizar uma fonte do jogo que comprove o hub permanente por **ID individual de aeronave** e concluir uma auditoria de todas as páginas na mesma execução com contadores estáveis e IDs sem repetição.

## 2026-11-21 — Backup integral e implantação verificada no servidor Zentria

**Solicitação:** após correção do IP pelo usuário, criar backup da instalação ativa e disponibilizar a nova versão para validação.

- Servidor: `192.168.101.234`, hostname `zentria`, Ubuntu; serviço `am4bot@principal` em `/home/piekas/AirlineManager4Bot`. A instalação anterior estava no commit `3a53f78667ac2607c3d61182f3f4b154d596609c`, com arquivos versionados limpos e serviço ativo.
- Antes da troca de código, o serviço foi parado e a instalação inteira foi arquivada, incluindo `.git`, `.venv`, `config`, `data` e demais arquivos, em `/home/piekas/am4bot-backups/20261121T211036Z-pre-3035aac/AirlineManager4Bot.tar.gz`. O backup possui **252.499.369 bytes**, permissão **0600**, arquivo `sha256` validado com sucesso e listagem do TAR íntegra. Uma cópia da unidade systemd e um manifesto dos commits também estão nessa pasta, fora do checkout.
- A branch `feat/hubs-inventory-readonly` foi buscada diretamente do GitHub e o servidor passou ao commit `3035aac3c8a2160687abed40a0eb8dd9c28ea56e` (funcionalidades da entrega `d246d15`, acrescidas do histórico de implantação). Não houve mudança no conteúdo versionado de `requirements.txt`; o Python da instalação compilou `src` e `scripts` sem erro. Configurações individuais, credenciais, dados e arquivos não versionados foram preservados.
- O serviço foi iniciado e conferido no `systemd` como **active/running**, com PID **393993**, `NRestarts=0` no pós-teste. A sessão Selenium do jogo foi restaurada e o painel respondeu na porta **8744** da rede local.
- **Primeira homologação operacional observada:** o log confirmou três páginas da frota no ciclo novo, cobertura acumulada **4/11**, **zero IDs repetidos** e `full_page_coverage_verified=False`. Foram persistidos **50 registros de demanda** por pesquisa de rotas, e o arquivo `data/hub_expansion.json` passou a existir com cursor de varredura. Após esse ciclo, havia **zero preços de hubs confirmados**, que exigem investigação adicional do DOM e novo teste. A base permanente por aeronave e a auditoria das 11 páginas em um único ciclo também seguem pendentes de comprovação real.
- O serviço continuou ativo na segunda inspeção, sem reinicializações automáticas registradas. O painel pode ser validado em `http://192.168.101.234:8744/`, com o acesso já configurado no servidor.

## 2026-11-21 — Tentativa de backup e implantação no servidor indicado

**Solicitação:** realizar backup no servidor e disponibilizar para validação a versão `d246d15` da branch `feat/hubs-inventory-readonly`.

- Conferido o checkout local na branch solicitada, sem alterações pendentes no código.
- O endereço SSH informado respondeu a ICMP, porém a conexão TCP à porta 22 expirou antes da etapa de autenticação (`TimeoutError: timed out`). Portas SSH alternativas 2222, 2200 e 8022 também expiraram. Isso impediu a inspeção segura de unidade `systemd`, pasta de instalação, configurações e dados.
- A porta HTTP 80 respondeu com `Server: Microsoft-HTTPAPI/2.0`. É necessário conferir se o endereço corresponde à máquina Linux onde o serviço `am4bot@principal` é executado.
- **Backup remoto não executado. Implantação não executada. Reinicialização do bot não executada.** O estado do servidor e a existência de backups anteriores continuam desconhecidos.
- **Critério de retomada:** disponibilidade da conexão SSH ao servidor correto. Após autenticar, identificar o diretório do serviço, realizar backup completo verificável fora do checkout, preservar dados e configurações locais, implantar `d246d15`, reiniciar o serviço e confirmar versão, saúde do processo e logs.

## 2026-11-21 — Consolidação da auditoria integral e publicação da coleta persistente

**Roadmap:** `docs/ROADMAP_HUBS_AERONAVES.md`, etapas 1, 2, 3 e 4.

### Entregue nesta branch

- A coleta incremental de preços de hubs e demanda Y/J/F está integrada ao ciclo de execução do bot, com armazenamento JSON por perfil, timestamps, origem do dado, cursor retomável e tratamento de tentativas malsucedidas. A leitura dos detalhes e do preço exige correspondência com o aeroporto selecionado e leituras estáveis do DOM. A demanda exige a conferência de destino, distância e contagens contra a pesquisa do jogo.
- A auditoria paginada agora diferencia observações acumuladas de **auditoria integral no mesmo ciclo**. Cada chamada possui um `audit_run_id` novo; só marca `full_page_coverage_verified` quando todas as páginas pertencem àquele identificador, não há aeronaves repetidas e o número de IDs é igual ao total de rotas exibido pelo jogo, com paginação coerente. A última comprovação integral é preservada em `last_verified_full_audit` mesmo quando leituras parciais posteriores renovarem a cobertura.
- O limite genérico de leitura incremental segue em cinco páginas por ciclo. O carregador AJAX comprovado aceita até 25 páginas e pode receber `fleet_audit_pages_per_cycle = 11` durante uma homologação de frota com 11 páginas. O padrão operacional permanece três páginas por ciclo; esse padrão documenta cobertura parcial sem declará-la como integral.
- A auditoria rejeita lotes se a contagem de rotas variar durante a navegação, restaura a página inicial e registra no log o ID, total de aeronaves e páginas apenas quando a prova integral é obtida.
- A vinculação de `home_hub_id` continua sujeita à evidência por aeronave capturada no próprio jogo, com fonte, identidade e horário. As aeronaves sem atributo explícito são mantidas como **Base a confirmar**, inclusive após uma auditoria integral da frota.

### Evidências e verificação

- A inspeção **manual** autenticada do jogo em 21/11/2026 percorreu 11 páginas com 204 cartões e 204 IDs únicos. Quantidades por página: 15, 20, 20, 18, 19, 19, 20, 19, 19, 19 e 16. O cabeçalho mostrava 204 rotas; a página original foi restaurada. A auditoria **automatizada** de onze páginas foi verificada com dados simulados correspondentes, incluindo mudanças de contagem no meio do AJAX e revalidação da primeira página.
- O DOM autenticado inspecionado não revelou um campo comprovável de base individual. Não foi atribuída base por inferência de origem da rota, destino, posição ou estado de manutenção.
- A coleta persistente e a navegação foram exercitadas por testes locais, mas a versão nova ainda precisa rodar com sessão Selenium autenticada para produzir registros operacionais reais e confirmar os seletores no próprio processo do bot.
- A tentativa de SSH em 21/11/2026 para `piekas@192.168.101.234` retornou `Permission denied (publickey,password)`. Sem a sessão autorizada do servidor, a homologação operacional integral e a comprovação individual permanecem pendentes.

### Critérios ainda abertos

- Executar a nova branch em uma sessão Selenium autenticada, conferir o arquivo `hub_expansion.json` do perfil e o log de auditoria integral. Para uma passagem coerente das 11 páginas observadas, ajustar temporariamente `fleet_audit_pages_per_cycle = 11` e manter `audit_route_pages = on`. A operação deve ser acompanhada para detectar alterações da frota enquanto a paginação estiver em andamento.
- Identificar uma fonte oficial do jogo que declare a base permanente de cada aeronave, correlacionada ao respectivo ID. Só então classificar o vínculo como comprovado e verificar as contagens do painel por base.


## 2026-11-21 — Coleta persistente de mercado e auditoria incremental de frota

**Objetivo:** integrar preço de novos hubs e demanda pesquisada ao ciclo do bot, preservar a prova individual de base e auditar páginas reais sem confundir posições paginadas com identidades fixas. Entrega de código concluída nesta branch. A homologação por navegação manual autenticada foi ampliada; homologação do ciclo real do bot permanece pendente.

### Código implementado

- `src/game_observations.py` consulta o formulário de compra de hubs e o resultado de pesquisa de rotas na sessão ativa do bot. Cada preço é associado ao `airport_id` selecionado somente após duas leituras DOM iguais, confirmação dos detalhes do aeroporto e ausência de carregamento AJAX pendente. O custo em dólares e os pontos do jogo são coletados separadamente. A compra não é acionada.
- A varredura de aeroportos avança de forma incremental por país, com cursor persistente e fila de tentativas que falharam. Cada tentativa conserva a última observação válida e usa espera progressiva para consulta futura. A pesquisa percorre as bases adquiridas e grava demanda Y/J/F, destino, distância, fonte e horário somente quando os dados DOM conferem com o resultado da busca.
- `src/hub_expansion.py` persiste preços, pontos e demanda por origem e destino no arquivo do perfil (`hub_expansion.json`). Registros de pesquisa antiga permanecem datados. Um custo adicional em pontos impede que o cenário seja classificado como financeiramente aprovado apenas pelo saldo em dólares.
- `src/bot.py` integrou as duas coletas ao ciclo normal. `config/defaults.ini` habilita `collect_market_observations` e limita `hub_prices_per_cycle` a três aeroportos por ciclo, ajustável entre um e dez em execução. A auditoria paginada também é habilitada e limitada, por padrão, a três páginas por ciclo.
- `src/fleet.py` audita a navegação nativa `routes.php?start=20*n&sort=` pelo alvo AJAX `routeAction`, confirma página, total e IDs em leituras repetidas, rejeita páginas repetidas ou alteradas e tenta restaurar a página de origem mesmo depois de uma transição não confirmada. O deslocamento usa 20 posições por página, independentemente da quantidade visível.
- `src/route_registry.py` acumula a cobertura por página e identifica aeronaves pelos IDs do jogo. A prova de `home_hub_id` exige um atributo explícito associado àquela aeronave e encaminhamento de sua origem, identidade e horário. `src/hub_registry.py` só contabiliza a aeronave no hub adquirido depois dessa verificação. Origem/destino da rota e a indicação de estar em uma base permanecem evidências insuficientes para atribuir o hub de origem.
- `assets/web/index.html` exibe o custo do hub em pontos, além do custo em dólares, na seção de detalhes financeiros.

### Testes e evidências

- Incluídos testes de preço e pontos do DOM, troca de país com opções AJAX obsoletas, fila de tentativas, demanda correlacionada, vínculo individual de aeronave, navegação incremental de 11 páginas, páginas com menos de 20 aeronaves, mudanças durante o ciclo e restauração da página de origem.
- O teste de ponta a ponta da lógica de base comprova que um ID explícito de hub no registro de rota é acompanhado da origem da evidência, do ID da aeronave e de um horário verificável. É uma simulação controlada e não substitui a identificação desse atributo no DOM autenticado do jogo.
- Inspeção manual autenticada anterior identificou 30 hubs, 217 aeronaves no painel, 205 rotas e preços de FLN/JOI de US$ 11.472.000 + 20 pontos. Essas amostras não foram gravadas por esta nova rotina em uma execução operacional e não atestam o sucesso dela.
- **Nova auditoria manual autenticada em 21/11/2026:** a navegação pelo paginador nativo percorreu todas as 11 páginas. Contagens visíveis por página, da 1 à 11: **15, 20, 20, 18, 19, 19, 20, 19, 19, 19, 16**. Foram registrados **204 IDs de aeronave únicos entre 204 cartões**, sem ID vazio nem repetido. O cabeçalho do jogo exibia **204 Routes** durante a inspeção. Os links reais usam `Ajax('routes.php?start=20*n&sort=', 'routeAction', this)`. O navegador voltou à página 1, que exibia 15 linhas, com `jQuery.active=0`. Esta é evidência de navegação humana no navegador autenticado, **não** de execução do código novo no processo Selenium do bot.
- **Base individual ainda sem prova:** os cartões inspecionados e o detalhe `fleet_details.php` não apresentaram `data-home-hub-id`, `data-base-id` ou `data-hub-id`. A rota atual (por exemplo, DTW–TSE) não comprova a base permanente. A interface deve continuar apresentando **Base a confirmar** para essas aeronaves.

### Bloqueios de homologação com dados reais

- **Coleta efetiva:** executar o bot em uma sessão autenticada com a nova branch e verificar novos registros por perfil em `hub_expansion.json`, inclusive pontos e horários. Nesta entrega, a coleta foi validada por testes com respostas representativas.
- **Base individual:** inspecionar no HTML autenticado se existe `data-home-hub-id` no cartão da aeronave ou no respectivo link de detalhes. Até que o jogo efetivamente forneça o atributo, cada aeronave sem evidência continua em **Base a confirmar**. Nenhuma vinculação individual real foi afirmada.
- **Auditoria completa:** observar ciclos efetivos de `am4bot@principal` até que todas as páginas disponíveis sejam lidas, confirmar restauração da página original e comparar IDs e contagens com o painel da conta. A cobertura de testes de 11 páginas foi simulada. A execução completa autenticada ainda não foi feita.
- **Acesso remoto verificado novamente em 21/11/2026:** `ssh -o BatchMode=yes -o ConnectTimeout=7 -o NumberOfPasswordPrompts=0 piekas@192.168.101.234` retornou `Permission denied (publickey,password)`. A verificação operacional depende de acesso autorizado ao processo `am4bot@principal` em `zentria`. Nenhuma operação de compra ou decolagem foi usada para homologar estes recursos.

**Publicação:** a entrega permanece na branch `feat/hubs-inventory-readonly`, sem implantação no servidor nem promoção para `main`.

## 2026-11-21 — Homologação manual em sessão autenticada e adaptação de seletores

**Roadmap:** `docs/ROADMAP_HUBS_AERONAVES.md`, etapas 1 e 4 (inspeção real parcial).

### Evidências observadas no Airline Manager 4 autenticado

- Conta em modo Easy, inspecionada com consultas e navegação de leitura, sem efetuar compras, abrir rotas ou despachar aeronaves.
- **Frota e paginação:** `#popContent .pagination .page-item.not-active > .page-link` identifica a página atual como `2`. Os links Previous e Next usam o carregador AJAX `routes.php?start=0` e `routes.php?start=40`. Os deslocamentos seguem múltiplos de 20 e o cabeçalho `#popContent .row.font-weight-bold > .col-12.exo.text-center.p-2` exibe `205 Routes`, que corresponde a 11 páginas de referência. Na segunda página foram observadas 18 linhas visíveis. A quantidade renderizada varia com o estado da frota e não pode ser usada sozinha como tamanho da página.
- **Hubs adquiridos:** a pesquisa de rotas expõe `#hubSelect`, com 30 bases na sessão observada. O vínculo individual e persistente `home_hub_id` por aeronave ainda não foi provado.
- **Compra de hubs:** a tela usa `#hubcountrySelector` (233 países), `#hubAirportSelector` (117 aeroportos brasileiros e uma opção inicial), `#hubCostInfo` (custo), `#airportInfo` (detalhes da opção selecionada) e `#hubList > .row[onclick]` (30 bases adquiridas). O seletor `#hubSelection` pertence ao fluxo de pedido de aeronave e não deve ser tratado como catálogo de compra de hubs. É necessário esperar o conteúdo de `#airportInfo` corresponder à opção escolhida, pois o carregamento é assíncrono.
- **Amostras de preço de compra:** FLN (`airport_id=2941`) e JOI (`airport_id=2957`) exibiram **US$ 11.472.000 + 20 pontos** por hub, cada um. Em FLN foram observados pista de 7.546 pés, participação de mercado de 47%, distância de 515 km, demanda Y=789/J=154/F=124 e carga de 592.000/231.000 lb. Em JOI, pista de 5.381 pés, mercado 76%, distância de 389 km, demanda Y=843/J=188/F=165 e carga de 633.000/282.000 lb. Esses são valores pontuais do jogo, sujeitos a variação, e não foram importados para o catálogo persistente.
- **Pesquisa de demanda:** `#resSearch` e `#resResult #list .sorter` exibem resultados com atributos `data-yclass`, `data-jclass`, `data-fclass`, `data-large`, `data-heavy`, `data-rwy` e distância. A amostra XAP–SBL apresentou distância aproximada de 1.992,76 km, Y=120, J=106, F=40, carga large=90/heavy=159 e pista de 5.013 pés. A tela inspecionada continha 50 resultados. O link de detalhes usa `route_research_route.php?dep=2926&arr=3139`.
- **Contexto da companhia:** o painel do jogo mostrava 217 aeronaves, 205 rotas, 0 estacionadas e 12 pendentes. Essas contagens são um retrato da sessão, não um inventário estável ou uma prova de atribuição de base por aeronave.

### Implementado nesta entrega

- Atualizado `src/game_source_probe.py` com os seletores reais de país, aeroporto, preço e detalhes para compra de hubs, lista adquirida e o seletor distinto de hub do pedido de aeronaves. A pesquisa passa a registrar a presença dos atributos de demanda cargueira.
- O diagnóstico sanitizado reconhece a página atual pela classe `not-active` e deriva o total de páginas do cabeçalho numérico de rotas quando não houver atributos de paginação explícitos. O resultado indica se essa evidência foi encontrada, sem copiar textos livres nem informações de autenticação.
- A auditoria de frota em `src/fleet.py` reconhece o mesmo paginador e total calculado de páginas, preservando os identificadores de aeronave e códigos de rota já disponíveis no DOM.
- O painel de diagnóstico passou a relacionar os seletores adicionais. Adicionados testes Node.js de regressão para a paginação real e ajustados os contratos de apresentação do diagnóstico.

### Verificação

- **495 testes passaram e 1 foi ignorado** na suíte Windows com `tests/test_instalacao_linux.py` excluído. O teste ignorado depende de permissões POSIX.
- `ruff check src scripts tests`, `compileall` para `src`, `scripts` e `tests`, e `git diff --check` aprovados.

### Pendências reais após esta inspeção

- Integrar a leitura de preço do hub e demanda em estruturas persistentes por perfil, com identificação exata do aeroporto, marca temporal e verificação de carregamento completo antes de recomendar compra.
- Confirmar a base de origem individual de cada aeronave por evidência explícita, inclusive fora da página atual, e homologar o carregador de paginação em um ciclo efetivo do bot. O diagnóstico real foi uma inspeção manual do navegador autenticado, sem executar auditoria de produção de todas as páginas.
- Comparar o painel do bot com a companhia real em desktop/celular e validar os cenários financeiros com custos completos. A coleta não alterou o estado do jogo.

## 2026-11-21 — Diagnóstico integrado à sessão do bot e interface de consulta

**Roadmap:** `docs/ROADMAP_HUBS_AERONAVES.md`, etapas 1 e 4.

### Implementado

- Novo `POST /api/admin/game-source-probe`, protegido por token configurado e cabeçalho `X-AM4`, exige corpo JSON vazio. O acesso a esse diagnóstico requer token mesmo no loopback. A consulta retorna apenas o relatório sanitizado e mensagens genéricas em caso de indisponibilidade.
- A requisição é enfileirada para execução pelo próprio thread do bot, durante a espera entre ciclos. Os handlers HTTP não consultam o Selenium diretamente. O bot rejeita chamadas simultâneas ou durante uma operação, cancela pedidos que expiraram e prioriza os prazos da próxima execução e da sincronização de caixa.
- Na tela **Hubs e Aeronaves**, uma seção recolhível permite iniciar o diagnóstico sob demanda, acompanhar andamento, conferir contagens e a presença de IDs por fonte, e examinar a evidência de paginação. A tela apresenta erros 403, 409, 503 e 504 sem expor HTML bruto, cookies, credenciais ou detalhes internos de exceções.
- Foram incluídos testes para concorrência entre requisições, indisponibilidade, timeout, parada e execução imediata do bot, além de cenários HTTP e da interface PT-BR/EN com acessibilidade e apresentação em dispositivos menores.
- Corrigida a validação de entradas de hub para rejeitar IDs booleanos ou coleções e preservar o catálogo confirmado. Testes cobrem os casos `False` e `[]`.

### Verificação e homologação

- **493 testes passaram, com 1 ignorado** no Windows, excluindo o arquivo de testes de instalação Linux desta execução. A interface também passou por verificação sintática de JavaScript e por testes de contrato. Compilação Python, análise Ruff e `git diff --check` foram aprovados.
- O diagnóstico descreve apenas a janela do jogo já aberta na sessão do bot. Ainda falta executar a consulta em uma companhia autenticada para confirmar os seletores de hub de origem da aeronave, os preços das novas bases, a demanda e o carregador real de páginas. A classificação de conclusão funcional depende dessas evidências.

## 2026-11-21 — Integridade dos seletores e evidências de paginação

**Roadmap:** `docs/ROADMAP_HUBS_AERONAVES.md`, etapas 1, 2 e 4.

### Implementado

- A leitura dos hubs adquiridos mantém o último catálogo confirmado quando o seletor contém entradas inesperadas, IDs inválidos que não sejam placeholders ou IDs duplicados com dados divergentes. Um exemplo de regressão confirma a preservação dos dados anteriores.
- O diagnóstico somente leitura agora distingue opções de hubs com `value` numérico explícito das opções cujo valor seria derivado do texto pelo navegador. Exibe a quantidade de nós com IDs interpretáveis e sinaliza evidências estruturadas para página atual, total de páginas, paginação visível e carregador do popup.
- Os relatórios do diagnóstico continuam limitados a nomes de seletores conhecidos, contagens, identificadores numéricos e booleanos. Novas verificações sanitizam indicadores de paginação e impedem a propagação de dados inesperados.

### Verificações e pendências

- Testes específicos dos registros de hubs e do diagnóstico DOM aprovados. Uma fixture HTML com estrutura representativa do jogo exercita identificadores, paginação e carregador sem autenticação.
- A confirmação dos seletores contra uma conta autenticada permanece pendente. A fixture é representativa e não constitui validação da interface real em execução.

## 2026-11-21 — Confiabilidade do ranking, isolamento de hubs e diagnóstico seguro do jogo

**Roadmap:** `docs/ROADMAP_HUBS_AERONAVES.md`, etapas 1, 2, 3 e 4.

### Implementado

- O ranking de **Próxima aeronave por base** agora considera a pesquisa mais recente para cada combinação de hub, modelo e rota. Pesquisas antigas deixam de ser recomendadas mesmo que indiquem lucro maior. Observações contemporâneas com evidências divergentes são sinalizadas para revisão, e empates usam critérios determinísticos.
- O inventário de hubs resolve as rotas a partir do diretório do **mesmo perfil** usado para os hubs. A leitura normaliza IDs numéricos com zeros à esquerda e aproveita o nome alternativo quando o campo principal vier vazio, mantendo compatibilidade com os arquivos anteriores.
- A atualização do seletor de hubs adquiridos descarta leituras com opções inesperadas ou IDs duplicados divergentes e conserva a última listagem comprovada. Os placeholders usuais continuam aceitos.
- O catálogo de novos hubs agora rejeita duplicatas com preços conflitantes, saneia registros legados com tipos inválidos e impede que uma leitura incompleta elimine candidatos existentes. Observações duplicadas já persistidas perdem a indicação de atualidade até nova conferência. Em empate de lucro diário, o menor investimento é priorizado.
- A tela de recomendações apresenta filtro de modelo de aeronave, ordenação por lucro diário ou retorno do investimento e tratamento para resultados ausentes e filtros vazios. Os controles e traduções foram ajustados para desktop e celular.
- Novo diagnóstico `src/game_source_probe.py` inspeciona, **em modo somente leitura**, os seletores conhecidos de hubs adquiridos, hubs compráveis, frota, pesquisa de rotas e paginação da janela já aberta no jogo. A saída usa contagens, nomes fixos dos seletores e IDs numéricos limitados, sem incluir HTML, credenciais ou atributos livres. A operação depende de uma sessão autenticada já existente.
- Regeneradas e revisadas as capturas de demonstração `screenshots/web-hubs.png`, `screenshots/web-novos-hubs.png` e `screenshots/web-hubs-mobile.png`, com dados fictícios.

### Verificações

- Incluídos testes de regressão para pesquisa atual versus pesquisa antiga, conflitos na mesma data, normalização de bases, isolamento por perfil, seletores incompletos, filtros do painel, sanitização do diagnóstico, duplicatas de aeroportos compráveis, catálogos incompletos, dados legados inválidos e desempate financeiro. A suíte Windows foi executada após a integração, com o teste de permissões POSIX isolado.
- Compilação Python e `ruff check src scripts tests` aprovados. O `git diff --check` também foi verificado. As verificações do instalador Linux realizadas nesta rodada continuam registradas na entrega seguinte.

### Homologação pendente

- Conferir seletores e paginação na conta autenticada, confirmar a origem do vínculo individual entre hub e aeronave e coletar preços e demanda reais. O diagnóstico preserva a sessão do operador e só descreve a janela que já estiver aberta.
- Comparar os números do painel e as recomendações com a companhia real antes de marcar as etapas 1 e 4 como homologadas. As telas e imagens desta entrega utilizam dados de demonstração.

## 2026-11-21 — Persistência atômica da frota e prova estrita de paginação

**Roadmap:** `docs/ROADMAP_HUBS_AERONAVES.md`, etapas 1, 2 e 4 (robustez e desempenho).

### Implementado

- A auditoria de rotas agora aplica as observações de toda a página e atualiza o histórico de cobertura em **uma única gravação atômica do JSON**. Antes, o caminho normal gravava uma vez por aeronave e mais uma para o resumo. O fluxo continua desduplicando IDs, preservando rotas de páginas ausentes e invalidando estimativas após troca comprovada de rota.
- `RouteRegistry.record_scan` aceita um lote opcional `route_observations`, usando a mesma lógica de `record` e `observe`, com data coerente para todos os registros da página. Chamadas anteriores, sem observações, continuam registrando somente o resumo da auditoria.
- A auditoria paginada passa a **exigir prova explícita do número de página e do total** obtidos do HTML no momento da leitura. Falta ou mudança de paginação interrompe o ciclo sem atribuir cobertura à página solicitada. Números impossíveis, como página maior que o total, são rejeitados.
- Testes novos verificam gravação única por página, preservação de histórico e atribuições, alteração de rota com descarte de lucro obsoleto, aeronave sem rota identificada, duplicatas na mesma página e rejeição de paginação sem evidência.

### Verificações

- Testes específicos de frota, cadastro de rotas e auditoria aprovados no Windows.
- Suíte geral do Windows aprovada com o teste de instalação POSIX separado, incluindo o teste ignorado já existente.
- **16 testes do instalador Linux passaram no Ubuntu via WSL**, usando dependências temporárias fora do repositório. `bash -n instalar.sh` e a ajuda do instalador também funcionaram nessa distribuição.
- Compilação Python e `git diff --check` aprovados.

### Homologação ainda dependente da sessão real

- O jogo autenticado ainda precisa confirmar a estrutura da navegação entre páginas e os vínculos `home_hub_id` por aeronave, bem como catálogo de hubs compráveis, preços e demanda. O fluxo de produção continua auditando apenas a página visível até existir carregador comprovado. A cobertura incremental é informativa e continua parcial.

## 2026-11-21 — Ranking da próxima aeronave, cobertura incremental e demonstração visual

**Roadmap:** `docs/ROADMAP_HUBS_AERONAVES.md`, etapas 2, 3 e 4 (implementação incremental).

### Implementado

- Registro `HubAircraftResearchRegistry` de cenários por perfil, com modelo, base e rota, origem e horários das evidências. A gravação substitui pesquisas da mesma combinação base/modelo/rota e mantém leituras independentes dos demais perfis.
- Motor `rank_next_aircraft` classifica cenários para cada base adquirida, apresenta a melhor rota viável e conserva alternativas com pendências. Verifica atualidade de inventário, pesquisa, preços, estimativa e saldo, compatibilidade de alcance e pista, demanda, disponibilidade, ocupação da rota e caixa disponível após reserva. Cenários com escala exigem evidência individual.
- Nova API autenticada de consulta `GET /api/hubs/recommendations` e seção **Próxima aeronave por base** no painel. Exibe modelo, rota, lucro diário incremental, investimento, retorno e verificações pendentes. As recomendações utilizam registros locais do perfil ativo.
- O registro de rotas passou a manter cobertura incremental por página e aeronave identificada, com desduplicação por ID, validade de uma hora e escolha das páginas menos recentemente observadas. A função `audit_routes_rolling` permite a um carregador de páginas verificado percorrer no máximo cinco páginas por ciclo. O fluxo normal continua auditando a página visível.
- **Hubs e Aeronaves** ganhou ordenação por rentabilidade, média por rota estimada e barra de cobertura. **Novos hubs** ganhou ordenação, quantidade de cenários verificados e avisos sobre pesquisa pendente. Incluídas traduções, atributos acessíveis e layout adaptado.
- `scripts/screenshots.py --web-only` gera as capturas web de um perfil temporário usando aeroportos, rotas, saldos e projeções fictícios. Novas imagens mostram hubs adquiridos, candidatos de expansão e visão móvel. README atualizado com essas capturas.
- Testes para persistência isolada das pesquisas, classificação de cenários, cobertura paginada, renderização de hubs e capturas de demonstração.

### Verificações e limitações

- O carregador paginado real do jogo precisa ser identificado e conectado à auditoria incremental. A cobertura registrada expressa observações parciais ao longo do tempo, porque páginas e frota mudam durante a operação.
- A origem confiável de `home_hub_id`, os preços de aquisição de hubs e a pesquisa de demanda para cenários novos ainda exigem confirmação autenticada. O registro de pesquisa armazena evidências fornecidas pelo leitor do jogo, mas o leitor automático desses campos ainda não foi integrado.
- A interface e as capturas usam dados explicitamente fictícios de demonstração. Recomendações reais só aparecerão após observações verificáveis, atualizadas e com saldo recente.
- A homologação visual com o jogo real, a conferência da contagem da frota e a instalação em Linux permanecem pendentes.
- As verificações locais desta entrega incluem compilação Python, `git diff --check`, suíte de testes Windows com exclusão do teste POSIX e geração de doze capturas web no perfil temporário.


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
