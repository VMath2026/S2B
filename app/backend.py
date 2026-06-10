from contextlib import asynccontextmanager
from decimal import Decimal
import json
import logging
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text

from app.bot.commands import get_bot_commands
from app.bot.handlers import router
from app.config import settings
from app.db.models import (
    Base,
    BouquetExample,
    ConversationLog,
    Customer,
    Flower,
    Order,
    Shop,
    ShopSettings,
)
from app.db.init_db import ensure_database_schema
from app.db.seed import seed_db
from app.db.session import SessionLocal, engine
from app.services.admin_auth import (
    ShopAdminIdentity,
    authenticate_shop_admin,
    create_or_update_shop_admin_user,
    create_shop_admin_token,
    verify_shop_admin_token,
)
from app.services.conversations import list_conversation_logs_for_customer
from app.services.flowers import get_active_flowers_for_shop, reset_reserved_flowers_for_shop
from app.services.shops import get_active_shops_by_city, get_shop_by_id


telegram_bot: Bot | None = None
telegram_dispatcher = Dispatcher()
telegram_dispatcher.include_router(router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_bot

    if settings.init_database_on_start:
        ensure_database_schema()
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
            await telegram_bot.set_my_commands(get_bot_commands())

    yield

    if telegram_bot is not None:
        await telegram_bot.session.close()


logger = logging.getLogger(__name__)


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

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be empty")
        return normalized


class FlowerUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    color: str | None = None
    price_per_stem: Decimal | None = Field(default=None, gt=0)
    quantity_available: int | None = Field(default=None, ge=0)
    quantity_reserved: int | None = Field(default=None, ge=0)
    photo_url: str | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be empty")
        return normalized


class ShopSettingsUpdate(BaseModel):
    greeting_text: str | None = None
    tone: str | None = None
    min_order_price: Decimal | None = Field(default=None, ge=0)
    delivery_price: Decimal | None = Field(default=None, ge=0)
    free_delivery_from: Decimal | None = Field(default=None, ge=0)
    urgent_delivery_price: Decimal | None = Field(default=None, ge=0)
    pickup_enabled: bool | None = None
    payment_mode: str | None = None
    working_hours: str | None = None
    manager_chat_id: int | None = None
    ai_enabled: bool | None = None
    image_generation_enabled: bool | None = None


class OrderStatusUpdate(BaseModel):
    status: str


class PaymentStatusUpdate(BaseModel):
    payment_status: str


class BouquetTemplatePayload(BaseModel):
    title: str
    description: str | None = None
    style: str | None = None
    colors: list[str] = Field(default_factory=list)
    flowers: list[str] = Field(default_factory=list)
    price: Decimal | None = Field(default=None, ge=0)
    image_url: str | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title cannot be empty")
        return normalized


class ShopAdminLogin(BaseModel):
    username: str
    password: str


class ShopCredentialsUpdate(BaseModel):
    username: str
    password: str = Field(min_length=8)


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
        logger.warning("Telegram webhook secret mismatch; processing update anyway")

    update = Update.model_validate(
        await request.json(),
        context={"bot": telegram_bot},
    )
    logger.warning("Telegram update received: update_id=%s", update.update_id)
    await telegram_dispatcher.feed_update(telegram_bot, update)
    return {"status": "ok"}


@app.get("/telegram/status")
async def telegram_status() -> dict[str, Any]:
    if telegram_bot is None:
        raise HTTPException(status_code=503, detail="BOT_TOKEN is not configured")

    bot_info = await telegram_bot.get_me()
    webhook_info = await telegram_bot.get_webhook_info()

    return {
        "bot_id": bot_info.id,
        "bot_username": bot_info.username,
        "webhook_url": webhook_info.url,
        "pending_update_count": webhook_info.pending_update_count,
        "last_error_date": webhook_info.last_error_date,
        "last_error_message": webhook_info.last_error_message,
    }


@app.post("/admin/auth/login")
def admin_login(payload: ShopAdminLogin) -> dict[str, Any]:
    identity = authenticate_shop_admin(
        username=payload.username,
        password=payload.password,
    )
    if identity is None:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    shop = get_shop_by_id(identity.shop_id)
    if shop is None:
        raise HTTPException(status_code=403, detail="Магазин отключен")

    try:
        token = create_shop_admin_token(identity)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "token": token,
        "shop": _shop_to_dict(shop),
        "username": identity.username,
    }


