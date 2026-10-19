import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import {
  AlertOctagon,
  AlertTriangle,
  CreditCard,
  FileQuestion,
  FileSearch,
  Landmark,
  MessageSquare,
  Paperclip,
  Rocket,
  ScanLine,
  Search,
  Send,
  ShieldCheck,
  Timer,
  Users,
} from "lucide-react";
import { useApp } from "../context/AppContext";
import { api, ApiError } from "../lib/api";
import {
  AMOUNT_VARS,
  MISSING_DETAIL_CHIPS,
  VARIABLE_LABELS,
  autoVariables,
  cx,
  formatAmountInput,
  ils,
  localizedButtons,
  parseAmount,
  renderTemplate,
  templateBody,
  templateName,
  VAT_DEADLINE_DAY,
} from "../lib/format";
import type { Client } from "../lib/types";
import { DateInput } from "../components/DateInput";
import {
  AttachmentChip,
  MANUAL_ATTACHMENT_ACCEPT,
  attachmentError,
  attachmentKind,
  useObjectUrl,
} from "../components/ManualAttachment";
import { WaBubble } from "../components/WaBubble";
import { Button, Card, Empty, Field, inputClass, Ltr, SectionTitle } from "../components/ui";

const CARD_META: Record<string, { title: string; icon: ReactNode; tone: string }> = {
  missing_supplier_invoice: { title: "חשבונית חסרה", icon: <FileQuestion className="h-5 w-5" />, tone: "text-sky-600 bg-sky-50" },
  missing_invoice_detail: { title: "פרט חסר", icon: <FileSearch className="h-5 w-5" />, tone: "text-indigo-600 bg-indigo-50" },
  unidentified_bank_charge: { title: "חיוב לא מזוהה", icon: <CreditCard className="h-5 w-5" />, tone: "text-amber-600 bg-amber-50" },
  tax_ready_to_pay: { title: "דיווח מס מוכן", icon: <Landmark className="h-5 w-5" />, tone: "text-emerald-600 bg-emerald-50" },
  monthly_folder_deadline_warning: { title: "מועד דיווח דחוף", icon: <AlertOctagon className="h-5 w-5" />, tone: "text-red-600 bg-red-50" },
};

const DATE_VARS = new Set(["invoice_date", "charge_date", "due_date"]);
const GROSS_AMOUNT_VARS = new Set(["amount", "charge_amount"]);

function ddmmyyyy(d: Date): string {
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}

