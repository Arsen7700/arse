import React, { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

const REPORT_SALE_PRESETS = [
  "SA",
  "Услуги",
  "Мой",
  "Карты",
  "Устройства",
  "Saima",
  "Телефоны",
  "Аксессуары",
  "Вместе дешевле",
  "O!семья",
];

const REPORT_ROWS = [
  { label: "SA", plan: 30, metric: "quantity", aliases: ["sa", "sim-карта", "sim карта", "сим-карта", "сим карта", "сим-карты"] },
  { label: "Услуги", plan: 15000, metric: "revenue", aliases: ["услуги", "услуга"] },
  { label: "Мой", plan: 25, metric: "quantity", aliases: ["мой", "мой!"] },
  { label: "Карты", plan: 25, metric: "quantity", aliases: ["карты", "карта"] },
  { label: "Устройства", plan: 2, metric: "devices", aliases: ["устройства", "устройство"] },
  { label: "Saima", plan: 1, metric: "quantity", aliases: ["saima"] },
  { label: "Телефоны", plan: 2, metric: "quantity", aliases: ["телефоны", "телефон"] },
  { label: "Аксессуары", plan: 3100, metric: "accessories", aliases: ["аксессуары", "аксессуар"] },
  { label: "Вместе дешевле", plan: 0, metric: "bundle", aliases: ["вместе дешевле"] },
  { label: "O!семья", plan: 0, metric: "family", aliases: ["o!семья", "o! семья"] },
];

const toLocalDateTime = (value) => {
  const date = new Date(value);
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 16);
};

const localDateInputValue = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const localMonthInputValue = (date) => {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  return `${date.getFullYear()}-${month}`;
};

const dateAtTimezoneUtc = (dateValue, timezone) => {
  const [year, month, day] = dateValue.split("-").map(Number);
  const target = Date.UTC(year, month - 1, day);
  let utc = target;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    }).formatToParts(new Date(utc));
    const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
    const observed = Date.UTC(
      Number(values.year), Number(values.month) - 1, Number(values.day),
      Number(values.hour), Number(values.minute), Number(values.second)
    );
    utc += target - observed;
  }
  return new Date(utc);
};

