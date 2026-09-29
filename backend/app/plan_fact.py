"""Canonical non-stock plan-fact items shown in the sales workflow."""

PLAN_FACT_ITEMS = (
    {"name": "SA", "parent": None, "metric": "quantity", "quantity_goal": 30, "revenue_goal": 0},
    {"name": "Мой", "parent": "SA", "metric": "quantity", "quantity_goal": 25, "revenue_goal": 0},
    {"name": "Услуги", "parent": "SA", "metric": "revenue", "quantity_goal": 0, "revenue_goal": 15000},
    {"name": "Карты", "parent": None, "metric": "quantity", "quantity_goal": 25, "revenue_goal": 0},
    {"name": "Устройства", "parent": None, "metric": "quantity", "quantity_goal": 2, "revenue_goal": 0},
    {"name": "Saima", "parent": None, "metric": "quantity", "quantity_goal": 1, "revenue_goal": 0},
    {"name": "Телефоны", "parent": None, "metric": "quantity", "quantity_goal": 2, "revenue_goal": 0},
    {"name": "Аксессуары", "parent": None, "metric": "revenue", "quantity_goal": 0, "revenue_goal": 3100},
    {"name": "Вместе дешевле", "parent": None, "metric": "quantity", "quantity_goal": 0, "revenue_goal": 0},
    {"name": "O!семья", "parent": None, "metric": "quantity", "quantity_goal": 0, "revenue_goal": 0},
)

PLAN_FACT_NAMES = {item["name"] for item in PLAN_FACT_ITEMS}
PLAN_FACT_GOALS = {item["name"]: item for item in PLAN_FACT_ITEMS}
