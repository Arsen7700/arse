import asyncio
import hmac
import logging
import os
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, Depends, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import extract, func, update
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from .database import Base, engine, get_db, SessionLocal
from . import models, schemas
from .migrations import migrate_plan_fact_catalog, migrate_sales_schema, migrate_store_and_staff_schema
from .plan_fact import PLAN_FACT_ITEMS, PLAN_FACT_NAMES
from .access import CurrentUser, apply_store_scope, assigned_store_id, current_user, require_roles
from .telegram_reports import (
    build_daily_report,
    build_monthly_report,
    build_personal_sales_report,
    check_and_send_scheduled_report,
    send_telegram_message,
)
from .telegram_auth import TelegramInitDataError, validate_telegram_init_data

migrate_sales_schema(engine)
Base.metadata.create_all(bind=engine)
migrate_store_and_staff_schema(engine)
migrate_plan_fact_catalog(engine)

app = FastAPI(title="Inventory & Sales API", version="1.0.0")
logger = logging.getLogger(__name__)
telegram_scheduler_task = None


def require_telegram_admin(x_telegram_admin_key: Optional[str] = Header(None)):
    expected_key = os.getenv("TELEGRAM_ADMIN_KEY", "")
    if not expected_key:
        raise HTTPException(status_code=503, detail="TELEGRAM_ADMIN_KEY не настроен на backend")
    if not x_telegram_admin_key or not hmac.compare_digest(x_telegram_admin_key, expected_key):
        raise HTTPException(status_code=403, detail="Неверный ключ администратора Telegram")


def require_telegram_report_sender(
    user: CurrentUser = Depends(current_user),
    x_telegram_admin_key: Optional[str] = Header(None),
):
    """Leads use their verified Telegram role; admins retain the extra secret check."""
    if user.role in {"lead", "specialist", "cashier"}:
        return
    require_telegram_admin(x_telegram_admin_key)


def configured_telegram_admin_ids() -> set[str]:
    values = os.getenv("TELEGRAM_ADMIN_IDS") or os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
    return {value.strip() for value in values.split(",") if value.strip()}


async def telegram_scheduler_loop():
    while True:
        try:
            await asyncio.to_thread(check_and_send_scheduled_report, SessionLocal)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduled Telegram report failed")
        await asyncio.sleep(30)


@app.on_event("startup")
async def start_telegram_scheduler():
    global telegram_scheduler_task
    telegram_scheduler_task = asyncio.create_task(telegram_scheduler_loop())


@app.on_event("shutdown")
async def stop_telegram_scheduler():
    if telegram_scheduler_task:
        telegram_scheduler_task.cancel()
        try:
            await telegram_scheduler_task
        except asyncio.CancelledError:
            pass

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

@app.middleware("http")
async def require_telegram_mini_app_user(request: Request, call_next):
    """Protect production API routes; keep health/docs and local development usable."""
    if os.getenv("APP_ENV", "production").lower() in {"development", "dev", "test"}:
        request.state.current_user = CurrentUser(0, "Локальный разработчик", "admin")
        return await call_next(request)
    if request.method == "OPTIONS" or request.url.path in {"/", "/docs", "/openapi.json", "/redoc"}:
        return await call_next(request)

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    admin_ids = configured_telegram_admin_ids()
    if not bot_token or not admin_ids:
        return JSONResponse(
            status_code=503,
            content={"detail": "Настройте TELEGRAM_BOT_TOKEN и TELEGRAM_ADMIN_IDS"},
        )

    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if not init_data:
        return JSONResponse(
            status_code=401,
            content={"detail": "Откройте приложение через кнопку бота в Telegram"},
        )
    try:
        telegram_user_id = validate_telegram_init_data(init_data, bot_token)
    except TelegramInitDataError:
        return JSONResponse(
            status_code=401,
            content={"detail": "Не удалось подтвердить вход через Telegram. Откройте Mini App заново."},
        )
    try:
        with SessionLocal() as auth_db:
            account = auth_db.get(models.StaffAccount, telegram_user_id)
            if str(telegram_user_id) in admin_ids:
                if account is None:
                    account = models.StaffAccount(
                        telegram_id=telegram_user_id,
                        display_name=f"Администратор {telegram_user_id}",
                        role="admin",
                        is_active=True,
                    )
                    auth_db.add(account)
                else:
                    account.role = "admin"
                    account.is_active = True
                auth_db.commit()
                request.state.current_user = CurrentUser(
                    telegram_user_id, account.display_name, "admin", account.store_id
                )
            elif account is None or not account.is_active:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Ваш Telegram-аккаунт ещё не добавлен администратором"},
                )
            else:
                if account.role not in {"specialist", "cashier", "lead", "admin"}:
                    return JSONResponse(status_code=403, content={"detail": "Для учётной записи не настроена роль"})
                if account.role in {"specialist", "cashier"}:
                    assigned_store = auth_db.get(models.Store, account.store_id) if account.store_id else None
                    if assigned_store is None or not assigned_store.is_active:
                        return JSONResponse(status_code=403, content={"detail": "Ваша лавочка не назначена или отключена"})
                request.state.current_user = CurrentUser(
                    account.telegram_id,
                    account.display_name,
                    account.role,
                    account.store_id,
                )
    except Exception:
        logger.exception("Unable to load Telegram staff account")
        return JSONResponse(status_code=503, content={"detail": "Не удалось загрузить учётную запись"})
    return await call_next(request)


# Add CORS last so it wraps auth middleware and also decorates 401/403 responses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def month_bounds(year: int, month: int):
    if not 2000 <= year <= 2100 or not 1 <= month <= 12:
        raise HTTPException(status_code=422, detail="Некорректный год или месяц")
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end


def ensure_default_store(db: Session) -> models.Store:
    store = db.query(models.Store).filter_by(name="Основная лавочка").first()
    if store is None:
        store = models.Store(name="Основная лавочка", is_active=True)
        db.add(store)
        db.flush()
    return store


