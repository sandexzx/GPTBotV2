from typing import Dict, List, Optional
import asyncio
from aiogram import Bot
from aiogram.types import Message
from datetime import datetime, timedelta

class QueueManager:
    def __init__(self):
        self.queue: List[Dict] = []
        self.current_request: Optional[Dict] = None
        self.lock = asyncio.Lock()
        self.processing = False
        self.last_notification_time: Dict[int, datetime] = {}  # Для отслеживания времени последнего уведомления

    async def add_to_queue(self, message: Message) -> int:
        """Добавляет запрос в очередь и возвращает позицию в очереди"""
        async with self.lock:
            position = len(self.queue) + 1
            self.queue.append({
                'user_id': message.from_user.id,
                'message': message,
                'chat_id': message.chat.id,
                'bot': message.bot,
                'position': position,
                'timestamp': datetime.now(),
                'last_notification': datetime.now()  # Время последнего уведомления
            })
            return position

    async def process_queue(self):
        """Обрабатывает очередь запросов"""
        if self.processing:
            return
        
        self.processing = True
        try:
            while self.queue:
                async with self.lock:
                    if not self.queue:
                        break
                    self.current_request = self.queue.pop(0)
                
                # Уведомляем пользователя, что его запрос начал обрабатываться
                await self.current_request['bot'].send_message(
                    self.current_request['chat_id'],
                    "🔄 Ваш запрос начал обрабатываться!"
                )
                
                # Возвращаем текущий запрос для обработки
                yield self.current_request
                
                # Уведомляем пользователя о завершении обработки
                await self.current_request['bot'].send_message(
                    self.current_request['chat_id'],
                    "✅ Обработка вашего запроса завершена!"
                )
                
                self.current_request = None
        finally:
            self.processing = False

    async def get_queue_position(self, user_id: int) -> Optional[int]:
        """Возвращает позицию пользователя в очереди"""
        async with self.lock:
            for i, request in enumerate(self.queue):
                if request['user_id'] == user_id:
                    return i + 1
            return None

    def is_user_in_queue(self, user_id: int) -> bool:
        """Проверяет, есть ли пользователь в очереди"""
        return any(request['user_id'] == user_id for request in self.queue)

    async def remove_from_queue(self, user_id: int) -> bool:
        """Удаляет запрос пользователя из очереди"""
        async with self.lock:
            for i, request in enumerate(self.queue):
                if request['user_id'] == user_id:
                    self.queue.pop(i)
                    return True
            return False

    async def send_queue_updates(self):
        """Отправляет обновления о статусе очереди"""
        while True:
            await asyncio.sleep(30)  # Проверяем каждые 30 секунд
            
            async with self.lock:
                current_time = datetime.now()
                for request in self.queue:
                    # Отправляем уведомление, если прошло более 1 минуты с последнего
                    if (current_time - request['last_notification']) > timedelta(minutes=1):
                        position = self.queue.index(request) + 1
                        await request['bot'].send_message(
                            request['chat_id'],
                            f"⏳ Ваш запрос все еще в очереди. Текущая позиция: {position}\n"
                            f"Примерное время ожидания: {position * 2} минут"
                        )
                        request['last_notification'] = current_time

# Создаем глобальный экземпляр менеджера очереди
queue_manager = QueueManager()

# Запускаем задачу для отправки обновлений о статусе очереди
async def start_queue_updates():
    await queue_manager.send_queue_updates() 