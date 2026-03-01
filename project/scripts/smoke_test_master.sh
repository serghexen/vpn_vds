#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage:
  smoke_test_master.sh [options]

Options:
  --repo-dir <path>            Repo directory (default: /opt/vpn_vds)
  --compose-file <path>        Compose file (default: project/docker-compose.master-full.yml)
  --base-url <url>             Base URL for HTTP checks (default: from project/env/bot.env BASE_URL)
  --check-user <name>          User for /sub/<user> and /i/<user> checks
  --skip-healthcheck           Skip healthcheck_master_replicas.sh
  --insecure                   Use curl -k for HTTPS checks
  --help                       Show help

Checks:
  1) docker containers hexenvpn-xray and hexenvpn-bot are Up
  2) port 443 is listening
  3) healthcheck_master_replicas.sh returns OK (unless skipped)
  4) optional HTTP checks:
     - GET <BASE_URL>/sub/<user> -> 200
     - GET <BASE_URL>/i/<user>   -> 200
USAGE
}

ok() { echo "OK   $*"; }
warn() { echo "WARN $*"; }
fail() { echo "FAIL $*"; FAILS=$((FAILS+1)); }

read_env_value() {
  local file="$1"
  local key="$2"
  [[ -f "$file" ]] || return 0
  awk -F= -v k="$key" '
    $0 ~ "^[[:space:]]*"k"=" {
      sub(/^[[:space:]]*/, "", $2)
      print $2
      exit
    }
  ' "$file"
}

http_code() {
  local url="$1"
  if [[ "$INSECURE" == "1" ]]; then
    curl -k -sS -o /dev/null -w '%{http_code}' "$url"
  else
    curl -sS -o /dev/null -w '%{http_code}' "$url"
  fi
}

REPO_DIR="/opt/vpn_vds"
COMPOSE_FILE="project/docker-compose.master-full.yml"
BASE_URL=""
CHECK_USER=""
SKIP_HEALTHCHECK=0
INSECURE=0
FAILS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-dir)
      REPO_DIR="${2:-}"; shift 2 ;;
    --compose-file)
      COMPOSE_FILE="${2:-}"; shift 2 ;;
    --base-url)
      BASE_URL="${2:-}"; shift 2 ;;
    --check-user)
      CHECK_USER="${2:-}"; shift 2 ;;
    --skip-healthcheck)
      SKIP_HEALTHCHECK=1; shift ;;
    --insecure)
      INSECURE=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1 ;;
  esac
done

if [[ ! -d "$REPO_DIR" ]]; then
  echo "Repo dir does not exist: $REPO_DIR" >&2
  exit 1
fi

cd "$REPO_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found" >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose is not available" >&2
  exit 1
fi

if [[ -z "$BASE_URL" ]]; then
  BASE_URL="$(read_env_value "$REPO_DIR/project/env/bot.env" "BASE_URL" || true)"
fi
BASE_URL="${BASE_URL%/}"

if [[ -z "$CHECK_USER" ]]; then
  CHECK_USER="$(read_env_value "$REPO_DIR/project/env/bot.env" "MONITOR_CHECK_USER" || true)"
fi

echo "== Smoke Test =="
echo "repo: $REPO_DIR"
echo "compose: $COMPOSE_FILE"
echo "base_url: ${BASE_URL:-<empty>}"
echo "check_user: ${CHECK_USER:-<empty>}"

if docker ps --format '{{.Names}}' | grep -qx 'hexenvpn-xray'; then
  ok "container hexenvpn-xray is Up"
else
  fail "container hexenvpn-xray is not running"
fi

if docker ps --format '{{.Names}}' | grep -qx 'hexenvpn-bot'; then
  ok "container hexenvpn-bot is Up"
else
  fail "container hexenvpn-bot is not running"
fi

if command -v ss >/dev/null 2>&1; then
  if ss -ltn | grep -q ':443 '; then
    ok "port 443 listening"
  else
    fail "port 443 not listening"
  fi
else
  warn "ss not available, port 443 check skipped"
fi

if [[ "$SKIP_HEALTHCHECK" == "0" ]]; then
  if [[ -n "$CHECK_USER" ]]; then
    if "$REPO_DIR/project/scripts/healthcheck_master_replicas.sh" --user "$CHECK_USER" >/dev/null 2>&1; then
      ok "healthcheck_master_replicas.sh OK (with user=$CHECK_USER)"
    else
      fail "healthcheck_master_replicas.sh failed (with user=$CHECK_USER)"
    fi
  else
    if "$REPO_DIR/project/scripts/healthcheck_master_replicas.sh" >/dev/null 2>&1; then
      ok "healthcheck_master_replicas.sh OK"
    else
      fail "healthcheck_master_replicas.sh failed"
    fi
  fi
else
  warn "healthcheck skipped"
fi

if [[ -n "$BASE_URL" && -n "$CHECK_USER" ]]; then
  code_sub="$(http_code "$BASE_URL/sub/$CHECK_USER" || echo "000")"
  if [[ "$code_sub" == "200" ]]; then
    ok "GET $BASE_URL/sub/$CHECK_USER -> 200"
  else
    fail "GET $BASE_URL/sub/$CHECK_USER -> $code_sub (expected 200)"
  fi

  code_i="$(http_code "$BASE_URL/i/$CHECK_USER" || echo "000")"
  if [[ "$code_i" == "200" ]]; then
    ok "GET $BASE_URL/i/$CHECK_USER -> 200"
  else
    fail "GET $BASE_URL/i/$CHECK_USER -> $code_i (expected 200)"
  fi
else
  warn "HTTP checks skipped (set BASE_URL and --check-user or MONITOR_CHECK_USER)"
fi

if [[ "$FAILS" -eq 0 ]]; then
  echo "RESULT: OK"
  exit 0
fi

echo "RESULT: FAIL ($FAILS)"
exit 2
