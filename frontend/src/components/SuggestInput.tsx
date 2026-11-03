import { useId, useState, type KeyboardEvent } from "react";
import { Check, ChevronDown } from "lucide-react";
import { cx } from "../lib/format";
import { inputClass } from "./ui";

/**
 * A text field with a list of suggestions drawn in the app's own colours (the browser's datalist popup
 * ignores the theme). Any other text can still be typed. Arrow keys move through the list, Enter picks
 * the highlighted suggestion and Escape closes the list without closing the surrounding dialog.
 */
export function SuggestInput({
  value,
  onChange,
  suggestions,
  placeholder,
  invalid = false,
  autoFocus,
}: {
  value: string;
  onChange: (v: string) => void;
  suggestions: readonly string[];
  placeholder?: string;
  invalid?: boolean;
  autoFocus?: boolean;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [filtering, setFiltering] = useState(false);
  const typed = value.trim();
  // The list opens with every suggestion, even when the field holds a title of its own; typing narrows it.
  const shown = filtering && typed ? suggestions.filter((s) => s.includes(typed)) : suggestions;
  const listOpen = open && shown.length > 0;

  const openAll = () => {
    setOpen(true);
    setFiltering(false);
  };

  const choose = (s: string) => {
    onChange(s);
    setOpen(false);
    setActive(-1);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!listOpen) {
        openAll();
        setActive(Math.max(0, suggestions.indexOf(typed)));
        return;
      }
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((i) => (i + step + shown.length) % shown.length);
    } else if (e.key === "Enter" && listOpen && shown[active]) {
      e.preventDefault(); // pick the suggestion instead of submitting the form
      choose(shown[active]);
    } else if (e.key === "Escape" && listOpen) {
      e.stopPropagation(); // close the list only, not the dialog
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <input
        role="combobox"
        aria-expanded={listOpen}
        aria-controls={`${id}-list`}
        aria-autocomplete="list"
        aria-activedescendant={listOpen && active >= 0 ? `${id}-${active}` : undefined}
        autoFocus={autoFocus}
        autoComplete="off"
        dir="auto"
        value={value}
        placeholder={placeholder}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setFiltering(true);
          setActive(-1);
        }}
        onFocus={openAll}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        className={cx(inputClass, "pe-9", invalid && "ring-2 ring-red-400")}
      />
      <button
        type="button"
        tabIndex={-1}
        aria-label={listOpen ? "סגירת הרשימה" : "הצגת האפשרויות"}
        onMouseDown={(e) => e.preventDefault()} // keep the caret in the field
        onClick={() => (listOpen ? setOpen(false) : openAll())}
        className="absolute end-1 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center text-ink-500 transition-colors hover:bg-ink-100 hover:text-ink-900"
      >
        <ChevronDown className={cx("h-4 w-4 transition-transform", listOpen && "rotate-180")} />
      </button>
      {listOpen && (
        <ul id={`${id}-list`} role="listbox" className="absolute inset-x-0 top-full z-10 mt-1 max-h-60 overflow-y-auto border border-ink-300 bg-surface py-1">
          {shown.map((s, i) => (
            <li
              key={s}
              id={`${id}-${i}`}
              role="option"
              aria-selected={s === typed}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(s)}
              onMouseEnter={() => setActive(i)}
              className={cx(
                "flex cursor-pointer items-center justify-between gap-2 px-3 py-2 text-sm transition-colors",
                i === active ? "bg-brand-600 text-white" : "text-ink-900",
              )}
            >
              {s}
              {s === typed && <Check className="h-4 w-4 shrink-0" />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
