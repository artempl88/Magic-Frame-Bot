# Читаем файл
with open('services/utm_analytics.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Заменяем проблемную строку на более простую
content = content.replace(
    'func.sum(func.case([(UTMClick.is_first_visit == True, 1)], else_=0)).label(\'first_visits\')',
    'func.count(UTMClick.id).filter(UTMClick.is_first_visit == True).label(\'first_visits\')'
)

# Записываем исправленный файл
with open('services/utm_analytics.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Заменил func.case на func.count().filter() для first_visits")
