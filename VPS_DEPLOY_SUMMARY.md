# 🪄 Magic Frame Bot - VPS Конфигурация готова!

Все настроено для развертывания на VPS с webhook: **https://bot.magicframebot.com/kwork**

## ✅ Что настроено:

### 🌐 **Webhook конфигурация:**
- **Основной webhook:** `https://bot.magicframebot.com/kwork`
- **ЮКасса webhook:** `https://bot.magicframebot.com/yookassa/webhook`
- **Health check:** `https://bot.magicframebot.com/kwork/health`
- **Порт:** `8081` (открыт для внешнего доступа)

### 📄 **Файлы конфигурации:**
- ✅ `.env.client` - VPS настройки с webhook URL
- ✅ `docker-compose.yml` - основной compose файл  
- ✅ `Makefile` - упрощенные команды для VPS
- ✅ `README.md` - обновлена для VPS

### 🗑️ **Удалено лишнее:**
- ❌ `docker-compose.simple.yml` (локальная конфигурация)
- ❌ Все nginx/grafana конфигурации
- ❌ Дублирующие Makefile файлы

## 🎯 **Основные команды:**

```bash
# Развертывание на VPS
make up         # Базовый запуск
make up-backup  # С автоматическими бэкапами
make up-full    # С Celery Worker

# Мониторинг
make logs       # Логи
make ps         # Статус
make health     # Проверка (включая webhook)

# Управление
make down       # Остановка
make restart    # Перезапуск
```

## 💳 **Платежная система:**

### **Telegram Stars (готово):**
- ✅ Полностью настроено и работает
- ✅ Админка для управления ценами

### **ЮКасса (требует настройки):**
- 📝 Добавить в `.env.client`:
  ```bash
  YOOKASSA_SHOP_ID=ваш_shop_id
  YOOKASSA_SECRET_KEY=ваш_secret_key
  ENABLE_YOOKASSA=true
  ```
- 📝 Настроить webhook в ЮКассе: `https://bot.magicframebot.com/yookassa/webhook`

## 🎛️ **Админ-панель:**

- **Вход:** `/admin` в боте
- **Управление ценами:** Stars и рубли
- **Настройки ЮКассы:** проверка статуса
- **Бэкапы:** ручное управление
- **Статистика:** доходы и аналитика

## 🔧 **Развертывание на VPS:**

### **1. Подготовка сервера:**
```bash
# Установить Docker и Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Клонировать репозиторий  
git clone <repo-url>
cd MagicFrameBot
```

### **2. Настройка:**
```bash
# Настроить webhook (уже настроено)
# При необходимости добавить ЮКассу в .env.client

# Установить зависимости (если нужно)
pip install yookassa==3.0.0
```

### **3. Запуск:**
```bash
# Запуск с автобэкапами (рекомендуется)
make up-backup

# Проверка
make health
make logs
```

## 🌐 **Настройка веб-сервера (nginx):**

### **На сервере настроить reverse proxy:**
```nginx
server {
    listen 80;
    server_name bot.magicframebot.com;
    
    location /kwork {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    location /yookassa/webhook {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### **SSL сертификат:**
```bash
# Установить Certbot
certbot --nginx -d bot.magicframebot.com
```

## 📊 **Мониторинг:**

### **Проверка работы:**
- 🌐 **Webhook:** https://bot.magicframebot.com/kwork/health
- 💳 **ЮКасса:** https://bot.magicframebot.com/yookassa/webhook
- 🤖 **Telegram:** отправить `/start` боту

### **Логи и статус:**
```bash
# Логи в реальном времени
make logs

# Статус всех сервисов
make ps

# Использование ресурсов
make stats
```

## 🔒 **Безопасность:**

- ✅ Webhook на HTTPS
- ✅ Закрытые порты БД и Redis
- ✅ Сильные пароли в .env.client
- ✅ Firewall настройки
- ✅ Автоматические бэкапы

## 🎉 **Готово к продакшену!**

**Ваш Magic Frame Bot полностью настроен для VPS:**

- 🚀 **Готов к деплою** на https://bot.magicframebot.com/kwork
- 💳 **Двойная платежная система** (Stars + ЮКасса)
- 🎛️ **Админ-панель** для управления
- 💾 **Автоматические бэкапы** для защиты данных
- 📊 **Полный мониторинг** и логирование

### **Следующие шаги:**
1. Развернуть на VPS
2. Настроить nginx reverse proxy
3. Установить SSL сертификат
4. Настроить ЮКассу (опционально)
5. Начать зарабатывать! 💰 