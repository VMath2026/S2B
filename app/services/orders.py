import json
from decimal import Decimal

from sqlalchemy import select

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


def get_order_by_id(order_id: int) -> Order | None:
    with SessionLocal() as session:
        return session.get(Order, order_id)


def list_recent_orders_for_shop(shop_id: int, limit: int = 10) -> list[Order]:
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(Order)
                .where(Order.shop_id == shop_id)
                .order_by(Order.id.desc())
                .limit(limit)
            ).all()
        )


def list_recent_orders(limit: int = 10) -> list[Order]:
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(Order)
                .order_by(Order.id.desc())
                .limit(limit)
            ).all()
        )


def update_order_payment_status(
    order_id: int,
    payment_status: str,
    *,
    telegram_payment_charge_id: str | None = None,
    provider_payment_charge_id: str | None = None,
) -> Order | None:
    with SessionLocal() as session:
        order = session.get(Order, order_id)
        if order is None:
            return None

        order.payment_status = payment_status
        if telegram_payment_charge_id:
            order.telegram_payment_charge_id = telegram_payment_charge_id
        if provider_payment_charge_id:
            order.provider_payment_charge_id = provider_payment_charge_id

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
