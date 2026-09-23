import os
from decimal import Decimal, ROUND_HALF_UP

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import extract, func, update
from datetime import datetime
from typing import Optional

from .database import Base, engine, get_db
from . import models, schemas
from .migrations import migrate_sales_schema

migrate_sales_schema(engine)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Inventory & Sales API", version="1.0.0")

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

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

@app.get("/")
def root():
    return {"message": "Inventory API is running"}

@app.post("/categories", response_model=schemas.CategoryOut)
def create_category(payload: schemas.CategoryCreate, db: Session = Depends(get_db)):
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
def list_categories(db: Session = Depends(get_db)):
    return db.query(models.Category).order_by(models.Category.name).all()

@app.post("/products", response_model=schemas.ProductOut)
def create_product(payload: schemas.ProductCreate, db: Session = Depends(get_db)):
    if payload.category_id is not None:
        category = db.get(models.Category, payload.category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Категория не найдена")

    product = models.Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product

@app.get("/products", response_model=list[schemas.ProductOut])
def list_products(
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Product)
    if search:
        q = q.filter(models.Product.name.ilike(f"%{search}%"))
    if category_id:
        q = q.filter(models.Product.category_id == category_id)
    return q.order_by(models.Product.id.desc()).all()

@app.put("/products/{product_id}", response_model=schemas.ProductOut)
def update_product(product_id: int, payload: schemas.ProductUpdate, db: Session = Depends(get_db)):
    product = db.get(models.Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    data = payload.model_dump(exclude_unset=True)
    if "category_id" in data and data["category_id"] is not None:
        if not db.get(models.Category, data["category_id"]):
            raise HTTPException(status_code=404, detail="Категория не найдена")

    for key, value in data.items():
        setattr(product, key, value)

    db.commit()
    db.refresh(product)
    return product

@app.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(models.Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    sale_count = db.query(models.Sale).filter(models.Sale.product_id == product_id).count()
    if sale_count > 0:
        raise HTTPException(
            status_code=400,
            detail="Нельзя удалить товар, по которому уже есть продажи"
        )

    db.delete(product)
    db.commit()
    return {"ok": True}

@app.patch("/products/{product_id}/stock", response_model=schemas.ProductOut)
def change_stock(product_id: int, payload: schemas.StockChange, db: Session = Depends(get_db)):
    product = db.get(models.Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

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
def create_sale(payload: schemas.SaleCreate, db: Session = Depends(get_db)):
    product = None
    if payload.product_id is not None:
        product = db.get(models.Product, payload.product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Товар не найден")
        product_name = product.name
        sale_price = product.sale_price
        purchase_price = product.purchase_price
    else:
        product_name = payload.product_name.strip()
        sale_price = payload.unit_sale_price
        purchase_price = 0

    total = float(
        (Decimal(str(sale_price)) * payload.quantity).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    )
    profit = float(
        (
            (Decimal(str(sale_price)) - Decimal(str(purchase_price)))
            * payload.quantity
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )

    sale = models.Sale(
        product_id=product.id if product else None,
        product_name=product_name,
        quantity=payload.quantity,
        unit_sale_price=sale_price,
        unit_purchase_price=purchase_price,
        total_amount=total,
        profit=profit,
        sale_date=payload.sale_date,
    )

    if product:
        # Conditional SQL update makes stock validation and decrement atomic, including
        # when multiple sales arrive concurrently.
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

@app.get("/sales", response_model=list[schemas.SaleOut])
def list_sales(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Sale)
    if start:
        q = q.filter(models.Sale.sale_date >= start)
    if end:
        q = q.filter(models.Sale.sale_date < end)
    return q.order_by(models.Sale.sale_date.desc()).all()

@app.put("/goals", response_model=schemas.GoalOut)
def upsert_goal(payload: schemas.GoalCreate, db: Session = Depends(get_db)):
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
def get_goal(year: int, month: int, db: Session = Depends(get_db)):
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

@app.get("/dashboard")
def dashboard(
    year: Optional[int] = Query(None, ge=2000, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    db: Session = Depends(get_db),
):
    now = datetime.now()
    year = now.year if year is None else year
    month = now.month if month is None else month
    start, end = month_bounds(year, month)

    sales = db.query(models.Sale).filter(
        models.Sale.sale_date >= start,
        models.Sale.sale_date < end,
    ).all()

    revenue = sum(s.total_amount for s in sales)
    profit = sum(s.profit for s in sales)
    sold_quantity = sum(s.quantity for s in sales)

    products = db.query(models.Product).order_by(models.Product.name).all()
    stock_qty = sum(product.quantity for product in products)
    stock_value = db.query(
        func.coalesce(func.sum(models.Product.purchase_price * models.Product.quantity), 0)
    ).scalar() or 0

    goal = db.query(models.MonthlyGoal).filter(
        models.MonthlyGoal.year == year,
        models.MonthlyGoal.month == month,
    ).first()

    revenue_goal = goal.revenue_goal if goal else 0
    quantity_goal = goal.quantity_goal if goal else 0
    revenue_progress = (revenue / revenue_goal * 100) if revenue_goal > 0 else 0
    quantity_progress = (sold_quantity / quantity_goal * 100) if quantity_goal > 0 else 0

    per_day = {}
    for s in sales:
        key = s.sale_date.strftime("%Y-%m-%d")
        per_day[key] = per_day.get(key, 0) + s.total_amount

    daily_series = [
        {"date": k, "revenue": round(v, 2)}
        for k, v in sorted(per_day.items())
    ]

    product_stats = {}
    for product in products:
        product_stats[("catalog", product.id)] = {
            "product_id": product.id,
            "product_name": product.name,
            "sold_quantity": 0,
            "revenue": 0.0,
            "profit": 0.0,
            "stock_quantity": product.quantity,
        }

    for sale in sales:
        if sale.product_id is not None:
            key = ("catalog", sale.product_id)
            if key not in product_stats:
                product_stats[key] = {
                    "product_id": sale.product_id,
                    "product_name": sale.product_name,
                    "sold_quantity": 0,
                    "revenue": 0.0,
                    "profit": 0.0,
                    "stock_quantity": 0,
                }
        else:
            key = ("manual", sale.product_name)
            if key not in product_stats:
                product_stats[key] = {
                    "product_id": None,
                    "product_name": sale.product_name,
                    "sold_quantity": 0,
                    "revenue": 0.0,
                    "profit": 0.0,
                    "stock_quantity": None,
                }
        stats = product_stats[key]
        stats["sold_quantity"] += sale.quantity
        stats["revenue"] += sale.total_amount
        stats["profit"] += sale.profit

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
        "revenue": round(revenue, 2),
        "profit": round(profit, 2),
        "sold_quantity": sold_quantity,
        "stock_quantity": int(stock_qty),
        "stock_value": round(float(stock_value), 2),
        "revenue_goal": revenue_goal,
        "quantity_goal": quantity_goal,
        "revenue_progress": round(revenue_progress, 1),
        "quantity_progress": round(quantity_progress, 1),
        "remaining_revenue": round(max(revenue_goal - revenue, 0), 2),
        "daily_series": daily_series,
        "per_product": per_product,
    }

@app.get("/reports/monthly")
def monthly_report(db: Session = Depends(get_db)):
    rows = db.query(
        extract("year", models.Sale.sale_date).label("year"),
        extract("month", models.Sale.sale_date).label("month_number"),
        func.sum(models.Sale.total_amount).label("revenue"),
        func.sum(models.Sale.profit).label("profit"),
        func.sum(models.Sale.quantity).label("quantity"),
    ).group_by("year", "month_number").order_by("year", "month_number").all()

    return [
        {
            "month": f"{int(r.year):04d}-{int(r.month_number):02d}",
            "revenue": round(r.revenue or 0, 2),
            "profit": round(r.profit or 0, 2),
            "quantity": int(r.quantity or 0),
        }
        for r in rows
    ]

@app.post("/seed")
def seed(db: Session = Depends(get_db)):
    if os.getenv("APP_ENV", "development").lower() == "production":
        raise HTTPException(status_code=404, detail="Not found")
    if db.query(models.Product).count() > 0:
        return {"message": "Тестовые данные уже есть"}

    cat1 = models.Category(name="Электроника")
    cat2 = models.Category(name="Аксессуары")
    db.add_all([cat1, cat2])
    db.flush()

    db.add_all([
        models.Product(
            name="Беспроводные наушники",
            category_id=cat1.id,
            purchase_price=1800,
            sale_price=2600,
            quantity=15,
            description="Bluetooth-наушники"
        ),
        models.Product(
            name="Power Bank 10000 mAh",
            category_id=cat1.id,
            purchase_price=1200,
            sale_price=1800,
            quantity=12,
            description="Внешний аккумулятор"
        ),
        models.Product(
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
