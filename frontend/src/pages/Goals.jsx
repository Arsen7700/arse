import React, { useEffect, useState } from "react";
import { api } from "../api";
import { PLAN_FACT_DEFAULTS, PLAN_FACT_GROUPS } from "../planFact";

const percent = (actual, target) => target > 0 ? Math.round((actual / target) * 100) : 0;

export default function Goals() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [goals, setGoals] = useState([]);
  const [catalog, setCatalog] = useState([]);
  const [actualByProduct, setActualByProduct] = useState({});
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setMessage("");
      try {
        const [goalResponse, dashboardResponse, catalogResponse] = await Promise.all([
          api.get(`/my-goals/${year}/${month}`),
          api.get("/dashboard", { params: { year, month } }),
          api.get("/saleable-products", { params: { year, month } }),
        ]);
        if (cancelled) return;
        setGoals(goalResponse.data);
        setCatalog(catalogResponse.data);
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
          <p className="muted">План и фактические продажи по показателям план-факта</p>
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
              {loading ? <tr><td colSpan="6">Загрузка плана-факта…</td></tr> : PLAN_FACT_GROUPS.flatMap((group) => {
                const names = [group.name, ...group.children];
                return names.flatMap((name) => {
                  const product = catalog.find((item) => item.name === name);
                  if (!product) return [];
                  const assigned = goals.find((goal) => goal.product_id === product.id);
                  const defaults = PLAN_FACT_DEFAULTS[name];
                  const defaultQuantityGoal = defaults?.metric === "quantity" ? defaults.goal : 0;
                  const defaultRevenueGoal = defaults?.metric === "revenue" ? defaults.goal : 0;
                  const goal = {
                    ...assigned,
                    product_id: product.id,
                    product_name: assigned?.product_name || product.name,
                    quantity_goal: assigned?.quantity_goal ?? defaultQuantityGoal,
                    revenue_goal: assigned?.revenue_goal ?? defaultRevenueGoal,
                  };
                  const actual = actualByProduct[product.id] || {};
                  const quantityPercent = percent(actual.sold_quantity || 0, Number(goal.quantity_goal));
                  const revenuePercent = percent(actual.revenue || 0, Number(goal.revenue_goal));
                  return [<tr key={product.id}>
                    <td>{product.parent_product_id ? `↳ ${goal.product_name}` : <strong>{goal.product_name}</strong>}</td>
                    <td>{goal.quantity_goal}</td>
                    <td>{actual.sold_quantity || 0} ({quantityPercent}%)</td>
                    <td>{Number(goal.revenue_goal || 0).toLocaleString("ru-RU")} сом</td>
                    <td>{Number(actual.revenue || 0).toLocaleString("ru-RU")} сом</td>
                    <td>Кол-во {quantityPercent}% · сумма {revenuePercent}%</td>
                  </tr>];
                });
              })}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
