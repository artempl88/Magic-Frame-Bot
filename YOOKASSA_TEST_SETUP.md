# 🧪 Настройка тестовых данных ЮКассы

## ✅ Тестовые данные добавлены в код!

**Дата:** 2025-07-22 07:44  
**Тестовые креденшиалы:** `381764678:TEST:132257`

### 📋 Что было сделано:

1. **Добавлены тестовые данные в `core/config.py`:**
   ```python
   YOOKASSA_SHOP_ID = "381764678"      # Тестовый shop_id
   YOOKASSA_SECRET_KEY = "TEST:132257" # Тестовый secret_key  
   ENABLE_YOOKASSA = True              # Включена ЮКасса
   YOOKASSA_WEBHOOK_URL = "/yookassa/webhook"
   ```

2. **Обновлен пример конфигурации `vps-env-example.txt`:**
   ```env
   YOOKASSA_SHOP_ID=381764678
   YOOKASSA_SECRET_KEY=TEST:132257
   ENABLE_YOOKASSA=true
   YOOKASSA_WEBHOOK_URL=/yookassa/webhook
   ```

### 🚀 Как использовать:

#### Для локального тестирования:
```bash
# Тестовые данные уже активны в коде
# Просто запустите бота:
make -f Makefile.client up
```

#### Для создания собственного .env.client:
```bash
# Скопируйте пример и добавьте свои данные
cp vps-env-example.txt .env.client

# Отредактируйте .env.client:
# - Замените BOT_TOKEN на реальный
# - Добавьте свои ADMIN_IDS  
# - Для продакшена замените тестовые данные ЮКассы
```

### 🧪 Проверка работы ЮКассы:

1. **Запустите бота**
2. **Перейдите в админку:** `/admin`
3. **Управление ценами** → **Настройки ЮКассы**
4. **Должно показать:** ✅ работает

### 💳 Тестовые платежи:

Эти креденшиалы позволяют:
- ✅ Создавать тестовые платежи
- ✅ Тестировать webhook'и
- ✅ Проверять интеграцию
- ❌ НЕ принимают реальные деньги

### ⚠️ ВАЖНО для продакшена:

```env
# В .env.client для продакшена замените на реальные:
YOOKASSA_SHOP_ID=ваш_реальный_shop_id
YOOKASSA_SECRET_KEY=ваш_реальный_secret_key
ENABLE_YOOKASSA=true
ENVIRONMENT=production
```

### 🔧 Webhook настройки:

**URL для ЮКассы:** `https://ваш-домен.com/yookassa/webhook`

Настройте этот URL в личном кабинете ЮКассы для получения уведомлений о платежах.

---

**Готово!** ✅ Тестовые данные ЮКассы добавлены и готовы к использованию. 