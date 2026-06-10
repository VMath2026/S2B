import { CalendarClock, CircleDollarSign, ClipboardList, ExternalLink, PhoneCall } from "lucide-react";
import type { Dispatch, SetStateAction } from "react";
import type { Order, OrderStatus, SelectedFlower } from "./api";

const ORDER_STATUS_OPTIONS: Array<{ value: OrderStatus; label: string }> = [
  { value: "new", label: "Новый" },
  { value: "accepted", label: "Принят" },
  { value: "in_progress", label: "В работе" },
  { value: "done", label: "Готов" },
  { value: "cancelled", label: "Отменен" },
  { value: "paid", label: "Оплачен" },
];

const ORDER_FILTER_OPTIONS: Array<{ value: OrderStatus | "all"; label: string }> = [
  { value: "all", label: "Все" },
  ...ORDER_STATUS_OPTIONS,
];

const PAYMENT_STATUS_LABELS: Record<string, string> = {
  not_paid: "не оплачен",
  invoice_sent: "счет отправлен",
  prepaid: "предоплата",
  paid: "оплачен",
  failed: "оплата не прошла",
  refunded: "возврат",
};

type OrdersViewProps = {
  orders: Order[];
  statusFilter: OrderStatus | "all";
  setStatusFilter: Dispatch<SetStateAction<OrderStatus | "all">>;
  changeOrderStatus: (order: Order, status: OrderStatus) => Promise<void>;
  changeOrderPayment: (order: Order, paymentStatus: string) => Promise<void>;
  busy: boolean;
};

type ParsedOrderComment = {
  comment: string | null;
  selectedFlowers: SelectedFlower[];
  aiSummary: string | null;
};

