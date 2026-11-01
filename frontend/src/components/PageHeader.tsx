import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useApp } from "../context/AppContext";
import { api } from "../lib/api";
import { cx, VAT_DEADLINE_DAY } from "../lib/format";
import type { Ticket } from "../lib/types";

/** The 26th: one form at every scale (logo, month band, login screen). */
export function DeadlineDisc({ className }: { className?: string }) {
  return (
    <span aria-hidden className={cx("grid shrink-0 place-items-center rounded-full bg-accent font-display leading-none text-accent-ink", className)}>
      {VAT_DEADLINE_DAY}
    </span>
  );
}

/** The next VAT deadline, the whole days until it, and its month's length. */
function nextDeadline(now: Date) {
  const target = new Date(now.getFullYear(), now.getMonth() + (now.getDate() <= VAT_DEADLINE_DAY ? 0 : 1), VAT_DEADLINE_DAY);
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return {
    target,
    daysLeft: Math.round((target.getTime() - today.getTime()) / 86400000),
    daysInMonth: new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate(),
    month: target.toLocaleDateString("he-IL", { month: "long" }),
    today: now.getMonth() === target.getMonth() ? now.getDate() : 0,
  };
}

/** The countdown as [figure, the words after it]. */
function countdownParts(daysLeft: number, month: string): [string, string, string] {
  if (daysLeft === 0) return ["היום", `ה־${VAT_DEADLINE_DAY}`, `ב${month}`];
  if (daysLeft === 1) return ["1", `יום ל־${VAT_DEADLINE_DAY}`, `ב${month}`];
  return [String(daysLeft), `ימים ל־${VAT_DEADLINE_DAY}`, `ב${month}`];
}

// Every page has its own header, so the last result is kept to avoid a flash of empty bars when switching tabs.
let lastTickets: Ticket[] = [];

/** Days of the deadline's month: requests opened so far (solid), reminders still scheduled (outlined), and the 26th. */
function MonthStrip({ deadline }: { deadline: ReturnType<typeof nextDeadline> }) {
  const { tick } = useApp();
  const [tickets, setTickets] = useState<Ticket[]>(lastTickets);

  useEffect(() => {
    api
      .tickets()
      .then((rows) => {
        lastTickets = rows;
        setTickets(rows);
      })
      .catch(() => undefined);
  }, [tick]);

  const { opened, scheduled, peak } = useMemo(() => {
    const opened: Record<number, number> = {};
    const scheduled: Record<number, number> = {};
    const inMonth = (d: Date) => d.getFullYear() === deadline.target.getFullYear() && d.getMonth() === deadline.target.getMonth();
    for (const t of tickets) {
      const created = new Date(t.created_at);
      if (inMonth(created)) opened[created.getDate()] = (opened[created.getDate()] ?? 0) + 1;
      if (t.next_reminder_at) {
        const next = new Date(t.next_reminder_at);
        if (inMonth(next)) scheduled[next.getDate()] = (scheduled[next.getDate()] ?? 0) + 1;
      }
    }
    return { opened, scheduled, peak: Math.max(1, ...Object.values(opened), ...Object.values(scheduled)) };
  }, [tickets, deadline.target]);

  const height = (n: number) => 4 + Math.round((n / peak) * 24);

  return (
    <div
      className="grid h-14 w-full"
      style={{ gridTemplateColumns: `repeat(${deadline.daysInMonth}, minmax(0, 1fr))` }}
      role="img"
      aria-label={countdownParts(deadline.daysLeft, deadline.month).join(" ")}
    >
      {Array.from({ length: deadline.daysInMonth }, (_, i) => {
        const day = i + 1;
        const isToday = day === deadline.today;
        const open = opened[day] ?? 0;
        const next = scheduled[day] ?? 0;
        return (
          <div
            key={day}
            className="relative flex flex-col items-center justify-end gap-0.5"
            title={`${day} ב${deadline.month} · ${open} בקשות נפתחו · ${next} תזכורות מתוכננות`}
          >
            {day === VAT_DEADLINE_DAY ? (
              <DeadlineDisc className="absolute -bottom-5 z-10 h-11 w-11 text-base" />
            ) : (
              <>
                {next > 0 && <span className="block w-1.5 border border-white/70" style={{ height: height(next) }} />}
                {open > 0 && <span className={cx("block w-1.5", isToday ? "bg-accent" : "bg-[#fff]")} style={{ height: height(open) }} />}
                {isToday && open === 0 && <span className="block h-1.5 w-1.5 rounded-full bg-accent" />}
                <span className={cx("h-4 text-xs leading-4", isToday ? "font-bold text-accent" : "text-field-muted")}>{(day === 1 || day % 5 === 0 || isToday) && day !== VAT_DEADLINE_DAY - 1 ? day : ""}</span>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

/**
 * The midnight band on top of every page: it joins the navigation rail into one field and always
 * shows how far away the 26th is. The disc hangs over the band's lower edge, so the band stays low
 * enough for Send Request to fit a 720px window. The page's explanation sits under the band, in full.
 */
export function PageHeader({ title, hint, actions }: { title: string; hint?: ReactNode; actions?: ReactNode }) {
  const deadline = nextDeadline(new Date());
  const [figure, line1, line2] = countdownParts(deadline.daysLeft, deadline.month);
  return (
    <>
      <header className="sticky top-0 z-20 grid grid-cols-[minmax(0,1fr)_auto] items-end gap-x-6 border-b border-white/10 bg-field px-4 py-3 text-white @3xl/main:grid-cols-2 @3xl/main:px-6">
        <h1 className="self-center font-display text-2xl leading-tight">{title}</h1>
        <div className="flex min-w-0 items-end gap-3 @3xl/main:row-span-2">
          <p className="flex shrink-0 items-end gap-2">
            <span className="font-display text-[2.75rem] leading-[0.95]">{figure}</span>
            <span className="text-sm font-semibold leading-tight">
              {line1}
              <br />
              {line2}
            </span>
          </p>
          <div className="hidden min-w-0 flex-1 @3xl/main:block">
            <MonthStrip deadline={deadline} />
          </div>
        </div>
        {actions && <div className="col-span-2 mt-2 flex flex-wrap items-center gap-2 @3xl/main:col-span-1">{actions}</div>}
      </header>
      {hint && <p className="mx-auto w-full max-w-7xl shrink-0 px-4 pt-3 text-sm text-ink-600 @3xl/main:px-6">{hint}</p>}
    </>
  );
}
