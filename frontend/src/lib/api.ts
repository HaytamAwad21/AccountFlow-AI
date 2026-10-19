import type {
  ActivityPage,
  AppSettings,
  BulkUploadResult,
  Campaign,
  CampaignDetail,
  Client,
  ClientInput,
  EditableSettings,
  InboundResult,
  Kpis,
  LoginResponse,
  LoginUser,
  Message,
  QuickSendResponse,
  SchedulerResult,
  Template,
  TemplateButton,
  Ticket,
  TicketDetail,
  TicketPriority,
  TicketStatus,
  User,
  UserRole,
} from "./types";
import type { Currency } from "./format";

export const API_BASE: string = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";

export class ApiError extends Error {
  status: number;
  missing: string[];

  constructor(status: number, message: string, missing: string[] = []) {
    super(message);
    this.status = status;
    this.missing = missing;
  }
}

const TOKEN_KEY = "accountflow.token";

function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

let authToken: string | null = readToken();
let onUnauthorized: (() => void) | null = null;

export function getToken(): string | null {
  return authToken;
}

/** Session token from POST /api/auth/login; sent as `Authorization: Bearer …` on every request. */
export function setToken(token: string | null): void {
  authToken = token;
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: the session lasts until the tab is closed */
  }
}

/** Called when the API answers 401 (expired / revoked session, suspended user). */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

function detailMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (typeof d === "object" && d && "msg" in d) {
          const field = (d as { loc?: unknown[] }).loc?.slice(-1)[0] ?? "";
          const msg = String((d as { msg: string }).msg).replace(/^Value error,\s*/, "");
          if (field === "tax_id" && /pattern/i.test(msg)) return "ח.פ / ע.מ חייב להכיל בדיוק 9 ספרות";
          // Whole-request checks (e.g. strict variable types) already name the field in Hebrew.
          if (field === "body" || field === "") return msg;
          return `${field}: ${msg}`;
        }
        return String(d);
      })
      .join("; ");
  }
  return "הבקשה נכשלה";
}

function authHeaders(init?: HeadersInit, token: string | null = authToken): Headers {
  const headers = new Headers(init);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = authHeaders(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    let missing: string[] = [];
    try {
      const body = await res.json();
      message = detailMessage(body.detail) || message;
      missing = body.missing ?? [];
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401 && !path.startsWith("/api/auth/login") && onUnauthorized) onUnauthorized();
    throw new ApiError(res.status, message, missing);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) });

function filenameFrom(res: Response, fallback: string): string {
  const cd = res.headers.get("Content-Disposition") ?? "";
  const m = /filename="?([^";]+)"?/i.exec(cd);
  return m ? m[1] : fallback;
}

export async function downloadFile(path: string, fallbackName: string): Promise<{ filename: string }> {
  const res = await fetch(`${API_BASE}${path}`, { headers: authHeaders() });
  if (!res.ok) throw new ApiError(res.status, `ההורדה נכשלה (${res.status})`);
  const blob = await res.blob();
  const filename = filenameFrom(res, fallbackName);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  return { filename };
}

export function mediaUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  return /^(https?:|blob:|data:)/.test(path) ? path : `${API_BASE}${path}`;
}

