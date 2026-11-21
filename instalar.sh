#!/usr/bin/env bash
# Instalação assistida do Airline Manager 4 Bot no Raspberry Pi OS e Ubuntu.
# Execute como usuário normal (com sudo), nunca como root.
set -Eeuo pipefail

REPOSITORIO="https://github.com/andreypiekas/AirlineManager4BOTWEB.git"
PERFIL="principal"
REDE_LOCAL=0
INICIAR=1
LOGIN="auto"
DIRETORIO=""
MODO_VERIFICAR=0
UFW_REDE=""
SEM_UFW=0

avisar() { printf '\n\033[1;36m[AM4]\033[0m %s\n' "$*"; }
erro() { printf '\n[AM4] ERRO: %s\n' "$*" >&2; exit 1; }
on_error() { printf '\n[AM4] Falha na linha %s (código %s). Nenhum dado existente foi apagado.\n' "$1" "$2" >&2; }
trap 'on_error "$LINENO" "$?"' ERR

ajuda() {
    cat <<'TEXTO'
INSTALADOR - Airline Manager 4 Bot (Raspberry Pi OS, Debian e Ubuntu)

Uso: bash instalar.sh [opções]

  --rede-local          Habilita painel na LAN, gera token e ajusta UFW ativo.
  --ufw-rede CIDR       Origem permitida no UFW (ex.: 192.168.101.0/24).
  --sem-ufw             Não altera o UFW (mesmo com --rede-local).
  --perfil NOME         Perfil da companhia (padrão: principal).
  --configurar-login    Solicita e-mail e senha, mesmo se já estiverem gravados.
  --sem-login           Pula a configuração de login.
  --sem-iniciar         Habilita serviço, mas não o inicia agora.
  --diretorio CAMINHO   Local personalizado do projeto.
  --verificar           Verifica sistema sem instalar nada.
  -h, --ajuda           Exibe esta ajuda.

Exemplo: bash instalar.sh --rede-local

Em um terminal interativo, o instalador solicita o login se estiver pendente.
Perfis novos começam em SIMULAÇÃO, sem despesas ou decolagens reais.
Uma segunda execução preserva configurações, credenciais e dados.
TEXTO
}

while (($#)); do
    case "$1" in
        --rede-local) REDE_LOCAL=1 ;;
        --sem-ufw) SEM_UFW=1 ;;
        --ufw-rede)
            shift
            (($#)) || erro "Falta a rede CIDR após --ufw-rede."
            UFW_REDE="$1"
            ;;
        --ufw-rede=*) UFW_REDE="${1#--ufw-rede=}" ;;
        --configurar-login) LOGIN="configurar" ;;
        --sem-login) LOGIN="pular" ;;
        --sem-iniciar) INICIAR=0 ;;
        --verificar) MODO_VERIFICAR=1 ;;
        --perfil|--diretorio)
            OPCAO="$1"
            shift
            (($#)) || erro "Falta o valor de $OPCAO."
            if [[ "$OPCAO" == "--perfil" ]]; then PERFIL="$1"; else DIRETORIO="$1"; fi
            ;;
        -h|--ajuda) ajuda; exit 0 ;;
        *) erro "Opção desconhecida: $1 (use --ajuda)." ;;
    esac
    shift
done

[[ -z "$UFW_REDE" || "$REDE_LOCAL" -eq 1 ]] || erro "--ufw-rede exige --rede-local."
[[ "$SEM_UFW" -eq 0 || -z "$UFW_REDE" ]] || erro "Não combine --sem-ufw e --ufw-rede."

[[ "$(uname -s)" == "Linux" ]] || erro "Este instalador funciona apenas no Linux."
[[ -r /etc/os-release ]] || erro "Não encontrei /etc/os-release."
# shellcheck disable=SC1091
source /etc/os-release
case "${ID:-}" in
    ubuntu) SISTEMA="ubuntu" ;;
    raspbian|debian) SISTEMA="debian" ;;
    *) erro "Distribuição não suportada: ${PRETTY_NAME:-${ID:-desconhecida}}. Use Raspberry Pi OS, Debian ou Ubuntu." ;;
