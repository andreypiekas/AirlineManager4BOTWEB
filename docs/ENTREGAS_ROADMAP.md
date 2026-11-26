# Histórico de entregas do roadmap

## 2026-11-26 — Revisão para liberação da compra planejada (G0)

- A leitura de referência da frota agora exige os mesmos IDs e os mesmos contadores de Routes, Parked e Pending antes e depois de abrir `Pending`. Continua exigindo que os IDs pendentes pertençam à frota e que a companhia esteja autenticada nas duas pontas. Os testes rejeitam tanto a substituição de uma aeronave com total igual quanto a mudança entre Routes e Parked com o mesmo conjunto de IDs.
- A tentativa em modo somente leitura no Chrome dedicado chegou à tela de login. O Chrome pessoal continuava autenticado em outro perfil. A integração da nova conferência com a cotação ao vivo continua pendente. A última cotação autenticada de **US$ 216.079.503** para o A380-800 com Trent 972 em Los Angeles confirma a prévia da cabine **443/42/24**. A cobrança e o custo da rota exigem comprovantes próprios.
- Passaram **2.535 testes no Windows**, com um teste pulado, e **16 testes do instalador no Linux/WSL**. Ruff, compilação Python, sintaxe do instalador e `instalar.sh --ajuda` passaram.
- A execução planejada permanece em **G0** com `execution_available=false`. O executor disponível no journal é simulado. O fluxo legado `autobuy_aircraft` pode fazer compras sem o plano por hub, rota e cabine. A implantação no Raspberry exige a chave SSH `am4bot_pi`, ausente no ambiente de validação. Nenhum pedido ou deploy foi executado.
- Antes de G3, confirmar no worker uma rota admissível e seu custo completo, reconciliar o caixa líquido e integrar um único envio assistido ao journal com prova independente de pedido e débito. A ativação autônoma G4 depende do piloto bem-sucedido e dos limites de operação configurados.

## 2026-11-26 — Piloto A5 com o A380-800 (G0)

- Entre **17h49 e 17h59 BRT**, o Chrome autenticado confirmou a cotação nativa de **US$ 216.079.503** para uma unidade do A380-800 (`2`), motor RR Trent 972 (`7`), Los Angeles (`24323457`) e cabine **443/42/24** Y/J/F. A cabine acrescentou **US$ 450.000** sobre os **US$ 215.629.503** exibidos para 600/0/0. A tela exibiu `Order` e o retorno foi feito por `Back`. A sessão dedicada do worker falhou na autenticação e o baseline integrado permanece pendente.
- `ACCOUNT` permaneceu em **US$ 271.345.612** antes e depois da prévia. `Hangars` confirmou **224/225** PAX e **uma vaga**. A frota mostrou **224** aeronaves, `Parked (0)` e `Pending (0)`. A diferença bruta de **US$ 55.266.109** cobre somente a comparação entre saldo e cotação do avião. Ainda faltam a taxa da rota escolhida, os valores dos compromissos e a reserva para fechar o caixa líquido.
- **LAX–TUN** mostrou **10.516 km**, pista de **10.499 ft**, `Daily` de **1.341/514/112** e `Today` de **567/444/71** Y/J/F, com um A380 na rota, zero aeronaves aptas e aviso de evento. Os **US$ 1.063.229** da prévia histórica de abertura serviram de referência para o replay, sem comprovação de taxa para uma segunda operação.
- A varredura indicou a alternativa **LAX–FRU (Bishkek)**. A consulta direta no jogo confirmou **11.354 km**, pista de **13.780 ft**, `Daily` de **2.097/352/133** Y/J/F, `A/C on route 0` e `A/C capable 0`. A distância e a pista atendem aos limites de **14.500 km** e **9.680 ft** do A380. O detalhe mostrou aviso de evento e ausência de `Today`. A taxa de abertura, a admissibilidade e a economia da rota seguem pendentes.
- O replay isolado usou a cotação observada do avião e **US$ 217.142.732** como exposição de referência para LAX–TUN. Com a rota adicional, a demanda e o caixa líquido ainda sem comprovação, a pré-checagem registrou os bloqueios e fez **zero tentativas de envio**. Em cenário hipotético com os requisitos preenchidos, compromissos zerados e reserva de US$ 10 milhões, o executor simulou timeout, confirmou o recibo em um leitor separado após reinício e manteve **uma única tentativa** após repetir a solicitação. Passaram **154 testes focados** de prévia, executor simulado, pré-checagem, inventário e worker.
- **Nenhum pedido foi enviado no jogo.** O fluxo planejado permanece em **G0**. O piloto assistido exige rota e custo total verificados, caixa líquido confirmado, envio integrado ao journal com aprovação individual e conciliação independente do pedido e da cobrança.

## 2026-11-26 — Cotação nativa e baseline de frota para o piloto A5 (G0)

- `POST /api/admin/aircraft-order-preview` recebe `model_id`, `engine_id`, `delivery_hub_id`, `configuration_yjf` e `expected_checkout_cost`. Exige autenticação administrativa e usa o Chrome do worker de observação entre ciclos. O worker confere a companhia nas duas pontas, revalida modelo, motor, hub, cabine e o valor configurado exibido pelo jogo e fecha a etapa por `Back`. A resposta informa a presença do controle nativo de encomenda ao corresponder à cotação. Essa evidência trata da prévia de uma unidade.
- Às 17h31 BRT, a consulta autenticada confirmou **US$ 51.000** para o Cessna 172 (`12`), motor `23`, Los Angeles (`24323457`) e cabine **3/0/0**. A segunda consulta verificou que uma expectativa de **US$ 51.001** produz divergência com os **US$ 51.000** exibidos pelo jogo. Nenhum pedido foi enviado.
- O leitor de `Pending` cruza os IDs únicos do mapa nativo com os contadores de Routes, Parked e Pending e exige que todos os IDs de Pending estejam no mapa. A API divulga as contagens e o horário. A reprodução local conciliou 224 IDs e a fixture de `Pending (0)`. A segunda execução do Chrome falhou na autenticação. A homologação integrada do baseline ao vivo segue pendente.
- A suíte completa no Linux passou com **2.550 testes**. No Windows, passaram 78 testes de prévia, worker, API e inventário e 97 de journal, executor simulado, plano e finanças. Esses últimos cobrem timeout, recuperação após reinício e ausência de reenvio. Ruff e compilação passaram.
- O registro local mostra 14 rotas ativas com LAX como terminal e a mais curta tem 4.811 km, acima dos 1.000 km do Cessna. Entre os 82 pares compatíveis em distância e pista na varredura nativa, nove ficam abaixo do limite de 100 km do otimizador. Os 73 avaliáveis foram observados durante evento. Na hipótese de lotação completa e combustível a US$ 1.990 por 1.000 lb, nenhum cobre só o combustível. LAX–SFO (543,2 km, pista de 11.870 ft) teria US$ 1.161,83 de receita e US$ 3.820,50 de combustível por trecho nessa comparação. Confirmar admissibilidade, tarifa, demanda residual fora do evento e taxa de abertura antes de aprovar uma rota.
- A captura das 17h31 BRT confirmou US$ 277.612.393 de saldo bruto, uma vaga PAX e zero em `Pending`. Compromissos e reserva ficaram indeterminados. O usuário reiterou autorização condicionada para a compra individual de teste. A próxima etapa de A5 exige caixa líquido comprovado, aprovação individual vinculada ao journal, envio controlado e prova independente do pedido e da cobrança. O recibo do PP-254 e a taxa de abertura LAX–TUN são lacunas de outro caso. G0 permanece.

## 2026-11-26 — Varredura nativa concluída nos 30 hubs próprios (G0)