def ensure_plan_fact_products(db: Session, store_id: int) -> None:
    """Create the fixed plan-fact item tree for a newly created store."""
    products_by_name = {
        product.name: product
        for product in db.query(models.Product).filter_by(
            store_id=store_id, is_plan_fact=True
        ).all()
    }
    for item in PLAN_FACT_ITEMS:
        if item["name"] in products_by_name:
            continue
        product = models.Product(
            store_id=store_id,
            name=item["name"],
            purchase_price=0,
            sale_price=0,
            quantity=0,
            description="Показатель план-факта; складской остаток не ведётся.",
            is_plan_fact=True,
            parent_product_id=(products_by_name[item["parent"]].id if item["parent"] else None),
        )
        db.add(product)
        db.flush()
        products_by_name[item["name"]] = product


def get_store(db: Session, store_id: int, *, active_only: bool = True) -> models.Store:
    store = db.get(models.Store, store_id)
    if not store or (active_only and not store.is_active):
        raise HTTPException(status_code=404, detail="Лавочка не найдена или отключена")
    return store


def require_product_access(db: Session, product_id: int, user: CurrentUser) -> models.Product:
    product = db.get(models.Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    if user.role in {"specialist", "cashier"} and product.store_id != user.store_id:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return product


def require_sale_access(db: Session, sale_id: int, user: CurrentUser) -> models.Sale:
    sale = db.get(models.Sale, sale_id)
    if not sale or (user.role in {"specialist", "cashier"} and sale.store_id != user.store_id):
        raise HTTPException(status_code=404, detail="Продажа не найдена")
    if user.role in {"specialist", "cashier"} and sale.created_by_telegram_id != user.telegram_id:
        raise HTTPException(status_code=403, detail="Можно изменять только свои продажи")
    return sale


@app.get("/auth/me")
def get_current_account(user: CurrentUser = Depends(current_user)):
    return {
        "telegram_id": user.telegram_id,
        "display_name": user.display_name,
        "role": user.role,
        "store_id": user.store_id,
    }


@app.get("/stores", response_model=list[schemas.StoreOut])
def list_stores(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
):
    query = db.query(models.Store)
    if user.role in {"specialist", "cashier"}:
        if user.store_id is None:
            return []
        query = query.filter(models.Store.id == user.store_id)
    elif user.role != "admin" or not include_inactive:
        query = query.filter(models.Store.is_active.is_(True))
    return query.order_by(models.Store.name).all()


@app.post("/admin/stores", response_model=schemas.StoreOut)
def create_store(
    payload: schemas.StoreCreate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("admin")),
):
    name = payload.name.strip()
    if db.query(models.Store).filter(func.lower(models.Store.name) == name.lower()).first():
        raise HTTPException(status_code=409, detail="Лавочка с таким названием уже существует")
    store = models.Store(name=name)
    db.add(store)
    db.commit()
    db.refresh(store)
    ensure_plan_fact_products(db, store.id)
    db.commit()
    return store


@app.put("/admin/stores/{store_id}", response_model=schemas.StoreOut)
def update_store(
    store_id: int,
    payload: schemas.StoreUpdate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("admin")),
):
    store = get_store(db, store_id, active_only=False)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "name":
            value = value.strip()
            if not value:
                raise HTTPException(status_code=422, detail="Название лавочки не может быть пустым")
            duplicate = db.query(models.Store).filter(
                func.lower(models.Store.name) == value.lower(), models.Store.id != store_id
            ).first()
            if duplicate:
                raise HTTPException(status_code=409, detail="Лавочка с таким названием уже существует")
        setattr(store, key, value)
    db.commit()
    db.refresh(store)
    return store


@app.get("/admin/users", response_model=list[schemas.StaffAccountOut])
def list_staff_accounts(
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("admin")),
):
    rows = db.query(models.StaffAccount, models.Store.name).outerjoin(
        models.Store, models.Store.id == models.StaffAccount.store_id
    ).order_by(models.StaffAccount.display_name).all()
    return [
        {
            "telegram_id": account.telegram_id,
            "display_name": account.display_name,
            "role": account.role,
            "store_id": account.store_id,
            "store_name": store_name,
            "is_active": account.is_active,
        }
        for account, store_name in rows
    ]


@app.post("/admin/users", response_model=schemas.StaffAccountOut)
def create_staff_account(
    payload: schemas.StaffAccountCreate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("admin")),
):
    if db.get(models.StaffAccount, payload.telegram_id):
        raise HTTPException(status_code=409, detail="Этот Telegram ID уже добавлен")
    if not payload.display_name.strip():
        raise HTTPException(status_code=422, detail="Укажите имя сотрудника")
    if payload.role in {"specialist", "cashier"} and payload.store_id is None:
        raise HTTPException(status_code=422, detail="Специалисту или кассиру нужно назначить лавочку")
    store = get_store(db, payload.store_id) if payload.store_id is not None else None
    account = models.StaffAccount(**payload.model_dump())
    db.add(account)
    db.commit()
    return {
        "telegram_id": account.telegram_id,
        "display_name": account.display_name,
        "role": account.role,
        "store_id": account.store_id,
        "store_name": store.name if store else None,
        "is_active": account.is_active,
    }


@app.put("/admin/users/{telegram_id}", response_model=schemas.StaffAccountOut)
def update_staff_account(
    telegram_id: int,
    payload: schemas.StaffAccountUpdate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("admin")),
):
    account = db.get(models.StaffAccount, telegram_id)
    if not account:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    data = payload.model_dump(exclude_unset=True)
    if str(telegram_id) in configured_telegram_admin_ids() and (
        data.get("role", account.role) != "admin" or data.get("is_active", account.is_active) is False
    ):
        raise HTTPException(
            status_code=409,
            detail="Первоначального администратора можно отключить только после удаления Telegram ID из настроек Render",
        )
    role = data.get("role", account.role)
    store_id = data.get("store_id", account.store_id)
    if role in {"specialist", "cashier"} and store_id is None:
        raise HTTPException(status_code=422, detail="Специалисту или кассиру нужно назначить лавочку")
    store = get_store(db, store_id) if store_id is not None else None
    for key, value in data.items():
        setattr(account, key, value)
    db.commit()
    return {
        "telegram_id": account.telegram_id,
        "display_name": account.display_name,
        "role": account.role,
        "store_id": account.store_id,
        "store_name": store.name if store else None,
        "is_active": account.is_active,
    }


