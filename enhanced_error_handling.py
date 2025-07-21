# Enhanced error handling functions to be added to admin.py

async def safe_db_operation(operation_name: str, operation_func, *args, **kwargs):
    """
    Безопасная обертка для DB операций с логированием
    """
    try:
        result = await operation_func(*args, **kwargs)
        logger.info(f"DB operation '{operation_name}' completed successfully")
        return result, None
    except Exception as e:
        error_msg = f"DB operation '{operation_name}' failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return None, error_msg

async def safe_api_call(api_name: str, api_func, *args, **kwargs):
    """
    Безопасная обертка для API вызовов
    """
    try:
        result = await api_func(*args, **kwargs)
        logger.info(f"API call '{api_name}' completed successfully")
        return result, None
    except Exception as e:
        error_msg = f"API call '{api_name}' failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return None, error_msg

async def safe_file_operation(file_operation: str, file_func, *args, **kwargs):
    """
    Безопасная обертка для файловых операций
    """
    try:
        result = await file_func(*args, **kwargs)
        logger.info(f"File operation '{file_operation}' completed successfully")
        return result, None
    except Exception as e:
        error_msg = f"File operation '{file_operation}' failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return None, error_msg

# Улучшенная функция для обработки баланса с дополнительными проверками
async def enhanced_process_credits_change(
    user_id: int,
    amount: int,
    admin_id: int,
    bot
) -> tuple[bool, str]:
    """Обработать изменение баланса пользователя с улучшенной обработкой ошибок"""
    
    # Валидация входных данных
    if not isinstance(user_id, int) or user_id <= 0:
        return False, "Неверный ID пользователя"
    
    if not isinstance(amount, int) or amount == 0:
        return False, "Неверное количество кредитов"
    
    if abs(amount) > 100000:  # Защита от слишком больших значений
        return False, "Слишком большое количество кредитов (макс. 100,000)"
    
    operation_name = f"change_credits_user_{user_id}_amount_{amount}"
    
    try:
        async with db.async_session() as session:
            # Получаем пользователя с блокировкой для избежания race conditions
            user = await session.get(User, user_id, populate_existing=True)
            if not user:
                logger.warning(f"User {user_id} not found for credits change by admin {admin_id}")
                return False, "Пользователь не найден"
            
            old_balance = user.balance
            new_balance = max(0, user.balance + amount)
            
            # Проверяем, что баланс не станет отрицательным при списании
            if amount < 0 and user.balance + amount < 0:
                logger.warning(f"Attempted to set negative balance for user {user_id}: {user.balance} + {amount}")
                new_balance = 0
            
            user.balance = new_balance
            
            # Обновляем статистику
            if amount > 0:
                user.total_bought += amount
            else:
                user.total_spent += abs(amount)
            
            await session.commit()
            
            # Логируем действие в базу данных
            try:
                await db.log_admin_action(
                    admin_id=admin_id,
                    action="give_credits",
                    target_user_id=user.telegram_id,
                    details=f"Amount: {amount}, Balance: {old_balance} -> {new_balance}",
                    additional_data={
                        "old_balance": old_balance,
                        "new_balance": new_balance,
                        "amount": amount
                    }
                )
            except Exception as log_error:
                logger.error(f"Failed to log admin action: {log_error}")
                # Не прерываем операцию из-за ошибки логирования
            
            # Уведомляем пользователя с обработкой ошибок
            try:
                action_text = "пополнен" if amount > 0 else "списан"
                text = f"💰 Ваш баланс {action_text} на {abs(amount)} кредитов\n"
                text += f"Новый баланс: {new_balance} кредитов"
                await bot.send_message(user.telegram_id, text)
                logger.info(f"Notification sent to user {user.telegram_id} about balance change")
            except Exception as notif_error:
                logger.error(f"Failed to notify user {user.telegram_id}: {notif_error}")
                # Не прерываем операцию из-за ошибки уведомления
            
            logger.info(f"Credits changed successfully for user {user_id}: {old_balance} -> {new_balance}")
            return True, f"Баланс успешно изменен: {old_balance} -> {new_balance} кредитов"
            
    except Exception as e:
        error_msg = f"Критическая ошибка при изменении баланса пользователя {user_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, "Произошла ошибка при изменении баланса"

# Улучшенная функция рассылки с дополнительными проверками
async def enhanced_broadcast_to_users(bot, admin_id: int, message_id: int) -> tuple[int, int, str]:
    """Выполнить рассылку сообщения с улучшенной обработкой ошибок"""
    
    success_count = 0
    error_count = 0
    errors_log = []
    
    try:
        # Получаем всех пользователей с обработкой ошибок
        users_result, error_msg = await safe_db_operation(
            "get_all_users_for_broadcast",
            db.get_all_users
        )
        
        if users_result is None:
            return 0, 0, f"Ошибка получения пользователей: {error_msg}"
        
        users = users_result
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
                error_msg = f"User {user.telegram_id}: {str(e)}"
                errors_log.append(error_msg)
                logger.error(f"Broadcast error for user {user.telegram_id}: {e}")
                
                # Если пользователь заблокировал бота, помечаем это
                if "bot was blocked" in str(e).lower():
                    try:
                        await db.update_user_status(user.telegram_id, is_blocked=True)
                    except:
                        pass  # Не критично
        
        # Логируем результат рассылки
        result_msg = f"Рассылка завершена: {success_count} успешно, {error_count} ошибок"
        logger.info(f"Broadcast completed: {success_count}/{total_users} successful")
        
        # Сохраняем лог ошибок, если они есть
        if errors_log:
            try:
                await db.log_admin_action(
                    admin_id=admin_id,
                    action="broadcast_errors",
                    details=f"Errors: {error_count}, Success: {success_count}",
                    additional_data={"errors": errors_log[:50]}  # Ограничиваем количество ошибок
                )
            except:
                pass  # Не критично
        
        return success_count, error_count, result_msg
        
    except Exception as e:
        error_msg = f"Критическая ошибка рассылки: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return success_count, error_count, error_msg
