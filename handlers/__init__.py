from . import main_menu, chat, prompts, admin


def setup_routers():
    """Настройка роутеров"""
    from aiogram import Router
    
    router = Router()
    router.include_router(admin.router)
    router.include_router(main_menu.router)
    router.include_router(chat.router)
    router.include_router(prompts.router)
    
    return router