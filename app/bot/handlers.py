import asyncio
import logging
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.ai.order_parser import AIUnavailableError, parse_order_message
from app.config import settings
from app.services.conversations import (
    get_or_create_conversation_state,
    reset_conversation_state,
    update_conversation_state,
)
from app.services.customers import get_or_create_customer
from app.services.flowers import get_active_flowers_for_shop, reserve_selected_flowers
from app.services.orders import create_confirmed_order, update_order_status
from app.services.pricing import build_bouquet_options, calculate_selected_flowers_price
from app.services.shops import (
    get_active_shops_by_city,
    get_current_shop_for_user,
    get_shop_by_id,
    get_shop_by_slug,
    get_shop_settings,
    set_manager_chat_for_shop,
    set_current_shop_for_user,
)


router = Router()
logger = logging.getLogger(__name__)
pending_shop_options: dict[int, list[int]] = {}
MAX_AI_REQUESTS_PER_ORDER = 3


@router.message(CommandStart())
async def start_handler(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return

    telegram_user_id = message.from_user.id
    slug = command.args.strip() if command.args else None

    if not slug:
        await message.answer(
            "Здравствуйте! Напишите город, и я покажу доступные цветочные магазины.\n\n"
            "Например: Москва или Санкт-Петербург."
        )
        return

    shop = get_shop_by_slug(slug)
    if shop is None:
        await message.answer("Магазин не найден. Проверьте ссылку.")
        return

    customer = get_or_create_customer(
        shop_id=shop.id,
        telegram_user_id=telegram_user_id,
        telegram_username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    set_current_shop_for_user(
        telegram_user_id=telegram_user_id,
        shop_id=shop.id,
    )

    reset_conversation_state(
        shop_id=shop.id,
        customer_id=customer.id,
    )

    shop_settings = get_shop_settings(shop.id)
    greeting = (
        shop_settings.greeting_text
        if shop_settings and shop_settings.greeting_text
        else f"Здравствуйте! Это бот магазина «{shop.name}»."
    )

    await message.answer(
        f"{greeting}\n\n"
        "Чтобы быстрее собрать заказ, напишите одним сообщением: для кого букет, "
        "повод, бюджет, стиль или цвета, дату, адрес доставки и телефон."
    )


@router.message(Command("reset"))
async def reset_handler(message: Message) -> None:
    if message.from_user is None:
        return

    telegram_user_id = message.from_user.id
    shop = get_current_shop_for_user(telegram_user_id)

    if shop is None:
        await message.answer(
            "Сначала выберите магазин:\n"
            "/start cvety-u-doma\n"
            "или\n"
            "/start rose-house"
        )
        return

    customer = get_or_create_customer(
        shop_id=shop.id,
        telegram_user_id=telegram_user_id,
        telegram_username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    reset_conversation_state(
        shop_id=shop.id,
        customer_id=customer.id,
    )

    await message.answer(
        f"Сбросил текущий заказ для магазина «{shop.name}». "
        "Напишите пожелания заново."
    )


@router.message(Command("chat_id"))
async def chat_id_handler(message: Message) -> None:
    await message.answer(f"chat_id этого чата: {message.chat.id}")


@router.message(Command("bind_shop"))
async def bind_shop_handler(message: Message, command: CommandObject) -> None:
    slug = command.args.strip() if command.args else None
    if not slug:
        await message.answer(
            "Укажите slug магазина, например:\n/bind_shop cvety-u-doma"
        )
        return

    shop = set_manager_chat_for_shop(slug, message.chat.id)
    if shop is None:
        await message.answer("Магазин не найден. Проверьте slug.")
        return

    await message.answer(
        f"Готово. Уведомления магазина «{shop.name}» будут приходить в этот чат."
    )


@router.callback_query(F.data == "confirm_order")
async def confirm_order_callback(callback: CallbackQuery) -> None:
    shop = get_current_shop_for_user(callback.from_user.id)
    if shop is None:
        await callback.answer("Сначала выберите магазин.", show_alert=True)
        return

    customer = get_or_create_customer(
        shop_id=shop.id,
        telegram_user_id=callback.from_user.id,
        telegram_username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    state = get_or_create_conversation_state(shop.id, customer.id)
    if not state.get("is_ready_for_confirmation"):
        await callback.answer("Заказ еще не готов к подтверждению.", show_alert=True)
        return

    if callback.message is not None:
        await _submit_order(callback.message, shop, customer.id, state)
    await callback.answer()


@router.callback_query(F.data == "change_order")
async def change_order_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Напишите одним сообщением, что нужно изменить: состав букета, бюджет, дату, адрес или телефон."
        )


@router.callback_query(F.data.startswith("select_bouquet:"))
async def select_bouquet_callback(callback: CallbackQuery) -> None:
    shop = get_current_shop_for_user(callback.from_user.id)
    if shop is None:
        await callback.answer("Сначала выберите магазин.", show_alert=True)
        return

    customer = get_or_create_customer(
        shop_id=shop.id,
        telegram_user_id=callback.from_user.id,
        telegram_username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    state = get_or_create_conversation_state(shop.id, customer.id)
    options = state.get("bouquet_options") or []

    try:
        option_index = int((callback.data or "").split(":", maxsplit=1)[1])
        if option_index < 0:
            raise IndexError
        option = options[option_index]
    except (IndexError, ValueError):
        await callback.answer("Этот вариант уже недоступен. Напишите /reset.", show_alert=True)
        return

    new_state = {
        **state,
        "selected_flowers": option.get("selected_flowers") or [],
        "estimated_price": option.get("estimated_price"),
        "summary": option.get("title"),
        "is_ready_for_confirmation": True,
    }
    update_conversation_state(shop.id, customer.id, new_state)

    await callback.answer("Вариант выбран.")
    if callback.message is not None:
        await callback.message.answer(
            _build_selected_bouquet_message(option),
            reply_markup=_customer_order_keyboard(),
        )


@router.callback_query(F.data == "reset_order")
async def reset_order_callback(callback: CallbackQuery) -> None:
    shop = get_current_shop_for_user(callback.from_user.id)
    if shop is None:
        await callback.answer("Магазин не выбран.", show_alert=True)
        return

    customer = get_or_create_customer(
        shop_id=shop.id,
        telegram_user_id=callback.from_user.id,
        telegram_username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    reset_conversation_state(shop.id, customer.id)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Начали заново. Напишите пожелания одним сообщением: для кого букет, повод, бюджет, стиль или цвета, дату, адрес доставки и телефон."
        )


@router.callback_query(F.data.startswith("manager_status:"))
async def manager_status_callback(callback: CallbackQuery) -> None:
    _, order_id_text, status = (callback.data or "").split(":", maxsplit=2)
    order = update_order_status(int(order_id_text), status)
    if order is None:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    await callback.answer("Статус обновлен.")
    if callback.message is not None:
        await callback.message.answer(f"Статус заказа №{order.id}: {order.status}")


@router.message(F.text)
async def text_handler(message: Message) -> None:
    if message.from_user is None:
        return

    telegram_user_id = message.from_user.id
    shop = get_current_shop_for_user(telegram_user_id)

    if shop is None:
        await _handle_shop_selection(message, telegram_user_id)
        return

    customer = get_or_create_customer(
        shop_id=shop.id,
        telegram_user_id=telegram_user_id,
        telegram_username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    state = get_or_create_conversation_state(
        shop_id=shop.id,
        customer_id=customer.id,
    )

    if _is_confirmation_message(message.text) and state.get("is_ready_for_confirmation"):
        await _submit_order(message, shop, customer.id, state)
        return

    if state.get("order_submitted"):
        await message.answer(
            "Заказ уже передан менеджеру. Если хотите оформить новый заказ, напишите /reset."
        )
        return

    ai_requests_used = int(state.get("ai_requests_used") or 0)
    if ai_requests_used >= MAX_AI_REQUESTS_PER_ORDER:
        await message.answer(
            "Чтобы не тратить лишние запросы, я остановлю уточнения. "
            "Если данные верны, ответьте «Да» для передачи менеджеру. "
            "Если нужно начать заново, напишите /reset."
        )
        return

    shop_settings = get_shop_settings(shop.id)
    flowers = get_active_flowers_for_shop(shop.id)

    try:
        ai_response = await asyncio.to_thread(
            parse_order_message,
            shop=shop,
            shop_settings=shop_settings,
            flowers=flowers,
            current_state=state,
            user_message=message.text or "",
        )
    except AIUnavailableError:
        logger.exception("AI order parser is unavailable")
        await message.answer(
            "Я пока не могу подключиться к ИИ, но магазин уже выбран.\n\n"
            f"Вы общаетесь с магазином «{shop.name}». "
            "Напишите одним сообщением: для кого букет, повод, бюджет, "
            "стиль или цвета, дату, адрес доставки и телефон."
        )
        return

    new_state = ai_response.state.model_dump()
    new_state["ai_requests_used"] = ai_requests_used + 1

    if _has_enough_details_for_options(new_state):
        options = build_bouquet_options(
            flowers=flowers,
            budget=new_state.get("budget"),
            colors=new_state.get("colors") or [],
            style=new_state.get("style"),
        )
        if options:
            new_state["bouquet_options"] = options
            new_state["selected_flowers"] = []
            new_state["estimated_price"] = None
            new_state["is_ready_for_confirmation"] = False
            ai_response.reply = _build_bouquet_options_message(options)
        else:
            new_state["bouquet_options"] = []
            new_state["is_ready_for_confirmation"] = False
            ai_response.reply += (
                "\n\nНе смог собрать варианты в этот бюджет по текущим остаткам. "
                "Попробуйте увеличить бюджет или изменить пожелания."
            )
    else:
        calculated_price = calculate_selected_flowers_price(
            new_state.get("selected_flowers") or [],
            flowers,
        )
        if calculated_price is not None:
            new_state["estimated_price"] = float(calculated_price)

    update_conversation_state(
        shop_id=shop.id,
        customer_id=customer.id,
        state=new_state,
    )

    await message.answer(
        ai_response.reply,
        reply_markup=(
            _bouquet_options_keyboard(new_state.get("bouquet_options") or [])
            if new_state.get("bouquet_options")
            else _customer_order_keyboard()
            if new_state.get("is_ready_for_confirmation")
            else None
        ),
    )


async def _handle_shop_selection(message: Message, telegram_user_id: int) -> None:
    text = (message.text or "").strip()
    option_ids = pending_shop_options.get(telegram_user_id)

    if option_ids and text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(option_ids):
            shop = get_shop_by_id(option_ids[index])
            if shop is None:
                await message.answer("Магазин не найден. Напишите город еще раз.")
                pending_shop_options.pop(telegram_user_id, None)
                return

            set_current_shop_for_user(telegram_user_id, shop.id)
            customer = get_or_create_customer(
                shop_id=shop.id,
                telegram_user_id=telegram_user_id,
                telegram_username=message.from_user.username if message.from_user else None,
                first_name=message.from_user.first_name if message.from_user else None,
            )
            reset_conversation_state(shop.id, customer.id)
            pending_shop_options.pop(telegram_user_id, None)

            shop_settings = get_shop_settings(shop.id)
            greeting = (
                shop_settings.greeting_text
                if shop_settings and shop_settings.greeting_text
                else f"Здравствуйте! Это бот магазина «{shop.name}»."
            )
            await message.answer(
                f"{greeting}\n\n"
                "Чтобы сэкономить запросы, напишите все пожелания одним сообщением: "
                "для кого букет, повод, бюджет, стиль или цвета, дата, адрес доставки и телефон."
            )
            return

        await message.answer("Не вижу магазина под таким номером. Отправьте цифру из списка.")
        return

    shops = get_active_shops_by_city(text)
    if not shops:
        await message.answer(
            "Пока не нашел магазины в этом городе. Попробуйте написать город иначе, например: Москва."
        )
        return

    pending_shop_options[telegram_user_id] = [shop.id for shop in shops]
    lines = [f"{index}. {shop.name}" for index, shop in enumerate(shops, start=1)]
    await message.answer(
        "Нашел магазины в вашем городе. Отправьте цифру нужного магазина:\n\n"
        + "\n".join(lines)
    )


def _is_confirmation_message(text: str | None) -> bool:
    normalized = (text or "").strip().lower()
    return normalized in {"да", "подтверждаю", "подходит", "ок", "окей", "yes", "y"}


async def _submit_order(
    message: Message,
    shop,
    customer_id: int,
    state: dict,
) -> None:
    unavailable = reserve_selected_flowers(
        shop_id=shop.id,
        selected_flowers=state.get("selected_flowers") or [],
    )
    if unavailable:
        await message.answer(
            "Пока подтверждали заказ, часть цветов стала недоступна:\n"
            + "\n".join(f"- {item}" for item in unavailable)
            + "\n\nНапишите /reset, чтобы собрать букет заново по актуальным остаткам."
        )
        return

    order = create_confirmed_order(
        shop_id=shop.id,
        customer_id=customer_id,
        state={**state, "order_submitted": True},
    )
    update_conversation_state(
        shop_id=shop.id,
        customer_id=customer_id,
        state={**state, "order_submitted": True},
    )

    shop_settings = get_shop_settings(shop.id)
    manager_text = _build_manager_order_message(order.id, shop.name, state)
    manager_chat_id = (
        shop_settings.manager_chat_id
        if shop_settings and shop_settings.manager_chat_id
        else settings.default_manager_chat_id
    )

    if manager_chat_id:
        try:
            await message.bot.send_message(
                manager_chat_id,
                manager_text,
                reply_markup=_manager_order_keyboard(order.id),
            )
            await message.answer(
                _build_customer_order_card(order.id, shop.name, state)
            )
            return
        except Exception:
            logger.exception("Failed to send order notification to manager chat")

    await message.answer(
        _build_customer_order_card(order.id, shop.name, state)
        + "\n\n"
        f"Заказ сохранен, но группа менеджеров еще не настроена. "
        "Чтобы получать уведомления в Telegram-группу, добавьте бота в группу, "
        "напишите там /chat_id и укажите этот chat_id в DEFAULT_MANAGER_CHAT_ID "
        "или в shop_settings.manager_chat_id."
    )


def _append_price_confirmation(
    reply: str,
    price: Decimal,
    ready_for_confirmation: bool,
) -> str:
    price_text = f"\n\nПримерная стоимость букета: {price:.0f} руб."
    if ready_for_confirmation and "подходит" not in reply.lower():
        price_text += "\nПодходит? Ответьте «Да», и я передам заказ менеджеру."
    if "стоим" in reply.lower() or "руб" in reply.lower():
        return reply
    return reply + price_text


def _has_enough_details_for_options(state: dict) -> bool:
    required_fields = ["recipient", "occasion", "budget", "style", "delivery_date", "phone"]
    return all(state.get(field) for field in required_fields)


def _build_bouquet_options_message(options: list[dict]) -> str:
    lines = ["Подобрал варианты в ваш бюджет. Выберите подходящий букет кнопкой ниже:"]
    for index, option in enumerate(options, start=1):
        flowers = ", ".join(
            f"{item.get('name')} x{item.get('quantity')}"
            for item in option.get("selected_flowers", [])
        )
        lines.append(
            f"\n{index}. {option.get('title')}\n"
            f"{flowers}\n"
            f"{option.get('description')}\n"
            f"Цена: {float(option.get('estimated_price') or 0):.0f} ₽"
        )
    return "\n".join(lines)


def _build_selected_bouquet_message(option: dict) -> str:
    flowers = ", ".join(
        f"{item.get('name')} x{item.get('quantity')}"
        for item in option.get("selected_flowers", [])
    )
    return (
        f"Вы выбрали: {option.get('title')}\n"
        f"Состав: {flowers}\n"
        f"Примерная стоимость: {float(option.get('estimated_price') or 0):.0f} ₽\n\n"
        "Подтвердить заказ?"
    )


def _bouquet_options_keyboard(options: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"Выбрать вариант {index}",
                callback_data=f"select_bouquet:{index - 1}",
            )
        ]
        for index, _option in enumerate(options, start=1)
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="Изменить пожелания",
                callback_data="change_order",
            ),
            InlineKeyboardButton(
                text="Начать заново",
                callback_data="reset_order",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_manager_order_message(order_id: int, shop_name: str, state: dict) -> str:
    flowers = state.get("selected_flowers") or []
    flowers_text = ", ".join(
        f"{item.get('name')} x{item.get('quantity')}" for item in flowers
    ) or "не указаны"

    total_price = state.get("estimated_price")
    total_price_text = (
        f"{float(total_price):.0f} руб."
        if total_price not in (None, "")
        else "уточнить"
    )

    return (
        f"Принят новый заказ №{order_id} на сумму {total_price_text}\n"
        f"Магазин: {shop_name}\n"
        f"Для кого: {state.get('recipient')}\n"
        f"Повод: {state.get('occasion')}\n"
        f"Бюджет: {state.get('budget')}\n"
        f"Цветы: {flowers_text}\n"
        f"Цена: {total_price_text}\n"
        f"Дата: {_display_value(state.get('delivery_date'))}\n"
        f"Адрес: {_display_value(state.get('delivery_address'))}\n"
        f"Телефон: {_display_value(state.get('phone'))}\n"
        f"Комментарий: {_display_value(state.get('comment'))}"
    )


def _display_value(value: object) -> object:
    return value if value not in (None, "") else "не указан"


def _customer_order_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить заказ",
                    callback_data="confirm_order",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Изменить пожелания",
                    callback_data="change_order",
                ),
                InlineKeyboardButton(
                    text="Начать заново",
                    callback_data="reset_order",
                ),
            ],
        ]
    )


