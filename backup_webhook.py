#!/usr/bin/env python3
"""
Простой webhook сервер для запуска резервного копирования
Запускается на хосте и принимает HTTP запросы от приложения
"""
import subprocess
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BackupWebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/create_backup':
            try:
                # Читаем данные запроса
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                description = data.get('description', 'Ручной бэкап из админки')
                
                # Выполняем системный скрипт резервного копирования
                cmd = [
                    'bash', '-c',
                    'CONTAINER_ID=7ef6284f8a9c DB_USER=magic_frame '
                    'POSTGRES_PASSWORD="RagnarLothbrok2021!" '
                    'BACKUP_DIR=/opt/magic-frame-bot/backups '
                    '/usr/local/bin/pg_backup.sh -d magic_frame_bot --container 7ef6284f8a9c'
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                
                if result.returncode == 0:
                    # Находим созданный файл
                    import glob
                    import os
                    backup_files = glob.glob('/opt/magic-frame-bot/backups/magic_frame_bot_*.sql.gz')
                    latest_file = max(backup_files, key=os.path.getctime) if backup_files else None
                    
                    if latest_file:
                        file_size = os.path.getsize(latest_file)
                        filename = os.path.basename(latest_file)
                        
                        response_data = {
                            'success': True,
                            'message': f'Резервная копия создана: {filename}',
                            'filename': filename,
                            'size': file_size,
                            'size_mb': round(file_size / 1024 / 1024, 1)
                        }
                    else:
                        response_data = {
                            'success': False,
                            'message': 'Файл резервной копии не найден'
                        }
                else:
                    response_data = {
                        'success': False,
                        'message': f'Ошибка выполнения скрипта: {result.stderr}'
                    }
                
                # Отправляем ответ
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode('utf-8'))
                
            except Exception as e:
                logger.error(f"Ошибка webhook: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {'success': False, 'message': f'Внутренняя ошибка: {str(e)}'}
                self.wfile.write(json.dumps(response).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = {'status': 'ok'}
            self.wfile.write(json.dumps(response).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

def run_server():
    server_address = ('0.0.0.0', 8082)
    httpd = HTTPServer(server_address, BackupWebhookHandler)
    logger.info("Backup webhook сервер запущен на http://127.0.0.1:8082")
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()
