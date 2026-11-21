# Histórico de entregas do roadmap

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
