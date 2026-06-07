from decimal import Decimal
from contextlib import asynccontextmanager
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from app.bot.handlers import router
from app.config import settings
from app.db.models import Base, Flower, Order, Shop, ShopSettings
from app.db.seed import seed_db
from app.db.session import SessionLocal, engine
from app.services.flowers import get_active_flowers_for_shop
from app.services.shops import get_active_shops_by_city, get_shop_by_id


telegram_bot: Bot | None = None
telegram_dispatcher = Dispatcher()
telegram_dispatcher.include_router(router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_bot

    if settings.init_database_on_start:
        Base.metadata.create_all(bind=engine)
        if settings.seed_database_on_start:
            seed_db()

    if settings.bot_token:
        telegram_bot = Bot(
            token=settings.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )

        public_url = _get_public_url()
        if public_url:
            webhook_url = f"{public_url}/telegram/webhook"
            await telegram_bot.set_webhook(
                webhook_url,
                secret_token=settings.telegram_webhook_secret or None,
                drop_pending_updates=True,
            )

    yield

    if telegram_bot is not None:
        await telegram_bot.session.close()


app = FastAPI(title="Flower AI Platform API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class FlowerCreate(BaseModel):
    name: str
    category: str | None = None
    color: str | None = None
    price_per_stem: Decimal = Field(gt=0)
    quantity_available: int = Field(ge=0, default=0)
    quantity_reserved: int = Field(ge=0, default=0)
    photo_url: str | None = None
    is_active: bool = True


class FlowerUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    color: str | None = None
    price_per_stem: Decimal | None = Field(default=None, gt=0)
    quantity_available: int | None = Field(default=None, ge=0)
    quantity_reserved: int | None = Field(default=None, ge=0)
    photo_url: str | None = None
    is_active: bool | None = None


class ShopSettingsUpdate(BaseModel):
    greeting_text: str | None = None
    tone: str | None = None
    min_order_price: Decimal | None = Field(default=None, ge=0)
    delivery_price: Decimal | None = Field(default=None, ge=0)
    working_hours: str | None = None
    manager_chat_id: int | None = None
    ai_enabled: bool | None = None
    image_generation_enabled: bool | None = None


class OrderStatusUpdate(BaseModel):
    status: str


@app.get("/health")
def health() -> dict[str, Any]:
    with engine.connect() as connection:
        connection.execute(text("select 1"))

    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "Flower AI Platform",
        "health": "/health",
        "docs": "/docs",
        "telegram_webhook": "/telegram/webhook",
    }


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
    if telegram_bot is None:
        raise HTTPException(status_code=503, detail="BOT_TOKEN is not configured")

    if (
        settings.telegram_webhook_secret
        and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret
    ):
        raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret")

    update = Update.model_validate(
        await request.json(),
        context={"bot": telegram_bot},
    )
    await telegram_dispatcher.feed_update(telegram_bot, update)
    return {"status": "ok"}


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY is not configured")

    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")


def _get_public_url() -> str:
    public_url = settings.app_base_url or settings.render_external_url
    return public_url.rstrip("/")


@app.get("/shops")
def list_shops(city: str | None = Query(default=None)) -> list[dict[str, Any]]:
    if city:
        shops = get_active_shops_by_city(city)
    else:
        with SessionLocal() as session:
            shops = list(
                session.scalars(
                    select(Shop)
                    .where(Shop.status == "active")
                    .order_by(Shop.city, Shop.name)
                ).all()
            )

    return [_shop_to_dict(shop) for shop in shops]


@app.get("/shops/{shop_id}")
def get_shop(shop_id: int) -> dict[str, Any]:
    shop = get_shop_by_id(shop_id)
    if shop is None:
        raise HTTPException(status_code=404, detail="Shop not found")

    return _shop_to_dict(shop)


@app.get("/shops/{shop_id}/flowers")
def list_shop_flowers(shop_id: int) -> list[dict[str, Any]]:
    shop = get_shop_by_id(shop_id)
    if shop is None:
        raise HTTPException(status_code=404, detail="Shop not found")

    flowers = get_active_flowers_for_shop(shop_id)
    return [_flower_to_dict(flower) for flower in flowers]


@app.get("/orders/{order_id}")
def get_order(order_id: int) -> dict[str, Any]:
    with SessionLocal() as session:
        order = session.get(Order, order_id)

    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    return _order_to_dict(order)


@app.get("/admin/shops/{shop_id}/flowers", dependencies=[Depends(require_admin)])
def admin_list_flowers(shop_id: int) -> list[dict[str, Any]]:
    _require_shop(shop_id)
    with SessionLocal() as session:
        flowers = list(
            session.scalars(
                select(Flower).where(Flower.shop_id == shop_id).order_by(Flower.name)
            ).all()
        )

    return [_flower_to_dict(flower) for flower in flowers]


@app.post("/admin/shops/{shop_id}/flowers", dependencies=[Depends(require_admin)])
def admin_create_flower(shop_id: int, payload: FlowerCreate) -> dict[str, Any]:
    _require_shop(shop_id)
    with SessionLocal() as session:
        flower = Flower(shop_id=shop_id, **payload.model_dump())
        session.add(flower)
        session.commit()
        session.refresh(flower)
        return _flower_to_dict(flower)


@app.patch("/admin/flowers/{flower_id}", dependencies=[Depends(require_admin)])
def admin_update_flower(flower_id: int, payload: FlowerUpdate) -> dict[str, Any]:
    with SessionLocal() as session:
        flower = session.get(Flower, flower_id)
        if flower is None:
            raise HTTPException(status_code=404, detail="Flower not found")

        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(flower, key, value)

        if flower.quantity_reserved > flower.quantity_available:
            raise HTTPException(
                status_code=400,
                detail="quantity_reserved cannot exceed quantity_available",
            )

        session.commit()
        session.refresh(flower)
        return _flower_to_dict(flower)


@app.delete("/admin/flowers/{flower_id}", dependencies=[Depends(require_admin)])
def admin_deactivate_flower(flower_id: int) -> dict[str, Any]:
    with SessionLocal() as session:
        flower = session.get(Flower, flower_id)
        if flower is None:
            raise HTTPException(status_code=404, detail="Flower not found")

        flower.is_active = False
        session.commit()
        session.refresh(flower)
        return _flower_to_dict(flower)


@app.get("/admin/shops/{shop_id}/settings", dependencies=[Depends(require_admin)])
def admin_get_shop_settings(shop_id: int) -> dict[str, Any]:
    _require_shop(shop_id)
    with SessionLocal() as session:
        shop_settings = _get_or_create_settings(session, shop_id)
        session.commit()
        session.refresh(shop_settings)
        return _shop_settings_to_dict(shop_settings)


@app.patch("/admin/shops/{shop_id}/settings", dependencies=[Depends(require_admin)])
def admin_update_shop_settings(
    shop_id: int,
    payload: ShopSettingsUpdate,
) -> dict[str, Any]:
    _require_shop(shop_id)
    with SessionLocal() as session:
        shop_settings = _get_or_create_settings(session, shop_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(shop_settings, key, value)

        session.commit()
        session.refresh(shop_settings)
        return _shop_settings_to_dict(shop_settings)


@app.get("/admin/shops/{shop_id}/orders", dependencies=[Depends(require_admin)])
def admin_list_shop_orders(
    shop_id: int,
    status: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    _require_shop(shop_id)
    with SessionLocal() as session:
        query = select(Order).where(Order.shop_id == shop_id).order_by(Order.id.desc())
        if status:
            query = query.where(Order.status == status)
        orders = list(session.scalars(query).all())

    return [_order_to_dict(order) for order in orders]


@app.patch("/admin/orders/{order_id}/status", dependencies=[Depends(require_admin)])
def admin_update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
) -> dict[str, Any]:
    allowed_statuses = {"new", "accepted", "in_progress", "done", "cancelled"}
    if payload.status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of: {', '.join(sorted(allowed_statuses))}",
        )

    with SessionLocal() as session:
        order = session.get(Order, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")

        order.status = payload.status
        session.commit()
        session.refresh(order)
        return _order_to_dict(order)


def _shop_to_dict(shop: Shop) -> dict[str, Any]:
    return {
        "id": shop.id,
        "name": shop.name,
        "slug": shop.slug,
        "city": shop.city,
        "timezone": shop.timezone,
        "status": shop.status,
    }


def _require_shop(shop_id: int) -> Shop:
    shop = get_shop_by_id(shop_id)
    if shop is None:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


def _flower_to_dict(flower: Flower) -> dict[str, Any]:
    return {
        "id": flower.id,
        "shop_id": flower.shop_id,
        "name": flower.name,
        "category": flower.category,
        "color": flower.color,
        "price_per_stem": _decimal_to_float(flower.price_per_stem),
        "quantity_available": flower.quantity_available,
        "quantity_reserved": flower.quantity_reserved,
        "quantity_free": flower.quantity_available - flower.quantity_reserved,
        "photo_url": flower.photo_url,
        "is_active": flower.is_active,
    }


def _order_to_dict(order: Order) -> dict[str, Any]:
    return {
        "id": order.id,
        "shop_id": order.shop_id,
        "customer_id": order.customer_id,
        "status": order.status,
        "occasion": order.occasion,
        "recipient": order.recipient,
        "budget": _decimal_to_float(order.budget),
        "style": order.style,
        "colors": order.colors,
        "avoid_flowers": order.avoid_flowers,
        "delivery_date": order.delivery_date,
        "delivery_address": order.delivery_address,
        "phone": order.phone,
        "comment": order.comment,
        "generated_image_url": order.generated_image_url,
        "total_price": _decimal_to_float(order.total_price),
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }


def _shop_settings_to_dict(shop_settings: ShopSettings) -> dict[str, Any]:
    return {
        "id": shop_settings.id,
        "shop_id": shop_settings.shop_id,
        "greeting_text": shop_settings.greeting_text,
        "tone": shop_settings.tone,
        "min_order_price": _decimal_to_float(shop_settings.min_order_price),
        "delivery_price": _decimal_to_float(shop_settings.delivery_price),
        "working_hours": shop_settings.working_hours,
        "manager_chat_id": shop_settings.manager_chat_id,
        "ai_enabled": shop_settings.ai_enabled,
        "image_generation_enabled": shop_settings.image_generation_enabled,
    }


def _get_or_create_settings(session, shop_id: int) -> ShopSettings:
    shop_settings = session.scalar(
        select(ShopSettings).where(ShopSettings.shop_id == shop_id)
    )
    if shop_settings is None:
        shop_settings = ShopSettings(shop_id=shop_id)
        session.add(shop_settings)
        session.flush()
    return shop_settings


def _decimal_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)
