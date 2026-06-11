import asyncio
import logging
import re
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    User,
)

from app.ai.image_generator import ImageGenerationError, generate_bouquet_image
from app.ai.order_parser import AIUnavailableError, parse_order_message
from app.config import settings
from app.services.conversations import (
    add_conversation_log,
    get_or_create_conversation_state,
    reset_conversation_state,
    update_conversation_state,
)
from app.services.customers import (
    get_customer_by_id,
    get_customer_by_telegram_user_id,
    get_or_create_customer,
)
from app.services.flowers import get_active_flowers_for_shop, reserve_selected_flowers
from app.services.orders import (
    create_confirmed_order,
    get_order_by_id,
    list_recent_orders_for_customer,
    list_recent_orders,
    list_recent_orders_for_shop,
    update_order_payment_status,
    update_order_status,
)
from app.services.order_validation import validate_order_state
from app.services.pricing import build_bouquet_options, calculate_selected_flowers_price
from app.services.templates import build_template_bouquet_options
from app.services.shops import (
    clear_current_shop_for_user,
    get_active_shops_by_city,
    get_current_shop_for_user,
    get_shop_by_id,
    get_shop_by_manager_chat_id,
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
    if not _is_private_message(message):
        return

    if message.from_user is None:
        return

    telegram_user_id = message.from_user.id
    slug = command.args.strip() if command.args else None

    if not slug:
        clear_current_shop_for_user(telegram_user_id)
        pending_shop_options.pop(telegram_user_id, None)
        await message.answer(
            "Здравствуйте! Напишите город, и я покажу доступные цветочные магазины.\n\n"
            "Например: Москва или Санкт-Петербург.\n\n"
            + _commands_help_text()
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

    await message.answer(_build_shop_greeting_text(shop))


@router.message(Command("reset"))
async def reset_handler(message: Message) -> None:
    if not _is_private_message(message):
        return

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


@router.message(Command("new_order"))
async def new_order_handler(message: Message) -> None:
    await reset_handler(message)


@router.message(Command("change_shop"))
async def change_shop_handler(message: Message) -> None:
    if not _is_private_message(message):
        return

    if message.from_user is None:
        return

    clear_current_shop_for_user(message.from_user.id)
    pending_shop_options.pop(message.from_user.id, None)
    await message.answer(
        "Ок, выберем другой магазин. Напишите город, и я покажу доступные варианты."
    )


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    if not _is_private_message(message):
        return

    await message.answer(
        _commands_help_text()
    )


@router.message(Command("manager"))
async def manager_handler(message: Message) -> None:
    if not _is_private_message(message):
        return

    if message.from_user is None:
        return

    shop = get_current_shop_for_user(message.from_user.id)
    if shop is None:
        await message.answer("Сначала выберите магазин: напишите /start.")
        return

    customer = get_or_create_customer(
        shop_id=shop.id,
        telegram_user_id=message.from_user.id,
        telegram_username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    state = get_or_create_conversation_state(shop.id, customer.id)
    await _request_manager_help(
        message,
        shop,
        customer.id,
        state,
        customer_user=message.from_user,
    )


@router.message(Command("ping"))
async def ping_handler(message: Message) -> None:
    if not _is_private_message(message):
        return

    await message.answer("pong")


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


@router.message(Command("orders"))
async def manager_orders_handler(message: Message) -> None:
    shop = _get_manager_shop_for_message(message)
    is_default_manager_chat = _is_default_manager_chat(message)
    if shop is None and not is_default_manager_chat:
        await message.answer(
            "Чтобы смотреть заказы здесь, привяжите группу к магазину командой:\n"
            "/bind_shop slug-магазина"
        )
        return

    orders = (
        list_recent_orders_for_shop(shop.id, limit=10)
        if shop is not None
        else list_recent_orders(limit=10)
    )
    if not orders:
        title = f"У магазина «{shop.name}»" if shop is not None else "В системе"
        await message.answer(f"{title} пока нет заказов.")
        return

    title = f"магазина «{shop.name}»" if shop is not None else "всех магазинов"
    await message.answer(_build_orders_list_message(title, orders))


@router.message(Command("reply"))
async def manager_reply_handler(message: Message, command: CommandObject) -> None:
    shop = _get_manager_shop_for_message(message)
    is_default_manager_chat = _is_default_manager_chat(message)
    if shop is None and not is_default_manager_chat:
        await message.answer("Сначала привяжите эту группу к магазину: /bind_shop slug-магазина")
        return

    args = (command.args or "").strip()
    if not args or " " not in args:
        await message.answer("Формат: /reply 12 текст сообщения клиенту")
        return

    order_id_text, reply_text = args.split(" ", maxsplit=1)
    if not order_id_text.isdigit() or not reply_text.strip():
        await message.answer("Формат: /reply 12 текст сообщения клиенту")
        return

    order = get_order_by_id(int(order_id_text))
    if order is None or (shop is not None and order.shop_id != shop.id):
        await message.answer("Заказ не найден в этом магазине.")
        return

    customer = get_customer_by_id(order.customer_id)
    if customer is None:
        await message.answer("Не нашел Telegram-клиента для этого заказа.")
        return

    try:
        await message.bot.send_message(
            customer.telegram_user_id,
            f"Сообщение менеджера по заказу №{order.id}:\n{reply_text.strip()}",
            parse_mode=None,
        )
    except Exception:
        logger.exception("Failed to send manager reply to customer")
        await message.answer("Не смог отправить сообщение клиенту. Попробуйте позже.")
        return

    await message.answer(f"Отправил клиенту сообщение по заказу №{order.id}.")


@router.message(Command("message"))
async def manager_direct_message_handler(message: Message, command: CommandObject) -> None:
    shop = _get_manager_shop_for_message(message)
    is_default_manager_chat = _is_default_manager_chat(message)
    if shop is None and not is_default_manager_chat:
        await message.answer(
            "Эта команда работает только в чате менеджеров. Привяжите группу командой /bind_shop slug-магазина."
        )
        return

    args = (command.args or "").strip()
    if not args or " " not in args:
        await message.answer("Формат: /message telegram_id текст сообщения клиенту")
        return

    user_id_text, reply_text = args.split(" ", maxsplit=1)
    if not user_id_text.isdigit() or not reply_text.strip():
        await message.answer("Формат: /message telegram_id текст сообщения клиенту")
        return

    telegram_user_id = int(user_id_text)
    customer = get_customer_by_telegram_user_id(
        telegram_user_id,
        shop_id=shop.id if shop is not None else None,
    )
    if customer is None:
        await message.answer("Клиент не найден для этого магазина. Проверьте telegram_id из заявки.")
        return

    customer_shop = shop or get_shop_by_id(customer.shop_id)
    shop_name = customer_shop.name if customer_shop is not None else "магазина"

    try:
        await message.bot.send_message(
            telegram_user_id,
            f"Сообщение менеджера «{shop_name}»:\n{reply_text.strip()}",
            parse_mode=None,
        )
    except Exception:
        logger.exception("Failed to send manager direct message to customer")
        await message.answer("Не смог отправить сообщение клиенту. Попробуйте открыть диалог кнопкой из заявки.")
        return

    await message.answer("Отправил сообщение клиенту через бота.")


@router.callback_query(F.data.startswith("select_shop:"))
async def select_shop_callback(callback: CallbackQuery) -> None:
    if not _is_private_callback(callback):
        await callback.answer()
        return

    try:
        shop_id = int((callback.data or "").split(":", maxsplit=1)[1])
    except ValueError:
        await callback.answer("Не смог выбрать магазин.", show_alert=True)
        return

    shop = get_shop_by_id(shop_id)
    if shop is None:
        await callback.answer("Магазин не найден.", show_alert=True)
        return

    customer = get_or_create_customer(
        shop_id=shop.id,
        telegram_user_id=callback.from_user.id,
        telegram_username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    set_current_shop_for_user(callback.from_user.id, shop.id)
    reset_conversation_state(shop.id, customer.id)
    pending_shop_options.pop(callback.from_user.id, None)

    await callback.answer("Магазин выбран.")
    if callback.message is not None:
        await callback.message.answer(_build_shop_greeting_text(shop))


@router.callback_query(F.data == "change_shop_button")
async def change_shop_button_callback(callback: CallbackQuery) -> None:
    if not _is_private_callback(callback):
        await callback.answer()
        return

    clear_current_shop_for_user(callback.from_user.id)
    pending_shop_options.pop(callback.from_user.id, None)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Ок, выберем другой магазин. Напишите город, и я покажу доступные варианты."
        )


@router.callback_query(F.data == "confirm_order")
async def confirm_order_callback(callback: CallbackQuery) -> None:
    if not _is_private_callback(callback):
        await callback.answer()
        return

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
    if state.get("order_submitted"):
        await callback.answer("Этот заказ уже создан. Для нового заказа нажмите /new_order.", show_alert=True)
        return

    if not state.get("is_ready_for_confirmation"):
        await callback.answer("Заказ еще не готов к подтверждению.", show_alert=True)
        return

    if callback.message is not None:
        await _submit_order(callback.message, shop, customer.id, state)
    await callback.answer()


@router.callback_query(F.data == "change_order")
async def change_order_callback(callback: CallbackQuery) -> None:
    if not _is_private_callback(callback):
        await callback.answer()
        return

    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Напишите одним сообщением, что нужно изменить: состав букета, бюджет, дату, адрес или телефон."
        )


@router.callback_query(F.data == "call_manager")
async def call_manager_callback(callback: CallbackQuery) -> None:
    if not _is_private_callback(callback):
        await callback.answer()
        return

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
    await callback.answer()
    if callback.message is not None:
        await _request_manager_help(
            callback.message,
            shop,
            customer.id,
            state,
            customer_user=callback.from_user,
        )


@router.callback_query(F.data.startswith("select_bouquet:"))
async def select_bouquet_callback(callback: CallbackQuery) -> None:
    if not _is_private_callback(callback):
        await callback.answer()
        return

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
        reply_markup = _customer_order_keyboard(
            image_enabled=_is_image_generation_enabled(shop.id),
        )
        if option.get("image_url"):
            await callback.message.answer_photo(
                option["image_url"],
                caption=_build_selected_bouquet_message(option),
                reply_markup=reply_markup,
            )
        else:
            await callback.message.answer(
                _build_selected_bouquet_message(option),
                reply_markup=reply_markup,
            )


@router.callback_query(F.data == "generate_image")
async def generate_image_callback(callback: CallbackQuery) -> None:
    if not _is_private_callback(callback):
        await callback.answer()
        return

    shop = get_current_shop_for_user(callback.from_user.id)
    if shop is None:
        await callback.answer("Сначала выберите магазин.", show_alert=True)
        return

    if not _is_image_generation_enabled(shop.id):
        await callback.answer("Для этого магазина эскизы пока выключены.", show_alert=True)
        return

    customer = get_or_create_customer(
        shop_id=shop.id,
        telegram_user_id=callback.from_user.id,
        telegram_username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    state = get_or_create_conversation_state(shop.id, customer.id)
    if not state.get("selected_flowers"):
        await callback.answer("Сначала выберите вариант букета.", show_alert=True)
        return

    if callback.message is None:
        await callback.answer()
        return

    cached_file_id = state.get("generated_image_file_id")
    if cached_file_id:
        await callback.answer("Отправляю готовый эскиз.")
        await callback.message.answer_photo(
            cached_file_id,
            caption=_build_image_caption(state),
        )
        return

    await callback.answer("Генерирую эскиз. Это может занять немного времени.")
    progress_message = await callback.message.answer("Генерирую эскиз букета...")

    try:
        image_bytes = await asyncio.to_thread(
            generate_bouquet_image,
            shop_name=shop.name,
            state=state,
        )
    except ImageGenerationError:
        logger.exception("Bouquet image generation failed")
        await progress_message.answer(
            "Не смог сгенерировать эскиз сейчас. Попробуйте позже или позовите менеджера.",
            reply_markup=_manager_help_keyboard(),
        )
        return

    sent_message = await callback.message.answer_photo(
        BufferedInputFile(image_bytes, filename="bouquet-preview.png"),
        caption=_build_image_caption(state),
    )
    if sent_message.photo:
        image_file_id = sent_message.photo[-1].file_id
        update_conversation_state(
            shop_id=shop.id,
            customer_id=customer.id,
            state={**state, "generated_image_file_id": image_file_id},
        )


@router.callback_query(F.data == "reset_order")
async def reset_order_callback(callback: CallbackQuery) -> None:
    if not _is_private_callback(callback):
        await callback.answer()
        return

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
    customer = get_customer_by_id(order.customer_id)
    if customer is not None:
        try:
            await callback.bot.send_message(
                customer.telegram_user_id,
                _build_customer_status_message(order.id, order.status),
            )
        except Exception:
            logger.exception("Failed to send order status update to customer")

    if callback.message is not None:
        await callback.message.answer(
            f"Статус заказа №{order.id}: {_status_label(order.status)}"
        )


@router.pre_checkout_query()
async def pre_checkout_handler(query: PreCheckoutQuery) -> None:
    order_id = _order_id_from_payment_payload(query.invoice_payload)
    if order_id is None:
        await query.answer(ok=False, error_message="Не смог найти заказ для оплаты.")
        return

    order = get_order_by_id(order_id)
    if order is None:
        await query.answer(ok=False, error_message="Заказ не найден.")
        return

    shop_settings = get_shop_settings(order.shop_id)
    expected_amount = _payment_amount_minor(
        order.total_price,
        payment_mode=shop_settings.payment_mode if shop_settings else "full_prepay",
    )
    if expected_amount is None or query.total_amount != expected_amount:
        await query.answer(ok=False, error_message="Сумма заказа изменилась. Напишите /manager.")
        return

    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message) -> None:
    payment = message.successful_payment
    if payment is None:
        return

    order_id = _order_id_from_payment_payload(payment.invoice_payload)
    if order_id is None:
        await message.answer("Оплата прошла, но я не смог связать ее с заказом. Напишите /manager.")
        return

    existing_order = get_order_by_id(order_id)
    shop_settings = get_shop_settings(existing_order.shop_id) if existing_order is not None else None
    next_payment_status = (
        "prepaid"
        if shop_settings is not None and shop_settings.payment_mode == "prepay_50"
        else "paid"
    )

    order = update_order_payment_status(
        order_id,
        next_payment_status,
        telegram_payment_charge_id=payment.telegram_payment_charge_id,
        provider_payment_charge_id=payment.provider_payment_charge_id,
    )
    if order is None:
        await message.answer("Оплата прошла, но заказ не найден. Напишите /manager.")
        return

    paid_amount = Decimal(payment.total_amount) / Decimal(100)
    await message.answer(
        f"Оплата заказа №{order.id} получена: {paid_amount:.0f} {payment.currency}. "
        "Спасибо! Менеджер увидит оплату и продолжит работу с заказом.",
        reply_markup=_post_order_keyboard(),
    )

    manager_chat_id = _get_manager_chat_id(order.shop_id)
    if manager_chat_id:
        try:
            await message.bot.send_message(
                manager_chat_id,
                f"Оплачен заказ №{order.id}\n"
                f"Сумма: {paid_amount:.0f} {payment.currency}\n"
                f"Telegram charge: {payment.telegram_payment_charge_id}",
            )
        except Exception:
            logger.exception("Failed to send payment notification to manager chat")


@router.message(F.text)
async def text_handler(message: Message) -> None:
    if not _is_private_message(message):
        return

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
    user_text = message.text or ""
    add_conversation_log(
        shop_id=shop.id,
        customer_id=customer.id,
        role="customer",
        message=user_text,
    )

    state = _apply_customer_history_shortcuts(
        shop_id=shop.id,
        customer_id=customer.id,
        state=state,
        user_message=user_text,
    )

    if _is_confirmation_message(message.text) and state.get("is_ready_for_confirmation"):
        await _submit_order(message, shop, customer.id, state)
        return

    if state.get("order_submitted"):
        await message.answer(
            "Заказ уже передан менеджеру. Если хотите оформить новый заказ, напишите /new_order. "
            "Если нужен другой магазин, напишите /change_shop."
        )
        return

    ai_requests_used = int(state.get("ai_requests_used") or 0)
    if ai_requests_used >= MAX_AI_REQUESTS_PER_ORDER:
        await message.answer(
            "Похоже, мы ходим по кругу, поэтому лучше подключить менеджера. "
            "Если не получается договориться с ботом, позовите менеджера. "
            "Если нужно начать заново, напишите /new_order.",
            reply_markup=_manager_help_keyboard(),
        )
        return

    shop_settings = get_shop_settings(shop.id)
    if shop_settings and not shop_settings.ai_enabled:
        await message.answer(
            "Сейчас магазин принимает заявки через менеджера. Нажмите кнопку ниже, и я передам ему ваши данные.",
            reply_markup=_manager_help_keyboard(),
        )
        return

    flowers = get_active_flowers_for_shop(shop.id)

    try:
        ai_response = await asyncio.to_thread(
            parse_order_message,
            shop=shop,
            shop_settings=shop_settings,
            flowers=flowers,
            current_state=state,
            user_message=user_text,
        )
    except AIUnavailableError:
        await _handle_ai_unavailable_order_message(
            message=message,
            shop=shop,
            shop_settings=shop_settings,
            customer_id=customer.id,
            state=state,
            user_text=user_text,
            flowers=flowers,
        )
        return

    new_state = ai_response.state.model_dump()
    new_state["ai_requests_used"] = ai_requests_used + 1

    should_validate = ai_response.message_kind not in {"irrelevant", "unsafe"}
    validation = None
    show_manager_help_keyboard = False
    if should_validate:
        validation = validate_order_state(
            new_state,
            min_order_price=shop_settings.min_order_price if shop_settings else None,
            timezone=shop.timezone,
        )
        new_state = validation.state

    if validation is not None and validation.is_ready_for_options:
        template_options = build_template_bouquet_options(
            shop_id=shop.id,
            budget=new_state.get("budget"),
            colors=new_state.get("colors") or [],
            style=new_state.get("style"),
        )
        stock_options = build_bouquet_options(
            flowers=flowers,
            budget=new_state.get("budget"),
            colors=new_state.get("colors") or [],
            style=new_state.get("style"),
        )
        options = [*template_options, *stock_options]
        if options:
            new_state["bouquet_options"] = options
            new_state["selected_flowers"] = []
            new_state["estimated_price"] = None
            new_state["is_ready_for_confirmation"] = False
            ai_response.reply = _build_bouquet_options_message(options)
        else:
            new_state["bouquet_options"] = []
            new_state["is_ready_for_confirmation"] = False
            show_manager_help_keyboard = True
            ai_response.reply = _build_no_bouquet_options_message(new_state, flowers)
    else:
        new_state["is_ready_for_confirmation"] = False
        new_state["bouquet_options"] = []
        if validation is not None and validation.errors:
            ai_response.reply = _build_validation_message(validation.errors)
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

    add_conversation_log(
        shop_id=shop.id,
        customer_id=customer.id,
        role="bot",
        message=ai_response.reply,
        meta={
            "message_kind": ai_response.message_kind,
            "missing_fields": ai_response.missing_fields,
        },
    )

    await message.answer(
        ai_response.reply,
        reply_markup=(
            _bouquet_options_keyboard(new_state.get("bouquet_options") or [])
            if new_state.get("bouquet_options")
            else _customer_order_keyboard(
                image_enabled=_is_image_generation_enabled(shop.id),
            )
            if new_state.get("is_ready_for_confirmation")
            else _manager_help_keyboard()
            if show_manager_help_keyboard
            or int(new_state.get("ai_requests_used") or 0) >= MAX_AI_REQUESTS_PER_ORDER
            else None
        ),
    )


async def _handle_ai_unavailable_order_message(
    *,
    message: Message,
    shop,
    shop_settings,
    customer_id: int,
    state: dict,
    user_text: str,
    flowers: list,
) -> None:
    logger.exception("AI order parser is unavailable")

    new_state = _merge_fallback_order_details(state, user_text)
    validation = validate_order_state(
        new_state,
        min_order_price=shop_settings.min_order_price if shop_settings else None,
        timezone=shop.timezone,
    )
    new_state = validation.state

    if validation.is_ready_for_options:
        options = [
            *build_template_bouquet_options(
                shop_id=shop.id,
                budget=new_state.get("budget"),
                colors=new_state.get("colors") or [],
                style=new_state.get("style"),
            ),
            *build_bouquet_options(
                flowers=flowers,
                budget=new_state.get("budget"),
                colors=new_state.get("colors") or [],
                style=new_state.get("style"),
            ),
        ]
        if options:
            new_state["bouquet_options"] = options
            new_state["selected_flowers"] = []
            new_state["estimated_price"] = None
            new_state["is_ready_for_confirmation"] = False
            reply = (
                "AI сейчас недоступен, но я собрал варианты по данным из сообщения.\n\n"
                + _build_bouquet_options_message(options)
            )
            reply_markup = _bouquet_options_keyboard(options)
        else:
            new_state["bouquet_options"] = []
            new_state["is_ready_for_confirmation"] = False
            reply = (
                "AI сейчас недоступен, а подходящие варианты по складу не нашлись. "
                "Лучше подключить менеджера, он быстро соберет букет вручную."
            )
            reply_markup = _manager_help_keyboard()
    else:
        new_state["is_ready_for_confirmation"] = False
        new_state["bouquet_options"] = []
        reply = (
            "AI сейчас недоступен, но я сохранил то, что смог разобрать. "
            + _build_validation_message(validation.errors)
        )
        reply_markup = _manager_help_keyboard()

    update_conversation_state(
        shop_id=shop.id,
        customer_id=customer_id,
        state=new_state,
    )
    add_conversation_log(
        shop_id=shop.id,
        customer_id=customer_id,
        role="bot",
        message=reply,
        meta={"fallback": "ai_unavailable", "validation_errors": validation.errors},
    )
    await message.answer(reply, reply_markup=reply_markup)


def _merge_fallback_order_details(state: dict, user_text: str) -> dict:
    updated = dict(state)
    text = (user_text or "").strip()
    normalized = text.lower()

    phone_match = re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", text)
    if phone_match:
        updated["phone"] = re.sub(r"[^\d+]", "", phone_match.group(0))

    budget_match = re.search(
        r"(?:бюджет|до|на|примерно)?\s*(\d+(?:[.,]\d+)?)\s*(тыс|тысяч|к|k)?",
        normalized,
    )
    if budget_match and any(word in normalized for word in ("бюджет", "руб", "тыс", "₽")):
        amount = float(budget_match.group(1).replace(",", "."))
        if budget_match.group(2):
            amount *= 1000
        updated["budget"] = amount

    for marker, value in (
        ("послезавтра", "послезавтра"),
        ("завтра", "завтра"),
        ("сегодня", "сегодня"),
    ):
        if marker in normalized:
            updated["delivery_date"] = value
            break
    if not updated.get("delivery_date"):
        date_match = re.search(r"\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b", text)
        if date_match:
            updated["delivery_date"] = date_match.group(0)

    recipient_markers = {
        "мам": "мама",
        "жен": "жена/девушка",
        "девуш": "жена/девушка",
        "подруг": "подруга",
        "сестр": "сестра",
        "муж": "мужчина",
        "парн": "мужчина",
    }
    if not updated.get("recipient"):
        for marker, value in recipient_markers.items():
            if marker in normalized:
                updated["recipient"] = value
                break

    if not updated.get("occasion"):
        if "день рождения" in normalized or re.search(r"\bдр\b", normalized):
            updated["occasion"] = "день рождения"
        elif "без повода" in normalized:
            updated["occasion"] = "без повода"

    style_markers = {
        "нежн": "нежный",
        "ярк": "яркий",
        "романтич": "романтичный",
        "классич": "классический",
        "минимал": "минималистичный",
        "пастел": "пастельный",
    }
    if not updated.get("style"):
        for marker, value in style_markers.items():
            if marker in normalized:
                updated["style"] = value
                break

    color_markers = {
        "красн": "red",
        "син": "blue",
        "голуб": "blue",
        "бел": "white",
        "розов": "pink",
        "желт": "yellow",
        "фиолет": "purple",
        "сирен": "lavender",
        "лаванд": "lavender",
    }
    colors = list(updated.get("colors") or [])
    for marker, value in color_markers.items():
        if marker in normalized and value not in colors:
            colors.append(value)
    updated["colors"] = colors

    address_match = re.search(
        r"(?:адрес|доставка|доставить)\s+(.+?)(?:\s+(?:телефон|тел|номер|\+?\d[\d\s().-]{7,}\d)|$)",
        text,
        flags=re.IGNORECASE,
    )
    if address_match:
        updated["delivery_address"] = address_match.group(1).strip(" ,.;")

    return updated


def _apply_customer_history_shortcuts(
    *,
    shop_id: int,
    customer_id: int,
    state: dict,
    user_message: str,
) -> dict:
    normalized = (user_message or "").strip().lower()
    history_markers = (
        "как в прошлый раз",
        "повторить заказ",
        "повтори заказ",
        "тот же адрес",
        "тот же телефон",
    )
    if not any(marker in normalized for marker in history_markers):
        return state

    try:
        previous_orders = list_recent_orders_for_customer(shop_id, customer_id, limit=1)
    except Exception:
        logger.exception("Failed to load customer order history")
        return state
    if not previous_orders:
        return state

    previous = previous_orders[0]
    updated = dict(state)
    if "повтор" in normalized or "как в прошлый раз" in normalized:
        for key in (
            "occasion",
            "recipient",
            "budget",
            "style",
            "colors",
            "avoid_flowers",
            "delivery_address",
            "phone",
            "selected_flowers",
            "estimated_price",
            "summary",
        ):
            value = _state_value_from_order(previous, key)
            if value not in (None, "", []):
                updated[key] = value

    if ("тот же адрес" in normalized or "как в прошлый раз" in normalized) and previous.delivery_address:
        updated["delivery_address"] = previous.delivery_address

    if ("тот же телефон" in normalized or "как в прошлый раз" in normalized) and previous.phone:
        updated["phone"] = previous.phone

    return updated


def _state_value_from_order(order, key: str):
    if key == "selected_flowers":
        return (order.selected_variant or {}).get("flowers") if order.selected_variant else []
    if key == "estimated_price":
        return float(order.total_price) if order.total_price is not None else None
    if key == "summary":
        return (order.selected_variant or {}).get("title") if order.selected_variant else None
    value = getattr(order, key, None)
    if key == "budget" and value is not None:
        return float(value)
    return value


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

            await message.answer(_build_shop_greeting_text(shop))
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
        "Нашел магазины в вашем городе. Выберите нужный кнопкой ниже или отправьте цифру:\n\n"
        + "\n".join(lines),
        reply_markup=_shop_selection_keyboard(shops),
    )


def _build_shop_greeting_text(shop) -> str:
    shop_settings = get_shop_settings(shop.id)
    greeting = (
        shop_settings.greeting_text
        if shop_settings and shop_settings.greeting_text
        else f"Здравствуйте! Это бот магазина «{shop.name}»."
    )
    return (
        f"{greeting}\n\n"
        "Чтобы быстрее собрать заказ, напишите все пожелания одним сообщением: "
        "для кого букет, повод, бюджет, стиль или цвета, дата, адрес доставки и телефон.\n\n"
        + _commands_help_text()
    )


def _shop_selection_keyboard(shops: list) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=shop.name,
                    callback_data=f"select_shop:{shop.id}",
                )
            ]
            for shop in shops
        ]
    )


