import React, { useEffect, useState } from "react";
import { api } from "../api";

const percent = (actual, target) =>
  target > 0 ? Math.round((actual / target) * 100) : 0;

export default function Goals() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [goals, setGoals] = useState([]);
  const [actualByProduct, setActualByProduct] = useState({});
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState(null);

  const load = async () => {
    setLoading(true);
    setMessage("");
    try {
      const [goalResponse, dashboardResponse] = await Promise.all([
        api.get(`/product-goals/${year}/${month}`),
        api.get("/dashboard", { params: { year, month } }),
      ]);
      setGoals(goalResponse.data);
      setActualByProduct(
        Object.fromEntries(
          (dashboardResponse.data.per_product || []).map((item) => [
            item.product_id,
            item,
          ])
        )
      );
    } catch (err) {
      setMessage(err.response?.data?.detail || "Не удалось загрузить цели товаров");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [year, month]);

  const updateGoalField = (productId, field, value) => {
    setGoals((current) =>
      current.map((goal) =>
        goal.product_id === productId ? { ...goal, [field]: value } : goal
      )
    );
  };

  const saveGoal = async (goal) => {
    setSavingId(goal.product_id);
    setMessage("");
    try {
      await api.put("/product-goals", {
        product_id: goal.product_id,
        year,
        month,
        revenue_goal: Number(goal.revenue_goal),
        quantity_goal: Number(goal.quantity_goal),
      });
      setMessage(`Цель для товара «${goal.product_name}» сохранена`);
    } catch (err) {
      setMessage(err.response?.data?.detail || "Не удалось сохранить цель");
    } finally {
      setSavingId(null);
    }
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Мои цели</h1>
          <p className="muted">Задайте месячную цель отдельно для каждого товара</p>
        </div>
      </div>

      <div className="card">
        <div className="row goal-period">
          <label>
            Год
            <input
              type="number"
              min="2000"
              max="2100"
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
            />
          </label>
          <label>
            Месяц
            <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
              {Array.from({ length: 12 }, (_, i) => (
                <option key={i + 1} value={i + 1}>
                  {i + 1} месяц
                </option>
              ))}
            </select>
          </label>
        </div>
        {message && <div className="notice">{message}</div>}
      </div>

      <div className="card">
        <div className="section-title">Цели товаров на {month}.{year}</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Товар</th>
                <th>Выручка сейчас</th>
                <th>Цель по выручке</th>
                <th>Выполнение</th>
                <th>Продано</th>
                <th>Цель по количеству</th>
                <th>Выполнение</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan="8">Загрузка целей...</td></tr>
              ) : goals.length ? (
                goals.map((goal) => {
                  const actual = actualByProduct[goal.product_id] || {};
                  const revenueProgress = percent(actual.revenue || 0, Number(goal.revenue_goal));
                  const quantityProgress = percent(actual.sold_quantity || 0, Number(goal.quantity_goal));
                  return (
                    <tr key={goal.product_id}>
                      <td>{goal.product_name}</td>
                      <td>{Number(actual.revenue || 0).toLocaleString("ru-RU")} сом</td>
                      <td>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          aria-label={`Цель по выручке для ${goal.product_name}`}
                          value={goal.revenue_goal}
                          onChange={(e) => updateGoalField(goal.product_id, "revenue_goal", e.target.value)}
                        />
                      </td>
                      <td>{revenueProgress}%</td>
                      <td>{actual.sold_quantity || 0}</td>
                      <td>
                        <input
                          type="number"
                          min="0"
                          aria-label={`Цель по количеству для ${goal.product_name}`}
                          value={goal.quantity_goal}
                          onChange={(e) => updateGoalField(goal.product_id, "quantity_goal", e.target.value)}
                        />
                      </td>
                      <td>{quantityProgress}%</td>
                      <td>
                        <button
                          type="button"
                          className="primary"
                          disabled={savingId === goal.product_id}
                          onClick={() => saveGoal(goal)}
                        >
                          {savingId === goal.product_id ? "Сохранение..." : "Сохранить"}
                        </button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr><td colSpan="8">Сначала добавьте товары, чтобы задать им цели.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
