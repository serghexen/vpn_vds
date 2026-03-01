#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage:
  harden_master.sh [options]

Options:
  --install-deps               Install ufw + fail2ban via apt-get
  --ssh-port <port>            SSH port for UFW allow (default: 22)
  --allow-ports <csv>          Extra TCP ports for UFW (default: 443,8443)
  --skip-ssh                   Skip SSH hardening
  --skip-ufw                   Skip UFW hardening
  --skip-fail2ban              Skip fail2ban hardening
  --help                       Show help

What it does:
  1) Creates backup under /root/backup-hardening/<timestamp>
  2) Writes /etc/ssh/sshd_config.d/90-hexenvpn-hardening.conf (safe drop-in)
  3) Validates sshd config and reloads ssh service
  4) Configures UFW with allow: SSH + selected ports; default deny incoming
  5) Configures fail2ban jail for sshd and restarts fail2ban
USAGE
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Run as root (sudo -i)." >&2
    exit 1
  fi
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
  if [[ -e "$src" ]]; then
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
  fi
}

install_deps() {
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "apt-get not found. --install-deps supports Debian/Ubuntu only." >&2
    exit 1
  fi
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y ufw fail2ban
}

set_ssh_hardening() {
  mkdir -p /etc/ssh/sshd_config.d
  cat > /etc/ssh/sshd_config.d/90-hexenvpn-hardening.conf <<'EOF'
# Managed by project/scripts/harden_master.sh
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
PermitRootLogin prohibit-password
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding yes
ClientAliveInterval 300
ClientAliveCountMax 2
EOF

  sshd -t
  if systemctl is-active --quiet ssh; then
    systemctl reload ssh
  elif systemctl is-active --quiet sshd; then
    systemctl reload sshd
  else
    echo "WARN: ssh/sshd service not active, reload skipped"
  fi
}

set_ufw_hardening() {
  require_cmd ufw
  local ssh_port="$1"
  local allow_csv="$2"

  ufw --force default deny incoming
  ufw --force default allow outgoing

  ufw allow "${ssh_port}/tcp" comment 'ssh'

  IFS=',' read -r -a ports <<<"$allow_csv"
  for p in "${ports[@]}"; do
    p="$(echo "$p" | tr -d '[:space:]')"
    [[ -z "$p" ]] && continue
    if [[ "$p" =~ ^[0-9]+$ ]]; then
      ufw allow "${p}/tcp"
    else
      echo "WARN: skip invalid port '$p'"
    fi
  done

  ufw --force enable
}

set_fail2ban_hardening() {
  require_cmd fail2ban-client
  mkdir -p /etc/fail2ban/jail.d
  cat > /etc/fail2ban/jail.d/sshd.local <<'EOF'
[sshd]
enabled = true
backend = systemd
maxretry = 5
findtime = 10m
bantime = 1h
EOF
  systemctl enable --now fail2ban
  systemctl restart fail2ban || true

  if wait_fail2ban_ready; then
    return 0
  fi

  echo "WARN: fail2ban with backend=systemd failed, trying backend=auto + auth.log"
  cat > /etc/fail2ban/jail.d/sshd.local <<'EOF'
[sshd]
enabled = true
backend = auto
logpath = /var/log/auth.log
maxretry = 5
findtime = 10m
bantime = 1h
EOF
  systemctl restart fail2ban || true

  if wait_fail2ban_ready; then
    return 0
  fi

  echo "ERROR: fail2ban is not running after fallback config" >&2
  journalctl -u fail2ban --no-pager -n 80 || true
  return 1
}

wait_fail2ban_ready() {
  local i
  for i in 1 2 3 4 5 6; do
    if systemctl is-active --quiet fail2ban; then
      if fail2ban-client ping >/dev/null 2>&1 && fail2ban-client status sshd >/dev/null 2>&1; then
        return 0
      fi
    fi
    sleep 1
  done
  return 1
}

INSTALL_DEPS=0
DO_SSH=1
DO_UFW=1
DO_FAIL2BAN=1
SSH_PORT="22"
ALLOW_PORTS="443,8443"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-deps)
      INSTALL_DEPS=1; shift ;;
    --ssh-port)
      SSH_PORT="${2:-}"; shift 2 ;;
    --allow-ports)
      ALLOW_PORTS="${2:-}"; shift 2 ;;
    --skip-ssh)
      DO_SSH=0; shift ;;
    --skip-ufw)
      DO_UFW=0; shift ;;
    --skip-fail2ban)
      DO_FAIL2BAN=0; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1 ;;
  esac
done

require_root
require_cmd systemctl
require_cmd sshd

if [[ ! "$SSH_PORT" =~ ^[0-9]+$ ]]; then
  echo "--ssh-port must be numeric" >&2
  exit 1
fi

TS="$(date +%F_%H-%M-%S)"
BKP_DIR="/root/backup-hardening/$TS"
mkdir -p "$BKP_DIR"

safe_copy /etc/ssh/sshd_config "$BKP_DIR/etc/ssh/sshd_config"
safe_copy /etc/ssh/sshd_config.d "$BKP_DIR/etc/ssh/sshd_config.d"
safe_copy /etc/fail2ban "$BKP_DIR/etc/fail2ban"
safe_copy /etc/ufw "$BKP_DIR/etc/ufw"

echo "[hardening] backup: $BKP_DIR"

if [[ "$INSTALL_DEPS" == "1" ]]; then
  install_deps
fi

if [[ "$DO_SSH" == "1" ]]; then
  set_ssh_hardening
  echo "[hardening] ssh: OK"
else
  echo "[hardening] ssh: skipped"
fi

if [[ "$DO_UFW" == "1" ]]; then
  set_ufw_hardening "$SSH_PORT" "$ALLOW_PORTS"
  echo "[hardening] ufw: OK"
else
  echo "[hardening] ufw: skipped"
fi

if [[ "$DO_FAIL2BAN" == "1" ]]; then
  set_fail2ban_hardening
  echo "[hardening] fail2ban: OK"
else
  echo "[hardening] fail2ban: skipped"
fi

echo "Done."
