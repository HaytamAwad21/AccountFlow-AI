import type { Client, RenderedButton, ReportingFrequency, Template, TicketPriority, TicketStatus, UserRole } from "./types";

/** Israeli VAT reports and payments are due on the 26th of the reporting month. */
export const VAT_DEADLINE_DAY = 26;

export const FREQUENCY_LABEL: Record<ReportingFrequency, string> = {
  MONTHLY: "דיווח חד חודשי",
  BIMONTHLY: "דיווח דו חודשי",
};

const HE_NUMBER = new Intl.NumberFormat("he-IL", { maximumFractionDigits: 2 });

/** Hebrew-locale number (1,234.5); wrap the result in a dir="ltr" span inside Hebrew sentences. */
export function formatNumber(value: number): string {
  return HE_NUMBER.format(value);
}


export const ROLE_LABEL: Record<UserRole, string> = { MANAGER: "מנהל משרד", WORKER: "עובד משרד" };

const VAR_RE = /\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g;

export function renderTemplate(body: string, vars: Record<string, string>): string {
  return body.replace(VAR_RE, (_m, name: string) => {
    const v = vars[name];
    return v === undefined || v === null || String(v).trim() === "" ? "—" : String(v);
  });
}

/** WhatsApp contact with clients is Hebrew-only: templates have a single Hebrew text. */
export function templateBody(t: Template): string {
  return t.body_he;
}

export function templateName(t: Template): string {
  return t.name_he;
}

export function localizedButtons(t: Template): RenderedButton[] {
  return t.buttons_json.map((b) => ({ id: b.id, title: b.he || b.id, action: b.action }));
}

/** Business and contact names may be Hebrew or English only. */
const ARABIC_RE = /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/;
export const NAME_LANGUAGE_ERROR = "שם הלקוח ושם העסק יכולים להיות בעברית או באנגלית בלבד";
export function hasArabic(text: string | null | undefined): boolean {
  return ARABIC_RE.test(text ?? "");
}

export function autoVariables(client: Client): Record<string, string> {
  return {
    client_name: client.full_name,
    company_name: client.company_name,
    open_items_count: String(client.open_ticket_count),
    days_left: String(client.days_to_deadline),
  };
}

export const AMOUNT_VARS = new Set(["amount", "charge_amount", "vat_amount", "tax_advance_amount", "expected_amount"]);
/** Variables entered with the HTML date picker (YYYY-MM-DD) and sent to WhatsApp as DD/MM/YYYY. */
export const DATE_VARS = new Set(["invoice_date", "charge_date", "due_date"]);
/** Variables entered with the HTML month picker (YYYY-MM) and sent to WhatsApp as MM/YYYY. */
export const MONTH_VARS = new Set(["tax_period"]);
/** Whole-number variables. */
export const INTEGER_VARS = new Set(["days_left", "open_items_count"]);

export type Currency = "ILS" | "USD";
export const DEFAULT_CURRENCY: Currency = "ILS";
export const CURRENCY_OPTIONS: { value: Currency; symbol: string; label: string }[] = [
  { value: "ILS", symbol: "₪", label: "שקל" },
  { value: "USD", symbol: "$", label: "דולר" },
];

/** What an amount field may contain while typing: digits and one decimal point, at most 2 decimals. */
export const AMOUNT_TYPING_RE = /^\d*(?:\.\d{0,2})?$/;
/** A complete, valid amount. */
const AMOUNT_COMPLETE_RE = /^\d+(?:\.\d{1,2})?$/;
export const NUMBERS_ONLY_ERROR = "נא להזין מספרים בלבד";

/** Same output as the backend (services/money.py): 500 -> "500 ₪" / "$500"; 1240.5 -> "1,240.50 ₪" / "$1,240.50". */
export function formatMoney(value: number, currency: Currency = DEFAULT_CURRENCY): string {
  const rounded = Math.round(value * 100) / 100;
  const digits = Number.isInteger(rounded) ? 0 : 2;
  const number = rounded.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return currency === "USD" ? `$${number}` : `${number} ₪`;
}

/** Hebrew error for a typed variable, or null when it is valid (empty values are checked as "missing"). */
export function variableError(name: string, value: string): string | null {
  const v = value.trim();
  if (!v) return null;
  if (AMOUNT_VARS.has(name)) {
    if (!AMOUNT_COMPLETE_RE.test(v)) return NUMBERS_ONLY_ERROR;
    if (Number(v) <= 0) return "הסכום חייב להיות גדול מאפס";
    return null;
  }
  if (DATE_VARS.has(name)) return isoToDmy(v) ? null : "תאריך לא תקין";
  if (MONTH_VARS.has(name)) return monthToMy(v) ? null : "חודש לא תקין";
  if (INTEGER_VARS.has(name)) return /^\d{1,5}$/.test(v) ? null : "נא להזין מספר שלם בלבד";
  return null;
}

/** Local date -> "YYYY-MM-DD" (the value format of <input type="date">). */
export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** "2026-10-03" -> "03/10/2026"; null when it is not a real calendar date between 2000 and 2100. */
export function isoToDmy(iso: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso.trim());
  if (!m) return null;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const date = new Date(y, mo - 1, d);
  if (y < 2000 || y > 2100 || date.getFullYear() !== y || date.getMonth() !== mo - 1 || date.getDate() !== d) return null;
  return `${m[3]}/${m[2]}/${m[1]}`;
}

