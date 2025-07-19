import asyncio
import logging
from celery import Celery, Task
from celery.utils.log import get_task_logger
from datetime import datetime, timedelta
import aiohttp
from typing import Dict, Any

from core.config import settings
from core.constants import GenerationStatus
from services.database import db
from services.wavespeed_api import get_wavespeed_api, GenerationRequest
from services.api_monitor import api_monitor
from models.models import User, Generation, Transaction, Statistics

# Настройка Celery
app = Celery('seedance_bot')

# Конфигурация Celery
app.conf.update(
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 минут максимум на задачу
    task_soft_time_limit=240,  # Мягкий лимит 4 минуты
)

# Логгер для задач
logger = get_task_logger(__name__)

# Базовый класс для асинхронных задач
class AsyncTask(Task):
    """Базовый класс для асинхронных Celery задач"""
    
    def run(self, *args, **kwargs):
        """Запуск асинхронной задачи в event loop"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.async_run(*args, **kwargs))
        finally:
            loop.close()
    
    async def async_run(self, *args, **kwargs):
        """Асинхронная логика задачи (переопределить в наследниках)"""
        raise NotImplementedError

@app.task(bind=True, base=AsyncTask, max_retries=3, default_retry_delay=60)
class GenerateVideoTask(AsyncTask):
    """Задача генерации видео"""
    
    async def async_run(self, generation_id: int, generation_data: dict):
        """Асинхронная генерация видео"""
        logger.info(f"Starting video generation for ID: {generation_id}")
        
        # Проверяем баланс API перед началом генерации
        try:
            from aiogram import Bot
            bot = Bot(token=settings.BOT_TOKEN)
            balance_check = await api_monitor.check_and_notify(bot)
            
            if not api_monitor.is_service_available(balance_check.get('balance')):
                logger.error(f"Generation {generation_id} cancelled: API service unavailable")
                
                # Обновляем статус на "ошибка"
                await db.update_generation_status(
                    generation_id,
                    GenerationStatus.FAILED,
                    error_message="API service temporarily unavailable"
                )
                
                # Возвращаем кредиты пользователю
                generation = await db.get_generation(generation_id)
                if generation:
                    await db.update_user_balance(generation.user_id, generation.cost)
                    
                    # Отменяем лимит генерации
                    user = await db.get_user_by_id(generation.user_id)
                    if user:
                        from bot.middlewares.throttling import GenerationThrottling
                        GenerationThrottling.cancel_generation_limit(user.telegram_id)
                
                return {
                    'success': False,
                    'generation_id': generation_id,
                    'error': 'API service temporarily unavailable'
                }
        except Exception as e:
            logger.error(f"Error checking API balance before generation: {e}")
        
        api = get_wavespeed_api()
        
        try:
            # Обновляем статус на "обработка"
            await db.update_generation_status(
                generation_id,
                GenerationStatus.PROCESSING,
                task_id=self.request.id
            )
            
            # Подготавливаем запрос
            request = GenerationRequest(
                model=generation_data['model'],
                prompt=generation_data['prompt'],
                duration=generation_data['duration'],
                aspect_ratio=generation_data.get('aspect_ratio', '16:9'),
                image=generation_data.get('image'),
                seed=generation_data.get('seed', -1)
            )
            
            # Callback для обновления прогресса
            async def progress_callback(progress: int, status: str):
                await db.update_generation_progress(
                    generation_id,
                    progress=progress,
                    status=status
                )
            
            # Генерируем видео
            result = await api.generate_video(request, progress_callback)
            
            # Сохраняем результат
            await db.update_generation_status(
                generation_id,
                GenerationStatus.COMPLETED,
                video_url=result.video_url,
                generation_time=result.generation_time
            )
            
            # Проверяем баланс API после завершения генерации
            try:
                from aiogram import Bot
                bot = Bot(token=settings.BOT_TOKEN)
                await api_monitor.check_and_notify(bot)
            except Exception as e:
                logger.error(f"Error checking API balance after generation: {e}")
            
            # Отправляем уведомление пользователю
            await send_generation_notification(
                generation_id,
                'completed',
                video_url=result.video_url
            )
            
            logger.info(f"Video generation completed for ID: {generation_id}")
            return {
                'success': True,
                'generation_id': generation_id,
                'video_url': result.video_url,
                'generation_time': result.generation_time
            }
            
        except asyncio.CancelledError:
            logger.warning(f"Video generation cancelled for ID: {generation_id}")
            raise
        except Exception as e:
            logger.error(f"Video generation failed for ID {generation_id}: {str(e)}")
            
            # Обновляем статус на "ошибка"
            await db.update_generation_status(
                generation_id,
                GenerationStatus.FAILED,
                error_message=str(e)
            )
            
            # Возвращаем кредиты пользователю и отменяем лимит
            generation = await db.get_generation(generation_id)
            if generation:
                await db.update_user_balance(generation.user_id, generation.cost)
                
                # Отменяем лимит генерации при неудачной попытке
                user = await db.get_user_by_id(generation.user_id)
                if user:
                    from bot.middlewares.throttling import GenerationThrottling
                    GenerationThrottling.cancel_generation_limit(user.telegram_id)
                
                # Отправляем уведомление об ошибке
                await send_generation_notification(
                    generation_id,
                    'failed',
                    error=str(e)
                )
            
            # Повторная попытка только для временных ошибок (НЕ для модерации)
            error_str = str(e).lower()
            if (any(word in error_str for word in ['timeout', 'network', 'connection', 'temporarily']) and 
                not any(word in error_str for word in ['flagged', 'sensitive', 'content', 'moderation', 'inappropriate'])):
                logger.info(f"Retrying generation {generation_id} due to temporary error: {str(e)}")
                raise self.retry(exc=e, countdown=60, max_retries=2)
            
            return {
                'success': False,
                'generation_id': generation_id,
                'error': str(e)
            }

@app.task
async def send_generation_notification(generation_id: int, status: str, **kwargs):
    """Отправка уведомления о статусе генерации"""
    from aiogram import Bot
    
    generation = await db.get_generation(generation_id)
    
    if not generation:
        logger.error(f"Generation {generation_id} not found for notification")
        return
    
    # Получаем пользователя
    user = await db.get_user_by_internal_id(generation.user_id)
    
    if not user:
        logger.error(f"User {generation.user_id} not found for notification")
        return
    
    # Создаем бота для отправки уведомления
    bot = Bot(token=settings.BOT_TOKEN)
    
    try:
        # Получаем функцию перевода
        from bot.middlewares.i18n import i18n
        _ = lambda key, **kw: i18n.get(key, user.language_code or 'ru', **kw)
        
        if status == 'completed':
            text = (
                f"✅ <b>{_('generation.video_ready', default='Видео готово!')}</b>\n\n"
                f"🆔 ID: <code>{generation_id}</code>\n"
                f"{_('generation.use_history_to_view', default='Используйте /history для просмотра')}"
            )
        elif status == 'recovered':
            text = (
                f"🎉 <b>{_('generation.video_recovered', default='Видео восстановлено!')}</b>\n\n"
                f"🆔 ID: <code>{generation_id}</code>\n"
                f"💡 {_('generation.recovery_explanation', default='Видео было сгенерировано, но не доставлено из-за технической ошибки')}\n"
                f"{_('generation.use_history_to_view', default='Используйте /history для просмотра')}"
            )
        else:
            error = kwargs.get('error', 'Unknown error')
            
            # Специальная обработка ошибок модерации
            if any(word in error.lower() for word in ['flagged', 'sensitive', 'content', 'moderation', 'inappropriate']):
                text = (
                    f"🚫 <b>{_('generation.moderation_error_title', default='Контент заблокирован')}</b>\n\n"
                    f"🆔 ID: <code>{generation_id}</code>\n"
                    f"💰 {_('generation.credits_returned', credits=generation.cost)}\n\n"
                    f"📝 {_('generation.moderation_reason', default='Причина')}: Контент был заблокирован системой модерации\n\n"
                    f"💡 {_('generation.moderation_advice', default='Попробуйте изменить описание или изображение')}"
                )
            else:
                text = (
                    f"❌ <b>{_('generation.error_title', default='Ошибка генерации')}</b>\n\n"
                    f"🆔 ID: <code>{generation_id}</code>\n"
                    f"💰 {_('generation.credits_returned', credits=generation.cost)}\n"
                    f"📝 {_('generation.error_reason', default='Причина')}: {error}"
                )
        
        await bot.send_message(user.telegram_id, text, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
    finally:
        await bot.session.close()

@app.task
def cleanup_old_generations():
    """Очистка старых генераций"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(_cleanup_old_generations())
    finally:
        loop.close()

