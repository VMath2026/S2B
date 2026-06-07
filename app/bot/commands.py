from aiogram.types import BotCommand


def get_bot_commands() -> list[BotCommand]:
    return [
        BotCommand(command="start", description="Выбрать магазин"),
        BotCommand(command="new_order", description="Создать новый заказ"),
        BotCommand(command="change_shop", description="Выбрать другой магазин"),
        BotCommand(command="manager", description="Позвать менеджера"),
        BotCommand(command="help", description="Показать команды"),
        BotCommand(command="ping", description="Проверить, что бот отвечает"),
    ]
