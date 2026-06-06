# Flower AI Platform Roadmap

## Product Goal

Multi-tenant SaaS for flower shops:

- Customer opens one Telegram bot.
- Bot asks for city and shows shops in that city.
- Customer selects a shop.
- AI assistant collects bouquet wishes in one compact message.
- AI checks real inventory, prices, color compatibility, and budget.
- Customer receives an approximate bouquet description and generated preview image.
- After confirmation, the order is saved and sent to the shop's Telegram manager group.

## Phase 1: Stable MVP

- Keep one backend and one Telegram bot for many shops.
- Use `shop_id` everywhere for tenant separation.
- Run PostgreSQL in Docker.
- Run bot and backend as services, not from a local terminal.
- Add FastAPI backend with health/status endpoints.
- Keep Telegram bot polling for development and VPS deployment.
- Use manager group binding through `/bind_shop <slug>`.

## Phase 2: Realistic Order Flow

- City-based shop selection.
- Inventory-aware AI prompt.
- Bouquet compatibility rules.
- Deterministic price calculation from database flower prices.
- AI asks for all missing details at once to reduce token/API usage.
- Limit AI requests per order.
- Confirmation step before creating an order.
- Manager group notification after confirmation.

## Phase 3: Image Preview

- Generate a bouquet preview only after the text order is nearly complete.
- Use selected flowers, colors, style, and budget in the image prompt.
- Store generated image URL in `orders.generated_image_url`.
- Make clear to the customer that the image is approximate.

## Phase 4: Admin Backend

- Shop admin login.
- CRUD for flowers, prices, stock, photos, bouquet examples.
- Shop settings: greeting, working hours, delivery price, manager group.
- Order dashboard.
- Conversation history.

## Phase 5: Production Deployment

- VPS or cloud server.
- Docker Compose for PostgreSQL, backend, and bot.
- Managed backups for PostgreSQL.
- Logging and error monitoring.
- HTTPS domain for backend.
- Optional Telegram webhook instead of polling.

## Phase 6: SaaS Hardening

- Per-shop subscriptions and usage limits.
- Billing.
- Role-based shop access.
- Audit logs.
- Data export.
- Rate limits and abuse protection.