@app.get("/team/staff", response_model=list[schemas.StaffAccountOut])
def list_team_staff(
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("lead")),
):
    rows = db.query(models.StaffAccount, models.Store.name).outerjoin(
        models.Store, models.Store.id == models.StaffAccount.store_id
    ).filter(
        models.StaffAccount.role.in_(("specialist", "cashier")),
        models.StaffAccount.is_active.is_(True),
    ).order_by(
        models.StaffAccount.display_name
    ).all()
    return [
        {
            "telegram_id": account.telegram_id,
            "display_name": account.display_name,
            "role": account.role,
            "store_id": account.store_id,
            "store_name": store_name,
            "is_active": account.is_active,
        }
        for account, store_name in rows
    ]


@app.post("/team/staff", response_model=schemas.StaffAccountOut)
def create_team_staff(
    payload: schemas.TeamStaffCreate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("lead")),
):
    if not payload.display_name.strip():
        raise HTTPException(status_code=422, detail="Укажите имя сотрудника")
    store = get_store(db, payload.store_id)
    account = db.get(models.StaffAccount, payload.telegram_id)
    if account:
        if account.is_active or account.role not in {"specialist", "cashier"}:
            raise HTTPException(status_code=409, detail="Этот Telegram ID уже добавлен")
        account.display_name = payload.display_name.strip()
        account.role = payload.role
        account.store_id = store.id
        account.is_active = True
    else:
        account = models.StaffAccount(
            telegram_id=payload.telegram_id,
            display_name=payload.display_name.strip(),
            role=payload.role,
            store_id=store.id,
            is_active=True,
        )
        db.add(account)
    db.commit()
    return {
        "telegram_id": account.telegram_id,
        "display_name": account.display_name,
        "role": account.role,
        "store_id": account.store_id,
        "store_name": store.name,
        "is_active": account.is_active,
    }


@app.put("/team/staff/{telegram_id}", response_model=schemas.StaffAccountOut)
def update_team_staff_role(
    telegram_id: int,
    payload: schemas.TeamStaffRoleUpdate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("lead")),
):
    account = db.get(models.StaffAccount, telegram_id)
    if not account or account.role not in {"specialist", "cashier"}:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    store = get_store(db, payload.store_id)
    account.role = payload.role
    account.store_id = store.id
    db.commit()
    return {
        "telegram_id": account.telegram_id,
        "display_name": account.display_name,
        "role": account.role,
        "store_id": account.store_id,
        "store_name": store.name,
        "is_active": account.is_active,
    }


@app.delete("/team/staff/{telegram_id}")
def delete_team_staff(
    telegram_id: int,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("lead")),
):
    """Remove staff access while preserving historical sales and goals."""
    account = db.get(models.StaffAccount, telegram_id)
    if not account or account.role not in {"specialist", "cashier"}:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    if str(telegram_id) in configured_telegram_admin_ids():
        raise HTTPException(status_code=409, detail="Нельзя удалить первоначального администратора")
    account.is_active = False
    db.commit()
    return {"ok": True, "message": "Доступ сотрудника удалён; история продаж сохранена."}


def daily_report_settings_data(settings, report_date: date, store_id: int):
    return {
        "report_date": report_date,
        "store_id": store_id,
        "cash_limit": settings.cash_limit if settings else "60к",
        "cash_remaining": settings.cash_remaining if settings else "80к",
        "collection_status": settings.collection_status if settings else "нет",
    }


def resolve_report_store(db: Session, user: CurrentUser, requested_store_id: int | None):
    store_id = assigned_store_id(user, requested_store_id)
    if store_id is None:
        raise HTTPException(status_code=422, detail="Выберите лавочку для отчёта")
    return get_store(db, store_id).id


@app.get("/reports/daily-settings", response_model=schemas.DailyReportSettingsOut)
def get_daily_report_settings(
    report_date: date = Query(...),
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("specialist", "cashier", "lead")),
):
    selected_store_id = resolve_report_store(db, user, store_id)
    settings = db.query(models.DailyReportSettings).filter_by(
        store_id=selected_store_id, report_date=report_date
    ).first()
    return daily_report_settings_data(settings, report_date, selected_store_id)


@app.put("/reports/daily-settings", response_model=schemas.DailyReportSettingsOut)
def update_daily_report_settings(
    payload: schemas.DailyReportSettingsUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("specialist", "cashier", "lead")),
):
    selected_store_id = resolve_report_store(db, user, payload.store_id)
    settings = db.query(models.DailyReportSettings).filter_by(
        store_id=selected_store_id, report_date=payload.report_date
    ).first()
    if settings is None:
        settings = models.DailyReportSettings(
            store_id=selected_store_id, report_date=payload.report_date
        )
        db.add(settings)
    settings.cash_limit = payload.cash_limit.strip()
    settings.cash_remaining = payload.cash_remaining.strip()
    settings.collection_status = payload.collection_status.strip()
    db.commit()
    db.refresh(settings)
    return daily_report_settings_data(settings, payload.report_date, selected_store_id)


