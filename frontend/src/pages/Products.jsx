import React, { useEffect, useState } from "react";
import { api } from "../api";
import { PLAN_FACT_GROUPS } from "../planFact";

export default function Products() {
  const [products, setProducts] = useState([]);
  const [stores, setStores] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.get("/products"), api.get("/stores")])
      .then(([productResponse, storeResponse]) => {
        setProducts(productResponse.data.filter((product) => product.is_plan_fact));
        setStores(storeResponse.data);
      })
      .catch((err) => setError(err.response?.data?.detail || "Не удалось загрузить показатели план-факта"));
  }, []);

  const productByStoreAndName = new Map(
    products.map((product) => [`${product.store_id}:${product.name}`, product])
  );

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Показатели план-факта</h1>
          <p className="muted">Категории для учёта продаж. Складские цены и остатки для них не используются.</p>
        </div>
      </div>

      {error && <div className="notice">{error}</div>}
      {stores.filter((store) => store.is_active).map((store) => (
        <section className="card" key={store.id}>
          <h2 className="section-title">{store.name}</h2>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Показатель</th><th>Тип факта</th></tr></thead>
              <tbody>
                {PLAN_FACT_GROUPS.map((group) => {
                  const parentExists = productByStoreAndName.has(`${store.id}:${group.name}`);
                  if (!parentExists) return null;
                  return <React.Fragment key={group.name}>
                    <tr><td><strong>{group.name}</strong></td><td>Количество</td></tr>
                    {group.children.map((child) => {
                      const product = productByStoreAndName.get(`${store.id}:${child}`);
                      return product && <tr key={product.id}>
                        <td className="plan-fact-child">↳ {child}</td>
                        <td>{child === "Услуги" ? "Сумма" : "Количество"}</td>
                      </tr>;
                    })}
                  </React.Fragment>;
                })}
              </tbody>
            </table>
          </div>
        </section>
      ))}
      {!error && products.length === 0 && <div className="card">Показатели план-факта ещё не загружены. Перезапустите сервер API, чтобы применить обновление каталога.</div>}
    </>
  );
}
