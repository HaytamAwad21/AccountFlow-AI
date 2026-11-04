import { useCallback, useEffect, useState } from "react";
import { History, RefreshCw, Search } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api } from "../lib/api";
import { cx, fullDateTime, isoDate, isoToDmy, ROLE_LABEL, splitUserName } from "../lib/format";
import { parseDdMmYyyy } from "../lib/date";
import type { ActivityEntry } from "../lib/types";
import { DateInput } from "../components/DateInput";
import { PageHeader } from "../components/PageHeader";
import { Button, Card, Empty, inputClass, Ltr, Spinner } from "../components/ui";

const PAGE = 100;

/** Only the events a manager should stop at get colour; the rest read as plain text. */
const ACTION_ALERT = new Set(["TICKET_REJECTED", "CLIENT_DEACTIVATED"]);

/** dd/mm/yyyy field over an ISO state value; a half-typed date is kept as text and not sent to the server. */
function DayField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <span className="block w-40">
      <DateInput
        value={isoToDmy(value) ?? value}
        onChange={(text) => {
          const date = parseDdMmYyyy(text);
          onChange(date ? isoDate(date) : text);
        }}
      />
    </span>
  );
}

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
    () => ({ user_id: userId || undefined, action: action || undefined, date_from: isoToDmy(dateFrom) ? dateFrom : undefined, date_to: isoToDmy(dateTo) ? dateTo : undefined, q: q || undefined }),
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
    <>
      <PageHeader
        title="יומן פעילות"
        hint="כל פעולה של צוות המשרד: התחברויות, שליחת בקשות, אישורים, שינויי לקוחות והגדרות. גלוי למנהל/ת המשרד בלבד."
        actions={
          <Button variant="fieldGhost" icon={<RefreshCw className="h-4 w-4" />} onClick={() => load()}>
            רענון
          </Button>
        }
      />
    <div className="mx-auto max-w-7xl space-y-5 p-4 @3xl:p-6">
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
          <label className="flex items-center gap-1.5 text-xs text-ink-500">
            מתאריך
            <DayField value={dateFrom} onChange={setDateFrom} />
          </label>
          <label className="flex items-center gap-1.5 text-xs text-ink-500">
            עד
            <DayField value={dateTo} onChange={setDateTo} />
          </label>
          <div className="relative">
            <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="חיפוש בתיאור…" className={cx(inputClass, "ps-9")} dir="auto" />
          </div>
        </div>
      </Card>

      <Card>
        <div className="flex items-center justify-between border-b border-ink-300 p-3 text-sm">
          <span className="font-display text-lg text-ink-900">{total.toLocaleString("he-IL")} רשומות</span>
          {loading && <Spinner />}
        </div>
        {!loading && items.length === 0 ? (
          <Empty icon={<History className="h-10 w-10" />} title="אין פעילות שתואמת לסינון" />
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr className="data-head">
                  <th className="px-4 py-2.5 text-start">זמן</th>
                  <th className="px-3 py-2.5 text-start">עובד/ת</th>
                  <th className="px-3 py-2.5 text-start">פעולה</th>
                  <th className="px-3 py-2.5 text-start">תיאור</th>
                  <th className="px-3 py-2.5 text-start">מכשיר וכתובת IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-200">
                {items.map((e) => (
                  <tr key={e.id} className="align-top hover:bg-ink-50">
                    <td className="whitespace-nowrap px-4 py-2.5 text-ink-600">{fullDateTime(e.created_at)}</td>
                    <td className="whitespace-nowrap px-3 py-2.5">
                      {e.user_name ? (
                        <span className="font-semibold text-ink-900" title={e.user_role ? ROLE_LABEL[e.user_role] : undefined}>
                          {splitUserName(e.user_name).name}
                        </span>
                      ) : (
                        <span className="text-ink-500">מערכת</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5">
                      <span className={cx("font-semibold", ACTION_ALERT.has(e.action) ? "text-red-700" : "text-ink-900")}>{e.action_label}</span>
                    </td>
                    <td className="px-3 py-2.5 text-ink-700" dir="auto">
                      {e.description}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5">
                      {e.device && <span className="block text-ink-700">{e.device}</span>}
                      <Ltr className="tabular-nums text-ink-400">{e.ip_address || "—"}</Ltr>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {items.length < total && (
          <div className="flex justify-center border-t border-ink-300 p-3">
            <Button variant="secondary" loading={loadingMore} onClick={more}>
              טעינת עוד ({(total - items.length).toLocaleString("he-IL")})
            </Button>
          </div>
        )}
      </Card>
    </div>
    </>
  );
}
