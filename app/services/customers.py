from sqlalchemy import select

from app.db.models import Customer
from app.db.session import SessionLocal


def get_or_create_customer(
    shop_id: int,
    telegram_user_id: int,
    telegram_username: str | None,
    first_name: str | None,
) -> Customer:
    with SessionLocal() as session:
        customer = session.scalar(
            select(Customer).where(
                Customer.shop_id == shop_id,
                Customer.telegram_user_id == telegram_user_id,
            )
        )

        if customer is None:
            customer = Customer(
                shop_id=shop_id,
                telegram_user_id=telegram_user_id,
                telegram_username=telegram_username,
                first_name=first_name,
            )
            session.add(customer)
            session.commit()
            session.refresh(customer)
            return customer

        customer.telegram_username = telegram_username
        customer.first_name = first_name
        session.commit()
        session.refresh(customer)
        return customer


def get_customer_by_id(customer_id: int | None) -> Customer | None:
    if customer_id is None:
        return None

    with SessionLocal() as session:
        return session.get(Customer, customer_id)


def get_customer_by_telegram_user_id(
    telegram_user_id: int,
    *,
    shop_id: int | None = None,
) -> Customer | None:
    with SessionLocal() as session:
        query = select(Customer).where(Customer.telegram_user_id == telegram_user_id)
        if shop_id is not None:
            query = query.where(Customer.shop_id == shop_id)

        return session.scalar(query.order_by(Customer.id.desc()))
