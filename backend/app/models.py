from sqlalchemy import Column, Integer, BigInteger, String, Float, DateTime, ForeignKey, UniqueConstraint, Boolean, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StaffAccount(Base):
    __tablename__ = "staff_accounts"

    telegram_id = Column(BigInteger, primary_key=True)
    display_name = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default="specialist")
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class DailyReportSettings(Base):
    __tablename__ = "daily_report_settings"
    __table_args__ = (UniqueConstraint("store_id", "report_date", name="uq_report_settings_store_date"),)

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)
    report_date = Column(Date, nullable=False, index=True)
    cash_limit = Column(String(100), nullable=False, default="60к")
    cash_remaining = Column(String(100), nullable=False, default="80к")
    collection_status = Column(String(100), nullable=False, default="нет")

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)

    products = relationship("Product", back_populates="category")

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    purchase_price = Column(Float, nullable=False, default=0)
    sale_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False, default=0)
    description = Column(String(1000), nullable=True)
    image_url = Column(String(500), nullable=True)
    is_plan_fact = Column(Boolean, nullable=False, default=False, index=True)
    parent_product_id = Column(Integer, ForeignKey("products.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("Category", back_populates="products")
    sales = relationship("Sale", back_populates="product")
    parent_product = relationship("Product", remote_side=[id], backref="child_products")

class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)
    created_by_telegram_id = Column(BigInteger, nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    product_name = Column(String(200), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_sale_price = Column(Float, nullable=False)
    unit_purchase_price = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    profit = Column(Float, nullable=False)
    sale_date = Column(DateTime, nullable=False, default=datetime.utcnow)

    product = relationship("Product", back_populates="sales")

class MonthlyGoal(Base):
    __tablename__ = "monthly_goals"
    __table_args__ = (
        UniqueConstraint("year", "month", name="uq_goal_year_month"),
    )

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    revenue_goal = Column(Float, nullable=False, default=0)
    quantity_goal = Column(Integer, nullable=False, default=0)


class ProductMonthlyGoal(Base):
    __tablename__ = "product_monthly_goals"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "year", "month", name="uq_product_goal_month"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    revenue_goal = Column(Float, nullable=False, default=0)
    quantity_goal = Column(Integer, nullable=False, default=0)


class StaffProductMonthlyGoal(Base):
    __tablename__ = "staff_product_monthly_goals"
    __table_args__ = (
        UniqueConstraint(
            "telegram_id", "product_id", "year", "month",
            name="uq_staff_product_goal_month",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, ForeignKey("staff_accounts.telegram_id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    revenue_goal = Column(Float, nullable=False, default=0)
    quantity_goal = Column(Integer, nullable=False, default=0)


class TelegramSchedule(Base):
    __tablename__ = "telegram_schedule"

    id = Column(Integer, primary_key=True)
    enabled = Column(Boolean, nullable=False, default=False)
    send_time = Column(String(5), nullable=False, default="20:00")
    timezone = Column(String(64), nullable=False, default="Asia/Almaty")
    last_sent_on = Column(Date, nullable=True)


class SavedReportText(Base):
    __tablename__ = "saved_report_texts"

    id = Column(Integer, primary_key=True, index=True)
    report_key = Column(String(120), nullable=False, unique=True, index=True)
    report_text = Column(String(4096), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
