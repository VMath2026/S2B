# Admin API

The admin API is served by FastAPI from `app.backend:app`.

## Run Locally

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.backend:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/docs
```

## Auth

Admin endpoints require:

```text
X-Admin-Key: <ADMIN_API_KEY from .env>
```

For production, replace the local development value with a long random secret.

## Useful Endpoints

```text
GET    /admin/shops/{shop_id}/flowers
POST   /admin/shops/{shop_id}/flowers
PATCH  /admin/flowers/{flower_id}
DELETE /admin/flowers/{flower_id}

GET    /admin/shops/{shop_id}/settings
PATCH  /admin/shops/{shop_id}/settings

GET    /admin/shops/{shop_id}/orders
PATCH  /admin/orders/{order_id}/status
```

## Example: Add Flower

```powershell
curl.exe -X POST http://127.0.0.1:8000/admin/shops/1/flowers `
  -H "Content-Type: application/json" `
  -H "X-Admin-Key: dev-admin-key-change-me" `
  -d "{\"name\":\"Пион\",\"category\":\"peony\",\"color\":\"pink\",\"price_per_stem\":350,\"quantity_available\":30}"
```

## Example: Update Stock

```powershell
curl.exe -X PATCH http://127.0.0.1:8000/admin/flowers/1 `
  -H "Content-Type: application/json" `
  -H "X-Admin-Key: dev-admin-key-change-me" `
  -d "{\"quantity_available\":100,\"price_per_stem\":190}"
```