def _is_confirmation_message(text: str | None) -> bool:
    normalized = (text or "").strip().lower()
    return normalized in {"да", "подтверждаю", "подходит", "ок", "окей", "yes", "y"}


def _commands_help_text() -> str:
    return (
        "Полезные команды:\n"
        "/new_order — новый заказ в текущем магазине\n"
        "/change_shop — выбрать другой магазин\n"
        "/reset — сбросить текущий заказ\n"
        "/manager — позвать менеджера\n"
        "/help — показать команды"
    )


def _status_label(status: str) -> str:
    labels = {
        "new": "новый",
        "accepted": "принят",
        "awaiting_payment": "ожидает оплаты",
        "in_progress": "в работе",
        "done": "готов",
        "cancelled": "отменен",
        "paid": "оплачен",
    }
    return labels.get(status, status)


def _build_customer_status_message(order_id: int, status: str) -> str:
    status_label = _status_label(status)
    messages = {
        "accepted": "Менеджер принял заказ и скоро уточнит детали.",
        "awaiting_payment": "Счет отправлен, ожидаем оплату.",
        "in_progress": "Заказ уже в работе.",
        "done": "Заказ готов.",
        "cancelled": "Заказ отменен. Если это ошибка, напишите /manager.",
    }
    details = messages.get(status, "Статус заказа обновлен.")
    return f"Статус заказа №{order_id}: {status_label}\n{details}"


