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
POST              /telegram/send-report (дневной или месячный; требует X-Telegram-Admin-Key)
POST              /seed (только если APP_ENV не production)
```

Продажа уменьшает склад условным атомарным обновлением. В режиме «Со склада» можно добавить несколько товаров в одну продажу; все строки сохраняются атомарно, и при нехватке любого товара ни одна строка не проводится. Для каждой строки можно оставить сумму по цене товара или указать свою общую сумму сделки; выручка и прибыль фиксируются на момент продажи. Прибыль учитывает только закупочную цену и не вычитает прочие расходы.

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

В production доступ к API защищается проверенной подписью Telegram Mini App. Первого администратора задайте числовым ID в `TELEGRAM_ADMIN_IDS` в Render; затем администратор добавляет остальных сотрудников и их Telegram ID через вкладку «Админ». Пароли не используются.

Роли: специалист видит товары своей лавочки и может редактировать существующие карточки, оформляет и редактирует свои продажи, а также заполняет лимит ДС, остаток ДС и инкассацию в дневном отчёте; добавлять новые товары может только ведущий или администратор. Кассир оформляет и редактирует только собственные продажи своей лавочки, без управления товарами и остатками. Ведущий видит отчёты команды, добавляет и редактирует карточки товаров и продажи лавочек, назначает специалистам/кассирам роли и лавочки, а также может корректировать три дневных поля отчёта. Ручная корректировка остатков доступна только администратору. Администратор управляет всеми аккаунтами, лавочками, товарами и остатками. Новые продажи записывают Telegram ID продавца. Настройки дневного отчёта сохраняются отдельно по лавочке и дате; новая таблица создаётся при старте без удаления прежних данных.

При первом запуске новой версии старые товары и продажи без лавочки будут отнесены к «Основной лавочке». Старые продажи останутся в базе и в отчёте команды будут помечены как записи без известного автора. Сама миграция изменяет схему базы при старте backend; она не копирует данные из SQLite в PostgreSQL. Перед production обновлением сделайте резервную копию PostgreSQL/SQLite и отдельно выполните миграцию данных, если меняете тип базы.

Пользователь должен запускать сайт кнопкой Mini App в Telegram; прямой браузерный доступ к API закрыт. Настройте `TELEGRAM_BOT_TOKEN` и `TELEGRAM_ADMIN_IDS` на Render. Инструкции BotFather и Render/Vercel находятся в [DEPLOY.md](DEPLOY.md).

Подробная инструкция Render/Vercel и миграции SQLite → PostgreSQL: [DEPLOY.md](DEPLOY.md).