- O worker autenticado concluiu **117.180/117.180 pares de demanda diária de passageiros** às **16h59min29s BRT**, cobrindo **3.906 destinos por hub**, **232 países** e **6.960/6.960 partições**. A primeira passagem terminou às 16h48 com 76.398 pares. As janelas complementares e as consultas diretas esgotaram a fila. Todos os pares retornaram demanda, distância e pista. O SQLite passou em `quick_check` e o endpoint de leitura consultou esse mesmo banco com autenticação.
- As observações acumuladas vão de 15h49 a 16h59 BRT, incluindo as pausas do ciclo. O melhor intervalo de 15 minutos terminou às 16h58min36s, com **51.131 pares (43,63%)**. No encerramento, **49.542 pares (42,28%)** permaneciam dentro da janela. A comparação encontrou **6.135 pares (5,24%)** com diferença Y/J/F em relação à matriz de 2020. Todas as leituras nativas exibiram aviso de evento. A atualização simultânea dos 30 hubs e a cobertura com origem em hubs externos seguem pendentes.
- As consultas individuais recuperaram **506 trechos abaixo de 400 km**. O painel confirmou **GRU–GIG** a **337 km** com **541/141/220** e **GRU–SDU** a **344 km** com **394/507/181** em Y/J/F. Às 16h59, duas leituras do detalhe de cada rota confirmaram os valores, zero aeronaves na rota ou aptas e ausência de `Today`. Parked estava vazio nas duas pontas da verificação. A admissibilidade operacional segue sem prévia elegível. O controle de **LAX–TUN** confirmou **1.341/514/112**, **10.515,260 km** e pista de **10.499 ft**.
- Entre **16h59 e 17h00 BRT**, `ACCOUNT` antes e depois e `Overview` confirmaram saldo bruto de **US$ 252.354.588**. Havia uma vaga PAX (224/225), zero aeronaves estacionadas e zero manutenções ou entregas pendentes nas duas superfícies. O resumo de 24 horas registrou uma taxa recente de abertura de **US$ 1.690.066**, com lançamento genérico no histórico. As 30 transações e as 16 despesas recentes consultadas não trouxeram os comprovantes do PP-254 e da abertura LAX–TUN. A conciliação integral do caixa continua pendente. Nenhum pedido foi enviado.
- `Special Events` confirmou Black Friday Cargo Rush, +50% de demanda mundial de carga, com fim previsto para **29/11 às 20h BRT**. `Events` mostrou **YYZ–VAG** com +863 passageiros em executiva até **30/11 por volta de 01h36 BRT**. As alternativas avaliadas nos replays permanecem pendentes de demanda residual, custos e preço final verificados. O próximo ciclo econômico deve usar observações fora do evento. O piloto condicionado e a execução real seguem bloqueados em **G0**.
- A validação do transporte registrou **61 testes focados**, **2.525 testes Windows e um pulado**, mais **16 testes do instalador em WSL**. Ruff e `compileall` passaram, e o GitHub aprovou Python 3.10 e 3.13 no commit `31dba90`. [CI da implementação](https://github.com/andreypiekas/AirlineManager4BOTWEB/actions/runs/45885786786) · [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46)

## 2026-11-26 — Janelas de distância e segundo trecho observado de LAX–TUN (G0)

- A retomada no Chrome dedicado registrou **65.847/117.180 pares com demanda (56,19%)**, **6.000/6.960 partições processadas** e **26.860 pares lidos nos últimos 15 minutos** às **16h36 BRT**. A comparação por par com a matriz de 2020 encontrou **3.438 divergências Y/J/F (5,22%)**. As 65.847 linhas nativas tinham aviso de evento. A coleta acumulada e a validade simultânea de 15 minutos são medidas distintas.
- O coletor passa a complementar listas nativas de 50 destinos com janelas sobrepostas de distância. Usa o menor valor retornado, arredondado para cima, até o limite mínimo de 500 km do formulário. Conserva as observações válidas, retoma as janelas pelo SQLite e consulta individualmente os IDs ainda ausentes. Uma resposta sem resultados por país deixa esses IDs pendentes. O lote continua limitado a quatro requisições simultâneas, com identidade da companhia validada antes e depois.
- Às **16h43 BRT**, a sessão dedicada voltou ao mesmo perfil e validou as janelas com o transporte atualizado. Em **52,04 s**, 26 consultas de GRU confirmaram **68/68** destinos para Argentina, **93/115** para Brasil, **709/709** para Estados Unidos e **312/312** para Canadá. Os 22 destinos brasileiros omitidos continuaram na fila de consultas diretas. A rodada ampla retomou a partir de 6.000 partições e sem recriar o banco.
- Às **16h36 BRT**, o histórico do **PP-254** mostrou **TUN–LAX** com **227.063 lb**, **844.456 quotas** e **US$ 2.542.350** de receita. O primeiro **LAX–TUN** mostrou as mesmas 227.063 lb, 814.085 quotas e US$ 2.451.390 de receita. O retorno registrou **3,73%** a mais de quotas. Aos preços observados no ciclo, de US$ 1.990 por 1.000 lb e US$ 149 por 1.000 quotas, a reposição dos dois insumos do retorno seria **US$ 577.679,31**. O índice de custo aplicado e a ocupação desse retorno ainda precisam de confirmação para calibrar a projeção.
- As prévias de uma unidade para Los Angeles repetiram **US$ 216.079.503** para o A380-800 Trent 972 de **443/42/24**, **US$ 6.840.196** para o A320-200 CFM56-5 de **140/6/4** e **US$ 51.000** para o Cessna 172 de **3/0/0** assentos Y/J/F. O saldo de **US$ 237.330.829** coincidiu antes e depois dos retornos por `Back`. O preço cobrado, o comprovante da abertura da rota e os valores devidos continuam pendentes. Nenhum pedido foi enviado e **G0** permanece.
- A captura autenticada das **16h36–16h40 BRT** conciliou **224 aeronaves**, 12 páginas de Routes e 30 hubs. Confirmou a mesma leitura de saldo, uma vaga PAX, uma aeronave estacionada e uma manutenção sem valor devido confirmado. O replay A3/A4 indexou **461.277 combinações** em **1.437 amostras de 19 hubs próprios** e bloqueou as **157** combinações avaliadas. O replay A6 indexou **31.779 combinações** com **99 amostras** de um hub externo e confirmou preço e pontos de dois hubs. Os **139** itens avaliados continuaram pendentes. Nenhum cenário atingiu os requisitos de publicação econômica.
- A suíte isolada do perfil em uso passou com **2.525 testes no Windows e um pulado**, mais **16 testes do instalador Linux em WSL**. O teste de migração cobre a retomada de partições saturadas já persistidas, a interseção entre janelas, respostas fora do teto e a recuperação por consulta direta.

## 2026-11-26 — Retomada da pesquisa nativa e conciliação de LAX–TUN (G0)

- O Chrome dedicado retomou a fila às **16h22 BRT**, conservando os **38.987 pares** gravados antes da interrupção. Às **16h26 BRT**, o SQLite tinha **46.792/117.180 pares com demanda**, **4.256/6.960 partições processadas** e **7.805 pares observados nos últimos 15 minutos**. A coleta segue em modo somente leitura. A cobertura vigente em 15 minutos permanece parcial.
- `ACCOUNT` antes e depois e `Overview` confirmaram **US$ 237.330.829**. O hangar PAX tinha **224/225** ocupados e havia uma aeronave em Parked. `Pending` mostrava zero entregas e uma manutenção com cerca de 30 minutos restantes, sem valor devido. `Summary` registrou **US$ 49.077.998** de receitas e **US$ 6.089.758** de despesas em 24 h, com zero em `A/C Orders` e `Route fees`. As 30 linhas do histórico e as dez despesas recentes consultadas ficaram sem os comprovantes da aquisição do PP-254 e da abertura de LAX–TUN. O caixa líquido permanece indeterminado.
- Duas consultas correlacionadas de LAX–TUN confirmaram **Daily 1.341/514/112** e **Today 965/479/91** em Y/J/F, pista de **10.499 ft** no destino, uma aeronave na rota, uma aeronave apta e aviso de evento. A amostra serve para conferência da demanda exibida. O evento e as lacunas de conciliação mantêm a projeção econômica e a homologação real bloqueadas. Nenhum pedido foi enviado.
- A pesquisa histórica conserva até três casas decimais da distância exibida. LAX–TUN tem **10.515,260 km** e entra no filtro inteiro de **10.516 km**. A importação passou a exigir o perfil e a versão do snapshot correspondentes. O ensaio isolado com os dois Parquet fixados importou **117.180/117.180 pares** em **3,109 s**, passou no `PRAGMA quick_check` e rejeitou o mesmo snapshot no perfil `other` sem criar o banco. A suíte Windows passou com **2.523 testes e um pulado**. Após os ajustes, passaram **33 testes focados** e os **16 testes do instalador Linux** no WSL.

## 2026-11-26 — Pesquisa histórica no painel e corte de 15 minutos da varredura nativa (G0)

- **Hubs → Pesquisa histórica de rotas** passou a consultar a matriz pública de demanda diária de passageiros do início de 2020. O usuário seleciona um hub da captura, alcance máximo, pista mínima e demanda mínima por classe Y/J/F. O painel mostra até 25 destinos por maior demanda total. O importador verifica o SHA-256 dos dois arquivos da revisão fixada, concilia o universo auditado e publica o SQLite no perfil somente se a importação estiver completa. A leitura local independe de token, DuckDB e sessão do jogo. [Revisão verificada](https://github.com/abc8747/am4/tree/795aaa4be38dc4bb4216d5ea6506896921dff2ae/src/am4/utils/data) · [Origem da matriz](https://abc8747.github.io/am4/guides/demand/) · [Licença MIT](https://github.com/abc8747/am4/blob/795aaa4be38dc4bb4216d5ea6506896921dff2ae/LICENSE)
- O perfil principal importou **117.180/117.180 pares de 30 hubs próprios para o catálogo de 3.907 aeroportos** em **4,047 s**. A verificação de integridade do SQLite passou. LAX–TUN apareceu no Chrome com **1.341/514/112 Y/J/F**, **10.515 km** e **10.499 ft**. Na comparação anterior, 179 de 3.415 pares divergiram da leitura nativa. A pesquisa histórica mantém `verified=false` e `execution_available=false`. As classificações de investimento exigem dados atuais verificados.
- A varredura nativa autorizada conciliou o catálogo em **79,328 s**. Entre **15h47min39s e 16h02min39s BRT**, 151 lotes no Chrome e até quatro pesquisas simultâneas registraram **26.463/117.180 pares com demanda (22,58%)** e processaram **2.416/6.960 partições (34,71%)**. A janela incluiu **25,937 s** de conferência financeira. A coleta continuou no mesmo arquivo com a autorização já concedida. O painel agora informa quantos pares do ciclo atual receberam observações nos últimos 15 minutos. A cobertura nessa janela ficou parcial. A leitura nativa de LAX–TUN repetiu **1.341/514/112** com aviso de evento. `Today`, custos por candidato, elegibilidade e pesquisa a partir de hubs externos seguem com validações próprias.
- Às **15h49 BRT**, `ACCOUNT` e `Overview` confirmaram **US$ 217.519.296**. O hangar PAX mostrou **224/225** ocupados e Parked estava vazio. Havia uma entrega e uma manutenção com prazos e sem valores devidos visíveis. `Finances → History → Summary` trouxe **US$ 5.486.926** de despesas e **US$ 50.182.729** de receitas em 24 h, com zero em `A/C Orders` e `Route fees`. As 30 linhas do histórico e os 11 lançamentos recentes em `Expenses` ficaram sem comprovante individual dos **US$ 216.079.503** do PP-254 ou dos **US$ 1.063.229** de LAX–TUN. Ambos são referências históricas fora dos compromissos a deduzir. O caixa líquido permanece indeterminado.
- O usuário autorizou o Cessna 172 como piloto condicionado à homologação. O executor está disponível em simulação e G0 continua vigente. Um teste real exige checkout verificado vinculado ao plano, caixa após compromissos e reconciliação independente do pedido e do débito. A sessão do jogo permaneceu em modo somente leitura e nenhum pedido foi enviado.

## 2026-11-26 — Varredura de demanda sem token e prévias com vaga no hangar (G0)

- O painel em **Hubs → Varredura nativa de demanda** pede confirmação explícita, exibe o aviso de cobertura incompleta e acompanha fila, progresso, pausa e conclusão. A coleta roda no Chrome autenticado do worker, em lotes de até quatro requisições simultâneas, e confirma a companhia antes e depois de cada lote. O progresso e os dados ficam no SQLite `data/native_demand.sqlite3` de cada perfil. É possível retomar após reiniciar o worker, autorizar a retomada de um lote interrompido pelo jogo e solicitar uma atualização após concluir.
- A fila concilia o catálogo nativo dos hubs próprios com os países e aeroportos do mapa. Pesquisa por país primeiro e verifica cada destino omitido por consulta direta. Guarda `Daily` Y/J/F, distância e pista quando presentes, aviso de evento e horário de leitura. O progresso distingue pares pesquisados de pares com demanda registrada. O histórico pode ser consultado por par no painel autenticado em `GET /api/research/demand?origin_id=1440&destination_id=432`. O levantamento amplo aguarda autorização no painel. A meta de 15 minutos para demanda vigente continua sem demonstração. `Today`, elegibilidade operacional, origens externas e economia da rota exigem suas respectivas provas.
- No Chrome dedicado, a amostra **LAX → Tunísia** fechou **9/9** destinos na fila de teste às 15h40 BRT. Após reabrir o SQLite, LAX–TUN retornou **1.341/514/112** Y/J/F, pista de **10.499 ft** e aviso de evento. Esse resultado certifica o recorte testado. A fila ampla e a cobertura global permanecem pendentes.
- O hangar PAX passou de **225/225** para **224/225** entre as consultas das 15h31 e 15h36 BRT. O formulário nativo fechou três prévias em Los Angeles (`24323457`). O **A320-200 CFM56-5** de **140/6/4** custou **US$ 6.840.196** na prévia. O **A380-800 RR Trent 972** de **443/42/24** para LAX–TUN repetiu **US$ 216.079.503**. O menor preço entre os **311** modelos PAX foi o **Cessna 172**, com **US$ 51.000** também confirmados na tela de configuração para **3/0/0**. O saldo antes e depois das duas últimas prévias foi **US$ 217.519.296**. Todos os formulários foram fechados pela etapa de retorno. Nenhum pedido foi enviado.
- A repetição da prévia confirma configuração e preço exibido. A cobrança histórica do PP-254, o comprovante da taxa LAX–TUN e os valores das pendências continuam sem conciliação individual. `price_verified=false`, `budget_after_reservations_and_limits=null` e **G0** continuam vigentes. A suíte Windows registrou **2.521 testes aprovados e um pulado**, excluído o arquivo específico do instalador Linux.

## 2026-11-26 — Demanda em lote, caixa e prévia autenticada de compra (G0)

- O Chrome dedicado executou **120/120 pesquisas nativas em 25,92 s** nos 30 hubs próprios, com até quatro consultas simultâneas, distância de até 20.000 km e pista a partir de 1.000 ft. A amostra trouxe **3.415 pares únicos**, dos quais 3.236 com a mesma demanda diária Y/J/F da matriz histórica e 179 com valores diferentes. Dos 25.164 pares geográficos dos seletores dos quatro países, retornaram 270/270 na Tunísia, 145/149 na Jamaica, 1.500/3.478 no Brasil e 1.500/21.267 nos Estados Unidos. **59/120** recortes coincidiram com o conjunto geográfico, e as 60 consultas de Brasil e Estados Unidos atingiram o teto de 50 linhas. Os denominadores incluem destinos que ainda podem ser excluídos por critérios operacionais. Houve aviso de evento em 119 respostas. A extrapolação das 6.960 consultas iniciais dá cerca de **25 minutos**, antes de qualquer complementação. A cobertura vigente em 15 minutos continua sem comprovação. A medição da API oficial ainda depende do token autorizado.
- Quatro consultas diretas recuperaram os quatro destinos omitidos em KIN–Jamaica, a 8–135 km da origem, e completaram esse recorte geográfico. A lista por país tinha retornado zero mesmo com os destinos passando pelos filtros informados. Em duas leituras do detalhe de **LAX–TUN**, `Daily` ficou em **1.341/514/112** e `Today` em **965/479/91** Y/J/F, com uma aeronave na rota, nenhuma apta para abertura e aviso de evento. Os valores são observações nativas da janela.
- O ciclo autenticado do worker levou **236,36 s** e conciliou a frota paginada (12/12 páginas e 222 aeronaves roteadas) e o catálogo dos 30 hubs, 232 países e 3.907 destinos. O catálogo representa 117.180 pares geográficos direcionados com origem própria e inclui 3.877 aeroportos externos. Rotas, modelos, motores e preços continuam com cobertura parcial. O cabeçalho `ACCOUNT` e a captura auditada repetiram **US$ 189.115.744** às 15h16–15h17 BRT, confirmando o saldo de `Overview`.
- `Overview` mostrou **US$ 189.115.744** por volta das 15h11 BRT, uma entrega e duas manutenções. `Hangars` confirmou **225/225** vagas PAX ocupadas e `Parked` permaneceu vazio. O resumo de 24 h conciliou **US$ 24.015.154** de despesas, sendo US$ 19.525.911 de combustível, US$ 2.724.369 de quotas e US$ 1.764.874 de taxas de rota. `A/C Orders` e `Hubs` ficaram zerados na janela. O histórico detalhado de 30 linhas e os 13 lançamentos de `Overview → Expenses` (até 59 minutos) não identificaram os débitos procurados. `Maintenance → Plan` mostrou o PP-254 sem valor de cobrança. As referências de **US$ 216.079.503** para o A380 configurado e **US$ 1.063.229** para LAX–TUN continuam sem vínculo individual com os débitos e ficam fora das deduções do caixa atual. Os valores devidos pela entrega e pelas duas manutenções também seguem em aberto. `commitments_verified=false` e `budget_after_reservations_and_limits=null`.
- Ao repetir a prévia de LAX–TUN, o formulário confirmou o A380-800, RR Trent 972 e Los Angeles (opção `24323457`). O aviso nativo de saldo insuficiente interrompeu a prévia antes da cabine. Faltavam **US$ 26.963.759** para a cotação anterior da aeronave, antes da abertura de rota e de outras despesas. A leitura de 11h03 BRT segue como referência de checkout para 443/42/24 assentos Y/J/F. `price_verified=false` e `execution_available=false`. O jogo permaneceu em somente leitura e nenhum pedido foi enviado.
- A contraprova de formulário com um A320-200 CFM56-5, também em Los Angeles, exibiu preço inicial de **US$ 6.770.196**, sem aviso de saldo. Com o hangar cheio, a tela mostrou `Upgrade hangars` e omitiu o botão de configuração. A prévia abortou antes da cabine e do preço final. A homologação simulada e a leitura do checkout de 11h03 continuam as referências para validar o vínculo entre hub, rota, motor, cabine e preço.
- **295 testes focados passaram** no Windows, incluindo a cabine da rota, hub, pré-voo, executor, diário de compra, finanças, worker e auditoria de demanda. A compra planejada segue em **G0**. O perfil local tinha `autobuy_aircraft=on` e `dry_run=off`, com o planejamento desabilitado. O fluxo normal da frota ainda pode acionar a compra legada quando suas condições são satisfeitas. A compra em produção permanece sem homologação.

## 2026-11-26 — Auditoria da API de demanda e reconciliação em aberto (G0)

- `scripts/audit_live_demand.py` consulta `fields=research` por ICAO, confronta os pares retornados com os IDs do catálogo nativo e registra lacunas, duplicatas, cota e tempo. A janela padrão é de 900 segundos. O utilitário encerra a coleta ao detectar erro do serviço, esgotar a cota ou atingir o prazo. Use `python scripts/audit_live_demand.py data/audited_game_snapshot.json` com `AM4_API_ACCESS_TOKEN` no ambiente do processo. `--external-origin <ICAO>` inclui uma origem adicional e pode ser repetido. `--export <novo.csv>` salva a amostra local para comparação com o Chrome. A saída mantém `verified=false` e `execution_available=false`.
- A API oficial requer token e documenta até 500 chamadas em 24 horas. Um levantamento dos 30 hubs próprios cabe nessa cota. Uma chamada para cada uma das 3.877 origens externas exigiria pelo menos oito janelas de cota. A resposta documentada traz Y/J/F e requer comparação com a pesquisa nativa. A demanda residual `Today` depende da leitura no jogo. [AM4 Developer API](https://airline4.net/api/docs/)
- Com respostas simuladas e o catálogo auditado, o utilitário percorreu as 30 origens em **0,14 s** e representou **117.060/117.180 pares**. Os quatro IDs sem código conciliado na referência local são **565, 964, 3241 e 3541**. A simulação mede o processamento local. A demanda vigente e o prazo de 15 minutos dependem de medir o endpoint autorizado e confrontar os retornos com o Chrome. O token estava ausente e a primeira tentativa de autenticação no Chrome dedicado expirou após o preenchimento salvo. A janela foi reaberta para autenticação manual em modo somente leitura.
- A última captura autenticada registrou **US$ 170.767.034** de saldo, **225/225** vagas PAX ocupadas, uma entrega e duas manutenções com valores devidos desconhecidos. O resumo de 24 horas conciliou **US$ 3.546.061** em despesas com combustível (US$ 587.787), quotas (US$ 1.193.400) e taxas de rota (US$ 1.764.874). As categorias de aeronaves e hubs estavam zeradas. A referência histórica segue em **US$ 216.079.503** para a configuração associada ao PP-254 e **US$ 1.063.229** para a abertura LAX–TUN. Falta o recibo que vincule cada lançamento à operação. O caixa disponível para investir segue indeterminado e a compra automática permanece em G0, com o executor homologado em simulação. A rodada manteve o jogo em somente leitura.

- Validação no Windows com **2.464 testes aprovados e um pulado**, excluído o arquivo do instalador Linux. Ruff e `git diff --check` passaram. O utilitário histórico voltou a cobrir **117.180/117.180 pares** em **3,61 s** após a mudança no carregamento do DuckDB.

## 2026-11-26 — Triagem global em lote e homologação isolada de LAX–TUN (G0)

- A matriz pública histórica do AM4, fixada na revisão `795aaa4be38dc4bb4216d5ea6506896921dff2ae`, coincidiu por ID com os **3.907 aeroportos** do catálogo autenticado. A triagem retornou **117.180/117.180 pares direcionados** dos 30 hubs próprios em **3,70 s**, incluindo a exportação. A aquisição dos arquivos para a auditoria levou cerca de 5,3 s. A matriz completa de 7.630.371 pares implica outros **15.143.562 pares direcionados** com origem nos 3.877 aeroportos externos. A demanda base coletada no início de 2020 é simétrica. [Dados da revisão](https://github.com/abc8747/am4/tree/795aaa4be38dc4bb4216d5ea6506896921dff2ae/src/am4/utils/data) · [Origem da matriz](https://abc8747.github.io/am4/guides/demand/)
- No Chrome dedicado, quatro pesquisas de origem e país levaram 19,88 s e trouxeram 282 pares únicos. Todos constavam na matriz e **267/282** tiveram Y/J/F idênticos na lista nativa, que exibia aviso de evento. LAX–TUN apresentou 1.341/514/112 em ambas as fontes. As 15 diferenças impedem tratar a matriz como demanda vigente. Demanda residual `Today`, elegibilidade e custos exigem validação própria. A API oficial documenta `fields=research` por aeroporto de origem (`dep_icao`), com limite de 500 requisições a cada 24 h. Nenhum token autorizado estava configurado. A cobertura efetiva desse endpoint e a execução em 15 minutos para demanda atual continuam sem aferição. [AM4 Developer API](https://airline4.net/api/docs/)
- O ciclo autenticado das 14h39–14h43 BRT terminou em **228,14 s**. A auditoria da frota conferiu 12/12 páginas, com 222 aeronaves com rota, zero estacionadas e três pendentes. O ciclo confirmou 30 hubs, 232 países e 3.907 destinos. A triagem processou o novo snapshot em mais **3,45 s**, com as mesmas contagens. Rotas, modelos, motores e preços continuaram com cobertura parcial.
- Para repetir a triagem, instale `duckdb==1.4.3` em um ambiente de auditoria, baixe `airports.parquet` e `routes.parquet` da revisão acima e execute `python scripts/audit_bulk_demand.py data/audited_game_snapshot.json <diretório-dos-parquets>`. Use `--export <novo.csv>` para exportar candidatos históricos com origem nos hubs próprios. O utilitário verifica os SHA-256 e confronta a matriz com o catálogo do snapshot. A saída mantém `verified=false` e `execution_available=false`.
- O total histórico de referência do PP-254 é **US$ 217.142.732**. A prévia da aeronave para LAX de **US$ 216.079.503** (A380-800, RR Trent 972, 443/42/24 Y/J/F, incluindo US$ 450.000 de cabine) e a taxa de LAX–TUN de **US$ 1.063.229** coincidem individualmente com lançamentos genéricos anteriores. Falta comprovante que vincule os débitos à matrícula e à rota. Esses valores históricos ficam fora das deduções do caixa atual. Em `Finances → History → Summary`, `A/C Orders` exibiu zero e `Route fees`, US$ 1.764.874 em 24 h, ambos agregados.
- `ACCOUNT` e `Overview` coincidiram em **US$ 170.767.034**. `Pending` e `Overview` mostraram uma entrega e duas manutenções. Os valores devidos seguem sem comprovação. `Hangars` mostrou **225/225** vagas PAX ocupadas. A seleção do RR Trent 972 e de Los Angeles funcionou no checkout; o aviso de saldo insuficiente interrompeu a prévia antes da configuração. Faltavam **US$ 45.312.469** para a cotação anterior da aeronave, antes de outras despesas. `price_verified=false`, `budget_after_reservations_and_limits=null` e `execution_available=false` seguem vigentes.
- O executor isolado foi homologado com o plano de LAX–TUN. O cenário com o caixa, a lotação e os compromissos observados fez zero tentativas até no simulador. Com caixa, reserva, capacidade e obrigações hipotéticos, houve uma tentativa simulada, timeout em `UNKNOWN` e confirmação após reinício por leitura independente, com zero reenvios. A confirmação auditada agora exige que o valor efetivamente cobrado coincida com o checkout do plano, separado da taxa de rota e das outras parcelas. Recibo sem valor, com o total da operação em vez do checkout ou com tipo inválido preserva `UNKNOWN`. O registro isolado fecha suas conexões SQLite após cada operação. Nenhum pedido foi enviado no jogo.
- Validação no Windows com **2.454 testes aprovados e um pulado**, excluído o arquivo do instalador Linux. Ruff e `git diff --check` passaram. O utilitário exportou 117.180 linhas de dados, rejeitou arquivo com SHA-256 divergente e preservou uma exportação já existente.

## 2026-11-26 — Catálogo geográfico global e fontes alternativas de caixa (G0)

- O Chrome dedicado autenticado leu os 232 países do seletor nativo de chegada em **52,38 s**, com uma requisição por vez. Os **3.907 IDs únicos** coincidiram integralmente com o mapa do jogo e com a contagem anterior do catálogo `New Hub`, que levou 144,5 s. Excluídos os 30 hubs próprios, o catálogo contém **3.877 aeroportos externos**. As 30 origens próprias e os destinos geram **117.180 pares direcionados**, excluindo a própria origem de cada par. Esses totais antecedem os filtros de pista, alcance, demanda e elegibilidade.
- O worker confere se todos os hubs próprios oferecem os mesmos países, lê o fragmento nativo de cada país uma vez e reconcilia os IDs com o mapa estável e as partições observadas no mesmo ciclo. O ciclo autenticado das **14h13min20s–14h17min01s BRT** levou **3min42s**, dos quais 73,80 s para menus e catálogo. A captura gravou a evidência em `observations.route_search_universe.destination_catalog` e conciliou **9/9 destinos** em LAX–Tunísia. Uma divergência independente na paginação manteve a frota parcial nesse ciclo. Na execução anterior, as 12 páginas da frota conciliaram e o catálogo geográfico ficou indisponível. A cobertura de rotas para investimento continua parcial.
- A medição de demanda usou 24 pesquisas nativas em seis origens para Tunísia, Jamaica, Brasil e Estados Unidos, com mínimo de 1.000 ft e teto de 20.000 km. A leitura sequencial levou **11,14 s**, cerca de 2,15 partições por segundo. Com quatro consultas simultâneas, as mesmas 24 pesquisas levaram **3,94 s**, cerca de 6,09 por segundo. As projeções para 6.960 partições são de **cerca de 54 e 19 minutos**, respectivamente, antes de janelas adicionais, consultas diretas e custos. Doze respostas atingiram o teto nativo de 50 linhas. O paralelismo ficou restrito ao ensaio. Fechar a elegibilidade econômica em 15 minutos exige uma fonte de demanda em lote com resultados conciliáveis ou outra forma de comprovar todas as exclusões sem pesquisas individuais.
- `Overview` mostrou o saldo e as pendências. A aba `Expenses` retornou 16 lançamentos, com o mais antigo marcado como 47 minutos, sem os débitos procurados ou controle para avançar no histórico. `Maintenance → Plan` identificou o **PP-254** com 46 horas de voo, 439 horas até o próximo A-check, 0,85% de desgaste e a indicação `Not at base`. A tela não identificou a base nominal nem exibiu valores em dólares. As duas fontes não forneceram comprovante de compra ou valores a pagar pelas pendências. Continuam documentadas as coincidências do débito histórico de **US$ 216.079.503** com a prévia da cabine e da taxa histórica de **US$ 1.063.229** com a abertura cotada de LAX–TUN. O total histórico de **US$ 217.142.732** segue fora das deduções do caixa atual.
- A prévia nativa em `dry_run` e o executor simulado preservam o plano que vincula o hub à rota, motor e cabine. A compra planejada segue em G0, com `price_verified=false`, `budget_after_reservations_and_limits=null` e `execution_available=false`. Passaram **2.453 testes no Windows**, com um pulado e o arquivo do instalador Linux excluído dessa execução. A rodada focada de prévia, plano, pré-voo e executor passou com **150 testes**. Ruff e `git diff --check` passaram. O jogo permaneceu em modo somente leitura.

## 2026-11-26 — Comprovante do PP-254 e universo nativo de candidatos (G0)

- O login salvo permitiu retomar o Chrome dedicado e confirmar a companhia antes e depois das consultas em modo somente leitura. `Routes → Order` abriu o catálogo de modelos e preços. Dos nove itens na lista da caixa de entrada, o único com assunto `Receipt` aparecia como recebido há dois meses. A lista e os detalhes nativos consultados não exibiram um comprovante associado ao PP-254. O preço da prévia do A380-800 em Los Angeles com RR Trent 972 e cabine 443/42/24 Y/J/F continua em **US$ 216.079.503**, incluindo **US$ 450.000** de cabine. Esse preço e a taxa de abertura cotada de **US$ 1.063.229** coincidem com lançamentos históricos genéricos. Faltam os vínculos do débito com a matrícula e da taxa com a rota. `price_verified=false` permanece.
- Às 13h49 BRT, `Pending` mostrou duas entregas e duas manutenções, sem valor em aberto nas linhas. As ofertas de antecipação de entrega custavam 20 e 3 pontos e eram opcionais. `Finances → History → Summary` mostrou zero em `A/C Orders`, `Hubs` e `Route fees` no resumo de 24 horas. A consulta não confirmou o saldo devido das pendências. O A4 mantém `budget_after_reservations_and_limits=null` para a compra planejada. Os **US$ 217.142.732** identificados no histórico permanecem fora dos compromissos a deduzir do caixa atual.
- Em `Routes → Research`, cada um dos 30 hubs próprios exibiu o mesmo conjunto de 232 opções de país de destino. A lista exclui a opção genérica `Any country`. O universo pesquisável nesses menus tem **6.960 partições únicas** de origem e país. Em uma varredura dirigida, a Tunísia conciliou **30/30 partições e 270/270 destinos do seletor**, com pista mínima de 1.000 ft e teto de 20.000 km. Os resultados vieram das listas nativas, sem consultas diretas adicionais. Restaram 6.930 partições de outros países nessa varredura. As 30 partições levaram 47,8 segundos. Uma extrapolação simples para os 232 países dá cerca de 3h05, acima dos 15 minutos de validade da captura, mesmo sem considerar pesquisas adicionais em partições com resultados omitidos.
- O modo de observação registra a enumeração em `observations.route_search_universe`. Confere o conjunto de origens com o inventário de hubs e exige que os seletores e as partições pertençam ao mesmo ciclo autenticado. O resumo divulga quantas partições foram tentadas, conciliadas e ainda faltam em cada combinação de pista e alcance, durante a validade da observação. As contagens medem a pesquisa por país e origem. A elegibilidade de aeronaves, o preço e a economia de cada rota exigem provas próprias.
- O ciclo do worker das 13h50min38s–13h53min32s BRT validou o snapshot privado com 30 hubs, 225 aeronaves e 1.179 amostras de demanda interna. A consulta configurada desse ciclo conciliou LAX–Tunísia (9/9 destinos), uma das 6.960 partições no recorte de 1.000 ft e 20.000 km. Os resultados do ciclo e da varredura manual têm janelas próprias. A observação A6 desse ciclo confirmou seis preços e encargos em pontos, com 99 amostras externas de demanda. O replay indexou 376.101 combinações internas e 31.581 externas. Os 40 itens amostrados em cada replay ficaram em `pesquisa_pendente`.
- Às 13h56 BRT, a varredura geográfica de `New Hub` leu **232/232 países**, com o seletor de países estável e **3.907 IDs de aeroporto únicos**. A comparação com o inventário nativo excluiu os 30 hubs próprios e identificou **3.877 aeroportos externos**. A leitura durou 144,5 segundos. A enumeração cobre as opções dos seletores. A6 ainda tem cobertura parcial de disponibilidade, preço, encargos e demanda por candidato.
- Validação com 2.463 testes aprovados no Linux/WSL, Ruff e `git diff --check`. A cobertura global de candidatos continua parcial e G0 permanece vigente. A atividade no jogo ficou em modo somente leitura.

## 2026-11-26 — Caixa do PP-254 e auditoria dirigida de candidatos (G0)

- O worker retomou o Chrome dedicado com o login salvo e confirmou a mesma companhia nas pontas de cada consulta. O detalhe do PP-254 repetiu a cabine de 443/42/24 assentos em Y/J/F. A prévia autenticada das 11h03 BRT totalizou **US$ 216.079.503** para essa cabine, o A380-800 com RR Trent 972 e entrega em Los Angeles. O valor inclui **US$ 450.000** de configuração (42 × US$ 5.000 e 24 × US$ 10.000). Coincide com o débito histórico `A/C Purchased`. A nova tentativa encontrou o aviso de saldo insuficiente antes da configuração. O detalhe da matrícula, o extrato recente e o resumo de 24 horas não expuseram um recibo que vincule matrícula, motor, hub, cabine e débito. `price_verified=false` permanece.
- A taxa de abertura de **US$ 1.063.229** de LAX–TUN também coincide com um lançamento histórico genérico. Os **US$ 217.142.732** associados são despesas históricas. O A4 não usa esses valores como obrigações a deduzir novamente do saldo atual. `A/C Orders` e `Route fees` vieram zerados no novo resumo. O alcance temporal efetivo do extrato e as categorias zeradas não comprovam liquidação nem ausência de compromissos.
- A interface mostrou 225/225 vagas PAX ocupadas, zero aeronaves em `Parked` e três em `Pending`. O worker classificou as três pendências como duas entregas e uma manutenção. Os cartões das entregas mostraram a opção de antecipar por 24 e 7 pontos, sem valor em dólares a pagar. Os painéis de manutenção e hangar tampouco vincularam saldos devedores aos itens. O A4 mostra o teto bruto e mantém o orçamento líquido como `null` enquanto faltam valores em aberto e evidência de liquidação. O ranking de diagnóstico e a decisão `nao_comprar` continuam disponíveis.
- Na leitura seguinte, `Pending` subiu para quatro aeronaves (duas entregas e duas manutenções). Os quatro itens identificados seguiam sem valor em aberto. `Banking → Airline account → Expenses` mostrou oito lançamentos recentes, com o mais antigo rotulado `1 hour ago`, sem paginação, débito de compra ou taxa de rota. Nenhum lançamento de reparo pôde ser vinculado aos quatro itens. Essas superfícies não confirmam zero obrigações.
- Com pista mínima de 1.000 ft, as leituras dirigidas conciliaram LAX–Tunísia (9/9), GRU–Argentina (68/68) e TXL–Congo (Kinshasa) (21/21). Em GRU–Brasil, as janelas de 20.000 e 1.261 km retornaram 50 e 44 linhas, com 93 IDs únicos. A repetição completou os 22 destinos omitidos por consulta direta e reconfirmou o seletor (115/115, excluída a origem). As rotas omitidas têm 29–389 km. Em KIN–Jamaica, `Any airport` informou que não havia resultados. O seletor permaneceu estável e as quatro buscas diretas confirmaram 4/4 destinos a 8–135 km. A admissibilidade operacional das rotas curtas continua pendente.
- O coletor reconhece o aviso nativo de resultado vazio, aguarda o AJAX antes de pesquisar e pode seguir para o próximo destino após uma tentativa expirar. O snapshot separa partições `reconciled`, `incomplete` e `unverified`. Uma partição só passa pela conciliação com os mesmos IDs no ciclo autenticado e os destinos diretos só alimentam amostras dentro dos filtros solicitados. A pesquisa externa alterna janelas ampla e configurada no modo de observação. A cobertura global continua parcial.
- A coleta dirigida usa `route_audit_origin_id` e `route_audit_country` em `[investment]`, com os limites de alcance e pista de `[settings]`. `route_audit_max_airports` e `route_audit_max_seconds` limitam as consultas diretas por partição. Os padrões são 24 destinos e 20 segundos. Para repetir GRU–Brasil nesta janela de validação, o worker usa alcance de 20.000 km, pista mínima de 1.000 ft e até 120 segundos para consultas diretas.
- Os ciclos autenticados das 13h26–13h29 e 13h29–13h32 BRT confirmaram `reconciled` em KIN–Jamaica (4/4 por consulta direta) e GRU–Brasil (93 pela lista, 22 por consulta direta). Na segunda captura, o worker conciliou 221 rotas em 12 páginas, 225 aeronaves no total e 30 hubs. O replay A3/A4 indexou 372.060 combinações a partir de 1.170 amostras. Os 40 itens avaliados continuaram pendentes. A pesquisa externa inicialmente combinou demanda recente com origens cujo catálogo já tinha vencido na janela de auditoria. No modo de observação, o coletor de demanda externa e o de detalhes agora usam os mesmos 15 minutos da captura. A regra anterior continua valendo para os demais consumidores do registro.
- Repetição autenticada das 13h37min11s–13h39min38s BRT. A captura confirmou 225 aeronaves, 30 hubs e a partição KIN–Jamaica (4/4). A6 incorporou nove hubs externos com preços e pontos vigentes, 99 amostras de demanda e uma consulta correlacionada de detalhe. O replay externo indexou 31.482 combinações. Os 40 itens avaliados em cada replay (interno e externo) ficaram em `pesquisa_pendente`, sem indicação de compra. A cobertura global e a admissibilidade dos trechos curtos continuam pendentes. Nenhum pedido foi enviado.
- Validação de código com 2.461 testes aprovados no Linux/WSL, Ruff e `git diff --check`. G0 permanece vigente, com o preço vinculado à matrícula e o caixa líquido sem comprovação.

## 2026-11-26 — Autonomia Total A2–A4/A6, conciliação do PP-254 e cobertura de candidatos (G0)

- O Chrome dedicado confirmou a companhia nas pontas do ciclo somente leitura das 13h04–13h06 BRT. `Flight history` voltou a mostrar XP-224 de LAX para TUN, com embarque de 376/35/21 em Y/J/F, receita de **US$ 2.451.390**, **227.063 lb** e **814.085 quotas de CO₂**. A duração programada foi de 6h41min, com chegada prevista às 16h29min22s BRT. As leituras de LAX–TUN e TUN–LAX repetiram `Today` de 965/479/91 sobre `Daily` de 1.341/514/112, com aviso de evento. A diferença corresponde exatamente ao embarque observado. O trecho de volta ainda não constava no histórico.
- **Compra do PP-254.** O lançamento histórico `A/C Purchased` de **US$ 216.079.503** coincide com a prévia de Los Angeles e cabine 443/42/24, composta de US$ 215.629.503 de base e US$ 450.000 de assentos. A entrega em LAX consta de `Pending` e `Parked`. O RR Trent 972 é a única das três variantes que reproduz o combustível e a duração do primeiro voo com diferenças de 1 lb e 1 segundo no índice 200. O lançamento é genérico e a identificação do motor permanece inferida. `price_verified=false` segue para a combinação de compra.
- **Abertura de LAX–TUN.** A revisão recuperou no registro histórico de `Finances → History` a despesa de **US$ 1.063.229** na categoria de abertura de rota, que coincide exatamente com a prévia elegível do PP-254 às 09h42. A interface do extrato não expôs o ID da rota no lançamento. Os dois lançamentos associados somam **US$ 217.142.732** antes de qualquer custo atribuível ao hangar. Às 13h09, `Expenses` exibiu 11 lançamentos recentes, com o mais antigo marcado como uma hora, e os dois débitos históricos estavam fora da lista. O resumo rotulado como 24 horas continuou com `A/C Orders` e `Route fees` zerados. A regra do agregado e os compromissos de caixa seguem sem comprovação.
- **Custos do primeiro trecho.** A tabela usa o consumo registrado no voo e converte as cotações nativas de reposição. A provisão de A-check é de **US$ 96.074,92**, calculada com 401 minutos e a referência do catálogo de US$ 6.468.885 a cada 450 horas. Valores em dólares arredondados uma vez, no total.

| Referência de preço por mil | Combustível e CO₂ (US$) | Com provisão de A-check (US$) | Receita menos custos da tabela (US$) |
| --- | ---: | ---: | ---: |
| Janela da decolagem às 09h48 (US$ 670 por 1.000 lb, US$ 181 por 1.000 quotas) | 299.481,60 | 395.556,52 | 2.055.833,48 |
| Consulta das 13h04 (US$ 1.810 por 1.000 lb, US$ 197 por 1.000 quotas) | 571.358,78 | 667.433,70 | 1.783.956,30 |

- **Tarifas em operação.** Às 13h10, o detalhe nativo e estável do PP-254 exibiu **US$ 4.800/9.690/14.640 em Y/J/F** nos campos de tarifa vigente. Aplicadas aos 376/35/21 passageiros, as três tarifas reproduzem exatamente os **US$ 2.451.390** do XP-224. O mesmo detalhe apresentou US$ 4.377/8.973/13.820 como tarifas sugeridas em `Auto`, que somariam US$ 2.250.027 nessa ocupação.
- O histórico traz quantidades consumidas e receita. O custo contábil do estoque usado, pessoal incremental, outros encargos e manutenção efetivamente debitada por trecho seguem sem vínculo. Os dois débitos iniciais ficam fora do cálculo por trecho.
- **Cobertura pelo seletor.** Entre 13h10 e 13h11 BRT, o Chrome confirmou a mesma companhia nas duas pontas de uma leitura direcionada, com pista mínima de 1.000 ft. A coluna de destinos conta os IDs do seletor estável, excluída a própria origem. A seleção direta pode incluir trechos abaixo do limite implícito da lista. A elegibilidade operacional dos trechos curtos segue pendente.

| Origem e país de destino | Teto e linhas em cada janela | IDs na lista | IDs por busca direta | Destinos do seletor conciliados |
| --- | --- | ---: | ---: | ---: |
| LAX → Tunísia | 20.000 km (9) | 9 | 0 | 9/9, incluindo TUN |
| GRU → Argentina | 20.000 km (50), 1.723 km (19) | 68 | 0 | 68/68 |
| TXL → Congo (Kinshasa) | 20.000 km (21) | 21 | 0 | 21/21 |
| GRU → Brasil | 20.000 km (50), 1.261 km (44) | 93 | 5 | 98/115 |

- A captura identifica a origem `465` como TXL. O registro anterior a chamou de Kinshasa, que é o nome no filtro de país de destino. No Brasil, as cinco buscas pontuais confirmaram destinos entre 249 e 386 km. Dezessete dos 115 IDs ficaram sem nova confirmação nesse ciclo. A rodada anterior das 03h14–03h17 havia conciliado todos os 115 com 22 consultas diretas. A consulta a KIN → Jamaica não produziu uma partição verificável.
- **Cobertura do worker.** O snapshot privado das 13h06 passou pelas verificações de esquema, perfil e fingerprint. Foram lidas as 12 páginas de Routes. Divergências entre as varreduras impediram a certificação da frota nesse ciclo. A partição nativa de ICN para Estados Unidos, com pista mínima de 5.000 ft e teto de 6.000 km, retornou 21 destinos para as 709 opções do seletor. Os outros 688 IDs ficaram sem verificação nessa partição, cujo seletor contém aeroportos fora do filtro.
- No replay A3/A4 da mesma captura, 30 hubs próprios, 15 com amostras, 1.051 rotas amostradas e 311 modelos produziram um índice de 334.218 combinações. As páginas nos offsets 0, 40, 167.080 e 334.200 devolveram 138 itens em `pesquisa_pendente`, todos com o gate contábil bloqueado. A6 indexou 31.800 combinações a partir de 100 amostras em dois dos nove hubs externos presentes no replay. As páginas nos offsets 0, 40 e 31.760 devolveram 120 itens em `pesquisa_pendente`. As duas filas mantiveram `purchase_eligible=false`. O índice e as páginas comprovam a navegação da fila observada. Cobertura global, esgotamento dos candidatos internos e homologação para compra seguem pendentes. A coleta ficou em modo somente leitura. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A2/A3/A6, demanda residual, custos de rota e hubs externos (G0)

- Entre 12h56 e 12h57 BRT, o Chrome dedicado leu os detalhes nativos com a companhia confirmada antes e depois. Os quatro itinerários em operação exibiram `Today` no detalhe. As rotas sem operação exibiram `Daily`. As amostras preservam o aviso nativo de evento.

| Rota | `Today` Y/J/F | `Daily` Y/J/F | Aeronaves na rota |
| --- | --- | --- | ---: |
| LAX–TUN e TUN–LAX | 965/479/91 | 1.341/514/112 | 1 |
| DAC–FNJ | 824/98/51 | 1.081/510/272 | 1 |
| ORD–CCS | 566/146/55 | 831/481/185 | 1 |
| DFW–CCS | 986/51/208 | 1.743/320/273 | 1 |
| BCN–SHA | Ausente | 1.991/376/176 | 0 |
| AQA–EZE | Ausente | 693/416/109 | 0 |
| LIS–JFK | Ausente | 1.012/521/255 | 0 |

- As duas consultas de LAX–TUN exibiram os mesmos números nos sentidos opostos. O residual equivale ao diário menos os 376/35/21 passageiros do primeiro trecho do PP-254. O histórico da aeronave confirmou novamente 227.063 lb, 814.085 quotas de CO₂ e receita de US$ 2.451.390. Os três valores por classe da prévia (US$ 4.377/8.973/13.820) continuam como referência do formulário. A receita do voo, isoladamente, não identifica as tarifas efetivamente cobradas por classe.
- `Flight history` mostrou as quantidades abaixo para os últimos trechos. Após um limite de espera na consulta direta, o worker leu US$ 1.940 por 1.000 lb e US$ 162 por 1.000 quotas de CO₂ às 12h57 BRT, com validade até cerca de 13h00min28s BRT. A tabela estima a reposição dos dois insumos à cotação desse ciclo. O valor de US$ 294.253,84 para o PP-254 na rodada anterior usava os preços das 11h25 BRT, de US$ 690 e US$ 169 por mil, respectivamente.

| Trecho registrado | Aeronave | Combustível (lb) | CO₂ (quotas) | Reposição (US$) |
| --- | --- | ---: | ---: | ---: |
| LAX–TUN | PP-254 | 227.063 | 814.085 | 572.383,99 |
| CCS–ORD | PP-118-3 | 76.691 | 111.269 | 166.806,12 |
| CCS–DFW | PP-118 | 74.906 | 99.726 | 161.473,25 |

- Nenhum dos detalhes apresentou aeronave apta na nova leitura. A taxa de abertura de US$ 1.063.229 para LAX–TUN e a de US$ 996.630 para BCN–SHA permanecem cotações de prévias elegíveis anteriores. Às 12h59 BRT, `Finances` mostrou `Route fees` agregado de US$ 0 nas últimas 24 horas, sem identificação por rota. A conciliação do débito da rota, as tarifas efetivas por classe e os custos incrementais completos por candidato continuam pendentes.
- O seletor de `New Hub` mostrou 232 opções de país ou região. Pela seleção de aeroporto, oito candidatos brasileiros (AQA, AJU, AFL, ARU, BGX, ATM, MEU e AUX) mostraram US$ 12.336.000 e 20 pontos cada. O catálogo também confirmou LIS e FRA por US$ 60.909.000 e JFK por US$ 54.818.100, todos com 20 pontos e fora dos 30 aeroportos próprios do seletor nativo. A pesquisa de saída personalizada reuniu 50 destinos de cada uma das origens AQA, AJU e AFL. A consulta AQA–TUD confirmou `Daily` de 111/70/53, sem `Today` e com zero aeronaves aptas. A cobertura externa segue parcial.
- O worker em `--observe-game` passou a coletar preços de novos hubs, demanda externa e detalhes correlacionados no ciclo autenticado. A leitura externa usa a lista nativa de hubs próprios para excluir suas origens, tem orçamento limitado e também pode ocorrer com o planejamento de investimentos desabilitado. O ciclo das 12h57–12h59 BRT registrou três preços, 50 destinos a partir de Frankfurt e um detalhe externo adicional. O snapshot privado passou na validação local de esquema, perfil e fingerprint. A auditoria conciliou 222 aeronaves em Routes (12 páginas), zero em Parked e três em Pending. Os 30 painéis de operações foram enumerados, com conciliação incompleta neste ciclo. Os compromissos financeiros e as opções de entrega ficaram sem confirmação no mesmo snapshot.
- O replay A6 do snapshot trouxe 40 combinações na primeira página. Todas ficaram em `pesquisa_pendente`, com `purchase_eligible=false` e cobertura parcial. Entre as lacunas estão preço de motor, demanda residual, taxa de rota, custos, compromissos de caixa e cenário externo completo. O fluxo normal mantém sua política de planejamento. A coleta foi somente leitura. A compra planejada permanece bloqueada em G0, com `price_verified=false` para o preço de compra efetivamente cobrado. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).
- A regressão do worker exige as três novas leituras na ordem esperada e confirma a captura somente quando a companhia coincide nas duas pontas do ciclo. A suíte em diretório isolado passou com 2.432 testes e um pulado por permissões POSIX. `tests/test_instalacao_linux.py` ficou fora da suíte Windows. Ruff e `git diff --check` passaram.

## 2026-11-26 — Autonomia Total A2/A5, prévia autenticada LAX–TUN e hubs de entrega (G0)

- Às 11h03 BRT, o worker autenticado no Chrome dedicado executou `fleet.order_aircraft` em `dry_run` com um plano de homologação para LAX–TUN (`1440`–`432`). O formulário confirmou **1 A380-800** (`2`), **RR Trent 972** (`7`), entrega em **Los Angeles** (`24323457`), **443/42/24 assentos Y/J/F** e **US$ 216.079.503** exibidos. A taxa de abertura de US$ 1.063.229 pertence à rota e ficou fora da cotação de compra. A prévia releu cabine e total e voltou à tela inicial pelo botão `Back`. A sessão confirmou a mesma companhia depois da consulta. Nenhum pedido foi enviado.
- A captura auditada das 11h03min26s–11h05min40s BRT validou 221 rotas em 12 páginas, zero aeronaves estacionadas, três pendências e 251 vínculos nos 30 painéis de operações. Os 30 IDs da gestão coincidiram com as 30 opções habilitadas de entrega para o modelo amostrado. O painel de `24323457` mostrou `KLAX/LAX` e 13 operações, e o seletor de pesquisa trouxe LAX como aeroporto `1440`. A coleta também registrou pessoal, hangar, finanças e cotações de US$ 690 por 1.000 lb de combustível e US$ 169 por 1.000 quotas de CO₂.
- O worker de observação passou a registrar `observations.delivery_hub_crosswalk` no snapshot privado. O cruzamento exige a opção de entrega habilitada no formulário, o ID explícito e os códigos IATA/ICAO do painel de gestão e o ID do aeroporto no seletor de pesquisa do mesmo ciclo autenticado. O registro de hubs usa o código do seletor quando disponível e recorre ao catálogo local nos demais casos. IDs duplicados, conjuntos divergentes, códigos ambíguos e evidência fora da janela tornam a coleta inconclusiva. A associação vale para o modelo amostrado.
- A auditoria das 11h07–11h09 BRT rejeitou o cruzamento depois que um teste de escala gravou dois aeroportos fictícios no registro local durante a coleta. O teste passou a usar um registro temporário. Suas duas variações passaram em diretório isolado, sem criar o registro de dados do perfil. A suíte Windows anterior ao ajuste da fixture teve **2.432 aprovados e um pulado**, com exclusão de `tests/test_instalacao_linux.py`. Após o ajuste, **384 testes focados** passaram, incluindo captura, prévias, expansão e registro de hubs. Ruff e `git diff --check` passaram.
- A repetição autenticada das 11h14min53s–11h17min48s BRT verificou **30 vínculos únicos** para o B747-400 (modelo `1`), com todas as opções habilitadas. LAX apareceu como `KLAX/LAX`, aeroporto `1440` e ID de gestão e entrega `24323457`, a mesma opção observada na prévia do A380-800. A frota e os painéis de operações voltaram a conciliar, com 221 rotas em 12 páginas, zero aeronaves em Parked, três pendências e 251 vínculos. Uma partição de pesquisa da origem `2149` ficou com cinco IDs pendentes. A nova consulta ao mercado de combustível e CO₂ atingiu o limite de espera. As cotações registradas acima pertencem à primeira captura.
- O replay local A3/A4 indexou **251.220 combinações** a partir de **795 amostras de rota em 12 hubs**. Avaliou 140 combinações nas duas primeiras páginas, uma página intermediária e a última. Todas ficaram bloqueadas, com cobertura parcial e lacunas comuns em preço de aeronave e motor, taxa de rota, demanda residual, tarifas e custos recorrentes. O replay A6 retornou zero candidatos, com catálogo externo e demanda a confirmar. Nenhum caso foi publicado. A política retornou `execution_available=false` em G0.
- A coleta mantém `price_verified=false`. O valor cobrado, a conciliação de compromissos, a base permanente por aeronave e a cobertura de candidatos seguem pendentes em G0. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A5, cabine da rota na prévia nativa de compra (G0)

- No Chrome dedicado autenticado, `Fleet → Order → A380-800 → Configuration` confirmou uma unidade do modelo `2`, motor **RR Trent 972** (`7`), entrega em **Los Angeles** (`24323457`) e **443/42/24 assentos Y/J/F**, a configuração usada no PP-254 em LAX–TUN. As alças do controle de 600 posições ficaram em 443 e 528. `#acCost` mostrou **US$ 216.079.503**, incluindo US$ 450.000 de configuração sobre os US$ 215.629.503 iniciais. A consulta saiu pelo botão `Back` e confirmou o retorno ao detalhe. O pedido não foi enviado.
- A entrada de prévia do worker usa a intenção de compra A5 e recebe do chamador o valor nativo de entrega, cuja identificação é distinta do ID de aeroporto da rota. Em `dry_run`, seleciona hub e motor, ajusta as duas alças pelas teclas nativas e confere o layout exato. Duas leituras do mesmo formulário devem concordar e o total exibido precisa bater com `checkout_cost`. A taxa de abertura pertence ao investimento da rota e fica fora desse total. A prévia fecha pelo botão `Back` ao concluir ou ao rejeitar a configuração. Chamadas planejadas fora de `dry_run` são bloqueadas antes de abrir o formulário.
- O replay local cobre o plano LAX–TUN e o fechamento após divergências de preço, assentos, hub, motor e saldo. Também cobre uma cabine que o controle não representa e a recusa de execução em modo real. Foram aprovados **194 testes focados** e **2.427 testes na suíte Windows**, com um pulado e exclusão de `tests/test_instalacao_linux.py`. Ruff e `git diff --check` passaram.
- A confirmação autenticada foi manual no Chrome. A execução da prévia no worker autenticado segue pendente. A tela não forneceu um campo independente de preço final comprovado. O valor exibido é anterior ao envio, `price_verified` segue em `false` e a automação planejada permanece em G0. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A3/A4/A5, compra vinculada ao hub, à rota e à cabine (G0)

- O teste de ponta a ponta parte de uma captura sintética com dois hubs próprios e uma rota candidata por hub. A3 calcula demanda residual por classe, cabine e economia. A4 compara os candidatos elegíveis e seleciona o investimento vencedor. A5 usa o hub de entrega, a rota, o modelo, o motor e os 100/20/10 assentos Y/J/F dessa mesma decisão. O executor simulado confirma uma encomenda para essa combinação e o painel exibe os assentos na prévia.
- A intenção de compra preserva os assentos das três classes. O pré-voo exige correspondência exata da cabine e do preço total com configuração incluída. Uma intenção auditada antiga sem cabine precisa ser refeita. Se a evidência da encomenda divergir da cabine aprovada, o journal conserva o estado `UNKNOWN` após reinício e bloqueia novo envio até a conciliação. Um cenário de teste cobre a alteração da cabine entre o pré-voo e o envio simulado.
- A3 passou a calcular ROI e prazo de retorno sobre o lucro diário já arredondado para centavos. A4 usa o mesmo valor para conferir a consistência do candidato. A simulação dos dois hubs cobre o caso que antes podia excluir uma rota válida pela diferença de arredondamento.
- O modo somente leitura coleta evidências. A compra planejada permanece em G0 com `execution_available=false`. Falta integrar a configuração nativa de assentos ao executor do worker e homologar a trilha de ponta a ponta. A compra legada usa configuração independente. A homologação requer cobertura autenticada das rotas candidatas, o vínculo entre hub de entrega e aeroporto, a prova do preço final com a cabine e um registro independente para conciliar pedido, matrícula, valor, hub, modelo, motor e assentos.
- A suíte Windows passou com **2.419 testes aprovados e um pulado**, com exclusão de `tests/test_instalacao_linux.py`. Ruff e `git diff --check` passaram. A revisão usou simulação local e não enviou pedidos ao jogo. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A1/A5, conciliação do débito do PP-254 (G0)

- No Chrome autenticado, a tela nativa `Order → A380-800 → Configuration` cotou **US$ 216.079.503** com **RR Trent 972**, entrega em **Los Angeles (LAX)** e cabine **443/42/24 Y/J/F**, idêntica à ficha do PP-254. A opção nativa de entrega tem ID `24323457`. O registro anterior em `Pending` e a chegada em `Parked` confirmam Los Angeles como destino de entrega. A coincidência exata com o débito `A/C Purchased`, observado às 08h11–08h16 BRT, sustenta a associação ao PP-254. O lançamento é genérico e a ficha da frota não mostra o comprovante original.
- O primeiro LAX–TUN (XP-224, 10.516 km) registrou 227.063 lb e duração programada de 6h41min. Aplicando o índice 200 da prévia anterior aos dados do catálogo, o GP7270 prevê 233.490 lb e 7h16min21s, o Trent 970 prevê 192.790 lb e 7h38min43s e o Trent 972 prevê 227.064 lb e 6h40min59s. O Trent 972 é a única variante que reproduz ambos os valores com diferenças de 1 lb e 1 segundo. A identificação do motor é uma inferência a partir do voo, pois a ficha e o lançamento não o exibem.
- `Finance → History` e o histórico de `Banking` exibiram 30 transações recentes, com a mais antiga de cerca de uma hora e substituição de registros com entradas novas. A compra anterior já estava fora dessas listas. As sete despesas visíveis somaram exatamente os US$ 1.666.838 do resumo, sendo US$ 603.609 em CO₂ e US$ 1.063.229 na taxa de abertura, valor igual ao da prévia LAX–TUN. O resumo mostrou `A/C Orders` zerado. A segunda leitura mostrou diferença entre o total de créditos do resumo e a soma dos créditos visíveis no histórico bancário. A regra exata de retenção ou agregação do resumo rotulado como 24h segue sem confirmação. O zero observado não comprova ausência de compras nem concilia compromissos.
- Passaram **320 testes focados** de seleção de motor e hub, pré-voo, política, journal, executor simulado, finanças e worker. Os cenários incluem recusa, timeout, reinício e conciliação sem reenvio. A política de compras planejadas reportou `release_gate=G0` e `execution_available=false`. A compra legada tem controle próprio (`options.autobuy_aircraft`), cujo padrão local é ligado. O estado efetivo de um bot em execução não foi confirmado nesta sessão.
- A leitura retomou a sessão autenticada e fechou a cotação sem enviar pedido. Manter `price_verified=false` até obter vínculo nativo independente entre pedido, matrícula, valor, motor e hub. A homologação ponta a ponta da compra planejada permanece pendente. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A1/A5, conferência da compra de aeronave (G0)

- A revisão do registro autenticado das 08h11–08h16 BRT reproduziu o débito `A/C Purchased` de US$ 216.079.503 com o preço-base de US$ 215.629.503 anunciado para o A380-800 em Los Angeles e US$ 450.000 para os 42 assentos J e 24 F observados no PP-254. A diferença foi zero. O lançamento genérico não contém matrícula, motor ou hub. A coincidência de valor e janela sustenta a associação histórica, com `price_verified=false` para a configuração exata.
- O snapshot autenticado das 10h10min25s–10h12min37s BRT confirmou uma vaga PAX (224/225), uma aeronave em entrega, duas em manutenção e 30 opções habilitadas de entrega, iguais aos 30 IDs da gestão de hubs para o modelo amostrado. O campo `A/C orders` da captura financeira de 24h veio zerado e não conciliou com o lançamento individual já observado. O total agregado não serve como prova de compra, preço ou compromissos pendentes nesse caso. A correspondência individual entre a opção de entrega e o aeroporto de pesquisa continua pendente.
- Passaram 355 testes focados. Eles cobrem modo somente leitura, seleção e conferência de motor/hub, bloqueio por preço ou caixa divergente, capacidade, recusa, timeout, reinício e conciliação sem duplicidade. A política do perfil retornou `release_gate=G0` e `execution_available=false`. O controle do Chrome foi interrompido porque a ferramenta não conseguiu confirmar a URL da aba. A revisão usou as observações autenticadas anteriores e testes locais, sem envio de pedido. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A3/A9, primeiro voo LAX–TUN e auditoria dos hubs (G0)

- O `Flight history` do A380-800 PP-254 registrou uma única entrada, XP-224, de LAX para TUN. O voo decolou às 09h48min22s BRT e estava em andamento na leitura, com chegada prevista às 16h29min22s BRT. O jogo registrou 376/35/21 passageiros Y/J/F, 432 de 509 assentos (84,87%), receita de US$ 2.451.390, 227.063 lb de combustível e 814.085 quotas de CO₂. O `Today's demand` após a decolagem mostrou 965/479/91 remanescentes sobre 1.341/514/112 diários. A diferença por classe é igual ao embarque desse trecho.
- O combustível real ficou 1 lb abaixo das 227.064 lb da fórmula da prévia e 7.023 lb abaixo das 234.086 lb exibidas no campo visível (−3,00%). A duração de 6h41min é compatível com a prévia no índice 200. O histórico não mostra o índice escolhido.
- Aplicando os 0,16 kg/pax/km da prévia e uma quota por kg a 432 passageiros e 10.516 km, a estimativa fica em 726.865,92 quotas. O histórico ficou 87.219 quotas acima (+12,00%) e equivale a 0,1792 quota por passageiro por km nesse trecho. A estimativa originalmente feita para 509 passageiros foi de 856.423 quotas. A diferença observada em um único voo ainda não sustenta mudar o coeficiente do bot.
- Às cotações da prévia, vigentes na largada, o consumo real equivaleria a US$ 152.132,21 de combustível e US$ 147.349,39 de CO₂, somando US$ 299.481,60. O valor supera em US$ 15.785,98 a prévia recalculada para a mesma ocupação e os mesmos preços. Os preços de estoque efetivamente pagos seguem sem conciliação. A taxa de abertura e a provisão de manutenção ficam fora dessa comparação.
- O painel de Los Angeles passou a incluir XP-224 e mostrava 13 operações. No modal Hubs, `#hubList` já estava pronta enquanto `#hubDetail` preservava uma imagem de carregamento oculta. A espera genérica encontrava essa imagem e expirava. O coletor passou a fechar o modal anterior pelo controle nativo e a exigir uma lista recém-renderizada e visível antes de conferir os IDs. A mesma navegação atende operações e a comparação dos hubs de entrega. A sessão de jogo ficou em modo somente leitura.
- Na captura das 09h56–09h58 BRT, os 30 hubs gerenciados coincidiram com as 30 opções de entrega habilitadas para o modelo amostrado. A leitura operacional abriu 29 painéis. Após limitar a consulta ao detalhe do modal e repetir uma leitura instável antes de descartar o painel, a captura das 10h02min18s–10h04min32s enumerou os 30 painéis, com 251 vínculos hub–aeronave para 223 aeronaves distintas. A confirmação da frota ficou incompleta nessa janela porque a leitura de `Parked (0)` retornou ausência de evidência. O coletor passou a abrir `Parked` pelo controle nativo, descartar o conteúdo anterior e aguardar duas leituras iguais da lista.
- Na captura autenticada das 10h10min25s–10h12min37s BRT, o worker confirmou a cobertura da frota em duas varreduras de 12 páginas. Eram 224 aeronaves, com 221 em Routes, zero em Parked e três em Pending (duas em manutenção e uma em entrega). O snapshot passou pela validação local e conciliou `Operations to/from hub` nos 30 painéis, com 251 vínculos para 223 aeronaves distintas, duas associações de manutenção e zero divergências. Los Angeles manteve 13 vínculos. As 30 opções habilitadas também voltaram a coincidir com os IDs da gestão de hubs para o modelo amostrado. O vínculo individual dos IDs do formulário de entrega com os aeroportos segue sem prova independente.
- Passaram 47 testes focados, 2.408 testes no Windows com um pulado e os 16 testes do instalador no Ubuntu via WSL. Ruff e `git diff --check` passaram. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A3/A4, prévia LAX–TUN com o PP-254 em Parked (G0)

- Após a antecipação da entrega, o worker encontrou o A380-800 PP-254 em `Parked` às 09h41min24s BRT. A primeira prévia perdeu a confirmação e o monitor refez a leitura. Na tentativa das 09h42min09s–09h42min27s, confirmou a mesma companhia e o mesmo avião em Los Angeles, com cabine de 443/42/24 assentos Y/J/F e 14.500 km de alcance. O Chrome confirmou uma única aeronave apta, o PP-254, e zero na rota. LAX–TUN (1440–432) foi cotada como rota direta de 10.516 km, com pista de 10.499 ft em Túnis.
- O detalhe e a prévia mostraram `Daily` de 1.341/514/112 em Y/J/F. O detalhe continuou com aviso de evento e sem `Today`. `Autoprice` preencheu US$ 4.377 / US$ 8.973 / US$ 13.820 em Y/J/F. A taxa de abertura da prévia foi de US$ 1.063.229, cobrada uma vez se a rota for criada. O formulário foi fechado sem envio.
- No índice de custo 200, a prévia mostrou 06h40min59s e 0,16 kg de CO₂ por passageiro por km. O worker registrou 227.064 lb por trecho. No Chrome, a tela visível exibiu 234.086 lb. O recálculo nativo de 199 para 200 atualizou para 227.064 lb o elemento oculto com o mesmo ID, enquanto o elemento visível conservou 234.086 lb. A fórmula nativa no índice 200 arredonda 227.063,5752 para 227.064 lb. As duas referências ficam registradas até haver consumo medido em trecho operado.
- O mercado na janela da prévia cotou US$ 670 por 1.000 lb e US$ 181 por 1.000 quotas, vigentes até aproximadamente 09h57 BRT. O combustível por trecho fica em US$ 152.132,88 pelo recálculo e US$ 156.837,62 pelo valor visível. Com os 509 assentos ocupados e a hipótese de uma quota por kg, o coeficiente implica cerca de 856.423 quotas e US$ 155.012,57 por trecho. Combustível e CO₂ estimado somam US$ 307.145,45 ou US$ 311.850,19 por trecho, conforme a referência de combustível. A provisão de A-check acrescentaria US$ 96.070,93 com base nas 450 horas e nos US$ 6.468.885 do catálogo. A taxa de abertura fica fora dos custos por trecho.
- A captura privada das 09h42min28s passou pela validação de esquema, perfil e fingerprint e inclui a cotação correlacionada, com custo de reposição de combustível de 15.213.288 centavos. O ciclo dedicado à rota certificou os hubs e deixou a cobertura global parcial. A cotação tem escopo de aeronave existente, com `purchase_eligible=false`. A projeção econômica segue sem homologação por falta de demanda residual e consumo operado, além do aviso de evento.
- As capturas e simulações anteriores desta rodada registram frota, despacho observado, mercado, finanças, salários, manutenção, campanhas, checklist e prévias de aquisição. A consulta manual conciliou 30/30 painéis de hubs e 30/30 opções de entrega do A380. A cobertura de operações dos hubs no worker e o preço efetivamente cobrado na aquisição seguem pendentes. Nenhuma ação de escrita foi executada no AM4. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A3/A4, cobertura de entrega e auditoria após reinício (G0)

- O Chrome dedicado retomou o acompanhamento às 09h30 BRT. O monitor confirmou o PP-254 em entrega para Los Angeles, previsão de chegada às 13h08 BRT, zero em `Parked` e quatro registros em `Pending`. A demanda de LAX–TUN voltou a ser 1.341/514/112 em Y/J/F, sem `Today` e sem aeronave apta. A prévia depende da elegibilidade do PP-254.
- A captura das 09h30min48s–09h33min15s BRT passou pelo carregador auditado. Certificou os 30 hubs próprios e registrou cotação de combustível de US$ 670 por 1.000 lb e CO₂ de US$ 181 por 1.000 quotas, além de histórico financeiro e quadro salarial. A certificação da frota ficou indisponível nesse ciclo. A alteração de navegação não resolveu o timeout no Chrome dedicado. As operações dos hubs ficaram sem painéis validados e a conferência do formulário de entrega também expirou.
- Por volta das 09h35 BRT, a consulta nativa independente comparou os IDs gerenciados antes e depois da oferta do A380-800. As 30 opções de entrega estavam habilitadas e coincidiram com os 30 hubs próprios, incluindo Los Angeles. O resultado cobre o formulário observado desse modelo. O preço efetivamente cobrado e a cobertura dos demais modelos seguem pendentes em G0.
- Na consulta nativa das 09h32–09h33 BRT, Marketing mostrou campanhas ecológica e de reputação ativas, com reputação de 90% em passageiros e 59% em carga. O painel de manutenção confirmou um A-check já iniciado de US$ 8.823.099 e um reparo agendado de US$ 255.056. A leitura abriu os detalhes de serviços existentes. `Finances` mostrava registros recentes de decolagens da frota.
- A suíte Windows depois da alteração passou com 2.406 testes e um pulado. Os 16 testes do instalador Linux passaram separadamente em Ubuntu via WSL. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A3/A4, navegação de hubs e validação de operações (G0)

- Por volta das 09h23 BRT, a consulta nativa em `Hubs → Operations to/from hub` leu os 30 painéis gerenciados. Houve 251 vínculos entre operações de hub e 223 aeronaves distintas, com 12 vínculos em Los Angeles. A leitura é independente da captura das 09h14 BRT. A conciliação entre os painéis e a frota na mesma janela do worker segue pendente.
- O worker passou a fechar o modal anterior antes de abrir Hubs pelo botão nativo. A coleta de operações e a comparação entre hubs gerenciados e selecionáveis no formulário de aquisição usam a mesma navegação. Passaram 100 testes focados, que incluem abertura e releitura dos hubs, a janela auditada, a frota e a prévia da rota. Ruff e `git diff --check` passaram.
- Os testes locais da auditoria cobrem as proteções de decolagem, combustível e CO₂, manutenção e oficina, hangar, cabine, criação e troca de rota, encomenda, compra de hub e executor de investimentos. A simulação isolada confirmou os fluxos de cotação de campanhas ecológica e de reputação sem clicar em compra. O checklist registrou a atividade pendente em uma amostra com recompensa disponível sem disparar o resgate. As operações que alteram o jogo foram conferidas em teste local.
- Às 09h25 BRT, o PP-254 continuava em entrega para Los Angeles, com chegada prevista às 13h08 BRT e `Parked (0)`. LAX–TUN segue aguardando a aeronave para a prévia. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A3/A4, acompanhamento do PP-254 e auditoria somente leitura (G0)

- O Chrome dedicado confirmou o A380-800 PP-254 em entrega a Los Angeles às 09h14 BRT. O contador indicava chegada por volta das 13h08 BRT. LAX–TUN (1440–432) exibiu 10.515 km, pista de 10.499 ft em TUN e demanda `Daily` Y/J/F de 1.341/514/112, com aviso de evento. `Today` estava ausente e `A/C capable` era zero. O acompanhamento em modo somente leitura segue ativo para cotar a rota quando o PP-254 aparecer em `Parked`.
- O worker reconfirmou a companhia na captura das 09h14min48s–09h16min52s BRT. A auditoria conciliou 12 de 12 páginas, 221 aeronaves com rota, zero estacionadas, duas em manutenção e duas em entrega, totalizando 225 aeronaves e 30 hubs próprios. A leitura do histórico financeiro de aeronaves confirmou oito de oito amostras. O snapshot privado passou pela validação de perfil, esquema e fingerprint.
- O ciclo registrou as cotações de US$ 1.850 por 1.000 lb de combustível e US$ 105 por 1.000 quotas de CO₂, vigentes até aproximadamente 09h30 BRT. Confirmou o resumo financeiro de 24 horas, o quadro salarial nas quatro categorias nativas, os dois eventos e a partição de Aden (923) para o Iêmen, com dez destinos conciliados com o seletor. Atualizou dois pares de pistas e dois modelos no catálogo local. A lista de compra mostrou 311 modelos PAX e dez modelos tinham detalhes observados em todas as suas variantes. A certificação da captura cobre os hubs e o inventário da frota. A cobertura de rotas candidatas, modelos, motores e preços segue parcial.
- `Maintenance → Hangars → PAX` confirmou 225/225 lugares e zero vagas. A prévia de uma vaga continuava em US$ 181.294.158 e 18 minutos. O painel `Operations to/from hub` de Los Angeles exibiu 12 operações no Chrome. O ciclo do worker deixou essa auditoria em estado incompleto, com zero painéis, e a conferência dos hubs de entrega expirou. O preço anunciado da aeronave na consulta anterior continua sendo referência de configuração, com `price_verified=false`.
- A suíte Windows passou com 2.406 testes e um pulado, com exclusão de `tests/test_instalacao_linux.py`. Os cenários locais incluem decolagem, manutenção e ampliação do hangar, compra de insumos, criação e troca de rota, encomenda de aeronave, compra de hub, planejamento e executor de investimentos. A execução dessas ações no jogo fica fora da sessão somente leitura. Ruff passou. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A3/A4, paginação da frota e prévia de aquisição (G0)

- A auditoria integral descarta a varredura quando encontra a mesma aeronave em páginas diferentes e reinicia a leitura uma vez dentro do mesmo prazo. A prova exige duas enumerações completas coerentes e a restauração da página inicial. No Chrome autenticado, os ciclos das 08h56–08h58 e 09h04–09h06 BRT confirmaram 222 vínculos distintos em 12 de 12 páginas. A captura privada das 09h06min35s passou pela validação do perfil, da janela e do fingerprint. Certificou o inventário da frota e os 30 hubs próprios e registrou os dois painéis de eventos. As operações dos hubs ficaram sem painéis validados, e a conferência de cobertura dos hubs de entrega atingiu o limite de espera. Candidatos, modelos, motores e preços continuam com cobertura parcial.
- O worker passou a consultar a lista nativa `Parked` e a tentar a prévia antes da paginação e da pesquisa geral quando o cabeçalho acusa aeronaves disponíveis. A tentativa confere a identidade da aeronave e os aeroportos, coleta `Daily` e `Today` quando disponíveis e tenta ler tarifas, taxa de abertura, combustível por trecho e coeficiente de CO₂. Caso a primeira tentativa fique incompleta, o worker pode tentar novamente depois de reconciliar a lista nativa. O Chrome mostrou `Parked (0)` tanto no worker quanto na consulta direta às 09h02 BRT. A validação da cotação de ponta a ponta aguarda uma aeronave que a pesquisa confirme como apta.
- A consulta às 09h02 BRT confirmou 224 aeronaves, 222 em `Routes`, uma em entrega e uma em manutenção. A aeronave em manutenção conservava um ID de rota no mapa de status e aparecia só em `Pending` na lista da frota. A conciliação passou a preservar esse ID separadamente quando a lista de manutenção, as contagens e os vínculos das páginas conferem. A ocupação por par de aeroportos continua parcial enquanto faltarem os terminais dessa atribuição.
- `Maintenance → Hangars → PAX` mostrou 224 lugares ocupados de 225, com uma vaga disponível. `Routes → Order` mostrou 311 ofertas de passageiros. O formulário `Configuration` exibiu 30 opções de entrega e confirmou US$ 215.629.503 para o A380-800 em Chapecó com 600/0/0 assentos Y/J/F e US$ 6.770.196 para o A320-200 em Los Angeles com 164/0/0 assentos. O detalhe do A380-800 GP7270 em Chapecó mostrava alcance de 14.500 km, pista mínima de 9.680 ft, prazo de cinco horas e A-check anunciado de US$ 6.468.885. A companhia foi reconfirmada às 09h02min58s BRT.
- A etapa `Configuration` oferecia `Back` e `Order`. Os valores observados são prévias de uma unidade na cabine inicial. Preço final por motor e hub, débito e compromissos financeiros continuam sem comprovação. `price_verified=false` permanece em G0. A sessão permaneceu somente leitura.
- A suíte Windows passou com 2.406 testes e um pulado, com exclusão de `tests/test_instalacao_linux.py`. Os testes cobrem a recuperação após sobreposição entre páginas, o descarte quando a sobreposição persiste, a prioridade em `Parked` e o vínculo preservado em manutenção. Ruff e `git diff --check` passaram. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A3/A4, primeira captura autenticada do worker (G0)

- Com a sessão dedicada autenticada, o clique por ponteiro deixava o painel `Company` vazio. O verificador agora aciona o controle nativo diretamente e aguarda exatamente um campo de identificação novo e visível em `#companyAction`. Aceita maiúsculas e espaços Unicode nos rótulos em inglês e português. A confirmação final continua exigindo o mesmo ID da primeira leitura. Após falhas ao gravar as preferências do Chrome no perfil anterior, a execução usou `%LOCALAPPDATA%\AirlineManager4BOTWEB\observation` via `AM4_CHROME_PROFILE_DIR` e login manual.
- O worker confirmou a companhia às 08h44min39s e reconfirmou o mesmo ID às 08h46min41s BRT. O ciclo somente leitura gravou `data/audited_game_snapshot.json`. O carregador conferiu o fingerprint, o esquema, o perfil e a janela da captura. A lista de 30 hubs foi validada e a cobertura geral ficou parcial. A captura permanece privada no diretório de dados local.
- O jogo mostrou 223 aeronaves com rota, `Parked (0)` e `Pending (2)`, totalizando 225. A varredura descartou o lote com IDs de aeronave repetidos entre páginas e terminou com uma de 12 páginas cobertas. `observations.hub_operations` ficou incompleto, sem painéis validados, e a conferência dos hubs de entrega atingiu o limite de espera. `observations.demand_events` ficou sem painéis validados. O ciclo não gerou nova prévia de rota, e a taxa de abertura e os custos incrementais de um candidato elegível seguem pendentes.
- Na pesquisa de Kinshasa (465) para Congo (Kinshasa), o seletor mostrou 21 destinos e a lista geral retornou oito. As 13 consultas diretas registradas resolveram os IDs omitidos dentro do mesmo ciclo confirmado, com o filtro de pista mínima de 5.000 ft. O resultado cobre essa partição. Rota, frota, modelos, motores e preços seguem sem cobertura certificada.
- Passaram 50 testes focados e, na suíte Windows, 2.402 testes com um pulado. A suíte Windows excluiu `tests/test_instalacao_linux.py`, cujas verificações dependem de APIs e caminhos Linux. Ruff e `git diff --check` passaram. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A3, custos observados de dois MC-21-400 pousados (G0)

- Entre 08h30 e 08h33 BRT, o Chrome mostrou 223 rotas, 225 aeronaves, `Parked (0)` e `Pending (2)`. A lista `Landed` mostrou PP-118-3 e PP-118 prontas para decolar em suas rotas existentes. Foram conferidos o detalhe nativo de cada aeronave, a cabine, `Todays demand` e o histórico de voos. A consulta foi somente leitura.
- PP-118-3, rota XP-107 ORD–CCS, 4.040 km. A cabine tinha 46/59/22 assentos Y/J/F. A demanda disponível era 642/241/93 de 831/481/185 no dia. As tarifas Y/J/F inferidas de US$ 1.960/4.090/6.410 reproduzem exatamente a receita de sete trechos do histórico. O último CCS–ORD levou 33/43/18 passageiros, faturou US$ 355.930 e consumiu 76.691 lb de combustível e 106.356 quotas de CO₂.
- PP-118, rota XP-109 DFW–CCS, 3.946 km. A cabine tinha 118/41/10 assentos Y/J/F. A demanda disponível era 1.169/115/223 de 1.743/320/273 no dia. As tarifas Y/J/F inferidas de US$ 1.920/4.010/6.290 reproduzem exatamente a receita de cinco trechos do histórico. O último CCS–DFW levou 90/33/8 passageiros, faturou US$ 355.450 e consumiu 74.906 lb e 108.123 quotas. O cartão de voo exibia 74.907 lb para o próximo trecho.
- O mercado exibiu US$ 390 por 1.000 lb e US$ 157 por 1.000 quotas, com próxima atualização por volta das 09h BRT. Aplicadas aos consumos históricos, as cotações totalizam US$ 46.607,38 para CCS–ORD e US$ 46.188,65 para CCS–DFW. A receita menos esses dois insumos resulta em US$ 309.322,62 e US$ 309.261,35, respectivamente, antes de manutenção e demais despesas. Os valores representam reposição pela cotação da consulta. O histórico prova o consumo dos trechos já operados. Com `Parked (0)`, a taxa de abertura de uma nova rota continuou pendente e as rotas ocupadas ficam fora da elegibilidade A3/A4.
- Às 08h30 BRT, o Chrome dedicado passou pela verificação de sessão, mas o worker encerrou na confirmação da identidade da companhia antes de gerar a captura auditada. Ao reabrir o perfil às 08h34 BRT, a sessão não estava disponível. A amostra de voo veio da consulta manual autenticada. A conciliação das receitas e o cálculo de reposição foram conferidos com os valores do histórico. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A3/A4, alcance do histórico de taxas de rota (G0)

- Entre 08h18 e 08h20 BRT, `Routes` manteve 223 rotas, 225 aeronaves, `Parked (0)` e `Pending (2)`. A prévia de LAX–TUN continuou indisponível para o PP-254, com entrega prevista por volta de 13h09 BRT.
- No Chrome, `Finances → History → Summary` exibiu `Route fees` de US$ 0 para as últimas 24 horas. `Expenses` exibiu seis lançamentos de 8 a 59 minutos antes da consulta, referentes a combustível, quotas e compra de aeronave. A tela individual não mostrou taxa de abertura nem vínculo a um par de aeroportos. O total de 24 horas serve à conciliação agregada. Para LAX–TUN, a taxa segue pendente da prévia do formulário e as tarifas e os consumos da mesma aeronave também seguem pendentes.
- Consulta somente leitura e alteração documental conferida com `git diff --check`. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A1/A3/A4, entrega em Los Angeles e custo de hangar (G0)

- Entre 08h11 e 08h16 BRT, `Routes` mostrou 223 rotas, 225 aeronaves, `Parked (0)` e `Pending (2)`. `Pending` identificou o A380-800 PP-254 em entrega a Los Angeles com previsão por volta de 13h09 BRT, e outro A380-800 em manutenção em Dzaoudzi. O detalhe individual do PP-254 trazia o rótulo `Parked`. A disponibilidade vem da lista nativa e do seletor de aeronaves aptas no detalhe da rota. O cartão de entrega ainda mostrava a contagem regressiva.
- A pesquisa de Los Angeles com teto de 11.000 km e pista mínima de 9.680 ft encontrou LAX–TUN (aeroportos 1440 e 432) a 10.515 km, com pista de 10.499 ft e `Daily` Y/J/F de 1.341/514/112. O detalhe repetiu a demanda diária, exibiu o aviso de evento e mostrou zero aeronaves na rota e zero aptas, sem `Today`. O alcance de 14.500 km e o mínimo de 9.680 ft do PP-254 fazem desse par um candidato à conferência após a entrega. LAX–POM, com pista de 9.022 ft, ficou abaixo do mínimo do avião. A coleta de demanda, tarifa, taxa e custos pode continuar durante os eventos. Para LAX–TUN, tarifa, taxa de abertura e consumo ficam pendentes até uma prévia elegível. A demanda com aviso conserva o escopo da observação e o bloqueio da projeção econômica.
- `Fleet → Seat layout` exibiu 443/42/24 assentos Y/J/F no PP-254. `Finances → History → Expenses` mostrou um débito recente de US$ 216.079.503 com o rótulo `A/C Purchased`. Para Los Angeles, o catálogo exibiu a mesma base de US$ 215.629.503 no GP7270, no RR Trent 970 e no RR Trent 972. Somar os adicionais anteriormente observados de US$ 5.000 por assento J e US$ 10.000 por assento F ao preço base reproduz exatamente o débito. O lançamento financeiro é genérico e a leitura não identificou o motor instalado. A correlação por horário e valor serve para conferir a referência histórica. `price_verified` permanece falso para a combinação específica.
- `Maintenance → Hangars → PAX` confirmou 225 de 225 vagas ocupadas e zero livres. A prévia de ampliação mostrava US$ 181.294.158 e 18 minutos para uma vaga, e US$ 1.812.941.584 e 2h59 para dez vagas. A referência daquela configuração de A380 mais uma vaga soma US$ 397.373.661 antes da taxa de abertura da rota e dos custos operacionais. `Order` indicava `Max fleet size reached` e não exibia acesso a `Configuration`. A consulta no Chrome foi somente leitura. A primeira captura autenticada do worker segue pendente. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A3, identificação da companhia no Chrome (G0)

- A tentativa de captura às 07h58 BRT avançou até a leitura da identidade da companhia e encerrou sem gravar a captura. Na consulta autenticada em Chrome, o seletor nativo encontrou um único rótulo de identidade visível. O texto renderizado estava em maiúsculas (`USER ID`), enquanto a expressão do worker exigia `User ID`. A validação agora aceita as capitalizações dos rótulos em inglês e português. A leitura continua exigindo um identificador numérico nativo e interrompe o ciclo se ele divergir entre as duas verificações.
- Por volta de 08h02 BRT, `Special Events` mostrou Black Friday Cargo Rush ativo, com +50% na demanda mundial de carga e fim previsto para 29/11 às 20h BRT. `Events` manteve o bônus de +863 na classe executiva em YYZ–VAG, com fim por volta de 30/11 às 01h36 BRT. `Routes` exibiu 223 rotas, 224 aeronaves, `Parked (0)` e `Pending (1)`. A única pendência era manutenção, com cerca de 4h11 restantes. A consulta foi somente leitura e não havia aeronave estacionada para abrir uma nova prévia.
- O mercado cotou US$ 2.470 por 1.000 lb de combustível e US$ 193 por 1.000 quotas de CO₂ até 08h30 BRT. Aplicar a cotação às 212.273 lb da prévia histórica de BCN–SHA resulta em US$ 524.314,31 de combustível por trecho. O cálculo cruza observações de horários diferentes e fica como referência. Ainda faltam demanda residual, prévia elegível fora do aviso e quotas de CO₂ do mesmo candidato.
- A nova execução com a correção aguardou login manual de 08h04 a 08h09 BRT. A janela expirou sem login e a captura autenticada do worker continua pendente. A sessão do Chrome usada para a consulta manual permanece em outro perfil.
- Passaram 69 testes focados, 2.401 testes no Windows com um pulado e 16 testes do instalador no Ubuntu via WSL. A execução integral no Windows reproduziu sete falhas restritas ao instalador Linux. Ruff e `git diff --check` passaram. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A3, registro dos eventos de demanda (G0)

- Entre 03h34 e 03h36 BRT, uma consulta somente leitura no Chrome encontrou dois eventos ativos. `Special Events` mostrou Black Friday Cargo Rush com +50% na demanda mundial de carga e fim previsto para 29/11 às 20h BRT. `Events` mostrou +863 passageiros de classe executiva em YYZ–VAG, a 8.051 km, com fim previsto para 30/11 por volta de 01h36 BRT. As estimativas de fim vêm dos contadores regressivos do jogo.
- O detalhe de YYZ–VAG mostrou o aviso de demanda de evento e `Daily` Y/J/F de 558/1.222/96, sem `Today`, com zero aeronaves na rota e zero aptas. `Routes` mostrou `Parked (0)` e `Pending (1)`. A prévia de BCN–SHA continua como referência de aeronave elegível durante evento. Quotas de CO₂ do candidato e uma nova amostra elegível sem aviso continuam pendentes.
- `--observe-game` passou a guardar os dois painéis em `observations.demand_events` da captura privada, com fonte, horário, contagem nativa e tempo restante de cada cartão. O painel de rotas preserva o par de aeroportos, a classe e a variação de demanda. Contagens discordantes, dados ausentes e leituras fora do ciclo confirmado ficam sem evidência. Uma contagem nativa igual a zero é registrada. O aviso da rota continua sendo conferido em cada leitura correlacionada, com compras bloqueadas em G0. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).
- A execução às 03h39 BRT confirmou que o perfil dedicado do worker existe e está sem sessão autenticada. A coleta encerrou antes de publicar a primeira captura. A aba autenticada da consulta manual usa outro perfil do Chrome.
- Passaram 131 testes focados, 2.399 testes no Windows com um pulado e 16 testes de instalação no Ubuntu via WSL. Ruff e `git diff --check` passaram.

## 2026-11-26 — Autonomia Total A2, auditoria de destinos omitidos e comparação com rotas em serviço (G0)

- Entre 03h20 e 03h25 BRT, a auditoria somente leitura identificou os aeroportos de partida e destino das 223 rotas de `Routes`. Todos os pares foram encontrados no catálogo comunitário de coordenadas. A menor distância entre os aeroportos foi de aproximadamente 2.554 km, em DEL–DIA, pela fórmula de haversine. A comparação dos aeroportos terminais deixou em aberto a distância dos trechos com escala e a admissibilidade de rotas abaixo de 400 km. [Catálogo de aeroportos](https://github.com/eaingaran/airline-manager4/blob/master/airports.json).
- `Fleet → Research` voltou a mostrar GRU–GIG na consulta direta, a 337 km, com pista de 13.123 ft e aviso de evento. `Events` confirmou o Black Friday Cargo Rush com +50% na demanda global de carga e fim previsto para 29/11 às 20h BRT. `Routes` mostrou `Parked (0)` e `Pending (1)`. BCN–SHA segue como referência de uma prévia elegível durante o evento. Faltam uma nova prévia elegível fora do evento, as quotas exatas de CO₂ do candidato e a primeira captura autenticada do worker.
- Em `--observe-game`, a auditoria de pesquisa por país passou a consultar diretamente os destinos omitidos nos resultados de `Any airport` quando faltarem até 24 IDs. A etapa complementar tem um orçamento de 20 segundos. A captura exige filtros e seletor estáveis, uma única linha com o par solicitado e o mesmo ciclo de companhia confirmado. A seção privada `observations.route_search_partitions` registra `direct_airport_searches` e `unresolved_selector_ids`. As consultas diretas servem para diagnosticar a partição e a cobertura de rotas continua parcial. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).
- Passaram 94 testes focados, 2.394 testes no Windows com um pulado e 16 testes de instalação no Ubuntu via WSL. Ruff e `git diff --check` passaram.

## 2026-11-26 — Autonomia Total A2, conferência direta de GRU para Brasil (G0)

- Em Chrome somente leitura, entre 03h14 e 03h17 BRT, as janelas de 20.000 km e 1.261 km em `Fleet → Research`, com origem GRU (2947), `Brazil`, `Any airport` e pista mínima de 1.000 ft, devolveram 50 e 44 linhas respectivamente. O seletor conservou os mesmos 116 IDs. A união retornou 93 destinos, com um destino em comum e a própria origem fora da lista.
- Cada um dos outros 22 IDs omitidos retornou uma única linha com origem e destino correspondentes, mantendo 1.261 km e 1.000 ft nos campos da consulta direta. Todas as linhas exibiram aviso de evento. A menor distância exibida foi 29 km e a maior, 389 km. As pistas foram de 4.341 a 13.123 ft. O quadro abaixo guarda os valores nativos exibidos pela pesquisa direta.

| Destino | ID | Distância (km) | Pista (ft) |
| --- | ---: | ---: | ---: |
| AQA | 2909 | 249 | 5.907 |
| BAT | 2918 | 386 | 5.906 |
| BAU | 2919 | 291 | 4.925 |
| JTC | 3075 | 300 | 6.890 |
| VCP | 2959 | 83 | 10.630 |
| CWB | 2932 | 360 | 7.267 |
| BFH | 2916 | 355 | 4.560 |
| GUJ | 2948 | 149 | 5.089 |
| SSZ | 3001 | 58 | 4.560 |
| JOI | 2957 | 389 | 5.381 |
| JDF | 2955 | 366 | 5.036 |
| LIP | 2961 | 389 | 5.577 |
| MII | 2970 | 380 | 4.921 |
| QPS | 3019 | 184 | 6.923 |
| POO | 2980 | 178 | 4.970 |
| RAO | 2993 | 289 | 6.890 |
| GIG | 2944 | 337 | 13.123 |
| SDU | 2992 | 344 | 4.341 |
| SJK | 2995 | 67 | 8.780 |
| CGH | 2999 | 29 | 6.365 |
| QHP | 3003 | 108 | 6.170 |
| VAG | 3016 | 230 | 4.921 |

- A busca de controle voltou a `Any airport` com teto de 500 km e retornou 12 linhas. A menor foi GRU–IZA, com 400,808 km no atributo nativo. Assim, as consultas por país e individuais juntas conciliam os 115 destinos distintos da origem nesse seletor. A menor distância observada na busca por país delimita a amostra. A regra operacional para as rotas curtas e a cobertura integral do planejamento continuam sem comprovação.
- Black Friday Cargo Rush seguia ativo com fim previsto para 29/11 às 20h BRT. Às 03h14 BRT, Routes mostrou 223 rotas, `Parked (0)` e `Pending (1)`. BCN–SHA permanece como referência durante o evento. O guia da Trophy Games descreve a estimativa de CO₂ por classe e diz que o cálculo exato tem um fator aleatório. A quantidade exata por trecho exige uma observação do voo correspondente. Faltam uma prévia elegível fora do evento e a primeira captura autenticada do worker. [Guia da Trophy Games](https://trophy-games.com/guide-airline-manager-beginner). [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).
- Entrega documental conferida com os IDs e os valores exibidos pelo jogo. `git diff --check` passou.

## 2026-11-26 — Autonomia Total A2, conciliação do seletor por país (G0)

- A consulta somente leitura por volta de 03h10 BRT verificou 116 IDs únicos no seletor de GRU para Brasil antes e depois da busca de 500 km com pista mínima de 1.000 ft. A resposta de `Any airport` trouxe 12 linhas com distância mínima de 400,808 km e omitiu GIG e SDU. A seleção direta de SDU (2992) mostrou GRU–SDU a 344 km, pista de 4.341 ft, `Daily` Y/J/F de 394/507/181, sem `Today`, com aviso de evento e com zero aeronaves na rota ou aptas. A elegibilidade operacional dessas rotas curtas continua pendente.
- Em `--observe-game`, a captura privada compara as opções de `Any airport` antes da pesquisa e depois da materialização da resposta estável. No ciclo de companhia confirmado, `observations.route_search_partitions` agrupa as janelas por origem, país e pista mínima. Registra IDs nativos observados, tetos solicitado e enviado, saturação da resposta e diferenças com o seletor, excluindo a própria origem da lista de ausências. Se as opções divergirem, a comparação fica sem verificação. A ausência de um ID exige avaliação própria de distância, pista e elegibilidade. A cobertura de rotas do planejamento permanece parcial.
- Black Friday Cargo Rush seguia ativo até 29/11 às 20h BRT. Routes mostrou 223 rotas, `Parked (0)` e `Pending (1)`. Faltam uma prévia elegível fora do evento, o consumo exato de quotas para o candidato e a primeira captura autenticada no perfil dedicado do worker. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).
- Passaram 107 testes focados, 2.393 testes no Windows com um pulado e 16 testes de instalação no Ubuntu via WSL. Ruff e `git diff --check` passaram.

## 2026-11-26 — Autonomia Total A2, limites da busca por país em GRU (G0)

- Por volta de 03h BRT, `Fleet → Research`, origem GRU (2947), Brasil, `Any airport` e pista mínima de 1.000 ft mostrou 50 linhas em 20.000 km e 44 em 1.261 km. A união retornou 93 dos 116 IDs de aeroportos do seletor, com um destino em comum. Entre os 23 IDs ausentes estava o próprio GRU. A menor distância nativa da união foi 400,808 km.
- Selecionar GIG (2944) diretamente retornou GRU–GIG a 337 km, pista de 13.123 ft e `Daily` Y/J/F de 541/141/220, com aviso de evento, sem `Today` e com `A/C on route` e `A/C capable` iguais a zero. Os tetos de 400 e 401 km foram ajustados pelo formulário para 500 km. As duas consultas e a entrada de 500 km retornaram 12 rotas entre 400,808 e 497,225 km.
- A coleta de demanda por país passou a enviar ao formulário pelo menos 500 km, verificar a coerência da resposta inteira com os filtros enviados e reaplicar o limite solicitado antes de persistir. Os testes cobrem a retenção de leituras dentro do limite original com seu horário e aviso de evento, e a rejeição de uma resposta incorreta mesmo para o teto de 500 km. A cobertura permanece parcial. Ainda é necessário conciliar os IDs omitidos e comprovar a elegibilidade das rotas correspondentes.
- A consulta foi somente leitura. Black Friday Cargo Rush seguia ativo até 29/11 às 20h BRT. Routes continuava com `Parked (0)` e `Pending (2)` às 03h04 BRT. Faltam uma nova prévia elegível fora do evento e a primeira captura autenticada no perfil do worker. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).
- Passaram 61 testes focados, 2.387 testes no Windows com um pulado e 16 testes de instalação no Ubuntu via WSL. Ruff e `git diff --check` passaram.

## 2026-11-26 — Autonomia Total A2, escopo do campo Base no inventário (G0)

- Entre 02h55 e 02h57 BRT, `Company` exibiu `Base` na ficha da companhia, com São Paulo Guarulhos, e listou 30 hubs. A lista `Fleet → A380-800` tinha 70 links para detalhes individuais e nenhum atributo `data-home-hub-id`, `data-base-id` ou `data-hub-id` no painel da lista.
- O detalhe do A380-800 cuja entrega em Guarulhos havia sido observada mostrou `Delivered` com o tempo decorrido desde a entrega e GRU–FUK via HOR como rota em operação. O detalhe não exibiu aeroporto de entrega nem base permanente. O painel segue com `Base a confirmar` para aeronaves sem vínculo individual comprovado. Passaram os 44 testes existentes de `hub_registry` e `route_registry`.
- A consulta somente leitura retornou 222 rotas, 224 aeronaves, `Parked (0)` e `Pending (2)`. O evento Black Friday Cargo Rush seguia ativo, com fim previsto para 29/11 às 20h BRT. Faltam a prévia elegível fora do evento e a captura autenticada no perfil dedicado do worker. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A1, preço exibido na configuração de cabine (G0)

- Por volta de 02h53 BRT, `Fleet → Order → Configuration` mostrou US$ 215.629.503 para uma unidade do A380-800 com motor GP7270, entrega em Chapecó e layout inicial de 600/0/0 assentos Y/J/F. Ao mover os seletores da prévia, `#acCost` mostrou US$ 215.634.503 com 598/1/0 e US$ 215.639.503 com 594/0/1.
- O cálculo exibido para esse modelo soma US$ 5.000 por assento executivo e US$ 10.000 por assento de primeira classe ao valor-base e multiplica pela quantidade. As duas variações foram verificadas na interface com quantidade igual a um. O botão `Order` inicia a submissão do pedido com modelo, motor, hub, assentos e quantidade. A consulta terminou pelo botão `Back`, sem envio de pedido. O valor efetivamente cobrado por variante e hub continua sem confirmação e `price_verified=false` permanece em G0.
- A leitura anterior de Routes às 02h48 BRT seguia com `Parked (0)` e Black Friday Cargo Rush ativo até 29/11 às 20h BRT. BCN–SHA segue como referência durante o evento. Ainda faltam uma prévia elegível fora do evento, a quantidade de quotas de CO₂ do mesmo candidato e o login no perfil dedicado para homologar o worker. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A3, combustível cotado para a mesma prévia (G0)

- Em `--observe-game`, a linha privada da prévia registra o custo de reposição do combustível por trecho, em centavos de dólar, se a cotação nativa por 1.000 lb já tiver sido observada na abertura da prévia e continuar vigente até o fim da conferência. Preserva o início da prévia, o preço, sua fonte e sua vigência. A captura conserva essa referência histórica se o preço vencer depois da conferência. O consumo, o custo e o layout pertencem à aeronave existente. O coeficiente de CO₂ segue como referência e o custo de quotas do mesmo trecho exige uma quantidade verificada.
- Por volta de 02h48 BRT, a consulta somente leitura no Chrome confirmou Black Friday Cargo Rush ativo, com fim previsto para 29/11 às 20h BRT. Routes mostrou 222 rotas, 224 aeronaves, `Parked (0)` e `Pending (2)`. As duas pendências eram manutenções. BCN–SHA continua como amostra manual durante o evento, com 212.273 lb por trecho a US$ 2.450 por 1.000 lb, equivalentes a US$ 520.068,85. A primeira captura do worker depende do login em seu Chrome dedicado. Replicar a prévia fora do evento exige uma aeronave elegível. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).
- Os 100 testes focados cobriram a mesma janela de preço, o arredondamento de meio centavo, o vencimento durante a prévia, a leitura tardia do preço, a permanência da evidência após o vencimento e a preservação da coleta legada. Passaram 2.385 testes no Windows, com um pulado, e 16 testes de instalação no Ubuntu via WSL. Ruff e `git diff --check` passaram.

## 2026-11-26 — Autonomia Total A3, layout da mesma aeronave na cotação privada (G0)

- Às 02h36 BRT, Routes mostrou 221 rotas, `Parked (0)` e `Pending (3)`. O detalhe nativo do PP-125-4, MC-21-400 em operação, mostrou 92/39/20 assentos Y/J/F. Os ícones de classe e os campos correspondentes de tarifa confirmaram a ordem das contagens. O link do avião e o controle nativo de matrícula no detalhe apontavam para o mesmo ID. A consulta foi somente leitura.
- O observador consulta o detalhe associado ao ID da aeronave nas duas pontas da prévia e registra `observed_seat_layout` na linha correspondente de `observations.native_route_quotes` se as contagens coincidirem. Se o layout faltar ou divergir, guarda somente os demais dados conferidos. Descarta a prévia se o detalhe do avião deixar de confirmar a origem ou o alcance. A evidência permanece privada, no escopo da aeronave existente, com compras bloqueadas em G0.
- Às 02h41 BRT, BCN–SHA voltou a mostrar 9.831 km, `Daily` de 1.991/376/176, aviso de demanda ampliada na pesquisa, ausência de `Today`, zero aeronaves na rota e zero aptas. A prévia anterior do A380-800 segue como a melhor amostra manual de aeronave elegível durante o Black Friday Cargo Rush, com fim previsto para 29/11 às 20h BRT. A primeira captura autenticada do worker, o formato do detalhe em Parked, a demanda `Today` e os custos incrementais completos do mesmo candidato fora do evento seguem pendentes. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).
- Passaram 2.379 testes no Windows, com um pulado, e 16 testes de instalação no Ubuntu via WSL. Os 72 testes focados incluíram a persistência na captura privada, a perda da origem e o layout estável, alterado ou indisponível. Um ensaio do JavaScript com a estrutura observada rejeitou ID discordante e ícones fora da ordem. Ruff e `git diff --check` passaram.

