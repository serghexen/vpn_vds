#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT_DIR/runtime/bot" "$ROOT_DIR/runtime/vless-sub" "$ROOT_DIR/runtime/xray" "$ROOT_DIR/runtime/sub" "$ROOT_DIR/env/ssh"

if [[ ! -f "$ROOT_DIR/runtime/vless-sub/clients.json" ]]; then
  echo "[]" > "$ROOT_DIR/runtime/vless-sub/clients.json"
fi

if [[ ! -f "$ROOT_DIR/runtime/xray/config.json" ]]; then
  cp "$ROOT_DIR/xray/config.template.json" "$ROOT_DIR/runtime/xray/config.json"
  echo "Created runtime/xray/config.json from template. Fill real keys/clients before start."
fi

if [[ ! -f "$ROOT_DIR/env/bot.env" ]]; then
  cp "$ROOT_DIR/env/bot.env.example" "$ROOT_DIR/env/bot.env"
  echo "Created env/bot.env from example. Fill BOT_TOKEN and admin settings."
fi

if [[ ! -f "$ROOT_DIR/env/nodes.env" ]]; then
  cp "$ROOT_DIR/env/nodes.env.example" "$ROOT_DIR/env/nodes.env"
  echo "Created env/nodes.env from example. Fill MASTER_PBK and optional replica params."
fi

echo "Runtime dirs initialized."
