#!/usr/bin/env python3
"""Rebuild master runtime data from a surviving replica xray config."""

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
import urllib.parse
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--replica-config", required=True)
    parser.add_argument("--link-config")
    parser.add_argument("--template", required=True)
    parser.add_argument("--old-clients")
    parser.add_argument("--xray-output", required=True)
    parser.add_argument("--clients-output", required=True)
    parser.add_argument("--sub-dir", required=True)
    parser.add_argument("--db-output", required=True)
    parser.add_argument("--master-host", required=True)
    parser.add_argument("--master-private-key", required=True)
    parser.add_argument("--master-public-key", required=True)
    parser.add_argument("--master-sni", default="www.google.com")
    parser.add_argument("--master-short-id", required=True)
    parser.add_argument("--master-port", type=int, default=443)
    parser.add_argument("--master-ws-port", type=int, default=2053)
    parser.add_argument("--master-ws-path", default="/api/v1/stream")
    parser.add_argument("--master-ws-fingerprint", default="chrome")
    parser.add_argument("--disable-master-ws", action="store_true")
    parser.add_argument("--subscription-port", type=int, default=8443)
    parser.add_argument("--tr-link-host", required=True)
    parser.add_argument("--tr-link-public-key", required=True)
    parser.add_argument("--tr-sni", default="www.yahoo.com")
    parser.add_argument("--tr-short-id", default="ffffffffff")
    parser.add_argument("--tr-port", type=int, default=443)
    parser.add_argument("--grace-days", type=int, default=30)
    parser.add_argument("--admin-tg-id", type=int, default=227380225)
    parser.add_argument("--admin-username", default="serg_hexen")
    return parser.parse_args()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def vless_clients(config):
    for inbound in config.get("inbounds", []):
        if inbound.get("protocol") == "vless":
            return inbound.setdefault("settings", {}).setdefault("clients", [])
    raise RuntimeError("VLESS inbound not found")


def token_for(name, old_by_name):
    old = old_by_name.get(name, {})
    token = str(old.get("token") or "").strip()
    if re.fullmatch(r"[a-fA-F0-9]{32}", token):
        return token.lower()
    seed = f"{name}:{time.time_ns()}:{secrets.token_hex(16)}".encode()
    return hashlib.md5(seed).hexdigest()


def make_link(uuid, host, port, sni, pbk, sid, title):
    title = urllib.parse.quote(title, safe="")
    return (
        f"vless://{uuid}@{host}:{port}?encryption=none&type=tcp&security=reality"
        f"&flow=xtls-rprx-vision&sni={sni}&fp=firefox&pbk={pbk}&sid={sid}&spx=/#{title}"
    )


