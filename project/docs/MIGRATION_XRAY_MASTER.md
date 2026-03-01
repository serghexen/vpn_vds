# Миграция: xray мастера -> Docker (с минимальным риском)

Документ описывает безопасный перевод `xray` на мастере (`86.104.72.155`) из systemd в Docker.
Сначала выполняется подготовка и проверка, затем короткое окно переключения с быстрым откатом.

## Цели
- Перевести `xray` в контейнер без потери данных и с минимальным простоем.
- Сохранить работоспособность Telegram-бота и выдачи/обновления подписок.

## Что должно быть уже готово
- Бот уже работает в Docker (`hexenvpn-bot` контейнер).
- На мастере есть актуальный репозиторий проекта (`/opt/vpn_vds`).
- Docker и `docker compose` установлены.

## 1. Предпроверки
```bash
cd /opt/vpn_vds

docker --version
docker compose version

systemctl is-active xray nginx
systemctl is-enabled xray nginx

docker ps --format 'table {{.Names}}\t{{.Status}}'
```

## 2. Бэкап перед миграцией (обязательно)
```bash
TS="$(date +%F_%H-%M-%S)"
BKP="/root/backup-xray-migration/$TS"
mkdir -p "$BKP"

cp -a /usr/local/etc/xray/config.json "$BKP/"
cp -a /etc/systemd/system/xray.service "$BKP/" || true
cp -a /etc/systemd/system/xray.service.d "$BKP/" || true
cp -a /var/lib/vless-sub/clients.json "$BKP/" || true
cp -a /var/www/sub "$BKP/" || true

ls -lah "$BKP"
```

## 3. Подготовка compose-конфига для мастера
Используем `project/docker-compose.master-full.yml` (сервисы `xray` + `bot`).

Важно:
- В compose используется host-конфиг `xray` из `/usr/local/etc/xray/config.json`.
- Перед переключением убедитесь, что текущий host-конфиг валиден (см. шаг 4).

## 4. Проверка конфига xray в Docker-режиме (без переключения)
```bash
docker compose -f project/docker-compose.master-full.yml pull xray

docker run --rm \
  -v /usr/local/etc/xray:/usr/local/etc/xray \
  ghcr.io/xtls/xray-core:latest \
  run -test -config /usr/local/etc/xray/config.json
```

Ожидается успешный тест без ошибок.

## 5. Подготовка короткого окна переключения
Перед переключением убедитесь, что:
- `hexenvpn-bot` контейнер запущен и стабилен.
- есть доступ к серверу по SSH из отдельной сессии (на случай отката).

Проверка:
```bash
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E 'hexenvpn-bot|hexenvpn-xray' || true
```

## 6. Переключение xray на Docker
```bash
cd /opt/vpn_vds

# Останавливаем host xray (чтобы не конфликтовал за 443)
systemctl stop xray
systemctl disable xray

# Поднимаем bot+xray в Docker (bot будет пересоздан с XRAY_RESTART_CMD под контейнерный xray)
docker compose -f project/docker-compose.master-full.yml up -d xray bot

# Проверка статуса и логов
docker compose -f project/docker-compose.master-full.yml ps
docker logs --tail 200 hexenvpn-xray
```

## 7. Проверка после переключения
1. Проверка сервисов:
```bash
docker ps --format 'table {{.Names}}\t{{.Status}}'
ss -ltnp | grep ':443' || true
```

2. Функциональная проверка:
- В Telegram: `/start`, `👤 Моя подписка`, админ-действие.
- Проверить добавление/удаление тестового пользователя (если допустимо), чтобы убедиться, что изменения в `config.json` применяются.

3. Контрольные логи:
```bash
docker logs --tail 200 hexenvpn-bot
docker logs --tail 200 hexenvpn-xray
```

## 8. Откат (если что-то пошло не так)
```bash
cd /opt/vpn_vds

# Останавливаем контейнер xray
docker compose -f project/docker-compose.master-full.yml stop xray bot

# Возвращаем host xray
systemctl enable --now xray
systemctl status xray --no-pager
```

Если нужно вернуть конфиг из бэкапа:
```bash
cp -a /root/backup-xray-migration/<TS>/config.json /usr/local/etc/xray/config.json
systemctl restart xray
```

## 9. После успешной миграции
- Оставляем `xray` в Docker, `nginx` и остальное — как согласовано.
- Обновляем эксплуатационные команды:
```bash
docker compose -f project/docker-compose.master-full.yml ps
docker compose -f project/docker-compose.master-full.yml restart xray
docker logs -f hexenvpn-xray
```

## Примечания по рискам
- Главный риск: конфликт порта `443`, если host xray не остановлен перед запуском контейнера.
- Главный способ снижения риска: короткое окно переключения + заранее проверенный конфиг + готовый rollback.
- Данные клиентов (`clients.json`) и подписки (`/var/www/sub`) не теряются, так как остаются на хосте.
