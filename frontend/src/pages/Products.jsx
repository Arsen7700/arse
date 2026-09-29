import React, { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

const emptyForm = {
  name: "",
  category_id: "",
  sale_price: 0,
  quantity: 0,
  description: "",
  image_url: "",
  store_id: "",
};

export default function Products() {
  const user = useAuth();
  const isLead = user?.role === "lead";
  const readOnly = false;
  const isAdmin = user?.role === "admin";
  const canAddProduct = isLead || isAdmin;
  const canSelectStore = isAdmin || isLead;
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [stores, setStores] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [message, setMessage] = useState("");

  const load = async () => {
    const [p, c] = await Promise.all([
      api.get("/products", {
        params: {
          search: search || undefined,
          category_id: categoryFilter || undefined,
        },
      }),
      api.get("/categories"),
    ]);
    setProducts(p.data);
    setCategories(c.data);
  };

  useEffect(() => {
    load();
  }, [search, categoryFilter]);

  useEffect(() => {
    api.get("/stores").then((response) => setStores(response.data)).catch(() => {});
  }, []);

  const save = async (e) => {
    e.preventDefault();
    setMessage("");
    const payload = {
      ...form,
      category_id: form.category_id ? Number(form.category_id) : null,
      sale_price: Number(form.sale_price),
      quantity: Number(form.quantity),
    };
    if (!canSelectStore) delete payload.store_id;

    try {
      if (editingId) {
        await api.put(`/products/${editingId}`, payload);
        setMessage("Товар обновлён");
      } else {
        await api.post("/products", payload);
        setMessage("Товар добавлен");
      }
      setForm(emptyForm);
      setEditingId(null);
      load();
    } catch (err) {
      setMessage(err.response?.data?.detail || "Ошибка сохранения");
    }
  };

  const edit = (p) => {
    setEditingId(p.id);
    setForm({
      name: p.name,
      category_id: p.category_id || "",
      sale_price: p.sale_price,
      quantity: p.quantity,
      description: p.description || "",
      image_url: p.image_url || "",
      store_id: p.store_id || "",
    });
  };

  const remove = async (id) => {
    try {
      await api.delete(`/products/${id}`);
      load();
    } catch (err) {
      alert(err.response?.data?.detail || "Ошибка удаления");
    }
  };

  const changeStock = async (id, amount) => {
    try {
      await api.patch(`/products/${id}/stock`, { amount });
      load();
    } catch (err) {
      alert(err.response?.data?.detail || "Ошибка");
    }
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Товары</h1>
          <p className="muted">{isLead ? "Добавление и редактирование карточек по всем лавочкам; складские остатки доступны администратору" : isAdmin ? "Полное управление товарами и остатками" : "Просмотр товаров лавочки; добавление доступно ведущему или администратору"}</p>
        </div>
      </div>

      {(!readOnly && (canAddProduct || editingId)) && <div className="card">
        <div className="section-title">
          {editingId ? "Редактировать товар" : "Добавить товар"}
        </div>

        <form className="form-grid" onSubmit={save}>
          <input
            placeholder="Название"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
          <select
            value={form.category_id}
            onChange={(e) => setForm({ ...form, category_id: e.target.value })}
          >
            <option value="">Без категории</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          {canSelectStore && (
            <select value={form.store_id} onChange={(e) => setForm({ ...form, store_id: e.target.value })}>
              <option value="">Основная лавочка</option>
              {stores.filter((store) => store.is_active).map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}
            </select>
          )}
          <input
            type="number"
            min="0"
            step="0.01"
            placeholder="Цена продажи"
            value={form.sale_price}
            onChange={(e) => setForm({ ...form, sale_price: e.target.value })}
            required
          />
          {isAdmin && <input
            type="number"
            min="0"
            placeholder="Количество"
            value={form.quantity}
            onChange={(e) => setForm({ ...form, quantity: e.target.value })}
          />}
          <input
            placeholder="URL фото (необязательно)"
            value={form.image_url}
            onChange={(e) => setForm({ ...form, image_url: e.target.value })}
          />
          <textarea
            placeholder="Описание"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <div className="row">
            <button className="primary" type="submit">
              {editingId ? "Сохранить" : "Добавить"}
            </button>
            {editingId && (
              <button
                type="button"
                onClick={() => {
                  setEditingId(null);
                  setForm(emptyForm);
                }}
              >
                Отмена
              </button>
            )}
          </div>
        </form>
        {message && <div className="notice">{message}</div>}
      </div>}

      <div className="card">
        <div className="filters">
          <input
            placeholder="Поиск по названию..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
          >
            <option value="">Все категории</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Название</th>
                {(isAdmin || isLead) && <th>Лавочка</th>}
                <th>Продажа</th>
                <th>Остаток</th>
                {!readOnly && <th>Действия</th>}
              </tr>
            </thead>
            <tbody>
              {products.map((p) => (
                <tr key={p.id}>
                  <td>{p.name}</td>
                  {(isAdmin || isLead) && <td>{stores.find((store) => store.id === p.store_id)?.name || `Лавочка ${p.store_id}`}</td>}
                  <td>{p.sale_price} сом</td>
                  <td>{p.quantity}</td>
                  {!readOnly && <td className="actions">
                    {isAdmin && <><button onClick={() => changeStock(p.id, 1)}>+1</button>
                    <button onClick={() => changeStock(p.id, -1)}>-1</button></>}
                    <button onClick={() => edit(p)}>Изменить</button>
                    <button className="danger" onClick={() => remove(p.id)}>
                      Удалить
                    </button>
                  </td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
