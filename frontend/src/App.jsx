import React, { lazy, Suspense } from "react";
import { Routes, Route, NavLink } from "react-router-dom";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const Products = lazy(() => import("./pages/Products"));
const Sales = lazy(() => import("./pages/Sales"));
const Goals = lazy(() => import("./pages/Goals"));

function Layout({ children }) {
  const navigation = [
    { to: "/", label: "Обзор", icon: "overview" },
    { to: "/products", label: "Товары", icon: "products" },
    { to: "/sales", label: "Продажи", icon: "sales" },
    { to: "/goals", label: "Мои цели", icon: "goals" },
  ];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M4 7.5 12 3l8 4.5v9L12 21l-8-4.5v-9Z" />
              <path d="m4.5 7.8 7.5 4.3 7.5-4.3M12 12v8.5" />
            </svg>
          </span>
          <span className="brand-copy">
            <strong>Склад+</strong>
            <small>учёт продаж</small>
          </span>
        </div>
        <nav aria-label="Основная навигация">
          {navigation.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"}>
              <svg className="nav-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                {item.icon === "overview" && <><path d="M4 10.5 12 4l8 6.5v8a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5v-8Z" /><path d="M9 20v-6h6v6" /></>}
                {item.icon === "products" && <><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z" /><path d="m4.5 7.8 7.5 4.3 7.5-4.3M12 12v8.5" /></>}
                {item.icon === "sales" && <><path d="M4 19V5M4 19h16" /><path d="m7 15 4-4 3 2 5-6" /><path d="M16 7h3v3" /></>}
                {item.icon === "goals" && <><circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="4.5" /><path d="m12 12 6-6" /></>}
              </svg>
              <span>{item.label}</span>
            </NavLink>
          ))}
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
