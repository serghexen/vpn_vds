#!/usr/bin/env bash
set -euo pipefail

CLIENTS_JSON="${CLIENTS_JSON:-/var/lib/vless-sub/clients.json}"
XRAY_CFG="${XRAY_CFG:-/usr/local/etc/xray/config.json}"
GRACE_DAYS="${GRACE_DAYS:-${SYNC_GRACE_DAYS:-1}}"
SAMPLE_SEC="${SAMPLE_SEC:-2}"

HOST_RUN=()
if command -v nsenter >/dev/null 2>&1; then
  HOST_RUN=(nsenter -t 1 -m -u -i -n -p)
fi

run_host() {
  if [[ "${#HOST_RUN[@]}" -gt 0 ]]; then
    "${HOST_RUN[@]}" sh -lc "$1"
  else
    sh -lc "$1"
  fi
}

human_bytes() {
  local bytes="${1:-0}"
  awk -v b="$bytes" '
    function fmt(v, u) { return sprintf("%.2f %s", v, u) }
    BEGIN {
      if (b < 1024) { print b " B"; exit }
      if (b < 1024*1024) { print fmt(b/1024, "KiB"); exit }
      if (b < 1024*1024*1024) { print fmt(b/1024/1024, "MiB"); exit }
      if (b < 1024*1024*1024*1024) { print fmt(b/1024/1024/1024, "GiB"); exit }
      print fmt(b/1024/1024/1024/1024, "TiB")
    }
  '
}

pct_val() {
  local used="${1:-0}"
  local total="${2:-0}"
  awk -v u="$used" -v t="$total" 'BEGIN { if (t<=0) print "0.0"; else printf "%.1f", (u*100.0/t) }'
}

if [[ ! "$SAMPLE_SEC" =~ ^[0-9]+$ ]] || [[ "$SAMPLE_SEC" -lt 1 ]]; then
  SAMPLE_SEC=2
fi

HOSTNAME_VAL="$(run_host 'hostname 2>/dev/null || echo unknown')"
UPTIME_VAL="$(run_host 'uptime -p 2>/dev/null || uptime 2>/dev/null || true')"
CPU_VAL="$(run_host 'getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 1')"
LOAD1="$(run_host "awk '{print \$1}' /proc/loadavg 2>/dev/null || echo 0")"
MEM_LINE="$(run_host "free -b 2>/dev/null | awk '/^Mem:/ {print \$2\" \"\$3\" \"\$7}' || echo '0 0 0'")"
DISK_LINE="$(run_host "df -P / 2>/dev/null | awk 'NR==2 {print \$2\" \"\$3\" \"\$4\" \"\$5}' || echo '0 0 0 0%'")"

read -r MEM_TOTAL_B MEM_USED_B MEM_AVAIL_B <<<"$MEM_LINE"
read -r DISK_TOTAL_K DISK_USED_K DISK_FREE_K DISK_PCT_STR <<<"$DISK_LINE"

DISK_TOTAL_B="$((DISK_TOTAL_K * 1024))"
DISK_USED_B="$((DISK_USED_K * 1024))"
DISK_FREE_B="$((DISK_FREE_K * 1024))"

MEM_USED_PCT="$(pct_val "$MEM_USED_B" "$MEM_TOTAL_B")"
DISK_USED_PCT="$(echo "$DISK_PCT_STR" | tr -cd '0-9.')"
if [[ -z "$DISK_USED_PCT" ]]; then
  DISK_USED_PCT="0.0"
fi

MEM_TOTAL_H="$(human_bytes "$MEM_TOTAL_B")"
MEM_USED_H="$(human_bytes "$MEM_USED_B")"
MEM_AVAIL_H="$(human_bytes "$MEM_AVAIL_B")"
DISK_TOTAL_H="$(human_bytes "$DISK_TOTAL_B")"
DISK_USED_H="$(human_bytes "$DISK_USED_B")"
DISK_FREE_H="$(human_bytes "$DISK_FREE_B")"

NET_DEV="$(run_host "ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if(\$i==\"dev\") {print \$(i+1); exit}}' || true")"
if [[ -z "$NET_DEV" ]]; then
  NET_DEV="$(run_host "ip route 2>/dev/null | awk '/default/ {print \$5; exit}' || true")"
fi
if [[ -z "$NET_DEV" ]]; then
  NET_DEV="eth0"
fi

NET_SPEED_MBIT="$(run_host "cat /sys/class/net/$NET_DEV/speed 2>/dev/null || echo unknown")"
if [[ "$NET_SPEED_MBIT" == "-1" || -z "$NET_SPEED_MBIT" ]]; then
  NET_SPEED_MBIT="unknown"
