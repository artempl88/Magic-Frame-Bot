# Читаем файл
with open('services/utm_analytics.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Найдем метод export_campaign_data
method_start = content.find('async def export_campaign_data(')
method_end = content.find('\n    async def', method_start + 1)
if method_end == -1:
    method_end = content.find('\n    def', method_start + 1)
if method_end == -1:
    method_end = content.find('\n# Глобальный экземпляр сервиса', method_start)

# Расширенная версия функции экспорта
new_export_method = '''    async def export_campaign_data(
        self,
        campaign_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        export_format: str = "detailed"
    ) -> List[Dict]:
        """Экспортирует данные кампании для CSV/Excel с расширенной аналитикой"""
        
        async with db.async_session() as session:
            # Получаем кампанию для метаданных
            campaign_result = await session.execute(
                select(UTMCampaign).where(UTMCampaign.id == campaign_id)
            )
            campaign = campaign_result.scalar()
            
            if not campaign:
                return []
            
            if export_format == "summary":
                # Краткий экспорт - только аналитика по кампании
                analytics = await self.get_campaign_analytics(campaign_id, start_date, end_date)
                
                summary_data = [{
                    'campaign_id': campaign_id,
                    'campaign_name': analytics['campaign']['name'],
                    'utm_source': analytics['campaign']['utm_source'],
                    'utm_medium': analytics['campaign']['utm_medium'],
                    'utm_campaign': analytics['campaign']['utm_campaign'],
                    'utm_content': analytics['campaign']['utm_content'] or '',
                    'total_clicks': analytics['clicks']['total_clicks'],
                    'unique_users': analytics['clicks']['unique_users'],
                    'first_visits': analytics['clicks']['first_visits'],
                    'registered_users_clicks': analytics['clicks']['registered_users_clicks'],
                    'new_users_clicks': analytics['clicks']['new_users_clicks'],
                    'registrations': analytics['events'].get('registration', {}).get('count', 0),
                    'purchases': analytics['events'].get('purchase', {}).get('count', 0),
                    'generations': analytics['events'].get('generation', {}).get('count', 0),
                    'total_revenue': analytics['revenue']['total'],
                    'revenue_per_click': analytics['revenue']['per_click'],
                    'revenue_per_user': analytics['revenue']['per_user'],
                    'click_to_registration_rate': analytics['conversions']['click_to_registration'],
                    'click_to_purchase_rate': analytics['conversions']['click_to_purchase'],
                    'registration_to_purchase_rate': analytics['conversions']['registration_to_purchase'],
                    'avg_time_to_convert_minutes': analytics['events'].get('purchase', {}).get('avg_time_to_convert_minutes', 0),
                    'created_at': analytics['campaign']['created_at'],
                    'is_active': analytics['campaign']['is_active'],
                    'export_date': datetime.utcnow().isoformat()
                }]
                
                return summary_data
            
            # Детальный экспорт - все клики и события
            query = """
            SELECT 
                c.id as click_id,
                c.clicked_at,
                c.telegram_id,
                c.is_first_visit,
                c.is_registered_user,
                c.user_agent,
                c.ip_address,
                c.referrer,
                u.username,
                u.first_name,
                u.last_name,
                u.language_code,
                u.is_premium,
                u.credits_balance,
                u.created_at as user_registration_date,
                e.id as event_id,
                e.event_type,
                e.event_at,
                e.revenue,
                e.credits_spent,
                e.credits_purchased,
                e.time_from_click,
                CASE 
                    WHEN e.time_from_click IS NOT NULL THEN 
                        ROUND(e.time_from_click / 60.0, 2)
                    ELSE NULL 
                END as time_from_click_minutes,
                CASE 
                    WHEN e.time_from_click IS NOT NULL THEN 
                        ROUND(e.time_from_click / 3600.0, 2) 
                    ELSE NULL 
                END as time_from_click_hours,
                EXTRACT(hour FROM c.clicked_at) as click_hour,
                EXTRACT(dow FROM c.clicked_at) as click_day_of_week,
                DATE(c.clicked_at) as click_date
            FROM utm_clicks c
            LEFT JOIN users u ON c.user_id = u.id
            LEFT JOIN utm_events e ON c.id = e.click_id
            WHERE c.campaign_id = :campaign_id
            """
            
            params = {'campaign_id': campaign_id}
            
            if start_date:
                query += " AND c.clicked_at >= :start_date"
                params['start_date'] = start_date
            
            if end_date:
                query += " AND c.clicked_at <= :end_date"
                params['end_date'] = end_date
            
            query += " ORDER BY c.clicked_at DESC, e.event_at ASC"
            
            result = await session.execute(text(query), params)
            
            data = []
            for row in result:
                # Конвертируем день недели в текст
                days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
                day_name = days[int(row.click_day_of_week)] if row.click_day_of_week is not None else ''
                
                data.append({
                    'campaign_id': campaign_id,
                    'campaign_name': campaign.name,
                    'utm_source': campaign.utm_source,
                    'utm_medium': campaign.utm_medium,
                    'utm_campaign': campaign.utm_campaign,
                    'utm_content': campaign.utm_content or '',
                    'click_id': row.click_id,
                    'clicked_at': row.clicked_at.isoformat() if row.clicked_at else '',
                    'click_date': row.click_date.isoformat() if row.click_date else '',
                    'click_hour': int(row.click_hour) if row.click_hour is not None else '',
                    'click_day_of_week': day_name,
                    'telegram_id': row.telegram_id,
                    'username': row.username or '',
                    'first_name': row.first_name or '',
                    'last_name': row.last_name or '',
                    'language_code': row.language_code or '',
                    'is_first_visit': row.is_first_visit,
                    'is_registered_user': row.is_registered_user,
                    'is_premium': row.is_premium or False,
                    'user_credits_balance': row.credits_balance or 0,
                    'user_registration_date': row.user_registration_date.isoformat() if row.user_registration_date else '',
                    'user_agent': row.user_agent or '',
                    'ip_address': row.ip_address or '',
                    'referrer': row.referrer or '',
                    'event_id': row.event_id or '',
                    'event_type': row.event_type or '',
                    'event_at': row.event_at.isoformat() if row.event_at else '',
                    'revenue': float(row.revenue) if row.revenue else 0.0,
                    'credits_spent': row.credits_spent or 0,
                    'credits_purchased': row.credits_purchased or 0,
                    'time_from_click_seconds': row.time_from_click or 0,
                    'time_from_click_minutes': float(row.time_from_click_minutes) if row.time_from_click_minutes else 0.0,
                    'time_from_click_hours': float(row.time_from_click_hours) if row.time_from_click_hours else 0.0,
                    'has_converted': 'Yes' if row.event_type else 'No',
                    'conversion_type': row.event_type or 'No conversion',
                    'export_timestamp': datetime.utcnow().isoformat()
                })
            
            return data'''

# Заменяем старый метод на новый
if method_end != -1:
    content = content[:method_start] + new_export_method + content[method_end:]
else:
    content = content[:method_start] + new_export_method + '\n\n'

# Записываем обновленный файл
with open('services/utm_analytics.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Улучшена функция экспорта UTM данных с расширенными полями")
