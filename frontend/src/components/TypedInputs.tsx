import { forwardRef, useState } from "react";
import { AlertCircle, ChevronDown } from "lucide-react";
import { AMOUNT_TYPING_RE, CURRENCY_OPTIONS, NUMBERS_ONLY_ERROR, cx, type Currency } from "../lib/format";
import { inputClass } from "./ui";

/** Red helper text under a field. */
export function FieldError({ message }: { message: string | null | undefined }) {
  if (!message) return null;
  return (
    <p role="alert" className="mt-1 flex items-center gap-1 text-[11px] font-medium text-red-600">
      <AlertCircle className="h-3.5 w-3.5 shrink-0" />
      {message}
    </p>
  );
}

/**
 * Money input: digits and one decimal point only (at most 2 decimals), with a ₪ / $ selector
 * inside the left edge of the box. Any other character is blocked and shows "נא להזין מספרים בלבד".
 * `value` is the raw number ("1240.5"); formatting with the currency happens when it is rendered / sent.
 */
export const AmountInput = forwardRef<
  HTMLInputElement,
  {
    value: string;
    onChange: (value: string) => void;
    currency: Currency;
    onCurrencyChange: (currency: Currency) => void;
    placeholder?: string;
    /** an error from the form (e.g. on submit); typing errors are handled here */
    error?: string | null;
    invalid?: boolean;
  }
>(function AmountInput({ value, onChange, currency, onCurrencyChange, placeholder, error, invalid }, ref) {
  const [typingError, setTypingError] = useState<string | null>(null);

  const accept = (raw: string) => {
    // Paste-friendly: thousands separators and surrounding spaces are dropped, nothing else is.
    const cleaned = raw.replace(/,/g, "").trim();
    if (AMOUNT_TYPING_RE.test(cleaned)) {
      setTypingError(null);
      onChange(cleaned);
    } else {
      setTypingError(/^\d*\.\d{3,}$/.test(cleaned) ? "עד 2 ספרות אחרי הנקודה" : NUMBERS_ONLY_ERROR);
    }
  };

  const shown = typingError ?? error ?? null;
  return (
    <div>
      <div className="relative">
        <input
          ref={ref}
          type="text"
          inputMode="decimal"
          pattern="\d+(\.\d{1,2})?"
          autoComplete="off"
          dir="ltr"
          value={value}
          onChange={(e) => accept(e.target.value)}
          onBlur={() => setTypingError(null)}
          placeholder={placeholder}
          aria-invalid={!!shown || invalid}
          className={cx(inputClass, "pl-[5.5rem] text-end tabular-nums", (shown || invalid) && "ring-2 ring-red-400 focus:ring-red-500")}
        />
        <div className="absolute inset-y-1 left-1 flex items-center">
          <select
            value={currency}
            onChange={(e) => onCurrencyChange(e.target.value as Currency)}
            aria-label="מטבע"
            title="מטבע"
            className="h-full appearance-none rounded-md border-0 bg-slate-100 py-0 pl-6 pr-2 text-xs font-semibold text-slate-700 ring-0 hover:bg-slate-200 focus:ring-2 focus:ring-brand-500"
          >
            {CURRENCY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.symbol} {o.label}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute left-1.5 h-3.5 w-3.5 text-slate-500" />
        </div>
      </div>
      <FieldError message={shown} />
    </div>
  );
});
