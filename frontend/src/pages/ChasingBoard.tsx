import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, FastForward, Inbox, RefreshCw, Search } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api } from "../lib/api";
import { cx, relativeTime } from "../lib/format";
import type { Kpis, SchedulerAction, Ticket, TicketStatus } from "../lib/types";
import { PageHeader } from "../components/PageHeader";
import { TicketModal } from "../components/TicketModal";
import { Button, Card, Empty, inputClass, Ltr, PriorityLabel, Spinner, StatusBadge, TabButton, Toggle } from "../components/ui";

const FILTERS: { key: string; label: string; statuses: TicketStatus[] | null }[] = [
  { key: "all", label: "הכל", statuses: null },
  { key: "waiting", label: "ממתין ללקוח", statuses: ["WAITING_FOR_CLIENT", "SNOOZED_TONIGHT", "OPEN"] },
  { key: "correction", label: "דרוש תיקון (מטושטש / שגוי)", statuses: ["NEEDS_CORRECTION"] },
  { key: "review", label: "מוכן לבדיקת פקיד", statuses: ["NEEDS_CLERK_REVIEW"] },
  { key: "escalated", label: "הוסלם", statuses: ["ESCALATED"] },
  { key: "resolved", label: "טופל", statuses: ["RESOLVED"] },
];

const ACTION_COPY: Record<SchedulerAction["kind"], { title: string; tone: "info" | "warning" | "error" | "success" }> = {
  FRIENDLY_REMINDER: { title: "נשלחה תזכורת ידידותית", tone: "info" },
  URGENT_DEADLINE_WARNING: { title: "נשלחה התראת מועד דיווח", tone: "warning" },
  URGENT_GROUPED: { title: "סומן דחוף (כלול בהתראת המועד)", tone: "warning" },
  ESCALATED: { title: "הוסלם — יש להתקשר ללקוח", tone: "error" },
  SNOOZE_PING: { title: "נשלחה תזכורת של 20:00", tone: "success" },
};

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <span title={hint ?? label}>
      <b className="text-ink-900">{value}</b> {label}
    </span>
  );
}

