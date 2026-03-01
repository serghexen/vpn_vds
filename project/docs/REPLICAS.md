# Профили реплик

Профили реплик хранятся в:
- `project/replicas/91.228.10.169`
- `project/replicas/194.116.191.181`

`xray.config.template.json` обезличен и безопасен для git.

Для развертывания создайте реальный конфиг в каждом профиле:
- `project/replicas/<ip>/usr/local/etc/xray/config.json`

После этого выполните деплой:
- `project/scripts/deploy_replica.sh 91.228.10.169 project/replicas/91.228.10.169`
- `project/scripts/deploy_replica.sh 194.116.191.181 project/replicas/194.116.191.181`
