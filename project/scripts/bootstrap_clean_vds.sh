#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<USAGE
Usage:
  bootstrap_clean_vds.sh --domain <fqdn> [options]

Required:
  --domain <fqdn>               Main domain for BASE_URL and links (example: vpn.example.com)

Options:
  --repo-dir <path>             Project repo dir on server (default: /opt/vpn_vds)
  --install-deps                Install required packages via apt (docker, compose, python3, etc.)
  --bot-token <token>           Telegram bot token (if omitted, __SET_ME__ is kept)
  --admin-id <id>               PRIMARY_ADMIN_TG_ID (default: 227380225)
  --admin-ids <csv>             ADMIN_TG_IDS (default: same as admin-id)
  --admin-usernames <csv>       ADMIN_TG_USERNAMES (default: serg_hexen)
  --support-text <text>         SUPPORT_TEXT (default: Поддержка: @serghexen)
  --support-url <url>           SUPPORT_CHAT_URL (default: https://t.me/serghexen)
  --email <name>                Initial xray client email (default: bootstrap_admin)
  --start                       Start containers after bootstrap
  -h, --help                    Show help

What this script does:
  1) Creates required host directories
  2) Creates /var/lib/vless-sub/clients.json if missing
  3) Generates REALITY keys + UUID + shortId
  4) Renders /usr/local/etc/xray/config.json from project/xray/config.template.json
  5) Creates/updates project/env/bot.env from bot.env.example
  6) Creates/updates project/env/nodes.env from nodes.env.example
  7) Validates xray config in official xray container
  8) Optionally starts docker compose stack (master-full)
USAGE
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Run as root (sudo -i)." >&2
    exit 1
  fi
}

install_deps() {
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "apt-get not found. Automatic dependency install supports Debian/Ubuntu only." >&2
    exit 1
  fi
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y \
    ca-certificates \
    curl \
    git \
    python3 \
    docker.io \
    docker-compose-v2
  systemctl enable --now docker
}

DOMAIN=""
REPO_DIR="/opt/vpn_vds"
BOT_TOKEN=""
ADMIN_ID="227380225"
ADMIN_IDS=""
ADMIN_USERNAMES="serg_hexen"
SUPPORT_TEXT="Поддержка: @serghexen"
SUPPORT_URL="https://t.me/serghexen"
INITIAL_EMAIL="bootstrap_admin"
DO_START=0
INSTALL_DEPS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)
      DOMAIN="${2:-}"; shift 2 ;;
    --repo-dir)
      REPO_DIR="${2:-}"; shift 2 ;;
    --bot-token)
      BOT_TOKEN="${2:-}"; shift 2 ;;
    --admin-id)
      ADMIN_ID="${2:-}"; shift 2 ;;
    --admin-ids)
      ADMIN_IDS="${2:-}"; shift 2 ;;
    --admin-usernames)
      ADMIN_USERNAMES="${2:-}"; shift 2 ;;
    --support-text)
      SUPPORT_TEXT="${2:-}"; shift 2 ;;
    --support-url)
      SUPPORT_URL="${2:-}"; shift 2 ;;
    --email)
      INITIAL_EMAIL="${2:-}"; shift 2 ;;
    --start)
      DO_START=1; shift ;;
    --install-deps)
      INSTALL_DEPS=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1 ;;
  esac
done

if [[ -z "$DOMAIN" ]]; then
  echo "--domain is required" >&2
  usage
  exit 1
fi

require_root

if [[ -z "$ADMIN_IDS" ]]; then
  ADMIN_IDS="$ADMIN_ID"
fi

if [[ "$INSTALL_DEPS" == "1" ]]; then
  install_deps
fi

require_cmd docker
require_cmd python3

if [[ ! -d "$REPO_DIR" ]]; then
  echo "Repo dir does not exist: $REPO_DIR" >&2
  exit 1
fi

TEMPLATE_XRAY="$REPO_DIR/project/xray/config.template.json"
BOT_ENV_EXAMPLE="$REPO_DIR/project/env/bot.env.example"
BOT_ENV="$REPO_DIR/project/env/bot.env"
NODES_ENV_EXAMPLE="$REPO_DIR/project/env/nodes.env.example"
NODES_ENV="$REPO_DIR/project/env/nodes.env"
COMPOSE_FILE="$REPO_DIR/project/docker-compose.master-full.yml"

[[ -f "$TEMPLATE_XRAY" ]] || { echo "Missing template: $TEMPLATE_XRAY" >&2; exit 1; }
[[ -f "$BOT_ENV_EXAMPLE" ]] || { echo "Missing env example: $BOT_ENV_EXAMPLE" >&2; exit 1; }
[[ -f "$NODES_ENV_EXAMPLE" ]] || { echo "Missing env example: $NODES_ENV_EXAMPLE" >&2; exit 1; }
[[ -f "$COMPOSE_FILE" ]] || { echo "Missing compose file: $COMPOSE_FILE" >&2; exit 1; }

mkdir -p \
  /usr/local/etc/xray \
  /var/lib/hexenvpn-bot \
  /var/lib/vless-sub \
  /var/www/sub \
  /var/backups/vless \
  /var/lock

if [[ ! -f /var/lib/vless-sub/clients.json ]]; then
  echo "[]" > /var/lib/vless-sub/clients.json
fi