@app.get("/admin/me")
def admin_me(
    x_admin_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    if x_admin_key is not None and not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY is not configured")

    if settings.admin_api_key and x_admin_key == settings.admin_api_key:
        return {"role": "owner", "shop": None, "username": "owner"}

    if x_admin_key is not None:
        raise HTTPException(status_code=401, detail="Invalid admin key")

    identity = verify_shop_admin_token(authorization)
    if identity is None:
        raise HTTPException(status_code=401, detail="Login required")

    shop = get_shop_by_id(identity.shop_id)
    if shop is None:
        raise HTTPException(status_code=403, detail="Магазин отключен")

    return {
        "role": "shop",
        "shop": _shop_to_dict(shop),
        "username": identity.username,
    }


@app.post("/admin/shops/{shop_id}/credentials")
def admin_set_shop_credentials(
    shop_id: int,
    payload: ShopCredentialsUpdate,
    x_admin_key: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_admin_key)
    shop = _require_shop(shop_id)
    try:
        user = create_or_update_shop_admin_user(
            shop_id=shop.id,
            username=payload.username,
            password=payload.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "shop_id": shop.id,
        "shop_name": shop.name,
        "username": user.username,
    }


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY is not configured")

    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")


def require_shop_access(
    shop_id: int,
    x_admin_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    _ensure_can_access_shop(shop_id, x_admin_key, authorization)


def require_flower_access(
    flower_id: int,
    x_admin_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    with SessionLocal() as session:
        flower = session.get(Flower, flower_id)
        if flower is None:
            raise HTTPException(status_code=404, detail="Flower not found")
        shop_id = flower.shop_id

    _ensure_can_access_shop(shop_id, x_admin_key, authorization)


def require_order_access(
    order_id: int,
    x_admin_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    with SessionLocal() as session:
        order = session.get(Order, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")
        shop_id = order.shop_id

    _ensure_can_access_shop(shop_id, x_admin_key, authorization)


def _ensure_can_access_shop(
    shop_id: int,
    x_admin_key: str | None,
    authorization: str | None,
) -> ShopAdminIdentity | None:
    if x_admin_key is not None and not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY is not configured")

    if settings.admin_api_key and x_admin_key == settings.admin_api_key:
        return None

    if x_admin_key is not None:
        raise HTTPException(status_code=401, detail="Invalid admin key")

    identity = verify_shop_admin_token(authorization)
    if identity is None:
        raise HTTPException(status_code=401, detail="Login required")

    if identity.shop_id != shop_id:
        raise HTTPException(status_code=403, detail="Access denied for this shop")

    return identity


def _get_public_url() -> str:
    public_url = settings.app_base_url or settings.render_external_url
    return public_url.rstrip("/")


def _run_startup_schema_updates() -> None:
    ensure_database_schema()


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


@app.get("/admin/shops/{shop_id}/flowers", dependencies=[Depends(require_shop_access)])
def admin_list_flowers(shop_id: int) -> list[dict[str, Any]]:
    _require_shop(shop_id)
    with SessionLocal() as session:
        flowers = list(
            session.scalars(
                select(Flower).where(Flower.shop_id == shop_id).order_by(Flower.name)
            ).all()
        )

    return [_flower_to_dict(flower) for flower in flowers]


@app.post("/admin/shops/{shop_id}/flowers", dependencies=[Depends(require_shop_access)])
def admin_create_flower(shop_id: int, payload: FlowerCreate) -> dict[str, Any]:
    _require_shop(shop_id)
    flower_data = _normalize_flower_payload(payload.model_dump())
    with SessionLocal() as session:
        _validate_flower_business_rules(session, shop_id, flower_data)
        flower = Flower(shop_id=shop_id, **flower_data)
        session.add(flower)
        session.commit()
        session.refresh(flower)
        return _flower_to_dict(flower)


@app.post("/admin/shops/{shop_id}/flowers/reset-reserved", dependencies=[Depends(require_shop_access)])
def admin_reset_reserved_flowers(shop_id: int) -> dict[str, Any]:
    _require_shop(shop_id)
    updated = reset_reserved_flowers_for_shop(shop_id)
    return {"status": "ok", "updated": updated}


@app.patch("/admin/flowers/{flower_id}", dependencies=[Depends(require_flower_access)])
def admin_update_flower(flower_id: int, payload: FlowerUpdate) -> dict[str, Any]:
    with SessionLocal() as session:
        flower = session.get(Flower, flower_id)
        if flower is None:
            raise HTTPException(status_code=404, detail="Flower not found")

        for key, value in _normalize_flower_payload(
            payload.model_dump(exclude_unset=True)
        ).items():
            setattr(flower, key, value)

        _validate_flower_business_rules(
            session,
            flower.shop_id,
            {
                "name": flower.name,
                "color": flower.color,
                "price_per_stem": flower.price_per_stem,
                "quantity_available": flower.quantity_available,
                "quantity_reserved": flower.quantity_reserved,
            },
            flower_id=flower.id,
        )

        session.commit()
        session.refresh(flower)
        return _flower_to_dict(flower)


@app.delete("/admin/flowers/{flower_id}", dependencies=[Depends(require_flower_access)])
def admin_deactivate_flower(flower_id: int) -> dict[str, Any]:
    with SessionLocal() as session:
        flower = session.get(Flower, flower_id)
        if flower is None:
            raise HTTPException(status_code=404, detail="Flower not found")

        flower.is_active = False
        session.commit()
        session.refresh(flower)
        return _flower_to_dict(flower)


@app.get("/admin/shops/{shop_id}/settings", dependencies=[Depends(require_shop_access)])
def admin_get_shop_settings(shop_id: int) -> dict[str, Any]:
    _require_shop(shop_id)
    with SessionLocal() as session:
        shop_settings = _get_or_create_settings(session, shop_id)
        session.commit()
        session.refresh(shop_settings)
        return _shop_settings_to_dict(shop_settings)


@app.patch("/admin/shops/{shop_id}/settings", dependencies=[Depends(require_shop_access)])
def admin_update_shop_settings(
    shop_id: int,
    payload: ShopSettingsUpdate,
) -> dict[str, Any]:
    _require_shop(shop_id)
    with SessionLocal() as session:
        shop_settings = _get_or_create_settings(session, shop_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            if key == "payment_mode" and value not in {
                "prepay_50",
                "full_prepay",
                "after_manager_confirmation",
            }:
                raise HTTPException(status_code=400, detail="Unsupported payment_mode")
            setattr(shop_settings, key, value)

        session.commit()
        session.refresh(shop_settings)
        return _shop_settings_to_dict(shop_settings)


@app.get("/admin/shops/{shop_id}/orders", dependencies=[Depends(require_shop_access)])
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
        customer_ids = {order.customer_id for order in orders if order.customer_id is not None}
        customers = {
            customer.id: customer
            for customer in session.scalars(select(Customer).where(Customer.id.in_(customer_ids))).all()
        } if customer_ids else {}

    return [_order_to_dict(order, customers.get(order.customer_id)) for order in orders]


@app.patch("/admin/orders/{order_id}/status", dependencies=[Depends(require_order_access)])
def admin_update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
) -> dict[str, Any]:
    allowed_statuses = {"new", "accepted", "in_progress", "done", "cancelled", "paid"}
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


@app.patch("/admin/orders/{order_id}/payment", dependencies=[Depends(require_order_access)])
def admin_update_order_payment(
    order_id: int,
    payload: PaymentStatusUpdate,
) -> dict[str, Any]:
    allowed_statuses = {"not_paid", "invoice_sent", "prepaid", "paid", "failed", "refunded"}
    if payload.payment_status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"payment_status must be one of: {', '.join(sorted(allowed_statuses))}",
        )

    with SessionLocal() as session:
        order = session.get(Order, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")

        order.payment_status = payload.payment_status
        if payload.payment_status == "paid":
            order.status = "paid"
        session.commit()
        session.refresh(order)
        return _order_to_dict(order)


@app.get("/admin/shops/{shop_id}/customers/{customer_id}/orders", dependencies=[Depends(require_shop_access)])
def admin_list_customer_orders(shop_id: int, customer_id: int) -> list[dict[str, Any]]:
    _require_shop(shop_id)
    with SessionLocal() as session:
        customer = session.get(Customer, customer_id)
        if customer is None or customer.shop_id != shop_id:
            raise HTTPException(status_code=404, detail="Customer not found")

        orders = list(
            session.scalars(
                select(Order)
                .where(Order.shop_id == shop_id, Order.customer_id == customer_id)
                .order_by(Order.id.desc())
                .limit(20)
            ).all()
        )
        return [_order_to_dict(order, customer) for order in orders]


@app.get("/admin/shops/{shop_id}/customers/{customer_id}/conversation", dependencies=[Depends(require_shop_access)])
def admin_list_customer_conversation(shop_id: int, customer_id: int) -> list[dict[str, Any]]:
    _require_shop(shop_id)
    logs = list_conversation_logs_for_customer(shop_id, customer_id)
    return [_conversation_log_to_dict(log) for log in reversed(logs)]


@app.get("/admin/shops/{shop_id}/bouquet-templates", dependencies=[Depends(require_shop_access)])
def admin_list_bouquet_templates(shop_id: int) -> list[dict[str, Any]]:
    _require_shop(shop_id)
    with SessionLocal() as session:
        templates = list(
            session.scalars(
                select(BouquetExample)
                .where(BouquetExample.shop_id == shop_id)
                .order_by(BouquetExample.id.desc())
            ).all()
        )
    return [_bouquet_template_to_dict(template) for template in templates]


@app.post("/admin/shops/{shop_id}/bouquet-templates", dependencies=[Depends(require_shop_access)])
def admin_create_bouquet_template(shop_id: int, payload: BouquetTemplatePayload) -> dict[str, Any]:
    _require_shop(shop_id)
    data = _normalize_bouquet_template_payload(payload.model_dump())
    with SessionLocal() as session:
        template = BouquetExample(shop_id=shop_id, **data)
        session.add(template)
        session.commit()
        session.refresh(template)
        return _bouquet_template_to_dict(template)


@app.patch("/admin/bouquet-templates/{template_id}")
def admin_update_bouquet_template(
    template_id: int,
    payload: BouquetTemplatePayload,
    x_admin_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    with SessionLocal() as session:
        template = session.get(BouquetExample, template_id)
        if template is None:
            raise HTTPException(status_code=404, detail="Bouquet template not found")
        shop_id = template.shop_id

    _ensure_can_access_shop(shop_id, x_admin_key, authorization)

    with SessionLocal() as session:
        template = session.get(BouquetExample, template_id)
        for key, value in _normalize_bouquet_template_payload(payload.model_dump()).items():
            setattr(template, key, value)
        session.commit()
        session.refresh(template)
        return _bouquet_template_to_dict(template)


@app.delete("/admin/bouquet-templates/{template_id}")
def admin_delete_bouquet_template(
    template_id: int,
    x_admin_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    with SessionLocal() as session:
        template = session.get(BouquetExample, template_id)
        if template is None:
            raise HTTPException(status_code=404, detail="Bouquet template not found")
        shop_id = template.shop_id

    _ensure_can_access_shop(shop_id, x_admin_key, authorization)

    with SessionLocal() as session:
        template = session.get(BouquetExample, template_id)
        if template is not None:
            session.delete(template)
            session.commit()
    return {"status": "ok"}


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


def _normalize_flower_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    for key in ("name", "category", "color", "photo_url"):
        if key not in normalized or normalized[key] is None:
            continue

        value = str(normalized[key]).strip()
        normalized[key] = value or None

    if "name" in normalized and normalized["name"] is None:
        normalized["name"] = ""

    return normalized


def _validate_flower_business_rules(
    session,
    shop_id: int,
    payload: dict[str, Any],
    *,
    flower_id: int | None = None,
) -> None:
    name = str(payload.get("name") or "").strip()
    color = str(payload.get("color") or "").strip().lower()
    price = payload.get("price_per_stem")
    quantity_available = int(payload.get("quantity_available") or 0)
    quantity_reserved = int(payload.get("quantity_reserved") or 0)

    if not name:
        raise HTTPException(status_code=400, detail="Название товара не может быть пустым")

    if Decimal(str(price or 0)) <= 0:
        raise HTTPException(status_code=400, detail="Цена должна быть больше 0")

    if quantity_reserved > quantity_available:
        raise HTTPException(status_code=400, detail="Резерв не может быть больше наличия")

    duplicate_query = select(Flower).where(
        Flower.shop_id == shop_id,
        func.lower(func.trim(Flower.name)) == name.lower(),
        func.coalesce(func.lower(func.trim(Flower.color)), "") == color,
    )
    if flower_id is not None:
        duplicate_query = duplicate_query.where(Flower.id != flower_id)

    if session.scalar(duplicate_query) is not None:
        raise HTTPException(
            status_code=400,
            detail="Такой товар с таким цветом уже есть. Укажите другой цвет или измените существующую позицию.",
        )


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


def _order_to_dict(order: Order, customer: Customer | None = None) -> dict[str, Any]:
    comment_payload = _parse_order_comment(order.comment)
    selected_flowers = (
        (order.selected_variant or {}).get("flowers")
        if order.selected_variant
        else comment_payload.get("selected_flowers", [])
    )
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
        "comment_payload": comment_payload,
        "customer_comment": comment_payload.get("comment") or None,
        "composition": selected_flowers,
        "selected_flowers": selected_flowers,
        "ai_summary": comment_payload.get("ai_summary") or None,
        "selected_variant": order.selected_variant,
        "generated_image_url": order.generated_image_url,
        "total_price": _decimal_to_float(order.total_price),
        "payment_status": order.payment_status,
        "telegram_payment_charge_id": order.telegram_payment_charge_id,
        "provider_payment_charge_id": order.provider_payment_charge_id,
        "customer": _customer_to_dict(customer),
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
        "free_delivery_from": _decimal_to_float(shop_settings.free_delivery_from),
        "urgent_delivery_price": _decimal_to_float(shop_settings.urgent_delivery_price),
        "pickup_enabled": shop_settings.pickup_enabled,
        "payment_mode": shop_settings.payment_mode,
        "working_hours": shop_settings.working_hours,
        "manager_chat_id": shop_settings.manager_chat_id,
        "ai_enabled": shop_settings.ai_enabled,
        "image_generation_enabled": shop_settings.image_generation_enabled,
    }


def _customer_to_dict(customer: Customer | None) -> dict[str, Any] | None:
    if customer is None:
        return None

    username = customer.telegram_username
    contact_url = f"https://t.me/{username.lstrip('@')}" if username else f"tg://user?id={customer.telegram_user_id}"
    return {
        "id": customer.id,
        "telegram_user_id": customer.telegram_user_id,
        "telegram_username": username,
        "first_name": customer.first_name,
        "contact_url": contact_url,
        "created_at": customer.created_at.isoformat() if customer.created_at else None,
    }


def _conversation_log_to_dict(log: ConversationLog) -> dict[str, Any]:
    return {
        "id": log.id,
        "shop_id": log.shop_id,
        "customer_id": log.customer_id,
        "role": log.role,
        "message": log.message,
        "meta": log.meta,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _bouquet_template_to_dict(template: BouquetExample) -> dict[str, Any]:
    return {
        "id": template.id,
        "shop_id": template.shop_id,
        "title": template.title,
        "description": template.description,
        "style": template.style,
        "colors": template.colors or [],
        "flowers": template.flowers or [],
        "price": _decimal_to_float(template.price),
        "image_url": template.image_url,
        "created_at": template.created_at.isoformat() if template.created_at else None,
    }


def _normalize_bouquet_template_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    for key in ("title", "description", "style", "image_url"):
        if key in normalized and normalized[key] is not None:
            value = str(normalized[key]).strip()
            normalized[key] = value or None
    normalized["title"] = normalized["title"] or ""
    normalized["colors"] = [str(item).strip() for item in normalized.get("colors") or [] if str(item).strip()]
    normalized["flowers"] = [str(item).strip() for item in normalized.get("flowers") or [] if str(item).strip()]
    return normalized


def _parse_order_comment(comment: str | None) -> dict[str, Any]:
    if not comment:
        return {}
    try:
        parsed = json.loads(comment)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {"comment": comment}


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
