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

export default function Dashboard() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data, setData] = useState(null);
  const [monthly, setMonthly] = useState([]);

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
