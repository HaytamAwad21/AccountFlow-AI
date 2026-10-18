import { useCallback, useEffect, useRef, useState } from "react";
import { Download, FileSpreadsheet, Megaphone, PhoneCall, Sparkles, UploadCloud } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api, downloadFile } from "../lib/api";
import { cx, fullDateTime, ils } from "../lib/format";
import type { Campaign, CampaignDetail, PaymentStatus } from "../lib/types";
import { Button, Card, Empty, inputClass, Ltr, SectionTitle, StatusBadge } from "../components/ui";

const PAY_META: Record<PaymentStatus, { label: string; className: string }> = {
  SENT: { label: "נשלח", className: "bg-slate-100 text-slate-700" },
  VIEWED: { label: "צפה בקישור התשלום", className: "bg-sky-100 text-sky-800" },
  CONFIRMED_PAID: { label: "✅ אישר תשלום", className: "bg-emerald-100 text-emerald-800" },
  QUESTION_ASKED: { label: "📞 ביקש שיחה", className: "bg-amber-100 text-amber-800" },
};

function ProgressBar({ c }: { c: Campaign }) {
  const s = c.stats;
  const total = Math.max(1, s.total);
  const seg = (n: number) => `${(n / total) * 100}%`;
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-full bg-slate-200">
        <div className="bg-emerald-500 transition-all" style={{ width: seg(s.confirmed_paid) }} title="אישרו תשלום" />
        <div className="bg-amber-400 transition-all" style={{ width: seg(s.requested_call) }} title="ביקשו שיחה" />
        <div className="bg-sky-400 transition-all" style={{ width: seg(s.viewed) }} title="צפו בקישור" />
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
        <span className="text-slate-600">
          <b className="text-slate-900">{s.sent}</b> נשלחו
        </span>
        <span className="text-slate-600">
          <b className="text-slate-900">{s.pending}</b> ממתינים
        </span>
        <span className="text-emerald-700">
          <span className="me-1 inline-block h-2 w-2 rounded-full bg-emerald-500" />
          <b>{s.confirmed_paid}</b> אישרו תשלום
        </span>
        <span className="text-amber-700">
          <span className="me-1 inline-block h-2 w-2 rounded-full bg-amber-400" />
          <b>{s.requested_call}</b> ביקשו שיחה
        </span>
        <span className="text-sky-700">
          <span className="me-1 inline-block h-2 w-2 rounded-full bg-sky-400" />
          <b>{s.viewed}</b> צפו בקישור
        </span>
        <span className="ms-auto text-slate-500">
          אושרו {ils(s.confirmed_amount)} מתוך {ils(s.total_due)}
        </span>
      </div>
    </div>
  );
}

