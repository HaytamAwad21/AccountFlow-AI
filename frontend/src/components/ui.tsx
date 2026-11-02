import { useEffect, useRef, useState, type ButtonHTMLAttributes, type KeyboardEvent as ReactKeyboardEvent, type ReactNode, type Ref } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, Briefcase, CheckCircle2, Crown, Eye, EyeOff, Info, Loader2, X, XCircle } from "lucide-react";
import { useApp } from "../context/AppContext";
import { PRIORITY_META, ROLE_LABEL, STATUS_META, cx } from "../lib/format";
import type { TicketPriority, TicketStatus, UserRole } from "../lib/types";

type Variant = "accent" | "onAccent" | "secondary" | "ghost" | "danger" | "fieldGhost";

const VARIANTS: Record<Variant, string> = {
  // The accent marks the clerk's next action: at most one on a screen.
  accent: "bg-accent text-accent-ink hover:bg-accent-deep disabled:bg-ink-200 disabled:text-ink-500",
  onAccent: "bg-accent-ink text-[#fff] hover:bg-[#1a2450]",
  secondary: "bg-surface text-ink-900 ring-1 ring-inset ring-ink-300 hover:bg-ink-100 disabled:text-ink-400",
  ghost: "text-ink-700 hover:bg-ink-100 hover:text-ink-900 disabled:text-ink-400",
  danger: "bg-red-600 text-white hover:bg-red-700 disabled:opacity-50",
  // For the midnight band.
  fieldGhost: "text-white ring-1 ring-inset ring-white/40 hover:bg-white/10 disabled:opacity-50",
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
  const sizes = { sm: "h-8 px-2.5 text-xs gap-1.5", md: "h-10 px-4 text-sm gap-2", lg: "h-12 px-5 text-base gap-2.5" };
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1 disabled:cursor-not-allowed",
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

/** A working section: a white panel with a thin border on the tinted page. Padding is set by each use. */
export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cx("border border-ink-300 bg-surface", className)}>{children}</section>;
}

export function SectionTitle({ step, title, hint, right }: { step?: string; title: string; hint?: string; right?: ReactNode }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <div className="min-w-0">
        <h3 className="flex items-center gap-2 font-display text-lg leading-tight text-ink-900">
          {step && <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-brand-600 text-xs text-white">{step}</span>}
          {title}
        </h3>
        {hint && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
      </div>
      {right}
    </div>
  );
}

/** Reversed tab, used for page tabs and filters. */
export function TabButton({ active, onClick, children, alert = false }: { active: boolean; onClick: () => void; children: ReactNode; alert?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cx(
        "whitespace-nowrap px-3 py-1.5 text-sm font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500",
        active ? "bg-brand-600 text-white" : cx("hover:bg-ink-100", alert ? "text-red-600" : "text-ink-700"),
      )}
    >
      {children}
    </button>
  );
}

export function RoleBadge({ role, className }: { role: UserRole; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1 text-xs font-semibold", className)}>
      {role === "MANAGER" ? <Crown className="h-3 w-3 shrink-0" /> : <Briefcase className="h-3 w-3 shrink-0" />}
      {ROLE_LABEL[role]}
    </span>
  );
}

/** State is a small flat shape, so a column scans by form as well as by colour. */
export function StatusMark({ status, className }: { status: TicketStatus; className?: string }) {
  const shape: Record<TicketStatus, ReactNode> = {
    OPEN: <circle cx="6" cy="6" r="4.5" fill="none" stroke="currentColor" strokeWidth="2" className="text-ink-500" />,
    WAITING_FOR_CLIENT: <circle cx="6" cy="6" r="5.5" fill="currentColor" className="text-link" />,
    SNOOZED_TONIGHT: (
      <g className="text-link">
        <circle cx="6" cy="6" r="4.5" fill="none" stroke="currentColor" strokeWidth="2" />
        <path d="M6 1.5a4.5 4.5 0 0 1 0 9z" fill="currentColor" />
      </g>
    ),
    NEEDS_CORRECTION: <path d="M6 .5 11.8 11.5H.2z" fill="currentColor" className="text-amber-600" />,
    NEEDS_CLERK_REVIEW: (
      <>
        <circle cx="6" cy="6" r="6" fill="#ffb27a" />
        <circle cx="6" cy="6" r="2.5" fill="#0d1533" />
      </>
    ),
    RESOLVED: <path d="M1.5 6.5 4.5 9.5 10.5 2.5" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-ink-500" />,
    ESCALATED: <rect x="1" y="1" width="10" height="10" fill="currentColor" className="text-red-600" />,
  };
  return (
    <svg viewBox="0 0 12 12" aria-hidden className={cx("h-3 w-3 shrink-0", className)}>
      {shape[status]}
    </svg>
  );
}

