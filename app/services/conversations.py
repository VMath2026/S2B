from copy import deepcopy
import logging

from sqlalchemy import select

from app.db.models import ConversationLog, ConversationState
from app.db.session import SessionLocal


logger = logging.getLogger(__name__)


DEFAULT_ORDER_STATE = {
    "occasion": None,
    "recipient": None,
    "budget": None,
    "style": None,
    "colors": [],
    "avoid_flowers": [],
    "delivery_date": None,
    "delivery_address": None,
    "phone": None,
    "comment": None,
    "selected_flowers": [],
    "bouquet_options": [],
    "estimated_price": None,
    "summary": None,
    "is_ready_for_confirmation": False,
    "order_submitted": False,
    "submitted_order_id": None,
    "manager_requested": False,
    "ai_requests_used": 0,
}


def _new_default_state() -> dict:
    return deepcopy(DEFAULT_ORDER_STATE)


def get_or_create_conversation_state(shop_id: int, customer_id: int) -> dict:
    with SessionLocal() as session:
        conversation_state = session.scalar(
            select(ConversationState).where(
                ConversationState.shop_id == shop_id,
                ConversationState.customer_id == customer_id,
            )
        )

        if conversation_state is None:
            state = _new_default_state()
            conversation_state = ConversationState(
                shop_id=shop_id,
                customer_id=customer_id,
                state=state,
            )
            session.add(conversation_state)
            session.commit()
            return state

        return conversation_state.state


def reset_conversation_state(shop_id: int, customer_id: int) -> dict:
    state = _new_default_state()

    with SessionLocal() as session:
        conversation_state = session.scalar(
            select(ConversationState).where(
                ConversationState.shop_id == shop_id,
                ConversationState.customer_id == customer_id,
            )
        )

        if conversation_state is None:
            conversation_state = ConversationState(
                shop_id=shop_id,
                customer_id=customer_id,
                state=state,
            )
            session.add(conversation_state)
        else:
            conversation_state.state = state

        session.commit()
        return state


def update_conversation_state(
    shop_id: int,
    customer_id: int,
    state: dict,
) -> dict:
    with SessionLocal() as session:
        conversation_state = session.scalar(
            select(ConversationState).where(
                ConversationState.shop_id == shop_id,
                ConversationState.customer_id == customer_id,
            )
        )

        if conversation_state is None:
            conversation_state = ConversationState(
                shop_id=shop_id,
                customer_id=customer_id,
                state=state,
            )
            session.add(conversation_state)
        else:
            conversation_state.state = state

        session.commit()
        return state


def add_conversation_log(
    *,
    shop_id: int,
    customer_id: int | None,
    role: str,
    message: str,
    meta: dict | None = None,
) -> None:
    text = str(message or "").strip()
    if not text:
        return

    try:
        with SessionLocal() as session:
            session.add(
                ConversationLog(
                    shop_id=shop_id,
                    customer_id=customer_id,
                    role=role,
                    message=text[:4000],
                    meta=meta,
                )
            )
            session.commit()
    except Exception:
        logger.exception("Failed to write conversation log")


def list_conversation_logs_for_customer(
    shop_id: int,
    customer_id: int,
    limit: int = 80,
) -> list[ConversationLog]:
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(ConversationLog)
                .where(
                    ConversationLog.shop_id == shop_id,
                    ConversationLog.customer_id == customer_id,
                )
                .order_by(ConversationLog.id.desc())
                .limit(limit)
            ).all()
        )


def list_error_logs_for_shop(shop_id: int, limit: int = 80) -> list[ConversationLog]:
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(ConversationLog)
                .where(
                    ConversationLog.shop_id == shop_id,
                    ConversationLog.role == "error",
                )
                .order_by(ConversationLog.id.desc())
                .limit(limit)
            ).all()
        )
