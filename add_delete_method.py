# Читаем файл
with open('services/utm_analytics.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Ищем конец класса UTMAnalyticsService (перед последней строкой "# Глобальный экземпляр сервиса")
insert_point = content.rfind("# Глобальный экземпляр сервиса")
if insert_point == -1:
    # Если не найдено, добавим в конец файла
    insert_point = len(content)

# Метод удаления с правильными отступами
delete_method = '''
    async def delete_utm_campaign(self, campaign_id: int, admin_id: int) -> bool:
        """Удаляет UTM кампанию и все связанные данные"""
        
        async with db.async_session() as session:
            # Проверяем существование кампании
            result = await session.execute(
                select(UTMCampaign).where(UTMCampaign.id == campaign_id)
            )
            campaign = result.scalar()
            
            if not campaign:
                return False
            
            try:
                # Удаляем связанные события
                await session.execute(
                    text("DELETE FROM utm_events WHERE campaign_id = :campaign_id"),
                    {"campaign_id": campaign_id}
                )
                
                # Удаляем связанные клики
                await session.execute(
                    text("DELETE FROM utm_clicks WHERE campaign_id = :campaign_id"),
                    {"campaign_id": campaign_id}
                )
                
                # Удаляем саму кампанию
                await session.execute(
                    text("DELETE FROM utm_campaigns WHERE id = :campaign_id"),
                    {"campaign_id": campaign_id}
                )
                
                await session.commit()
                
                logger.info(f"Admin {admin_id} deleted UTM campaign {campaign_id} ({campaign.name})")
                return True
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Error deleting UTM campaign {campaign_id}: {e}")
                return False

'''

# Вставляем метод перед комментарием
new_content = content[:insert_point] + delete_method + content[insert_point:]

# Записываем обновленный файл
with open('services/utm_analytics.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Метод delete_utm_campaign добавлен корректно")
