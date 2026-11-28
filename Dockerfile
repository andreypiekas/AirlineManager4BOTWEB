FROM python:3.13-slim-trixie

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --user-group --uid 10001 am4bot \
    && install -d -m 0700 -o am4bot -g am4bot /app/profiles

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY assets/ assets/
COPY config/defaults.ini config/
COPY scripts/configurar_linux.py scripts/

USER am4bot
EXPOSE 8745
STOPSIGNAL SIGINT

CMD ["/bin/sh", "-ec", "\
    umask 077; \
    python -c \"from pathlib import Path; from scripts.configurar_linux import configurar; configurar(Path.cwd(), 'docker', True, False)\"; \
    exec python src/main.py --web --profile docker"]
