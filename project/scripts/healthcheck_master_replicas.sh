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
MASTER_WS_ENABLED="${MASTER_WS_ENABLED:-0}"
MASTER_WS_PORT="${MASTER_WS_PORT:-2053}"
TR_WS_ENABLED="${TR_WS_ENABLED:-0}"
TR_WS_PORT="${TR_WS_PORT:-2053}"
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
inbounds=[ib for ib in cfg.get('inbounds',[]) if ib.get('protocol')=='vless']
dup_ids=0
dup_em=0
unique_ids=set()
for ib in inbounds:
    clients=ib.get('settings',{}).get('clients',[])
    ids=[(c.get('id') or '').strip() for c in clients if c.get('id')]
    emails=[(c.get('email') or '').strip().lower() for c in clients if c.get('email')]
    dup_ids += len([k for k,v in collections.Counter(ids).items() if v>1])
    dup_em += len([k for k,v in collections.Counter(emails).items() if v>1])
    unique_ids.update(ids)
print(dup_ids, dup_em, len(unique_ids), len(inbounds))
PY
}

check_user_local() {
  local name="$1"
  python3 - "$name" <<'PY'
import json, sys
n=sys.argv[1].strip().lower()
cfg=json.load(open('/usr/local/etc/xray/config.json','r',encoding='utf-8'))
inbounds=[ib for ib in cfg.get('inbounds',[]) if ib.get('protocol')=='vless']
counts=[sum(1 for c in ib.get('settings',{}).get('clients',[]) if (c.get('email') or '').strip().lower()==n) for ib in inbounds]
print(len(inbounds), sum(1 for count in counts if count == 1), sum(counts))
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

if [[ "$MASTER_WS_ENABLED" == "1" ]]; then
  if run_host "ss -ltn | grep -q ':${MASTER_WS_PORT} '"; then
    ok "master WS TLS port $MASTER_WS_PORT listening"
  else
    fail "master WS TLS port $MASTER_WS_PORT not listening"
  fi
fi

read -r dup_ids dup_emails total_clients inbound_count < <(check_dups_local /usr/local/etc/xray/config.json)
if [[ "$dup_ids" == "0" && "$dup_emails" == "0" ]]; then
  ok "master xray duplicates: none (clients=$total_clients inbounds=$inbound_count)"
else
  fail "master xray duplicates found (dup_ids=$dup_ids dup_emails=$dup_emails clients=$total_clients inbounds=$inbound_count)"
fi

if [[ -n "$CHECK_USER" ]]; then
  read -r expected matched total_matches < <(check_user_local "$CHECK_USER")
  if [[ "$expected" -gt 0 && "$matched" == "$expected" ]]; then
    ok "master user '$CHECK_USER' exists once in every inbound ($matched/$expected)"
  else
    fail "master user '$CHECK_USER' inbound matches=$matched/$expected total=$total_matches"
  fi
fi

check_replica() {
  local host="$1"
  [[ -z "$host" ]] && return 0
  echo "== Replica $host =="
  local out rc
out="$(ssh -n -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10 "root@$host" "python3 - <<'PY'
import json, collections, subprocess
cfg=json.load(open('/usr/local/etc/xray/config.json','r',encoding='utf-8'))
inbounds=[ib for ib in cfg.get('inbounds',[]) if ib.get('protocol')=='vless']
dup_ids=dup_em=0
all_ids=set()
for ib in inbounds:
    clients=ib.get('settings',{}).get('clients',[])
    ids=[(c.get('id') or '').strip() for c in clients if c.get('id')]
    emails=[(c.get('email') or '').strip().lower() for c in clients if c.get('email')]
    dup_ids += len([k for k,v in collections.Counter(ids).items() if v>1])
    dup_em += len([k for k,v in collections.Counter(emails).items() if v>1])
    all_ids.update(ids)
print(dup_ids, dup_em, len(all_ids), len(inbounds))
PY")" || rc=$?
  if [[ "${rc:-0}" != "0" ]]; then
    fail "replica $host unreachable via SSH key $SSH_KEY"
    return 0
  fi
  local d1 d2 total inbound_count
  read -r d1 d2 total inbound_count <<<"$out"
  local active runtime
  read -r active runtime <<<"$(ssh -n -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10 "root@$host" "if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx hexenvpn-xray; then echo active docker; elif [ \"\$(systemctl is-active xray 2>/dev/null || true)\" = active ]; then echo active systemd; else echo inactive unknown; fi" 2>/dev/null || echo "inactive unknown")"
  if [[ "$active" == "active" ]]; then
    ok "replica $host xray active (runtime=$runtime)"
  else
    fail "replica $host xray status=$active (runtime=$runtime)"
  fi
  if ssh -n -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10 "root@$host" \
    "ss -ltn 2>/dev/null | grep -q ':443 '"; then
    ok "replica $host port 443 listening"
  else
    fail "replica $host port 443 not listening"
  fi
  if [[ "$host" == "$TR_HOST" && "$TR_WS_ENABLED" == "1" ]]; then
    if ssh -n -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10 "root@$host" \
      "ss -ltn 2>/dev/null | grep -q ':${TR_WS_PORT} '"; then
      ok "replica $host WS TLS port $TR_WS_PORT listening"
    else
      fail "replica $host WS TLS port $TR_WS_PORT not listening"
    fi
  fi
  if [[ "$d1" == "0" && "$d2" == "0" ]]; then
    ok "replica $host duplicates: none (clients=$total inbounds=$inbound_count)"
  else
    fail "replica $host duplicates found (dup_ids=$d1 dup_emails=$d2 clients=$total)"
  fi

  if [[ -n "$CHECK_USER" ]]; then
    local cnt expected
    read -r cnt expected <<<"$(ssh -n -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10 "root@$host" "python3 - <<'PY'
import json
name='$CHECK_USER'.strip().lower()
cfg=json.load(open('/usr/local/etc/xray/config.json','r',encoding='utf-8'))
inbounds=[ib for ib in cfg.get('inbounds',[]) if ib.get('protocol')=='vless']
matched=sum(1 for ib in inbounds if sum(1 for c in ib.get('settings',{}).get('clients',[]) if (c.get('email') or '').strip().lower()==name)==1)
print(matched, len(inbounds))
PY" 2>/dev/null || echo "ERR")"
    if [[ "$expected" =~ ^[0-9]+$ && "$expected" -gt 0 && "$cnt" == "$expected" ]]; then
      ok "replica $host user '$CHECK_USER' exists once in every inbound ($cnt/$expected)"
    else
      fail "replica $host user '$CHECK_USER' inbound matches=$cnt/${expected:-0}"
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
