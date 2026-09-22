import { useEffect, useState } from "react";
import { api } from "../api";

export default function Goals() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [revenueGoal, setRevenueGoal] = useState(100000);
  const [quantityGoal, setQuantityGoal] = useState(100);
  const [dashboard, setDashboard] = useState(null);
  const [message, setMessage] = useState("");

  const load = async () => {
    const [g, d] = await Promise.all([
      api.get(`/goals/${year}/${month}`),
      api.get("/dashboard", { params: { year, month } }),
    ]);

    setRevenueGoal(g.data.revenue_goal);
    setQuantityGoal(g.data.quantity_goal);
    setDashboard(d.data);
  };

  useEffect(() => {
    load();
  }, [year, month]);

  const save = async (e) => {
    e.preventDefault();
    await api.put("/goals", {
      year,
      month,
      revenue_goal: Number(revenueGoal),
      quantity_goal: Number(quantityGoal),
    });
    setMessage("Цель сохранена");
    load();
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Мои цели</h1>
          <p className="muted">Каждый месяц хранится отдельно</p>
        </div>
      </div>

      <div className="card">
        <form className="form-grid" onSubmit={save}>
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
          <input
            type="number"
            min="0"
            value={revenueGoal}
            onChange={(e) => setRevenueGoal(e.target.value)}
            placeholder="Цель по выручке"
          />
          <input
            type="number"
            min="0"
            value={quantityGoal}
            onChange={(e) => setQuantityGoal(e.target.value)}
            placeholder="Цель по количеству"
          />
          <button className="primary" type="submit">
            Сохранить цель
          </button>
        </form>
        {message && <div className="notice">{message}</div>}
      </div>

      {dashboard && (
        <div className="card">
          <div className="section-title">Прогресс</div>
          <p>
            Текущая выручка:{" "}
            <b>{dashboard.revenue.toLocaleString("ru-RU")} сом</b>
          </p>
          <p>
            Цель: <b>{dashboard.revenue_goal.toLocaleString("ru-RU")} сом</b>
          </p>
          <p>
            Осталось:{" "}
            <b>{dashboard.remaining_revenue.toLocaleString("ru-RU")} сом</b>
          </p>

          <div className="progress">
            <div
              className="progress-fill"
              style={{
                width: `${Math.min(dashboard.revenue_progress, 100)}%`,
              }}
            />
          </div>
          <div className="small">
            {dashboard.revenue_progress}% по выручке
          </div>

          <div style={{ height: 18 }} />

          <div className="progress">
            <div
              className="progress-fill"
              style={{
                width: `${Math.min(dashboard.quantity_progress, 100)}%`,
              }}
            />
          </div>
          <div className="small">
            {dashboard.quantity_progress}% по количеству товаров
          </div>
        </div>
      )}
    </>
  );
}
