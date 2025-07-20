#!/bin/bash

# Скрипт для быстрой настройки клиентского бота (упрощенная версия)

set -e

echo "🤖 Настройка клиентского бота"
echo "============================="

# Проверяем Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker не установлен"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose не установлен"
    exit 1
fi

# Создаем .env.client если не существует
if [ ! -f ".env.client" ]; then
    echo "📋 Создание .env.client..."
    cat > .env.client << 'EOF'
# Конфигурация клиентского бота

# === TELEGRAM BOT (ОБЯЗАТЕЛЬНО ЗАПОЛНИТЬ) ===
BOT_TOKEN=your_bot_token_here
BOT_USERNAME=YourClientBot

# === API ===
WAVESPEED_API_KEY=your_api_key_here
WAVESPEED_BASE_URL=https://api.wavespeed.ai

# === DATABASE ===
DB_HOST=postgres
DB_PORT=5432
DB_NAME=client_bot
DB_USER=botuser
DB_PASSWORD=secure_db_password_123

# === REDIS ===
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=secure_redis_password_123
REDIS_DB=0

# === WEBHOOK ===
WEBHOOK_HOST=https://your-domain.com
WEBHOOK_PATH=/webhook
WEBHOOK_PORT=8081

# === ADMIN ===
ADMIN_IDS=123456789,987654321

# === ENVIRONMENT ===
DEBUG=false
LOG_LEVEL=INFO
ENVIRONMENT=production
SECRET_KEY=super_secret_key_for_production_12345

# === CELERY ===
CELERY_BROKER_URL=redis://:secure_redis_password_123@redis:6379/1
CELERY_RESULT_BACKEND=redis://:secure_redis_password_123@redis:6379/1

# === FEATURES ===
WELCOME_BONUS_CREDITS=10
REFERRAL_BONUS_CREDITS=20
GENERATIONS_PER_MINUTE=5
GENERATIONS_PER_HOUR=50
EOF

    echo "✅ Файл .env.client создан"
    echo ""
    echo "⚠️  ВАЖНО: Отредактируйте .env.client и укажите:"
    echo "   - BOT_TOKEN (токен бота)"
    echo "   - BOT_USERNAME (username бота)"
    echo "   - WAVESPEED_API_KEY (API ключ)"
    echo "   - ADMIN_IDS (ваши Telegram ID)"
    echo "   - WEBHOOK_HOST (ваш домен)"
    echo "   - Пароли для БД и Redis"
    echo ""
    read -p "Нажмите Enter после редактирования .env.client..."
else
    echo "✅ Файл .env.client уже существует"
fi

# Проверяем порты
echo "🔧 Проверка портов..."
check_port() {
    local port=$1
    local service=$2
    if netstat -tuln 2>/dev/null | grep -q ":$port " || ss -tuln 2>/dev/null | grep -q ":$port "; then
        echo "⚠️  Порт $port ($service) занят"
        return 1
    else
        echo "✅ Порт $port ($service) свободен"
        return 0
    fi
}

ports_ok=true
check_port 8081 "Bot webhook" || ports_ok=false
check_port 5433 "PostgreSQL" || ports_ok=false
check_port 6380 "Redis" || ports_ok=false

if [ "$ports_ok" = false ]; then
    echo ""
    echo "❌ Некоторые порты заняты. Остановите конфликтующие сервисы или измените порты в docker-compose.simple.yml"
    exit 1
fi

# Создаем необходимые директории
echo "📁 Создание директорий..."
mkdir -p logs static backups

echo ""
echo "🏗️  Сборка Docker образов..."
docker-compose -f docker-compose.simple.yml build

echo ""
echo "🚀 Запуск сервисов..."
docker-compose -f docker-compose.simple.yml up -d

echo ""
echo "⏳ Ожидание готовности сервисов..."
sleep 15

echo ""
echo "🔍 Проверка статуса..."
docker-compose -f docker-compose.simple.yml ps

echo ""
echo "🎉 Клиентский бот запущен!"
echo ""
echo "📊 Доступные сервисы:"
echo "   - Bot webhook: http://localhost:8081"
echo "   - PostgreSQL: localhost:5433"
echo "   - Redis: localhost:6380"
echo ""
echo "🔧 Полезные команды:"
echo "   make -f Makefile.client help      # Все команды"
echo "   make -f Makefile.client logs      # Логи"
echo "   make -f Makefile.client status    # Статус"
echo "   make -f Makefile.client health    # Проверка здоровья"
echo "   make -f Makefile.client down      # Остановка"
echo ""
echo "📖 Документация: README.CLIENT.md"
echo ""
echo "🌐 Для работы webhook настройте веб-сервер:"
echo "   - Nginx: проксировать на localhost:8081"
echo "   - Caddy: reverse_proxy localhost:8081" 