import { useCallback, useEffect, useState } from "react";
import { History, RefreshCw, Search } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api } from "../lib/api";
import { cx, fullDateTime, splitUserName } from "../lib/format";
import type { ActivityEntry } from "../lib/types";
import { Button, Card, Empty, inputClass, Ltr, RoleBadge, Spinner } from "../components/ui";

const PAGE = 100;

const ACTION_TONE: Record<string, string> = {
  LOGIN: "bg-emerald-50 text-emerald-800",
  LOGOUT: "bg-slate-100 text-slate-700",
  TICKET_SENT: "bg-sky-50 text-sky-800",
  MANUAL_MESSAGE_SENT: "bg-emerald-50 text-emerald-800",
  REMINDERS_SENT: "bg-sky-50 text-sky-800",
  CAMPAIGN_SENT: "bg-sky-50 text-sky-800",
  TICKET_APPROVED: "bg-emerald-50 text-emerald-800",
  TICKET_REJECTED: "bg-red-50 text-red-700",
  PASSWORD_RESET: "bg-amber-100 text-amber-800",
  PASSWORD_CHANGED: "bg-amber-100 text-amber-800",
  SETTINGS_UPDATED: "bg-violet-100 text-violet-800",
  USER_CREATED: "bg-violet-100 text-violet-800",
  USER_UPDATED: "bg-violet-100 text-violet-800",
  CLIENT_DEACTIVATED: "bg-red-50 text-red-700",
};

/** Manager-only audit trail of operational events: sessions, requests and reminders sent,
 *  broadcasts, invoice decisions and management changes. Failed logins are never shown. */
export function ActivityLog() {
  const { isManager, users, tick, tickTypes } = useApp();
  const [items, setItems] = useState<ActivityEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [userId, setUserId] = useState<number | "">("");
  const [action, setAction] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  const filters = useCallback(
    () => ({ user_id: userId || undefined, action: action || undefined, date_from: dateFrom || undefined, date_to: dateTo || undefined, q: q || undefined }),
    [userId, action, dateFrom, dateTo, q],
  );

  const load = useCallback(async () => {
    const page = await api.activity({ ...filters(), limit: PAGE, offset: 0 });
    setItems(page.items);
    setTotal(page.total);
    setLabels(page.actions);
  }, [filters]);

  useEffect(() => {
    if (!isManager) return;
    setLoading(true);
    const t = window.setTimeout(() => {
      load()
        .catch(() => undefined)
        .finally(() => setLoading(false));
    }, 200);
    return () => window.clearTimeout(t);
  }, [isManager, load]);

  // live: new audit rows arrive as "activity" events
  useEffect(() => {
    if (isManager && tickTypes.includes("activity")) load().catch(() => undefined);
  }, [tick]); // eslint-disable-line react-hooks/exhaustive-deps

  const more = async () => {
    setLoadingMore(true);
    try {
      const page = await api.activity({ ...filters(), limit: PAGE, offset: items.length });
      setItems((prev) => [...prev, ...page.items]);
      setTotal(page.total);
    } finally {
      setLoadingMore(false);
    }
  };

  // Manager-only page: nothing is rendered for workers (the sidebar also hides the tab).
  if (!isManager) return null;

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-4 @3xl:p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-slate-900">
            <History className="h-6 w-6" /> יומן פעילות
          </h1>
          <p className="text-sm text-slate-500">כל פעולה של צוות המשרד: התחברויות, שליחת בקשות, אישורים, שינויי לקוחות והגדרות. גלוי למנהל/ת המשרד בלבד.</p>
        </div>
        <Button variant="ghost" icon={<RefreshCw className="h-4 w-4" />} onClick={() => load()}>
          רענון
        </Button>
      </header>

      <Card className="p-3">
        <div className="grid gap-2 @3xl:grid-cols-[1fr_1fr_auto_auto_1.3fr]">
          <select value={userId} onChange={(e) => setUserId(e.target.value ? Number(e.target.value) : "")} className={inputClass}>
            <option value="">כל העובדים</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {splitUserName(u.full_name).name}
              </option>
            ))}
          </select>
          <select value={action} onChange={(e) => setAction(e.target.value)} className={inputClass}>
            <option value="">כל הפעולות</option>
            {Object.entries(labels).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-1.5 text-xs text-slate-500">
            מתאריך
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className={cx(inputClass, "w-auto")} />
          </label>
          <label className="flex items-center gap-1.5 text-xs text-slate-500">
            עד
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className={cx(inputClass, "w-auto")} />
          </label>
          <div className="relative">
            <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="חיפוש בתיאור…" className={cx(inputClass, "ps-9")} dir="auto" />
          </div>
        </div>
      </Card>

      <Card>
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 text-sm">
          <span className="font-semibold text-slate-900">{total.toLocaleString("he-IL")} רשומות</span>
          {loading && <Spinner />}
        </div>
        {!loading && items.length === 0 ? (
          <Empty icon={<History className="h-10 w-10" />} title="אין פעילות שתואמת לסינון" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold text-slate-500">
                  <th className="px-4 py-2.5 text-start">זמן</th>
                  <th className="px-3 py-2.5 text-start">עובד/ת</th>
                  <th className="px-3 py-2.5 text-start">פעולה</th>
                  <th className="px-3 py-2.5 text-start">תיאור</th>
                  <th className="px-3 py-2.5 text-start">כתובת IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((e) => (
                  <tr key={e.id} className="align-top hover:bg-slate-50">
                    <td className="whitespace-nowrap px-4 py-2.5 text-xs text-slate-600">{fullDateTime(e.created_at)}</td>
                    <td className="whitespace-nowrap px-3 py-2.5">
                      {e.user_name ? (
                        <div className="flex flex-col items-start gap-0.5">
                          <span className="font-medium text-slate-900">{splitUserName(e.user_name).name}</span>
                          {e.user_role && <RoleBadge role={e.user_role} />}
                        </div>
                      ) : (
                        <span className="text-xs text-slate-400">מערכת</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5">
                      <span className={cx("rounded-full px-2 py-0.5 text-xs font-medium", ACTION_TONE[e.action] ?? "bg-sky-50 text-sky-800")}>{e.action_label}</span>
                    </td>
                    <td className="px-3 py-2.5 text-slate-700" dir="auto">
                      {e.description}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 font-mono text-[11px] text-slate-400">
                      <Ltr>{e.ip_address || "—"}</Ltr>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {items.length < total && (
          <div className="flex justify-center border-t border-slate-100 p-3">
            <Button variant="secondary" loading={loadingMore} onClick={more}>
              טעינת עוד ({(total - items.length).toLocaleString("he-IL")})
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
