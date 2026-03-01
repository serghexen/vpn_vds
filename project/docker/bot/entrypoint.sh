#!/usr/bin/env bash
set -euo pipefail

mkdir -p /var/lib/hexenvpn-bot /var/lib/vless-sub /var/www/sub /var/backups/vless /var/lock

if [[ ! -f /var/lib/vless-sub/clients.json ]]; then
  echo "[]" > /var/lib/vless-sub/clients.json
fi

exec python3 /opt/hexenvpn-bot/bot.py
