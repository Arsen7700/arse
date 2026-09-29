import React, { lazy, Suspense } from "react";
import { Routes, Route, NavLink } from "react-router-dom";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const Products = lazy(() => import("./pages/Products"));
const Sales = lazy(() => import("./pages/Sales"));
const Goals = lazy(() => import("./pages/Goals"));

function Layout({ children }) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">Склад+</div>
        <nav>
          <NavLink to="/">Dashboard</NavLink>
          <NavLink to="/products">Товары</NavLink>
          <NavLink to="/sales">Продажи</NavLink>
          <NavLink to="/goals">Мои цели</NavLink>
        </nav>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}

export default function App() {
  if (import.meta.env.PROD && !window.Telegram?.WebApp?.initData) {
    return (
      <main className="content telegram-only-notice">
        <section className="card">
          <h1>Откройте через Telegram</h1>
          <p className="muted">
            Для безопасного доступа к складу запустите Mini App кнопкой меню в чате с ботом.
          </p>
        </section>
      </main>
    );
  }

  return (
    <Layout>
      <Suspense fallback={<div>Загрузка страницы...</div>}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/products" element={<Products />} />
          <Route path="/sales" element={<Sales />} />
          <Route path="/goals" element={<Goals />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}
