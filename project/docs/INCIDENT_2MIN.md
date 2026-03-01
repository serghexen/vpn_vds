# Инцидент за 2 минуты (master + replicas)

Короткий регламент, если «всё упало» или `xray` ушёл в restart loop.

## 0) Быстрый диагноз (мастер)
```bash
cd /opt/vpn_vds
docker compose -f project/docker-compose.master-full.yml ps
docker logs --tail 80 hexenvpn-xray
```

## 1) Быстрый healthcheck всего контура
```bash
cd /opt/vpn_vds
project/scripts/healthcheck_master_replicas.sh
```

Проверка конкретного пользователя:
```bash
project/scripts/healthcheck_master_replicas.sh --user test1
```

## 2) Если ошибка вида `User <name> already exists`
Причина: дубли в `xray` (часто из-за `name`/`Name`).

Порядок:
1. На мастере удалить/пересоздать пользователя только через `vless-*`:
```bash
docker exec hexenvpn-bot sh -lc "/usr/local/sbin/vless-del-user --name <name>"
docker exec hexenvpn-bot sh -lc "/usr/local/sbin/vless-add-user --name <name> --days 3"
```
2. Если `xray` не поднимается, сначала очистить дубли в `config.json` (case-insensitive), затем `run -test`, потом рестарт.

## 3) Правило для прода
- Не редактировать `/usr/local/etc/xray/config.json` руками для добавления/удаления клиентов.
- Добавление/удаление только через:
  - бот (админка),
  - или `vless-add-user` / `vless-del-user`.

## 4) Логи без раздувания диска
В compose включена ротация:
- `max-size: 10m`
- `max-file: 3`

Проверка:
```bash
docker inspect hexenvpn-bot --format '{{json .HostConfig.LogConfig}}'
docker inspect hexenvpn-xray --format '{{json .HostConfig.LogConfig}}'
```

## 5) Безопасный перезапуск (релиз)
Если нужно применить изменения без ручных шагов:
```bash
cd /opt/vpn_vds
project/scripts/release_master.sh
```

Опционально (тяжелее по ресурсам):
- с обновлением `xray`-образа: `project/scripts/release_master.sh --pull-xray`
- с пересборкой `bot`: `project/scripts/release_master.sh --build-bot`

## 6) После reboot не поднялись контейнеры
Проверки:
```bash
systemctl is-enabled docker
docker inspect -f '{{.Name}} -> {{.HostConfig.RestartPolicy.Name}}' hexenvpn-bot hexenvpn-xray
```

Ожидается:
- Docker: `enabled`
- Политика контейнеров: `unless-stopped`

Быстрое восстановление:
```bash
cd /opt/vpn_vds
docker compose -f project/docker-compose.master-full.yml up -d --force-recreate
```
