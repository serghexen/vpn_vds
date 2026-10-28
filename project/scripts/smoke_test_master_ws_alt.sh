#!/usr/bin/env bash
set -Eeuo pipefail

USER_NAME="${1:-}"
SUB_DIR="${SUB_DIR:-/var/www/sub}"
TEST_PORT="${TEST_PORT:-12080}"
IMAGE="${XRAY_IMAGE:-ghcr.io/xtls/xray-core:latest}"

if [[ -z "$USER_NAME" ]]; then
  echo "Usage: smoke_test_master_ws_alt.sh <vpn_name>" >&2
  exit 1
fi
if [[ ! "$USER_NAME" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Invalid vpn_name" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d /tmp/hexenvpn-ws-alt-test.XXXXXX)"
CONTAINER="hexenvpn-ws-alt-test-$$"
cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

SUB_FILE="$SUB_DIR/$USER_NAME" OUT_FILE="$TMP_DIR/client.json" TEST_PORT="$TEST_PORT" python3 - <<'PY'
import base64
import json
import os
import urllib.parse
from pathlib import Path

lines = base64.b64decode(Path(os.environ['SUB_FILE']).read_text().strip(), validate=True).decode().splitlines()
selected = None
for line in lines:
    parsed = urllib.parse.urlsplit(line)
    query = {key: values[0] for key, values in urllib.parse.parse_qs(parsed.query).items()}
    if parsed.scheme == 'vless' and query.get('type') == 'ws' and query.get('security') == 'tls':
        selected = (parsed, query)
        break
if selected is None:
    raise SystemExit('WS+TLS link not found in subscription')

parsed, query = selected
config = {
    'log': {'loglevel': 'warning'},
    'inbounds': [{
        'listen': '127.0.0.1',
        'port': int(os.environ['TEST_PORT']),
        'protocol': 'socks',
        'settings': {'auth': 'noauth', 'udp': True},
    }],
    'outbounds': [{
        'protocol': 'vless',
        'settings': {'vnext': [{
            'address': '127.0.0.1',
            'port': parsed.port,
            'users': [{'id': parsed.username, 'encryption': 'none'}],
        }]},
        'streamSettings': {
            'network': 'ws',
            'security': 'tls',
            'tlsSettings': {
                'serverName': query.get('sni') or parsed.hostname,
                'fingerprint': query.get('fp', 'chrome'),
            },
            'wsSettings': {
                'path': query.get('path', '/'),
                'headers': {'Host': query.get('host') or query.get('sni') or parsed.hostname},
            },
        },
    }],
}
path = Path(os.environ['OUT_FILE'])
path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
path.chmod(0o600)
PY

docker run -d --name "$CONTAINER" --network host --user 0:0 \
  -v "$TMP_DIR/client.json:/usr/local/etc/xray/config.json:ro" \
  "$IMAGE" run -config /usr/local/etc/xray/config.json >/dev/null

sleep 1
if [[ "$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || true)" != "running" ]]; then
  docker logs "$CONTAINER" >&2 || true
  echo "RESULT: FAIL (client container exited)" >&2
  exit 2
fi

for _ in $(seq 1 10); do
  if curl -fsS --connect-timeout 3 --max-time 8 --socks5-hostname "127.0.0.1:$TEST_PORT" https://api.ipify.org >"$TMP_DIR/exit-ip"; then
    break
  fi
  sleep 1
done

[[ -s "$TMP_DIR/exit-ip" ]] || {
  docker logs "$CONTAINER" >&2 || true
  echo "RESULT: FAIL" >&2
  exit 2
}

echo "EXIT_IP=$(cat "$TMP_DIR/exit-ip")"
echo "RESULT: OK"
