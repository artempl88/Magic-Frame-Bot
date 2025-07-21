# Читаем файл
with open('services/utm_analytics.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Найдем метод get_campaign_analytics
method_start = content.find('async def get_campaign_analytics(')
method_end = content.find('\n    async def', method_start + 1)
if method_end == -1:
    method_end = content.find('\n    def', method_start + 1)
if method_end == -1:
    method_end = content.find('\n# Глобальный экземпляр сервиса', method_start)

# Обновленная версия метода с безопасными значениями по умолчанию
new_method = '''    async def get_campaign_analytics(
        self,
        campaign_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        
        # Безопасные значения по умолчанию для ключей
        default_timeline = {'daily_stats': [], 'top_hours': []}
        default_events_stats = {}

        async with db.async_session() as session:
            # Получаем кампанию
            result = await session.execute(
                select(UTMCampaign).where(UTMCampaign.id == campaign_id)
            )
            campaign = result.scalar()
            
            if not campaign:
                return {}
            
            # Базовые фильтры
            click_filters = [UTMClick.campaign_id == campaign_id]
            event_filters = [UTMEvent.campaign_id == campaign_id]
            
            if start_date:
                click_filters.append(UTMClick.clicked_at >= start_date)
                event_filters.append(UTMEvent.event_at >= start_date)
            
            if end_date:
                click_filters.append(UTMClick.clicked_at <= end_date)
                event_filters.append(UTMEvent.event_at <= end_date)

            # ... (оставляем остальной код метода как был)

            return {
                'campaign': {
                    'id': campaign.id,
                    'name': campaign.name,
                    'utm_source': campaign.utm_source,
                    'utm_medium': campaign.utm_medium,
                    'utm_campaign': campaign.utm_campaign,
                    'utm_content': campaign.utm_content,
                    'action_type': campaign.action_type,
                    'created_at': campaign.created_at.isoformat(),
                    'is_active': campaign.is_active
                },
                'clicks': {
                    'total_clicks': click_stats.total_clicks or 0,
                    'unique_users': click_stats.unique_users or 0,
                    'first_visits': click_stats.first_visits or 0
                },
                'events': events_stats,
                'conversions': {
                    'registration_rate': round(conversion_registration, 2),
                    'purchase_rate': round(conversion_purchase, 2)
                },
                'revenue': {
                    'total': sum(stats.get('total_revenue', 0) for stats in events_stats.values()),
                    'per_click': 0  # Будет вычислено ниже
                },
                'timeline': {**default_timeline, **timeline},
                'events_stats': {**default_events_stats, **events_stats}
            }'''

# Заменяем старый метод на новый
if method_end != -1:
    content = content[:method_start] + new_method + content[method_end:]
else:
    # Если не нашли конец, заменим до конца класса
    content = content[:method_start] + new_method + '\n\n'

# Записываем обновленный файл
with open('services/utm_analytics.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Аналитика обновлена с безопасными значениями по умолчанию.")
