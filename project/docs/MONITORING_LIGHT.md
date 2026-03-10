# Лёгкий мониторинг через Telegram-бота

Реализация без Prometheus/Grafana и без заметной нагрузки на VM.

## Что добавлено
- Скрипт метрик: `project/scripts/metrics_master_light.sh`
- В админке бота: кнопка `📊 Состояние узла`
- В админке бота: кнопка `📈 Трафик узлов` (за 24ч и с начала месяца)
- Команда бота: `/health` (только для админа)
- Отдельный healthcheck реплик: `project/scripts/healthcheck_replica.sh`

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

## Отдельные алерты UK/TR (опционально)

Если нужно получать отдельные уведомления по каждой реплике:

1. В `project/env/bot.env` включить:
```env
REPLICA_MONITOR_ENABLED=1
REPLICA_MONITOR_INTERVAL_SEC=300
REPLICA_MONITOR_COOLDOWN_SEC=1800
REPLICA_MONITOR_CMD=/usr/local/sbin/healthcheck-replica
```

2. Перезапустить бота:
```bash
docker compose -f project/docker-compose.master-full.yml up -d --no-deps --build bot
```

Бот будет отправлять отдельные алерты:
- по UK;
- по TR;
- отдельные сообщения о восстановлении каждой реплики.

## Авто-отчет по трафику узлов (опционально)

В `project/env/bot.env`:
```env
TRAFFIC_REPORT_ENABLED=1
TRAFFIC_REPORT_INTERVAL_SEC=300
TRAFFIC_REPORT_HOUR=10
TRAFFIC_REPORT_MINUTE=0
```

Что делает:
- бот раз в день после указанного времени отправляет админам отчет по узлам:
  - трафик за 24 часа;
  - трафик с начала текущего месяца.
