import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest

from app.telegram_auth import TelegramInitDataError, validate_telegram_init_data


def signed_init_data(bot_token, *, user_id=12345, auth_date=1_700_000_000):
    fields = {
        "auth_date": str(auth_date),
        "query_id": "sample-query",
        "user": json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":")),
    }
    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(fields.items())
    )
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode(fields)


def test_validate_telegram_init_data_returns_signed_user_id():
    payload = signed_init_data("bot-token")
    assert validate_telegram_init_data(
        payload, "bot-token", now=1_700_000_100
    ) == 12345


def test_validate_telegram_init_data_rejects_tampered_payload():
    payload = signed_init_data("bot-token").replace("12345", "54321")
    with pytest.raises(TelegramInitDataError):
        validate_telegram_init_data(payload, "bot-token", now=1_700_000_100)


def test_validate_telegram_init_data_rejects_expired_payload():
    payload = signed_init_data("bot-token")
    with pytest.raises(TelegramInitDataError, match="expired"):
        validate_telegram_init_data(
            payload, "bot-token", now=1_700_000_000 + 86_401
        )
