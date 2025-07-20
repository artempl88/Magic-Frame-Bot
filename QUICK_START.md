# ⚡ Быстрый старт - за 5 минут

Максимально быстрое развертывание клиентского бота.

## 🎯 Что нужно заранее

1. **Токен бота** от @BotFather
2. **Ваш Telegram ID** от @userinfobot
3. **Docker** установлен на компьютере

## 🚀 Автоматическая установка

```bash
# 1. Запустите автонастройку
./setup-client.sh

# 2. Отредактируйте .env.client когда попросит
# Укажите:
# - BOT_TOKEN=ваш_токен_от_botfather
# - ADMIN_IDS=ваш_telegram_id

# 3. Нажмите Enter для продолжения
```

**Готово!** Бот запущен на http://localhost:8081

## 🛠️ Ручная установка

```bash
# 1. Создайте конфигурацию
cat > .env.client << 'EOF'
BOT_TOKEN=1234567890:AAAA-BBBB_CCCC_DDDD_EEEE_FFFF_GGGG_HHHH
BOT_USERNAME=YourBot
ADMIN_IDS=123456789
DB_PASSWORD=password123
REDIS_PASSWORD=redis123
WAVESPEED_API_KEY=your_api_key
DEBUG=true
LOG_LEVEL=DEBUG
EOF

# 2. Запустите бота
make -f Makefile.client quick-start

# 3. Проверьте статус
make -f Makefile.client status
```

## 📱 Проверка работы

1. Найдите бота в Telegram
2. Отправьте `/start`
3. Бот должен ответить!

## 🌐 Развертывание на сервере

```bash
# На VPS выполните:
make -f Makefile.client vps-up

# С автоматическими бэкапами:
make -f Makefile.client vps-up-backup

# Настройте Nginx:
# proxy_pass http://127.0.0.1:8081;

# Установите webhook:
curl -X POST "https://api.telegram.org/botТОКЕН/setWebhook" \
     -d "url=https://yourdomain.com/webhook"
```

## 💾 Бэкапы

```bash
# Создать бэкап прямо сейчас
make -f Makefile.client backup-auto

# Через админку бота: /admin → 💾 Бэкапы БД
# - Ручное создание с описанием
# - Просмотр списка
# - Статистика и управление

# Автоматические бэкапы каждый день в 3:00 UTC
```

## 🆘 Если что-то не работает

```bash
# Посмотрите логи
make -f Makefile.client logs

# Перезапустите
make -f Makefile.client restart

# Проверьте health
curl http://localhost:8081/health
```

## 📖 Подробная инструкция

Смотрите **DEPLOY_GUIDE.md** для полного руководства с пошаговыми инструкциями.

---

**🎉 Готово за 5 минут!** Ваш бот работает. 