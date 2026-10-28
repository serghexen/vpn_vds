# Резервный профиль WS+TLS на реплике

Схема предназначена для сетей, в которых прямой `VLESS TCP REALITY` не подключается:

```text
клиент -> домен:2053 (настоящий TLS) -> nginx -> 127.0.0.1:10086 -> Xray VLESS WS
```

Рабочий TR:

- узел: `193.46.56.199`;
- домен: `tr.serghexen.ru`;
- TLS-порт: `2053`;
- внутренний порт Xray: `10086`;
- WebSocket path: `/api/v1/stream`;
- Compose: `/opt/hexenvpn-node/docker-compose.yml`;
- nginx: `/etc/nginx/conf.d/hexenvpn-tr-ws.conf`.

## Подготовка

1. Добавить DNS `A`-запись домена на IP реплики.
2. Проверить запись минимум через `1.1.1.1` и `8.8.8.8`.
3. Скопировать конфиги Xray/nginx и `docker inspect` в датированный backup.
4. Установить `certbot` и выпустить сертификат через HTTP-01.

Пример выдачи сертификата:

```bash
certbot certonly --webroot \
  -w /usr/local/mgr5/www/letsencrypt \
  -d tr.serghexen.ru \
  --agree-tos --register-unsafely-without-email --non-interactive
```

## Конфигурация

- Добавить в Xray inbound из `project/xray/replica-ws-inbound.template.json`.
- Клиенты должны иметь те же UUID/email, что и REALITY-inbound, но без `flow`.
- Добавить mapping `127.0.0.1:10086:10086` из `project/docker-compose.replica-xray.yml`.
- Создать nginx-конфиг из `project/nginx/replica-ws.conf.template`.
- Проверить `xray run -test` и `nginx -t` до переключения.

## Мастер и подписки

В `nodes.env` включить:

```dotenv
TR_WS_ENABLED=1
TR_WS_HOST=tr.serghexen.ru
TR_WS_PORT=2053
TR_WS_SNI=tr.serghexen.ru
TR_WS_PATH=/api/v1/stream
TR_WS_FP=chrome
```

Скрипты `vless-add-user` и `vless-del-user` синхронизируют все VLESS-inbound реплики. Для уже существующих пользователей применяется `refresh_tr_ws_alt.py`.

## Проверка

```bash
docker exec hexenvpn-bot /usr/local/sbin/healthcheck-replica --node tr
docker exec hexenvpn-bot /usr/local/sbin/healthcheck-master-replicas
```

Дополнительно проверить реальный выход через локальный SOCKS-клиент Xray: ожидаемый внешний IP должен совпасть с IP TR.

## Откат

1. Остановить новый Compose-контейнер.
2. Вернуть `config.json` из backup.
3. Вернуть прежний контейнер или запустить его с исходными port/volume параметрами.
4. Удалить WS server block nginx и выполнить `nginx -t && systemctl reload nginx`.
5. Проверить `443` и `healthcheck-replica`.

WebSocket оставлен ради совместимости с Happ/v2RayTun. Переход на XHTTP хранится отдельным пунктом в TODO.

## Инцидент REALITY 09.09.2026

Проверка обычной Турции из США завершалась таймаутом, тогда как WS работал.
UUID, public key, shortId и flow в подписке совпадали с сервером.
Выяснилось, что TR не мог установить TCP/TLS-соединение с адресами
`www.yahoo.com:443`, указанного как цель REALITY.

При этом `yahoo.com:443` отвечал по TLS 1.3 и предъявлял сертификат,
валидный для прежнего клиентского SNI `www.yahoo.com` (`*.yahoo.com`).
Изолированный тест REALITY с новой целью и прежними клиентскими параметрами
прошёл успешно. После этого в рабочем конфиге изменено только:

```json
"dest": "yahoo.com:443"
```

`serverNames = ["www.yahoo.com"]`, UUID всех 20 клиентов, private/public key,
shortId, flow и WS-inbound сохранены. Обновление подписки для этой правки
не требуется. Права конфигурации сохранены: `0644`, владелец `root:root`.
Применение потребовало одного короткого перезапуска Xray на TR.

После перезапуска обе Турции проверены из США реальным HTTPS-трафиком;
обе вернули выходной IP `193.46.56.199`. Подписка через резервный адрес TR
также проверена внутри WS-туннеля: HTTP 200, TLS-проверка успешна.
Пользователь подтвердил результат на телефоне: REALITY показал 866 мс,
WS — 723 мс. Оба профиля США на том же скриншоте оставались с `n/a`;
это отдельная продолжающаяся диагностика.

Бэкап на TR: `/root/backup-tr-reality-target-20260909T052132Z/config.json`.
Возврат старой цели вернёт и её недоступность, если соединение с
`www.yahoo.com` с TR всё ещё не восстановлено. При откате после новых
админ-операций не перезаписывать весь конфиг старым бэкапом: в нём могут
отсутствовать добавленные позже пользователи.

Контроль цели (одна проверка, без нагрузочного тестирования):

```bash
timeout 10 openssl s_client -connect yahoo.com:443 \
  -servername www.yahoo.com -verify_hostname www.yahoo.com \
  -verify_return_error -tls1_3 -brief </dev/null
```
