#!/bin/bash

# Скрипт развертывания Seedance Bot на VPS
# Автор: Seedance Team
# Версия: 1.0

set -e

echo "🚀 Начинаем развертывание Seedance Bot на VPS..."

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода цветного текста
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка наличия Docker
if ! command -v docker &> /dev/null; then
    print_error "Docker не установлен. Установите Docker и Docker Compose."
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    print_error "Docker Compose не установлен."
    exit 1
fi

# Проверка наличия .env файла
if [ ! -f ".env" ]; then
    print_warning "Файл .env не найден."
    if [ -f "vps-env-example.txt" ]; then
        print_status "Копируем пример конфигурации..."
        cp vps-env-example.txt .env
        print_warning "Отредактируйте файл .env с вашими настройками перед продолжением."
        print_warning "Особенно важно настроить:"
        echo "  - BOT_TOKEN"
        echo "  - WEBHOOK_HOST"
        echo "  - DB_PASSWORD"
        echo "  - REDIS_PASSWORD"
        echo "  - SECRET_KEY"
        echo "  - ADMIN_IDS"
        read -p "Нажмите Enter после настройки .env файла..."
    else
        print_error "Файл конфигурации не найден. Создайте .env файл."
        exit 1
    fi
fi

# Создание необходимых директорий
print_status "Создаем необходимые директории..."
mkdir -p logs static/images static/videos backups

# Проверка системного nginx
print_status "Проверка системного nginx..."
if systemctl is-active --quiet nginx; then
    print_success "Nginx запущен"
    
    # Проверяем конфигурацию для бота
    if [ ! -f "/etc/nginx/sites-available/seedance-bot" ]; then
        print_warning "Конфигурация nginx для бота не найдена."
        print_status "У вас уже есть SSL от Beget - отлично!"
        print_status "Выполните настройку nginx:"
        echo "  1. sudo cp nginx-site.conf /etc/nginx/sites-available/seedance-bot"
        echo "  2. Отредактируйте файл и укажите ваши SSL сертификаты"
        echo "  3. sudo ln -s /etc/nginx/sites-available/seedance-bot /etc/nginx/sites-enabled/"
        echo "  4. sudo nginx -t && sudo systemctl reload nginx"
        echo ""
        print_status "Подробная инструкция в файле BEGET_SSL_SETUP.md"
        read -p "Нажмите Enter после настройки nginx..."
    else
        print_success "Конфигурация nginx найдена"
    fi
else
    print_error "Nginx не запущен или не установлен."
    print_status "Установите nginx:"
    echo "  sudo apt install nginx"
    echo "  sudo systemctl start nginx"
    echo "  sudo systemctl enable nginx"
    exit 1
fi

# Остановка существующих контейнеров
print_status "Остановка существующих контейнеров..."
docker-compose -f docker-compose.vps.yml down 2>/dev/null || true

# Сборка образов
print_status "Сборка Docker образов..."
docker-compose -f docker-compose.vps.yml build --no-cache

# Запуск сервисов
print_status "Запуск сервисов..."
docker-compose -f docker-compose.vps.yml up -d

# Ожидание запуска
print_status "Ожидание запуска сервисов..."
sleep 30

# Проверка статуса
print_status "Проверка статуса сервисов..."
if docker-compose -f docker-compose.vps.yml ps | grep -q "Up"; then
    print_success "Сервисы запущены успешно!"
else
    print_error "Ошибка запуска сервисов."
    docker-compose -f docker-compose.vps.yml logs
    exit 1
fi

# Миграции базы данных
print_status "Применение миграций базы данных..."
docker-compose -f docker-compose.vps.yml exec bot python migrations/apply_migrations.py

# Проверка webhook'а
print_status "Проверка webhook'а..."
WEBHOOK_URL=$(grep WEBHOOK_HOST .env | cut -d '=' -f2)
if [ ! -z "$WEBHOOK_URL" ]; then
    echo "Webhook URL: ${WEBHOOK_URL}/webhook"
    print_warning "Не забудьте настроить webhook в BotFather!"
    print_warning "Команда: /setwebhook"
    print_warning "URL: ${WEBHOOK_URL}/webhook"
fi

# Настройка логротate
print_status "Настройка ротации логов..."
sudo tee /etc/logrotate.d/seedance-bot > /dev/null <<EOF
$(pwd)/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 $(whoami) $(whoami)
    postrotate
        docker-compose -f $(pwd)/docker-compose.vps.yml restart bot
    endscript
}
EOF

# Настройка системного сервиса
print_status "Создание systemd сервиса..."
sudo tee /etc/systemd/system/seedance-bot.service > /dev/null <<EOF
[Unit]
Description=Seedance Bot
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$(pwd)
ExecStart=/usr/bin/docker-compose -f docker-compose.vps.yml up -d
ExecStop=/usr/bin/docker-compose -f docker-compose.vps.yml down
User=$(whoami)
Group=$(whoami)

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable seedance-bot.service

# Финальная проверка
print_status "Финальная проверка..."
sleep 10

# Проверка здоровья контейнеров
HEALTHY_CONTAINERS=$(docker-compose -f docker-compose.vps.yml ps --services --filter "status=running" | wc -l)
TOTAL_CONTAINERS=$(docker-compose -f docker-compose.vps.yml config --services | wc -l)

if [ "$HEALTHY_CONTAINERS" -eq "$TOTAL_CONTAINERS" ]; then
    print_success "✅ Развертывание завершено успешно!"
    echo ""
    echo "📊 Статус сервисов:"
    docker-compose -f docker-compose.vps.yml ps
    echo ""
    echo "📝 Полезные команды:"
    echo "  Логи бота:      docker-compose -f docker-compose.vps.yml logs bot"
    echo "  Перезапуск:     docker-compose -f docker-compose.vps.yml restart"
    echo "  Остановка:      docker-compose -f docker-compose.vps.yml down"
    echo "  Обновление:     git pull && docker-compose -f docker-compose.vps.yml up -d --build"
    echo ""
    print_warning "🔧 Следующие шаги (SSL от Beget уже есть):"
    echo "  1. Настроить nginx конфигурацию:"
    echo "     sudo cp nginx-site.conf /etc/nginx/sites-available/seedance-bot"
    echo "     sudo nano /etc/nginx/sites-available/seedance-bot  # укажите пути к SSL"
    echo "     sudo ln -s /etc/nginx/sites-available/seedance-bot /etc/nginx/sites-enabled/"
    echo "     sudo nginx -t && sudo systemctl reload nginx"
    echo ""
    echo "  2. Настроить webhook в BotFather:"
    echo "     /setwebhook -> https://yourdomain.com/webhook"
    echo ""
    echo "  3. Проверить работу:"
    echo "     curl https://yourdomain.com/health"
    echo ""
    echo "  📖 Подробная инструкция: BEGET_SSL_SETUP.md"
else
    print_error "❌ Не все сервисы запустились корректно."
    echo "Проверьте логи: docker-compose -f docker-compose.vps.yml logs"
    exit 1
fi 