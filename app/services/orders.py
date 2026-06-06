import json
from decimal import Decimal

from app.db.models import Order
from app.db.session import SessionLocal


def create_confirmed_order(
    *,
    shop_id: int,
    customer_id: int,
    state: dict,
) -> Order:
    with SessionLocal() as session:
        order = Order(
            shop_id=shop_id,
            customer_id=customer_id,
            status="new",
            occasion=state.get("occasion"),
            recipient=state.get("recipient"),
            budget=_to_decimal_or_none(state.get("budget")),
            style=state.get("style"),
            colors=state.get("colors") or None,
            avoid_flowers=state.get("avoid_flowers") or None,
            delivery_date=state.get("delivery_date"),
            delivery_address=state.get("delivery_address"),
            phone=state.get("phone"),
            comment=_build_order_comment(state),
            total_price=_to_decimal_or_none(state.get("estimated_price")),
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return order


def update_order_status(order_id: int, status: str) -> Order | None:
    with SessionLocal() as session:
        order = session.get(Order, order_id)
        if order is None:
            return None

        order.status = status
        session.commit()
        session.refresh(order)
        return order


def _build_order_comment(state: dict) -> str | None:
    payload = {
        "comment": state.get("comment"),
        "selected_flowers": state.get("selected_flowers") or [],
        "ai_summary": state.get("summary"),
    }
    return json.dumps(payload, ensure_ascii=False)


def _to_decimal_or_none(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))
