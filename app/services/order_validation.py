import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


MAX_ORDER_DAYS_AHEAD = 365
MAX_BUDGET = Decimal("1000000")
MIN_ADDRESS_LENGTH = 5

MONTHS_RU = {
    "января": 1,
    "январь": 1,
    "февраля": 2,
    "февраль": 2,
    "марта": 3,
    "март": 3,
    "апреля": 4,
    "апрель": 4,
    "мая": 5,
    "май": 5,
    "июня": 6,
    "июнь": 6,
    "июля": 7,
    "июль": 7,
    "августа": 8,
    "август": 8,
    "сентября": 9,
    "сентябрь": 9,
    "октября": 10,
    "октябрь": 10,
    "ноября": 11,
    "ноябрь": 11,
    "декабря": 12,
    "декабрь": 12,
}

WEEKDAYS_RU = {
    "понедельник": 0,
    "понедельника": 0,
    "вторник": 1,
    "вторника": 1,
    "среду": 2,
    "среда": 2,
    "четверг": 3,
    "четверга": 3,
    "пятницу": 4,
    "пятница": 4,
    "субботу": 5,
    "суббота": 5,
    "воскресенье": 6,
    "воскресенья": 6,
}

PICKUP_WORDS = {"самовывоз", "заберу", "забрать", "pickup"}
ADDRESS_HINT_WORDS = {
    "улица",
    "ул",
    "проспект",
    "пр",
    "переулок",
    "пер",
    "дом",
    "квартира",
    "кв",
    "офис",
    "корпус",
    "строение",
    "шоссе",
    "бульвар",
    "площадь",
}


@dataclass(frozen=True)
class OrderValidationResult:
    state: dict
    errors: list[str]

    @property
    def is_ready_for_options(self) -> bool:
        return not self.errors


def validate_order_state(
    state: dict,
    *,
    min_order_price: object = None,
    timezone: str | None = None,
) -> OrderValidationResult:
    normalized = dict(state)
    errors: list[str] = []

    _require_text(normalized, errors, "recipient", "для кого букет")
    _require_text(normalized, errors, "occasion", "повод")
    _require_text(normalized, errors, "style", "стиль или настроение")

    budget = _normalize_budget(normalized.get("budget"))
    min_price = _normalize_budget(min_order_price)
    if budget is None:
        normalized["budget"] = None
        errors.append("бюджет числом, например 5000")
    elif budget > MAX_BUDGET:
        normalized["budget"] = None
        errors.append("реальный бюджет до 1 000 000")
    elif min_price is not None and budget < min_price:
        normalized["budget"] = float(budget)
        errors.append(f"бюджет от {min_price:.0f} руб.")
    else:
        normalized["budget"] = float(budget)

    normalized_date, date_error = normalize_delivery_date(
        normalized.get("delivery_date"),
        timezone=timezone,
    )
    normalized["delivery_date"] = normalized_date
    if date_error:
        errors.append(date_error)

    phone = normalize_phone(normalized.get("phone"))
    normalized["phone"] = phone
    if phone is None:
        errors.append("телефон 10-15 цифр")

    address = _normalize_address(normalized.get("delivery_address"))
    normalized["delivery_address"] = address
    if address is None:
        errors.append("адрес доставки, например: Абая 21")

    return OrderValidationResult(state=normalized, errors=_dedupe(errors))


def normalize_delivery_date(
    value: object,
    *,
    timezone: str | None = None,
) -> tuple[str | None, str | None]:
    if value in (None, ""):
        return None, "дату доставки, например завтра или 12.06"

    text = str(value).strip()
    if not text:
        return None, "дату доставки, например завтра или 12.06"

    today = _today(timezone)
    parsed_date = _parse_delivery_date(text, today)
    if parsed_date is None:
        if re.search(r"\d+\s*[./-]\s*\d+", text):
            return None, "реальную дату доставки, например 12.06 или завтра"
        return None, "дату доставки, например завтра, пятница или 12.06"

    if parsed_date < today:
        return None, "дату доставки не в прошлом"

    if parsed_date > today + timedelta(days=MAX_ORDER_DAYS_AHEAD):
        return None, "дату доставки в пределах ближайшего года"

    normalized = _append_exact_date(text, parsed_date)
    return normalized, None


