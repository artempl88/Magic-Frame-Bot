# 🪄 Magic Frame Bot - VPS версия

AI бот для генерации видео готовый к продакшн развертыванию на VPS с поддержкой Telegram Stars и ЮКассы.

## 📚 Документация

| Файл | Описание |
|------|----------|
| **[QUICK_START.md](QUICK_START.md)** | ⚡ Быстрый старт за 5 минут |
| **[DEPLOY_GUIDE.md](DEPLOY_GUIDE.md)** | 📖 Подробная инструкция для новичков |
| **[YOOKASSA_TEST_SETUP.md](YOOKASSA_TEST_SETUP.md)** | 🧪 Настройка тестовых данных ЮКассы |
| **[README.CLIENT.md](README.CLIENT.md)** | 🔧 Техническая документация |

## 🎯 Что включено

- ✅ **Telegram Bot** - AI генерация видео через WaveSpeed API
- ✅ **PostgreSQL** - база данных
- ✅ **Redis** - кеш и сессии  
- ✅ **Telegram Stars** - встроенная платежная система
- ✅ **ЮКасса** - банковские карты (с тестовыми данными `381764678:TEST:132257`)
- ✅ **Админ-панель** - управление ценами и настройками
- ✅ **Автоматические бэкапы** - защита данных
- ✅ **Webhook** - готов к VPS развертыванию

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
make help

# Запуск на VPS
make up        # Запустить бота на VPS (webhook: https://chatbotan.ru/magicframe)
make up-backup # Запустить с автобэкапами
make up-full   # Запустить с Celery Worker
make down      # Остановить
make restart   # Перезапустить

# Мониторинг
make ps      # Статус сервисов
make logs    # Логи
make health  # Проверка здоровья (включая webhook)

# База данных и бэкапы
make backup-auto    # Создать бэкап сейчас
make backup-list    # Список бэкапов  
make backup-cleanup # Очистить старые
make shell-db       # Подключиться к БД
```

## 🚀 Быстрый старт на VPS

1. **Клонировать репозиторий:**
   ```bash
   git clone <repo-url>
   cd MagicFrameBot
   ```

2. **Настроить webhook и ЮКассу в `.env.client`:**
   ```bash
   # Настроено для https://chatbotan.ru/magicframe
   # При необходимости добавьте ЮКассу:
   YOOKASSA_SHOP_ID=ваш_shop_id
   YOOKASSA_SECRET_KEY=ваш_secret_key
   ```

3. **Запустить бота:**
   ```bash
   make up-backup  # С автоматическими бэкапами
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

## 🎉 Готово!

**Ваш Magic Frame Bot готов к продакшену на VPS!**

- 🤖 **Webhook:** https://chatbotan.ru/magicframe
- 💳 **ЮКасса webhook:** https://chatbotan.ru/yookassa/webhook
- 🏥 **Health check:** https://chatbotan.ru/magicframe/health
- 💰 **Админка:** `/admin` в боте

**Следующие шаги:**
1. Настроить ЮКассу в `.env.client`
2. Установить цены через админку
3. Протестировать платежи
4. Получать доходы! 💸 