def _manager_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Принять",
                    callback_data=f"manager_status:{order_id}:accepted",
                ),
                InlineKeyboardButton(
                    text="В работе",
                    callback_data=f"manager_status:{order_id}:in_progress",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Готово",
                    callback_data=f"manager_status:{order_id}:done",
                ),
                InlineKeyboardButton(
                    text="Отменить",
                    callback_data=f"manager_status:{order_id}:cancelled",
                ),
            ],
        ]
    )


def _build_customer_order_card(order_id: int, shop_name: str, state: dict) -> str:
    flowers = state.get("selected_flowers") or []
    flowers_text = ", ".join(
        f"{item.get('name')} x{item.get('quantity')}" for item in flowers
    ) or "состав уточнит менеджер"

    return (
        f"Заказ №{order_id} принят\n\n"
        f"Магазин: {shop_name}\n"
        f"Букет: {flowers_text}\n"
        f"Примерная цена: {state.get('estimated_price')} руб.\n"
        f"Для кого: {state.get('recipient')}\n"
        f"Повод: {state.get('occasion')}\n"
        f"Доставка: {state.get('delivery_date')}, {state.get('delivery_address')}\n"
        f"Телефон: {state.get('phone')}\n\n"
        "Менеджер проверит наличие цветов, финальную стоимость и скоро свяжется с вами."
    )
