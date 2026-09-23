# Развёртывание Inventory Dashboard

Инструкция для Windows и VS Code. Проект состоит из frontend на Vite и API на FastAPI. В разработке используется SQLite; для Render рекомендуется отдельная PostgreSQL база.

## 1. Установка и локальный запуск

Установите Python 3.10+ и Node.js LTS, затем откройте папку проекта в VS Code. Команды запускайте из PowerShell.

### Backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

При запрете запуска скриптов в PowerShell откройте терминал `cmd` и активируйте командой `.venv\Scripts\activate.bat`. API: `http://127.0.0.1:8000`; Swagger: `http://127.0.0.1:8000/docs`. При первом старте SQLite-файл `backend/inventory.db` создаётся автоматически, если команда запущена из `backend`.

### Frontend

Во втором терминале:

```powershell
cd frontend
Copy-Item .env.example .env
pnpm install
pnpm dev
```

Если у вас нет pnpm, установите его через `corepack enable`, либо используйте `npm install` и `npm run dev`. Откройте Vite URL из вывода терминала. Для production build выполните `pnpm build` (либо `npm run build`); файлы будут в `frontend/dist`.

## 2. Переменные окружения

Локальные образцы лежат в `backend/.env.example` и `frontend/.env.example`. Реальные `.env` файлы игнорируются Git.

| Переменная | Где | Значение |
| --- | --- | --- |
| `DATABASE_URL` | Render backend | Internal URL PostgreSQL, выданный Render; локально по умолчанию SQLite |
| `APP_ENV` | Render backend | `production` (отключает endpoint тестового заполнения `/seed`) |
| `CORS_ORIGINS` | Render backend | Полный origin сайта Vercel, например `https://ваш-домен.vercel.app` (без завершающего `/`); несколько origin перечисляются через запятую |
| `VITE_API_URL` | Vercel frontend | Полный базовый URL Web Service Render, например `https://имя-сервиса.onrender.com` (без `/` в конце) |

Переменные Vite встраиваются в frontend при сборке. После изменения `VITE_API_URL` на Vercel запустите новый deploy. Никогда не помещайте пароли, токены и production URL с учётными данными в Git или `VITE_*` переменные.

## 3. Git и GitHub

В переданной папке изначально не было Git-репозитория и remote. Локальный Git-репозиторий уже инициализирован на ветке `main`, но коммита и remote пока нет. Создайте пустой репозиторий на GitHub через веб-интерфейс, затем из корня проекта (папка, где лежат `backend`, `frontend`, `README.md` и этот файл) выполните:

```powershell
git add .
git status --short
git commit -m "Prepare inventory dashboard for deployment"
git remote add origin <URL-вашего-GitHub-репозитория>
git push -u origin main
```

Замените текст в угловых скобках URL-ом репозитория, например адресом, который GitHub показывает кнопкой **Code**. Проверьте `git status` перед commit. Не добавляйте `.env`, `backend/.venv`, `frontend/node_modules` или SQLite файл. Если Git спрашивает имя/email, задайте их командами `git config --global user.name "Ваше имя"` и `git config --global user.email "ваш email"`.

Если локально уже есть Git-репозиторий, не запускайте `git init`; сначала проверьте `git status` и `git remote -v`, затем настройте нужный remote.

## 4. PostgreSQL и сохранение существующих данных

Backend выбирает базу по `DATABASE_URL`. Без этой переменной локально остаётся `sqlite:///./inventory.db`; SQLite получает нужные параметры соединения, для PostgreSQL добавлен драйвер psycopg. В Render задайте `DATABASE_URL` значением Internal Database URL из панели Render. При старте приложение сохраняет существующие продажи и автоматически обновляет структуру таблицы продаж для поддержки продаж без товара из каталога. Таблица отдельных месячных целей каждого товара создаётся автоматически; прежняя общая цель остаётся в базе и не удаляется.

Файл SQLite с исходными данными в переданной копии проекта не обнаружен. При запуске backend во время проверки создался локальный `backend/inventory.db` с пустой схемой; он исключён из Git. Поэтому определить, существуют ли пользовательские данные на другом компьютере, невозможно. Никакие данные не переносились. Если SQLite содержит важные данные, используйте безопасный план:

1. Остановите запись в старую базу и сделайте отдельную копию файла `inventory.db` (не перемещайте и не перезаписывайте исходник).
2. Создайте PostgreSQL базу на Render и сохраните её `DATABASE_URL` только в настройках сервиса.
3. Подготовьте перенос данных с проверкой типов и количества записей. Сначала восстановите копию в тестовую PostgreSQL базу, сравните категории, товары, остатки, продажи и цели, проверьте отчёты.
4. На время переключения остановите записи, выполните финальную синхронизацию и контрольные сверки; сохраните исходную SQLite-копию для возврата.
5. Только после проверки переключите production сервис на PostgreSQL и наблюдайте логи. Не удаляйте резервную копию, пока не подтвердили целостность данных.

