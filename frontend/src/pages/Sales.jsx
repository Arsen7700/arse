import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api";

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
  const [products, setProducts] = useState([]);
  const [sales, setSales] = useState([]);
  const [saleType, setSaleType] = useState("inventory");
  const [productId, setProductId] = useState("");
  const [manualName, setManualName] = useState("");
  const [manualSalePrice, setManualSalePrice] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [saleDate, setSaleDate] = useState(() => toLocalDateTime(new Date()));
  const [message, setMessage] = useState("");
  const [historyMessage, setHistoryMessage] = useState("");
  const [editingSale, setEditingSale] = useState(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyDate, setHistoryDate] = useState(() => localDateInputValue(new Date()));
  const [historyLoading, setHistoryLoading] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [reportDate, setReportDate] = useState(() => localDateInputValue(new Date()));
  const [reportSales, setReportSales] = useState([]);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportMessage, setReportMessage] = useState("");
  const [reportSending, setReportSending] = useState(false);
  const [telegramAdminKey, setTelegramAdminKey] = useState("");
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
    if (historyOpen) loadHistory();
  }, [historyOpen, historyDate]);

  useEffect(() => {
    const loadReport = async () => {
      if (!reportOpen || !reportDate) return;
      const [year, month, day] = reportDate.split("-").map(Number);
      const nextDate = new Date(Date.UTC(year, month - 1, day + 1)).toISOString().slice(0, 10);
      const start = dateAtTimezoneUtc(reportDate, telegramSchedule.timezone);
      const end = dateAtTimezoneUtc(nextDate, telegramSchedule.timezone);
      setReportLoading(true);
      setReportMessage("");
      try {
        const response = await api.get("/sales", {
          params: { start: start.toISOString(), end: end.toISOString() },
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
  }, [reportOpen, reportDate, telegramSchedule.timezone]);

  useEffect(() => {
    if (!reportOpen) return;
    api.get("/telegram/schedule")
      .then((response) => setTelegramSchedule(response.data))
      .catch(() => setReportMessage("Не удалось загрузить настройки отправки"));
  }, [reportOpen]);

  const selected = useMemo(
    () => products.find((p) => p.id === Number(productId)),
    [products, productId]
  );

  const salePrice = saleType === "inventory"
    ? selected?.sale_price || 0
    : Number(manualSalePrice || 0);
  const purchasePrice = saleType === "inventory"
    ? selected?.purchase_price || 0
    : 0;
  const total = salePrice * Number(quantity || 0);
  const profit = (salePrice - purchasePrice) * Number(quantity || 0);
  const reportByProduct = new Map();
  reportSales.forEach((sale) => {
    const name = sale.product_name || "Товар без названия";
    const item = reportByProduct.get(name) || {
      product_name: name,
      quantity: 0,
      revenue: 0,
    };
    item.quantity += sale.quantity;
    item.revenue += sale.total_amount;
    reportByProduct.set(name, item);
  });
  const reportLines = [...reportByProduct.values()]
    .sort((a, b) => a.product_name.localeCompare(b.product_name, "ru"))
    .map((item) => {
      const averagePrice = item.quantity ? item.revenue / item.quantity : 0;
      return `• ${item.product_name} — ${item.quantity} шт.; средняя цена ${averagePrice.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} сом; сумма ${item.revenue.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} сом`;
    });
  const reportQuantity = [...reportByProduct.values()].reduce((sum, item) => sum + item.quantity, 0);
  const reportText = [
    `Отчёт о продажах за ${reportDate ? new Date(`${reportDate}T00:00:00`).toLocaleDateString("ru-RU") : ""}`,
    "",
    ...(reportLines.length ? reportLines : ["За выбранный день продаж нет."]),
    "",
    `Всего продано: ${reportQuantity} шт.`,
  ].join("\n");

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
    if (!telegramAdminKey) {
      setReportMessage("Введите ключ администратора Telegram из настроек Render");
      return;
    }
    setReportSending(true);
    setReportMessage("");
    try {
      const response = await api.post(
        "/telegram/send-report",
        { report_date: reportDate },
        { headers: { "X-Telegram-Admin-Key": telegramAdminKey } }
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
      const payload = {
        quantity: Number(quantity),
        sale_date: new Date(saleDate).toISOString(),
      };
      if (saleType === "inventory") {
        payload.product_id = Number(productId);
      } else {
        payload.product_name = manualName.trim();
        payload.unit_sale_price = Number(manualSalePrice);
      }
      await api.post("/sales", payload);
      setMessage("Продажа сохранена");
      setQuantity(1);
      if (saleType === "manual") {
        setManualName("");
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
          <p className="muted">Регистрация продаж</p>
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

      <div className="card">
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
              onClick={() => setSaleType("manual")}
            >
              Без добавления товара
            </button>
          </div>

          {saleType === "inventory" ? (
            <select
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
              required
            >
              <option value="">Выберите товар со склада</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} — осталось {p.quantity}
                </option>
              ))}
            </select>
          ) : (
            <>
              <input
                placeholder="Название товара"
                value={manualName}
                onChange={(e) => setManualName(e.target.value)}
                required
              />
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

          <input
            type="number"
            min="1"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
          />

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
      </div>

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
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {historyLoading ? (
                    <tr><td colSpan="6">Загрузка истории...</td></tr>
                  ) : sales.length ? (
                    sales.map((sale) => (
                      <tr key={sale.id}>
                        <td>{new Date(sale.sale_date).toLocaleTimeString("ru-RU")}</td>
                        <td>{sale.product_name || "Товар недоступен"}</td>
                        <td>{sale.quantity}</td>
                        <td>{sale.total_amount} сом</td>
                        <td>{sale.profit} сом</td>
                        <td className="actions">
                          <button type="button" onClick={() => beginEdit(sale)}>Изменить</button>
                          <button type="button" className="danger" onClick={() => deleteSale(sale.id)}>Удалить</button>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr><td colSpan="6">За выбранный день продаж нет</td></tr>
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
                <p className="muted">Отчёт по проданным товарам за выбранный день.</p>
              </div>
              <button type="button" onClick={() => setReportOpen(false)}>Закрыть</button>
            </div>

            <label className="report-date-label">
              День отчёта
              <input
                type="date"
                value={reportDate}
                onChange={(event) => setReportDate(event.target.value)}
              />
            </label>

            {reportLoading ? (
              <div className="notice">Формирую отчёт...</div>
            ) : (
              <textarea className="report-text" readOnly value={reportText} />
            )}
            {reportMessage && <div className="notice">{reportMessage}</div>}

            <div className="telegram-settings">
              <h3>Отправка в Telegram</h3>
              <label className="telegram-key-label">
                Ключ администратора
                <input
                  type="password"
                  autoComplete="new-password"
                  placeholder="Задаётся в переменной TELEGRAM_ADMIN_KEY на Render"
                  value={telegramAdminKey}
                  onChange={(event) => setTelegramAdminKey(event.target.value)}
                />
              </label>
              <p className="small">Ключ действует только пока открыта эта страница и не сохраняется в браузере.</p>
              <div className="row report-actions">
                <button type="button" className="primary" disabled={reportSending || reportLoading} onClick={sendReportNow}>
                  {reportSending ? "Отправляю…" : "Отправить выбранный день сейчас"}
                </button>
              </div>

              <form className="telegram-schedule-form" onSubmit={saveTelegramSchedule}>
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
              </form>
            </div>

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
