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
  healthcheck_ru_tr_bridge.sh [--user <name>] [--nodes-env <path>]

Checks (only when bridge mode is enabled):
  - RU (TR_LINK_HOST) and TR (TR_HOST) reachable by SSH
  - xray active on RU and TR
  - RU inbound accepts users, contains CHECK_USER (optional)
  - RU outbound points to TR host:port and has bridge UUID
  - bridge UUID exists on TR inbound
  - RU outbound REALITY publicKey == actual TR publicKey
  - TR_LINK_PBK (or TR_PBK fallback) == actual RU publicKey
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
TR_HOST="${TR_HOST:-}"
TR_LINK_HOST="${TR_LINK_HOST:-}"
TR_VLESS_PORT="${TR_VLESS_PORT:-443}"
TR_SNI="${TR_SNI:-www.yahoo.com}"
TR_SID="${TR_SID:-ffffffffff}"
TR_LINK_PBK_EFFECTIVE="${TR_LINK_PBK:-${TR_PBK:-}}"

ok() { echo "OK   $*"; }
warn() { echo "WARN $*"; }
fail() { echo "FAIL $*"; FAILS=$((FAILS+1)); }

if [[ -z "$TR_HOST" || -z "$TR_LINK_HOST" ]]; then
  echo "WARN bridge check skipped: TR_HOST/TR_LINK_HOST is empty"
  echo "RESULT: SKIP"
  exit 0
fi

if [[ "$TR_HOST" == "$TR_LINK_HOST" ]]; then
  echo "WARN bridge check skipped: TR_LINK_HOST equals TR_HOST (direct TR mode)"
  echo "RESULT: SKIP"
  exit 0
fi

remote_run() {
  local host="$1"
  local cmd="$2"
  ssh -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10 "root@$host" "$cmd"
}

remote_state() {
  local host="$1"
  remote_run "$host" "if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx hexenvpn-xray; then echo active docker; elif [ \"\$(systemctl is-active xray 2>/dev/null || true)\" = active ]; then echo active systemd; else echo inactive unknown; fi"
}

remote_public_from_private() {
  local host="$1"
  remote_run "$host" "python3 - <<'PY'
import json
cfg=json.load(open('/usr/local/etc/xray/config.json','r',encoding='utf-8'))
ib=next((x for x in cfg.get('inbounds',[]) if x.get('protocol')=='vless'),{})
print(ib.get('streamSettings',{}).get('realitySettings',{}).get('privateKey',''))
PY"
}

calc_pubkey_remote() {
  local host="$1"
  local private_key="$2"
  remote_run "$host" "if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx hexenvpn-xray; then docker exec hexenvpn-xray xray x25519 -i '$private_key'; elif command -v xray >/dev/null 2>&1; then xray x25519 -i '$private_key'; else exit 7; fi" \
    | awk -F': ' '/Password \(PublicKey\):/{print $2; exit}'
}

echo "== RU->TR Bridge =="
echo "RU=$TR_LINK_HOST TR=$TR_HOST"

if ! remote_run "$TR_LINK_HOST" "echo RU_OK" >/dev/null 2>&1; then
  fail "RU host $TR_LINK_HOST unreachable via SSH key $SSH_KEY"
fi
if ! remote_run "$TR_HOST" "echo TR_OK" >/dev/null 2>&1; then
  fail "TR host $TR_HOST unreachable via SSH key $SSH_KEY"
fi

if [[ "$FAILS" -gt 0 ]]; then
  echo "RESULT: FAIL ($FAILS)"
  exit 2
fi

read -r ru_active ru_runtime <<<"$(remote_state "$TR_LINK_HOST" 2>/dev/null || echo "inactive unknown")"
if [[ "$ru_active" == "active" ]]; then
  ok "RU xray active (runtime=$ru_runtime)"
else
  fail "RU xray status=$ru_active (runtime=$ru_runtime)"
fi

read -r tr_active tr_runtime <<<"$(remote_state "$TR_HOST" 2>/dev/null || echo "inactive unknown")"
if [[ "$tr_active" == "active" ]]; then
  ok "TR xray active (runtime=$tr_runtime)"
else
  fail "TR xray status=$tr_active (runtime=$tr_runtime)"
