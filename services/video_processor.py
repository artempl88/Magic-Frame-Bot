import os
import tempfile
import subprocess
from typing import Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class VideoProcessor:
    """Класс для обработки видео"""
    
    def __init__(self):
        self.qr_code_path = Path(__file__).parent.parent / "qr-code.gif"
        
    async def add_qr_code_to_video(self, video_data: bytes, output_path: Optional[str] = None) -> bytes:
        """
        Добавляет QR-код в правый нижний угол видео
        
        Args:
            video_data: Данные видео в байтах
            output_path: Путь для сохранения (опционально)
            
        Returns:
            Обработанные данные видео с QR-кодом
        """
        try:
            # Создаем временные файлы
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as input_file:
                input_file.write(video_data)
                input_path = input_file.name
                
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as output_file:
                if output_path is None:
                    output_path = output_file.name
                    
            try:
                # Проверяем существование QR-кода
                if not self.qr_code_path.exists():
                    logger.error(f"QR code file not found: {self.qr_code_path}")
                    return video_data
                
                # FFmpeg команда для наложения QR-кода
                # Размещаем QR-код в правом нижнем углу с отступом 20px
                # Масштабируем QR-код до 80x80 пикселей
                cmd = [
                    'ffmpeg',
                    '-i', input_path,                    # Входное видео
                    '-i', str(self.qr_code_path),        # QR-код
                    '-filter_complex',
                    '[1:v]scale=80:80[qr];'              # Масштабируем QR-код
                    '[0:v][qr]overlay=W-w-20:H-h-20',   # Накладываем в правый нижний угол
                    '-c:a', 'copy',                      # Копируем аудио без изменений
                    '-c:v', 'libx264',                   # Кодек видео
                    '-preset', 'fast',                   # Быстрая обработка
                    '-crf', '23',                        # Качество
                    '-y',                                # Перезаписать файл
                    output_path
                ]
                
                # Выполняем команду
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120  # 2 минуты таймаут
                )
                
                if result.returncode != 0:
                    logger.error(f"FFmpeg error: {result.stderr}")
                    return video_data
                
                # Читаем обработанное видео
                with open(output_path, 'rb') as f:
                    processed_video = f.read()
                
                logger.info(f"QR code added successfully. Original size: {len(video_data)}, New size: {len(processed_video)}")
                return processed_video
                
            finally:
                # Удаляем временные файлы
                try:
                    os.unlink(input_path)
                    if output_path != output_file.name:
                        os.unlink(output_path)
                except:
                    pass
                    
        except subprocess.TimeoutExpired:
            logger.error("Video processing timeout")
            return video_data
        except Exception as e:
            logger.error(f"Error adding QR code to video: {e}")
            return video_data
    
    def is_ffmpeg_available(self) -> bool:
        """Проверяет доступность FFmpeg"""
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except:
            return False

# Глобальный экземпляр
video_processor = VideoProcessor()

async def add_qr_code_to_video(video_data: bytes) -> bytes:
    """
    Удобная функция для добавления QR-кода к видео
    
    Args:
        video_data: Данные видео в байтах
        
    Returns:
        Обработанные данные видео с QR-кодом
    """
    return await video_processor.add_qr_code_to_video(video_data) 