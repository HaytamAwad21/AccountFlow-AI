import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { CalendarRange, Check, ChevronDown } from "lucide-react";
import { expandYear, parseDdMmYyyy, toDdMmYyyy } from "../lib/date";
import { cx } from "../lib/format";
import { DateInput } from "./DateInput";
import { inputClass } from "./ui";

export type RangeKey = "all" | "this_month" | "last_month" | "2m" | "3m" | "6m" | "12m" | "this_year" | "custom";

/** The chosen period. `from` and `to` are dd/mm/yyyy text and only matter for "custom"; the picker passes on a
 *  date once it is finished or its field is left, never while it is half-typed. */
export interface DateRange {
  key: RangeKey;
  from: string;
  to: string;
}

/** First and last day of a period, both inclusive; null is open-ended. */
export interface Bounds {
  from: Date | null;
  to: Date | null;
  error: string | null;
}

export const ALL_TIME: DateRange = { key: "all", from: "", to: "" };

const OPTIONS: { key: RangeKey; label: string }[] = [
  { key: "all", label: "כל התקופה" },
  { key: "this_month", label: "החודש הנוכחי" },
  { key: "last_month", label: "החודש הקודם" },
  { key: "2m", label: "חודשיים אחרונים" },
  { key: "3m", label: "3 חודשים אחרונים" },
  { key: "6m", label: "6 חודשים אחרונים" },
  { key: "12m", label: "12 חודשים אחרונים" },
  { key: "this_year", label: "מתחילת השנה" },
  { key: "custom", label: "טווח תאריכים" },
];

const LAST_MONTHS: Partial<Record<RangeKey, number>> = { "2m": 2, "3m": 3, "6m": 6, "12m": 12 };

/** The same day `n` months back; a day the earlier month lacks becomes its last day (31/12 back 3 is 30/09). */
function monthsBack(d: Date, n: number): Date {
  const first = new Date(d.getFullYear(), d.getMonth() - n, 1);
  const last = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
  return new Date(first.getFullYear(), first.getMonth(), Math.min(d.getDate(), last));
}

export function rangeBounds(r: DateRange, now = new Date()): Bounds {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const n = LAST_MONTHS[r.key];
  if (n) return { from: monthsBack(today, n), to: today, error: null };
  switch (r.key) {
    case "this_month":
      return { from: new Date(today.getFullYear(), today.getMonth(), 1), to: today, error: null };
    case "last_month":
      return { from: new Date(today.getFullYear(), today.getMonth() - 1, 1), to: new Date(today.getFullYear(), today.getMonth(), 0), error: null };
    case "this_year":
      return { from: new Date(today.getFullYear(), 0, 1), to: today, error: null };
    case "custom": {
      // An empty side is open-ended; "05/10/26" counts as 2026.
      const from = parseDdMmYyyy(expandYear(r.from));
      const to = parseDdMmYyyy(expandYear(r.to));
      const error =
        r.from && !from
          ? "תאריך ההתחלה לא תקין. יש להזין יום/חודש/שנה, למשל 05/10/2026"
          : r.to && !to
            ? "תאריך הסיום לא תקין. יש להזין יום/חודש/שנה, למשל 05/10/2026"
            : from && to && from > to
              ? "תאריך ההתחלה מאוחר מתאריך הסיום"
              : null;
      return { from, to, error };
    }
    default:
      return { from: null, to: null, error: null };
  }
}

/** Whether an ISO timestamp falls on a day inside the bounds (local time). Nothing matches a range in error. */
export function inBounds(iso: string, b: Bounds): boolean {
  if (b.error) return false;
  const t = new Date(iso);
  if (b.from && t < b.from) return false;
  if (b.to && t >= new Date(b.to.getFullYear(), b.to.getMonth(), b.to.getDate() + 1)) return false;
  return true;
}

function Span({ b, className }: { b: Bounds; className?: string }) {
  if (!b.from || !b.to) return null;
  return (
    <span className={cx("tabular-nums", className)}>
      <bdi>{toDdMmYyyy(b.from)}</bdi> – <bdi>{toDdMmYyyy(b.to)}</bdi>
    </span>
  );
}

/**
 * A bank-style period picker: ready-made periods (this month, the last 2, 3, 6 or 12 months…) in a list drawn
 * in the app's colours, or a custom range typed or picked on the calendar. `countFor` shows how many items
 * each period holds.
 */
