# Базовая конфигурация VPN-проекта (с мастера)

## Независимое восстановление: 28.10.2026

По запросу владельца создана и проверена свежая локальная копия в закрытом
каталоге `backups/recovery-20261028/`, исключенном из Git. Она дополняет
прежние копии только на сервере. SHA-256, SQLite, подписки, TLS-ключи и слои
Docker-образов проверены на сервере и после скачивания на Mac.
Код и шаблоны хранятся в Git; секреты, БД, сертификаты и Docker-образы отдельно.
Инструкция: [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md).
Скрипты: `project/scripts/backup_recovery_bundle.py` и
`project/scripts/verify_recovery_bundle.py`.
Проверка архива не заменяет пробное восстановление на новой ВМ.

## Действующая инфраструктура: 26.10.2026

- Мастер США: `82.21.92.91`, домены `serghexen.ru` и `23pr.serghexen.ru`.
  Предыдущий адрес `82.39.214.176` больше не используется.
- TR `193.46.56.199` выведена из эксплуатации. UK также отключена.
  Упоминания TR, RU -> TR и старых адресов ниже и в прежних runbook описывают
  доступные шаблоны или историю, а не действующие узлы.
- В runtime `nodes.env`: `TR_HOST`, `TR_LINK_HOST`, `TR_PBK`, `TR_LINK_PBK`,
  `TR_WS_HOST`, `TR_WS_SNI` пусты; `TR_WS_ENABLED=0`.
  При отсутствии реплик `REPLICA_MONITOR_ENABLED=0`; монитор мастера включен.
- TR-профили удалены из обеих копий подписок всех 19 пользователей
  (имя и токен). Тест USA via TR снят с выдачи. Пользователи, UUID, сроки,
  исторические записи трафика и резервные копии сохранены.
- Админка показывает диагностику/рестарт только включенных реплик;
  кнопки отключенных узлов в старых сообщениях больше не запускают команды.
- Hysteria UDP 443/2443 и MTProxy 9443 переведены на новый адрес.
  HTTP CONNECT для внешнего notifier: `http://82.21.92.91:3128`.
  Сам notifier не изменялся; его переменную меняет владелец другого проекта.
- Отдельный личный тест VLESS + XHTTP + TLS на `2096/TCP`: контейнер
  `hexenvpn-xhttp-test`, инструкции в `project/xhttp-test/README.md`.
  В общую подписку не включен; AmneziaWG не устанавливалась.
- Отдельный личный тест Trojan + TLS на `2087/TCP`: контейнер
  `hexenvpn-trojan-test`, инструкции в `project/trojan-test/README.md`.
  В общую подписку не включен; сроками и блокировками бота не управляется.
- A-запись `tr.serghexen.ru` следует удалить в панели DNS. Старые клиентские
  подписки нужно обновить, чтобы убрать Турцию из приложения.

Бэкапы на мастере: `/root/backup-ip-change-20261026T141352Z` и
`/root/backup-retire-tr-20261026T142236Z`. По решению владельца новые копии
оставлены только на сервере; на локальный компьютер они не переносились.
Основной Xray, SSH и firewall при этой операции не менялись; пересоздавался
бот для применения env, а также отдельные Hysteria/MTProxy контейнеры.

Указание "только на сервере" выше относится к операции 26.10.2026.
28.10.2026 владелец отдельно разрешил локальную копию с секретами;
результат и инструкция восстановления приведены в начале документа.

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
   - для bridge-схемы `RU -> TR`: задайте `TR_LINK_HOST=<RU_IP>` и `TR_LINK_PBK=<RU_REALITY_PUBLIC_KEY>`
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

## Миграция xray на репликах (UK/TR)
Безопасный поэтапный runbook для перевода реплик из systemd в Docker:
- `project/docs/MIGRATION_REPLICA_DOCKER.md`

## Развертывание на чистой VDS (автоматизация)
Полный bootstrap-сценарий для нового сервера:
- `project/docs/CLEAN_VDS_BOOTSTRAP.md`

Bootstrap-скрипт:
- `project/scripts/bootstrap_clean_vds.sh`
- Поддерживает `--install-deps` для установки Docker/Compose/Python на новой VDS.

## Операционный healthcheck и инциденты
- Скрипт быстрой проверки master+replicas:
  - `project/scripts/healthcheck_master_replicas.sh`
- Проверка bridge-цепочки `RU -> TR` (если включен `TR_LINK_HOST`):
  - `project/scripts/healthcheck_ru_tr_bridge.sh`
- Отдельная проверка конкретной реплики:
  - `project/scripts/healthcheck_replica.sh --node uk`
  - `project/scripts/healthcheck_replica.sh --node tr`
- Быстрые ops-команды по реплике (диагностика/рестарт/postcheck):
  - `project/scripts/replica_ops.sh --node uk --action restart-post`
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
  - в админке: `📈 Трафик узлов` + опциональный daily-отчет по узлам
  - опциональные алерты аномалий трафика/сессий
- Оценка ёмкости:
  - `project/scripts/capacity_estimate.sh`
  - `project/docs/SIZING.md`
- Короткий anti-incident runbook:
  - `project/docs/INCIDENT_2MIN.md`
- Runbook «упала реплика UK/TR»:
  - `project/docs/RUNBOOK_REPLICA_UK_TR.md`
- TODO проекта:
  - `project/docs/TODO.md`
- Фоновый мониторинг в Telegram (бот):
  - включается переменными `MONITOR_*` в `project/env/bot.env`
  - отправляет алерты администраторам (`PRIMARY_ADMIN_TG_ID` + `ADMIN_TG_IDS`) при проблемах healthcheck

## Резервный master-профиль WS+TLS

На мастере параллельно с `VLESS TCP REALITY :443` может работать профиль `VLESS WebSocket TLS :2053`:

- nginx принимает TLS на `2053` и проксирует `/api/v1/stream` на `127.0.0.1:10086`;
- Xray слушает WS-вход только через локальный Docker port mapping;
- `vless-add-user`, `vless-del-user` и `vless-sync-expire` синхронизируют оба master-inbound;
- `refresh_master_ws_alt.py` добавляет ALT-ссылку существующим пользователям;
- end-to-end проверка: `project/scripts/smoke_test_master_ws_alt.sh <vpn_name>`.

Переменные находятся в `project/env/nodes.env.example` (`MASTER_WS_*`).

## Резервный TR-профиль WS+TLS

TR может одновременно обслуживать старый `VLESS TCP REALITY :443` и резервный `VLESS WebSocket TLS :2053`.

- переменные: `project/env/nodes.env.example` (`TR_WS_*`);
- обновление существующих подписок: `project/scripts/refresh_tr_ws_alt.py`;
- nginx-шаблон: `project/nginx/replica-ws.conf.template`;
- Xray inbound-шаблон: `project/xray/replica-ws-inbound.template.json`;
- инструкция и откат: `project/docs/REPLICA_WS_TLS.md`.

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
  - `ssh -i ~/.ssh/id_rsa -o IdentitiesOnly=yes adminops@serghexen.ru`
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
