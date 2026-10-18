import { forwardRef, useEffect, useLayoutEffect, useRef, useState, type InputHTMLAttributes } from "react";
import { createPortal } from "react-dom";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { maskDate, parseDdMmYyyy, toDdMmYyyy } from "../lib/date";
import { cx } from "../lib/format";
import { inputClass } from "./ui";

const WEEKDAYS = ["א׳", "ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "ש׳"]; // Israeli week: Sunday first
const MONTH_FMT = new Intl.DateTimeFormat("he-IL", { month: "long", year: "numeric" });

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type"> & {
  value: string;
  onChange: (value: string) => void;
};

/** dd/mm/yyyy text field with an automatic slash mask and a Hebrew pop-up calendar. */
export const DateInput = forwardRef<HTMLInputElement, Props>(function DateInput({ value, onChange, className, placeholder, ...rest }, ref) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const selected = parseDdMmYyyy(value);
  const [view, setView] = useState(() => {
    const d = selected ?? new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });

  // Fixed position under the field (escapes scrolling modal bodies); flips up near the bottom.
  useLayoutEffect(() => {
    if (!open || !wrapRef.current) return;
    const r = wrapRef.current.getBoundingClientRect();
    const h = popRef.current?.offsetHeight ?? 300;
    const w = popRef.current?.offsetWidth ?? 280;
    const top = r.bottom + 4 + h > window.innerHeight ? Math.max(8, r.top - 4 - h) : r.bottom + 4;
    const left = Math.min(Math.max(8, r.left), window.innerWidth - w - 8); // aligned with the calendar button
    setPos({ top, left });
  }, [open, view]);

  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      const t = e.target as Node;
      if (wrapRef.current?.contains(t) || popRef.current?.contains(t)) return;
      setOpen(false);
    };
    // capture phase: Escape closes only the calendar, not the surrounding modal or page shortcuts
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      setOpen(false);
    };
    const onScroll = (e: Event) => !popRef.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("resize", onScroll);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      document.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("resize", onScroll);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open]);

  const toggle = () => {
    if (!open) {
      const d = selected ?? new Date();
      setView(new Date(d.getFullYear(), d.getMonth(), 1));
      setPos(null);
    }
    setOpen((o) => !o);
  };

  const pick = (d: Date) => {
    onChange(toDdMmYyyy(d));
    setOpen(false);
  };

  const today = new Date();
  const sameDay = (a: Date | null, b: Date) =>
    !!a && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  const first = view.getDay();
  const daysInMonth = new Date(view.getFullYear(), view.getMonth() + 1, 0).getDate();
  const cells: (Date | null)[] = [
    ...Array.from({ length: first }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => new Date(view.getFullYear(), view.getMonth(), i + 1)),
  ];
  const shift = (months: number) => setView((v) => new Date(v.getFullYear(), v.getMonth() + months, 1));

  return (
    <div ref={wrapRef} className="relative">
      <input
        ref={ref}
        {...rest}
        type="text"
        dir="ltr"
        inputMode="numeric"
        autoComplete="off"
        maxLength={10}
        placeholder={placeholder ?? "dd/mm/yyyy"}
        value={value}
        onChange={(e) => onChange(maskDate(e.target.value, value))}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" && e.altKey) {
            e.preventDefault();
            toggle();
          }
          rest.onKeyDown?.(e);
        }}
        className={cx(inputClass, "pl-10 text-end tabular-nums", className)}
      />
      {/* physical left side: the LTR date sits on the right, the calendar button on the left */}
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          toggle();
        }}
        aria-label="פתיחת לוח שנה"
        title="בחירה מלוח שנה"
        className={cx(
          "absolute left-1.5 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-brand-600",
          open && "bg-slate-100 text-brand-600",
        )}
      >
        <CalendarDays className="h-4 w-4" />
      </button>

      {open &&
        createPortal(
          <div
            ref={popRef}
            dir="rtl"
            role="dialog"
            aria-label="לוח שנה"
            style={{ top: pos?.top ?? -9999, left: pos?.left ?? -9999 }}
            className="fixed z-[100] w-[272px] rounded-xl bg-white p-3 text-sm shadow-xl ring-1 ring-slate-200"
          >
            <div className="mb-2 flex items-center justify-between">
              <button type="button" onClick={() => shift(-1)} aria-label="החודש הקודם" className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100">
                <ChevronRight className="h-4 w-4" />
              </button>
              <span className="font-semibold text-slate-900">{MONTH_FMT.format(view)}</span>
              <button type="button" onClick={() => shift(1)} aria-label="החודש הבא" className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100">
                <ChevronLeft className="h-4 w-4" />
              </button>
            </div>
            <div className="grid grid-cols-7 gap-0.5 text-center">
              {WEEKDAYS.map((w) => (
                <span key={w} className="py-1 text-[11px] font-medium text-slate-400">
                  {w}
                </span>
              ))}
              {cells.map((d, i) =>
                d ? (
                  <button
                    key={i}
                    type="button"
                    onClick={() => pick(d)}
                    className={cx(
                      "h-8 rounded-md tabular-nums",
                      sameDay(selected, d)
                        ? "bg-brand-600 font-semibold text-white"
                        : sameDay(today, d)
                          ? "font-semibold text-brand-600 ring-1 ring-inset ring-brand-300 hover:bg-slate-100"
                          : "text-slate-700 hover:bg-slate-100",
                    )}
                  >
                    {d.getDate()}
                  </button>
                ) : (
                  <span key={i} />
                ),
              )}
            </div>
            <div className="mt-2 flex items-center justify-between border-t border-slate-100 pt-2 text-xs">
              <button type="button" onClick={() => pick(new Date())} className="rounded-md px-2 py-1 font-medium text-brand-600 hover:bg-slate-100">
                היום
              </button>
              {value && (
                <button
                  type="button"
                  onClick={() => {
                    onChange("");
                    setOpen(false);
                  }}
                  className="rounded-md px-2 py-1 text-slate-500 hover:bg-slate-100"
                >
                  ניקוי
                </button>
              )}
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
});
