import React, { useEffect, useState } from "react";
import { api } from "../api";

const roleNames = { specialist: "Специалист", lead: "Ведущий", admin: "Администратор" };

export default function AdminPanel() {
  const [stores, setStores] = useState([]);
  const [staff, setStaff] = useState([]);
  const [storeName, setStoreName] = useState("");
  const [newStaff, setNewStaff] = useState({ telegram_id: "", display_name: "", role: "specialist", store_id: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const [storesResponse, staffResponse] = await Promise.all([
        api.get("/stores", { params: { include_inactive: true } }),
        api.get("/admin/users"),
      ]);
      setStores(storesResponse.data);
      setStaff(staffResponse.data);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Не удалось загрузить панель администратора");
    }
  };

  useEffect(() => { load(); }, []);

  const createStore = async (event) => {
    event.preventDefault();
    setError(""); setMessage("");
    try {
      await api.post("/admin/stores", { name: storeName });
      setStoreName(""); setMessage("Лавочка добавлена"); await load();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Не удалось добавить лавочку");
    }
  };

  const updateStore = async (store) => {
    setError(""); setMessage("");
    try {
      await api.put(`/admin/stores/${store.id}`, { name: store.name, is_active: store.is_active });
      setMessage("Настройки лавочки сохранены"); await load();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Не удалось сохранить лавочку");
    }
  };

  const createAccount = async (event) => {
    event.preventDefault();
    setError(""); setMessage("");
    const payload = { ...newStaff, telegram_id: Number(newStaff.telegram_id), store_id: newStaff.store_id ? Number(newStaff.store_id) : null };
    try {
      await api.post("/admin/users", payload);
      setNewStaff({ telegram_id: "", display_name: "", role: "specialist", store_id: "" });
      setMessage("Сотрудник добавлен. Он может открыть приложение через Telegram."); await load();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Не удалось добавить сотрудника");
    }
  };

  const updateStaffField = (telegramId, key, value) => {
    setStaff((current) => current.map((person) => person.telegram_id === telegramId ? { ...person, [key]: value } : person));
  };

  const saveStaff = async (person) => {
    setError(""); setMessage("");
    try {
      await api.put(`/admin/users/${person.telegram_id}`, {
        display_name: person.display_name,
        role: person.role,
        store_id: person.store_id === "" ? null : Number(person.store_id),
        is_active: person.is_active,
      });
      setMessage(`Права ${person.display_name} обновлены`); await load();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Не удалось сохранить права сотрудника");
    }
  };

  return (
    <>
      <div className="page-header"><div><h1>Панель администратора</h1><p className="muted">Лавочки, сотрудники и уровни доступа</p></div></div>
      {error && <div className="notice admin-error">{error}</div>}
      {message && <div className="notice">{message}</div>}

      <section className="card">
        <div className="section-title">Лавочки</div>
        <form className="row admin-create-row" onSubmit={createStore}>
          <input placeholder="Название новой лавочки" value={storeName} onChange={(event) => setStoreName(event.target.value)} required />
          <button className="primary" type="submit">Добавить лавочку</button>
        </form>
        <div className="admin-store-list">
          {stores.map((store) => (
            <div className="admin-store-row" key={store.id}>
              <input aria-label="Название лавочки" value={store.name} onChange={(event) => setStores((current) => current.map((item) => item.id === store.id ? { ...item, name: event.target.value } : item))} />
              <label className="admin-active-toggle"><input type="checkbox" checked={store.is_active} onChange={(event) => setStores((current) => current.map((item) => item.id === store.id ? { ...item, is_active: event.target.checked } : item))} /> Активна</label>
              <button type="button" onClick={() => updateStore(store)}>Сохранить</button>
            </div>
          ))}
          {!stores.length && <p className="muted">Лавочки пока не добавлены.</p>}
        </div>
      </section>

      <section className="card">
        <div className="section-title">Добавить сотрудника</div>
        <p className="muted">Попросите сотрудника прислать числовой Telegram ID. Пароль не нужен.</p>
        <form className="form-grid admin-account-form" onSubmit={createAccount}>
          <input type="number" min="1" placeholder="Telegram ID" value={newStaff.telegram_id} onChange={(event) => setNewStaff({ ...newStaff, telegram_id: event.target.value })} required />
          <input placeholder="Имя сотрудника" value={newStaff.display_name} onChange={(event) => setNewStaff({ ...newStaff, display_name: event.target.value })} required />
          <select value={newStaff.role} onChange={(event) => setNewStaff({ ...newStaff, role: event.target.value, store_id: event.target.value === "specialist" ? newStaff.store_id : "" })}>
            <option value="specialist">Специалист</option><option value="lead">Ведущий</option><option value="admin">Администратор</option>
          </select>
          {newStaff.role === "specialist" && (
            <select value={newStaff.store_id} onChange={(event) => setNewStaff({ ...newStaff, store_id: event.target.value })} required>
              <option value="">Назначить лавочку</option>
              {stores.filter((store) => store.is_active).map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}
            </select>
          )}
          <button className="primary" type="submit">Добавить доступ</button>
        </form>
      </section>

      <section className="card">
        <div className="section-title">Сотрудники и доступ</div>
        <div className="table-wrap">
          <table className="admin-staff-table">
            <thead><tr><th>Сотрудник</th><th>Telegram ID</th><th>Роль</th><th>Лавочка</th><th>Статус</th><th>Действие</th></tr></thead>
            <tbody>
              {staff.map((person) => (
                <tr key={person.telegram_id}>
                  <td><input aria-label="Имя сотрудника" value={person.display_name} onChange={(event) => updateStaffField(person.telegram_id, "display_name", event.target.value)} /></td>
                  <td>{person.telegram_id}</td>
                  <td><select aria-label="Роль сотрудника" value={person.role} onChange={(event) => updateStaffField(person.telegram_id, "role", event.target.value)}>{Object.entries(roleNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></td>
                  <td><select aria-label="Лавочка сотрудника" value={person.store_id || ""} onChange={(event) => updateStaffField(person.telegram_id, "store_id", event.target.value)}><option value="">Все лавочки / не назначена</option>{stores.filter((store) => store.is_active).map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}</select></td>
                  <td><label className="admin-active-toggle"><input type="checkbox" checked={person.is_active} onChange={(event) => updateStaffField(person.telegram_id, "is_active", event.target.checked)} /> Активен</label></td>
                  <td><button className="primary" type="button" onClick={() => saveStaff(person)}>Сохранить</button></td>
                </tr>
              ))}
              {!staff.length && <tr><td colSpan="6">Сотрудники не добавлены.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      <section className="card admin-permissions-note"><div className="section-title">Что разрешают роли</div><p><strong>Специалист</strong> — управляет товарами своей лавочки, оформляет продажи и видит свои продажи. Остатки меняются через продажи; ручная корректировка доступна администратору.</p><p><strong>Ведущий</strong> — просмотр товаров и отчётов сотрудников по всем лавочкам, без редактирования.</p><p><strong>Администратор</strong> — полный доступ, управление сотрудниками, лавочками, товарами и остатками.</p></section>
    </>
  );
}