fi
RX1_TX1="$(run_host "awk -v dev='$NET_DEV' -F'[: ]+' '\$1==dev {print \$3\" \"\$11}' /proc/net/dev 2>/dev/null || echo '0 0'")"
sleep "$SAMPLE_SEC"
RX2_TX2="$(run_host "awk -v dev='$NET_DEV' -F'[: ]+' '\$1==dev {print \$3\" \"\$11}' /proc/net/dev 2>/dev/null || echo '0 0'")"
read -r RX1 TX1 <<<"$RX1_TX1"
read -r RX2 TX2 <<<"$RX2_TX2"

RX_RATE_MBIT="$(awk -v a="$RX1" -v b="$RX2" -v s="$SAMPLE_SEC" 'BEGIN { d=b-a; if (d<0||s<=0) d=0; printf "%.2f", (d*8.0)/(s*1000000.0) }')"
TX_RATE_MBIT="$(awk -v a="$TX1" -v b="$TX2" -v s="$SAMPLE_SEC" 'BEGIN { d=b-a; if (d<0||s<=0) d=0; printf "%.2f", (d*8.0)/(s*1000000.0) }')"

read -r ACTIVE_CNT GRACE_CNT SUSP_CNT TOTAL_CNT < <(
python3 - "$CLIENTS_JSON" "$GRACE_DAYS" <<'PY'
import json, sys, time
path=sys.argv[1]
grace_days=int(sys.argv[2] or 1)
now=int(time.time())
grace_sec=grace_days*86400
active=grace=susp=0
try:
    rows=json.load(open(path,'r',encoding='utf-8'))
except Exception:
    rows=[]
for r in rows:
    if r.get('revoked', False):
        susp += 1
        continue
    exp=int(r.get('expire',0) or 0)
    if exp<=0 or now<=exp:
        active += 1
    elif now<=exp+grace_sec:
        grace += 1
    else:
        susp += 1
print(active, grace, susp, len(rows))
PY
)

XRAY_ACTIVE_NOW="$(
python3 - "$XRAY_CFG" <<'PY'
import json, sys
path=sys.argv[1]
try:
    cfg=json.load(open(path,'r',encoding='utf-8'))
except Exception:
    print(0); raise SystemExit
total=0
for ib in cfg.get('inbounds',[]):
    if ib.get('protocol')!='vless':
        continue
    total += len(ib.get('settings',{}).get('clients',[]))
print(total)
PY
)"

CAPACITY_JSON="$(
python3 - "$CPU_VAL" "$LOAD1" "$MEM_TOTAL_B" "$MEM_USED_B" "$DISK_USED_PCT" "$ACTIVE_CNT" "$GRACE_CNT" <<'PY'
import json, sys
cpu=max(1,float(sys.argv[1] or 1))
load1=max(0.0,float(sys.argv[2] or 0))
mem_total=max(1,float(sys.argv[3] or 1))
mem_used=max(0.0,float(sys.argv[4] or 0))
disk_pct=max(0.0,float(sys.argv[5] or 0))
active=int(sys.argv[6] or 0)
grace=int(sys.argv[7] or 0)

load_ratio=load1/cpu
mem_ratio=mem_used/mem_total
disk_ratio=disk_pct/100.0
pressure=max(load_ratio, mem_ratio, disk_ratio)

# Conservative heuristic for VLESS Reality mixed traffic.
cpu_cap=int(cpu*120)
mem_cap=int((mem_total/(1024**3))*250)
theoretical_base=max(20, min(cpu_cap, mem_cap if mem_cap>0 else cpu_cap))

# Practical production baseline (intentionally lower than theoretical).
practical_cpu_cap=int(cpu*50)
practical_mem_cap=int((mem_total/(1024**3))*120)
practical_base=max(20, min(practical_cpu_cap, practical_mem_cap if practical_mem_cap>0 else practical_cpu_cap))

if pressure < 0.50:
    factor=1.00
elif pressure < 0.70:
    factor=0.80
elif pressure < 0.85:
    factor=0.60
elif pressure < 0.95:
    factor=0.40
else:
    factor=0.20

recommended_theoretical=max(20, int(theoretical_base*factor))
recommended_practical=max(20, int(practical_base*factor))
current=max(0, active+grace)
headroom=recommended_practical-current

if headroom >= max(10, int(recommended_practical*0.20)):
    status="OK"
elif headroom >= 0:
    status="WARN"
