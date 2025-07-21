"""
Тесты для админских обработчиков
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram import Bot
from aiogram.types import CallbackQuery, User as TelegramUser, Message, Chat

# Импортируем тестируемые функции
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.handlers.admin import (
    show_admin_stats,
    admin_broadcast,
    give_credits,
    process_credits_change,
    broadcast_to_users,
    admin_panel
)
from core.config import settings


class TestAdminHandlers:
    """Тесты админских обработчиков"""
    
    @pytest.fixture
    def mock_bot(self):
        """Мок бота"""
        bot = AsyncMock(spec=Bot)
        bot.id = 12345
        bot.username = "test_bot"
        return bot
    
    @pytest.fixture
    def mock_admin_user(self):
        """Мок админского пользователя"""
        return TelegramUser(
            id=settings.ADMIN_IDS[0] if settings.ADMIN_IDS else 123456789,
            is_bot=False,
            first_name="Admin",
            username="admin_user"
        )
    
    @pytest.fixture
    def mock_chat(self):
        """Мок чата"""
        return Chat(id=123456789, type="private")
    
    @pytest.fixture
    def mock_callback_query(self, mock_bot, mock_admin_user, mock_chat):
        """Мок callback query"""
        callback = AsyncMock(spec=CallbackQuery)
        callback.from_user = mock_admin_user
        callback.message = AsyncMock()
        callback.message.chat = mock_chat
        callback.bot = mock_bot
        callback.data = "admin_stats"
        callback.answer = AsyncMock()
        return callback
    
    @pytest.fixture
    def mock_message(self, mock_bot, mock_admin_user, mock_chat):
        """Мок сообщения"""
        message = AsyncMock(spec=Message)
        message.from_user = mock_admin_user
        message.chat = mock_chat
        message.bot = mock_bot
        message.answer = AsyncMock()
        return message

    @pytest.mark.asyncio
    async def test_admin_stats_handler(self, mock_callback_query):
        """Тест обработчика статистики админа"""
        
        # Мокаем базу данных
        mock_stats = {
            'users': {'total': 100, 'active_today': 50, 'new_today': 10},
            'generations': {'total': 500, 'today': 25, 'pending': 5},
            'finance': {'revenue_today': 1000, 'total_revenue': 50000}
        }
        
        with patch('bot.handlers.admin.db') as mock_db, \
             patch('bot.handlers.admin.BaseHandler') as mock_base_handler:
            
            mock_db.get_bot_statistics.return_value = mock_stats
            mock_base_handler.get_user_and_translator.return_value = (
                MagicMock(language_code='ru'), 
                MagicMock()
            )
            mock_base_handler.answer_callback = AsyncMock()
            
            # Вызываем обработчик
            await show_admin_stats(mock_callback_query)
            
            # Проверяем, что функции были вызваны
            mock_db.get_bot_statistics.assert_called_once()
            mock_base_handler.get_user_and_translator.assert_called_once_with(mock_callback_query)
            mock_callback_query.message.edit_text.assert_called_once()
            mock_base_handler.answer_callback.assert_called_once_with(mock_callback_query)

    @pytest.mark.asyncio
    async def test_admin_broadcast_handler(self, mock_callback_query):
        """Тест обработчика рассылки"""
        
        with patch('bot.handlers.admin.BaseHandler') as mock_base_handler, \
             patch('aiogram.fsm.context.FSMContext') as mock_state:
            
            mock_base_handler.get_user_and_translator.return_value = (
                MagicMock(language_code='ru'), 
                MagicMock()
            )
            mock_base_handler.answer_callback = AsyncMock()
            mock_state_instance = AsyncMock()
            
            # Вызываем обработчик
            await admin_broadcast(mock_callback_query, mock_state_instance)
            
            # Проверяем, что состояние было установлено
            mock_state_instance.set_state.assert_called_once()
            mock_callback_query.message.edit_text.assert_called_once()
            mock_base_handler.answer_callback.assert_called_once_with(mock_callback_query)

    @pytest.mark.asyncio
    async def test_give_credits_handler(self, mock_callback_query):
        """Тест обработчика выдачи кредитов"""
        
        with patch('bot.handlers.admin.BaseHandler') as mock_base_handler, \
             patch('aiogram.fsm.context.FSMContext') as mock_state:
            
            mock_base_handler.get_user_and_translator.return_value = (
                MagicMock(language_code='ru'), 
                MagicMock()
            )
            mock_base_handler.answer_callback = AsyncMock()
            mock_state_instance = AsyncMock()
            
            # Вызываем обработчик
            await give_credits(mock_callback_query, mock_state_instance)
            
            # Проверяем результат
            mock_state_instance.set_state.assert_called_once()
            mock_callback_query.message.edit_text.assert_called_once()
            mock_base_handler.answer_callback.assert_called_once_with(mock_callback_query)

    @pytest.mark.asyncio
    async def test_process_credits_change_success(self):
        """Тест успешного изменения кредитов"""
        
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.telegram_id = 123456789
        mock_user.balance = 100
        mock_user.total_bought = 0
        mock_user.total_spent = 0
        
        mock_bot = AsyncMock()
        
        with patch('bot.handlers.admin.db') as mock_db:
            mock_session = AsyncMock()
            mock_session.get.return_value = mock_user
            mock_session.commit = AsyncMock()
            mock_db.async_session.return_value.__aenter__.return_value = mock_session
            mock_db.log_admin_action = AsyncMock()
            
            # Тестируем увеличение баланса
            result = await process_credits_change(
                user_id=1,
                amount=50,
                admin_id=123456789,
                bot=mock_bot
            )
            
            # Проверяем результат
            assert result is True
            assert mock_user.balance == 150
            assert mock_user.total_bought == 50
            mock_session.commit.assert_called_once()
            mock_db.log_admin_action.assert_called_once()
            mock_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_credits_change_user_not_found(self):
        """Тест изменения кредитов для несуществующего пользователя"""
        
        mock_bot = AsyncMock()
        
        with patch('bot.handlers.admin.db') as mock_db:
            mock_session = AsyncMock()
            mock_session.get.return_value = None  # Пользователь не найден
            mock_db.async_session.return_value.__aenter__.return_value = mock_session
            
            result = await process_credits_change(
                user_id=999,
                amount=50,
                admin_id=123456789,
                bot=mock_bot
            )
            
            # Проверяем результат
            assert result is False

    @pytest.mark.asyncio
    async def test_broadcast_to_users_success(self):
        """Тест успешной рассылки"""
        
        mock_users = [
            MagicMock(telegram_id=111),
            MagicMock(telegram_id=222),
            MagicMock(telegram_id=333)
        ]
        
        mock_bot = AsyncMock()
        
        with patch('bot.handlers.admin.db') as mock_db:
            mock_db.get_all_users.return_value = mock_users
            
            success_count = await broadcast_to_users(
                bot=mock_bot,
                admin_id=123456789,
                message_id=456
            )
            
            # Проверяем результат
            assert success_count == 3
            assert mock_bot.copy_message.call_count == 3

    @pytest.mark.asyncio
    async def test_broadcast_to_users_with_errors(self):
        """Тест рассылки с ошибками"""
        
        mock_users = [
            MagicMock(telegram_id=111),
            MagicMock(telegram_id=222),  # Этот пользователь вызовет ошибку
            MagicMock(telegram_id=333)
        ]
        
        mock_bot = AsyncMock()
        
        # Настраиваем мок так, чтобы второй вызов вызывал исключение
        mock_bot.copy_message.side_effect = [
            None,  # Первый вызов успешен
            Exception("Bot was blocked by the user"),  # Второй вызов с ошибкой
            None   # Третий вызов успешен
        ]
        
        with patch('bot.handlers.admin.db') as mock_db:
            mock_db.get_all_users.return_value = mock_users
            
            success_count = await broadcast_to_users(
                bot=mock_bot,
                admin_id=123456789,
                message_id=456
            )
            
            # Проверяем результат
            assert success_count == 2  # Должно быть 2 успешных
            assert mock_bot.copy_message.call_count == 3

    @pytest.mark.asyncio
    async def test_admin_panel_handler(self, mock_message):
        """Тест обработчика админ панели"""
        
        with patch('bot.handlers.admin.BaseHandler') as mock_base_handler:
            mock_base_handler.get_user_and_translator.return_value = (
                MagicMock(language_code='ru'), 
                MagicMock()
            )
            
            # Вызываем обработчик
            await admin_panel(mock_message)
            
            # Проверяем, что сообщение было отправлено
            mock_message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_admin_handlers_integration():
    """Интеграционный тест админских обработчиков"""
    
    # Этот тест проверяет взаимодействие между различными обработчиками
    
    mock_bot = AsyncMock()
    mock_admin_id = 123456789
    
    # Мокаем callback query для статистики
    mock_stats_callback = AsyncMock()
    mock_stats_callback.from_user.id = mock_admin_id
    mock_stats_callback.data = "admin_stats"
    mock_stats_callback.message.edit_text = AsyncMock()
    mock_stats_callback.answer = AsyncMock()
    
    # Мокаем callback query для рассылки
    mock_broadcast_callback = AsyncMock()
    mock_broadcast_callback.from_user.id = mock_admin_id
    mock_broadcast_callback.data = "admin_broadcast"
    mock_broadcast_callback.message.edit_text = AsyncMock()
    mock_broadcast_callback.answer = AsyncMock()
    
    with patch('bot.handlers.admin.db') as mock_db, \
         patch('bot.handlers.admin.BaseHandler') as mock_base_handler, \
         patch('core.config.settings.ADMIN_IDS', [mock_admin_id]):
        
        # Настраиваем моки
        mock_stats = {
            'users': {'total': 100, 'active_today': 50, 'new_today': 10},
            'generations': {'total': 500, 'today': 25, 'pending': 5},
            'finance': {'revenue_today': 1000, 'total_revenue': 50000}
        }
        
        mock_db.get_bot_statistics.return_value = mock_stats
        mock_base_handler.get_user_and_translator.return_value = (
            MagicMock(language_code='ru'), 
            MagicMock()
        )
        mock_base_handler.answer_callback = AsyncMock()
        
        # Тестируем последовательность вызовов
        await show_admin_stats(mock_stats_callback)
        await admin_broadcast(mock_broadcast_callback, AsyncMock())
        
        # Проверяем, что все функции были вызваны правильно
        mock_db.get_bot_statistics.assert_called_once()
        mock_stats_callback.message.edit_text.assert_called_once()
        mock_broadcast_callback.message.edit_text.assert_called_once()


if __name__ == "__main__":
    # Для запуска тестов: python -m pytest tests/test_admin_handlers.py -v
    pytest.main([__file__, "-v"])
