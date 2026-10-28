# Профили реплик

Актуальный обезличенный профиль TR хранится в:
- `project/replicas/193.46.56.199/xray.config.template.json`

Каталоги `91.228.10.169` и `194.116.191.181` относятся к прежним VM и оставлены только как исторические шаблоны.

`xray.config.template.json` обезличен и безопасен для git.

Для развертывания создайте реальный конфиг в каждом профиле:
- `project/replicas/<ip>/usr/local/etc/xray/config.json`

Для текущего TR реальный конфиг создаётся по шаблону:
- `project/replicas/193.46.56.199/xray.config.template.json`

WS+TLS на TR разворачивается по инструкции:
- `project/docs/REPLICA_WS_TLS.md`
