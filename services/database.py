import asyncio
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, update, delete, func, and_, or_, String, cast
from sqlalchemy.orm import selectinload
import logging

from core.config import settings
from models.models import (
    Base, User, Generation, Transaction, PromoCode, PromoCodeUsage, 
    SupportTicket, Statistics, AdminLog, UserAction,
    GenerationStatusEnum, TransactionTypeEnum, TransactionStatusEnum
)

logger = logging.getLogger(__name__)

class DatabaseService:
    def __init__(self):
        self.engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            pool_size=20,
            max_overflow=40,
            pool_pre_ping=True,
            pool_recycle=3600  # Переподключение каждый час
        )
        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    
    async def create_tables(self):
        """Создание всех таблиц"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def drop_tables(self):
        """Удаление всех таблиц (только для тестов!)"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    
    # ========== User методы ==========
    
    async def get_user(self, telegram_id: int) -> Optional[User]:
        """Получить пользователя по telegram_id"""
        async with self.async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()
    
    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Получить пользователя по внутреннему ID"""
        async with self.async_session() as session:
            return await session.get(User, user_id)
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Получить пользователя по username"""
        async with self.async_session() as session:
            result = await session.execute(
                select(User).where(User.username == username)
            )
            return result.scalar_one_or_none()
    
    async def create_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language_code: Optional[str] = None,
        referrer_telegram_id: Optional[int] = None
    ) -> User:
        """Создать нового пользователя"""
        async with self.async_session() as session:
            # Проверяем, существует ли уже пользователь
            existing = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"User with telegram_id {telegram_id} already exists")
            
            # Ищем реферера по telegram_id
            referrer = None
            if referrer_telegram_id:
                referrer_result = await session.execute(
                    select(User).where(User.telegram_id == referrer_telegram_id)
                )
                referrer = referrer_result.scalar_one_or_none()
            
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language_code=language_code or 'ru',
                referrer_id=referrer.id if referrer else None,
                balance=settings.WELCOME_BONUS_CREDITS,
                total_bonuses=settings.WELCOME_BONUS_CREDITS
            )
            session.add(user)
            
            # Коммитим чтобы получить ID нового пользователя
            await session.commit()
            await session.refresh(user)
            
            # Если есть реферер, обрабатываем реферальный бонус
            if referrer:
                await self._process_referral_bonus(session, referrer, user)
                await session.commit()
            
            return user
    
    async def _process_referral_bonus(self, session: AsyncSession, referrer: User, new_user: User):
        """Обработка реферального бонуса"""
        # Обновляем статистику реферера
        referrer.referral_count += 1
        referrer.referral_earnings += settings.REFERRAL_BONUS_CREDITS
        referrer.balance += settings.REFERRAL_BONUS_CREDITS
        
        # Создаем транзакцию для реферера
        ref_transaction = Transaction(
            user_id=referrer.id,
            type=TransactionTypeEnum.REFERRAL,
            amount=settings.REFERRAL_BONUS_CREDITS,
            balance_before=referrer.balance - settings.REFERRAL_BONUS_CREDITS,
            balance_after=referrer.balance,
            status=TransactionStatusEnum.COMPLETED,
            description=f"Бонус за приглашение пользователя {new_user.telegram_id}",
            completed_at=datetime.utcnow(),
            meta_data={"referral_id": new_user.id}
        )
        session.add(ref_transaction)
    
    async def update_user_balance(self, user_id: int, amount: int, description: Optional[str] = None) -> bool:
        """Обновить баланс пользователя (по внутреннему ID)"""
        # Валидация amount
        if abs(amount) > 1_000_000:
            logger.error(f"Attempt to update balance with too large amount: {amount}")
            return False
            
        async with self.async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                return False
                
            old_balance = user.balance
            new_balance = user.balance + amount
            
            # Проверка на отрицательный баланс
            if new_balance < 0:
                logger.warning(f"Attempt to set negative balance for user {user_id}: {new_balance}")
                return False
                
            user.balance = new_balance
            
            if amount > 0:
                user.total_bought += amount
            else:
                user.total_spent += abs(amount)
            
            # Создаем транзакцию для отслеживания
            transaction = Transaction(
                user_id=user_id,
                type=TransactionTypeEnum.GENERATION if amount < 0 else TransactionTypeEnum.BONUS,
                amount=amount,
                balance_before=old_balance,
                balance_after=new_balance,
                status=TransactionStatusEnum.COMPLETED,
                description=description,
                completed_at=datetime.utcnow()
            )
            session.add(transaction)
            
            await session.commit()
            return True
    
    async def get_user_balance(self, telegram_id: int) -> int:
        """Получить баланс пользователя"""
        async with self.async_session() as session:
            result = await session.execute(
                select(User.balance).where(User.telegram_id == telegram_id)
            )
            balance = result.scalar_one_or_none()
            return balance or 0
    
    async def update_user_activity(self, telegram_id: int):
        """Обновить время последней активности"""
        async with self.async_session() as session:
            await session.execute(
                update(User)
                .where(User.telegram_id == telegram_id)
                .values(last_active=datetime.utcnow())
            )
            await session.commit()
    
    async def update_user(self, telegram_id: int, **kwargs):
        """Обновить данные пользователя"""
        async with self.async_session() as session:
            # Фильтруем только существующие поля
            allowed_fields = {
                'username', 'first_name', 'last_name', 'language_code',
                'is_banned', 'ban_reason', 'is_premium', 'settings'
            }
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in allowed_fields}
            
            if filtered_kwargs:
                await session.execute(
                    update(User)
                    .where(User.telegram_id == telegram_id)
                    .values(**filtered_kwargs)
                )
                await session.commit()
    
    async def update_user_settings(self, user_id: int, settings: Dict[str, Any]) -> bool:
        """Обновить настройки пользователя"""
        async with self.async_session() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(settings=settings)
            )
            await session.commit()
            return True
    
    async def get_user_generations_count(self, user_id: int) -> int:
        """Получить количество генераций пользователя"""
        async with self.async_session() as session:
            result = await session.execute(
                select(func.count(Generation.id))
                .where(Generation.user_id == user_id)
            )
            return result.scalar() or 0
    
    async def get_user_total_spent(self, user_id: int) -> int:
        """Получить общую сумму потраченных кредитов пользователя"""
        async with self.async_session() as session:
            result = await session.execute(
                select(func.sum(Transaction.amount))
                .where(
                    and_(
                        Transaction.user_id == user_id,
                        Transaction.amount < 0,  # Только отрицательные транзакции (траты)
                        Transaction.status == TransactionStatusEnum.COMPLETED
                    )
                )
            )
            total_spent = result.scalar() or 0
            return abs(total_spent)  # Возвращаем положительное число
    
    async def get_user_statistics(self, telegram_id: int) -> Dict[str, Any]:
        """Получить статистику пользователя"""
        user = await self.get_user(telegram_id)
        if not user:
            return {}
        
        async with self.async_session() as session:
            # Подсчет генераций
            generations_count = await session.execute(
                select(func.count(Generation.id))
                .where(Generation.user_id == user.id)
            )
            total_generations = generations_count.scalar() or 0
            
            successful_generations = await session.execute(
                select(func.count(Generation.id))
                .where(
                    and_(
                        Generation.user_id == user.id,
                        Generation.status == GenerationStatusEnum.COMPLETED
                    )
                )
            )
            
            # Средняя оценка
            avg_rating = await session.execute(
                select(func.avg(Generation.rating))
                .where(
                    and_(
                        Generation.user_id == user.id,
                        Generation.rating.isnot(None)
                    )
                )
            )
            
            # Последняя генерация
            last_gen = await session.execute(
                select(Generation.created_at)
                .where(Generation.user_id == user.id)
                .order_by(Generation.created_at.desc())
                .limit(1)
            )
            last_generation = last_gen.scalar_one_or_none()
            
            # Подсчет бонусов
            total_bonuses = await session.execute(
                select(func.sum(Transaction.amount))
                .where(
                    and_(
                        Transaction.user_id == user.id,
                        Transaction.type.in_([
                            TransactionTypeEnum.BONUS,
                            TransactionTypeEnum.REFERRAL,
                            TransactionTypeEnum.ADMIN_GIFT
                        ]),
                        Transaction.status == TransactionStatusEnum.COMPLETED
                    )
                )
            )
            
            # Подсчет streak'ов (ежедневная активность)
            current_streak, max_streak = await self._calculate_user_streaks(session, user.id)
            
            return {
                "user_id": user.telegram_id,
                "registration_date": user.created_at,
                "language": user.language_code,
                "balance": user.balance,
                "total_bought": user.total_bought,
                "total_spent": user.total_spent,
                "total_bonuses": total_bonuses.scalar() or 0,
                "total_generations": total_generations,
                "successful_generations": successful_generations.scalar() or 0,
                "average_rating": round(avg_rating.scalar() or 0, 2),
                "referral_count": user.referral_count,
                "referral_earnings": user.referral_earnings,
                "last_generation": last_generation,
                "is_premium": user.is_premium,
                "current_streak": current_streak,
                "max_streak": max_streak
            }
    
    async def _calculate_user_streaks(self, session: AsyncSession, user_id: int) -> tuple[int, int]:
        """Рассчитать текущую и максимальную полосу активности пользователя"""
        try:
            # Получаем даты всех генераций пользователя, сгруппированные по дням
            result = await session.execute(
                select(func.date(Generation.created_at).label('generation_date'))
                .where(
                    and_(
                        Generation.user_id == user_id,
                        Generation.status == GenerationStatusEnum.COMPLETED
                    )
                )
                .group_by(func.date(Generation.created_at))
                .order_by(func.date(Generation.created_at).desc())
            )
            
            generation_dates = [row.generation_date for row in result.fetchall()]
            
            if not generation_dates:
                return 0, 0
            
            # Рассчитываем текущий streak
            current_streak = 0
            today = datetime.utcnow().date()
            yesterday = today - timedelta(days=1)
            
            # Проверяем непрерывность начиная с сегодня или вчера
            check_date = today if today in generation_dates else yesterday
            
            for date in generation_dates:
                if date == check_date:
                    current_streak += 1
                    check_date -= timedelta(days=1)
                elif date < check_date:
                    # Пропуск в активности
                    break
            
            # Рассчитываем максимальный streak
            max_streak = 0
            temp_streak = 0
            prev_date = None
            
            # Сортируем даты по возрастанию для подсчета максимального streak
            sorted_dates = sorted(generation_dates)
            
            for date in sorted_dates:
                if prev_date is None or date == prev_date + timedelta(days=1):
                    temp_streak += 1
                    max_streak = max(max_streak, temp_streak)
                else:
                    temp_streak = 1
                prev_date = date
            
            return current_streak, max_streak
            
        except Exception as e:
            logger.error(f"Error calculating user streaks: {e}")
            return 0, 0
    
    # ========== Generation методы ==========
    
    async def create_generation(
        self,
        user_id: int,  # Внутренний ID пользователя
        mode: str,
        model: str,
        prompt: str,
        cost: int,
        **kwargs
    ) -> Generation:
        """Создать новую генерацию"""
        # Валидация cost
        if cost < 0 or cost > 10000:
            raise ValueError(f"Invalid generation cost: {cost}")
            
        async with self.async_session() as session:
            # Определяем, используются ли бонусные кредиты
            used_bonus_credits = await self._is_using_bonus_credits(session, user_id, cost)
            
            generation = Generation(
                user_id=user_id,
                mode=mode,
                model=model,
                prompt=prompt[:2000],  # Ограничиваем длину промпта
                cost=cost,
                used_bonus_credits=used_bonus_credits,
                resolution=kwargs.get('resolution', '720p'),
                duration=kwargs.get('duration', 5),
                aspect_ratio=kwargs.get('aspect_ratio', '16:9'),
                negative_prompt=kwargs.get('negative_prompt', '')[:500],  # Ограничиваем длину
                image_url=kwargs.get('image_url'),
                video_url=None,
                video_file_id=None,
                thumbnail_url=None,
                seed=kwargs.get('seed', -1),
                file_size=None,
                generation_time=None,
                queue_time=None,
                status=GenerationStatusEnum.PENDING,
                error_message=None,
                error_code=None,
                task_id=kwargs.get('task_id'),
                queue_position=kwargs.get('queue_position'),
                progress=0,
                rating=None,
                feedback=None
            )
            session.add(generation)
            await session.commit()
            await session.refresh(generation)
            return generation
    
    async def _is_using_bonus_credits(self, session: AsyncSession, user_id: int, cost: int) -> bool:
        """
        Определяет, используются ли бонусные кредиты для генерации
        
        Логика:
        1. Получаем общую сумму бонусных кредитов пользователя
        2. Получаем общую сумму потраченных кредитов на генерации
        3. Если (потраченные + текущая стоимость) <= бонусные кредиты, то используются бонусы
        """
        # Получаем пользователя
        user = await session.get(User, user_id)
        if not user:
            return False
        
        # Получаем общую сумму бонусных кредитов
        total_bonus_result = await session.execute(
            select(func.sum(Transaction.amount))
            .where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.type.in_([
                        TransactionTypeEnum.BONUS,
                        TransactionTypeEnum.REFERRAL,
                        TransactionTypeEnum.ADMIN_GIFT
                    ]),
                    Transaction.status == TransactionStatusEnum.COMPLETED,
                    Transaction.amount > 0
                )
            )
        )
        total_bonus_credits = total_bonus_result.scalar() or 0
        
        # Получаем общую сумму потраченных кредитов на генерации
        total_spent_result = await session.execute(
            select(func.sum(Generation.cost))
            .where(
                and_(
                    Generation.user_id == user_id,
                    Generation.status == GenerationStatusEnum.COMPLETED
                )
            )
        )
        total_spent_on_generations = total_spent_result.scalar() or 0
        
        # Проверяем, хватает ли бонусных кредитов
        # Если после этой генерации общие траты не превысят бонусные кредиты
        return (total_spent_on_generations + cost) <= total_bonus_credits
    
    async def update_generation_status(
        self,
        generation_id: int,
        status: Union[str, GenerationStatusEnum],
        **kwargs
    ):
        """Обновить статус генерации"""
        async with self.async_session() as session:
            # Конвертируем строку в enum если нужно
            if isinstance(status, str):
                status = GenerationStatusEnum(status)
            
            values = {'status': status}
            
            if status == GenerationStatusEnum.PROCESSING:
                values['started_at'] = datetime.utcnow()
            elif status == GenerationStatusEnum.COMPLETED:
                values['completed_at'] = datetime.utcnow()
                if 'video_url' in kwargs:
                    values['video_url'] = kwargs['video_url']
                if 'generation_time' in kwargs:
                    values['generation_time'] = kwargs['generation_time']
                if 'video_file_id' in kwargs:
                    values['video_file_id'] = kwargs['video_file_id']
            elif status == GenerationStatusEnum.FAILED:
                if 'error_message' in kwargs:
                    values['error_message'] = kwargs['error_message'][:500]  # Ограничиваем длину
                if 'error_code' in kwargs:
                    values['error_code'] = kwargs['error_code'][:50]  # Ограничиваем длину
            
            if 'task_id' in kwargs:
                values['task_id'] = kwargs['task_id']
            if 'queue_position' in kwargs:
                values['queue_position'] = kwargs['queue_position']
            
            await session.execute(
                update(Generation)
                .where(Generation.id == generation_id)
                .values(**values)
            )
            await session.commit()
    
    async def update_generation_progress(
        self,
        generation_id: int,
        progress: int,
        status: Optional[str] = None
    ):
        """Обновить прогресс генерации"""
        # Валидация progress
        progress = max(0, min(100, progress))
        
        async with self.async_session() as session:
            values = {'progress': progress}
            if status:
                values['status'] = GenerationStatusEnum(status)
            
            await session.execute(
                update(Generation)
                .where(Generation.id == generation_id)
                .values(**values)
            )
            await session.commit()
    
    async def update_generation_video_file_id(self, generation_id: int, file_id: str):
        """Обновить Telegram file_id для видео"""
        async with self.async_session() as session:
            await session.execute(
                update(Generation)
                .where(Generation.id == generation_id)
                .values(video_file_id=file_id[:200])  # Ограничиваем длину
            )
            await session.commit()
    
    async def get_generation(self, generation_id: int) -> Optional[Generation]:
        """Получить генерацию по ID"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Generation)
                .where(Generation.id == generation_id)
                .options(selectinload(Generation.user))
            )
            return result.scalar_one_or_none()
    
    async def get_user_generations(
        self,
        user_id: int,  # Внутренний ID
        limit: int = 10,
        offset: int = 0
    ) -> List[Generation]:
        """Получить генерации пользователя"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Generation)
                .where(Generation.user_id == user_id)
                .order_by(Generation.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()
    
    async def rate_generation(
        self,
        generation_id: int,
        rating: int,
        feedback: Optional[str] = None
    ):
        """Оценить генерацию"""
        # Валидация rating
        if rating < 1 or rating > 5:
            raise ValueError(f"Invalid rating: {rating}")
            
        async with self.async_session() as session:
            await session.execute(
                update(Generation)
                .where(Generation.id == generation_id)
                .values(rating=rating, feedback=feedback[:500] if feedback else None)
            )
            await session.commit()
    
    # ========== Transaction методы ==========
    
    async def create_transaction(
        self,
        user_id: int,
        type: Union[str, TransactionTypeEnum],
        amount: int,
        **kwargs
    ) -> Transaction:
        """Создать транзакцию"""
        async with self.async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                raise ValueError(f"User with id {user_id} not found")
            
            # Конвертируем строку в enum если нужно
            if isinstance(type, str):
                type = TransactionTypeEnum(type)
            
            balance_after = user.balance + amount if kwargs.get('update_balance', True) else user.balance
            
            transaction = Transaction(
                user_id=user_id,
                type=type,
                amount=amount,
                balance_before=user.balance,
                balance_after=balance_after,
                stars_paid=kwargs.get('stars_paid'),
                rub_paid=kwargs.get('rub_paid'),
                package_id=kwargs.get('package_id'),
                payment_method=kwargs.get('payment_method', 'telegram_stars'),
                payment_id=kwargs.get('payment_id'),
                description=kwargs.get('description', '')[:500],  # Ограничиваем длину
                meta_data=kwargs.get('metadata'),
                status=TransactionStatusEnum.PENDING
            )
            session.add(transaction)
            await session.commit()
            await session.refresh(transaction)
            return transaction
    
    async def complete_transaction(
        self, 
        transaction_id: int, 
        telegram_charge_id: Optional[str] = None
    ):
        """Завершить транзакцию"""
        async with self.async_session() as session:
            transaction = await session.get(Transaction, transaction_id)
            if not transaction:
                raise ValueError(f"Transaction {transaction_id} not found")
            
            if transaction.status != TransactionStatusEnum.PENDING:
                raise ValueError(f"Transaction {transaction_id} is not pending")
            
            transaction.status = TransactionStatusEnum.COMPLETED
            transaction.completed_at = datetime.utcnow()
            
            # Сохраняем telegram_charge_id для возможности возврата
            if telegram_charge_id:
                transaction.telegram_charge_id = telegram_charge_id
            
            # Обновляем баланс пользователя
            user = await session.get(User, transaction.user_id)
            if user and transaction.amount != 0:
                user.balance += transaction.amount
                transaction.balance_after = user.balance
                
                if transaction.amount > 0:
                    user.total_bought += transaction.amount
                    if not user.first_purchase_at:
                        user.first_purchase_at = datetime.utcnow()
                
                # Обновляем бонусы если это бонусная транзакция
                if transaction.type in [TransactionTypeEnum.BONUS, TransactionTypeEnum.REFERRAL]:
                    user.total_bonuses = (user.total_bonuses or 0) + transaction.amount
            
            await session.commit()
    
    async def process_refund(self, transaction_id: int) -> bool:
        """Обработать возврат средств"""
        async with self.async_session() as session:
            transaction = await session.get(Transaction, transaction_id)
            if not transaction:
                return False
            
            if transaction.status != TransactionStatusEnum.COMPLETED:
                return False
            
            # Обновляем статус транзакции
            transaction.status = TransactionStatusEnum.REFUNDED
            transaction.refunded_at = datetime.utcnow()
            
            # Списываем кредиты с баланса пользователя
            user = await session.get(User, transaction.user_id)
            if user:
                user.balance -= transaction.amount
                if user.balance < 0:
                    user.balance = 0
                
                # Создаем транзакцию возврата
                refund_transaction = Transaction(
                    user_id=user.id,
                    type=TransactionTypeEnum.REFUND,
                    amount=-transaction.amount,
                    balance_before=user.balance + transaction.amount,
                    balance_after=user.balance,
                    status=TransactionStatusEnum.COMPLETED,
                    description=f"Возврат платежа #{transaction.id}",
                    completed_at=datetime.utcnow(),
                    meta_data={
                        "original_transaction_id": transaction.id,
                        "refund_reason": "admin_refund"
                    }
                )
                session.add(refund_transaction)
            
            await session.commit()
            return True
    
    async def get_transaction(self, transaction_id: int) -> Optional[Transaction]:
        """Получить транзакцию по ID"""
        async with self.async_session() as session:
            return await session.get(Transaction, transaction_id)
    
    async def get_user_transactions(
        self,
        telegram_id: int,
        limit: int = 10,
        offset: int = 0,
        type: Optional[TransactionTypeEnum] = None,
        include_all_statuses: bool = False
    ) -> List[Transaction]:
        """Получить транзакции пользователя"""
        user = await self.get_user(telegram_id)
        if not user:
            return []
        
        async with self.async_session() as session:
            query = select(Transaction).where(Transaction.user_id == user.id)
            
            if type:
                query = query.where(Transaction.type == type)
            
            # Фильтруем по статусу, если не запрошены все статусы
            if not include_all_statuses:
                query = query.where(Transaction.status.in_([
                    TransactionStatusEnum.COMPLETED,
                    TransactionStatusEnum.REFUNDED  # Показываем возвращенные для прозрачности
                ]))
            
            query = query.order_by(Transaction.created_at.desc()).limit(limit).offset(offset)
            
            result = await session.execute(query)
            return result.scalars().all()
    
    # ========== Referral методы ==========
    
    async def increment_referral_stats(self, referrer_id: int, bonus_amount: int):
        """Увеличить статистику рефералов"""
        async with self.async_session() as session:
            await session.execute(
                update(User)
                .where(User.id == referrer_id)
                .values(
                    referral_count=User.referral_count + 1,
                    referral_earnings=User.referral_earnings + bonus_amount
                )
            )
            await session.commit()
    
    async def get_referral_statistics(self, user_id: int) -> Dict[str, Any]:
        """Получить статистику рефералов"""
        async with self.async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                return {}
            
            # Получаем рефералов
            referrals = await session.execute(
                select(User)
                .where(User.referrer_id == user.id)
                .order_by(User.created_at.desc())
            )
            referral_list = referrals.scalars().all()
            
            # Активные рефералы (сделали хотя бы одну генерацию)
            active_referrals = 0
            for ref in referral_list:
                gen_count = await session.execute(
                    select(func.count(Generation.id))
                    .where(Generation.user_id == ref.id)
                )
                if gen_count.scalar() > 0:
                    active_referrals += 1
            
            # Рефералы за текущий месяц
            month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
            monthly_referrals = await session.execute(
                select(func.count(User.id))
                .where(
                    and_(
                        User.referrer_id == user.id,
                        User.created_at >= month_start
                    )
                )
            )
            
            # Последние рефералы
            recent_referrals = []
            for ref in referral_list[:10]:
                recent_referrals.append({
                    'id': ref.id,
                    'username': ref.username,
                    'date': ref.created_at,
                    'is_active': await self._is_user_active(session, ref.id)
                })
            
            return {
                'total_referrals': user.referral_count,
                'active_referrals': active_referrals,
                'total_earned': user.referral_earnings,
                'this_month': monthly_referrals.scalar() or 0,
                'recent_referrals': recent_referrals
            }
    
    async def _is_user_active(self, session: AsyncSession, user_id: int) -> bool:
        """Проверить, активен ли пользователь"""
        gen_count = await session.execute(
            select(func.count(Generation.id))
            .where(Generation.user_id == user_id)
        )
        return gen_count.scalar() > 0
    
    # ========== Search методы ==========
    
    async def search_users(
        self,
        query: str,
        limit: int = 10
    ) -> List[User]:
        """Поиск пользователей"""
        # Валидация query
        if not query or len(query) > 100:
            return []
            
        async with self.async_session() as session:
            # Защита от SQL injection - используем параметризованные запросы
            search_pattern = f"%{query}%"
            
            result = await session.execute(
                select(User)
                .where(
                    or_(
                        User.username.ilike(search_pattern),
                        User.first_name.ilike(search_pattern),
                        User.last_name.ilike(search_pattern),
                        cast(User.telegram_id, String).like(search_pattern)
                    )
                )
                .limit(min(limit, 100))  # Ограничиваем максимальный limit
            )
            return result.scalars().all()
    
    # ========== Admin методы ==========
    
    async def get_all_users(
        self,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None,
        only_banned: bool = False,
        only_premium: bool = False
    ) -> List[User]:
        """Получить всех пользователей (для админов)"""
        # Валидация параметров
        limit = min(limit, 1000)  # Максимум 1000 пользователей за раз
        
        async with self.async_session() as session:
            query = select(User)
            
            if search:
                search_pattern = f"%{search[:100]}%"  # Ограничиваем длину search
                query = query.where(
                    or_(
                        User.username.ilike(search_pattern),
                        User.first_name.ilike(search_pattern),
                        cast(User.telegram_id, String).like(search_pattern)
                    )
                )
            
            if only_banned:
                query = query.where(User.is_banned == True)
            
            if only_premium:
                query = query.where(User.is_premium == True)
            
            query = query.order_by(User.created_at.desc()).limit(limit).offset(offset)
            
            result = await session.execute(query)
            return result.scalars().all()
    
    async def ban_user(
        self, 
        telegram_id: int, 
        banned: bool = True,
        reason: Optional[str] = None
    ) -> bool:
        """Забанить/разбанить пользователя"""
        async with self.async_session() as session:
            result = await session.execute(
                update(User)
                .where(User.telegram_id == telegram_id)
                .values(
                    is_banned=banned,
                    ban_reason=reason[:500] if reason and banned else None,
                    banned_at=datetime.utcnow() if banned else None
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def unban_user(self, user_id: int) -> bool:
        """Разбанить пользователя по внутреннему ID"""
        async with self.async_session() as session:
            result = await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(
                    is_banned=False,
                    ban_reason=None,
                    banned_at=None
                )
            )
            await session.commit()
            return result.rowcount > 0
    
    async def ban_user_by_id(self, user_id: int, reason: Optional[str] = None) -> bool:
        """Забанить пользователя по внутреннему ID"""
        async with self.async_session() as session:
            result = await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(
                    is_banned=True,
                    ban_reason=reason[:500] if reason else None,
                    banned_at=datetime.utcnow()
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def add_credits_to_user(
        self, 
        telegram_id: int, 
        amount: int, 
        admin_id: int,
        reason: Optional[str] = None
    ) -> bool:
        """Добавить кредиты пользователю (админская функция)"""
        # Валидация amount
        if abs(amount) > 1_000_000:
            logger.error(f"Attempt to add too many credits: {amount}")
            return False
            
        user = await self.get_user(telegram_id)
        if not user:
            return False
        
        async with self.async_session() as session:
            # Обновляем баланс
            await session.execute(
                update(User)
                .where(User.id == user.id)
                .values(balance=User.balance + amount)
            )
            
            # Получаем обновленный баланс
            result = await session.execute(
                select(User.balance).where(User.id == user.id)
            )
            new_balance = result.scalar()
            
            # Создаем транзакцию
            transaction = Transaction(
                user_id=user.id,
                type=TransactionTypeEnum.ADMIN_GIFT,
                amount=amount,
                balance_before=new_balance - amount,
                balance_after=new_balance,
                status=TransactionStatusEnum.COMPLETED,
                description=(reason or f"Начислено администратором {admin_id}")[:500],
                completed_at=datetime.utcnow(),
                meta_data={"admin_id": admin_id}
            )
            session.add(transaction)
            
            await session.commit()
            return True
    
    async def add_credits(
        self, 
        user_id: int,  # Внутренний ID
        amount: int, 
        reason: Optional[str] = None
    ) -> bool:
        """Добавить кредиты пользователю"""
        # Валидация amount
        if abs(amount) > 1_000_000:
            logger.error(f"Attempt to add too many credits: {amount}")
            return False
            
        async with self.async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                return False
            
            old_balance = user.balance
            user.balance += amount
            
            if amount > 0:
                user.total_bought += amount
                user.total_bonuses = (user.total_bonuses or 0) + amount
            
            # Создаем транзакцию
            transaction = Transaction(
                user_id=user_id,
                type=TransactionTypeEnum.BONUS if amount > 0 else TransactionTypeEnum.GENERATION,
                amount=amount,
                balance_before=old_balance,
                balance_after=user.balance,
                status=TransactionStatusEnum.COMPLETED,
                description=(reason or f"{'Начисление' if amount > 0 else 'Списание'} {abs(amount)} кредитов")[:500],
                completed_at=datetime.utcnow()
            )
            session.add(transaction)
            
            await session.commit()
            return True
    
    # ========== Statistics методы ==========
    
    async def get_bot_statistics(self) -> Dict[str, Any]:
        """Получить общую статистику бота"""
        async with self.async_session() as session:
            # Пользователи
            total_users = await session.execute(
                select(func.count(User.id))
            )
            
            active_today = await session.execute(
                select(func.count(User.id))
                .where(User.last_active >= datetime.utcnow() - timedelta(days=1))
            )
            
            new_today = await session.execute(
                select(func.count(User.id))
                .where(User.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0))
            )
            
            # Генерации
            total_generations = await session.execute(
                select(func.count(Generation.id))
            )
            
            generations_today = await session.execute(
                select(func.count(Generation.id))
                .where(Generation.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0))
            )
            
            pending_generations = await session.execute(
                select(func.count(Generation.id))
                .where(Generation.status.in_([
                    GenerationStatusEnum.PENDING, 
                    GenerationStatusEnum.PROCESSING
                ]))
            )
            
            # Финансы
            revenue_today = await session.execute(
                select(func.sum(Transaction.stars_paid))
                .where(
                    and_(
                        Transaction.type == TransactionTypeEnum.PURCHASE,
                        Transaction.status == TransactionStatusEnum.COMPLETED,
                        Transaction.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
                    )
                )
            )
            
            total_revenue = await session.execute(
                select(func.sum(Transaction.stars_paid))
                .where(
                    and_(
                        Transaction.type == TransactionTypeEnum.PURCHASE,
                        Transaction.status == TransactionStatusEnum.COMPLETED
                    )
                )
            )
            
            return {
                "users": {
                    "total": total_users.scalar() or 0,
                    "active_today": active_today.scalar() or 0,
                    "new_today": new_today.scalar() or 0
                },
                "generations": {
                    "total": total_generations.scalar() or 0,
                    "today": generations_today.scalar() or 0,
                    "pending": pending_generations.scalar() or 0
                },
                "finance": {
                    "revenue_today": revenue_today.scalar() or 0,
                    "total_revenue": total_revenue.scalar() or 0
                }
            }
    
    # ========== Action logging ==========
    
    async def log_user_action(
        self,
        user_id: int,
        action: str,
        category: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Логировать действие пользователя"""
        async with self.async_session() as session:
            action_log = UserAction(
                user_id=user_id,
                action=action[:100],  # Ограничиваем длину
                category=category[:50] if category else None,
                details=details
            )
            session.add(action_log)
            await session.commit()
    
    async def log_admin_action(
        self,
        admin_id: int,
        action: str,
        target_user_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Логировать действие администратора"""
        async with self.async_session() as session:
            log = AdminLog(
                admin_id=admin_id,
                action=action[:100],  # Ограничиваем длину
                target_user_id=target_user_id,
                details=details
            )
            session.add(log)
            await session.commit()

    async def get_failed_generations_with_task_id(self, hours_back: int = 24) -> List[Generation]:
        """
        Получить неудачные генерации с task_id за последние N часов
        
        Args:
            hours_back: Количество часов назад для поиска
            
        Returns:
            Список неудачных генераций с task_id
        """
        async with self.async_session() as session:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
            
            result = await session.execute(
                select(Generation)
                .where(
                    Generation.status == GenerationStatusEnum.FAILED,
                    Generation.task_id.isnot(None),
                    Generation.created_at >= cutoff_time
                )
                .order_by(Generation.created_at.desc())
            )
            
            return result.scalars().all()
    
    async def get_generations_by_task_ids(self, task_ids: List[str]) -> List[Generation]:
        """
        Получить генерации по списку task_id
        
        Args:
            task_ids: Список task_id для поиска
            
        Returns:
            Список генераций
        """
        if not task_ids:
            return []
            
        async with self.async_session() as session:
            result = await session.execute(
                select(Generation)
                .where(Generation.task_id.in_(task_ids))
            )
            
            return result.scalars().all()

# Singleton экземпляр
db = DatabaseService()

# Функция инициализации БД
async def init_database():
    """Инициализация базы данных"""
    await db.create_tables()
    logger.info("Database initialized successfully")