#!/usr/bin/env python3
"""Create a private application recovery bundle on the master without restarting it."""

import argparse
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile


APP_PATHS = (
    '/opt/vpn_vds', '/opt/hexenvpn-hysteria', '/opt/hexenvpn-xhttp-test',
    '/opt/hexenvpn-trojan-test', '/opt/hexenvpn-mtproxy',
    '/opt/hexenvpn-telegram-connect', '/usr/local/etc/xray',
    '/usr/local/sbin', '/var/lib/vless-sub', '/var/www',
    '/etc/nginx', '/etc/letsencrypt', '/etc/ssl',
)
REFERENCE_PATHS = (
    '/root/.ssh', '/home/adminops/.ssh', '/etc/ssh', '/etc/netplan',
    '/etc/hosts', '/etc/hostname', '/etc/fstab', '/etc/docker',
    '/etc/systemd/system', '/etc/cron.d', '/var/spool/cron/crontabs',
    '/etc/ufw', '/etc/iptables', '/etc/apt', '/etc/os-release',
)
DB_PATH = '/var/lib/hexenvpn-bot/bot.db'


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def run(args):
    return subprocess.check_output(args, timeout=120)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def stable_files():
    result = {}
    # Ignore access logs and historical traffic; capture configuration/user changes.
    for name in APP_PATHS:
        root = Path(name)
        if not root.exists():
            raise RuntimeError('Missing required application path: ' + name)
        for p in sorted(root.rglob('*')):
            if p.is_file() and not p.is_symlink() and '.git' not in p.parts:
                result[str(p)] = digest(p)
    return result