async def _cleanup_old_generations():
    """Асинхронная очистка старых генераций"""
    # Удаляем генерации старше 30 дней
    cutoff_date = datetime.utcnow() - timedelta(days=30)
    
    async with db.async_session() as session:
        from sqlalchemy import delete
        
        result = await session.execute(
            delete(Generation).where(
                Generation.created_at < cutoff_date,
                Generation.status.in_([GenerationStatus.COMPLETED, GenerationStatus.FAILED])
            )
        )
        
        deleted_count = result.rowcount
        await session.commit()
        
        logger.info(f"Deleted {deleted_count} old generations")

@app.task
def calculate_daily_statistics():
    """Расчет ежедневной статистики"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(_calculate_daily_statistics())
    finally:
        loop.close()

async def _calculate_daily_statistics():
    """Асинхронный расчет статистики"""
    yesterday = datetime.utcnow().date() - timedelta(days=1)
    
    async with db.async_session() as session:
        from sqlalchemy import select, func, and_
        
        # Новые пользователи
        new_users = await session.execute(
            select(func.count(User.id)).where(
                func.date(User.created_at) == yesterday
            )
        )
        
        # Активные пользователи
        active_users = await session.execute(
            select(func.count(func.distinct(Generation.user_id))).where(
                func.date(Generation.created_at) == yesterday
            )
        )
        
        # Генерации
        total_generations = await session.execute(
            select(func.count(Generation.id)).where(
                func.date(Generation.created_at) == yesterday
            )
        )
        
        successful_generations = await session.execute(
            select(func.count(Generation.id)).where(
                and_(
                    func.date(Generation.created_at) == yesterday,
                    Generation.status == GenerationStatus.COMPLETED
                )
            )
        )
        
        # Доход
        revenue = await session.execute(
            select(func.sum(Transaction.stars_paid)).where(
                and_(
                    func.date(Transaction.created_at) == yesterday,
                    Transaction.status == 'completed'
                )
            )
        )
        
        # Среднее время генерации
        avg_gen_time = await session.execute(
            select(func.avg(Generation.generation_time)).where(
                and_(
                    func.date(Generation.created_at) == yesterday,
                    Generation.status == GenerationStatus.COMPLETED,
                    Generation.generation_time.isnot(None)
                )
            )
        )
        
        # Сохраняем статистику
        stats = Statistics(
            date=yesterday,
            new_users=new_users.scalar() or 0,
            active_users=active_users.scalar() or 0,
            total_generations=total_generations.scalar() or 0,
            successful_generations=successful_generations.scalar() or 0,
            failed_generations=(total_generations.scalar() or 0) - (successful_generations.scalar() or 0),
            revenue_stars=revenue.scalar() or 0,
            avg_generation_time=avg_gen_time.scalar()
        )
        
        session.add(stats)
        await session.commit()
        
        logger.info(f"Daily statistics calculated for {yesterday}")

@app.task
def send_inactive_user_reminder():
    """Отправка напоминаний неактивным пользователям"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(_send_inactive_user_reminder())
    finally:
        loop.close()

