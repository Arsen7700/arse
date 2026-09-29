import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api";

const dateValue = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const money = (value) => `${Number(value || 0).toLocaleString("ru-RU")} сом`;
const roleNames = { specialist: "Специалист", cashier: "Кассир" };

export default function TeamReports() {
  const today = new Date();
  const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
  const [startDate, setStartDate] = useState(dateValue(monthStart));
  const [endDate, setEndDate] = useState(dateValue(today));
  const [storeId, setStoreId] = useState("");
  const [stores, setStores] = useState([]);
  const [staff, setStaff] = useState([]);
  const [teamAccounts, setTeamAccounts] = useState([]);
  const [newAccount, setNewAccount] = useState({ telegram_id: "", display_name: "", role: "specialist", store_id: "" });
  const [managementMessage, setManagementMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.get("/stores"), api.get("/team/staff")])
      .then(([storesResponse, staffResponse]) => {
        setStores(storesResponse.data);
        setTeamAccounts(staffResponse.data);
      })
      .catch((requestError) => setError(requestError.response?.data?.detail || "Не удалось загрузить сотрудников и лавочки"));
  }, []);

  const updateTeamAccount = (telegramId, field, value) => {
    setTeamAccounts((current) => current.map((person) => person.telegram_id === telegramId
      ? { ...person, [field]: value }
      : person));
  };

  const saveTeamAccount = async (person) => {
    try {
      await api.put(`/team/staff/${person.telegram_id}`, {
        role: person.role,
        store_id: Number(person.store_id),
      });
      setManagementMessage(`Роль и лавочка сотрудника ${person.display_name} сохранены.`);
    } catch (requestError) {
      setManagementMessage(requestError.response?.data?.detail || "Не удалось сохранить роль сотрудника");
    }
  };

  const createTeamAccount = async (event) => {
    event.preventDefault();
    try {
      const response = await api.post("/team/staff", {
        ...newAccount,
        telegram_id: Number(newAccount.telegram_id),
        store_id: Number(newAccount.store_id),
      });
      setTeamAccounts((current) => [...current, response.data].sort((a, b) => a.display_name.localeCompare(b.display_name, "ru")));
      setNewAccount({ telegram_id: "", display_name: "", role: "specialist", store_id: "" });
      setManagementMessage("Сотруднику выдан доступ в выбранную лавочку.");
    } catch (requestError) {
      setManagementMessage(requestError.response?.data?.detail || "Не удалось добавить сотрудника");
    }
  };

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
      <section className="card">
        <div className="section-title">Назначение специалистов и кассиров</div>
        <p className="muted">Добавляйте сотрудников или меняйте роль специалиста/кассира и их лавочку. Ведущих и администраторов здесь назначать нельзя.</p>
        {managementMessage && <div className="notice">{managementMessage}</div>}
        <form className="form-grid admin-account-form" onSubmit={createTeamAccount}>
          <input type="number" min="1" placeholder="Telegram ID" value={newAccount.telegram_id} onChange={(event) => setNewAccount({ ...newAccount, telegram_id: event.target.value })} required />
          <input placeholder="Имя сотрудника" value={newAccount.display_name} onChange={(event) => setNewAccount({ ...newAccount, display_name: event.target.value })} required />
          <select value={newAccount.role} onChange={(event) => setNewAccount({ ...newAccount, role: event.target.value })}><option value="specialist">Специалист</option><option value="cashier">Кассир</option></select>
          <select value={newAccount.store_id} onChange={(event) => setNewAccount({ ...newAccount, store_id: event.target.value })} required><option value="">Выберите лавочку</option>{stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}</select>
          <button className="primary" type="submit">Добавить сотрудника</button>
        </form>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Сотрудник</th><th>Telegram ID</th><th>Роль</th><th>Лавочка</th><th>Сохранить</th></tr></thead>
            <tbody>
              {teamAccounts.map((person) => (
                <tr key={person.telegram_id}>
                  <td>{person.display_name}</td><td>{person.telegram_id}</td>
                  <td><select aria-label={`Роль ${person.display_name}`} value={person.role} onChange={(event) => updateTeamAccount(person.telegram_id, "role", event.target.value)}>{Object.entries(roleNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></td>
                  <td><select aria-label={`Лавочка ${person.display_name}`} value={person.store_id || ""} onChange={(event) => updateTeamAccount(person.telegram_id, "store_id", event.target.value)}>{stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}</select></td>
                  <td><button className="primary" type="button" disabled={!person.store_id} onClick={() => saveTeamAccount(person)}>Сохранить</button></td>
                </tr>
              ))}
              {!teamAccounts.length && <tr><td colSpan="5">Специалисты и кассиры не найдены.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
