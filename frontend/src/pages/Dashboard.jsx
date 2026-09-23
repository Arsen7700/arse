import React, { useEffect, useState } from "react";
import { api } from "../api";

const money = (value) => `${Number(value || 0).toLocaleString("ru-RU")} сом`;
const localDateValue = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

export default function Dashboard() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data, setData] = useState(null);
  const [selectedDay, setSelectedDay] = useState(() => localDateValue(new Date()));
  const [daySales, setDaySales] = useState([]);
  const [dayLoading, setDayLoading] = useState(true);
  const [dayError, setDayError] = useState("");

  const load = async () => {
    const d = await api.get("/dashboard", { params: { year, month } });
    setData(d.data);
  };

  useEffect(() => {
    load();
  }, [year, month]);

  useEffect(() => {
    const loadDay = async () => {
      if (!selectedDay) return;
      const [selectedYear, selectedMonth, selectedDate] = selectedDay.split("-").map(Number);
      const start = new Date(selectedYear, selectedMonth - 1, selectedDate);
      const end = new Date(selectedYear, selectedMonth - 1, selectedDate + 1);
      setDayLoading(true);
      setDayError("");
      try {
        const response = await api.get("/sales", {
          params: { start: start.toISOString(), end: end.toISOString() },
        });
        setDaySales(response.data);
      } catch (err) {
        setDayError(err.response?.data?.detail || "Не удалось загрузить статистику за день");
        setDaySales([]);
      } finally {
        setDayLoading(false);
      }
    };
    loadDay();
  }, [selectedDay]);

  const dailyStats = new Map();
  (data?.per_product || [])
    .filter((item) => item.product_id !== null)
    .forEach((item) => {
      dailyStats.set(`catalog-${item.product_id}`, {
        product_name: item.product_name,
        sold_quantity: 0,
        revenue: 0,
        profit: 0,
        transactions: 0,
      });
    });
  daySales.forEach((sale) => {
    const key = sale.product_id !== null
      ? `catalog-${sale.product_id}`
      : `manual-${sale.product_name}`;
    const item = dailyStats.get(key) || {
      product_name: sale.product_name || `Товар ${sale.product_id ?? "без каталога"}`,
      sold_quantity: 0,
      revenue: 0,
      profit: 0,
      transactions: 0,
    };
    item.sold_quantity += sale.quantity;
    item.revenue += sale.total_amount;
    item.profit += sale.profit;
    item.transactions += 1;
    dailyStats.set(key, item);
  });
  const dailyProducts = [...dailyStats.values()].sort((a, b) =>
    a.product_name.localeCompare(b.product_name, "ru")
  );

  if (!data) return <div>Загрузка...</div>;

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p className="muted">Статистика продаж по каждому товару</p>
        </div>

        <div className="row">
          <input
            type="number"
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
          />
          <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
            {Array.from({ length: 12 }, (_, i) => (
              <option key={i + 1} value={i + 1}>
                {i + 1} месяц
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="card">
        <div className="section-title">Статистика по каждому товару за месяц</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Товар</th>
                <th>Продано</th>
                <th>Выручка</th>
                <th>Прибыль</th>
                <th>Остаток</th>
              </tr>
            </thead>
            <tbody>
              {data.per_product?.length ? (
                data.per_product.map((item) => (
                  <tr key={item.product_id ?? `manual-${item.product_name}`}>
                    <td>{item.product_name}</td>
                    <td>{item.sold_quantity}</td>
                    <td>{money(item.revenue)}</td>
                    <td>{money(item.profit)}</td>
                    <td>{item.stock_quantity ?? "—"}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan="5">Товары пока не добавлены</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="history-toolbar">
          <div>
            <div className="section-title">Статистика за день</div>
            <label>
              Выберите день
              <input
                type="date"
                value={selectedDay}
                onChange={(event) => setSelectedDay(event.target.value)}
              />
            </label>
          </div>
          {dayError && <div className="notice">{dayError}</div>}
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Товар</th>
                <th>Продано</th>
                <th>Выручка</th>
                <th>Прибыль</th>
                <th>Количество продаж</th>
              </tr>
            </thead>
            <tbody>
              {dayLoading ? (
                <tr><td colSpan="5">Загрузка статистики...</td></tr>
              ) : dailyProducts.length ? (
                dailyProducts.map((item, index) => (
                  <tr key={`${item.product_name}-${index}`}>
                    <td>{item.product_name}</td>
                    <td>{item.sold_quantity}</td>
                    <td>{money(item.revenue)}</td>
                    <td>{money(item.profit)}</td>
                    <td>{item.transactions}</td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan="5">Товары пока не добавлены</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

    </>
  );
}
