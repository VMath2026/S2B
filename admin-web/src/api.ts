export type Shop = {
  id: number;
  name: string;
  slug: string;
  city: string | null;
  timezone: string;
  status: string;
};

export type Flower = {
  id: number;
  shop_id: number;
  name: string;
  category: string | null;
  color: string | null;
  price_per_stem: number;
  quantity_available: number;
  quantity_reserved: number;
  quantity_free: number;
  photo_url: string | null;
  is_active: boolean;
};

export type ShopSettings = {
  id: number;
  shop_id: number;
  greeting_text: string | null;
  tone: string;
  min_order_price: number;
  delivery_price: number;
  working_hours: string | null;
  manager_chat_id: number | null;
  ai_enabled: boolean;
  image_generation_enabled: boolean;
};

export type LoginResponse = {
  token: string;
  shop: Shop;
  username: string;
};

export type FlowerPayload = {
  name: string;
  category?: string | null;
  color?: string | null;
  price_per_stem: number;
  quantity_available: number;
  quantity_reserved: number;
  photo_url?: string | null;
  is_active: boolean;
};

type ApiConfig = {
  baseUrl: string;
  adminKey?: string;
  token?: string;
};

function buildUrl(baseUrl: string, path: string) {
  return `${baseUrl.replace(/\/$/, "")}${path}`;
}

async function request<T>(
  config: ApiConfig,
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(buildUrl(config.baseUrl, path), {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(config.token ? { Authorization: `Bearer ${config.token}` } : {}),
      ...(config.adminKey ? { "X-Admin-Key": config.adminKey } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail ?? response.statusText;
    throw new Error(Array.isArray(detail) ? detail.join(", ") : detail);
  }

  return response.json() as Promise<T>;
}

export function loginShop(baseUrl: string, username: string, password: string) {
  return request<LoginResponse>(
    { baseUrl },
    "/admin/auth/login",
    {
      method: "POST",
      body: JSON.stringify({ username, password }),
    },
  );
}

export function listShops(config: ApiConfig) {
  return request<Shop[]>(config, "/shops");
}

export function listFlowers(config: ApiConfig, shopId: number) {
  return request<Flower[]>(config, `/admin/shops/${shopId}/flowers`);
}

export function createFlower(config: ApiConfig, shopId: number, payload: FlowerPayload) {
  return request<Flower>(config, `/admin/shops/${shopId}/flowers`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateFlower(
  config: ApiConfig,
  flowerId: number,
  payload: Partial<FlowerPayload>,
) {
  return request<Flower>(config, `/admin/flowers/${flowerId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deactivateFlower(config: ApiConfig, flowerId: number) {
  return request<Flower>(config, `/admin/flowers/${flowerId}`, {
    method: "DELETE",
  });
}

export function getSettings(config: ApiConfig, shopId: number) {
  return request<ShopSettings>(config, `/admin/shops/${shopId}/settings`);
}

export function updateSettings(
  config: ApiConfig,
  shopId: number,
  payload: Partial<ShopSettings>,
) {
  return request<ShopSettings>(config, `/admin/shops/${shopId}/settings`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function setShopCredentials(
  config: ApiConfig,
  shopId: number,
  payload: { username: string; password: string },
) {
  return request<{ shop_id: number; shop_name: string; username: string }>(
    config,
    `/admin/shops/${shopId}/credentials`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}
