# Runbook: упала реплика UK/TR

Этот runbook для безопасной диагностики и восстановления отдельной реплики без изменений на мастере.

## Быстрые команды

Проверка UK:
```bash
project/scripts/healthcheck_replica.sh --node uk
```

Проверка TR:
```bash
project/scripts/healthcheck_replica.sh --node tr
```

Проверка с конкретным пользователем:
```bash
project/scripts/healthcheck_replica.sh --node uk --user test1
```

## Что проверяет `healthcheck_replica.sh`
- доступ по SSH до реплики;
- состояние `xray` (docker-контейнер `hexenvpn-xray` или `systemd`-сервис);
- порт `443` в LISTEN;
- дубли `id/email` в `/usr/local/etc/xray/config.json`;
- (опционально) что пользователь есть ровно 1 раз.

## Мягкий рестарт Xray на реплике

UK:
```bash
project/scripts/replica_ops.sh --node uk --action restart-post
```

TR:
```bash
project/scripts/replica_ops.sh --node tr --action restart-post
```

`restart-post` делает:
1. мягкий рестарт `xray` на реплике;
2. пауза 2 сек;
3. полный post-check через `healthcheck_replica.sh`.

## Режимы `replica_ops.sh`

- `--action diag` - только диагностика;
- `--action restart` - только рестарт;
- `--action postcheck` - только post-check;
- `--action restart-post` - рестарт + post-check (рекомендуется).

Пример:
```bash
project/scripts/replica_ops.sh --node tr --action restart-post --user test1
```

## Отдельные алерты в Telegram по репликам

В `project/env/bot.env`:
```env
REPLICA_MONITOR_ENABLED=1
REPLICA_MONITOR_INTERVAL_SEC=300
REPLICA_MONITOR_COOLDOWN_SEC=1800
REPLICA_MONITOR_CMD=/usr/local/sbin/healthcheck-replica
```

Применить:
```bash
docker compose -f project/docker-compose.master-full.yml up -d --no-deps --build bot
```

После включения бот шлет отдельные уведомления:
- проблема на UK;
- проблема на TR;
- отдельное уведомление о восстановлении каждой реплики.

## Если SSH до реплики недоступен

1. Проверить доступ ключом:
```bash
ssh -i /root/.ssh/vless_sync_ed25519 -o BatchMode=yes -o IdentitiesOnly=yes root@<replica_ip> "echo OK"
```
2. Проверить firewall/sshd на реплике через консоль провайдера.
3. После восстановления SSH - повторить `diag`, затем `restart-post`.

