# Миграция реплики (UK/TR) на Docker Compose

Цель: перевести `xray` на реплике с `systemd` на Docker максимально безопасно и с быстрым откатом.

## Что важно
- Перед переключением делается backup конфига и unit-данных.
- По умолчанию скрипт работает в `dry-run` (без изменений).
- При сбое переключения скрипт автоматически пытается вернуть `systemd`.
- Проверка после миграции выполняется через `healthcheck_replica.sh`.

## Файлы
- Compose-профиль реплики:
  - `project/docker-compose.replica-xray.yml`
- Скрипт миграции:
  - `project/scripts/migrate_replica_to_docker.sh`
- Проверка реплики:
  - `project/scripts/healthcheck_replica.sh`

## Рекомендуемый порядок (сначала UK, потом TR)

### 1) Dry-run UK (без изменений)
```bash
project/scripts/migrate_replica_to_docker.sh --node uk
```

### 2) Применить UK
```bash
project/scripts/migrate_replica_to_docker.sh --node uk --apply
```

Что делает `--apply`:
1. precheck (`docker`, `compose`, test конфига);
2. backup на реплике в `/root/backup-replica-docker-migrate/<timestamp>`;
3. загрузка compose в `/opt/hexenvpn-replica/docker-compose.yml`;
4. switch runtime: `systemd stop xray` -> `docker compose up -d xray`;
5. проверка порта `443`, статуса контейнера;
6. postcheck через `healthcheck_replica.sh`.

### 3) Проверка после переключения
```bash
project/scripts/healthcheck_replica.sh --node uk
docker exec hexenvpn-bot sh -lc '/usr/local/sbin/healthcheck-replica --node uk'
```

### 4) Если что-то не так — rollback
```bash
project/scripts/migrate_replica_to_docker.sh --node uk --rollback
```

Rollback:
- `docker compose down` на реплике;
- `systemctl start xray`;
- проверка порта `443`.

## После стабилизации UK
Повторить те же шаги для TR:
```bash
project/scripts/migrate_replica_to_docker.sh --node tr
project/scripts/migrate_replica_to_docker.sh --node tr --apply
```

## Критерии “миграция успешна”
- `healthcheck_replica.sh --node <uk|tr>` -> `RESULT: OK`;
- в админке работает `🔍 Диаг UK/TR`;
- создание/удаление пользователя не ломает синхронизацию;
- на реплике `hexenvpn-xray` в статусе `running`, порт `443` слушает.

