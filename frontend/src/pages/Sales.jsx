import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api";

export default function Sales() {
  const [products, setProducts] = useState([]);
  const [sales, setSales] = useState([]);
  const [saleType, setSaleType] = useState("inventory");
  const [productId, setProductId] = useState("");
  const [manualName, setManualName] = useState("");
  const [manualSalePrice, setManualSalePrice] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [saleDate, setSaleDate] = useState(
    new Date().toISOString().slice(0, 16)
  );
  const [message, setMessage] = useState("");

  const load = async () => {
    const [p, s] = await Promise.all([api.get("/products"), api.get("/sales")]);
    setProducts(p.data);
    setSales(s.data);
  };

  useEffect(() => {
    load();
  }, []);

  const selected = useMemo(
    () => products.find((p) => p.id === Number(productId)),
    [products, productId]
  );

  const salePrice = saleType === "inventory"
    ? selected?.sale_price || 0
    : Number(manualSalePrice || 0);
  const purchasePrice = saleType === "inventory"
    ? selected?.purchase_price || 0
    : 0;
  const total = salePrice * Number(quantity || 0);
  const profit = (salePrice - purchasePrice) * Number(quantity || 0);

  const submit = async (e) => {
    e.preventDefault();
    setMessage("");
    try {
      const payload = {
        quantity: Number(quantity),
        sale_date: new Date(saleDate).toISOString(),
      };
      if (saleType === "inventory") {
        payload.product_id = Number(productId);
      } else {
        payload.product_name = manualName.trim();
        payload.unit_sale_price = Number(manualSalePrice);
      }
      await api.post("/sales", payload);
      setMessage("Продажа сохранена");
      setQuantity(1);
      if (saleType === "manual") {
        setManualName("");
        setManualSalePrice("");
      }
      load();
    } catch (err) {
      setMessage(err.response?.data?.detail || "Ошибка продажи");
    }
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Продажи</h1>
          <p className="muted">Регистрация и история продаж</p>
        </div>
      </div>

      <div className="card">
        <form className="form-grid" onSubmit={submit}>
          <div className="row">
            <button
              type="button"
              className={saleType === "inventory" ? "primary" : ""}
              onClick={() => setSaleType("inventory")}
            >
              Со склада
            </button>
            <button
              type="button"
              className={saleType === "manual" ? "primary" : ""}
              onClick={() => setSaleType("manual")}
            >
              Без добавления товара
            </button>
          </div>

          {saleType === "inventory" ? (
            <select
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
              required
            >
              <option value="">Выберите товар со склада</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} — осталось {p.quantity}
                </option>
              ))}
            </select>
          ) : (
            <>
              <input
                placeholder="Название товара"
                value={manualName}
                onChange={(e) => setManualName(e.target.value)}
                required
              />
              <input
                type="number"
                min="0.01"
                step="0.01"
                placeholder="Цена продажи за единицу"
                value={manualSalePrice}
                onChange={(e) => setManualSalePrice(e.target.value)}
                required
              />
            </>
          )}

          <input
            type="number"
            min="1"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
          />

          <input
            type="datetime-local"
            value={saleDate}
            onChange={(e) => setSaleDate(e.target.value)}
          />

          <div className="summary-box">
            <div>Сумма: {total.toLocaleString("ru-RU")} сом</div>
            <div>Прибыль: {profit.toLocaleString("ru-RU")} сом</div>
          </div>

          <button className="primary" type="submit">
            Сохранить продажу
          </button>
        </form>
        {message && <div className="notice">{message}</div>}
      </div>

      <div className="card">
        <div className="section-title">История продаж</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Дата</th>
                <th>Товар</th>
                <th>Кол-во</th>
                <th>Сумма</th>
                <th>Прибыль</th>
              </tr>
            </thead>
            <tbody>
              {sales.map((s) => {
                const p = products.find((x) => x.id === s.product_id);
                return (
                  <tr key={s.id}>
                    <td>{new Date(s.sale_date).toLocaleString("ru-RU")}</td>
                    <td>{s.product_name || p?.name || "Товар недоступен"}</td>
                    <td>{s.quantity}</td>
                    <td>{s.total_amount} сом</td>
                    <td>{s.profit} сом</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