export const api = {
  loginUsers: () => request<LoginUser[]>("/api/auth/users"),
  login: (userId: number, password: string) =>
    request<LoginResponse>("/api/auth/login", { method: "POST", ...json({ user_id: userId, password }) }),
  /** Revokes the given session token (defaults to the current one). Never throws. */
  logout: async (token: string | null = authToken) => {
    if (!token) return;
    try {
      await fetch(`${API_BASE}/api/auth/logout`, { method: "POST", headers: authHeaders(undefined, token) });
    } catch {
      /* offline: the token simply expires */
    }
  },
  me: () => request<User>("/api/auth/me"),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<{ ok: boolean }>("/api/auth/change-password", {
      method: "POST",
      ...json({ current_password: currentPassword, new_password: newPassword }),
    }),
  activity: (params: { user_id?: number; action?: string; date_from?: string; date_to?: string; q?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    });
    return request<ActivityPage>(`/api/activity?${qs.toString()}`);
  },

  users: () => request<User[]>("/api/users"),
  createUser: (body: { full_name: string; job_title: string; email: string; role: UserRole; is_active: boolean; password: string }) =>
    request<User>("/api/users", { method: "POST", ...json(body) }),
  updateUser: (id: number, body: Partial<Pick<User, "full_name" | "job_title" | "role" | "is_active">> & { password?: string }) =>
    request<User>(`/api/users/${id}`, { method: "PUT", ...json(body) }),

  settings: () => request<AppSettings>("/api/settings"),
  updateSettings: (body: Partial<EditableSettings>) => request<AppSettings>("/api/settings", { method: "PUT", ...json(body) }),
  kpis: () => request<Kpis>("/api/dashboard/kpis"),

  clients: (q = "", includeInactive = false) =>
    request<Client[]>(`/api/clients?q=${encodeURIComponent(q)}&include_inactive=${includeInactive}`),
  createClient: (body: ClientInput) => request<Client>("/api/clients", { method: "POST", ...json(body) }),
  updateClient: (id: number, body: Partial<ClientInput>) => request<Client>(`/api/clients/${id}`, { method: "PUT", ...json(body) }),
  deactivateClient: (id: number) => request<Client>(`/api/clients/${id}`, { method: "DELETE" }),
  messages: (clientId: number) => request<Message[]>(`/api/clients/${clientId}/messages`),

  templates: () => request<Template[]>("/api/templates"),
  updateTemplate: (id: number, body: Partial<Omit<Template, "buttons_json">> & { buttons_json?: TemplateButton[] }) =>
    request<Template>(`/api/templates/${id}`, { method: "PUT", ...json(body) }),
  supplierSuggestions: (clientId?: number) =>
    request<string[]>(`/api/suppliers/suggestions${clientId ? `?client_id=${clientId}` : ""}`),

  quickSend: (body: {
    client_id: number;
    template_id: number;
    context_variables: Record<string, string>;
    /** currency of each money variable; missing entries default to ILS on the server */
    currencies?: Record<string, Currency>;
    priority?: TicketPriority;
  }) =>
    request<QuickSendResponse>("/api/tickets/quick-send", { method: "POST", ...json(body) }),
  tickets: (params: { status?: TicketStatus[]; client_id?: number; q?: string } = {}) => {
    const qs = new URLSearchParams();
    params.status?.forEach((s) => qs.append("status", s));
    if (params.client_id) qs.set("client_id", String(params.client_id));
    if (params.q) qs.set("q", params.q);
    return request<Ticket[]>(`/api/tickets?${qs.toString()}`);
  },
  ticket: (id: number) => request<TicketDetail>(`/api/tickets/${id}`),
  approveTicket: (id: number, note = "") => request<TicketDetail>(`/api/tickets/${id}/approve`, { method: "POST", ...json({ note }) }),
  rejectTicket: (id: number, reason: string) => request<TicketDetail>(`/api/tickets/${id}/reject`, { method: "POST", ...json({ reason }) }),
  resolveTicket: (id: number, note = "") => request<TicketDetail>(`/api/tickets/${id}/resolve`, { method: "POST", ...json({ note }) }),
  reopenTicket: (id: number) => request<TicketDetail>(`/api/tickets/${id}/reopen`, { method: "POST" }),
  editOcr: (id: number, body: Record<string, string | number | null>) =>
    request<TicketDetail>(`/api/tickets/${id}/ocr`, { method: "PATCH", ...json(body) }),

  sendButton: (clientId: number, buttonId: string, ticketId: number | null) =>
    request<InboundResult>("/api/webhook/whatsapp-inbound", {
      method: "POST",
      ...json({ client_id: clientId, type: "button", button_id: buttonId, ticket_id: ticketId }),
    }),
  sendText: (clientId: number, text: string, ticketId?: number | null) =>
    request<InboundResult>("/api/webhook/whatsapp-inbound", {
      method: "POST",
      ...json({ client_id: clientId, type: "text", text, ticket_id: ticketId ?? null }),
    }),
  uploadMedia: (clientId: number, file: File, ticketId?: number | null) => {
    const fd = new FormData();
    fd.append("client_id", String(clientId));
    if (ticketId) fd.append("ticket_id", String(ticketId));
    fd.append("file", file);
    return request<InboundResult>("/api/webhook/whatsapp-inbound", { method: "POST", body: fd });
  },
  demoReceipt: (clientId: number, scenario: "clear" | "blurry" | "missing_number", ticketId?: number | null) =>
    request<InboundResult>("/api/simulator/demo-receipt", {
      method: "POST",
      ...json({ client_id: clientId, scenario, ticket_id: ticketId ?? null }),
    }),
  /** A worker's manual message to the client: free text and / or a picture or PDF (not automated). */
  manualSend: (clientId: number, contentText: string, imageFile?: File | null) => {
    const fd = new FormData();
    fd.append("client_id", String(clientId));
    fd.append("content_text", contentText);
    if (imageFile) fd.append("image_file", imageFile);
    return request<Message>("/api/whatsapp/manual-send", { method: "POST", body: fd });
  },
  markRead: (clientId: number) => request<{ ok: boolean; updated: number }>(`/api/simulator/${clientId}/read`, { method: "POST" }),

  timeJump: (hours = 48) => request<SchedulerResult>(`/api/scheduler/simulate-time-jump?hours=${hours}`, { method: "POST" }),
  triggerCheck: () => request<SchedulerResult>("/api/scheduler/trigger-48h-check", { method: "POST" }),

  campaigns: () => request<Campaign[]>("/api/campaigns"),
  campaign: (id: number) => request<CampaignDetail>(`/api/campaigns/${id}`),
  uploadTaxSheet: (file: File, title?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    if (title) fd.append("title", title);
    return request<BulkUploadResult>("/api/campaigns/bulk-tax-upload", { method: "POST", body: fd });
  },
  demoBatch: () => request<BulkUploadResult>("/api/campaigns/demo-batch", { method: "POST" }),
};
