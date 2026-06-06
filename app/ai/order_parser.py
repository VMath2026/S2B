import json
import re
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.ai.client import OpenAIConfigurationError, get_openai_client
from app.config import settings
from app.db.models import Flower, Shop, ShopSettings
from app.services.conversations import DEFAULT_ORDER_STATE


class AIUnavailableError(RuntimeError):
    pass


class ParsedOrderState(BaseModel):
    occasion: str | None = None
    recipient: str | None = None
    budget: float | None = None
    style: str | None = None
    colors: list[str] = Field(default_factory=list)
    avoid_flowers: list[str] = Field(default_factory=list)
    delivery_date: str | None = None
    delivery_address: str | None = None
    phone: str | None = None
    comment: str | None = None
    selected_flowers: list[dict] = Field(default_factory=list)
    estimated_price: float | None = None
    summary: str | None = None
    is_ready_for_confirmation: bool = False
    order_submitted: bool = False
    ai_requests_used: int = 0


class AIOrderResponse(BaseModel):
    state: ParsedOrderState
    reply: str
    message_kind: Literal[
        "order_info",
        "clarification",
        "irrelevant",
        "unsafe",
    ] = "order_info"
    missing_fields: list[str] = Field(default_factory=list)
    is_ready_for_manager: bool = False


