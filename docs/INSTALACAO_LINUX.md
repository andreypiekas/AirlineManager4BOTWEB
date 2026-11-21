# Instalação fácil no Raspberry Pi OS e Ubuntu

Instalador destinado a **Raspberry Pi OS (Debian Bookworm/Trixie)** e **Ubuntu 22.04+**. O programa roda em segundo plano, com painel web e serviço `systemd`, sem interface gráfica local. Recomendamos **Raspberry Pi OS 64 bits** nos Raspberry Pi 3/4/5.

## Instalação pelo terminal

No terminal do servidor, execute como usuário normal com acesso a `sudo`:

```bash
curl -fsSLo instalar-am4.sh https://raw.githubusercontent.com/andreypiekas/AirlineManager4BOTWEB/main/instalar.sh && bash instalar-am4.sh --rede-local
```

O instalador baixa o projeto em `~/AirlineManager4Bot`, instala Python e Chromium, cria o ambiente `.venv` e configura o painel como serviço do sistema. Se você já tem um clone do projeto, execute `bash instalar.sh --rede-local` de dentro dele.

### Login e primeiro acesso

O instalador pede o login do jogo caso esteja pendente. A senha fica oculta. Pressione **Enter** no campo de e-mail para pular e abrir apenas o painel. Para uma instalação sem perguntas de login, use `--sem-login`.

Ao final, abra o endereço completo exibido no terminal. Com `--rede-local`, ele vem com um token para acesso na mesma rede, como `http://192.168.1.50:8744/?token=TOKEN_GERADO`. Guarde o link com o token em local privado. Sem `--rede-local`, o endereço padrão é `http://127.0.0.1:8744/` no servidor, acessível também por túnel SSH.

Se você pulou o login, adicione-o depois na pasta do projeto:

```bash
.venv/bin/python scripts/configurar_linux.py --configurar-login
sudo systemctl restart am4bot@principal
```

Use `--perfil NOME` no comando de configuração e `am4bot@NOME` no comando do serviço se tiver escolhido outro perfil. As credenciais ficam em `config/secrets.ini` no perfil principal e em `profiles/NOME/secrets.ini` nos demais, com acesso restrito ao usuário do bot.

Perfis novos começam em **Simulação (sem gastos)**. Abra **Parâmetros → Opções** para revisar antes de mudar para operações reais. O painel volta após a reinicialização do servidor e a opção **Iniciar o bot ao abrir** controla se o bot também inicia.

### Firewall UFW no Ubuntu e Debian

Ao usar `--rede-local`, o instalador agora verifica automaticamente se o **UFW está ativo**. Se estiver, identifica a sub-rede da interface de rede do IP do servidor e cria uma regra de entrada **TCP restrita àquela rede**, para a porta real do perfil (por padrão, 8744). Por exemplo, um servidor com `192.168.101.234/24` recebe a regra equivalente a:

```bash
sudo ufw allow from 192.168.101.0/24 to any port 8744 proto tcp
```

Não é necessário executar esse comando manualmente quando a detecção automática funcionar. O instalador **não ativa o UFW**, não abre a porta para `any`/`0.0.0.0/0`, não remove regras já existentes e não modifica o SSH. Reexecutar a instalação mantém as configurações do bot e usa a verificação de regras duplicadas do próprio UFW.

Se o servidor possuir várias interfaces, VPNs ou redes Docker, indique a sub-rede que poderá acessar o painel (deve ser um CIDR IPv4 privado):

```bash
bash instalar.sh --rede-local --ufw-rede 192.168.101.0/24
```

Se preferir administrar o firewall por conta própria, use `--sem-ufw`. Se a detecção de rede falhar, o script **não abre nenhuma porta**: apresenta um aviso e solicita a opção `--ufw-rede`. Consulte:

```bash
sudo ufw status numbered
sudo ss -lntp | grep ':8744'
```

Uma regra antiga que já permita `8744/tcp` a partir de `Anywhere` **continua existindo**, pois o instalador não apaga regras do administrador. Revise e remova regras públicas desnecessárias de forma consciente. Não encaminhe a porta do painel no roteador para a internet.

### Gerenciar o bot

```bash
sudo systemctl status am4bot@principal
sudo systemctl restart am4bot@principal
sudo systemctl stop am4bot@principal
sudo systemctl start am4bot@principal
sudo journalctl -u am4bot@principal -f
```

Para conferir o endereço e o token novamente:

```bash
.venv/bin/python scripts/configurar_linux.py --mostrar-acesso --ip 192.168.1.50
```

### Perfis diferentes

O perfil `principal` usa a porta 8744. O instalador escolhe automaticamente outra porta livre entre os perfis configurados para novos perfis:

```bash
bash instalar.sh --rede-local --perfil companhia2
sudo systemctl status am4bot@companhia2
```

Cada perfil possui seus próprios dados, credenciais, ajustes e sessão Chromium. Não execute o mesmo perfil em dois dispositivos simultaneamente.

### Opções

| Opção | Resultado |
| --- | --- |
| `--rede-local` | Habilita acesso LAN, gera token e ajusta o UFW ativo apenas para a sub-rede detectada |
| `--ufw-rede 192.168.101.0/24` | Define explicitamente a sub-rede privada autorizada no UFW (requer `--rede-local`) |
| `--sem-ufw` | Não altera o UFW, mesmo quando o painel é habilitado na LAN |
| `--configurar-login` | Solicita o login mesmo se ele já estiver configurado |
| `--sem-login` | Pula a configuração de login |
| `--perfil companhia2` | Configura serviço para outro perfil |
| `--sem-iniciar` | Registra e habilita o serviço sem ligá-lo imediatamente |
| `--diretorio /caminho` | Usa um diretório de instalação personalizado, sem espaços |
| `--verificar` | Inspeciona distribuição, arquitetura e executáveis sem instalar |
| `--ajuda` | Exibe ajuda do instalador |