export function StatusBadge({ status, short = false }: { status: TicketStatus; short?: boolean }) {
  const m = STATUS_META[status];
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-sm font-semibold">
      <StatusMark status={status} />
      {short ? m.short : m.label}
    </span>
  );
}

export function PriorityLabel({ priority }: { priority: TicketPriority }) {
  const m = PRIORITY_META[priority];
  return <span className={cx("text-xs", m.className)}>{m.label}</span>;
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cx("h-4 w-4 animate-spin text-ink-400", className)} />;
}

export function Empty({ icon, title, hint }: { icon: ReactNode; title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      <div className="text-ink-300">{icon}</div>
      <p className="font-semibold text-ink-900">{title}</p>
      {hint && <p className="max-w-sm text-sm text-ink-500">{hint}</p>}
    </div>
  );
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  wide = false,
  narrow = false,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  wide?: boolean;
  /** A small centred dialog whose body scrolls inside it. */
  narrow?: boolean;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Focus moves into the dialog and returns to whatever opened it.
  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement as HTMLElement | null;
    if (!panelRef.current?.contains(opener)) panelRef.current?.focus();
    return () => opener?.focus();
  }, [open]);

  if (!open) return null;

  const trapTab = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "Tab") return;
    const items = panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE);
    if (!items?.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (e.shiftKey ? active === first || active === panelRef.current : active === last) {
      e.preventDefault();
      (e.shiftKey ? last : first).focus();
    }
  };

  // Portalled to <body>: the sidebar's transform would otherwise trap `fixed` inside its width.
  return createPortal(
    <div
      dir="rtl"
      className={cx("fixed inset-0 z-50 flex justify-center overflow-y-auto bg-[#0d1533]/70 p-4", narrow ? "items-center" : "items-start sm:p-8")}
      onMouseDown={onClose}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        className={cx(
          "animate-slide-in border border-ink-300 bg-surface outline-none",
          narrow ? "flex max-h-[80vh] w-[440px] max-w-[calc(100vw-32px)] flex-col" : cx("w-full", wide ? "max-w-6xl" : "max-w-xl"),
        )}
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={trapTab}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-ink-300 px-6 py-4">
          <div className="min-w-0">
            <div className={cx("font-display text-xl leading-tight text-ink-900", narrow && "whitespace-nowrap")}>{title}</div>
            {subtitle && <div className="mt-1 text-sm text-ink-500">{subtitle}</div>}
          </div>
          <button onClick={onClose} className="p-1.5 text-ink-500 hover:bg-ink-100 hover:text-ink-900" aria-label="סגירה">
            <X className="h-5 w-5" />
          </button>
        </div>
        {narrow ? <div className="min-h-0 overflow-y-auto">{children}</div> : children}
      </div>
    </div>,
    document.body,
  );
}

const TOAST_ICON = {
  info: <Info className="h-5 w-5 text-link" />,
  success: <CheckCircle2 className="h-5 w-5 text-emerald-600" />,
  warning: <AlertTriangle className="h-5 w-5 text-amber-500" />,
  error: <XCircle className="h-5 w-5 text-red-600" />,
};

export function Toaster() {
  const { toasts, dismissToast } = useApp();
  return (
    <div className="pointer-events-none fixed bottom-4 left-1/2 z-[60] flex w-[min(440px,calc(100vw-2rem))] -translate-x-1/2 flex-col gap-2">
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto flex animate-slide-in gap-3 border border-ink-300 bg-surface p-3.5">
          <div className="mt-0.5 shrink-0">{TOAST_ICON[t.tone]}</div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-bold text-ink-900">{t.title}</p>
            {t.body && (
              <p dir={t.dir ?? "auto"} className="mt-0.5 line-clamp-3 whitespace-pre-line text-xs text-ink-600">
                {t.body}
              </p>
            )}
          </div>
          <button onClick={() => dismissToast(t.id)} className="shrink-0 self-start text-ink-400 hover:text-ink-900" aria-label="סגירת התראה">
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
    <label className={cx("inline-flex select-none items-center gap-2 text-sm font-medium text-ink-700", disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer")}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cx("relative h-5 w-9 shrink-0 rounded-full transition-colors", checked ? "bg-brand-600" : "bg-ink-300")}
      >
        <span className={cx("absolute top-0.5 h-4 w-4 rounded-full bg-[#fff] transition-all", checked ? "start-[18px]" : "start-0.5")} />
      </button>
      {label}
    </label>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-bold text-ink-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-ink-500">{hint}</span>}
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
        className="absolute left-1.5 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center text-ink-400 hover:bg-ink-100 hover:text-ink-900"
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

export const inputClass =
  "block w-full border-0 bg-surface px-3 py-2 text-sm text-ink-900 ring-1 ring-inset ring-ink-300 placeholder:text-ink-400 hover:ring-ink-400 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-brand-500 disabled:bg-ink-50 disabled:text-ink-500";