## 2026-11-26 — Autonomia Total A3, recuperação da coleta de uma prévia em Parked (G0)

- Às 02h31 BRT, o Chrome mostrou o Black Friday Cargo Rush ativo, com +50% de demanda mundial de carga e 3 dias e 17h28 restantes. O fim continuava previsto para 29/11 às 20h BRT. Routes mostrou 221 rotas, 224 aeronaves, `Parked (0)` e `Pending (3)`. A consulta foi somente leitura. A evidência de BCN–SHA obtida durante o evento segue como referência de `Daily`, tarifa, taxa e combustível.
- Em `--observe-game`, o coletor verifica até três aeronaves pelos IDs nativos de Parked em ordem crescente e até três destinos por aeronave. Registra no máximo uma prévia, com a mesma aeronave em `#capAc` nas duas leituras do detalhe. Pode consultar a próxima aeronave após origem divergente, perda de elegibilidade ou falha de leitura. Quando faltam amostras, a consulta complementar de demanda ocorre no máximo uma vez por origem por ciclo. Após a consulta complementar, o coletor tenta reabrir Routes para a próxima leitura. O fluxo legado continua examinando uma aeronave.
- Os testes locais reproduziram a origem discordante, a perda de elegibilidade e o timeout na pesquisa. A homologação ao vivo depende do login manual no Chrome persistente do worker. A validação completa da demanda e dos custos incrementais depende de uma nova amostra com aeronave elegível fora do evento. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).
- A suíte Windows passou com 2.368 testes e um pulado. Passaram os 19 testes focados, os 16 testes de instalação no Ubuntu via WSL, Ruff e `git diff --check`.