export function OrdersView({
  orders,
  statusFilter,
  setStatusFilter,
  changeOrderStatus,
  changeOrderPayment,
  busy,
}: OrdersViewProps) {
  return (
    <section className="ordersPanel">
      <div className="ordersToolbar">
        <div>
          <p className="eyebrow">Контроль заказов</p>
          <h3>Новые заявки и доставка</h3>
        </div>
        <div className="statusFilters" aria-label="Фильтр статуса заказа">
          {ORDER_FILTER_OPTIONS.map((option) => (
            <button
              key={option.value}
              className={statusFilter === option.value ? "active" : ""}
              onClick={() => setStatusFilter(option.value)}
              type="button"
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {orders.length === 0 ? (
        <div className="empty">
          Заказов с таким статусом пока нет. Когда клиент подтвердит букет в боте, он появится здесь.
        </div>
      ) : (
        <div className="ordersGrid">
          {orders.map((order) => (
            <OrderCard
              key={order.id}
              order={order}
              busy={busy}
              changeOrderStatus={changeOrderStatus}
              changeOrderPayment={changeOrderPayment}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function OrderCard({
  order,
  busy,
  changeOrderStatus,
  changeOrderPayment,
}: {
  order: Order;
  busy: boolean;
  changeOrderStatus: (order: Order, status: OrderStatus) => Promise<void>;
  changeOrderPayment: (order: Order, paymentStatus: string) => Promise<void>;
}) {
  const details = parseOrderComment(order);
  const flowers = details.selectedFlowers.length > 0
    ? details.selectedFlowers
    : order.composition ?? order.selected_flowers ?? [];

  return (
    <article className="orderCard">
      <div className="orderCardHead">
        <div>
          <p className="eyebrow">Заказ №{order.id}</p>
          <h3>{order.recipient || "Получатель не указан"}</h3>
          <p className="mutedText">{formatDateTime(order.created_at)}</p>
        </div>
        <div className="orderBadges">
          <span className={`badge status-${order.status}`}>{statusLabel(order.status)}</span>
          <span className={`badge payment-${order.payment_status}`}>
            {paymentStatusLabel(order.payment_status)}
          </span>
        </div>
      </div>

      <div className="orderSummary">
        <div>
          <ClipboardList size={17} />
          <span>{details.aiSummary || order.occasion || "Букет без описания"}</span>
        </div>
        <div>
          <CircleDollarSign size={17} />
          <span>{formatMoney(order.total_price ?? order.budget)}</span>
        </div>
      </div>

      <div className="orderDetails">
        <div>
          <span>Состав</span>
          <strong>{formatFlowers(flowers)}</strong>
        </div>
        <div>
          <span>Пожелания</span>
          <strong>{formatPreferences(order)}</strong>
        </div>
        <div>
          <span>Доставка</span>
          <strong>
            <CalendarClock size={15} />
            {formatDelivery(order)}
          </strong>
        </div>
        <div>
          <span>Телефон</span>
          <strong>
            <PhoneCall size={15} />
            {order.phone || "не указан"}
          </strong>
        </div>
        {details.comment && (
          <div className="wide">
            <span>Комментарий клиента</span>
            <strong>{details.comment}</strong>
          </div>
        )}
        {order.customer && (
          <div className="wide">
            <span>Telegram клиента</span>
            <strong>
              {order.customer.first_name || "имя не указано"}, id {order.customer.telegram_user_id}
              {order.customer.telegram_username ? `, @${order.customer.telegram_username}` : ""}
            </strong>
          </div>
        )}
      </div>

      <div className="orderActions">
        {order.customer?.contact_url && (
          <a className="secondaryAction" href={order.customer.contact_url} target="_blank" rel="noreferrer">
            <ExternalLink size={16} />
            Открыть клиента
          </a>
        )}
        <label>
          <span>Статус заказа</span>
          <select
            value={order.status}
            onChange={(event) => void changeOrderStatus(order, event.target.value as OrderStatus)}
            disabled={busy}
          >
            {ORDER_STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Оплата</span>
          <select
            value={order.payment_status}
            onChange={(event) => void changeOrderPayment(order, event.target.value)}
            disabled={busy}
          >
            <option value="not_paid">Не оплачен</option>
            <option value="invoice_sent">Счет отправлен</option>
            <option value="prepaid">Предоплата 50%</option>
            <option value="paid">Оплачен</option>
            <option value="failed">Оплата не прошла</option>
            <option value="refunded">Возврат</option>
          </select>
        </label>
      </div>
    </article>
  );
}

function parseOrderComment(order: Order): ParsedOrderComment {
  const directFlowers = order.composition ?? order.selected_flowers ?? [];
  const directComment = order.customer_comment ?? valueToString(order.comment_payload?.comment);
  const directSummary = order.selected_variant?.title ?? order.ai_summary ?? valueToString(order.comment_payload?.ai_summary);

  if (directFlowers.length > 0 || directComment || directSummary) {
    return {
      comment: directComment,
      selectedFlowers: directFlowers,
      aiSummary: directSummary,
    };
  }

  if (!order.comment) {
    return { comment: null, selectedFlowers: [], aiSummary: null };
  }

  try {
    const parsed = JSON.parse(order.comment) as unknown;
    if (!isRecord(parsed)) {
      return { comment: order.comment, selectedFlowers: [], aiSummary: null };
    }

    return {
      comment: valueToString(parsed.comment),
      selectedFlowers: normalizeSelectedFlowers(parsed.selected_flowers),
      aiSummary: valueToString(parsed.ai_summary),
    };
  } catch {
    return { comment: order.comment, selectedFlowers: [], aiSummary: null };
  }
}

function normalizeSelectedFlowers(value: unknown): SelectedFlower[] {
  if (!Array.isArray(value)) return [];

  return value
    .filter(isRecord)
    .map((item) => ({
      name: valueToString(item.name),
      quantity: valueToNumber(item.quantity),
      color: valueToString(item.color),
      category: valueToString(item.category),
      price_per_stem: valueToNumber(item.price_per_stem),
    }));
}

function formatFlowers(flowers: SelectedFlower[]): string {
  if (flowers.length === 0) return "состав не указан";
  return flowers
    .map((flower) => {
      const name = flower.name || "цветок";
      const quantity = flower.quantity ? ` x${flower.quantity}` : "";
      const color = flower.color ? `, ${displayColor(flower.color)}` : "";
      return `${name}${quantity}${color}`;
    })
    .join("; ");
}

function formatPreferences(order: Order): string {
  const parts = [
    order.occasion ? `повод: ${order.occasion}` : null,
    order.style ? `стиль: ${order.style}` : null,
    order.colors?.length ? `цвета: ${order.colors.map(displayColor).join(", ")}` : null,
    order.avoid_flowers?.length ? `исключить: ${order.avoid_flowers.join(", ")}` : null,
  ].filter(Boolean);

  return parts.length ? parts.join("; ") : "не указаны";
}

function formatDelivery(order: Order): string {
  const date = order.delivery_date || "дата не указана";
  const address = order.delivery_address || "адрес не указан";
  return `${date}, ${address}`;
}

function statusLabel(status: OrderStatus): string {
  return ORDER_STATUS_OPTIONS.find((option) => option.value === status)?.label ?? status;
}

function paymentStatusLabel(status: string | null): string {
  if (!status) return "не оплачен";
  return PAYMENT_STATUS_LABELS[status] ?? status;
}

function formatMoney(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "сумма не указана";
  return `${Math.round(value).toLocaleString("ru-RU")} руб.`;
}

function formatDateTime(value: string | null): string {
  if (!value) return "дата создания не указана";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function displayColor(color: string): string {
  const labels: Record<string, string> = {
    red: "красный",
    white: "белый",
    pink: "розовый",
    blue: "синий",
    purple: "фиолетовый",
    lavender: "лавандовый",
    yellow: "желтый",
  };
  return labels[color.trim().toLowerCase()] ?? color;
}

function valueToString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function valueToNumber(value: unknown): number | null {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
