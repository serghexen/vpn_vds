#!/usr/bin/env python3
"""Add an isolated VLESS WebSocket inbound to an existing master config."""

import argparse
import json
import os
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/usr/local/etc/xray/config.json")
    parser.add_argument("--listen", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=10086)
    parser.add_argument("--path", default="/api/v1/stream")
    parser.add_argument("--tag", default="master-ws-alt")
    return parser.parse_args()


def main():
    args = parse_args()
    config_path = Path(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    inbounds = config.setdefault("inbounds", [])

    source = next(
        (
            inbound
            for inbound in inbounds
            if inbound.get("protocol") == "vless"
            and inbound.get("streamSettings", {}).get("security") == "reality"
        ),
        None,
    )
    if source is None:
        raise SystemExit("REALITY VLESS inbound not found")

    clients = []
    for row in source.get("settings", {}).get("clients", []):
        uuid = str(row.get("id") or "").strip()
        email = str(row.get("email") or "").strip()
        if uuid:
            clients.append({"id": uuid, "email": email})

    inbound = {
        "listen": args.listen,
        "port": args.port,
        "tag": args.tag,
        "protocol": "vless",
        "settings": {"clients": clients, "decryption": "none"},
        "streamSettings": {
            "network": "ws",
            "security": "none",
            "wsSettings": {"path": args.path},
        },
    }

    existing_index = next(
        (index for index, row in enumerate(inbounds) if row.get("tag") == args.tag),
        None,
    )
    if existing_index is None:
        inbounds.append(inbound)
        action = "added"
    else:
        inbounds[existing_index] = inbound
        action = "updated"

    tmp = config_path.with_name(config_path.name + ".ws-alt.tmp")
    tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, config_path)
    print(f"WS_ALT={action} CLIENTS={len(clients)} PORT={args.port} PATH={args.path}")


if __name__ == "__main__":
    main()