async def _send_inactive_user_reminder():
    """Асинхронная отправка напоминаний"""
    from aiogram import Bot
    from bot.middlewares.i18n import i18n
    
    bot = Bot(token=settings.BOT_TOKEN)
    
    # Находим пользователей, неактивных более 7 дней
    inactive_date = datetime.utcnow() - timedelta(days=7)
    
    async with db.async_session() as session:
        from sqlalchemy import and_, select
        
        inactive_users = await session.execute(
            select(User).where(
                and_(
                    User.last_active < inactive_date,
                    User.balance > 0,  # Только с положительным балансом
                    User.is_banned == False
                )
            ).limit(100)  # Ограничиваем количество
        )
        
        sent_count = 0
        
        for user in inactive_users.scalars():
            try:
                _ = lambda key, **kw: i18n.get(key, user.language_code or 'ru', **kw)
                
                text = (
                    f"👋 {_('reminder.hello', default='Привет!')}\n\n"
                    f"{_('reminder.inactive', default='Вы давно не создавали видео.')}\n"
                    f"{_('reminder.balance', balance=user.balance)}\n\n"
                    f"{_('reminder.try_new', default='Попробуйте новые функции и модели!')} 🎬"
                )
                
                await bot.send_message(user.telegram_id, text, parse_mode='HTML')
                sent_count += 1
                
                # Задержка между сообщениями
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Failed to send reminder to user {user.telegram_id}: {e}")
        
        logger.info(f"Sent {sent_count} inactive user reminders")
    
    await bot.session.close()