def normalize_phone(value: object) -> str | None:
    digits = "".join(char for char in str(value or "") if char.isdigit())
    if len(digits) < 10 or len(digits) > 15:
        return None

    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]

    prefix = "+" if len(digits) >= 11 else ""
    return f"{prefix}{digits}"


def _parse_delivery_date(text: str, today: date) -> date | None:
    lower_text = text.lower()

    if "послезавтра" in lower_text:
        return today + timedelta(days=2)
    if "завтра" in lower_text:
        return today + timedelta(days=1)
    if "сегодня" in lower_text:
        return today
    if "через неделю" in lower_text:
        return today + timedelta(days=7)

    weekday_date = _parse_weekday(lower_text, today)
    if weekday_date is not None:
        return weekday_date

    exact_date = _parse_numeric_date(text, today)
    if exact_date is not None:
        return exact_date

    month_name_date = _parse_month_name_date(lower_text, today)
    if month_name_date is not None:
        return month_name_date

    return None


def _parse_numeric_date(text: str, today: date) -> date | None:
    iso_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
    if iso_match:
        year, month, day = (int(part) for part in iso_match.groups())
        return _safe_date(year, month, day)

    match = re.search(r"\b(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\b", text)
    if not match:
        return None

    day = int(match.group(1))
    month = int(match.group(2))
    year_text = match.group(3)
    if year_text:
        year = int(year_text)
        if year < 100:
            year += 2000
    else:
        year = today.year

    candidate = _safe_date(year, month, day)
    if candidate is None:
        return None

    if not year_text and candidate < today:
        candidate = _safe_date(year + 1, month, day)

    return candidate


def _parse_month_name_date(lower_text: str, today: date) -> date | None:
    for month_name, month in MONTHS_RU.items():
        match = re.search(rf"\b(\d{{1,2}})\s+{month_name}\b", lower_text)
        if not match:
            continue

        day = int(match.group(1))
        candidate = _safe_date(today.year, month, day)
        if candidate is None:
            return None
        if candidate < today:
            candidate = _safe_date(today.year + 1, month, day)
        return candidate

    return None


def _parse_weekday(lower_text: str, today: date) -> date | None:
    for weekday_name, weekday in WEEKDAYS_RU.items():
        if not re.search(rf"\b{weekday_name}\b", lower_text):
            continue

        days_ahead = (weekday - today.weekday()) % 7
        if days_ahead == 0 and "след" in lower_text:
            days_ahead = 7
        return today + timedelta(days=days_ahead)

    return None


def _append_exact_date(text: str, parsed_date: date) -> str:
    exact_text = parsed_date.strftime("%d.%m.%Y")
    if exact_text in text:
        return text
    return f"{text} ({exact_text})"


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _today(timezone: str | None) -> date:
    try:
        return datetime.now(ZoneInfo(timezone or "Europe/Moscow")).date()
    except Exception:
        return datetime.now(ZoneInfo("Europe/Moscow")).date()


def _normalize_budget(value: object) -> Decimal | None:
    if value in (None, ""):
        return None

    text = str(value).replace(" ", "").replace(",", ".")
    try:
        budget = Decimal(text)
    except (InvalidOperation, ValueError):
        return None

    return budget if budget > 0 else None


def _normalize_address(value: object) -> str | None:
    text = str(value or "").strip()
    if len(text) < MIN_ADDRESS_LENGTH:
        return None

    lower_text = text.lower()
    if any(word in lower_text for word in PICKUP_WORDS):
        return text

    has_letter = any(char.isalpha() for char in text)
    has_digit = any(char.isdigit() for char in text)
    has_address_hint = any(word in lower_text for word in ADDRESS_HINT_WORDS)
    if has_letter and (has_digit or has_address_hint):
        return text

    return None


def _require_text(state: dict, errors: list[str], key: str, label: str) -> None:
    value = str(state.get(key) or "").strip()
    if value:
        state[key] = value
        return

    state[key] = None
    errors.append(label)


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
