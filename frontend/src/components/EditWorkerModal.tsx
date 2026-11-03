import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import type { User, UserRole } from "../lib/types";
import { Button, Field, inputClass, Modal, PasswordInput, RoleBadge, Toggle } from "./ui";
import { EMAIL_RE, JobTitleInput, RolePicker } from "./WorkerFields";

/** Manager-only editor for an office worker: every field (name, job title, e-mail, role, active / suspended
 *  status) and a password reset (PUT /api/users/{id}). */
export function EditWorkerModal({ worker, onClose }: { worker: User | null; onClose: () => void }) {
  const { refreshUsers, toast, user } = useApp();
  const [fullName, setFullName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserRole>("WORKER");
  const [active, setActive] = useState(true);
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!worker) return;
    setFullName(worker.full_name);
    setJobTitle(worker.job_title);
    setEmail(worker.email);
    setRole(worker.role);
    setActive(worker.is_active);
    setPassword("");
  }, [worker]);

  const nameInvalid = fullName.trim().length < 2;
  const emailInvalid = !EMAIL_RE.test(email.trim());
  const emailChanged = !!worker && email.trim().toLowerCase() !== worker.email;
  const passwordInvalid = password.length > 0 && password.length < 6;
  const dirty =
    !!worker &&
    (fullName.trim() !== worker.full_name ||
      jobTitle.trim() !== worker.job_title ||
      emailChanged ||
      role !== worker.role ||
      active !== worker.is_active ||
      password.length > 0);
  const editingSelf = worker?.id === user?.id;

  const save = async () => {
    if (!worker || nameInvalid || emailInvalid || passwordInvalid || !dirty) return;
    setSaving(true);
    try {
      const body: Partial<Pick<User, "full_name" | "job_title" | "email" | "role" | "is_active">> & { password?: string } = {};
      if (fullName.trim() !== worker.full_name) body.full_name = fullName.trim();
      if (jobTitle.trim() !== worker.job_title) body.job_title = jobTitle.trim();
      if (emailChanged) body.email = email.trim().toLowerCase();
      if (role !== worker.role) body.role = role;
      if (active !== worker.is_active) body.is_active = active;
      if (password) body.password = password;
      await api.updateUser(worker.id, body);
      await refreshUsers();
      toast({
        tone: "success",
        title: "פרטי העובד/ת עודכנו",
        body: password ? `${fullName.trim()} · הסיסמה אופסה והחיבורים הפתוחים נותקו` : fullName.trim(),
      });
      onClose();
    } catch (e) {
      toast({ tone: "error", title: "עדכון העובד/ת נכשל", body: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={worker !== null} onClose={onClose} title="עריכת עובד" subtitle={worker?.email}>
      {worker && (
        <form
          dir="rtl"
          className="space-y-4 p-6"
          onSubmit={(e) => {
            e.preventDefault();
            save();
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="שם מלא" hint={nameInvalid ? "נדרשים לפחות 2 תווים" : undefined}>
              <input
                autoFocus
                dir="auto"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="לדוגמה: יעל לוי"
                className={cx(inputClass, nameInvalid && "ring-2 ring-red-400")}
              />
            </Field>
            <Field label="תפקיד במשרד" hint="מוצג מתחת לשם (רשות)">
              <JobTitleInput value={jobTitle} onChange={setJobTitle} />
            </Field>
            <div className="sm:col-span-2">
              <Field label="אימייל" hint={emailInvalid ? "כתובת אימייל לא תקינה" : undefined}>
                <input
                  type="email"
                  dir="ltr"
                  autoComplete="off"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@firm.co.il"
                  className={cx(inputClass, "text-left", emailInvalid && "ring-2 ring-red-400")}
                />
              </Field>
            </div>
          </div>

          <div>
            <span className="mb-1.5 block text-xs font-bold text-ink-700">הרשאה</span>
            <RolePicker value={role} onChange={setRole} />
          </div>

          <div>
            <span className="mb-1 block text-xs font-medium text-ink-600">סטטוס</span>
            <Toggle
              checked={active}
              onChange={setActive}
              label={<span className={cx("font-medium", active ? "text-emerald-700" : "text-red-600")}>{active ? "פעיל" : "הושעה"}</span>}
            />
            {!active && <p className="mt-1 text-xs text-ink-500">עובד/ת מושעה לא יוכל/תוכל להתחבר למערכת ולבצע פעולות.</p>}
          </div>

          <Field label="סיסמה חדשה (אופציונלי)" hint={passwordInvalid ? "לפחות 6 תווים" : "השאירו ריק כדי לא לשנות. איפוס סיסמה מנתק את העובד/ת מכל החיבורים."}>
            <PasswordInput value={password} onChange={setPassword} autoComplete="new-password" placeholder="" invalid={passwordInvalid} />
          </Field>

          {editingSelf && (role !== "MANAGER" || !active) && (
            <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
              שימו לב: אתם עורכים את המשתמש המחובר. לאחר השמירה ייתכן שתאבדו את הרשאות המנהל.
            </p>
          )}

          <div className="flex items-center justify-between gap-2 border-t border-ink-100 pt-4">
            <span className="flex items-center gap-2 text-xs text-ink-500">
              תצוגה: <RoleBadge role={role} />
            </span>
            <span className="flex gap-2">
              <Button type="button" variant="ghost" onClick={onClose}>
                ביטול
              </Button>
              <Button type="submit" variant="accent" loading={saving} disabled={!dirty || nameInvalid || emailInvalid || passwordInvalid} icon={<Save className="h-4 w-4" />}>
                שמירה
              </Button>
            </span>
          </div>
        </form>
      )}
    </Modal>
  );
}
