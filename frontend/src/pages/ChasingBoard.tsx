import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { BellRing, Clock3, FastForward, Hourglass, Inbox, RefreshCw, Search, ShieldCheck, Sparkles, Timer } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api } from "../lib/api";
import { cx, relativeTime } from "../lib/format";
import type { Kpis, SchedulerAction, Ticket, TicketStatus } from "../lib/types";
import { TicketModal } from "../components/TicketModal";
import { Button, Card, Empty, inputClass, Ltr, PriorityLabel, Spinner, StatusBadge, Toggle } from "../components/ui";

const FILTERS: { key: string; label: string; statuses: TicketStatus[] | null }[] = [
  { key: "all", label: "הכל", statuses: null },
  { key: "waiting", label: "⏳ ממתין ללקוח", statuses: ["WAITING_FOR_CLIENT", "SNOOZED_TONIGHT", "OPEN"] },
  { key: "correction", label: "⚠️ דרוש תיקון (מטושטש / שגוי)", statuses: ["NEEDS_CORRECTION"] },
  { key: "review", label: "🔍 מוכן לבדיקת פקיד", statuses: ["NEEDS_CLERK_REVIEW"] },
  { key: "escalated", label: "🚨 הוסלם", statuses: ["ESCALATED"] },
  { key: "resolved", label: "✅ טופל", statuses: ["RESOLVED"] },
];

const ACTION_COPY: Record<SchedulerAction["kind"], { title: string; tone: "info" | "warning" | "error" | "success" }> = {
  FRIENDLY_REMINDER: { title: "🔔 נשלחה תזכורת ידידותית", tone: "info" },
  URGENT_DEADLINE_WARNING: { title: "⚠️ נשלחה התראת מועד דיווח", tone: "warning" },
  URGENT_GROUPED: { title: "⚠️ סומן דחוף (כלול בהתראת המועד)", tone: "warning" },
  ESCALATED: { title: "🚨 הוסלם — יש להתקשר ללקוח", tone: "error" },
  SNOOZE_PING: { title: "🌙 נשלחה תזכורת של 20:00", tone: "success" },
};

function Kpi({ icon, label, value, accent, hint }: { icon: ReactNode; label: string; value: string | number; accent: string; hint?: string }) {
  return (
    <Card className="flex items-center gap-3 p-4">
      <span className={cx("grid h-10 w-10 shrink-0 place-items-center rounded-lg", accent)}>{icon}</span>
      <div className="min-w-0">
        <p className="text-2xl font-bold leading-none text-slate-900">{value}</p>
        <p className="mt-1 text-xs leading-tight text-slate-500" title={hint ?? label}>
          {label}
        </p>
      </div>
    </Card>
  );
}