export function DateRangeFilter({ value, onChange, countFor }: { value: DateRange; onChange: (r: DateRange) => void; countFor?: (b: Bounds) => number }) {
  const id = useId();
  const wrapRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const current = OPTIONS.find((o) => o.key === value.key) ?? OPTIONS[0];
  const bounds = rangeBounds(value);
  // What is in the two date fields, including a date still being typed.
  const [draft, setDraft] = useState({ from: value.from, to: value.to });
  useEffect(() => setDraft({ from: value.from, to: value.to }), [value.from, value.to]);

  const edit = (side: "from" | "to", text: string) => {
    setDraft((d) => ({ ...d, [side]: text }));
    // A finished date applies at once; a half-typed one waits until the field is left.
    if (!text || parseDdMmYyyy(text)) onChange({ ...value, [side]: text });
  };

  const leave = (side: "from" | "to") => {
    const text = expandYear(draft[side].trim());
    setDraft((d) => ({ ...d, [side]: text }));
    if (text !== value[side]) onChange({ ...value, [side]: text });
  };

  useEffect(() => {
    if (!open) return;
    listRef.current?.focus();
    const close = (e: MouseEvent) => !wrapRef.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const show = () => {
    setActive(OPTIONS.indexOf(current));
    setOpen(true);
  };

  const choose = (key: RangeKey) => {
    setOpen(false);
    buttonRef.current?.focus();
    if (key === value.key) return;
    if (key !== "custom") return onChange({ key, from: "", to: "" });
    // The custom range starts from the period on screen, so it only needs adjusting.
    onChange({ key, from: bounds.from ? toDdMmYyyy(bounds.from) : "", to: bounds.to ? toDdMmYyyy(bounds.to) : "" });
  };

  const onListKey = (e: KeyboardEvent<HTMLUListElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((i) => (i + step + OPTIONS.length) % OPTIONS.length);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      choose(OPTIONS[active].key);
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      setOpen(false);
      buttonRef.current?.focus();
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  };

  return (
    <div className="flex flex-wrap items-end gap-x-3 gap-y-2">
      <div ref={wrapRef} className="relative w-52">
        <span id={`${id}-label`} className="mb-1 block text-xs font-bold text-ink-700">
          טווח זמן
        </span>
        <button
          ref={buttonRef}
          type="button"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-labelledby={`${id}-label ${id}-value`}
          onClick={() => (open ? setOpen(false) : show())}
          onKeyDown={(e) => {
            if ((e.key === "ArrowDown" || e.key === "ArrowUp") && !open) {
              e.preventDefault();
              show();
            }
          }}
          className={cx(inputClass, "flex items-center gap-2 py-1.5 text-start")}
        >
          <CalendarRange className="h-4 w-4 shrink-0 text-ink-500" />
          <span id={`${id}-value`} className="min-w-0 flex-1 truncate">
            {current.label}
          </span>
          <ChevronDown className={cx("h-4 w-4 shrink-0 text-ink-500 transition-transform", open && "rotate-180")} />
        </button>
        {open && (
          <ul
            ref={listRef}
            role="listbox"
            tabIndex={-1}
            aria-labelledby={`${id}-label`}
            aria-activedescendant={`${id}-${active}`}
            onKeyDown={onListKey}
            className="absolute inset-x-0 top-full z-20 mt-1 border border-ink-300 bg-surface py-1 focus:outline-none"
          >
            {OPTIONS.map((o, i) => {
              const b = rangeBounds({ key: o.key, from: "", to: "" });
              const hot = i === active;
              const count = o.key !== "custom" && countFor ? countFor(b) : null;
              return (
                <li
                  key={o.key}
                  id={`${id}-${i}`}
                  role="option"
                  aria-selected={o.key === value.key}
                  title={b.from && b.to ? `${toDdMmYyyy(b.from)} – ${toDdMmYyyy(b.to)}` : undefined}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => choose(o.key)}
                  onMouseEnter={() => setActive(i)}
                  className={cx(
                    "flex cursor-pointer items-center gap-1.5 px-2 py-1.5 text-sm transition-colors",
                    hot ? "bg-brand-600 text-white" : "text-ink-900",
                    o.key === "custom" && "mt-1 border-t border-ink-200",
                  )}
                >
                  <span className="w-4 shrink-0">{o.key === value.key && <Check className="h-3.5 w-3.5" />}</span>
                  <span className="min-w-0 flex-1 truncate">{o.label}</span>
                  {count !== null && <span className={cx("text-xs tabular-nums", hot ? "text-white" : "text-ink-500")}>{count}</span>}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {value.key === "custom" ? (
        <>
          {/* the two dates wrap as one pair */}
          <div className="flex w-full gap-3 @md:w-auto">
            <label className="block min-w-0 flex-1 @md:w-40 @md:flex-none">
              <span className="mb-1 block text-xs font-bold text-ink-700">מתאריך</span>
              <DateInput value={draft.from} onChange={(t) => edit("from", t)} onBlur={() => leave("from")} className="py-1.5" aria-label="מתאריך" />
            </label>
            <label className="block min-w-0 flex-1 @md:w-40 @md:flex-none">
              <span className="mb-1 block text-xs font-bold text-ink-700">עד תאריך</span>
              <DateInput value={draft.to} onChange={(t) => edit("to", t)} onBlur={() => leave("to")} className="py-1.5" aria-label="עד תאריך" />
            </label>
          </div>
          {bounds.error && (
            <p role="alert" className="basis-full text-xs font-bold text-red-700">
              {bounds.error}
            </p>
          )}
        </>
      ) : (
        <Span b={bounds} className="pb-2 text-xs text-ink-500" />
      )}
    </div>
  );
}