export function QuickDispatch() {
  const { clients, templates, selectedClientId, selectClient, toast, refreshClients, settings, user } = useApp();
  // "template": automated request with 48h follow-up; "manual": the worker's own free text / picture.
  const [mode, setMode] = useState<"template" | "manual">("template");
  const [manualText, setManualText] = useState("");
  const [manualFile, setManualFile] = useState<File | null>(null);
  const [manualError, setManualError] = useState<string | null>(null);
  const manualFileRef = useRef<HTMLInputElement>(null);
  const manualTextRef = useRef<HTMLTextAreaElement>(null);
  const manualPreviewUrl = useObjectUrl(manualFile);
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);
  const [templateId, setTemplateId] = useState<number | null>(null);
  const [vars, setVars] = useState<Record<string, string>>({});
  const [suppliers, setSuppliers] = useState<string[]>([]);
  const [sending, setSending] = useState(false);
  const [missing, setMissing] = useState<string[]>([]);
  const [lastSent, setLastSent] = useState<{ ref: string; ms: number; client: string } | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const firstInputRef = useRef<HTMLInputElement>(null);

  const vatRate = settings?.vat_rate ?? 18;
  const allocationThreshold = settings?.allocation_number_threshold_nis ?? 10000;
  const client = clients.find((c) => c.id === selectedClientId) ?? null;
  const cards = useMemo(() => templates.filter((t) => !t.is_system && CARD_META[t.slug]), [templates]);
  const template = templates.find((t) => t.id === templateId) ?? null;
  const workerName = user?.full_name ?? "עובד/ת המשרד";

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const digits = q.replace(/\D/g, "");
    return clients
      .filter((c) => c.is_active)
      .filter(
        (c) =>
          !q ||
          c.full_name.toLowerCase().includes(q) ||
          c.company_name.toLowerCase().includes(q) ||
          (digits.length > 2 && (c.whatsapp_phone.replace(/\D/g, "").includes(digits) || c.tax_id.includes(digits))),
      );
  }, [clients, query]);

  useEffect(() => setHighlight(0), [query]);
  useEffect(() => {
    if (!templateId && cards.length) setTemplateId(cards[0].id);
  }, [cards, templateId]);
  useEffect(() => {
    api.supplierSuggestions(client?.id).then(setSuppliers).catch(() => setSuppliers([]));
  }, [client?.id]);
  useEffect(() => {
    searchRef.current?.focus();
  }, []);

  // Pre-fill sensible defaults whenever the template or client changes.
  useEffect(() => {
    if (!template || !client) return;
    setMissing([]);
    setVars((prev) => {
      const next: Record<string, string> = {};
      for (const v of template.required_variables) next[v] = prev[v] ?? "";
      if (template.slug === "monthly_folder_deadline_warning") {
        const auto = autoVariables(client);
        next.days_left = auto.days_left;
        next.open_items_count = auto.open_items_count;
      }
      if ("tax_period" in next && !next.tax_period) {
        const d = new Date();
        const m = d.getDate() > 15 ? d : new Date(d.getFullYear(), d.getMonth() - 1, 1);
        next.tax_period = `${String(m.getMonth() + 1).padStart(2, "0")}/${m.getFullYear()}`;
      }
      if ("due_date" in next && !next.due_date) {
        const d = new Date();
        const day = VAT_DEADLINE_DAY;
        const due = d.getDate() <= day ? new Date(d.getFullYear(), d.getMonth(), day) : new Date(d.getFullYear(), d.getMonth() + 1, day);
        next.due_date = ddmmyyyy(due);
      }
      return next;
    });
  }, [template?.id, client?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const inputVars = template
    ? template.slug === "monthly_folder_deadline_warning"
      ? ["days_left", "open_items_count"]
      : template.required_variables
    : [];

  const finalVars = useMemo(() => {
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(vars)) out[k] = AMOUNT_VARS.has(k) ? formatAmountInput(v) : v.trim();
    return out;
  }, [vars]);

  const preview = template && client ? renderTemplate(templateBody(template), { ...autoVariables(client), ...finalVars }) : "";
  const previewButtons = template ? localizedButtons(template) : [];
  const unfilled = inputVars.filter((v) => !String(vars[v] ?? "").trim());

  const focusComposer = (which: "template" | "manual") =>
    window.setTimeout(() => (which === "manual" ? manualTextRef.current : firstInputRef.current)?.focus(), 30);

  const pickClient = (c: Client) => {
    selectClient(c.id, true);
    setQuery("");
    focusComposer(mode);
  };

  const pickTemplate = (id: number) => {
    setTemplateId(id);
    setMode("template");
  };

  const pickManual = () => {
    setMode("manual");
    focusComposer("manual");
  };

  const send = async () => {
    if (!client || !template || sending) return;
    if (unfilled.length) {
      setMissing(unfilled);
      return;
    }
    setSending(true);
    try {
      const r = await api.quickSend({ client_id: client.id, template_id: template.id, context_variables: finalVars });
      setLastSent({ ref: r.ticket.ticket_ref, ms: r.elapsed_ms, client: client.full_name });
      toast({
        tone: "success",
        title: `${r.ticket.ticket_ref} נשלח ל${client.full_name} תוך ${Math.round(r.elapsed_ms)} אלפיות שנייה`,
        body: `מעקב אוטומטי הופעל: תזכורת כל ${settings?.reminder_interval_hours ?? 48} שעות. צפו בטלפון של הלקוח בצד ←`,
      });
      const keep: Record<string, string> = {};
      for (const k of ["tax_period", "due_date"]) if (vars[k]) keep[k] = vars[k];
      setVars(keep);
      refreshClients().catch(() => undefined);
      api.supplierSuggestions(client.id).then(setSuppliers).catch(() => undefined);
      searchRef.current?.focus();
    } catch (e) {
      if (e instanceof ApiError && e.missing.length) setMissing(e.missing);
      toast({ tone: "error", title: "השליחה נכשלה", body: e instanceof Error ? e.message : String(e) });
    } finally {
      setSending(false);
    }
  };

  const onManualFile = (file: File | undefined) => {
    if (manualFileRef.current) manualFileRef.current.value = "";
    if (!file) return;
    const error = attachmentError(file);
    setManualError(error);
    if (!error) setManualFile(file);
  };

  const sendManual = async () => {
    if (!client || sending) return;
    const text = manualText.trim();
    if (!text && !manualFile) {
      setManualError("כתבו הודעה או צרפו תמונה או קובץ");
      manualTextRef.current?.focus();
      return;
    }
    setSending(true);
    try {
      const m = await api.manualSend(client.id, text, manualFile);
      toast({
        tone: "success",
        title: `ההודעה הידנית נשלחה ל${client.full_name}`,
        body: m.media_url ? "ההודעה והקובץ המצורף מופיעים בטלפון של הלקוח בצד ←" : "ההודעה מופיעה בטלפון של הלקוח בצד ←",
      });
      setManualText("");
      setManualFile(null);
      setManualError(null);
      refreshClients().catch(() => undefined);
      manualTextRef.current?.focus();
    } catch (e) {
      toast({ tone: "error", title: "שליחת ההודעה הידנית נכשלה", body: e instanceof Error ? e.message : String(e) });
    } finally {
      setSending(false);
    }
  };

  const onSearchKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter" && filtered[highlight]) {
      e.preventDefault();
      pickClient(filtered[highlight]);
    }
  };

  /** Gross amount -> net + VAT at the office's live VAT rate (and the allocation-number hint). */
  const vatBreakdown = (key: string): ReactNode => {
    const gross = parseAmount(vars[key]);
    if (gross === null || gross <= 0) return null;
    const net = gross / (1 + vatRate / 100);
    const needsAllocation = net >= allocationThreshold;
    return (
      <p className="mt-1 text-[11px] text-slate-500">
        לפני מע״מ {ils(net)} · מע״מ {vatRate}% {ils(gross - net)}
        {needsAllocation && (
          <span className="ms-1 inline-flex items-center gap-1 font-semibold text-amber-700">
            · <AlertTriangle className="h-3 w-3" /> חובת מספר הקצאה (מעל {ils(allocationThreshold)})
          </span>
        )}
      </p>
    );
  };

  const manualHasContent = manualText.trim().length > 0 || manualFile !== null;

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">שליחת בקשה</h1>
          <p className="text-sm text-slate-500">בוחרים לקוח, בוחרים בקשה, ממלאים את החסר ולוחצים Enter. הבוט ימשיך לרדוף אחרי הלקוח בוואטסאפ.</p>
        </div>
        {lastSent && (
          <div className="rounded-lg bg-emerald-50 px-3 py-1.5 text-xs text-emerald-800 ring-1 ring-emerald-200">
            אחרון: <b>{lastSent.ref}</b> ← {lastSent.client} · {Math.round(lastSent.ms)} אלפיות שנייה
          </div>
        )}
      </header>

      <div className="grid gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
        {/* Step 1 */}
        <Card className="flex max-h-[calc(100vh-170px)] flex-col p-4">
          <SectionTitle step="1" title="לקוח" hint="חיפוש לפי שם, עסק, טלפון או ח.פ · ↑↓ Enter" />
          <div className="relative mb-3">
            <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              ref={searchRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onSearchKey}
              placeholder="שם, עסק, 052-123…, ח.פ…"
              className={cx(inputClass, "ps-9")}
              dir="auto"
            />
          </div>
          <div className="-mx-1 min-h-0 flex-1 space-y-1 overflow-y-auto px-1">
            {filtered.length === 0 && <Empty icon={<Users className="h-8 w-8" />} title="לא נמצאו לקוחות" />}
            {filtered.map((c, i) => (
              <button
                key={c.id}
                onClick={() => pickClient(c)}
                className={cx(
                  "flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-start transition",
                  c.id === client?.id ? "bg-brand-50 ring-1 ring-brand-500" : i === highlight && query ? "bg-slate-100" : "hover:bg-slate-50",
                )}
              >
                <div className="min-w-0 flex-1">
                  <p dir="auto" className="truncate text-sm font-medium text-slate-900">
                    {c.full_name}
                  </p>
                  <p dir="auto" className="truncate text-xs text-slate-500">
                    {c.company_name}
                  </p>
                  <p className="truncate text-[11px] text-slate-400">
                    <Ltr>{c.whatsapp_phone}</Ltr> · ח.פ <Ltr>{c.tax_id || "—"}</Ltr>
                  </p>
                </div>
                {c.open_ticket_count > 0 && (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800" title="פניות פתוחות">
                    {c.open_ticket_count}
                  </span>
                )}
              </button>
            ))}
          </div>
        </Card>

        <div className="space-y-5">
          {/* Step 2 */}
          <Card className="p-4">
            <SectionTitle step="2" title="מה צריך מהלקוח?" hint="תבניות אוטומטיות בלחיצה אחת או הודעה ידנית חופשית · כל ההודעות נשלחות בעברית" />
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {cards.map((t) => {
                const meta = CARD_META[t.slug];
                const active = mode === "template" && t.id === templateId;
                return (
                  <button
                    key={t.id}
                    onClick={() => pickTemplate(t.id)}
                    className={cx(
                      "flex flex-col items-start gap-2 rounded-xl border p-3 text-start transition",
                      active ? "border-brand-500 bg-brand-50/60 ring-1 ring-brand-500" : "border-slate-200 hover:border-slate-300 hover:bg-slate-50",
                    )}
                  >
                    <span className={cx("grid h-9 w-9 place-items-center rounded-lg", meta.tone)}>{meta.icon}</span>
                    <span className="text-sm font-semibold text-slate-900">{meta.title}</span>
                    <span className="line-clamp-2 text-[11px] text-slate-500">{templateName(t)}</span>
                    {t.requires_media_reply && (
                      <span className="inline-flex items-center gap-1 text-[10px] font-medium text-indigo-600">
                        <ScanLine className="h-3 w-3" /> אימות Vision AI
                      </span>
                    )}
                  </button>
                );
              })}
              <button
                onClick={pickManual}
                className={cx(
                  "flex flex-col items-start gap-2 rounded-xl border p-3 text-start transition",
                  mode === "manual" ? "border-wa-teal bg-teal-50/60 ring-1 ring-wa-teal" : "border-dashed border-slate-300 hover:border-slate-400 hover:bg-slate-50",
                )}
              >
                <span className="grid h-9 w-9 place-items-center rounded-lg bg-teal-50 text-wa-teal">
                  <MessageSquare className="h-5 w-5" />
                </span>
                <span className="text-sm font-semibold text-slate-900">הודעה ידנית חופשית</span>
                <span className="line-clamp-2 text-[11px] text-slate-500">טקסט חופשי ותמונה או קובץ, בשמך</span>
                <span className="text-[10px] font-medium text-slate-400">ללא תזכורות אוטומטיות</span>
              </button>
            </div>
          </Card>

          <div className="grid gap-5 xl:grid-cols-2">
            {/* Step 3 */}
            {mode === "manual" ? (
              <Card className="p-4">
                <SectionTitle
                  step="3"
                  title="כותבים הודעה ללקוח"
                  hint={client ? `נשלחת בשם ${workerName} · הלקוח רואה ”הודעה מאת ${workerName}“` : "בחרו קודם לקוח"}
                />
                {!client ? (
                  <Empty icon={<Users className="h-8 w-8" />} title="בחרו לקוח" />
                ) : (
                  <form
                    className="space-y-3"
                    onSubmit={(e) => {
                      e.preventDefault();
                      sendManual();
                    }}
                  >
                    <Field label="תוכן ההודעה">
                      <textarea
                        ref={manualTextRef}
                        value={manualText}
                        onChange={(e) => {
                          setManualText(e.target.value);
                          setManualError(null);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                            e.preventDefault();
                            sendManual();
                          }
                        }}
                        rows={5}
                        dir="auto"
                        placeholder={`שלום ${client.full_name}, …`}
                        className={cx(inputClass, "resize-y leading-relaxed")}
                      />
                    </Field>
                    <input
                      ref={manualFileRef}
                      type="file"
                      accept={MANUAL_ATTACHMENT_ACCEPT}
                      className="hidden"
                      onChange={(e) => onManualFile(e.target.files?.[0])}
                    />
                    {manualFile ? (
                      <AttachmentChip file={manualFile} previewUrl={manualPreviewUrl} onRemove={() => setManualFile(null)} disabled={sending} />
                    ) : (
                      <Button
                        type="button"
                        variant="secondary"
                        className="w-full"
                        icon={<Paperclip className="h-4 w-4" />}
                        onClick={() => manualFileRef.current?.click()}
                        disabled={sending}
                      >
                        צירוף תמונה או קובץ
                      </Button>
                    )}
                    <p className="text-[11px] text-slate-400">JPG, PNG, WEBP או PDF · עד 15MB</p>
                    {manualError && <p className="text-xs font-medium text-red-600">{manualError}</p>}
                    <Button
                      type="submit"
                      variant="wa"
                      size="lg"
                      loading={sending}
                      disabled={!manualHasContent}
                      className="!h-auto min-h-12 w-full py-3 text-center leading-snug"
                      icon={<Send className="h-5 w-5 shrink-0 -scale-x-100" />}
                    >
                      שלח הודעה ידנית ללקוח
                    </Button>
                    <p className="text-center text-[11px] text-slate-400">Ctrl+Enter לשליחה · ההודעה נרשמת ביומן הפעילות</p>
                  </form>
                )}
              </Card>
            ) : (
              <Card className="p-4">
                <SectionTitle step="3" title="ממלאים רק את החסר" hint={client ? "שם הלקוח והעסק ממולאים אוטומטית" : "בחרו קודם לקוח"} />
                {!client || !template ? (
                  <Empty icon={<Users className="h-8 w-8" />} title="בחרו לקוח ותבנית" />
                ) : (
                  <form
                    className="space-y-3"
                    onSubmit={(e) => {
                      e.preventDefault();
                      send();
                    }}
                  >
                    {inputVars.map((v, idx) => {
                      const meta = VARIABLE_LABELS[v] ?? { label: v, placeholder: "" };
                      const isMissing = missing.includes(v);
                      return (
                        <Field key={v} label={meta.label}>
                          {DATE_VARS.has(v) ? (
                            <DateInput
                              ref={idx === 0 ? firstInputRef : undefined}
                              value={vars[v] ?? ""}
                              onChange={(val) => {
                                setVars((p) => ({ ...p, [v]: val }));
                                setMissing((m) => m.filter((x) => x !== v));
                              }}
                              placeholder={meta.placeholder}
                              className={cx(isMissing && "ring-2 ring-red-400")}
                            />
                          ) : (
                            <input
                              ref={idx === 0 ? firstInputRef : undefined}
                              value={vars[v] ?? ""}
                              onChange={(e) => {
                                setVars((p) => ({ ...p, [v]: e.target.value }));
                                setMissing((m) => m.filter((x) => x !== v));
                              }}
                              onBlur={() => AMOUNT_VARS.has(v) && setVars((p) => ({ ...p, [v]: formatAmountInput(p[v] ?? "") }))}
                              placeholder={meta.placeholder}
                              list={v === "supplier_name" ? "supplier-suggestions" : undefined}
                              dir={AMOUNT_VARS.has(v) ? "ltr" : "auto"}
                              inputMode={AMOUNT_VARS.has(v) ? "decimal" : undefined}
                              className={cx(inputClass, AMOUNT_VARS.has(v) && "text-end", isMissing && "ring-2 ring-red-400")}
                            />
                          )}
                          {GROSS_AMOUNT_VARS.has(v) && vatBreakdown(v)}
                          {DATE_VARS.has(v) && (
                            <div className="mt-1 flex gap-1">
                              {[0, -1, -7].map((off) => (
                                <button
                                  key={off}
                                  type="button"
                                  onClick={() => setVars((p) => ({ ...p, [v]: ddmmyyyy(new Date(Date.now() + off * 86400000)) }))}
                                  className="rounded bg-slate-100 px-1.5 py-0.5 text-[10.5px] text-slate-600 hover:bg-slate-200"
                                >
                                  {off === 0 ? "היום" : off === -1 ? "אתמול" : "לפני שבוע"}
                                </button>
                              ))}
                            </div>
                          )}
                          {v === "missing_detail" && (
                            <>
                              <div className="mt-1 flex flex-wrap gap-1">
                                {MISSING_DETAIL_CHIPS.map((chip) => (
                                  <button
                                    key={chip}
                                    type="button"
                                    onClick={() => setVars((p) => ({ ...p, missing_detail: chip }))}
                                    className="rounded bg-slate-100 px-1.5 py-0.5 text-[10.5px] text-slate-600 hover:bg-slate-200"
                                  >
                                    {chip}
                                  </button>
                                ))}
                              </div>
                              {/הקצאה|ח\.פ|ע\.מ|עוסק/.test(vars.missing_detail ?? "") && (
                                <p className="mt-1 flex items-center gap-1 text-[11px] font-medium text-indigo-700">
                                  <ShieldCheck className="h-3.5 w-3.5" /> תשובת הלקוח תיבדק אוטומטית: בדיוק 9 ספרות לפי הוראות רשות המסים
                                </p>
                              )}
                            </>
                          )}
                        </Field>
                      );
                    })}
                    <datalist id="supplier-suggestions">
                      {suppliers.map((s) => (
                        <option key={s} value={s} />
                      ))}
                    </datalist>
                    {missing.length > 0 && <p className="text-xs font-medium text-red-600">נא למלא: {missing.map((m) => VARIABLE_LABELS[m]?.label ?? m).join(", ")}</p>}
                    <Button
                      type="submit"
                      variant="wa"
                      size="lg"
                      loading={sending}
                      className="!h-auto min-h-12 w-full py-3 text-center leading-snug"
                      icon={<Rocket className="h-5 w-5 shrink-0" />}
                    >
                      שליחה לוואטסאפ והפעלת מעקב {settings?.reminder_interval_hours ?? 48} שעות (Enter)
                    </Button>
                    <p className="flex items-center justify-center gap-1.5 text-[11px] text-slate-400">
                      <Timer className="h-3.5 w-3.5" /> תזכורת כל {settings?.reminder_interval_hours ?? 48} שעות · עד {settings?.max_reminders ?? 3} תזכורות · הסלמה לקראת
                      מועד הדיווח <Ltr>{client.next_deadline}</Ltr>
                    </p>
                  </form>
                )}
              </Card>
            )}

            {/* Live preview */}
            <Card className="overflow-hidden">
              <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
                <h3 className="text-sm font-semibold text-slate-900">תצוגה מקדימה של הוואטסאפ</h3>
                {client && <span className="text-xs text-slate-500">עברית · מימין לשמאל</span>}
              </div>
              <div className="min-h-[260px] bg-wa-wall p-4" dir="rtl">
                {client && mode === "manual" ? (
                  manualHasContent ? (
                    <WaBubble
                      text={manualText.trim()}
                      fromFirm
                      compact
                      automated={false}
                      senderName={workerName}
                      mediaPath={manualPreviewUrl}
                      mediaKind={manualFile ? attachmentKind(manualFile) : undefined}
                      type={manualFile ? "IMAGE_UPLOAD" : "TEXT"}
                    />
                  ) : (
                    <p className="py-16 text-center text-xs text-slate-500">כתבו הודעה או צרפו תמונה כדי לראות כאן את מה שהלקוח יקבל.</p>
                  )
                ) : client && template ? (
                  <WaBubble text={preview} fromFirm buttons={previewButtons} compact type="TEMPLATE" automated />
                ) : (
                  <p className="py-16 text-center text-xs text-slate-500">כאן תופיע ההודעה המדויקת שהלקוח יקבל.</p>
                )}
              </div>
              {mode === "template" && template && client && unfilled.length > 0 && (
                <p className="border-t border-slate-200 px-4 py-2 text-[11px] text-amber-700">
                  ”—“ מסמן שדות שעדיין לא מולאו: {unfilled.map((u) => VARIABLE_LABELS[u]?.label ?? u).join(", ")}
                </p>
              )}
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
