#!/usr/bin/env python3
"""Verify a recovery bundle without extracting secrets outside a private temp directory."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import sqlite3
import subprocess
import tarfile
import tempfile
import urllib.parse


def sha256(stream):
    h = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        h.update(chunk)
    return h.hexdigest()


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Unsafe archive member')
    return name


def verify_images(path, images):
    hashes, documents, sizes = {}, {}, {}
    # Containerd image IDs may identify an OCI index, not the config blob ID.
    # Stream once: repeated seeks in a large gzip archive are very expensive.
    with tarfile.open(path, 'r|gz') as tar:
        for member in tar:
            safe_name(member.name)
            if not member.isfile():
                continue
            with tar.extractfile(member) as stream:
                if member.size < 1024 * 1024:
                    data = stream.read()
                    digest = hashlib.sha256(data).hexdigest()
                    try:
                        documents[member.name] = json.loads(data)
                    except (ValueError, UnicodeDecodeError):
                        pass
                else:
                    digest = sha256(stream)
            hashes[member.name] = digest
            sizes[member.name] = member.size
            if member.name.startswith('blobs/sha256/'):
                assert digest == member.name.rsplit('/', 1)[1], 'Corrupt OCI blob'
    entries = documents['manifest.json']
    configs = set()
    for entry in entries:
        configs.add(hashes[entry['Config']])
        for layer in entry['Layers']:
            assert sizes.get(layer, 0) > 0, 'Empty/missing image layer'
    expected = {image['Id'].split(':')[1] for image in images}
    if 'index.json' not in documents:
        assert configs == expected, 'Legacy Docker image IDs mismatch'
        return {image['Id']: image['Id'] for image in images}
    descriptors = documents['index.json']['manifests']
    assert {d['digest'].split(':')[1] for d in descriptors} == expected, 'OCI image IDs mismatch'
    mapping = {}

    def resolve(descriptor, image):
        digest = descriptor['digest'].split(':')[1]
        name = 'blobs/sha256/' + digest
        assert hashes.get(name) == digest, 'Missing image descriptor'
        document = documents[name]
        if 'manifests' in document:
            matches = [d for d in document['manifests']
                       if d.get('platform', {}).get('architecture') == image['Architecture']
                       and d.get('platform', {}).get('os') == image['Os']]
            assert matches, 'Missing deployed image architecture'
            return resolve(matches[0], image)
        config_digest = document['config']['digest'].split(':')[1]
        assert config_digest in configs, 'Image config absent from Docker load manifest'
        for layer in document['layers']:
            blob = 'blobs/' + layer['digest'].replace(':', '/')
            assert hashes.get(blob) == layer['digest'].split(':')[1], 'Missing/corrupt image layer'
        return 'sha256:' + config_digest

    by_id = {image['Id']: image for image in images}
    for descriptor in descriptors:
        mapping[descriptor['digest']] = resolve(descriptor, by_id[descriptor['digest']])
    return mapping


def verify(bundle):
    if (bundle / 'INCOMPLETE').exists():
        raise ValueError('Incomplete bundle')
    sums = {}
    for line in (bundle / 'SHA256SUMS').read_text().splitlines():
        expected, name = line.split('  ', 1)
        safe_name(name)
        with open(bundle / name, 'rb') as stream:
            assert sha256(stream) == expected, 'Bundle SHA256 mismatch: ' + name
        sums[name] = expected
    assert {'files.tar.gz', 'images.tar.gz', 'manifest.json'} <= sums.keys()
    manifest = json.loads((bundle / 'manifest.json').read_text())
    summary = {'bundle_checksums': 'ok'}
    with tarfile.open(bundle / 'files.tar.gz', 'r:gz') as tar:
        members = {}
        for member in tar.getmembers():
            safe_name(member.name)
            assert member.name not in members, 'Duplicate archive member'
            members[member.name] = member
            assert member.isdir() or member.isfile() or member.issym() or member.islnk(), 'Special archive member'
            if member.islnk():
                safe_name(member.linkname)
        for name, item in manifest.items():
            member = members[name]
            if 'link' in item:
                assert member.issym() and member.linkname == item['link'], 'Symlink mismatch'
            else:
                with tar.extractfile(member) as stream:
                    assert sha256(stream) == item['sha256'], 'File hash mismatch: ' + name
        assert set(manifest) == {n for n, m in members.items() if not m.isdir()}, 'Manifest coverage mismatch'
        summary['verified_files_and_links'] = len(manifest)

        def read(name):
            # Resolve rootfs symlinks in archive space, never on the local filesystem.
            for _ in range(20):
                member = members[name]
                if not member.issym():
                    return tar.extractfile(member).read()
                link = member.linkname
                name = ('rootfs/' + link.lstrip('/')) if link.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(name), link))
                safe_name(name)
            raise ValueError('Symlink loop')

        def load(name):
            return json.loads(read(name))

        users = load('rootfs/var/lib/vless-sub/clients.json')
        config = load('rootfs/usr/local/etc/xray/config.json')
        for field in ('name', 'uuid', 'token'):
            values = [u[field] for u in users]
            assert all(values) and len(values) == len(set(values)), 'Missing/duplicate registry field: ' + field
        ids = {u['uuid'] for u in users}
        inbound_counts = []
        for inbound in config['inbounds']:
            if inbound['protocol'] == 'vless':
                clients = inbound['settings']['clients']
                assert {c['id'] for c in clients} == ids, 'VLESS registry mismatch; review revoked/expired clients'
                assert len(clients) == len(ids), 'Duplicate VLESS UUID'
                inbound_counts.append(len(clients))
        assert inbound_counts, 'No VLESS inbound'
        for user in users:
            files = [read('rootfs/var/www/sub/' + user[key]).strip() for key in ('name', 'token')]
            assert files[0] == files[1], 'Subscription aliases differ'
            decoded = base64.b64decode(files[0], validate=True).decode()
            links = [urllib.parse.urlsplit(line) for line in decoded.splitlines() if line.strip()]
            assert links and all(link.scheme == 'vless' and link.username == user['uuid'] for link in links), 'Subscription UUID mismatch'
        summary.update(vpn_users=len(users), vless_inbound_counts=inbound_counts, user_subscription_files=2 * len(users))
        with tempfile.TemporaryDirectory(prefix='vpn-recovery-verify-') as temp:
            os.chmod(temp, 0o700)
            db = Path(temp) / 'bot.db'
            fd = os.open(db, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(read('rootfs/var/lib/hexenvpn-bot/bot.db'))
            connection = sqlite3.connect('file:' + str(db) + '?mode=ro', uri=True)
            try:
                assert connection.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
                assert not connection.execute('PRAGMA foreign_key_check').fetchall()
                rows = connection.execute('select vpn_name from tg_users').fetchall()
                assert all(row[0] in {u['name'] for u in users} for row in rows), 'Unmapped Telegram account'
                summary['telegram_users'] = len(rows)
                for name in ('user_devices', 'traffic_samples'):
                    summary[name] = connection.execute('select count(*) from ' + name).fetchone()[0]
                summary['database_integrity'] = 'ok'
            finally:
                connection.close()
        containers = load('inventory/containers.json')
        images = load('inventory/images.json')
        summary['containers'] = [c['Name'].lstrip('/') for c in containers]
        summary['image_count'] = len(images)
        for c in containers:
            labels = c['Config']['Labels']
            for name in labels['com.docker.compose.project.config_files'].split(','):
                assert 'rootfs/' + name.lstrip('/') in members, 'Missing Compose file'
        cert = read('rootfs/etc/ssl/public.crt')
        key = read('rootfs/etc/ssl/private.key')
        cert_pub = subprocess.run(['openssl', 'x509', '-pubkey', '-noout'], input=cert, capture_output=True, check=True).stdout
        key_pub = subprocess.run(['openssl', 'pkey', '-pubout'], input=key, capture_output=True, check=True).stdout
        assert cert_pub == key_pub, 'TLS private key mismatch'
        summary['tls_certificate_key_match'] = True
        summary['tls_dates'] = subprocess.run(['openssl', 'x509', '-noout', '-dates'], input=cert, capture_output=True, check=True).stdout.decode().splitlines()
        for directory in ('hexenvpn-xhttp-test', 'hexenvpn-trojan-test'):
            base = 'rootfs/opt/' + directory + '/'
            cfg = load(base + 'config.json')
            meta = load(base + 'manifest.json')
            ref = meta['subscription_file']
            path = 'rootfs/' + ref.lstrip('/') if ref.startswith('/') else 'rootfs/var/www/sub/' + ref
            assert read(path).strip() == read(base + 'subscription.b64').strip(), 'Test subscription mismatch'
            clients = cfg['inbounds'][0]['settings']['clients']
            assert clients, 'Missing test credentials'
            decoded = base64.b64decode(read(path).strip(), validate=True).decode()
            credentials = {c.get('id', c.get('password')) for c in clients}
            for line in decoded.splitlines():
                uri = urllib.parse.urlsplit(line)
                assert urllib.parse.unquote(uri.username or '') in credentials, 'Test credential mismatch'
            summary[directory] = 'config, credentials, Compose and subscription preserved'
        for suffix, filename in (('', 'server.json'), ('-plain', 'server-plain.json')):
            base = 'rootfs/opt/hexenvpn-hysteria/'
            cfg = load(base + 'project/hysteria/' + filename)
            ref = read(base + 'test-sub' + suffix + '-file').decode().strip()
            path = 'rootfs/' + ref.lstrip('/') if ref.startswith('/') else 'rootfs/var/www/sub/' + ref
            uri = urllib.parse.urlsplit(base64.b64decode(read(path).strip(), validate=True).decode().strip())
            assert urllib.parse.unquote(uri.netloc.rsplit('@', 1)[0]) == cfg['auth']['password'], 'Hysteria password mismatch'
            summary['hysteria' + suffix] = 'config and subscription credentials match'
        assert read('rootfs/opt/hexenvpn-mtproxy/data/secret').strip(), 'Missing MTProxy secret'
        assert read('rootfs/opt/hexenvpn-telegram-connect/squid.conf').strip(), 'Missing CONNECT config'
        assert any(line.startswith('BOT_TOKEN=') and len(line.split('=', 1)[1].strip()) > 20
                   for line in read('rootfs/opt/vpn_vds/project/env/bot.env').decode().splitlines()), 'Missing bot token'
        summary['mounts'] = len(load('inventory/mount-coverage.json'))
    summary['image_id_to_config_id'] = verify_images(bundle / 'images.tar.gz', images)
    summary['docker_images_match_running_containers'] = True
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.bundle), indent=2))