def _is_private_message(message: Message) -> bool:
    chat_type = message.chat.type
    return getattr(chat_type, "value", chat_type) == "private"


def _is_private_callback(callback: CallbackQuery) -> bool:
    if callback.message is None:
        return True

    chat_type = callback.message.chat.type
    return getattr(chat_type, "value", chat_type) == "private"


async def _request_manager_help(
    message: Message,
    shop,
    customer_id: int,
    state: dict,
    *,
    customer_user: User | None = None,
) -> None:
    if state.get("manager_requested"):
        await message.answer(
            "Я уже отправил заявку менеджеру. Он свяжется с вами, как только увидит сообщение."
        )
        return

    manager_chat_id = _get_manager_chat_id(shop.id)
    if not manager_chat_id:
        await message.answer(
            "Пока не настроен чат менеджеров. Напишите /new_order, чтобы начать заново, "
            "или попробуйте уточнить заказ еще раз."
        )
        return

    try:
        await message.bot.send_message(
            manager_chat_id,
            _build_manager_help_message(customer_user, shop.name, state),
            reply_markup=_manager_customer_contact_keyboard(customer_user),
            parse_mode=None,
        )
    except Exception:
        logger.exception("Failed to request manager help")
        await message.answer(
            "Не смог отправить сообщение менеджеру. Попробуйте еще раз чуть позже."
        )
        return

    update_conversation_state(
        shop_id=shop.id,
        customer_id=customer_id,
        state={**state, "manager_requested": True},
    )
    await message.answer(
        "Позвал менеджера и передал ему текущие детали заказа. "
        "Он свяжется с вами, чтобы договориться вручную."
    )


