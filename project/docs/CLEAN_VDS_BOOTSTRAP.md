# Чистая VDS: автоматический bootstrap (bot + xray в Docker)

Этот сценарий поднимает новую VDS с нуля максимально автоматически:
- создаёт нужные директории,
- генерирует REALITY-ключи,
- создаёт `xray` конфиг,
- готовит `bot.env`,
- готовит `nodes.env`,
- валидирует конфиг,
- (опционально) сразу запускает Docker-стек.

## 1. Подготовка сервера
Вариант A (рекомендуется): передать в bootstrap ключ `--install-deps`, чтобы он сам установил пакеты.

Вариант B (вручную):
```bash
apt update
apt install -y git docker.io docker-compose-v2
systemctl enable --now docker
```

## 2. Клонирование проекта
```bash
mkdir -p /opt
cd /opt
git clone https://github.com/serghexen/vpn_vds.git
cd /opt/vpn_vds
```

## 3. Запуск bootstrap-скрипта
Пример:
```bash
project/scripts/bootstrap_clean_vds.sh \
  --install-deps \
  --domain vpn.example.com \
  --bot-token "<TELEGRAM_BOT_TOKEN>" \
  --admin-id 227380225 \
  --admin-usernames serg_hexen
```

Если хотите сразу поднять контейнеры:
```bash
project/scripts/bootstrap_clean_vds.sh \
  --install-deps \
  --domain vpn.example.com \
  --bot-token "<TELEGRAM_BOT_TOKEN>" \
  --admin-id 227380225 \
  --admin-usernames serg_hexen \
  --start
```

## 4. Что делает скрипт
- Создает директории:
  - `/usr/local/etc/xray`
  - `/var/lib/hexenvpn-bot`
  - `/var/lib/vless-sub`
  - `/var/www/sub`
- Создает `/var/lib/vless-sub/clients.json` (если отсутствует).
- (опционально) устанавливает зависимости через `apt`:
  - `docker.io`, `docker-compose-v2`, `python3`, `git`, `curl`, `ca-certificates`
- Генерирует:
  - REALITY private/public key
  - UUID первого клиента
  - `shortId`
- Рендерит `/usr/local/etc/xray/config.json` из `project/xray/config.template.json`.
- Создает/обновляет `project/env/bot.env` из `project/env/bot.env.example`.
- Создает/обновляет `project/env/nodes.env` из `project/env/nodes.env.example`.
  - автоматически проставляет `MASTER_HOST=<domain>` и `MASTER_PBK=<REALITY_PUBLIC_KEY>`
  - при наличии реплик нужно вручную дописать `UK_*`/`TR_*`
- Проверяет конфиг командой:
  - `docker run --rm -v /usr/local/etc/xray:/usr/local/etc/xray ghcr.io/xtls/xray-core:latest run -test -config /usr/local/etc/xray/config.json`
- Пишет сводку параметров в `/root/hexenvpn-bootstrap-<timestamp>.txt`.

## 5. Ручной запуск (если без `--start`)
```bash
docker compose -f /opt/vpn_vds/project/docker-compose.master-full.yml up -d
docker compose -f /opt/vpn_vds/project/docker-compose.master-full.yml ps
```

## 6. Проверка
```bash
docker logs --tail 100 hexenvpn-xray
docker logs --tail 100 hexenvpn-bot
ls -lah /var/lib/hexenvpn-bot/bot.db
```

## 7. Важный нюанс
Скрипт генерирует новый REALITY ключ и базовый xray-конфиг для чистого старта.
Параметры подключения клиентов берите из файла:
- `/root/hexenvpn-bootstrap-<timestamp>.txt`
