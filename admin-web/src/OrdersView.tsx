import { useMemo, useState } from "react";
import {
  CalendarDays,
  CheckCircle2,
  CreditCard,
  Download,
  ExternalLink,
  MessageCircle,
  PackageCheck,
  Save,
  Send,
} from "lucide-react";
import type { ConversationLog, Order, OrderStatus, OrderUpdatePayload, SelectedFlower } from "./api";

type OrderDraft = {
  selected_variant_title: string;
  total_price: string;
  delivery_date: string;
  phone: string;
  delivery_address: string;
  delivery_type: string;
  urgent_delivery: boolean;
  selected_flowers_text: string;
  customer_comment: string;
};

type Props = {
  orders: Order[];
  statusFilter: OrderStatus | "all";
  setStatusFilter: (status: OrderStatus | "all") => void;
  changeOrderStatus: (order: Order, status: OrderStatus) => Promise<void>;
  changeOrderPayment: (order: Order, status: string) => Promise<void>;
  saveOrder: (order: Order, payload: OrderUpdatePayload) => Promise<void>;
  sendInvoice: (order: Order, paymentMode: "full_prepay" | "prepay_50") => Promise<void>;
  confirmOrder: (order: Order) => Promise<void>;
  messageCustomer: (order: Order, text: string) => Promise<void>;
  loadConversation: (order: Order) => Promise<ConversationLog[]>;
  remindPayment: (order: Order) => Promise<void>;
  exportOrders: () => Promise<void>;
  busy: boolean;
};

const STATUS_OPTIONS: Array<{ value: OrderStatus | "all"; label: string }> = [
  { value: "all", label: "Все" },
  { value: "new", label: "Новые" },
  { value: "accepted", label: "Приняты" },
  { value: "awaiting_payment", label: "Ожидают оплаты" },
  { value: "in_progress", label: "В работе" },
  { value: "done", label: "Готовы" },
  { value: "paid", label: "Оплачены" },
  { value: "cancelled", label: "Отменены" },
];

const PAYMENT_OPTIONS = [
  { value: "all", label: "Любая оплата" },
  { value: "not_paid", label: "Не оплачен" },
  { value: "invoice_sent", label: "Счет отправлен" },
  { value: "prepaid", label: "Предоплата" },
  { value: "paid", label: "Оплачен" },
  { value: "failed", label: "Ошибка оплаты" },
  { value: "refunded", label: "Возврат" },
];

const QUICK_REPLIES = [
  "Здравствуйте! Подтвердили заказ, скоро отправим детали.",
  "Букет готов, можно забирать или ожидать доставку.",
  "Подскажите, пожалуйста, точный адрес и удобное время доставки.",
  "Счет отправили. После оплаты сразу передадим заказ флористу.",
];