fi

ru_info="$(remote_run "$TR_LINK_HOST" "TR_HOST='$TR_HOST' CHECK_USER='$CHECK_USER' python3 - <<'PY'
import json, os
cfg=json.load(open('/usr/local/etc/xray/config.json','r',encoding='utf-8'))
ib=next((x for x in cfg.get('inbounds',[]) if x.get('protocol')=='vless'), {})
clients=ib.get('settings',{}).get('clients',[])
rs_in=ib.get('streamSettings',{}).get('realitySettings',{})
chk=(os.environ.get('CHECK_USER','') or '').strip().lower()
chk_cnt=sum(1 for c in clients if (c.get('email') or '').strip().lower()==chk) if chk else -1

out=None
for ob in cfg.get('outbounds',[]):
    if ob.get('protocol')!='vless':
        continue
    vnext=((ob.get('settings') or {}).get('vnext') or [{}])[0]
    if (vnext.get('address') or '') == os.environ.get('TR_HOST',''):
        out=ob
        break
if out is None:
    out=next((x for x in cfg.get('outbounds',[]) if x.get('tag')=='to-tr'), {})

vnext=((out.get('settings') or {}).get('vnext') or [{}])[0]
users=vnext.get('users') or [{}]
rs_out=(out.get('streamSettings') or {}).get('realitySettings') or {}
print(f'RU_CLIENTS={len(clients)}')
print(f'RU_CHECK_USER_COUNT={chk_cnt}')
print('RU_IN_SERVERNAMES=' + ','.join(rs_in.get('serverNames') or []))
print('RU_IN_SHORTIDS=' + ','.join(rs_in.get('shortIds') or []))
print('RU_IN_PRIVATE=' + (rs_in.get('privateKey') or ''))
print('RU_OUT_ADDR=' + str(vnext.get('address') or ''))
print('RU_OUT_PORT=' + str(vnext.get('port') or ''))
print('RU_OUT_UUID=' + str(users[0].get('id') or ''))
print('RU_OUT_SERVERNAME=' + str(rs_out.get('serverName') or ''))
print('RU_OUT_SHORTID=' + str(rs_out.get('shortId') or ''))
print('RU_OUT_PBK=' + str(rs_out.get('publicKey') or ''))
PY")"

tr_info="$(remote_run "$TR_HOST" "CHECK_USER='$CHECK_USER' python3 - <<'PY'
import json, os
cfg=json.load(open('/usr/local/etc/xray/config.json','r',encoding='utf-8'))
ib=next((x for x in cfg.get('inbounds',[]) if x.get('protocol')=='vless'), {})
clients=ib.get('settings',{}).get('clients',[])
rs=ib.get('streamSettings',{}).get('realitySettings',{})
chk=(os.environ.get('CHECK_USER','') or '').strip().lower()
chk_cnt=sum(1 for c in clients if (c.get('email') or '').strip().lower()==chk) if chk else -1
ids='|'.join((c.get('id') or '').strip() for c in clients if c.get('id'))
print(f'TR_CLIENTS={len(clients)}')
print(f'TR_CHECK_USER_COUNT={chk_cnt}')
print('TR_IDS=' + ids)
print('TR_IN_SERVERNAMES=' + ','.join(rs.get('serverNames') or []))
print('TR_IN_SHORTIDS=' + ','.join(rs.get('shortIds') or []))
print('TR_IN_PRIVATE=' + (rs.get('privateKey') or ''))
PY")"

kv() {
  local blob="$1"
  local key="$2"
  printf '%s\n' "$blob" | awk -F= -v k="$key" '$1==k {sub(/^[^=]*=/,""); print; exit}'
}

ru_clients="$(kv "$ru_info" RU_CLIENTS)"
ru_check_cnt="$(kv "$ru_info" RU_CHECK_USER_COUNT)"
ru_in_names="$(kv "$ru_info" RU_IN_SERVERNAMES)"
ru_in_sids="$(kv "$ru_info" RU_IN_SHORTIDS)"
ru_in_private="$(kv "$ru_info" RU_IN_PRIVATE)"
ru_out_addr="$(kv "$ru_info" RU_OUT_ADDR)"
ru_out_port="$(kv "$ru_info" RU_OUT_PORT)"
ru_out_uuid="$(kv "$ru_info" RU_OUT_UUID)"
ru_out_sni="$(kv "$ru_info" RU_OUT_SERVERNAME)"
ru_out_sid="$(kv "$ru_info" RU_OUT_SHORTID)"
ru_out_pbk="$(kv "$ru_info" RU_OUT_PBK)"