Перед реальным переносом рекомендуется внедрить Alembic и написать/проверить отдельный импортёр. Простое изменение `DATABASE_URL` не переносит строки из SQLite в PostgreSQL. Миграция в этой поставке не выполнялась.

## 5. Vercel (frontend)

1. Импортируйте GitHub-репозиторий в Vercel.
2. Укажите **Framework Preset: Vite**.
3. **Root Directory: `frontend`** (если корнем GitHub репозитория выбрана папка проекта с `backend` и `frontend`).
4. Build Command: `npm run build`.
5. Output Directory: `dist`.
6. Добавьте `VITE_API_URL` со значением URL опубликованного Render Web Service без завершающего `/`.
7. Запустите deploy. В `frontend/vercel.json` настроен fallback на `index.html` для прямого открытия маршрутов React Router.

Опционально проверить Vercel CLI из `frontend`:

```powershell
npx vercel --version
npx vercel
npx vercel --prod
```

Команда `npx vercel` может попросить установить CLI, войти в аккаунт и связать каталог с проектом. `npx vercel --prod` публикует production версию: выполняйте её только после проверки выбранного Vercel project и переменных. В этой среде проверена версия CLI 59.24.0; реальный deploy не выполнялся, потому что для него нужны ваш Vercel аккаунт и привязка проекта.

## 6. Render (backend)

Создайте PostgreSQL instance, затем Web Service из того же GitHub репозитория:

- **Root Directory:** `backend`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

В Environment добавьте:

- `DATABASE_URL` — Internal Database URL созданного PostgreSQL instance.
- `APP_ENV` — `production`.
- `CORS_ORIGINS` — точный origin Vercel сайта (при нескольких — разделите запятыми).

Не задавайте фиксированный порт: Render передаёт порт через `$PORT`. Uvicorn слушает `0.0.0.0`, чтобы сервис был доступен через Render proxy. Проверка здоровья: откройте `https://<имя-сервиса>.onrender.com/`; ожидается JSON с сообщением `Inventory API is running`. Swagger обычно доступен по `/docs`.

В Render можно прикрепить постоянный диск для SQLite, но это не рекомендуется как production DB: одна копия приложения и дисковая привязка ограничивают масштабирование. Используйте управляемый PostgreSQL и его резервное копирование.

## 7. Проверка после настройки

Локально запустите backend и frontend, затем:

```powershell
cd backend
python -m pytest
cd ..\frontend
pnpm build
```

В браузере создайте товар, измените остаток, оформите продажу со склада, проверьте отказ при превышении остатка. Цена продажи товара может быть нулевой: бесплатная выдача списывает остаток, выручка равна нулю, а прибыль отражает себестоимость как убыток. Затем зарегистрируйте продажу в режиме «Без добавления товара»: задайте название, цену продажи и количество; такая запись не списывает склад. Для неё себестоимость считается равной нулю, поэтому прибыль равна выручке. На странице «Мои цели» задайте на выбранный месяц цель по выручке и количеству отдельно для нескольких товаров и проверьте, что значения сохраняются независимо. После публикации проверьте те же действия и отсутствие CORS ошибок в DevTools. API пока не имеет аутентификации или ролей. Не открывайте его с рабочими данными до внедрения защиты доступа: CORS не предотвращает прямые HTTP запросы.

## 8. Типичные проблемы

- **Frontend не соединяется с API:** проверьте `VITE_API_URL`, выполните новый Vercel deploy после изменения env, убедитесь, что backend отвечает на `/`.
- **CORS ошибка:** внесите origin сайта (scheme + hostname, без пути и завершающего `/`) в `CORS_ORIGINS`; после изменения перезапустите/ redeploy backend.
- **Render не стартует:** проверьте root directory `backend`, build/start команды и логи. Start command обязан читать `$PORT` и слушать `0.0.0.0`.
- **Ошибка соединения с БД:** проверьте `DATABASE_URL`, доступность PostgreSQL и что задан именно Internal URL для сервиса Render. Не вставляйте URL с паролем в код или frontend.
- **Таблицы отсутствуют:** проверьте логи старта. `create_all` создаёт таблицы при старте, но не обновляет структуру уже существующих таблиц. Для изменения схемы нужны миграции.
- **Прямой переход по ссылке Vercel возвращает 404:** проверьте наличие `frontend/vercel.json` и redeploy.
- **Сборка падает:** проверьте Node LTS, вывод `npm install`/`pnpm install`, затем повторите `npm run build`; текст ошибки обычно указывает проблемный импорт или зависимость.
- **Данные исчезли после перезапуска:** локальная SQLite или файловая система ephemeral service не должна считаться резервной production базой. Подключите PostgreSQL и отдельно спланируйте перенос.
