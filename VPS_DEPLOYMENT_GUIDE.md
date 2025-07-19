# 🚀 Руководство по развертыванию Seedance Bot на VPS

Это руководство поможет вам развернуть Seedance Bot на вашем VPS сервере.

## 📋 Требования

### Минимальные системные требования:
- **CPU**: 2 ядра
- **RAM**: 4 GB
- **Диск**: 20 GB свободного места
- **ОС**: Ubuntu 20.04 LTS или новее / CentOS 8 / Debian 11
- **Сеть**: Статический IP адрес, домен (для webhook)

### Необходимое ПО:
- Docker 20.10+
- Docker Compose 2.0+
- Git
- Nginx (или будет установлен в контейнере)
- Certbot (для SSL сертификатов)

## 🔧 Подготовка сервера

### 1. Обновление системы
```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Установка Docker
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

### 3. Установка Docker Compose
```bash
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 4. Настройка файрвола
```bash
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

## 🌐 Настройка домена и SSL

### 1. Настройка DNS
Добавьте A-запись для вашего домена, указывающую на IP вашего VPS:
```
yourdomain.com -> YOUR_VPS_IP
```

### 2. Получение SSL сертификата
```bash
sudo apt install certbot
sudo certbot certonly --standalone -d yourdomain.com
```

## 📦 Развертывание бота

### 1. Клонирование репозитория
```bash
git clone <repository-url>
cd Seedance
```

### 2. Настройка переменных окружения
```bash
# Копируем пример конфигурации
cp vps-env-example.txt .env

# Редактируем конфигурацию
nano .env
```

#### Обязательные настройки в .env:
```bash
# Telegram
BOT_TOKEN=your_bot_token_from_botfather
WEBHOOK_HOST=https://yourdomain.com

# Безопасность  
DB_PASSWORD=very_strong_database_password
REDIS_PASSWORD=very_strong_redis_password
SECRET_KEY=very_long_secret_key_at_least_32_characters

# Администраторы
ADMIN_IDS=123456789,987654321  # Ваши Telegram ID

# API
WAVESPEED_API_KEY=your_wavespeed_api_key
```

### 3. Автоматическое развертывание
```bash
chmod +x deploy-vps.sh
./deploy-vps.sh
```

### 4. Ручное развертывание (альтернатива)
```bash
# Создание директорий
mkdir -p logs static backups

# Сборка и запуск
docker-compose -f docker-compose.vps.yml up -d --build

# Применение миграций
docker-compose -f docker-compose.vps.yml exec bot python migrations/apply_migrations.py
```

## ⚙️ Настройка Telegram webhook

### 1. Через BotFather
Отправьте команду в чат с @BotFather:
```
/setwebhook
URL: https://yourdomain.com/webhook
```

### 2. Через API (альтернатива)
```bash
curl -X POST \
  "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://yourdomain.com/webhook"
```

### 3. Проверка webhook
```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```

## 📊 Мониторинг и управление

### Основные команды
```bash
# Статус сервисов
docker-compose -f docker-compose.vps.yml ps

# Логи
docker-compose -f docker-compose.vps.yml logs bot
docker-compose -f docker-compose.vps.yml logs postgres

# Перезапуск
docker-compose -f docker-compose.vps.yml restart bot

# Остановка
docker-compose -f docker-compose.vps.yml down

# Обновление
git pull
docker-compose -f docker-compose.vps.yml up -d --build
```

### Проверка здоровья
```bash
# Health check бота
curl http://localhost:8080/health

# Проверка webhook
curl https://yourdomain.com/webhook
```

## 🔒 Безопасность

### Рекомендации:
1. **Измените пароли по умолчанию** в .env файле
2. **Ограничьте доступ к портам** - только 80, 443, SSH
3. **Регулярно обновляйте систему** и Docker образы
4. **Настройте автоматические резервные копии**
5. **Используйте сильные пароли** (минимум 16 символов)

### Дополнительная защита:
```bash
# Отключение root логина
sudo sed -i 's/#PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl reload sshd

# Установка fail2ban
sudo apt install fail2ban
sudo systemctl enable fail2ban
```

## 📈 Мониторинг

### Логи
- Логи бота: `./logs/`
- Логи nginx: внутри контейнера nginx
- Системные логи: `journalctl -u seedance-bot.service`

### Метрики системы
```bash
# Использование ресурсов
docker stats

# Место на диске
df -h

# Загрузка системы
htop
```

## 🔄 Резервное копирование

### Автоматическое (настроено в docker-compose.vps.yml)
- Резервная копия PostgreSQL создается каждый день в 3:00
- Файлы сохраняются в `./backups/`
- Хранятся 7 дней

### Ручное создание резервной копии
```bash
# База данных
docker-compose -f docker-compose.vps.yml exec postgres pg_dump -U seedance seedance_bot > backup_$(date +%Y%m%d).sql

# Статические файлы
tar -czf static_backup_$(date +%Y%m%d).tar.gz static/
```

## 🛠️ Устранение неполадок

### Частые проблемы:

#### 1. Контейнеры не запускаются
```bash
# Проверить логи
docker-compose -f docker-compose.vps.yml logs

# Проверить свободное место
df -h

# Перезапустить Docker
sudo systemctl restart docker
```

#### 2. Webhook не работает
```bash
# Проверить SSL сертификат
curl -I https://yourdomain.com

# Проверить nginx логи
docker-compose -f docker-compose.vps.yml logs nginx

# Проверить настройки webhook в Telegram
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```

#### 3. База данных недоступна
```bash
# Проверить статус PostgreSQL
docker-compose -f docker-compose.vps.yml exec postgres pg_isready

# Проверить логи БД
docker-compose -f docker-compose.vps.yml logs postgres
```

#### 4. Проблемы с генерацией видео
```bash
# Проверить статус Celery worker
docker-compose -f docker-compose.vps.yml logs celery_worker

# Проверить очередь задач
docker-compose -f docker-compose.vps.yml exec redis redis-cli -a $REDIS_PASSWORD
> LLEN celery
```

### Перезапуск после сбоя
```bash
# Полная пересборка
docker-compose -f docker-compose.vps.yml down
docker system prune -af
docker-compose -f docker-compose.vps.yml up -d --build
```

## 📞 Поддержка

При возникновении проблем:

1. Проверьте логи: `docker-compose -f docker-compose.vps.yml logs`
2. Убедитесь, что все переменные в .env настроены корректно
3. Проверьте доступность домена и SSL сертификата
4. Убедитесь, что webhook настроен в Telegram

## 🔄 Обновление

### Обновление кода
```bash
git pull
docker-compose -f docker-compose.vps.yml up -d --build
```

### Обновление Docker образов
```bash
docker-compose -f docker-compose.vps.yml pull
docker-compose -f docker-compose.vps.yml up -d
```

### Применение миграций
```bash
docker-compose -f docker-compose.vps.yml exec bot python migrations/apply_migrations.py
```

---

**Примечание**: Замените `yourdomain.com` на ваш реальный домен во всех конфигурационных файлах. 