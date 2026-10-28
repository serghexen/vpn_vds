# Isolated USA XHTTP test

Owner-only VLESS + XHTTP + TLS experiment, deployed on 2026-10-26.
This is not integrated with bot expiry, account revocation, traffic reports,
or the device limit. Do not distribute this credential to other users.

## Deployment

- Host: `82.21.92.91`; TLS SNI and HTTP host: `serghexen.ru`.
- Directory: `/opt/hexenvpn-xhttp-test`, root-only.
- Compose project and container: `hexenvpn-xhttp-test`.
- Public port: `2096/TCP`. No UDP port is published.
- Separate randomly generated UUID; no production user credentials reused.
- Two profiles in one separate test subscription: `stream-up` and `packet-up`.
- Direct TLS with HTTP/2; no nginx changes or reverse proxy required.
- Reuses the currently installed Xray 26.3.27 image by immutable digest.
- Limits: 192 MiB RAM, 0.5 CPU, 64 processes, bounded Docker logs.
- Read-only root filesystem, no capabilities, no Docker socket or host network.
- Private/link-local/loopback destination ranges are rejected by Xray routing.
  This routing policy is not a complete multi-tenant network isolation boundary.

The public port is bound to all host IPv4 addresses, so it survives a host IP
change without recreating the container. The issued links contain a literal
IP and must still be updated after an IP change, as must `manifest.json` used
by the smoke test. SNI remains the certificate domain.

## Files and checks

Tracked source: `compose.yml`, `prepare.py`, `smoke.py`.
Runtime files are created only on the server and excluded from Git:
`.env`, `config.json`, `manifest.json`, `subscription.b64`.

`prepare.py` refuses to overwrite existing runtime state. It snapshots hashes
of existing configurations and subscriptions, and IDs/start times of running
containers before preparing the new test. It does not publish the subscription.
The manifest records the exact random subscription filename and URL.

```bash
cd /opt/hexenvpn-xhttp-test
docker compose -p hexenvpn-xhttp-test -f compose.yml ps
python3 smoke.py
```

The smoke test creates temporary clients on this same server and verifies:
both modes transfer an HTTPS request with the expected public exit IP;
a private destination is rejected; an incorrect UUID cannot transfer data;
pre-existing files and running service instances remain unchanged.
The baseline comparison is intended for deployment checks, not perpetual
monitoring: legitimate later provisioning or restarts will change it.

All four checks passed during deployment. Existing Xray, nginx, bot, Hysteria,
and proxy containers were not restarted. Original subscriptions stayed intact.
The new separate subscription returned HTTP 200 with certificate verification
for a Happ user agent. Android import and home-network connectivity still need
the owner's confirmation; server-local tests do not establish either.

## Certificates

The existing Let's Encrypt live and archive directories are mounted read-only.
Xray certificate loading is not one-time, allowing renewed files to be reread.
Certificate issuance/renewal is still managed separately on the master; this
test does not set up or modify renewal. Current certificate expires 2026-12-08.

## Rollback

```bash
cd /opt/hexenvpn-xhttp-test
docker compose -p hexenvpn-xhttp-test -f compose.yml down
```

Remove only the exact file named by `subscription_file` in the manifest from
`/var/www/sub`, and remove the separate test subscription from Happ.
Retain the root-only runtime directory for recovery. Do not stop the main
Compose stack, restart Docker, change SSH, or remove the normal subscriptions.

AmneziaWG was not installed: the owner chose only Happ-compatible experiments.

## References

- [XHTTP transport](https://xtls.github.io/en/config/transports/xhttp.html)
- [XHTTP modes and settings](https://github.com/XTLS/Xray-core/discussions/4113)
- [Happ Android](https://github.com/Happ-proxy/happ-android)
