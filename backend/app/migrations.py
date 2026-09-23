"""Small, data-preserving schema migration for manual sales."""

from sqlalchemy import inspect
from sqlalchemy.engine import Engine


def migrate_sales_schema(engine: Engine) -> None:
    """Make sales independent of products while preserving every existing sale."""
    inspector = inspect(engine)
    if not inspector.has_table("sales"):
        return  # create_all will create the current schema on a new database.

    columns = {column["name"]: column for column in inspector.get_columns("sales")}
    product_id = columns.get("product_id")
    needs_migration = "product_name" not in columns or bool(
        product_id and product_id.get("nullable") is False
    )
    if not needs_migration:
        return

    if engine.dialect.name == "sqlite":
        _migrate_sqlite(engine, columns)
    elif engine.dialect.name == "postgresql":
        _migrate_postgresql(engine)
    else:
        raise RuntimeError(
            f"Automatic sales migration is not supported for {engine.dialect.name}"
        )


def _migrate_sqlite(engine: Engine, columns: dict) -> None:
    name_expression = (
        "COALESCE(s.product_name, p.name, 'Товар (не указан)')"
        if "product_name" in columns
        else "COALESCE(p.name, 'Товар (не указан)')"
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            with connection.begin():
                connection.exec_driver_sql("ALTER TABLE sales RENAME TO sales_legacy")
                connection.exec_driver_sql(
                    """
                    CREATE TABLE sales (
                        id INTEGER NOT NULL PRIMARY KEY,
                        product_id INTEGER NULL,
                        product_name VARCHAR(200) NOT NULL,
                        quantity INTEGER NOT NULL,
                        unit_sale_price FLOAT NOT NULL,
                        unit_purchase_price FLOAT NOT NULL,
                        total_amount FLOAT NOT NULL,
                        profit FLOAT NOT NULL,
                        sale_date DATETIME NOT NULL,
                        FOREIGN KEY(product_id) REFERENCES products (id)
                    )
                    """
                )
                connection.exec_driver_sql(
                    f"""
                    INSERT INTO sales (
                        id, product_id, product_name, quantity,
                        unit_sale_price, unit_purchase_price, total_amount,
                        profit, sale_date
                    )
                    SELECT s.id, s.product_id, {name_expression}, s.quantity,
                           s.unit_sale_price, s.unit_purchase_price,
                           s.total_amount, s.profit, s.sale_date
                    FROM sales_legacy AS s
                    LEFT JOIN products AS p ON p.id = s.product_id
                    """
                )
                connection.exec_driver_sql("DROP TABLE sales_legacy")
                connection.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS ix_sales_id ON sales (id)"
                )
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()


def _migrate_postgresql(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE sales ALTER COLUMN product_id DROP NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE sales ADD COLUMN IF NOT EXISTS product_name VARCHAR(200)"
        )
        connection.exec_driver_sql(
            """
            UPDATE sales AS s
            SET product_name = COALESCE(p.name, 'Товар (не указан)')
            FROM products AS p
            WHERE s.product_name IS NULL AND p.id = s.product_id
            """
        )
        connection.exec_driver_sql(
            "UPDATE sales SET product_name = 'Товар (не указан)' "
            "WHERE product_name IS NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE sales ALTER COLUMN product_name SET NOT NULL"
        )