def _get_manager_chat_id(shop_id: int) -> int | None:
    shop_settings = get_shop_settings(shop_id)
    if shop_settings and shop_settings.manager_chat_id:
        return shop_settings.manager_chat_id
    return settings.default_manager_chat_id


def _build_manager_help_message(
    customer_user: User | None,
    shop_name: str,
    state: dict,
) -> str:
    flowers = state.get("selected_flowers") or []
    flowers_text = ", ".join(
        f"{item.get('name')} x{item.get('quantity')}" for item in flowers
    ) or "еще не выбран"

    username = (
        f"@{customer_user.username}"
        if customer_user and customer_user.username
        else "не указан"
    )
    user_id = customer_user.id if customer_user else "не указан"
    first_name = customer_user.first_name if customer_user else "не указано"
    reply_hint = (
        f"/message {user_id} текст сообщения"
        if isinstance(user_id, int)
        else "/message telegram_id текст сообщения"
    )

    return (
        "Клиент просит менеджера\n"
        f"Магазин: {shop_name}\n"
        f"Клиент: {first_name}, {username}, id {user_id}\n"
        f"Для кого: {_display_value(state.get('recipient'))}\n"
        f"Повод: {_display_value(state.get('occasion'))}\n"
        f"Бюджет: {_display_value(state.get('budget'))}\n"
        f"Стиль: {_display_value(state.get('style'))}\n"
        f"Цвета: {', '.join(state.get('colors') or []) or 'не указаны'}\n"
        f"Выбранный букет: {flowers_text}\n"
        f"Цена: {_display_value(state.get('estimated_price'))}\n"
        f"Дата: {_display_value(state.get('delivery_date'))}\n"
        f"Адрес: {_display_value(state.get('delivery_address'))}\n"
        f"Телефон: {_display_value(state.get('phone'))}\n"
        f"Комментарий: {_display_value(state.get('comment'))}\n\n"
        f"Если кнопка ниже не открыла диалог, ответьте через бота: {reply_hint}"
    )


