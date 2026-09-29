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

REPORT_ROWS = (
    (
        "SA",
        30,
        "quantity",
        ("sa", "sim-карта", "sim карта", "сим-карта", "сим карта", "сим-карты"),
    ),
    ("Услуги", 15000, "revenue", ("услуги", "услуга")),
    ("Мой", 25, "quantity", ("мой", "мой!")),
    (
        "Карты",
        25,
        "quantity",
        ("карты", "карта"),
    ),
    ("Устройства", 2, "quantity", ("устройства", "устройство")),
    ("Saima", 1, "quantity", ("saima",)),
    ("Телефоны", 2, "quantity", ("телефоны", "телефон")),
    ("Аксессуары", 3100, "accessories", ("аксессуары", "аксессуар")),
    ("Вместе дешевле", 0, "quantity", ("вместе дешевле",)),
    ("O!семья", 0, "quantity", ("o!семья", "o! семья")),
)


def build_daily_report(
    db: Session, report_date: date, timezone_name: str, store_id: int | None = None
) -> str:
    zone = ZoneInfo(timezone_name)
    local_start = datetime.combine(report_date, time.min, tzinfo=zone)
    local_end = datetime.combine(report_date + timedelta(days=1), time.min, tzinfo=zone)
    start_utc = local_start.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = local_end.astimezone(timezone.utc).replace(tzinfo=None)

    query = db.query(models.Sale).filter(
        models.Sale.sale_date >= start_utc, models.Sale.sale_date < end_utc
    )
    if store_id is not None:
        query = query.filter(models.Sale.store_id == store_id)
    sales = query.order_by(models.Sale.product_name, models.Sale.sale_date).all()
    settings = None
    if store_id is not None:
        settings = db.query(models.DailyReportSettings).filter_by(
            store_id=store_id, report_date=report_date
        ).first()

    return _format_report(
        f"Отчёт о продажах за {report_date.strftime('%d.%m.%Y')}",
        sales,
        "За выбранный день продаж нет.",
        settings,
    )


def build_monthly_report(
    db: Session, year: int, month: int, timezone_name: str, store_id: int | None = None
) -> str:
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
    query = db.query(models.Sale).filter(
        models.Sale.sale_date >= start_utc, models.Sale.sale_date < end_utc
    )
    if store_id is not None:
        query = query.filter(models.Sale.store_id == store_id)
    sales = query.order_by(models.Sale.product_name, models.Sale.sale_date).all()
    return _format_report(
        f"Отчёт о продажах за {month:02d}.{year}",
        sales,
        "За выбранный месяц продаж нет.",
    )


def _format_report(title: str, sales: list, empty_message: str, settings=None) -> str:
    normalized_aliases = {
        alias.casefold(): (label, metric)
        for label, _plan, metric, aliases in REPORT_ROWS
        for alias in aliases
    }
    actuals = {
        label: {"quantity": 0, "revenue": Decimal("0")}
        for label, _plan, _metric, _aliases in REPORT_ROWS
    }
    for sale in sales:
        mapped = normalized_aliases.get((sale.product_name or "").strip().casefold())
        if mapped is None:
            continue
        label, _metric = mapped
        item = actuals[label]
        item["quantity"] += sale.quantity
        item["revenue"] += Decimal(str(sale.total_amount))

    report_date = title.removeprefix("Отчёт о продажах за ")
    lines = ["План/факт", report_date, "O!Store Бета 2"]
    for label, plan, metric, _aliases in REPORT_ROWS:
        item = actuals[label]
        if metric == "revenue":
            fact = f"{item['revenue']:.0f}"
            lines.append(f"{label}: {plan}/ {fact}")
        elif metric == "accessories":
            fact_amount = f"{item['revenue']:.0f}"
            lines.append(
                f"{label}: {plan}/ {item['quantity']}шт ({fact_amount})"
            )
        elif label == "Устройства":
            lines.append(f"{label}: {plan} \\ {item['quantity']}")
        elif label == "O!семья":
            lines.append(f"{label}-{item['quantity']}")
        elif label == "Вместе дешевле":
            lines.append(f"{label} {item['quantity']}")
        else:
            lines.append(f"{label}: {plan}/ {item['quantity']}")

    lines.extend(
        [
            f"Лимит Дс {settings.cash_limit if settings else '60к'}",
            f"Остаток ДС: {settings.cash_remaining if settings else '80к'}",
            f"Инкассация: {settings.collection_status if settings else 'нет'}",
            "Отказы со стороны банка:0 2",
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