X25519_OUT="$(docker run --rm ghcr.io/xtls/xray-core:latest x25519)"
REALITY_PRIVATE_KEY="$(printf '%s\n' "$X25519_OUT" | awk -F': ' '/Private key/ {print $2}' | tail -n1)"
REALITY_PUBLIC_KEY="$(printf '%s\n' "$X25519_OUT" | awk -F': ' '/Public key/ {print $2}' | tail -n1)"

if [[ -z "$REALITY_PRIVATE_KEY" || -z "$REALITY_PUBLIC_KEY" ]]; then
  echo "Failed to parse REALITY keys from xray output" >&2
  echo "$X25519_OUT" >&2
  exit 1
fi

UUID="$(python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
)"

SHORT_ID="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(5))
PY
)"

export TEMPLATE_XRAY REALITY_PRIVATE_KEY UUID INITIAL_EMAIL SHORT_ID
python3 - <<'PY'
import json, os
from pathlib import Path

src = Path(os.environ['TEMPLATE_XRAY'])
out = Path('/usr/local/etc/xray/config.json')
obj = json.loads(src.read_text(encoding='utf-8'))

for ib in obj.get('inbounds', []):
    if ib.get('protocol') != 'vless':
        continue
    ib.setdefault('settings', {})['clients'] = [{
        'id': os.environ['UUID'],
        'flow': 'xtls-rprx-vision',
        'email': os.environ['INITIAL_EMAIL'],
    }]
    rs = ib.get('streamSettings', {}).get('realitySettings', {})
    rs['privateKey'] = os.environ['REALITY_PRIVATE_KEY']
    rs['shortIds'] = [os.environ['SHORT_ID']]

out.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
PY

cp -f "$BOT_ENV_EXAMPLE" "$BOT_ENV"

BASE_URL="https://${DOMAIN}:8443"
export BOT_ENV BOT_TOKEN ADMIN_ID ADMIN_IDS ADMIN_USERNAMES BASE_URL SUPPORT_TEXT SUPPORT_URL
python3 - <<'PY'
import os
from pathlib import Path

p = Path(os.environ['BOT_ENV'])
lines = p.read_text(encoding='utf-8').splitlines()
vals = {
  'BOT_TOKEN': os.environ.get('BOT_TOKEN', '').strip() or '__SET_ME__',
  'PRIMARY_ADMIN_TG_ID': os.environ['ADMIN_ID'],
  'ADMIN_TG_IDS': os.environ['ADMIN_IDS'],
  'ADMIN_TG_USERNAMES': os.environ['ADMIN_USERNAMES'],
  'BASE_URL': os.environ['BASE_URL'],
  'SUPPORT_TEXT': os.environ['SUPPORT_TEXT'],
  'SUPPORT_CHAT_URL': os.environ['SUPPORT_URL'],
}
out = []
seen = set()
for line in lines:
    if '=' not in line:
        out.append(line)
        continue
    k, _ = line.split('=', 1)
    if k in vals:
        out.append(f"{k}={vals[k]}")
        seen.add(k)
    else:
        out.append(line)
for k, v in vals.items():
    if k not in seen:
        out.append(f"{k}={v}")
p.write_text('\n'.join(out) + '\n', encoding='utf-8')
PY

cp -f "$NODES_ENV_EXAMPLE" "$NODES_ENV"
export NODES_ENV DOMAIN REALITY_PUBLIC_KEY
python3 - <<'PY'
import os
from pathlib import Path

p = Path(os.environ['NODES_ENV'])
lines = p.read_text(encoding='utf-8').splitlines()
vals = {
  'MASTER_HOST': os.environ['DOMAIN'],
  'MASTER_PBK': os.environ['REALITY_PUBLIC_KEY'],
}
out = []
seen = set()
for line in lines:
    if '=' not in line:
        out.append(line)
        continue
    k, _ = line.split('=', 1)
    if k in vals:
        out.append(f"{k}={vals[k]}")
        seen.add(k)
    else:
        out.append(line)
for k, v in vals.items():
    if k not in seen:
        out.append(f"{k}={v}")
p.write_text('\n'.join(out) + '\n', encoding='utf-8')
PY

docker run --rm -v /usr/local/etc/xray:/usr/local/etc/xray ghcr.io/xtls/xray-core:latest run -test -config /usr/local/etc/xray/config.json

INFO_FILE="/root/hexenvpn-bootstrap-$(date +%F_%H-%M-%S).txt"
cat > "$INFO_FILE" <<INFO
DOMAIN=$DOMAIN
BASE_URL=$BASE_URL
REALITY_PUBLIC_KEY=$REALITY_PUBLIC_KEY
REALITY_PRIVATE_KEY=$REALITY_PRIVATE_KEY
UUID=$UUID
SHORT_ID=$SHORT_ID
INITIAL_EMAIL=$INITIAL_EMAIL
BOT_ENV=$BOT_ENV
NODES_ENV=$NODES_ENV
XRAY_CONFIG=/usr/local/etc/xray/config.json
COMPOSE_FILE=$COMPOSE_FILE
INFO

echo "Bootstrap complete."
echo "Info saved: $INFO_FILE"
echo "REALITY_PUBLIC_KEY: $REALITY_PUBLIC_KEY"
echo "UUID: $UUID"
echo "SHORT_ID: $SHORT_ID"

echo "Next step:"
echo "  docker compose -f $COMPOSE_FILE up -d"

if [[ "$DO_START" == "1" ]]; then
  cd "$REPO_DIR"
  docker compose -f "$COMPOSE_FILE" up -d
  docker compose -f "$COMPOSE_FILE" ps
fi