## 2026-11-26 — Autonomia Total A2, conciliação da pesquisa de GRU para a Argentina (G0)

- No Chrome autenticado, `Fleet → Research` com GRU (ID nativo 2947), Argentina, `Any airport` e pista mínima de 1.000 ft devolveu 50 linhas com teto de 20.000 km. A menor distância nativa era 1.722,199 km (GRU–EZE) e a maior, 3.930,879 km (GRU–USH). O teto de 1.723 km devolveu 19 linhas, de GRU–IGR a GRU–EZE. GRU–EZE apareceu nas duas leituras. A união conciliou os 68 IDs de aeroporto do seletor nativo, sem IDs faltantes ou excedentes. A pista mais curta da união tinha 3.934 ft. A prova se aplica a esse recorte manual.
- A opção individual Buenos Aires Jorge (AEP, ID 2845) retornou GRU–AEP com 1.694 km e pista de 6.890 ft. O jogo devolveu os mesmos valores após reduzir a distância máxima a 1.500 km e elevar a pista mínima a 10.000 ft. Por isso, a busca delimitada conserva `Any airport` e confere os limites dos resultados retornados.
- O coletor configurado de hubs próprios abre até uma consulta adicional do mesmo país quando a lista por país atinge 50 linhas. Usa como novo teto o arredondamento para cima da menor distância nativa da lista e exige redução do teto. Concilia os destinos por ID, preserva o primeiro horário válido de cada destino e conserva avisos de evento de qualquer janela correlacionada. Se a última consulta expirar, mantém as janelas já aceitas. A cobertura do planejamento permanece parcial.
- Às 02h19 BRT, o painel Events mostrou Black Friday Cargo Rush ativo, com +50% de demanda mundial de carga e fim previsto para 29/11 às 20h BRT. Routes mostrou 221 rotas, 224 aeronaves, `Parked (0)` e `Pending (3)`. A consulta foi somente leitura. A captura autenticada no perfil do worker, a demanda residual fora do evento e os custos incrementais completos para o mesmo candidato elegível seguem pendentes. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).
- A suíte Windows passou com 2.364 testes e um pulado. Os 66 testes focados e os 16 testes de instalação no Ubuntu via WSL passaram. Os testes locais exercitaram a terceira consulta, a conciliação, a preservação dos avisos e a recuperação de timeout. Ruff e `git diff --check` passaram.

## 2026-11-26 — Autonomia Total A2–A4, login manual no worker de observação (G0)

- O Chrome autenticado mostrou Black Friday Cargo Rush ativo, com +50% de demanda mundial de carga e fim previsto para 29/11 às 20h BRT. Routes mostrou 221 rotas, 224 aeronaves, `Parked (0)` e `Pending (3)`. A melhor referência disponível continua sendo a prévia de BCN–SHA com o A380-800 então apto. Foram observadas tarifas de US$ 4.103/8.425/12.998, taxa de US$ 996.630 e 212.273 lb por trecho. `Daily` era 1.991/376/176 com aviso de evento. A mesma prévia ainda precisa de `Today` e da validação dos custos incrementais fora do evento.
- `--observe-game --wait-for-login` abre o Chrome persistente do worker em modo visível e aguarda login manual por até cinco minutos. A espera pode ser interrompida, confere a origem antes de ler a sessão e mantém as travas de dados e perfil. A observação conserva as verificações de sessão e companhia no ciclo. A flag só funciona em modo de observação.
- O processo local iniciou com o painel na interface de loopback e chegou à espera por login manual na janela dedicada às 02h09 BRT. Às 02h14, a espera expirou, o Chrome dedicado encerrou e a captura auditada ainda estava ausente. O painel local foi fechado em seguida. A sessão existente da auditoria manual está em outro perfil Chrome. A validação no Chrome foi somente leitura.
- O teste de identidade exclui `config/session/`, diretório privado ignorado no Git. A primeira execução da suíte com o worker ativo identificou a trava do perfil como arquivo local inacessível no Windows. A execução direcionada com o worker ativo passou após a correção.
- A suíte Windows passou com 2.362 testes e um pulado. Os 17 testes direcionados e os 16 testes de instalação no Ubuntu via WSL passaram. Ruff e `git diff --check` passaram.

## 2026-11-26 — Autonomia Total A2, conciliação das operações dos hubs (G0)

- Por volta de 00h25 BRT, o Chrome autenticado confirmou que o Black Friday Cargo Rush continuava ativo, com fim previsto para 29/11 às 20h BRT. Routes mostrou 221 rotas, `Parked (0)` e `Pending (3)`. Os três registros pendentes estavam em manutenção. O ID do PP-217 em Pending apareceu também em `Operations to/from hub` de STG para STG–PRY. A consulta foi somente leitura. A prévia de BCN–SHA continua como a amostra correlacionada de tarifa, taxa e consumo registrada durante o evento.
- O worker de observação lê os detalhes nativos de cada hub entre duas leituras da lista gerenciada. A captura privada registra os painéis coletados e o resultado da conciliação no campo `observations.hub_operations`, vinculado à janela da companhia confirmada. A comparação usa os IDs de aeronave e os aeroportos da operação nos dois sentidos. Quando os dois aeroportos são hubs da companhia, verifica o vínculo em ambos. Uma ocorrência adicional pode ser corroborada pelo mesmo ID classificado em Pending como manutenção. Uma entrega encontrada na lista de operações causa divergência.
- O relatório registra diferenças por aeronave e hub e sinaliza leituras incompletas, incluindo painel ausente, códigos ambíguos e pendência sem classificação entre as ocorrências adicionais. A verificação cobre associações observadas no ciclo. Base permanente, cobertura da pesquisa de candidatos, demanda residual fora do evento e custo incremental completo seguem pendentes. A primeira execução autenticada depende da sessão persistente do perfil do worker, separada do Chrome usado na consulta manual.
- A suíte Windows passou com 2.355 testes e um pulado. Os 78 testes focados e os 16 testes do instalador no Ubuntu via WSL passaram. Ruff e `git diff --check` passaram.

## 2026-11-26 — Autonomia Total A1–A3, catálogo nativo no worker de observação (G0)

- `--observe-game` passou a consultar detalhes independentes de rota, o catálogo de aeronaves e motores e a cobertura do seletor de hubs de entrega. A coleta ocorre depois da prévia de Parked e antes da confirmação final de sessão. A consulta de variantes continua limitada a dois modelos por ciclo.
- O planejamento pode usar alcance, capacidade e preço anunciado de uma lista nativa de passageiros validada em duas leituras. A evidência mantém o horário original, a fonte `game_passenger_order_list`, a validade de 15 minutos e `engine_prices_verified=false`. Uma lista nativa válida tem precedência se o cache de mercado legado estiver indisponível ou for mais antigo. O observador usa o registro do catálogo e preserva o cache legado de mercado.
- O Chrome autenticado mostrou 311 cartões no catálogo de passageiros, todos com ID nativo único e atributos de alcance, capacidade e preço válidos. O A380-800 aparecia com 14.500 km, 600 lugares e preço anunciado de US$ 215.629.503. Routes mostrou 221 rotas, 224 aeronaves, `Parked (0)` e três em manutenção. A última confirmação do painel Events em 25/11 às 23h58 BRT mostrava o Black Friday Cargo Rush ativo, com término previsto em 29/11 às 20h BRT. A consulta foi somente leitura.
- A suíte Windows passou com 2.344 testes e um pulado. Os 16 testes do instalador passaram no Ubuntu via WSL. Ruff e `git diff --check` passaram.
- A validação no Chrome confirma os campos da lista nativa. A captura autenticada no perfil do worker, o preço final por variante e hub, a base permanente, a demanda residual fora do evento e o custo incremental completo do mesmo candidato seguem pendentes. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-26 — Autonomia Total A2, pesquisa delimitada por país em Guarulhos (G0)

- Na pesquisa nativa de GRU (2.947), o filtro mundial com teto de 2.000 km e pista mínima de 1.000 ft mostrou 50 destinos. Com Argentina e `Any airport`, a consulta mostrou 31, dos quais GRU–RES, GRU–CNQ, GRU–AOL, GRU–FMA, GRU–PSS e GRU–IGR estavam ausentes da lista mundial. Com o teto de 1.500 km, apareceram 11 destinos argentinos, com máximo exibido de 1.463 km. Mantido o teto de 2.000 km e elevada a pista mínima para 10.000 ft, quatro destinos argentinos passaram, com pista mínima retornada de 10.499 ft. A leitura de GRU–RES confirmou 1.339 km e `Daily` Y/J/F de 530/344/72 com aviso de evento. É uma descoberta de cobertura, sem evidência de aeronave apta ou demanda residual para a rota.
- O coletor passou a usar, na rodada configurada de um hub próprio com lista saturada, uma segunda consulta pelo país do destino mais próximo da primeira lista. Usa o seletor nativo com `Any airport`, limpa o resultado anterior e exige origem, país, distância e pista coerentes com a consulta. Os destinos inéditos preservam o horário da respectiva leitura. As rodadas amplas e externas seguem com janela adicional por distância. Todos os resultados mantêm cobertura parcial.
- A suíte Windows executada sem o instalador Linux passou com 2.342 testes e um pulado. Após o ajuste final dos controles nativos, a suíte focada passou com 57 testes. Os 16 testes do instalador passaram no Ubuntu via WSL. Ruff e `git diff --check` passaram.
- Às 23h58 BRT de 25/11, a consulta em Chrome confirmou o Black Friday Cargo Rush ativo até 29/11 às 20h BRT. Às 00h06 de 26/11, o painel Routes mostrou `Parked (0)` e `Pending (3)`. Os três A380-800 estavam em `Pending maintenance`. A lista do mapa exibia PP-253 como `PARKED`, mas seu detalhe atualizado mostrou o voo XP-224 em GRU–FUK via HOR, com partida e chegada em andamento. O painel Routes e o detalhe atualizado prevalecem ao determinar disponibilidade. A validação foi somente leitura. O checkout não continha sessão persistente do worker para homologar a nova consulta.

## 2026-11-25 — Autonomia Total A3/A9, entrega em Guarulhos e consumo na prévia (G0)

- Às 23h43 BRT, o A380-800 PP-253 (ID 25.943.576) saiu de Pending e apareceu em Parked em Guarulhos com 409/41/36 lugares Y/J/F. O detalhe de GRU–SYD (2.947 → 3.870, 13.368 km) mostrou uma única opção em `#capAc`, vinculada ao PP-253, com zero aeronaves na rota. `Daily` era 910/942/171, com aviso de evento e sem `Today`.
- O seletor da aeronave apresentou Sydney a 13.367 km. A primeira abertura da prévia não exibiu o formulário. Na tentativa seguinte o formulário do PP-253 retornou FUK–SYD, com 7.815 km, demanda diária de 880/186/271, sugestões de US$ 3.296/6.812/10.578, taxa de US$ 806.392 e 168.743 lb por trecho. A prévia de FUK–SYD foi fechada. Seus valores de tarifa, taxa e consumo foram descartados para GRU–SYD. Às 23h49 BRT, a pesquisa de GRU–SYD ainda exibia 910/942/171, sem `Today`, e `A/C capable` havia retornado a zero.
- Às 23h48 BRT, Fleet confirmou `Routed` para o mesmo PP-253 em GRU–FUK via HOR, operação XP-224 (ID nativo 39.241.492, conferido às 23h55 BRT). O catálogo identifica GRU como 2.947, HOR como 2.021 e FUK como 2.715. `Todays demand` mostrou os pares 210/549, 353/389 e 161/191 em Y/J/F. O histórico exibiu 339/36/30 passageiros, 406.969 lb, 1.435.775 quotas e receita de US$ 3.891.234. As tarifas sugeridas de US$ 7.710/15.639/23.818 reproduzem exatamente a receita exibida. As quantidades do histórico, aplicadas às cotações vigentes até 00h00 BRT (US$ 1.950 por 1.000 lb e US$ 157 por 1.000 quotas), correspondem a US$ 793.589,55 de combustível e US$ 225.416,68 de CO₂, subtotal de US$ 1.019.006,23. São conversões ao preço de mercado consultado. Débitos e outros custos operacionais permanecem sem comprovação.
- O painel Events confirmou o Black Friday Cargo Rush ativo por mais 3 dias e 20 horas aproximadamente, com +50% de demanda mundial de carga e término previsto em 29/11/2026 às 20h BRT. A prévia confirmada de BCN–SHA segue como referência correlacionada de tarifa e taxa para o A380 entregue em Barcelona. A cotação de combustível das 23h30 BRT aplicada às 212.273 lb daquela prévia resulta em US$ 413.932,35 por trecho.
- O coletor de Parked lê `#departFuelInfo` em lb por trecho e `#departCo2Info` em kg/pax/km, com confirmação de identidade, distância, unidades e estabilidade nas duas leituras. O snapshot privado mantém os campos opcionais da mesma observação e o replay mostra as faixas no escopo da aeronave existente. Leituras legadas sem consumo continuam válidas como referências de tarifa e taxa. O coeficiente de CO₂ fica separado da quantidade de quotas de um voo e não gera custo ou lucro automaticamente.
- A suíte Windows passou com 2.340 testes e um pulado. Os 16 testes do instalador passaram no Ubuntu via WSL. Ruff e `git diff --check` passaram.
- O Chrome foi usado somente para consulta. A prévia consultada em Guarulhos mudou de origem durante a janela de disponibilidade do avião. A regressão local confirma o descarte antes do `Autoprice` no worker quando a origem do formulário diverge. Demanda residual fora de evento, custos completos do mesmo candidato, preço final, base permanente e primeira captura autenticada no worker seguem pendentes em G0. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-25 — Autonomia Total A3/A9, janela de observação e custos de referência (G0)

- Às 23h31–23h32 BRT, a pesquisa direta GRU–SYD (IDs 2.947 e 3.870) listou 13.367 km e o detalhe mostrou 13.368 km. As pistas eram de 12.139 e 12.999 pés. `Daily` mostrava 910/942/171 em Y/J/F e 683.000/1.413.000 lb de carga, com aviso de evento, sem linha `Today`, zero aeronaves na rota e zero aptas antes da entrega. A ajuda do jogo no mesmo detalhe descreve `Today` como os passageiros restantes no dia e a demanda como diária.
- As cotações verificadas às 23h30 BRT, com vigência até 00h00, eram US$ 1.950 por 1.000 lb e US$ 157 por 1.000 quotas. Em GRU–HAC via YPY, o histórico do A380-800 mostrou um trecho com 412/19/11 passageiros, 405.458 lb, 1.379.127 quotas e receita de US$ 3.722.135. As três tarifas sugeridas no controle `Auto`, de US$ 7.682/15.583/23.734, reproduzem a receita registrada dos cinco trechos exibidos nos dois sentidos. Aos valores de mercado da consulta, o primeiro trecho teria US$ 790.643,10 de combustível e US$ 216.522,94 de CO₂. O subtotal de US$ 1.007.166,04 usa os consumos históricos e preços da consulta.
- O catálogo exibiu US$ 6.468.885 de A-check a cada 450 horas para o A380-800 nas variantes GP7270, RR Trent 970 e RR Trent 972. A divisão resulta em US$ 14.375,30 por hora de voo como referência de provisionamento para a revisão. Descontos, desgaste, outros custos de operação e o débito efetivo do A-check dependem de comprovação separada.
- O worker de observação confirma a mesma companhia imediatamente antes de gravar o snapshot. A janela gravada informa início do ciclo e confirmação da companhia. Cada insumo conserva seu horário original, inclusive quando vem de uma observação anterior à janela. A janela entra no identificador verificável da captura. O ID da companhia fica em memória.
- Validação com 52 testes direcionados, suíte Windows com 2.334 aprovados e um pulado, Ruff e `git diff --check`. A exclusividade e a liberação da trava `flock` foram conferidas no Ubuntu via WSL. A consulta ao AM4 ocorreu em modo somente leitura. G0 mantido. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-25 — Autonomia Total A2–A4, worker de observação autenticada (G0)