@app.get("/reports/staff")
def staff_sales_report(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("lead")),
):
    sales_query = db.query(models.Sale)
    if start:
        sales_query = sales_query.filter(models.Sale.sale_date >= start)
    if end:
        sales_query = sales_query.filter(models.Sale.sale_date < end)
    sales_query = apply_store_scope(sales_query, models.Sale, user, store_id)
    sales = sales_query.all()

    grouped = {}
    for sale in sales:
        key = sale.created_by_telegram_id
        entry = grouped.setdefault(key, {
            "sold_quantity": 0, "revenue": 0.0, "profit": 0.0,
            "sales_count": 0, "store_ids": set(), "products": {},
        })
        entry["sold_quantity"] += sale.quantity
        entry["revenue"] += sale.total_amount
        entry["profit"] += sale.profit
        entry["sales_count"] += 1
        entry["store_ids"].add(sale.store_id)
        product_key = (sale.product_id, sale.product_name)
        product_stats = entry["products"].setdefault(product_key, {
            "product_name": sale.product_name,
            "sold_quantity": 0,
            "revenue": 0.0,
            "profit": 0.0,
            "sales_count": 0,
        })
        product_stats["sold_quantity"] += sale.quantity
        product_stats["revenue"] += sale.total_amount
        product_stats["profit"] += sale.profit
        product_stats["sales_count"] += 1

    attributed_ids = [key for key in grouped if key is not None]
    accounts_query = db.query(models.StaffAccount).filter(
        (models.StaffAccount.role.in_(("specialist", "cashier")))
        | (models.StaffAccount.telegram_id.in_(attributed_ids) if attributed_ids else False)
    )
    if store_id is not None:
        accounts_query = accounts_query.filter(
            (models.StaffAccount.store_id == store_id)
            | (models.StaffAccount.telegram_id.in_(attributed_ids) if attributed_ids else False)
        )
    accounts = accounts_query.order_by(models.StaffAccount.display_name).all()
    all_store_ids = {shop_id for entry in grouped.values() for shop_id in entry["store_ids"]}
    all_store_ids.update(account.store_id for account in accounts if account.store_id is not None)
    stores = {
        store.id: store.name
        for store in db.query(models.Store).filter(models.Store.id.in_(all_store_ids)).all()
    } if all_store_ids else {}

    result = []
    for account in accounts:
        stats = grouped.get(account.telegram_id, {})
        result.append({
            "telegram_id": account.telegram_id,
            "display_name": account.display_name,
            "role": account.role,
            "store_name": ", ".join(sorted(stores.get(shop_id, f"Лавочка {shop_id}") for shop_id in stats.get("store_ids", set()))) or stores.get(account.store_id, "—"),
            "sold_quantity": stats.get("sold_quantity", 0),
            "revenue": round(stats.get("revenue", 0), 2),
            "profit": round(stats.get("profit", 0), 2),
            "sales_count": stats.get("sales_count", 0),
            "products": [
                {**item, "revenue": round(item["revenue"], 2), "profit": round(item["profit"], 2)}
                for item in sorted(stats.get("products", {}).values(), key=lambda value: value["product_name"].casefold())
            ],
        })
    if None in grouped:
        stats = grouped[None]
        result.append({
            "telegram_id": None,
            "display_name": "Исторические продажи",
            "role": "unknown",
            "store_name": "Все лавочки",
            "sold_quantity": stats["sold_quantity"],
            "revenue": round(stats["revenue"], 2),
            "profit": round(stats["profit"], 2),
            "sales_count": stats["sales_count"],
            "products": [
                {**item, "revenue": round(item["revenue"], 2), "profit": round(item["profit"], 2)}
                for item in sorted(stats["products"].values(), key=lambda value: value["product_name"].casefold())
            ],
        })
    return result

@app.get("/")
def root():
    return {"message": "Inventory API is running"}

@app.post("/categories", response_model=schemas.CategoryOut)
def create_category(
    payload: schemas.CategoryCreate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("specialist", "lead")),
):
    exists = db.query(models.Category).filter(
        func.lower(models.Category.name) == payload.name.strip().lower()
    ).first()
    if exists:
        return exists
    obj = models.Category(name=payload.name.strip())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

@app.get("/categories", response_model=list[schemas.CategoryOut])
def list_categories(db: Session = Depends(get_db), _user: CurrentUser = Depends(current_user)):
    return db.query(models.Category).order_by(models.Category.name).all()

@app.post("/products", response_model=schemas.ProductOut)
def create_product(
    payload: schemas.ProductCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("lead")),
):
    selected_store_id = assigned_store_id(user, payload.store_id)
    store = get_store(db, selected_store_id) if selected_store_id is not None else ensure_default_store(db)
    if payload.category_id is not None:
        category = db.get(models.Category, payload.category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Категория не найдена")

    values = payload.model_dump(exclude={"store_id"})
    if user.role != "admin":
        values["quantity"] = 0
    product = models.Product(**values, store_id=store.id)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product

@app.get("/products", response_model=list[schemas.ProductOut])
def list_products(
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
):
    q = apply_store_scope(db.query(models.Product), models.Product, user, store_id)
    q = q.filter(models.Product.is_plan_fact.is_(True))
    q = q.filter(models.Product.name.in_(PLAN_FACT_NAMES))
    if search:
        q = q.filter(models.Product.name.ilike(f"%{search}%"))
    if category_id:
        q = q.filter(models.Product.category_id == category_id)
    return q.order_by(models.Product.id.desc()).all()


@app.get("/saleable-products", response_model=list[schemas.ProductOut])
def list_saleable_products(
    year: Optional[int] = Query(None, ge=2000, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
):
    q = db.query(models.Product).filter(models.Product.is_plan_fact.is_(True))
    q = q.filter(models.Product.name.in_(PLAN_FACT_NAMES))
    q = apply_store_scope(q, models.Product, user, store_id)
    return q.order_by(models.Product.parent_product_id, models.Product.id).all()


def require_sale_plan(db: Session, product: models.Product, user: CurrentUser, sale_date: datetime):
    if product.is_plan_fact:
        return
    zone = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Almaty"))
    local_sale_date = sale_date.astimezone(zone) if sale_date.tzinfo else sale_date
    plan_query = db.query(models.StaffProductMonthlyGoal.id).join(
        models.StaffAccount,
        models.StaffAccount.telegram_id == models.StaffProductMonthlyGoal.telegram_id,
    ).filter(
        models.StaffProductMonthlyGoal.product_id == product.id,
        models.StaffProductMonthlyGoal.year == local_sale_date.year,
        models.StaffProductMonthlyGoal.month == local_sale_date.month,
        models.StaffAccount.is_active.is_(True),
    )
    if user.role in {"specialist", "cashier"}:
        plan_query = plan_query.filter(
            models.StaffProductMonthlyGoal.telegram_id == user.telegram_id
        )
    if not plan_query.first():
        raise HTTPException(
            status_code=400,
            detail="Этот товар не включён в план-факт на месяц продажи",
        )


def require_sale_product(db: Session, product_id: int, sale_date: datetime, user: CurrentUser):
    product = require_product_access(db, product_id, user)
    assigned_store_id(user, product.store_id)
    require_sale_plan(db, product, user, sale_date)
    return product

@app.put("/products/{product_id}", response_model=schemas.ProductOut)
def update_product(
    product_id: int,
    payload: schemas.ProductUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("specialist", "lead")),
):
    product = require_product_access(db, product_id, user)

    data = payload.model_dump(exclude_unset=True)
    if user.role != "admin":
        data.pop("quantity", None)
    if "category_id" in data and data["category_id"] is not None:
        if not db.get(models.Category, data["category_id"]):
            raise HTTPException(status_code=404, detail="Категория не найдена")

    for key, value in data.items():
        setattr(product, key, value)

    db.commit()
    db.refresh(product)
    return product

@app.delete("/products/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("specialist", "lead")),
):
    product = require_product_access(db, product_id, user)
    if product.is_plan_fact:
        raise HTTPException(status_code=400, detail="Показатель план-факта нельзя удалить")

    sale_count = db.query(models.Sale).filter(models.Sale.product_id == product_id).count()
    if sale_count > 0:
        raise HTTPException(
            status_code=400,
            detail="Нельзя удалить товар, по которому уже есть продажи"
        )

    db.query(models.ProductMonthlyGoal).filter(
        models.ProductMonthlyGoal.product_id == product_id
    ).delete(synchronize_session=False)
    db.query(models.StaffProductMonthlyGoal).filter(
        models.StaffProductMonthlyGoal.product_id == product_id
    ).delete(synchronize_session=False)
    db.delete(product)
    db.commit()
    return {"ok": True}

@app.patch("/products/{product_id}/stock", response_model=schemas.ProductOut)
def change_stock(
    product_id: int,
    payload: schemas.StockChange,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("admin")),
):
    product = require_product_access(db, product_id, user)
    if product.is_plan_fact:
        raise HTTPException(status_code=400, detail="Для показателя план-факта складской остаток не ведётся")

    result = db.execute(
        update(models.Product)
        .where(
            models.Product.id == product_id,
            models.Product.quantity + payload.amount >= 0,
        )
        .values(quantity=models.Product.quantity + payload.amount)
    )
    if not result.rowcount:
        raise HTTPException(status_code=400, detail="Количество не может быть отрицательным")
    db.commit()
    db.refresh(product)
    return product

