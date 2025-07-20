# Клиентский бот - упрощенная версия

Упрощенная конфигурация бота для клиента с минимальным набором сервисов.

## 🎯 Что включено

- **Telegram Bot** - основной сервис
- **PostgreSQL** - база данных
- **Redis** - кеш и сессии
- **Celery Worker** - фоновые задачи (опционально)
- **Резервное копирование** - автоматические бэкапы БД

## 🚫 Что убрано

- Nginx (используйте системный веб-сервер)
- Prometheus/Grafana (мониторинг)
- Flower (мониторинг Celery)
- Celery Beat (периодические задачи)

## 📦 Порты

| Сервис | Порт | Описание |
|--------|------|----------|
| Bot webhook | 8081 | HTTP endpoint для Telegram |
| PostgreSQL | 5433 | База данных (локальный доступ) |
| Redis | 6380 | Кеш (локальный доступ) |

## 🚀 Быстрый старт

### 1. Настройка конфигурации

Создайте файл `.env.client`:

```bash
# Telegram Bot
BOT_TOKEN=1234567890:AAAA-BBBB_CCCC_DDDD_EEEE_FFFF_GGGG_HHHH
BOT_USERNAME=YourClientBot

# API
WAVESPEED_API_KEY=your_api_key_here

# Database
DB_PASSWORD=secure_db_password_123

# Redis
REDIS_PASSWORD=secure_redis_password_123

# Admin
ADMIN_IDS=123456789,987654321

# Webhook
WEBHOOK_HOST=https://your-domain.com
```

### 2. Запуск локально

```bash
# Сборка и запуск
make -f Makefile.client quick-start

# Только основные сервисы
make -f Makefile.client start-minimal

# С Celery Worker
make -f Makefile.client up-full
```

### 3. Запуск на VPS

```bash
# Минимальная конфигурация
make -f Makefile.client vps-up

# С Celery Worker
make -f Makefile.client vps-up-full

# С резервным копированием
make -f Makefile.client vps-up-backup
```

## 🛠️ Управление

### Основные команды

```bash
# Показать все команды
make -f Makefile.client help

# Статус сервисов
make -f Makefile.client status

# Логи
make -f Makefile.client logs
make -f Makefile.client logs-bot

# Перезапуск
make -f Makefile.client restart

# Остановка
make -f Makefile.client down
```

### Работа с базой данных

```bash
# Подключиться к БД
make -f Makefile.client shell-db

# Применить миграции
make -f Makefile.client migrate

# Создать резервную копию
make -f Makefile.client backup

# Восстановить из резервной копии
make -f Makefile.client restore-file BACKUP_FILE=./backups/backup_20240101_120000.sql.gz
```

### Отладка

```bash
# Проверить здоровье сервисов
make -f Makefile.client health

# Debug режим
make -f Makefile.client debug

# Интерактивная оболочка Python
make -f Makefile.client debug-shell
```

## 🌐 Настройка веб-сервера

### Nginx

Создайте конфигурацию `/etc/nginx/sites-available/client-bot`:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Caddy

Создайте `Caddyfile`:

```
your-domain.com {
    reverse_proxy localhost:8081
}
```

## 📊 Мониторинг

### Простая проверка

```bash
# Статистика ресурсов
make -f Makefile.client stats

# Процессы в контейнерах
make -f Makefile.client top

# Health check
curl http://localhost:8081/health
```

### Системный мониторинг

```bash
# Использование места
docker system df

# Логи системы
journalctl -u docker -f
```

## 💾 Резервное копирование

### Автоматические бэкапы

```bash
# Локально с автоматическими бэкапами
make -f Makefile.client up-backup

# На VPS с автоматическими бэкапами
make -f Makefile.client vps-up-backup
```

**Расписание автоматических бэкапов:**
- 🕒 **Ежедневно в 3:00 UTC** - основные бэкапы
- 🕑 **Еженедельно в воскресенье 2:00 UTC** - полные бэкапы (только VPS)
- 🧹 **Ежедневно в 4:00 UTC** - автоочистка файлов старше 30 дней

### Ручные бэкапы

```bash
# Создать бэкап прямо сейчас
make -f Makefile.client backup-auto

# Создать бэкап через админку бота (с описанием)
# /admin → 💾 Бэкапы БД → ➕ Создать бэкап

# Список всех бэкапов
make -f Makefile.client backup-list

# Размер папки с бэкапами
make -f Makefile.client backup-size

# Очистить старые бэкапы
make -f Makefile.client backup-cleanup

# Восстановить из файла
make -f Makefile.client restore-file BACKUP_FILE=./backups/backup_20240101_120000.sql.gz
```

### Управление через админку

В админской панели бота (`/admin` → `💾 Бэкапы БД`) доступно:

- **➕ Создать бэкап** - ручное создание с описанием
- **📁 Список бэкапов** - просмотр всех бэкапов с метаданными  
- **📊 Статистика** - общая информация о бэкапах
- **🧹 Очистить старые** - удаление бэкапов старше 30 дней
- **🗑️ Удалить** - удаление конкретного бэкапа
- **⚠️ Восстановить** - восстановление БД (с подтверждением)

## 🔧 Конфигурация

### Структура файлов

```
├── .env.client              # Настройки окружения
├── docker-compose.simple.yml # Локальная разработка
├── docker-compose.client.yml # VPS развертывание
├── Makefile.client          # Команды управления
├── logs/                    # Логи приложения
├── static/                  # Статические файлы
└── backups/                 # Резервные копии
```

### Профили Docker Compose

- **По умолчанию**: Только bot + postgres + redis
- **full**: Добавляет Celery Worker
- **backup**: Добавляет автоматические бэкапы

```bash
# Запуск с профилем
docker-compose -f docker-compose.client.yml --profile full up -d
```

## 🐛 Решение проблем

### Конфликт портов

Если порты заняты, измените их в файлах:
- `docker-compose.simple.yml` - для локальной разработки
- `docker-compose.client.yml` - для VPS

### Проблемы с базой данных

```bash
# Проверить подключение
make -f Makefile.client shell-db

# Пересоздать БД
make -f Makefile.client clean
make -f Makefile.client up
make -f Makefile.client migrate
```

### Проблемы с памятью

Уменьшить настройки Redis в docker-compose файлах:

```yaml
redis:
  command: >
    redis-server
    --maxmemory 128mb  # было 256mb
```

### Логи заполняют диск

```bash
# Очистить логи Docker
docker system prune -a -f

# Настроить ротацию логов
echo '{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker
```

## 📈 Масштабирование

### Увеличение производительности

1. **Увеличить память для Redis**:
```yaml
--maxmemory 512mb
```

2. **Добавить Celery Worker**:
```bash
make -f Makefile.client up-full
```

3. **Настроить параллелизм**:
```yaml
command: celery -A bot.tasks worker --concurrency=4
```

### Мониторинг производительности

```bash
# Статистика контейнеров
docker stats

# Использование места
df -h
du -sh ./logs ./backups

# Нагрузка на систему
htop
```

## 🔒 Безопасность

1. **Используйте сильные пароли** в `.env.client`
2. **Ограничьте доступ к портам** через firewall
3. **Регулярно обновляйте** Docker образы
4. **Создавайте резервные копии** важных данных
5. **Мониторьте логи** на предмет подозрительной активности

```bash
# Обновление образов
docker-compose pull
make -f Makefile.client restart
``` 