import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowRight, ChevronLeft, CloudFog, FileX2, Paperclip, Phone, ScanLine, Send, Smartphone, Video, Wifi, WifiOff } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api, ApiError } from "../lib/api";
import { cx, dayLabel, initials, STATUS_META } from "../lib/format";
import type { InboundResult, Message, RenderedButton, Ticket } from "../lib/types";
import { Ltr, Spinner } from "./ui";
import { WaBubble } from "./WaBubble";

const DONE_STATUSES = new Set(["RESOLVED"]);

export function PhoneSimulator() {
  const { clients, selectedClientId, selectClient, phoneOpen, setPhoneOpen, tick, live, toast, settings } = useApp();
  const firm = settings?.firm_name ?? "משרד רואי חשבון";
  const client = clients.find((c) => c.id === selectedClientId) ?? null;
  const [messages, setMessages] = useState<Message[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [text, setText] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    if (!client) return;
    const [msgs, tks] = await Promise.all([api.messages(client.id), api.tickets({ client_id: client.id })]);
    setMessages(msgs);
    setTickets(tks);
  }, [client?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!client) return;
    setLoading(true);
    load()
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, [client?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Ticks coalesce bursts of events from many clients, so refetch on every tick (one small query).
  useEffect(() => {
    if (!client || tick === 0) return;
    load().catch(() => undefined);
  }, [tick]); // eslint-disable-line react-hooks/exhaustive-deps

  // The phone "opens the chat": blue ticks for the firm's messages.
  useEffect(() => {
    if (!client || !phoneOpen) return;
    const unread = messages.some((m) => m.direction === "OUTBOUND" && m.delivery_status !== "READ" && m.delivery_status !== "FAILED");
    if (!unread) return;
    const t = window.setTimeout(() => api.markRead(client.id).catch(() => undefined), 1200);
    return () => window.clearTimeout(t);
  }, [messages, client?.id, phoneOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, busy, client?.id]);

  const ticketById = useMemo(() => new Map(tickets.map((t) => [t.id, t])), [tickets]);

  // Only the newest button-bearing message of each still-open ticket is interactive (like real WhatsApp UX).
  const liveButtonMessageIds = useMemo(() => {
    const latest = new Map<string, number>();
    for (const m of messages) {
      if (m.direction === "OUTBOUND" && m.buttons_json?.length) latest.set(String(m.ticket_id ?? "none"), m.id);
    }
    const ids = new Set<number>();
    latest.forEach((msgId, key) => {
      const tk = key === "none" ? null : ticketById.get(Number(key));
      if (tk && !DONE_STATUSES.has(tk.status)) ids.add(msgId);
    });
    return ids;
  }, [messages, ticketById]);

  const activeTicket = useMemo(() => {
    const open = tickets.filter((t) => !DONE_STATUSES.has(t.status));
    return (
      open.find((t) => t.status === "NEEDS_CORRECTION") ??
      open.find((t) => t.requires_media_reply && ["WAITING_FOR_CLIENT", "SNOOZED_TONIGHT", "ESCALATED"].includes(t.status)) ??
      open[0] ??
      null
    );
  }, [tickets]);

  const report = (r: InboundResult, label: string) => {
    if (r.validation) {
      const fieldName = r.validation.field === "allocation_number" ? "מספר הקצאה" : "ח.פ / ע.מ";
      toast({
        tone: r.validation.valid ? "success" : "warning",
        title: r.validation.valid ? `${fieldName} תקין נקלט ✓` : `${fieldName} נדחה — חייב להכיל בדיוק 9 ספרות`,
        body: r.reply ?? undefined,
        dir: "rtl",
      });
    } else if (r.ocr) {
      const ok = r.ocr.is_valid === true;
      const manual = r.ocr.is_valid === null;
      toast({
        tone: ok ? "success" : manual ? "info" : "warning",
        title: ok
          ? `Vision AI אימת את חשבונית ${r.ocr.invoice_number} תוך ${Math.round(r.elapsed_ms ?? 0)} אלפיות שנייה`
          : manual
            ? "המסמך הועבר לבדיקת פקיד"
            : `Vision AI דחה את הצילום ← ${r.ticket ? STATUS_META[r.ticket.status].short : ""}`,
        body: ok ? `${r.ocr.supplier_name} · סה״כ ${r.ocr.total_amount}` : r.ocr.rejection_reason_he ?? r.ocr.provider_note,
      });
    } else if (r.ticket) {
      toast({ tone: "info", title: `${label} ← ${STATUS_META[r.ticket.status].label}`, body: r.ticket.ticket_ref });
    }
  };

  const run = async (key: string, label: string, fn: () => Promise<InboundResult>) => {
    setBusy(key);
    try {
      const r = await fn();
      report(r, label);
      await load();
    } catch (e) {
      toast({ tone: "error", title: "פעולת הסימולטור נכשלה", body: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const onButton = (m: Message) => (b: RenderedButton) => {
    if (!client) return;
    run(`btn-${m.id}-${b.id}`, `הלקוח לחץ ”${b.title}“`, () => api.sendButton(client.id, b.id, m.ticket_id));
  };

  const sendText = () => {
    if (!client || !text.trim()) return;
    const value = text.trim();
    setText("");
    run("text", "הלקוח השיב", () => api.sendText(client.id, value));
  };

  const onFile = (file: File | undefined) => {
    if (!client || !file) return;
    run("upload", "הלקוח העלה קובץ", () => api.uploadMedia(client.id, file, activeTicket?.id));
    if (fileRef.current) fileRef.current.value = "";
  };

  const demo = (scenario: "clear" | "blurry" | "missing_number") => {
    if (!client) return;
    run(`demo-${scenario}`, "קבלת הדגמה", () => api.demoReceipt(client.id, scenario, activeTicket?.id));
  };

  if (!phoneOpen) {
    return (
      <button
        onClick={() => setPhoneOpen(true)}
        className="fixed end-0 top-1/2 z-30 flex -translate-y-1/2 flex-col items-center gap-2 rounded-s-xl bg-wa-header px-2 py-4 text-white shadow-lg hover:bg-wa-teal"
        title="פתיחת סימולטור הוואטסאפ של הלקוח"
      >
        <Smartphone className="h-5 w-5" />
        <span className="text-[11px] font-semibold [writing-mode:vertical-rl]">הטלפון של הלקוח</span>
      </button>
    );
  }

  const groups: { day: string; items: Message[] }[] = [];
  for (const m of messages) {
    const day = dayLabel(m.created_at);
    if (!groups.length || groups[groups.length - 1].day !== day) groups.push({ day, items: [] });
    groups[groups.length - 1].items.push(m);
  }

  return (
    <aside className="fixed inset-y-0 end-0 z-30 flex w-[400px] max-w-full flex-col border-s border-slate-200 bg-slate-100 shadow-xl xl:static xl:z-auto xl:shadow-none">
      <div className="flex items-center gap-2 border-b border-slate-200 bg-white px-3 py-2.5">
        <Smartphone className="h-4 w-4 text-wa-teal" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-slate-900">📱 סימולטור וואטסאפ חי של הלקוח</p>
          <p className="flex items-center gap-1 text-[11px] text-slate-500">
            {live ? <Wifi className="h-3 w-3 text-emerald-500" /> : <WifiOff className="h-3 w-3 text-amber-500" />}
            {live ? "מחובר בזמן אמת" : "מתחבר מחדש (רענון תקופתי)"}
          </p>
        </div>
        <button onClick={() => setPhoneOpen(false)} className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" title="כיווץ">
          <ChevronLeft className="h-4 w-4 rotate-180" />
        </button>
      </div>

      <div className="px-3 pt-2.5">
        <select
          value={client?.id ?? ""}
          onChange={(e) => selectClient(Number(e.target.value))}
          className="w-full rounded-lg border-0 bg-white py-1.5 pe-8 ps-2 text-xs text-slate-800 ring-1 ring-slate-300 focus:ring-2 focus:ring-wa-teal"
        >
          {clients
            .filter((c) => c.is_active)
            .map((c) => (
              <option key={c.id} value={c.id}>
                {c.full_name} · {c.company_name}
                {c.open_ticket_count ? ` · ${c.open_ticket_count} פתוחות` : ""}
              </option>
            ))}
        </select>
      </div>

      <div className="flex min-h-0 flex-1 items-stretch justify-center p-3">
        <div className="flex w-full max-w-[370px] flex-col overflow-hidden rounded-[2.2rem] border-[7px] border-slate-900 bg-slate-900 shadow-2xl">
          {/* status bar */}
          <div className="relative flex h-6 items-center justify-between bg-wa-header px-5 text-[10px] font-semibold text-white" dir="ltr">
            <span>{new Date().toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" })}</span>
            <span className="absolute left-1/2 top-0 h-4 w-24 -translate-x-1/2 rounded-b-xl bg-slate-900" />
            <span>5G ▮▮▮</span>
          </div>
          {/* chat header */}
          <div className="flex items-center gap-2 bg-wa-header px-2 pb-2 pt-1 text-white">
            <ArrowRight className="h-4 w-4 opacity-80" />
            <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-emerald-200 text-xs font-bold text-wa-header">{initials(firm)}</div>
            <div className="min-w-0 flex-1 leading-tight">
              <p className="truncate text-[13px] font-semibold">{firm} ✔︎</p>
              <p className="truncate text-[10.5px] opacity-80">חשבון עסקי · בטלפון של {client?.full_name ?? "—"}</p>
            </div>
            <Video className="h-4 w-4 opacity-80" />
            <Phone className="h-4 w-4 opacity-80" />
          </div>

          {/* conversation */}
          <div
            ref={scrollRef}
            className="relative min-h-0 flex-1 space-y-1.5 overflow-y-auto bg-wa-wall px-2.5 py-3"
            style={{
              backgroundImage:
                "radial-gradient(rgba(0,0,0,0.035) 1px, transparent 1px), radial-gradient(rgba(0,0,0,0.025) 1px, transparent 1px)",
              backgroundSize: "18px 18px, 11px 11px",
              backgroundPosition: "0 0, 6px 9px",
            }}
          >
            {client && (
              <div className="mx-auto mb-2 max-w-[90%] rounded-md bg-amber-50 px-2 py-1 text-center text-[10.5px] text-amber-900 shadow-sm">
                🔒 הודעות אל <Ltr>{client.whatsapp_phone}</Ltr> · בעברית
              </div>
            )}
            {loading && (
              <div className="flex justify-center py-6">
                <Spinner />
              </div>
            )}
            {!loading && messages.length === 0 && (
              <p className="py-10 text-center text-xs text-slate-500">אין עדיין הודעות. שלחו בקשה מעמדת ”שליחת בקשה“.</p>
            )}
            {groups.map((g) => (
              <div key={g.day} className="space-y-1.5">
                <div className="sticky top-0 z-10 flex justify-center py-1">
                  <span className="rounded-md bg-sky-50/95 px-2 py-0.5 text-[10.5px] font-medium text-slate-600 shadow-sm">{g.day}</span>
                </div>
                {g.items.map((m) => (
                  <WaBubble
                    key={m.id}
                    text={m.content_text}
                    fromFirm={m.direction === "OUTBOUND"}
                    createdAt={m.created_at}
                    buttons={m.buttons_json}
                    delivery={m.delivery_status}
                    mediaPath={m.media_url}
                    type={m.message_type}
                    buttonsDisabled={!liveButtonMessageIds.has(m.id) || busy !== null}
                    onButton={onButton(m)}
                  />
                ))}
              </div>
            ))}
            {busy && (
              <div className="flex items-start">
                <div className="flex items-center gap-1 rounded-lg rounded-ss-none bg-white px-3 py-2 shadow-sm">
                  {busy.startsWith("demo") || busy === "upload" ? (
                    <span className="flex items-center gap-1.5 text-[11px] text-indigo-700">
                      <ScanLine className="h-3.5 w-3.5 animate-pulse" /> Vision AI בודק את הצילום…
                    </span>
                  ) : (
                    [0, 1, 2].map((i) => (
                      <span key={i} className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-slate-400" style={{ animationDelay: `${i * 0.2}s` }} />
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {/* demo actions */}
          <div className="space-y-1 bg-[#f0f2f5] px-2 pt-2">
            <div className="flex items-center justify-between px-0.5 text-[10px] text-slate-500">
              <span className="font-semibold">הדגמת Vision AI</span>
              <span className="truncate ps-2" dir="rtl">
                {activeTicket ? `${activeTicket.ticket_ref} · ${activeTicket.context_variables_json.supplier_name ?? activeTicket.template_name}` : "אין בקשה פתוחה"}
              </span>
            </div>
            <DemoButton
              icon={<ScanLine className="h-3.5 w-3.5" />}
              label="📸 הדמיה: הלקוח שולח חשבונית תקינה וברורה"
              className="bg-emerald-600 hover:bg-emerald-700"
              loading={busy === "demo-clear"}
              disabled={!client || busy !== null}
              onClick={() => demo("clear")}
            />
            <DemoButton
              icon={<CloudFog className="h-3.5 w-3.5" />}
              label="🌫️ הדמיה: הלקוח שולח קבלה מטושטשת"
              className="bg-amber-500 hover:bg-amber-600"
              loading={busy === "demo-blurry"}
              disabled={!client || busy !== null}
              onClick={() => demo("blurry")}
            />
            <DemoButton
              icon={<FileX2 className="h-3.5 w-3.5" />}
              label="❌ הדמיה: חשבונית ללא מספר חשבונית"
              className="bg-rose-600 hover:bg-rose-700"
              loading={busy === "demo-missing_number"}
              disabled={!client || busy !== null}
              onClick={() => demo("missing_number")}
            />
          </div>

          {/* composer */}
          <form
            className="flex items-center gap-1.5 bg-[#f0f2f5] px-2 pb-3 pt-2"
            onSubmit={(e) => {
              e.preventDefault();
              sendText();
            }}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".jpg,.jpeg,.png,.webp,.pdf,image/jpeg,image/png,image/webp,application/pdf"
              className="hidden"
              onChange={(e) => onFile(e.target.files?.[0])}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={!client || busy !== null}
              className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-slate-500 hover:bg-white disabled:opacity-40"
              title="העלאת צילום / PDF אמיתי מהמחשב"
            >
              <Paperclip className="h-4 w-4" />
            </button>
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              dir="auto"
              placeholder={client ? `השב כ${client.full_name}…` : "בחרו לקוח"}
              disabled={!client}
              className="h-9 min-w-0 flex-1 rounded-full border-0 bg-white px-3.5 text-[13px] text-slate-900 ring-0 placeholder:text-slate-400 focus:ring-1 focus:ring-wa-teal"
            />
            <button
              type="submit"
              disabled={!client || !text.trim() || busy !== null}
              className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-wa-teal text-white hover:bg-wa-header disabled:opacity-40"
              title="שליחה בשם הלקוח"
            >
              <Send className="h-4 w-4 -scale-x-100" />
            </button>
          </form>
        </div>
      </div>
      {client && (
        <div className="flex items-center gap-2 border-t border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-500">
          <span className="grid h-6 w-6 place-items-center rounded-full bg-slate-200 text-[10px] font-bold text-slate-600">{initials(client.full_name)}</span>
          <span dir="auto" className="truncate font-medium text-slate-700">
            {client.full_name}
          </span>
          <span className="ms-auto shrink-0">{tickets.filter((t) => !DONE_STATUSES.has(t.status)).length} בקשות פתוחות</span>
        </div>
      )}
    </aside>
  );
}

function DemoButton({
  icon,
  label,
  className,
  loading,
  disabled,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  className: string;
  loading: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cx(
        "flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-start text-[11.5px] font-semibold text-white shadow-sm transition disabled:opacity-50",
        className,
      )}
    >
      {loading ? <Spinner className="!h-3.5 !w-3.5 text-white" /> : icon}
      <span className="truncate">{label}</span>
    </button>
  );
}
