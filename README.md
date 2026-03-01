# vpn_vds

Базовый IaC-проект для VPN-стека на основе текущей конфигурации мастера:
- Xray (`reality`, VLESS)
- Nginx для эндпоинтов подписок
- Telegram-бот (`hexenvpn-bot`)
- Скрипты жизненного цикла пользователей (`vless-add-user`, `vless-del-user`, `vless-sync-expire`)

## Основные файлы проекта
- `project/bot/bot.py`
- `project/systemd/*.service`
- `project/nginx/*.conf`
- `project/nginx/njs/subscription.js`
- `project/scripts/vless-*`
- `project/xray/config.template.json`
- `project/env/bot.env.example`
- `project/env/nodes.env.example`
- `project/replicas/*/xray.config.template.json`

## Развертывание
- Мастер: `project/scripts/deploy_master.sh 86.104.72.155`
- Реплика: `project/scripts/deploy_replica.sh <ip> project/replicas/<ip>`
- Локально в Docker: `project/scripts/init_docker_runtime.sh`, затем `docker compose -f project/docker-compose.yml up -d --build`

После развертывания на мастере зафиксировать автозапуск:
- `systemctl enable docker`
- `docker inspect -f '{{.Name}} -> {{.HostConfig.RestartPolicy.Name}}' hexenvpn-bot hexenvpn-xray` (должно быть `unless-stopped`)

## SSH доступ к VM
- Рабочий вход на мастер: `ssh -i ~/.ssh/id_rsa -o IdentitiesOnly=yes adminops@86.104.72.155`
- Проверка после входа: `hostname && whoami`
- Парольный вход в SSH отключен, используем только ключи.

Подробности:
- `project/docs/README.md`
- `project/docs/REPLICAS.md`
- `project/docs/INCIDENT_2MIN.md`
- `project/docs/BACKUP_RESTORE_MASTER.md`
- `project/docs/SMOKE_TEST_MASTER.md`
- `project/docs/HARDENING_MASTER.md`
- `project/docs/MONITORING_LIGHT.md`
- `project/docs/SIZING.md`
- `project/scripts/release_master.sh` (безопасный релиз на мастере с проверками и rollback)

## Безопасность
Секреты и runtime-данные намеренно исключены из git через `.gitignore`.
