#!/usr/bin/env bash
set -euo pipefail

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

pct() {
  local used="${1:-0}"
  local total="${2:-0}"
  awk -v u="$used" -v t="$total" 'BEGIN { if (t<=0) print "n/a"; else printf "%.1f%%", (u*100.0/t) }'
}

HOSTNAME_VAL="$(run_host 'hostname 2>/dev/null || echo unknown')"
UPTIME_VAL="$(run_host 'uptime -p 2>/dev/null || uptime 2>/dev/null || true')"
LOAD_VAL="$(run_host "awk '{print \$1\" \"\$2\" \"\$3}' /proc/loadavg 2>/dev/null || echo n/a")"
CPU_VAL="$(run_host 'getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo n/a')"
MEM_LINE="$(run_host "free -b 2>/dev/null | awk '/^Mem:/ {print \$2\" \"\$3\" \"\$7}' || true")"
DISK_LINE="$(run_host "df -P / 2>/dev/null | awk 'NR==2 {print \$2\" \"\$3\" \"\$4\" \"\$5}' || true")"

MEM_TOTAL_B=0
MEM_USED_B=0
MEM_AVAIL_B=0
if [[ -n "$MEM_LINE" ]]; then
  read -r MEM_TOTAL_B MEM_USED_B MEM_AVAIL_B <<<"$MEM_LINE"
fi

DISK_TOTAL_K=0
DISK_USED_K=0
DISK_FREE_K=0
DISK_PCT="n/a"
if [[ -n "$DISK_LINE" ]]; then
  read -r DISK_TOTAL_K DISK_USED_K DISK_FREE_K DISK_PCT <<<"$DISK_LINE"
fi

MEM_TOTAL_H="$(human_bytes "$MEM_TOTAL_B")"
MEM_USED_H="$(human_bytes "$MEM_USED_B")"
MEM_AVAIL_H="$(human_bytes "$MEM_AVAIL_B")"
MEM_PCT="$(pct "$MEM_USED_B" "$MEM_TOTAL_B")"

DISK_TOTAL_B="$((DISK_TOTAL_K * 1024))"
DISK_USED_B="$((DISK_USED_K * 1024))"
DISK_FREE_B="$((DISK_FREE_K * 1024))"
DISK_TOTAL_H="$(human_bytes "$DISK_TOTAL_B")"
DISK_USED_H="$(human_bytes "$DISK_USED_B")"
DISK_FREE_H="$(human_bytes "$DISK_FREE_B")"

BOT_DB_SIZE_B="$(run_host 'stat -c %s /var/lib/hexenvpn-bot/bot.db 2>/dev/null || echo 0')"
CLIENTS_SIZE_B="$(run_host 'stat -c %s /var/lib/vless-sub/clients.json 2>/dev/null || echo 0')"
BOT_DB_H="$(human_bytes "$BOT_DB_SIZE_B")"
CLIENTS_H="$(human_bytes "$CLIENTS_SIZE_B")"

XRAY_STATE="n/a"
XRAY_RESTARTS="n/a"
BOT_STATE="n/a"
BOT_RESTARTS="n/a"
if run_host 'command -v docker >/dev/null 2>&1'; then
  XRAY_STATE="$(run_host "docker inspect -f '{{.State.Status}}' hexenvpn-xray 2>/dev/null || echo missing")"
  XRAY_RESTARTS="$(run_host "docker inspect -f '{{.RestartCount}}' hexenvpn-xray 2>/dev/null || echo n/a")"
  BOT_STATE="$(run_host "docker inspect -f '{{.State.Status}}' hexenvpn-bot 2>/dev/null || echo missing")"
  BOT_RESTARTS="$(run_host "docker inspect -f '{{.RestartCount}}' hexenvpn-bot 2>/dev/null || echo n/a")"
fi

echo "📊 Состояние узла"
echo "Host: $HOSTNAME_VAL"
echo "Uptime: $UPTIME_VAL"
echo "Load(1/5/15): $LOAD_VAL | CPU: $CPU_VAL"
echo "RAM: used=$MEM_USED_H total=$MEM_TOTAL_H avail=$MEM_AVAIL_H use=$MEM_PCT"
echo "Disk /: used=$DISK_USED_H total=$DISK_TOTAL_H free=$DISK_FREE_H use=$DISK_PCT"
echo "Docker xray: state=$XRAY_STATE restarts=$XRAY_RESTARTS"
echo "Docker bot: state=$BOT_STATE restarts=$BOT_RESTARTS"
echo "bot.db: $BOT_DB_H"
echo "clients.json: $CLIENTS_H"
