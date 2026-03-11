#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NODES_ENV="${NODES_ENV:-$ROOT_DIR/env/nodes.env}"
COMPOSE_SRC="${COMPOSE_SRC:-$ROOT_DIR/docker-compose.replica-xray.yml}"
SSH_KEY_DEFAULT="/root/.ssh/vless_sync_ed25519"
SSH_TIMEOUT=10
MODE="dry-run" # dry-run | apply | rollback
NODE=""
HOST=""
LABEL=""

usage() {
  cat <<'USAGE'
Usage:
  migrate_replica_to_docker.sh [options]

Modes:
  default                  Dry-run (checks only, no changes)
  --apply                  Perform migration: systemd xray -> docker xray
  --rollback               Rollback to systemd xray

Options:
  --node <uk|tr>           Resolve host from nodes.env
  --host <ip-or-hostname>  Explicit replica host
  --label <name>           Friendly label in output
  --nodes-env <path>       nodes.env path (default: project/env/nodes.env)
  --ssh-key <path>         SSH key path (default: /root/.ssh/vless_sync_ed25519)
  --ssh-timeout <sec>      SSH timeout (default: 10)
  -h, --help               Show help

Examples:
  migrate_replica_to_docker.sh --node uk
  migrate_replica_to_docker.sh --node uk --apply
  migrate_replica_to_docker.sh --node uk --rollback
USAGE
}

ok() { echo "OK   $*"; }
warn() { echo "WARN $*"; }
fail() { echo "FAIL $*"; exit 2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      MODE="apply"; shift ;;
    --rollback)
      MODE="rollback"; shift ;;
    --node)
      NODE="${2:-}"; shift 2 ;;
    --host)
      HOST="${2:-}"; shift 2 ;;
    --label)
      LABEL="${2:-}"; shift 2 ;;
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

SSH_KEY="${SSH_KEY:-$SSH_KEY_DEFAULT}"

if [[ -z "$HOST" && -n "$NODE" ]]; then
  case "${NODE,,}" in
    uk) HOST="${UK_HOST:-}" ; LABEL="${LABEL:-UK}" ;;
    tr) HOST="${TR_HOST:-}" ; LABEL="${LABEL:-TR}" ;;
    *) fail "Unknown --node value: $NODE (expected uk|tr)" ;;
  esac
fi

[[ -n "$HOST" ]] || fail "Replica host is empty. Use --host or --node."
[[ -n "$LABEL" ]] || LABEL="$HOST"
[[ -f "$COMPOSE_SRC" ]] || fail "Compose source not found: $COMPOSE_SRC"

echo "== Replica Docker Migration =="
echo "mode: $MODE"
echo "target: $LABEL ($HOST)"
echo "nodes_env: $NODES_ENV"
echo "compose_src: $COMPOSE_SRC"
echo "ssh_key: $SSH_KEY"

remote_sh() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout="$SSH_TIMEOUT" "root@$HOST" "$@"
}

echo "== Precheck =="
remote_sh "test -f /usr/local/etc/xray/config.json" && ok "xray config exists" || fail "missing /usr/local/etc/xray/config.json"
remote_sh "command -v docker >/dev/null 2>&1" && ok "docker found" || fail "docker not found"
COMPOSE_CMD="$(remote_sh "if docker compose version >/dev/null 2>&1; then echo 'docker compose'; elif command -v docker-compose >/dev/null 2>&1; then echo 'docker-compose'; fi" || true)"
[[ -n "$COMPOSE_CMD" ]] || fail "docker compose not found (neither 'docker compose' nor 'docker-compose')"
ok "compose cmd: $COMPOSE_CMD"
remote_sh "docker run --rm -v /usr/local/etc/xray:/usr/local/etc/xray ghcr.io/xtls/xray-core:latest run -test -config /usr/local/etc/xray/config.json >/dev/null" \
  && ok "xray config test OK (container)" || fail "xray config test failed"
sysd_state="$(remote_sh "systemctl is-active xray 2>/dev/null || true" || true)"
echo "systemd xray state: ${sysd_state:-unknown}"

if [[ "$MODE" == "dry-run" ]]; then
  echo "RESULT: DRY-RUN OK (no changes)"
  exit 0
fi

if [[ "$MODE" == "rollback" ]]; then
  echo "== Rollback =="
  remote_sh "set -e; $COMPOSE_CMD -f /opt/hexenvpn-replica/docker-compose.yml down || true; systemctl start xray; systemctl is-active xray"
  remote_sh "ss -ltn | grep -q ':443 '" && ok "port 443 listening after rollback" || fail "port 443 not listening after rollback"
  echo "RESULT: ROLLBACK OK"
  exit 0
fi

echo "== Backup =="
TS="$(date +%F_%H-%M-%S)"
BACKUP_DIR="/root/backup-replica-docker-migrate/${TS}"
remote_sh "set -e; mkdir -p '$BACKUP_DIR'; cp -a /usr/local/etc/xray/config.json '$BACKUP_DIR/config.json'; systemctl cat xray > '$BACKUP_DIR/systemd-xray.unit.txt' || true; systemctl status xray --no-pager > '$BACKUP_DIR/systemd-xray.status.txt' || true; echo '$BACKUP_DIR'"
ok "backup created: $BACKUP_DIR"

echo "== Upload Compose =="
remote_sh "mkdir -p /opt/hexenvpn-replica"
scp -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout="$SSH_TIMEOUT" "$COMPOSE_SRC" "root@$HOST:/opt/hexenvpn-replica/docker-compose.yml" >/dev/null
ok "compose uploaded to /opt/hexenvpn-replica/docker-compose.yml"

echo "== Switch Runtime (systemd -> docker) =="
set +e
remote_sh "set -e; systemctl stop xray; $COMPOSE_CMD -f /opt/hexenvpn-replica/docker-compose.yml up -d xray; docker ps --format '{{.Names}}' | grep -qx hexenvpn-xray"
rc_switch=$?
set -e
if [[ "$rc_switch" != "0" ]]; then
  warn "switch failed, trying rollback to systemd immediately"
  remote_sh "set -e; $COMPOSE_CMD -f /opt/hexenvpn-replica/docker-compose.yml down || true; systemctl start xray"
  fail "migration failed; rolled back to systemd"
fi

sleep 2
remote_sh "ss -ltn | grep -q ':443 '" && ok "port 443 listening on docker runtime" || fail "port 443 not listening after switch"
remote_sh "docker inspect -f '{{.State.Status}}' hexenvpn-xray | grep -qx running" && ok "container hexenvpn-xray running" || fail "container hexenvpn-xray not running"

echo "== Postcheck (from master) =="
"$ROOT_DIR/scripts/healthcheck_replica.sh" --host "$HOST" --label "$LABEL" --ssh-key "$SSH_KEY" --nodes-env "$NODES_ENV"
ok "postcheck passed"

echo "RESULT: APPLY OK"
echo "Rollback command if needed:"
echo "  $ROOT_DIR/scripts/migrate_replica_to_docker.sh --host $HOST --label $LABEL --rollback --ssh-key $SSH_KEY --nodes-env $NODES_ENV"
