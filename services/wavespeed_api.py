import aiohttp
import asyncio
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import base64
from io import BytesIO

from core.config import settings

logger = logging.getLogger(__name__)

@dataclass
class GenerationRequest:
    """Запрос на генерацию видео"""
    model: str
    prompt: str
    duration: int
    seed: int = -1
    aspect_ratio: str = "16:9"
    image: Optional[str] = None
    last_image: Optional[str] = None
    # Параметры для Google Veo3
    negative_prompt: Optional[str] = None
    enable_prompt_expansion: bool = True
    generate_audio: bool = False

@dataclass
class GenerationResult:
    """Результат генерации"""
    task_id: str
    status: str
    video_url: Optional[str] = None
    error: Optional[str] = None
    generation_time: Optional[float] = None

class WaveSpeedAPIError(Exception):
    """Базовое исключение для ошибок API"""
    pass

class WaveSpeedAPI:
    """Клиент для работы с WaveSpeed AI API"""
    
    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or settings.WAVESPEED_API_KEY
        self.base_url = base_url or settings.WAVESPEED_BASE_URL
        self.session: Optional[aiohttp.ClientSession] = None
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    async def __aenter__(self):
        """Вход в контекстный менеджер"""
        self.session = aiohttp.ClientSession(
            headers=self._headers,
            timeout=aiohttp.ClientTimeout(total=300)  # 5 минут таймаут
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Выход из контекстного менеджера"""
        if self.session:
            await self.session.close()
    
    def _get_session(self) -> aiohttp.ClientSession:
        """Получить сессию или создать новую"""
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=300)
            )
        return self.session
    
    async def convert_image_to_base64(self, image_data: bytes) -> str:
        """Конвертировать изображение в base64"""
        return base64.b64encode(image_data).decode('utf-8')
    
    async def submit_generation(self, request: GenerationRequest) -> str:
        """
        Отправить запрос на генерацию видео
        
        Returns:
            task_id: ID задачи для отслеживания статуса
        """
        # Определяем endpoint в зависимости от модели
        if request.model in ["veo3", "veo3-fast"]:
            # Google Veo3 models
            endpoint = f"/api/v3/google/{request.model}"
        else:
            # ByteDance models
            endpoint = f"/api/v3/bytedance/{request.model}"
        
        url = f"{self.base_url}{endpoint}"
        
        # Подготовка данных
        data = {
            "prompt": request.prompt,
        }
        
        # Добавляем параметры в зависимости от модели
        if request.model in ["veo3", "veo3-fast"]:
            # Google Veo3 parameters
            data["duration"] = 8  # Фиксированная длительность для Veo3
            if hasattr(request, 'aspect_ratio') and request.aspect_ratio:
                data["aspect_ratio"] = request.aspect_ratio
            if hasattr(request, 'negative_prompt') and request.negative_prompt:
                data["negative_prompt"] = request.negative_prompt
            if hasattr(request, 'enable_prompt_expansion'):
                data["enable_prompt_expansion"] = getattr(request, 'enable_prompt_expansion', True)
            if hasattr(request, 'generate_audio'):
                data["generate_audio"] = getattr(request, 'generate_audio', False)
            if request.seed and request.seed != -1:
                data["seed"] = request.seed
        else:
            # ByteDance parameters
            data["duration"] = request.duration
            data["seed"] = request.seed
            
            # Добавляем параметры в зависимости от типа генерации
            if request.image:
                data["image"] = request.image
            if request.last_image:
                data["last_image"] = request.last_image
            if "t2v" in request.model:  # Text-to-Video
                data["aspect_ratio"] = request.aspect_ratio
        
        logger.info(f"Submitting generation request to {url}")
        logger.debug(f"Request data: {data}")
        
        try:
            session = self._get_session()
            async with session.post(url, json=data) as response:
                result = await response.json()
                
                if response.status != 200:
                    error_msg = result.get('message', 'Unknown error')
                    logger.error(f"API Error ({response.status}): {error_msg}")
                    raise WaveSpeedAPIError(f"API Error: {error_msg}")
                
                task_id = result['data']['id']
                logger.info(f"Generation task created: {task_id}")
                return task_id
                
        except aiohttp.ClientError as e:
            logger.error(f"Network error: {str(e)}")
            raise WaveSpeedAPIError(f"Network error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            raise WaveSpeedAPIError(f"Unexpected error: {str(e)}")
    
    async def check_status(self, task_id: str) -> GenerationResult:
        """Проверить статус генерации"""
        endpoint = f"/api/v3/predictions/{task_id}/result"
        url = f"{self.base_url}{endpoint}"
        
        try:
            session = self._get_session()
            async with session.get(url) as response:
                result = await response.json()
                
                if response.status != 200:
                    error_msg = result.get('message', 'Unknown error')
                    raise WaveSpeedAPIError(f"API Error: {error_msg}")
                
                data = result['data']
                
                return GenerationResult(
                    task_id=task_id,
                    status=data['status'],
                    video_url=data['outputs'][0] if data.get('outputs') else None,
                    error=data.get('error'),
                    generation_time=data.get('timings', {}).get('inference', 0) / 1000  # мс в секунды
                )
                
        except aiohttp.ClientError as e:
            logger.error(f"Network error checking status: {str(e)}")
            raise WaveSpeedAPIError(f"Network error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error checking status: {str(e)}")
            raise WaveSpeedAPIError(f"Unexpected error: {str(e)}")
    
    async def wait_for_completion(
        self,
        task_id: str,
        max_attempts: int = 180,  # Увеличиваем с 60 до 180 (6 минут вместо 2)
        delay: int = 2,
        progress_callback=None
    ) -> GenerationResult:
        """
        Ожидать завершения генерации
        
        Args:
            task_id: ID задачи
            max_attempts: Максимальное количество попыток (180 = 6 минут)
            delay: Задержка между попытками в секундах
            progress_callback: Функция для обновления прогресса
        """
        start_time = datetime.utcnow()
        last_progress = 0
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        for attempt in range(max_attempts):
            try:
                result = await self.check_status(task_id)
                consecutive_errors = 0  # Сбрасываем счетчик ошибок при успехе
                
                # Определяем прогресс на основе статуса и времени
                progress = self._calculate_progress(result.status, attempt, start_time, max_attempts)
                
                # Обновляем прогресс только если он изменился или достиг 100%
                if progress > last_progress or progress == 100:
                    last_progress = progress
                    logger.debug(f"Progress update: {progress}% (status: {result.status}, attempt: {attempt})")
                    if progress_callback:
                        await progress_callback(progress, result.status)
                
                if result.status == "completed":
                    if progress_callback:
                        await progress_callback(100, "completed")
                    return result
                    
                elif result.status == "failed":
                    error_msg = result.error or "Unknown error"
                    logger.error(f"Generation failed: {error_msg}")
                    raise WaveSpeedAPIError(f"Generation failed: {error_msg}")
                
                # Ждем перед следующей попыткой
                await asyncio.sleep(delay)
                
            except WaveSpeedAPIError:
                raise
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error during wait (attempt {attempt + 1}/{max_attempts}): {str(e)}")
                
                # Если слишком много ошибок подряд, прерываем
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive errors ({consecutive_errors}), stopping")
                    raise WaveSpeedAPIError(f"Too many consecutive errors: {str(e)}")
                
                # Если это последняя попытка, поднимаем ошибку
                if attempt == max_attempts - 1:
                    raise
                
                # Ждем перед повторной попыткой
                await asyncio.sleep(delay)
        
        raise TimeoutError("Generation timeout exceeded")
    
    def _calculate_progress(self, status: str, attempt: int, start_time: datetime, max_attempts: int) -> int:
        """
        Вычислить прогресс на основе статуса и времени
        
        Args:
            status: Статус от API
            attempt: Номер попытки
            start_time: Время начала генерации
            max_attempts: Максимальное количество попыток
            
        Returns:
            Прогресс от 0 до 100
        """
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        max_time = max_attempts * 2  # 2 секунды между попытками
        
        # Минимальная задержка перед показом прогресса
        if elapsed < 2:
            return 0
        
        # Базовый прогресс на основе времени (максимум 85%)
        time_progress = min(int((elapsed - 2) / (max_time - 2) * 85), 85)
        
        # Дополнительный прогресс на основе статуса
        status_progress = 0
        if status == "starting":
            status_progress = 5
        elif status == "processing":
            status_progress = 15
        elif status == "rendering":
            status_progress = 35
        elif status == "finalizing":
            status_progress = 55
        elif status == "completed":
            status_progress = 100
        
        # Комбинируем прогресс, но не превышаем 95% до завершения
        total_progress = max(time_progress, status_progress)
        
        # Ограничиваем максимум 95% до завершения
        if status != "completed":
            total_progress = min(total_progress, 95)
        
        return total_progress
    
    async def generate_video(
        self,
        request: GenerationRequest,
        progress_callback=None
    ) -> GenerationResult:
        """
        Полный цикл генерации видео
        
        Args:
            request: Параметры генерации
            progress_callback: Функция для обновления прогресса
        """
        logger.info(f"Starting video generation: {request.model}")
        
        try:
            # Отправляем запрос
            task_id = await self.submit_generation(request)
            
            # Ждем завершения
            result = await self.wait_for_completion(
                task_id,
                progress_callback=progress_callback
            )
            
            logger.info(f"Generation completed: {task_id}")
            return result
            
        except Exception as e:
            logger.error(f"Generation failed: {str(e)}")
            raise
    
    async def download_video(self, video_url: str, max_retries: int = 3) -> bytes:
        """Скачать готовое видео с повторными попытками"""
        for attempt in range(max_retries):
            try:
                session = self._get_session()
                
                # Увеличиваем timeout для больших файлов
                timeout = aiohttp.ClientTimeout(total=60, connect=10)
                
                async with session.get(video_url, timeout=timeout) as response:
                    if response.status != 200:
                        error_msg = f"HTTP {response.status}: {response.reason}"
                        logger.warning(f"Download attempt {attempt + 1} failed: {error_msg}")
                        
                        if attempt == max_retries - 1:
                            raise WaveSpeedAPIError(f"Failed to download video: {error_msg}")
                        continue
                    
                    # Проверяем размер файла
                    content_length = response.headers.get('content-length')
                    if content_length:
                        file_size = int(content_length)
                        if file_size > 100 * 1024 * 1024:  # 100MB limit
                            raise WaveSpeedAPIError("Video file too large (max 100MB)")
                    
                    video_data = await response.read()
                    
                    # Проверяем, что получили данные
                    if not video_data:
                        raise WaveSpeedAPIError("Empty video data received")
                    
                    # Проверяем, что это действительно видео (простые проверки)
                    if len(video_data) < 1000:  # Минимальный размер для видео
                        raise WaveSpeedAPIError("Invalid video data (too small)")
                    
                    logger.info(f"Video downloaded successfully: {len(video_data)} bytes")
                    return video_data
                
            except asyncio.TimeoutError:
                logger.warning(f"Download attempt {attempt + 1} timed out")
                if attempt == max_retries - 1:
                    raise WaveSpeedAPIError("Download timeout - video file too large or server slow")
                await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
                
            except aiohttp.ClientError as e:
                logger.warning(f"Download attempt {attempt + 1} failed: {str(e)}")
                if attempt == max_retries - 1:
                    raise WaveSpeedAPIError(f"Network error downloading video: {str(e)}")
                await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
                
            except Exception as e:
                logger.error(f"Unexpected error downloading video: {str(e)}")
                if attempt == max_retries - 1:
                    raise WaveSpeedAPIError(f"Failed to download video: {str(e)}")
                await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
        
        raise WaveSpeedAPIError("All download attempts failed")
    
    async def validate_image(self, image_data: bytes) -> bool:
        """Валидация изображения перед отправкой"""
        # Проверка размера
        if len(image_data) > settings.MAX_FILE_SIZE:
            raise ValueError(f"Image too large: {len(image_data)} bytes (max: {settings.MAX_FILE_SIZE})")
        
        # Проверка формата (простая проверка по заголовку)
        if image_data[:2] == b'\xff\xd8':  # JPEG
            return True
        elif image_data[:8] == b'\x89PNG\r\n\x1a\n':  # PNG
            return True
        else:
            raise ValueError("Invalid image format. Only JPEG and PNG are supported.")
    
    async def close(self):
        """Закрыть сессию"""
        if self.session:
            await self.session.close()
            self.session = None

    async def check_completed_generations(self, task_ids: list[str]) -> Dict[str, GenerationResult]:
        """
        Проверить статус нескольких генераций и вернуть завершенные
        
        Args:
            task_ids: Список ID задач для проверки
            
        Returns:
            Словарь {task_id: GenerationResult} только для завершенных генераций
        """
        completed_generations = {}
        
        for task_id in task_ids:
            try:
                result = await self.check_status(task_id)
                if result.status == "completed" and result.video_url:
                    completed_generations[task_id] = result
                    logger.info(f"Found completed generation: {task_id}")
            except Exception as e:
                logger.warning(f"Error checking task {task_id}: {e}")
                continue
        
        return completed_generations
    
    async def recover_lost_videos(self, failed_generations: list) -> list:
        """
        Восстановить видео для неудачных генераций, которые могли быть завершены
        
        Args:
            failed_generations: Список неудачных генераций из БД
            
        Returns:
            Список восстановленных генераций
        """
        recovered = []
        
        # Собираем task_id для проверки
        task_ids = [gen.task_id for gen in failed_generations if gen.task_id]
        
        if not task_ids:
            logger.info("No task IDs to check for recovery")
            return recovered
        
        logger.info(f"Checking {len(task_ids)} failed generations for recovery")
        
        # Проверяем статус всех задач
        completed_results = await self.check_completed_generations(task_ids)
        
        # Обновляем статус в БД для найденных завершенных генераций
        for generation in failed_generations:
            if generation.task_id and generation.task_id in completed_results:
                result = completed_results[generation.task_id]
                
                try:
                    # Обновляем статус в БД
                    from services.database import db
                    await db.update_generation_status(
                        generation.id,
                        'completed',
                        video_url=result.video_url,
                        generation_time=result.generation_time
                    )
                    
                    recovered.append({
                        'generation_id': generation.id,
                        'task_id': generation.task_id,
                        'video_url': result.video_url,
                        'generation_time': result.generation_time
                    })
                    
                    logger.info(f"Recovered video for generation {generation.id}")
                    
                except Exception as e:
                    logger.error(f"Error updating generation {generation.id}: {e}")
        
        return recovered

# Singleton экземпляр для переиспользования
_api_instance: Optional[WaveSpeedAPI] = None

def get_wavespeed_api() -> WaveSpeedAPI:
    """Получить экземпляр API клиента"""
    global _api_instance
    if not _api_instance:
        _api_instance = WaveSpeedAPI()
    return _api_instance

# Вспомогательные функции

async def calculate_generation_cost(
    model: str,
    duration: int
) -> int:
    """Рассчитать стоимость генерации в кредитах"""
    from core.constants import GENERATION_COSTS, get_generation_cost
    
    # Используем функцию get_generation_cost для правильного поиска
    cost = get_generation_cost(model, duration)
    
    if cost == 0:
        # Если модель не найдена, возвращаем дефолтную стоимость
        logger.warning(f"Unknown model: {model}, using default cost")
        return 10
    
    return cost

async def get_model_info(model: str) -> Dict[str, Any]:
    """Получить информацию о модели"""
    from core.constants import MODEL_INFO
    
    # Определяем тип модели (lite или pro)
    if "lite" in model:
        return MODEL_INFO.get("lite", {})
    elif "pro" in model:
        return MODEL_INFO.get("pro", {})
    
    return {}

async def format_model_name(model: str) -> str:
    """Форматировать название модели для отображения"""
    parts = model.split("-")
    
    # Извлекаем информацию
    version = "V1"
    model_type = "Pro" if "pro" in model else "Lite"
    mode = "T2V" if "t2v" in model else "I2V"
    resolution = ""
    
    for part in parts:
        if part.endswith("p"):
            resolution = part.upper()
    
            return f"Magic Frame {version} {model_type} {mode} {resolution}"