import { useEffect, useState } from "react";
import { UserPlus } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api } from "../lib/api";
import { cx, ROLE_LABEL } from "../lib/format";
import type { UserRole } from "../lib/types";
import { Button, Field, inputClass, Modal, PasswordInput, RoleBadge, Toggle } from "./ui";

const JOB_TITLE_SUGGESTIONS = ["מנהל/ת משרד", "רואה/ת חשבון", "מנהל/ת חשבונות", "פקיד/ת הנה״ח", "פקיד/ת שכר", "מתמחה", "מזכיר/ה"];
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const ROLE_HELP: Record<UserRole, string> = {
  MANAGER: "ניהול לקוחות, תבניות, הגדרות המשרד, עובדים ויומן הפעילות",
  WORKER: "שליחת הודעות, לוח מעקב, אישור חשבוניות וסימולטור",
};

/** Manager-only "add worker" form: name and job title are separate fields. */
export function AddWorkerModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { refreshUsers, toast } = useApp();
  const [fullName, setFullName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserRole>("WORKER");
  const [active, setActive] = useState(true);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [touched, setTouched] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setFullName("");
    setJobTitle("");
    setEmail("");
    setRole("WORKER");
    setActive(true);
    setPassword("");
    setConfirm("");
    setTouched(false);
  }, [open]);

  const errors = {
    fullName: fullName.trim().length < 2 ? "נדרשים לפחות 2 תווים" : null,
    email: !EMAIL_RE.test(email.trim()) ? "כתובת אימייל לא תקינה" : null,
    password: password.length < 6 ? "לפחות 6 תווים" : null,
    confirm: confirm !== password ? "אימות הסיסמה אינו תואם" : null,
  };
  const hasErrors = Object.values(errors).some(Boolean);
  const show = (key: keyof typeof errors, value: string) => (touched || value ? errors[key] : null);

  const save = async () => {
    setTouched(true);
    if (hasErrors) return;
    setSaving(true);
    try {
      await api.createUser({
        full_name: fullName.trim(),
        job_title: jobTitle.trim(),
        email: email.trim().toLowerCase(),
        role,
        is_active: active,
        password,
      });
      await refreshUsers();
      toast({ tone: "success", title: "העובד/ת נוסף/ה לצוות", body: `${fullName.trim()}${jobTitle.trim() ? ` · ${jobTitle.trim()}` : ""}` });
      onClose();
    } catch (e) {
      toast({ tone: "error", title: "הוספת העובד/ת נכשלה", body: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="הוספת עובד/ת" subtitle="פרטי העובד/ת, הרשאה וסיסמה ראשונית">
      <form
        dir="rtl"
        className="space-y-5 p-6"
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <section className="grid gap-3 sm:grid-cols-2">
          <Field label="שם מלא" hint={show("fullName", fullName) ?? undefined}>
            <input
              autoFocus
              dir="auto"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="לדוגמה: יעל לוי"
              className={cx(inputClass, show("fullName", fullName) && "ring-2 ring-red-400")}
            />
          </Field>
          <Field label="תפקיד במשרד" hint="מוצג מתחת לשם (רשות)">
            <input
              dir="auto"
              list="job-title-suggestions"
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
              placeholder="לדוגמה: פקידת הנה״ח"
              className={inputClass}
            />
            <datalist id="job-title-suggestions">
              {JOB_TITLE_SUGGESTIONS.map((t) => (
                <option key={t} value={t} />
              ))}
            </datalist>
          </Field>
          <div className="sm:col-span-2">
            <Field label="אימייל" hint={show("email", email) ?? undefined}>
              <input
                type="email"
                dir="ltr"
                autoComplete="off"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@firm.co.il"
                className={cx(inputClass, "text-left", show("email", email) && "ring-2 ring-red-400")}
              />
            </Field>
          </div>
        </section>

        <section>
          <span className="mb-1.5 block text-xs font-medium text-slate-600">הרשאה</span>
          <div className="grid gap-2 sm:grid-cols-2">
            {(Object.keys(ROLE_LABEL) as UserRole[]).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setRole(r)}
                className={cx(
                  "rounded-xl border p-3 text-start transition",
                  role === r ? "border-brand-500 bg-brand-50 ring-1 ring-brand-500" : "border-slate-200 hover:bg-slate-50",
                )}
              >
                <RoleBadge role={r} />
                <span className="mt-1.5 block text-[11px] leading-snug text-slate-500">{ROLE_HELP[r]}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="grid gap-3 sm:grid-cols-2">
          <Field label="סיסמה ראשונית" hint={show("password", password) ?? "העובד/ת יוכל/תוכל לשנות אותה לאחר ההתחברות"}>
            <PasswordInput value={password} onChange={setPassword} autoComplete="new-password" invalid={!!show("password", password)} />
          </Field>
          <Field label="אימות סיסמה" hint={show("confirm", confirm) ?? undefined}>
            <PasswordInput value={confirm} onChange={setConfirm} autoComplete="new-password" invalid={!!show("confirm", confirm)} />
          </Field>
        </section>

        <section>
          <span className="mb-1 block text-xs font-medium text-slate-600">סטטוס</span>
          <Toggle
            checked={active}
            onChange={setActive}
            label={<span className={cx("font-medium", active ? "text-emerald-700" : "text-red-600")}>{active ? "פעיל — יכול/ה להתחבר מיד" : "הושעה — לא יוכל/תוכל להתחבר"}</span>}
          />
        </section>

        <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
          <Button type="button" variant="ghost" onClick={onClose}>
            ביטול
          </Button>
          <Button type="submit" variant="primary" loading={saving} disabled={touched && hasErrors} icon={<UserPlus className="h-4 w-4" />}>
            הוספת עובד/ת
          </Button>
        </div>
      </form>
    </Modal>
  );
}