@app.post("/sales", response_model=schemas.SaleOut)
def create_sale(
    payload: schemas.SaleCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("specialist", "cashier", "lead")),
):
    if payload.product_id is None:
        raise HTTPException(status_code=400, detail="Продажа возможна только по товару из каталога")
    product = require_sale_product(db, payload.product_id, payload.sale_date, user)
    sale_store_id = product.store_id
    product_name = product.name
    sale_price = product.sale_price
    purchase_price = product.purchase_price

    if payload.total_amount is not None:
        total_decimal = Decimal(str(payload.total_amount)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        sale_price = total_decimal / payload.quantity
        profit_decimal = (
            total_decimal - Decimal(str(purchase_price)) * payload.quantity
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        total_decimal = (Decimal(str(sale_price)) * payload.quantity).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        profit_decimal = (
            (Decimal(str(sale_price)) - Decimal(str(purchase_price)))
            * payload.quantity
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = float(total_decimal)
    profit = float(profit_decimal)

    sale = models.Sale(
        store_id=sale_store_id,
        created_by_telegram_id=user.telegram_id,
        product_id=product.id if product else None,
        product_name=product_name,
        quantity=payload.quantity,
        unit_sale_price=float(sale_price),
        unit_purchase_price=purchase_price,
        total_amount=total,
        profit=profit,
        sale_date=payload.sale_date,
    )

    # Conditional SQL update makes stock validation and decrement atomic, including
    # when multiple sales arrive concurrently.
    if not product.is_plan_fact:
        result = db.execute(
            update(models.Product)
            .where(
                models.Product.id == product.id,
                models.Product.quantity >= payload.quantity,
            )
            .values(quantity=models.Product.quantity - payload.quantity)
        )
        if not result.rowcount:
            db.rollback()
            raise HTTPException(status_code=400, detail="Недостаточно товара на складе")
    db.add(sale)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(sale)
    return sale


@app.post("/sales/bulk", response_model=list[schemas.SaleOut])
def create_bulk_inventory_sale(
    payload: schemas.BulkInventorySaleCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("specialist", "cashier", "lead")),
):
    products = {}
    requested_quantities = {}
    for item in payload.items:
        requested_quantities[item.product_id] = (
            requested_quantities.get(item.product_id, 0) + item.quantity
        )

    for product_id in requested_quantities:
        product = require_sale_product(db, product_id, payload.sale_date, user)
        products[product_id] = product

    created_sales = []
    try:
        # Decrement each distinct product once. All lines are committed together;
        # a shortage on any item rolls back every stock change and sale row.
        for product_id, requested_quantity in requested_quantities.items():
            if products[product_id].is_plan_fact:
                continue
            result = db.execute(
                update(models.Product)
                .where(
                    models.Product.id == product_id,
                    models.Product.quantity >= requested_quantity,
                )
                .values(quantity=models.Product.quantity - requested_quantity)
            )
            if not result.rowcount:
                raise HTTPException(
                    status_code=400,
                    detail=f"Недостаточно товара на складе: {products[product_id].name}",
                )

        for item in payload.items:
            product = products[item.product_id]
            purchase_price = Decimal(str(product.purchase_price))
            if item.total_amount is not None:
                total_decimal = Decimal(str(item.total_amount)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                unit_sale_price = total_decimal / item.quantity
                profit_decimal = (
                    total_decimal - purchase_price * item.quantity
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                unit_sale_price = Decimal(str(product.sale_price))
                total_decimal = (unit_sale_price * item.quantity).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                profit_decimal = (
                    (unit_sale_price - purchase_price) * item.quantity
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            created_sales.append(
                models.Sale(
                    store_id=product.store_id,
                    created_by_telegram_id=user.telegram_id,
                    product_id=product.id,
                    product_name=product.name,
                    quantity=item.quantity,
                    unit_sale_price=float(unit_sale_price),
                    unit_purchase_price=product.purchase_price,
                    total_amount=float(total_decimal),
                    profit=float(profit_decimal),
                    sale_date=payload.sale_date,
                )
            )

        db.add_all(created_sales)
        db.commit()
        for sale in created_sales:
            db.refresh(sale)
    except Exception:
        db.rollback()
        raise

    return created_sales


@app.put("/sales/{sale_id}", response_model=schemas.SaleOut)
def update_sale(
    sale_id: int,
    payload: schemas.SaleUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("specialist", "cashier", "lead")),
):
    sale = require_sale_access(db, sale_id, user)

    data = payload.model_dump(exclude_unset=True)
    if "quantity" in data:
        quantity_delta = data["quantity"] - sale.quantity
        product = db.get(models.Product, sale.product_id) if sale.product_id is not None else None
        if quantity_delta and product is not None and not product.is_plan_fact:
            if quantity_delta > 0:
                result = db.execute(
                    update(models.Product)
                    .where(
                        models.Product.id == sale.product_id,
                        models.Product.quantity >= quantity_delta,
                    )
                    .values(quantity=models.Product.quantity - quantity_delta)
                )
                if not result.rowcount:
                    db.rollback()
                    raise HTTPException(
                        status_code=400,
                        detail="Недостаточно товара на складе для увеличения продажи",
                    )
            else:
                result = db.execute(
                    update(models.Product)
                    .where(models.Product.id == sale.product_id)
                    .values(quantity=models.Product.quantity - quantity_delta)
                )
                if not result.rowcount:
                    db.rollback()
                    raise HTTPException(status_code=404, detail="Товар не найден")
        sale.quantity = data["quantity"]

    if "product_name" in data:
        sale.product_name = data["product_name"]
    if "unit_sale_price" in data:
        sale.unit_sale_price = data["unit_sale_price"]
    if "sale_date" in data:
        sale.sale_date = data["sale_date"]

    sale.total_amount = float(
        (Decimal(str(sale.unit_sale_price)) * sale.quantity).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    )
    sale.profit = float(
        (
            (Decimal(str(sale.unit_sale_price)) - Decimal(str(sale.unit_purchase_price)))
            * sale.quantity
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )
    db.commit()
    db.refresh(sale)
    return sale


@app.delete("/sales/{sale_id}")
def delete_sale(
    sale_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("specialist", "cashier", "lead")),
):
    sale = require_sale_access(db, sale_id, user)

    product = db.get(models.Product, sale.product_id) if sale.product_id is not None else None
    if product is not None and not product.is_plan_fact:
        result = db.execute(
            update(models.Product)
            .where(models.Product.id == sale.product_id)
            .values(quantity=models.Product.quantity + sale.quantity)
        )
        if not result.rowcount:
            db.rollback()
            raise HTTPException(status_code=404, detail="Товар не найден")

    db.delete(sale)
    db.commit()
    return {"ok": True}

@app.get("/sales", response_model=list[schemas.SaleOut])
def list_sales(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
):
    q = apply_store_scope(db.query(models.Sale), models.Sale, user, store_id)
    if user.role in {"specialist", "cashier"}:
        q = q.filter(models.Sale.created_by_telegram_id == user.telegram_id)
    if start:
        q = q.filter(models.Sale.sale_date >= start)
    if end:
        q = q.filter(models.Sale.sale_date < end)
    rows = q.outerjoin(
        models.StaffAccount,
        models.StaffAccount.telegram_id == models.Sale.created_by_telegram_id,
    ).outerjoin(models.Store, models.Store.id == models.Sale.store_id).add_columns(
        models.StaffAccount.display_name, models.Store.name
    ).order_by(models.Sale.sale_date.desc()).all()
    return [
        {
            **schemas.SaleOut.model_validate(sale).model_dump(),
            "seller_name": seller_name or "Не указан",
            "store_name": store_name or "—",
        }
        for sale, seller_name, store_name in rows
    ]

@app.put("/goals", response_model=schemas.GoalOut)
def upsert_goal(
    payload: schemas.GoalCreate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("admin")),
):
    goal = db.query(models.MonthlyGoal).filter(
        models.MonthlyGoal.year == payload.year,
        models.MonthlyGoal.month == payload.month,
    ).first()

    if goal:
        goal.revenue_goal = payload.revenue_goal
        goal.quantity_goal = payload.quantity_goal
    else:
        goal = models.MonthlyGoal(**payload.model_dump())
        db.add(goal)

    db.commit()
    db.refresh(goal)
    return goal

@app.get("/goals/{year}/{month}")
def get_goal(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(current_user),
):
    if not 2000 <= year <= 2100 or not 1 <= month <= 12:
        raise HTTPException(status_code=422, detail="Некорректный год или месяц")
    goal = db.query(models.MonthlyGoal).filter(
        models.MonthlyGoal.year == year,
        models.MonthlyGoal.month == month,
    ).first()
    if not goal:
        return {
            "id": None,
            "year": year,
            "month": month,
            "revenue_goal": 0,
            "quantity_goal": 0
        }
    return {
        "id": goal.id,
        "year": goal.year,
        "month": goal.month,
        "revenue_goal": goal.revenue_goal,
        "quantity_goal": goal.quantity_goal
    }


def telegram_schedule_data(schedule):
    if schedule is None:
        return {
            "enabled": False,
            "send_time": "20:00",
            "timezone": "Asia/Almaty",
            "last_sent_on": None,
        }
    return {
        "enabled": schedule.enabled,
        "send_time": schedule.send_time,
        "timezone": schedule.timezone,
        "last_sent_on": schedule.last_sent_on,
    }


@app.get("/telegram/schedule", response_model=schemas.TelegramScheduleOut)
def get_telegram_schedule(
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("admin")),
):
    return telegram_schedule_data(db.get(models.TelegramSchedule, 1))


@app.put("/telegram/schedule", response_model=schemas.TelegramScheduleOut)
def update_telegram_schedule(
    payload: schemas.TelegramScheduleUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_telegram_admin),
    _user: CurrentUser = Depends(require_roles("admin")),
):
    try:
        ZoneInfo(payload.timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(status_code=422, detail="Неизвестный часовой пояс")
    if payload.enabled and (
        not os.getenv("TELEGRAM_BOT_TOKEN") or not os.getenv("TELEGRAM_CHAT_ID")
    ):
        raise HTTPException(
            status_code=503,
            detail="Сначала настройте TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID в Render",
        )

    schedule = db.get(models.TelegramSchedule, 1)
    if schedule is None:
        schedule = models.TelegramSchedule(id=1)
        db.add(schedule)
    schedule.enabled = payload.enabled
    schedule.send_time = payload.send_time
    schedule.timezone = payload.timezone
    db.commit()
    db.refresh(schedule)
    return telegram_schedule_data(schedule)


@app.post("/telegram/send-report")
def send_telegram_report(
    payload: schemas.TelegramReportRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_telegram_report_sender),
    _user: CurrentUser = Depends(require_roles("admin", "lead", "specialist", "cashier")),
):
    schedule = db.get(models.TelegramSchedule, 1)
    timezone_name = schedule.timezone if schedule else "Asia/Almaty"
    try:
        if _user.role in {"specialist", "cashier"}:
            zone = ZoneInfo(timezone_name)
            if payload.period == "month":
                start_local = datetime(payload.report_year, payload.report_month, 1, tzinfo=zone)
                end_local = (
                    datetime(payload.report_year + 1, 1, 1, tzinfo=zone)
                    if payload.report_month == 12
                    else datetime(payload.report_year, payload.report_month + 1, 1, tzinfo=zone)
                )
                title = f"Мои продажи за {payload.report_month:02d}.{payload.report_year}"
            else:
                start_local = datetime.combine(payload.report_date, datetime.min.time(), tzinfo=zone)
                end_local = start_local + timedelta(days=1)
                title = f"Мои продажи за {payload.report_date.strftime('%d.%m.%Y')}"
            start = start_local.astimezone(timezone.utc).replace(tzinfo=None)
            end = end_local.astimezone(timezone.utc).replace(tzinfo=None)
            report = build_personal_sales_report(db, start, end, title, _user.telegram_id)
        elif payload.period == "month":
            report = build_monthly_report(
                db, payload.report_year, payload.report_month, timezone_name, payload.store_id
            )
        else:
            report = build_daily_report(
                db, payload.report_date, timezone_name, payload.store_id
            )
        send_telegram_message(report)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=502, detail=str(error))
    return {"ok": True, "message": "Отчёт отправлен в Telegram"}