- Às 23h22 BRT, o Chrome autenticado voltou a exibir o `Black Friday Cargo Rush` ativo, com +50% de demanda mundial de carga e fim previsto para 29/11 às 20h BRT. Parked estava vazio. Pending mostrava o A380-800 em entrega a Guarulhos para aproximadamente 23h44 BRT.
- As cotações das 23h22 BRT eram US$ 2.280 por 1.000 lb e US$ 149 por 1.000 quotas, com renovação às 23h30. A cotação atualizada aplicada às 212.273 lb da prévia anterior de BCN–SHA resulta em US$ 483.982,44 por trecho. Aplicada às 411.979 lb e 1.572.414 quotas do histórico de CCK–KIN via TGD, resulta em US$ 1.173.601,81 para os dois insumos. Essas conversões usam a cotação da consulta e os consumos registrados nas observações anteriores.
- `python src/main.py --observe-game` inicia o ciclo de observação após a abertura do painel e com uma sessão autenticada no Chrome persistente do worker. Os workers desktop e web compartilham travas por diretório de dados e de sessão. A nova opção verifica a origem AM4 e o ID nativo da companhia e encerra se perder a sessão. O ciclo consulta demanda, inventário, cotações, finanças, equipe e saldo com uma sequência explícita de leitores, e grava a captura local. Compras, alterações na frota e notificações automáticas ficam desabilitadas nesse modo.
- A prévia correlaciona o candidato às duas leituras de `#capAc`, usa o botão nativo `Autoprice` e preserva `Today` e `Daily` observados quando estáveis. Se faltarem amostras da origem verificada em Parked, a prévia pode pesquisar esse hub uma vez no mesmo ciclo. A aba de CO₂ está vinculada ao controle nativo que carrega `co2.php`. As cotações de aeronaves existentes conservam sua origem, horário e escopo. O residual econômico e os custos completos permanecem sem confirmação.
- A suíte Windows passou com 2.333 testes e um pulado. Os 16 testes do instalador passaram no Ubuntu via WSL. Ruff e `git diff --check` passaram.
- A consulta no Chrome foi somente leitura. A captura autenticada do worker, a correlação das seções em uma publicação econômica e a repetição após o evento seguem pendentes. Registros auxiliares da captura conservam os horários originais. G0 mantido. Reversão por `git revert` do commit desta entrega. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-25 — Autonomia Total A3/A9, cotação de Parked e histórico de insumos (G0)

- Às 22h58–22h59 BRT, o Chrome autenticado mostrou `Black Friday Cargo Rush` ativo, com +50% de demanda mundial de carga e fim previsto para 29/11 às 20h BRT. Parked estava vazio. Pending mostrava três manutenções e um A380-800 em entrega a Guarulhos, com previsão por volta das 23h44 BRT. BCN–SHA (1.780 → 3.950, 9.831 km) mantinha `Daily` de 1.991/376/176 em Y/J/F, o aviso de evento, `A/C on route` e `A/C capable` iguais a zero e `Today` ausente. A referência de tarifas, taxa e combustível do candidato segue sendo a prévia observada às 22h39–22h42 BRT, registrada abaixo.
- Em Fleet → Routes → Flight history, um A380-800 registrou, em CCK–KIN, 478/11/14 passageiros, 411.979 lb, 1.572.414 quotas e US$ 4.646.226 de receita. A interface identificava o voo como `12 hours ago`. Em KIN–CCK, `24 hours ago`, o mesmo avião registrou 422/10/14 passageiros, 411.979 lb, 1.404.205 quotas e US$ 4.148.716 de receita. O detalhe atual da rota mostrava escala em TGD. O histórico apresentava os aeroportos nas pontas e a idade do voo, sem identificador ou horário exato por voo.
- Às cotações consultadas antes das 23h BRT, de US$ 2.450 por 1.000 lb e US$ 115 por 1.000 quotas, o trecho CCK–KIN teria US$ 1.009.348,55 em combustível e US$ 180.827,61 em CO₂, subtotal de US$ 1.190.176,16. Para KIN–CCK, o subtotal seria US$ 1.170.832,13. O histórico forneceu as quantidades consumidas. Débitos efetivos, demais despesas e emissões do candidato BCN–SHA seguem sem confirmação.
- Às 23h09 BRT, o cartão da operação CCK–KIN via TGD mostrou `Todays demand` com os pares 1.050/1.050, 884/884 e 77/77. O cartão não exibiu tarifas vigentes.
- Com planejamento e coleta de mercado habilitados, o worker pode consultar até uma prévia direta por ciclo. A amostra verifica até três destinos pesquisados para a aeronave de menor ID da lista nativa de Parked. Confere `#capAc` e a ausência de aeronave na rota antes e depois, vincula o formulário aos aeroportos e à aeronave, ativa `Autoprice` e fecha o painel. `Daily` só é anexado quando as duas leituras coincidem. O snapshot registra as duas distâncias, sinaliza o evento e restringe a tarifa e a taxa ao escopo da aeronave existente. Um aviso correlacionado bloqueia a projeção no replay.
- Validação local com 120 testes direcionados aprovados. A suíte Windows passou com 2.320 testes e um pulado. Os 16 testes do instalador passaram em WSL. Ruff e `git diff --check` passaram.
- A conferência no Chrome foi somente leitura. A homologação do coletor no worker, a demanda sem evento, os custos completos do mesmo candidato, o preço final e a base permanente seguem pendentes. G0 mantido. Reversão por `git revert` do commit desta entrega. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-25 — Autonomia Total A2, conciliação das varreduras de Routes (G0)

- O AM4 já mostrou aeronaves em páginas diferentes e inversão de sentido de uma rota entre leituras do mesmo inventário. A auditoria integral anterior exigia igualdade das linhas em cada página. Agora, quando a apresentação varia, a cobertura exige duas varreduras completas com o mesmo total nativo, IDs de rota e aeronave únicos em cada varredura e igualdade dos vínculos, aeroportos, matrículas, modelos e sinais explícitos de base. O registro usa as páginas da última varredura e mantém a verificação da restauração da página inicial.
- Os testes locais confirmaram a conciliação com o inventário após mudança de página e inversão de sentido. Duplicidade de aeronave entre páginas, duplicidade de ID de rota e mudança de aeroporto impediram o registro do lote. A certificação em um snapshot autenticado do worker e a prova de cobertura da pesquisa de candidatos seguem pendentes.
- Validação: 2.308 testes aprovados e um pulado na suíte Windows, além de 16 testes do instalador em WSL. Ruff nos arquivos alterados e `git diff --check` aprovados.
- Na retomada, a sessão Chrome autenticada estava indisponível. A última observação do evento segue sendo a coleta de BCN–SHA, com término previsto para 29/11 às 20h BRT. Demanda fora de evento e custos completos seguem pendentes. G0 mantido. Reversão por `git revert` do commit desta entrega. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-25 — Autonomia Total A2–A4, cotação nativa BCN–SHA com A380-800 apto (G0)

- Por volta das 22h39–22h42 BRT, Parked passou de zero para dois A380-800 após as entregas. O cartão em Barcelona mostrou 465/28/26 assentos Y/J/F. A pesquisa de BCN–SHA (IDs 1.780 e 3.950, direta) mostrou `A/C on route` igual a zero e `A/C capable` igual a um. A única opção de `#capAc` correspondia ao ID do A380 de Barcelona. O detalhe manteve o aviso de evento, `Daily` de 1.991/376/176 e nenhum `Today` visível.
- Em Parked → Route → China → Shanghai Hongqiao → Next, a prévia do mesmo A380 confirmou BCN–SHA, 9.831 km, nenhuma escala, zero aeronaves na rota e o mesmo `Daily`. A ação `Autoprice` preencheu US$ 4.103/8.425/12.998 em Y/J/F. A taxa de abertura foi US$ 996.630. O formulário mostrou alcance de 14.500 km, 519 lugares, velocidade de 1.049 km/h, índice de custo 200, consumo de 212.273 lb e coeficiente de CO₂ de 0,16 kg/pax/km. A velocidade coincide com a única variante de 1.049 km/h do catálogo consultado, RR Trent 972. O detalhe da aeronave estacionada ficou sem identificação explícita do motor.
- Às 22h41 BRT, as cotações permaneciam em US$ 2.450 por 1.000 lb e US$ 115 por 1.000 quotas, com renovação prevista às 23h BRT. O consumo exibido equivale a US$ 520.068,85 de combustível por trecho. Para ilustrar a exposição a CO₂ com ocupação completa e os pesos 1/2/3 do simulador, `9.831 × (465 + 2 × 28 + 3 × 26) × 0,16` produz 942.203,04 quotas estimadas se cada kg corresponder a uma quota. Isso equivale a US$ 108.353,35 de CO₂ e a um subtotal de US$ 628.422,20 por trecho nesses dois insumos. A prévia ficou sem número nativo de quotas por voo. Ocupação, emissões efetivas e outros incrementos ficaram sem confirmação.
- Na mesma rodada, CCS–DTW (3.859 km) exibiu `Today` de 523/439/32 e `Daily` de 606/492/36 em Y/J/F, com aviso de evento, uma aeronave já na rota e zero opções em `#capAc`. Esses valores pertencem à rota em operação em Caracas. A demanda residual de BCN–SHA segue pendente.
- Evidência manual no Chrome, em somente leitura. A prévia foi fechada sem criar a rota. A tarifa e a taxa são referências do A380 já entregue. `Today` e demanda sem aviso de evento continuam pendentes para uma decisão econômica. Nenhuma amostra foi promovida a evidência de compra ou publicação do worker. G0 segue vigente. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-25 — Autonomia Total A2–A4, histórico do A380-800 e triagem em Barcelona (G0)

- Por volta das 22h27 BRT, Pending mostrou A380-800 em entrega para Barcelona e Caracas por volta das 22h39 BRT, e para Guarulhos por volta das 23h45 BRT. A pesquisa direta BCN–SHA (IDs de aeroporto 1.780 e 3.950) mostrava 9.831 km, pistas de 11.654 e 11.154 pés, `Daily` Y/J/F de 1.991/376/176 e carga de 1.494.000/564.000 lb. A rota exibia aviso de evento, sem `Today` visível, com zero aeronaves na rota e zero aptas antes da entrega. Às 22h34 BRT, o painel de eventos mostrava `Black Friday Cargo Rush` com aumento mundial de 50% na demanda de carga e 3d 21:25:47 restantes, com fim previsto em 29/11 às 20h BRT.
- No catálogo do A380-800 para Barcelona, o GP7270 mostrava 964 km/h e 22,89 lb/km, o RR Trent 970 mostrava 917 km/h e 18,90 lb/km e o RR Trent 972 mostrava 1.049 km/h e 22,26 lb/km. As três variantes exibiam alcance de 14.500 km, pista mínima de 9.680 pés, capacidade de 600 passageiros, 0,16 kg/pax/km e A-Check de US$ 6.468.885 a cada 450 horas. `#acCost` mostrou US$ 215.629.503 nas três seleções e permanece `price_verified=false`.
- A etapa `Configuration` abriu a prévia de assentos com 600/0/0 em Y/J/F e apresentou um botão separado de encomenda (`#btnPurchaseIntroA`). A prévia manteve o mesmo `#acCost` de US$ 215.629.503 para RR Trent 972 em Barcelona e GP7270 em Caracas, sem campo de preço final identificado. O preço anunciado continua sem prova de checkout.
- Na rota direta DXB–APA (2.499 e 1.128, 12.521 km), um A380-800 em operação tinha layout Y/J/F de 290/92/42. Às 22h30 BRT, o detalhe exibia `Today` de 850/163/73, `Daily` de 1.098/238/109 e aviso de evento. O histórico mostrou 270.355 lb de combustível por sentido, cerca de 21,59 lb/km. As emissões registradas foram 963.418 quotas na ida com 248/75/36 passageiros e 854.936 quotas na volta com 228/67/29 passageiros.
- Aplicando as cotações observadas às 22h30 BRT de US$ 2.450 por 1.000 lb e US$ 115 por 1.000 quotas às quantidades de DXB–APA, uma ida custaria US$ 773.162,82 e uma volta US$ 760.687,39 em combustível e CO₂. São custos históricos recalculados com as cotações da captura, cuja renovação era prevista às 23h BRT. A variante do motor do avião em operação ficou sem confirmação. A coleta no Chrome foi somente leitura. Passaram 2.304 testes na suíte Windows, com um teste pulado e o instalador Linux executado separadamente com 16 testes aprovados. G0 segue vigente. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-25 — Autonomia Total A2 e A6, alcance da pesquisa de candidatos (G0)

- No Chrome autenticado em modo somente leitura, Dhaka (DAC) foi consultada pela lista de hubs próprios. Lisboa (LIS), ausente das 30 opções próprias, funcionou por `Custom departure` → Portugal → Lisbon. Nas duas origens, pesquisas de 2.000 km e 1.900 km com pista mínima de 1.000 pés e destino em qualquer país retornaram 50 linhas cada, em ordem decrescente de distância e sem continuação visível. A janela de 1.900 km mostrou 17 destinos adicionais em DAC e 21 em LIS que também satisfaziam o limite de 2.000 km.
- Em DAC, aplicar o menor valor da lista ampla arredondado para cima (1.759,992436 km → 1.760 km) retornou 50 linhas, das quais 49 eram novas. Esse par de buscas observou 99 destinos distintos com o mesmo filtro de pista. Todas as linhas continuavam com aviso de evento. Em LIS–GRQ, o detalhe mostrou `Daily` de 724/160/214 em Y/J/F, 543.000/240.000 lb de carga e zero aeronaves na rota ou aptas. A linha listava 1.995 km, com 1.995,205689 km no atributo nativo, e o detalhe mostrava 1.996 km.
- Na coleta de planejamento, uma primeira leitura estável com pelo menos 50 linhas pode abrir uma única segunda janela com o limite arredondado, quando inferior à distância consultada e aceito pela pesquisa. As duas leituras usam a mesma origem e pista, passam pela mesma validação e mantêm o horário da leitura de cada destino. O aviso de evento de uma rota que reaparece é preservado. A pesquisa externa revalida a propriedade depois das consultas. Cobertura parcial, esgotamento interno e publicação de casos econômicos continuam sujeitos às evidências do snapshot.
- Passaram 155 testes direcionados, incluindo a janela delimitada, a deduplicação, os horários, o aviso de evento e a rejeição da segunda lista quando a origem difere. Os 16 testes do instalador Linux passaram no Ubuntu via WSL. A conferência das consultas foi manual pelo Chrome. A execução autenticada do worker segue pendente. Ruff e `git diff --check` passaram. G0 continua vigente. Reversão por `git revert` do commit desta entrega. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-25 — Autonomia Total A2, conciliação das operações nos 30 hubs (G0)

- No Chrome autenticado em modo somente leitura, os mesmos seletores da auditoria de Routes leram 218 IDs distintos de aeronave e 218 IDs distintos de rota, todos com par de aeroportos. A leitura dupla por página e o retorno de `Previous` confirmaram as 12 páginas. Nenhuma linha expôs `data-home-hub-id`.
- Em Hubs, os 30 cartões exibiram `Operations to/from hub` no detalhe, sem controle de continuação visível. As 248 linhas continham 221 aeronaves distintas. Em 27 hubs, os IDs coincidiram exatamente com as aeronaves de Routes que tinham o aeroporto do hub em uma das pontas. LAX, DZA e STG mostraram uma aeronave adicional cada. Os três IDs coincidiam com os itens marcados `Pending maintenance` em Pending. As três entregas pendentes ficaram fora das operações dos hubs. Em 27 casos, a mesma aeronave aparecia em dois hubs, um em cada ponta.
- A nova leitura de Routes após percorrer os hubs manteve os 218 vínculos por ID de aeronave e rota. A posição de 12 aeronaves mudou de página, e uma rota inverteu a ordem dos aeroportos. Ignorando o sentido da operação, os pares permaneceram iguais e os 30 hubs voltaram a conciliar com as três pendências de manutenção. A evidência cobre a associação operacional durante a coleta sequencial. Para certificar a cobertura de candidatos e vincular observações ao snapshot do worker, ainda é necessário comprovar a enumeração da pesquisa no mesmo ciclo. Base permanente e custos econômicos seguem pendentes.
- Perto das 22h12 BRT, Parked continuava com zero aeronaves e o `Black Friday Cargo Rush` ainda tinha 3d 21:48:07 restantes. As três entregas tinham previsão aproximada para 22h39, 22h39 e 23h45 BRT. A elegibilidade só pode ser confirmada no detalhe da rota após a chegada. Alteração documental conferida com `git diff --check`. G0 segue vigente. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-25 — Autonomia Total A2–A4, página terminal de Routes e vigência da amostra (G0)

- No Chrome autenticado por volta das 22h BRT, `Black Friday Cargo Rush` seguia ativo com 3d 21:57:14 restantes e aumento mundial de 50% na demanda de carga. Parked exibiu zero aeronaves. Pending mostrou seis itens, entre eles três entregas previstas em 00:36:11, 00:36:28 e 01:41:35. A aptidão para uma rota precisa ser confirmada em `#capAc` após a entrega. A consulta foi somente leitura. Demanda fora de evento, tarifa, taxa de abertura, consumo e emissões de um candidato apto seguem pendentes.
- O paginador nativo de Routes lista a página atual e os links `Previous` e `Next` quando aplicáveis. A lista de 218 rotas começou com 17 linhas e terminou na 12ª página. A divisão do total por 20 produzia uma estimativa de 11 páginas. A auditoria integral segue os links até a página terminal, repete a leitura em ordem inversa e exige contagem e IDs coerentes no mesmo ciclo. O ciclo integral é limitado a 25 páginas e 120 segundos. Leituras parciais preservam as exigências de cobertura e uma mudança na posição terminal invalida a certificação anterior.
- Os testes reproduziram o paginador observado, páginas intermediárias incompletas e alterações incompatíveis com a cobertura já certificada. A conferência no jogo foi manual pelo Chrome. A execução do worker contra a conta e a certificação de cobertura por hub ficam para nova validação. Passaram 2.302 testes na suíte Windows, com um teste ignorado e o instalador Linux excluído. Ruff e `git diff --check` passaram. G0 segue vigente. Reversão por `git revert` do commit desta entrega. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-25 — Autonomia Total A2–A4, demanda nativa e paginação de Routes (G0)

- No Chrome, em modo somente leitura, Parked voltou a exibir zero aeronaves. A pesquisa de DAC–FNJ a partir de DAC manteve o aviso de evento. Em `#rDetails`, a seção Y/J/F mostrou `Daily` de 1.081/510/272 e `Today` de 1.054/461/249. O detalhe exibiu `A/C on route` igual a um e `A/C capable` igual a zero. Layout do candidato, tarifa aplicável, taxa de abertura e custos incrementais seguem pendentes de uma prévia com aeronave apta e de observação sem aviso de evento.
- Routes exibiu 218 linhas em 12 páginas. A navegação de ida e volta reconciliou os mesmos 218 IDs de linha. Onze páginas coincidiram por ID e par de aeroportos. A outra leitura capturou um campo de distância no lugar do par em uma linha, cuja identificação TNR–TOJ foi confirmada na primeira página. Os filtros oferecidos eram de passageiros e carga. As passagens sequenciais documentam o alcance da paginação. A cobertura por hub ainda exige atribuição e reconciliação no mesmo snapshot.
- O coletor do detalhe usa o cabeçalho Y/J/F para separar passageiros da seção de carga, que repete os rótulos. `Daily`, `Today` e `A/C capable` entram no snapshot auditado como observações quando concordam nas duas leituras. `Today` ausente ou instável permanece sem valor. O aviso de qualquer uma das duas leituras correlacionadas segue até a fila e bloqueia a projeção econômica. A admissão em A3/A4 continua exigindo as evidências completas da rota e do candidato.
- Passaram 115 testes direcionados e 2.295 na suíte Windows, com um teste ignorado e o instalador Linux excluído. Ruff e `git diff --check` passaram. G0 segue vigente, com homologação econômica pendente. Reversão por `git revert` do commit desta entrega. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-25 — Autonomia Total A2–A4, vigência dos eventos e busca de aeronave apta (G0)

- No Chrome autenticado entre 21h35 e 21h39 BRT, Events → Special Events mostrava `Black Friday Cargo Rush` com aumento mundial de 50% na demanda de carga e cerca de 3 dias e 22 horas restantes. A aba Events também mostrava um bônus de classe executiva em YYZ–VAG, com cerca de 4 dias e 4 horas restantes. A busca exibiu `Demand is currently boosted due to a special event` nas 101 linhas consultadas. A descrição do evento global documenta o aumento de carga, e o aviso da pesquisa deixa a demanda de passageiros sem validação fora de evento.
- Foram consultadas DAC–FNJ diretamente, 50 rotas de Chapecó até 2.000 km e 50 de Guarulhos até 10.500 km com pista de pelo menos 10.000 pés. Os seis detalhes abertos em `#rDetails` (DAC–FNJ, XAP–SBL, XAP–LPB, XAP–IQQ, GRU–AYT e GRU–TCP) mostraram `A/C capable` igual a zero e ausência de `#capAc`. A aba Parked e o contador `#hParked` mostraram zero aeronaves durante a consulta. A busca é amostral e informa a disponibilidade no momento da coleta.
- Os atributos Y/J/F da lista coincidiram com `Daily` nos seis detalhes. DAC–FNJ voltou a mostrar `Daily` de 1.081/510/272 e `Today` de 1.054/461/249, com uma aeronave na rota. Nos cinco detalhes com `A/C on route` igual a zero, só `Daily` estava visível. O residual dessas rotas segue sem confirmação nativa. A prévia da nova rota continuou indisponível para a amostra, com tarifa, taxa de abertura e consumo do candidato pendentes.
- O painel Fuel exibiu US$ 1.950 por 1.000 lb e a aba CO2 exibiu US$ 176 por 1.000 cotas, com as unidades explícitas nos títulos dos gráficos e cerca de 21 minutos restantes para a troca da cotação. Os valores são da rodada de mercado consultada às 21h38–21h39 BRT. O custo incremental por voo ainda precisa de consumo e emissões atribuídos ao candidato e à rota, além dos demais custos aplicáveis.
- Validação na interface em modo somente leitura. Alteração documental conferida com `git diff --check`. G0 mantido e nenhum caso econômico publicado. Retomar com pesquisa sem aviso de evento e uma rota com `A/C capable` positivo. Reversão por `git revert` do commit desta entrega. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-25 — Autonomia Total A1–A4, validação autenticada somente leitura (G0)

- Chrome autenticado, em um único perfil, na noite de 25/11/2026 (BRT). Em Fleet → Research, a pesquisa da rota direta DAC–FNJ a partir do hub correspondeu aos aeroportos e à distância de 3.723 km da operação observada. O detalhe `#rDetails` rotulou Y/J/F como `Daily` (1.081/510/272) e `Today` (1.054/461/249). Em `#detailsAction #list-demand .col-4`, a primeira posição coincidiu com `Today` e a segunda com `Daily`. Entre a leitura inicial na lista de rotas e a leitura do detalhe, a redução de 27/49/23 coincidiu com um embarque que já estava em curso. Os atributos `data-yclass`, `data-jclass` e `data-fclass` da pesquisa coincidiram com `Daily` nessa rota, inclusive na consulta FNJ–DAC com origem personalizada. O aviso de evento estava visível. Os números valem para o momento da coleta e a amostra segue inelegível para projeção econômica.
- O detalhe de uma aeronave trouxe o layout Y/J/F em `#detailsAction #seat-layout .col-4`, com a ordem das classes confirmada pelos ícones e pelos campos de tarifa correspondentes. Uma única tarifa inteira por classe reproduziu a receita de cada um dos 20 voos do histórico a partir dos embarques. Essa é uma verificação indireta da tarifa efetiva da operação existente. Na pesquisa DAC–FNJ, `#rDetails` mostrou `A/C on route` igual a 1, `A/C capable` igual a 0 e ausência do seletor `#capAc`. A disponibilidade de um candidato, as tarifas aplicáveis a ele, a taxa de abertura de rota e os custos incrementais ficam pendentes para um caso econômico novo.
- Fleet totalizou 225 aeronaves. As listas por modelo em `#fleetDetailList` apresentaram 120 MC-21-400, 35 A340-200 e 64 A380-800, com 219 IDs distintos. A aba de pendências acrescentou seis A380-800 distintos, três em entrega e três em manutenção, e a aba de aeronaves estacionadas mostrou zero. A união de três listas de modelo e da aba de pendências reconciliou o total durante uma varredura sequencial. A paginação foi observada em Routes (`#routesContainer .pagination`), com 17 e 20 linhas distintas nas duas primeiras páginas e total exibido de 219 rotas. As três listas da frota por modelo apareceram sem controle de paginação. A varredura ainda requer prova de cobertura de rotas por hub no mesmo snapshot e conciliação financeira das pendências.
- Em Hubs, `Operations to/from hub` mostrou operações de ida e volta no detalhe do hub. O vínculo permanente por aeronave segue como `Base a confirmar`.
- Em Fleet → Buy, `#acCost` exibiu US$ 215.629.503 nas seis combinações de GP7270, RR Trent 970 e RR Trent 972 com dois hubs de entrega para o A380-800. O A340-200 exibiu US$ 15.688.189 no catálogo e apresentou CFM56-5C2, CFM56-5C3 e CFM56-5C4. A consulta documenta preço exibido, com checkout e preço final por configuração ainda pendentes. `price_verified=false` permanece aplicável.
- Verificação somente leitura na interface do AM4 e alteração documental conferida com `git diff --check`. G0 mantido. A integração com o worker, o caso econômico completo e a homologação integral seguem pendentes. Reversão por `git revert` do commit desta entrega. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-25 — Autonomia Total A1–A4, diagnóstico das fontes de demanda e tarifas (G0)

- A sonda de leitura de `src/game_source_probe.py` e a área administrativa de `assets/web/index.html` passaram a indicar a presença dos campos nativos de layout e demanda da aeronave, da lista de aeronaves para a rota e dos campos candidatos de demanda, tarifa e taxa no formulário. Quando existe um único painel de detalhes com uma única lista de demanda e três colunas visíveis, a sonda compara os dois números de cada coluna por posição. Ela emite relações fixas, sem devolver montantes, textos ou HTML. O formato aceito nesta etapa é um par de inteiros separado por barra ou quebra de linha. O painel resume as fontes reportadas pela versão do worker, com contagens de elementos detectados no DOM.
- Dois agentes fizeram revisões independentes da sonda e do painel. Os 101 testes direcionados passaram e cobrem extração com DOM simulado em Node, entrada inválida, painel oculto, resposta de worker anterior e integração administrativa. A suíte Windows passou com 2.288 testes e 1 ignorado. Também passaram Ruff, compileall, `git diff --check` e 16 testes simulados do instalador no Ubuntu via WSL.
- A tentativa no Chrome chegou ao login. A coleta real precisa de uma sessão autenticada fornecida pelo titular. Em uma rota operada fora de evento, a próxima observação deve vincular pesquisa, formulário e detalhes pelos mesmos IDs nativos, incluindo a escala quando houver. Registrar horário e cobertura da observação e confirmar qual posição representa demanda diária e qual representa saldo residual. Uma contagem de elementos ou comparação de números é diagnóstico estrutural. O preço final, a disponibilidade, os custos incrementais e a semântica de demanda continuam pendentes de homologação em G0. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46).

## 2026-11-25 — Autonomia Total A3/A4, publicação atômica da pesquisa (G0)

- `src/audited_economics_registry.py` valida independentemente todo o lote e grava os casos e controles A4 em uma única substituição atômica. A marca `sweep_published` distingue a captura inicial da publicação vazia. Repetições idênticas preservam o arquivo e evidências de portfólio posteriormente complementadas; casos adicionais ou lotes divergentes da mesma captura são rejeitados. A escrita individual anterior permanece disponível para registros legados.
- `src/planning_cycle.py` exige a marca de publicação e correspondência exata dos IDs avaliados da auditoria, inclusive quando não há avaliações. Falha na segunda página, duplicidade ou divergência de identidade impede publicação parcial. A marca registra apenas a publicação da amostra, sem certificação de cobertura global ou compromissos. O resumo de planejamento anterior sem essa marca exige nova coleta.
- `tests/test_audited_economics_registry.py` e `tests/test_planning_cycle.py` verificam lotes vazios e não vazios, falha simulada de gravação, repetição, tentativa de alteração posterior, preservação do portfólio e rejeição de resumo sem publicação. Os 59 testes direcionados passaram, além de Ruff, compileall e `git diff --check`. A suíte anterior à marca apresentou 7 falhas exclusivas do instalador Linux no Windows (`os.fchmod`, arquivo temporário em uso e `bash` com código 127). Na validação final, a suíte Windows sem o instalador Linux passou em 2.287 testes com 1 ignorado (136,93 s). Os 16 testes do instalador passaram no Ubuntu via WSL com o pytest do diretório de pacotes existente.
- G0 mantido. A coleta autenticada de demanda residual, layout, disponibilidade, tarifas, preço final e custos segue pendente. Não houve compra ou implantação. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46); rollback por reversão do commit da entrega.

## 2026-11-25 — Autonomia Total A3/A4, publicação de casos econômicos pelo worker (G0)

- O accounting gate de `src/research_accounting_gate.py` encaminha os casos avaliados por um callback interno opcional. `src/audited_game_snapshot.py` preserva a resposta pública do replay e não grava o registro. `src/planning_cycle.py` confere a correspondência entre os casos completos e os IDs da auditoria das páginas, admite resultados avaliados e bloqueados e publica os casos antes da comparação A4. O registro `src/audited_economics_registry.py` recalcula a economia no relógio atual e rejeita a identidade divergente antes da gravação. O resumo do worker revalida a existência e vigência dos casos avaliados, sem expor os insumos privados.
- O worker grava os controles da captura ao publicar casos completos, mas mantém cobertura da pesquisa e compromissos sem certificação. Casos incompletos continuam no diagnóstico amostral. O fim da amostra não prova cobertura global. A reavaliação independente, o limite de armazenamento, a idempotência e G0 são preservados.
- Validação em `tests/test_planning_cycle.py` com A3 e registro reais, A4 real e replay sintético de caso completo; inclui evidência ausente, identidade divergente, repetição e expiração. A pesquisa real em fixtures incompletas continua bloqueada. Passaram 393 testes direcionados, Ruff, compileall e `git diff --check`. A coleta autenticada não foi executada nesta entrega. O produtor de demanda residual, preço final, disponibilidade, layout, tarifas e custos completos segue pendente, assim como a conciliação A4 e expansão externa A6. A evidência histórica de `src/seats.py` distingue demanda total e residual, porém a ordem dos valores no DOM e a semântica de Y/J/F na pesquisa direta ainda precisam de correlação autenticada. Nenhuma compra ou implantação realizada. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46); rollback por reversão do commit da entrega.

## 2026-11-25 — Contexto padrão no launcher Codex Web GPT (G0)

- O Codex Web GPT 6.2.0 gerava `<codex_multipart_commit>` com **Bigger Context (experimental)**. A rejeição por tamanho foi observada no navegador do launcher. A opção foi desativada pela interface e confirmada nos arquivos de configuração do launcher e do serviço local. O contexto e o índice passaram a explicar a retomada pelo arquivo versionado em uma conversa nova.
- A alteração no repositório é documental. Uma nova execução completa pelo launcher ainda está pendente. A retomada do roadmap e a homologação permanecem no G0.

## 2026-11-25 — Recuperação do checkpoint de compactação (G0)

- O checkpoint foi reconstruído a partir do trecho disponível e do estado versionado. A retomada segue pela integração dos registros A3/A4 e A6/A7 no worker, com coleta autenticada e cobertura integral ainda pendentes. Em caso de rejeição por tamanho da compactação automática, a instrução de retomada indica somente `docs/contexto.md` em uma nova tarefa Cloud.
- Passaram 228 testes de registro econômico, ciclo de planejamento, ingestão de pesquisa própria, expansão e avaliação econômica. A atualização foi documental. G0 continua vigente.

## 2026-11-25 — Retomada do roadmap no Codex Cloud (G0)

- `AGENTS.md` orienta retomar por `docs/contexto.md` e ler o roadmap e este histórico por trechos. O índice multiparte é versionado. O arquivo bruto local é opcional e fica fora do Git e das mensagens. Uma tarefa no Codex Cloud pode seguir quando esse bruto estiver ausente.
- A verificação documental abrangeu os arquivos versionados, a regra que ignora o bruto e `git diff --check`. A execução no Codex Cloud depende do acesso ao repositório e à branch de desenvolvimento. Gate G0 vigente, com coleta autenticada e homologação ainda pendentes.

## 2026-11-25 — Consolidação das branches e auditorias A3–A5 (G0)

