from decimal import Decimal
from itertools import combinations

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


def build_bouquet_options(
    *,
    flowers: list[Flower],
    budget: float | int | str | None,
    colors: list[str] | None = None,
    style: str | None = None,
    max_options: int = 7,
) -> list[dict]:
    budget_decimal = _to_decimal_or_none(budget)
    if budget_decimal is None or budget_decimal <= 0:
        return []

    available_flowers = [
        flower
        for flower in flowers
        if flower.price_per_stem
        and flower.quantity_available > flower.quantity_reserved
        and Decimal(str(flower.price_per_stem)) > 0
    ]
    if not available_flowers:
        return []

    preferred_colors = {color.strip().lower() for color in colors or [] if color}
    sorted_flowers = sorted(
        available_flowers,
        key=lambda flower: (
            0
            if preferred_colors and str(flower.color or "").lower() in preferred_colors
            else 1,
            Decimal(str(flower.price_per_stem)),
            flower.name,
        ),
    )

    options: list[dict] = []
    seen: set[tuple[tuple[str, int], ...]] = set()

    monobouquet_limit = min(3, max_options)
    for flower in sorted_flowers:
        if len(options) >= monobouquet_limit:
            break

        quantity = _odd_quantity(
            min(
                int(
                    budget_decimal
                    * Decimal("0.82")
                    / Decimal(str(flower.price_per_stem))
                ),
                flower.quantity_available - flower.quantity_reserved,
            )
        )
        if quantity >= 3:
            _append_option(
                options,
                seen,
                title=f"Монобукет: {flower.name}",
                description=_build_description([flower], style),
                selected_flowers=[{"name": flower.name, "quantity": quantity}],
                flowers=available_flowers,
                budget=budget_decimal,
                max_options=max_options,
            )

    for first, second in combinations(sorted_flowers, 2):
        selected_flowers = _build_mix_selection(
            [first, second],
            budget_decimal,
            [Decimal("0.55"), Decimal("0.30")],
        )
        if not selected_flowers:
            continue

        _append_option(
            options,
            seen,
            title=f"Микс: {first.name} + {second.name}",
            description=_build_description([first, second], style),
            selected_flowers=selected_flowers,
            flowers=available_flowers,
            budget=budget_decimal,
            max_options=max_options,
        )

    for first, second, third in combinations(sorted_flowers, 3):
        selected_flowers = _build_mix_selection(
            [first, second, third],
            budget_decimal,
            [Decimal("0.45"), Decimal("0.25"), Decimal("0.18")],
        )
        if not selected_flowers:
            continue

        _append_option(
            options,
            seen,
            title=f"Сборный букет: {first.name} + {second.name} + {third.name}",
            description=_build_description([first, second, third], style),
            selected_flowers=selected_flowers,
            flowers=available_flowers,
            budget=budget_decimal,
            max_options=max_options,
        )

    return options[:max_options]


def _build_mix_selection(
    flowers: list[Flower],
    budget: Decimal,
    budget_ratios: list[Decimal],
) -> list[dict]:
    selected_flowers: list[dict] = []
    for flower, ratio in zip(flowers, budget_ratios):
        price = Decimal(str(flower.price_per_stem))
        available = flower.quantity_available - flower.quantity_reserved
        quantity = _odd_quantity(min(int(budget * ratio / price), available))
        if quantity < 3:
            return []

        selected_flowers.append({"name": flower.name, "quantity": quantity})

    return selected_flowers


def _append_option(
    options: list[dict],
    seen: set[tuple[tuple[str, int], ...]],
    *,
    title: str,
    description: str,
    selected_flowers: list[dict],
    flowers: list[Flower],
    budget: Decimal,
    max_options: int,
) -> None:
    if len(options) >= max_options:
        return

    total = calculate_selected_flowers_price(selected_flowers, flowers)
    if total is None or total > budget:
        return

    signature = tuple(
        sorted((str(item["name"]), int(item["quantity"])) for item in selected_flowers)
    )
    if signature in seen:
        return

    seen.add(signature)
    options.append(
        {
            "title": title,
            "description": description,
            "selected_flowers": selected_flowers,
            "estimated_price": float(total),
        }
    )


def _build_description(flowers: list[Flower], style: str | None) -> str:
    colors = ", ".join(
        sorted({_translate_color(str(flower.color)) for flower in flowers if flower.color})
    )
    style_text = f" под стиль «{style}»" if style else ""
    if colors:
        return f"Подойдет{style_text}; палитра: {colors}."
    return f"Подойдет{style_text}."


def _translate_color(color: str) -> str:
    colors = {
        "red": "красный",
        "white": "белый",
        "pink": "розовый",
        "blue": "синий",
        "lavender": "лавандовый",
        "yellow": "желтый",
    }
    return colors.get(color.lower(), color)


def _odd_quantity(quantity: int) -> int:
    if quantity <= 0:
        return 0
    return quantity if quantity % 2 == 1 else quantity - 1


def _to_decimal_or_none(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None
