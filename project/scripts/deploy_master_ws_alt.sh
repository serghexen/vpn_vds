#!/usr/bin/env bash
set -Eeuo pipefail

STAGING_DIR="${1:-/tmp/ws-alt-deploy}"
REPO_DIR="${REPO_DIR:-/opt/vpn_vds}"
PROJECT_DIR="$REPO_DIR/project"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.master-full.yml"
NODES_ENV="$PROJECT_DIR/env/nodes.env"
BACKUP_DIR="/root/backup-master-ws-alt/$(date +%F_%H-%M-%S)"
CHANGED=0

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi

required=(
  docker-compose.master-full.yml
  sub.conf
  config.template.json
  nodes.env.example
  vless-add-user
  vless-sync-expire
  healthcheck_master_replicas.sh
  bootstrap_clean_vds.sh
  recover_master_from_replica.py
  enable_master_ws_alt.py
  refresh_master_ws_alt.py
)
for name in "${required[@]}"; do
  [[ -f "$STAGING_DIR/$name" ]] || { echo "Missing staging file: $name" >&2; exit 1; }
done

mkdir -p "$BACKUP_DIR/repo/scripts" "$BACKUP_DIR/repo/nginx" "$BACKUP_DIR/repo/xray" "$BACKUP_DIR/repo/env"
chmod 700 "$BACKUP_DIR"
cp -a /usr/local/etc/xray/config.json "$BACKUP_DIR/xray.config.json"
cp -a /etc/nginx/conf.d/sub.conf "$BACKUP_DIR/nginx.sub.conf"
cp -a /var/www/sub "$BACKUP_DIR/sub"
cp -a "$COMPOSE_FILE" "$BACKUP_DIR/repo/docker-compose.master-full.yml"
cp -a "$NODES_ENV" "$BACKUP_DIR/repo/env/nodes.env"
cp -a "$PROJECT_DIR/nginx/sub.conf" "$BACKUP_DIR/repo/nginx/sub.conf"
cp -a "$PROJECT_DIR/xray/config.template.json" "$BACKUP_DIR/repo/xray/config.template.json"
for name in vless-add-user vless-sync-expire healthcheck_master_replicas.sh bootstrap_clean_vds.sh recover_master_from_replica.py; do
  cp -a "$PROJECT_DIR/scripts/$name" "$BACKUP_DIR/repo/scripts/$name"
done

rollback() {
  local rc=$?
  [[ "$CHANGED" -eq 0 ]] && return "$rc"
  echo "[ws-alt] failed rc=$rc, restoring $BACKUP_DIR" >&2
  set +e
  cp -a "$BACKUP_DIR/xray.config.json" /usr/local/etc/xray/config.json
  cp -a "$BACKUP_DIR/nginx.sub.conf" /etc/nginx/conf.d/sub.conf
  cp -a "$BACKUP_DIR/sub/." /var/www/sub/
  cp -a "$BACKUP_DIR/repo/docker-compose.master-full.yml" "$COMPOSE_FILE"
  cp -a "$BACKUP_DIR/repo/env/nodes.env" "$NODES_ENV"
  cp -a "$BACKUP_DIR/repo/nginx/sub.conf" "$PROJECT_DIR/nginx/sub.conf"
  cp -a "$BACKUP_DIR/repo/xray/config.template.json" "$PROJECT_DIR/xray/config.template.json"
  for name in vless-add-user vless-sync-expire healthcheck_master_replicas.sh bootstrap_clean_vds.sh recover_master_from_replica.py; do
    cp -a "$BACKUP_DIR/repo/scripts/$name" "$PROJECT_DIR/scripts/$name"
  done
  cd "$REPO_DIR"
  docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate xray bot
  nginx -t && systemctl reload nginx
  return "$rc"
}
trap rollback ERR