- As branches permanentes são `main` e `codex/autonomia-a0-a1-20261122`. A [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46) acompanha o desenvolvimento. A [PR #44](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/44) documenta a implementação inicial de hubs em `33d081b`. A branch de desenvolvimento já usa o inventário auditado do `HubRegistry` no painel e na API. O histórico da PR #44 segue como referência para a revisão de uma promoção.
- A [PR #47](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/47) passou a exigir evidência dentro do prazo, checkout do preço final vinculado à variante e cobertura comprovada pelo snapshot original. A integração preservou a vinculação da cobertura ao conjunto de casos, os controles de truncamento e a resposta vazia de uma captura ainda sem avaliações. A5 incorporou a validação da titularidade do executor na recuperação simulada e o tratamento de falhas na leitura do checkout e da confirmação.
- O bundle local `.git/branch-cleanup-20261125-113314.bundle` registra as 59 pontas remotas e 12 locais anteriores à limpeza. `git bundle verify` conferiu o arquivo e a ponta da PR #44 foi restaurada e verificada em um repositório separado. Para restaurar uma branch remota arquivada, use `git fetch <bundle> refs/remotes/origin/<branch>:refs/heads/<branch>`. As cópias de trabalho antigas permaneceram no disco. O diff não commitado de `AirlineManager4BOTWEB-a3-route` foi conferido após a transição e recebeu uma cópia adicional em `.git/branch-cleanup-20261125-unstaged-a3-route.patch`.
- A suíte Windows passou com 2.276 testes e 1 ignorado. O módulo de oportunidades passou novamente com 113 testes, incluindo dois casos adicionais de expiração fora do intervalo numérico. No Ubuntu via WSL passaram os 16 testes simulados do instalador. Ruff, compileall e `git diff --check` passaram. G0 continua vigente. Homologação autenticada e instalação real no servidor seguem pendentes.

## 2026-11-25 — Autonomia Total A1–A3, demanda de evento na pesquisa auditada (G0)

- Na consulta autenticada e somente leitura em Fleet → Research, as 50 linhas em `#resResult #list .sorter` exibiram o aviso `Demand is currently boosted due to a special event`. As linhas traziam atributos de distância e demanda Y/J/F. Nenhum controle de continuação foi identificado na amostra. Em Fleet, a vista consultada exibiu contagens agregadas por categoria. A evidência não confirma paginação, vínculo permanente aeronave–hub, demanda residual ou cobertura integral por hub.
- No A380-800, o catálogo apresentou GP7270, RR Trent 970 e RR Trent 972. O valor exibido em `#acCost` permaneceu em US$ 215.629.503 ao alternar GP7270 e RR Trent 972 e consultar duas bases de entrega. O elemento não apresentou `data-final-price`. O preço final por configuração segue pendente, com `price_verified=false`.
- O coletor preserva o aviso explícito da pesquisa inicial ou da leitura estável posterior quando origem, destino, distância e demanda concordam. Os resultados com aviso continuam disponíveis como observações parciais e bloqueiam a projeção econômica auditada. Uma revisão independente confirmou que o fim da fila amostrada não promove a cobertura de A4 ou A6. O texto observado e coberto pelos testes está em inglês.
- Os 335 testes direcionados passaram, incluindo o desaparecimento do aviso entre as leituras. A suíte Windows terminou com 2.205 aprovados e 1 ignorado, excluindo os testes do instalador Linux. Ruff, compileall e `git diff --check` passaram. A coleta autenticada sondou o catálogo e os resultados visíveis. G0 vigente, sem compra, criação de rota ou implantação. Casos econômicos completos, cobertura por hub e homologação integral seguem pendentes. Rollback por reversão do commit da entrega. [PR #46](https://github.com/andreypiekas/AirlineManager4BOTWEB/pull/46)

## 2026-11-25 — Autonomia Total, compactação dos arquivos de retomada (G0)

- O [contexto permanente](contexto.md) guarda o checkpoint ativo e remete à revisão `8fdab91` no Git para os detalhes anteriores. O [índice multiparte](codex_multipart_commit.md) substitui o texto longo na leitura de retomada. O histórico bruto foi compactado em GZip local, ignorado pelo Git.
- Validação documental por `git diff --check`, verificação dos links, conferência das regras de exclusão e comparação integral dos bytes descompactados com o original. A entrega alterou documentação e armazenamento local do histórico. G0 permanece vigente.

## 2026-11-25 — Autonomia Total, revisão documental do estado e da retomada (G0)

- A revisão consolida o estado de A0–A9 e ordena a coleta nativa de A1/A2, a publicação das evidências A3/A4 pelo worker e a recomendação A6/A7 com cobertura e prova de esgotamento interno. A base de código é `b9af7d2` na branch `codex/autonomia-a0-a1-20261122`. A PR #44 aponta para `33d081b`.
- O [contexto permanente](contexto.md) registra a sequência de retomada. O histórico multiparte local recebeu um checkpoint e preserva o arquivo bruto separado.
- Validação documental com `git diff --check`, verificação das referências locais e verificação de preservação do conteúdo original do multipart. A suíte e os testes simulados do instalador da base estão descritos na entrega seguinte. Homologação autenticada e validação em servidor seguem pendentes. Nenhuma compra ou implantação realizada. Rollback dos documentos rastreados por reversão do commit.

## 2026-11-25 — Autonomia Total A1/A6, revalidação do checkout e propriedade auditada (G0)

- A1: o pré-voo planejado consulta o painel atual após verificar modelo, variante, base e estabilidade do preço final. Um aviso `#accountLow` visível nessa etapa interrompe a validação. A regressão foi reproduzida em simulação e bloqueada antes do envio do pedido. Na evidência registrada, as variantes do A320-200 mudaram velocidade e consumo sem alterar `#acCost`; a amostra do A380-800 não apresentou fonte explícita de preço final. A validação por modelo, variante e hub segue pendente.
- A6: o snapshot valida perfil, origem, identidade, vigência e IDs dos hubs próprios. Replay, painel e Telegram reutilizam essa prova. Em caso de divergência com inventário vivo vigente, o ranking diagnóstico exclui os hubs indicados pelas duas fontes e a decisão perde a prova de propriedade. O vínculo permanente aeronave–hub, a varredura completa e os cenários econômicos conclusivos continuam pendentes.
- `AGENTS.md` e `docs/contexto.md` determinam que os checkpoints sejam gravados no arquivo canônico e relidos após compactação. O histórico multiparte original fica no arquivo local `docs/codex_multipart_commit.md`.
- Validação direcionada: 433 testes aprovados. Suíte Windows consolidada: 2.204 aprovados e 1 ignorado (134,79 s, instalação Linux excluída). Ruff, compileall e `git diff --check` aprovados. Os 16 testes simulados do instalador passaram no Ubuntu via WSL. Instalação real em servidor e homologação autenticada permanecem pendentes. G0 vigente. Nenhuma compra real ou implantação realizada. Rollback por reversão do commit desta entrega.

## 2026-11-25 — Autonomia Total A6, replay auditado da pesquisa externa (G0)

- `src/audited_game_snapshot.py` passa a capturar a reserva operacional e disponibiliza `replay_external_research_page()`. O replay utiliza exclusivamente as evidências do perfil capturado, verifica identidade, integridade e vigência, revalida propriedade, preço, pontos e demanda com o relógio atual e vincula a paginação à captura e às evidências vigentes. Reserva auditada anterior pode ser usada quando a nova observação está ausente. Valores inválidos permanecem desconhecidos. O orçamento apresentado é anterior aos compromissos.
- `src/web.py` substitui as leituras independentes no endpoint de pesquisa externa pelo replay. `assets/web/index.html` limpa resultados e desabilita paginação diante de captura ausente, vencida ou inválida. Compatibilidade com captura anterior preservada mediante nova coleta. Resultado somente leitura, parcial e inelegível para compra. Não certifica lucro, custo total ou esgotamento de hubs próprios.
- Testes direcionados (222 aprovados), incluindo UI/JavaScript, API, paginação, alteração da captura, expiração independente de preço/pontos, propriedade, adulteração e isolamento por perfil. Suíte Windows consolidada: 2.200 aprovados e 1 ignorado (138,41 s; instalação Linux excluída). Ruff, compileall e git diff --check aprovados. Homologação autenticada e instalação Linux pendentes. G0 preservado; nenhuma transação real ou implantação. Rollback por reversão do commit desta entrega.

## 2026-11-25 — Autonomia Total A6, captura auditada da pesquisa externa (G0)

- O snapshot produtivo passa a incluir observações do catálogo de aquisição e da pesquisa externa de rotas, separadas da pesquisa dos hubs próprios e vinculadas ao fingerprint da captura. A inclusão depende de inventário próprio vigente, procedência correta e identidades de candidatos e rotas não ambíguas. Preço e pontos expiram independentemente; amostras inválidas, vencidas, conflitantes ou pertencentes a hubs próprios são excluídas. O resumo disponibiliza contagens vigentes de candidatos, preços, pontos e amostras, sem identidades privadas.
- Compatibilidade com capturas anteriores preservada. Cobertura de rotas e preços continua parcial e o resumo é somente leitura, inelegível para compra. A captura é uma fonte de entrada para a futura avaliação A6; o produtor de cenários econômicos conclusivos e sua integração ao planejador ainda estão pendentes. G0 mantido.
- Validação Windows: 2.199 testes coletados, 2.198 aprovados e 1 ignorado por permissões POSIX (instalação Linux excluída). Após a proteção adicional contra overflow de timestamp, 118 testes direcionados, Ruff, compilação Python e verificação de diff aprovados. Homologação autenticada e instalação Linux permanecem pendentes. Rollback por reversão do commit desta entrega.

## 2026-11-25 — Autonomia Total A3/A4/A7, conciliação de caixa antes do ranking (G0)

- O planejamento produtivo exige saldo auditado A3, saldo autenticado da captura e leitura viva verificada. O menor saldo bruto limita as alternativas antes da classificação; compromissos, pedidos incrementais e a maior reserva aplicável são deduzidos uma única vez. Saldo maior não amplia orçamento; divergência bloqueia recomendação e ausência de prova deixa orçamento desconhecido. A revalidação posterior rejeita alteração de saldo, tipo inválido ou regressão temporal antes da criação da prévia de compra.
- O painel PT/EN explica separadamente os três saldos, teto bruto e orçamento após compromissos, mesmo quando não há alternativas. Preserva zero como valor observado e identifica alternativas de diagnóstico quando a comparação permanece inconclusiva.
- Validação: 159 testes direcionados aprovados, Ruff, compileall e git diff --check aprovados. Suíte Windows consolidada: 2.194 aprovados e 1 ignorado (131,99 s; instalação Linux excluída). Rollback por reversão deste commit. Produção das provas econômicas completas, cobertura real e homologação no jogo e Linux permanecem pendentes. G0 vigente; nenhuma compra ou implantação.

## 2026-11-25 — Autonomia Total A6/A7/A8, integridade financeira e projeções condicionais (G0)

- O ranking externo rejeita hubs próprios, IDs duplicados (inclusive colisões de tipos legados), preços/pontos conflitantes, observações vencidas ou futuras e valores financeiros inválidos. A revalidação confere investimento, composição, lucro, payback e caixa líquido da reserva com arredondamento monetário consistente. O limite técnico para valores financeiros é 10^15 em moeda do jogo.
- Custos recorrentes excluídos são preservados no cenário e nas provas de custo e lucro. Exclusões inválidas impedem conclusão; despesas não quantificadas produzem projeções condicionais, abaixo das alternativas conclusivas e inelegíveis para A8. O gate produtivo exige declaração explícita de exclusões no cenário ou na prova financeira. O Telegram e o painel mostram as ressalvas, e mudanças de exclusões participam da deduplicação.
- O registro rejeita novas observações futuras e permite recuperar registros temporais inválidos da mesma identidade econômica, preservando alternativas independentes, conflitos legítimos e observações mais recentes.
- Validação: 375 testes direcionados aprovados; suíte Windows consolidada com 2.192 aprovados e 1 ignorado (134,67 s; instalação Linux excluída). Ruff, compileall e git diff --check aprovados. Rollback por reversão deste commit. Coleta autenticada, produtores de evidência completa, homologação POSIX e executor real seguem pendentes. G0 vigente; nenhuma compra ou implantação.

## 2026-11-25 — Autonomia Total A6/A7, escopo obrigatório da captura produtiva (G0)

- `src/expansion_feasibility.py` permite consultar a análise histórica, mas o gate produtivo exige a identidade explícita de perfil e snapshot no inventário, pesquisa, portfólio, cobertura geral e por hub, catálogo externo e provas econômicas do cenário. Metadados ausentes ou divergentes impedem a recomendação; a mera presença de uma captura não certifica outras observações.
- `src/web.py` utiliza o snapshot produtivo vigente e validado, expõe `planning_snapshot_id` e aplica o gate estrito. `src/expansion_alerts.py` reutiliza essa identidade, sem fabricar um snapshot a partir do hash de relatórios independentes. O Telegram preserva a deduplicação por mudança material e suprime alertas sem captura válida. `src/expansion_reporting.py` preserva timestamps fracionários na comparação de evidências.
- 333 testes direcionados aprovados; suíte Windows com 2.161 testes coletados e código de saída 0 (instalação Linux excluída); Ruff, compileall e git diff --check aprovados. Auditorias independentes A3/A4 (188 testes) e A6 (333 testes) identificaram lacunas de saldo independente, integridade de candidatos, persistência temporal e custos excluídos; detalhes e sequência no checkpoint 12 de contexto.md. Rollback por reversão do commit desta entrega. G0 permanece vigente. A associação efetiva das fontes produtivas A3/A4/A6 ao snapshot, inclusive a cobertura integral de oportunidades, depende dos produtores e da homologação. Nenhuma transação real ou implantação executada.

## 2026-11-25 — Autonomia Total A6, identidade nativa e integridade de investimento (G0)

- Cenários externos e suas provas de custos/lucro passam a distinguir modelo, motor, origem, destino e escala por IDs nativos. Observações históricas incompletas continuam acessíveis, porém inconclusivas. Contradições no mesmo horário, inclusive entre o campo legado e a lista moderna, bloqueiam a conclusão até evidência posterior. Mudanças de rótulos não criam novas identidades.
- O gate de expansão valida a consistência do perfil e snapshot quando presentes, os tipos e composição do preço final do motor e os valores financeiros finitos. O painel informa o perfil atual. O vínculo obrigatório ao snapshot produtivo e a comprovação de regras de escala permanecem pendentes.
- O cálculo de caixa e os relatórios deixam de descontar a reserva duas vezes: investimento é comparado ao caixa disponível líquido da reserva; caixa bruto exigido continua investimento mais reserva. O Telegram considera IDs nativos na deduplicação das recomendações.
- Validação: 308 testes direcionados aprovados, Ruff e compileall aprovados, suíte Windows com 2.158 testes coletados e execução concluída com código 0 (instalação Linux excluída), git diff --check aprovado. Rollback por reversão do commit da entrega. Permanecem pendentes produtores produtivos de cenários completos, escopo obrigatório, evidências autenticadas e homologação A0–A9. Nenhuma transação real ou implantação executada.

## 2026-11-25 — Autonomia Total A3/A4/A9, vinculação da captura produtiva ao registro econômico (G0)

- O worker inicializa o registro A3 após cada captura produtiva, antes da pesquisa contábil e da decisão A4. A captura parcial recebe identidade própria e substitui avaliações e controles de snapshots anteriores. A repetição idempotente da mesma captura preserva os casos; uma captura mais antiga ou de identidade distinta no mesmo horário é rejeitada. O modo de simulação continua fora da publicação do registro.
- O registro valida fingerprint, perfil, origem, versão e metadados temporais de captura e observação. Casos persistidos exigem correspondência de horários com o cabeçalho; registros antigos sem horário de captura continuam compatíveis. Cobertura integral não é certificada com zero casos, inclusive após releitura de um registro adulterado. As gravações são atômicas e privadas. O arquivo representa a captura ativa; a preservação de um histórico completo de casos econômicos continua pendente.
- As métricas A9 reconhecem o registro vazio vinculado à coleta atual, com zero avaliações, zero elegíveis e decisão de não comprar. A fila de pesquisa permanece parcial e a conclusão de uma amostra não certifica cobertura.
- Validação: 56 testes direcionados aprovados (19,55 s); suíte Windows com 2.130 testes coletados, 2.129 aprovados e 1 ignorado, sem falhas (instalação Linux excluída); Ruff e `git diff --check` aprovados. Rollback por reversão deste commit. Permanecem pendentes os produtores de casos econômicos completos e da certificação de cobertura/compromissos, as evidências autenticadas faltantes e a homologação A0–A9. Nenhuma transação ou implantação executada.

## 2026-11-25 — Autonomia Total A0/A2/A3/A4, integridade da identidade e cobertura (G0)

- A0/A3: a taxa da rota, a projeção financeira e os insumos contábeis dependentes da rota exigem correspondência com a escala proposta. Evidências de escala divergente ou ausente são rejeitadas. Rotas diretas continuam compatíveis com registros antigos; itinerários com escalas diferentes são alternativas econômicas distintas. A conversão A5 para intenção de compra com escala permanece bloqueada até implementação e homologação do executor.
- A2: a pesquisa incremental, o registro de cenários, as recomendações e o planejador preservam IDs nativos de modelos homônimos e distinguem registros antigos sem ID. A identificação apenas pelo nome não elimina alternativas nativas distintas. A situação foi reproduzida com dados simulados; homônimos no catálogo real ainda não foram confirmados.
- A3/A4: a cobertura de pesquisa é vinculada ao conjunto exato de IDs econômicas revisadas. Inclusões, remoções e truncamento invalidam a certificação. O limite de armazenamento marca o snapshot persistentemente como truncado, impedindo recertificação até uma coleta nova. Repetições idempotentes não invalidam cobertura. Compromissos financeiros independentes são preservados.
- Validação: 340 testes direcionados aprovados; 186 aprovados após a extensão A2 ao registro de cenários; suíte Windows consolidada 2.121 aprovados e 1 ignorado (131,60 s; testes de instalação Linux excluídos; últimas alterações A2 validadas também em testes direcionados); Ruff e `git diff --check` aprovados. Os testes POSIX de instalação e a homologação autenticada continuam pendentes. A busca de produção confirmou que o registro auditado A3 ainda não possui um consumidor que grave casos completos e certifique cobertura. A integração desse registro com o worker e a obtenção de evidências reais são os próximos passos. Nenhuma transação real ou implantação executada.

## 2026-11-25 — Autonomia Total A3, validação da rentabilidade com tarifas do jogo (G0)

- A criação de rotas diretas agora recebe o modelo e os custos operacionais usados na pesquisa e recalcula o lucro depois que o jogo preenche as tarifas automáticas. O cálculo usa a distância nativa confirmada no formulário e as tarifas Y/J/F efetivamente lidas antes da submissão. A estimativa de mercado permanece como critério de ordenação, sem ser reutilizada como lucro final da rota.
- Em execução real, a taxa da rota não é paga quando faltam dados do modelo ou dos custos, quando o lucro é desconhecido, não finito ou não positivo. A simulação continua permitindo registrar a cotação observada sem enviar a mutação. Chamadas antigas de `create_route()` sem os novos parâmetros mantêm compatibilidade.
- O gate G0 da nova política de investimento continua restrito às encomendas planejadas. O fluxo legado permanece independente da política nova até uma migração explícita, conforme a regra de compatibilidade do roadmap. Nenhuma compra real ou implantação foi executada.
- Validação: 2.114 testes aprovados e 1 ignorado na suíte Windows, excluindo `tests/test_instalacao_linux.py`; 154 testes direcionados de rota, seleção de motor e hub passaram; `ruff check src tests` e `git diff --check` aprovados. A homologação autenticada das tarifas e da rentabilidade no jogo permanece pendente.

## 2026-11-24 — Autonomia Total A1, preço final vinculado à variante de motor (G0)

- Cada variante do catálogo passa a carregar um contrato tipado `FinalCheckoutPrice`, com identidade do motor, valor, fonte e estado de verificação. As leituras atuais permanecem como `unknown`, pois a observação autenticada de 23/11 identificou `#engSelection` e `#acCost`, mas não comprovou um preço final associado a cada variante.
- O pré-voo planejado associa o preço à variante selecionada somente após duas leituras idênticas do checkout, confirmação de que o valor inclui o motor, correlação entre modelo e base e revalidação da seleção. A validação exige ID do motor, valor positivo, estado verificado e fonte final autorizada. A verificação de seleção permanece independente da verificação de preço.
- Validação: 2.187 testes aprovados e 1 ignorado na suíte Windows, excluindo `tests/test_instalacao_linux.py`. Ruff e `git diff --check` aprovados. A execução integral no Windows confirmou três falhas restritas aos testes Linux de permissões POSIX e sintaxe Bash. Permanecem pendentes a identificação de um campo nativo confiável para preço final e a homologação autenticada do vínculo entre preço e variante. O diagnóstico atual continua com `price_verified=false`, mantendo compras planejadas bloqueadas. Nenhuma transação real executada.

## 2026-11-24 — Autonomia Total A6/A8, seleção externa por limites de hub (G0)

- O seletor percorre o ranking completo de candidatos externos com evidência conclusiva, aplicando os limites individuais de capital e pontos por perfil ao custo do hub. A seleção pode alcançar candidatos abaixo do Top 3 e preserva a comparação econômica para análise, mesmo com os limites zerados ou inválidos. A exigência de pontos positivos continua pendente de comprovação do saldo correspondente.
- A API, o painel PT/EN e o relatório de expansão passam a distinguir as sugestões econômicas dos hubs dentro dos limites individuais. O painel mostra o primeiro candidato dentro dos limites e os motivos de exclusão; mudanças na seleção participam da deduplicação dos alertas. A seleção é somente leitura e não autoriza nem registra uma compra.
- Validação direcionada: 215 testes aprovados; suíte Windows com 2.094 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. Rollback por reversão deste commit. Permanecem pendentes a evidência de demanda residual, preço final, conciliação, saldo de pontos quando exigidos e a homologação do executor real. Nenhuma transação real executada.

## 2026-11-24 — Autonomia Total A7/A8, limites independentes de aquisição de hubs (G0)

- A política por perfil passa a oferecer `max_hub_investment` (capital máximo por hub, em moeda do jogo) e `max_hub_points` (máximo de pontos exigidos por hub), com configuração e validação no painel PT/EN e na API autenticada. O limite individual de aeronaves permanece independente; os limites financeiros de ciclo e de 24 horas continuam compartilhados para proteger o caixa global.
- Os dois novos campos iniciam em zero, inclusive em perfis antigos. Capital zero impede compras de hub; pontos zero só admite checkout que comprove exigência de zero pontos. O teto de configuração de pontos é de 1 bilhão, uma restrição administrativa do bot, sem pressupor um limite oficial do jogo.
- O executor simulado exige o teto de capital do hub e valida os pontos exigidos na leitura do checkout antes da submissão; os testes cobrem configuração ausente, capital excedido, pontos excedidos e independência do limite de aeronaves. A política produtiva continua bloqueada em G0. Nenhuma transação real foi executada.
- Validação: suíte Windows com 2.087 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. Rollback por reversão deste commit. Permanecem pendentes a comprovação do checkout e da demanda residual, a integração do executor real e a homologação dos fluxos A0–A9.

## 2026-11-24 — Autonomia Total A3/A9, rastreabilidade da avaliação contábil (G0)

- O registro privado do ciclo passa a preservar o deslocamento de cada combinação avaliada, as identificações econômicas das avaliações compartilhadas e dos layouts hipotéticos, e os respectivos impedimentos por código e campo. A trilha é vinculada ao snapshot e aos fingerprints da pesquisa e gravada atomicamente junto ao resumo e ao cursor.
- A leitura do resumo reconcilia os totais de combinações, layouts e impedimentos com a trilha e rejeita registros ausentes, estruturalmente inválidos ou divergentes. Registros anteriores exigem um novo ciclo para publicar o resumo, preservando o cursor válido. A API continua expondo apenas os agregados, sem divulgar a trilha privada. O registro corresponde à coleta atual e não constitui histórico permanente nem comprovação de elegibilidade.
- Validação: 7 testes do worker aprovados, incluindo comparação da trilha com o replay do snapshot, rejeição de identificação inválida e retomada entre ciclos; suíte Windows com 2.080 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. Rollback por reversão deste commit. Permanecem pendentes a demanda residual, os preços finais, o registro produtivo de casos elegíveis, a conciliação e a homologação A0–A9. Nenhuma transação real executada.

## 2026-11-24 — Autonomia Total A3, custo incremental de hangar com evidência nativa (G0)

- A pesquisa contábil de aeronaves de passageiros aproveita uma vaga livre de hangar comprovada no snapshot para estabelecer custo incremental zero de uma única aeronave. O contrato valida a fonte nativa, a consistência da capacidade e das vagas, o prazo de validade e o vínculo com o perfil, snapshot e hub da proposta. A resposta de pesquisa apresenta os custos comprovados com fonte e horário da coleta.
- Hangares sem vagas, informações inconsistentes ou vencidas e valores divergentes continuam sem comprovação de custo. O preço exibido de ampliação do hangar permanece apenas uma referência até a validação do custo final. A vaga observada não substitui as travas de reserva, compromissos e revalidação de capacidade do A4/A5.
- Validação: 145 testes direcionados aprovados; suíte Windows com 2.080 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. Rollback por reversão deste commit. Permanecem pendentes a demanda residual, os preços finais, a alimentação produtiva do registro A3, a conciliação e a homologação A0–A9. Nenhuma transação real executada.

## 2026-11-24 — Autonomia Total A3/A9, progressão da pesquisa entre ciclos (G0)

- A pesquisa contábil automática retoma o deslocamento salvo por perfil quando a ordem das identidades de hubs, rotas, modelos e motores permanece igual. Mudanças nessa composição reiniciam a paginação; ao chegar ao fim, o próximo ciclo começa novamente. A posição é persistida atomicamente junto à execução do planejador e preservada durante falhas ou indisponibilidade temporária da fila.
- O limite de duas páginas por execução foi mantido. Cada página é avaliada com o snapshot corrente, e as continuações dentro do mesmo snapshot exigem o fingerprint completo da evidência. As contagens não são acumuladas entre coletas; o painel PT/EN mostra a faixa efetivamente avaliada na coleta atual. Percorrer as identidades em ciclos distintos não comprova cobertura econômica simultânea nem torna um candidato elegível.
- Validação: 222 testes direcionados aprovados; 7 testes do worker aprovados após ampliação da regressão para falha, ausência temporária do catálogo, retomada, mudança de composição e reinício ao final; suíte Windows com 2.079 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída). Ruff e git diff --check aprovados. Rollback por reversão deste commit. Permanecem pendentes a comprovação da demanda residual e dos preços finais, a alimentação produtiva do registro A3, a conciliação e a homologação A0–A9. Nenhuma transação real executada.

## 2026-11-24 — Autonomia Total A3/A9, avaliação econômica no worker (G0)

- O ciclo de planejamento executa automaticamente o replay contábil das combinações pesquisadas antes da decisão global A4. A avaliação utiliza exclusivamente o snapshot capturado no mesmo ciclo, valida identidade e paginação, e agrega impedimentos por código. Configurações de assentos hipotéticas permanecem não verificadas e inelegíveis.
- A API e o painel PT/EN distinguem combinações examinadas, bloqueadas e configurações hipotéticas dos cenários registrados A3 e dos candidatos A4. A falta de fontes na fila não significa ausência de oportunidades. O limite inicial de duas páginas (até 80 combinações por execução) protege a latência do worker; a varredura começa no início de cada snapshot e não comprova cobertura total. A progressão entre ciclos permanece pendente.
- Inspeção autenticada somente leitura do catálogo de encomendas: o detalhe de uma aeronave expõe seleção de motor e hub e os botões Order e Configuration. Ambos são controles de submissão; a inspeção não comprovou a semântica de Configuration nem o preço final. Nenhum desses controles foi acionado e nenhuma compra real foi executada.
- Validação: 45 testes direcionados iniciais e 7 testes do worker após a nova regressão aprovados; suíte Windows com 2.079 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. Rollback por reversão deste commit. Permanecem pendentes a demanda residual, preço final, cobertura integral, registro produtivo de casos elegíveis, conciliação e homologação A0–A9.

## 2026-11-24 — Autonomia Total A4/A9, isolamento do histórico financeiro (G0)

- Inspeção autenticada, somente leitura, em Finances > History > Expenses: a tabela visível em `#transactionContainer` apresenta idade relativa, descrição e valor. As linhas não expõem identificador estável, data absoluta, vínculo com pedido ou voo, nem controle visível de paginação. Não há comprovação da cobertura integral das despesas nem deduplicação confiável entre coletas. O resumo nativo de 24 horas continua sendo uma observação histórica parcial; o detalhamento não foi promovido a diário conciliado.
- O coletor grava a identidade do perfil no momento da coleta e usa escrita atômica privada. Arquivos legados sem identidade ou pertencentes a outro perfil exigem nova coleta. A captura auditada e as métricas A9 conferem a identidade original antes de aproveitar o resumo, impedindo que uma cópia de outro perfil limite o orçamento ou apareça nos relatórios.
- Validação: 134 testes direcionados aprovados; suíte Windows com 2.078 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. Rollback por reversão deste commit. Permanecem pendentes a conciliação integral dos gastos e compromissos, a demanda residual verificável, os custos finais, a produção de evidências econômicas e a homologação A0–A9. Nenhuma transação real executada.

## 2026-11-24 — Autonomia Total A3, restrições físicas com coleta parcial (G0)

- O contrato de viabilidade econômica preserva vetos físicos independentes: alcance direto insuficiente, pista de origem ou destino insuficiente e incompatibilidades nos trechos ou na pista de uma escala verificada. Medidas ausentes ou inválidas continuam bloqueando a recomendação; a insuficiência conhecida permanece explícita mesmo que outras medidas faltem.
- O replay do snapshot utiliza o alcance observado da variante de motor para excluir a rota direta mesmo sem o detalhe das pistas. A evidência permanece vinculada à variante e não é estendida a outros motores. Uma escala ainda pode ser pesquisada; sua viabilidade e as regras do jogo precisam de confirmação.
- Validação: suíte Windows com 2.076 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída), iniciada antes do refinamento final de escalas; 137 testes direcionados aprovados na versão final, incluindo regressão do replay auditado, medidas inválidas e escalas parciais; Ruff e git diff --check aprovados. Rollback por reversão deste commit. Permanecem pendentes a demanda residual verificável, os custos finais de aquisição, a alimentação econômica produtiva, a conciliação financeira e a homologação autenticada. Nenhuma compra real executada.

## 2026-11-24 — Autonomia Total A4, restrição financeira histórica nativa (G0)

- A captura vincula ao perfil e snapshot a soma das despesas identificadas de encomendas de aeronaves, hubs e taxas de rota no resumo nativo das últimas 24 horas. A evidência mantém o horário original, expira em 900 segundos e exige resumo contabilmente consistente.
- O planejador limita o orçamento ao menor teto aplicável entre o histórico observado, os controles auditados e o diário local, sem somar despesas possivelmente sobrepostas. Se os gastos históricos esgotaram o teto, sinaliza a restrição mesmo sem candidatos A3 registrados. O painel PT/EN mostra os valores como históricos e o Telegram identifica o bloqueio.
- A janela histórica encerra-se no instante da observação. O teto restante é uma estimativa conservadora para o snapshot, sujeita a nova coleta; a soma parcial não comprova todos os desembolsos (por exemplo, despesas de hangar não discriminadas), gastos do período atual ou compromissos futuros. Nenhuma compra real executada.
- Validação: 116 testes direcionados, suíte Windows com 2.066 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída), 17 testes de relatório diário aprovados; Ruff e git diff --check aprovados. Rollback por reversão deste commit. Permanecem pendentes a conciliação completa de gastos e compromissos, a produção de evidências econômicas A3, a calibração e a homologação A0–A9.

## 2026-11-24 — Autonomia Total A4, controles locais de política vinculados à coleta (G0)

- A coleta produtiva registra a reserva operacional e os limites configurados de investimento por ciclo e por 24 horas, com identidade de perfil e snapshot. O planejador A4 utiliza esses controles somente quando permanecem compatíveis com a política atual. Alterações ou limites ausentes exigem nova coleta; a reserva zero explícita é válida, enquanto limites de gasto zero permanecem desconfigurados.
- Os valores configurados não comprovam gastos realizados, pedidos pendentes ou compromissos futuros. Esses controles continuam independentes e podem bloquear aquisições. Snapshots antigos preservam a compatibilidade com as evidências anteriormente registradas. Nenhuma compra real executada.
- Validação: 56 testes direcionados aprovados; suíte Windows com 2.063 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. Permanecem pendentes a alimentação produtiva A3, demanda residual, custos finais, comprovação de gastos e compromissos, calibração e homologação autenticada A0–A9.

## 2026-11-24 — Autonomia Total A9, replanejamento no ciclo operacional (G0)

