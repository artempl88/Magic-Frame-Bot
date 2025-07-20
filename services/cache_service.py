import json
import logging
from typing import Any, Optional, Union, Callable, Dict, List, Set
from datetime import timedelta
import asyncio
import redis.asyncio as redis
from functools import wraps
import inspect

from core.config import settings

logger = logging.getLogger(__name__)

class CacheService:
    """Сервис для работы с кешем Redis"""
    
    def __init__(self, redis_url: str = None, prefix: str = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis: Optional[redis.Redis] = None
        self.prefix = prefix or getattr(settings, 'CACHE_PREFIX', 'magic_frame')
        self._connection_retries = 3
        self._connection_timeout = 5
    
    async def connect(self):
        """Подключение к Redis с повторными попытками"""
        if self._redis:
            return
        
        for attempt in range(self._connection_retries):
            try:
                self._redis = await redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=self._connection_timeout,
                    socket_timeout=self._connection_timeout,
                    retry_on_timeout=True,
                    retry_on_error=[ConnectionError, TimeoutError]
                )
                
                # Проверяем соединение
                await self._redis.ping()
                logger.info("Connected to Redis successfully")
                return
                
            except Exception as e:
                logger.error(f"Redis connection attempt {attempt + 1} failed: {e}")
                if attempt == self._connection_retries - 1:
                    logger.critical("Failed to connect to Redis after all retries")
                    raise
                await asyncio.sleep(1)
    
    async def disconnect(self):
        """Отключение от Redis"""
        if self._redis:
            await self._redis.close()
            self._redis = None
            logger.info("Disconnected from Redis")
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
    
    def _make_key(self, key: str) -> str:
        """Создание ключа с префиксом"""
        return f"{self.prefix}:{key}"
    
    async def _ensure_connected(self):
        """Убедиться, что подключение активно"""
        if not self._redis:
            await self.connect()
        else:
            try:
                await self._redis.ping()
            except (ConnectionError, TimeoutError):
                logger.warning("Redis connection lost, reconnecting...")
                self._redis = None
                await self.connect()
    
    async def get(self, key: str, default: Any = None) -> Optional[Any]:
        """Получить значение из кеша"""
        try:
            await self._ensure_connected()
            
            value = await self._redis.get(self._make_key(key))
            if value is None:
                return default
            
            # Пробуем десериализовать JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
                
        except Exception as e:
            logger.error(f"Cache get error for key '{key}': {e}")
            return default
    
    async def set(
        self,
        key: str,
        value: Any,
        expire: Union[int, timedelta] = None
    ) -> bool:
        """
        Сохранить значение в кеш
        
        Args:
            key: Ключ
            value: Значение
            expire: Время жизни в секундах или timedelta
        """
        try:
            await self._ensure_connected()
            
            # Сериализуем в JSON если это не строка
            if not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False, default=str)
            
            # Конвертируем timedelta в секунды
            if isinstance(expire, timedelta):
                expire = int(expire.total_seconds())
            
            # Используем значение по умолчанию из настроек
            if expire is None:
                expire = getattr(settings, 'CACHE_TTL', 3600)
            
            result = await self._redis.set(
                self._make_key(key),
                value,
                ex=expire if expire > 0 else None
            )
            return bool(result)
            
        except Exception as e:
            logger.error(f"Cache set error for key '{key}': {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Удалить значение из кеша"""
        try:
            await self._ensure_connected()
            result = await self._redis.delete(self._make_key(key))
            return bool(result)
        except Exception as e:
            logger.error(f"Cache delete error for key '{key}': {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Проверить существование ключа"""
        try:
            await self._ensure_connected()
            return bool(await self._redis.exists(self._make_key(key)))
        except Exception as e:
            logger.error(f"Cache exists error for key '{key}': {e}")
            return False
    
    async def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """Увеличить значение счетчика"""
        try:
            await self._ensure_connected()
            return await self._redis.incrby(self._make_key(key), amount)
        except Exception as e:
            logger.error(f"Cache incr error for key '{key}': {e}")
            return None
    
    async def decr(self, key: str, amount: int = 1) -> Optional[int]:
        """Уменьшить значение счетчика"""
        try:
            await self._ensure_connected()
            return await self._redis.decrby(self._make_key(key), amount)
        except Exception as e:
            logger.error(f"Cache decr error for key '{key}': {e}")
            return None
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Установить время жизни ключа"""
        try:
            await self._ensure_connected()
            return bool(await self._redis.expire(self._make_key(key), seconds))
        except Exception as e:
            logger.error(f"Cache expire error for key '{key}': {e}")
            return False
    
    async def ttl(self, key: str) -> int:
        """Получить оставшееся время жизни ключа"""
        try:
            await self._ensure_connected()
            ttl = await self._redis.ttl(self._make_key(key))
            return ttl if ttl >= 0 else -1
        except Exception as e:
            logger.error(f"Cache ttl error for key '{key}': {e}")
            return -1
    
    # ========== Методы для работы со списками ==========
    
    async def lpush(self, key: str, *values) -> Optional[int]:
        """Добавить элементы в начало списка"""
        try:
            await self._ensure_connected()
            
            # Сериализуем значения
            serialized_values = []
            for value in values:
                if not isinstance(value, str):
                    value = json.dumps(value, ensure_ascii=False, default=str)
                serialized_values.append(value)
            
            return await self._redis.lpush(self._make_key(key), *serialized_values)
        except Exception as e:
            logger.error(f"Cache lpush error for key '{key}': {e}")
            return None
    
    async def rpush(self, key: str, *values) -> Optional[int]:
        """Добавить элементы в конец списка"""
        try:
            await self._ensure_connected()
            
            # Сериализуем значения
            serialized_values = []
            for value in values:
                if not isinstance(value, str):
                    value = json.dumps(value, ensure_ascii=False, default=str)
                serialized_values.append(value)
            
            return await self._redis.rpush(self._make_key(key), *serialized_values)
        except Exception as e:
            logger.error(f"Cache rpush error for key '{key}': {e}")
            return None
    
    async def lrange(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        """Получить элементы списка"""
        try:
            await self._ensure_connected()
            values = await self._redis.lrange(self._make_key(key), start, end)
            
            # Десериализуем значения
            result = []
            for value in values:
                try:
                    result.append(json.loads(value))
                except json.JSONDecodeError:
                    result.append(value)
            
            return result
        except Exception as e:
            logger.error(f"Cache lrange error for key '{key}': {e}")
            return []
    
    async def lpop(self, key: str, count: int = 1) -> Optional[Any]:
        """Извлечь элементы из начала списка"""
        try:
            await self._ensure_connected()
            
            if count == 1:
                value = await self._redis.lpop(self._make_key(key))
                if value is None:
                    return None
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            else:
                values = await self._redis.lpop(self._make_key(key), count)
                result = []
                for value in values:
                    try:
                        result.append(json.loads(value))
                    except json.JSONDecodeError:
                        result.append(value)
                return result
                
        except Exception as e:
            logger.error(f"Cache lpop error for key '{key}': {e}")
            return None
    
    async def rpop(self, key: str, count: int = 1) -> Optional[Any]:
        """Извлечь элементы из конца списка"""
        try:
            await self._ensure_connected()
            
            if count == 1:
                value = await self._redis.rpop(self._make_key(key))
                if value is None:
                    return None
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            else:
                values = await self._redis.rpop(self._make_key(key), count)
                result = []
                for value in values:
                    try:
                        result.append(json.loads(value))
                    except json.JSONDecodeError:
                        result.append(value)
                return result
                
        except Exception as e:
            logger.error(f"Cache rpop error for key '{key}': {e}")
            return None
    
    async def llen(self, key: str) -> int:
        """Получить длину списка"""
        try:
            await self._ensure_connected()
            return await self._redis.llen(self._make_key(key))
        except Exception as e:
            logger.error(f"Cache llen error for key '{key}': {e}")
            return 0
    
    # ========== Методы для работы с хешами ==========
    
    async def hget(self, key: str, field: str, default: Any = None) -> Optional[Any]:
        """Получить значение поля хеша"""
        try:
            await self._ensure_connected()
            value = await self._redis.hget(self._make_key(key), field)
            if value is None:
                return default
            
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
                
        except Exception as e:
            logger.error(f"Cache hget error for key '{key}', field '{field}': {e}")
            return default
    
    async def hset(self, key: str, field: str, value: Any) -> bool:
        """Установить значение поля хеша"""
        try:
            await self._ensure_connected()
            
            if not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False, default=str)
            
            result = await self._redis.hset(self._make_key(key), field, value)
            return bool(result)
            
        except Exception as e:
            logger.error(f"Cache hset error for key '{key}', field '{field}': {e}")
            return False
    
    async def hdel(self, key: str, *fields) -> int:
        """Удалить поля хеша"""
        try:
            await self._ensure_connected()
            return await self._redis.hdel(self._make_key(key), *fields)
        except Exception as e:
            logger.error(f"Cache hdel error for key '{key}': {e}")
            return 0
    
    async def hgetall(self, key: str) -> Dict[str, Any]:
        """Получить все поля хеша"""
        try:
            await self._ensure_connected()
            hash_data = await self._redis.hgetall(self._make_key(key))
            
            # Десериализуем значения
            result = {}
            for field, value in hash_data.items():
                try:
                    result[field] = json.loads(value)
                except json.JSONDecodeError:
                    result[field] = value
            
            return result
        except Exception as e:
            logger.error(f"Cache hgetall error for key '{key}': {e}")
            return {}
    
    async def hexists(self, key: str, field: str) -> bool:
        """Проверить существование поля хеша"""
        try:
            await self._ensure_connected()
            return bool(await self._redis.hexists(self._make_key(key), field))
        except Exception as e:
            logger.error(f"Cache hexists error for key '{key}', field '{field}': {e}")
            return False
    
    # ========== Методы для работы с множествами ==========
    
    async def sadd(self, key: str, *values) -> int:
        """Добавить элементы в множество"""
        try:
            await self._ensure_connected()
            
            # Сериализуем значения
            serialized_values = []
            for value in values:
                if not isinstance(value, str):
                    value = json.dumps(value, ensure_ascii=False, default=str)
                serialized_values.append(value)
            
            return await self._redis.sadd(self._make_key(key), *serialized_values)
        except Exception as e:
            logger.error(f"Cache sadd error for key '{key}': {e}")
            return 0
    
    async def smembers(self, key: str) -> Set[Any]:
        """Получить все элементы множества"""
        try:
            await self._ensure_connected()
            members = await self._redis.smembers(self._make_key(key))
            
            # Десериализуем значения
            result = set()
            for member in members:
                try:
                    result.add(json.loads(member))
                except json.JSONDecodeError:
                    result.add(member)
            
            return result
        except Exception as e:
            logger.error(f"Cache smembers error for key '{key}': {e}")
            return set()
    
    async def srem(self, key: str, *values) -> int:
        """Удалить элементы из множества"""
        try:
            await self._ensure_connected()
            
            # Сериализуем значения
            serialized_values = []
            for value in values:
                if not isinstance(value, str):
                    value = json.dumps(value, ensure_ascii=False, default=str)
                serialized_values.append(value)
            
            return await self._redis.srem(self._make_key(key), *serialized_values)
        except Exception as e:
            logger.error(f"Cache srem error for key '{key}': {e}")
            return 0
    
    async def sismember(self, key: str, value: Any) -> bool:
        """Проверить наличие элемента в множестве"""
        try:
            await self._ensure_connected()
            
            if not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False, default=str)
            
            return bool(await self._redis.sismember(self._make_key(key), value))
        except Exception as e:
            logger.error(f"Cache sismember error for key '{key}': {e}")
            return False
    
    # ========== Дополнительные методы ==========
    
    async def clear_pattern(self, pattern: str) -> int:
        """Удалить ключи по паттерну"""
        try:
            await self._ensure_connected()
            
            # Ищем ключи по паттерну
            keys = await self._redis.keys(self._make_key(pattern))
            if keys:
                return await self._redis.delete(*keys)
            return 0
            
        except Exception as e:
            logger.error(f"Cache clear_pattern error for pattern '{pattern}': {e}")
            return 0
    
    async def clear_user_cache(self, user_id: int) -> int:
        """Очистить кеш пользователя"""
        return await self.clear_pattern(f"user:{user_id}:*")
    
    async def clear_all(self) -> bool:
        """Очистить весь кеш (осторожно!)"""
        try:
            await self._ensure_connected()
            await self._redis.flushdb()
            logger.warning("All cache cleared!")
            return True
        except Exception as e:
            logger.error(f"Cache clear_all error: {e}")
            return False
    
    async def get_info(self) -> Dict[str, Any]:
        """Получить информацию о Redis"""
        try:
            await self._ensure_connected()
            info = await self._redis.info()
            return {
                'connected_clients': info.get('connected_clients', 0),
                'used_memory_human': info.get('used_memory_human', '0B'),
                'keyspace_hits': info.get('keyspace_hits', 0),
                'keyspace_misses': info.get('keyspace_misses', 0),
                'total_commands_processed': info.get('total_commands_processed', 0),
            }
        except Exception as e:
            logger.error(f"Cache get_info error: {e}")
            return {}


# ========== Декораторы для кеширования ==========

def cached(
    key: str = None,
    expire: Union[int, timedelta] = None,
    prefix: str = "func"
):
    """
    Декоратор для кеширования результатов функций
    
    Args:
        key: Ключ кеша (если None, генерируется автоматически)
        expire: Время жизни кеша
        prefix: Префикс для ключа
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Генерируем ключ кеша
            if key:
                cache_key = key
            else:
                # Автоматическая генерация ключа на основе функции и аргументов
                func_name = func.__name__
                args_str = "_".join(str(arg) for arg in args if not inspect.iscoroutine(arg))
                kwargs_str = "_".join(f"{k}={v}" for k, v in kwargs.items())
                cache_key = f"{prefix}:{func_name}:{args_str}:{kwargs_str}"
            
            # Пытаемся получить из кеша
            cached_result = await cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for key: {cache_key}")
                return cached_result
            
            # Выполняем функцию
            if inspect.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Сохраняем в кеш
            await cache.set(cache_key, result, expire)
            logger.debug(f"Cache set for key: {cache_key}")
            
            return result
        return wrapper
    return decorator


def cache_user_data(expire: Union[int, timedelta] = 1800):
    """
    Декоратор для кеширования пользовательских данных
    
    Args:
        expire: Время жизни кеша (по умолчанию 30 минут)
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Ищем user_id в аргументах
            user_id = None
            if args and isinstance(args[0], (int, str)):
                user_id = args[0]
            elif 'user_id' in kwargs:
                user_id = kwargs['user_id']
            elif 'telegram_id' in kwargs:
                user_id = kwargs['telegram_id']
            
            if not user_id:
                # Если не можем определить пользователя, выполняем без кеша
                if inspect.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
            
            # Генерируем ключ кеша
            func_name = func.__name__
            cache_key = f"user:{user_id}:{func_name}"
            
            # Пытаемся получить из кеша
            cached_result = await cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Выполняем функцию
            if inspect.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Сохраняем в кеш
            await cache.set(cache_key, result, expire)
            
            return result
        return wrapper
    return decorator


# ========== Singleton экземпляр ==========

# Создаем единственный экземпляр сервиса кеша
cache = CacheService()

# Функция инициализации кеша
async def init_cache():
    """Инициализация кеша"""
    try:
        await cache.connect()
        logger.info("Cache service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize cache: {e}")

# Функция очистки при завершении
async def cleanup_cache():
    """Очистка кеша при завершении"""
    try:
        await cache.disconnect()
        logger.info("Cache service cleaned up")
    except Exception as e:
        logger.error(f"Failed to cleanup cache: {e}")