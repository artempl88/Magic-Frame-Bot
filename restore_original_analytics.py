# Читаем файл
with open('services/utm_analytics.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Найдем метод get_campaign_analytics и заменим на оригинальную версию
method_start = content.find('async def get_campaign_analytics(')
method_end = content.find('\n    async def', method_start + 1)
if method_end == -1:
    method_end = content.find('\n    def', method_start + 1)
if method_end == -1:
    method_end = content.find('\n# Глобальный экземпляр сервиса', method_start)

# Оригинальная версия метода, которая работает
original_method = '''    async def get_campaign_analytics(
        self,
        campaign_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """Получает аналитику по конкретной кампании"""
        
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
            
            # Статистика по кликам
            clicks_result = await session.execute(
                select(
                    func.count(UTMClick.id).label('total_clicks'),
                    func.count(func.distinct(UTMClick.telegram_id)).label('unique_users'),
                    func.count(UTMClick.id).filter(UTMClick.is_first_visit == True).label('first_visits')
                ).where(and_(*click_filters))
            )
            click_stats = clicks_result.first()
            
            # Статистика по событиям
            events_result = await session.execute(
                select(
                    UTMEvent.event_type,
                    func.count(UTMEvent.id).label('count'),
                    func.sum(UTMEvent.revenue).label('total_revenue'),
                    func.sum(UTMEvent.credits_spent).label('total_credits_spent'),
                    func.sum(UTMEvent.credits_purchased).label('total_credits_purchased')
                ).where(and_(*event_filters))
                .group_by(UTMEvent.event_type)
            )
            
            events_stats = {}
            for row in events_result:
                events_stats[row.event_type] = {
                    'count': row.count,
                    'total_revenue': float(row.total_revenue) if row.total_revenue else 0.0,
                    'total_credits_spent': row.total_credits_spent or 0,
                    'total_credits_purchased': row.total_credits_purchased or 0
                }
            
            # Конверсии
            registrations = events_stats.get('registration', {}).get('count', 0)
            purchases = events_stats.get('purchase', {}).get('count', 0)
            
            conversion_registration = (registrations / click_stats.total_clicks * 100) if click_stats.total_clicks > 0 else 0
            conversion_purchase = (purchases / registrations * 100) if registrations > 0 else 0
            
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
                }
            }'''

# Заменяем метод
if method_end != -1:
    content = content[:method_start] + original_method + content[method_end:]
else:
    content = content[:method_start] + original_method + '\n\n'

# Записываем обновленный файл
with open('services/utm_analytics.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Восстановлена совместимая версия метода аналитики")
