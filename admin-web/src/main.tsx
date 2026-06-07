import { StrictMode, useEffect, useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { createRoot } from "react-dom/client";
import {
  Check,
  EyeOff,
  KeyRound,
  Loader2,
  LogOut,
  PackagePlus,
  RefreshCw,
  Save,
  Settings,
  ShieldCheck,
  Sprout,
  Trash2,
} from "lucide-react";
import {
  ApiError,
  createFlower,
  deactivateFlower,
  Flower,
  FlowerPayload,
  getMe,
  getSettings,
  listFlowers,
  listShops,
  loginShop,
  setShopCredentials,
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

type AuthRole = "shop" | "owner";

type ApiConfig = {
  baseUrl: string;
  adminKey?: string;
  token?: string;
};

type Session = {
  role: AuthRole;
  baseUrl: string;
  username: string;
  token?: string;
  adminKey?: string;
  shop?: Shop;
};

function App() {
  const [baseUrl, setBaseUrl] = useState(localStorage.getItem("flowerAdmin.baseUrl") ?? "");
  const [authMode, setAuthMode] = useState<AuthRole>("shop");
  const [username, setUsername] = useState(localStorage.getItem("flowerAdmin.username") ?? "");
  const [password, setPassword] = useState("");
  const [adminKey, setAdminKey] = useState("");
  const [session, setSession] = useState<Session | null>(() => readSession());
  const [shops, setShops] = useState<Shop[]>([]);
  const [shopId, setShopId] = useState<number | null>(Number(localStorage.getItem("flowerAdmin.shopId")) || null);
  const [flowers, setFlowers] = useState<Flower[]>([]);
  const [settings, setSettings] = useState<ShopSettings | null>(null);
  const [draft, setDraft] = useState<FlowerPayload>(emptyFlower);
  const [editing, setEditing] = useState<Record<number, Partial<FlowerPayload>>>({});
  const [credentialsDraft, setCredentialsDraft] = useState({ username: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [tab, setTab] = useState<"flowers" | "settings">("flowers");

  const config = useMemo<ApiConfig | null>(() => sessionToConfig(session), [session]);
  const selectedShop = shops.find((shop) => shop.id === shopId) ?? session?.shop ?? null;

  useEffect(() => {
    if (!session) return;
    void loadAll(session);
  }, []);

  useEffect(() => {
    localStorage.setItem("flowerAdmin.baseUrl", baseUrl);
    if (username) localStorage.setItem("flowerAdmin.username", username);
    if (shopId) localStorage.setItem("flowerAdmin.shopId", String(shopId));
  }, [baseUrl, username, shopId]);

  async function login() {
    if (!baseUrl.trim()) {
      setMessage("Укажите адрес backend на Render.");
      return;
    }

    setBusy(true);
    setMessage("");
    try {
      if (authMode === "shop") {
        const response = await loginShop(baseUrl, username, password);
        const nextSession: Session = {
          role: "shop",
          baseUrl,
          username: response.username,
          token: response.token,
          shop: response.shop,
        };
        saveSession(nextSession);
        setSession(nextSession);
        setPassword("");
        setShops([response.shop]);
        setShopId(response.shop.id);
        await reloadShop(response.shop.id, nextSession);
        setMessage("Вход выполнен.");
        return;
      }

      if (!adminKey.trim()) {
        setMessage("Укажите служебный ключ владельца.");
        return;
      }

      const nextSession: Session = {
        role: "owner",
        baseUrl,
        username: "owner",
        adminKey,
      };
      await getMe(sessionToConfig(nextSession)!);
      saveSession(nextSession);
      setSession(nextSession);
      await loadAll(nextSession);
      setMessage("Служебный вход выполнен.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось войти.");
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    localStorage.removeItem("flowerAdmin.session");
    setSession(null);
    setShops([]);
    setShopId(null);
    setFlowers([]);
    setSettings(null);
    setMessage("");
  }

  async function loadAll(activeSession = session) {
    if (!activeSession) return;

    setBusy(true);
    setMessage("");
    try {
      const activeConfig = sessionToConfig(activeSession);
      if (!activeConfig) return;

      await getMe(activeConfig);

      if (activeSession.role === "shop" && activeSession.shop) {
        setShops([activeSession.shop]);
        setShopId(activeSession.shop.id);
        await reloadShop(activeSession.shop.id, activeSession);
        return;
      }

      const loadedShops = await listShops(activeConfig);
      setShops(loadedShops);
      const nextShopId = shopId ?? loadedShops[0]?.id ?? null;
      setShopId(nextShopId);

      if (nextShopId) {
        await reloadShop(nextShopId, activeSession);
      }
    } catch (error) {
      if (handleAuthError(error)) return;
      setMessage(error instanceof Error ? error.message : "Не удалось загрузить данные.");
    } finally {
      setBusy(false);
    }
  }

  async function reloadShop(nextShopId = shopId, activeSession = session) {
    const activeConfig = sessionToConfig(activeSession);
    if (!nextShopId || !activeConfig) return;
    setBusy(true);
    setMessage("");
    try {
      const [loadedFlowers, loadedSettings] = await Promise.all([
        listFlowers(activeConfig, nextShopId),
        getSettings(activeConfig, nextShopId),
      ]);
      setFlowers(loadedFlowers);
      setSettings(loadedSettings);
      const credentialsShop = shops.find((shop) => shop.id === nextShopId) ?? activeSession?.shop ?? null;
      setCredentialsDraft((current) => ({
        username: current.username || credentialsShop?.slug || "",
        password: current.password,
      }));
    } catch (error) {
      if (handleAuthError(error)) return;
      setMessage(error instanceof Error ? error.message : "Не удалось обновить магазин.");
    } finally {
      setBusy(false);
    }
  }

  async function addFlower() {
    if (!shopId || !config) return;
    if (!draft.name.trim() || draft.price_per_stem <= 0) {
      setMessage("Заполните название товара и цену за стебель.");
      return;
    }

    setBusy(true);
    try {
      await createFlower(config, shopId, normalizeFlower(draft));
      setDraft(emptyFlower);
      await reloadShop(shopId);
      setMessage("Товар добавлен.");
    } catch (error) {
      if (handleAuthError(error)) return;
      setMessage(error instanceof Error ? error.message : "Не удалось добавить товар.");
    } finally {
      setBusy(false);
    }
  }

  async function saveFlower(flower: Flower) {
    if (!config) return;
    setBusy(true);
    try {
      await updateFlower(config, flower.id, normalizePartialFlower(editing[flower.id] ?? {}));
      setEditing((current) => {
        const next = { ...current };
        delete next[flower.id];
        return next;
      });
      await reloadShop(shopId);
      setMessage("Товар сохранен.");
    } catch (error) {
      if (handleAuthError(error)) return;
      setMessage(error instanceof Error ? error.message : "Не удалось сохранить товар.");
    } finally {
      setBusy(false);
    }
  }

  async function hideFlower(flower: Flower) {
    if (!config) return;
    setBusy(true);
    try {
      await deactivateFlower(config, flower.id);
      await reloadShop(shopId);
      setMessage("Товар скрыт из подбора.");
    } catch (error) {
      if (handleAuthError(error)) return;
      setMessage(error instanceof Error ? error.message : "Не удалось скрыть товар.");
    } finally {
      setBusy(false);
    }
  }

  async function saveSettings() {
    if (!shopId || !settings || !config) return;
    setBusy(true);
    try {
      await updateSettings(config, shopId, {
        greeting_text: settings.greeting_text,
        tone: settings.tone,
        min_order_price: settings.min_order_price,
        delivery_price: settings.delivery_price,
        working_hours: settings.working_hours,
        manager_chat_id: settings.manager_chat_id || null,
        ai_enabled: settings.ai_enabled,
        image_generation_enabled: settings.image_generation_enabled,
      });
      await reloadShop(shopId);
      setMessage("Настройки сохранены.");
    } catch (error) {
      if (handleAuthError(error)) return;
      setMessage(error instanceof Error ? error.message : "Не удалось сохранить настройки.");
    } finally {
      setBusy(false);
    }
  }

  async function saveCredentials() {
    if (!shopId || !config || session?.role !== "owner") return;
    if (!credentialsDraft.username.trim() || credentialsDraft.password.length < 8) {
      setMessage("Укажите логин и пароль не короче 8 символов.");
      return;
    }

    setBusy(true);
    try {
      const response = await setShopCredentials(config, shopId, credentialsDraft);
      setCredentialsDraft({ username: response.username, password: "" });
      setMessage(`Доступ для магазина сохранен: ${response.username}`);
    } catch (error) {
      if (handleAuthError(error)) return;
      setMessage(error instanceof Error ? error.message : "Не удалось сохранить доступ магазина.");
    } finally {
      setBusy(false);
    }
  }

  function handleAuthError(error: unknown) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      logout();
      setMessage("Доступ устарел или ключ неверный. Войдите заново.");
      return true;
    }
    return false;
  }

  if (!session) {
    return (
      <LoginScreen
        authMode={authMode}
        setAuthMode={setAuthMode}
        baseUrl={baseUrl}
        setBaseUrl={setBaseUrl}
        username={username}
        setUsername={setUsername}
        password={password}
        setPassword={setPassword}
        adminKey={adminKey}
        setAdminKey={setAdminKey}
        login={login}
        busy={busy}
        message={message}
      />
    );
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">{session.role === "owner" ? "Служебный доступ" : "Кабинет магазина"}</p>
          <h1>{selectedShop?.name ?? "Панель магазина"}</h1>
        </div>
        <div className="topActions">
          <button className="iconButton" onClick={() => void loadAll()} disabled={busy} title="Обновить">
            {busy ? <Loader2 className="spin" size={18} /> : <RefreshCw size={18} />}
          </button>
          <button className="iconButton" onClick={logout} title="Выйти">
            <LogOut size={18} />
          </button>
        </div>
      </header>

      {message && <div className="notice">{message}</div>}

      <section className="workspace">
        <aside className="sidebar">
          <div className="panelTitle">Магазин</div>
          <div className="shopList">
            {shops.map((shop) => (
              <button
                key={shop.id}
                className={shop.id === shopId ? "shop active" : "shop"}
                onClick={() => {
                  setShopId(shop.id);
                  setCredentialsDraft({ username: shop.slug, password: "" });
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
              <h2>{tab === "flowers" ? "Товары и остатки" : "Настройки бота"}</h2>
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
            <SettingsView
              settings={settings}
              setSettings={setSettings}
              saveSettings={saveSettings}
              busy={busy}
              isOwner={session.role === "owner"}
              credentialsDraft={credentialsDraft}
              setCredentialsDraft={setCredentialsDraft}
              saveCredentials={saveCredentials}
            />
          )}
        </section>
      </section>
    </main>
  );
}

function LoginScreen(props: {
  authMode: AuthRole;
  setAuthMode: (value: AuthRole) => void;
  baseUrl: string;
  setBaseUrl: (value: string) => void;
  username: string;
  setUsername: (value: string) => void;
  password: string;
  setPassword: (value: string) => void;
  adminKey: string;
  setAdminKey: (value: string) => void;
  login: () => Promise<void>;
  busy: boolean;
  message: string;
}) {
  return (
    <main className="loginShell">
      <section className="loginPanel">
        <div>
          <p className="eyebrow">Flower AI Platform</p>
          <h1>Вход в панель</h1>
        </div>

        <div className="modeSwitch">
          <button className={props.authMode === "shop" ? "active" : ""} onClick={() => props.setAuthMode("shop")}>
            <KeyRound size={16} />
            Магазин
          </button>
          <button className={props.authMode === "owner" ? "active" : ""} onClick={() => props.setAuthMode("owner")}>
            <ShieldCheck size={16} />
            Владелец
          </button>
        </div>

        <TextInput
          label="Адрес backend"
          value={props.baseUrl}
          onChange={props.setBaseUrl}
          placeholder="https://flower-ai-backend-n37n.onrender.com"
        />

        {props.authMode === "shop" ? (
          <>
            <TextInput label="Логин магазина" value={props.username} onChange={props.setUsername} />
            <TextInput label="Пароль" value={props.password} onChange={props.setPassword} type="password" />
          </>
        ) : (
          <TextInput label="Служебный ключ владельца" value={props.adminKey} onChange={props.setAdminKey} type="password" />
        )}

        <button className="primary loginButton" onClick={() => void props.login()} disabled={props.busy}>
          {props.busy ? <Loader2 className="spin" size={17} /> : <Check size={17} />}
          Войти
        </button>

        {props.message && <div className="notice">{props.message}</div>}
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
        <TextInput label="Название товара" value={draft.name} onChange={(name) => setDraft({ ...draft, name })} placeholder="Роза" />
        <TextInput label="Тип цветка" value={draft.category ?? ""} onChange={(category) => setDraft({ ...draft, category })} placeholder="rose" />
        <TextInput label="Цвет для подбора" value={draft.color ?? ""} onChange={(color) => setDraft({ ...draft, color })} placeholder="red" />
        <NumberInput label="Цена за стебель" value={draft.price_per_stem} onChange={(price_per_stem) => setDraft({ ...draft, price_per_stem })} />
        <NumberInput label="Всего в наличии" value={draft.quantity_available} onChange={(quantity_available) => setDraft({ ...draft, quantity_available })} />
        <button className="primary addButton" onClick={() => void addFlower()} disabled={busy}>
          <PackagePlus size={17} />
          Добавить
        </button>
      </div>

      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Название товара</th>
              <th>Тип</th>
              <th>Цвет</th>
              <th>Цена за стебель</th>
              <th>В наличии</th>
              <th>Резерв</th>
              <th>Доступно</th>
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
                    <button className="iconButton danger" onClick={() => void hideFlower(flower)} disabled={busy} title="Скрыть из подбора">
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
  isOwner: boolean;
  credentialsDraft: { username: string; password: string };
  setCredentialsDraft: (value: { username: string; password: string }) => void;
  saveCredentials: () => Promise<void>;
}) {
  const {
    settings,
    setSettings,
    saveSettings,
    busy,
    isOwner,
    credentialsDraft,
    setCredentialsDraft,
    saveCredentials,
  } = props;

  if (!settings) return <div className="empty">Настройки появятся после подключения.</div>;

  return (
    <>
      <div className="settingsGrid">
        <label>
          <span>Текст приветствия в боте</span>
          <textarea value={settings.greeting_text ?? ""} onChange={(event) => setSettings({ ...settings, greeting_text: event.target.value })} />
        </label>
        <label>
          <span>Стиль общения бота</span>
          <select value={settings.tone} onChange={(event) => setSettings({ ...settings, tone: event.target.value })}>
            <option value="friendly">Дружелюбный</option>
            <option value="elegant">Элегантный</option>
            <option value="concise">Краткий</option>
          </select>
        </label>
        <NumberInput label="Минимальная сумма заказа" value={settings.min_order_price} onChange={(min_order_price) => setSettings({ ...settings, min_order_price })} />
        <NumberInput label="Стоимость доставки" value={settings.delivery_price} onChange={(delivery_price) => setSettings({ ...settings, delivery_price })} />
        <TextInput label="График работы" value={settings.working_hours ?? ""} onChange={(working_hours) => setSettings({ ...settings, working_hours })} placeholder="Пн-Вс 09:00-21:00" />
        <NumberInput label="Telegram chat_id менеджеров" value={settings.manager_chat_id ?? 0} onChange={(manager_chat_id) => setSettings({ ...settings, manager_chat_id })} />
        <label className="toggle">
          <input type="checkbox" checked={settings.ai_enabled} onChange={(event) => setSettings({ ...settings, ai_enabled: event.target.checked })} />
          <span>Бот отвечает клиентам</span>
        </label>
        <label className="toggle">
          <input type="checkbox" checked={settings.image_generation_enabled} onChange={(event) => setSettings({ ...settings, image_generation_enabled: event.target.checked })} />
          <span>Эскизы букетов через ИИ</span>
        </label>
        <button className="primary saveSettings" onClick={() => void saveSettings()} disabled={busy}>
          <Save size={17} />
          Сохранить настройки
        </button>
      </div>

      {isOwner && (
        <div className="credentialsPanel">
          <div>
            <p className="eyebrow">Доступ магазина</p>
            <h2>Логин и пароль</h2>
          </div>
          <TextInput
            label="Логин магазина"
            value={credentialsDraft.username}
            onChange={(username) => setCredentialsDraft({ ...credentialsDraft, username })}
          />
          <TextInput
            label="Новый пароль"
            value={credentialsDraft.password}
            onChange={(password) => setCredentialsDraft({ ...credentialsDraft, password })}
            type="password"
          />
          <button className="primary saveSettings" onClick={() => void saveCredentials()} disabled={busy}>
            <KeyRound size={17} />
            Сохранить доступ
          </button>
        </div>
      )}
    </>
  );
}

function TextInput(props: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <label>
      <span>{props.label}</span>
      <input
        value={props.value}
        onChange={(event) => props.onChange(event.target.value)}
        placeholder={props.placeholder}
        type={props.type ?? "text"}
      />
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

function sessionToConfig(session: Session | null): ApiConfig | null {
  if (!session) return null;
  return {
    baseUrl: session.baseUrl,
    adminKey: session.adminKey,
    token: session.token,
  };
}

function readSession(): Session | null {
  const raw = localStorage.getItem("flowerAdmin.session");
  if (!raw) return null;

  try {
    return JSON.parse(raw) as Session;
  } catch {
    localStorage.removeItem("flowerAdmin.session");
    return null;
  }
}

function saveSession(session: Session) {
  localStorage.setItem("flowerAdmin.session", JSON.stringify(session));
  localStorage.setItem("flowerAdmin.baseUrl", session.baseUrl);
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
