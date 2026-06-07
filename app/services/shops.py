from sqlalchemy import select

from app.db.models import Shop, ShopSettings, UserShopSession
from app.db.session import SessionLocal


def get_shop_by_slug(slug: str) -> Shop | None:
    normalized_slug = slug.strip()
    if not normalized_slug:
        return None

    with SessionLocal() as session:
        return session.scalar(
            select(Shop).where(
                Shop.slug == normalized_slug,
                Shop.status == "active",
            )
        )


def get_shop_settings(shop_id: int) -> ShopSettings | None:
    with SessionLocal() as session:
        return session.scalar(
            select(ShopSettings).where(ShopSettings.shop_id == shop_id)
        )


def get_shop_by_id(shop_id: int) -> Shop | None:
    with SessionLocal() as session:
        return session.scalar(
            select(Shop).where(
                Shop.id == shop_id,
                Shop.status == "active",
            )
        )


def get_shop_by_manager_chat_id(manager_chat_id: int) -> Shop | None:
    with SessionLocal() as session:
        return session.scalar(
            select(Shop)
            .join(ShopSettings, ShopSettings.shop_id == Shop.id)
            .where(
                ShopSettings.manager_chat_id == manager_chat_id,
                Shop.status == "active",
            )
        )


def get_active_shops_by_city(city: str) -> list[Shop]:
    normalized_city = city.strip()
    if not normalized_city:
        return []

    with SessionLocal() as session:
        return list(
            session.scalars(
                select(Shop)
                .where(
                    Shop.city.ilike(normalized_city),
                    Shop.status == "active",
                )
                .order_by(Shop.name)
            ).all()
        )


def set_current_shop_for_user(telegram_user_id: int, shop_id: int) -> None:
    with SessionLocal() as session:
        user_session = session.scalar(
            select(UserShopSession).where(
                UserShopSession.telegram_user_id == telegram_user_id
            )
        )

        if user_session is None:
            user_session = UserShopSession(
                telegram_user_id=telegram_user_id,
                current_shop_id=shop_id,
            )
            session.add(user_session)
        else:
            user_session.current_shop_id = shop_id

        session.commit()


def clear_current_shop_for_user(telegram_user_id: int) -> None:
    with SessionLocal() as session:
        user_session = session.scalar(
            select(UserShopSession).where(
                UserShopSession.telegram_user_id == telegram_user_id
            )
        )
        if user_session is None:
            return

        user_session.current_shop_id = None
        session.commit()


def set_manager_chat_for_shop(slug: str, manager_chat_id: int) -> Shop | None:
    normalized_slug = slug.strip()
    if not normalized_slug:
        return None

    with SessionLocal() as session:
        shop = session.scalar(
            select(Shop).where(
                Shop.slug == normalized_slug,
                Shop.status == "active",
            )
        )
        if shop is None:
            return None

        settings = session.scalar(
            select(ShopSettings).where(ShopSettings.shop_id == shop.id)
        )
        if settings is None:
            settings = ShopSettings(shop_id=shop.id)
            session.add(settings)

        settings.manager_chat_id = manager_chat_id
        session.commit()
        session.refresh(shop)
        return shop


def get_current_shop_for_user(telegram_user_id: int) -> Shop | None:
    with SessionLocal() as session:
        return session.scalar(
            select(Shop)
            .join(
                UserShopSession,
                UserShopSession.current_shop_id == Shop.id,
            )
            .where(
                UserShopSession.telegram_user_id == telegram_user_id,
                Shop.status == "active",
            )
        )
