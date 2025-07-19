# 🚀 Настройка на поддомене bot.seedancebot.com

Отличное решение использовать отдельный поддомен для бота! Это профессиональный подход.

## 🎯 **Преимущества поддомена:**

- ✅ **Разделение сервисов** - основной сайт на seedancebot.com, бот на bot.seedancebot.com
- ✅ **Безопасность** - изоляция бота от основного сайта
- ✅ **Простота настройки** - нет конфликтов с существующими конфигурациями
- ✅ **Профессиональный вид** - четкое разделение функций

## ⚡ **Быстрая настройка (3 минуты):**

### **1. Проверьте SSL для поддомена:**
```bash
# Проверьте, покрывает ли SSL сертификат поддомен
curl -I https://bot.seedancebot.com

# Если нужен отдельный сертификат для поддомена:
sudo certbot --nginx -d bot.seedancebot.com
```

### **2. Настройте nginx для поддомена:**
```bash
# Используйте специальную конфигурацию для поддомена
sudo cp nginx-bot-subdomain.conf /etc/nginx/sites-available/bot-seedancebot

# Отредактируйте пути к SSL сертификатам
sudo nano /etc/nginx/sites-available/bot-seedancebot
# Укажите правильные пути к вашим SSL сертификатам

# Обновите путь к статическим файлам
# Замените: alias /path/to/seedance/static/;
# На:       alias /полный/путь/к/вашему/проекту/static/;

# Активируйте конфигурацию
sudo ln -s /etc/nginx/sites-available/bot-seedancebot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### **3. Настройте .env файл:**
```bash
cd /path/to/seedance
cp vps-env-example.txt .env
nano .env
```

**Ключевые настройки:**
```env
BOT_TOKEN=ваш_токен_от_botfather
WEBHOOK_HOST=https://bot.seedancebot.com    # ← уже настроено в примере!
DB_PASSWORD=надежный_пароль_бд
REDIS_PASSWORD=надежный_пароль_redis
SECRET_KEY=очень_длинный_секретный_ключ_минимум_32_символа
ADMIN_IDS=ваш_telegram_id
WAVESPEED_API_KEY=ваш_api_ключ
```

### **4. Запустите бота:**
```bash
chmod +x deploy-vps.sh
./deploy-vps.sh
```

### **5. Настройте webhook в Telegram:**
```bash
curl -X POST "https://api.telegram.org/botВАШ_ТОКЕН/setWebhook" \
     -d "url=https://bot.seedancebot.com/webhook"
```

## ✅ **Проверка работы:**

### **Доступность сервисов:**
```bash
# Основной сайт
curl -I https://seedancebot.com

# Поддомен бота
curl -I https://bot.seedancebot.com

# Health check бота
curl https://bot.seedancebot.com/health

# Webhook info
curl "https://api.telegram.org/botВАШ_ТОКЕН/getWebhookInfo"
```

### **Статус контейнеров:**
```bash
docker-compose -f docker-compose.vps.yml ps
```

## 🌐 **Архитектура с поддоменом:**

```
seedancebot.com (основной сайт)
      ↓
nginx (системный)
      ↓
bot.seedancebot.com → Docker бот:8080
                           ↓
                    PostgreSQL + Redis + Celery
```

## 📝 **URL структура:**

| Сервис | URL |
|--------|-----|
| **Основной сайт** | https://seedancebot.com |
| **Telegram webhook** | https://bot.seedancebot.com/webhook |
| **Health check** | https://bot.seedancebot.com/health |
| **API** | https://bot.seedancebot.com/api/ |
| **Статические файлы** | https://bot.seedancebot.com/static/ |

## 🔧 **SSL сертификаты:**

### **Вариант 1: Wildcard сертификат (*.seedancebot.com)**
```nginx
ssl_certificate /etc/ssl/certs/seedancebot.com.crt;
ssl_certificate_key /etc/ssl/private/seedancebot.com.key;
```

### **Вариант 2: Отдельный сертификат для поддомена**
```nginx
ssl_certificate /etc/ssl/certs/bot.seedancebot.com.crt;
ssl_certificate_key /etc/ssl/private/bot.seedancebot.com.key;
```

### **Вариант 3: Let's Encrypt для поддомена**
```bash
sudo certbot --nginx -d bot.seedancebot.com
```

## 🚨 **Устранение неполадок:**

### **Поддомен не резолвится:**
```bash
# Проверьте DNS запись
nslookup bot.seedancebot.com
dig bot.seedancebot.com

# Должна быть A-запись, указывающая на IP вашего VPS
```

### **SSL ошибка для поддомена:**
```bash
# Проверьте, покрывает ли сертификат поддомен
openssl s_client -connect bot.seedancebot.com:443 -servername bot.seedancebot.com

# Получите отдельный сертификат если нужно
sudo certbot --nginx -d bot.seedancebot.com
```

### **502 Bad Gateway:**
```bash
# Проверьте, запущен ли бот
docker-compose -f docker-compose.vps.yml ps

# Проверьте доступность бота изнутри
curl http://127.0.0.1:8080/health

# Проверьте логи nginx
sudo tail -f /var/log/nginx/bot_seedancebot_error.log
```

## 🎉 **Готово!**

Ваш бот теперь работает на профессиональном поддомене bot.seedancebot.com!

**Ссылки для проверки:**
- Основной сайт: https://seedancebot.com  
- Telegram бот: https://t.me/SeedanceOfficialBot
- Webhook: https://bot.seedancebot.com/webhook
- Health check: https://bot.seedancebot.com/health 