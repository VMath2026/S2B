# Flower AI Platform

Multi-tenant Telegram/AI platform for flower shops.

## What It Does

- One Telegram bot serves many flower shops.
- User enters a city and selects a shop.
- AI assistant collects bouquet wishes in a compact flow.
- AI checks shop inventory and flower prices.
- Customer confirms the order.
- Order is saved and sent to the shop manager Telegram group.
- Customer can pay the order through Telegram Payments when configured.
- Bot validates delivery date, phone, budget, and address before creating orders.
- Bot can generate a visual bouquet preview when image generation is enabled.

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
OPENAI_IMAGE_MODEL=gpt-image-1
OPENAI_IMAGE_SIZE=1024x1024
OPENAI_IMAGE_QUALITY=low
OPENAI_IMAGE_FORMAT=png
ADMIN_API_KEY=
APP_BASE_URL=https://your-render-service.onrender.com
TELEGRAM_WEBHOOK_SECRET=
DEFAULT_MANAGER_CHAT_ID=
PAYMENT_PROVIDER_TOKEN=
PAYMENT_CURRENCY=RUB
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

Supported delivery date examples in Telegram: `сегодня`, `завтра`,
`послезавтра`, `пятница`, `12.06`, `12.06.2026`, `2026-06-12`, `12 июня`.
Impossible dates and dates in the past are rejected.

To send every new order to a manager Telegram group, add the bot to that group,
send `/chat_id` in the group, then put the returned numeric chat id into
`DEFAULT_MANAGER_CHAT_ID` on Render and redeploy. For a specific shop, send
`/bind_shop cvety-u-doma` in the manager group instead.

Manager group commands:

```text
/orders
/reply 12 текст сообщения клиенту
```

To enable online payment after order confirmation, connect a Telegram Payments
provider in BotFather and put its token into `PAYMENT_PROVIDER_TOKEN`. The bot
will send an invoice to the customer after the order is created and will notify
the manager group when the payment succeeds.

To enable bouquet preview images, keep `OPENAI_API_KEY` set, configure
`OPENAI_IMAGE_MODEL`, `OPENAI_IMAGE_SIZE`, `OPENAI_IMAGE_QUALITY`, and
`OPENAI_IMAGE_FORMAT`, then enable `image_generation_enabled` in the shop
settings from the admin panel. The bot shows the image button only after the
customer selects a bouquet option, and reuses the same Telegram image if the
button is pressed again.

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
