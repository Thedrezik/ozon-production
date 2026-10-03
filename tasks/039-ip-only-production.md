Задача 039 — IP-only Production Preparation & Ozon Integration Finalization
Работай с локальным репозиторием:
C:\Users\kdn14\Documents\GitHub\ozon-production
Прочитай:
- AGENTS.md 
- docs/PRODUCT.md 
- docs/STATE.md 
- docs/DECISIONS.md 
- docs/ARCHITECTURE.md 
- docs/DEPLOYMENT.md 
- docs/SECURITY.md 
- docs/PERFORMANCE.md 
- docs/OPTIONAL_FEATURES.md 
- BACKUP_RESTORE.md 
Task 034 остаётся pending.
Цель — окончательно подготовить проект к production deployment на:
-  Debian 12; 
-  x86_64; 
-  1 CPU; 
-  1 GB RAM; 
-  1 GiB swap; 
-  Docker Compose; 
-  PostgreSQL + backend + Caddy; 
-  публичный IPv4; 
- без покупного домена. 
Реальный deployment пока не выполнять.
Проверь актуальную официальную документацию Caddy/Let's Encrypt/ACME.
Нужен production-вариант:
https://PUBLIC_IP
Требования:
-  сертификату доверяют обычные Android/browser клиенты; 
-  автоматическое renewal; 
-  HTTP → HTTPS; 
-  PWA/API/SSE работают; 
-  никаких self-signed CA, которые нужно вручную устанавливать на телефоны. 
Если текущий Caddy не умеет это корректно автоматически — подготовь минимальное надёжное решение, например получение/renew IP certificate отдельным ACME client и использование cert/key в Caddy.
Не требуй покупки домена.
По актуальной официальной Ozon Seller API документации проверь, допускается ли webhook URL вида:
https://PUBLIC_IP/api/ozon/webhook
Проверь требования:
-  URL; 
-  HTTPS/certificate; 
-  push/webhook configuration; 
-  необходимые Seller API permissions. 
Если literal IP Ozon не принимает — не придумывай. Документируй подтверждённый fallback без покупки собственного домена и сохрани reconciliation.
Проверь существующую реализацию.
Admin нашего приложения должен иметь экран Ozon Integration, где вводятся:
-  Client ID; 
-  Api-Key. 
Ключ:
-  после сохранения frontend обратно не получает; 
-  хранится зашифрованным; 
-  перед сохранением проходит connection check; 
-  не попадает в logs/audit. 
По официальной документации определить минимально необходимые Ozon API permissions для текущего продукта:
-  FBS orders; 
-  posting/status; 
-  warehouse; 
-  tariff information; 
-  reconciliation; 
-  push/webhook. 
Наше приложение не должно менять состояние заказа в Ozon, если это не требуется текущей бизнес-логикой.
Не требовать full-write Admin key, если read-only/minimal role достаточна.
Проверь актуальные правила срока жизни API keys.
Если дату expiration можно достоверно получить/определить — сделай лёгкое Admin warning без частого polling.
Если достоверной даты нет — ничего не придумывай.
Подготовь:
scripts/bootstrap-vps.sh
Для чистого Debian 12.
Он должен:
-  проверить OS/architecture; 
-  обновить packages; 
-  установить необходимые утилиты; 
-  установить Docker Engine + Compose plugin официальным способом; 
-  создать 1 GiB swap, если swap отсутствует; 
-  не разрушать существующий swap; 
-  подготовить firewall; 
-  сохранить SSH; 
-  открыть только необходимые HTTP/HTTPS порты; 
-  подготовить каталоги приложения; 
-  быть idempotent насколько разумно; 
-  не содержать secrets. 
Deployment должен использовать:
-  SSH key; 
-  отдельного deploy user с sudo; 
-  никаких root passwords в repo/scripts/prompts. 
Не проси пользователя передавать root password coding-agent.
Подготовь простой production deployment:
предпочтительно private GitHub repo + deploy key.
Допустим документированный scp/rsync fallback.
Не хранить GitHub password/token в repository.
Update flow:
backup → pull → build → migrate → restart → smoke
Подготовь чистый production env template только с реально используемыми настройками.
Secrets вводятся непосредственно на VPS.
Добавь безопасные команды генерации:
-  application secret; 
-  credential encryption/master key; 
-  прочих необходимых secrets. 
Не выводить реальные secrets в logs.
Проверь и упростить существующие scripts.
Нужны понятные команды для:
-  bootstrap; 
-  deploy; 
-  update; 
-  rollback; 
-  backup; 
-  restore; 
-  status; 
-  logs; 
-  smoke. 
Пользователь не должен вручную выполнять 30 команд для обычного deployment.
В DEPLOYMENT.md первым шагом после аренды VPS должны быть:
```
cat /etc/os-release
uname -m
nproc
free -h
df -h /
swapon --show
ss -lntup
ip -br addr
```
На этом этапе ничего destructive.
Цель:
-  1 CPU; 
-  1 GB RAM; 
-  1 GiB swap; 
-  1 backend worker; 
-  маленький PostgreSQL pool. 
Сохрани resource limits, подготовленные task 032/034, если они всё ещё рациональны после task 036.
Optional features task 036 выключены — учитывай это.
Android wrapper будет отдельной задачей после успешного production deployment, когда окончательно известен рабочий HTTPS endpoint.
Запусти доступное:
-  backend tests; 
-  Ruff; 
-  frontend lint/typecheck/build; 
-  E2E; 
-  shell syntax/tests; 
-  Compose config; 
- git diff --check. 
Docker использовать, если доступен.
Не изображать live VPS verification без реального VPS.
Task 034 оставить pending.
Deployment не выполнять.
 Commit/push не делать.
В финале кратко сообщи:
-  как реализован HTTPS без покупного домена; 
-  допускает ли Ozon webhook bare IP; 
-  какие минимальные Ozon API permissions нужны; 
-  где вводятся Client ID/API key; 
-  какие bootstrap/deployment scripts готовы; 
-  что нужно от пользователя после аренды VPS; 
- один первый шаг после SSH login.