@app.get(
    "/product-goals/{year}/{month}",
    response_model=list[schemas.ProductGoalOut],
)
def list_product_goals(
    year: int,
    month: int,
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
):
    if not 2000 <= year <= 2100 or not 1 <= month <= 12:
        raise HTTPException(status_code=422, detail="Некорректный год или месяц")

    product_query = apply_store_scope(
        db.query(models.Product, models.ProductMonthlyGoal), models.Product, user, store_id
    )
    rows = product_query.outerjoin(
        models.ProductMonthlyGoal,
        (models.ProductMonthlyGoal.product_id == models.Product.id)
        & (models.ProductMonthlyGoal.year == year)
        & (models.ProductMonthlyGoal.month == month),
    ).order_by(models.Product.name).all()

    return [
        {
            "product_id": product.id,
            "product_name": product.name,
            "year": year,
            "month": month,
            "revenue_goal": goal.revenue_goal if goal else 0,
            "quantity_goal": goal.quantity_goal if goal else 0,
        }
        for product, goal in rows
    ]


@app.put("/product-goals", response_model=schemas.ProductGoalOut)
def upsert_product_goal(
    payload: schemas.ProductGoalCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("specialist")),
):
    product = require_product_access(db, payload.product_id, user)

    goal = db.query(models.ProductMonthlyGoal).filter_by(
        product_id=payload.product_id,
        year=payload.year,
        month=payload.month,
    ).first()
    if goal:
        goal.revenue_goal = payload.revenue_goal
        goal.quantity_goal = payload.quantity_goal
    else:
        goal = models.ProductMonthlyGoal(**payload.model_dump())
        db.add(goal)

    db.commit()
    db.refresh(goal)
    return {
        "product_id": product.id,
        "product_name": product.name,
        "year": goal.year,
        "month": goal.month,
        "revenue_goal": goal.revenue_goal,
        "quantity_goal": goal.quantity_goal,
    }