### Atualização e reinstalação

Entre na pasta exibida pelo instalador (normalmente `~/AirlineManager4Bot`) e execute:

```bash
git pull --ff-only && bash instalar.sh
```

Para atualizar a URL de um clone antigo, rode `git remote set-url origin https://github.com/andreypiekas/AirlineManager4BOTWEB.git` nessa mesma pasta. A atualização reaproveita credenciais, preferências e dados do perfil. Use `--perfil NOME` se você estiver atualizando o serviço de um perfil adicional.

### Diagnóstico

- Confirme o sistema: `bash instalar.sh --verificar`.
- Se o painel responder no próprio servidor mas der timeout em outros computadores, confirme `--rede-local`, a porta do perfil e o UFW com `sudo ufw status numbered`. Caso necessário, execute `bash instalar.sh --rede-local --ufw-rede 192.168.101.0/24`, ajustando a faixa à sua rede.
- Confira os eventos: `sudo journalctl -u am4bot@principal -n 100 --no-pager`.
- Se o Chromium ou o ChromeDriver não iniciar, confira `chromium --version` (Raspberry Pi OS) ou `chromium-browser --version` (Ubuntu) e `chromedriver --version`. No Ubuntu, confirme `snap list chromium`.
- No Ubuntu minimal ou contêiner, `snapd` exige serviços do sistema ativos; instalações sem `systemd` não são suportadas.
- Se `.venv/bin/python scripts/configurar_linux.py --configurar-login` mostrar `Não foi possível acessar um terminal interativo`, abra uma sessão com TTY (por exemplo, `ssh -t usuario@servidor`) ou utilize o terminal integrado do servidor. O script lê e-mail pelo terminal e senha com eco desativado; não passe a senha como argumento de linha de comando.
- Caso o ambiente não forneça terminal interativo (contêiner, cron ou SSH sem alocação de TTY), configure as credenciais editando `config/secrets.ini` com uma seção `[login]`, as chaves `username` e `password`; depois execute `chmod 600 config/secrets.ini` e `sudo systemctl restart am4bot@principal`. Preserve todas as outras seções existentes.
- Não atribua permissões globais ao `config/secrets.ini` e não exponha a porta web na internet.
- O instalador é validado com testes de configuração e sintaxe; a navegação real do Selenium precisa ser conferida no dispositivo de destino.

### ChromeDriver encerra inesperadamente (Ubuntu)

Se os registros mostrarem `HTTPConnectionPool(host='localhost', port=...)` com `Connection refused`, o Selenium perdeu a comunicação com o **ChromeDriver local**. A porta aleatória é interna ao Selenium, não é a porta 8744 do painel e não envolve a regra UFW.

Se a reinicialização falhar com `Service /usr/bin/chromedriver unexpectedly exited. Status code was: 1`, possíveis causas incluem Chromium Snap, uma sessão de usuário necessária ao Snap indisponível, incompatibilidade entre navegador/driver ou o encerramento do navegador por falta de memória. O código 1 sozinho não determina a causa.

As notificações de status e erro identificam o servidor, o perfil e o PID da execução que as enviou. Compare essa origem com `hostname` e `systemctl show am4bot@principal -p MainPID` antes de relacionar o alerta ao serviço do painel. O reinício automático do navegador pode ocorrer dentro do mesmo processo Python; confira também os horários no journal, mesmo se o PID não mudou.

Quando o bot seleciona um driver local, inclusive pelo par `AM4_CHROMEDRIVER_BINARY` / `AM4_CHROME_BINARY`, esse caminho tem prioridade sobre `SE_CHROMEDRIVER` herdado pelo processo. O log registra o driver efetivamente selecionado. Sem um par local selecionado, a descoberta normal do Selenium é preservada.

O bot atualizado captura a saída do processo ChromeDriver em **`data/logs/chromedriver.log`**, arquivo com permissões 0600. Em perfis adicionais, usa `profiles/NOME/data/logs/chromedriver.log`. O log pode conter detalhes de navegação: remova dados sensíveis antes de compartilhá-lo.

Comandos para diagnóstico, executados no servidor como usuário da instalação:

~~~bash
cd ~/AirlineManager4Bot
tail -n 80 data/logs/chromedriver.log
chromedriver --version
chromium-browser --version
snap list chromium
sudo systemctl status am4bot@principal --no-pager
sudo journalctl -u am4bot@principal -n 120 --no-pager
free -h
df -h
sudo journalctl -k --since "30 minutes ago" --no-pager | grep -Ei 'oom|out.of.memory|killed process|chrom|snap|apparmor'
~~~

No Ubuntu com Chromium Snap, verifique a disponibilidade do driver sem uma sessão interativa:

~~~bash
USUARIO=$(systemctl show am4bot@principal -p User --value)
sudo -u "$USUARIO" -H chromedriver --version
loginctl show-user "$USUARIO" -p Linger
~~~

Dependendo da configuração do Snap e do gerenciador de sessão, pode ser necessário habilitar o **linger** para o usuário do serviço, mas apenas se a investigação comprovar que essa é a causa. Não apague a sessão persistente do Chrome nem encerre todos os processos Chrome do servidor indiscriminadamente.

### Referências

- [Raspberry Pi OS: Python e ambientes virtuais](https://www.raspberrypi.com/documentation/computers/os.html)
- [Ubuntu: pacote Chromium distribuído por Snap](https://ubuntu.com/blog/chromium-in-ubuntu-deb-to-snap-transition)
