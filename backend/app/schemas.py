from pydantic import BaseModel, Field, model_validator
from datetime import datetime
from typing import Optional

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
    name: str
    category_id: Optional[int]
    purchase_price: float
    sale_price: float
    quantity: int
    description: Optional[str]
    image_url: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}

class StockChange(BaseModel):
    amount: int

class SaleCreate(BaseModel):
    product_id: Optional[int] = None
    product_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    unit_sale_price: Optional[float] = Field(default=None, ge=0)
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