def staff_product_goal_data(goal, product):
    return {
        "telegram_id": goal.telegram_id,
        "product_id": product.id,
        "product_name": product.name,
        "year": goal.year,
        "month": goal.month,
        "revenue_goal": goal.revenue_goal,
        "quantity_goal": goal.quantity_goal,
    }


@app.get("/my-goals/{year}/{month}", response_model=list[schemas.StaffProductGoalOut])
def list_my_staff_goals(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("specialist", "cashier")),
):
    if not 2000 <= year <= 2100 or not 1 <= month <= 12:
        raise HTTPException(status_code=422, detail="Некорректный год или месяц")
    rows = db.query(models.StaffProductMonthlyGoal, models.Product).join(
        models.Product, models.Product.id == models.StaffProductMonthlyGoal.product_id
    ).filter(
        models.StaffProductMonthlyGoal.telegram_id == user.telegram_id,
        models.StaffProductMonthlyGoal.year == year,
        models.StaffProductMonthlyGoal.month == month,
    ).order_by(models.Product.name).all()
    return [staff_product_goal_data(goal, product) for goal, product in rows]


@app.get(
    "/team/staff-goals/{telegram_id}/{year}/{month}",
    response_model=list[schemas.StaffProductGoalOut],
)
def list_staff_goals(
    telegram_id: int,
    year: int,
    month: int,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("lead")),
):
    if not 2000 <= year <= 2100 or not 1 <= month <= 12:
        raise HTTPException(status_code=422, detail="Некорректный год или месяц")
    account = db.get(models.StaffAccount, telegram_id)
    if not account or account.role not in {"specialist", "cashier"}:
        raise HTTPException(status_code=404, detail="Специалист или кассир не найден")
    rows = db.query(models.StaffProductMonthlyGoal, models.Product).join(
        models.Product, models.Product.id == models.StaffProductMonthlyGoal.product_id
    ).filter(
        models.StaffProductMonthlyGoal.telegram_id == telegram_id,
        models.StaffProductMonthlyGoal.year == year,
        models.StaffProductMonthlyGoal.month == month,
    ).order_by(models.Product.name).all()
    return [staff_product_goal_data(goal, product) for goal, product in rows]


