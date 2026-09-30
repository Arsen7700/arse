import React, { lazy, Suspense, useEffect, useState } from "react";
import { Routes, Route, NavLink } from "react-router-dom";
import { api } from "./api";
import { AuthContext, roleLabel } from "./auth";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const Products = lazy(() => import("./pages/Products"));
const Sales = lazy(() => import("./pages/Sales"));
const Goals = lazy(() => import("./pages/Goals"));
const TeamReports = lazy(() => import("./pages/TeamReports"));
const AdminPanel = lazy(() => import("./pages/AdminPanel"));

const icons = {
  overview: <><path d="M4 10.5 12 4l8 6.5v8a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5v-8Z" /><path d="M9 20v-6h6v6" /></>,
  products: <><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z" /><path d="m4.5 7.8 7.5 4.3 7.5-4.3M12 12v8.5" /></>,
  sales: <><path d="M4 19V5M4 19h16" /><path d="m7 15 4-4 3 2 5-6" /><path d="M16 7h3v3" /></>,
  history: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /><path d="M4.5 5.5 3 7" /></>,
  reports: <><path d="M4 19V5M4 19h17" /><path d="M8 16v-4M12 16V8M16 16v-6M20 16V5" /></>,
  goals: <><circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="4.5" /><path d="m12 12 6-6" /></>,
  admin: <><circle cx="12" cy="8" r="3.5" /><path d="M5 20v-1.5a7 7 0 0 1 14 0V20" /><path d="M18 4.5v4M16 6.5h4" /></>,
  team: <><circle cx="9" cy="8" r="3" /><path d="M3 20v-1a6 6 0 0 1 12 0v1" /><path d="M16 5.5a3 3 0 0 1 0 5.8M18 14a5 5 0 0 1 3 4.5V20" /></>,
};

function Layout({ children, user }) {
  const isCashier = user.role === "cashier";
  const navigation = [
    { to: "/", label: "Обзор", icon: "overview" },
    ...(!isCashier ? [{ to: "/products", label: "Товары", icon: "products" }] : []),
    { to: "/sales", label: "Продажи", icon: "sales" },
    { to: "/history", label: "История", icon: "history" },
    { to: "/reports", label: "Отчёты", icon: "reports" },
    ...(user.role === "lead" || user.role === "admin"
      ? [{ to: "/team-reports", label: "Команда", icon: "team" }]
      : user.role === "specialist" || user.role === "cashier"
        ? [{ to: "/goals", label: "Мои цели", icon: "goals" }]
        : []),
    ...(user.role === "admin" ? [{ to: "/admin", label: "Админ", icon: "admin" }] : []),
  ];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none"><path d="M4 7.5 12 3l8 4.5v9L12 21l-8-4.5v-9Z" /><path d="m4.5 7.8 7.5 4.3 7.5-4.3M12 12v8.5" /></svg>
          </span>
          <span className="brand-copy"><strong>Склад+</strong><small>{roleLabel(user.role)}</small></span>
        </div>
        <nav className={`nav-count-${navigation.length}`} aria-label="Основная навигация">
          {navigation.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"}>
              <svg className="nav-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">{icons[item.icon]}</svg>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="content">
        <div className="account-chip"><span className="account-avatar">{user.display_name?.slice(0, 1)?.toUpperCase() || "У"}</span><span>{user.display_name}</span></div>
        {children}
      </main>
    </div>
  );
}

function AuthenticatedApp() {
  const [user, setUser] = useState(null);
  const [authError, setAuthError] = useState("");

  useEffect(() => {
    api.get("/auth/me")
      .then((response) => setUser(response.data))
      .catch((error) => {
        setAuthError(error.response?.data?.detail || "Не удалось загрузить профиль доступа");
      });
  }, []);

  if (authError) {
    const isUnregistered = /не добавлен/i.test(authError);
    return (
      <main className="content telegram-only-notice">
        <section className="card">
          <h1>{isUnregistered ? "Нет доступа" : "Не удалось войти"}</h1>
          <p className="muted">{isUnregistered ? "Попросите администратора добавить ваш Telegram ID и назначить лавочку." : authError}</p>
        </section>
      </main>
    );
  }
  if (!user) return <main className="content"><div className="card">Загружаю профиль…</div></main>;

  return (
    <AuthContext.Provider value={user}>
      <Layout user={user}>
        <Suspense fallback={<div className="card">Загрузка страницы…</div>}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/products" element={user.role === "cashier" ? <Dashboard /> : <Products />} />
            <Route path="/sales" element={<Sales />} />
            <Route path="/history" element={<Sales />} />
            <Route path="/reports" element={<Sales />} />
            <Route path="/goals" element={user.role === "cashier" || user.role === "specialist" ? <Goals /> : <Dashboard />} />
            <Route path="/team-reports" element={user.role === "admin" || user.role === "lead" ? <TeamReports /> : <Dashboard />} />
            <Route path="/admin" element={user.role === "admin" ? <AdminPanel /> : <Dashboard />} />
            <Route path="*" element={<Dashboard />} />
          </Routes>
        </Suspense>
      </Layout>
    </AuthContext.Provider>
  );
}

export default function App() {
  if (import.meta.env.PROD && !window.Telegram?.WebApp?.initData) {
    return (
      <main className="content telegram-only-notice">
        <section className="card">
          <h1>Откройте через Telegram</h1>
          <p className="muted">Для безопасного доступа запустите Mini App кнопкой в чате с ботом.</p>
        </section>
      </main>
    );
  }
  return <AuthenticatedApp />;
}
