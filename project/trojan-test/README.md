# Isolated USA Trojan TLS test

Owner-only experiment deployed on 2026-10-26 alongside existing VPN services.
Not connected to bot expiry, account blocking, traffic accounting or the device
limit. Do not share this static test credential with other users.

## Runtime

- Host: `82.21.92.91`; SNI: `serghexen.ru`; public port: `2087/TCP`.
- Directory: `/opt/hexenvpn-trojan-test`, mode 0700.
- Compose project and container: `hexenvpn-trojan-test`.
- Profile: `USA TEST Trojan TLS`; TCP + TLS, chrome fingerprint.
- Uses the installed Xray 26.3.27 image pinned by immutable digest.
- Separate random 256-bit password, generated and stored only on the server.
- 192 MiB memory, 0.5 CPU, 64 processes; bounded Docker logs.
- Read-only filesystem; no capabilities, Docker socket or host network.
- Private, loopback and link-local destinations are rejected by routing rules.
  This is not a complete multi-tenant isolation boundary.

Xray emits a deprecation warning for this basic Trojan configuration. Keep it
as an optional experiment, not a promised long-term replacement for VLESS.
A successful server-local test does not establish resistance to filtering or
connectivity from the owner's Wi-Fi. No fallback website is configured.

## Files

`prepare.py` refuses to overwrite an existing configuration. It records hashes
of existing subscriptions/configurations and IDs/start times of running
containers. It generates runtime files but does not publish the subscription.

`.env`, `config.json`, `manifest.json` and `subscription.b64` contain runtime
data and are excluded from Git. The manifest records the exact secret test URL
and filename; do not paste these into public documentation or commits.

The container binds all host IPv4 addresses. Issued profiles contain a literal
IP, which must be changed after another IP replacement. Also update the manifest
used by the smoke test; keep SNI equal to the certificate domain.

## Checks

```bash
cd /opt/hexenvpn-trojan-test
docker compose -p hexenvpn-trojan-test -f compose.yml ps
python3 smoke.py
```

The smoke test uses temporary clients on the same server, without exporting
credentials. Checks: successful HTTPS egress, rejected loopback destination,
rejected wrong password, then another successful request. All passed during
deployment. Existing containers, profiles and configurations stayed unchanged.
The baseline comparison is for deployment verification; legitimate later
changes to users or restarts will require a new audit baseline.

## TLS and rollback

Existing Let's Encrypt live/archive directories are mounted read-only.
`oneTimeLoading=false` permits renewed certificate files to be reread.
This test does not configure or change certificate renewal. The certificate
currently expires on 2026-12-08.

To stop only this experiment:

```bash
cd /opt/hexenvpn-trojan-test
docker compose -p hexenvpn-trojan-test -f compose.yml down
```

Remove only the exact `subscription_file` from the manifest and the separate
Trojan subscription in Happ. Retain root-only runtime files for recovery.
Do not stop the main Compose stack or restart Docker, nginx, Xray or the VM.

## References

- [Xray Trojan inbound](https://xtls.github.io/en/config/inbounds/trojan.html)
- [Xray Trojan outbound](https://xtls.github.io/en/config/outbounds/trojan.html)
