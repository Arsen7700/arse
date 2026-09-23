from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint, Boolean, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)

    products = relationship("Product", back_populates="category")

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    purchase_price = Column(Float, nullable=False, default=0)
    sale_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False, default=0)
    description = Column(String(1000), nullable=True)
    image_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("Category", back_populates="products")
    sales = relationship("Sale", back_populates="product")

class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
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


class TelegramSchedule(Base):
    __tablename__ = "telegram_schedule"

    id = Column(Integer, primary_key=True)
    enabled = Column(Boolean, nullable=False, default=False)
    send_time = Column(String(5), nullable=False, default="20:00")
    timezone = Column(String(64), nullable=False, default="Asia/Almaty")
    last_sent_on = Column(Date, nullable=True)
