#!/usr/bin/env python3
"""Exercise Trojan locally on the server; never export client credentials."""

import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import secrets


def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / 'manifest.json').read_text())
    inbound = json.loads((root / 'config.json').read_text())['inbounds'][0]
    password = inbound['settings']['clients'][0]['password']
    cases = [(password, 'https://api.ipify.org', True),
             (password, 'http://127.0.0.1:80', False),
             (secrets.token_urlsafe(32), 'https://api.ipify.org', False),
             (password, 'https://api.ipify.org', True)]
    for i, (auth, target, success) in enumerate(cases):
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        config = {
            'log': {'loglevel': 'warning'},
            'inbounds': [{'listen': '127.0.0.1', 'port': port, 'protocol': 'socks', 'settings': {'auth': 'noauth'}}],
            'outbounds': [{'protocol': 'trojan', 'settings': {'servers': [{
                'address': manifest['address'], 'port': manifest['port'],
                'password': auth,
            }]}, 'streamSettings': {
                'network': 'tcp', 'security': 'tls',
                'tlsSettings': {'serverName': manifest['domain'], 'alpn': ['http/1.1'], 'fingerprint': 'chrome', 'allowInsecure': False},
            }}],
        }
        name = f'hexenvpn-trojan-check-{os.getpid()}-{i}'
        with tempfile.TemporaryDirectory(prefix='trojan-check-') as tmp:
            f = Path(tmp) / 'client.json'
            f.write_text(json.dumps(config))
            f.chmod(0o600)
            try:
                subprocess.run(['docker', 'run', '-d', '--name', name, '--network', 'host',
                                '--read-only', '--cap-drop', 'ALL', '--user', '0:0',
                                '--memory', '128m', '--cpus', '0.25',
                                '-v', str(f) + ':/etc/xray/client.json:ro', manifest['image'],
                                'run', '-config', '/etc/xray/client.json'], check=True, stdout=subprocess.DEVNULL)
                time.sleep(1)
                running = subprocess.check_output(['docker', 'inspect', '-f', '{{.State.Running}}', name], text=True).strip()
                assert running == 'true', 'Test client failed to start'
                r = subprocess.run(['curl', '-fsS', '--noproxy', '', '--connect-timeout', '4',
                                    '--max-time', '15' if success else '6', '--socks5-hostname',
                                    f'127.0.0.1:{port}', target], capture_output=True, text=True)
                ok = (r.returncode == 0 and r.stdout.strip() == manifest['address']) if success else r.returncode != 0
                print(f'case={i} expected={"egress" if success else "reject"} result={"OK" if ok else "FAIL"}', flush=True)
                if not ok:
                    raise SystemExit('Trojan smoke test failed')
            finally:
                subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for file, expected in manifest['baseline']['files'].items():
        assert hashlib.sha256(Path(file).read_bytes()).hexdigest() == expected, 'Existing configuration/subscription changed: ' + file
    for name, expected in manifest['baseline']['containers'].items():
        c = json.loads(subprocess.check_output(['docker', 'inspect', name], text=True))[0]
        assert [c['Id'], c['State']['StartedAt']] == expected and c['State']['Running'], 'Existing service changed: ' + name
    print('All pre-existing subscriptions/configurations unchanged; existing containers not restarted')


if __name__ == '__main__':
    main()
