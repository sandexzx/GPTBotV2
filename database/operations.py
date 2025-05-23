from sqlalchemy.exc import NoResultFound
from typing import Optional, List, Dict, Any

from .models import Session, User, Chat, Message, Prompt


def get_or_create_user(tg_id: int, username: Optional[str] = None) -> int:
    """Получить существующего пользователя или создать нового"""
    session = Session()
    user = session.query(User).filter(User.tg_id == tg_id).first()
    if not user:
        user = User(tg_id=tg_id, username=username)
        session.add(user)
        session.commit()
    user_id = user.id
    session.close()
    return user_id


def create_chat(user_id: int, model: str) -> int:
    """Создать новый чат"""
    session = Session()
    user = session.query(User).filter(User.id == user_id).one()
    
    chat = Chat(user=user, model=model)
    session.add(chat)
    session.commit()
    
    result = chat.id
    session.close()
    return result

def get_prompt_by_id(prompt_id: int) -> Optional[Prompt]:
    """Получить промпт по ID"""
    session = Session()
    try:
        prompt = session.query(Prompt).filter(Prompt.id == prompt_id).one()
        result = prompt  # Сохраняем результат до закрытия сессии
        session.close()
        return result
    except NoResultFound:
        session.close()
        return None

def add_message(chat_id: int, role: str, content: str, tokens: int, cost_usd: float) -> Message:
    """Добавить сообщение в чат"""
    session = Session()
    
    message = Message(
        chat_id=chat_id,
        role=role,
        content=content,
        tokens=tokens,
        cost_usd=cost_usd
    )
    
    session.add(message)
    
    # Обновляем статистику чата
    chat = session.query(Chat).filter(Chat.id == chat_id).one()
    if role == "user":
        chat.tokens_input += tokens
    else:
        chat.tokens_output += tokens
    chat.cost_usd += cost_usd
    
    # Обновляем статистику пользователя
    user = chat.user
    if role == "user":
        user.total_tokens_input += tokens
    else:
        user.total_tokens_output += tokens
    user.total_cost_usd += cost_usd
    
    session.commit()
    result = message
    session.close()
    return result


def get_chat_messages(chat_id: int) -> List[Dict[str, Any]]:
    """Получить все сообщения чата в формате для API OpenAI"""
    session = Session()
    messages = session.query(Message).filter(Message.chat_id == chat_id).all()
    
    result = [{"role": msg.role, "content": msg.content} for msg in messages]
    session.close()
    return result


def get_chat_stats(chat_id: int) -> Dict[str, Any]:
    """Получить статистику чата"""
    session = Session()
    chat = session.query(Chat).filter(Chat.id == chat_id).one()
    
    result = {
        "tokens_input": chat.tokens_input,
        "tokens_output": chat.tokens_output,
        "cost_usd": chat.cost_usd,
    }
    session.close()
    return result


def save_prompt(user_id: int, name: str, content: str) -> Prompt:
    """Сохранить промпт"""
    session = Session()
    
    prompt = Prompt(user_id=user_id, name=name, content=content)
    session.add(prompt)
    session.commit()
    
    result = prompt
    session.close()
    return result


def get_user_prompts(user_id: int) -> List[Prompt]:
    """Получить все промпты пользователя"""
    session = Session()
    prompts = session.query(Prompt).filter(Prompt.user_id == user_id).all()
    
    result = list(prompts)  # Копируем результаты
    session.close()
    return result


def delete_prompt(prompt_id: int) -> bool:
    """Удалить промпт"""
    session = Session()
    try:
        prompt = session.query(Prompt).filter(Prompt.id == prompt_id).one()
        session.delete(prompt)
        session.commit()
        session.close()
        return True
    except NoResultFound:
        session.close()
        return False


def get_admin_stats() -> Dict[str, Any]:
    """Получить админскую статистику"""
    session = Session()
    
    users = session.query(User).all()
    user_stats = []
    
    for user in users:
        user_stat = {
            "tg_id": user.tg_id,
            "username": user.username,
            "total_tokens_input": user.total_tokens_input,
            "total_tokens_output": user.total_tokens_output,
            "total_cost_usd": user.total_cost_usd,
            "chats_count": len(user.chats)
        }
        user_stats.append(user_stat)
    
    # Статистика по моделям
    model_stats = {}
    chats = session.query(Chat).all()
    for chat in chats:
        if chat.model not in model_stats:
            model_stats[chat.model] = {
                "tokens_input": 0,
                "tokens_output": 0,
                "cost_usd": 0.0,
                "chats_count": 0
            }
        
        model_stats[chat.model]["tokens_input"] += chat.tokens_input
        model_stats[chat.model]["tokens_output"] += chat.tokens_output
        model_stats[chat.model]["cost_usd"] += chat.cost_usd
        model_stats[chat.model]["chats_count"] += 1
    
    result = {
        "users": user_stats,
        "models": model_stats
    }
    
    session.close()
    return result

def update_message_tokens(chat_id: int, is_user_message: bool, new_tokens: int, old_tokens: int, model: str) -> None:
    """Обновить количество токенов в последнем сообщении и пересчитать статистику"""
    from services.token_counter import calculate_cost
    session = Session()
    
    # Определяем роль сообщения
    role = "user" if is_user_message else "assistant"
    
    # Получаем последнее сообщение пользователя и обновляем его токены
    last_message = session.query(Message).filter(
        Message.chat_id == chat_id, 
        Message.role == role
    ).order_by(Message.id.desc()).first()
    
    if last_message:
        # Вычисляем разницу между оценкой и реальным количеством
        tokens_diff = new_tokens - old_tokens
        cost_diff = calculate_cost(tokens_diff, model, is_user_message)
        
        # Обновляем запись сообщения
        last_message.tokens = new_tokens
        last_message.cost_usd = calculate_cost(new_tokens, model, is_user_message)
        
        # Обновляем статистику чата
        chat = session.query(Chat).filter(Chat.id == chat_id).one()
        if is_user_message:
            chat.tokens_input += tokens_diff
        else:
            chat.tokens_output += tokens_diff
        chat.cost_usd += cost_diff
        
        # Обновляем статистику пользователя
        user = chat.user
        if is_user_message:
            user.total_tokens_input += tokens_diff
        else:
            user.total_tokens_output += tokens_diff
        user.total_cost_usd += cost_diff
        
        session.commit()
    session.close()