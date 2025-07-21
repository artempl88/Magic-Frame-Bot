#!/usr/bin/env python3

import re

def enhance_error_handling():
    # Read the admin.py file
    with open('./bot/handlers/admin.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace the process_credits_change function with enhanced version
    old_function_pattern = r'async def process_credits_change\([\s\S]*?^    return success_count'
    
    enhanced_function = '''async def process_credits_change(
    user_id: int,
    amount: int,
    admin_id: int,
    bot
) -> bool:
    """Обработать изменение баланса пользователя с улучшенной обработкой ошибок"""
    
    # Валидация входных данных
    if not isinstance(user_id, int) or user_id <= 0:
        logger.error(f"Invalid user_id: {user_id}")
        return False
    
    if not isinstance(amount, int) or amount == 0:
        logger.error(f"Invalid amount: {amount}")
        return False
    
    if abs(amount) > 100000:  # Защита от слишком больших значений
        logger.error(f"Amount too large: {amount}")
        return False
    
    try:
        async with db.async_session() as session:
            # Получаем пользователя
            user = await session.get(User, user_id)
            if not user:
                logger.warning(f"User {user_id} not found for credits change by admin {admin_id}")
                return False
            
            old_balance = user.balance
            new_balance = max(0, user.balance + amount)
            
            # Проверяем, что баланс не станет отрицательным при списании
            if amount < 0 and user.balance + amount < 0:
                logger.warning(f"Attempted to set negative balance for user {user_id}: {user.balance} + {amount}")
                new_balance = 0
            
            user.balance = new_balance
            
            if amount > 0:
                user.total_bought += amount
            else:
                user.total_spent += abs(amount)
            
            await session.commit()
            
            # Логируем действие с обработкой ошибок
            try:
                await db.log_admin_action(
                    admin_id=admin_id,
                    action="give_credits",
                    target_user_id=user.telegram_id,
                    details=f"Amount: {amount}, Balance: {old_balance} -> {new_balance}"
                )
            except Exception as log_error:
                logger.error(f"Failed to log admin action: {log_error}")
                # Не прерываем операцию из-за ошибки логирования
            
            # Уведомляем пользователя с обработкой ошибок
            try:
                action_text = "пополнен" if amount > 0 else "списан"
                text = f"💰 Ваш баланс {action_text} на {abs(amount)} кредитов\\n"
                text += f"Новый баланс: {new_balance} кредитов"
                await bot.send_message(user.telegram_id, text)
                logger.info(f"Notification sent to user {user.telegram_id} about balance change")
            except Exception as notif_error:
                logger.error(f"Failed to notify user {user.telegram_id}: {notif_error}")
                # Не прерываем операцию из-за ошибки уведомления
            
            logger.info(f"Credits changed successfully for user {user_id}: {old_balance} -> {new_balance}")
            return True
            
    except Exception as e:
        logger.error(f"Critical error changing user {user_id} balance: {e}", exc_info=True)
        return False


async def broadcast_to_users(bot, admin_id: int, message_id: int) -> int:
    """Выполнить рассылку сообщения с улучшенной обработкой ошибок"""
    success_count = 0
    error_count = 0
    
    try:
        users = await db.get_all_users()
        total_users = len(users)
        
        logger.info(f"Starting broadcast to {total_users} users")
        
        for i, user in enumerate(users):
            try:
                await bot.copy_message(
                    chat_id=user.telegram_id,
                    from_chat_id=admin_id,
                    message_id=message_id
                )
                success_count += 1
                
                # Антифлуд пауза
                await asyncio.sleep(0.05)
                
                # Логируем прогресс каждые 100 пользователей
                if (i + 1) % 100 == 0:
                    logger.info(f"Broadcast progress: {i + 1}/{total_users} users processed")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Broadcast error for user {user.telegram_id}: {e}")
                
                # Если пользователь заблокировал бота, помечаем это
                if "bot was blocked" in str(e).lower():
                    try:
                        # Можно добавить обновление статуса пользователя
                        pass
                    except:
                        pass  # Не критично
        
        logger.info(f"Broadcast completed: {success_count}/{total_users} successful, {error_count} errors")
        return success_count
        
    except Exception as e:
        logger.error(f"Critical broadcast error: {e}", exc_info=True)'''
    
    # Replace the old function
    content = re.sub(old_function_pattern, enhanced_function, content, flags=re.MULTILINE)
    
    # Write the updated content
    with open('./bot/handlers/admin.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Enhanced error handling for critical functions")

if __name__ == "__main__":
    enhance_error_handling()
