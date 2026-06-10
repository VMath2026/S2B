from app.db.models import Base
from app.db.session import engine
from sqlalchemy import text


def init_db() -> None:
    ensure_database_schema()
    print("Database tables created successfully.")


def ensure_database_schema() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("alter table shop_settings add column if not exists free_delivery_from numeric"))
        connection.execute(
            text(
                "alter table shop_settings "
                "add column if not exists urgent_delivery_price numeric not null default 0"
            )
        )
        connection.execute(
            text(
                "alter table shop_settings "
                "add column if not exists pickup_enabled boolean not null default true"
            )
        )
        connection.execute(
            text(
                "alter table shop_settings "
                "add column if not exists payment_mode text not null default 'after_manager_confirmation'"
            )
        )
        connection.execute(
            text(
                "alter table orders "
                "add column if not exists payment_status text not null default 'not_paid'"
            )
        )
        connection.execute(text("alter table orders add column if not exists selected_variant jsonb"))
        connection.execute(
            text(
                "alter table orders "
                "add column if not exists telegram_payment_charge_id text"
            )
        )
        connection.execute(
            text(
                "alter table orders "
                "add column if not exists provider_payment_charge_id text"
            )
        )
        connection.execute(
            text(
                "create table if not exists conversation_logs ("
                "id serial primary key, "
                "shop_id integer not null references shops(id) on delete cascade, "
                "customer_id integer references customers(id) on delete set null, "
                "role text not null, "
                "message text not null, "
                "meta jsonb, "
                "created_at timestamp default now()"
                ")"
            )
        )


if __name__ == "__main__":
    init_db()
