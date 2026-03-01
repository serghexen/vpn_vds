FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client ca-certificates tzdata util-linux \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/hexenvpn-bot
COPY project/docker/bot/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
