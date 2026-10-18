import { useEffect, useState, type ButtonHTMLAttributes, type ReactNode, type Ref } from "react";
import { AlertTriangle, CheckCircle2, Eye, EyeOff, Info, Loader2, X, XCircle } from "lucide-react";
import { useApp } from "../context/AppContext";
import { PRIORITY_META, ROLE_LABEL, STATUS_META, cx } from "../lib/format";
import type { TicketPriority, TicketStatus, UserRole } from "../lib/types";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "success" | "wa";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand-600 text-white hover:bg-brand-700 shadow-sm disabled:bg-brand-600/50",
  secondary: "bg-white text-slate-800 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 disabled:text-slate-400",
  ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900 disabled:text-slate-300",
  danger: "bg-red-600 text-white hover:bg-red-700 disabled:bg-red-600/50",
  success: "bg-emerald-600 text-white hover:bg-emerald-700 disabled:bg-emerald-600/50",
  wa: "bg-wa-teal text-white hover:bg-wa-header disabled:bg-wa-teal/50",
};

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon,
  children,
  className,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: ReactNode;
}) {
  const sizes = { sm: "h-8 px-2.5 text-xs gap-1.5", md: "h-9 px-3.5 text-sm gap-2", lg: "h-12 px-5 text-base gap-2.5" };
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center rounded-lg font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1 disabled:cursor-not-allowed",
        sizes[size],
        VARIANTS[variant],
        className,
      )}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("rounded-xl border border-slate-200 bg-white shadow-sm", className)}>{children}</div>;
}

export function SectionTitle({ step, title, hint, right }: { step?: string; title: string; hint?: string; right?: ReactNode }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <div>
        <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          {step && <span className="grid h-5 w-5 place-items-center rounded-full bg-brand-600 text-[11px] font-bold text-white">{step}</span>}
          {title}
        </h3>
        {hint && <p className="mt-0.5 text-xs text-slate-500">{hint}</p>}
      </div>
      {right}
    </div>
  );
}

export function RoleBadge({ role, className }: { role: UserRole; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10.5px] font-semibold",
        role === "MANAGER" ? "bg-amber-100 text-amber-800" : "bg-sky-100 text-sky-800",
        className,
      )}
    >
      {role === "MANAGER" ? "👑 " : "🧑‍💼 "}
      {ROLE_LABEL[role]}
    </span>
  );
}

export function StatusBadge({ status, short = false }: { status: TicketStatus; short?: boolean }) {
  const m = STATUS_META[status];
  return (
    <span className={cx("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset", m.className)}>
      <span className={cx("h-1.5 w-1.5 rounded-full", m.dot)} />
      {short ? m.short : m.label}
    </span>
  );
}

export function PriorityLabel({ priority }: { priority: TicketPriority }) {
  const m = PRIORITY_META[priority];
  return <span className={cx("text-xs", m.className)}>{m.label}</span>;
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cx("h-4 w-4 animate-spin text-slate-400", className)} />;
}

export function Empty({ icon, title, hint }: { icon: ReactNode; title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      <div className="text-slate-300">{icon}</div>
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {hint && <p className="max-w-sm text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  wide = false,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4 backdrop-blur-[2px] sm:p-8" onMouseDown={onClose}>
      <div
        className={cx("w-full animate-slide-in rounded-2xl bg-white shadow-2xl", wide ? "max-w-6xl" : "max-w-xl")}
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-4">
          <div className="min-w-0">
            <div className="text-lg font-semibold text-slate-900">{title}</div>
            {subtitle && <div className="mt-0.5 text-sm text-slate-500">{subtitle}</div>}
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="סגירה">
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

const TOAST_ICON = {
  info: <Info className="h-5 w-5 text-brand-600" />,
  success: <CheckCircle2 className="h-5 w-5 text-emerald-600" />,
  warning: <AlertTriangle className="h-5 w-5 text-amber-500" />,
  error: <XCircle className="h-5 w-5 text-red-600" />,
};

export function Toaster() {
  const { toasts, dismissToast } = useApp();
  return (
    <div className="pointer-events-none fixed bottom-4 left-1/2 z-[60] flex w-[min(440px,calc(100vw-2rem))] -translate-x-1/2 flex-col gap-2">
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto flex animate-slide-in gap-3 rounded-xl border border-slate-200 bg-white p-3.5 shadow-lg">
          <div className="mt-0.5 shrink-0">{TOAST_ICON[t.tone]}</div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-slate-900">{t.title}</p>
            {t.body && (
              <p dir={t.dir ?? "auto"} className="mt-0.5 line-clamp-3 whitespace-pre-line text-xs text-slate-600">
                {t.body}
              </p>
            )}
          </div>
          <button onClick={() => dismissToast(t.id)} className="shrink-0 self-start text-slate-400 hover:text-slate-700" aria-label="סגירת התראה">
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label className={cx("inline-flex select-none items-center gap-2 text-sm text-slate-700", disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer")}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cx("relative h-5 w-9 shrink-0 rounded-full transition-colors", checked ? "bg-emerald-500" : "bg-slate-300")}
      >
        <span className={cx("absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all", checked ? "start-[18px]" : "start-0.5")} />
      </button>
      {label}
    </label>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-600">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>}
    </label>
  );
}

/** Numbers, phones and IDs stay left-to-right inside Hebrew text. */
export function Ltr({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span dir="ltr" className={cx("inline-block", className)}>
      {children}
    </span>
  );
}

/**
 * Password field with a show / hide toggle. The value is typed left-to-right, so the field uses
 * PHYSICAL sides (eye button on the left, padding on the left): logical start/end would resolve
 * differently for the LTR input and its RTL container and make the text run under the button.
 */
export function PasswordInput({
  value,
  onChange,
  autoComplete = "current-password",
  placeholder = "••••••••",
  invalid = false,
  inputRef,
  autoFocus,
}: {
  value: string;
  onChange: (v: string) => void;
  autoComplete?: string;
  placeholder?: string;
  invalid?: boolean;
  inputRef?: Ref<HTMLInputElement>;
  autoFocus?: boolean;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative" dir="ltr">
      <input
        ref={inputRef}
        type={show ? "text" : "password"}
        autoComplete={autoComplete}
        autoFocus={autoFocus}
        dir="ltr"
        spellCheck={false}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={cx(inputClass, "pl-10 pr-3 text-left", invalid && "ring-2 ring-red-400")}
      />
      <button
        type="button"
        onMouseDown={(e) => e.preventDefault()} // keep the caret in the field
        onClick={() => setShow((v) => !v)}
        aria-pressed={show}
        aria-label={show ? "הסתרת הסיסמה" : "הצגת הסיסמה"}
        title={show ? "הסתרת הסיסמה" : "הצגת הסיסמה"}
        className="absolute left-1.5 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-700"
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

export const inputClass =
  "block w-full rounded-lg border-0 bg-white px-3 py-2 text-sm text-slate-900 ring-1 ring-inset ring-slate-300 placeholder:text-slate-400 focus:ring-2 focus:ring-inset focus:ring-brand-500 disabled:bg-slate-50 disabled:text-slate-500";
