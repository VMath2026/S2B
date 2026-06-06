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
