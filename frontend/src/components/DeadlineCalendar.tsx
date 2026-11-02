import { useEffect, useState } from "react";
import { useApp } from "../context/AppContext";
import { cx, DEFAULT_VAT_DEADLINE_DAY, nextDeadlineDate } from "../lib/format";

const WEEKDAYS = ["א׳", "ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "ש׳"]; // Israeli week: Sunday first
const DEADLINE_LABEL = "מועד דיווח מע״מ";
const DAY_MS = 86400000;

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const daysBetween = (from: Date, to: Date) => Math.round((startOfDay(to).getTime() - startOfDay(from).getTime()) / DAY_MS);

/** The countdown as [figure, the words after it]. */
function countdownParts(daysLeft: number, day: number, month: string): [string, string, string] {
  if (daysLeft === 0) return ["היום", `ה־${day}`, `ב${month}`];
  if (daysLeft === 1) return ["1", `יום ל־${day}`, `ב${month}`];
  return [String(daysLeft), `ימים ל־${day}`, `ב${month}`];
}

function tooltip(date: Date, isDeadline: boolean): string {
  const full = date.toLocaleDateString("he-IL", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  return isDeadline ? `${full} · ${DEADLINE_LABEL}` : full;
}

/** One day: the deadline disc, the today ring, or a plain number. A past deadline keeps its colour, faded. */
function DayNumber({ day, isDeadline, isToday, isPast, isUrgent, isWeekend }: { day: number; isDeadline: boolean; isToday: boolean; isPast: boolean; isUrgent: boolean; isWeekend: boolean }) {
  return (
    <span
      className={cx(
        "relative grid h-6 w-6 place-items-center rounded-full text-xs tabular-nums",
        isDeadline && "z-10 bg-accent font-bold text-accent-ink",
        isDeadline && isPast && "opacity-60",
        isDeadline && isToday && "ring-2 ring-brand-500 ring-offset-2 ring-offset-field",
        !isDeadline && isToday && "font-bold text-white ring-2 ring-inset ring-brand-500",
        !isDeadline && !isToday && isPast && "text-field-muted/60",
        !isDeadline && !isToday && !isPast && isUrgent && "font-semibold text-[#fcd34d]",
        !isDeadline && !isToday && !isPast && !isUrgent && (isWeekend ? "text-field-muted" : "text-white"),
      )}
    >
      {day}
    </span>
  );
}

/**
 * The midnight band on top of every tab, rendered once by the app shell: the countdown to the VAT
 * deadline and every day of the current month. `vat_deadline_day` comes from AppContext, so a settings
 * change reaches every open tab through SSE. Wide tabs get one row of days; a narrow tab, where 31
 * labelled cells cannot fit, gets a 7-column month grid.
 */
export function DeadlineCalendar() {
  const { settings } = useApp();
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const deadlineDay = settings?.vat_deadline_day ?? DEFAULT_VAT_DEADLINE_DAY;
  const urgentDays = settings?.urgent_deadline_days ?? 3;
  const year = now.getFullYear();
  const month = now.getMonth();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const shownDeadline = Math.min(deadlineDay, daysInMonth); // the mark in this month, even once it has passed
  const next = nextDeadlineDate(deadlineDay, now); // the countdown rolls over to next month's deadline
  const [figure, line1, line2] = countdownParts(daysBetween(now, next), next.getDate(), next.toLocaleDateString("he-IL", { month: "long" }));
  const label = `${figure} ${line1} ${line2}`;

  const days = Array.from({ length: daysInMonth }, (_, i) => {
    const day = i + 1;
    const date = new Date(year, month, day);
    const isPast = day < now.getDate();
    const before = daysBetween(date, next);
    return {
      day,
      date,
      isPast,
      isToday: day === now.getDate(),
      isDeadline: day === shownDeadline,
      isUrgent: !isPast && before >= 1 && before <= urgentDays,
      isWeekend: date.getDay() >= 5,
    };
  });
  const { date: firstOfMonth } = days[0];

  return (
    <section
      aria-label={DEADLINE_LABEL}
      className="z-30 shrink-0 border-b border-white/10 bg-field px-4 py-2 text-white @3xl/main:sticky @3xl/main:top-0 @3xl/main:flex @3xl/main:h-[62px] @3xl/main:items-center @3xl/main:gap-4 @3xl/main:px-6"
    >
      <p className="flex shrink-0 items-center gap-2 pb-1 @3xl/main:pb-0">
        <span className="font-display text-4xl leading-none">{figure}</span>
        <span className="text-sm font-semibold leading-tight">
          {line1}
          <br />
          {line2}
        </span>
      </p>

      <div className="min-w-0 flex-1">
        {/* one row of days */}
        <div className="hidden @xl/main:grid" style={{ gridTemplateColumns: `repeat(${daysInMonth}, minmax(0, 1fr))` }} role="img" aria-label={label}>
          {days.map(({ date, ...d }) => (
            <div key={d.day} className="relative h-[38px]" title={tooltip(date, d.isDeadline)}>
              <div className={cx("flex h-6 justify-center", d.isUrgent && "bg-[#fcd34d]/15")}>
                <DayNumber {...d} />
              </div>
              {d.isDeadline && (
                <span
                  className={cx(
                    "absolute top-6 z-10 whitespace-nowrap text-[11px] font-semibold leading-[14px] text-accent",
                    d.day <= 3 ? "right-0" : d.day > daysInMonth - 3 ? "left-0" : "left-1/2 -translate-x-1/2",
                  )}
                >
                  {DEADLINE_LABEL}
                </span>
              )}
            </div>
          ))}
        </div>

        {/* a narrow tab: a month grid, Sunday on the right */}
        <div className="@xl/main:hidden" role="img" aria-label={label}>
          <div className="grid grid-cols-7 text-center">
            {WEEKDAYS.map((w) => (
              <span key={w} className="pb-0.5 text-xs font-semibold text-field-muted">
                {w}
              </span>
            ))}
            {Array.from({ length: firstOfMonth.getDay() }, (_, i) => (
              <span key={`blank-${i}`} />
            ))}
            {days.map(({ date, ...d }) => (
              <div key={d.day} className={cx("flex h-7 items-center justify-center", d.isUrgent && "bg-[#fcd34d]/15")} title={tooltip(date, d.isDeadline)}>
                <DayNumber {...d} />
              </div>
            ))}
          </div>
          <p className="mt-1 flex items-center gap-1.5 text-[11px] font-semibold leading-[14px] text-accent">
            <span aria-hidden className="h-2 w-2 rounded-full bg-accent" />
            {DEADLINE_LABEL}: {shownDeadline} ב{now.toLocaleDateString("he-IL", { month: "long" })}
          </p>
        </div>
      </div>
    </section>
  );
}