export function ChasingBoard() {
  const { tick, toast, settings, refreshSettings, selectClient, isManager } = useApp();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [jumping, setJumping] = useState(false);
  const [checking, setChecking] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const interval = settings?.reminder_interval_hours ?? 48;

  const load = useCallback(async () => {
    const [t, k] = await Promise.all([api.tickets(), api.kpis()]);
    setTickets(t);
    setKpis(k);
  }, []);

  useEffect(() => {
    load()
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, [load, tick]);

  const counts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const f of FILTERS) out[f.key] = f.statuses ? tickets.filter((t) => f.statuses!.includes(t.status)).length : tickets.length;
    return out;
  }, [tickets]);

  const visible = useMemo(() => {
    const f = FILTERS.find((x) => x.key === filter);
    const needle = q.trim().toLowerCase();
    return tickets.filter(
      (t) =>
        (!f?.statuses || f.statuses.includes(t.status)) &&
        (!needle ||
          t.ticket_ref.toLowerCase().includes(needle) ||
          t.client_name.toLowerCase().includes(needle) ||
          t.company_name.toLowerCase().includes(needle) ||
          String(t.context_variables_json.supplier_name ?? "").toLowerCase().includes(needle)),
    );
  }, [tickets, filter, q]);

  const announce = (actions: SchedulerAction[], heading: string) => {
    if (!actions.length) {
      toast({ tone: "info", title: heading, body: "לא היו תזכורות שהגיע מועדן." });
      return;
    }
    const summary = actions.reduce<Record<string, number>>((acc, a) => ({ ...acc, [a.kind]: (acc[a.kind] ?? 0) + 1 }), {});
    toast(
      {
        tone: "success",
        title: `${heading}: ${actions.length} פעולות אוטומטיות`,
        body: Object.entries(summary)
          .map(([k, n]) => `${n} × ${ACTION_COPY[k as SchedulerAction["kind"]].title.replace(/^\S+\s/, "")}`)
          .join(" · "),
      },
      7000,
    );
    actions.slice(0, 5).forEach((a, i) =>
      window.setTimeout(
        () =>
          toast(
            {
              tone: ACTION_COPY[a.kind].tone,
              title: `${ACTION_COPY[a.kind].title} · ${a.ticket_ref}`,
              body: `${a.client_name}: ${a.message}`,
              dir: "auto" as const,
            },
            6500,
          ),
        250 * (i + 1),
      ),
    );
  };

  const timeJump = async () => {
    setJumping(true);
    try {
      const r = await api.timeJump(interval);
      announce(r.actions, `⏩ הודמה קפיצה של +${interval} שעות`);
      await load();
    } catch (e) {
      toast({ tone: "error", title: "הדמיית הזמן נכשלה", body: e instanceof Error ? e.message : String(e) });
    } finally {
      setJumping(false);
    }
  };

  const runCheck = async () => {
    setChecking(true);
    try {
      const r = await api.triggerCheck();
      announce(r.actions, "מחזור תזכורות (שעון אמיתי)");
      await load();
    } finally {
      setChecking(false);
    }
  };

  const toggleAuto = async (v: boolean) => {
    try {
      await api.updateSettings({ auto_approve_verified: v });
      await refreshSettings();
      toast({ tone: "info", title: v ? "אישור אוטומטי הופעל" : "אישור אוטומטי כובה", body: v ? "חשבוניות מאומתות ייסגרו אוטומטית." : "חשבוניות מאומתות ימתינו לבדיקת פקיד." });
    } catch (e) {
      toast({ tone: "error", title: "לא ניתן לשנות", body: e instanceof Error ? e.message : String(e) });
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">📋 לוח מעקב חי</h1>
          <p className="text-sm text-slate-500">כל בקשה פתוחה, מצבה בוואטסאפ ומה הבוט יעשה בהמשך.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {settings && isManager && (
            <Toggle checked={settings.auto_approve_verified} onChange={toggleAuto} label="אישור אוטומטי לחשבוניות מאומתות" />
          )}
          <Button variant="ghost" icon={<RefreshCw className="h-4 w-4" />} loading={checking} onClick={runCheck} title="הרצת מחזור התזכורות לפי השעון האמיתי">
            בדיקה עכשיו
          </Button>
          <Button variant="primary" size="lg" icon={<FastForward className="h-5 w-5 -scale-x-100" />} loading={jumping} onClick={timeJump}>
            ⏩ הדמיית +{interval} שעות (הפעלת לולאת התזכורות)
          </Button>
        </div>
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <Kpi icon={<Hourglass className="h-5 w-5" />} accent="bg-sky-50 text-sky-600" label="פניות פעילות הממתינות ללקוח" value={kpis?.active_waiting ?? "—"} />
        <Kpi icon={<BellRing className="h-5 w-5" />} accent="bg-violet-50 text-violet-600" label="תזכורות אוטומטיות החודש" value={kpis?.auto_reminders_this_month ?? "—"} />
        <Kpi icon={<ShieldCheck className="h-5 w-5" />} accent="bg-indigo-50 text-indigo-600" label="ממתינות לבדיקת פקיד (אומתו ב-OCR)" value={kpis?.needs_clerk_review ?? "—"} />
        <Kpi icon={<Sparkles className="h-5 w-5" />} accent="bg-emerald-50 text-emerald-600" label="טופלו השבוע" value={kpis?.resolved_this_week ?? "—"} />
        <Kpi
          icon={<Timer className="h-5 w-5" />}
          accent="bg-amber-50 text-amber-600"
          label="הערכת שעות עבודה שנחסכו"
          value={kpis ? `${kpis.estimated_hours_saved} ש׳` : "—"}
          hint={kpis?.hours_saved_basis}
        />
      </div>

      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 p-3">
          <div className="flex flex-wrap gap-1">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                className={cx(
                  "rounded-lg px-2.5 py-1.5 text-xs font-medium transition",
                  filter === f.key ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100",
                  f.key === "escalated" && counts.escalated > 0 && filter !== f.key && "text-red-600",
                )}
              >
                {f.label} <span className={cx("ms-1 rounded px-1 text-[10px]", filter === f.key ? "bg-white/20" : "bg-slate-100")}>{counts[f.key]}</span>
              </button>
            ))}
          </div>
          <div className="relative ms-auto w-full sm:w-64">
            <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="פנייה, לקוח, ספק…" className={cx(inputClass, "py-1.5 ps-9")} dir="auto" />
          </div>
        </div>

        {loading ? (
          <div className="flex justify-center p-10">
            <Spinner className="h-6 w-6" />
          </div>
        ) : visible.length === 0 ? (
          <Empty icon={<Inbox className="h-10 w-10" />} title="אין כאן פניות" hint="שלחו בקשה מעמדת ”שליחת בקשה“ או שנו את הסינון." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-start text-[11px] font-semibold text-slate-500">
                  <th className="px-4 py-2.5 text-start">פנייה</th>
                  <th className="px-3 py-2.5 text-start">לקוח</th>
                  <th className="px-3 py-2.5 text-start">בקשה</th>
                  <th className="px-3 py-2.5 text-start">סטטוס</th>
                  <th className="px-3 py-2.5 text-start">תזכורות</th>
                  <th className="px-3 py-2.5 text-start">תזכורת הבאה</th>
                  <th className="px-3 py-2.5 text-start">קשר אחרון</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {visible.map((t) => (
                  <tr
                    key={t.id}
                    onClick={() => {
                      setOpenId(t.id);
                      selectClient(t.client_id);
                    }}
                    className={cx(
                      "cursor-pointer transition hover:bg-slate-50",
                      t.status === "ESCALATED" && "bg-red-50/70 hover:bg-red-50",
                      t.priority === "URGENT_DEADLINE" && t.status !== "ESCALATED" && t.status !== "RESOLVED" && "bg-amber-50/40",
                    )}
                  >
                    <td className="whitespace-nowrap px-4 py-2.5">
                      <p className="font-mono text-xs font-semibold text-slate-900">
                        <Ltr>{t.ticket_ref}</Ltr>
                      </p>
                      <PriorityLabel priority={t.priority} />
                    </td>
                    <td className="max-w-[220px] px-3 py-2.5">
                      <div className="flex items-center gap-2">
                        <div className="min-w-0">
                          <p dir="auto" className="truncate font-medium text-slate-900">
                            {t.client_name}
                          </p>
                          <p dir="auto" className="truncate text-xs text-slate-500">
                            {t.company_name}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="max-w-[240px] px-3 py-2.5">
                      <p className="truncate text-slate-800">{t.template_name}</p>
                      <p dir="auto" className="truncate text-xs text-slate-500">
                        {[
                          t.context_variables_json.supplier_name,
                          t.context_variables_json.invoice_number && `#${t.context_variables_json.invoice_number}`,
                          t.context_variables_json.missing_detail,
                          t.context_variables_json.amount ?? t.context_variables_json.charge_amount ?? t.context_variables_json.vat_amount,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </p>
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusBadge status={t.status} />
                      {t.status === "NEEDS_CORRECTION" && (t.ocr_validation_json?.rejection_reason_he || t.context_variables_json.last_invalid_value) && (
                        <p
                          className="mt-1 max-w-[220px] truncate text-[11px] text-amber-700"
                          title={t.ocr_validation_json?.rejection_reason_he ?? undefined}
                        >
                          {t.context_variables_json.last_invalid_value && t.context_variables_json.awaiting_text
                            ? `ערך לא תקין: ${t.context_variables_json.last_invalid_value} (נדרשות 9 ספרות)`
                            : t.ocr_validation_json?.rejection_reason_he}
                        </p>
                      )}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-1">
                        {Array.from({ length: t.max_reminders }).map((_, i) => (
                          <span key={i} className={cx("h-1.5 w-4 rounded-full", i < t.reminder_count ? "bg-violet-500" : "bg-slate-200")} />
                        ))}
                        <span className="ms-1 text-xs text-slate-500">
                          {t.reminder_count}/{t.max_reminders}
                        </span>
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-xs text-slate-600">
                      {t.next_reminder_at ? (
                        <span className="inline-flex items-center gap-1">
                          <Clock3 className="h-3.5 w-3.5 text-slate-400" /> {relativeTime(t.next_reminder_at)}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-xs text-slate-500">{relativeTime(t.last_contacted_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <TicketModal ticketId={openId} onClose={() => setOpenId(null)} />
    </div>
  );
}