tr_clients="$(kv "$tr_info" TR_CLIENTS)"
tr_check_cnt="$(kv "$tr_info" TR_CHECK_USER_COUNT)"
tr_ids="$(kv "$tr_info" TR_IDS)"
tr_in_private="$(kv "$tr_info" TR_IN_PRIVATE)"

if [[ -n "$ru_clients" && "$ru_clients" -gt 0 ]]; then
  ok "RU inbound clients=$ru_clients"
else
  fail "RU inbound clients is empty"
fi

if [[ -n "$CHECK_USER" ]]; then
  if [[ "$ru_check_cnt" == "1" ]]; then
    ok "RU has user '$CHECK_USER' exactly once"
  else
    fail "RU user '$CHECK_USER' count=$ru_check_cnt (expected 1)"
  fi
  if [[ "$tr_check_cnt" == "1" ]]; then
    ok "TR has user '$CHECK_USER' exactly once"
  else
    fail "TR user '$CHECK_USER' count=$tr_check_cnt (expected 1)"
  fi
fi

if [[ "$ru_out_addr" == "$TR_HOST" && "$ru_out_port" == "$TR_VLESS_PORT" ]]; then
  ok "RU outbound points to TR ($ru_out_addr:$ru_out_port)"
else
  fail "RU outbound target mismatch ($ru_out_addr:$ru_out_port expected $TR_HOST:$TR_VLESS_PORT)"
fi

if [[ -n "$ru_out_uuid" && "$tr_ids" == *"$ru_out_uuid"* ]]; then
  ok "bridge UUID exists on TR ($ru_out_uuid)"
else
  fail "bridge UUID missing on TR (uuid=$ru_out_uuid)"
fi

if [[ "$ru_out_sni" == "$TR_SNI" ]]; then
  ok "RU outbound serverName matches TR_SNI ($TR_SNI)"
else
  fail "RU outbound serverName mismatch ($ru_out_sni expected $TR_SNI)"
fi

if [[ "$ru_out_sid" == "$TR_SID" ]]; then
  ok "RU outbound shortId matches TR_SID ($TR_SID)"
else
  fail "RU outbound shortId mismatch ($ru_out_sid expected $TR_SID)"
fi

if [[ -z "$tr_in_private" ]]; then
  fail "TR inbound REALITY private key is empty"
else
  tr_pub="$(calc_pubkey_remote "$TR_HOST" "$tr_in_private" || true)"
  if [[ -z "$tr_pub" ]]; then
    fail "unable to derive TR public key from private key"
  elif [[ "$ru_out_pbk" == "$tr_pub" ]]; then
    ok "RU outbound publicKey matches TR public key"
  else
    fail "RU outbound publicKey mismatch (got=$ru_out_pbk expected=$tr_pub)"
  fi
fi

if [[ -z "$ru_in_private" ]]; then
  fail "RU inbound REALITY private key is empty"
else
  ru_pub="$(calc_pubkey_remote "$TR_LINK_HOST" "$ru_in_private" || true)"
  if [[ -z "$ru_pub" ]]; then
    fail "unable to derive RU public key from private key"
  elif [[ -z "$TR_LINK_PBK_EFFECTIVE" ]]; then
    fail "TR_LINK_PBK/TR_PBK is empty in nodes env"
  elif [[ "$TR_LINK_PBK_EFFECTIVE" == "$ru_pub" ]]; then
    ok "TR_LINK_PBK matches RU public key"
  else
    fail "TR_LINK_PBK mismatch (got=$TR_LINK_PBK_EFFECTIVE expected=$ru_pub)"
  fi
fi

if [[ "$FAILS" -eq 0 ]]; then
  echo "RESULT: OK"
  exit 0
fi

echo "RESULT: FAIL ($FAILS)"
exit 2
