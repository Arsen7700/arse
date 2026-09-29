from datetime import datetime
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.access import CurrentUser, current_user
from app.main import app
import app.main as main_module


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(main_module, "SessionLocal", TestingSession)
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


def signed_telegram_init_data(bot_token, user_id):
    fields = {
        "auth_date": str(int(time.time())),
        "query_id": "test-query",
        "user": json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":")),
    }
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_production_api_requires_valid_allowed_telegram_user(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot-token")
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", "")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "12345")

    missing = client.get(
        "/products", headers={"Origin": "http://localhost:5173"}
    )
    assert missing.status_code == 401
    assert missing.headers["access-control-allow-origin"] == "http://localhost:5173"

    unauthorized_user = client.get(
        "/products",
        headers={"X-Telegram-Init-Data": signed_telegram_init_data("test-bot-token", 67890)},
    )
    assert unauthorized_user.status_code == 403

    authorized_user = client.get(
        "/products",
        headers={"X-Telegram-Init-Data": signed_telegram_init_data("test-bot-token", 12345)},
    )
    assert authorized_user.status_code == 200, authorized_user.text


def test_production_admin_can_invite_telegram_specialist(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot-token")
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", "50001")
    admin_headers = {
        "X-Telegram-Init-Data": signed_telegram_init_data("test-bot-token", 50001)
    }
    store = client.post("/admin/stores", json={"name": "Тестовая лавочка"}, headers=admin_headers)
    assert store.status_code == 200, store.text
    store_id = store.json()["id"]
    added = client.post(
        "/admin/users",
        json={
            "telegram_id": 50002,
            "display_name": "Специалист",
            "role": "specialist",
            "store_id": store_id,
        },
        headers=admin_headers,
    )
    assert added.status_code == 200, added.text
    specialist_headers = {
        "X-Telegram-Init-Data": signed_telegram_init_data("test-bot-token", 50002)
    }
    assert client.get("/auth/me", headers=specialist_headers).json()["role"] == "specialist"
    created = client.post(
        "/products",
        json={"name": "Товар специалиста", "sale_price": 50, "quantity": 20},
        headers=specialist_headers,
    )
    assert created.status_code == 403
    admin_created = client.post(
        "/products",
        json={"name": "Товар администратора", "sale_price": 50, "quantity": 20, "store_id": store_id},
        headers=admin_headers,
    )
    assert admin_created.status_code == 200, admin_created.text
    assert client.patch(
        f"/products/{admin_created.json()['id']}/stock",
        json={"amount": 3},
        headers=specialist_headers,
    ).status_code == 403
    uninvited_headers = {
        "X-Telegram-Init-Data": signed_telegram_init_data("test-bot-token", 50003)
    }
    assert client.get("/products", headers=uninvited_headers).status_code == 403


def assign_product_plan(client, product, *, telegram_id=None, year=None, month=None):
    if telegram_id is None:
        telegram_id = 8_100_000 + product["id"]
        created = client.post(
            "/team/staff",
            json={
                "telegram_id": telegram_id,
                "display_name": f"Планировщик {telegram_id}",
                "role": "specialist",
                "store_id": product["store_id"],
            },
        )
        assert created.status_code == 200, created.text
    now = datetime.now()
    response = client.put(
        "/team/staff-goals",
        json={
            "telegram_id": telegram_id,
            "product_id": product["id"],
            "year": year or now.year,
            "month": month or now.month,
            "revenue_goal": 1000,
            "quantity_goal": 10,
        },
    )
    assert response.status_code == 200, response.text


def create_product(client, *, quantity=5, purchase_price=10, sale_price=25, name="Тестовый товар", store_id=None, plan=True):
    response = client.post(
        "/products",
        json={
            "name": name,
            "purchase_price": purchase_price,
            "sale_price": sale_price,
            "quantity": quantity,
            "store_id": store_id,
        },
    )
    assert response.status_code == 200, response.text
    product = response.json()
    if plan:
        assign_product_plan(client, product)
    return product


def test_shop_scoping_specialist_permissions_and_lead_reports(client):
    first_product = create_product(client, plan=False)
    first_store_id = first_product["store_id"]
    second_store = client.post("/admin/stores", json={"name": "Вторая лавочка"})
    assert second_store.status_code == 200, second_store.text
    second_store_id = second_store.json()["id"]
    second_product_response = client.post(
        "/products",
        json={
            "name": "Товар второй лавочки",
            "sale_price": 40,
            "quantity": 6,
            "store_id": second_store_id,
        },
    )
    assert second_product_response.status_code == 200, second_product_response.text
    second_product = second_product_response.json()
    for telegram_id, store_id in ((10101, first_store_id), (20202, first_store_id), (30303, second_store_id)):
        created_account = client.post(
            "/admin/users",
            json={
                "telegram_id": telegram_id,
                "display_name": f"Сотрудник {telegram_id}",
                "role": "specialist",
                "store_id": store_id,
            },
        )
        assert created_account.status_code == 200, created_account.text
    assign_product_plan(client, first_product, telegram_id=10101)
    assign_product_plan(client, second_product, telegram_id=30303)

    def use_user(user_id, role, store_id=None):
        app.dependency_overrides[current_user] = lambda: CurrentUser(
            user_id, f"Сотрудник {user_id}", role, store_id
        )

    try:
        use_user(10101, "specialist", first_store_id)
        own_product = client.post(
            "/products",
            json={"name": "Новый товар", "sale_price": 12, "quantity": 99},
        )
        assert own_product.status_code == 403

        outsider = client.get("/products", params={"store_id": second_store_id})
        assert outsider.status_code == 403
        assert client.get("/products").json()

        sale = client.post(
            "/sales",
            json={
                "product_id": first_product["id"],
                "quantity": 1,
                "sale_date": datetime.now().isoformat(),
            },
        )
        assert sale.status_code == 200, sale.text
        sale_id = sale.json()["id"]
        assert sale.json()["created_by_telegram_id"] == 10101
        assert client.patch(
            f"/products/{first_product['id']}/stock", json={"amount": 1}
        ).status_code == 403

        use_user(20202, "specialist", first_store_id)
        assert client.get("/sales").json() == []
        assert client.put(
            f"/sales/{sale_id}", json={"quantity": 2}
        ).status_code == 403

        use_user(30303, "specialist", second_store_id)
        second_sale = client.post(
            "/sales",
            json={
                "product_id": second_product["id"],
                "quantity": 2,
                "sale_date": datetime.now().isoformat(),
            },
        )
        assert second_sale.status_code == 200, second_sale.text

        use_user(40404, "lead")
        lead_product = client.post(
            "/products",
            json={"name": "Товар ведущего", "sale_price": 20, "quantity": 8, "store_id": first_store_id},
        )
        assert lead_product.status_code == 200, lead_product.text
        assert lead_product.json()["quantity"] == 0
        report = client.get("/reports/staff")
        assert report.status_code == 200, report.text
        assert len(report.json()) == 3
        assert sum(row["sold_quantity"] for row in report.json()) == 3
        second_specialist = next(row for row in report.json() if row["telegram_id"] == 30303)
        assert second_specialist["products"][0]["product_name"] == "Товар второй лавочки"
        assert second_specialist["products"][0]["sold_quantity"] == 2
        assert len(client.get("/products").json()) == 3
        lead_sale = client.post(
            "/sales",
            json={"product_id": first_product["id"], "quantity": 1, "sale_date": datetime.now().isoformat()},
        )
        assert lead_sale.status_code == 200, lead_sale.text
        assert client.put(
            f"/products/{first_product['id']}", json={"name": "Товар изменён ведущим"}
        ).status_code == 200
        assert client.put(
            f"/sales/{lead_sale.json()['id']}", json={"quantity": 2}
        ).status_code == 200
        assert client.delete(f"/sales/{lead_sale.json()['id']}").status_code == 200
        assert client.get("/admin/users").status_code == 403
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_admin_can_manage_stores_and_telegram_accounts(client):
    store = client.post("/admin/stores", json={"name": "Центр"})
    assert store.status_code == 200, store.text
    store_id = store.json()["id"]
    account = client.post(
        "/admin/users",
        json={
            "telegram_id": 50505,
            "display_name": "Новый специалист",
            "role": "specialist",
            "store_id": store_id,
        },
    )
    assert account.status_code == 200, account.text
    assert account.json()["store_name"] == "Центр"
    assert client.post(
        "/admin/users",
        json={
            "telegram_id": 50505,
            "display_name": "Дубликат",
            "role": "specialist",
            "store_id": store_id,
        },
    ).status_code == 409
    updated = client.put(
        "/admin/users/50505", json={"is_active": False}
    )
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False


def test_lead_can_assign_specialist_and_cashier_roles(client):
    store = client.post("/admin/stores", json={"name": "Лавочка для ролей"}).json()
    account = client.post(
        "/admin/users",
        json={
            "telegram_id": 61616,
            "display_name": "Кассовый сотрудник",
            "role": "specialist",
            "store_id": store["id"],
        },
    )
    assert account.status_code == 200, account.text
    app.dependency_overrides[current_user] = lambda: CurrentUser(71717, "Ведущий", "lead")
    try:
        assert client.get("/team/staff").status_code == 200
        added_cashier = client.post(
            "/team/staff",
            json={
                "telegram_id": 62626,
                "display_name": "Новый кассир",
                "role": "cashier",
                "store_id": store["id"],
            },
        )
        assert added_cashier.status_code == 200, added_cashier.text
        assert added_cashier.json()["role"] == "cashier"
        changed = client.put(
            "/team/staff/61616",
            json={"role": "cashier", "store_id": store["id"]},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["role"] == "cashier"
        assert client.get("/admin/users").status_code == 403
        assert client.put(
            "/team/staff/61616", json={"role": "admin", "store_id": store["id"]}
        ).status_code == 422
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_cashier_can_register_and_edit_only_own_store_sales(client):
    store = client.post("/admin/stores", json={"name": "Кассовая лавочка"}).json()
    account = client.post(
        "/team/staff",
        json={"telegram_id": 81818, "display_name": "Кассир", "role": "cashier", "store_id": store["id"]},
    )
    assert account.status_code == 200, account.text
    product = client.post(
        "/products",
        json={"name": "Товар кассы", "sale_price": 15, "quantity": 4, "store_id": store["id"]},
    ).json()
    assign_product_plan(client, product, telegram_id=81818)
    app.dependency_overrides[current_user] = lambda: CurrentUser(81818, "Кассир", "cashier", store["id"])
    try:
        sale = client.post(
            "/sales",
            json={"product_id": product["id"], "quantity": 1, "sale_date": datetime.now().isoformat()},
        )
        assert sale.status_code == 200, sale.text
        assert sale.json()["created_by_telegram_id"] == 81818
        assert client.get("/sales").json()[0]["id"] == sale.json()["id"]
        assert client.post(
            "/products", json={"name": "Нет прав", "sale_price": 1, "quantity": 1}
        ).status_code == 403
        assert client.patch(f"/products/{product['id']}/stock", json={"amount": 1}).status_code == 403
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_specialist_can_save_daily_cash_report_fields_for_own_store(client):
    store = client.post("/admin/stores", json={"name": "Лавочка отчёта"}).json()
    other_store = client.post("/admin/stores", json={"name": "Чужая лавочка"}).json()
    app.dependency_overrides[current_user] = lambda: CurrentUser(91919, "Специалист", "specialist", store["id"])
    try:
        saved = client.put(
            "/reports/daily-settings",
            json={
                "report_date": "2026-09-30",
                "cash_limit": "75к",
                "cash_remaining": "42к",
                "collection_status": "да",
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["cash_limit"] == "75к"
        assert saved.json()["cash_remaining"] == "42к"
        assert saved.json()["collection_status"] == "да"
        defaults = client.get("/reports/daily-settings", params={"report_date": "2026-10-01"})
        assert defaults.json()["cash_limit"] == "60к"
        denied = client.get(
            "/reports/daily-settings",
            params={"report_date": "2026-09-30", "store_id": other_store["id"]},
        )
        assert denied.status_code == 403
    finally:
        app.dependency_overrides.pop(current_user, None)


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


def test_inventory_sale_can_override_total_amount_optionally(client):
    product = create_product(client, quantity=5, purchase_price=10, sale_price=25)
    response = client.post(
        "/sales",
        json={
            "product_id": product["id"],
            "quantity": 2,
            "total_amount": 40,
            "sale_date": datetime.now().isoformat(),
        },
    )

    assert response.status_code == 200, response.text
    sale = response.json()
    assert sale["total_amount"] == 40
    assert sale["unit_sale_price"] == 20
    assert sale["profit"] == 20
    assert client.get("/products").json()[0]["quantity"] == 3


def test_inventory_sale_rejects_negative_total_amount(client):
    product = create_product(client)
    response = client.post(
        "/sales",
        json={
            "product_id": product["id"],
            "quantity": 1,
            "total_amount": -1,
            "sale_date": datetime.now().isoformat(),
        },
    )
    assert response.status_code == 422
    assert client.get("/products").json()[0]["quantity"] == 5


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


def test_bulk_inventory_sale_saves_multiple_items_and_decrements_stock(client):
    first = create_product(client, quantity=4, purchase_price=10, sale_price=25)
    second_response = client.post(
        "/products",
        json={"name": "Второй товар", "purchase_price": 5, "sale_price": 12, "quantity": 3},
    )
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()
    assign_product_plan(client, second)

    response = client.post(
        "/sales/bulk",
        json={
            "sale_date": datetime.now().isoformat(),
            "items": [
                {"product_id": first["id"], "quantity": 2},
                {"product_id": second["id"], "quantity": 1, "total_amount": 10},
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert len(response.json()) == 2
    stock = {product["id"]: product["quantity"] for product in client.get("/products").json()}
    assert stock == {first["id"]: 2, second["id"]: 2}
    assert len(client.get("/sales").json()) == 2


def test_bulk_inventory_sale_rolls_back_all_items_if_any_stock_is_insufficient(client):
    first = create_product(client, quantity=4)
    second_response = client.post(
        "/products",
        json={"name": "Второй товар", "sale_price": 12, "quantity": 1},
    )
    second = second_response.json()
    assign_product_plan(client, second)

    response = client.post(
        "/sales/bulk",
        json={
            "sale_date": datetime.now().isoformat(),
            "items": [
                {"product_id": first["id"], "quantity": 2},
                {"product_id": second["id"], "quantity": 2},
            ],
        },
    )

    assert response.status_code == 400
    stock = {product["id"]: product["quantity"] for product in client.get("/products").json()}
    assert stock == {first["id"]: 4, second["id"]: 1}
    assert client.get("/sales").json() == []


def test_manual_sale_without_catalog_product_is_rejected(client):
    response = client.post(
        "/sales",
        json={
            "product_name": "Разовая услуга",
            "unit_sale_price": 100,
            "quantity": 2,
            "sale_date": datetime.now().isoformat(),
        },
    )
    assert response.status_code == 400
    assert "только по товару из каталога" in response.json()["detail"]


def test_manual_sale_requires_name_and_sale_price(client):
    response = client.post(
        "/sales",
        json={"quantity": 1, "sale_date": datetime.now().isoformat()},
    )
    assert response.status_code == 422


def test_manual_sale_can_no_longer_be_created(client):
    created = client.post(
        "/sales",
        json={
            "product_name": "Ручная продажа",
            "unit_sale_price": 100,
            "quantity": 2,
            "sale_date": datetime.now().isoformat(),
        },
    )
    assert created.status_code == 400
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


def test_lead_assigns_personal_product_plan_and_staff_only_sees_own(client):
    store = client.post("/admin/stores", json={"name": "Целевая лавочка"}).json()
    product_response = client.post(
        "/products",
        json={"name": "Плановый товар", "sale_price": 100, "quantity": 10, "store_id": store["id"]},
    )
    assert product_response.status_code == 200, product_response.text
    product = product_response.json()
    for telegram_id in (51001, 51002):
        created = client.post(
            "/team/staff",
            json={
                "telegram_id": telegram_id,
                "display_name": f"Сотрудник {telegram_id}",
                "role": "specialist",
                "store_id": store["id"],
            },
        )
        assert created.status_code == 200, created.text

    assigned = client.put(
        "/team/staff-goals",
        json={
            "telegram_id": 51001,
            "product_id": product["id"],
            "year": 2026,
            "month": 9,
            "revenue_goal": 5000,
            "quantity_goal": 20,
        },
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["product_name"] == "Плановый товар"

    app.dependency_overrides[current_user] = lambda: CurrentUser(51001, "Сотрудник", "specialist", store["id"])
    try:
        own = client.get("/my-goals/2026/9")
        assert own.status_code == 200, own.text
        assert own.json() == [assigned.json()]
        saleable = client.get("/saleable-products", params={"year": 2026, "month": 9})
        assert [row["id"] for row in saleable.json()] == [product["id"]]
        assert client.get("/team/staff-goals/51002/2026/9").status_code == 403
        assert client.put(
            "/team/staff-goals",
            json={
                "telegram_id": 51002,
                "product_id": product["id"],
                "year": 2026,
                "month": 9,
                "revenue_goal": 1,
                "quantity_goal": 1,
            },
        ).status_code == 403
    finally:
        app.dependency_overrides.pop(current_user, None)

    app.dependency_overrides[current_user] = lambda: CurrentUser(51002, "Другой", "cashier", store["id"])
    try:
        other = client.get("/my-goals/2026/9")
        assert other.status_code == 200, other.text
        assert other.json() == []
        assert client.get("/saleable-products", params={"year": 2026, "month": 9}).json() == []
        denied_sale = client.post(
            "/sales",
            json={"product_id": product["id"], "quantity": 1, "sale_date": "2026-09-15T12:00:00"},
        )
        assert denied_sale.status_code == 400
    finally:
        app.dependency_overrides.pop(current_user, None)


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
    monkeypatch.setattr(main_module, "build_daily_report", lambda db, day, zone, store_id=None: f"report {day} {zone}")
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


def test_lead_can_send_full_telegram_report_without_admin_key(client, monkeypatch):
    delivered = []
    monkeypatch.setattr(main_module, "send_telegram_message", delivered.append)
    app.dependency_overrides[current_user] = lambda: CurrentUser(72727, "Ведущий", "lead")
    try:
        response = client.post(
            "/telegram/send-report",
            json={"report_date": "2026-09-23"},
        )
        assert response.status_code == 200, response.text
        assert delivered and delivered[0].startswith("План/факт\n23.09.2026")
    finally:
        app.dependency_overrides.pop(current_user, None)


@pytest.mark.parametrize("role", ["specialist", "cashier"])
def test_staff_can_send_only_their_own_sales(role, client, monkeypatch):
    delivered = []
    monkeypatch.setattr(main_module, "send_telegram_message", delivered.append)
    store = client.post("/admin/stores", json={"name": "Личная лавочка"}).json()
    product = create_product(
        client, name="Моя продажа", sale_price=42, quantity=10, store_id=store["id"]
    )
    for telegram_id, display_name in ((73737, "Сотрудник"), (74747, "Другой сотрудник")):
        account = client.post(
            "/team/staff",
            json={"telegram_id": telegram_id, "display_name": display_name, "role": role, "store_id": store["id"]},
        )
        assert account.status_code == 200, account.text
        assign_product_plan(client, product, telegram_id=telegram_id, year=2026, month=9)

    for telegram_id, display_name in ((73737, "Сотрудник"), (74747, "Другой сотрудник")):
        app.dependency_overrides[current_user] = lambda telegram_id=telegram_id, display_name=display_name: CurrentUser(
            telegram_id, display_name, role, store["id"]
        )
        created = client.post(
            "/sales",
            json={
                "product_id": product["id"],
                "quantity": 2,
                "sale_date": "2026-09-23T10:00:00",
            },
        )
        assert created.status_code == 200, created.text

    app.dependency_overrides[current_user] = lambda: CurrentUser(
        73737, "Сотрудник", role, store["id"]
    )
    try:
        response = client.post(
            "/telegram/send-report",
            json={"report_date": "2026-09-23"},
        )
        assert response.status_code == 200, response.text
        assert delivered[0].startswith("Мои продажи за 23.09.2026")
        assert "Моя продажа — 2 шт.; сумма 84.00 сом" in delivered[0]
        assert "Чужая продажа" not in delivered[0]
        assert "План/факт" not in delivered[0]
        assert "Всего продано: 2 шт." in delivered[0]
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_monthly_telegram_report_uses_plan_fact_and_zeroes(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_KEY", "test-admin-secret")
    service_product = create_product(client, name="Услуги", sale_price=16710, quantity=10)
    service = client.post(
        "/sales",
        json={
            "product_id": service_product["id"],
            "quantity": 1,
            "sale_date": "2026-09-15T12:00:00",
        },
    )
    assert service.status_code == 200, service.text
    sim_product = create_product(client, name="SIM-карта", sale_price=0, purchase_price=0, quantity=10)
    card = client.post(
        "/sales",
        json={
            "product_id": sim_product["id"],
            "quantity": 2,
            "sale_date": "2026-09-15T12:30:00",
        },
    )
    assert card.status_code == 200, card.text
    delivered = []
    monkeypatch.setattr(main_module, "send_telegram_message", delivered.append)

    response = client.post(
        "/telegram/send-report",
        json={"period": "month", "report_year": 2026, "report_month": 9},
        headers={"X-Telegram-Admin-Key": "test-admin-secret"},
    )

    assert response.status_code == 200, response.text
    assert delivered[0].startswith("План/факт\n09.2026\nO!Store Бета 2")
    assert "Услуги: 15000/ 16710" in delivered[0]
    assert "SA: 30/ 2" in delivered[0]
    assert "Карты: 25/ 0" in delivered[0]
    assert "Мой: 25/ 0" in delivered[0]
    assert "Аксессуары: 3100/ 0шт (0)" in delivered[0]
    assert "средняя цена" not in delivered[0]
    assert "Общая выручка" not in delivered[0]


def test_monthly_telegram_report_shows_zero_facts_without_sales(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_KEY", "test-admin-secret")
    delivered = []
    monkeypatch.setattr(main_module, "send_telegram_message", delivered.append)

    response = client.post(
        "/telegram/send-report",
        json={"period": "month", "report_year": 2026, "report_month": 9},
        headers={"X-Telegram-Admin-Key": "test-admin-secret"},
    )

    assert response.status_code == 200, response.text
    assert delivered[0].startswith("План/факт\n09.2026\nO!Store Бета 2")
    assert "SA: 30/ 0" in delivered[0]
    assert "Услуги: 15000/ 0" in delivered[0]
    assert "Мой: 25/ 0" in delivered[0]
    assert "Карты: 25/ 0" in delivered[0]
    assert "Устройства: 2 \\ 0" in delivered[0]
    assert "Аксессуары: 3100/ 0шт (0)" in delivered[0]


def test_daily_telegram_report_shows_zero_facts_without_sales(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_KEY", "test-admin-secret")
    delivered = []
    monkeypatch.setattr(main_module, "send_telegram_message", delivered.append)

    response = client.post(
        "/telegram/send-report",
        json={"report_date": "2026-09-29"},
        headers={"X-Telegram-Admin-Key": "test-admin-secret"},
    )

    assert response.status_code == 200, response.text
    assert delivered[0].startswith("План/факт\n29.09.2026\nO!Store Бета 2")
    assert "SA: 30/ 0" in delivered[0]
    assert "Мой: 25/ 0" in delivered[0]
    assert "Карты: 25/ 0" in delivered[0]


def test_daily_telegram_report_includes_selected_store_cash_fields(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_KEY", "test-admin-secret")
    store = client.post("/admin/stores", json={"name": "Лавочка для Telegram"}).json()
    saved = client.put(
        "/reports/daily-settings",
        json={
            "report_date": "2026-09-29",
            "store_id": store["id"],
            "cash_limit": "55к",
            "cash_remaining": "12к",
            "collection_status": "да",
        },
    )
    assert saved.status_code == 200, saved.text
    delivered = []
    monkeypatch.setattr(main_module, "send_telegram_message", delivered.append)

    response = client.post(
        "/telegram/send-report",
        json={"report_date": "2026-09-29", "store_id": store["id"]},
        headers={"X-Telegram-Admin-Key": "test-admin-secret"},
    )

    assert response.status_code == 200, response.text
    assert "Лимит Дс 55к" in delivered[0]
    assert "Остаток ДС: 12к" in delivered[0]
    assert "Инкассация: да" in delivered[0]


def test_monthly_telegram_report_requires_valid_year_and_month(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_KEY", "test-admin-secret")
    response = client.post(
        "/telegram/send-report",
        json={"period": "month", "report_year": 2026},
        headers={"X-Telegram-Admin-Key": "test-admin-secret"},
    )
    assert response.status_code == 422
