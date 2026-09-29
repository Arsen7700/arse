import React, { useEffect, useState } from "react";
import { api } from "../api";

const percent = (actual, target) => target > 0 ? Math.round((actual / target) * 100) : 0;

export default function Goals() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [goals, setGoals] = useState([]);
  const [actualByProduct, setActualByProduct] = useState({});
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setMessage("");
      try {
        const [goalResponse, dashboardResponse] = await Promise.all([
          api.get(`/my-goals/${year}/${month}`),
          api.get("/dashboard", { params: { year, month } }),
        ]);
        if (cancelled) return;
        setGoals(goalResponse.data);
        setActualByProduct(Object.fromEntries(
          (dashboardResponse.data.per_product || []).map((item) => [item.product_id, item])
        ));
      } catch (err) {
        if (!cancelled) setMessage(err.response?.data?.detail || "Не удалось загрузить назначенные цели");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [year, month]);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Мои цели</h1>
          <p className="muted">Ваш план и фактические продажи по каждому товару</p>
        </div>
      </div>

      <section className="card">
        <div className="row goal-period">
          <label>Год<input type="number" min="2000" max="2100" value={year} onChange={(event) => setYear(Number(event.target.value))} /></label>
          <label>Месяц<select value={month} onChange={(event) => setMonth(Number(event.target.value))}>
            {Array.from({ length: 12 }, (_, index) => <option key={index + 1} value={index + 1}>{index + 1} месяц</option>)}
          </select></label>
        </div>
        {message && <div className="notice">{message}</div>}
      </section>

      <section className="card">
        <div className="section-title">План-факт за {String(month).padStart(2, "0")}.{year}</div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Товар</th><th>План, шт.</th><th>Факт, шт.</th><th>План, сом</th><th>Факт, сом</th><th>Выполнение</th></tr></thead>
            <tbody>
              {loading ? <tr><td colSpan="6">Загрузка плана-факта…</td></tr> : goals.length ? goals.map((goal) => {
                const actual = actualByProduct[goal.product_id] || {};
                const quantityPercent = percent(actual.sold_quantity || 0, Number(goal.quantity_goal));
                const revenuePercent = percent(actual.revenue || 0, Number(goal.revenue_goal));
                return <tr key={goal.product_id}>
                  <td>{goal.product_name}</td>
                  <td>{goal.quantity_goal}</td>
                  <td>{actual.sold_quantity || 0} ({quantityPercent}%)</td>
                  <td>{Number(goal.revenue_goal || 0).toLocaleString("ru-RU")} сом</td>
                  <td>{Number(actual.revenue || 0).toLocaleString("ru-RU")} сом</td>
                  <td>Кол-во {quantityPercent}% · сумма {revenuePercent}%</td>
                </tr>;
              }) : <tr><td colSpan="6">Ведущий или администратор ещё не назначил вам план на этот месяц.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
