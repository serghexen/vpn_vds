# Hardening мастера (лёгкий, без заметной нагрузки)

Скрипт:
- `project/scripts/harden_master.sh`

Что настраивает:
1. SSH hardening через drop-in: `/etc/ssh/sshd_config.d/90-hexenvpn-hardening.conf`
2. UFW:
   - `deny incoming`
   - `allow outgoing`
   - `allow` для SSH-порта и нужных TCP-портов (`443,8443`)
3. fail2ban для `sshd`.

Перед запуском:
- Откройте вторую SSH-сессию на сервер (на случай отката).
- Убедитесь, что заходите по SSH-ключу, не по паролю.

## Запуск
```bash
cd /opt/vpn_vds
bash project/scripts/harden_master.sh --install-deps
```

Если SSH не на `22`:
```bash
bash project/scripts/harden_master.sh --install-deps --ssh-port 2222
```

Если нужны дополнительные открытые порты:
```bash
bash project/scripts/harden_master.sh --allow-ports 443,8443,80
```

## Проверка после запуска
```bash
sshd -t && echo "sshd config OK"
systemctl is-active ssh || systemctl is-active sshd
ufw status verbose
systemctl is-active fail2ban
fail2ban-client status sshd
```

Проверка VPN-сервисов:
```bash
cd /opt/vpn_vds
bash project/scripts/smoke_test_master.sh
```

## Откат
Скрипт всегда делает backup в:
- `/root/backup-hardening/<timestamp>`

Ручной откат (пример):
```bash
TS="<timestamp>"
cp -a /root/backup-hardening/$TS/etc/ssh/sshd_config /etc/ssh/sshd_config
cp -a /root/backup-hardening/$TS/etc/ssh/sshd_config.d /etc/ssh/
cp -a /root/backup-hardening/$TS/etc/ufw /etc/
cp -a /root/backup-hardening/$TS/etc/fail2ban /etc/
sshd -t
systemctl reload ssh || systemctl reload sshd
systemctl restart ufw fail2ban
```
