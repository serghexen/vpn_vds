#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage:
  backup_master.sh [options]

Options:
  --repo-dir <path>            Repo directory on master (default: /opt/vpn_vds)
  --backup-root <path>         Backup root directory (default: /root/backup-master)
  --keep-count <n>             Keep only last N backups (default: 14)
  --label <text>               Optional label suffix in backup folder name
  --no-rotate                  Do not remove old backups
  --help                       Show this help

Creates backup of:
  - /var/lib/hexenvpn-bot/bot.db (SQLite online backup)
  - /var/lib/vless-sub/clients.json
  - /var/lib/vless-sub/happ-links.json
  - /usr/local/etc/xray/config.json
  - /etc/nginx/njs/subscription.js
  - <repo>/project/env/bot.env
  - <repo>/project/env/nodes.env
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
    echo "OK  $src"
  else
    echo "SKIP $src (not found)"
  fi
}

backup_sqlite() {
  local src="$1"
  local dst="$2"
  if [[ ! -f "$src" ]]; then
    echo "SKIP $src (not found)"
    return 0
  fi
  mkdir -p "$(dirname "$dst")"
  python3 - "$src" "$dst" <<'PY'
import sqlite3
import sys
src, dst = sys.argv[1], sys.argv[2]
con = sqlite3.connect(src)
bak = sqlite3.connect(dst)
with bak:
    con.backup(bak)
bak.close()
con.close()
PY
  echo "OK  $src (sqlite online backup)"
}

rotate_backups() {
  local root="$1"
  local keep="$2"
  mapfile -t dirs < <(find "$root" -mindepth 1 -maxdepth 1 -type d -name '20*' | sort)
  local total="${#dirs[@]}"
  if (( total <= keep )); then
    return 0
  fi
  local delete_n=$((total - keep))
  echo "[rotate] total=$total keep=$keep delete=$delete_n"
  for d in "${dirs[@]:0:delete_n}"; do
    rm -rf "$d"
    echo "[rotate] removed $d"
  done
}

REPO_DIR="/opt/vpn_vds"
BACKUP_ROOT="/root/backup-master"
KEEP_COUNT=14
LABEL=""
DO_ROTATE=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-dir)
      REPO_DIR="${2:-}"; shift 2 ;;
    --backup-root)
      BACKUP_ROOT="${2:-}"; shift 2 ;;
    --keep-count)
      KEEP_COUNT="${2:-}"; shift 2 ;;
    --label)
      LABEL="${2:-}"; shift 2 ;;
    --no-rotate)
      DO_ROTATE=0; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1 ;;
  esac
done

require_cmd python3
require_cmd sha256sum

if [[ ! "$KEEP_COUNT" =~ ^[0-9]+$ ]] || [[ "$KEEP_COUNT" -lt 1 ]]; then
  echo "--keep-count must be integer >= 1" >&2
  exit 1
fi

if [[ ! -d "$REPO_DIR" ]]; then
  echo "Repo dir does not exist: $REPO_DIR" >&2
  exit 1
fi

TS="$(date +%F_%H-%M-%S)"
if [[ -n "$LABEL" ]]; then
  SAFE_LABEL="$(printf '%s' "$LABEL" | LC_ALL=C tr -c 'A-Za-z0-9._+-' '_')"
  DIR_NAME="${TS}_${SAFE_LABEL}"
else
  DIR_NAME="$TS"
fi

BACKUP_DIR="$BACKUP_ROOT/$DIR_NAME"
mkdir -p "$BACKUP_DIR/files"

echo "[backup] target=$BACKUP_DIR"

backup_sqlite /var/lib/hexenvpn-bot/bot.db "$BACKUP_DIR/files/var/lib/hexenvpn-bot/bot.db"
safe_copy /var/lib/vless-sub/clients.json "$BACKUP_DIR/files/var/lib/vless-sub/clients.json"
safe_copy /var/lib/vless-sub/happ-links.json "$BACKUP_DIR/files/var/lib/vless-sub/happ-links.json"
safe_copy /usr/local/etc/xray/config.json "$BACKUP_DIR/files/usr/local/etc/xray/config.json"
safe_copy /etc/nginx/njs/subscription.js "$BACKUP_DIR/files/etc/nginx/njs/subscription.js"
safe_copy "$REPO_DIR/project/env/bot.env" "$BACKUP_DIR/files/repo/project/env/bot.env"
safe_copy "$REPO_DIR/project/env/nodes.env" "$BACKUP_DIR/files/repo/project/env/nodes.env"

{
  echo "timestamp=$TS"
  echo "repo_dir=$REPO_DIR"
  echo "host=$(hostname)"
  echo "git_commit=$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"
} > "$BACKUP_DIR/backup.meta"

if find "$BACKUP_DIR/files" -type f | grep -q .; then
  (
    cd "$BACKUP_DIR/files"
    find . -type f -print0 | sort -z | xargs -0 sha256sum > "$BACKUP_DIR/backup.sha256"
  )
fi

echo "[backup] completed: $BACKUP_DIR"

if [[ "$DO_ROTATE" == "1" ]]; then
  rotate_backups "$BACKUP_ROOT" "$KEEP_COUNT"
fi

echo "[backup] done"