@app.put("/team/staff-goals", response_model=schemas.StaffProductGoalOut)
def upsert_staff_goal(
    payload: schemas.StaffProductGoalCreate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("lead")),
):
    account = db.get(models.StaffAccount, payload.telegram_id)
    if not account or account.role not in {"specialist", "cashier"} or not account.is_active:
        raise HTTPException(status_code=404, detail="Активный специалист или кассир не найден")
    product = db.get(models.Product, payload.product_id)
    if not product or product.store_id != account.store_id:
        raise HTTPException(status_code=404, detail="Товар не найден в лавочке сотрудника")
    goal = db.query(models.StaffProductMonthlyGoal).filter_by(
        telegram_id=payload.telegram_id,
        product_id=payload.product_id,
        year=payload.year,
        month=payload.month,
    ).first()
    if goal is None:
        goal = models.StaffProductMonthlyGoal(**payload.model_dump())
        db.add(goal)
    else:
        goal.revenue_goal = payload.revenue_goal
        goal.quantity_goal = payload.quantity_goal
    db.commit()
    db.refresh(goal)
    return staff_product_goal_data(goal, product)

@app.get("/dashboard")
def dashboard(
    year: Optional[int] = Query(None, ge=2000, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
):
    now = datetime.now()
    year = now.year if year is None else year
    month = now.month if month is None else month
    start, end = month_bounds(year, month)

    sales_query = apply_store_scope(db.query(models.Sale), models.Sale, user, store_id).filter(
        models.Sale.sale_date >= start,
        models.Sale.sale_date < end,
    )
    if user.role in {"specialist", "cashier"}:
        sales_query = sales_query.filter(models.Sale.created_by_telegram_id == user.telegram_id)
    sales = sales_query.all()

    profit = sum(s.profit for s in sales)
    sold_quantity = sum(s.quantity for s in sales)

    products = apply_store_scope(
        db.query(models.Product), models.Product, user, store_id
    ).order_by(models.Product.name).all()
    stock_qty = sum(product.quantity for product in products)

    planned_products_query = db.query(models.Product).filter(
        models.Product.is_plan_fact.is_(True),
        models.Product.name.in_(PLAN_FACT_NAMES),
    )
    planned_products = apply_store_scope(
        planned_products_query, models.Product, user, store_id
    ).distinct().order_by(models.Product.name).all()

    goal = db.query(models.MonthlyGoal).filter(
        models.MonthlyGoal.year == year,
        models.MonthlyGoal.month == month,
    ).first()

    revenue_goal = goal.revenue_goal if goal else 0
    quantity_goal = goal.quantity_goal if goal else 0
    quantity_progress = (sold_quantity / quantity_goal * 100) if quantity_goal > 0 else 0

    product_stats = {}
    for product in planned_products:
        key = ("plan_fact", product.name.casefold())
        product_stats.setdefault(key, {
            "product_id": product.id,
            "product_name": product.name,
            "sold_quantity": 0,
            "revenue": 0.0,
            "profit": 0.0,
            "stock_quantity": None,
        })

    for sale in sales:
        sale_name = sale.product_name.strip().casefold()
        key = ("plan_fact", sale_name)
        if key not in product_stats:
            continue
        stats = product_stats[key]
        is_service = sale_name in {"услуги", "услуга"}
        if not is_service:
            stats["sold_quantity"] += sale.quantity
        stats["revenue"] += sale.total_amount
        stats["profit"] += sale.profit
        if is_service:
            sa_stats = product_stats.get(("plan_fact", "sa"))
            if sa_stats is not None:
                sa_stats["revenue"] += sale.total_amount
                sa_stats["profit"] += sale.profit

    per_product = [
        {
            **stats,
            "revenue": round(stats["revenue"], 2),
            "profit": round(stats["profit"], 2),
        }
        for stats in sorted(
            product_stats.values(), key=lambda item: item["product_name"].casefold()
        )
    ]

    return {
        "year": year,
        "month": month,
        "profit": round(profit, 2),
        "sold_quantity": sold_quantity,
        "stock_quantity": int(stock_qty),
        "revenue_goal": revenue_goal,
        "quantity_goal": quantity_goal,
        "quantity_progress": round(quantity_progress, 1),
        "per_product": per_product,
    }

@app.get("/reports/monthly")
def monthly_report(
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
):
    report_query = apply_store_scope(db.query(models.Sale), models.Sale, user, store_id)
    if user.role in {"specialist", "cashier"}:
        report_query = report_query.filter(models.Sale.created_by_telegram_id == user.telegram_id)
    scoped_sale_ids = report_query.with_entities(models.Sale.id).subquery()
    rows = db.query(
        extract("year", models.Sale.sale_date).label("year"),
        extract("month", models.Sale.sale_date).label("month_number"),
        func.sum(models.Sale.profit).label("profit"),
        func.sum(models.Sale.quantity).label("quantity"),
    ).filter(models.Sale.id.in_(scoped_sale_ids)).group_by("year", "month_number").order_by("year", "month_number").all()

    return [
        {
            "month": f"{int(r.year):04d}-{int(r.month_number):02d}",
            "profit": round(r.profit or 0, 2),
            "quantity": int(r.quantity or 0),
        }
        for r in rows
    ]

@app.post("/seed")
def seed(db: Session = Depends(get_db)):
    if os.getenv("APP_ENV", "production").lower() == "production":
        raise HTTPException(status_code=404, detail="Not found")
    if db.query(models.Product).count() > 0:
        return {"message": "Тестовые данные уже есть"}

    store = ensure_default_store(db)
    cat1 = models.Category(name="Электроника")
    cat2 = models.Category(name="Аксессуары")
    db.add_all([cat1, cat2])
    db.flush()

    db.add_all([
        models.Product(
            store_id=store.id,
            name="Беспроводные наушники",
            category_id=cat1.id,
            purchase_price=1800,
            sale_price=2600,
            quantity=15,
            description="Bluetooth-наушники"
        ),
        models.Product(
            store_id=store.id,
            name="Power Bank 10000 mAh",
            category_id=cat1.id,
            purchase_price=1200,
            sale_price=1800,
            quantity=12,
            description="Внешний аккумулятор"
        ),
        models.Product(
            store_id=store.id,
            name="Чехол для телефона",
            category_id=cat2.id,
            purchase_price=250,
            sale_price=500,
            quantity=40,
            description="Универсальный чехол"
        ),
    ])
    db.commit()
    return {"message": "Тестовые данные добавлены"}
