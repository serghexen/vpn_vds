#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NODES_ENV="${NODES_ENV:-$ROOT_DIR/env/nodes.env}"
SSH_KEY_DEFAULT="/root/.ssh/vless_sync_ed25519"
SSH_TIMEOUT=10
NODE=""
HOST=""
LABEL=""
CHECK_USER=""
FAILS=0

usage() {
  cat <<'USAGE'
Usage:
  healthcheck_replica.sh [options]

Options:
  --node <uk|tr>              Replica alias from nodes.env
  --host <ip-or-hostname>     Explicit replica host
  --label <name>              Display name in output
  --user <vpn_name>           Validate that user exists exactly once
  --nodes-env <path>          Path to nodes.env (default: project/env/nodes.env)
  --ssh-key <path>            SSH private key (default: /root/.ssh/vless_sync_ed25519)
  --ssh-timeout <sec>         SSH timeout (default: 10)
  -h, --help                  Show help

Checks:
  - SSH reachability
  - xray status (docker container or systemd service)
  - port 443 listening
  - duplicate ids/emails in /usr/local/etc/xray/config.json
  - optional: user existence count
USAGE
}

ok() { echo "OK   $*"; }
fail() { echo "FAIL $*"; FAILS=$((FAILS + 1)); }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --node)
      NODE="${2:-}"; shift 2 ;;
    --host)
      HOST="${2:-}"; shift 2 ;;
    --label)
      LABEL="${2:-}"; shift 2 ;;
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

echo "== Replica $LABEL ($HOST) =="

remote_json="$(
  ssh -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout="$SSH_TIMEOUT" "root@$HOST" \
    "CHECK_USER='$CHECK_USER' python3 - <<'PY'
import collections
import json
import os
import subprocess

cfg_path = '/usr/local/etc/xray/config.json'
check_user = (os.environ.get('CHECK_USER') or '').strip().lower()

out = {
    'ok': True,
    'runtime': 'unknown',
    'xray_active': False,
    'port_443': False,
    'dup_ids': 0,
    'dup_emails': 0,
    'clients_total': 0,
    'check_user': check_user,
    'user_count': -1,
    'error': '',
}

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

try:
    cfg = json.load(open(cfg_path, 'r', encoding='utf-8'))
except Exception as e:
    out['ok'] = False
    out['error'] = f'cannot read xray config: {e}'
    print(json.dumps(out, ensure_ascii=False))
    raise SystemExit(0)

clients = []
for ib in cfg.get('inbounds', []):
    if ib.get('protocol') != 'vless':
        continue
    clients.extend(ib.get('settings', {}).get('clients', []) or [])

ids = [(c.get('id') or '').strip() for c in clients if c.get('id')]
emails = [(c.get('email') or '').strip().lower() for c in clients if c.get('email')]
out['dup_ids'] = len([k for k, v in collections.Counter(ids).items() if v > 1])
out['dup_emails'] = len([k for k, v in collections.Counter(emails).items() if v > 1])
out['clients_total'] = len(clients)

docker_active = False
r = run(['sh', '-lc', 'docker ps --format \\'{{.Names}}\\' 2>/dev/null | grep -qx hexenvpn-xray'])
if r.returncode == 0:
    docker_active = True

systemd_active = False
r2 = run(['sh', '-lc', 'systemctl is-active xray 2>/dev/null || true'])
if (r2.stdout or '').strip() == 'active':
    systemd_active = True

if docker_active:
    out['runtime'] = 'docker'
elif systemd_active:
    out['runtime'] = 'systemd'
else:
    out['runtime'] = 'unknown'

out['xray_active'] = bool(docker_active or systemd_active)

r3 = run(['sh', '-lc', 'ss -ltn 2>/dev/null | grep -q :443'])
out['port_443'] = (r3.returncode == 0)

if check_user:
    cnt = 0
    for c in clients:
        if (c.get('email') or '').strip().lower() == check_user:
            cnt += 1
    out['user_count'] = cnt

print(json.dumps(out, ensure_ascii=False))
PY"
)" || {
  fail "replica $LABEL unreachable via SSH key $SSH_KEY"
  echo "RESULT: FAIL ($FAILS)"
  exit 2
}

readarray -t parsed < <(python3 - "$remote_json" <<'PY'
import json
import sys
obj = json.loads(sys.argv[1])
print("1" if obj.get("ok") else "0")
print(obj.get("runtime") or "unknown")
print("1" if obj.get("xray_active") else "0")
print("1" if obj.get("port_443") else "0")
print(int(obj.get("dup_ids") or 0))
print(int(obj.get("dup_emails") or 0))
print(int(obj.get("clients_total") or 0))
print(obj.get("check_user") or "")
print(int(obj.get("user_count") if obj.get("user_count") is not None else -1))
print(obj.get("error") or "")
PY
)

is_ok="${parsed[0]:-0}"
runtime="${parsed[1]:-unknown}"
xray_active="${parsed[2]:-0}"
port_443="${parsed[3]:-0}"
dup_ids="${parsed[4]:-0}"
dup_emails="${parsed[5]:-0}"
clients_total="${parsed[6]:-0}"
user_name="${parsed[7]:-}"
user_count="${parsed[8]:--1}"
remote_error="${parsed[9]:-}"

if [[ "$is_ok" != "1" ]]; then
  fail "replica $LABEL check error: ${remote_error:-unknown}"
else
  if [[ "$xray_active" == "1" ]]; then
    ok "replica $LABEL xray active (runtime=$runtime)"
  else
    fail "replica $LABEL xray is not active (runtime=$runtime)"
  fi

  if [[ "$port_443" == "1" ]]; then
    ok "replica $LABEL port 443 listening"
  else
    fail "replica $LABEL port 443 not listening"
  fi

  if [[ "$dup_ids" == "0" && "$dup_emails" == "0" ]]; then
    ok "replica $LABEL duplicates: none (clients=$clients_total)"
  else
    fail "replica $LABEL duplicates found (dup_ids=$dup_ids dup_emails=$dup_emails clients=$clients_total)"
  fi

  if [[ -n "$user_name" ]]; then
    if [[ "$user_count" == "1" ]]; then
      ok "replica $LABEL user '$user_name' exists exactly once"
    else
      fail "replica $LABEL user '$user_name' count=$user_count (expected 1)"
    fi
  fi
fi

if [[ "$FAILS" -eq 0 ]]; then
  echo "RESULT: OK"
  exit 0
fi

echo "RESULT: FAIL ($FAILS)"
exit 2
