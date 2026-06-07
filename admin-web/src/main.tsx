import { StrictMode, useEffect, useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { createRoot } from "react-dom/client";
import {
  Check,
  EyeOff,
  Loader2,
  PackagePlus,
  RefreshCw,
  Save,
  Settings,
  Sprout,
  Trash2,
} from "lucide-react";
import {
  createFlower,
  deactivateFlower,
  Flower,
  FlowerPayload,
  getSettings,
  listFlowers,
  listShops,
  Shop,
  ShopSettings,
  updateFlower,
  updateSettings,
} from "./api";
import "./styles.css";

const emptyFlower: FlowerPayload = {
  name: "",
  category: "",
  color: "",
  price_per_stem: 0,
  quantity_available: 0,
  quantity_reserved: 0,
  photo_url: "",
  is_active: true,
};

type SavedConfig = {
  baseUrl: string;
  adminKey: string;
};

function App() {
  const [baseUrl, setBaseUrl] = useState(localStorage.getItem("flowerAdmin.baseUrl") ?? "");
  const [adminKey, setAdminKey] = useState(localStorage.getItem("flowerAdmin.adminKey") ?? "");
  const [shops, setShops] = useState<Shop[]>([]);
  const [shopId, setShopId] = useState<number | null>(Number(localStorage.getItem("flowerAdmin.shopId")) || null);
  const [flowers, setFlowers] = useState<Flower[]>([]);
  const [settings, setSettings] = useState<ShopSettings | null>(null);
  const [draft, setDraft] = useState<FlowerPayload>(emptyFlower);
  const [editing, setEditing] = useState<Record<number, Partial<FlowerPayload>>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [tab, setTab] = useState<"flowers" | "settings">("flowers");

  const config = useMemo<SavedConfig>(() => ({ baseUrl, adminKey }), [baseUrl, adminKey]);
  const selectedShop = shops.find((shop) => shop.id === shopId) ?? null;

  useEffect(() => {
    localStorage.setItem("flowerAdmin.baseUrl", baseUrl);
    localStorage.setItem("flowerAdmin.adminKey", adminKey);
    if (shopId) localStorage.setItem("flowerAdmin.shopId", String(shopId));
  }, [baseUrl, adminKey, shopId]);

  async function loadAll() {
    if (!baseUrl || !adminKey) {
      setMessage("Укажите Render API URL и ADMIN_API_KEY.");
      return;
    }

    setBusy(true);
    setMessage("");
    try {
      const loadedShops = await listShops(config);
      setShops(loadedShops);
      const nextShopId = shopId ?? loadedShops[0]?.id ?? null;
      setShopId(nextShopId);

      if (nextShopId) {
        const [loadedFlowers, loadedSettings] = await Promise.all([
          listFlowers(config, nextShopId),
          getSettings(config, nextShopId),
        ]);
        setFlowers(loadedFlowers);
        setSettings(loadedSettings);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось загрузить данные.");
    } finally {
      setBusy(false);
    }
  }

  async function reloadShop(nextShopId = shopId) {
    if (!nextShopId) return;
    setBusy(true);
    setMessage("");
    try {
      const [loadedFlowers, loadedSettings] = await Promise.all([
        listFlowers(config, nextShopId),
        getSettings(config, nextShopId),
      ]);
      setFlowers(loadedFlowers);
      setSettings(loadedSettings);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось обновить магазин.");
    } finally {
      setBusy(false);
    }
  }

  async function addFlower() {
    if (!shopId) return;
    if (!draft.name.trim() || draft.price_per_stem <= 0) {
      setMessage("Заполните название и цену.");
      return;
    }

    setBusy(true);
    try {
      await createFlower(config, shopId, normalizeFlower(draft));
      setDraft(emptyFlower);
      await reloadShop(shopId);
      setMessage("Позиция добавлена.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось добавить позицию.");
    } finally {
      setBusy(false);
    }
  }

  async function saveFlower(flower: Flower) {
    setBusy(true);
    try {
      await updateFlower(config, flower.id, normalizePartialFlower(editing[flower.id] ?? {}));
      setEditing((current) => {
        const next = { ...current };
        delete next[flower.id];
        return next;
      });
      await reloadShop(shopId);
      setMessage("Позиция сохранена.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось сохранить позицию.");
    } finally {
      setBusy(false);
    }
  }

  async function hideFlower(flower: Flower) {
    setBusy(true);
    try {
      await deactivateFlower(config, flower.id);
      await reloadShop(shopId);
      setMessage("Позиция скрыта.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось скрыть позицию.");
    } finally {
      setBusy(false);
    }
  }

  async function saveSettings() {
    if (!shopId || !settings) return;
    setBusy(true);
    try {
      await updateSettings(config, shopId, {
        greeting_text: settings.greeting_text,
        tone: settings.tone,
        min_order_price: settings.min_order_price,
        delivery_price: settings.delivery_price,
        working_hours: settings.working_hours,
        manager_chat_id: settings.manager_chat_id,
        ai_enabled: settings.ai_enabled,
        image_generation_enabled: settings.image_generation_enabled,
      });
      await reloadShop(shopId);
      setMessage("Настройки сохранены.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось сохранить настройки.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Flower AI Platform</p>
          <h1>Панель магазина</h1>
        </div>
        <button className="iconButton" onClick={() => void loadAll()} disabled={busy} title="Обновить">
          {busy ? <Loader2 className="spin" size={18} /> : <RefreshCw size={18} />}
        </button>
      </header>

      <section className="connection">
        <label>
          <span>Render API URL</span>
          <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://service.onrender.com" />
        </label>
        <label>
          <span>ADMIN_API_KEY</span>
          <input value={adminKey} onChange={(event) => setAdminKey(event.target.value)} type="password" />
        </label>
        <button className="primary" onClick={() => void loadAll()} disabled={busy}>
          <Check size={17} />
          Подключить
        </button>
      </section>

      {message && <div className="notice">{message}</div>}

      <section className="workspace">
        <aside className="sidebar">
          <div className="panelTitle">Магазины</div>
          <div className="shopList">
            {shops.map((shop) => (
              <button
                key={shop.id}
                className={shop.id === shopId ? "shop active" : "shop"}
                onClick={() => {
                  setShopId(shop.id);
                  void reloadShop(shop.id);
                }}
              >
                <span>{shop.name}</span>
                <small>{shop.city ?? "Город не указан"} · /start {shop.slug}</small>
              </button>
            ))}
          </div>
        </aside>

        <section className="content">
          <div className="contentHead">
            <div>
              <p className="eyebrow">{selectedShop?.city ?? "Магазин"}</p>
              <h2>{selectedShop?.name ?? "Выберите магазин"}</h2>
            </div>
            <div className="tabs">
              <button className={tab === "flowers" ? "active" : ""} onClick={() => setTab("flowers")}>
                <Sprout size={16} />
                Товары
              </button>
              <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}>
                <Settings size={16} />
                Настройки
              </button>
            </div>
          </div>

          {tab === "flowers" ? (
            <FlowersView
              draft={draft}
              setDraft={setDraft}
              flowers={flowers}
              editing={editing}
              setEditing={setEditing}
              addFlower={addFlower}
              saveFlower={saveFlower}
              hideFlower={hideFlower}
              busy={busy}
            />
          ) : (
            <SettingsView settings={settings} setSettings={setSettings} saveSettings={saveSettings} busy={busy} />
          )}
        </section>
      </section>
    </main>
  );
}

function FlowersView(props: {
  draft: FlowerPayload;
  setDraft: (value: FlowerPayload) => void;
  flowers: Flower[];
  editing: Record<number, Partial<FlowerPayload>>;
  setEditing: Dispatch<SetStateAction<Record<number, Partial<FlowerPayload>>>>;
  addFlower: () => Promise<void>;
  saveFlower: (flower: Flower) => Promise<void>;
  hideFlower: (flower: Flower) => Promise<void>;
  busy: boolean;
}) {
  const { draft, setDraft, flowers, editing, setEditing, addFlower, saveFlower, hideFlower, busy } = props;

  return (
    <>
      <div className="addRow">
        <TextInput label="Название" value={draft.name} onChange={(name) => setDraft({ ...draft, name })} />
        <TextInput label="Категория" value={draft.category ?? ""} onChange={(category) => setDraft({ ...draft, category })} />
        <TextInput label="Цвет" value={draft.color ?? ""} onChange={(color) => setDraft({ ...draft, color })} />
        <NumberInput label="Цена" value={draft.price_per_stem} onChange={(price_per_stem) => setDraft({ ...draft, price_per_stem })} />
        <NumberInput label="Остаток" value={draft.quantity_available} onChange={(quantity_available) => setDraft({ ...draft, quantity_available })} />
        <button className="primary addButton" onClick={() => void addFlower()} disabled={busy}>
          <PackagePlus size={17} />
          Добавить
        </button>
      </div>

      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Название</th>
              <th>Категория</th>
              <th>Цвет</th>
              <th>Цена</th>
              <th>Остаток</th>
              <th>Резерв</th>
              <th>Свободно</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {flowers.map((flower) => {
              const row = { ...flower, ...(editing[flower.id] ?? {}) };
              return (
                <tr key={flower.id} className={!flower.is_active ? "mutedRow" : ""}>
                  <td><input value={row.name ?? ""} onChange={(event) => edit(flower.id, "name", event.target.value, setEditing)} /></td>
                  <td><input value={row.category ?? ""} onChange={(event) => edit(flower.id, "category", event.target.value, setEditing)} /></td>
                  <td><input value={row.color ?? ""} onChange={(event) => edit(flower.id, "color", event.target.value, setEditing)} /></td>
                  <td><input type="number" value={row.price_per_stem ?? 0} onChange={(event) => edit(flower.id, "price_per_stem", Number(event.target.value), setEditing)} /></td>
                  <td><input type="number" value={row.quantity_available ?? 0} onChange={(event) => edit(flower.id, "quantity_available", Number(event.target.value), setEditing)} /></td>
                  <td><input type="number" value={row.quantity_reserved ?? 0} onChange={(event) => edit(flower.id, "quantity_reserved", Number(event.target.value), setEditing)} /></td>
                  <td><span className="stock">{flower.quantity_free}</span></td>
                  <td className="actions">
                    <button className="iconButton" onClick={() => void saveFlower(flower)} disabled={busy} title="Сохранить">
                      <Save size={16} />
                    </button>
                    <button className="iconButton danger" onClick={() => void hideFlower(flower)} disabled={busy} title="Скрыть">
                      {flower.is_active ? <EyeOff size={16} /> : <Trash2 size={16} />}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

function SettingsView(props: {
  settings: ShopSettings | null;
  setSettings: (settings: ShopSettings) => void;
  saveSettings: () => Promise<void>;
  busy: boolean;
}) {
  const { settings, setSettings, saveSettings, busy } = props;
  if (!settings) return <div className="empty">Настройки появятся после подключения.</div>;

  return (
    <div className="settingsGrid">
      <label>
        <span>Приветствие</span>
        <textarea value={settings.greeting_text ?? ""} onChange={(event) => setSettings({ ...settings, greeting_text: event.target.value })} />
      </label>
      <label>
        <span>Тон</span>
        <select value={settings.tone} onChange={(event) => setSettings({ ...settings, tone: event.target.value })}>
          <option value="friendly">friendly</option>
          <option value="elegant">elegant</option>
          <option value="concise">concise</option>
        </select>
      </label>
      <NumberInput label="Мин. заказ" value={settings.min_order_price} onChange={(min_order_price) => setSettings({ ...settings, min_order_price })} />
      <NumberInput label="Доставка" value={settings.delivery_price} onChange={(delivery_price) => setSettings({ ...settings, delivery_price })} />
      <TextInput label="График" value={settings.working_hours ?? ""} onChange={(working_hours) => setSettings({ ...settings, working_hours })} />
      <NumberInput label="Manager chat_id" value={settings.manager_chat_id ?? 0} onChange={(manager_chat_id) => setSettings({ ...settings, manager_chat_id })} />
      <label className="toggle">
        <input type="checkbox" checked={settings.ai_enabled} onChange={(event) => setSettings({ ...settings, ai_enabled: event.target.checked })} />
        <span>AI включен</span>
      </label>
      <label className="toggle">
        <input type="checkbox" checked={settings.image_generation_enabled} onChange={(event) => setSettings({ ...settings, image_generation_enabled: event.target.checked })} />
        <span>Генерация изображений</span>
      </label>
      <button className="primary saveSettings" onClick={() => void saveSettings()} disabled={busy}>
        <Save size={17} />
        Сохранить
      </button>
    </div>
  );
}

function TextInput(props: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label>
      <span>{props.label}</span>
      <input value={props.value} onChange={(event) => props.onChange(event.target.value)} />
    </label>
  );
}

function NumberInput(props: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label>
      <span>{props.label}</span>
      <input type="number" value={props.value} onChange={(event) => props.onChange(Number(event.target.value))} />
    </label>
  );
}

function edit(
  id: number,
  key: keyof FlowerPayload,
  value: string | number | boolean,
  setEditing: Dispatch<SetStateAction<Record<number, Partial<FlowerPayload>>>>,
) {
  setEditing((current) => ({
    ...current,
    [id]: {
      ...(current[id] ?? {}),
      [key]: value,
    },
  }));
}

function normalizeFlower(payload: FlowerPayload): FlowerPayload {
  return {
    ...payload,
    category: payload.category || null,
    color: payload.color || null,
    photo_url: payload.photo_url || null,
  };
}

function normalizePartialFlower(payload: Partial<FlowerPayload>): Partial<FlowerPayload> {
  return Object.fromEntries(
    Object.entries(payload).map(([key, value]) => [key, value === "" ? null : value]),
  ) as Partial<FlowerPayload>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
