from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(Text, default="Europe/Moscow", nullable=False)
    status: Mapped[str] = mapped_column(Text, default="active", nullable=False)
    tariff: Mapped[str] = mapped_column(Text, default="basic", nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class ShopSettings(Base):
    __tablename__ = "shop_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )
    greeting_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tone: Mapped[str] = mapped_column(Text, default="friendly", nullable=False)
    min_order_price: Mapped[float] = mapped_column(Numeric, default=0, nullable=False)
    delivery_price: Mapped[float] = mapped_column(Numeric, default=0, nullable=False)
    free_delivery_from: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    urgent_delivery_price: Mapped[float] = mapped_column(Numeric, default=0, nullable=False)
    pickup_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    payment_mode: Mapped[str] = mapped_column(Text, default="after_manager_confirmation", nullable=False)
    working_hours: Mapped[str | None] = mapped_column(Text, nullable=True)
    manager_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    image_generation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ShopAdminUser(Base):
    __tablename__ = "shop_admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False,
    )
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("shop_id", "telegram_user_id", name="uq_customer_shop_telegram"),
    )


class UserShopSession(Base):
    __tablename__ = "user_shop_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    current_shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="SET NULL"),
        nullable=True
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )


class ConversationState(Base):
    __tablename__ = "conversation_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False
    )
    state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("shop_id", "customer_id", name="uq_state_shop_customer"),
    )


class ConversationLog(Base):
    __tablename__ = "conversation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class Flower(Base):
    __tablename__ = "flowers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_per_stem: Mapped[float] = mapped_column(Numeric, nullable=False)
    quantity_available: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quantity_reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True
    )
    status: Mapped[str] = mapped_column(Text, default="draft", nullable=False)
    occasion: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipient: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    style: Mapped[str | None] = mapped_column(Text, nullable=True)
    colors: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    avoid_flowers: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    delivery_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_variant: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    generated_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_price: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    payment_status: Mapped[str] = mapped_column(Text, default="not_paid", nullable=False)
    telegram_payment_charge_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_payment_charge_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class BouquetExample(Base):
    __tablename__ = "bouquet_examples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    style: Mapped[str | None] = mapped_column(Text, nullable=True)
    colors: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    flowers: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False
    )
    tariff: Mapped[str] = mapped_column(Text, nullable=False)
    monthly_price: Mapped[float] = mapped_column(Numeric, nullable=False)
    dialog_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    image_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[Date] = mapped_column(Date, server_default=func.current_date())
    paid_until: Mapped[Date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="active", nullable=False)


class UsageCounter(Base):
    __tablename__ = "usage_counters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False
    )
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    dialogs_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    images_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("shop_id", "month", name="uq_usage_shop_month"),
    )
