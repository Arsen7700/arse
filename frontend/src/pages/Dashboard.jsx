import React, { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { PLAN_FACT_ITEMS } from "../planFact";
import StatCard from "../components/StatCard";

const money = (value) => `${Number(value || 0).toLocaleString("ru-RU")} сом`;
const localDateValue = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

export default function Dashboard() {
  const user = useAuth();
  const canSelectStores = ["admin", "lead"].includes(user?.role);
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data, setData] = useState(null);
  const [stores, setStores] = useState([]);
  const [selectedStoreIds, setSelectedStoreIds] = useState([]);
  const [storesLoaded, setStoresLoaded] = useState(false);
  const [selectedDay, setSelectedDay] = useState(() => localDateValue(new Date()));
  const [daySales, setDaySales] = useState([]);
  const [dayLoading, setDayLoading] = useState(true);
  const [dayError, setDayError] = useState("");

  useEffect(() => {
    if (!canSelectStores) {
      setStoresLoaded(true);
      return;
    }
    api.get("/stores")
      .then((response) => {
        setStores(response.data);
        setSelectedStoreIds(response.data.map((store) => store.id));
      })
      .catch(() => setStores([]))
      .finally(() => setStoresLoaded(true));
  }, [canSelectStores]);

  useEffect(() => {
    if (canSelectStores && !storesLoaded) return;
    if (canSelectStores && selectedStoreIds.length === 0) {
      setData({ year, month, sold_quantity: 0, profit: 0, stock_quantity: 0, per_product: [] });
      return;
    }
    const params = new URLSearchParams({ year: String(year), month: String(month) });
    if (canSelectStores) selectedStoreIds.forEach((id) => params.append("store_ids", String(id)));
    api.get(`/dashboard?${params.toString()}`)
      .then((response) => setData(response.data))
      .catch(() => setData({ year, month, sold_quantity: 0, profit: 0, stock_quantity: 0, per_product: [] }));
  }, [year, month, canSelectStores, storesLoaded, selectedStoreIds]);

  useEffect(() => {
    const loadDay = async () => {
      if (!selectedDay) return;
      if (canSelectStores && !storesLoaded) return;
      if (canSelectStores && selectedStoreIds.length === 0) {
        setDaySales([]);
        setDayLoading(false);
        return;
      }
      const [selectedYear, selectedMonth, selectedDate] = selectedDay.split("-").map(Number);
      const start = new Date(selectedYear, selectedMonth - 1, selectedDate);
      const end = new Date(selectedYear, selectedMonth - 1, selectedDate + 1);
      setDayLoading(true);
      setDayError("");
      try {
        const params = new URLSearchParams({ start: start.toISOString(), end: end.toISOString() });
        if (canSelectStores) selectedStoreIds.forEach((id) => params.append("store_ids", String(id)));
        const response = await api.get(`/sales?${params.toString()}`);
        setDaySales(response.data);
      } catch (err) {
        setDayError(err.response?.data?.detail || "Не удалось загрузить статистику за день");
        setDaySales([]);
      } finally {
        setDayLoading(false);
      }
    };
    loadDay();
  }, [selectedDay, canSelectStores, storesLoaded, selectedStoreIds]);

  const dailyStats = new Map();
  (data?.per_product || [])
    .filter((item) => item.product_id !== null)
    .forEach((item) => {
      dailyStats.set(`catalog-${item.product_id}`, {
        product_name: item.product_name,
        sold_quantity: 0,
        revenue: 0,
        realization_amount: 0,
        profit: 0,
        transactions: 0,
      });
    });
  const planFactNames = new Set(PLAN_FACT_ITEMS.map((item) => item.name));
  daySales.filter((sale) => planFactNames.has(sale.product_name)).forEach((sale) => {
    const key = sale.product_id !== null
      ? `catalog-${sale.product_id}`
      : `manual-${sale.product_name}`;
    const item = dailyStats.get(key) || {
      product_name: sale.product_name || `Товар ${sale.product_id ?? "без каталога"}`,
      sold_quantity: 0,
      revenue: 0,
      realization_amount: 0,
      profit: 0,
      transactions: 0,
    };
    item.sold_quantity += sale.quantity;
    item.revenue += sale.total_amount;
    item.realization_amount += Number(sale.accessory_realization_amount || 0);
    item.profit += sale.profit;
    item.transactions += 1;
    dailyStats.set(key, item);
  });
  const dailyProducts = [...dailyStats.values()].sort((a, b) =>
    a.product_name.localeCompare(b.product_name, "ru")
  );
  const monthRevenue = (data?.per_product || []).reduce((sum, item) => sum + Number(item.revenue || 0), 0);

  if (!data) return <div>Загрузка...</div>;

  const allStoresSelected = stores.length > 0 && selectedStoreIds.length === stores.length;
  const storeFilterLabel = allStoresSelected
    ? "Все лавочки"
    : selectedStoreIds.length === 1
      ? stores.find((store) => store.id === selectedStoreIds[0])?.name || "1 лавочка"
      : `Выбрано лавочек: ${selectedStoreIds.length}`;

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Обзор продаж</h1>
          <p className="muted">Показатели и динамика за {String(month).padStart(2, "0")}.{year}</p>
        </div>

        <div className="row dashboard-filters">
          {canSelectStores && <details className="dashboard-store-filter">
            <summary>{storeFilterLabel}</summary>
            <div className="dashboard-store-options">
              <label>
                <input
                  type="checkbox"
                  checked={allStoresSelected}
                  onChange={(event) => setSelectedStoreIds(event.target.checked ? stores.map((store) => store.id) : [])}
                />
                Все лавочки
              </label>
              {stores.map((store) => (
                <label key={store.id}>
                  <input
                    type="checkbox"
                    checked={selectedStoreIds.includes(store.id)}
                    onChange={(event) => setSelectedStoreIds((current) => event.target.checked
                      ? [...current, store.id]
                      : current.filter((id) => id !== store.id))}
                  />
                  {store.name}
                </label>
              ))}
            </div>
          </details>}
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

      <section className="stats-grid dashboard-kpis" aria-label="Сводка за месяц">
        <StatCard title="Продано по плану-факту" value={`${Number(data.sold_quantity || 0).toLocaleString("ru-RU")} шт.`} subtitle="За выбранный месяц" />
        <StatCard title="Выручка" value={money(monthRevenue)} subtitle="По зарегистрированным продажам" />
        <StatCard title="Прибыль" value={money(data.profit)} subtitle="За выбранный месяц" />
        <StatCard title="Остаток товаров" value={Number(data.stock_quantity || 0).toLocaleString("ru-RU")} subtitle="Единиц на складе" />
      </section>

      <div className="card">
        <div className="section-title">Статистика по товарам из план-факта за месяц</div>
        <div className="table-wrap">
          <table className="dashboard-month-table">
            <thead>
              <tr>
                <th>Товар</th>
                <th>Факт, количество</th>
                <th>Факт, сумма</th>
                <th>Сумма реализации аксессуаров</th>
              </tr>
            </thead>
            <tbody>
              {data.per_product?.length ? (
                data.per_product.map((item) => (
                  <tr key={item.product_id ?? `manual-${item.product_name}`}>
                    <td>{item.product_name}</td>
                    <td>{item.sold_quantity}</td>
                    <td>{money(item.revenue)}</td>
                    <td>{money(item.realization_amount)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan="4">На выбранный месяц показатели план-факта не найдены</td>
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
          <table className="dashboard-day-table">
            <thead>
              <tr>
                <th>Товар</th>
                <th>Факт, количество</th>
                <th>Факт, сумма</th>
                <th>Сумма реализации аксессуаров</th>
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
                    <td>{money(item.realization_amount)}</td>
                    <td>{item.transactions}</td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan="5">Показатели пока не найдены</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

    </>
  );
}
