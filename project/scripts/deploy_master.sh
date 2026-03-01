#!/usr/bin/env bash
set -Eeuo pipefail

HOST="${1:-}"
if [[ -z "$HOST" ]]; then
  echo "Usage: $0 <host>"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Expected local inputs:
# - env/bot.env (real token/admin settings)
# - xray/config.json (real production config)
if [[ ! -f "$ROOT_DIR/env/bot.env" ]]; then
  echo "Missing $ROOT_DIR/env/bot.env (copy from env/bot.env.example and fill values)" >&2
  exit 1
fi
if [[ ! -f "$ROOT_DIR/xray/config.json" ]]; then
  echo "Missing $ROOT_DIR/xray/config.json (copy from xray/config.template.json and fill values)" >&2
  exit 1
fi

scp "$ROOT_DIR/bot/bot.py" root@"$HOST":/opt/hexenvpn-bot/bot.py
scp "$ROOT_DIR/env/bot.env" root@"$HOST":/etc/hexenvpn-bot/bot.env
scp "$ROOT_DIR/xray/config.json" root@"$HOST":/usr/local/etc/xray/config.json
scp "$ROOT_DIR/systemd/hexenvpn-bot.service" root@"$HOST":/etc/systemd/system/hexenvpn-bot.service
scp "$ROOT_DIR/systemd/xray.service" root@"$HOST":/etc/systemd/system/xray.service
scp "$ROOT_DIR/systemd/xray.service.override.conf" root@"$HOST":/etc/systemd/system/xray.service.d/10-donot_touch_single_conf.conf
scp "$ROOT_DIR/nginx/nginx.conf" root@"$HOST":/etc/nginx/nginx.conf
scp "$ROOT_DIR/nginx/sub.conf" root@"$HOST":/etc/nginx/sites-available/sub.conf
scp "$ROOT_DIR/nginx/redirect.conf" root@"$HOST":/etc/nginx/sites-available/redirect.conf
ssh root@"$HOST" "mkdir -p /etc/nginx/njs"
scp "$ROOT_DIR/nginx/njs/subscription.js" root@"$HOST":/etc/nginx/njs/subscription.js
scp "$ROOT_DIR/scripts/vless-add-user" root@"$HOST":/usr/local/sbin/vless-add-user
scp "$ROOT_DIR/scripts/vless-del-user" root@"$HOST":/usr/local/sbin/vless-del-user
scp "$ROOT_DIR/scripts/vless-sync-expire" root@"$HOST":/usr/local/sbin/vless-sync-expire

ssh root@"$HOST" "chmod +x /usr/local/sbin/vless-add-user /usr/local/sbin/vless-del-user /usr/local/sbin/vless-sync-expire /opt/hexenvpn-bot/bot.py && /usr/local/bin/xray run -test -config /usr/local/etc/xray/config.json && systemctl daemon-reload && systemctl restart xray hexenvpn-bot nginx && systemctl --no-pager --full status xray hexenvpn-bot nginx | sed -n '1,80p'"
