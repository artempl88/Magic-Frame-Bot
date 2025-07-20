# 🔄 Webhook временно настроен на старый домен

## ✅ Обновлено:

### 🌐 **Webhook URLs (временно на seedancebot.com):**
- **Основной webhook:** `https://bot.seedancebot.com/magicframe`
- **ЮКасса webhook:** `https://bot.seedancebot.com/yookassa/webhook`
- **Health check:** `https://bot.seedancebot.com/magicframe/health`

### 📄 **Обновленные файлы:**
- ✅ `docker-compose.yml` - порт 8081 для seedancebot.com
- ✅ `.env.client` - webhook URLs на старом домене
- ✅ `Makefile` - команды health и info используют старый URL
- ✅ `README.md` - указано временное использование

## ⚠️ **Важно:**

### **Контейнеры остались переименованными:**
- 🐳 `magic_frame_bot` (не изменилось)
- 🐳 `magic_frame_postgres` (не изменилось)
- 🐳 `magic_frame_redis` (не изменилось)
- 💾 База данных: `magic_frame_bot` (не изменилось)
- 🎨 Брендинг: **Magic Frame** (не изменилось)

### **Webhook настроен временно:**
```bash
# Webhook Configuration (VPS Production - ВРЕМЕННО на старом домене)
WEBHOOK_HOST=https://bot.seedancebot.com
WEBHOOK_PATH=/magicframe
WEBHOOK_PORT=8081
```

## 🚀 **Готово к запуску:**

### **Команды работают как обычно:**
```bash
make up-backup  # Запуск с автобэкапами
make logs       # Мониторинг
make health     # Проверка webhook (на seedancebot.com/magicframe)
```

### **Проверка работы:**
- 🌐 **Webhook:** https://bot.seedancebot.com/magicframe/health
- 💳 **ЮКасса:** https://bot.seedancebot.com/yookassa/webhook
- 📊 **Статус:** `make health` для проверки

## 🔮 **В будущем (когда настроите новый домен):**

1. **Изменить в `.env.client`:**
   ```bash
   WEBHOOK_HOST=https://bot.magicframebot.com
   ```

2. **Обновить все команды Makefile**
3. **Обновить README.md**
4. **Настроить DNS для magicframebot.com**

## 🎯 **Текущий статус:**

**Magic Frame Bot готов к деплою на VPS:**
- 🪄 **Брендинг:** Magic Frame (обновлен)
- 🐳 **Контейнеры:** magic_frame_* (переименованы)
- 🌐 **Webhook:** seedancebot.com (временно)
- 💾 **БД:** magic_frame_bot (переименована)
- 💳 **Платежи:** Telegram Stars + ЮКасса готовы

---

**✅ Magic Frame Bot с временным webhook готов!** 