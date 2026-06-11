from decimal import Decimal
import re

from sqlalchemy import select

from app.db.models import BouquetExample
from app.db.session import SessionLocal


def build_template_bouquet_options(
    *,
    shop_id: int,
    budget: float | int | str | None,
    colors: list[str] | None = None,
    style: str | None = None,
    limit: int = 3,
) -> list[dict]:
    budget_decimal = _to_decimal_or_none(budget)
    with SessionLocal() as session:
        templates = list(
            session.scalars(
                select(BouquetExample)
                .where(BouquetExample.shop_id == shop_id)
                .order_by(BouquetExample.id.desc())
            ).all()
        )

    preferred_colors = {_normalize_text(color) for color in colors or [] if _normalize_text(color)}
    preferred_style = _normalize_text(style)
    options: list[dict] = []

    for template in templates:
        price = _to_decimal_or_none(template.price)
        if price is None:
            continue
        if budget_decimal is not None and price is not None and price > budget_decimal:
            continue
        if preferred_style and template.style and preferred_style not in _normalize_text(template.style):
            continue
        template_colors = {_normalize_text(color) for color in template.colors or [] if _normalize_text(color)}
        if preferred_colors and template_colors and preferred_colors.isdisjoint(template_colors):
            continue

        selected_flowers = _parse_template_flowers(template.flowers or [])
        if not selected_flowers:
            continue

        options.append(
            {
                "title": template.title or "Готовый букет",
                "description": template.description or "Готовый коммерческий вариант магазина.",
                "selected_flowers": selected_flowers,
                "estimated_price": float(price),
                "image_url": template.image_url,
                "source": "template",
            }
        )
        if len(options) >= limit:
            break

    return options


def _parse_template_flowers(flowers: list[str]) -> list[dict]:
    result: list[dict] = []
    for raw in flowers:
        text = str(raw or "").strip()
        if not text:
            continue

        quantity = 1
        quantity_match = re.search(r"(?:x|х|\*)\s*(\d+)|(\d+)\s*(?:шт|ст|pcs)?", text, flags=re.IGNORECASE)
        if quantity_match:
            quantity = int(quantity_match.group(1) or quantity_match.group(2))
            text = text[: quantity_match.start()].strip(" ,;:-")

        if text:
            result.append({"name": text, "quantity": max(1, quantity)})
    return result


def _normalize_text(value: object) -> str:
    return str(value or "").strip().lower()


def _to_decimal_or_none(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None
