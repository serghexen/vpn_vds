#!/usr/bin/env python3
"""Prepare an owner-only XHTTP test on the master without editing production."""

import argparse
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import uuid
from urllib.parse import quote, urlencode


def docker_json(*args):
    return json.loads(subprocess.check_output(['docker', *args], text=True))


def snapshot():
    files = [Path('/usr/local/etc/xray/config.json'), Path('/var/lib/vless-sub/clients.json')]
    files += list(Path('/etc/nginx/conf.d').glob('*.conf'))
    files += [p for p in Path('/var/www/sub').iterdir() if p.is_file()]
    containers = subprocess.check_output(['docker', 'ps', '-q'], text=True).split()
    instances = {}
    for c in docker_json('inspect', *containers):
        instances[c['Name']] = [c['Id'], c['State']['StartedAt']]
    return {
        'files': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        'containers': instances,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--address', required=True)
    parser.add_argument('--domain', required=True)
    parser.add_argument('--port', type=int, default=2096)
    args = parser.parse_args()
    ipaddress.IPv4Address(args.address)
    if not re.fullmatch(r'[a-zA-Z0-9.-]+', args.domain) or not 1024 <= args.port <= 65535:
        raise SystemExit('Invalid domain or port')
    root = Path(__file__).resolve().parent
    if any((root / name).exists() for name in ('config.json', '.env', 'manifest.json')):
        raise SystemExit('Existing test state: refuse to overwrite credentials')
    if not Path(f'/etc/letsencrypt/live/{args.domain}/fullchain.pem').is_file():
        raise SystemExit('Certificate missing')
    with socket.socket() as s:
        s.bind(('0.0.0.0', args.port))
    os.umask(0o077)
    baseline = snapshot()
    main_container = docker_json('inspect', 'hexenvpn-xray')[0]
    image_info = docker_json('image', 'inspect', main_container['Image'])[0]
    image = next((s for s in image_info.get('RepoDigests', []) if s.startswith('ghcr.io/xtls/')), main_container['Image'])
    client_id = str(uuid.uuid4())
    path = '/api/v1/xhttp/' + secrets.token_hex(8)
    sub_name = 'test-xhttp-' + secrets.token_hex(16)
    config = {
        'log': {'loglevel': 'warning'},
        'inbounds': [{
            'listen': '0.0.0.0', 'port': 2096, 'tag': 'owner-xhttp-test',
            'protocol': 'vless',
            'settings': {'clients': [{'id': client_id, 'email': 'owner-xhttp-test'}], 'decryption': 'none'},
            'streamSettings': {
                'network': 'xhttp', 'security': 'tls',
                'xhttpSettings': {'path': path, 'mode': 'auto'},
                'tlsSettings': {
                    'alpn': ['h2', 'http/1.1'], 'minVersion': '1.2',
                    'certificates': [{
                        'certificateFile': f'/etc/letsencrypt/live/{args.domain}/fullchain.pem',
                        'keyFile': f'/etc/letsencrypt/live/{args.domain}/privkey.pem',
                        'oneTimeLoading': False,
                    }],
                },
            },
        }],
        'outbounds': [{'protocol': 'freedom', 'tag': 'direct'}, {'protocol': 'blackhole', 'tag': 'block'}],
        'routing': {'domainStrategy': 'IPIfNonMatch', 'rules': [{
            'type': 'field', 'ip': [
                '0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8',
                '169.254.0.0/16', '172.16.0.0/12', '192.168.0.0/16',
                '224.0.0.0/4', '240.0.0.0/4', '::/128', '::1/128', 'fc00::/7', 'fe80::/10',
            ], 'outboundTag': 'block',
        }]},
    }
    links = []
    for mode, label in [('stream-up', 'USA TEST XHTTP'), ('packet-up', 'USA TEST XHTTP Packet')]:
        query = urlencode({'encryption': 'none', 'security': 'tls', 'type': 'xhttp',
                           'sni': args.domain, 'host': args.domain, 'path': path,
                           'mode': mode, 'alpn': 'h2', 'fp': 'chrome'}, quote_via=quote)
        links.append(f'vless://{client_id}@{args.address}:{args.port}?{query}#{quote(label)}')
    (root / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    (root / '.env').write_text(f'XRAY_IMAGE={image}\nTLS_DOMAIN={args.domain}\nXHTTP_PORT={args.port}\n')
    (root / 'subscription.b64').write_bytes(base64.b64encode('\n'.join(links).encode()))
    (root / 'manifest.json').write_text(json.dumps({
        'address': args.address, 'domain': args.domain, 'port': args.port,
        'subscription_file': '/var/www/sub/' + sub_name,
        'subscription_url': f'https://{args.domain}:8443/sub/{sub_name}',
        'image': image, 'baseline': baseline,
    }, indent=2) + '\n')
    print('Prepared isolated XHTTP test; main services unchanged; subscription not yet published')


if __name__ == '__main__':
    main()
