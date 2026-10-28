#!/usr/bin/env python3
"""Add or replace the TR WebSocket ALT link in every subscription."""

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
    parser.add_argument("--host", default=os.environ.get("TR_WS_HOST", ""))
    parser.add_argument("--port", type=int, default=int(os.environ.get("TR_WS_PORT", "2053")))
    parser.add_argument("--sni", default=os.environ.get("TR_WS_SNI", ""))
    parser.add_argument("--path", default=os.environ.get("TR_WS_PATH", "/api/v1/stream"))
    parser.add_argument("--fingerprint", default=os.environ.get("TR_WS_FP", "chrome"))
    parser.add_argument("--reality-host", default=os.environ.get("TR_HOST", ""))
    parser.add_argument("--reality-port", type=int, default=int(os.environ.get("TR_VLESS_PORT", "443")))
    parser.add_argument("--reality-sni", default=os.environ.get("TR_SNI", "www.yahoo.com"))
    parser.add_argument("--reality-pbk", default=os.environ.get("TR_PBK", ""))
    parser.add_argument("--reality-sid", default=os.environ.get("TR_SID", "ffffffffff"))
    parser.add_argument("--reality-fingerprint", default=os.environ.get("TR_FP", "firefox"))
    parser.add_argument("--reality-spider-x", default=os.environ.get("TR_SPX", "/"))
    return parser.parse_args()


def decode_subscription(path):
    raw = path.read_text(encoding="utf-8").strip()
    return base64.b64decode(raw, validate=True).decode("utf-8").splitlines()


def parsed_link(link):
    try:
        parsed = urllib.parse.urlsplit(link)
        query = urllib.parse.parse_qs(parsed.query)
        title = urllib.parse.unquote(parsed.fragment)
        return parsed, query, title
    except Exception:
        return None, {}, ""


def is_tr_alt(link, host, port):
    parsed, query, title = parsed_link(link)
    return bool(
        parsed
        and parsed.scheme == "vless"
        and (
            (parsed.hostname == host and parsed.port == port and query.get("type", [""])[0] == "ws")
            or title == "🇹🇷 Турция ALT [WS]"
        )
    )


def find_tr_uuid(links):
    for link in links:
        parsed, query, title = parsed_link(link)
        if parsed and parsed.scheme == "vless" and "Турция" in title and query.get("type", [""])[0] != "ws":
            return parsed.username
    raise RuntimeError("existing TR profile not found")


def is_tr_reality(link):
    parsed, query, title = parsed_link(link)
    return bool(
        parsed
        and parsed.scheme == "vless"
        and "Турция" in title
        and query.get("type", [""])[0] != "ws"
    )


def make_reality_link(uuid, args):
    query = urllib.parse.urlencode(
        {
            "encryption": "none",
            "type": "tcp",
            "security": "reality",
            "flow": "xtls-rprx-vision",
            "sni": args.reality_sni,
            "fp": args.reality_fingerprint,
            "pbk": args.reality_pbk,
            "sid": args.reality_sid,
            "spx": args.reality_spider_x,
        },
        quote_via=urllib.parse.quote,
    )
    title = urllib.parse.quote("🇹🇷 Турция [VPN]", safe="")
    return f"vless://{uuid}@{args.reality_host}:{args.reality_port}?{query}#{title}"


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
    title = urllib.parse.quote("🇹🇷 Турция ALT [WS]", safe="")
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
        raise SystemExit("--host or TR_WS_HOST is required")
    sni = args.sni or args.host
    clients = json.loads(Path(args.clients).read_text(encoding="utf-8"))
    sub_dir = Path(args.sub_dir)
    www_data = pwd.getpwnam("www-data")
    changed = 0

    for row in clients:
        name = str(row.get("name") or "").strip()
        token = str(row.get("token") or "").strip()
        if not name or not token:
            continue
        aliases = [sub_dir / name, sub_dir / token]
        source = next((path for path in aliases if path.is_file()), None)
        if source is None:
            raise RuntimeError(f"subscription missing for {name}")
        links = [link for link in decode_subscription(source) if not is_tr_alt(link, args.host, args.port)]
        tr_uuid = find_tr_uuid(links)
        if args.reality_host and args.reality_pbk:
            links = [make_reality_link(tr_uuid, args) if is_tr_reality(link) else link for link in links]
        alt = make_alt_link(tr_uuid, args.host, args.port, sni, args.path, args.fingerprint)
        insert_at = next((index + 1 for index, link in enumerate(links) if "Турция" in parsed_link(link)[2]), len(links))
        links.insert(insert_at, alt)
        for alias in aliases:
            write_subscription(alias, links, www_data.pw_uid, www_data.pw_gid)
        changed += 1

    print(f"UPDATED_USERS={changed}")


if __name__ == "__main__":
    main()
