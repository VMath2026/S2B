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

export type OrderStatus = "new" | "accepted" | "awaiting_payment" | "in_progress" | "done" | "cancelled" | "paid";

export type PaymentStatus =
  | "not_paid"
  | "invoice_sent"
  | "prepaid"
  | "paid"
  | "failed"
  | "refunded"
  | string;

export type SelectedFlower = {
  name?: string | null;
  quantity?: number | null;
  color?: string | null;
  category?: string | null;
  price_per_stem?: number | null;
};

export type Customer = {
  id: number;
  telegram_user_id: number;
  telegram_username: string | null;
  first_name: string | null;
  contact_url: string | null;
  created_at: string | null;
};

export type Order = {
  id: number;
  shop_id: number;
  customer_id: number | null;
  status: OrderStatus;
  occasion: string | null;
  recipient: string | null;
  budget: number | null;
  style: string | null;
  colors: string[] | null;
  avoid_flowers: string[] | null;
  delivery_date: string | null;
  delivery_address: string | null;
  phone: string | null;
  comment: string | null;
  comment_payload: { comment?: string; selected_flowers?: SelectedFlower[]; ai_summary?: string } | null;
  composition: SelectedFlower[] | null;
  selected_flowers?: SelectedFlower[];
  customer_comment?: string | null;
  ai_summary?: string | null;
  selected_variant: {
    title?: string;
    flowers?: SelectedFlower[];
    estimated_price?: number;
    delivery_type?: string;
    urgent_delivery?: boolean;
  } | null;
  pricing_summary: {
    bouquet_total: number;
    delivery_fee: number;
    grand_total: number;
    delivery_type: string;
    urgent_delivery: boolean;
  };
  generated_image_url: string | null;
  total_price: number | null;
  payment_status: PaymentStatus;
  telegram_payment_charge_id: string | null;
  provider_payment_charge_id: string | null;
  customer: Customer | null;
  created_at: string | null;
};

export type OrderUpdatePayload = {
  recipient?: string | null;
  occasion?: string | null;
  budget?: number | null;
  style?: string | null;
  colors?: string[] | null;
  avoid_flowers?: string[] | null;
  delivery_date?: string | null;
  delivery_address?: string | null;
  phone?: string | null;
  customer_comment?: string | null;
  selected_variant_title?: string | null;
  selected_flowers?: SelectedFlower[] | null;
  delivery_type?: string | null;
  urgent_delivery?: boolean | null;
  total_price?: number | null;
};

export type ConversationLog = {
  id: number;
  role: string;
  message: string;
  meta: Record<string, unknown> | null;
  created_at: string | null;
};

export type BouquetTemplate = {
  id: number;
  shop_id: number;
  title: string;
  description: string | null;
  style: string | null;
  colors: string[];
  flowers: string[];
  price: number | null;
  image_url: string | null;
  created_at: string | null;
};

export type ShopSettings = {
  id: number;
  shop_id: number;
  greeting_text: string | null;
  tone: string;
  min_order_price: number;
  delivery_price: number;
  free_delivery_from: number | null;
  urgent_delivery_price: number;
  pickup_enabled: boolean;
  payment_mode: string;
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

export type AdminMe = {
  role: "owner" | "shop";
  shop: Shop | null;
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

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function formatApiDetail(detail: unknown): string {
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const record = item as { loc?: unknown[]; msg?: string };
          const field = Array.isArray(record.loc) ? record.loc.join(".") : "";
          return [field, record.msg].filter(Boolean).join(": ");
        }
        return String(item);
      })
      .filter(Boolean)
      .join(", ");
  }

  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return "Request failed";
}

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
    throw new ApiError(
      formatApiDetail(detail),
      response.status,
    );
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

export function getMe(config: ApiConfig) {
  return request<AdminMe>(config, "/admin/me");
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

export function resetReservedFlowers(config: ApiConfig, shopId: number) {
  return request<{ status: string; updated: number }>(
    config,
    `/admin/shops/${shopId}/flowers/reset-reserved`,
    { method: "POST" },
  );
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

export function listOrders(config: ApiConfig, shopId: number, status?: OrderStatus) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<Order[]>(config, `/admin/shops/${shopId}/orders${query}`);
}

export function updateOrderStatus(
  config: ApiConfig,
  orderId: number,
  status: OrderStatus,
) {
  return request<Order>(config, `/admin/orders/${orderId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
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

export function updateOrderPayment(config: ApiConfig, orderId: number, payment_status: string) {
  return request<Order>(config, `/admin/orders/${orderId}/payment`, {
    method: "PATCH",
    body: JSON.stringify({ payment_status }),
  });
}

export function updateOrder(config: ApiConfig, orderId: number, payload: OrderUpdatePayload) {
  return request<Order>(config, `/admin/orders/${orderId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function sendOrderInvoice(
  config: ApiConfig,
  orderId: number,
  payment_mode: "full_prepay" | "prepay_50",
) {
  return request<{ status: string; order: Order; amount: number }>(
    config,
    `/admin/orders/${orderId}/send-invoice`,
    {
      method: "POST",
      body: JSON.stringify({ payment_mode }),
    },
  );
}

export function sendPaymentReminder(config: ApiConfig, orderId: number) {
  return request<{ status: string }>(
    config,
    `/admin/orders/${orderId}/payment-reminder`,
    { method: "POST" },
  );
}

export async function exportOrdersCsv(config: ApiConfig, shopId: number) {
  const response = await fetch(buildUrl(config.baseUrl, `/admin/shops/${shopId}/orders/export.csv`), {
    headers: {
      ...(config.token ? { Authorization: `Bearer ${config.token}` } : {}),
      ...(config.adminKey ? { "X-Admin-Key": config.adminKey } : {}),
    },
  });
  if (!response.ok) {
    throw new ApiError(response.statusText, response.status);
  }
  return response.blob();
}

export function confirmOrder(config: ApiConfig, orderId: number) {
  return request<{ status: string; order: Order }>(
    config,
    `/admin/orders/${orderId}/confirm`,
    { method: "POST" },
  );
}

export function messageOrderCustomer(config: ApiConfig, orderId: number, text: string) {
  return request<{ status: string }>(
    config,
    `/admin/orders/${orderId}/message`,
    {
      method: "POST",
      body: JSON.stringify({ text }),
    },
  );
}

export function listCustomerOrders(config: ApiConfig, shopId: number, customerId: number) {
  return request<Order[]>(config, `/admin/shops/${shopId}/customers/${customerId}/orders`);
}

export function listCustomerConversation(config: ApiConfig, shopId: number, customerId: number) {
  return request<ConversationLog[]>(config, `/admin/shops/${shopId}/customers/${customerId}/conversation`);
}

export function listShopErrors(config: ApiConfig, shopId: number) {
  return request<ConversationLog[]>(config, `/admin/shops/${shopId}/errors`);
}

export function listBouquetTemplates(config: ApiConfig, shopId: number) {
  return request<BouquetTemplate[]>(config, `/admin/shops/${shopId}/bouquet-templates`);
}

export function createBouquetTemplate(
  config: ApiConfig,
  shopId: number,
  payload: Omit<BouquetTemplate, "id" | "shop_id" | "created_at">,
) {
  return request<BouquetTemplate>(config, `/admin/shops/${shopId}/bouquet-templates`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