export function OrdersView(props: Props) {
  const {
    orders,
    statusFilter,
    setStatusFilter,
    changeOrderStatus,
    changeOrderPayment,
    saveOrder,
    sendInvoice,
    confirmOrder,
    messageCustomer,
    loadConversation,
    remindPayment,
    exportOrders,
    busy,
  } = props;
  const [drafts, setDrafts] = useState<Record<number, OrderDraft>>({});
  const [messages, setMessages] = useState<Record<number, string>>({});
  const [conversations, setConversations] = useState<Record<number, ConversationLog[]>>({});
  const [search, setSearch] = useState("");
  const [paymentFilter, setPaymentFilter] = useState("all");
  const [deliveryDateFilter, setDeliveryDateFilter] = useState("");

  const filteredOrders = useMemo(() => {
    const query = search.trim().toLowerCase();
    return orders.filter((order) => {
      if (paymentFilter !== "all" && order.payment_status !== paymentFilter) return false;
      if (deliveryDateFilter && !String(order.delivery_date ?? "").startsWith(deliveryDateFilter)) return false;
      if (!query) return true;
      const haystack = [
        order.id,
        order.recipient,
        order.phone,
        order.delivery_address,
        order.customer?.telegram_username,
        order.customer?.first_name,
      ]
        .map((value) => String(value ?? "").toLowerCase())
        .join(" ");
      return haystack.includes(query);
    });
  }, [deliveryDateFilter, orders, paymentFilter, search]);

  function draftFor(order: Order): OrderDraft {
    return drafts[order.id] ?? orderToDraft(order);
  }

  function patchDraft(order: Order, patch: Partial<OrderDraft>) {
    setDrafts((current) => ({
      ...current,
      [order.id]: {
        ...draftFor(order),
        ...patch,
      },
    }));
  }

  async function saveDraft(order: Order) {
    await saveOrder(order, draftToPayload(draftFor(order)));
    setDrafts((current) => {
      const next = { ...current };
      delete next[order.id];
      return next;
    });
  }

  async function openConversation(order: Order) {
    const loaded = await loadConversation(order);
    setConversations((current) => ({ ...current, [order.id]: loaded }));
  }

  async function sendMessage(order: Order) {
    const text = messages[order.id] ?? "";
    await messageCustomer(order, text);
    setMessages((current) => ({ ...current, [order.id]: "" }));
  }

  return (
    <div className="ordersPanel">
      <div className="ordersToolbar">
        <div>
          <p className="eyebrow">Заказы</p>
          <h3>{filteredOrders.length} из {orders.length}</h3>
        </div>
        <div className="statusFilters">
          {STATUS_OPTIONS.map((option) => (
            <button
              key={option.value}
              className={statusFilter === option.value ? "active" : ""}
              onClick={() => setStatusFilter(option.value)}
              type="button"
            >
              {option.label}
            </button>
          ))}
          <button className="secondaryAction" onClick={() => void exportOrders()} disabled={busy} type="button">
            <Download size={16} />
            CSV
          </button>
        </div>
      </div>

      <div className="orderFilters">
        <label>
          <span>Поиск</span>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="номер, клиент, телефон, адрес" />
        </label>
        <label>
          <span>Оплата</span>
          <select value={paymentFilter} onChange={(event) => setPaymentFilter(event.target.value)}>
            {PAYMENT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Дата доставки</span>
          <input type="date" value={deliveryDateFilter} onChange={(event) => setDeliveryDateFilter(event.target.value)} />
        </label>
      </div>

      {filteredOrders.length === 0 ? (
        <div className="empty">Заказов по выбранным фильтрам пока нет.</div>
      ) : (
        <div className="ordersGrid">
          {filteredOrders.map((order) => {
            const draft = draftFor(order);
            const conversation = conversations[order.id];
            return (
              <article className="orderCard" key={order.id}>
                <div className="orderCardHead">
                  <div>
                    <p className="eyebrow">{formatDateTime(order.created_at)}</p>
                    <h3>Заказ №{order.id}</h3>
                    <p className="mutedText">{order.customer?.first_name || order.recipient || "Клиент без имени"}</p>
                  </div>
                  <div className="orderBadges">
                    <span className={`badge status-${order.status}`}>{statusLabel(order.status)}</span>
                    <span className={`badge payment-${order.payment_status}`}>{paymentStatusLabel(order.payment_status)}</span>
                  </div>
                </div>

                <div className="orderSummary">
                  <div>
                    <PackageCheck size={18} />
                    <span>{order.selected_variant?.title || order.occasion || "Вариант не выбран"}</span>
                  </div>
                  <div>
                    <CreditCard size={18} />
                    <span>{formatMoney(order.pricing_summary?.grand_total ?? order.total_price ?? order.budget)}</span>
                  </div>
                </div>

                <div className="orderDetails">
                  <Detail label="Состав" value={formatFlowers(order.composition ?? order.selected_flowers ?? order.selected_variant?.flowers)} wide />
                  <Detail label="Пожелания" value={formatPreferences(order)} />
                  <Detail label="Доставка" value={formatDelivery(order)} />
                  <Detail label="Телефон" value={order.phone || "не указан"} />
                  <Detail label="Адрес" value={order.delivery_address || deliveryTypeLabel(order.selected_variant?.delivery_type) || "не указан"} />
                  <Detail label="Стоимость" value={formatPricing(order)} />
                  <Detail label="Комментарий" value={order.customer_comment || order.comment || "нет"} wide />
                  <Detail
                    label="Клиент"
                    value={order.customer?.telegram_username ? `@${order.customer.telegram_username}` : order.customer?.first_name || "неизвестен"}
                  />
                </div>

                <div className="orderActions">
                  {order.customer?.contact_url ? (
                    <a className="secondaryAction" href={order.customer.contact_url} target="_blank" rel="noreferrer">
                      <ExternalLink size={16} />
                      Открыть клиента
                    </a>
                  ) : (
                    <button className="secondaryAction" disabled type="button">
                      <ExternalLink size={16} />
                      Нет контакта
                    </button>
                  )}
                  <label>
                    <span>Статус</span>
                    <select value={order.status} onChange={(event) => void changeOrderStatus(order, event.target.value as OrderStatus)} disabled={busy}>
                      {STATUS_OPTIONS.filter((option) => option.value !== "all").map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>Оплата</span>
                    <select value={order.payment_status} onChange={(event) => void changeOrderPayment(order, event.target.value)} disabled={busy}>
                      {PAYMENT_OPTIONS.filter((option) => option.value !== "all").map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </label>
                </div>

                <div className="orderEditGrid">
                  <label>
                    <span>Выбранный вариант</span>
                    <input value={draft.selected_variant_title} onChange={(event) => patchDraft(order, { selected_variant_title: event.target.value })} />
                  </label>
                  <label>
                    <span>Сумма</span>
                    <input type="number" min={0} value={draft.total_price} onChange={(event) => patchDraft(order, { total_price: event.target.value })} />
                  </label>
                  <label>
                    <span>Дата</span>
                    <input value={draft.delivery_date} onChange={(event) => patchDraft(order, { delivery_date: event.target.value })} placeholder="2026-06-12 15:00" />
                  </label>
                  <label>
                    <span>Телефон</span>
                    <input value={draft.phone} onChange={(event) => patchDraft(order, { phone: event.target.value })} />
                  </label>
                  <label>
                    <span>Получение</span>
                    <select value={draft.delivery_type} onChange={(event) => patchDraft(order, { delivery_type: event.target.value })}>
                      <option value="delivery">Доставка</option>
                      <option value="pickup">Самовывоз</option>
                    </select>
                  </label>
                  <label className="toggle">
                    <input
                      type="checkbox"
                      checked={draft.urgent_delivery}
                      onChange={(event) => patchDraft(order, { urgent_delivery: event.target.checked })}
                    />
                    <span>Срочная доставка</span>
                  </label>
                  <label className="wide">
                    <span>Адрес</span>
                    <input value={draft.delivery_address} onChange={(event) => patchDraft(order, { delivery_address: event.target.value })} />
                  </label>
                  <label className="wide">
                    <span>Состав</span>
                    <textarea value={draft.selected_flowers_text} onChange={(event) => patchDraft(order, { selected_flowers_text: event.target.value })} />
                  </label>
                  <label className="wide">
                    <span>Комментарий</span>
                    <textarea value={draft.customer_comment} onChange={(event) => patchDraft(order, { customer_comment: event.target.value })} />
                  </label>
                  <div className="orderEditActions">
                    <button className="primary" onClick={() => void saveDraft(order)} disabled={busy} type="button">
                      <Save size={16} />
                      Сохранить
                    </button>
                    <button className="secondaryAction" onClick={() => void confirmOrder(order)} disabled={busy} type="button">
                      <CheckCircle2 size={16} />
                      Подтвердить
                    </button>
                    <button className="secondaryAction" onClick={() => void sendInvoice(order, "full_prepay")} disabled={busy} type="button">
                      <CreditCard size={16} />
                      Счет 100%
                    </button>
                    <button className="secondaryAction" onClick={() => void sendInvoice(order, "prepay_50")} disabled={busy} type="button">
                      <CreditCard size={16} />
                      Предоплата 50%
                    </button>
                    <button className="secondaryAction" onClick={() => void remindPayment(order)} disabled={busy} type="button">
                      <CalendarDays size={16} />
                      Напомнить
                    </button>
                    <button className="secondaryAction" onClick={() => void openConversation(order)} disabled={busy || !order.customer_id} type="button">
                      <MessageCircle size={16} />
                      Диалог
                    </button>
                  </div>
                </div>

                {conversation && (
                  <div className="conversationBox">
                    {conversation.length === 0 ? (
                      <p className="mutedText">Диалог пока пуст.</p>
                    ) : (
                      conversation.map((item) => (
                        <div className="conversationMessage" key={item.id}>
                          <span>{item.role} · {formatDateTime(item.created_at)}</span>
                          <p>{item.message}</p>
                        </div>
                      ))
                    )}
                  </div>
                )}

                <div className="managerMessageBox">
                  <label>
                    <span>Сообщение клиенту</span>
                    <textarea value={messages[order.id] ?? ""} onChange={(event) => setMessages((current) => ({ ...current, [order.id]: event.target.value }))} />
                  </label>
                  <div className="quickReplies">
                    {QUICK_REPLIES.map((reply) => (
                      <button key={reply} type="button" onClick={() => setMessages((current) => ({ ...current, [order.id]: reply }))}>
                        {reply}
                      </button>
                    ))}
                  </div>
                  <button className="primary" onClick={() => void sendMessage(order)} disabled={busy} type="button">
                    <Send size={16} />
                    Отправить
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Detail(props: { label: string; value: string; wide?: boolean }) {
  return (
    <div className={props.wide ? "wide" : undefined}>
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </div>
  );
}

function orderToDraft(order: Order): OrderDraft {
  return {
    selected_variant_title: order.selected_variant?.title ?? "",
    total_price: valueToString(order.total_price ?? order.pricing_summary?.grand_total ?? ""),
    delivery_date: order.delivery_date ?? "",
    phone: order.phone ?? "",
    delivery_address: order.delivery_address ?? "",
    delivery_type: valueToString(order.selected_variant?.delivery_type ?? "delivery"),
    urgent_delivery: Boolean(order.selected_variant?.urgent_delivery),
    selected_flowers_text: flowersToText(order.composition ?? order.selected_flowers ?? order.selected_variant?.flowers),
    customer_comment: order.customer_comment ?? order.comment ?? "",
  };
}

function draftToPayload(draft: OrderDraft): OrderUpdatePayload {
  return {
    selected_variant_title: draft.selected_variant_title.trim() || null,
    total_price: valueToNumber(draft.total_price),
    delivery_date: draft.delivery_date.trim() || null,
    phone: draft.phone.trim() || null,
    delivery_address: draft.delivery_address.trim() || null,
    delivery_type: draft.delivery_type || "delivery",
    urgent_delivery: draft.urgent_delivery,
    selected_flowers: parseFlowersText(draft.selected_flowers_text),
    customer_comment: draft.customer_comment.trim() || null,
  };
}

function flowersToText(flowers?: SelectedFlower[] | null): string {
  return normalizeSelectedFlowers(flowers)
    .map((flower) => {
      const parts = [flower.name, flower.quantity ? `x${flower.quantity}` : "", displayColor(flower.color), flower.price_per_stem ? `${flower.price_per_stem} руб.` : ""];
      return parts.filter(Boolean).join(" ");
    })
    .join("\n");
}

function parseFlowersText(value: string): SelectedFlower[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const quantityMatch = line.match(/\bx\s*(\d+)\b/i);
      const priceMatch = line.match(/(\d+(?:[.,]\d+)?)\s*(?:руб|р\.?)\b/i);
      const name = line
        .replace(/\bx\s*\d+\b/gi, "")
        .replace(/(\d+(?:[.,]\d+)?)\s*(?:руб|р\.?)\b/gi, "")
        .trim();
      return {
        name,
        quantity: quantityMatch ? Number(quantityMatch[1]) : null,
        price_per_stem: priceMatch ? Number(priceMatch[1].replace(",", ".")) : null,
      };
    });
}

function normalizeSelectedFlowers(flowers?: SelectedFlower[] | null): SelectedFlower[] {
  return Array.isArray(flowers) ? flowers.filter((flower) => flower && typeof flower === "object") : [];
}

function formatFlowers(flowers?: SelectedFlower[] | null): string {
  const list = normalizeSelectedFlowers(flowers);
  if (list.length === 0) return "состав не указан";
  return list
    .map((flower) => [flower.name || "цветок", flower.quantity ? `${flower.quantity} шт.` : "", displayColor(flower.color)].filter(Boolean).join(", "))
    .join("; ");
}

function formatPreferences(order: Order): string {
  const values = [
    order.style ? `стиль: ${order.style}` : "",
    order.colors?.length ? `цвета: ${order.colors.map(displayColor).join(", ")}` : "",
    order.avoid_flowers?.length ? `не использовать: ${order.avoid_flowers.join(", ")}` : "",
  ].filter(Boolean);
  return values.length ? values.join("; ") : "нет особых пожеланий";
}

function formatDelivery(order: Order): string {
  const type = deliveryTypeLabel(order.selected_variant?.delivery_type);
  const urgent = order.selected_variant?.urgent_delivery ? "срочно" : "";
  const date = order.delivery_date || "дата не указана";
  return [type, urgent, date].filter(Boolean).join(", ");
}

function formatPricing(order: Order): string {
  const pricing = order.pricing_summary;
  if (!pricing) return formatMoney(order.total_price ?? order.budget);
  return [
    `букет ${formatMoney(pricing.bouquet_total)}`,
    `доставка ${formatMoney(pricing.delivery_fee)}`,
    `итого ${formatMoney(pricing.grand_total)}`,
  ].join("; ");
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    new: "новый",
    accepted: "принят",
    awaiting_payment: "ожидает оплаты",
    in_progress: "в работе",
    done: "готов",
    cancelled: "отменен",
    paid: "оплачен",
  };
  return labels[status] ?? status;
}

function paymentStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    not_paid: "не оплачен",
    invoice_sent: "счет отправлен",
    prepaid: "предоплата",
    paid: "оплачен",
    failed: "ошибка оплаты",
    refunded: "возврат",
  };
  return labels[status] ?? status;
}

function formatMoney(value?: number | null): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "сумма не указана";
  return `${Math.round(value).toLocaleString("ru-RU")} руб.`;
}

function formatDateTime(value: string | null): string {
  if (!value) return "дата не указана";
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

function displayColor(value?: string | null): string {
  if (!value) return "";
  const labels: Record<string, string> = {
    red: "красный",
    white: "белый",
    pink: "розовый",
    yellow: "желтый",
    purple: "фиолетовый",
    blue: "синий",
    green: "зеленый",
  };
  return labels[value.toLowerCase()] ?? value;
}

function valueToString(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

function valueToNumber(value: string): number | null {
  const normalized = value.trim().replace(",", ".");
  if (!normalized) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function deliveryTypeLabel(value: unknown): string {
  if (isRecord(value)) return "";
  if (value === "pickup") return "самовывоз";
  if (value === "delivery") return "доставка";
  return typeof value === "string" ? value : "";
}
