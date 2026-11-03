import { cx, ROLE_LABEL } from "../lib/format";
import type { UserRole } from "../lib/types";
import { SuggestInput } from "./SuggestInput";
import { RoleBadge } from "./ui";

/** Fields shared by the "add worker" and "edit worker" dialogs, so both look and behave the same. */

const JOB_TITLE_SUGGESTIONS = ["מנהל/ת משרד", "רואה/ת חשבון", "מנהל/ת חשבונות", "פקיד/ת הנה״ח", "פקיד/ת שכר", "מתמחה", "מזכיר/ה"];
export const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const ROLE_HELP: Record<UserRole, string> = {
  MANAGER: "ניהול לקוחות, תבניות, הגדרות המשרד, עובדים ויומן הפעילות",
  WORKER: "שליחת הודעות, לוח מעקב, אישור חשבוניות וסימולטור",
};

export function JobTitleInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return <SuggestInput value={value} onChange={onChange} suggestions={JOB_TITLE_SUGGESTIONS} placeholder="לדוגמה: פקידת הנה״ח" />;
}

export function RolePicker({ value, onChange }: { value: UserRole; onChange: (r: UserRole) => void }) {
  return (
    <div role="radiogroup" aria-label="הרשאה" className="grid gap-2 sm:grid-cols-2">
      {(Object.keys(ROLE_LABEL) as UserRole[]).map((r) => (
        <button
          key={r}
          type="button"
          role="radio"
          aria-checked={value === r}
          onClick={() => onChange(r)}
          className={cx(
            "border p-3 text-start transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500",
            value === r ? "border-brand-500 bg-brand-50 ring-1 ring-inset ring-brand-500" : "border-ink-300 hover:bg-ink-50",
          )}
        >
          <RoleBadge role={r} />
          <span className="mt-1.5 block text-xs leading-snug text-ink-500">{ROLE_HELP[r]}</span>
        </button>
      ))}
    </div>
  );
}
