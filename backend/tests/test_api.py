from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


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
    assert dashboard.json()["revenue"] == 50
    assert dashboard.json()["profit"] == 30
    report = client.get("/reports/monthly")
    assert report.status_code == 200
    assert report.json()[0]["month"] == now.strftime("%Y-%m")
