from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Flower, Shop, ShopSettings, Subscription
from app.db.session import SessionLocal


SHOP_SEEDS = [
    {
        "name": "Цветы у дома",
        "slug": "cvety-u-doma",
        "city": "Москва",
        "settings": {
            "greeting_text": "Здравствуйте! Поможем собрать свежий букет под ваш повод.",
            "tone": "friendly",
            "min_order_price": Decimal("1500"),
            "delivery_price": Decimal("400"),
            "working_hours": "Пн-Вс 09:00-21:00",
            "ai_enabled": True,
            "image_generation_enabled": False,
        },
        "flowers": [
            {
                "name": "Роза",
                "category": "rose",
                "color": "red",
                "price_per_stem": Decimal("180"),
                "quantity_available": 120,
            },
            {
                "name": "Тюльпан",
                "category": "tulip",
                "color": "pink",
                "price_per_stem": Decimal("110"),
                "quantity_available": 80,
            },
            {
                "name": "Хризантема",
                "category": "chrysanthemum",
                "color": "white",
                "price_per_stem": Decimal("140"),
                "quantity_available": 60,
            },
        ],
        "subscription": {
            "tariff": "basic",
            "monthly_price": Decimal("2990"),
            "dialog_limit": 1000,
            "image_limit": 100,
            "status": "active",
        },
    },
    {
        "name": "Rose House",
        "slug": "rose-house",
        "city": "Санкт-Петербург",
        "settings": {
            "greeting_text": "Добро пожаловать в Rose House. Подберем букет с доставкой по городу.",
            "tone": "elegant",
            "min_order_price": Decimal("2000"),
            "delivery_price": Decimal("500"),
            "working_hours": "Пн-Вс 10:00-22:00",
            "ai_enabled": True,
            "image_generation_enabled": True,
        },
        "flowers": [
            {
                "name": "Пионовидная роза",
                "category": "rose",
                "color": "pink",
                "price_per_stem": Decimal("260"),
                "quantity_available": 90,
            },
            {
                "name": "Эустома",
                "category": "eustoma",
                "color": "lavender",
                "price_per_stem": Decimal("210"),
                "quantity_available": 70,
            },
            {
                "name": "Гортензия",
                "category": "hydrangea",
                "color": "blue",
                "price_per_stem": Decimal("450"),
                "quantity_available": 35,
            },
        ],
        "subscription": {
            "tariff": "pro",
            "monthly_price": Decimal("5990"),
            "dialog_limit": 3000,
            "image_limit": 500,
            "status": "active",
        },
    },
]


def ensure_shop(session: Session, seed: dict) -> bool:
    shop = session.scalar(select(Shop).where(Shop.slug == seed["slug"]))
    if shop is None:
        shop = Shop(name=seed["name"], slug=seed["slug"], city=seed["city"])
        session.add(shop)
        session.flush()
        created = True
    else:
        created = False

    settings = session.scalar(
        select(ShopSettings).where(ShopSettings.shop_id == shop.id)
    )
    if settings is None:
        session.add(ShopSettings(shop_id=shop.id, **seed["settings"]))
        created = True

    has_flowers = session.scalar(select(Flower.id).where(Flower.shop_id == shop.id))
    if has_flowers is None:
        session.add_all(
            Flower(shop_id=shop.id, **flower_seed)
            for flower_seed in seed["flowers"]
        )
        created = True

    subscription = session.scalar(
        select(Subscription).where(Subscription.shop_id == shop.id)
    )
    if subscription is None:
        session.add(Subscription(shop_id=shop.id, **seed["subscription"]))
        created = True

    return created


def seed_db() -> None:
    with SessionLocal() as session:
        inserted = False
        for shop_seed in SHOP_SEEDS:
            inserted = ensure_shop(session, shop_seed) or inserted

        session.commit()

    if inserted:
        print("Seed data inserted successfully.")
    else:
        print("Seed data already exists.")


if __name__ == "__main__":
    seed_db()
