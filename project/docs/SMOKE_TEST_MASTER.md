# Smoke test мастера (лёгкая проверка)

Скрипт:
- `project/scripts/smoke_test_master.sh`

Проверяет:
1. Контейнеры `hexenvpn-xray` и `hexenvpn-bot` в статусе `Up`.
2. Порт `443` слушается на мастере.
3. `healthcheck_master_replicas.sh` проходит успешно.
4. `healthcheck_ru_tr_bridge.sh` проходит успешно (или `SKIP`, если bridge-режим не включен).
5. (Опционально) HTTP:
   - `GET <BASE_URL>/sub/<user>` -> `200`
   - `GET <BASE_URL>/i/<user>` -> `200`

## Быстрый запуск
```bash
cd /opt/vpn_vds
bash project/scripts/smoke_test_master.sh
```

## Запуск с проверкой конкретного пользователя
```bash
bash project/scripts/smoke_test_master.sh --check-user test1
```

## Если на сервере самоподписанный сертификат
```bash
bash project/scripts/smoke_test_master.sh --check-user test1 --insecure
```

## Если нужно пропустить проверку RU->TR bridge
```bash
bash project/scripts/smoke_test_master.sh --skip-ru-tr-bridge-check
```

Примечания:
- `BASE_URL` берётся из `project/env/bot.env` (`BASE_URL=...`), если не передан через `--base-url`.
- Если `--check-user` не указан, скрипт пробует взять `MONITOR_CHECK_USER` из `project/env/bot.env`.
