# Telegram MTProxy on USA

Deployed 2026-09-10 at `82.39.214.176:9443` (TCP).
Separate Compose project and container: `hexenvpn-mtproxy`.
Runtime directory: `/opt/hexenvpn-mtproxy` on the master.
TR and notifier were not modified.

## Implementation

Matches the official `telegrammessenger/proxy` image found in the saved TR
Docker inventory, pinned by digest in `../mtproxy/compose.yml`.
Live SSH to TR timed out during this deployment, so the live TR configuration
was not verified. The [official repository](https://github.com/TelegramMessenger/MTProxy)
marks this image as outdated. Upgrade evaluation remains separate work.

The custom entrypoint downloads the current Telegram configuration and server
secret over verified HTTPS on each start. It avoids the image's legacy public-IP
discovery service and does not print the client secret in startup logs.
PUBLIC_IP in `.env` must be updated if the master IP changes again.

The independent client secret is generated on the server in `data/secret`.
Do not commit it or reuse a previous TR secret. The parent directory is mode
0700; the secret is 0600. Telegram links can use the `dd` prefix for random
padding; the stored secret remains 32 hex characters.

No promoted-channel tag was copied. Statistics ports are not published.
One worker, 4096 connection limit, 192 MiB memory, 0.5 CPU and 64 PID limits.
Read-only container root filesystem; the proxy drops to `nobody`.
Restart policy: `unless-stopped`. No VM reboot is required.

## Operations

Run through `adminops` and sudo on the master:

```sh
cd /opt/hexenvpn-mtproxy
sudo docker compose -p hexenvpn-mtproxy ps
sudo docker logs --tail 50 hexenvpn-mtproxy
sudo docker compose -p hexenvpn-mtproxy restart mtproxy
```

Restart fetches refreshed Telegram backend configuration. Telegram recommends
periodic refresh; no new scheduler was installed in this task.
To disable only this proxy, preserving its secret:

```sh
sudo docker compose -p hexenvpn-mtproxy down
```

## Verification

- Container running, zero restarts and no OOM at initial verification.
- External TCP connection to port 9443 from the user's Mac succeeded.
- Container has established outbound connections to Telegram backends.
- Xray, clients.json and nginx configuration hashes unchanged.
- Xray/bot container IDs and start times unchanged; HTTPS support returns 200.
- Actual Telegram client connection from the user's Wi-Fi still requires testing.

References: [official image documentation](https://hub.docker.com/r/telegrammessenger/proxy)
and [MTProxy README](https://github.com/TelegramMessenger/MTProxy).
