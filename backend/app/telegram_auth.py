"""Validation of Telegram Mini App initData for protected API access."""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class TelegramInitDataError(ValueError):
    """Raised when Telegram Mini App initialization data is not trustworthy."""


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    *,
    now: int | None = None,
    max_age_seconds: int = 86_400,
) -> int:
    """Return the authenticated Telegram user ID or reject the payload."""
    if not init_data or not bot_token:
        raise TelegramInitDataError("Telegram initData or bot token is missing")

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as error:
        raise TelegramInitDataError("Malformed Telegram initData") from error

    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise TelegramInitDataError("Duplicate Telegram initData fields")
    received_hash = fields.pop("hash", "")
    if len(received_hash) != 64:
        raise TelegramInitDataError("Telegram initData hash is missing")

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(fields.items())
    )
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
    ).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash.lower()):
        raise TelegramInitDataError("Telegram initData signature is invalid")

    try:
        auth_date = int(fields["auth_date"])
        user = json.loads(fields["user"])
        user_id = int(user["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise TelegramInitDataError("Telegram user or auth_date is missing") from error

    current_time = int(time.time()) if now is None else now
    age = current_time - auth_date
    if age < -300 or age > max_age_seconds:
        raise TelegramInitDataError("Telegram initData has expired")
    if user_id <= 0:
        raise TelegramInitDataError("Telegram user ID is invalid")
    return user_id