async def _submit_order(
    message: Message,
    shop,
    customer_id: int,
    state: dict,
) -> None:
    if state.get("order_submitted"):
        await message.answer(
            "Этот заказ уже создан. Чтобы оформить новый, нажмите /new_order.",
            reply_markup=_post_order_keyboard(),
        )
        return

    shop_settings = get_shop_settings(shop.id)
    validation = validate_order_state(
        state,
        min_order_price=shop_settings.min_order_price if shop_settings else None,
        timezone=getattr(shop, "timezone", None),
    )
    if validation.errors:
        update_conversation_state(
            shop_id=shop.id,
            customer_id=customer_id,
            state={**validation.state, "is_ready_for_confirmation": False},
        )
        await message.answer(
            _build_validation_message(validation.errors),
            reply_markup=_manager_help_keyboard(),
        )
        return

    state = validation.state

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
        state={**state, "order_submitted": True, "submitted_order_id": order.id},
    )

    customer = get_customer_by_id(customer_id)
    manager_text = _build_manager_order_message_v2(order.id, shop.name, state, customer)
    manager_chat_id = _get_manager_chat_id(shop.id)
    manager_notified = False

    if manager_chat_id:
        try:
            await message.bot.send_message(
                manager_chat_id,
                manager_text,
                reply_markup=_manager_order_keyboard(order.id, customer),
                parse_mode=None,
            )
            manager_notified = True
        except Exception:
            logger.exception("Failed to send order notification to manager chat")

    await _send_customer_order_completion(
        message=message,
        order=order,
        shop_name=shop.name,
        state=state,
        manager_notified=manager_notified,
    )