esac
ARQUITETURA="$(uname -m)"
if ((MODO_VERIFICAR)); then
    avisar "Sistema: ${PRETTY_NAME:-$ID}; arquitetura: $ARQUITETURA"
    avisar "Python: $(command -v python3 || printf 'não encontrado')"
    avisar "Chromium: $(command -v chromium || command -v chromium-browser || printf 'não encontrado')"
    avisar "ChromeDriver: $(command -v chromedriver || printf 'não encontrado')"
    exit 0
fi

(( EUID != 0 )) || erro "Execute sem sudo, com seu usuário normal: bash instalar.sh"
command -v sudo >/dev/null || erro "Instale sudo e conceda permissão ao seu usuário."
command -v systemctl >/dev/null && [[ -d /run/systemd/system ]] ||
    erro "O systemd precisa estar em execução. Use instalar.sh --verificar para inspecionar o ambiente."
[[ "$PERFIL" =~ ^[a-z0-9][a-z0-9_-]{0,23}$ ]] || erro "Perfil inválido (a-z, 0-9, _ e -, até 24 caracteres)."
if [[ "$SISTEMA" == "debian" && "$ARQUITETURA" != "aarch64" && "$ARQUITETURA" != "x86_64" ]]; then
    avisar "Aviso: prefira um sistema 64 bits para melhor suporte aos pacotes Python."
fi

ORIGEM_SCRIPT=""
if [[ -f "${BASH_SOURCE[0]:-}" ]]; then
    ORIGEM_SCRIPT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
fi
if [[ -n "$DIRETORIO" ]]; then
    command -v realpath >/dev/null || erro "O comando realpath não está instalado."
    APP_DIR="$(realpath -m -- "$DIRETORIO")"
elif [[ -n "$ORIGEM_SCRIPT" && -f "$ORIGEM_SCRIPT/config/defaults.ini" ]]; then
    APP_DIR="$ORIGEM_SCRIPT"
else
    APP_DIR="$HOME/AirlineManager4Bot"
