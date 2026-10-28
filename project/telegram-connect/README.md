# USA Telegram API CONNECT proxy

Deployed 2026-09-10. Endpoint: `http://82.39.214.176:3128`.
Separate runtime directory: `/opt/hexenvpn-telegram-connect` on USA.
Compose project and container: `hexenvpn-telegram-connect`.

This is an HTTP CONNECT proxy for service HTTPS requests, not the Telegram
MTProxy on port 9443. The notifier host was not accessed or changed.

Consumer setting (apply in the other project):

```dotenv
SELLER_TELEGRAM_HTTPS_PROXY=http://82.39.214.176:3128
```

Access is restricted to source `89.110.88.203/32`, the previously supplied
service host IP. Only CONNECT to `api.telegram.org:443` is allowed. Loopback
inside the container is permitted for diagnostics. All other requests are
denied. If the service's actual outbound IP changes, update the source ACL;
do not replace it with an unrestricted allow rule. No password is needed.

TLS is tunneled, not intercepted. No bot tokens were needed for testing.
Access logging and caching are disabled. Read-only, non-root container with
128 MiB memory, 0.5 CPU and 4096 file-descriptor limits; automatic restart is
enabled. The file-descriptor limit avoids excessive startup allocation.

## Operations

```sh
cd /opt/hexenvpn-telegram-connect
sudo docker compose -p hexenvpn-telegram-connect ps
sudo docker logs --tail 30 hexenvpn-telegram-connect
sudo docker compose -p hexenvpn-telegram-connect restart proxy
# Disable only this proxy:
sudo docker compose -p hexenvpn-telegram-connect down
```

## Verification

- Real CONNECT from the container network namespace: 200; Telegram HTTPS
  response 302; TLS certificate verification successful.
- Other destination denied with 403, even for the local diagnostic client.
- External request from an unauthorized source denied with 403.
- Final container state running, zero restarts/OOM, about 12 MiB used.
- Existing Xray/bot/MTProxy IDs and start times unchanged; configuration hashes
  match pre-deployment values. Subscription support HTTPS returns 200.
- No connection was made to the service host; integration must be verified
  by its owner after updating the setting in the separate project.

Sources: [Canonical Squid image](https://hub.docker.com/r/ubuntu/squid),
[Squid access rules](https://www.squid-cache.org/Doc/config/http_access/).
