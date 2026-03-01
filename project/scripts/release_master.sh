#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage:
  release_master.sh [options]

Options:
  --repo-dir <path>            Repo directory on master (default: /opt/vpn_vds)
  --compose-file <path>        Compose file path (default: project/docker-compose.master-full.yml)
  --backup-root <path>         Backup root dir (default: /root/backup-release-master)
  --check-user <name>          Extra healthcheck user validation
  --skip-precheck              Skip pre-release healthcheck
  --skip-postcheck             Skip post-release healthcheck
  --pull-xray                  Pull latest xray image before restart
  --build-bot                  Rebuild bot image before restart
  --help                       Show this help

What it does:
  1) Creates timestamped backup of critical files
  2) Optionally runs precheck
  3) Optionally pulls xray / rebuilds bot
  4) Recreates xray+bot containers
  5) Runs postcheck
  6) On failure restores backed up files and re-runs containers
USAGE
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing command: $1" >&2
    exit 1
  }
}

safe_copy() {
  local src="$1"
  local dst="$2"
  if [[ -f "$src" ]]; then
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
  fi
}

REPO_DIR="/opt/vpn_vds"
COMPOSE_FILE="project/docker-compose.master-full.yml"
BACKUP_ROOT="/root/backup-release-master"
CHECK_USER=""
SKIP_PRECHECK=0
SKIP_POSTCHECK=0
PULL_XRAY=0
BUILD_BOT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-dir)
      REPO_DIR="${2:-}"; shift 2 ;;
    --compose-file)
      COMPOSE_FILE="${2:-}"; shift 2 ;;
    --backup-root)
      BACKUP_ROOT="${2:-}"; shift 2 ;;
    --check-user)
      CHECK_USER="${2:-}"; shift 2 ;;
    --skip-precheck)
      SKIP_PRECHECK=1; shift ;;
    --skip-postcheck)
      SKIP_POSTCHECK=1; shift ;;
    --pull-xray)
      PULL_XRAY=1; shift ;;
    --build-bot)
      BUILD_BOT=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1 ;;
  esac
done

require_cmd docker

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose is not available" >&2
  exit 1
fi

if [[ ! -d "$REPO_DIR" ]]; then
  echo "Repo dir does not exist: $REPO_DIR" >&2
  exit 1
fi

cd "$REPO_DIR"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Compose file does not exist: $REPO_DIR/$COMPOSE_FILE" >&2
  exit 1
fi

HEALTHCHECK_SCRIPT="$REPO_DIR/project/scripts/healthcheck_master_replicas.sh"
if [[ ! -f "$HEALTHCHECK_SCRIPT" ]]; then
  echo "Missing healthcheck script: $HEALTHCHECK_SCRIPT" >&2
  exit 1
fi

TS="$(date +%F_%H-%M-%S)"
BACKUP_DIR="$BACKUP_ROOT/$TS"
mkdir -p "$BACKUP_DIR"

echo "[release] repo=$REPO_DIR"
echo "[release] compose=$COMPOSE_FILE"
echo "[release] backup=$BACKUP_DIR"
echo "[release] git=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

safe_copy /usr/local/etc/xray/config.json "$BACKUP_DIR/usr/local/etc/xray/config.json"
safe_copy /var/lib/vless-sub/clients.json "$BACKUP_DIR/var/lib/vless-sub/clients.json"
safe_copy /var/lib/hexenvpn-bot/bot.db "$BACKUP_DIR/var/lib/hexenvpn-bot/bot.db"
safe_copy /etc/nginx/njs/subscription.js "$BACKUP_DIR/etc/nginx/njs/subscription.js"
safe_copy "$REPO_DIR/project/env/bot.env" "$BACKUP_DIR/repo/project/env/bot.env"
safe_copy "$REPO_DIR/project/env/nodes.env" "$BACKUP_DIR/repo/project/env/nodes.env"

ROLLBACK_NEEDED=0

rollback() {
  echo "[rollback] started"
  safe_copy "$BACKUP_DIR/usr/local/etc/xray/config.json" /usr/local/etc/xray/config.json
  safe_copy "$BACKUP_DIR/var/lib/vless-sub/clients.json" /var/lib/vless-sub/clients.json
  safe_copy "$BACKUP_DIR/var/lib/hexenvpn-bot/bot.db" /var/lib/hexenvpn-bot/bot.db
  safe_copy "$BACKUP_DIR/etc/nginx/njs/subscription.js" /etc/nginx/njs/subscription.js
  safe_copy "$BACKUP_DIR/repo/project/env/bot.env" "$REPO_DIR/project/env/bot.env"
  safe_copy "$BACKUP_DIR/repo/project/env/nodes.env" "$REPO_DIR/project/env/nodes.env"

  docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate xray bot
  echo "[rollback] containers recreated from restored files"
}

run_healthcheck() {
  local mode="$1"
  if [[ -n "$CHECK_USER" ]]; then
    "$HEALTHCHECK_SCRIPT" --user "$CHECK_USER"
  else
    "$HEALTHCHECK_SCRIPT"
  fi
  echo "[release] $mode healthcheck: OK"
}

on_error() {
  local line="$1"
  echo "[release] failed at line $line"
  if [[ "$ROLLBACK_NEEDED" == "1" ]]; then
    rollback
    if [[ "$SKIP_POSTCHECK" == "0" ]]; then
      run_healthcheck "rollback-post"
    fi
  fi
}
trap 'on_error $LINENO' ERR

if [[ "$SKIP_PRECHECK" == "0" ]]; then
  run_healthcheck "pre"
else
  echo "[release] pre healthcheck skipped"
fi

if [[ "$PULL_XRAY" == "1" ]]; then
  echo "[release] pull xray image"
  docker compose -f "$COMPOSE_FILE" pull xray
fi

if [[ "$BUILD_BOT" == "1" ]]; then
  echo "[release] build bot image"
  docker compose -f "$COMPOSE_FILE" build bot
fi

ROLLBACK_NEEDED=1
echo "[release] recreate xray+bot"
docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate xray bot

sleep 3
docker compose -f "$COMPOSE_FILE" ps

if [[ "$SKIP_POSTCHECK" == "0" ]]; then
  run_healthcheck "post"
else
  echo "[release] post healthcheck skipped"
fi

ROLLBACK_NEEDED=0
echo "[release] success"
