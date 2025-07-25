# 🔧 Руководство по настройке конфигурации

## ❌ ВАЖНО: Замените тестовые значения!

В файле `core/config.py` есть тестовые значения, которые **ОБЯЗАТЕЛЬНО** нужно заменить:

### 🔑 Обязательные настройки для замены:

```python
# ❌ ЗАГЛУШКИ В core/config.py - ЗАМЕНИТЬ:
BOT_TOKEN: str = "test_token"                    # → Реальный токен от BotFather
BOT_USERNAME: str = "SeedanceOfficialBot"        # → Username вашего бота
WAVESPEED_API_KEY: str = "test_key"              # → Реальный API ключ от WaveSpeed
DB_PASSWORD: str = "test_password"               # → Безопасный пароль БД
SECRET_KEY: str = "test_secret_key_12345"        # → Случайный секретный ключ
```

## 📋 Пример файла .env.client

Создайте файл `.env.client` в корне проекта со следующими настройками:

```bash
# ===============================================
# ОСНОВНЫЕ НАСТРОЙКИ TELEGRAM БОТА
# ===============================================

# Токен бота от @BotFather (обязательно!)
BOT_TOKEN=1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890

# Username бота (без @)
BOT_USERNAME=your_bot_username

# ===============================================
# WAVESPEED AI API
# ===============================================

# API ключ от WaveSpeed AI (получить на https://wavespeed.ai)
WAVESPEED_API_KEY=ws_live_abc123def456ghi789jkl012mno345pqr

# Базовый URL API (обычно не меняется)
WAVESPEED_BASE_URL=https://api.wavespeed.ai

# ===============================================
# БАЗА ДАННЫХ POSTGRESQL
# ===============================================

# Хост БД (localhost для локальной разработки)
DB_HOST=localhost

# Порт БД (стандартный 5432)
DB_PORT=5432

# Имя базы данных
DB_NAME=client_bot

# Пользователь БД
DB_USER=botuser

# Пароль БД (ОБЯЗАТЕЛЬНО измените!)
DB_PASSWORD=secure_random_password_here

# ===============================================
# REDIS ДЛЯ КЕШИРОВАНИЯ
# ===============================================

# Хост Redis
REDIS_HOST=localhost

# Порт Redis (стандартный 6379)
REDIS_PORT=6379

# Пароль Redis (оставьте пустым если не установлен)
REDIS_PASSWORD=redis_secure_password

# Номер БД Redis (0-15)
REDIS_DB=0

# ===============================================
# WEBHOOK ДЛЯ VPS РАЗВЕРТЫВАНИЯ
# ===============================================

# Домен вашего сервера (для VPS)
WEBHOOK_HOST=https://yourdomain.com

# Путь webhook (обычно не меняется)
WEBHOOK_PATH=/webhook

# Порт для webhook (обычно 8080 или 8081)
WEBHOOK_PORT=8081

# ===============================================
# АДМИНИСТРИРОВАНИЕ
# ===============================================

# ID администраторов (через запятую, получить от @userinfobot)
ADMIN_IDS=123456789,987654321

# ID канала для админских уведомлений (опционально)
ADMIN_CHANNEL_ID=-1001234567890

# ===============================================
# ПОДДЕРЖКА И КАНАЛЫ
# ===============================================

# ID чата поддержки (опционально)
SUPPORT_CHAT_ID=-1001234567890

# Username канала для обязательной подписки (опционально, без @)
CHANNEL_USERNAME=your_channel

# ===============================================
# БЕЗОПАСНОСТЬ И ШИФРОВАНИЕ
# ===============================================

# Секретный ключ (генерируйте случайно, минимум 32 символа)
SECRET_KEY=your_super_secret_key_here_min_32_chars_long

# Окружение (production/development)
ENVIRONMENT=production

# ===============================================
# ОПЦИОНАЛЬНЫЕ НАСТРОЙКИ
# ===============================================

# Отладочный режим (true/false)
DEBUG=false

# Уровень логирования (DEBUG/INFO/WARNING/ERROR)
LOG_LEVEL=INFO

# Sentry DSN для мониторинга ошибок (опционально)
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id

# ===============================================
# ОГРАНИЧЕНИЯ И ЛИМИТЫ
# ===============================================

# Максимальный размер файла (в байтах, 10MB)
MAX_FILE_SIZE=10485760

# Генераций в минуту на пользователя
GENERATIONS_PER_MINUTE=3

# Генераций в час на пользователя  
GENERATIONS_PER_HOUR=30

# ===============================================
# БОНУСЫ И НАГРАДЫ
# ===============================================

# Приветственный бонус новым пользователям
WELCOME_BONUS_CREDITS=10

# Бонус рефереру за приглашение
REFERRAL_BONUS_CREDITS=20

# Бонус приглашенному другу
REFERRAL_FRIEND_BONUS_CREDITS=10
```

## 🚀 Как получить токены и ключи:

### 1. **Telegram Bot Token**
1. Напишите @BotFather в Telegram
2. Выполните `/newbot`
3. Следуйте инструкциям
4. Получите токен в формате `1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ`

### 2. **WaveSpeed AI Key**
1. Зарегистрируйтесь на https://wavespeed.ai
2. Перейдите в настройки API
3. Создайте новый API ключ
4. Скопируйте ключ в формате `ws_live_...`

### 3. **Admin IDs**
1. Напишите @userinfobot в Telegram
2. Отправьте `/start`
3. Скопируйте ваш User ID
4. Добавьте в ADMIN_IDS через запятую

### 4. **Секретный ключ**
Сгенерируйте случайный ключ длиной минимум 32 символа:
```bash
# Linux/Mac:
openssl rand -hex 32

# Python:
import secrets
print(secrets.token_hex(32))

# Online: https://randomkeygen.com/
```

## ⚠️ Безопасность:

1. **Никогда не коммитьте файлы .env в Git!**
2. **Используйте сложные пароли для БД**
3. **Регулярно обновляйте секретные ключи**
4. **Ограничивайте доступ к серверу**
5. **Включите SSL/HTTPS на продакшене**

## 🔄 После настройки:

1. Создайте файл `.env.client` с вашими значениями
2. Проверьте что все токены корректны
3. Запустите бота: `make -f Makefile.client up`
4. Проверьте логи: `make -f Makefile.client logs`

## 📋 Проверочный список:

- [ ] ✅ Получен токен от @BotFather
- [ ] ✅ Получен API ключ от WaveSpeed AI  
- [ ] ✅ Настроены ID администраторов
- [ ] ✅ Изменены пароли БД и Redis
- [ ] ✅ Сгенерирован секретный ключ
- [ ] ✅ Настроен домен для VPS (если нужно)
- [ ] ✅ Создан файл .env.client
- [ ] ✅ Проверен запуск бота

## 🆘 Если возникли проблемы:

1. Проверьте логи: `make -f Makefile.client logs`
2. Проверьте здоровье сервисов: `make -f Makefile.client health`
3. Убедитесь что все сервисы запущены: `make -f Makefile.client ps`
4. Проверьте подключение к БД: `make -f Makefile.client shell-db`

## 🎯 Итог

После правильной настройки всех параметров у вас будет полностью рабочий бот с:
- ✅ Генерацией видео через WaveSpeed AI
- ✅ Системой администрирования  
- ✅ Автоматическими бэкапами
- ✅ Системой пользователей и кредитов
- ✅ Безопасной аутентификацией 