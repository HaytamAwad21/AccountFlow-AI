import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { API_BASE, api, getToken, setToken, setUnauthorizedHandler } from "../lib/api";
import type { AppSettings, Client, ServerEvent, Template, User } from "../lib/types";

export type ToastTone = "info" | "success" | "warning" | "error";
export interface Toast {
  id: number;
  title: string;
  body?: string;
  tone: ToastTone;
  dir?: "rtl" | "ltr" | "auto";
}

interface AppState {
  /** false until the stored session token has been checked with /api/auth/me */
  authChecked: boolean;
  clients: Client[];
  templates: Template[];
  users: User[];
  user: User | null;
  isManager: boolean;
  settings: AppSettings | null;
  selectedClientId: number | null;
  phoneOpen: boolean;
  tick: number;
  tickTypes: ServerEvent["type"][];
  live: boolean;
  toasts: Toast[];
  selectClient: (id: number | null, openPhone?: boolean) => void;
  setPhoneOpen: (open: boolean) => void;
  /** Password login. Replaces (and revokes) any current session. Throws ApiError on failure. */
  login: (userId: number, password: string) => Promise<User>;
  logout: () => Promise<void>;
  refreshClients: () => Promise<void>;
  refreshTemplates: () => Promise<void>;
  refreshSettings: () => Promise<void>;
  refreshUsers: () => Promise<void>;
  toast: (t: Omit<Toast, "id">, ttlMs?: number) => void;
  dismissToast: (id: number) => void;
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [authChecked, setAuthChecked] = useState(false);
  const [sessionUser, setSessionUser] = useState<User | null>(null);
  const [clients, setClients] = useState<Client[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [selectedClientId, setSelectedClientId] = useState<number | null>(null);
  const [phoneOpen, setPhoneOpen] = useState(true);
  const [tick, setTick] = useState(0);
  const [live, setLive] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastSeq = useRef(0);
  const tickTimer = useRef<number | null>(null);
  const pendingTypes = useRef<Set<ServerEvent["type"]>>(new Set());
  const [tickTypes, setTickTypes] = useState<ServerEvent["type"][]>([]);

  const refreshClients = useCallback(async () => {
    setClients(await api.clients("", true));
  }, []);
  const refreshTemplates = useCallback(async () => {
    setTemplates(await api.templates());
  }, []);
  const refreshSettings = useCallback(async () => {
    setSettings(await api.settings());
  }, []);
  const refreshUsers = useCallback(async () => {
    setUsers(await api.users());
  }, []);

  const dismissToast = useCallback((id: number) => setToasts((ts) => ts.filter((t) => t.id !== id)), []);
  const toast = useCallback(
    (t: Omit<Toast, "id">, ttlMs = 5000) => {
      const id = ++toastSeq.current;
      setToasts((ts) => [...ts.slice(-5), { ...t, id }]);
      window.setTimeout(() => dismissToast(id), ttlMs);
    },
    [dismissToast],
  );

  const clearSession = useCallback(() => {
    setToken(null);
    setSessionUser(null);
    setClients([]);
    setTemplates([]);
    setUsers([]);
    setSettings(null);
    setSelectedClientId(null);
  }, []);

  // Any 401 from the API (expired / revoked session, suspended user) drops back to the login screen.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (getToken()) toast({ tone: "warning", title: "ההתחברות הסתיימה", body: "יש להתחבר מחדש עם הסיסמה." });
      clearSession();
    });
    return () => setUnauthorizedHandler(null);
  }, [clearSession, toast]);

  // Restore a stored session on page load.
  useEffect(() => {
    if (!getToken()) {
      setAuthChecked(true);
      return;
    }
    api
      .me()
      .then(setSessionUser)
      .catch(() => clearSession())
      .finally(() => setAuthChecked(true));
  }, [clearSession]);

  const login = useCallback(
    async (userId: number, password: string) => {
      const previous = getToken();
      const res = await api.login(userId, password);
      setToken(res.token);
      if (previous && previous !== res.token) api.logout(previous); // revoke the replaced session
      setSessionUser(res.user);
      toast({
        tone: "success",
        title: `ברוך/ה הבא/ה, ${res.user.full_name.split(" - ")[0]}`,
        body: res.user.role === "MANAGER" ? "מחובר/ת כמנהל/ת משרד" : "מחובר/ת כעובד/ת משרד",
      });
      return res.user;
    },
    [toast],
  );

  const logout = useCallback(async () => {
    await api.logout();
    clearSession();
    toast({ tone: "info", title: "התנתקת מהמערכת" });
  }, [clearSession, toast]);

  // Coalesce bursts of server events into one refetch tick, remembering every event type seen.
  const bump = useCallback((type?: ServerEvent["type"]) => {
    if (type) pendingTypes.current.add(type);
    if (tickTimer.current !== null) return;
    tickTimer.current = window.setTimeout(() => {
      tickTimer.current = null;
      setTickTypes(Array.from(pendingTypes.current));
      pendingTypes.current = new Set();
      setTick((n) => n + 1);
    }, 150);
  }, []);

  const loggedInId = sessionUser?.id ?? null;

  // Load shared data once logged in; retries while the API is still starting.
  useEffect(() => {
    if (loggedInId === null) return;
    let cancelled = false;
    let attempt = 0;
    const load = async () => {
      try {
        await Promise.all([refreshClients(), refreshTemplates(), refreshSettings(), refreshUsers()]);
        if (attempt > 0 && !cancelled) toast({ tone: "success", title: "החיבור לשרת AccountFlow הצליח" });
      } catch (e) {
        if (cancelled || !getToken()) return;
        if (attempt === 1) {
          toast({ tone: "warning", title: "ממתין לשרת AccountFlow…", body: e instanceof Error ? e.message : String(e) }, 6000);
        }
        attempt += 1;
        window.setTimeout(load, Math.min(1000 * attempt, 5000));
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [loggedInId, refreshClients, refreshTemplates, refreshSettings, refreshUsers, toast]);

  // Real-time stream (SSE) with automatic polling fallback, only while logged in.
  useEffect(() => {
    if (loggedInId === null) return;
    let es: EventSource | null = null;
    let poll: number | null = null;
    let closed = false;

    const startPolling = () => {
      if (poll === null) poll = window.setInterval(() => setTick((n) => n + 1), 4000);
    };
    const stopPolling = () => {
      if (poll !== null) {
        window.clearInterval(poll);
        poll = null;
      }
    };
    es = new EventSource(`${API_BASE}/api/events/stream`);
    es.onopen = () => {
      setLive(true);
      stopPolling();
    };
    es.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data) as ServerEvent;
        if (ev.type === "hello") return;
        bump(ev.type);
      } catch {
        /* ignore malformed frames */
      }
    };
    es.onerror = () => {
      if (closed) return;
      setLive(false);
      startPolling();
    };
    return () => {
      closed = true;
      es?.close();
      stopPolling();
      setLive(false);
    };
  }, [bump, loggedInId]);

  // Keep shared lists fresh when the server reports changes.
  useEffect(() => {
    if (!tickTypes.length || loggedInId === null) return;
    if (tickTypes.some((t) => ["message", "ticket", "client", "campaign", "scheduler"].includes(t))) refreshClients().catch(() => undefined);
    if (tickTypes.includes("template")) refreshTemplates().catch(() => undefined);
    if (tickTypes.includes("settings")) refreshSettings().catch(() => undefined);
    if (tickTypes.includes("users")) {
      refreshUsers().catch(() => undefined);
      api.me().then(setSessionUser).catch(() => undefined); // own role / name may have changed
    }
  }, [tick]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (selectedClientId === null && clients.length) {
      const firstActive = clients.find((c) => c.is_active);
      if (firstActive) setSelectedClientId(firstActive.id);
    }
  }, [clients, selectedClientId]);

  // Prefer the freshest copy from the users list (e.g. right after a manager renamed this user).
  const user = useMemo(() => {
    if (!sessionUser) return null;
    return users.find((u) => u.id === sessionUser.id) ?? sessionUser;
  }, [users, sessionUser]);

  const selectClient = useCallback((id: number | null, openPhone = false) => {
    setSelectedClientId(id);
    if (openPhone) setPhoneOpen(true);
  }, []);

  const value: AppState = {
    authChecked,
    clients,
    templates,
    users,
    user,
    isManager: user?.role === "MANAGER",
    settings,
    selectedClientId,
    phoneOpen,
    tick,
    tickTypes,
    live,
    toasts,
    selectClient,
    setPhoneOpen,
    login,
    logout,
    refreshClients,
    refreshTemplates,
    refreshSettings,
    refreshUsers,
    toast,
    dismissToast,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApp must be used inside <AppProvider>");
  return ctx;
}
