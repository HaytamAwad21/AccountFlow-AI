import { useCallback, useEffect, useRef, useState } from "react";
import { Download, FileSpreadsheet, Megaphone, PhoneCall, Sparkles, UploadCloud } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api, downloadFile } from "../lib/api";
import { cx, fullDateTime, ils } from "../lib/format";
import type { Campaign, CampaignDetail, PaymentStatus } from "../lib/types";
import { PageHeader } from "../components/PageHeader";
import { Button, Card, Empty, inputClass, Ltr, SectionTitle, StatusBadge } from "../components/ui";

/** Paid is the solid blue, a requested call is the clerk's next action (the accent), a viewed link is a pale tint. */
const PAY_META: Record<PaymentStatus, { label: string; mark: string }> = {
  SENT: { label: "נשלח", mark: "ring-1 ring-inset ring-ink-400" },
  VIEWED: { label: "צפה בקישור התשלום", mark: "bg-brand-300" },
  CONFIRMED_PAID: { label: "אישר תשלום", mark: "bg-brand-600" },
  QUESTION_ASKED: { label: "ביקש שיחה", mark: "bg-accent" },
};

function ProgressBar({ c }: { c: Campaign }) {
  const s = c.stats;
  const total = Math.max(1, s.total);
  const seg = (n: number) => `${(n / total) * 100}%`;
  return (
    <div>
      <div className="flex h-3 overflow-hidden bg-ink-200">
        <div className="bg-brand-600 transition-all" style={{ width: seg(s.confirmed_paid) }} title="אישרו תשלום" />
        <div className="bg-accent transition-all" style={{ width: seg(s.requested_call) }} title="ביקשו שיחה" />
        <div className="bg-brand-300 transition-all" style={{ width: seg(s.viewed) }} title="צפו בקישור" />
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-700">
        <span>
          <b className="text-ink-900">{s.sent}</b> נשלחו
        </span>
        <span>
          <b className="text-ink-900">{s.pending}</b> ממתינים
        </span>
        <span>
          <span className="me-1 inline-block h-2 w-2 bg-brand-600" />
          <b className="text-ink-900">{s.confirmed_paid}</b> אישרו תשלום
        </span>
        <span>
          <span className="me-1 inline-block h-2 w-2 bg-accent" />
          <b className="text-ink-900">{s.requested_call}</b> ביקשו שיחה
        </span>
        <span>
          <span className="me-1 inline-block h-2 w-2 bg-brand-300" />
          <b className="text-ink-900">{s.viewed}</b> צפו בקישור
        </span>
        <span className="ms-auto text-ink-500">
          אושרו {ils(s.confirmed_amount)} מתוך {ils(s.total_due)}
        </span>
      </div>
    </div>
  );
}