def init_tg_db(path, users, admin_tg_id, admin_username):
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tg_users (
            tg_id INTEGER PRIMARY KEY,
            username TEXT,
            vpn_name TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            last_start_at INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    now = int(time.time())
    for user in users:
        match = re.fullmatch(r"tg_(\d+)", user["name"])
        if not match:
            continue
        tg_id = int(match.group(1))
        username = admin_username if tg_id == admin_tg_id else None
        conn.execute(
            "INSERT OR REPLACE INTO tg_users(tg_id, username, vpn_name, created_at, last_start_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (tg_id, username, user["name"], now, now),
        )
    conn.commit()
    conn.close()


def main():
    args = parse_args()
    replica = load_json(args.replica_config)
    link_config = load_json(args.link_config) if args.link_config else replica
    template = load_json(args.template)
    old_clients = load_json(args.old_clients) if args.old_clients else []
    old_by_name = {str(row.get("name") or ""): row for row in old_clients}

    recovered = []
    seen_names = set()
    for row in vless_clients(replica):
        name = str(row.get("email") or "").strip()
        uuid = str(row.get("id") or "").strip()
        if not name or not uuid or name == "ru_bridge" or name in seen_names:
            continue
        recovered.append({"name": name, "uuid": uuid})
        seen_names.add(name)

    if not recovered:
        raise RuntimeError("No recoverable clients found")

    link_uuid_by_name = {
        str(row.get("email") or "").strip(): str(row.get("id") or "").strip()
        for row in vless_clients(link_config)
        if str(row.get("email") or "").strip() and str(row.get("id") or "").strip()
    }

    configured = False
    for inbound in template.get("inbounds", []):
        if inbound.get("protocol") != "vless":
            continue
        stream = inbound.setdefault("streamSettings", {})
        clients = []
        for row in recovered:
            client = {"id": row["uuid"], "email": row["name"]}
            if stream.get("network") == "tcp" and stream.get("security") == "reality":
                client["flow"] = "xtls-rprx-vision"
            clients.append(client)
        inbound.setdefault("settings", {})["clients"] = clients
        if stream.get("security") == "reality":
            reality = stream.setdefault("realitySettings", {})
            reality["privateKey"] = args.master_private_key
            reality["shortIds"] = [args.master_short_id]
            reality["serverNames"] = [args.master_sni]
        if stream.get("network") == "ws":
            stream.setdefault("wsSettings", {})["path"] = args.master_ws_path
        configured = True
    if not configured:
        raise RuntimeError("VLESS inbound not found in template")

    # Keep the operational Stats API used by the bot for live sessions and traffic.
    for section in ("api", "stats", "policy", "routing"):
        if section in replica:
            template[section] = replica[section]
    api_inbounds = [
        inbound for inbound in replica.get("inbounds", []) if inbound.get("tag") == "api"
    ]
    template["inbounds"] = [
        inbound for inbound in template.get("inbounds", []) if inbound.get("tag") != "api"
    ] + api_inbounds

    xray_output = Path(args.xray_output)
    xray_output.parent.mkdir(parents=True, exist_ok=True)
    xray_output.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(xray_output, 0o644)

    now = int(time.time())
    emergency_expire = now + args.grace_days * 86400
    clients = []
    sub_dir = Path(args.sub_dir)
    sub_dir.mkdir(parents=True, exist_ok=True)
    for row in recovered:
        name = row["name"]
        uuid = row["uuid"]
        link_uuid = link_uuid_by_name.get(name, uuid)
        old_expire = int(old_by_name.get(name, {}).get("expire") or 0)
        expire = max(emergency_expire, old_expire)
        token = token_for(name, old_by_name)
        clients.append(
            {"name": name, "uuid": uuid, "token": token, "expire": expire, "revoked": False}
        )
        links = [
            make_link(
                uuid,
                args.master_host,
                args.master_port,
                args.master_sni,
                args.master_public_key,
                args.master_short_id,
                "🇺🇸 США [VPN]",
            )
        ]
        if not args.disable_master_ws:
            ws_query = urllib.parse.urlencode(
                {
                    "encryption": "none",
                    "type": "ws",
                    "security": "tls",
                    "sni": args.master_host,
                    "host": args.master_host,
                    "fp": args.master_ws_fingerprint,
                    "path": args.master_ws_path,
                },
                quote_via=urllib.parse.quote,
            )
            ws_title = urllib.parse.quote("🇺🇸 США ALT [WS]", safe="")
            links.append(
                f"vless://{uuid}@{args.master_host}:{args.master_ws_port}?{ws_query}#{ws_title}"
            )
        links.append(
            make_link(
                link_uuid,
                args.tr_link_host,
                args.tr_port,
                args.tr_sni,
                args.tr_link_public_key,
                args.tr_short_id,
                "🇹🇷 Турция [VPN]",
            )
        )
        encoded = base64.b64encode("\n".join(links).encode()).decode()
        (sub_dir / name).write_text(encoded, encoding="utf-8")
        (sub_dir / token).write_text(encoded, encoding="utf-8")

    clients_output = Path(args.clients_output)
    clients_output.parent.mkdir(parents=True, exist_ok=True)
    clients_output.write_text(json.dumps(clients, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    init_tg_db(args.db_output, clients, args.admin_tg_id, args.admin_username)

    print(f"RECOVERED_USERS={len(clients)}")
    print(f"RECOVERED_TG_USERS={sum(1 for row in clients if re.fullmatch(r'tg_\d+', row['name']))}")
    print(f"LINK_UUID_OVERRIDES={sum(1 for row in recovered if link_uuid_by_name.get(row['name'], row['uuid']) != row['uuid'])}")
    print(f"EMERGENCY_EXPIRE={emergency_expire}")
    print(f"MASTER_PUBLIC_KEY={args.master_public_key}")


if __name__ == "__main__":
    main()
