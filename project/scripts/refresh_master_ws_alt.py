#!/usr/bin/env python3
"""Add or replace the master WebSocket ALT link in every subscription."""

import argparse
import base64
import json
import os
import pwd
import urllib.parse
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clients", default="/var/lib/vless-sub/clients.json")
    parser.add_argument("--sub-dir", default="/var/www/sub")
    parser.add_argument("--host", default=os.environ.get("MASTER_HOST", ""))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MASTER_WS_PORT", "2053")))
    parser.add_argument("--sni", default=os.environ.get("MASTER_WS_SNI", ""))
    parser.add_argument("--path", default=os.environ.get("MASTER_WS_PATH", "/api/v1/stream"))
    parser.add_argument("--fingerprint", default=os.environ.get("MASTER_WS_FP", "chrome"))
    return parser.parse_args()


def decode_subscription(path):
    try:
        return base64.b64decode(path.read_text(encoding="utf-8").strip(), validate=True).decode("utf-8").splitlines()
    except Exception as exc:
        raise RuntimeError(f"invalid subscription file {path}: {exc}") from exc


def is_alt_link(link, host, port):
    try:
        parsed = urllib.parse.urlsplit(link)
        query = urllib.parse.parse_qs(parsed.query)
        return (
            parsed.scheme == "vless"
            and parsed.hostname == host
            and parsed.port == port
            and query.get("type", [""])[0] == "ws"
        )
    except Exception:
        return False


def make_alt_link(uuid, host, port, sni, path, fingerprint):
    query = urllib.parse.urlencode(
        {
            "encryption": "none",
            "type": "ws",
            "security": "tls",
            "sni": sni,
            "host": sni,
            "fp": fingerprint,
            "path": path,
        },
        quote_via=urllib.parse.quote,
    )
    title = urllib.parse.quote("🇺🇸 США ALT [WS]", safe="")
    return f"vless://{uuid}@{host}:{port}?{query}#{title}"


def write_subscription(path, links, uid, gid):
    encoded = base64.b64encode("\n".join(links).encode("utf-8")).decode("ascii")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(encoded, encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.chown(tmp, uid, gid)
    os.replace(tmp, path)


def main():
    args = parse_args()
    if not args.host:
        raise SystemExit("--host or MASTER_HOST is required")
    sni = args.sni or args.host
    clients = json.loads(Path(args.clients).read_text(encoding="utf-8"))
    sub_dir = Path(args.sub_dir)
    www_data = pwd.getpwnam("www-data")
    changed = 0

    for row in clients:
        name = str(row.get("name") or "").strip()
        token = str(row.get("token") or "").strip()
        uuid = str(row.get("uuid") or "").strip()
        if not name or not token or not uuid:
            continue

        aliases = [sub_dir / name, sub_dir / token]
        source = next((path for path in aliases if path.is_file()), None)
        if source is None:
            raise RuntimeError(f"subscription missing for {name}")

        links = [link for link in decode_subscription(source) if not is_alt_link(link, args.host, args.port)]
        alt = make_alt_link(uuid, args.host, args.port, sni, args.path, args.fingerprint)
        insert_at = 1 if links else 0
        links.insert(insert_at, alt)
        for alias in aliases:
            write_subscription(alias, links, www_data.pw_uid, www_data.pw_gid)
        changed += 1

    print(f"UPDATED_USERS={changed}")


if __name__ == "__main__":
    main()