# Настройка периодических задач
from celery.schedules import crontab

app.conf.beat_schedule = {
    'cleanup-old-generations': {
        'task': 'bot.tasks.cleanup_old_generations',
        'schedule': crontab(hour=3, minute=0),  # Каждый день в 3:00
    },
    'calculate-daily-statistics': {
        'task': 'bot.tasks.calculate_daily_statistics',
        'schedule': crontab(hour=0, minute=30),  # Каждый день в 0:30
    },
    'send-inactive-reminders': {
        'task': 'bot.tasks.send_inactive_user_reminder',
        'schedule': crontab(hour=12, minute=0, day_of_week=1),  # Каждый понедельник в 12:00
    },
}

# Регистрация задач
generate_video_task = app.register_task(GenerateVideoTask())

# Утилиты для работы с задачами
async def cancel_generation_task(generation_id: int) -> bool:
    """Отмена задачи генерации"""
    try:
        generation = await db.get_generation(generation_id)
        if generation and generation.task_id:
            app.control.revoke(generation.task_id, terminate=True)
            
            # Обновляем статус
            await db.update_generation_status(
                generation_id,
                GenerationStatus.CANCELLED
            )
            
            # Возвращаем кредиты
            await db.update_user_balance(generation.user_id, generation.cost)
            
            # Отменяем лимит генерации при отмене
            user = await db.get_user_by_id(generation.user_id)
            if user:
                from bot.middlewares.throttling import GenerationThrottling
                GenerationThrottling.cancel_generation_limit(user.telegram_id)
            
            logger.info(f"Generation task {generation.task_id} cancelled")
            return True
        return False
    except Exception as e:
        logger.error(f"Error cancelling generation task: {e}")
        return False

async def get_task_status(task_id: str) -> Dict[str, Any]:
    """Получить статус задачи"""
    try:
        result = app.AsyncResult(task_id)
        return {
            'state': result.state,
            'result': result.result,
            'info': result.info
        }
    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        return {'state': 'UNKNOWN', 'error': str(e)}

@app.task
async def recover_lost_videos_task():
    """Задача для восстановления потерянных видео"""
    logger.info("Starting lost videos recovery task")
    
    try:
        # Получаем неудачные генерации за последние 24 часа
        failed_generations = await db.get_failed_generations_with_task_id(hours_back=24)
        
        if not failed_generations:
            logger.info("No failed generations to check for recovery")
            return {'recovered': 0, 'checked': 0}
        
        logger.info(f"Checking {len(failed_generations)} failed generations for recovery")
        
        # Восстанавливаем видео
        api = get_wavespeed_api()
        recovered = await api.recover_lost_videos(failed_generations)
        
        # Отправляем уведомления пользователям о восстановленных видео
        for recovery in recovered:
            try:
                await send_generation_notification(
                    recovery['generation_id'],
                    'recovered',
                    video_url=recovery['video_url']
                )
                logger.info(f"Sent recovery notification for generation {recovery['generation_id']}")
            except Exception as e:
                logger.error(f"Error sending recovery notification: {e}")
        
        logger.info(f"Recovery task completed: {len(recovered)} videos recovered from {len(failed_generations)} checked")
        
        return {
            'recovered': len(recovered),
            'checked': len(failed_generations)
        }
        
    except Exception as e:
        logger.error(f"Error in recovery task: {e}")
        return {'error': str(e)}