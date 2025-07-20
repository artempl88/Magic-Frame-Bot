# 🤖 Клиентский Telegram Бот

Упрощенная версия Telegram бота для клиентов с минимальным набором сервисов.

## 📚 Документация

| Файл | Описание |
|------|----------|
| **[QUICK_START.md](QUICK_START.md)** | ⚡ Быстрый старт за 5 минут |
| **[DEPLOY_GUIDE.md](DEPLOY_GUIDE.md)** | 📖 Подробная инструкция для новичков |
| **[README.CLIENT.md](README.CLIENT.md)** | 🔧 Техническая документация |

## 🎯 Что включено

- ✅ **Telegram Bot** - основной сервис
- ✅ **PostgreSQL** - база данных (порт 5433)
- ✅ **Redis** - кеш и сессии (порт 6380)
- ✅ **Celery Worker** - фоновые задачи (опционально)
- ✅ **Автоматические бэкапы** - резервное копирование БД

## 🧹 Очищено от лишних компонентов

- ❌ Nginx - веб-сервер (не нужен для простого бота)
- ❌ Grafana - мониторинг и дашборды
- ❌ Prometheus - система метрик  
- ❌ Flower - мониторинг Celery
- ❌ Старые скрипты и конфигурации

📋 Подробности в [DOCKER_CLEANUP_SUMMARY.md](DOCKER_CLEANUP_SUMMARY.md)

## ⚡ Быстрый старт

⚠️ **ВАЖНО**: Перед запуском обязательно замените тестовые значения! См. [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md)

```bash
# 1. Настройте конфигурацию (ОБЯЗАТЕЛЬНО!)
nano .env.client  # Замените test_token и test_key на реальные!

# 2. Автоматическая настройка и запуск
./setup-client.sh

# Или вручную
make -f Makefile.client quick-start
```

### 🔧 Обязательно замените заглушки:
- `BOT_TOKEN` - токен от @BotFather  
- `WAVESPEED_API_KEY` - ключ API от WaveSpeed
- `ADMIN_IDS` - ваши Telegram ID
- `DB_PASSWORD` - безопасный пароль БД
- `SECRET_KEY` - случайный секретный ключ

📋 Полный список в [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md)

**Готово!** Бот запущен на http://localhost:8081

## 📦 Файлы проекта

```
📁 Конфигурации развертывания:
├── docker-compose.simple.yml    # Локальная разработка
├── docker-compose.client.yml    # VPS развертывание
└── Makefile.client             # Команды управления

📁 Настройка и документация:
├── setup-client.sh             # Автоматическая настройка
├── QUICK_START.md              # Быстрый старт за 5 минут
├── DEPLOY_GUIDE.md             # Подробная инструкция
└── README.CLIENT.md            # Техническая документация

📁 Конфигурация:
├── .env.client                 # Настройки окружения (создается автоматически)
├── logs/                       # Логи приложения
├── static/                     # Статические файлы
└── backups/                    # Резервные копии БД
```

## 🛠️ Основные команды

```bash
# Показать все команды
make -f Makefile.client help

# Запуск/остановка
make -f Makefile.client up        # Запустить локально
make -f Makefile.client up-backup # Запустить с автобэкапами
make -f Makefile.client down      # Остановить
make -f Makefile.client restart   # Перезапустить

# Мониторинг
make -f Makefile.client ps      # Статус сервисов
make -f Makefile.client logs    # Логи
make -f Makefile.client health  # Проверка здоровья

# База данных и бэкапы
make -f Makefile.client backup-auto    # Создать бэкап сейчас
make -f Makefile.client backup-list    # Список бэкапов  
make -f Makefile.client backup-cleanup # Очистить старые
make -f Makefile.client shell-db       # Подключиться к БД
```

## 🌐 Развертывание на VPS

```bash
# Запуск на продакшн сервере
make -f Makefile.client vps-up

# С фоновыми задачами  
make -f Makefile.client vps-up-full

# С автоматическими бэкапами
make -f Makefile.client vps-up-backup

# Остановка
make -f Makefile.client vps-down
```

## 🔧 Webhook для VPS (опционально)

Для продакшн развертывания на VPS с доменом настройте webhook в `.env.client`:

```bash
# Webhook настройки
WEBHOOK_HOST=https://yourdomain.com
WEBHOOK_PATH=/webhook
WEBHOOK_PORT=8081
```

Telegram будет отправлять обновления напрямую на ваш бот.

## 📞 Помощь

1. **Новичок?** → Читайте [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md)
2. **Нужно быстро?** → Смотрите [QUICK_START.md](QUICK_START.md)  
3. **Технические детали?** → Изучайте [README.CLIENT.md](README.CLIENT.md)

## 🆘 Решение проблем

```bash
# Бот не отвечает
make -f Makefile.client logs-bot
make -f Makefile.client restart

# Проблемы с БД
make -f Makefile.client shell-db
make -f Makefile.client logs-db

# Проверка здоровья
curl http://localhost:8081/health
make -f Makefile.client health
```

## 🎯 Системные требования

**Минимальные:**
- RAM: 2 GB
- CPU: 1 ядро  
- Диск: 10 GB
- Docker + Docker Compose

**Рекомендуемые:**
- RAM: 4 GB
- CPU: 2 ядра
- Диск: 20 GB
- SSD диск

## 🔒 Безопасность

- ✅ Используйте сильные пароли в `.env.client`
- ✅ Настройте SSL сертификаты
- ✅ Ограничьте доступ к портам через firewall  
- ✅ Регулярно создавайте резервные копии
- ✅ Обновляйте систему и Docker образы

## 📈 Мониторинг

```bash
# Использование ресурсов
make -f Makefile.client stats

# Размер логов и бэкапов
du -sh logs/ backups/

# Свободное место
df -h
```

---

**🚀 Готов к работе!** Ваш клиентский бот развернут и настроен. 