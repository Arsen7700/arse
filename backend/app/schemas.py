from pydantic import BaseModel, Field, model_validator
from datetime import datetime, date
from typing import Optional, Literal


class StoreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class StoreOut(StoreCreate):
    id: int
    is_active: bool
    model_config = {"from_attributes": True}


class StoreUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    is_active: Optional[bool] = None


class StaffAccountCreate(BaseModel):
    telegram_id: int = Field(gt=0)
    display_name: str = Field(min_length=1, max_length=200)
    role: Literal["specialist", "cashier", "lead", "admin"] = "specialist"
    store_id: Optional[int] = None
    is_active: bool = True


class StaffAccountUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    role: Optional[Literal["specialist", "cashier", "lead", "admin"]] = None
    store_id: Optional[int] = None
    is_active: Optional[bool] = None


class StaffAccountOut(BaseModel):
    telegram_id: int
    display_name: str
    role: str
    store_id: Optional[int]
    store_name: Optional[str] = None
    is_active: bool


class TeamStaffRoleUpdate(BaseModel):
    role: Literal["specialist", "cashier"]
    store_id: int = Field(gt=0)


class TeamStaffCreate(BaseModel):
    telegram_id: int = Field(gt=0)
    display_name: str = Field(min_length=1, max_length=200)
    role: Literal["specialist", "cashier"]
    store_id: int = Field(gt=0)


class DailyReportSettingsUpdate(BaseModel):
    model_config = {"str_strip_whitespace": True}
    report_date: date
    store_id: Optional[int] = None
    cash_limit: str = Field(min_length=1, max_length=100)
    cash_remaining: str = Field(min_length=1, max_length=100)
    collection_status: str = Field(min_length=1, max_length=100)


class DailyReportSettingsOut(BaseModel):
    report_date: date
    store_id: int
    cash_limit: str
    cash_remaining: str
    collection_status: str

class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

class CategoryOut(CategoryCreate):
    id: int
    model_config = {"from_attributes": True}

class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category_id: Optional[int] = None
    purchase_price: float = Field(default=0, ge=0)
    sale_price: float = Field(ge=0)
    quantity: int = Field(ge=0)
    description: Optional[str] = None
    image_url: Optional[str] = None
    store_id: Optional[int] = None

class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    category_id: Optional[int] = None
    purchase_price: Optional[float] = Field(default=None, ge=0)
    sale_price: Optional[float] = Field(default=None, ge=0)
    quantity: Optional[int] = Field(default=None, ge=0)
    description: Optional[str] = None
    image_url: Optional[str] = None

class ProductOut(BaseModel):
    id: int
    store_id: int
    name: str
    category_id: Optional[int]
    purchase_price: float
    sale_price: float
    quantity: int
    description: Optional[str]
    image_url: Optional[str]
    is_plan_fact: bool = False
    parent_product_id: Optional[int] = None
    created_at: datetime
    model_config = {"from_attributes": True}

class StockChange(BaseModel):
    amount: int

class SaleCreate(BaseModel):
    product_id: Optional[int] = None
    store_id: Optional[int] = None
    product_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    unit_sale_price: Optional[float] = Field(default=None, ge=0)
    total_amount: Optional[float] = Field(default=None, ge=0)
    quantity: int = Field(gt=0)
    sale_date: datetime

    @model_validator(mode="after")
    def validate_sale_source(self):
        if self.product_id is None:
            if not self.product_name or not self.product_name.strip() or self.unit_sale_price is None:
                raise ValueError(
                    "Для продажи без товара укажите название и цену продажи"
                )
            self.product_name = self.product_name.strip()
        return self


class InventorySaleLineCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0)
    total_amount: Optional[float] = Field(default=None, ge=0)


class BulkInventorySaleCreate(BaseModel):
    items: list[InventorySaleLineCreate] = Field(min_length=1, max_length=100)
    sale_date: datetime


class SaleUpdate(BaseModel):
    product_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    quantity: Optional[int] = Field(default=None, gt=0)
    unit_sale_price: Optional[float] = Field(default=None, ge=0)
    sale_date: Optional[datetime] = None

    @model_validator(mode="after")
    def clean_product_name(self):
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"Поле {field_name} не может быть пустым")
        if self.product_name is not None:
            if not self.product_name.strip():
                raise ValueError("Укажите название товара")
            self.product_name = self.product_name.strip()
        return self

class SaleOut(BaseModel):
    id: int
    store_id: int
    created_by_telegram_id: Optional[int]
    store_name: Optional[str] = None
    seller_name: Optional[str] = None
    product_id: Optional[int]
    product_name: str
    quantity: int
    unit_sale_price: float
    unit_purchase_price: float
    total_amount: float
    profit: float
    sale_date: datetime
    model_config = {"from_attributes": True}

class GoalCreate(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    revenue_goal: float = Field(ge=0)
    quantity_goal: int = Field(ge=0)

class GoalOut(GoalCreate):
    id: int
    model_config = {"from_attributes": True}


class ProductGoalCreate(BaseModel):
    product_id: int = Field(gt=0)
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    revenue_goal: float = Field(ge=0)
    quantity_goal: int = Field(ge=0)


class ProductGoalOut(BaseModel):
    product_id: int
    product_name: str
    year: int
    month: int
    revenue_goal: float
    quantity_goal: int


class StaffProductGoalCreate(BaseModel):
    telegram_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    revenue_goal: float = Field(ge=0)
    quantity_goal: int = Field(ge=0)


class StaffProductGoalOut(BaseModel):
    telegram_id: int
    product_id: int
    product_name: str
    year: int
    month: int
    revenue_goal: float
    quantity_goal: int


class TelegramScheduleUpdate(BaseModel):
    enabled: bool
    send_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(min_length=1, max_length=64)


class TelegramScheduleOut(TelegramScheduleUpdate):
    last_sent_on: Optional[date] = None


class TelegramReportRequest(BaseModel):
    period: Literal["day", "month"] = "day"
    report_date: Optional[date] = None
    store_id: Optional[int] = Field(default=None, gt=0)
    report_year: Optional[int] = Field(default=None, ge=2000, le=2100)
    report_month: Optional[int] = Field(default=None, ge=1, le=12)
    report_text: Optional[str] = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def validate_period_fields(self):
        if self.period == "day" and self.report_date is None:
            raise ValueError("Для дневного отчёта укажите report_date")
        if self.period == "month" and (
            self.report_year is None or self.report_month is None
        ):
            raise ValueError("Для месячного отчёта укажите report_year и report_month")
        return self
