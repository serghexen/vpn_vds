# Лёгкий мониторинг через Telegram-бота

Реализация без Prometheus/Grafana и без заметной нагрузки на VM.

## Что добавлено
- Скрипт метрик: `project/scripts/metrics_master_light.sh`
- В админке бота: кнопка `📊 Состояние узла`
- Команда бота: `/health` (только для админа)

## Какие метрики показывает
- host, uptime
- load average и число CPU
- RAM (used/total/avail)
- диск `/` (used/total/free/use%)
- статус и restart count контейнеров `hexenvpn-xray` и `hexenvpn-bot`
- размеры `bot.db` и `clients.json`

## Что нужно для работы
В compose для `bot` должен быть смонтирован скрипт:
- `/usr/local/sbin/metrics-master-light`

И переменная окружения:
- `METRICS_CMD=/usr/local/sbin/metrics-master-light`

Это уже добавлено в:
- `project/docker-compose.master-full.yml`
- `project/docker-compose.master-bot.yml`
- `project/docker-compose.yml`

## Проверка
На мастере после обновления проекта:
```bash
cd /opt/vpn_vds
docker compose -f project/docker-compose.master-full.yml up -d --force-recreate bot
docker exec hexenvpn-bot sh -lc '/usr/local/sbin/metrics-master-light'
```

Далее в Telegram:
- открыть `🛠 Админка` -> `📊 Состояние узла`
- или отправить `/health`
