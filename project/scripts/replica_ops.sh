#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NODES_ENV="${NODES_ENV:-$ROOT_DIR/env/nodes.env}"
HC_SCRIPT_DEFAULT="$ROOT_DIR/scripts/healthcheck_replica.sh"
HC_SCRIPT="${REPLICA_HC_CMD:-/usr/local/sbin/healthcheck-replica}"
SSH_KEY_DEFAULT="/root/.ssh/vless_sync_ed25519"
SSH_TIMEOUT=10
NODE=""
HOST=""
LABEL=""
ACTION="diag"
CHECK_USER=""

usage() {
  cat <<'USAGE'
Usage:
  replica_ops.sh [options]

Options:
  --node <uk|tr>              Replica alias from nodes.env
  --host <ip-or-hostname>     Explicit replica host
  --label <name>              Display name in output
  --action <name>             diag | restart | postcheck | restart-post
  --user <vpn_name>           Optional user check for postcheck
  --nodes-env <path>          Path to nodes.env (default: project/env/nodes.env)
  --ssh-key <path>            SSH private key (default: /root/.ssh/vless_sync_ed25519)
  --ssh-timeout <sec>         SSH timeout (default: 10)
  -h, --help                  Show help

Examples:
  replica_ops.sh --node uk --action diag
  replica_ops.sh --node tr --action restart-post --user test1
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --node)
      NODE="${2:-}"; shift 2 ;;
    --host)
      HOST="${2:-}"; shift 2 ;;
    --label)
      LABEL="${2:-}"; shift 2 ;;
    --action)
      ACTION="${2:-diag}"; shift 2 ;;
    --user)
      CHECK_USER="${2:-}"; shift 2 ;;
    --nodes-env)
      NODES_ENV="${2:-}"; shift 2 ;;
    --ssh-key)
      SSH_KEY_DEFAULT="${2:-}"; shift 2 ;;
    --ssh-timeout)
      SSH_TIMEOUT="${2:-10}"; shift 2 ;;
    -h|--help)
      usage
      exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1 ;;
  esac
done

if [[ -f "$NODES_ENV" ]]; then
  # shellcheck disable=SC1090
  source "$NODES_ENV"
fi

if [[ ! -x "$HC_SCRIPT" ]]; then
  HC_SCRIPT="$HC_SCRIPT_DEFAULT"
fi

SSH_KEY="${SSH_KEY:-$SSH_KEY_DEFAULT}"

if [[ -z "$HOST" && -n "$NODE" ]]; then
  case "${NODE,,}" in
    uk) HOST="${UK_HOST:-}" ; LABEL="${LABEL:-UK}" ;;
    tr) HOST="${TR_HOST:-}" ; LABEL="${LABEL:-TR}" ;;
    *)
      echo "Unknown --node value: $NODE (expected uk|tr)" >&2
      exit 1 ;;
  esac
fi

if [[ -z "$HOST" ]]; then
  echo "Replica host is empty. Use --host or --node uk|tr." >&2
  exit 1
fi

if [[ -z "$LABEL" ]]; then
  LABEL="$HOST"
fi

run_healthcheck() {
  local args=(--host "$HOST" --label "$LABEL" --nodes-env "$NODES_ENV" --ssh-key "$SSH_KEY" --ssh-timeout "$SSH_TIMEOUT")
  if [[ -n "$CHECK_USER" ]]; then
    args+=(--user "$CHECK_USER")
  fi
  "$HC_SCRIPT" "${args[@]}"
}

restart_remote_xray() {
  echo "== Restart xray on $LABEL ($HOST) =="
  ssh -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout="$SSH_TIMEOUT" "root@$HOST" \
    "set -e
if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -qx 'hexenvpn-xray'; then
  docker restart hexenvpn-xray >/dev/null
  echo 'runtime=docker action=restart'
elif command -v systemctl >/dev/null 2>&1; then
  systemctl restart xray
  echo 'runtime=systemd action=restart'
else
  echo 'runtime=unknown action=failed'
  exit 3
fi
if command -v ss >/dev/null 2>&1 && ss -ltn | grep -q ':443 '; then
  echo 'port443=listening'
else
  echo 'port443=not-listening'
fi"
}

case "$ACTION" in
  diag)
    run_healthcheck ;;
  restart)
    restart_remote_xray ;;
  postcheck)
    run_healthcheck ;;
  restart-post)
    restart_remote_xray
    sleep 2
    run_healthcheck ;;
  *)
    echo "Unknown action: $ACTION (expected diag|restart|postcheck|restart-post)" >&2
    exit 1 ;;
esac