export default function Sales() {
  const user = useAuth();
  const readOnly = false;
  const isLead = user?.role === "lead";
  const isAdmin = user?.role === "admin";
  const canSendFullReport = isAdmin || isLead;
  const canEditDailySettings = ["specialist", "lead", "admin"].includes(user?.role);
  const canSelectReportStore = ["lead", "admin"].includes(user?.role);
  const [products, setProducts] = useState([]);
  const [stores, setStores] = useState([]);
  const [sales, setSales] = useState([]);
  const [saleType, setSaleType] = useState("inventory");
  const [inventoryItems, setInventoryItems] = useState([
    { product_id: "", quantity: 1, total_amount: "" },
  ]);
  const [manualName, setManualName] = useState("");
  const [manualNameCustom, setManualNameCustom] = useState(false);
  const [manualSalePrice, setManualSalePrice] = useState("");
  const [manualSaleStoreId, setManualSaleStoreId] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [saleDate, setSaleDate] = useState(() => toLocalDateTime(new Date()));
  const [message, setMessage] = useState("");
  const [historyMessage, setHistoryMessage] = useState("");
  const [editingSale, setEditingSale] = useState(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyDate, setHistoryDate] = useState(() => localDateInputValue(new Date()));
  const [historyLoading, setHistoryLoading] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [reportPeriod, setReportPeriod] = useState("day");
  const [reportDate, setReportDate] = useState(() => localDateInputValue(new Date()));
  const [reportMonth, setReportMonth] = useState(() => localMonthInputValue(new Date()));
  const [reportSales, setReportSales] = useState([]);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportMessage, setReportMessage] = useState("");
  const [reportSending, setReportSending] = useState(false);
  const [telegramAdminKey, setTelegramAdminKey] = useState("");
  const [reportStoreId, setReportStoreId] = useState("");
  const [dailySettings, setDailySettings] = useState({ cash_limit: "60к", cash_remaining: "80к", collection_status: "нет" });
  const [telegramSchedule, setTelegramSchedule] = useState({
    enabled: false,
    send_time: "20:00",
    timezone: "Asia/Almaty",
  });

  const loadProducts = async () => {
    const p = await api.get("/products");
    setProducts(p.data);
  };

  const loadHistory = async () => {
    if (!historyDate) return;
    const [year, month, day] = historyDate.split("-").map(Number);
    const start = new Date(year, month - 1, day);
    const end = new Date(year, month - 1, day + 1);
    setHistoryLoading(true);
    try {
      const s = await api.get("/sales", {
        params: { start: start.toISOString(), end: end.toISOString() },
      });
      setSales(s.data);
    } catch (err) {
      setHistoryMessage(err.response?.data?.detail || "Не удалось загрузить историю продаж");
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    loadProducts();
  }, []);

  useEffect(() => {
    if (canSelectReportStore) {
      api.get("/stores").then((response) => {
        setStores(response.data);
        setReportStoreId((current) => current || String(response.data[0]?.id || ""));
      }).catch(() => {});
    }
  }, [canSelectReportStore]);

  useEffect(() => {
    if (historyOpen) loadHistory();
  }, [historyOpen, historyDate]);

  useEffect(() => {
    const loadReport = async () => {
      if (!reportOpen) return;
      let start;
      let end;
      if (reportPeriod === "day") {
        if (!reportDate) return;
        const [year, month, day] = reportDate.split("-").map(Number);
        const nextDate = new Date(Date.UTC(year, month - 1, day + 1)).toISOString().slice(0, 10);
        start = dateAtTimezoneUtc(reportDate, telegramSchedule.timezone);
        end = dateAtTimezoneUtc(nextDate, telegramSchedule.timezone);
      } else {
        if (!reportMonth) return;
        const [year, month] = reportMonth.split("-").map(Number);
        const firstDay = `${year}-${String(month).padStart(2, "0")}-01`;
        const nextMonth = new Date(Date.UTC(year, month, 1)).toISOString().slice(0, 10);
        start = dateAtTimezoneUtc(firstDay, telegramSchedule.timezone);
        end = dateAtTimezoneUtc(nextMonth, telegramSchedule.timezone);
      }
      setReportLoading(true);
      setReportMessage("");
      try {
        const response = await api.get("/sales", {
          params: { start: start.toISOString(), end: end.toISOString(), store_id: canSelectReportStore ? reportStoreId || undefined : undefined },
        });
        setReportSales(response.data);
      } catch (err) {
        setReportSales([]);
        setReportMessage(err.response?.data?.detail || "Не удалось загрузить данные отчёта");
      } finally {
        setReportLoading(false);
      }
    };
    loadReport();
  }, [reportOpen, reportPeriod, reportDate, reportMonth, reportStoreId, canSelectReportStore, telegramSchedule.timezone]);

  useEffect(() => {
    if (!reportOpen || reportPeriod !== "day" || !reportDate || !canEditDailySettings) return;
    api.get("/reports/daily-settings", {
      params: { report_date: reportDate, store_id: canSelectReportStore ? reportStoreId || undefined : undefined },
    }).then((response) => setDailySettings(response.data))
      .catch((err) => setReportMessage(err.response?.data?.detail || "Не удалось загрузить данные кассы"));
  }, [reportOpen, reportPeriod, reportDate, reportStoreId, canEditDailySettings, canSelectReportStore]);

  useEffect(() => {
    if (!reportOpen || !isAdmin) return;
    api.get("/telegram/schedule")
      .then((response) => setTelegramSchedule(response.data))
      .catch(() => setReportMessage("Не удалось загрузить настройки отправки"));
  }, [reportOpen, isAdmin]);

  const inventoryTotal = inventoryItems.reduce((sum, line) => {
    const product = products.find((item) => item.id === Number(line.product_id));
    const lineQuantity = Number(line.quantity || 0);
    const lineTotal = line.total_amount !== ""
      ? Number(line.total_amount || 0)
      : (product?.sale_price || 0) * lineQuantity;
    return sum + lineTotal;
  }, 0);
  const inventoryProfit = inventoryItems.reduce((sum, line) => {
    const product = products.find((item) => item.id === Number(line.product_id));
    const lineQuantity = Number(line.quantity || 0);
    const lineTotal = line.total_amount !== ""
      ? Number(line.total_amount || 0)
      : (product?.sale_price || 0) * lineQuantity;
    return sum + lineTotal - (product?.purchase_price || 0) * lineQuantity;
  }, 0);
  const salePrice = Number(manualSalePrice || 0);
  const total = saleType === "inventory"
    ? inventoryTotal
    : salePrice * Number(quantity || 0);
  const profit = saleType === "inventory"
    ? inventoryProfit
    : total;
  const reportActuals = new Map(REPORT_ROWS.map((row) => [row.label, { quantity: 0, revenue: 0 }]));
  const reportAliases = new Map(
    REPORT_ROWS.flatMap((row) => row.aliases.map((alias) => [alias, row.label]))
  );
  reportSales.forEach((sale) => {
    const label = reportAliases.get((sale.product_name || "").trim().toLocaleLowerCase("ru-RU"));
    if (!label) return;
    const item = reportActuals.get(label);
    item.quantity += sale.quantity;
    item.revenue += Number(sale.total_amount || 0);
  });
  const reportPeriodLabel = reportPeriod === "day"
    ? (reportDate ? reportDate.split("-").reverse().join(".") : "")
    : (reportMonth ? `${reportMonth.slice(5, 7)}.${reportMonth.slice(0, 4)}` : "");
  const reportText = [
    "План/факт",
    reportPeriodLabel,
    "O!Store Бета 2",
    ...REPORT_ROWS.map((row) => {
      const actual = reportActuals.get(row.label);
      if (row.metric === "revenue") return `${row.label}: ${row.plan}/ ${Math.round(actual.revenue)}`;
      if (row.metric === "accessories") return `${row.label}: ${row.plan}/ ${actual.quantity}шт (${Math.round(actual.revenue)})`;
      if (row.metric === "devices") return `${row.label}: ${row.plan} \\ ${actual.quantity}`;
      if (row.metric === "family") return `${row.label}-${actual.quantity}`;
      if (row.metric === "bundle") return `${row.label} ${actual.quantity}`;
      return `${row.label}: ${row.plan}/ ${actual.quantity}`;
    }),
    `Лимит Дс ${reportPeriod === "day" ? dailySettings.cash_limit : "60к"}`,
    `Остаток ДС: ${reportPeriod === "day" ? dailySettings.cash_remaining : "80к"}`,
    `Инкассация: ${reportPeriod === "day" ? dailySettings.collection_status : "нет"}`,
    "Отказы со стороны банка:0 2",
  ].join("\n");

  const saveDailySettings = async () => {
    if (!reportDate) return;
    try {
      const response = await api.put("/reports/daily-settings", {
        ...dailySettings,
        report_date: reportDate,
        ...(canSelectReportStore && reportStoreId ? { store_id: Number(reportStoreId) } : {}),
      });
      setDailySettings(response.data);
      setReportMessage("Данные кассы сохранены для выбранной даты и лавочки.");
    } catch (err) {
      setReportMessage(err.response?.data?.detail || "Не удалось сохранить данные кассы");
    }
  };

  const copyReport = async () => {
    try {
      await navigator.clipboard.writeText(reportText);
      setReportMessage("Отчёт скопирован. Его можно вставить в Telegram.");
    } catch {
      setReportMessage("Не удалось скопировать. Выделите текст отчёта и скопируйте вручную.");
    }
  };

  const shareReportToTelegram = () => {
    window.open(
      `https://t.me/share/url?text=${encodeURIComponent(reportText)}`,
      "_blank",
      "noopener,noreferrer"
    );
  };

  const sendReportNow = async () => {
    if (isAdmin && !telegramAdminKey) {
      setReportMessage("Введите ключ администратора Telegram из настроек Render");
      return;
    }
    setReportSending(true);
    setReportMessage("");
    try {
      const reportPayload = reportPeriod === "day"
        ? { period: "day", report_date: reportDate, ...(reportStoreId ? { store_id: Number(reportStoreId) } : {}) }
        : {
          period: "month",
          report_year: Number(reportMonth.slice(0, 4)),
          report_month: Number(reportMonth.slice(5, 7)),
          ...(reportStoreId ? { store_id: Number(reportStoreId) } : {}),
        };
      const response = await api.post(
        "/telegram/send-report",
        reportPayload,
        isAdmin ? { headers: { "X-Telegram-Admin-Key": telegramAdminKey } } : {}
      );
      setReportMessage(response.data.message);
    } catch (err) {
      setReportMessage(err.response?.data?.detail || "Не удалось отправить отчёт");
    } finally {
      setReportSending(false);
    }
  };

  const saveTelegramSchedule = async (event) => {
    event.preventDefault();
    if (!telegramAdminKey) {
      setReportMessage("Введите ключ администратора Telegram из настроек Render");
      return;
    }
    setReportMessage("");
    try {
      const response = await api.put(
        "/telegram/schedule",
        telegramSchedule,
        { headers: { "X-Telegram-Admin-Key": telegramAdminKey } }
      );
      setTelegramSchedule(response.data);
      setReportMessage("Расписание Telegram сохранено");
    } catch (err) {
      setReportMessage(err.response?.data?.detail || "Не удалось сохранить расписание");
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    setMessage("");
    try {
      const saleDateIso = new Date(saleDate).toISOString();
      if (saleType === "inventory") {
        const payload = {
          sale_date: saleDateIso,
          items: inventoryItems.map((line) => ({
            product_id: Number(line.product_id),
            quantity: Number(line.quantity),
            total_amount: line.total_amount === "" ? undefined : Number(line.total_amount),
          })),
        };
        const response = await api.post("/sales/bulk", payload);
        setMessage(`Сохранено товаров в продаже: ${response.data.length}`);
        setInventoryItems([{ product_id: "", quantity: 1, total_amount: "" }]);
      } else {
        const payload = {
          quantity: Number(quantity),
          sale_date: saleDateIso,
        };
        payload.product_name = manualName.trim();
        payload.unit_sale_price = salePrice;
        if (canSelectReportStore && manualSaleStoreId) payload.store_id = Number(manualSaleStoreId);
        await api.post("/sales", payload);
        setMessage("Продажа сохранена");
        setQuantity(1);
        setManualName("");
        setManualNameCustom(false);
        setManualSalePrice("");
      }
      await loadProducts();
      if (historyOpen) await loadHistory();
    } catch (err) {
      setMessage(err.response?.data?.detail || "Ошибка продажи");
    }
  };

  const beginEdit = (sale) => {
    setEditingSale({
      id: sale.id,
      product_name: sale.product_name || "",
      quantity: sale.quantity,
      unit_sale_price: sale.unit_sale_price,
      sale_date: toLocalDateTime(sale.sale_date),
    });
    setHistoryMessage("");
  };

  const saveSaleEdit = async (e) => {
    e.preventDefault();
    try {
      await api.put(`/sales/${editingSale.id}`, {
        product_name: editingSale.product_name.trim(),
        quantity: Number(editingSale.quantity),
        unit_sale_price: Number(editingSale.unit_sale_price),
        sale_date: new Date(editingSale.sale_date).toISOString(),
      });
      setEditingSale(null);
      setHistoryMessage("Продажа обновлена");
      await loadProducts();
      await loadHistory();
    } catch (err) {
      setHistoryMessage(err.response?.data?.detail || "Ошибка изменения продажи");
    }
  };

  const deleteSale = async (saleId) => {
    if (!window.confirm("Удалить эту продажу? Для продажи со склада остаток вернётся на склад.")) {
      return;
    }
    try {
      await api.delete(`/sales/${saleId}`);
      if (editingSale?.id === saleId) setEditingSale(null);
      setHistoryMessage("Продажа удалена");
      await loadProducts();
      await loadHistory();
    } catch (err) {
      setHistoryMessage(err.response?.data?.detail || "Ошибка удаления продажи");
    }
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Продажи</h1>
          <p className="muted">{isLead ? "Регистрация и редактирование продаж по лавочкам" : "Регистрация ваших продаж"}</p>
        </div>
        <div className="row sales-page-actions">
          <button type="button" onClick={() => setHistoryOpen(true)}>
            История продаж
          </button>
          <button type="button" className="primary" onClick={() => setReportOpen(true)}>
            Отчёт для Telegram
          </button>
        </div>
      </div>

      {!readOnly && <div className="card">
        <form className="form-grid" onSubmit={submit}>
          <div className="row">
            <button
              type="button"
              className={saleType === "inventory" ? "primary" : ""}
              onClick={() => setSaleType("inventory")}
            >
              Со склада
            </button>
            <button
              type="button"
              className={saleType === "manual" ? "primary" : ""}
              onClick={() => {
                setSaleType("manual");
              }}
            >
              Без добавления товара
            </button>
          </div>

          {saleType === "inventory" ? (
            <div className="inventory-sale-lines">
              {inventoryItems.map((line, index) => (
                <div className="inventory-sale-line" key={index}>
                  <label>
                    Товар {index + 1}
                    <select
                      value={line.product_id}
                      onChange={(event) => setInventoryItems(inventoryItems.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, product_id: event.target.value } : item
                      ))}
                      required
                    >
                      <option value="">Выберите товар со склада</option>
                      {products.map((product) => (
                        <option key={product.id} value={product.id}>
                          {product.name} — осталось {product.quantity}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Количество
                    <input
                      type="number"
                      min="1"
                      value={line.quantity}
                      onChange={(event) => setInventoryItems(inventoryItems.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, quantity: event.target.value } : item
                      ))}
                      required
                    />
                  </label>
                  <label>
                    Сумма строки (необязательно)
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      placeholder="По цене товара"
                      value={line.total_amount}
                      onChange={(event) => setInventoryItems(inventoryItems.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, total_amount: event.target.value } : item
                      ))}
                    />
                  </label>
                  <button
                    type="button"
                    className="danger"
                    disabled={inventoryItems.length === 1}
                    onClick={() => setInventoryItems(inventoryItems.filter((_, itemIndex) => itemIndex !== index))}
                    aria-label={`Удалить строку товара ${index + 1}`}
                  >
                    Убрать
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={() => setInventoryItems([
                  ...inventoryItems,
                  { product_id: "", quantity: 1, total_amount: "" },
                ])}
              >
                + Добавить товар
              </button>
            </div>
          ) : (
            <>
              <select
                value={manualNameCustom ? "__custom__" : manualName}
                onChange={(event) => {
                  const isCustom = event.target.value === "__custom__";
                  setManualNameCustom(isCustom);
                  setManualName(isCustom ? "" : event.target.value);
                }}
                required
              >
                <option value="">Выберите товар или услугу</option>
                {REPORT_SALE_PRESETS.map((name) => <option key={name} value={name}>{name}</option>)}
                <option value="__custom__">Другое название…</option>
              </select>
              {manualNameCustom && (
                <input
                  placeholder="Введите название товара или услуги"
                  value={manualName}
                  onChange={(event) => setManualName(event.target.value)}
                  required
                />
              )}
      {canSelectReportStore && (
                <select required={isLead} value={manualSaleStoreId} onChange={(event) => setManualSaleStoreId(event.target.value)}>
                  <option value="">{isLead ? "Выберите лавочку" : "Основная лавочка"}</option>
                  {stores.filter((store) => store.is_active).map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}
                </select>
              )}
              <input
                type="number"
                min="0"
                step="0.01"
                placeholder="Цена продажи за единицу"
                value={manualSalePrice}
                onChange={(e) => setManualSalePrice(e.target.value)}
                required
              />
            </>
          )}

          {saleType === "manual" && (
            <input
              type="number"
              min="1"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
            />
          )}

          <input
            type="datetime-local"
            value={saleDate}
            onChange={(e) => setSaleDate(e.target.value)}
          />

          <div className="summary-box">
            <div>Сумма: {total.toLocaleString("ru-RU")} сом</div>
            <div>Прибыль: {profit.toLocaleString("ru-RU")} сом</div>
          </div>

          <button className="primary" type="submit">
            Сохранить продажу
          </button>
        </form>
        {message && <div className="notice">{message}</div>}
      </div>}

      {historyOpen && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              setHistoryOpen(false);
              setEditingSale(null);
            }
          }}
        >
          <section className="sales-history-modal" role="dialog" aria-modal="true" aria-labelledby="sales-history-title">
            <div className="modal-header">
              <div>
                <h2 id="sales-history-title">История продаж</h2>
                <p className="muted">Выберите день, чтобы посмотреть продажи за эту дату.</p>
              </div>
              <button
                type="button"
                aria-label="Закрыть историю"
                onClick={() => {
                  setHistoryOpen(false);
                  setEditingSale(null);
                }}
              >
                Закрыть
              </button>
            </div>

            <div className="history-toolbar">
              <label>
                День продаж
                <input
                  type="date"
                  value={historyDate}
                  onChange={(event) => setHistoryDate(event.target.value)}
                />
              </label>
              <div className="history-summary">Продаж за день: {sales.length}</div>
            </div>

            {historyMessage && <div className="notice">{historyMessage}</div>}
            {editingSale && (
              <form className="form-grid history-edit-form" onSubmit={saveSaleEdit}>
                <input
                  placeholder="Название товара"
                  value={editingSale.product_name}
                  onChange={(e) => setEditingSale({ ...editingSale, product_name: e.target.value })}
                  required
                />
                <input
                  type="number"
                  min="1"
                  value={editingSale.quantity}
                  onChange={(e) => setEditingSale({ ...editingSale, quantity: e.target.value })}
                  required
                />
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={editingSale.unit_sale_price}
                  onChange={(e) => setEditingSale({ ...editingSale, unit_sale_price: e.target.value })}
                  required
                />
                <input
                  type="datetime-local"
                  value={editingSale.sale_date}
                  onChange={(e) => setEditingSale({ ...editingSale, sale_date: e.target.value })}
                  required
                />
                <div className="row">
                  <button className="primary" type="submit">Сохранить изменения</button>
                  <button type="button" onClick={() => setEditingSale(null)}>Отмена</button>
                </div>
              </form>
            )}

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Время</th>
                    <th>Товар</th>
                    <th>Кол-во</th>
                    <th>Сумма</th>
                    <th>Прибыль</th>
                    {(isLead || isAdmin) && <><th>Сотрудник</th><th>Лавочка</th></>}
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {historyLoading ? (
                    <tr><td colSpan={isLead || isAdmin ? 8 : 6}>Загрузка истории...</td></tr>
                  ) : sales.length ? (
                    sales.map((sale) => (
                      <tr key={sale.id}>
                        <td>{new Date(sale.sale_date).toLocaleTimeString("ru-RU")}</td>
                        <td>{sale.product_name || "Товар недоступен"}</td>
                        <td>{sale.quantity}</td>
                        <td>{sale.total_amount} сом</td>
                        <td>{sale.profit} сом</td>
        {(isLead || isAdmin) && <><td>{sale.seller_name || "Не указан"}</td><td>{sale.store_name || "—"}</td></>}
                        <td className="actions">
                          <button type="button" onClick={() => beginEdit(sale)}>Изменить</button>
                          <button type="button" className="danger" onClick={() => deleteSale(sale.id)}>Удалить</button>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr><td colSpan={isLead || isAdmin ? 8 : 6}>За выбранный день продаж нет</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}

      {reportOpen && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={(event) => {
            if (event.target === event.currentTarget) setReportOpen(false);
          }}
        >
          <section className="sales-history-modal report-modal" role="dialog" aria-modal="true" aria-labelledby="sales-report-title">
            <div className="modal-header">
              <div>
                <h2 id="sales-report-title">Отчёт для Telegram</h2>
                <p className="muted">Отчёт по проданным товарам за выбранный день или месяц.</p>
              </div>
              <button type="button" onClick={() => setReportOpen(false)}>Закрыть</button>
            </div>

            <label className="report-date-label">
              Период отчёта
              <select value={reportPeriod} onChange={(event) => setReportPeriod(event.target.value)}>
                <option value="day">За день</option>
                <option value="month">За месяц</option>
              </select>
            </label>
            {reportPeriod === "day" ? (
              <label className="report-date-label">
                День отчёта
                <input
                  type="date"
                  value={reportDate}
                  onChange={(event) => setReportDate(event.target.value)}
                />
              </label>
            ) : (
              <label className="report-date-label">
                Месяц отчёта
                <input
                  type="month"
                  value={reportMonth}
                  onChange={(event) => setReportMonth(event.target.value)}
                />
              </label>
            )}

            {canSelectReportStore && (
              <label className="report-date-label">
                Лавочка отчёта
                <select value={reportStoreId} onChange={(event) => setReportStoreId(event.target.value)}>
                  {stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}
                </select>
              </label>
            )}

            {canEditDailySettings && reportPeriod === "day" && (
              <section className="daily-report-settings">
                <h3>Данные кассы за день</h3>
                <label>Лимит ДС<input maxLength={100} value={dailySettings.cash_limit} onChange={(event) => setDailySettings({ ...dailySettings, cash_limit: event.target.value })} /></label>
                <label>Остаток ДС<input maxLength={100} value={dailySettings.cash_remaining} onChange={(event) => setDailySettings({ ...dailySettings, cash_remaining: event.target.value })} /></label>
                <label>Инкассация<input maxLength={100} value={dailySettings.collection_status} onChange={(event) => setDailySettings({ ...dailySettings, collection_status: event.target.value })} /></label>
                <button type="button" onClick={saveDailySettings}>Сохранить данные кассы</button>
              </section>
            )}

            {reportLoading ? (
              <div className="notice">Формирую отчёт...</div>
            ) : (
              <textarea className="report-text" readOnly value={reportText} />
            )}
            {reportMessage && <div className="notice">{reportMessage}</div>}

            {canSendFullReport && <div className="telegram-settings">
              <h3>Отправка в Telegram</h3>
              {isAdmin && <label className="telegram-key-label">
                Ключ администратора
                <input
                  type="password"
                  autoComplete="new-password"
                  placeholder="Задаётся в переменной TELEGRAM_ADMIN_KEY на Render"
                  value={telegramAdminKey}
                  onChange={(event) => setTelegramAdminKey(event.target.value)}
                />
              </label>}
              <p className="small">{isLead ? "Ведущий отправляет полный отчёт, используя свою роль Telegram." : "Ключ действует только пока открыта эта страница и не сохраняется в браузере."}</p>
              <div className="row report-actions">
                <button type="button" className="primary" disabled={reportSending || reportLoading} onClick={sendReportNow}>
                  {reportSending ? "Отправляю…" : "Отправить отчёт сейчас"}
                </button>
              </div>

              {isAdmin && <form className="telegram-schedule-form" onSubmit={saveTelegramSchedule}>
                <label className="telegram-toggle">
                  <input
                    type="checkbox"
                    checked={telegramSchedule.enabled}
                    onChange={(event) => setTelegramSchedule({ ...telegramSchedule, enabled: event.target.checked })}
                  />
                  <span>Отправлять отчёт ежедневно автоматически</span>
                </label>
                <div className="telegram-schedule-fields">
                  <label>
                    Время отправки
                    <input
                      type="time"
                      value={telegramSchedule.send_time}
                      onChange={(event) => setTelegramSchedule({ ...telegramSchedule, send_time: event.target.value })}
                      required
                    />
                  </label>
                  <label>
                    Часовой пояс
                    <select
                      value={telegramSchedule.timezone}
                      onChange={(event) => setTelegramSchedule({ ...telegramSchedule, timezone: event.target.value })}
                    >
                      <option value="Asia/Almaty">Алматы (UTC+5)</option>
                      <option value="Asia/Bishkek">Бишкек (UTC+6)</option>
                      <option value="Europe/Moscow">Москва</option>
                      <option value="UTC">UTC</option>
                    </select>
                  </label>
                </div>
                <button type="submit" disabled={reportSending}>Сохранить расписание</button>
                <p className="small">Последняя отправка: {telegramSchedule.last_sent_on || "ещё не отправлялся"}. Время доставки зависит от доступности сервера.</p>
              </form>}
            </div>}

            <div className="row report-actions">
              <button type="button" className="primary" disabled={reportLoading} onClick={copyReport}>
                Скопировать текст
              </button>
              <button type="button" disabled={reportLoading} onClick={shareReportToTelegram}>
                Открыть Telegram
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
