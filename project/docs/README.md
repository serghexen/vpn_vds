# Базовая конфигурация VPN-проекта (с мастера)

В проекте хранится воспроизводимая базовая конфигурация:
- сервис Xray и его конфиг
- сервис Telegram-бота и код бота
- конфиги Nginx для эндпоинтов подписок
- скрипты управления пользователями (`vless-add-user`, `vless-del-user`, `vless-sync-expire`)

## Структура
- `bot/bot.py` - код бота с мастера
- `systemd/*.service` - unit-файлы сервисов
- `xray/config.template.json` - обезличенный шаблон конфига
- `nginx/*.conf` - конфиги Nginx с мастера
- `nginx/njs/subscription.js` - NJS-логика для `/sub/*` и `/i/*` (включая страницы импорта iOS/Android)
- `scripts/vless-*` - скрипты управления с мастера
- `env/bot.env.example` - обезличенный шаблон переменных окружения
- `env/nodes.env.example` - шаблон параметров мастер/реплик для ссылок и синхронизации
- `state/clients.seed.template.json` - обезличенный пример снимка клиентов

## Политика секретов
Не коммитьте продовые секреты.
Игнорируется git:
- `project/env/bot.env`
- `project/xray/config.json`
- `project/state/clients.json`
- `project/master/` (сырой дамп файлов с сервера)

## Развертывание на мастер
1. Подготовьте секретные файлы:
   - `cp project/env/bot.env.example project/env/bot.env` и укажите реальный токен/админов
   - `cp project/xray/config.template.json project/xray/config.json` и заполните реальные ключи/клиентов
2. Запустите:
   - `project/scripts/deploy_master.sh 86.104.72.155`

Скрипт проверяет конфиг Xray и перезапускает `xray`, `hexenvpn-bot`, `nginx`.
Также обновляет `/etc/nginx/njs/subscription.js` на сервере.

## Docker (локальный проект)
`xray` и `bot` могут запускаться в Docker через compose.

1. Инициализируйте runtime-файлы:
   - `project/scripts/init_docker_runtime.sh`
2. Заполните секреты/конфиги:
   - `project/env/bot.env`
   - `project/env/nodes.env` (`MASTER_HOST`, `MASTER_PBK`, опционально `UK_*`/`TR_*`)
   - `project/runtime/xray/config.json`
   - (опционально) SSH-ключ для синхронизации реплик: `project/env/ssh/vless_sync_ed25519`
3. Запустите:
   - `docker compose -f project/docker-compose.yml up -d --build`

Примечания:
- Скрипты бота поддерживают Docker-режим (`XRAY_AUTORELOAD=1`) и не требуют `systemctl` в контейнере.
- Контейнер Xray перечитывает конфиг через перезапуск процесса при изменении `config.json` в примонтированном volume.

## Миграция только бота на мастере
Используйте `project/docker-compose.master-bot.yml`, если нужно перенести в Docker только Telegram-бот, а `xray`/`nginx` оставить в systemd на хосте.

Полная инструкция:
- `project/docs/MIGRATION_BOT_MASTER.md`

## Миграция xray на мастере
Безопасный поэтапный runbook для перевода `xray` из systemd в Docker:
- `project/docs/MIGRATION_XRAY_MASTER.md`

Для миграции используется compose-файл:
- `project/docker-compose.master-full.yml`

## Развертывание на чистой VDS (автоматизация)
Полный bootstrap-сценарий для нового сервера:
- `project/docs/CLEAN_VDS_BOOTSTRAP.md`

Bootstrap-скрипт:
- `project/scripts/bootstrap_clean_vds.sh`
- Поддерживает `--install-deps` для установки Docker/Compose/Python на новой VDS.

## Операционный healthcheck и инциденты
- Скрипт быстрой проверки master+replicas:
  - `project/scripts/healthcheck_master_replicas.sh`
- Безопасный релиз на мастере (docker xray+bot + rollback):
  - `project/scripts/release_master.sh`
- Backup/restore мастера:
  - `project/scripts/backup_master.sh`
  - `project/scripts/restore_master.sh`
  - `project/docs/BACKUP_RESTORE_MASTER.md`
- Smoke test мастера:
  - `project/scripts/smoke_test_master.sh`
  - `project/docs/SMOKE_TEST_MASTER.md`
- Hardening мастера:
  - `project/scripts/harden_master.sh`
  - `project/docs/HARDENING_MASTER.md`
- Лёгкий мониторинг в Telegram:
  - `project/scripts/metrics_master_light.sh`
  - `project/docs/MONITORING_LIGHT.md`
- Оценка ёмкости:
  - `project/scripts/capacity_estimate.sh`
  - `project/docs/SIZING.md`
- Короткий anti-incident runbook:
  - `project/docs/INCIDENT_2MIN.md`
- TODO проекта:
  - `project/docs/TODO.md`
- Фоновый мониторинг в Telegram (бот):
  - включается переменными `MONITOR_*` в `project/env/bot.env`
  - отправляет алерты администраторам (`PRIMARY_ADMIN_TG_ID` + `ADMIN_TG_IDS`) при проблемах healthcheck

## Автозапуск после reboot (обязательно)
Чтобы после перезагрузки VDS сервисы поднимались автоматически:

1. Docker должен быть включен в systemd:
   - `systemctl enable docker`
   - `systemctl is-enabled docker` -> `enabled`
2. Контейнеры должны иметь restart policy:
   - `docker inspect -f '{{.Name}} -> {{.HostConfig.RestartPolicy.Name}}' hexenvpn-bot hexenvpn-xray`
   - ожидается `unless-stopped`

Если policy не применена, пересоздайте контейнеры из compose:
- `docker compose -f project/docker-compose.master-full.yml up -d --force-recreate`

## SSH доступ к мастеру
- Подключение по ключу:
  - `ssh -i ~/.ssh/id_rsa -o IdentitiesOnly=yes adminops@86.104.72.155`
- Быстрая проверка:
  - `hostname && whoami`
- Примечание:
  - парольный вход в SSH отключен, рабочий сценарий — только через ключ.

## Первый запуск на чистой VDS
При первом старте бота база создается автоматически, вручную создавать SQLite-файл и таблицы не нужно.

Что происходит:
1. Контейнер бота стартует.
2. В `bot.py` вызывается `init_db(...)`.
3. Если `/var/lib/hexenvpn-bot/bot.db` отсутствует, SQLite создаёт файл.
4. Автоматически создаются таблицы:
   - `tg_users`
   - `admin_state`
   - `provisioning_jobs`

Важно:
- База находится на хосте в `/var/lib/hexenvpn-bot/bot.db` (через bind-mount), а не внутри образа.
- При перезапуске или пересоздании контейнера данные сохраняются.

Проверка после первого запуска:
```bash
ls -lah /var/lib/hexenvpn-bot/bot.db
```
