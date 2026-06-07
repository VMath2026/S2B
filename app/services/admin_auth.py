import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from sqlalchemy import select

from app.config import settings
from app.db.models import ShopAdminUser
from app.db.session import SessionLocal


PASSWORD_ITERATIONS = 120_000
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 14


@dataclass(frozen=True)
class ShopAdminIdentity:
    shop_id: int
    username: str


def create_or_update_shop_admin_user(
    *,
    shop_id: int,
    username: str,
    password: str,
) -> ShopAdminUser:
    normalized_username = _normalize_username(username)
    if not normalized_username:
        raise ValueError("username is required")
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")

    with SessionLocal() as session:
        user = session.scalar(
            select(ShopAdminUser).where(ShopAdminUser.username == normalized_username)
        )
        if user is None:
            user = ShopAdminUser(
                shop_id=shop_id,
                username=normalized_username,
                password_hash=hash_password(password),
            )
            session.add(user)
        else:
            user.shop_id = shop_id
            user.password_hash = hash_password(password)
            user.is_active = True

        session.commit()
        session.refresh(user)
        return user


def authenticate_shop_admin(
    *,
    username: str,
    password: str,
) -> ShopAdminIdentity | None:
    normalized_username = _normalize_username(username)
    if not normalized_username or not password:
        return None

    with SessionLocal() as session:
        user = session.scalar(
            select(ShopAdminUser).where(ShopAdminUser.username == normalized_username)
        )
        if user is None or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None

        return ShopAdminIdentity(shop_id=user.shop_id, username=user.username)


def create_shop_admin_token(identity: ShopAdminIdentity) -> str:
    payload = {
        "shop_id": identity.shop_id,
        "username": identity.username,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    payload_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    payload_b64 = _b64encode(payload_text.encode("utf-8"))
    signature = _sign(payload_b64)
    return f"{payload_b64}.{signature}"


def verify_shop_admin_token(token: str | None) -> ShopAdminIdentity | None:
    if not token:
        return None

    if token.lower().startswith("bearer "):
        token = token.split(" ", maxsplit=1)[1].strip()

    if "." not in token:
        return None

    payload_b64, signature = token.split(".", maxsplit=1)
    expected_signature = _sign(payload_b64)
    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        payload = json.loads(_b64decode(payload_b64).decode("utf-8"))
    except Exception:
        return None

    if int(payload.get("exp") or 0) < int(time.time()):
        return None

    shop_id = payload.get("shop_id")
    username = payload.get("username")
    if not isinstance(shop_id, int) or not isinstance(username, str):
        return None

    return ShopAdminIdentity(shop_id=shop_id, username=username)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return (
        f"pbkdf2_sha256${PASSWORD_ITERATIONS}$"
        f"{_b64encode(salt)}${_b64encode(digest)}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_b64, digest_b64 = password_hash.split("$")
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    try:
        iterations = int(iterations_text)
        salt = _b64decode(salt_b64)
        expected_digest = _b64decode(digest_b64)
    except Exception:
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(digest, expected_digest)


def _normalize_username(username: str) -> str:
    return username.strip().lower()


def _token_secret() -> str:
    secret = settings.admin_session_secret or settings.admin_api_key
    if not secret:
        raise RuntimeError("ADMIN_SESSION_SECRET or ADMIN_API_KEY is required")
    return secret


def _sign(payload_b64: str) -> str:
    digest = hmac.new(
        _token_secret().encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