export function BulkTax() {
  const { tick, toast, selectClient, settings } = useApp();
  const demoMode = settings?.demo_mode ?? false;
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selected, setSelected] = useState<CampaignDetail | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    const list = await api.campaigns();
    setCampaigns(list);
    const id = selectedId ?? list[0]?.id ?? null;
    if (id) {
      setSelectedId(id);
      setSelected(await api.campaign(id));
    }
  }, [selectedId]);

  useEffect(() => {
    load().catch(() => undefined);
  }, [load, tick]);

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy("upload");
    setErrors([]);
    try {
      const r = await api.uploadTaxSheet(file, title || undefined);
      setErrors(r.errors);
      setSelectedId(r.campaign.id);
      setSelected(r.campaign);
      toast({
        tone: r.errors.length ? "warning" : "success",
        title: `נשלחו ${r.sent} הודעות דיווח אישיות`,
        body: `${r.campaign.title}${r.created_clients ? ` · נוצרו ${r.created_clients} לקוחות חדשים` : ""}${r.errors.length ? ` · ${r.errors.length} שורות דולגו` : ""}`,
      });
      setTitle("");
      await load();
    } catch (e) {
      toast({ tone: "error", title: "ההעלאה נכשלה", body: e instanceof Error ? e.message : String(e) }, 8000);
    } finally {
      setBusy(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const demo = async () => {
    setBusy("demo");
    try {
      const r = await api.demoBatch();
      setSelectedId(r.campaign.id);
      setSelected(r.campaign);
      toast({ tone: "success", title: `קבוצת ההדגמה נשלחה ל-${r.sent} לקוחות`, body: "לחצו שולם או שיחה בסימולטור וצפו בסרגל מתעדכן." });
      await load();
    } catch (e) {
      toast({ tone: "error", title: "שליחת ההדגמה נכשלה", body: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const sample = async (format: "csv" | "xlsx") => {
    try {
      await downloadFile(`/api/campaigns/sample-sheet?format=${format}`, `accountflow_tax_sheet_sample.${format}`);
    } catch (e) {
      toast({ tone: "error", title: "ההורדה נכשלה", body: e instanceof Error ? e.message : String(e) });
    }
  };

  return (
    <>
      <PageHeader title="הודעות ”הדיווח מוכן“ בתפוצה" hint="גוררים את הגיליון החודשי מתוכנת הנהלת החשבונות — כל לקוח מקבל בוואטסאפ את הסכומים שלו, עם כפתורי ”שולם“ ו”שיחה“." />
    <div className="mx-auto max-w-7xl space-y-5 p-4 @3xl:p-6">
      <div className="grid gap-6 @4xl:grid-cols-[400px_minmax(0,1fr)]">
        <div className="space-y-6">
          <Card className="p-4">
            <SectionTitle
              title="העלאת גיליון מס חודשי"
              hint="CSV או Excel · עמודות: client_tax_id, client_phone, client_name, tax_period, vat_amount, tax_advance_amount, due_date · ח.פ חייב להכיל 9 ספרות"
            />
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="שם הקמפיין (רשות) — לדוגמה: דיווח מע״מ ומקדמות אוקטובר 2026" className={cx(inputClass, "mb-3")} />
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                upload(e.dataTransfer.files?.[0]);
              }}
              onClick={() => fileRef.current?.click()}
              className={cx(
                "flex cursor-pointer flex-col items-center justify-center gap-2 border-2 border-dashed px-4 py-8 text-center transition-colors",
                dragging ? "border-brand-500 bg-brand-50" : "border-ink-300 hover:border-brand-500 hover:bg-ink-50",
              )}
            >
              <UploadCloud className={cx("h-8 w-8", dragging ? "text-link" : "text-ink-400")} />
              <p className="text-sm font-medium text-ink-800">{busy === "upload" ? "שולח…" : "גררו לכאן קובץ CSV / XLSX"}</p>
              <p className="text-xs text-ink-500">או לחצו לבחירה · לקוחות מזוהים לפי ח.פ או טלפון, לקוחות חדשים נוצרים אוטומטית</p>
              <Button type="button" variant="accent" size="sm">
                בחירת קובץ
              </Button>
              <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls,text/csv" className="hidden" onChange={(e) => upload(e.target.files?.[0])} />
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" icon={<Download className="h-3.5 w-3.5" />} onClick={() => sample("csv")}>
                הורדת גיליון לדוגמה (CSV)
              </Button>
              <Button size="sm" variant="ghost" icon={<FileSpreadsheet className="h-3.5 w-3.5" />} onClick={() => sample("xlsx")}>
                XLSX
              </Button>
            </div>
            {/* made-up amounts: a demo install only, never real clients */}
            {demoMode && (
              <Button variant="secondary" className="mt-3 w-full" icon={<Sparkles className="h-4 w-4" />} loading={busy === "demo"} onClick={demo}>
                טעינת קבוצת הדגמה מיידית (8 לקוחות)
              </Button>
            )}
            {errors.length > 0 && (
              <div className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-800">
                <p className="mb-1 font-semibold">שורות שדולגו</p>
                <ul className="list-inside list-disc space-y-0.5">
                  {errors.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              </div>
            )}
          </Card>

          <Card className="p-4">
            <h3 className="mb-2 font-display text-lg leading-tight text-ink-900">קמפיינים</h3>
            {campaigns.length === 0 ? (
              <Empty
                icon={<Megaphone className="h-8 w-8" />}
                title="עדיין לא נשלחו תפוצות"
                hint={demoMode ? "העלו גיליון או טענו את קבוצת ההדגמה." : "העלו גיליון כדי לשלוח את הדיווח ללקוחות."}
              />
            ) : (
              campaigns.map((c) => (
                <button
                  key={c.id}
                  onClick={() => {
                    setSelectedId(c.id);
                    api.campaign(c.id).then(setSelected);
                  }}
                  className={cx("block w-full p-3 text-start transition-colors", selectedId === c.id ? "bg-ink-100" : "hover:bg-ink-50")}
                >
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <p className="truncate text-sm font-semibold text-ink-900">{c.title}</p>
                    <span className="shrink-0 text-xs text-ink-500">{fullDateTime(c.created_at)}</span>
                  </div>
                  <ProgressBar c={c} />
                </button>
              ))
            )}
          </Card>
        </div>

        <Card className="min-w-0">
          {!selected ? (
            <Empty icon={<Megaphone className="h-10 w-10" />} title="בחרו קמפיין" />
          ) : (
            <>
              <div className="space-y-3 border-b border-ink-300 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h2 className="font-display text-lg leading-tight text-ink-900">{selected.title}</h2>
                    <p className="text-xs text-ink-500">
                      תקופה <Ltr>{selected.tax_period}</Ltr> · {selected.total_clients} לקוחות · מתעדכן בזמן אמת כשלקוחות לוחצים על הכפתורים
                    </p>
                  </div>
                  <span className="font-display text-2xl leading-none text-ink-900">
                    {Math.round((selected.stats.confirmed_paid / Math.max(1, selected.stats.total)) * 100)}% שילמו
                  </span>
                </div>
                <ProgressBar c={selected} />
              </div>
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr className="data-head">
                      <th className="px-4 py-2.5 text-start">פנייה</th>
                      <th className="px-3 py-2.5 text-start">לקוח</th>
                      <th className="px-3 py-2.5 text-end">מע״מ</th>
                      <th className="px-3 py-2.5 text-end">מקדמת מס</th>
                      <th className="px-3 py-2.5 text-end">ביטוח לאומי</th>
                      <th className="px-3 py-2.5 text-end">סה״כ לתשלום</th>
                      <th className="px-3 py-2.5 text-start">מועד</th>
                      <th className="px-3 py-2.5 text-start">תגובת הלקוח</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-ink-200">
                    {selected.recipients.map((r) => (
                      <tr key={r.id} className="cursor-pointer hover:bg-ink-50" onClick={() => selectClient(r.client_id, true)} title="פתיחת הוואטסאפ של הלקוח">
                        <td className="whitespace-nowrap px-4 py-2.5 text-ink-600">
                          <Ltr>{r.ticket_ref}</Ltr>
                        </td>
                        <td dir="auto" className="max-w-[200px] truncate px-3 py-2.5 font-bold text-ink-900">
                          {r.client_name}
                        </td>
                        <td className="px-3 py-2.5 text-end tabular-nums">{ils(r.vat_amount)}</td>
                        <td className="px-3 py-2.5 text-end tabular-nums">{ils(r.income_tax_advance)}</td>
                        <td className="px-3 py-2.5 text-end tabular-nums">{ils(r.national_insurance)}</td>
                        <td className="px-3 py-2.5 text-end font-semibold tabular-nums">{ils(r.total_due)}</td>
                        <td className="px-3 py-2.5 text-ink-600">
                          <Ltr>{r.due_date}</Ltr>
                        </td>
                        <td className="px-3 py-2.5">
                          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                            <span className="inline-flex items-center gap-1.5 whitespace-nowrap font-semibold">
                              {r.payment_status === "QUESTION_ASKED" ? <PhoneCall className="h-3 w-3" /> : <span className={cx("h-2.5 w-2.5 shrink-0", PAY_META[r.payment_status].mark)} />}
                              {PAY_META[r.payment_status].label}
                            </span>
                            {r.ticket_status && r.ticket_status !== "RESOLVED" && r.ticket_status !== "WAITING_FOR_CLIENT" && <StatusBadge status={r.ticket_status} short />}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
    </>
  );
}