export function BulkTax() {
  const { tick, toast, selectClient } = useApp();
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
        title: `📊 נשלחו ${r.sent} הודעות דיווח אישיות`,
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
      toast({ tone: "success", title: `📊 קבוצת ההדגמה נשלחה ל-${r.sent} לקוחות`, body: "לחצו ✅ שולם או 📞 שיחה בסימולטור וצפו בסרגל מתעדכן." });
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
    <div className="mx-auto max-w-7xl space-y-5 p-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">📊 הודעות ”הדיווח מוכן“ בתפוצה</h1>
        <p className="text-sm text-slate-500">גוררים את הגיליון החודשי מתוכנת הנהלת החשבונות — כל לקוח מקבל בוואטסאפ את הסכומים שלו, עם כפתורי ”שולם“ ו”שיחה“.</p>
      </header>

      <div className="grid gap-5 lg:grid-cols-[420px_minmax(0,1fr)]">
        <div className="space-y-5">
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
                "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-10 text-center transition",
                dragging ? "border-brand-500 bg-brand-50" : "border-slate-300 hover:border-brand-500 hover:bg-slate-50",
              )}
            >
              <UploadCloud className={cx("h-10 w-10", dragging ? "text-brand-600" : "text-slate-400")} />
              <p className="text-sm font-medium text-slate-800">{busy === "upload" ? "שולח…" : "גררו לכאן קובץ CSV / XLSX"}</p>
              <p className="text-xs text-slate-500">או לחצו לבחירה · לקוחות מזוהים לפי ח.פ או טלפון, לקוחות חדשים נוצרים אוטומטית</p>
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
            <Button variant="primary" className="mt-3 w-full" icon={<Sparkles className="h-4 w-4" />} loading={busy === "demo"} onClick={demo}>
              טעינת קבוצת הדגמה מיידית (8 לקוחות)
            </Button>
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

          <Card className="p-2">
            <p className="px-2 pb-1 pt-1 text-xs font-semibold text-slate-500">קמפיינים</p>
            {campaigns.length === 0 ? (
              <Empty icon={<Megaphone className="h-8 w-8" />} title="עדיין לא נשלחו תפוצות" hint="העלו גיליון או טענו את קבוצת ההדגמה." />
            ) : (
              campaigns.map((c) => (
                <button
                  key={c.id}
                  onClick={() => {
                    setSelectedId(c.id);
                    api.campaign(c.id).then(setSelected);
                  }}
                  className={cx("block w-full rounded-lg p-3 text-start transition", selectedId === c.id ? "bg-brand-50 ring-1 ring-brand-500" : "hover:bg-slate-50")}
                >
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <p className="truncate text-sm font-semibold text-slate-900">{c.title}</p>
                    <span className="shrink-0 text-[11px] text-slate-500">{fullDateTime(c.created_at)}</span>
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
              <div className="space-y-3 border-b border-slate-200 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h2 className="text-lg font-semibold text-slate-900">{selected.title}</h2>
                    <p className="text-xs text-slate-500">
                      תקופה <Ltr>{selected.tax_period}</Ltr> · {selected.total_clients} לקוחות · מתעדכן בזמן אמת כשלקוחות לוחצים על הכפתורים
                    </p>
                  </div>
                  <span className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-semibold text-white">
                    {Math.round((selected.stats.confirmed_paid / Math.max(1, selected.stats.total)) * 100)}% שילמו
                  </span>
                </div>
                <ProgressBar c={selected} />
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold text-slate-500">
                      <th className="px-4 py-2.5 text-start">לקוח</th>
                      <th className="px-3 py-2.5 text-end">מע״מ</th>
                      <th className="px-3 py-2.5 text-end">מקדמת מס</th>
                      <th className="px-3 py-2.5 text-end">ביטוח לאומי</th>
                      <th className="px-3 py-2.5 text-end">סה״כ לתשלום</th>
                      <th className="px-3 py-2.5 text-start">מועד</th>
                      <th className="px-3 py-2.5 text-start">תגובת הלקוח</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {selected.recipients.map((r) => (
                      <tr key={r.id} className="cursor-pointer hover:bg-slate-50" onClick={() => selectClient(r.client_id, true)} title="פתיחת הוואטסאפ של הלקוח">
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-2">
                            <span dir="auto" className="truncate font-medium text-slate-900">
                              {r.client_name}
                            </span>
                          </div>
                          <p className="mt-0.5 font-mono text-[11px] text-slate-400">
                            <Ltr>{r.ticket_ref}</Ltr>
                          </p>
                        </td>
                        <td className="px-3 py-2.5 text-end tabular-nums">{ils(r.vat_amount)}</td>
                        <td className="px-3 py-2.5 text-end tabular-nums">{ils(r.income_tax_advance)}</td>
                        <td className="px-3 py-2.5 text-end tabular-nums">{ils(r.national_insurance)}</td>
                        <td className="px-3 py-2.5 text-end font-semibold tabular-nums">{ils(r.total_due)}</td>
                        <td className="px-3 py-2.5 text-xs text-slate-600">
                          <Ltr>{r.due_date}</Ltr>
                        </td>
                        <td className="px-3 py-2.5">
                          <div className="flex flex-col items-start gap-1">
                            <span className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", PAY_META[r.payment_status].className)}>
                              {r.payment_status === "QUESTION_ASKED" && <PhoneCall className="h-3 w-3" />}
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
  );
}
