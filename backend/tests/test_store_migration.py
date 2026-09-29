from sqlalchemy import create_engine, text

from app.migrations import migrate_store_and_staff_schema


def test_store_migration_preserves_legacy_products_and_sales():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE stores (id INTEGER PRIMARY KEY, name VARCHAR(120) UNIQUE NOT NULL, "
            "is_active BOOLEAN NOT NULL DEFAULT 1, created_at DATETIME)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE products (id INTEGER PRIMARY KEY, name VARCHAR(200), quantity INTEGER)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE sales (id INTEGER PRIMARY KEY, product_id INTEGER, product_name VARCHAR(200), "
            "quantity INTEGER, unit_sale_price FLOAT, unit_purchase_price FLOAT, total_amount FLOAT, "
            "profit FLOAT, sale_date DATETIME)"
        )
        connection.exec_driver_sql("INSERT INTO products VALUES (7, 'Старый товар', 4)")
        connection.exec_driver_sql(
            "INSERT INTO sales VALUES (9, 7, 'Старый товар', 2, 30, 10, 60, 40, '2026-09-01 10:00:00')"
        )

    migrate_store_and_staff_schema(engine)

    with engine.connect() as connection:
        store_id = connection.execute(
            text("SELECT id FROM stores WHERE name = 'Основная лавочка'")
        ).scalar_one()
        assert connection.execute(
            text("SELECT id, store_id FROM products WHERE id = 7")
        ).one() == (7, store_id)
        sale = connection.execute(
            text("SELECT id, store_id, created_by_telegram_id, total_amount FROM sales WHERE id = 9")
        ).one()
        assert sale == (9, store_id, None, 60)
        assert connection.execute(text("SELECT COUNT(*) FROM products")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM sales")).scalar_one() == 1
    engine.dispose()
