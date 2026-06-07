from sqlalchemy import select

from app.db.models import Flower
from app.db.session import SessionLocal


def get_active_flowers_for_shop(shop_id: int) -> list[Flower]:
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(Flower)
                .where(
                    Flower.shop_id == shop_id,
                    Flower.is_active.is_(True),
                    Flower.quantity_available > Flower.quantity_reserved,
                )
                .order_by(Flower.name)
            ).all()
        )


def reserve_selected_flowers(shop_id: int, selected_flowers: list[dict]) -> list[str]:
    if not selected_flowers:
        return []

    unavailable: list[str] = []

    with SessionLocal() as session:
        flowers = list(
            session.scalars(
                select(Flower).where(
                    Flower.shop_id == shop_id,
                    Flower.is_active.is_(True),
                )
            ).all()
        )
        flowers_by_name = {flower.name.lower(): flower for flower in flowers}

        for selected in selected_flowers:
            name = str(selected.get("name") or "").strip()
            quantity = int(selected.get("quantity") or 0)
            if not name or quantity <= 0:
                continue

            flower = flowers_by_name.get(name.lower())
            if flower is None:
                unavailable.append(name)
                continue

            free_quantity = flower.quantity_available - flower.quantity_reserved
            if free_quantity < quantity:
                unavailable.append(f"{flower.name} доступно {free_quantity} шт.")
                continue

            flower.quantity_reserved += quantity

        if unavailable:
            session.rollback()
            return unavailable

        session.commit()
        return []


def reset_reserved_flowers_for_shop(shop_id: int) -> int:
    with SessionLocal() as session:
        flowers = list(
            session.scalars(
                select(Flower).where(Flower.shop_id == shop_id)
            ).all()
        )

        updated = 0
        for flower in flowers:
            if flower.quantity_reserved > 0:
                flower.quantity_reserved = 0
                updated += 1

        session.commit()
        return updated
