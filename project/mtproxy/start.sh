#!/bin/bash
set -Eeuo pipefail
umask 077
SECRET="$(cat /data/secret)"
[[ "$SECRET" =~ ^[0-9a-f]{32}$ ]]
[[ "$PUBLIC_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
# Avoid the legacy image's external IP discovery service and secret logging.
curl -fsS --connect-timeout 10 --max-time 45 --retry 2 \
  https://core.telegram.org/getProxySecret -o /tmp/proxy-secret
curl -fsS --connect-timeout 10 --max-time 45 --retry 2 \
  https://core.telegram.org/getProxyConfig -o /tmp/proxy-multi.conf
test -s /tmp/proxy-secret
grep -q 'proxy_for' /tmp/proxy-multi.conf
INTERNAL_IP="$(ip -4 route get 8.8.8.8 | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}')"
test -n "$INTERNAL_IP"
exec /usr/local/bin/mtproto-proxy -u nobody -p 2398 -H 9443 -M 1 -C 4096 \
  --aes-pwd /tmp/proxy-secret /tmp/proxy-multi.conf \
  --nat-info "$INTERNAL_IP:$PUBLIC_IP" -S "$SECRET"
