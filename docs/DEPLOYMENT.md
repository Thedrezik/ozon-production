# Production deployment — task 034

Статус на 2026-10-02: конфигурация и команды подготовлены; production **не развёрнут**.
Task 034 остаётся `pending`: нет доступа к целевому Linux VPS, публичному домену,
и рабочему Docker daemon. Windows предоставляет только служебный WSL
`docker-desktop`; его CLI отказывает в использовании. Никакого успешного Linux
restore, PostgreSQL/Caddy запуска или публичного HTTPS здесь не заявлено.

## 1. Отдельный VPS: минимум 1 CPU / 1 GB RAM

Рекомендованная минимальная production-конфигурация: **1 CPU / 1 GB RAM**,
отдельный Linux VPS с Caddy, одним backend worker и PostgreSQL. Все существующие
функции сохраняются; review тяжёлой функциональности/lightweight mode выполняется
позднее отдельным этапом. Redis/Celery и дополнительные сервисы не добавляются.

Рабочая схема: публичный HTTPS с auth/RBAC, один backend worker, PostgreSQL,
Caddy со статической PWA. UI и `/api/*` имеют один origin. Внешний CDN/proxy в
этой схеме не предусмотрен: Ozon source IP проверяется на Caddy и backend.

Нужны Linux, Docker Engine + Compose v2 с `--wait`, Bash, Python 3,
curl, tar, util-linux/flock, Git. Docker устанавливать по официальной инструкции
для дистрибутива. Рекомендуемая ОС для приведённых host-команд — Ubuntu 24.04 LTS;
для другого дистрибутива использовать соответствующие package/firewall команды.
Docker Engine + Compose plugin устанавливать из
[официального apt repository](https://docs.docker.com/engine/install/ubuntu/).
Первый шаг — SSH и read-only inventory **до** изменения firewall/сервисов:

```sh
cat /etc/os-release
uname -m
nproc
free -m
df -h /
ss -lnt
ip -4 route
ip -6 route
swapon --show
# После переноса checkout можно вместо inventory запустить:
bash scripts/vps-preflight.sh
```

До установки Docker команды `docker network ...` не требуются. После установки
проверить сети/маршруты и выбрать две непересекающиеся private Docker-подсети.
Образы собирать на другой машине и загружать на VPS; Playwright/browser/build
не включаются в runtime и не запускаются одновременно с production на 1 GB.

### Лимиты и бюджет памяти

| Сервис | RAM cap | RAM + swap cap | Максимальный swap | CPU ceiling |
| --- | --- | --- | --- | --- |
| PostgreSQL | 256 MiB | 320 MiB | 64 MiB | 0.75 |
| Backend, 1 worker | 384 MiB | 512 MiB | 128 MiB | 0.75 |
| Caddy | 96 MiB | 128 MiB | 32 MiB | 0.25 |

RAM caps вместе — **736 MiB**. Для ОС/Docker остаётся приблизительно **218 MiB**
при десятичном 1 GB либо **288 MiB** при 1 GiB; фактический usable MemTotal ниже
паспортной памяти — проверить `/proc/meminfo`, MemAvailable и отсутствие OOM.
CPU ceilings — верхние границы, не резервирование дополнительных CPU; на одном
CPU процессы делят физический процессор. PIDs cap каждого сервиса — 100.
PostgreSQL: max_connections=20, shared_buffers=64MB, work_mem=2MB,
maintenance_work_mem=32MB; pool backend **2 + 1**, connect/pool timeout 3 s,
один Uvicorn worker. Caddy GOMEMLIMIT=64MiB — мягкая цель Go heap, не отдельный cap.

`memswap_limit` задаёт суммарные RAM+swap; явные caps не позволяют контейнерам
потреблять весь host swap. Без host swap дополнительные страницы недоступны.
OOM killer не отключается. Проверить kernel/cgroup swap-limit support через
`docker info`, фактические limits через inspect и memory/swap peak на VPS.
См. [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/).
Лимиты — выбранная стартовая конфигурация для 1 GB, её работоспособность ещё
нужно подтвердить реальной нагрузкой; swap не увеличивает допустимый рабочий RAM.

### Firewall

Входящие порты приложения: **TCP 80** (redirect/ACME) и **TCP 443** (HTTPS,
Ozon/Telegram callbacks, PWA, SSE). UDP 443 не опубликован; HTTP/3 не требуется.
SSH разрешить на **фактическом** SSH-порту; при стабильном admin IP ограничить
его источником также в provider firewall. **8000, 5432, 2019 не открывать**.
Только Caddy публикует порты.
Исходящие DNS и HTTPS нужны для ACME, Seller API и включённых провайдеров доставки;
для загрузки образов нужен доступ к выбранному registry.

Для свежего Ubuntu VPS с одним SSH listener, сохранить текущую SSH-сессию и
проверить новую сессию после включения UFW. Сначала разрешить SSH, затем включать
firewall; не выполнять `ufw reset` и не угадывать SSH-порт:

```sh
sudo apt-get update
sudo apt-get install -y ufw ca-certificates curl git python3 util-linux
ssh_port=$(sudo sshd -T | awk '$1 == "port" {print $2; exit}')
test -n "$ssh_port"
sudo ufw limit "$ssh_port/tcp"
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw enable
sudo ufw status verbose
```

При нескольких SSH listener сначала разрешить каждый используемый SSH-порт.
Provider firewall должен разрешать те же inbound TCP порты. Если TCP 80/443
уже заняты другим web-сервисом, разобраться до deploy; wrapper не освобождает
порты и не меняет firewall автоматически. `PROXY_SUBNET` и `DATABASE_SUBNET`
выбирать после проверки существующих routes/Docker networks.

Docker может менять forwarding/firewall и обходить обычные UFW INPUT-правила.
Не отключать Docker iptables; оставить backend/PostgreSQL без published ports.
См. [официальную документацию Docker](https://docs.docker.com/engine/network/packet-filtering-firewalls/).
Не считать `ufw status` доказательством внешней недоступности опубликованных портов.
Проверить с внешней машины SSH и 80/443, отсутствие 8000/5432/2019 и прочих
непредусмотренных listener; например, `nmap -Pn -sT --open -p- VPS_IP`.

### Swap: рекомендованный аварийный буфер 1 GiB

Для 1 GB RAM рекомендован **1 GiB swap**, если у провайдера он ещё не настроен.
Он смягчает краткие пики host/maintenance, но не заменяет RAM и не оправдывает
постоянный paging или build на рабочем VPS. Если swap уже есть, проверить его
размер и использование, не добавлять второй файл автоматически. Постоянные
si/so в `vmstat 1`, растущая latency или OOM означают, что capacity gate не пройден.

Ниже команды только для свежего сервера с ext4/XFS, без существующего swap.
Файл создаётся без перезаписи существующего пути; используется dd, не fallocate
со sparse/CoW страницами. Для Btrfs/сетевой FS нужен отдельный filesystem-specific
порядок, этот блок останавливается. Предварительно проверить свободный диск:

```sh
sudo bash <<'SH'
set -Eeuo pipefail
test -z "$(swapon --show --noheadings)" || { echo 'Swap exists; review it instead of adding another file.' >&2; exit 1; }
if [[ -e /swapfile || -L /swapfile ]]; then echo 'Existing /swapfile will not be overwritten.' >&2; exit 1; fi
case "$(findmnt -no FSTYPE -T /)" in ext4|xfs) ;; *) echo 'Review filesystem-specific swap setup.' >&2; exit 1 ;; esac
available=$(df -B1 --output=avail / | tail -n 1)
test "$available" -ge 2147483648
(umask 077; set -o noclobber; : > /swapfile)
dd if=/dev/zero of=/swapfile bs=1M count=1024 status=progress conv=notrunc
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
backup=$(mktemp /etc/fstab.ozon-backup.XXXXXX)
cp /etc/fstab "$backup"
if ! awk '$1 == "/swapfile" {found=1} END {exit !found}' /etc/fstab; then
  printf '/swapfile none swap sw 0 0\n' >> /etc/fstab
fi
if ! findmnt --verify --tab-file /etc/fstab; then
  cp "$backup" /etc/fstab
  echo 'fstab reverted; swap is active only until reboot. Inspect before proceeding.' >&2
  exit 1
fi
swapon --show
free -m
SH
sudo sysctl -w vm.swappiness=10
```

Для сохранения swappiness создать новый `/etc/sysctl.d/99-ozon-swappiness.conf`
через `sudoedit` со строкой `vm.swappiness=10`, предварительно проверив существующие
sysctl overrides. После `sudo sysctl --system` и планового reboot снова проверить
`sysctl vm.swappiness` и `swapon --show`. Не выполнять `swapoff` под нагрузкой.
Обоснование: [swapon filesystem constraints](https://man7.org/linux/man-pages/man8/swapon.8.html)
и [Linux vm.swappiness](https://docs.kernel.org/admin-guide/sysctl/vm.html).

## 2. Release, env и секреты

Использовать **standalone** `docker-compose.production.yml`, не overlay поверх
development. Проект всегда `ozon-production`; не менять его имя между обновлениями.
Данные: `ozon-production_postgres_data`, `_uploads`, `_backups`, `_caddy_data`,
`_caddy_config`. Последние два сохраняют TLS-состояние. Никогда не применять
`down -v`, volume prune или удаление этих volumes при update/rollback.

`.env.production.example` — полный список production env; рабочий файл
`.env.production` исключён из Git и build context. Секреты не нужны при build;
Caddy получает только DOMAIN и GOMEMLIMIT. Backend получает private env только
при запуске, PostgreSQL — DB/user/password. Файлы с секретами/backup/master key
доступны только оператору. Пользователь с доступом к Docker фактически имеет
административные права. `docker compose config` и `docker inspect` могут раскрыть
env: использовать `config --quiet`, не публиковать полный вывод.

На VPS в `/opt/ozon-production` после клонирования выбранного release:

```sh
# Подставить домен и две предварительно проверенные свободные подсети.
python3 scripts/init-production-env.py --domain production.company.ru \
  --proxy-subnet 172.29.40.0/28 --database-subnet 172.29.41.0/28 \
  --release "$(git rev-parse HEAD)"
chmod 600 .env.production
docker compose --env-file .env.production -p ozon-production \
  -f docker-compose.production.yml config --quiet
```

Генератор не перезаписывает файл, создаёт независимые APP_SECRET, DB password,
Fernet master key; пароль URL-safe, DATABASE_URL согласован с PostgreSQL.
`POSTGRES_DB/USER` задаются через env, пароль не hardcode. При ручной настройке
URL-encode пароль в DATABASE_URL; POSTGRES_PASSWORD содержит исходный пароль.
Смена DB password в env не меняет пароль существующей PostgreSQL роли: выполнять
управляемую ротацию в DB и env вместе, не удалять volume.

Обязательные env: DOMAIN/APP_PUBLIC_URL, APP_SECRET, POSTGRES_DB/USER/PASSWORD,
DATABASE_URL, OZON_CREDENTIALS_MASTER_KEY, BACKEND_IMAGE/CADDY_IMAGE,
PROXY_SUBNET/DATABASE_SUBNET/CADDY_PROXY_IP. DOMAIN — только DNS hostname;
APP_PUBLIC_URL — `https://DOMAIN`. Production Compose принудительно задаёт
APP_ENV=production, OZON_MOCK_MODE=false, постоянные пути uploads/backups и
точный Caddy `/32`. Uvicorn работает с `--no-proxy-headers`, одним worker,
без access log/server header; FastAPI debug выключен, API docs отключены.
Startup проверяет настройки, HttpOnly/Secure/SameSite=Strict cookies и точный
allowed Host/Origin обеспечиваются существующим backend. CORS credentials
не разрешены: браузер работает с одним origin. Не добавлять `*` origins/proxy CIDR.

Ozon credentials можно задать private env либо сохранить через существующий
административный экран; сохранённые зашифрованные credentials авторитетны.
Master key хранить отдельно от backup; его потеря лишает доступа к сохранённому
Ozon ключу. Не менять master key без re-encryption. Опциональные VAPID и Telegram
группы задавать целиком либо оставлять целиком пустыми. Не передавать secrets
в VITE variables, Docker build args, командную строку curl или business comments.

## 3. Образы и первое развёртывание

Рекомендуется build на отдельной Linux-машине: frontend build ранее достигал
~428 MiB, лимиты контейнеров не ограничивают builder. На VPS с 1 GB RAM
не собирать образы одновременно с рабочим приложением. Из checkout того же SHA:

```sh
release=$(git rev-parse HEAD)
docker build -t "ozon-backend:$release" backend
docker build -f deployment/Caddy.Dockerfile -t "ozon-caddy:$release" .
docker save "ozon-backend:$release" "ozon-caddy:$release" | gzip > release-images.tar.gz
# Передать архив на VPS по защищённому каналу; затем на VPS:
gzip -dc release-images.tar.gz | docker load
release=$(git rev-parse HEAD)
mkdir -p deployment-results
set -o pipefail
DRILL_BACKEND_IMAGE="ozon-backend:$release" bash scripts/backup-restore-drill.sh 2>&1 | tee deployment-results/linux-restore-drill.txt
# Следующая команда только после exit 0/PASS полного target Linux drill:
IMAGE_MODE=existing bash scripts/production.sh deploy
```

Альтернатива: private registry, BACKEND_IMAGE/CADDY_IMAGE с immutable tags/digests,
`IMAGE_MODE=pull` (default). `IMAGE_MODE=build` допустим только при проверенном
запасе памяти/окне обслуживания. PostgreSQL берётся из postgres:17-alpine;
проверять обновления minor/security и отдельно тестировать их на isolated DB.
Перед production acceptance записать фактические image digests и Git SHA.

`deploy` предназначен для первого запуска и отказывает при существующем DB volume.
Он проверяет Compose, получает образы, ждёт PostgreSQL, валидирует production
Settings, выполняет Alembic, валидирует Caddy, запускает backend/Caddy, проверяет
readiness и запускает public smoke. Первый запуск не имеет application backup:
existing deployment обязан использовать update. До него проверить настройки VPS/firewall.

DNS A/AAAA должны указывать на сервер, включая реально работоспособный IPv6;
не оставлять неправильную AAAA. Caddy получает/обновляет публичный сертификат и
перенаправляет HTTP на HTTPS; persistent `/data` обязателен.
См. [Caddy Automatic HTTPS](https://caddyserver.com/docs/automatic-https).
Public smoke использует обычную TLS verification, без `curl -k`.

Создать первого администратора интерактивно после миграций:

```sh
docker compose --env-file .env.production -p ozon-production \
  -f docker-compose.production.yml exec backend \
  python -m app.cli create-admin --username admin --display-name 'Руководитель'
bash scripts/production-smoke.sh
```

## 4. Update, rollback и повседневные команды

Все команды запускать из checkout на VPS; wrapper фиксирует env/project/Compose,
использует flock, private state в ignored `deployment-results/private`, не удаляет
production volumes. Примеры:

| Действие | Команда |
| --- | --- |
| Статус | `bash scripts/production.sh status` |
| Backend / proxy / DB logs | `bash scripts/production.sh logs backend` (либо caddy/postgres) |
| Liveness | `bash scripts/production.sh health` |
| Database readiness | `bash scripts/production.sh readiness` |
| Public HTTPS/headers/routes | `bash scripts/production-smoke.sh` |
| Согласованный backup | `bash scripts/production.sh backup` |
| Restore | `bash scripts/production.sh restore backup-YYYYMMDDTHHMMSSZ.tar.gz` |
| Update | `IMAGE_MODE=existing bash scripts/production.sh update RELEASE_REF` |
| Rollback последнего update | `bash scripts/production.sh rollback` |
| Restart API/proxy | `bash scripts/production.sh restart` |
| Stop / start | `bash scripts/production.sh stop` / `bash scripts/production.sh start` |

До update получить новый ref (`git fetch origin` без изменения работающего
checkout) и загрузить образы, именованные **полным SHA**, выбранным update.
Рабочее дерево должно быть чистым. Wrapper сохраняет старый ref/env, останавливает
Caddy/API/фоновые writers, создаёт backup реальными scripts, записывает имя архива,
переключает checkout, задаёт новые SHA image tags, получает/build образы, выполняет
миграции и только после успеха запускает API/proxy, readiness и smoke. С custom
registry edit/prepare release tags отдельно: автоматический update рассчитан на
локальные `ozon-backend:SHA` / `ozon-caddy:SHA` tags из приведённого build/save flow.
Если нужен pull/build **после** backup, выбрать соответствующий IMAGE_MODE.

Migration failure оставляет API/proxy остановленными и ненулевой exit code.
Не запускать старую версию против частично изменённой схемы и не делать слепой
`alembic downgrade`. Проверить logs и Alembic current, затем устранить причину
или выполнить rollback. Не удалять snapshot `deployment-results/private` до
проверенного успешного release; следующая update заменяет snapshot предыдущей.

Rollback останавливает writers, выбирает сохранённый ref/env и спрашивает
`RESTORE` перед настоящим DB/uploads restore; затем проверяет миграции matching
release и запускает сервисы. Старые image tags должны оставаться локально доступны.
`pg_restore --clean` удаляет только объекты из dump; новые таблицы/зависимости,
созданные неудачной миграцией, могут остаться или блокировать restore. При такой
ошибке **держать API остановленным**, оценить схему и восстановить snapshot в
отдельную новую DB согласованной старой версии с контролируемым переключением
DATABASE_URL. Не удалять исходную DB/volume и не заявлять универсальный rollback
всех будущих миграций. DB и uploads не имеют общей атомарной транзакции.

`backup` и `restore` оставляют API остановленным: после проверки запустить `start`.
Backup использует one-off helpers со старым backend image и теми же volumes;
они не запускают API/scheduler. Retention по умолчанию 14, override RETENTION_COUNT.
Для ежедневного backup использовать эту consistent команду в maintenance window
и явный `start` **только после успеха backup**; мониторить ненулевой exit code.
Copy backup off-VPS, ключи хранить отдельно. См. [BACKUP_RESTORE.md](../BACKUP_RESTORE.md).

## 5. Обязательный реальный Linux restore drill

**До production launch, именно на целевом Linux VPS**:

На 1 GB VPS использовать уже загруженный release image, чтобы drill не запускал
build. Выполнить до первого production startup; при повторном acceptance в
maintenance window остановить production через `production.sh stop` (volumes
сохраняются). Не запускать два полных стека одновременно под host memory budget.

```sh
release=$(git rev-parse HEAD)
mkdir -p deployment-results
set -o pipefail
DRILL_BACKEND_IMAGE="ozon-backend:$release" bash scripts/backup-restore-drill.sh 2>&1 | tee deployment-results/linux-restore-drill.txt
```

Команда сама генерирует synthetic env без Ozon/Telegram/VAPID credentials,
отдельный Compose project и уникальные names для всех пяти volumes. Caddy не
запускается, порты не публикуются. `check-drill-config.py` проверяет resolved
volumes, project, mounts, test mode и выключенные providers перед startup,
destructive restore и cleanup. Снимок **всех** существовавших volumes сравнивается
после cleanup, новые drill volumes обязаны исчезнуть. Operational volumes ни в
одном drill-контейнере не монтируются; metadata snapshot сам по себе не является
сравнением содержимого работающей production DB.

Проверки: migrations; реальный pg_dump; database.dump/uploads.tar.gz/README.txt;
публикация archive; DB marker `before-backup` → `after-backup` плюс новая строка;
изменённый original upload плюс новый upload; реальный pg_restore; исходные marker
и upload восстановлены; post-backup row/upload отсутствуют; ровно два последних
архива после retention; cleanup только guarded project; прежние volumes сохранены.
Любой failure блокирует launch, даже если cleanup прошёл. Windows shell regression
и Windows Docker Desktop drill не заменяют эту проверку.

**Результат: NOT RUN.** Внести сюда и в STATE.md UTC дату, VPS/OS, SHA/digests,
имя generated project, полный exit code и PASS/FAIL всех пунктов после реального
запуска. Не отмечать acceptance criterion/task completed до этого.

## 6. Linux containers, PostgreSQL, E2E и ресурсные измерения

На отдельной Linux test-машине с Docker, Node/npm и установленным Chromium:

```sh
cd frontend
npm ci
npx playwright install --with-deps chromium
cd ..
bash scripts/container-acceptance.sh
# Либо только existing E2E runner:
cd frontend
E2E_CONTAINER=true E2E_PROBE=true npm run test:e2e
```

Runner переиспользует все 12 сценариев task 033, создаёт **свежие** PostgreSQL,
uploads/backups и Caddy volumes для каждого сценария, выполняет миграции и
отказывает, если DB не пуста. Реальные backend/React PWA/PostgreSQL/Caddy;
только external Ozon adapter — synthetic. Test-only fault proxy воспроизводит
503, lost SSE и competing-write barrier, остальные API исполняются приложением.
Fixtures/tests/fault proxy монтируются только в isolated окружении и не входят
в production image. Cleanup повторно проверяет resolved mounts/volumes.

HTTPS здесь использует **local internal CA** и явное отключение certificate
verification только для generated localhost fixture. Это не подтверждение
публичного ACME. Test-mode webhook source filter ослаблен только в fixture, а
APP_ENV=test не проверяет Secure cookie behavior. Production cookie/origin/proxy
контроль выполняется отдельным checklist ниже с unmodified production ingress.
Не направлять runner на production URL, не подключать real provider credentials.

E2E_PROBE добавляет PostgreSQL migration/index inventory, EXPLAIN (ANALYZE, BUFFERS)
фактически исполненных queue/dashboard/risk/analytics/audit запросов, 4 параллельных
клиента/20 reads, DB connection/idle transaction counts. В `deployment-results`
сохраняются synthetic plans, Docker CPU/cgroup memory и process VmRSS по сервисам.
Process RSS разделяемой PostgreSQL памяти нельзя просто складывать. Эти замеры
используют небольшие fixtures; это **не** p95/нагрузочная гарантия для VPS.
SSE/reconnect проходят browser workflow. Reconciliation вызывается через existing
service; real background/provider loops проверять отдельно при запуске.

На целевом VPS снять `docker stats --no-stream`, `free -m`, OOM/restart counts,
connections и responsiveness при реальной рабочей нагрузке и нескольких SSE.
Сервисные caps PostgreSQL/backend/Caddy: 256/384/96 MiB, один worker, pool 2+1,
max_connections=20. Учитывать дополнительно Linux/Docker: 736 MiB caps не
доказывают, что хост с 1 GiB достаточен. EXPLAIN ANALYZE/read benchmarks делать на
synthetic DB, включая реалистичное количество **активных** заказов; проверить
sort spill, scan selectivity, audit trigger/row locks, stale transactions и DB
recovery после restart. Согласовать latency/RSS с [PERFORMANCE.md](PERFORMANCE.md).
Не добавлять Redis/Celery до измеренного подтверждения необходимости.

После startup на целевом 1 GB VPS записать реальные caps и host pressure, не
публикуя полный inspect с env:

```sh
ids=$(docker compose --env-file .env.production -p ozon-production -f docker-compose.production.yml ps -q)
test -n "$ids"
docker inspect --format '{{.Name}} RAM={{.HostConfig.Memory}} RAM+swap={{.HostConfig.MemorySwap}} CPU={{.HostConfig.NanoCpus}} OOM={{.State.OOMKilled}} Restarts={{.RestartCount}}' $ids
docker stats --no-stream $ids
free -m
vmstat 1 10
bash scripts/production.sh readiness
```

Повторить при нескольких пользователях/SSE, reconciliation/delivery и реальных
phone uploads. Gate: no OOM/restart, no sustained swap thrashing, healthy readiness
и приемлемые измеренные latency при заявленном числе активных заказов. Пока этот
прогон отсутствует, поддержка 1 GB — целевая конфигурация, не успешный acceptance.

## 7. Production security / persistence acceptance

Public smoke автоматически проверяет публичный TLS/redirect, static SPA/PWA,
health/readiness и mock=false, CSP/nosniff/DENY/no-referrer/HSTS, third-party Origin
denial и Ozon route 403 с поддельными XFF/source-IP headers. Дополнительно на HTTPS
в браузере с synthetic/operator test user (credentials не сохранять в отчёт):

- Login/logout Set-Cookie: Secure, HttpOnly, SameSite=Strict, host-only, Path=/api;
  cookie отсутствует в JS/localStorage. Logout/session revocation действительно
  запрещают reads, worker не имеет manager/admin permissions.
- Authenticated POST с отсутствующим/неверным CSRF → 403; корректный CSRF и
  чужой Origin → 403; cross-origin preflight не содержит allow-origin/credentials.
  Same-origin production action проходит. Неверный Host при прямом private
  backend запросе → 400. Поддельный XFF не меняет auth/audit IP.
- CSP запрещает inline script/frame; `/docs`/`openapi.json` **на private backend**
  отключены. Public SPA может вернуть shell на произвольный non-API путь, это не
  API docs. Invalid JSON/422/404/503 не содержат traceback/DB URL/секретов.
  Проверить API/static error headers и фактическое отсутствие secrets в logs.
- Header `X-Ozon-Source-IP` перезаписывается Caddy; private backend peer совпадает
  с CADDY_PROXY_IP, trust только `/32`. Login/audit сознательно используют socket
  peer Caddy, aggregate rate limit shared; forwarded headers не используются как
  произвольная идентичность клиента. CDN заголовкам доверие не добавлять.
- Валидное небольшое JPEG upload/read проходит с RBAC; >UPLOAD_MAX_BYTES
  отклоняется backend, >21 MB body отклоняется edge; SVG/forged MIME запрещены.
  Новый comment/order/photo переживают backend/PostgreSQL/Caddy restart; backups
  остаются в volume. После restart проверить readiness и доступность фото.
- Два браузера: действие работника обновляет manager через SSE; reconnect,
  logout/deactivation во время stream, offline→online refresh, no duplicate task.
- В isolated production-config container проверить startup rejection при
  placeholder APP_SECRET, неправильном master key/DB password, неверном DOMAIN,
  broad trusted proxy, неполной Telegram/VAPID группе. Не менять рабочие secrets
  production ради negative tests; Settings regression tests покрывают это локально.

Проверить внешнюю доступность только предусмотренных портов и новую SSH-сессию.
Записать результаты firewall проверки с внешней машины.

## 8. Реальный Ozon и внешние уведомления

Публичный URL receiver: `https://DOMAIN/api/ozon/webhook`.
В admin Ozon Integration задать Client ID/key и expiration, выполнить existing
connection check (backend `/v1/roles`), затем ограниченный FBS import через
existing v4 importer. Не использовать account credentials в automated fixtures.
Проверить отдельные Ozon/Internal Production Status и сохранность истории.

После import включить OZON_RECONCILIATION_ENABLED=true и OZON_WEBHOOK_ENABLED=true,
перезапустить один backend, проверить sync status/last_success/freshness. В Seller
Settings → Push notifications настроить URL, выполнить Ozon connection/TYPE_PING
check и подписаться на поддерживаемые posting new/state/cancelled/cutoff/delivery
events. Проверить event inbox и обработку, replay без дубликатов, cancellation
после производства создаёт одну Manager Task, reconciliation восстанавливает
пропущенные изменения, sync error создаёт/закрывает source-keyed task.

Официальный контракт/source networks были проверены проектом 2026-10-01 и описаны
в [OZON_API.md](OZON_API.md); web reader 2026-10-02 не смог загрузить официальную
страницу. Перед включением реального ingress оператор обязан сверить текущий
[Ozon Seller API push contract](https://docs.ozon.ru/api/seller/#tag/push_start)
и source networks с обоими allowlists. Не расширять IP filter для ручного curl.
Обычный внешний curl должен получить 403, Ozon connection check — TYPE_PING 200.

Sync диагностика: admin integration status, last safe error code, Manager Tasks,
webhook inbox status/attempts/next_retry, `production.sh logs backend`, readiness,
DNS/time/outbound HTTPS. Секреты/сырые provider exceptions не выводить; после
устранения причины использовать existing admin event retry и проверить recovery.
Денежный риск неизвестных Ozon тарифов остаётся unknown; не вычислять его из цены.

Web Push: сгенерировать пару через `python -m app.push_keys` в приватном окружении,
перенести VAPID_PRIVATE_KEY/PUBLIC_KEY/SUBJECT в backend env, restart; проверить
public-key config (private key отсутствует), subscribe конкретного HTTPS устройства,
permission, opt-in, production blocker/deadline notice, delivery row→SENT и OS
reception/deep link. Проверить expired subscription cleanup/retry; не логировать
push endpoint. Without device/keys: **manual acceptance pending**.

Telegram: задать полную группу env; в приватном operator script/API client вызвать
Telegram `setWebhook` с `url=https://DOMAIN/api/telegram/webhook` и secret_token;
token не помещать в history/логи/командные аргументы. Сверить webhook status через
`getWebhookInfo`, bind через существующий one-time deep link, wrong secret → 403,
correct callback→binding, opted-in delivery→SENT и сообщение/deep link, unlink.
Engine использует существующие notification_deliveries, bounded retries; проверить
FAILED/next_attempt_at и in-app notice независимо от внешней доставки. Without
bot/private chat: **manual acceptance pending**.
Контракт настройки: [Telegram setWebhook](https://core.telegram.org/bots/api#setwebhook)
и [getWebhookInfo](https://core.telegram.org/bots/api#getwebhookinfo).

## 9. Физический телефон и запись acceptance

Для фактического развёртывания подготовить: VPS IPv4 (IPv6 только если настроен),
ОС/версию/архитектуру, фактические RAM/CPU/disk, SSH user/port и способ доступа
по ключу, домен и возможность изменения DNS A/AAAA, доступ к provider firewall,
выбранный tested checkout/SHA и способ передачи образов соответствующей архитектуры.
Дополнительно: Ozon Client ID/API key/expiration с нужными permissions, при
включении доставки — Telegram bot/username/secret и VAPID pair/subject, место
off-server backup и устройство для push/PWA/camera acceptance. Secrets вводить
непосредственно в private env/admin screen, не хранить в deployment evidence.
Для capacity проверки указать ожидаемое число активных заказов, одновременных
пользователей/SSE и типичный размер фотографий; функции приложения не удаляются.

На Android/iOS: публичный сертификат без предупреждений, manifest/icons/install,
service worker active, touch/mobile viewport, отсутствие горизонтального скролла;
камера/QR с реальной наклейкой, разрешение/отказ камеры, JPEG upload, Web Push
permission и OS reception (учесть требования платформы/установленной PWA).
Camera/Web Push требуют secure context. Отключить сеть после queue load, проверить
read-only OFFLINE/stale/time, reload той же вкладки, запрет mutations, reconnect
и свежие данные, no replay, logout cache clearing. Physical device здесь недоступен.

Acceptance журнал:

| Gate | Результат здесь | Требуемое доказательство на VPS |
| --- | --- | --- |
| Production Compose/build/migrations/start | NOT RUN | Exit 0, SHA/digests, ps/readiness |
| HTTPS/redirect/public routes/headers | NOT RUN | Public smoke PASS с verified cert |
| Только нужные порты и 1 GB capacity | NOT RUN | Внешний port scan, host/container peaks, no OOM |
| Persistent restart | NOT RUN | DB row/photo/backup после restart |
| Target Linux isolated restore | NOT RUN — launch blocker | Полный PASS + cleanup/volume guards |
| PostgreSQL plans/CPU/RSS/concurrency | NOT RUN | Synthetic reports + target capacity measurement |
| Container HTTPS desktop/mobile E2E | NOT RUN | 12/12, без retries |
| Production auth/proxy security | NOT RUN | Checklist раздела 7 |
| Real Ozon/Web Push/Telegram | NOT RUN | Provider/device smoke, без secrets в отчёте |
| Physical phone/PWA/camera | NOT RUN | Device/OS и результаты раздела 9 |

Локально: backend suite 273 passed + новые safety tests, Ruff, frontend
lint/typecheck/build и E2E 12/12; Bash synthetic backup/retention/restore rollback
checks прошли в Git Bash. YAML parsed, **это не Docker Compose validation**.
Synthetic production-flow check дополнительно подтверждает блокировку startup
после migration failure и сохранность прежнего атомарного rollback snapshot при
backup failure (`bash scripts/test-production-flow.sh`).
Полные актуальные результаты записаны в STATE.md. Ни commit, ни push не выполнялись;
task 035 не начата. После прохождения реальных gates обновить этот журнал,
STATE.md и только тогда acceptance checkboxes/status task 034.
