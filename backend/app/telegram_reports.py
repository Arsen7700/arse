"""Telegram report formatting and Bot API delivery helpers."""

import json
import os
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from . import models


def build_daily_report(db: Session, report_date: date, timezone_name: str) -> str:
    zone = ZoneInfo(timezone_name)
    local_start = datetime.combine(report_date, time.min, tzinfo=zone)
    local_end = datetime.combine(report_date + timedelta(days=1), time.min, tzinfo=zone)
    start_utc = local_start.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = local_end.astimezone(timezone.utc).replace(tzinfo=None)

    sales = (
        db.query(models.Sale)
        .filter(models.Sale.sale_date >= start_utc, models.Sale.sale_date < end_utc)
        .order_by(models.Sale.product_name, models.Sale.sale_date)
        .all()
    )

    grouped = {}
    for sale in sales:
        name = sale.product_name or "Товар без названия"
        item = grouped.setdefault(name, {"quantity": 0, "revenue": Decimal("0")})
        item["quantity"] += sale.quantity
        item["revenue"] += Decimal(str(sale.total_amount))

    lines = [f"Отчёт о продажах за {report_date.strftime('%d.%m.%Y')}", ""]
    if grouped:
        for name, item in sorted(grouped.items(), key=lambda pair: pair[0].casefold()):
            quantity = item["quantity"]
            revenue = item["revenue"]
            average_price = revenue / quantity if quantity else Decimal("0")
            lines.append(
                f"• {name} — {quantity} шт.; средняя цена {average_price:.2f} сом; "
                f"сумма {revenue:.2f} сом"
            )
    else:
        lines.append("За выбранный день продаж нет.")

    total_quantity = sum(item["quantity"] for item in grouped.values())
    total_revenue = sum(
        (item["revenue"] for item in grouped.values()), Decimal("0")
    )
    lines.extend(
        [
            "",
            f"Всего продано: {total_quantity} шт.",
            f"Общая выручка: {total_revenue:.2f} сом",
        ]
    )
    return "\n".join(lines)


def send_telegram_message(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Настройте TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID в Render")

    # Telegram text messages are limited to 4096 characters. Split only between lines.
    chunks = []
    current = ""
    for line in text.splitlines():
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > 4000 and current:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)

    for chunk in chunks:
        request = Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps({"chat_id": chat_id, "text": chunk}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as error:
            raise RuntimeError("Не удалось связаться с Telegram Bot API") from error
        if not result.get("ok"):
            raise RuntimeError(result.get("description", "Telegram не принял сообщение"))


def check_and_send_scheduled_report(session_factory) -> bool:
    """Send today's report once when the enabled schedule becomes due."""
    db = session_factory()
    try:
        schedule = db.get(models.TelegramSchedule, 1)
        if not schedule or not schedule.enabled:
            return False
        try:
            zone = ZoneInfo(schedule.timezone)
        except ZoneInfoNotFoundError:
            return False

        now = datetime.now(zone)
        if now.strftime("%H:%M") < schedule.send_time or schedule.last_sent_on == now.date():
            return False

        report = build_daily_report(db, now.date(), schedule.timezone)
        send_telegram_message(report)
        schedule.last_sent_on = now.date()
        db.commit()
        return True
    finally:
        db.close()
