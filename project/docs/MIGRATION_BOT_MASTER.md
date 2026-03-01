# Миграция: бот мастера -> Docker (xray остается на хосте)

Эта миграция переносит только `hexenvpn-bot` в Docker на мастере.
`xray` и `nginx` остаются под управлением systemd на хосте.

## Предусловия
- Выполнять на мастере (`86.104.72.155`)
- Установлены Docker и compose plugin
- Репозиторий проекта уже находится на хосте

## 1. Предпроверки
```bash
systemctl is-active hexenvpn-bot xray nginx
systemctl is-enabled hexenvpn-bot xray nginx
```

## 2. Бэкап (обязательно)
```bash
TS="$(date +%F_%H-%M-%S)"
mkdir -p /root/backup-bot-migration/$TS
cp -a /var/lib/hexenvpn-bot /root/backup-bot-migration/$TS/
cp -a /var/lib/vless-sub /root/backup-bot-migration/$TS/
cp -a /var/www/sub /root/backup-bot-migration/$TS/
cp -a /opt/hexenvpn-bot /root/backup-bot-migration/$TS/
cp -a /etc/hexenvpn-bot /root/backup-bot-migration/$TS/
cp -a /usr/local/etc/xray/config.json /root/backup-bot-migration/$TS/
```

## 3. Подготовка env-файла в проекте
```bash
cp --update=none project/env/bot.env.example project/env/bot.env
# укажите в project/env/bot.env реальный BOT_TOKEN и admin-параметры
chmod +x project/scripts/vless-add-user project/scripts/vless-del-user project/scripts/vless-sync-expire
```

## 4. Сборка образа бота
```bash
docker compose -f project/docker-compose.master-bot.yml build bot
```

## 5. Переключение
```bash
systemctl stop hexenvpn-bot
systemctl disable hexenvpn-bot

docker compose -f project/docker-compose.master-bot.yml up -d bot
```

## 6. Проверка
```bash
docker compose -f project/docker-compose.master-bot.yml ps
docker logs --tail 200 hexenvpn-bot
```

В Telegram проверьте:
- `/start`
- `👤 Моя подписка`
- одно действие из админки (`📋 Список пользователей`)

## 7. Откат (если потребуется)
```bash
docker compose -f project/docker-compose.master-bot.yml down
systemctl enable hexenvpn-bot
systemctl start hexenvpn-bot
systemctl status hexenvpn-bot --no-pager
```

## Примечания
- База пользователей сохраняется, потому что контейнер напрямую монтирует хостовый `/var/lib/hexenvpn-bot`.
- `clients.json` и `/var/www/sub` тоже монтируются с хоста, поэтому данные подписок сохраняются.
- Скрипты бота перезапускают host `xray` через `nsenter ... systemctl restart xray`.