/** Supplier, numbers and amount of a request, for the details column. */
function ticketDetail(t: Ticket): string {
  const c = t.context_variables_json;
  return [c.supplier_name, c.invoice_number && `#${c.invoice_number}`, c.missing_detail, c.amount ?? c.charge_amount ?? c.vat_amount].filter(Boolean).join(" · ");
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

  const nextReview = useMemo(() => tickets.find((t) => t.status === "NEEDS_CLERK_REVIEW") ?? null, [tickets]);

  const openTicket = (t: Ticket) => {
    setOpenId(t.id);
    selectClient(t.client_id);
  };

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
      announce(r.actions, `הודמה קפיצה של +${interval} שעות`);
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
    <>
      <PageHeader
        title="לוח מעקב חי"
        hint="כל בקשה פתוחה, מצבה בוואטסאפ ומה הבוט יעשה בהמשך."
        actions={
          <>
            <Button variant="fieldGhost" size="sm" icon={<FastForward className="h-3.5 w-3.5 -scale-x-100" />} loading={jumping} onClick={timeJump}>
              הדמיית +{interval} שעות (הפעלת לולאת התזכורות)
            </Button>
            <Button variant="fieldGhost" size="sm" icon={<RefreshCw className="h-3.5 w-3.5" />} loading={checking} onClick={runCheck} title="הרצת מחזור התזכורות לפי השעון האמיתי">
              בדיקה עכשיו
            </Button>
          </>
        }
      />
    <div className="mx-auto max-w-7xl space-y-5 p-4 @3xl:p-6">
      {nextReview && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 bg-accent px-4 py-3 text-accent-ink">
          <span className="font-display text-2xl leading-none">{counts.review}</span>
          <p className="min-w-0 flex-1 font-semibold">
            {counts.review === 1 ? "פנייה אחת מחכה לבדיקה שלך" : "פניות מחכות לבדיקה שלך"}. הבאה בתור: <bdi>{nextReview.client_name}</bdi>
          </p>
          <Button variant="onAccent" icon={<ArrowLeft className="h-4 w-4" />} onClick={() => openTicket(nextReview)}>
            פתיחת הפנייה הבאה
          </Button>
        </div>
      )}

      <p className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-600">
        <Stat label="פניות פעילות הממתינות ללקוח" value={kpis?.active_waiting ?? "—"} />
        <Stat label="תזכורות אוטומטיות החודש" value={kpis?.auto_reminders_this_month ?? "—"} />
        <Stat label="ממתינות לבדיקת פקיד (אומתו ב-OCR)" value={kpis?.needs_clerk_review ?? "—"} />
        <Stat label="טופלו השבוע" value={kpis?.resolved_this_week ?? "—"} />
        <Stat label="הערכת שעות עבודה שנחסכו" value={kpis ? `${kpis.estimated_hours_saved} ש׳` : "—"} hint={kpis?.hours_saved_basis} />
      </p>

      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-ink-300 p-3">
          <div className="flex flex-wrap gap-1">
            {FILTERS.map((f) => (
              <TabButton key={f.key} active={filter === f.key} onClick={() => setFilter(f.key)} alert={f.key === "escalated" && counts.escalated > 0}>
                {f.label} <span className="ms-1 font-normal opacity-75">{counts[f.key]}</span>
              </TabButton>
            ))}
          </div>
          {settings && isManager && <Toggle checked={settings.auto_approve_verified} onChange={toggleAuto} label="אישור אוטומטי לחשבוניות מאומתות" />}
          <div className="relative ms-auto w-full @xl:w-64">
            <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
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
            <table className="data-table">
              <thead>
                <tr className="data-head">
                  <th className="px-4 py-2.5 text-start">פנייה</th>
                  <th className="px-3 py-2.5 text-start">לקוח</th>
                  <th className="px-3 py-2.5 text-start">בקשה</th>
                  <th className="px-3 py-2.5 text-start">פרטים</th>
                  <th className="px-3 py-2.5 text-start">סטטוס</th>
                  <th className="px-3 py-2.5 text-start">תזכורות</th>
                  <th className="hidden px-3 py-2.5 text-start @5xl:table-cell">תזכורת הבאה</th>
                  <th className="hidden px-3 py-2.5 text-start @5xl:table-cell">קשר אחרון</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-200">
                {visible.map((t) => (
                  <tr
                    key={t.id}
                    onClick={() => openTicket(t)}
                    className={cx(
                      "cursor-pointer transition-colors hover:bg-ink-50",
                      t.status === "ESCALATED" && "bg-red-50/70 hover:bg-red-50",
                      t.priority === "URGENT_DEADLINE" && t.status !== "ESCALATED" && t.status !== "RESOLVED" && "bg-amber-50/40",
                    )}
                  >
                    <td className="whitespace-nowrap px-4 py-2.5 font-bold text-ink-900">
                      <Ltr>{t.ticket_ref}</Ltr>
                      {t.priority !== "NORMAL" && t.status !== "RESOLVED" && (
                        <span className="ms-2">
                          <PriorityLabel priority={t.priority} />
                        </span>
                      )}
                    </td>
                    <td dir="auto" className="max-w-[200px] truncate px-3 py-2.5 font-bold text-ink-900" title={t.company_name}>
                      {t.client_name}
                    </td>
                    <td className="max-w-[170px] truncate px-3 py-2.5" title={t.template_name}>
                      {t.template_name}
                    </td>
                    <td dir="auto" className="max-w-[170px] truncate px-3 py-2.5 text-ink-600" title={ticketDetail(t)}>
                      {ticketDetail(t)}
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusBadge status={t.status} />
                      {t.status === "NEEDS_CORRECTION" && (t.ocr_validation_json?.rejection_reason_he || t.context_variables_json.last_invalid_value) && (
                        <p
                          className="mt-1 max-w-[220px] truncate text-amber-700"
                          title={t.ocr_validation_json?.rejection_reason_he ?? undefined}
                        >
                          {t.context_variables_json.last_invalid_value && t.context_variables_json.awaiting_text
                            ? `ערך לא תקין: ${t.context_variables_json.last_invalid_value} (נדרשות 9 ספרות)`
                            : t.ocr_validation_json?.rejection_reason_he}
                        </p>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5">
                      {t.reminder_count}/{t.max_reminders}
                    </td>
                    <td className="hidden whitespace-nowrap px-3 py-2.5 text-ink-600 @5xl:table-cell">{t.next_reminder_at ? relativeTime(t.next_reminder_at) : "—"}</td>
                    <td className="hidden whitespace-nowrap px-3 py-2.5 text-ink-600 @5xl:table-cell">{relativeTime(t.last_contacted_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <TicketModal ticketId={openId} onClose={() => setOpenId(null)} />
    </div>
    </>
  );
}
