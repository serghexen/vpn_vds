# Backup/Restore мастера (лёгкий режим)

Цель: сохранять критичные данные мастера с минимальной нагрузкой на VM.

Скрипты:
- `project/scripts/backup_master.sh`
- `project/scripts/restore_master.sh`

## Что попадает в backup
- `/var/lib/hexenvpn-bot/bot.db` (SQLite online backup)
- `/var/lib/vless-sub/clients.json`
- `/var/lib/vless-sub/happ-links.json`
- `/usr/local/etc/xray/config.json`
- `/etc/nginx/njs/subscription.js`
- `project/env/bot.env`
- `project/env/nodes.env`

## Ручной backup
```bash
cd /opt/vpn_vds
project/scripts/backup_master.sh
```

По умолчанию:
- каталог: `/root/backup-master/<timestamp>`
- ротация: хранится 14 последних backup

Примеры:
```bash
# хранить только последние 7 backup
project/scripts/backup_master.sh --keep-count 7

# свой каталог backup
project/scripts/backup_master.sh --backup-root /root/backup-vpn

# backup с меткой в имени каталога
project/scripts/backup_master.sh --label before-update
```

## Автоматический backup (cron)
Пример: каждый день в 04:15.

```bash
crontab -e
```

Добавить строку:
```cron
15 4 * * * cd /opt/vpn_vds && project/scripts/backup_master.sh --keep-count 14 >> /var/log/hexenvpn-backup.log 2>&1
```

## Restore
Восстановление из последнего backup:
```bash
cd /opt/vpn_vds
project/scripts/restore_master.sh --from latest --yes
```

Restore из конкретного каталога:
```bash
project/scripts/restore_master.sh --from /root/backup-master/2026-02-28_12-00-00 --yes
```

Важно:
- Перед восстановлением скрипт автоматически делает safety backup (`pre-restore`).
- По умолчанию после restore пересоздаются docker-сервисы `xray` и `bot`.
- По умолчанию запускается `healthcheck_master_replicas.sh`.

Опции:
```bash
# без перезапуска контейнеров
project/scripts/restore_master.sh --from latest --no-restart --yes

# без post-check
project/scripts/restore_master.sh --from latest --no-postcheck --yes

# дополнительно проверить конкретного пользователя
project/scripts/restore_master.sh --from latest --check-user test1 --yes
```
