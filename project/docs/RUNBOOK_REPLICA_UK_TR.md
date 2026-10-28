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

Проверка цепочки `RU -> TR` (если включен bridge-режим через `TR_LINK_HOST`):
```bash
project/scripts/healthcheck_ru_tr_bridge.sh
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

## Что проверяет `healthcheck_ru_tr_bridge.sh`
- что `TR_LINK_HOST` (RU) и `TR_HOST` доступны по SSH;
- что `xray` активен и на RU, и на TR;
- что RU принимает пользователей (и опционально `--user`);
- что RU outbound смотрит на `TR_HOST:TR_VLESS_PORT`;
- что bridge UUID из RU outbound существует в TR inbound;
- что `publicKey` RU->TR совпадает с фактическим TR REALITY public key;
- что `TR_LINK_PBK` (или fallback `TR_PBK`) совпадает с фактическим RU REALITY public key.

Важно:
- в bridge-режиме ключ для ссылки на турецкий профиль должен задаваться в `TR_LINK_PBK` (это ключ RU-входа);
- `TR_PBK` можно оставить для обратной совместимости, но предпочтительно использовать `TR_LINK_PBK`.
- скрипты `vless-add-user`/`vless-del-user` в bridge-режиме автоматически синхронизируют пользователя и на RU-вход (`TR_LINK_HOST`), чтобы новые аккаунты сразу работали через `RU -> TR`.

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

## Рестарт из админки бота

В `🛠 Админка` -> `🖥 Сервис` доступны кнопки:
- `🔁 Рестарт UK`
- `🔁 Рестарт TR`

Сценарий безопасный:
1. бот спрашивает подтверждение;
2. выполняет `restart-post` через `replica_ops.sh`;
3. показывает результат в чате админа.

## Если SSH до реплики недоступен

1. Проверить доступ ключом:
```bash
ssh -i /root/.ssh/vless_sync_ed25519 -o BatchMode=yes -o IdentitiesOnly=yes root@<replica_ip> "echo OK"
```
2. Проверить firewall/sshd на реплике через консоль провайдера.
3. После восстановления SSH - повторить `diag`, затем `restart-post`.
