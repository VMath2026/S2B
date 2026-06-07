from copy import deepcopy

from sqlalchemy import select

from app.db.models import ConversationState
from app.db.session import SessionLocal


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
