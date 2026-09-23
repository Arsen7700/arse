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

    return _format_report(
        f"Отчёт о продажах за {report_date.strftime('%d.%m.%Y')}",
        sales,
        "За выбранный день продаж нет.",
    )


def build_monthly_report(db: Session, year: int, month: int, timezone_name: str) -> str:
    if not 2000 <= year <= 2100 or not 1 <= month <= 12:
        raise ValueError("Некорректный год или месяц")
    zone = ZoneInfo(timezone_name)
    local_start = datetime(year, month, 1, tzinfo=zone)
    local_end = (
        datetime(year + 1, 1, 1, tzinfo=zone)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=zone)
    )
    start_utc = local_start.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = local_end.astimezone(timezone.utc).replace(tzinfo=None)
    sales = (
        db.query(models.Sale)
        .filter(models.Sale.sale_date >= start_utc, models.Sale.sale_date < end_utc)
        .order_by(models.Sale.product_name, models.Sale.sale_date)
        .all()
    )
    return _format_report(
        f"Отчёт о продажах за {month:02d}.{year}",
        sales,
        "За выбранный месяц продаж нет.",
    )


def _format_report(title: str, sales: list, empty_message: str) -> str:
    grouped = {}
    for sale in sales:
        name = sale.product_name or "Товар без названия"
        item = grouped.setdefault(name, {"quantity": 0, "revenue": Decimal("0")})
        item["quantity"] += sale.quantity
        item["revenue"] += Decimal(str(sale.total_amount))

    lines = [title, ""]
    if grouped:
        for name, item in sorted(grouped.items(), key=lambda pair: pair[0].casefold()):
            quantity = item["quantity"]
            revenue = item["revenue"]
            lines.append(
                f"• {name} — {quantity} шт.; сумма {revenue:.2f} сом"
            )
    else:
        lines.append(empty_message)

    total_quantity = sum(item["quantity"] for item in grouped.values())
    lines.extend(
        [
            "",
            f"Всего продано: {total_quantity} шт.",
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
