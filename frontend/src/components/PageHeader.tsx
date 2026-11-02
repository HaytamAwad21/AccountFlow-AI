import type { ReactNode } from "react";
import { cx } from "../lib/format";

/** The logo at every scale (sidebar, mobile bar, login screen). It reads the next deadline's day; null while that loads. */
export function DeadlineDisc({ className, day }: { className?: string; day: number | null }) {
  return (
    <span aria-hidden className={cx("grid shrink-0 place-items-center rounded-full bg-accent font-display leading-none text-accent-ink", className)}>
      {day}
    </span>
  );
}

/**
 * The page's title and actions, directly under the shared DeadlineCalendar band so the two read as one
 * field. On wide tabs it sticks below the band (62px); the page's explanation sits under it, in full.
 */
export function PageHeader({ title, hint, actions }: { title: string; hint?: ReactNode; actions?: ReactNode }) {
  return (
    <>
      <header className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 bg-field px-4 py-2 text-white @3xl/main:top-[62px] @3xl/main:px-6">
        <h1 className="font-display text-2xl leading-tight">{title}</h1>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </header>
      {hint && <p className="mx-auto w-full max-w-7xl shrink-0 px-4 pt-3 text-sm text-ink-600 @3xl/main:px-6">{hint}</p>}
    </>
  );
}
