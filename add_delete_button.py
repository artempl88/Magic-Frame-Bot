import re

# Читаем файл
with open('bot/handlers/utm_admin.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Ищем блок с кнопками в view_campaign и добавляем кнопку удаления
old_pattern = '''        builder.button(text="📥 Экспорт данных", callback_data=f"utm_export_{campaign_id}")
        builder.button(text="📋 Список кампаний", callback_data="utm_list_campaigns")
        builder.button(text="◀️ Меню UTM", callback_data="utm_analytics")
        builder.adjust(2, 1, 1)'''

new_pattern = '''        builder.button(text="📥 Экспорт данных", callback_data=f"utm_export_{campaign_id}")
        builder.button(text="🗑️ Удалить кампанию", callback_data=f"utm_delete_{campaign_id}")
        builder.button(text="📋 Список кампаний", callback_data="utm_list_campaigns")
        builder.button(text="◀️ Меню UTM", callback_data="utm_analytics")
        builder.adjust(2, 1, 1, 1)'''

content = content.replace(old_pattern, new_pattern)

# Записываем обновленный файл
with open('bot/handlers/utm_admin.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Кнопка удаления добавлена в view_campaign")