/** Local date -> "YYYY-MM" (the value format of <input type="month">). */
export function isoMonth(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** "2026-09" -> "09/2026"; null when invalid. */
export function monthToMy(value: string): string | null {
  const m = /^(\d{4})-(\d{2})$/.exec(value.trim());
  if (!m) return null;
  const [y, mo] = [Number(m[1]), Number(m[2])];
  if (y < 2000 || y > 2100 || mo < 1 || mo > 12) return null;
  return `${m[2]}/${m[1]}`;
}

export function parseAmount(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "number") return value;
  const n = Number(value.replace(/[^\d.-]/g, ""));
  return value.trim() && Number.isFinite(n) ? n : null;
}

export function ils(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `₪${n.toLocaleString("he-IL", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diff = new Date(iso).getTime() - Date.now();
  const mins = Math.round(Math.abs(diff) / 60000);
  if (mins < 1) return "עכשיו";
  let label: string;
  if (mins < 60) label = `${mins} דק׳`;
  else if (mins < 60 * 48) label = `${Math.round(mins / 60)} שע׳`;
  else label = `${Math.round(mins / 1440)} ימים`;
  return diff > 0 ? `בעוד ${label}` : `לפני ${label}`;
}

export function clockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" });
}

export function dayLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(Date.now() - 86400000);
  if (d.toDateString() === today.toDateString()) return "היום";
  if (d.toDateString() === yesterday.toDateString()) return "אתמול";
  return d.toLocaleDateString("he-IL", { weekday: "long", day: "numeric", month: "long" });
}

export function fullDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("he-IL", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export const STATUS_META: Record<TicketStatus, { label: string; short: string; className: string; dot: string }> = {
  OPEN: { label: "פתוח", short: "פתוח", className: "bg-slate-100 text-slate-700 ring-slate-200", dot: "bg-slate-400" },
  WAITING_FOR_CLIENT: { label: "ממתין ללקוח", short: "ממתין", className: "bg-sky-50 text-sky-800 ring-sky-200", dot: "bg-sky-500" },
  SNOOZED_TONIGHT: { label: "נדחה ל-20:00", short: "נדחה", className: "bg-violet-50 text-violet-800 ring-violet-200", dot: "bg-violet-500" },
  NEEDS_CORRECTION: { label: "דרוש תיקון", short: "תיקון", className: "bg-amber-50 text-amber-800 ring-amber-200", dot: "bg-amber-500" },
  NEEDS_CLERK_REVIEW: { label: "ממתין לבדיקת פקיד", short: "לבדיקה", className: "bg-indigo-50 text-indigo-800 ring-indigo-200", dot: "bg-indigo-500" },
  RESOLVED: { label: "טופל", short: "טופל", className: "bg-emerald-50 text-emerald-800 ring-emerald-200", dot: "bg-emerald-500" },
  ESCALATED: { label: "הוסלם", short: "הוסלם", className: "bg-red-50 text-red-700 ring-red-200", dot: "bg-red-500" },
};

export const PRIORITY_META: Record<TicketPriority, { label: string; className: string }> = {
  NORMAL: { label: "רגיל", className: "text-slate-500" },
  HIGH: { label: "גבוה", className: "text-amber-700 font-semibold" },
  URGENT_DEADLINE: { label: "דחוף · מועד דיווח", className: "text-red-600 font-semibold" },
};

export const VARIABLE_LABELS: Record<string, { label: string; placeholder: string }> = {
  supplier_name: { label: "שם הספק", placeholder: "לדוגמה: דלק תחנת דלק" },
  amount: { label: "סכום ששולם", placeholder: "לדוגמה: 1240.50" },
  invoice_date: { label: "תאריך תשלום / חשבונית", placeholder: "" },
  invoice_number: { label: "מספר חשבונית", placeholder: "לדוגמה: 88412" },
  missing_detail: { label: "הפרט החסר", placeholder: "מה חסר בחשבונית?" },
  charge_amount: { label: "סכום החיוב", placeholder: "לדוגמה: 2350" },
  charge_date: { label: "תאריך החיוב", placeholder: "" },
  bank_reference: { label: "אסמכתת בנק / כרטיס", placeholder: "לדוגמה: CC-7781-2290" },
  tax_period: { label: "תקופת דיווח", placeholder: "" },
  vat_amount: { label: "מע״מ לתשלום", placeholder: "לדוגמה: 4820" },
  tax_advance_amount: { label: "מקדמות מס", placeholder: "לדוגמה: 2150" },
  due_date: { label: "מועד אחרון לתשלום", placeholder: "" },
  days_left: { label: "ימים שנותרו (אוטומטי)", placeholder: "" },
  open_items_count: { label: "פריטים פתוחים (אוטומטי)", placeholder: "" },
  rejection_reason: { label: "סיבת הדחייה", placeholder: "" },
};

/** Quick picks for the "missing detail" field. The first two trigger the 9-digit Tax Authority validation. */
export const MISSING_DETAIL_CHIPS = ["מספר הקצאה", "ח.פ / ע.מ של הספק", "מספר חשבונית", "שם העסק ומספר העוסק שלנו", "פירוט מע״מ"];

export function initials(name: string): string {
  const base = name.split(" - ")[0];
  const parts = base.replace(/[^\p{L}\s.-]/gu, "").trim().split(/\s+/).filter(Boolean);
  return (parts[0]?.[0] ?? "?") + (parts.length > 1 ? parts[parts.length - 1][0] : "");
}

/** "מאיה כהן - מנהלת משרד" -> { name: "מאיה כהן", title: "מנהלת משרד" } */
export function splitUserName(fullName: string): { name: string; title: string } {
  const [name, ...rest] = fullName.split(" - ");
  return { name: name.trim(), title: rest.join(" - ").trim() };
}

export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}