def container_state(containers):
    return {c['Id']: c['State']['StartedAt'] for c in containers}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='New absolute directory under /root')
    args = parser.parse_args()
    out = Path(args.output).absolute()
    if os.geteuid() != 0 or out.parent != Path('/root'):
        parser.error('Run as root and choose a new directory directly under /root')
    os.umask(0o077)
    out.mkdir(mode=0o700, exist_ok=False)
    (out / 'INCOMPLETE').write_text('Do not use until backup completes.\n')
    staging = out / 'snapshot'
    app = staging / 'rootfs'
    reference = staging / 'reference'
    inventory = staging / 'inventory'
    for p in (app, reference, inventory):
        p.mkdir(parents=True, mode=0o700)
    ids = run(['docker', 'ps', '-aq']).decode().split()
    if not ids:
        raise RuntimeError('No containers found')
    containers = json.loads(run(['docker', 'inspect', *ids]))
    write_json(inventory / 'containers.json', containers)
    before = stable_files()
    print('Copying application files and reference configuration', flush=True)
    for name in APP_PATHS:
        subprocess.run(['cp', '-a', '--parents', name, str(app)], check=True)
    for name in REFERENCE_PATHS:
        if os.path.lexists(name):
            subprocess.run(['cp', '-a', '--parents', name, str(reference)], check=True)

    db_dir = Path(DB_PATH).parent
    unexpected = [p.name for p in db_dir.iterdir()
                  if p.name not in ('bot.db', 'bot.db-wal', 'bot.db-shm', 'bot.db-journal')]
    if unexpected:
        raise RuntimeError('Review additional bot data before backup: ' + repr(unexpected))
    db_copy = app / DB_PATH.lstrip('/')
    db_copy.parent.mkdir(parents=True, mode=0o700)
    with sqlite3.connect('file:' + DB_PATH + '?mode=ro', uri=True) as src:
        with sqlite3.connect(db_copy) as dest:
            src.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise RuntimeError('SQLite integrity check failed')
            if dest.execute('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('SQLite foreign key check failed')
    shutil.copystat(DB_PATH, db_copy)
    st = os.stat(DB_PATH)
    os.chown(db_copy, st.st_uid, st.st_gid)

    mounts = []
    copied_volumes = set()
    for c in containers:
        for m in c.get('Mounts', []):
            source = m.get('Source', '')
            item = {'container': c['Name'], **m}
            if m['Type'] == 'volume':
                if m['Destination'].startswith('/var/log/'):
                    item['backup'] = 'excluded: diagnostic logs only'
                else:
                    name = m['Name']
                    target = staging / 'volumes' / name
                    if name not in copied_volumes:
                        target.mkdir(parents=True)
                        subprocess.run(['cp', '-a', source + '/.', str(target)], check=True)
                        copied_volumes.add(name)
                    item['backup'] = 'volumes/' + name
            elif m['Type'] == 'bind':
                if source.startswith('/var/log/'):
                    item['backup'] = 'excluded: diagnostic logs only'
                elif source == str(db_dir) or any(source == p or source.startswith(p + '/') for p in APP_PATHS):
                    item['backup'] = 'rootfs/' + source.lstrip('/')
                elif any(source == p or source.startswith(p + '/') for p in REFERENCE_PATHS):
                    item['backup'] = 'reference/' + source.lstrip('/')
                else:
                    raise RuntimeError('Uncovered bind mount: ' + source)
            else:
                raise RuntimeError('Review unsupported mount type: ' + m['Type'])
            mounts.append(item)
    write_json(inventory / 'mount-coverage.json', mounts)

    image_ids = sorted({c['Image'] for c in containers})
    images = json.loads(run(['docker', 'image', 'inspect', *image_ids]))
    write_json(inventory / 'images.json', images)
    # Local tags let recovery avoid mutable :latest tags and registry availability.
    override = {}
    for c in containers:
        labels = c['Config'].get('Labels') or {}
        project = labels.get('com.docker.compose.project')
        service = labels.get('com.docker.compose.service')
        if not project or not service:
            raise RuntimeError('Container without Compose recovery identity: ' + c['Name'])
        override.setdefault(project, {'services': {}})['services'][service] = {
            'image': 'hexenvpn-recovery:' + c['Image'].split(':')[1],
            'pull_policy': 'never',
        }
    write_json(inventory / 'compose-image-overrides.json', override)
    commands = {
        'packages.txt': ['dpkg-query', '-W', '-f=${Package}\t${Version}\n'],
        'docker-version.txt': ['docker', 'version'],
        'compose-version.txt': ['docker', 'compose', 'version'],
        'nginx-version.txt': ['nginx', '-V'],
        'systemd-units.txt': ['systemctl', 'list-unit-files', '--no-pager'],
        'timers.txt': ['systemctl', 'list-timers', '--all', '--no-pager'],
        'listeners.txt': ['ss', '-lntup'],
        'ip-address.txt': ['ip', '-j', 'addr'],
        'ip-route.txt': ['ip', '-j', 'route'],
        'iptables.txt': ['iptables-save'],
    }
    for name, command in commands.items():
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        (inventory / name).write_bytes(result.stdout)
        if result.returncode:
            raise RuntimeError('Inventory command failed: ' + name)
    after = stable_files()
    if before != after:
        raise RuntimeError('Application files changed during snapshot; retry when provisioning is idle')
    for path, expected in before.items():
        if digest(app / path.lstrip('/')) != expected:
            raise RuntimeError('Snapshot file mismatch: ' + path)
    write_json(inventory / 'source-sha256.json', before)
    write_json(inventory / 'capture.json', {
        'captured_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'sqlite_snapshot': DB_PATH,
        'consistency': 'Online SQLite snapshot; application files stable during copy. No services stopped.',
        'excluded': ['container logs', '/var/log/nginx', 'OS image', 'external DNS/provider account'],
        'restore_warning': 'Never restore reference/ wholesale. Keep new host network and SSH settings.',
    })
    print('Application snapshot consistent; saving deployed Docker images', flush=True)
    with open(out / 'docker-save.log', 'wb') as err:
        proc = subprocess.Popen(['docker', 'image', 'save', *image_ids], stdout=subprocess.PIPE, stderr=err)
        try:
            with gzip.open(out / 'images.tar.gz', 'wb', compresslevel=1) as dest:
                shutil.copyfileobj(proc.stdout, dest, length=1024 * 1024)
            if proc.wait(timeout=1800):
                raise RuntimeError('Docker image save failed; see private docker-save.log')
        finally:
            proc.stdout.close()
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    current = json.loads(run(['docker', 'inspect', *ids]))
    if container_state(current) != container_state(containers):
        raise RuntimeError('A container restarted during backup; investigate before accepting')
    manifest = {}
    for p in sorted(staging.rglob('*')):
        rel = p.relative_to(staging).as_posix()
        if p.is_symlink():
            manifest[rel] = {'link': os.readlink(p)}
        elif p.is_file():
            manifest[rel] = {'sha256': digest(p), 'size': p.stat().st_size}
    write_json(out / 'manifest.json', manifest)
    with tarfile.open(out / 'files.tar.gz', 'w:gz', dereference=False) as tar:
        for name in sorted(staging.iterdir()):
            tar.add(name, arcname=name.name)
    names = ['files.tar.gz', 'images.tar.gz', 'manifest.json']
    (out / 'SHA256SUMS').write_text(''.join(digest(out / n) + '  ' + n + '\n' for n in names))
    (out / 'INCOMPLETE').unlink()
    print('BACKUP_READY ' + str(out), flush=True)
    print('Files:', len(manifest), 'containers:', len(containers), 'images:', len(images), flush=True)
    print('Private snapshot kept on server; nothing deleted or restarted.', flush=True)


if __name__ == '__main__':
    main()
