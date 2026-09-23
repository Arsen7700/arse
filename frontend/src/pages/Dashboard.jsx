import React, { useEffect, useState } from "react";
import { api } from "../api";
import StatCard from "../components/StatCard";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  BarChart,
  Bar,
} from "recharts";

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
  const [monthly, setMonthly] = useState([]);
  const [selectedDay, setSelectedDay] = useState(() => localDateValue(new Date()));
  const [daySales, setDaySales] = useState([]);
  const [dayProducts, setDayProducts] = useState([]);
  const [dayLoading, setDayLoading] = useState(true);
  const [dayError, setDayError] = useState("");

  const load = async () => {
    const [d, m] = await Promise.all([
      api.get("/dashboard", { params: { year, month } }),
      api.get("/reports/monthly"),
    ]);
    setData(d.data);
    setMonthly(m.data);
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
        const grouped = new Map();
        response.data.forEach((sale) => {
          const name = sale.product_name || `Товар ${sale.product_id ?? "без каталога"}`;
          const item = grouped.get(name) || {
            product_name: name,
            sold_quantity: 0,
            revenue: 0,
            profit: 0,
            transactions: 0,
          };
          item.sold_quantity += sale.quantity;
          item.revenue += sale.total_amount;
          item.profit += sale.profit;
          item.transactions += 1;
          grouped.set(name, item);
        });
        setDayProducts(
          [...grouped.values()].sort((a, b) => a.product_name.localeCompare(b.product_name, "ru"))
        );
      } catch (err) {
        setDayError(err.response?.data?.detail || "Не удалось загрузить статистику за день");
        setDaySales([]);
        setDayProducts([]);
      } finally {
        setDayLoading(false);
      }
    };
    loadDay();
  }, [selectedDay]);

  const daySummary = daySales.reduce(
    (summary, sale) => ({
      revenue: summary.revenue + sale.total_amount,
      profit: summary.profit + sale.profit,
      quantity: summary.quantity + sale.quantity,
    }),
    { revenue: 0, profit: 0, quantity: 0 }
  );

  if (!data) return <div>Загрузка...</div>;

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p className="muted">Статистика продаж и выполнение месячной цели</p>
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

      <div className="stats-grid">
        <StatCard title="Выручка за месяц" value={money(data.revenue)} />
        <StatCard title="Чистая прибыль" value={money(data.profit)} />
        <StatCard title="Продано товаров" value={data.sold_quantity} />
        <StatCard title="На складе" value={data.stock_quantity} />
        <StatCard title="Месячная цель" value={money(data.revenue_goal)} />
        <StatCard title="Осталось до цели" value={money(data.remaining_revenue)} />
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

        <div className="stats-grid daily-stats-grid">
          <StatCard title="Выручка за день" value={money(daySummary.revenue)} />
          <StatCard title="Прибыль за день" value={money(daySummary.profit)} />
          <StatCard title="Продано за день" value={daySummary.quantity} />
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
              ) : dayProducts.length ? (
                dayProducts.map((item) => (
                  <tr key={item.product_name}>
                    <td>{item.product_name}</td>
                    <td>{item.sold_quantity}</td>
                    <td>{money(item.revenue)}</td>
                    <td>{money(item.profit)}</td>
                    <td>{item.transactions}</td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan="5">За выбранный день продаж нет</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="section-title">Прогресс по выручке</div>
        <div className="progress">
          <div
            className="progress-fill"
            style={{ width: `${Math.min(data.revenue_progress, 100)}%` }}
          />
        </div>
        <div className="small">
          {data.revenue_progress}% выполнено
        </div>
      </div>

      <div className="charts-grid">
        <div className="card chart-card">
          <div className="section-title">Выручка по дням</div>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data.daily_series}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="revenue" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card chart-card">
          <div className="section-title">Продажи по месяцам</div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={monthly}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="revenue" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </>
  );
}