async def _send_customer_order_completion(
    *,
    message: Message,
    order,
    shop_name: str,
    state: dict,
    manager_notified: bool,
) -> None:
    text = _build_customer_order_card(order.id, shop_name, state)
    if not manager_notified:
        text += (
            "\n\nЗаказ сохранен, но группа менеджеров еще не настроена. "
            "Чтобы получать уведомления в Telegram-группу, добавьте бота в группу, "
            "напишите там /chat_id и укажите этот chat_id в DEFAULT_MANAGER_CHAT_ID "
            "или в shop_settings.manager_chat_id."
        )

    await message.answer(text, reply_markup=_post_order_keyboard())
    await _send_payment_invoice(message, order, shop_name, state)


async def _send_payment_invoice(
    message: Message,
    order,
    shop_name: str,
    state: dict,
) -> None:
    if not settings.payment_provider_token:
        await message.answer(
            "Онлайн-оплата пока не подключена. Менеджер пришлет способ оплаты после проверки заказа."
        )
        return

    shop_settings = get_shop_settings(order.shop_id)
    payment_mode = shop_settings.payment_mode if shop_settings else "full_prepay"
    if payment_mode == "after_manager_confirmation":
        await message.answer("Оплата будет доступна после подтверждения заказа менеджером.")
        return

    amount = _payment_amount_minor(order.total_price, payment_mode=payment_mode)
    if amount is None:
        await message.answer("Сумма заказа пока не определена. Менеджер уточнит оплату вручную.")
        return

    description_parts = [
        f"Заказ №{order.id}",
        str(state.get("summary") or state.get("occasion") or "букет"),
        str(state.get("delivery_date") or ""),
    ]
    description = ". ".join(part for part in description_parts if part).strip()

    try:
        await message.bot.send_invoice(
            chat_id=message.chat.id,
            title=f"Букет от «{shop_name}»",
            description=description[:240],
            payload=f"order:{order.id}",
            provider_token=settings.payment_provider_token,
            currency=settings.payment_currency,
            prices=[LabeledPrice(label=_payment_label(order.id, payment_mode), amount=amount)],
            start_parameter=f"flower-order-{order.id}",
        )
        update_order_payment_status(order.id, "invoice_sent")
    except Exception:
        logger.exception("Failed to send payment invoice")
        await message.answer(
            "Заказ создан, но счет на оплату сейчас не удалось отправить. Менеджер поможет с оплатой вручную."
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


def _build_validation_message(errors: list[str]) -> str:
    return (
        "Чтобы корректно оформить заказ, уточните: "
        + ", ".join(errors)
        + ".\n\n"
        "Можно одним сообщением, например: букет для мамы, день рождения, бюджет 5000, "
        "нежный стиль, завтра, Абая 21, +77015064262."
    )


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


def _build_no_bouquet_options_message(state: dict, flowers: list) -> str:
    budget = state.get("budget")
    budget_text = (
        f"{float(budget):.0f} руб."
        if budget not in (None, "")
        else "не указан"
    )
    colors = ", ".join(_display_color(color) for color in state.get("colors") or [])
    colors_text = colors or "не указаны"
    available_text = _format_available_flowers_brief(flowers)

    return (
        "Не смог собрать варианты по текущим условиям.\n"
        f"Я понял бюджет: {budget_text}\n"
        f"Цвета: {colors_text}\n"
        f"Свободные цветы сейчас: {available_text}\n\n"
        "Если бюджет или цвет распознались неверно, напишите одним сообщением: "
        "бюджет 7000, цвет белый, стиль нежный. Либо позовите менеджера."
    )


def _format_available_flowers_brief(flowers: list, limit: int = 5) -> str:
    items = []
    for flower in flowers[:limit]:
        free_quantity = int(flower.quantity_available or 0) - int(flower.quantity_reserved or 0)
        items.append(
            f"{flower.name.strip()} {_display_color(flower.color)} "
            f"{free_quantity} шт. по {float(flower.price_per_stem):.0f} руб."
        )

    if not items:
        return "нет активных свободных цветов"

    if len(flowers) > limit:
        items.append(f"еще {len(flowers) - limit} поз.")

    return "; ".join(items)


def _display_color(color: object) -> str:
    labels = {
        "red": "красный",
        "white": "белый",
        "pink": "розовый",
        "blue": "синий",
        "purple": "фиолетовый",
        "lavender": "лавандовый",
        "yellow": "желтый",
    }
    value = str(color or "").strip().lower()
    return labels.get(value, value or "цвет не указан")


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


def _build_manager_order_message(
    order_id: int,
    shop_name: str,
    state: dict,
    customer=None,
) -> str:
    flowers = state.get("selected_flowers") or []
    flowers_text = ", ".join(
        f"{item.get('name')} x{item.get('quantity')}" for item in flowers
    ) or "не указаны"
    customer_text = _format_manager_customer_line(customer)

    total_price = state.get("estimated_price")
    total_price_text = (
        f"{float(total_price):.0f} руб."
        if total_price not in (None, "")
        else "уточнить"
    )

    return (
        f"Принят новый заказ №{order_id} на сумму {total_price_text}\n"
        f"Магазин: {shop_name}\n"
        f"{customer_text}\n"
        f"Для кого: {state.get('recipient')}\n"
        f"Повод: {state.get('occasion')}\n"
        f"Бюджет: {state.get('budget')}\n"
        f"Цветы: {flowers_text}\n"
        f"Цена: {total_price_text}\n"
        "Оплата: счет отправлен клиенту после оформления, если подключен PAYMENT_PROVIDER_TOKEN\n"
        f"Дата: {_display_value(state.get('delivery_date'))}\n"
        f"Адрес: {_display_value(state.get('delivery_address'))}\n"
        f"Телефон: {_display_value(state.get('phone'))}\n"
        f"Комментарий: {_display_value(state.get('comment'))}\n\n"
        f"Ответить клиенту по заказу: /reply {order_id} текст сообщения"
    )


def _build_manager_order_message_v2(
    order_id: int,
    shop_name: str,
    state: dict,
    customer=None,
) -> str:
    flowers = state.get("selected_flowers") or []
    flowers_text = ", ".join(
        f"{item.get('name')} x{item.get('quantity')}" for item in flowers
    ) or "состав не указан"
    customer_text = _format_manager_customer_line(customer)

    total_price = state.get("estimated_price")
    total_price_text = (
        f"{float(total_price):.0f} руб."
        if total_price not in (None, "")
        else "уточнить"
    )
    budget = state.get("budget")
    budget_text = (
        f"{float(budget):.0f} руб."
        if budget not in (None, "")
        else "не указан"
    )
    payment_text = (
        "счет отправится клиенту автоматически"
        if settings.payment_provider_token
        else "ручная оплата после проверки менеджером"
    )

    return (
        f"Новый заказ №{order_id}\n"
        f"Магазин: {shop_name}\n"
        f"{customer_text}\n"
        "Статус: новый\n"
        f"Оплата: {payment_text}\n"
        f"Сумма: {total_price_text}\n\n"
        f"Букет: {_display_value(state.get('summary'))}\n"
        f"Состав: {flowers_text}\n"
        f"Для кого: {_display_value(state.get('recipient'))}\n"
        f"Повод: {_display_value(state.get('occasion'))}\n"
        f"Бюджет клиента: {budget_text}\n"
        f"Стиль: {_display_value(state.get('style'))}\n"
        f"Цвета: {_format_manager_colors(state)}\n\n"
        f"Доставка: {_display_value(state.get('delivery_date'))}\n"
        f"Адрес: {_display_value(state.get('delivery_address'))}\n"
        f"Телефон: {_display_value(state.get('phone'))}\n"
        f"Комментарий: {_display_value(state.get('comment'))}\n\n"
        f"Ответить клиенту: /reply {order_id} текст сообщения"
    )


def _format_manager_colors(state: dict) -> str:
    colors = state.get("colors") or []
    if not colors:
        return "не указаны"
    return ", ".join(_display_color(color) for color in colors)


def _display_value(value: object) -> object:
    return value if value not in (None, "") else "не указан"


def _format_manager_customer_line(customer) -> str:
    if customer is None:
        return "Клиент Telegram: не найден"

    username = (
        f"@{customer.telegram_username}"
        if getattr(customer, "telegram_username", None)
        else "username не указан"
    )
    first_name = getattr(customer, "first_name", None) or "имя не указано"
    telegram_user_id = getattr(customer, "telegram_user_id", None) or "id не указан"
    return f"Клиент Telegram: {first_name}, {username}, id {telegram_user_id}"


def _manager_customer_contact_keyboard(customer_contact) -> InlineKeyboardMarkup | None:
    contact_url = _customer_contact_url(customer_contact)
    if not contact_url:
        return None

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть диалог с клиентом",
                    url=contact_url,
                )
            ]
        ]
    )