fi
[[ "$APP_DIR" != *[[:space:]]* && "$APP_DIR" != *%* && "$APP_DIR" != *\"* ]] ||
    erro "Use um caminho sem espaços, '%' ou aspas: $APP_DIR"
[[ "$APP_DIR" == /* && "$APP_DIR" != "/" ]] || erro "Diretório de instalação inválido."
if [[ ! -f "$APP_DIR/config/defaults.ini" && -e "$APP_DIR" && -n "$(ls -A "$APP_DIR" 2>/dev/null)" ]]; then
    erro "Diretório ocupado por outros arquivos: $APP_DIR (não será sobrescrito)."
fi

USUARIO="$(id -un)"
SERVICO="am4bot@${PERFIL}.service"
UNIDADE_INSTALADA="/etc/systemd/system/am4bot@.service"
if [[ -e "$UNIDADE_INSTALADA" ]]; then
    grep -Fxq "WorkingDirectory=$APP_DIR" "$UNIDADE_INSTALADA" &&
        grep -Fxq "User=$USUARIO" "$UNIDADE_INSTALADA" ||
        erro "Já existe um serviço AM4 em outro diretório ou usuário. Consulte: systemctl cat $SERVICO"
fi

avisar "Preparando ${PRETTY_NAME:-$ID} ($ARQUITETURA)."
avisar "Aplicativo: $APP_DIR | Perfil: $PERFIL"
sudo -v
avisar "Instalando dependências do sistema..."
sudo apt-get update
sudo apt-get install -y git ca-certificates curl python3 python3-venv python3-pip python3-tk
if [[ "$SISTEMA" == "ubuntu" ]]; then
    # No Ubuntu os pacotes Chromium/ChromeDriver são wrappers do Snap.
    sudo apt-get install -y snapd chromium-browser chromium-chromedriver
    if ! snap list chromium >/dev/null 2>&1; then sudo snap install chromium; fi
else
    sudo apt-get install -y chromium chromium-driver
fi
command -v chromium >/dev/null || command -v chromium-browser >/dev/null ||
    erro "Chromium não foi localizado após a instalação."
command -v chromedriver >/dev/null || erro "ChromeDriver não foi localizado após a instalação."
python3 -c 'import sys; assert sys.version_info >= (3, 10), "É necessário Python 3.10 ou superior."'

if [[ ! -f "$APP_DIR/config/defaults.ini" ]]; then
    avisar "Baixando o repositório..."
    git clone --depth 1 "$REPOSITORIO" "$APP_DIR"
else
    avisar "Repositório existente detectado; código e arquivos preservados."
fi
cd -- "$APP_DIR"
[[ -f "requirements.txt" && -f "scripts/configurar_linux.py" && -f "scripts/configurar_ufw.py" ]] ||
    erro "O repositório não contém os arquivos necessários do instalador."

avisar "Criando ambiente virtual Python..."
if [[ ! -x ".venv/bin/python" ]]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt

avisar "Configurando o painel e o perfil..."
ARGUMENTOS=(--diretorio "$APP_DIR" --perfil "$PERFIL")
if ((REDE_LOCAL)); then ARGUMENTOS+=(--rede-local); fi
if [[ "$LOGIN" == "configurar" ]]; then
    ARGUMENTOS+=(--configurar-login)
elif [[ "$LOGIN" == "auto" && -t 0 ]]; then
    ARGUMENTOS+=(--login-se-pendente)
fi
.venv/bin/python scripts/configurar_linux.py "${ARGUMENTOS[@]}"

avisar "Registrando serviço systemd..."
if [[ ! -e "$UNIDADE_INSTALADA" ]]; then
    ARQUIVO_UNIDADE="$(mktemp)"
    trap 'rm -f "$ARQUIVO_UNIDADE"' EXIT
    cat > "$ARQUIVO_UNIDADE" <<UNIDADE
[Unit]
Description=Airline Manager 4 Bot (perfil %i)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$USUARIO
WorkingDirectory=$APP_DIR
Environment=PYTHONUTF8=1
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/src/main.py --web --profile %i
KillSignal=SIGINT
TimeoutStopSec=65
Restart=on-failure
RestartSec=20
UMask=0077

[Install]
WantedBy=multi-user.target
UNIDADE
    sudo install -m 0644 "$ARQUIVO_UNIDADE" "$UNIDADE_INSTALADA"
fi
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICO"
if ((INICIAR)); then
    sudo systemctl restart "$SERVICO"
    PYTHONPATH=src .venv/bin/python - "$PERFIL" <<'PYTHON' ||
import sys
import time

import paths
from config import AppConfig
from web import instance_answers

paths.activate(sys.argv[1])
cfg = AppConfig()
host = cfg.get("web", "host") or "127.0.0.1"
if host in ("0.0.0.0", "::") or not cfg.web_token:
    host = "127.0.0.1"
deadline = time.monotonic() + 15
while not instance_answers(cfg.get_int("web", "port", 8744), cfg.web_token, host):
    if time.monotonic() >= deadline:
        sys.exit(1)
    time.sleep(0.5)
PYTHON
        erro "Painel web não respondeu. Consulte: sudo journalctl -u $SERVICO -n 80 --no-pager"
    sudo systemctl is-active --quiet "$SERVICO" ||
        erro "Serviço não iniciou. Consulte: sudo journalctl -u $SERVICO -n 80 --no-pager"
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
IP="${IP:-IP-DA-MAQUINA}"
if ((REDE_LOCAL && ! SEM_UFW)); then
    avisar "Verificando o firewall UFW (sem abrir portas para toda a internet)..."
    ARG_UFW=(--diretorio "$APP_DIR" --perfil "$PERFIL" --ip "$IP")
    if [[ -n "$UFW_REDE" ]]; then ARG_UFW+=(--rede "$UFW_REDE"); fi
    .venv/bin/python scripts/configurar_ufw.py "${ARG_UFW[@]}"
fi
avisar "Instalação finalizada!"
.venv/bin/python scripts/configurar_linux.py --diretorio "$APP_DIR" --perfil "$PERFIL" --mostrar-acesso --ip "$IP"
printf 'Serviço: %s\n' "$SERVICO"
printf 'Pasta:   %s\n' "$APP_DIR"
printf 'Logs:    sudo journalctl -u %s -f\n' "$SERVICO"
printf 'Status:  sudo systemctl status %s\n' "$SERVICO"
if (( ! INICIAR )); then printf 'Iniciar: sudo systemctl start %s\n' "$SERVICO"; fi
printf '\nImportante: perfil novo inicia em SIMULAÇÃO. Desative somente depois de validar os ajustes.\n'
