# Recovery without the old VM

## Scope and security

The owner authorized a new local recovery bundle on 2026-10-28. This supersedes
the earlier server-only restriction for this backup. Store it under `backups/`,
which is excluded from Git. Directory mode must be 0700, downloaded files 0600.
The archive contains bot tokens, user data, VPN credentials, TLS private keys,
and reference SSH keys. Never commit, publish, or attach it to a support ticket.
File permissions are not encryption; an encrypted offline copy on another
owner-controlled device is advisable. A copy only on this Mac does not protect
against losing the Mac.

Verified capture: `backups/recovery-20261028/`, source master `82.21.92.91`,
accessed through the prepared replacement `162.141.123.118`. The private
`verification.json` records 19 VPN users, 38 user subscription files, 13 Telegram
mappings, 58 devices, 8 containers, 5 deployed images, and 690 verified files or
links. Both server-side and downloaded-copy verification passed. The old host
copy remains at `/root/recovery-20261028-local-project`. No service was restarted.
The source and recovery tools are also included in `source.bundle`; application
credentials are only in the private archives, not in Git.

This is an application recovery bundle, not a disk image. A replacement Ubuntu
host, Docker/Compose, Python, nginx with its required modules, and DNS/provider
access are still needed. OS packages may need an Internet connection; deployed
Docker images and source code are saved locally so the old VM is not required.

## Capture

`project/scripts/backup_recovery_bundle.py` is tailored to the current USA stack:
main Xray and bot, nginx subscriptions, Hysteria2 (two variants), XHTTP, Trojan,
MTProxy and HTTP CONNECT. Review its explicit paths when adding a service.

On the old host, as root:

```bash
python3 /path/to/backup_recovery_bundle.py --output /root/recovery-YYYYMMDDTHHMMSSZ
```

Do not provision, revoke, or modify users/configuration during capture. The
script makes an online SQLite backup and verifies its integrity; configuration
hashes must remain unchanged during copying. Services are not stopped. This is
not a transaction across the entire application: traffic/device counters may
advance after the SQLite snapshot. Unexpected bot data files, uncovered mounts,
missing application paths or container restarts fail the capture. On failure,
keep the `INCOMPLETE` directory for diagnosis and retry into a new directory.

Artifacts:

- `files.tar.gz`: `rootfs/` application data, `reference/` host configuration,
  `volumes/` non-log anonymous volume contents, and `inventory/` metadata.
- `images.tar.gz`: all five deployed Docker images, saved by exact image ID.
- `manifest.json`: SHA-256 for every snapshot file and symlink targets.
- `SHA256SUMS`: transfer checksums for these artifacts.
- Local `source.bundle`: Git bundle added after the final recovery-tool commit.
- Local `verification.json`: non-secret verification results for that snapshot.

`inventory/containers.json` includes runtime environment secrets. Treat it as
private even though the public recovery scripts contain no credentials.
Diagnostic container/nginx logs are excluded. Restore may need to reset device
log-ingestion offsets because the old access logs are intentionally not copied.

Transfer through authenticated SSH with strict host-key checking. A jump host
can relay the encrypted connection without receiving private keys. Never use
agent forwarding or disable host-key verification to simplify the transfer.
Download to `.partial` files, verify hashes, then rename. Keep old server copies
until the local bundle is independently verified.

## Verify before accepting

```bash
python3 project/scripts/verify_recovery_bundle.py backups/<bundle-directory>
git bundle verify backups/<bundle-directory>/source.bundle
```

The verifier checks outer checksums, every archived file, SQLite integrity and
foreign keys, registry UUIDs, user subscription aliases, Telegram mappings,
certificate/key matching, separate test subscriptions, Compose file presence,
and image config hashes against the deployed image IDs. It never installs or
starts services. Do not run Python with `-O`, which disables its assertions.

This validates recovery materials, not a complete live restore. A restore drill
on a separate host remains the final end-to-end test.

## Restore sequence

1. Establish independent SSH/admin access and inspect resources on the new VM.
   The replacement prepared on 2026-10-28 has about 1 GB RAM; assess capacity
   before starting all services. Keep DNS pointed at the old host for now.
2. Verify the bundle locally and after transfer. Extract only in a new private
   staging directory, never directly into `/`. Restore no files from
   `reference/` automatically: old SSH, authorized_keys, network, firewall,
   hostname and systemd settings can lock out the new host. Inspect selected
   cron/timer and certificate-renewal settings individually.
3. Recover code via `git clone /path/source.bundle vpn_vds`. Also retain
   `rootfs/opt/vpn_vds` as the exact deployed code snapshot; it may differ from
   Git. Review these differences before replacing either version.
4. Install host packages using `inventory/packages.txt` and
   `inventory/nginx-version.txt` as references (nginx and its njs module are
   host services, not included in Docker images). Do NOT run the clean bootstrap
   script over recovered data: it generates replacement identities/configs.
5. With the bot stopped, restore application files to their original paths,
   preserving executable permissions and needed numeric ownership. Restore the
   online snapshot `rootfs/var/lib/hexenvpn-bot/bot.db`; do not carry over old WAL
   or SHM files. No other copy of this Telegram bot should be polling.
6. Load images with `gzip -dc images.tar.gz | docker image load`. Image saves by
   ID may not preserve tags/digests. Containerd IDs refer to OCI manifests;
   classic Docker may instead expose the config ID after import. Consult
   `image_id_to_config_id` in `verification.json` to locate each imported image,
   then tag it `hexenvpn-recovery:<original-image-id-without-sha256-prefix>`. Split
   `inventory/compose-image-overrides.json` into per-project JSON override files.
   Use these with the original Compose file, `--no-build --pull never`, and the
   original project names from `inventory/containers.json`. Do not pull `latest`
   or depend on the old registry digests being available after `docker load`.
7. Restore any needed non-log Docker volumes to newly created volumes rather
   than overwriting `/var/lib/docker`. `inventory/mount-coverage.json` maps old
   volume names to their container destinations. The application Xray configs
   are bind mounts; anonymous image-default config volumes are not their source.
8. Replace the old IP in Hysteria bind addresses, MTProxy environment, standalone
   profile endpoints/manifests and any proxy ACL/upstreams that actually require
   it. Preserve UUIDs, tokens, REALITY key pairs, passwords, TLS SNI and WS/XHTTP
   paths. Keep retired UK/TR disabled; do not blindly revive historical settings.
9. Validate Xray/nginx configs. Start core VPN and subscription services first,
   then the optional services within available RAM. Test using the new IP and
   original TLS hostname before DNS cutover. Check all 19 users against the
   snapshot, both subscription aliases, create/delete/revoke with a temporary
   account, and actual traffic on each restored protocol.
10. Verify certificate dates; renew when necessary. Re-establish automatic
    renewal and certificate reload hooks rather than assuming old timers work.
11. Stop the old bot before starting the restored one. Switch domain A records
    only after validation. Keep old and new backups. Standalone profiles with
    literal IPs and external notifier proxy URLs require client-side updates;
    the external notifier is a different project and is not changed here.

DNS account credentials, a new VM, and future certificate issuance cannot be
replaced by a Git repository or a local archive. Keep independent provider access.