- Com o planejamento habilitado, o próprio worker recalcula a decisão A4 após consolidar cada snapshot produtivo, independentemente de consultas ao painel ou do envio de notificações. A execução é somente leitura, registra status e horários em arquivo privado por perfil e invalida a decisão anterior durante uma nova execução, após falha, expiração ou mudança de snapshot.
- A API autenticada e o painel PT/EN exibem a última execução válida. O resultado registrado é histórico e não autoriza compras. A simulação não publica esse registro nem consulta o planejador produtivo. As falhas registram somente o tipo da exceção, sem divulgar detalhes da conta.
- Validação: 60 testes direcionados aprovados, incluindo replanejamento real A4 com registro vazio, invalidação, falhas, isolamento e API. Suíte Windows: 2.062 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. Rollback por reversão deste commit na branch de trabalho. Replanejamento depende do ciclo periódico existente; gatilhos independentes, alimentação produtiva A3, demanda residual, custos finais, calibração de voos e homologação autenticada A0–A9 seguem pendentes. Nenhuma compra real executada.

## 2026-11-24 — Autonomia Total A9, observabilidade das decisões A3/A4 (G0)

- A API de métricas, o painel PT/EN e o resumo diário do Telegram passam a distinguir pesquisa preliminar de cenários registrados no A3 e candidatos do planejador A4. Os seis escopos de coleta são independentes; as contagens auditadas dependem de captura atual (até 900 segundos), perfil e snapshot correspondentes. Registro vazio informa zero cenários registrados, sem comprovar ausência de oportunidades. Evidência vencida ou divergente mantém contagens desconhecidas.
- Uma sugestão de análise exige cobertura comprovada, candidato elegível, plano disponível e ausência de impedimentos. O Telegram apresenta a decisão e os bloqueios auditados, com rótulos conhecidos e contagem dos demais. O ambiente de simulação não consulta a evidência produtiva. Candidatos A4 não equivalem a compras aprovadas ou realizadas.
- Validação: 73 testes direcionados aprovados, incluindo API autenticada e resumo diário com captura vigente, expirada e simulação. Suíte Windows: 2.058 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. Rollback por reversão deste commit na branch de trabalho. Permanecem pendentes a alimentação produtiva do registro A3, a comprovação de demanda residual e custos finais, a calibração com voos e razão financeira e a homologação das fases A0–A9. Nenhuma compra real executada.

## 2026-11-24 — Autonomia Total A3, veto de rota por observação nativa (G0)

- O replay auditado usa a contagem positiva do formulário nativo correlacionado por perfil, origem, destino, distância e escala para excluir a projeção econômica de uma rota potencialmente ocupada, mesmo sem cobertura completa da frota. O gate A3 também considera a contagem positiva do detalhe nativo atual e o feed sinaliza essa observação como pendência.
- Contagens zero isoladas não provam disponibilidade. Tarifas e taxa do formulário existente permanecem referências específicas da aeronave observada, sem transferência para a proposta de compra. Demanda residual, preço final e custos incrementais ainda exigem evidência independente; a proposta permanece bloqueada. Nenhuma compra real executada.
- Regressão coberta para contagem positiva sem frota, contagem zero, distância incompatível e detalhe nativo positivo. Suíte Windows: 2.053 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. Rollback por reversão deste commit na branch de trabalho. A homologação de A3–A9 continua pendente.

## 2026-11-24 — Autonomia Total A4/A7, peso de retorno no ranking (G0)

- A política por perfil passa a oferecer `return_weight` de 0 a 100, com padrão zero para preservar o ranking anterior. O painel PT/EN salva o valor pela API autenticada e os planejadores consideram o peso na composição do score. Uma política baseada exclusivamente em retorno é válida; valores inválidos e a ausência de qualquer peso positivo são recusados.
- O retorno auditado usa o ROI de 365 dias comprovado pela avaliação A3. Na comparação preliminar, o índice normalizado equivale à eficiência diária do capital, porque a anualização é proporcional. O painel explica essa relação para evitar interpretar os dois pesos como evidências econômicas independentes.
- Validação: 175 testes direcionados e 2.052 testes da suíte Windows aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. Nenhuma transação real executada. A integração do ciclo ao executor produtivo depende de sua homologação; o ciclo operacional do bot não encerra automaticamente o orçamento persistente. Permanecem pendentes a cobertura econômica real e a homologação das fases A0–A9. Rollback por reversão deste commit na branch de trabalho; configurações existentes mantêm os demais pesos.

## 2026-11-24 — Autonomia Total A4/A7, saldo persistente do ciclo no planejamento (G0)

- O planejador auditado e a API consultam o ciclo ativo e as reservas do diário SQLite em uma única transação de leitura. As confirmações vinculadas ao ciclo continuam contabilizadas mesmo fora da janela móvel de 24 horas. O orçamento disponível respeita simultaneamente o limite local vigente e o limite auditado, adotando o menor saldo restante para evitar dupla contagem de observações possivelmente sobrepostas.
- O painel PT/EN apresenta o saldo local e sinaliza evidência ausente. Bancos legados são consultados sem migração pela API e a ausência de comprovação do ciclo impede a proposta. Os valores são estimativas registradas no diário; o desembolso real exige comprovação independente.
- Validação: 257 testes direcionados aprovados, incluindo persistência, isolamento por perfil, encerramento do ciclo, leitura de esquema legado e restrição da proposta pela API. Suíte Windows: 2.050 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. Nenhuma compra real ou implantação. Continuam pendentes a integração do ciclo ao orquestrador produtivo, a alimentação produtiva das evidências econômicas e a homologação A0–A9. Rollback da entrega por reversão do commit na branch de trabalho, preservando os registros SQLite.

## 2026-11-24 — Autonomia Total A4/A5/A7, diário persistente por ciclo (G0)

- O diário SQLite mantém um único ciclo ativo por perfil, com identidade própria e abertura/encerramento persistentes. Sob exclusividade do executor, a aprovação e a vinculação da intenção ao ciclo ocorrem na mesma transação que verifica o teto configurado. O cálculo soma reservas ainda abertas e aquisições confirmadas no ciclo, compartilhando o orçamento entre aeronaves e hubs. O limite diário continua independente.
- Reiniciar o processo ou atualizar o snapshot não reinicia o orçamento. O encerramento exige o identificador do ciclo esperado, a exclusividade do executor e ausência de reservas pendentes. Registros anteriores à migração continuam preservados: reservas antigas entram no cálculo e confirmações antigas sem vínculo permanecem sujeitas ao controle de 24 horas. O novo controle usa os custos estimados registrados, não o desembolso real comprovado pelo jogo.
- Os dois executores simulados usam o controle antes do checkout. Testes cobrem limite ausente, reinício, encerramento explícito, reservas pendentes e expansão hub/aeronave com snapshots distintos. Suíte Windows: 2.045 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. A abertura e o encerramento ainda precisam ser integrados ao orquestrador produtivo e a exposição do ciclo ao planejamento auditado. A execução autenticada e a homologação A0–A9 continuam pendentes; nenhuma transação real executada.

## 2026-11-24 — Autonomia Total A4, teto financeiro por ciclo (G0)

- A política de investimento passa a oferecer `max_cycle_spend`, configurável no painel PT/EN e validado pela API. O padrão zero exige configuração explícita antes de uma proposta auditada. O teto vigente e o teto comprovado pelo registro A4 são comparados, adotando-se o menor e descontando-se o gasto de ciclo registrado.
- O orçamento global respeita o saldo restante desse limite, além dos compromissos, reserva, limite do período e diário local. Limite ausente, inválido ou esgotado bloqueia a proposta. O painel informa o valor restante quando disponível; os testes verificam também a redução do teto pela API e a impossibilidade de usar o teto para mascarar pesos de ranking zerados.
- Validação: 170 testes direcionados aprovados; suíte Windows com 2.041 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. A aplicação do teto nesta entrega é restrita ao planejamento auditado. Continuam pendentes a identidade persistente do ciclo, a vinculação do diário de aquisições ao ciclo, a aplicação no executor, a cobertura econômica integral e a homologação das fases A0–A9. Nenhuma transação real executada.

## 2026-11-24 — Autonomia Total A4, limites vigentes e diário de 24 horas (G0)

- A comparação global auditada incorpora a reserva operacional vigente, o teto de gasto e a quantidade máxima de aquisições nas últimas 24 horas, usando o mesmo diário local consultado pela conciliação financeira. A reserva aplicada é a maior entre a configuração atual e as evidências A3/A4. O orçamento é o menor entre caixa após compromissos, limites auditados de ciclo/período e limite local de gasto restante, sem somar exposições já conciliadas ao caixa.
- Limites ausentes ou inválidos, janela local incompleta ou antiga, perfil divergente e quantidade esgotada impedem a proposta. O painel PT/EN exibe a disponibilidade dos limites locais. Os valores do diário são estimativas de intenções reservadas e confirmadas; não constituem comprovação do gasto real completo do jogo. A configuração explícita de teto por ciclo e o vínculo temporal do gasto auditado continuam pendentes.
- Validação: 143 testes direcionados aprovados (incluindo integração real do planejador pela API com alteração de política); suíte Windows com 2.035 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. Continuam pendentes a cobertura econômica integral, demanda residual, custos finais, alimentação produtiva do registro A3 e homologação autenticada das fases A0–A9. Nenhuma transação real executada.

## 2026-11-24 — Autonomia Total A4, capacidade global do hangar de passageiros (G0)

- O planejador auditado utiliza as vagas livres do hangar de passageiros da companhia, observadas no jogo e vinculadas ao perfil, ao snapshot e ao instante original da coleta. A mesma capacidade restringe todas as alternativas de hubs próprios. A antiga evidência por hub permanece apenas para compatibilidade dos registros existentes.
- Ausência de evidência, contagens inconsistentes, fonte incorreta, coleta vencida ou hangar cheio impedem a sugestão de aquisição. O painel apresenta a quantidade global de vagas quando confirmada; a conciliação após compras também considera a idade dessa evidência. Uma eventual ampliação de hangar requer avaliação e validação próprias.
- Validação: 149 testes direcionados e 2.024 testes da suíte Windows aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. Nenhuma transação real executada. Permanecem pendentes a cobertura econômica integral, os custos finais e a demanda residual, a alimentação produtiva do registro A3 e a homologação autenticada das fases A0–A9.

## 2026-11-24 — Autonomia Total A4, vinculação à coleta atual da frota (G0)

- O planejamento global passa a exigir uma coleta atual, válida e vinculada ao mesmo snapshot das avaliações A3. A cobertura da frota usa a observação do jogo e sua validade temporal, inclusive quando ainda não há avaliações registradas. A cobertura de pesquisa exige simultaneamente os escopos de hubs, rotas, modelos, motores e preços e a comprovação independente do registro A4.
- A quantidade de aeronaves sem rota é derivada dos totais conciliados da coleta, preservando o timestamp mais antigo entre o inventário e a auditoria das rotas. A prova antiga armazenada é substituída pela observação atual; ausência, vencimento e divergência da coleta impedem uma proposta de compra. A conciliação financeira utiliza os controles efetivamente empregados na comparação. Nenhum identificador de aeronave é exposto pelo resumo agregado.
- Validação: 117 testes direcionados aprovados após os ajustes finais; suíte Windows com 2.021 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. As fixtures comprovam os bloqueios e a integração local. Continuam pendentes a cobertura integral de pesquisa, a demanda residual e os custos finais comprovados, a alimentação produtiva do registro econômico e a homologação autenticada das fases A0–A9. Nenhuma transação real foi executada.

## 2026-11-24 — Autonomia Total A3, referência salarial por variante (G0)

- A observação nativa de pessoal captura quantidade, salário diário unitário e total por função, exigindo as quatro categorias únicas e a consistência aritmética. A leitura autenticada anterior identificou os quatro cartões e as respectivas linhas de salário diário, sem alterações no jogo. A coleta Selenium automatizada ainda requer homologação autenticada. Os registros permanecem isolados por perfil, em arquivo privado, com invalidação antes de nova tentativa e validade de 900 segundos.
- A pesquisa atual de hubs próprios e externos e a reprodução histórica compartilham o cálculo do salário diário caso todos os profissionais exigidos pela variante sejam adicionais. A referência expira com a evidência mais antiga, integra o fingerprint da paginação e aparece no painel PT/EN. Não comprova déficit ou excedente de pessoal, custo incremental ou despesa realizada, não altera o lucro auditado e não torna uma proposta elegível. As fixtures utilizam valores sintéticos; nenhuma informação salarial da conta foi publicada no repositório.
- Validação: 172 testes direcionados aprovados; suíte Windows completa com 2.014 aprovados, nenhuma falha e 1 ignorado (instalação Linux excluída); Ruff e git diff --check aprovados. Nenhuma transação real executada. Permanecem pendentes a comprovação do custo incremental de pessoal, demanda residual, custos finais e homologação integral das fases A0–A9.

## 2026-11-24 — Autonomia Total A3/A5, requisitos operacionais por variante (G0)

- A leitura autenticada do detalhe da aeronave passa a registrar o tempo de entrega exibido e os quantitativos de pilotos, tripulação de cabine, engenheiros e técnicos. A observação opcional exige as cinco linhas únicas, valores inteiros válidos e duração positiva. O catálogo mantém os dados por variante de motor, associados à identidade do modelo e ao instante da coleta. O painel PT/EN e a reprodução histórica apresentam somente os requisitos correlacionados à variante.
- Evidência nativa em leitura sem mutação: o detalhe do Cessna 172 apresentou entrega de 30 segundos, 1 piloto, 0 tripulantes de cabine, 1 engenheiro e 1 técnico. A fixture anonimizada e os testes cobrem ausência, duplicidade e valores inválidos, inclusive tripulação zero. Os requisitos exibidos não comprovam disponibilidade de pessoal, salários, custos incrementais nem prazo de entrega efetivo. Esses dados ainda não habilitam uma aquisição ou avaliação econômica integral. Nenhuma transação real executada.
- Validação: 219 testes direcionados aprovados e suíte Windows completa com 2.009 aprovados, 1 ignorado e nenhuma falha (instalação Linux excluída), incluindo o teste adicional de reprodução histórica. Ruff e git diff --check aprovados. A homologação integral A0–A9 permanece pendente.

## 2026-11-24 — Autonomia Total A3/A4, stress simultâneo no ranking global (G0)

- A avaliação econômica auditada passa a recalcular receita, combustível, CO₂, lucro e retorno quando os quatro fatores de stress ocorrem simultaneamente, preservando os cenários isolados. O ranking global utiliza a menor proporção de lucro em relação ao cenário base entre os cinco cenários, limitada ao intervalo de zero a um. Quando o peso de risco é positivo, a ausência do cenário combinado impede a classificação. O painel PT/EN mostra os quatro multiplicadores e o resultado combinado.
- Validação: 141 testes direcionados aprovados, teste da interface atualizado e aprovado, suíte Windows com 2.008 aprovados e 1 ignorado (instalação Linux excluída). Nenhuma compra executada. Os cenários continuam sendo projeções condicionadas às evidências econômicas disponíveis; a homologação real e a comprovação de demanda residual, configuração selecionável e custos finais permanecem pendentes.

## 2026-11-24 — Autonomia Total A3, comparação econômica com referência nativa de assentos (G0)

- A simulação inclui a configuração Y/J/F observada e correlacionada ao modelo e motor como referência econômica, deduplicando configurações iguais. Cada alternativa informa sua diferença de contribuição diária em relação à referência, nos cenários base e stress, tanto com preços observados quanto com os limites configurados, quando disponíveis. Havendo projeção de A-check, a comparação utiliza a contribuição após a reserva. O painel PT/EN identifica a referência como não confirmada.
- Validação: 167 testes direcionados aprovados, Ruff e git diff --check aprovados. A suíte completa não foi executada nesta entrega. A configuração permanece observacional e inelegível para aquisição; demanda residual, configuração efetivamente selecionável e custos finais continuam pendentes. Nenhuma transação real executada.

## 2026-11-24 — Autonomia Total A3, observação nativa dos assentos (G0)

- A leitura estável do detalhe de cada variante captura os assentos Y/J/F dentro de `#step2`, diferenciando o modelo oculto do formulário visível. Exige campos únicos, contagens inteiras e capacidade ponderada coerente. A informação acompanha o motor correlacionado, o registro de pesquisa e a reprodução histórica; o painel PT/EN sinaliza que a configuração ainda não está confirmada.
- Evidência autenticada anterior à implementação: Cessna 172 com capacidade de 3 passageiros e modelo oculto 3/0/0, enquanto a etapa inicial informava limite de frota atingido. Nenhuma interação de compra. O formulário oculto não comprova disponibilidade, configuração selecionável ou custo final; mesmo a leitura visível permanece apenas observacional. A validação econômica continua bloqueando configurações sem evidência de aquisição.
- Validação: 223 testes direcionados aprovados, incluindo execução do coletor DOM em Node, persistência por variante, identidade, reprodução histórica e interface. Ruff e git diff --check aprovados. Suíte completa não executada nesta entrega. Permanecem pendentes configuração efetivamente selecionável, demanda residual, custos finais e homologação das fases A0–A9.

## 2026-11-24 — Autonomia Total A9, tempos de detecção e conciliação no diário (G0)

- O diário mede o intervalo local entre envio e reconhecimento de incerteza, e entre incerteza e conciliação, com contagem de amostras por perfil. A janela considera a transição final e recupera o evento predecessor mesmo se ele ocorreu antes do corte. Intervalos negativos ou transições inconsistentes são descartados. O painel PT/EN e o relatório diário Telegram exibem essas métricas quando há evidência.
- Validação: 47 testes direcionados, Ruff e git diff --check aprovados. A métrica de detecção do incidente real permanece desconhecida: o diário comprova apenas os tempos entre seus próprios eventos. A calibração de lucro exige histórico de voos e contabilidade independentes. Nenhuma compra executada.

## 2026-11-24 — Autonomia Total A3, avaliação individual de layouts (G0)

- A pesquisa histórica passa a identificar e avaliar cada configuração hipotética Y/J/F separadamente, vinculando sua identidade econômica à combinação de hub, rota, modelo, motor e snapshot. O validador conserva os impedimentos comuns e rejeita a configuração ainda não confirmada pela loja do jogo. A interface PT/EN exibe os motivos de bloqueio por layout.
- Testes direcionados: 203 aprovados. Suíte Windows: 2.001 aprovados, nenhum erro e 1 ignorado (testes de instalação Linux excluídos). Ruff e git diff --check aprovados. As configurações continuam inelegíveis para compra; a coleta de configuração nativa, demanda residual, custos finais e demais evidências para avaliação financeira completa permanece pendente.

## 2026-11-24 — Autonomia Total A3, preços configurados e stress reproduzível (G0)

- Os limites positivos de compra de combustível e CO₂ (`fuel_price_good` e `co2_price_good`, em USD/1000) são tratados como hipóteses explícitas de planejamento. A pesquisa mantém os cenários com cotações observadas e calcula, separadamente, contribuição diária base e stress com os preços configurados, preservando as configurações de assentos em cada comparação. O otimizador também considera os layouts que maximizam a contribuição sob essas hipóteses.
- A configuração é vinculada ao fingerprint da pesquisa e preservada na captura privada para reprodução histórica. Snapshots anteriores continuam legíveis. Os cenários são apresentados no painel PT/EN, sem elevar hipóteses a preços verificados ou habilitar aquisições. Quando um dos limites não é positivo, a simulação configurada fica indisponível.
- Validação Windows: 163 testes direcionados, suíte completa com 2.001 aprovados e 1 ignorado (instalação Linux excluída), Ruff e git diff --check aprovados. A projeção ainda exige cotações recentes para a comparação observada. Permanecem pendentes as fontes nativas e a homologação integral das fases A0–A9. Nenhuma transação real executada.

## 2026-11-24 — Autonomia Total A3, integração da validação econômica auditada (G0)

- A pesquisa histórica por hub, rota, modelo e motor passa a executar o validador econômico de aquisição sobre o snapshot privado e a hora de captura. A API informa os impedimentos comuns aos layouts hipotéticos, as entradas contábeis verificadas e um identificador reproduzível de avaliação. O painel PT/EN apresenta o estado e os motivos em detalhes expansíveis.
- O adaptador reconhece capacidade somente no detalhe correlacionado e recente da variante, preços de combustível e CO₂ dentro da janela observada, custo incremental zero para hub próprio comprovado e ocupação com evidência consistente. Distingue rota ocupada de ocupação desconhecida e converte pistas de pés para metros no contrato auditado. Não atribui demanda residual, configuração de assentos nativa, preço final, disponibilidade de compra ou despesas sem evidência. A validação é compartilhada pelos layouts e não gera oportunidades elegíveis ou registros de aquisição enquanto faltarem esses dados.
- Validação Windows: 226 testes direcionados e suíte completa com 2.000 aprovados, 1 ignorado e nenhum erro (testes de instalação Linux excluídos). Ruff e git diff --check aprovados. Nenhuma transação real executada. Permanecem pendentes a coleta nativa dos dados de aquisição, a avaliação integral por layout e a homologação das demais fases do objetivo.

## 2026-11-24 — Autonomia Total A3, sensibilidade e recuperação indicativa de capital (G0)

- A pesquisa por combinação de hub, rota, motor e layout simula cada variável de stress isoladamente: preço de combustível +20%, CO₂ +20%, ocupação -10% e demanda -10%, além do stress combinado. Cada comparação preserva a configuração Y/J/F e a margem, com as mesmas hipóteses de rotação e tarifas. Quando disponível, a reserva condicional de A-check também é aplicada às contribuições comparadas.
- Com preço observado da variante e subtotal de capital disponível (aeronave, hangar e hub quando aplicável), cada layout apresenta dias indicativos para recuperar esse subtotal e a contribuição anual em percentual do subtotal nos cenários base e stress. Contribuição não positiva não gera prazo de recuperação. A validade é limitada pela primeira evidência a expirar. A simulação é reproduzível na captura histórica e permanece inelegível para compra. Não calcula payback ou ROI auditados, pois taxa da rota, preço final, demanda residual e demais despesas ainda não estão confirmados.
- Validação Windows: 175 testes direcionados e suíte com 1.999 aprovados, 1 ignorado e nenhuma falha; instalação Linux excluída. Ruff e git diff --check aprovados. Nenhuma transação real executada. A avaliação auditada e homologação das fases restantes continuam pendentes.

## 2026-11-24 — Autonomia Total A3, correlação histórica de cotações de rota (G0)

- A reprodução da pesquisa por snapshot agora associa as cotações nativas capturadas por perfil, origem, destino, direção, distância e identidade da escala. O painel PT/EN apresenta quantidade, intervalos de taxa, tarifas Y/J/F e ocupação, com validade calculada pela observação mais antiga. Os identificadores privados das aeronaves não são expostos na pesquisa.
- A correspondência exige distância exata, inclusive na soma dos trechos de escala; diferenças de arredondamento podem omitir uma referência. Os valores são específicos das aeronaves existentes, preservados como evidência histórica, sem estimar preço final de novas rotas ou demanda residual. Lucro líquido e elegibilidade permanecem desconhecidos ou bloqueados.
- Validação Windows: 31 testes direcionados e suíte completa com 1.997 aprovados, 1 ignorado e nenhum erro; testes de instalação Linux excluídos. Ruff e git diff --check aprovados. Nenhuma transação real executada. Ainda falta integrar evidências suficientes à avaliação auditada A3 e homologar as demais fases.

## 2026-11-24 — Autonomia Total A3, reserva condicional de A-check (G0)

- A simulação econômica utiliza custo e intervalo de A-check observados no detalhe da variante com identidade confirmada. A reserva diária é o custo dividido pelo intervalo, multiplicado pelas horas de voo projetadas. São calculadas as horas reais (distância / velocidade efetiva × partidas) e nominais (distância / velocidade de cruzeiro × partidas), inclusive pelos dois trechos em uma escala exploratória. A maior reserva é deduzida da contribuição após margem, nos cenários base e stress, em um resultado condicional separado.
- O painel PT/EN mostra custo, intervalo, as duas reservas e a contribuição após a reserva adicional por layout. Sem os dois parâmetros observados, a projeção adicional é omitida. A contribuição original mantém suas exclusões. O relógio de manutenção e as demais despesas ainda exigem comprovação; demanda residual, custo final de rota, lucro líquido auditado e elegibilidade continuam pendentes.
- Validação Windows: 174 testes direcionados aprovados, incluindo Easy/Realism, evidência parcial por motor e painel. Ruff e `git diff --check` aprovados. Suíte Windows: 1.996 aprovados e 1 ignorado; testes de instalação Linux excluídos. A alteração final do rótulo do painel também passou nos 174 testes direcionados.
- Próxima dependência: conectar observações nativas à avaliação auditada A3 e verificar demanda residual, preço final e contabilização de manutenção. Nenhuma transação real executada; objetivo integral ativo.

## 2026-11-24 — Autonomia Total A3, evidências de cotações nativas de rota (G0)

- O bot conserva cotações de formulários nativos somente após duas leituras consistentes de identidade, distância, taxa, ocupação e tarifas Y/J/F. A simulação também coleta a cotação, sem enviar o formulário. A coleção é limitada a 256 registros recentes, isolada por perfil e consolidada no snapshot privado do ciclo.
- A observação identifica a aeronave existente e a escala quando aplicável. Demanda total de escala é preservada separadamente; demanda residual permanece desconhecida. A API de resumo expõe apenas a quantidade de cotações recentes. A cotação não comprova preço de rota para uma futura encomenda e permanece inelegível para compra.
- Validação Windows: 84 testes direcionados aprovados; suíte Windows ampliada: 1.994 aprovados e 1 ignorado, com `tests/test_instalacao_linux.py` excluído por depender de Linux. Ruff e `git diff --check` aprovados. A coleta ainda requer homologação Selenium autenticada. Permanecem pendentes a comprovação de demanda residual e preço de futuras rotas, a alimentação de oportunidades elegíveis A3 e as demais fases do roadmap. Nenhuma transação real executada.

## 2026-11-24 — Autonomia Total A3/A5, validação das tarifas nativas de rota (G0)

- A criação de rotas diretas e com escala e a preparação de trocas usam uma leitura compartilhada das três tarifas no formulário nativo ativo. Campos duplicados, ambíguos ou vazios quando habilitados e valores negativos são rejeitados. Classes desabilitadas podem apresentar zero. O preço automático exige um único controle.
- Antes do envio, as tarifas são relidas e comparadas com a cotação inicial, juntamente com o formulário e o saldo. Nas trocas, a espera pelo preenchimento nativo tem limite e uma divergência impede a preparação. A estimativa para escala utiliza os valores estritamente validados.
- Validação Windows: 63 testes direcionados aprovados, Ruff e `git diff --check` aprovados. A integração Selenium com o jogo real ainda requer homologação. As tarifas observadas em formulários de aeronaves existentes não comprovam preços para futuras compras; a alimentação de oportunidades auditadas A3 permanece pendente. Nenhuma transação real executada.

## 2026-11-24 — Autonomia Total A3, otimização de layouts Y/J/F (G0)

- A pesquisa por hub, rota, modelo e motor agora inclui layouts que maximizam a contribuição diária estimada no cenário base e no stress combinado, preservando as alternativas de referência econômica e premium. O algoritmo inteiro respeita a capacidade ponderada 1/2/3, demanda por classe, margem e custo de CO₂; explora as quantidades de F e encontra a melhor combinação Y/J por busca sobre uma função discreta côncava. As alternativas idênticas são consolidadas, com indicação das estratégias que as selecionaram.
- O painel identifica layouts otimizados em PT/EN e os resultados incluem receita discriminada por classe. Cada layout permanece fixo na comparação base/stress. O cálculo usa as hipóteses da pesquisa existente e a demanda total observada, não comprova disponibilidade residual nem preços finais. Lucro líquido, payback e elegibilidade de compra permanecem pendentes de evidência.
- Validação Windows: 234 testes direcionados aprovados, incluindo comparação do otimizador com enumeração exaustiva em 160 cenários determinísticos. Ruff e `git diff --check` aprovados.
- Pendentes: fontes verificadas de demanda residual e taxas/preços finais, alimentação de casos auditados A3 elegíveis e homologação das fases seguintes. Nenhuma compra real executada; objetivo integral ativo.

## 2026-11-24 — Autonomia Total A2/A4/A5, conciliação do snapshot vigente (G0)

- O plano auditado de aquisição exige consistência com a última captura disponível do jogo. Captura divergente, expirada ou inválida bloqueia o plano, preservando os resultados históricos para diagnóstico. Uma instalação sem captura local mantém a compatibilidade com registros auditados independentes; as demais verificações financeiras e de cobertura continuam obrigatórias.
- A captura registra a partição de aeronaves com rota e sem rota e a confirmação nativa de identidades. Uma frota não vazia com zero páginas de rotas pode ter cobertura coerente quando todas as aeronaves sem rota são conciliadas e os totais e IDs conferem. Isso não promove as demais fontes de pesquisa a cobertura completa.
- Validação Windows: 222 testes direcionados aprovados (contrato, captura, registro A3, painel, economia e portfólio). Ruff e `git diff --check` aprovados.
- Pendentes: fontes verificadas de demanda residual e preços finais, alimentação de oportunidades A3 elegíveis e homologação das etapas restantes. Nenhuma transação real executada; objetivo integral ativo.

## 2026-11-24 — Autonomia Total A2/A3, cobertura independente de modelos e motores (G0)

- O snapshot passa a reconhecer a cobertura do catálogo de passageiros quando a lista nativa e os detalhes de todos os modelos apresentam correspondência de identidade e tentativa válida. A cobertura das variantes exige observações de todas as opções disponíveis de cada modelo. A validade de cada escopo respeita a expiração mais próxima entre a lista nativa (900 s) e os detalhes dos modelos (3 dias).
- A API reavalia a validade dos escopos na leitura do snapshot. Detalhes ausentes, tentativas inconclusivas, expiração ou registros antigos sem a nova prova mantêm a cobertura correspondente pendente. Cobertura de opções de motor não equivale à comprovação de todos os parâmetros econômicos ou do preço final; rotas e preços permanecem parciais.
- Validação Windows: 222 testes direcionados aprovados, incluindo regressões de expiração, identidade, detalhes de variantes e integração com o snapshot. Ruff e `git diff --check` aprovados.
- Pendentes: demanda residual, taxas, preços finais, produção de oportunidades A3 elegíveis e homologação das fases seguintes. Nenhuma compra real executada. A meta integral permanece ativa.

## 2026-11-24 — Autonomia Total A3, painel de reprodução histórica (G0)

- A análise auditada de expansão disponibiliza uma seção própria para consultar as combinações de hub, rota, modelo e motor do último snapshot A3, com paginação vinculada à identidade e à impressão digital da captura. Mostra demanda total observada, distâncias, ocupação, triagem física, custos indicativos, layouts e contribuições diárias em condições históricas, com motivos de bloqueio e indicadores desconhecidos explícitos.
- O relógio da captura é aplicado também às cotações e às evidências de ocupação, motores, dimensões e simulações. Preços históricos são identificados na interface. Respostas atrasadas, páginas de outra captura, ausência de dados, expiração ou respostas inválidas não apresentam cenários antigos como vigentes nem habilitam compras. Interface PT/EN.
- Validação Windows: 174 testes direcionados aprovados antes da inclusão da regressão de interface; em seguida, os 10 testes do painel foram aprovados, incluindo a nova regressão Node.js de reprodução histórica, paginação, expiração e resposta inelegível. Ruff e `git diff --check` aprovados.
- Pendentes: coleta conclusiva de demanda residual, taxas e preços finais, geração de casos elegíveis A3 e homologação autenticada das fases restantes. Nenhuma transação real executada. O objetivo integral permanece ativo.

## 2026-11-24 — Autonomia Total A3, reprodução paginada das alternativas por snapshot (G0)

- A captura automática agora preserva o modo de jogo observado, a margem configurada e as evidências de ocupação da frota usadas na avaliação. O replay reutiliza o mesmo otimizador de pesquisa com o relógio da captura, incluindo as cotações de combustível e CO₂, para gerar combinações hub/rota/modelo/motor e layouts em condições reproduzíveis.
- Endpoint GET autenticado `/api/investment/audited-expansion/research`, somente leitura. Primeira consulta sem parâmetros; páginas seguintes usam `research_offset` (next_offset), `snapshot_id` e `research_snapshot` (snapshot_fingerprint). Mudanças de snapshot impedem combinar páginas de capturas diferentes; capturas anteriores sem os novos insumos exigem recoleta. As projeções são históricas, expiram conforme as evidências e não autorizam compras.
- Validação Windows: 165 testes direcionados aprovados, incluindo reprodução após mudança do relógio, margem, rota ocupada, paginação, adulteração, expiração e autenticação do endpoint. Ruff e `git diff --check` aprovados.
- Pendentes: integração visual do replay, cobertura conclusiva da demanda residual, preços finais, custos e geração de casos A3 auditados elegíveis, seguida da homologação A4–A9. Nenhuma transação real executada. O objetivo integral permanece ativo.

