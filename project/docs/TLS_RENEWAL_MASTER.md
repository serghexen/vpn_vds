# Сертификат мастера: продление и инцидент 09.09.2026

## Причина и результат

Сертификат `serghexen.ru` истёк 08.09.2026 в 09:43:10 МСК.
Он обслуживал страницу/подписки на `8443` и профиль США ALT WS+TLS на `2053`.
Certbot запускался по таймеру, но использовал `authenticator = manual` с DNS-01
без `manual-auth-hook`. Автоматические попытки продления завершались ошибкой.

На мастере `82.38.60.90` выполнено:

- Резервное копирование `/etc/letsencrypt` и `/etc/nginx` в
  `/root/backup-tls-repair-20260909T033836Z` (каталог доступен только root).
- Добавление `/etc/nginx/conf.d/acme-http.conf` с HTTP-01 на порту `80`.
- Продление существующего сертификата через webroot; срок до 08.12.2026.
- Сохранение hook `nginx -t && systemctl reload nginx` для последующих продлений.
- Успешный `certbot renew --dry-run --run-deploy-hooks`.

Xray и бот не перезапускались. Пользователи, UUID и VPN-конфиги не менялись.
С TR проверены оба профиля США реальной передачей HTTPS-трафика:
выходной IP `82.38.60.90`. Страница и подписка пользователя вернули HTTP 200,
подписка содержала четыре VLESS-профиля.

Истечение этого сертификата не объясняет само по себе отказ REALITY на `443`:
у него отдельный механизм проверки. Успешная проверка с TR также не исключает
ограничения в сети конкретного пользователя.

## Действующая конфигурация

`/etc/nginx/conf.d/acme-http.conf`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name serghexen.ru;
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
        default_type text/plain;
        try_files $uri =404;
    }
    location / { return 404; }
}
```

Порт `80/tcp` должен оставаться доступным извне, включая firewall провайдера.
DNS должен указывать на мастер. Если добавляется AAAA, HTTP-проверка должна
работать и по указанному IPv6.

Существующие ссылки nginx сохранены:

- `/etc/ssl/public.crt` -> `/etc/letsencrypt/live/serghexen.ru/fullchain.pem`
- `/etc/ssl/private.key` -> `/etc/letsencrypt/live/serghexen.ru/privkey.pem`

В `/etc/letsencrypt/renewal/serghexen.ru.conf` Certbot сохранил `webroot`,
`http-01`, `/var/www/letsencrypt` и `renew_hook` для reload nginx.
Не редактировать renewal-файл вручную; использовать команды Certbot.

## Проверки

Команды выполняются на мастере:

```bash
sudo certbot certificates
sudo systemctl is-enabled certbot.timer
sudo systemctl is-active certbot.timer
sudo journalctl -u certbot.service --since '7 days ago' --no-pager
sudo openssl x509 -in /etc/ssl/public.crt -noout -dates
```

После изменения настроек продления:

```bash
sudo certbot renew --cert-name serghexen.ru --dry-run --run-deploy-hooks --no-random-sleep-on-renew
```

Проверка HTTPS с внешней машины без отключения проверки сертификата:

```bash
curl --connect-timeout 5 --max-time 15 -sS -o /dev/null \
  -w 'HTTP=%{http_code} TLS_VERIFY=%{ssl_verify_result}\n' \
  https://serghexen.ru:8443/support
```

Корень `/` на `8443` и `2053` штатно возвращает 404; это не признак отказа TLS.
Проверка порта или `docker ps` не проверяет срок сертификата и передачу VPN-трафика.

Документация: https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates
