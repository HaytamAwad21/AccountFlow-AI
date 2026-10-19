import { useEffect, useState } from "react";
import { CheckCircle2, CircleDashed, ExternalLink, Pencil, RotateCcw, Smartphone, ThumbsDown, ThumbsUp, XCircle } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api, mediaUrl } from "../lib/api";
import { cx, fullDateTime, ils, relativeTime } from "../lib/format";
import type { OcrResult, TicketDetail } from "../lib/types";
import { Button, inputClass, Ltr, Modal, PriorityLabel, Spinner, StatusBadge } from "./ui";
import { maskDate } from "../lib/date";
import { DateInput } from "./DateInput";
import { WaBubble } from "./WaBubble";

const CHECKS: { key: keyof OcrResult["checks"]; label: string; hint: string }[] = [
  { key: "clarity", label: "חדות / טשטוש", hint: "הטקסט קריא וציון הטשטוש מעל הסף" },
  { key: "document_type", label: "חשבונית מס + מספר", hint: "כותרת 'חשבונית מס / فاتورة ضريبية / Tax Invoice' ומספר חשבונית" },
  { key: "supplier_match", label: "התאמת ספק", hint: "שם הספק תואם לספק שהתבקש" },
  { key: "math_integrity", label: "תקינות חשבון ומע״מ", hint: "לפני מע״מ + מע״מ = סה״כ, לפי שיעור המע״מ שבהגדרות" },
  { key: "tax_id", label: "ח.פ / ע.מ של הספק (9 ספרות)", hint: "הוראות רשות המסים: בדיוק 9 ספרות" },
  { key: "allocation_number", label: "מספר הקצאה (9 ספרות)", hint: "חובה מעל סף ההקצאה שבהגדרות המשרד" },
];

const EDIT_FIELDS: { key: string; label: string; numeric?: boolean; ltr?: boolean }[] = [
  { key: "supplier_name", label: "ספק" },
  { key: "business_id", label: "ח.פ / ע.מ ספק", ltr: true },
  { key: "invoice_number", label: "מספר חשבונית", ltr: true },
  { key: "allocation_number", label: "מספר הקצאה", ltr: true },
  { key: "invoice_date", label: "תאריך חשבונית", ltr: true },
  { key: "net_amount", label: "לפני מע״מ", numeric: true },
  { key: "vat_amount", label: "מע״מ", numeric: true },
  { key: "total_amount", label: "סה״כ", numeric: true },
];

const CONTEXT_LABELS: Record<string, string> = {
  supplier_name: "ספק",
  amount: "סכום",
  invoice_date: "תאריך",
  invoice_number: "מספר חשבונית",
  missing_detail: "פרט חסר",
  charge_amount: "סכום חיוב",
  charge_date: "תאריך חיוב",
  bank_reference: "אסמכתה",
  tax_period: "תקופת דיווח",
  vat_amount: "מע״מ",
  tax_advance_amount: "מקדמות",
  due_date: "מועד תשלום",
  national_insurance: "ביטוח לאומי",
  total_due: "סה״כ לתשלום",
  detail_kind: "סוג הפרט",
  allocation_number: "מספר הקצאה שהוזן",
  tax_id: "ח.פ שהוזן",
  client_reply_text: "תשובת הלקוח",
  last_invalid_value: "ערך שגוי אחרון",
  invalid_attempts: "ניסיונות שגויים",
  classification: "סיווג",
  upload_attempts: "העלאות",
  open_items_count: "פריטים פתוחים",
  days_left: "ימים למועד",
  last_client_text: "הודעה אחרונה מהלקוח",
  client_response: "תגובת הלקוח",
  payment_confirmed_at: "אישור תשלום",
  call_requested_at: "בקשת שיחה",
  forwarded_despite_ocr: "הועבר לפקיד",
  payment_link: "קישור תשלום",
};

const VALUE_LABELS: Record<string, string> = {
  allocation_number: "מספר הקצאה",
  tax_id: "ח.פ / ע.מ",
  personal: "הוצאה פרטית",
  business_no_receipt: "הוצאה עסקית ללא קבלה",
  no_document: "אין ללקוח את המסמך",
  true: "כן",
  false: "לא",
};

function CheckIcon({ value }: { value: boolean | null }) {
  if (value === true) return <CheckCircle2 className="h-4 w-4 text-emerald-600" />;
  if (value === false) return <XCircle className="h-4 w-4 text-red-600" />;
  return <CircleDashed className="h-4 w-4 text-slate-300" />;
}

const OCR_STATUS_LABEL = { PASSED: "עבר", FAILED: "נכשל", MANUAL_REVIEW: "בדיקה ידנית" } as const;

export function TicketModal({ ticketId, onClose }: { ticketId: number | null; onClose: () => void }) {
  const { tick, toast, selectClient } = useApp();
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({});
  const [rejecting, setRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  useEffect(() => {
    if (!ticketId) {
      setTicket(null);
      setEditing(false);
      setRejecting(false);
      setRejectReason("");
      return;
    }
    api.ticket(ticketId).then(setTicket).catch(() => undefined);
  }, [ticketId, tick]);

  const ocr = ticket?.ocr_validation_json ?? null;

  const startEdit = () => {
    const f: Record<string, string> = {};
    for (const { key } of EDIT_FIELDS) {
      const v = ocr ? (ocr as unknown as Record<string, unknown>)[key] : null;
      f[key] = v === null || v === undefined ? "" : String(v);
    }
    const ctx = ticket?.context_variables_json ?? {};
    if (!f.supplier_name && ctx.supplier_name) f.supplier_name = String(ctx.supplier_name);
    if (!f.allocation_number && ctx.allocation_number) f.allocation_number = String(ctx.allocation_number);
    if (!f.business_id && ctx.tax_id) f.business_id = String(ctx.tax_id);
    if (f.invoice_date) f.invoice_date = maskDate(f.invoice_date, ""); // OCR may return YYYY-MM-DD
    setForm(f);
    setEditing(true);
  };

  const act = async (key: string, fn: () => Promise<TicketDetail>, done: string) => {
    setBusy(key);
    try {
      const t = await fn();
      setTicket(t);
      toast({ tone: "success", title: done, body: t.ticket_ref });
      return t;
    } catch (e) {
      toast({ tone: "error", title: "הפעולה נכשלה", body: e instanceof Error ? e.message : String(e) });
      return null;
    } finally {
      setBusy(null);
    }
  };

  const saveOcr = async () => {
    if (!ticket) return;
    const body: Record<string, string | number | null> = {};
    for (const { key, numeric } of EDIT_FIELDS) {
      const raw = (form[key] ?? "").trim();
      if (!raw) continue;
      body[key] = numeric ? Number(raw.replace(/[^\d.-]/g, "")) : raw;
    }
    const t = await act("ocr", () => api.editOcr(ticket.id, body), "שדות החשבונית נשמרו ונבדקו מחדש");
    if (t) setEditing(false);
  };

  const reject = async () => {
    if (!ticket || rejectReason.trim().length < 3) return;
    const t = await act("reject", () => api.rejectTicket(ticket.id, rejectReason.trim()), "החשבונית נדחתה — הלקוח התבקש לשלוח צילום חדש");
    if (t) {
      setRejecting(false);
      setRejectReason("");
    }
  };

  const ctxEntries = ticket
    ? Object.entries(ticket.context_variables_json).filter(
        ([k, v]) => v !== null && v !== "" && !["client_name", "company_name", "awaiting_media", "awaiting_text"].includes(k),
      )
    : [];

  return (
    <Modal
      open={ticketId !== null}
      onClose={onClose}
      wide
      title={
        ticket ? (
          <span className="flex flex-wrap items-center gap-2">
            <Ltr>{ticket.ticket_ref}</Ltr>
            <StatusBadge status={ticket.status} />
            <PriorityLabel priority={ticket.priority} />
          </span>
        ) : (
          "טוען…"
        )
      }
      subtitle={
        ticket && (
          <span className="flex flex-wrap items-center gap-2">
            <span dir="auto">{ticket.client_name}</span>· <span dir="auto">{ticket.company_name}</span>· {ticket.template_name}
          </span>
        )
      }
    >
      {!ticket ? (
        <div className="flex justify-center p-12">
          <Spinner className="h-6 w-6" />
        </div>
      ) : (
        <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_420px]">
          {/* timeline */}
          <div className="border-b border-slate-200 lg:border-b-0 lg:border-e">
            <div className="flex items-center justify-between px-5 py-3 text-xs text-slate-500">
              <span className="font-semibold">ציר הזמן בוואטסאפ · {ticket.messages.length} הודעות</span>
              <span>
                תזכורות {ticket.reminder_count}/{ticket.max_reminders} · הבאה {relativeTime(ticket.next_reminder_at)}
              </span>
            </div>
            <div className="max-h-[62vh] space-y-2 overflow-y-auto bg-wa-wall px-4 py-4">
              {ticket.messages.map((m) => (
                <div key={m.id}>
                  <p className={cx("mb-0.5 text-[10px] text-slate-500", m.direction === "OUTBOUND" ? "text-start" : "text-end")}>
                    {m.sender_name} · {fullDateTime(m.created_at)}
                  </p>
                  <WaBubble
                    text={m.content_text}
                    fromFirm={m.direction === "OUTBOUND"}
                    createdAt={m.created_at}
                    buttons={m.buttons_json}
                    buttonsDisabled
                    delivery={m.delivery_status}
                    mediaPath={m.media_url}
                    type={m.message_type}
                    automated={m.is_automated}
                    senderName={m.sender_name}
                  />
                </div>
              ))}
            </div>
          </div>

          {/* OCR + actions */}
          <div className="max-h-[70vh] space-y-4 overflow-y-auto p-5">
            <div className="flex flex-wrap gap-2">
              {ticket.status !== "RESOLVED" && (
                <Button
                  variant="success"
                  icon={<ThumbsUp className="h-4 w-4" />}
                  loading={busy === "approve"}
                  onClick={() => act("approve", () => api.approveTicket(ticket.id), "החשבונית אושרה והפנייה נסגרה")}
                >
                  אישור החשבונית וסגירה
                </Button>
              )}
              {ticket.status !== "RESOLVED" && ocr && (
                <Button variant="secondary" icon={<ThumbsDown className="h-4 w-4" />} onClick={() => setRejecting((v) => !v)}>
                  דחיית החשבונית
                </Button>
              )}
              {ticket.status === "RESOLVED" ? (
                <Button icon={<RotateCcw className="h-4 w-4" />} loading={busy === "reopen"} onClick={() => act("reopen", () => api.reopenTicket(ticket.id), "הפנייה נפתחה מחדש")}>
                  פתיחה מחדש
                </Button>
              ) : (
                <Button loading={busy === "resolve"} onClick={() => act("resolve", () => api.resolveTicket(ticket.id), "הפנייה נסגרה")}>
                  סגירה ללא חשבונית
                </Button>
              )}
              <Button
                variant="ghost"
                icon={<Smartphone className="h-4 w-4" />}
                onClick={() => {
                  selectClient(ticket.client_id, true);
                  onClose();
                }}
              >
                פתיחת השיחה
              </Button>
            </div>
            {rejecting && ticket.status !== "RESOLVED" && (
              <div className="space-y-2 rounded-lg bg-red-50 p-3 ring-1 ring-inset ring-red-200">
                <label className="block text-xs font-semibold text-red-800" htmlFor="reject-reason">
                  סיבת הדחייה (תישלח ללקוח בוואטסאפ)
                </label>
                <input
                  id="reject-reason"
                  autoFocus
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && reject()}
                  placeholder="לדוגמה: חסר מספר הקצאה בחשבונית"
                  maxLength={300}
                  className={inputClass}
                  dir="auto"
                />
                <div className="flex justify-end gap-2">
                  <Button size="sm" variant="ghost" onClick={() => setRejecting(false)}>
                    ביטול
                  </Button>
                  <Button size="sm" variant="danger" loading={busy === "reject"} disabled={rejectReason.trim().length < 3} onClick={reject}>
                    דחייה ושליחה ללקוח
                  </Button>
                </div>
              </div>
            )}
            {ticket.resolution_note && <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">{ticket.resolution_note}</p>}

            <section>
              <h4 className="mb-2 text-xs font-semibold text-slate-500">הקבלה שהועלתה</h4>
              {ticket.media_file_path ? (
                <a href={mediaUrl(ticket.media_file_path) ?? "#"} target="_blank" rel="noreferrer" className="group relative block overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
                  {/\.pdf$/i.test(ticket.media_file_path) ? (
                    <p className="p-6 text-center text-sm text-slate-600">מסמך PDF — פתיחה</p>
                  ) : (
                    <img src={mediaUrl(ticket.media_file_path) ?? ""} alt="קבלה" className="max-h-72 w-full object-contain" />
                  )}
                  <span className="absolute end-2 top-2 rounded bg-white/90 p-1 text-slate-600 opacity-0 shadow group-hover:opacity-100">
                    <ExternalLink className="h-3.5 w-3.5" />
                  </span>
                </a>
              ) : (
                <p className="rounded-lg border border-dashed border-slate-300 px-3 py-6 text-center text-xs text-slate-400">עדיין לא התקבל מסמך</p>
              )}
            </section>

            <section>
              <div className="mb-2 flex items-center justify-between">
                <h4 className="text-xs font-semibold text-slate-500">אימות Vision AI ורשות המסים</h4>
                {ocr && (
                  <span
                    className={cx(
                      "rounded-full px-2 py-0.5 text-[11px] font-semibold",
                      ocr.is_valid === true ? "bg-emerald-100 text-emerald-800" : ocr.is_valid === false ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-700",
                    )}
                  >
                    {OCR_STATUS_LABEL[ocr.status]} · {Math.round((ocr.confidence_score ?? 0) * 100)}%
                  </span>
                )}
              </div>
              {!ocr ? (
                <p className="text-xs text-slate-400">טרם בוצעה בדיקת OCR.</p>
              ) : (
                <div className="space-y-3">
                  <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                    {CHECKS.map((c) => (
                      <li key={c.key} className="flex items-center gap-2.5 px-3 py-2" title={c.hint}>
                        <CheckIcon value={ocr.checks?.[c.key] ?? null} />
                        <span className="text-sm text-slate-800">{c.label}</span>
                        {c.key === "clarity" && ocr.blur_score !== null && (
                          <span className="ms-auto text-[11px] text-slate-400">ציון חדות {Math.round(ocr.blur_score)}</span>
                        )}
                        {c.key === "supplier_match" && ocr.supplier_match_score !== null && (
                          <span className="ms-auto text-[11px] text-slate-400">{Math.round(ocr.supplier_match_score * 100)}% התאמה</span>
                        )}
                        {c.key === "math_integrity" && ocr.vat_rate_applied !== null && (
                          <span className="ms-auto text-[11px] text-slate-400">מע״מ {ocr.vat_rate_applied}%</span>
                        )}
                        {c.key === "allocation_number" && ocr.allocation_required !== null && (
                          <span className="ms-auto text-[11px] text-slate-400">
                            {ocr.allocation_required ? `חובה (מעל ${ils(ocr.allocation_threshold)})` : "לא נדרש"}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                  {ocr.rejection_reason_he && (
                    <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{ocr.rejection_reason_he}</p>
                  )}

                  {editing ? (
                    <div className="grid grid-cols-2 gap-2">
                      {EDIT_FIELDS.map((f) => (
                        <label key={f.key} className={cx("block", f.key === "supplier_name" && "col-span-2")}>
                          <span className="mb-0.5 block text-[11px] text-slate-500">{f.label}</span>
                          {f.key === "invoice_date" ? (
                            <DateInput value={form[f.key] ?? ""} onChange={(v) => setForm((p) => ({ ...p, [f.key]: v }))} className="py-1.5" />
                          ) : (
                            <input
                              dir={f.ltr || f.numeric ? "ltr" : "auto"}
                              value={form[f.key] ?? ""}
                              onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
                              className={cx(inputClass, "py-1.5")}
                              inputMode={f.numeric ? "decimal" : undefined}
                            />
                          )}
                        </label>
                      ))}
                      <div className="col-span-2 flex gap-2 pt-1">
                        <Button variant="primary" size="sm" loading={busy === "ocr"} onClick={saveOcr}>
                          שמירה ובדיקה מחדש
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
                          ביטול
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <table className="w-full text-sm">
                      <tbody className="divide-y divide-slate-100">
                        {[
                          ["ספק", ocr.supplier_name],
                          ["ח.פ / ע.מ ספק", ocr.business_id],
                          ["מספר חשבונית", ocr.invoice_number],
                          ["מספר הקצאה", ocr.allocation_number],
                          ["תאריך חשבונית", ocr.invoice_date],
                          ["לפני מע״מ", ils(ocr.net_amount)],
                          ["מע״מ", ils(ocr.vat_amount)],
                          ["סה״כ", ils(ocr.total_amount)],
                        ].map(([k, v]) => (
                          <tr key={k}>
                            <td className="py-1.5 pe-2 text-xs text-slate-500">{k}</td>
                            <td dir="auto" className="py-1.5 text-end font-medium text-slate-900">
                              {v || "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                  {!editing && (
                    <Button size="sm" variant="ghost" icon={<Pencil className="h-3.5 w-3.5" />} onClick={startEdit}>
                      תיקון שדות ידני
                    </Button>
                  )}
                  <p className="text-[11px] text-slate-400">
                    מנוע: {ocr.provider}
                    {ocr.simulated ? " (סימולטור לא מקוון)" : ""}. {ocr.provider_note}
                  </p>
                </div>
              )}
              {!ocr && ticket.media_file_path && (
                <Button size="sm" variant="ghost" icon={<Pencil className="h-3.5 w-3.5" />} onClick={startEdit}>
                  הזנת שדות החשבונית ידנית
                </Button>
              )}
            </section>

            {ctxEntries.length > 0 && (
              <section>
                <h4 className="mb-2 text-xs font-semibold text-slate-500">פרטי הבקשה</h4>
                <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
                  {ctxEntries.map(([k, v]) => (
                    <div key={k} className="min-w-0">
                      <dt className="text-slate-400">{CONTEXT_LABELS[k] ?? k.replace(/_/g, " ")}</dt>
                      <dd dir="auto" className="truncate font-medium text-slate-800" title={String(v)}>
                        {VALUE_LABELS[String(v)] ?? String(v)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}
            <p className="text-[11px] text-slate-400">
              נוצר {fullDateTime(ticket.created_at)} · קשר אחרון {relativeTime(ticket.last_contacted_at)}
              {ticket.worker_name ? ` · נשלח ע״י ${ticket.worker_name}` : ""}
            </p>
          </div>
        </div>
      )}
    </Modal>
  );
}
