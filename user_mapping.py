USER_MAPPING = {
    165879072: "Главный Админ", 
    5237388776: "Яночка", 
    415595998: "Иришка Бухтоярова", 
    838624082: "Мама", 
    133252780: "Таня", 
    1906674281: "Люба"
}

def get_user_name(user_id):
    """
    Получить имя пользователя по его ID
    :param user_id: ID пользователя
    :return: Имя пользователя или None, если пользователь не найден
    """
    return USER_MAPPING.get(user_id)

def add_user_mapping(user_id, user_name):
    """
    Добавить новое соответствие ID и имени пользователя
    :param user_id: ID пользователя
    :param user_name: Имя пользователя
    """
    USER_MAPPING[user_id] = user_name 