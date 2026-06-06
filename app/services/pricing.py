from decimal import Decimal

from app.db.models import Flower


def calculate_selected_flowers_price(
    selected_flowers: list[dict],
    flowers: list[Flower],
) -> Decimal | None:
    if not selected_flowers:
        return None

    prices_by_name = {flower.name.lower(): flower.price_per_stem for flower in flowers}
    total = Decimal("0")
    matched_any = False

    for selected in selected_flowers:
        name = str(selected.get("name") or "").strip().lower()
        quantity = selected.get("quantity") or 0
        if not name or name not in prices_by_name:
            continue

        total += Decimal(str(prices_by_name[name])) * Decimal(str(quantity))
        matched_any = True

    if not matched_any:
        return None

    return total