def _customer_contact_url(customer_contact) -> str | None:
    if customer_contact is None:
        return None

    username = (
        getattr(customer_contact, "telegram_username", None)
        or getattr(customer_contact, "username", None)
    )
    if username:
        return f"https://t.me/{str(username).lstrip('@')}"

    telegram_user_id = (
        getattr(customer_contact, "telegram_user_id", None)
        or getattr(customer_contact, "id", None)
    )
    if telegram_user_id:
        return f"tg://user?id={telegram_user_id}"

    return None


def _get_manager_shop_for_message(message: Message):
    if _is_private_message(message):
        return None
    return get_shop_by_manager_chat_id(message.chat.id)


def _is_default_manager_chat(message: Message) -> bool:
    return (
        settings.default_manager_chat_id is not None
        and message.chat.id == settings.default_manager_chat_id
    )


def _build_orders_list_message(scope_title: str, orders: list) -> str:
    lines = [f"Последние заказы {scope_title}:"]
    for order in orders:
        price = (
            f"{Decimal(str(order.total_price)):.0f} руб."
            if order.total_price not in (None, "")
            else "сумма не указана"
        )
        lines.append(
            f"№{order.id}: {_status_label(order.status)}, "
            f"{_payment_status_label(order.payment_status)}, {price}\n"
            f"Дата: {_display_value(order.delivery_date)}\n"
            f"Телефон: {_display_value(order.phone)}"
        )
    lines.append(
        "\nОтвет клиенту по заказу: /reply 12 текст сообщения\n"
        "Сообщение по Telegram ID: /message telegram_id текст сообщения"
    )
    return "\n\n".join(lines)


