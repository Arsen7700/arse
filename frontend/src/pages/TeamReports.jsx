import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api";

const dateValue = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const money = (value) => `${Number(value || 0).toLocaleString("ru-RU")} сом`;

export default function TeamReports() {
  const today = new Date();
  const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
  const [startDate, setStartDate] = useState(dateValue(monthStart));
  const [endDate, setEndDate] = useState(dateValue(today));
  const [storeId, setStoreId] = useState("");
  const [stores, setStores] = useState([]);
  const [staff, setStaff] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/stores")
      .then((response) => setStores(response.data))
      .catch((requestError) => setError(requestError.response?.data?.detail || "Не удалось загрузить список лавочек"));
  }, []);

  useEffect(() => {
    if (!startDate || !endDate) return;
    if (startDate > endDate) {
      setError("Начальная дата должна быть раньше конечной");
      setStaff([]);
      setLoading(false);
      return;
    }
    setLoading(true); setError("");
    const [startYear, startMonth, startDay] = startDate.split("-").map(Number);
    const [endYear, endMonth, endDay] = endDate.split("-").map(Number);
    const start = new Date(startYear, startMonth - 1, startDay);
    const end = new Date(endYear, endMonth - 1, endDay + 1);
    api.get("/reports/staff", {
      params: { start: start.toISOString(), end: end.toISOString(), store_id: storeId || undefined },
    }).then((response) => setStaff(response.data))
      .catch((requestError) => {
        setStaff([]);
        setError(requestError.response?.data?.detail || "Не удалось загрузить отчёт команды");
      })
      .finally(() => setLoading(false));
  }, [startDate, endDate, storeId]);

  const totals = useMemo(() => staff.reduce((result, person) => ({
    sold: result.sold + Number(person.sold_quantity || 0),
    revenue: result.revenue + Number(person.revenue || 0),
    profit: result.profit + Number(person.profit || 0),
  }), { sold: 0, revenue: 0, profit: 0 }), [staff]);

  return (
    <>
      <div className="page-header"><div><h1>Отчёты команды</h1><p className="muted">Продажи каждого специалиста за выбранный период</p></div></div>
      <section className="card team-report-filters">
        <label>С даты<input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
        <label>По дату<input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
        <label>Лавочка<select value={storeId} onChange={(event) => setStoreId(event.target.value)}><option value="">Все лавочки</option>{stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}</select></label>
      </section>
      {error && <div className="notice admin-error">{error}</div>}
      <section className="stats-grid team-summary-grid">
        <article className="card stat-card"><div className="muted">Продано всего</div><div className="stat-value">{totals.sold.toLocaleString("ru-RU")} шт.</div></article>
        <article className="card stat-card"><div className="muted">Выручка команды</div><div className="stat-value">{money(totals.revenue)}</div></article>
        <article className="card stat-card"><div className="muted">Прибыль команды</div><div className="stat-value">{money(totals.profit)}</div></article>
      </section>
      <section className="card">
        <div className="section-title">Продажи по сотрудникам</div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Сотрудник</th><th>Лавочка</th><th>Продано</th><th>Выручка</th><th>Прибыль</th><th>Продаж</th><th>По товарам</th></tr></thead>
            <tbody>
              {loading ? <tr><td colSpan="7">Загружаю отчёты…</td></tr> : staff.length ? staff.map((person) => (
                <tr key={person.telegram_id ?? "legacy"}>
                  <td>{person.display_name}</td><td>{person.store_name}</td><td>{person.sold_quantity} шт.</td>
                  <td>{money(person.revenue)}</td><td>{money(person.profit)}</td><td>{person.sales_count}</td>
                  <td>{person.products?.length ? <details className="staff-product-details"><summary>{person.products.length} поз.</summary><ul>{person.products.map((product) => <li key={product.product_name}><strong>{product.product_name}</strong> — {product.sold_quantity} шт.; {money(product.revenue)}</li>)}</ul></details> : "—"}</td>
                </tr>
              )) : <tr><td colSpan="7">За выбранный период продаж нет.</td></tr>}
            </tbody>
          </table>
        </div>
        <p className="small">Продажи, внесённые до подключения учётных записей, отмечены отдельно: у них нет сохранённого автора.</p>
      </section>
    </>
  );
}