else:
    status="CRITICAL"

print(json.dumps({
    "cpu_cap": cpu_cap,
    "mem_cap": mem_cap,
    "theoretical_base": theoretical_base,
    "practical_cpu_cap": practical_cpu_cap,
    "practical_mem_cap": practical_mem_cap,
    "practical_base": practical_base,
    "pressure": round(pressure,3),
    "load_ratio": round(load_ratio,3),
    "mem_ratio": round(mem_ratio,3),
    "disk_ratio": round(disk_ratio,3),
    "recommended_theoretical": recommended_theoretical,
    "recommended_practical": recommended_practical,
    "current": current,
    "headroom": headroom,
    "status": status
}))
PY
)"

CAP_CPU="$(python3 - <<PY
import json
o=json.loads('''$CAPACITY_JSON''')
print(o["cpu_cap"])
PY
)"
CAP_MEM="$(python3 - <<PY
import json
o=json.loads('''$CAPACITY_JSON''')
print(o["mem_cap"])
PY
)"
CAP_BASE_THEO="$(python3 - <<PY
import json
o=json.loads('''$CAPACITY_JSON''')
print(o["theoretical_base"])
PY
)"
CAP_PRACT_CPU="$(python3 - <<PY
import json
o=json.loads('''$CAPACITY_JSON''')
print(o["practical_cpu_cap"])
PY
)"
CAP_PRACT_MEM="$(python3 - <<PY
import json
o=json.loads('''$CAPACITY_JSON''')
print(o["practical_mem_cap"])
PY
)"
CAP_PRACT_BASE="$(python3 - <<PY
import json
o=json.loads('''$CAPACITY_JSON''')
print(o["practical_base"])
PY
)"
CAP_PRESSURE="$(python3 - <<PY
import json
o=json.loads('''$CAPACITY_JSON''')
print(o["pressure"])
PY
)"
CAP_REC_THEO="$(python3 - <<PY
import json
o=json.loads('''$CAPACITY_JSON''')
print(o["recommended_theoretical"])
PY
)"
CAP_REC_PRACT="$(python3 - <<PY
import json
o=json.loads('''$CAPACITY_JSON''')
print(o["recommended_practical"])
PY
)"
CAP_HEADROOM="$(python3 - <<PY
import json
o=json.loads('''$CAPACITY_JSON''')
print(o["headroom"])
PY
)"
CAP_STATUS="$(python3 - <<PY
import json
o=json.loads('''$CAPACITY_JSON''')
print(o["status"])
PY
)"

echo "📈 Capacity Estimate (heuristic)"
echo "Host: $HOSTNAME_VAL"
echo "Uptime: $UPTIME_VAL"
echo "CPU: $CPU_VAL vCPU | Load1: $LOAD1 | load_ratio=$(python3 - <<PY
import json
print(json.loads('''$CAPACITY_JSON''')["load_ratio"])
PY
)"
echo "RAM: used=$MEM_USED_H total=$MEM_TOTAL_H avail=$MEM_AVAIL_H use=${MEM_USED_PCT}%"
echo "Disk /: used=$DISK_USED_H total=$DISK_TOTAL_H free=$DISK_FREE_H use=${DISK_USED_PCT}%"
echo "Network: dev=$NET_DEV speed=${NET_SPEED_MBIT}Mbps rx=${RX_RATE_MBIT}Mbps tx=${TX_RATE_MBIT}Mbps (sample ${SAMPLE_SEC}s)"
echo "Users: active=$ACTIVE_CNT grace=$GRACE_CNT suspended=$SUSP_CNT total=$TOTAL_CNT xray_current=$XRAY_ACTIVE_NOW"
echo "Capacity model: pressure=$CAP_PRESSURE"
echo "Theoretical: cpu_cap=$CAP_CPU mem_cap=$CAP_MEM base=$CAP_BASE_THEO recommended=$CAP_REC_THEO"
echo "Practical: cpu_cap=$CAP_PRACT_CPU mem_cap=$CAP_PRACT_MEM base=$CAP_PRACT_BASE recommended=$CAP_REC_PRACT"
echo "Headroom (practical): $CAP_HEADROOM"
echo "Status: $CAP_STATUS"
if [[ "$CAP_STATUS" == "CRITICAL" ]]; then
  echo "Advice: ограничить новые выдачи и добавить реплику/ресурсы."
elif [[ "$CAP_STATUS" == "WARN" ]]; then
  echo "Advice: запас маленький, планируйте расширение."
else
  echo "Advice: запас по текущей нагрузке нормальный."
fi
