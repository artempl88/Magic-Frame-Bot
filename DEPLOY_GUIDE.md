# 🚀 Полная инструкция по развертыванию клиентского бота

**Подробное руководство для новичков** - от создания бота до полного развертывания.

## 📋 Содержание

1. [Подготовка](#1-подготовка)
2. [Создание бота в Telegram](#2-создание-бота-в-telegram)
3. [Установка Docker](#3-установка-docker)
4. [Настройка проекта](#4-настройка-проекта)
5. [Локальное развертывание](#5-локальное-развертывание)
6. [VPS развертывание](#6-vps-развертывание)
7. [Настройка домена и SSL](#7-настройка-домена-и-ssl)
8. [Проверка работоспособности](#8-проверка-работоспособности)
9. [Обслуживание и мониторинг](#9-обслуживание-и-мониторинг)
10. [Решение проблем](#10-решение-проблем)

---

## 1. Подготовка

### Что вам понадобится:

- **Компьютер** с Windows/Linux/macOS
- **VPS сервер** (если планируете развертывание в продакшн)
- **Домен** (для webhook'ов Telegram)
- **Токен Telegram бота**
- **API ключ WaveSpeed** (или другого сервиса)

### Минимальные системные требования:

- **RAM**: 2 GB (рекомендуется 4 GB)
- **Диск**: 10 GB свободного места
- **CPU**: 1 ядро (рекомендуется 2 ядра)

---

## 2. Создание бота в Telegram

### Шаг 2.1: Создание бота

1. Откройте Telegram и найдите бота **@BotFather**
2. Отправьте команду `/newbot`
3. Введите **имя бота** (например: "My Client Bot")
4. Введите **username бота** (например: "myclientbot" - должен заканчиваться на "bot")
5. **Сохраните токен** - он понадобится позже!

```
Пример ответа BotFather:
Done! Congratulations on your new bot. You will find it at t.me/myclientbot. 
You can now add a description, about section and profile picture for your bot.

Use this token to access the HTTP API:
1234567890:AAAA-BBBB_CCCC_DDDD_EEEE_FFFF_GGGG_HHHH

Keep your token secure and store it safely, it can be used by anyone to control your bot.
```

### Шаг 2.2: Настройка бота

1. Отправьте `/setdescription` для описания бота
2. Отправьте `/setabouttext` для краткого описания
3. Отправьте `/setuserpic` для загрузки аватара

### Шаг 2.3: Получение своего Telegram ID

1. Найдите бота **@userinfobot**
2. Отправьте ему `/start`
3. **Сохраните ваш ID** - он понадобится для админских прав

---

## 3. Установка Docker

### На Windows:

1. Скачайте **Docker Desktop** с https://www.docker.com/products/docker-desktop
2. Запустите установщик и следуйте инструкциям
3. Перезагрузите компьютер
4. Запустите Docker Desktop
5. Проверьте установку в PowerShell:
```powershell
docker --version
docker-compose --version
```

### На Ubuntu/Debian:

```bash
# Обновляем систему
sudo apt update && sudo apt upgrade -y

# Устанавливаем Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Добавляем пользователя в группу docker
sudo usermod -aG docker $USER

# Устанавливаем Docker Compose
sudo apt install docker-compose -y

# Перезаходим в систему или выполняем:
newgrp docker

# Проверяем установку
docker --version
docker-compose --version
```

### На CentOS/RHEL:

```bash
# Устанавливаем Docker
sudo yum install -y yum-utils
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo yum install docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Запускаем Docker
sudo systemctl start docker
sudo systemctl enable docker

# Добавляем пользователя в группу
sudo usermod -aG docker $USER

# Проверяем
docker --version
docker compose version
```

---

## 4. Настройка проекта

### Шаг 4.1: Скачивание проекта

```bash
# Клонируем репозиторий
git clone https://github.com/your-repo/seedance-bot.git
cd seedance-bot

# Или распаковываем архив
unzip seedance-bot.zip
cd seedance-bot
```

### Шаг 4.2: Создание конфигурации

Создайте файл `.env.client`:

```bash
# В Linux/macOS
cp .env.client.example .env.client
nano .env.client

# В Windows
copy .env.client.example .env.client
notepad .env.client
```

### Шаг 4.3: Заполнение конфигурации

Откройте `.env.client` и заполните:

```env
# === TELEGRAM BOT (ОБЯЗАТЕЛЬНО!) ===
BOT_TOKEN=1234567890:AAAA-BBBB_CCCC_DDDD_EEEE_FFFF_GGGG_HHHH
BOT_USERNAME=myclientbot

# === API ===
WAVESPEED_API_KEY=your_api_key_here
WAVESPEED_BASE_URL=https://api.wavespeed.ai

# === DATABASE ===
DB_PASSWORD=my_super_secure_password_123

# === REDIS ===
REDIS_PASSWORD=my_redis_password_456

# === ADMIN ===
ADMIN_IDS=123456789,987654321  # Ваши Telegram ID через запятую

# === WEBHOOK (для продакшн) ===
WEBHOOK_HOST=https://yourdomain.com

# === ENVIRONMENT ===
DEBUG=false
LOG_LEVEL=INFO
SECRET_KEY=change_this_to_random_string_789
```

**⚠️ ВАЖНО:** 
- Замените `BOT_TOKEN` на реальный токен от BotFather
- Замените `ADMIN_IDS` на ваши Telegram ID  
- Создайте сложные пароли для `DB_PASSWORD` и `REDIS_PASSWORD`
- Для продакшн замените `WEBHOOK_HOST` на ваш домен

---

## 5. Локальное развертывание

### Шаг 5.1: Автоматическая настройка

```bash
# Дайте права на выполнение (Linux/macOS)
chmod +x setup-client.sh

# Запустите автоматическую настройку
./setup-client.sh
```

### Шаг 5.2: Ручная настройка

Если автоматическая настройка не работает:

```bash
# Сборка образов
docker-compose -f docker-compose.simple.yml build

# Запуск сервисов
docker-compose -f docker-compose.simple.yml up -d

# Проверка статуса
docker-compose -f docker-compose.simple.yml ps
```

### Шаг 5.3: Проверка локального запуска

```bash
# Логи бота
docker-compose -f docker-compose.simple.yml logs -f bot

# Проверка health check
curl http://localhost:8081/health

# Если curl не установлен (Windows)
Invoke-WebRequest -Uri http://localhost:8081/health
```

**Ожидаемый результат:**
```json
{"status": "ok", "timestamp": "2024-01-01T12:00:00Z"}
```

---

## 6. VPS развертывание

### Шаг 6.1: Подготовка VPS

#### Подключение к серверу:

```bash
# SSH подключение
ssh root@your-server-ip

# Или с ключом
ssh -i your-key.pem user@your-server-ip
```

#### Обновление системы:

```bash
# Ubuntu/Debian
apt update && apt upgrade -y

# CentOS/RHEL  
yum update -y
```

#### Установка необходимого ПО:

```bash
# Ubuntu/Debian
apt install -y git curl wget nano htop

# CentOS/RHEL
yum install -y git curl wget nano htop
```

### Шаг 6.2: Установка Docker на VPS

Следуйте инструкциям из раздела 3, в зависимости от вашей ОС.

### Шаг 6.3: Загрузка проекта на VPS

```bash
# Клонирование репозитория
git clone https://github.com/your-repo/seedance-bot.git
cd seedance-bot

# Или загрузка через scp
scp -r ./seedance-bot user@your-server-ip:/home/user/
```

### Шаг 6.4: Настройка конфигурации на VPS

```bash
# Создание конфигурации
cp .env.client.example .env.client
nano .env.client
```

**Обязательно измените для VPS:**
```env
# Webhook для продакшн
WEBHOOK_HOST=https://yourdomain.com

# Безопасность
DEBUG=false
ENVIRONMENT=production

# Сильные пароли
DB_PASSWORD=very_strong_password_123
REDIS_PASSWORD=another_strong_password_456
SECRET_KEY=random_secret_key_789
```

### Шаг 6.5: Запуск на VPS

```bash
# Минимальная конфигурация
make -f Makefile.client vps-up

# С Celery Worker (если нужны фоновые задачи)
make -f Makefile.client vps-up-full

# С автоматическими бэкапами
make -f Makefile.client vps-up-backup
```

---

## 7. Настройка домена и SSL

### Шаг 7.1: Настройка DNS

В панели управления вашего домена создайте A-запись:

```
Тип: A
Имя: @ (или bot)
Значение: IP_ВАШЕГО_VPS
TTL: 300
```

### Шаг 7.2: Установка Nginx

```bash
# Ubuntu/Debian
apt install -y nginx

# CentOS/RHEL
yum install -y nginx

# Запуск
systemctl start nginx
systemctl enable nginx
```

### Шаг 7.3: Настройка Nginx

Создайте конфигурацию `/etc/nginx/sites-available/client-bot`:

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Размер загружаемых файлов
        client_max_body_size 20M;
        
        # Таймауты
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # Health check
    location /health {
        proxy_pass http://127.0.0.1:8081/health;
        access_log off;
    }
}
```

Активируйте конфигурацию:

```bash
# Создаем символическую ссылку
ln -s /etc/nginx/sites-available/client-bot /etc/nginx/sites-enabled/

# Проверяем конфигурацию
nginx -t

# Перезапускаем Nginx
systemctl reload nginx
```

### Шаг 7.4: Установка SSL сертификата

```bash
# Устанавливаем Certbot
apt install -y certbot python3-certbot-nginx

# Получаем сертификат
certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Настраиваем автообновление
echo "0 12 * * * /usr/bin/certbot renew --quiet" | crontab -
```

### Шаг 7.5: Альтернатива - Caddy (проще)

Если хотите более простое решение, используйте Caddy:

```bash
# Установка Caddy
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install caddy

# Создание Caddyfile
cat > /etc/caddy/Caddyfile << 'EOF'
yourdomain.com {
    reverse_proxy localhost:8081
}
EOF

# Запуск Caddy
systemctl start caddy
systemctl enable caddy
```

---

## 8. Проверка работоспособности

### Шаг 8.1: Проверка сервисов

```bash
# Статус контейнеров
make -f Makefile.client status

# Логи бота
make -f Makefile.client logs-bot

# Health check
curl https://yourdomain.com/health
```

### Шаг 8.2: Проверка бота в Telegram

1. Найдите вашего бота в Telegram
2. Отправьте `/start`
3. Проверьте, что бот отвечает

### Шаг 8.3: Настройка Webhook

```bash
# Установка webhook (замените на ваш домен и токен)
curl -X POST "https://api.telegram.org/bot1234567890:YOUR_BOT_TOKEN/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://yourdomain.com/webhook"}'

# Проверка webhook
curl "https://api.telegram.org/bot1234567890:YOUR_BOT_TOKEN/getWebhookInfo"
```

**Ожидаемый ответ:**
```json
{
  "ok": true,
  "result": {
    "url": "https://yourdomain.com/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0
  }
}
```

---

## 9. Обслуживание и мониторинг

### Шаг 9.1: Основные команды

```bash
# Показать все команды
make -f Makefile.client help

# Посмотреть статус
make -f Makefile.client status

# Перезапустить
make -f Makefile.client restart

# Остановить
make -f Makefile.client down

# Обновить
git pull
make -f Makefile.client restart
```

### Шаг 9.2: Мониторинг ресурсов

```bash
# Статистика контейнеров
make -f Makefile.client stats

# Использование диска
df -h

# Память
free -h

# Процессы
htop
```

### Шаг 9.3: Резервное копирование

```bash
# Создать бэкап
make -f Makefile.client backup

# Посмотреть бэкапы
ls -la ./backups/

# Восстановить из бэкапа
make -f Makefile.client restore-file BACKUP_FILE=./backups/backup_20240101_120000.sql.gz
```

### Шаг 9.4: Логи

```bash
# Все логи
make -f Makefile.client logs

# Только ошибки
make -f Makefile.client logs | grep -i error

# Последние 100 строк
make -f Makefile.client logs --tail=100

# Логи в реальном времени
make -f Makefile.client logs -f
```

---

## 10. Решение проблем

### Проблема: Бот не отвечает

**Симптомы:** Бот не реагирует на команды

**Решение:**
```bash
# Проверяем статус
make -f Makefile.client status

# Смотрим логи
make -f Makefile.client logs-bot

# Проверяем webhook
curl "https://api.telegram.org/botYOUR_TOKEN/getWebhookInfo"

# Перезапускаем
make -f Makefile.client restart
```

### Проблема: Ошибка подключения к базе данных

**Симптомы:** `connection refused` в логах

**Решение:**
```bash
# Проверяем PostgreSQL
make -f Makefile.client logs-db

# Подключаемся к БД
make -f Makefile.client shell-db

# Перезапускаем БД
docker-compose -f docker-compose.simple.yml restart postgres
```

### Проблема: Webhook не работает

**Симптомы:** Бот работает в polling, но не через webhook

**Решение:**
```bash
# Проверяем доступность
curl https://yourdomain.com/health

# Проверяем Nginx
systemctl status nginx
nginx -t

# Проверяем SSL
curl -I https://yourdomain.com

# Переустанавливаем webhook
curl -X POST "https://api.telegram.org/botYOUR_TOKEN/setWebhook" \
     -d "url=https://yourdomain.com/webhook"
```

### Проблема: Нехватка места на диске

**Симптомы:** `No space left on device`

**Решение:**
```bash
# Проверяем место
df -h

# Очищаем Docker
docker system prune -a -f

# Очищаем логи
journalctl --vacuum-time=7d

# Удаляем старые бэкапы
find ./backups -name "*.sql.gz" -mtime +7 -delete
```

### Проблема: Высокое потребление памяти

**Симптомы:** Система тормозит, OOM killer

**Решение:**
```bash
# Смотрим потребление
make -f Makefile.client stats

# Уменьшаем память Redis в docker-compose.simple.yml
# --maxmemory 128mb (вместо 256mb)

# Перезапускаем
make -f Makefile.client restart
```

### Проблема: Порты заняты

**Симптомы:** `port already in use`

**Решение:**
```bash
# Проверяем какой процесс использует порт
sudo netstat -tulpn | grep :8081

# Останавливаем конфликтующий сервис
sudo systemctl stop conflicting-service

# Или меняем порты в конфигурации
nano docker-compose.simple.yml
# Измените 8081 на другой порт
```

---

## 📞 Получение помощи

### Логирование ошибок

Если у вас проблемы, соберите информацию:

```bash
# Статус системы
make -f Makefile.client status > debug_info.txt
make -f Makefile.client logs >> debug_info.txt
docker system info >> debug_info.txt
free -h >> debug_info.txt
df -h >> debug_info.txt
```

### Полезные ссылки

- **Docker документация**: https://docs.docker.com/
- **Telegram Bot API**: https://core.telegram.org/bots/api
- **Nginx документация**: https://nginx.org/ru/docs/
- **Let's Encrypt**: https://letsencrypt.org/

### Чек-лист перед обращением за помощью

- [ ] Проверил логи `make -f Makefile.client logs`
- [ ] Проверил статус `make -f Makefile.client status`
- [ ] Проверил конфигурацию `.env.client`
- [ ] Попробовал перезапуск `make -f Makefile.client restart`
- [ ] Проверил доступность домена `curl https://yourdomain.com/health`
- [ ] Проверил webhook `curl "https://api.telegram.org/botTOKEN/getWebhookInfo"`

---

## 🎉 Поздравляем!

Если вы дошли до этого места и бот работает - вы молодцы! 

Ваш клиентский бот готов к работе и полностью настроен. Не забывайте:

- ✅ Регулярно делать бэкапы
- ✅ Мониторить логи и ресурсы  
- ✅ Обновлять систему и Docker образы
- ✅ Следить за безопасностью (пароли, SSL)

**Удачи в использовании!** 🚀 