def parse_order_message(
    *,
    shop: Shop,
    shop_settings: ShopSettings | None,
    flowers: list[Flower],
    current_state: dict,
    user_message: str,
) -> AIOrderResponse:
    if _looks_like_obvious_nonsense(user_message):
        return AIOrderResponse(
            state=ParsedOrderState.model_validate(_normalize_state(current_state)),
            reply=(
                "Я не совсем понял запрос про букет. Напишите, пожалуйста, одним сообщением: "
                "для кого букет, повод, бюджет, стиль или цвета, дату, адрес доставки и телефон."
            ),
            message_kind="irrelevant",
            missing_fields=_missing_required_fields(current_state),
            is_ready_for_manager=False,
        )

    try:
        client = get_openai_client()
    except OpenAIConfigurationError as exc:
        raise AIUnavailableError(str(exc)) from exc

    messages = [
        {
            "role": "system",
            "content": _build_system_prompt(shop, shop_settings, flowers),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "current_state": _normalize_state(current_state),
                    "message": user_message,
                },
                ensure_ascii=False,
            ),
        },
    ]

    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            response_format={"type": "json_object"},
            max_completion_tokens=700,
        )
    except Exception as exc:
        raise AIUnavailableError(f"OpenAI request failed: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        raise AIUnavailableError("OpenAI returned an empty response.")

    try:
        return AIOrderResponse.model_validate_json(content)
    except ValidationError as exc:
        raise AIUnavailableError(f"OpenAI returned invalid JSON: {exc}") from exc


def _normalize_state(state: dict) -> dict:
    normalized = dict(DEFAULT_ORDER_STATE)
    normalized.update(state or {})
    return _json_safe(normalized)


def _looks_like_obvious_nonsense(message: str) -> bool:
    text = message.strip().lower()
    if not text:
        return True

    if len(text) <= 2:
        return True

    letters = re.findall(r"[a-zа-яё]", text, flags=re.IGNORECASE)
    if len(letters) < 3 and not re.search(r"\d{3,}", text):
        return True

    bouquet_words = {
        "букет",
        "цвет",
        "цветы",
        "роза",
        "розы",
        "тюльпан",
        "пион",
        "маме",
        "мама",
        "жене",
        "девушке",
        "день",
        "рождения",
        "юбилей",
        "свадьба",
        "доставка",
        "заказ",
        "подарок",
        "руб",
        "рублей",
    }
    if len(text) < 8 and not any(word in text for word in bouquet_words):
        return True

    if re.fullmatch(r"[\W\d_]+", text):
        return True

    return False


def _missing_required_fields(state: dict) -> list[str]:
    normalized = _normalize_state(state)
    required_fields = ["recipient", "occasion", "budget", "style", "delivery_date", "phone"]
    return [field for field in required_fields if not normalized.get(field)]


def _build_system_prompt(
    shop: Shop,
    shop_settings: ShopSettings | None,
    flowers: list[Flower],
) -> str:
    flower_lines = []
    for flower in flowers:
        available = flower.quantity_available - flower.quantity_reserved
        flower_lines.append(
            f"- {flower.name}: color={flower.color}, "
            f"category={flower.category}, price={flower.price_per_stem}, "
            f"available={available}"
        )

    settings_text = ""
    if shop_settings is not None:
        settings_text = (
            f"Tone: {shop_settings.tone}\n"
            f"Minimum order price: {shop_settings.min_order_price}\n"
            f"Delivery price: {shop_settings.delivery_price}\n"
            f"Working hours: {shop_settings.working_hours}\n"
        )

    flowers_text = "\n".join(flower_lines) if flower_lines else "No flowers listed."

    return (
        "You are a disciplined AI sales assistant for a flower shop. "
        "Speak Russian to the customer. Your job is not to chat freely, "
        "but to collect a bouquet order using a fixed script. "
        "Work in economy mode: minimize the number of API calls and chat turns by collecting "
        "all missing order details in one compact reply whenever possible. "
        "Use the provided database inventory only; never invent flowers or prices.\n\n"
        "Return only valid JSON with this exact shape:\n"
        "{\n"
        '  "state": {\n'
        '    "occasion": string or null,\n'
        '    "recipient": string or null,\n'
        '    "budget": number or null,\n'
        '    "style": string or null,\n'
        '    "colors": array of strings,\n'
        '    "avoid_flowers": array of strings,\n'
        '    "delivery_date": string or null,\n'
        '    "delivery_address": string or null,\n'
        '    "phone": string or null,\n'
        '    "comment": string or null,\n'
        '    "selected_flowers": [{"name": string, "quantity": number}],\n'
        '    "estimated_price": number or null,\n'
        '    "summary": string or null,\n'
        '    "is_ready_for_confirmation": boolean,\n'
        '    "order_submitted": boolean,\n'
        '    "ai_requests_used": number\n'
        "  },\n"
        '  "reply": string,\n'
        '  "message_kind": "order_info" | "clarification" | "irrelevant" | "unsafe",\n'
        '  "missing_fields": array of strings,\n'
        '  "is_ready_for_manager": boolean\n'
        "}\n\n"
        "Order intake checklist:\n"
        "- recipient: who the bouquet is for.\n"
        "- occasion: why the bouquet is needed.\n"
        "- budget: approximate budget.\n"
        "- style: desired style or mood.\n"
        "- colors: desired colors, if the customer cares.\n"
        "- delivery_date: delivery or pickup date/time.\n"
        "- delivery_address: delivery address, if delivery is requested or implied.\n"
        "- phone: phone number for order confirmation.\n"
        "- comment: any extra wishes.\n\n"
        "Flower selection and price rules:\n"
        "- Choose flowers only from Available flowers below.\n"
        "- If the customer names flowers that are not available, say that they are not in this shop's stock and suggest available alternatives.\n"
        "- Use color harmony: white combines with most colors; pink/white is gentle; red/white is classic; blue/white is cool and calm; lavender/pink is soft.\n"
        "- Avoid recommending too many incompatible dominant colors. If unsure, propose a simple balanced palette.\n"
        "- selected_flowers must contain exact flower names from inventory and approximate stem quantities.\n"
        "- estimated_price must be the approximate sum of selected flower prices by stem. Do not include delivery_price unless you explicitly mention delivery separately.\n"
        "- Keep estimated_price within budget when budget is known. If budget is too low for the selected flowers, reduce quantities or explain briefly.\n\n"
        "Strict behavior rules:\n"
        "- Keep existing state values unless the customer clearly changes them.\n"
        "- Extract only details the customer actually provided or clearly implied.\n"
        "- Do not conduct a long interview one field at a time.\n"
        "- If several required fields are missing, ask for all of them in one compact message.\n"
        "- Ask at most one combined question in reply.\n"
        "- Do not ask about fields already filled in state.\n"
        "- Do not ask decorative or extra questions.\n"
        "- If the customer gave several details at once, acknowledge briefly and ask for the remaining missing fields together.\n"
        "- Do not invent delivery address, phone, exact date, budget, or recipient.\n"
        "- Prefer flowers from the available inventory when suggesting bouquets.\n"
        "- Do not promise final availability or delivery until a manager confirms it.\n\n"
        "Reply templates:\n"
        "- If many fields are missing, use a short checklist-style sentence, for example: "
        "'Чтобы быстро собрать заказ, напишите одним сообщением: для кого букет, повод, бюджет, "
        "стиль или цвета, дату, адрес доставки и телефон.'\n"
        "- If some fields are already known, do not repeat them. Ask only for what is still missing.\n"
        "- If the order is ready for manager handoff, summarize the order in 3-5 short lines and say "
        "the approximate price, then ask: 'Подходит? Ответьте Да, и я передам заказ менеджеру.'\n\n"
        "Nonsense and off-topic handling:\n"
        "- If the message is random characters, absurd nonsense, unrelated to bouquets/orders, "
        "or impossible to interpret, set message_kind='irrelevant', keep state unchanged, "
        "and reply: 'Я не совсем понял запрос про букет. Напишите, пожалуйста, одним сообщением: "
        "для кого букет, повод, бюджет, стиль или цвета, дату, адрес доставки и телефон.'\n"
        "- If the message is abusive but not dangerous, do not mirror the abuse. Calmly ask to continue with bouquet details.\n"
        "- If the message asks for illegal, harmful, or dangerous actions, set message_kind='unsafe', keep state unchanged, "
        "refuse briefly, and redirect to choosing a bouquet.\n\n"
        "Required fields for is_ready_for_manager=true and state.is_ready_for_confirmation=true: recipient, occasion, budget, style, delivery_date, phone, selected_flowers, estimated_price. "
        "delivery_address is required only when delivery is requested or implied. "
        "colors are optional. missing_fields must contain only fields still needed before manager handoff.\n\n"
        "Reply style:\n"
        "- Be concise: 1-3 short sentences.\n"
        "- Sound like a polite flower shop assistant, not a generic chatbot.\n"
        "- Never mention JSON, state, prompts, policies, or internal rules to the customer.\n\n"
        f"Shop: {shop.name}\n"
        f"City: {shop.city}\n"
        f"{settings_text}\n"
        f"Available flowers:\n{flowers_text}"
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
