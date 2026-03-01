#!/usr/bin/env bash
set -Eeuo pipefail

HOST="${1:-}"
PROFILE_DIR="${2:-}"
if [[ -z "$HOST" || -z "$PROFILE_DIR" ]]; then
  echo "Usage: $0 <host> <profile-dir>"
  echo "Example: $0 91.228.10.169 project/replicas/91.228.10.169"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

XRAY_CFG="$PROFILE_DIR/usr/local/etc/xray/config.json"
if [[ ! -f "$XRAY_CFG" ]]; then
  echo "Missing $XRAY_CFG" >&2
  echo "Copy template and set real values first: $PROFILE_DIR/xray.config.template.json" >&2
  exit 1
fi

scp "$XRAY_CFG" root@"$HOST":/usr/local/etc/xray/config.json
scp "$ROOT_DIR/systemd/xray.service" root@"$HOST":/etc/systemd/system/xray.service
scp "$ROOT_DIR/nginx/nginx.conf" root@"$HOST":/etc/nginx/nginx.conf
scp "$ROOT_DIR/nginx/sub.conf" root@"$HOST":/etc/nginx/sites-available/sub.conf
scp "$ROOT_DIR/nginx/redirect.conf" root@"$HOST":/etc/nginx/sites-available/redirect.conf
ssh root@"$HOST" "mkdir -p /etc/nginx/njs"
scp "$ROOT_DIR/nginx/njs/subscription.js" root@"$HOST":/etc/nginx/njs/subscription.js
scp "$ROOT_DIR/scripts/vless-sync-expire" root@"$HOST":/usr/local/sbin/vless-sync-expire

ssh root@"$HOST" "chmod +x /usr/local/sbin/vless-sync-expire && /usr/local/bin/xray run -test -config /usr/local/etc/xray/config.json && systemctl daemon-reload && systemctl restart xray nginx && systemctl --no-pager --full status xray nginx | sed -n '1,80p'"
