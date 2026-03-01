#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NODES_ENV="${NODES_ENV:-$ROOT_DIR/env/nodes.env}"
SSH_KEY_DEFAULT="/root/.ssh/vless_sync_ed25519"
CHECK_USER=""
FAILS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      CHECK_USER="${2:-}"; shift 2 ;;
    --nodes-env)
      NODES_ENV="${2:-}"; shift 2 ;;
    -h|--help)
      cat <<USAGE
Usage:
  healthcheck_master_replicas.sh [--user <name>] [--nodes-env <path>]

Checks:
  - xray up/listening on master
  - duplicate ids/emails (case-insensitive) in xray config on master and replicas
  - optional: specific user existence on master/replicas
USAGE
      exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1 ;;
  esac
done

if [[ -f "$NODES_ENV" ]]; then
  # shellcheck disable=SC1090
  source "$NODES_ENV"
fi

SSH_KEY="${SSH_KEY:-$SSH_KEY_DEFAULT}"
UK_HOST="${UK_HOST:-}"
TR_HOST="${TR_HOST:-}"
HOST_RUN=()
if command -v docker >/dev/null 2>&1 && command -v ss >/dev/null 2>&1; then
  HOST_RUN=()
elif command -v nsenter >/dev/null 2>&1; then
  HOST_RUN=(nsenter -t 1 -m -u -i -n -p)
fi

ok() { echo "OK   $*"; }
warn() { echo "WARN $*"; }
fail() { echo "FAIL $*"; FAILS=$((FAILS+1)); }

run_host() {
  if [[ "${#HOST_RUN[@]}" -gt 0 ]]; then
    "${HOST_RUN[@]}" sh -lc "$1"
  else
    sh -lc "$1"
  fi
}

check_dups_local() {
  local cfg="$1"
  python3 - "$cfg" <<'PY'
import json, sys, collections
cfg=json.load(open(sys.argv[1], 'r', encoding='utf-8'))
clients=[c for ib in cfg.get('inbounds',[]) if ib.get('protocol')=='vless' for c in ib.get('settings',{}).get('clients',[])]
ids=[(c.get('id') or '').strip() for c in clients if c.get('id')]
emails=[(c.get('email') or '').strip().lower() for c in clients if c.get('email')]
dup_ids=sorted([k for k,v in collections.Counter(ids).items() if v>1])
dup_em=sorted([k for k,v in collections.Counter(emails).items() if v>1])
print(len(dup_ids), len(dup_em), len(clients))
PY
}

check_user_local() {
  local name="$1"
  python3 - "$name" <<'PY'
import json, sys
n=sys.argv[1].strip().lower()
cfg=json.load(open('/usr/local/etc/xray/config.json','r',encoding='utf-8'))
cnt=sum(1 for ib in cfg.get('inbounds',[]) if ib.get('protocol')=='vless' for c in ib.get('settings',{}).get('clients',[]) if (c.get('email') or '').strip().lower()==n)
print(cnt)
PY
}

echo "== Master =="
if run_host "command -v docker >/dev/null 2>&1"; then
  if run_host "docker ps --format '{{.Names}}' | grep -qx 'hexenvpn-xray'"; then
    ok "master xray container up"
  else
    fail "master xray container is not running"
  fi
else
  warn "docker command unavailable for master runtime check (skipped)"
fi

if run_host "command -v ss >/dev/null 2>&1"; then
  if run_host "ss -ltn | grep -q ':443 '"; then
    ok "master port 443 listening"
  else
    fail "master port 443 not listening"
  fi
else
  warn "ss command unavailable for master port check (skipped)"
fi

read -r dup_ids dup_emails total_clients < <(check_dups_local /usr/local/etc/xray/config.json)
if [[ "$dup_ids" == "0" && "$dup_emails" == "0" ]]; then
  ok "master xray duplicates: none (clients=$total_clients)"
else
  fail "master xray duplicates found (dup_ids=$dup_ids dup_emails=$dup_emails clients=$total_clients)"
fi

if [[ -n "$CHECK_USER" ]]; then
  cnt="$(check_user_local "$CHECK_USER")"
  if [[ "$cnt" == "1" ]]; then
    ok "master user '$CHECK_USER' exists exactly once"
  else
    fail "master user '$CHECK_USER' count=$cnt (expected 1)"
  fi
fi

check_replica() {
  local host="$1"
  [[ -z "$host" ]] && return 0
  echo "== Replica $host =="
  local out rc
  out="$(ssh -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10 "root@$host" "python3 - <<'PY'
import json, collections, subprocess
cfg=json.load(open('/usr/local/etc/xray/config.json','r',encoding='utf-8'))
clients=[c for ib in cfg.get('inbounds',[]) if ib.get('protocol')=='vless' for c in ib.get('settings',{}).get('clients',[])]
ids=[(c.get('id') or '').strip() for c in clients if c.get('id')]
emails=[(c.get('email') or '').strip().lower() for c in clients if c.get('email')]
dup_ids=len([k for k,v in collections.Counter(ids).items() if v>1])
dup_em=len([k for k,v in collections.Counter(emails).items() if v>1])
active=subprocess.run(['systemctl','is-active','xray'], capture_output=True, text=True).stdout.strip()
print(active, dup_ids, dup_em, len(clients))
PY")" || rc=$?
  if [[ "${rc:-0}" != "0" ]]; then
    fail "replica $host unreachable via SSH key $SSH_KEY"
    return 0
  fi
  local active d1 d2 total
  read -r active d1 d2 total <<<"$out"
  if [[ "$active" == "active" ]]; then
    ok "replica $host xray active"
  else
    fail "replica $host xray status=$active"
  fi
  if [[ "$d1" == "0" && "$d2" == "0" ]]; then
    ok "replica $host duplicates: none (clients=$total)"
  else
    fail "replica $host duplicates found (dup_ids=$d1 dup_emails=$d2 clients=$total)"
  fi

  if [[ -n "$CHECK_USER" ]]; then
    local cnt
    cnt="$(ssh -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10 "root@$host" "python3 - <<'PY'
import json
name='$CHECK_USER'.strip().lower()
cfg=json.load(open('/usr/local/etc/xray/config.json','r',encoding='utf-8'))
cnt=sum(1 for ib in cfg.get('inbounds',[]) if ib.get('protocol')=='vless' for c in ib.get('settings',{}).get('clients',[]) if (c.get('email') or '').strip().lower()==name)
print(cnt)
PY" 2>/dev/null || echo "ERR")"
    if [[ "$cnt" == "1" ]]; then
      ok "replica $host user '$CHECK_USER' exists exactly once"
    else
      fail "replica $host user '$CHECK_USER' count=$cnt (expected 1)"
    fi
  fi
}

check_replica "$UK_HOST"
check_replica "$TR_HOST"

if [[ "$FAILS" -eq 0 ]]; then
  echo "RESULT: OK"
  exit 0
fi

echo "RESULT: FAIL ($FAILS)"
exit 2