def _payment_amount_minor(
    total_price: object,
    *,
    payment_mode: str = "full_prepay",
) -> int | None:
    if total_price in (None, ""):
        return None

    try:
        amount = Decimal(str(total_price)).quantize(Decimal("0.01"))
        if payment_mode == "prepay_50":
            amount = (amount * Decimal("0.5")).quantize(Decimal("0.01"))
        amount = amount * 100
    except Exception:
        return None

    amount_minor = int(amount)
    return amount_minor if amount_minor > 0 else None


def _payment_label(order_id: int, payment_mode: str) -> str:
    if payment_mode == "prepay_50":
        return f"Предоплата 50% по заказу №{order_id}"
    return f"Заказ №{order_id}"


def _order_id_from_payment_payload(payload: str | None) -> int | None:
    if not payload or not payload.startswith("order:"):
        return None

    order_id_text = payload.split(":", maxsplit=1)[1]
    if not order_id_text.isdigit():
        return None
    return int(order_id_text)


def _payment_status_label(status: str | None) -> str:
    labels = {
        "not_paid": "не оплачен",
        "invoice_sent": "счет отправлен",
        "prepaid": "предоплата получена",
        "paid": "оплачен",
        "failed": "оплата не прошла",
        "refunded": "возврат",
    }
    return labels.get(status or "not_paid", status or "не оплачен")


def _is_image_generation_enabled(shop_id: int) -> bool:
    shop_settings = get_shop_settings(shop_id)
    return bool(shop_settings and shop_settings.image_generation_enabled)


def _build_image_caption(state: dict) -> str:
    price = state.get("estimated_price")
    price_text = f"{float(price):.0f} руб." if price not in (None, "") else "уточнить"
    return (
        f"Эскиз букета: {_display_value(state.get('summary'))}\n"
        f"Примерная цена: {price_text}\n"
        "Изображение примерное: финальный букет зависит от наличия цветов и сборки флориста."
    )


def _post_order_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Новый заказ",
                    callback_data="reset_order",
                ),
                InlineKeyboardButton(
                    text="Другой магазин",
                    callback_data="change_shop_button",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Позвать менеджера",
                    callback_data="call_manager",
                )
            ],
        ]
    )


def _customer_order_keyboard(*, image_enabled: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="Подтвердить заказ",
                callback_data="confirm_order",
            )
        ]
    ]
    if image_enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Показать эскиз букета",
                    callback_data="generate_image",
                )
            ]
        )

    rows.extend(
        [
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
            [
                InlineKeyboardButton(
                    text="Позвать менеджера",
                    callback_data="call_manager",
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _manager_help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Позвать менеджера",
                    callback_data="call_manager",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Новый заказ",
                    callback_data="reset_order",
                ),
                InlineKeyboardButton(
                    text="Изменить пожелания",
                    callback_data="change_order",
                ),
            ],
        ]
    )


def _manager_order_keyboard(order_id: int, customer=None) -> InlineKeyboardMarkup:
    rows = []
    contact_url = _customer_contact_url(customer)
    if contact_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Открыть диалог с клиентом",
                    url=contact_url,
                )
            ]
        )

    rows.extend(
        [
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
    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def _build_customer_order_card(order_id: int, shop_name: str, state: dict) -> str:
    flowers = state.get("selected_flowers") or []
    flowers_text = ", ".join(
        f"{item.get('name')} x{item.get('quantity')}" for item in flowers
    ) or "состав уточнит менеджер"
    price_text = (
        f"{float(state.get('estimated_price')):.0f} руб."
        if state.get("estimated_price") not in (None, "")
        else "уточнит менеджер"
    )
    payment_text = (
        "Счет на оплату придет следующим сообщением."
        if settings.payment_provider_token
        else "Оплату менеджер пришлет вручную после проверки заказа."
    )

    return (
        f"Заказ №{order_id} принят\n\n"
        f"Магазин: {shop_name}\n"
        f"Букет: {flowers_text}\n"
        f"Примерная цена: {price_text}\n"
        f"Для кого: {_display_value(state.get('recipient'))}\n"
        f"Повод: {_display_value(state.get('occasion'))}\n"
        f"Доставка: {_display_value(state.get('delivery_date'))}, {_display_value(state.get('delivery_address'))}\n"
        f"Телефон: {_display_value(state.get('phone'))}\n"
        f"Оплата: {payment_text}\n\n"
        "Менеджер проверит наличие цветов, финальную стоимость и скоро свяжется с вами."
    )
