import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles.css";

const telegramWebApp = window.Telegram?.WebApp;
telegramWebApp?.ready();
telegramWebApp?.setHeaderColor?.("#111827");
telegramWebApp?.setBackgroundColor?.("#0b1220");

if (telegramWebApp) {
  // Keep Telegram's minimize/close swipe from intercepting vertical page scrolling.
  try {
    telegramWebApp.disableVerticalSwipes?.();
  } catch {
    // Older Telegram clients may not support the swipe behavior API.
  }

  const syncFullscreenState = () => {
    document.documentElement.classList.toggle(
      "telegram-fullscreen",
      Boolean(telegramWebApp.isFullscreen)
    );
  };
  const fallbackToExpandedView = () => {
    telegramWebApp.expand();
    syncFullscreenState();
  };

  telegramWebApp.onEvent?.("fullscreenChanged", syncFullscreenState);
  telegramWebApp.onEvent?.("fullscreenFailed", fallbackToExpandedView);
  syncFullscreenState();
  telegramWebApp.expand();

  if (typeof telegramWebApp.requestFullscreen === "function") {
    try {
      telegramWebApp.requestFullscreen();
    } catch {
      fallbackToExpandedView();
    }
  } else {
    fallbackToExpandedView();
  }
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
