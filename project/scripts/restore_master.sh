#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage:
  restore_master.sh --from <backup_dir> [options]

Options:
  --from <path|latest>         Backup directory to restore (or "latest")
  --repo-dir <path>            Repo directory on master (default: /opt/vpn_vds)
  --backup-root <path>         Backup root directory (default: /root/backup-master)
  --compose-file <path>        Compose file path (default: project/docker-compose.master-full.yml)
  --check-user <name>          Extra healthcheck user validation
  --no-restart                 Do not restart/recreate docker services
  --no-postcheck               Skip post-restore healthcheck
  --yes                        Confirm restore (required)
  --help                       Show this help

Restore behavior:
  - Always creates safety pre-restore backup via backup_master.sh
  - Restores only files existing in selected backup
  - By default recreates docker services xray+bot
USAGE
}

safe_restore() {
  local src="$1"
  local dst="$2"
  if [[ -f "$src" ]]; then
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
    echo "OK  restore $dst"
  else
    echo "SKIP $dst (not in backup)"
  fi
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing command: $1" >&2
    exit 1
  }
}

FROM_BACKUP=""
REPO_DIR="/opt/vpn_vds"
BACKUP_ROOT="/root/backup-master"
COMPOSE_FILE="project/docker-compose.master-full.yml"
CHECK_USER=""
DO_RESTART=1
DO_POSTCHECK=1
YES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)
      FROM_BACKUP="${2:-}"; shift 2 ;;
    --repo-dir)
      REPO_DIR="${2:-}"; shift 2 ;;
    --backup-root)
      BACKUP_ROOT="${2:-}"; shift 2 ;;
    --compose-file)
      COMPOSE_FILE="${2:-}"; shift 2 ;;
    --check-user)
      CHECK_USER="${2:-}"; shift 2 ;;
    --no-restart)
      DO_RESTART=0; shift ;;
    --no-postcheck)
      DO_POSTCHECK=0; shift ;;
    --yes)
      YES=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1 ;;
  esac
done

if [[ "$YES" != "1" ]]; then
  echo "Refusing to run without --yes" >&2
  exit 1
fi

if [[ -z "$FROM_BACKUP" ]]; then
  echo "--from is required" >&2
  usage
  exit 1
fi

if [[ "$FROM_BACKUP" == "latest" ]]; then
  FROM_BACKUP="$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20*' | sort | tail -n1 || true)"
fi

if [[ -z "$FROM_BACKUP" || ! -d "$FROM_BACKUP" ]]; then
  echo "Backup dir not found: $FROM_BACKUP" >&2
  exit 1
fi

FILES_ROOT="$FROM_BACKUP/files"
if [[ ! -d "$FILES_ROOT" ]]; then
  echo "Invalid backup structure: $FILES_ROOT not found" >&2
  exit 1
fi

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
if [[ "$DO_POSTCHECK" == "1" && ! -f "$HEALTHCHECK_SCRIPT" ]]; then
  echo "Missing healthcheck script: $HEALTHCHECK_SCRIPT" >&2
  exit 1
fi

echo "[restore] source=$FROM_BACKUP"
echo "[restore] repo=$REPO_DIR"
echo "[restore] compose=$COMPOSE_FILE"

echo "[restore] creating safety backup before restore"
"$REPO_DIR/project/scripts/backup_master.sh" --repo-dir "$REPO_DIR" --backup-root "$BACKUP_ROOT" --label pre-restore

safe_restore "$FILES_ROOT/var/lib/hexenvpn-bot/bot.db" /var/lib/hexenvpn-bot/bot.db
safe_restore "$FILES_ROOT/var/lib/vless-sub/clients.json" /var/lib/vless-sub/clients.json
safe_restore "$FILES_ROOT/var/lib/vless-sub/happ-links.json" /var/lib/vless-sub/happ-links.json
safe_restore "$FILES_ROOT/usr/local/etc/xray/config.json" /usr/local/etc/xray/config.json
safe_restore "$FILES_ROOT/etc/nginx/njs/subscription.js" /etc/nginx/njs/subscription.js
safe_restore "$FILES_ROOT/repo/project/env/bot.env" "$REPO_DIR/project/env/bot.env"
safe_restore "$FILES_ROOT/repo/project/env/nodes.env" "$REPO_DIR/project/env/nodes.env"

if [[ "$DO_RESTART" == "1" ]]; then
  echo "[restore] recreate xray+bot"
  docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate xray bot
  docker compose -f "$COMPOSE_FILE" ps
else
  echo "[restore] restart skipped"
fi

if [[ "$DO_POSTCHECK" == "1" ]]; then
  if [[ -n "$CHECK_USER" ]]; then
    "$HEALTHCHECK_SCRIPT" --user "$CHECK_USER"
  else
    "$HEALTHCHECK_SCRIPT"
  fi
fi

echo "[restore] completed"
