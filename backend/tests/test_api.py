from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
import app.main as main_module


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def create_product(client, *, quantity=5, purchase_price=10, sale_price=25):
    response = client.post(
        "/products",
        json={
            "name": "Тестовый товар",
            "purchase_price": purchase_price,
            "sale_price": sale_price,
            "quantity": quantity,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_product_can_be_created_without_purchase_price(client):
    response = client.post(
        "/products",
        json={"name": "Товар без закупочной цены", "sale_price": 20, "quantity": 3},
    )
    assert response.status_code == 200, response.text
    assert response.json()["purchase_price"] == 0


def test_product_crud_and_stock_validation(client):
    product = create_product(client)
    product_id = product["id"]

    updated = client.put(f"/products/{product_id}", json={"name": "Обновлённый"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Обновлённый"

    changed = client.patch(f"/products/{product_id}/stock", json={"amount": 2})
    assert changed.status_code == 200
    assert changed.json()["quantity"] == 7
    assert client.patch(f"/products/{product_id}/stock", json={"amount": -8}).status_code == 400

    assert client.delete(f"/products/{product_id}").status_code == 200
    assert client.get("/products").json() == []


def test_sale_decrements_stock_and_calculates_revenue_and_profit(client):
    product = create_product(client)
    response = client.post(
        "/sales",
        json={
            "product_id": product["id"],
            "quantity": 2,
            "sale_date": datetime.now().isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    sale = response.json()
    assert sale["total_amount"] == 50
    assert sale["profit"] == 30
    assert client.get("/products").json()[0]["quantity"] == 3
    assert client.delete(f"/products/{product['id']}").status_code == 400


def test_sale_cannot_exceed_stock(client):
    product = create_product(client, quantity=1)
    response = client.post(
        "/sales",
        json={
            "product_id": product["id"],
            "quantity": 2,
            "sale_date": datetime.now().isoformat(),
        },
    )
    assert response.status_code == 400
    assert client.get("/products").json()[0]["quantity"] == 1
    assert client.get("/sales").json() == []


def test_manual_sale_does_not_require_catalog_product_or_change_stock(client):
    create_product(client, quantity=5)
    response = client.post(
        "/sales",
        json={
            "product_name": "Разовая услуга",
            "unit_sale_price": 100,
            "quantity": 2,
            "sale_date": datetime.now().isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    sale = response.json()
    assert sale["product_id"] is None
    assert sale["product_name"] == "Разовая услуга"
    assert sale["total_amount"] == 200
    assert sale["profit"] == 200
    assert client.get("/products").json()[0]["quantity"] == 5


def test_manual_sale_requires_name_and_sale_price(client):
    response = client.post(
        "/sales",
        json={"quantity": 1, "sale_date": datetime.now().isoformat()},
    )
    assert response.status_code == 422


def test_manual_sale_can_be_edited_and_deleted(client):
    created = client.post(
        "/sales",
        json={
            "product_name": "Ручная продажа",
            "unit_sale_price": 100,
            "quantity": 2,
            "sale_date": datetime.now().isoformat(),
        },
    )
    assert created.status_code == 200, created.text
    sale_id = created.json()["id"]

    updated = client.put(
        f"/sales/{sale_id}",
        json={"product_name": "Исправленная продажа", "quantity": 3, "unit_sale_price": 50},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["product_name"] == "Исправленная продажа"
    assert updated.json()["total_amount"] == 150
    assert updated.json()["profit"] == 150

    assert client.delete(f"/sales/{sale_id}").status_code == 200
    assert client.get("/sales").json() == []


def test_catalog_sale_edit_adjusts_stock_and_delete_restores_it(client):
    product = create_product(client, quantity=5)
    created = client.post(
        "/sales",
        json={
            "product_id": product["id"],
            "quantity": 2,
            "sale_date": datetime.now().isoformat(),
        },
    )
    sale_id = created.json()["id"]
    assert client.get("/products").json()[0]["quantity"] == 3

    updated = client.put(f"/sales/{sale_id}", json={"quantity": 4})
    assert updated.status_code == 200, updated.text
    assert client.get("/products").json()[0]["quantity"] == 1

    rejected = client.put(f"/sales/{sale_id}", json={"quantity": 6})
    assert rejected.status_code == 400
    assert client.get("/sales").json()[0]["quantity"] == 4
    assert client.get("/products").json()[0]["quantity"] == 1

    assert client.delete(f"/sales/{sale_id}").status_code == 200
    assert client.get("/products").json()[0]["quantity"] == 5


def test_free_inventory_sale_decrements_stock_and_records_loss(client):
    product = create_product(client, quantity=2, purchase_price=10, sale_price=0)
    response = client.post(
        "/sales",
        json={
            "product_id": product["id"],
            "quantity": 1,
            "sale_date": datetime.now().isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    sale = response.json()
    assert sale["total_amount"] == 0
    assert sale["profit"] == -10
    assert client.get("/products").json()[0]["quantity"] == 1


def test_goal_upsert_dashboard_and_monthly_report(client):
    product = create_product(client)
    now = datetime.now()
    sale_response = client.post(
        "/sales",
        json={
            "product_id": product["id"],
            "quantity": 2,
            "sale_date": now.isoformat(),
        },
    )
    assert sale_response.status_code == 200

    goal = {"year": now.year, "month": now.month, "revenue_goal": 100, "quantity_goal": 5}
    assert client.put("/goals", json=goal).status_code == 200
    goal["revenue_goal"] = 200
    assert client.put("/goals", json=goal).status_code == 200
    assert client.get(f"/goals/{now.year}/{now.month}").json()["revenue_goal"] == 200

    dashboard = client.get("/dashboard", params={"year": now.year, "month": now.month})
    assert dashboard.status_code == 200
    assert "revenue" not in dashboard.json()
    assert "daily_series" not in dashboard.json()
    assert dashboard.json()["profit"] == 30
    assert "stock_value" not in dashboard.json()
    product_stats = dashboard.json()["per_product"]
    assert len(product_stats) == 1
    assert product_stats[0]["product_name"] == "Тестовый товар"
    assert product_stats[0]["sold_quantity"] == 2
    assert product_stats[0]["revenue"] == 50
    assert product_stats[0]["profit"] == 30
    assert product_stats[0]["stock_quantity"] == 3
    report = client.get("/reports/monthly")
    assert report.status_code == 200
    assert report.json()[0]["month"] == now.strftime("%Y-%m")
    assert "revenue" not in report.json()[0]


def test_product_goals_are_saved_separately_by_product_and_month(client):
    first_product = create_product(client)
    second_product = client.post(
        "/products",
        json={"name": "Другой товар", "sale_price": 30, "quantity": 4},
    ).json()
    year, month = 2026, 9

    saved = client.put(
        "/product-goals",
        json={
            "product_id": first_product["id"],
            "year": year,
            "month": month,
            "revenue_goal": 500,
            "quantity_goal": 10,
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["product_name"] == "Тестовый товар"

    goals = client.get(f"/product-goals/{year}/{month}").json()
    first_goal = next(row for row in goals if row["product_id"] == first_product["id"])
    second_goal = next(row for row in goals if row["product_id"] == second_product["id"])
    assert first_goal["revenue_goal"] == 500
    assert first_goal["quantity_goal"] == 10
    assert second_goal["revenue_goal"] == 0
    assert second_goal["quantity_goal"] == 0

    next_month = client.get(f"/product-goals/{year}/{month + 1}").json()
    assert next(row for row in next_month if row["product_id"] == first_product["id"])["revenue_goal"] == 0


def test_telegram_schedule_requires_admin_key(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_KEY", "test-admin-secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")
    payload = {
        "enabled": True,
        "send_time": "21:15",
        "timezone": "Asia/Almaty",
    }

    denied = client.put("/telegram/schedule", json=payload)
    assert denied.status_code == 403

    saved = client.put(
        "/telegram/schedule",
        json=payload,
        headers={"X-Telegram-Admin-Key": "test-admin-secret"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["enabled"] is True
    assert saved.json()["send_time"] == "21:15"
    assert saved.json()["timezone"] == "Asia/Almaty"

    loaded = client.get("/telegram/schedule")
    assert loaded.status_code == 200
    assert loaded.json()["send_time"] == "21:15"


def test_manual_telegram_report_uses_admin_key_and_sends_selected_date(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_KEY", "test-admin-secret")
    delivered = []
    monkeypatch.setattr(main_module, "build_daily_report", lambda db, day, zone: f"report {day} {zone}")
    monkeypatch.setattr(main_module, "send_telegram_message", delivered.append)

    denied = client.post("/telegram/send-report", json={"report_date": "2026-09-23"})
    assert denied.status_code == 403

    response = client.post(
        "/telegram/send-report",
        json={"report_date": "2026-09-23"},
        headers={"X-Telegram-Admin-Key": "test-admin-secret"},
    )
    assert response.status_code == 200, response.text
    assert delivered == ["report 2026-09-23 Asia/Almaty"]


def test_monthly_telegram_report_groups_sales_by_product(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_KEY", "test-admin-secret")
    product = create_product(client)
    created = client.post(
        "/sales",
        json={
            "product_id": product["id"],
            "quantity": 2,
            "sale_date": "2026-09-15T12:00:00",
        },
    )
    assert created.status_code == 200, created.text
    delivered = []
    monkeypatch.setattr(main_module, "send_telegram_message", delivered.append)

    response = client.post(
        "/telegram/send-report",
        json={"period": "month", "report_year": 2026, "report_month": 9},
        headers={"X-Telegram-Admin-Key": "test-admin-secret"},
    )

    assert response.status_code == 200, response.text
    assert "Отчёт о продажах за 09.2026" in delivered[0]
    assert "Тестовый товар — 2 шт." in delivered[0]
    assert "сумма 50.00 сом" in delivered[0]
    assert "Общая выручка" not in delivered[0]


def test_monthly_telegram_report_requires_valid_year_and_month(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_KEY", "test-admin-secret")
    response = client.post(
        "/telegram/send-report",
        json={"period": "month", "report_year": 2026},
        headers={"X-Telegram-Admin-Key": "test-admin-secret"},
    )
    assert response.status_code == 422