## 2026-11-24 — Autonomia Total A3/A4/A7, captura automática de evidências do jogo (G0)

- Com o planejamento habilitado, o ciclo atualiza o saldo após as operações e consolida um snapshot local por perfil com hash canônico. Preserva as datas originais do seletor de hubs, auditoria da frota, amostras de demanda e detalhes de rotas, catálogo de motores, mercado, compromissos e histórico financeiro. O arquivo é gravado atomicamente com permissão privada quando suportada.
- A cobertura da frota exige auditoria corrente, páginas coerentes e identidade conciliada das aeronaves pendentes/estacionadas quando existentes. O seletor de hubs próprios exige leitura recente. Pesquisas limitadas, catálogo indicativo e ausência de preço final não certificam cobertura de rotas, modelos, motores ou preços. Caixa confirmado não implica compromissos ou reserva confirmados.
- A API auditada e o painel de expansão exibem a coleta parcial e a quantidade de amostras, sem publicar os IDs da frota do snapshot. Leitura verifica perfil, hash e idade. Nenhuma avaliação econômica elegível ou autorização de compra é criada a partir desta captura parcial.
- Validação Windows: 1.956 testes aprovados e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX), seguida de 23 testes direcionados aprovados após o ajuste final e inclusão do teste de captura persistente. Ruff e `git diff --check` aprovados.
- Ainda pendentes a produção de candidatos A3 a partir das evidências completas, a cobertura integral de pesquisa, o preço final por configuração, demanda residual, taxas e compromissos independentes, além da homologação autenticada. Nenhuma transação real executada. O objetivo integral permanece ativo.

## 2026-11-24 — Autonomia Total A4/A5, conciliação financeira atual do plano auditado (G0)

- Antes de emitir uma prévia A5, o painel exige saldo vivo válido, lido em momento igual ou posterior à evidência de caixa do snapshot A3, e exatamente compatível com o valor auditado. Divergência ou ausência de confirmação mantém a comparação inconclusiva e impede o plano.
- O diário local inclui o horário da última aquisição confirmada na janela de 24 horas. Confirmação posterior a qualquer evidência da avaliação ou dos controles do portfólio exige atualização do snapshot, inclusive se o saldo atual coincidir com o anterior. Motivos de bloqueio disponíveis em PT/EN.
- Validação Windows: 1.953 testes aprovados, nenhum reprovado e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX). Ruff e `git diff --check` aprovados. Testes cobrem saldo ausente, leitura anterior, divergência e compra confirmada após o snapshot.
- Ainda pendentes a conciliação de compromissos reais e mutações legadas, a produção de evidências completas A3/A4 em execução e a homologação autenticada. Nenhuma transação real executada. O objetivo integral permanece ativo.

## 2026-11-24 — Autonomia Total A4/A5, bloqueio por operações locais pendentes (G0)

- Os relatórios de recomendações e de expansão auditada consultam o diário de investimentos existente em modo SQLite somente leitura, por perfil e ambiente real, sem criar ou migrar o banco em consultas GET. Ausência de diário significa somente ausência de reservas locais; erro de leitura, esquema incompatível ou ambiente de simulação impede conclusão.
- Intenções reservadas (APPROVED, PRECHECKED, SUBMITTED e UNKNOWN), criação de rota ou redirecionamento pendente tornam a comparação inconclusiva e impedem a prévia de um novo plano A5. Alternativas continuam disponíveis para análise. Motivos identificados no painel PT/EN e no relatório de investimentos.
- Validação Windows: 1.949 testes aprovados, nenhum reprovado e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX). Ruff e `git diff --check` aprovados. Testes abrangem isolamento, ausência/corrupção do diário, ambiente incorreto, leitura sem alteração e bloqueios de rotas e compra submetida.
- Permanecem pendentes a conciliação de compromissos reais, a vinculação do saldo vivo e das confirmações posteriores ao snapshot A3/A4, as evidências completas de rentabilidade e a homologação autenticada. Nenhuma compra real executada. O objetivo integral permanece ativo.

## 2026-11-24 — Autonomia Total A4/A7, validade do saldo para investimentos (G0)

- As consultas de expansão de hubs, pesquisa externa e recomendações de aeronaves passaram a usar exclusivamente o saldo inteiro não negativo confirmado pelo jogo nos últimos 900 segundos. Amostras históricas continuam disponíveis para exibição e cálculo de renda, mas não restabelecem uma evidência de saldo revogada, inclusive após gasto, falha de leitura ou reinício.
- Nova leitura do cabeçalho, perda de sessão e encerramento do navegador revogam a confirmação anterior. Somente uma leitura válida restabelece a elegibilidade financeira. O saldo zero confirmado é válido; valores fracionários, booleanos, negativos, não finitos e observações futuras ou expiradas são rejeitados.
- Validação Windows: 1.943 testes aprovados, nenhum reprovado e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX); 112 testes direcionados aprovados antes dos dois testes adicionais de revogação, e 38 testes de saldo aprovados após a inclusão. Ruff aprovado.
- Permanecem pendentes a conciliação de compromissos financeiros futuros, as evidências completas de rentabilidade e a homologação autenticada do planejador. Nenhuma transação real foi executada. O objetivo integral permanece ativo.

## 2026-11-24 — Autonomia Total A5, conciliação persistente de criação de rotas (G0)

- A criação de rota direta ou com escala reserva uma intenção exclusiva por perfil antes do clique. Uma resposta perdida, falha do navegador ou reinício conserva a intenção; a recuperação consulta os detalhes da aeronave sem reenviar a criação. Somente a confirmação independente da rota esperada permite registrar a relação e contabilizar a taxa cotada. O registro persistente de despesas e contadores utiliza a identidade da intenção para impedir contabilização repetida após reinício e atualiza o caixa por nova leitura.
- Intenção inconclusiva ou arquivo ilegível bloqueia novas criações e compras de aeronaves. A conciliação mantém a pendência até confirmação positiva. A recuperação também preserva o registro diante de falha de escrita; a confirmação persistida permite repetir apenas a contabilização, se necessário.
- Validação Windows: 1.931 testes aprovados, nenhum reprovado e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX); 81 testes direcionados aprovados. Ruff e `git diff --check` aprovados.
- Permanecem pendentes a identificação nativa de recusa definitiva, a comprovação do débito exato em extrato e a homologação autenticada das rotas estacionadas e com escala. A taxa registrada é a cotação, não um débito conciliado em extrato. Nenhuma transação real no jogo foi executada. O objetivo integral permanece ativo.

## 2026-11-24 — Autonomia Total A3/A5, confirmação independente e validade do saldo (G0)

- A leitura do saldo exige um valor monetário inteiro completo e não negativo. Gastos com valores inválidos são recusados. A atualização estimada do caixa após despesa e uma tentativa de sincronização sem leitura válida revogam a data de confirmação do saldo em memória.
- A criação de rotas diretas e com escala verifica novamente a cotação e o saldo imediatamente antes do envio. A confirmação de criação consulta os detalhes da própria aeronave e exige a rota correspondente ativa, incluindo a escala prevista quando aplicável. A resposta visual de sucesso ou uma queda isolada do saldo não basta para contabilizar a rota direta.
- Validação Windows: 1.924 testes aprovados, nenhum reprovado e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX); 70 testes direcionados aprovados. Ruff e `git diff --check` aprovados.
- Permanecem pendentes a homologação autenticada do formulário estacionado e da identificação de escala nos detalhes, a conciliação persistente de criação incerta após timeout/reinício e a revisão do fallback de amostras históricas do caixa no painel de investimentos. Nenhuma mutação real no jogo foi realizada. O objetivo integral e G0 permanecem ativos.

## 2026-11-24 — Autonomia Total A3/A5, pré-checagem da criação de rotas (G0)

- A criação de rota direta de aeronave estacionada reutiliza o contrato estrutural do formulário de redirecionamento para verificar vínculo com a aeronave, aeroportos de origem e destino, distância, alcance, ocupação e uma única taxa positiva. A distância deve concordar com a pesquisa em até 5 km. Com duplicidades desativadas, ocupação desconhecida ou diferente de zero impede a criação; a política é propagada ao formulário final.
- Os valores monetários e contagens do formulário de rota direta e com escala exigem números inteiros completos. Texto misturado, sinais negativos, decimais e agrupamento inválido são rejeitados. A rota direta revalida a cotação, a ocupação, os aeroportos e o saldo disponível imediatamente antes de submeter; divergências interrompem a ação. Quando o formulário inicial não confirma a rota, o ciclo pode testar outra candidata.
- Validação Windows: 1.906 testes aprovados, nenhum reprovado e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX); 49 testes direcionados aprovados. Ruff nos arquivos modificados e `git diff --check` aprovados.
- A validação reutiliza o contrato do redirecionamento e ainda requer homologação autenticada específica do formulário de aeronave estacionada. A frota observada anteriormente não possuía aeronaves estacionadas; nenhuma compra, criação ou alteração de rota foi executada para obter o formulário. A taxa de uma rota candidata para aeronave ainda não adquirida permanece desconhecida; o subtotal indicativo não passa a ser elegível para compra. G0 e o objetivo integral permanecem ativos.

## 2026-11-24 — Autonomia Total A3/A4/A7, composição indicativa do investimento (G0)

- A fila de pesquisa de hubs próprios e externos apresenta o preço exibido da variante identificada ou, na sua ausência, o preço indicativo do catálogo do modelo. Para uma única aeronave, utiliza a disponibilidade atual do hangar de passageiros ou a cotação exibida para ampliar uma vaga. Hubs externos acrescentam o preço monetário observado do hub quando disponível.
- O subtotal só é apresentado quando todos esses componentes estão disponíveis e identifica a ausência da taxa de rota. Evidências de hangar ausentes, inválidas, futuras ou com mais de 900 segundos deixam o componente desconhecido. A expiração das cotações é considerada também no painel PT/EN e a alteração da observação de hangar invalida o cursor de pesquisa interativa.
- O subtotal é indicativo, condicionado à disponibilidade de uma vaga no momento da pesquisa, e não certifica preço final, saldo após compromissos, taxa de rota, elegibilidade, ROI ou payback. A taxa de rota continua pendente de uma leitura nativa correlacionada à combinação candidata. Nenhuma transação foi realizada.
- Validação Windows: 1.888 testes aprovados e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX); 229 testes direcionados aprovados. Ruff e `git diff --check` aprovados. G0 e o objetivo de autonomia total permanecem ativos.

## 2026-11-24 — Autonomia Total A9/A7, histórico financeiro correlacionado à rota (G0)

- A leitura financeira passou a exigir inventário recente, identidade da aeronave, identificador de rota e aeroportos observados no jogo. Registros de outras rotas são excluídos da amostra de 24 horas, inclusive após trocas de rota. A leitura inválida revoga a amostra anterior; caches legados sem correlação não aparecem como evidência financeira da rota atual.
- A amostra conserva receita observada, consumo de combustível e CO₂, preços usados e margem operacional estimada. O painel PT/EN identifica a soma como amostra parcial de registros, sem presumir cobertura integral, identificadores únicos de voo ou custos contábeis efetivamente incorridos. A calibração conclusiva continua dependente de histórico completo e independente, entregas e custos reais conciliados.
- Validação Windows: 1.878 testes aprovados, nenhum reprovado e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX). 122 testes direcionados aprovados. Ruff e `git diff --check` aprovados.
- A leitura autenticada integrada e a comprovação de demanda residual, despesas reais e histórico integral permanecem pendentes. Nenhuma transação no jogo foi realizada. G0 permanece ativo.

## 2026-11-24 — Autonomia Total A2/A3/A4, conciliação de ocupação da frota (G0)

- A auditoria de ocupação utilizada pela pesquisa de hubs próprios, externos e pelo ranking de aeronaves passou a exigir a conciliação de identidades das aeronaves pendentes e estacionadas quando elas existem. Contagens coincidentes, evidências incompletas ou divergentes preservam os vínculos de rota comprovados, mas não certificam ausência de aeronaves em outras rotas. Uma auditoria integral com todas as aeronaves em rota continua suficiente para a contagem própria quando não há evidência nativa contraditória.
- A validação da conciliação exige o identificador da observação nativa vinculada à auditoria. A regra mantém a ocupação como evidência independente da demanda residual e bloqueia recomendações quando a cobertura permanece parcial.
- Validação Windows: 1.876 testes aprovados e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX). 243 testes direcionados aprovados, incluindo a integração com o ranking, divergências de identidade, evidência ausente e compatibilidade com auditorias sem aeronaves fora de rota. Ruff e `git diff --check` aprovados.
- Permanecem pendentes a comprovação nativa de demanda residual, os custos finais e a homologação autenticada da coleta integral. Nenhuma transação real foi executada. G0 continua ativo.

## 2026-11-24 — Autonomia Total A3/A7, projeção exploratória de rotas com escala (G0)

- A pesquisa de hubs próprios e externos passou a calcular cenários econômicos com uma escala somente quando os dois trechos e as três pistas estão correlacionados à variante do motor e à amostra da rota. O cálculo utiliza a distância total percorrida para combustível, CO₂ e frequência, adiciona uma parada segundo a hipótese existente de tempo em solo e conserva a distância direta como referência para as tarifas estimadas. As tarifas, as regras nativas e os encargos específicos da escala ainda dependem de confirmação. O cenário permanece inelegível para compra.
- A simulação base e o stress preservam a mesma configuração de assentos, a margem de segurança e os bloqueios por ocupação observada, demanda temporária e evidência conflitante. A validade é limitada também pela expiração da observação da escala. O painel PT/EN identifica o cenário exploratório e as distâncias utilizadas para custo e tarifa.
- Validação Windows: 1.868 testes aprovados e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX). 175 testes direcionados aprovados, incluindo alcance por trecho, pista de escala insuficiente, motor divergente, ocupação, eventos, expiração e cálculos de custos. Ruff e `git diff --check` aprovados.
- Permanecem pendentes a homologação autenticada de escala, a demanda residual, os custos completos por rota, os compromissos financeiros e a cobertura integral do portfólio. Nenhuma transação real foi executada. G0 continua ativo.

## 2026-11-24 — Autonomia Total A3/A7, dimensões específicas por variante (G0)

- A fila de pesquisa dos hubs próprios e externos passou a priorizar o alcance observado no detalhe correlacionado do motor. Uma variante com alcance inferior ao trecho direto exige pesquisa de escala mesmo que o alcance genérico do modelo seja suficiente. A projeção direta também considera a capacidade observada da variante e pode utilizar o detalhe válido quando o catálogo genérico está incompleto. Na ausência do detalhe, o catálogo continua como hipótese de simulação identificada; a triagem física mantém as dimensões não confirmadas.
- A projeção econômica e a classificação de alcance compartilham o resultado da triagem física. A simulação é bloqueada diante de alcance ou pista insuficientes e o painel PT/EN informa o alcance, a capacidade e a origem de cada valor utilizado no cálculo. O cenário de escala permanece exploratório, sem estimativa financeira certificada. As expirações de demanda, detalhe da variante, rota, mercado, modo e ocupação continuam aplicáveis.
- Validação Windows: 1.856 testes aprovados e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX). 133 testes direcionados aprovados, incluindo fronteiras de alcance, variantes com capacidade distinta, divergência em relação ao catálogo e apresentação no painel. Ruff, compilação Python e `git diff --check` aprovados.
- Permanecem pendentes as regras autenticadas de escala, demanda residual, horários/rotação, encargos completos, compromissos financeiros e homologação integrada. Nenhuma alteração real foi executada no jogo. G0 continua ativo.

## 2026-11-24 — Autonomia Total A4/A9, histórico financeiro e impedimentos no Telegram (G0)

- A inspeção autenticada e somente leitura de Finances > History encontrou uma tabela de 30 registros recentes, com três colunas (tempo relativo, descrição e valor), sem links de detalhe ou identificador de encomenda nas linhas. A consulta mostrou despesas de cotas de CO₂ e A-check, além de receitas de voos. Não foi possível comprovar conciliação individual das encomendas, saldo futuro a pagar ou cobertura de todas as obrigações por essa tela. A seleção de Expenses não apresentou uma lista separada confirmável nessa inspeção. A tela de rotas foi restaurada. Nenhuma transação do jogo foi executada.
- O resumo diário optativo de investimentos passou a incluir receitas, despesas, resultado e despesas históricas com encomendas de aeronaves e hubs, a partir do resumo nativo validado das últimas 24 horas. A informação é omitida quando a evidência está expirada ou em simulação. Os valores agregados não certificam pagamentos individuais, compromissos futuros ou lucro de uma rota.
- As métricas agora preservam os códigos de impedimento do comparador global, deduplicados. O Telegram traduz os impedimentos conhecidos, incluindo falta de vaga no hangar, divergências da frota, pedidos a conciliar e evidências de ranking pendentes. Códigos futuros desconhecidos são contabilizados sem reproduzir texto arbitrário na mensagem. O relatório continua separado do executor de compras.
- Validação Windows: 1.854 testes aprovados e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX). 32 testes direcionados aprovados, incluindo a expiração financeira, simulação e motivos do planejador. Ruff, compilação Python e `git diff --check` aprovados. O envio real do Telegram não foi acionado durante os testes.
- Permanecem pendentes a fonte financeira de compromissos incrementais, a coleta autenticada integrada, a economia completa por rota e motor e as demais fases do roadmap. G0 continua ativo.

## 2026-11-24 — Autonomia Total A4/A7, conciliação de identidades da frota (G0)

- A consulta autenticada e somente leitura do inventário por modelo encontrou 223 aeronaves distintas (120, 37 e 66 nas três listas) e os sete identificadores observados em Pending coincidiram com os identificadores dos controles nativos de detalhe do inventário (duas entregas e cinco manutenções). Nenhum identificador individual foi registrado neste documento.
- A coleta estável de Pending e Parked conserva os identificadores somente em memória até a confirmação final do inventário e da auditoria de rotas. A confirmação exige que os dois conjuntos sejam disjuntos, tenham os tamanhos esperados e formem exatamente o complemento das aeronaves com rota auditada. A prova fica vinculada à observação nativa por um identificador aleatório de coleta e ao inventário certificado no mesmo ciclo, dentro da janela temporal de 120 segundos. Somente o resultado agregado e o identificador da coleta são persistidos adicionalmente.
- A API e o painel PT/EN distinguem identidades conciliadas, divergentes e a confirmar, inclusive quando as contagens coincidem. O comparador global bloqueia a decisão sem a conciliação de identidade, e caches anteriores continuam disponíveis como observações de contagem sem fabricar uma prova de identidade. O conjunto de pendências não representa valores a pagar ou a identificação financeira de uma encomenda.
- Validação Windows: 1.851 testes aprovados e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX). 129 testes direcionados aprovados, incluindo divergências com o mesmo total, observações distintas, privacidade e interface. Ruff, compilação Python e `git diff --check` aprovados.
- A execução integrada do coletor Selenium e a partição completa entre rotas, estacionadas e pendências ainda requerem homologação autenticada. Na consulta ao jogo a lista de estacionadas tinha zero aeronaves. Compromissos financeiros, demanda residual, custos finais e cobertura dos hubs continuam pendentes. Nenhuma compra ou alteração real foi executada no jogo. G0 continua ativo.

## 2026-11-24 — Autonomia Total A4, revogação de observações após mutações (G0)

- A revogação da cobertura integral do inventário agora invalida também o cache nativo de hangar, aeronaves estacionadas e pendentes do mesmo perfil. O início de uma nova auditoria de planejamento, criação ou substituição de rota e encomenda de aeronave deixam de publicar a observação anterior como atual, mesmo quando a tentativa de alteração termina sem confirmação do jogo.
- Reparo, A-check, ampliação de hangar e alterações na oficina passaram a revogar as duas evidências imediatamente antes do envio da ação. A simulação e as verificações que antecedem a ação preservam o cache. A atualização é atômica e a revogação não alcança outros perfis. A decisão de invalidar também a cobertura de rotas nas operações de manutenção é conservadora, pois o estado da frota pode mudar durante a parada.
- Validação Windows: 1.846 testes aprovados e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX), antes da inclusão da oficina. Após a inclusão, 99 testes direcionados aprovados, inclusive revogação por perfil, timeout e simulação. O teste inicial de oficina foi corrigido para respeitar o ganho mínimo exigido pela rotina. Ruff, compilação Python e `git diff --check` aprovados.
- A conciliação monetária dos pedidos, a cobertura integral de hubs/rotas e a homologação autenticada do ciclo permanecem pendentes. G0 continua ativo. Nenhuma ação real foi executada no jogo nesta entrega.

## 2026-11-24 — Autonomia Total A4/A7, entregas de aeronaves pendentes (G0)

- A inspeção autenticada da aba Pending mostrou seis aeronaves, sendo duas com o rótulo nativo `Pending delivery:` e quatro com `Pending maintenance:`. Ambos os estados aparecem em células próprias com contador regressivo. O menu Order exibiu catálogo e capacidade, sem uma relação financeira das encomendas. A inspeção foi somente leitura.
- O coletor passou a reconhecer os dois estados pelo rótulo explícito da célula de status e pelo marcador de contador regressivo. Rótulos ausentes, desconhecidos ou conflitantes permanecem sem classificação. A leitura estável, a validação de totais, a expiração e a privacidade das contagens permanecem aplicáveis. Caches anteriores são compatíveis e não produzem uma contagem de entrega artificialmente igual a zero.
- O painel PT/EN e a API exibem separadamente aeronaves aguardando entrega, manutenção e estados sem classificação. A conciliação de contagens aceita o novo formato e conserva o bloqueio financeiro. A lista de entregas em trânsito não prova o valor a pagar, a origem do pedido, a cobertura de outras obrigações ou a identidade individual conciliada com o diário. A integração Selenium ainda precisa de homologação autenticada; G0 permanece ativo.
- Validação Windows: 1.839 testes aprovados e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX); 96 testes direcionados aprovados, incluindo contrato JavaScript, classificação conflitante, compatibilidade de cache e painel em inglês. O teste inicial do painel revelou uma tradução ausente na fixture e foi corrigido. Ruff, compilação Python e `git diff --check` aprovados.

## 2026-11-24 — Autonomia Total A4, conciliação dentro do ciclo de auditoria (G0)

- A coleta nativa de hangar, aeronaves estacionadas e pendentes passou a ocorrer imediatamente após a auditoria paginada e antes da conferência final do inventário, das correções de rota e das compras nessa etapa. A tela de rotas é restaurada antes da leitura final, e a coleta continua restrita à opção de planejamento habilitada.
- O cache registra o início e o fim da coleta. Para auditorias extensas, permite conciliar observações feitas integralmente entre as duas conferências consistentes do inventário, desde que o início da coleta esteja a até 120 segundos da confirmação final. A validade de 15 minutos continua aplicável às duas fontes; caches antigos conservam o critério temporal anterior. Intervalos inválidos, fontes divergentes ou dados expirados não certificam as contagens.
- O resultado permanece agregado e não confirma identidades individuais, pedidos de entrega, obrigações financeiras ou vínculo permanente ao hub. A restauração da tela e os tempos reais ainda dependem de homologação autenticada; mutações posteriores de rota ou compra invalidam a cobertura existente. G0 permanece ativo.
- Validação Windows: 1.839 testes aprovados e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX); 99 testes direcionados aprovados, incluindo ordenação das leituras no ciclo, restauração da tela, auditoria longa e intervalos inválidos. Ruff, compilação Python e `git diff --check` aprovados.

## 2026-11-24 — Autonomia Total A4/A7, conciliação das contagens da frota (G0)

- O inventário cruza as contagens nativas das listas de aeronaves estacionadas e pendentes com as contagens da auditoria integral de rotas e do inventário de aeronaves. Exige evidências atuais (até 15 minutos) e proximidade temporal de até 120 segundos entre a observação nativa, o início do inventário e a conclusão da auditoria. Registra coincidência, divergência, observações em horários distintos, fonte única ou cobertura parcial, sem persistir identificadores adicionais.
- A comparação global bloqueia a conclusão quando existe aeronave estacionada a resolver, contagem divergente ou ausência de conciliação válida. Uma contagem positiva de qualquer fonte atual mantém o bloqueio. O painel PT/EN apresenta o resultado e as contagens da auditoria junto às nativas. A soma de estacionadas e pendentes não representa encomendas nem prova identidade individual, vínculo permanente ao hub ou compromissos financeiros; estes continuam pendentes.
- A janela de 120 segundos é conservadora e poderá limitar a conciliação em ciclos extensos. A coleta nativa atualmente ocorre depois das demais etapas operacionais, portanto a coincidência temporal precisa de homologação autenticada e poderá exigir aproximação das coletas no ciclo. G0 permanece ativo, sem aquisição real.
- Validação Windows: 1.838 testes aprovados e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX). O teste inicial da interface falhou por retenção de dados no cenário sintético e foi corrigido antes da suíte final. Ruff, compilação Python e `git diff --check` aprovados.

## 2026-11-24 — Autonomia Total A4/A7, limites de investimento e aquisições em 24 horas (G0)

- O diário de investimentos passou a retornar, em uma única consulta isolada por perfil, as reservas atuais e as intenções confirmadas nas últimas 24 horas. Os estados APPROVED, PRECHECKED, SUBMITTED e UNKNOWN mantêm a reserva mesmo quando anteriores à janela. As confirmações são contabilizadas uma única vez, seguindo a mesma regra dos executores.
- A comparação global aplica os limites configurados de gasto e quantidade de aquisições antes do ranking, preservando a restrição independente de caixa e reserva. O painel PT/EN apresenta os limites restantes e indica quando o diário não fornece dados válidos. Foram traduzidos também os novos motivos de exclusão e bloqueio.
- O uso da janela é uma estimativa do diário local, sem equivalência com o gasto real da companhia. Compromissos externos ao diário, aeronaves sem rota, cobertura integral e homologação do executor continuam pendentes. A política permanece no gate G0, sem execução real.
- Validação Windows: 1.830 testes aprovados e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX). Quatro testes direcionados aprovados após correção da importação de `time` e da cobertura de traduções do teste de interface. Ruff, compilação Python e `git diff --check` aprovados.

## 2026-11-24 — Autonomia Total A4/A9, resumo financeiro observado de 24 horas (G0)

- A inspeção autenticada do resumo nativo de transações confirmou o período explícito de 24 horas e nove indicadores monetários: despesas, receitas, resultado, combustível, cotas, taxas de rota, encomendas de aeronaves, hubs e passagens. A leitura agregada observada apresentou consistência entre receitas, despesas e resultado. O histórico individual exibido tem cobertura limitada e não comprova a razão financeira completa.
- O ciclo de planejamento ganhou coleta somente leitura, com dupla leitura estável, janela de 120 segundos, validação de rótulos, valores inteiros, consistência contábil e revogação do cache por perfil antes da atualização. A evidência expira em 15 minutos. Apenas agregados são persistidos, sem nome da conta ou identificadores privados.
- As recomendações e as métricas A9 expõem o resumo histórico, com isolamento da simulação e apresentação PT/EN. A classificação das pendências da frota foi corrigida no painel e nos logs. Os agregados não comprovam compromissos futuros, entrega de encomendas, gasto por plano ou lucro incremental por aeronave. A calibração continua pendente, G0 permanece ativo e a integração Selenium ainda requer homologação autenticada. Nenhuma aquisição foi acionada.
- Validação Windows: 51 testes direcionados aprovados, incluindo contrato JavaScript sintético, valores negativos, consistência, expiração, isolamento e revogação. Ruff, compilação Python e `git diff --check` aprovados.

## 2026-11-24 — Autonomia Total A4/A7, cotação e prazo de ampliação do hangar (G0)

- A inspeção autenticada anterior do hangar PAX cheio (223/223) mostrou duas opções nativas habilitadas: ampliação de uma vaga por US$ 190.835.956 com prazo exibido de 00:18:00 e dez vagas por US$ 1.908.359.562 com prazo de 02:59:00. Nenhuma opção foi acionada.
- O coletor passou a registrar as cotações exibidas na mesma leitura estável da capacidade. Valida a ação nativa, quantidade, visibilidade, habilitação, ausência de controles duplicados, valor monetário, rótulo e prazo. Uma cotação ausente ou inválida não elimina a leitura independente de capacidade. Os dados seguem a revogação e expiração de 15 minutos por perfil; caches anteriores continuam compatíveis.
- O planejador expõe o custo exibido de ampliação quando não há vagas, confrontando cada opção separadamente com o caixa reconciliado (quando disponível) e o teto de caixa após reservas locais. O painel PT/EN exibe valores e prazos. A cotação não é contabilizada novamente sobre o investimento dos candidatos, que já pode incluir custo de hangar. Preço final, compromissos efetivos, disponibilidade após conclusão e viabilidade do investimento completo continuam pendentes; o bloqueio de hangar cheio permanece até evidência de vagas livres. A integração Selenium ainda requer homologação autenticada.
- Validação Windows: 1.815 testes aprovados e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX); 104 testes direcionados aprovados, incluindo contrato JavaScript, controles inválidos, expiração, compatibilidade de cache, comparação financeira e painel. Ruff, compilação Python e `git diff --check` aprovados.

## 2026-11-24 — Autonomia Total A4/A7, capacidade de hangar e pendências da frota (G0)

- Na navegação autenticada, `hangars.php` exibiu a categoria PAX ativa, capacidade de 223, 223 aeronaves e zero vagas disponíveis. A tela `fleet_pending.php` apresentou 11 linhas únicas, em concordância com o cabeçalho e o contador da aba; todas estavam em manutenção pendente. A tela `fleet_parked.php` apresentou cabeçalho de zero aeronaves e mensagem explícita de lista vazia. A leitura não comprova o número de encomendas em trânsito nem o valor de obrigações futuras. Nenhuma compra, manutenção ou alteração de rota foi acionada.
- O ciclo de planejamento passou a coletar os fragmentos nativos de hangar de passageiros, frota pendente e frota estacionada com dupla leitura estável e janela de até 120 segundos. O contrato valida categoria, rótulos, capacidade, ocupação, vagas, contadores independentes, quantidade de linhas, identidades únicas e estado explícito de lista vazia. Pendências de manutenção são classificadas separadamente; estados diferentes ficam sem classificação. O registro por perfil guarda exclusivamente contagens, revoga a coleta anterior antes de nova tentativa e expira em 15 minutos.
- As APIs `/api/hubs` e `/api/hubs/recommendations` expõem essas observações e o painel PT/EN mostra vagas livres, pendências por classificação e aeronaves estacionadas. O planejador de comparação sinaliza falta de vagas ou ausência de leitura de hangar. O ranking exploratório permanece disponível para análise; a decisão financeira continua inconclusiva até comprovação independente dos pedidos, compromissos, custo de expansão de hangar e demais controles A4. A execução planejada continua em G0 e a coleta Selenium integrada ainda requer homologação.
- Validação Windows: 1.813 testes aprovados e 1 ignorado na suíte ampla (excluído `tests/test_instalacao_linux.py`, requisito POSIX); 114 testes direcionados aprovados. Ruff, compilação Python e `git diff --check` aprovados.

## 2026-11-24 — Autonomia Total A1/A2/A7, cobertura do catálogo de encomendas (G0)

- A inspeção autenticada da lista nativa de encomendas encontrou 311 cartões visíveis, com 311 IDs distintos, nomes distintos e seções consecutivas. Os 311 manipuladores de detalhe apontavam para `ac_orders.php?mode=detail` com `charter=0`. A lista permaneceu com o mesmo conjunto de identidades após acionar a ordenação por preço. Não foi efetuada nenhuma encomenda.
- O coletor registra o conjunto exato por perfil mediante dupla leitura estável, com validação das seções, IDs, nomes, visibilidade e ausência de carregamento. A evidência da lista expira em 15 minutos e é revogada antes de cada nova coleta. Se o contrato da lista não for confirmado, a pesquisa individual pode continuar pela lista visível anterior, mantendo a cobertura inconclusiva.
- A API `/api/hubs/recommendations` e o painel PT/EN agora exibem a quantidade de modelos com identidade de detalhe confirmada, os modelos com observações de todas as variantes disponíveis e a quantidade de variantes observadas entre as identificadas. Tentativas posteriores inconclusivas retiram o modelo da contagem verificada, mesmo quando sua última leitura válida é preservada para consulta. A cobertura da lista não comprova outros catálogos, todos os campos de cada variante, preços finais, disponibilidade de entrega ou viabilidade econômica. O planejamento global continua parcial e G0 permanece ativo.
- Validação Windows: 346 testes direcionados aprovados, incluindo contrato DOM sintético, lista inválida, identidade divergente, expiração, revogação, variantes e painel. Ruff, compilação Python e `git diff --check` aprovados. Ainda falta homologar o coletor Selenium integrado na sessão autenticada e pesquisar os demais modelos e preços finais.

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
