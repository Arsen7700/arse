# Учёт товаров, продаж и месячных целей

Full-stack приложение: React + Vite, FastAPI, SQLAlchemy. Для локальной разработки используется SQLite. Production-конфигурация поддерживает PostgreSQL через `DATABASE_URL`.

## Структура

```text
backend/       FastAPI API, SQLAlchemy models, tests
frontend/      React + Vite application
DEPLOY.md      Подробная инструкция локального запуска и деплоя
```

## Быстрый запуск в Windows / VS Code

Откройте два терминала.

### Backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

API будет доступен на `http://127.0.0.1:8000`, документация — `http://127.0.0.1:8000/docs`. SQLite создаётся автоматически в текущей рабочей папке backend. Не удаляйте `inventory.db`, если в нём есть нужные данные.

### Frontend

```powershell
cd frontend
Copy-Item .env.example .env
pnpm install
pnpm dev
```

Vite напечатает локальный адрес (обычно `http://localhost:5173`). `VITE_API_URL` можно изменить в `frontend/.env`. После изменения переменных перезапустите Vite.

## Основные API

```text
GET/POST          /categories
GET/POST          /products
PUT/DELETE        /products/{id}
PATCH             /products/{id}/stock
GET/POST          /sales
GET/PUT           /goals/{year}/{month}, /goals
GET/PUT           /product-goals/{year}/{month}, /product-goals
GET               /dashboard
GET               /reports/monthly
GET/PUT           /telegram/schedule (PUT требует X-Telegram-Admin-Key)
POST              /telegram/send-report (требует X-Telegram-Admin-Key)
POST              /seed (только если APP_ENV не production)
```

Продажа уменьшает склад условным атомарным обновлением. Сумма продажи и валовая прибыль фиксируются по ценам на момент продажи. Прибыль учитывает только закупочную цену и не вычитает прочие расходы.

## Проверки

Backend-тесты находятся в `backend/tests`:

```powershell
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest
```

Frontend production build:

```powershell
cd frontend
pnpm install
pnpm build
```

Перед публичным запуском настройте CORS и учтите, что приложение пока не имеет входа в систему или разграничения прав. CORS не заменяет авторизацию: API позволяет клиенту менять данные. Не публикуйте рабочие данные до внедрения аутентификации или защиты API на доверенном уровне.

Подробная инструкция Render/Vercel и миграции SQLite → PostgreSQL: [DEPLOY.md](DEPLOY.md).
