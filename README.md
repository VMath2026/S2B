# Flower AI Platform

Multi-tenant Telegram/AI platform for flower shops.

## What It Does

- One Telegram bot serves many flower shops.
- User enters a city and selects a shop.
- AI assistant collects bouquet wishes in a compact flow.
- AI checks shop inventory and flower prices.
- Customer confirms the order.
- Order is saved and sent to the shop manager Telegram group.

## Stack

- Python 3.13
- FastAPI
- aiogram
- SQLAlchemy sync engine
- psycopg
- PostgreSQL
- OpenAI API

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill secrets:

```text
BOT_TOKEN=
OPENAI_API_KEY=
ADMIN_API_KEY=
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5433/flower_ai
```

Start PostgreSQL:

```powershell
docker compose up -d postgres
```

Initialize database:

```powershell
python -m app.db.init_db
python -m app.db.seed
```

Run bot:

```powershell
python -m app.main
```

Run backend:

```powershell
uvicorn app.backend:app --host 127.0.0.1 --port 8000
```

Open API docs:

```text
http://127.0.0.1:8000/docs
```

## Render Web Service

Deploy this repository as a Render Web Service. The Dockerfile starts FastAPI on
Render's `$PORT`.

Set these environment variables in Render:

```text
BOT_TOKEN=
OPENAI_API_KEY=
ADMIN_API_KEY=
APP_BASE_URL=https://your-render-service.onrender.com
TELEGRAM_WEBHOOK_SECRET=
DEFAULT_MANAGER_CHAT_ID=
INIT_DATABASE_ON_START=true
SEED_DATABASE_ON_START=true
DATABASE_URL=
```

After deploy, open:

```text
https://your-render-service.onrender.com/
https://your-render-service.onrender.com/health
```

The root URL should return service info. Telegram updates are received at
`/telegram/webhook`; the app registers this webhook automatically on startup when
`BOT_TOKEN` and `APP_BASE_URL` are set.

To send every new order to a manager Telegram group, add the bot to that group,
send `/chat_id` in the group, then put the returned numeric chat id into
`DEFAULT_MANAGER_CHAT_ID` on Render and redeploy. For a specific shop, send
`/bind_shop cvety-u-doma` in the manager group instead.

## Shop Admin Web

The React/TypeScript admin panel lives in `admin-web`.

```powershell
cd admin-web
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

Enter the Render API URL and `ADMIN_API_KEY`, then select a shop to manage
products, inventory, prices, and shop settings.

For Vercel, import the GitHub repository and set the project root directory to:

```text
admin-web
```