CHANGED=1
install -m 0644 "$STAGING_DIR/docker-compose.master-full.yml" "$COMPOSE_FILE"
install -m 0644 "$STAGING_DIR/sub.conf" "$PROJECT_DIR/nginx/sub.conf"
install -m 0644 "$STAGING_DIR/sub.conf" /etc/nginx/conf.d/sub.conf
install -m 0644 "$STAGING_DIR/config.template.json" "$PROJECT_DIR/xray/config.template.json"
install -m 0644 "$STAGING_DIR/nodes.env.example" "$PROJECT_DIR/env/nodes.env.example"
install -m 0755 "$STAGING_DIR/vless-add-user" "$PROJECT_DIR/scripts/vless-add-user"
install -m 0755 "$STAGING_DIR/vless-sync-expire" "$PROJECT_DIR/scripts/vless-sync-expire"
install -m 0755 "$STAGING_DIR/healthcheck_master_replicas.sh" "$PROJECT_DIR/scripts/healthcheck_master_replicas.sh"
install -m 0755 "$STAGING_DIR/bootstrap_clean_vds.sh" "$PROJECT_DIR/scripts/bootstrap_clean_vds.sh"
install -m 0755 "$STAGING_DIR/recover_master_from_replica.py" "$PROJECT_DIR/scripts/recover_master_from_replica.py"
install -m 0755 "$STAGING_DIR/enable_master_ws_alt.py" "$PROJECT_DIR/scripts/enable_master_ws_alt.py"
install -m 0755 "$STAGING_DIR/refresh_master_ws_alt.py" "$PROJECT_DIR/scripts/refresh_master_ws_alt.py"

NODES_ENV="$NODES_ENV" python3 - <<'PY'
import os
from pathlib import Path

path = Path(os.environ['NODES_ENV'])
lines = path.read_text(encoding='utf-8').splitlines()
master_host = ''
for line in lines:
    if line.startswith('MASTER_HOST='):
        master_host = line.split('=', 1)[1].strip()
        break
if not master_host:
    raise SystemExit('MASTER_HOST is empty')

values = {
    'MASTER_WS_ENABLED': '1',
    'MASTER_WS_PORT': '2053',
    'MASTER_WS_SNI': master_host,
    'MASTER_WS_PATH': '/api/v1/stream',
    'MASTER_WS_FP': 'chrome',
}
result = []
seen = set()
for line in lines:
    key = line.split('=', 1)[0] if '=' in line else ''
    if key in values:
        result.append(f'{key}={values[key]}')
        seen.add(key)
    else:
        result.append(line)
for key, value in values.items():
    if key not in seen:
        result.append(f'{key}={value}')
path.write_text('\n'.join(result) + '\n', encoding='utf-8')
PY

"$PROJECT_DIR/scripts/enable_master_ws_alt.py" --config /usr/local/etc/xray/config.json
docker run --rm -v /usr/local/etc/xray:/usr/local/etc/xray:ro ghcr.io/xtls/xray-core:latest run -test -config /usr/local/etc/xray/config.json
nginx -t
cd "$REPO_DIR"
docker compose -f "$COMPOSE_FILE" config --quiet

docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate xray
for _ in $(seq 1 15); do
  [[ "$(docker inspect -f '{{.State.Status}}' hexenvpn-xray 2>/dev/null || true)" == "running" ]] && break
  sleep 1
done
[[ "$(docker inspect -f '{{.State.Status}}' hexenvpn-xray)" == "running" ]]
systemctl reload nginx
docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate bot

set -a
# shellcheck disable=SC1090
source "$NODES_ENV"
set +a
"$PROJECT_DIR/scripts/refresh_master_ws_alt.py" \
  --host "$MASTER_HOST" \
  --port "$MASTER_WS_PORT" \
  --sni "$MASTER_WS_SNI" \
  --path "$MASTER_WS_PATH" \
  --fingerprint "$MASTER_WS_FP"

ss -ltn | grep -q ':2053 '
curl -ksS --connect-timeout 10 --resolve "$MASTER_HOST:2053:127.0.0.1" -o /dev/null "https://$MASTER_HOST:2053/"
docker exec hexenvpn-bot /usr/local/sbin/vless-sync-expire --grace-days 1
docker exec hexenvpn-bot /usr/local/sbin/healthcheck-master-replicas

CHANGED=0
trap - ERR
echo "[ws-alt] completed backup=$BACKUP_DIR"
