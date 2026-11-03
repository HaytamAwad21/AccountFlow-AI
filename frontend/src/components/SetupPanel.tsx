import { useState } from "react";
import { Building2 } from "lucide-react";
import { useApp } from "../context/AppContext";
import { ApiError } from "../lib/api";
import { cx } from "../lib/format";
import { Button, Field, inputClass, PasswordInput } from "./ui";
import { EMAIL_RE, JobTitleInput } from "./WorkerFields";

/**
 * First run of a new office (no users yet): the office name and its first manager. The setup code
 * comes from the server's settings file, so only whoever installed the server can claim the office.
 */
export function SetupPanel() {
  const { setupOffice } = useApp();
  const [setupCode, setSetupCode] = useState("");
  const [firmName, setFirmName] = useState("");
  const [fullName, setFullName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [touched, setTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const errors = {
    setupCode: !setupCode.trim() ? "יש להזין את קוד ההקמה" : null,
    firmName: firmName.trim().length < 2 ? "נדרשים לפחות 2 תווים" : null,
    fullName: fullName.trim().length < 2 ? "נדרשים לפחות 2 תווים" : null,
    email: !EMAIL_RE.test(email.trim()) ? "כתובת אימייל לא תקינה" : null,
    password: password.length < 6 ? "לפחות 6 תווים" : null,
    confirm: confirm !== password ? "אימות הסיסמה אינו תואם" : null,
  };
  const hasErrors = Object.values(errors).some(Boolean);
  const show = (key: keyof typeof errors, value: string) => (touched || value ? errors[key] : null);

  const save = async () => {
    setTouched(true);
    setError(null);
    if (hasErrors) return;
    setSaving(true);
    try {
      await setupOffice({
        setup_code: setupCode.trim(),
        firm_name: firmName.trim(),
        full_name: fullName.trim(),
        job_title: jobTitle.trim(),
        email: email.trim().toLowerCase(),
        password,
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "הקמת המשרד נכשלה");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      dir="rtl"
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      <p className="text-sm leading-relaxed text-ink-600">
        זו הפעם הראשונה שהמערכת עולה בשרת הזה. הזינו את פרטי המשרד ואת פרטי המנהל/ת הראשון/ה. את שאר העובדים מוסיפים אחר כך בהגדרות.
      </p>

      <Field label="קוד הקמה" hint={show("setupCode", setupCode) ?? "מופיע בקובץ ההגדרות של השרת (SETUP_CODE)"}>
        <input
          autoFocus
          dir="ltr"
          autoComplete="off"
          spellCheck={false}
          value={setupCode}
          onChange={(e) => setSetupCode(e.target.value)}
          className={cx(inputClass, "text-left font-mono", show("setupCode", setupCode) && "ring-2 ring-red-400")}
        />
      </Field>

      <Field label="שם המשרד" hint={show("firmName", firmName) ?? "מופיע בהודעות הוואטסאפ ללקוחות"}>
        <input
          dir="auto"
          value={firmName}
          onChange={(e) => setFirmName(e.target.value)}
          placeholder="לדוגמה: לוי ושות׳ - רואי חשבון"
          className={cx(inputClass, show("firmName", firmName) && "ring-2 ring-red-400")}
        />
      </Field>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="שם מלא" hint={show("fullName", fullName) ?? undefined}>
          <input
            dir="auto"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="לדוגמה: רונית לוי"
            className={cx(inputClass, show("fullName", fullName) && "ring-2 ring-red-400")}
          />
        </Field>
        <Field label="תפקיד במשרד" hint="רשות">
          <JobTitleInput value={jobTitle} onChange={setJobTitle} />
        </Field>
      </div>

      <Field label="אימייל" hint={show("email", email) ?? undefined}>
        <input
          type="email"
          dir="ltr"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="name@firm.co.il"
          className={cx(inputClass, "text-left", show("email", email) && "ring-2 ring-red-400")}
        />
      </Field>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="סיסמה" hint={show("password", password) ?? "לפחות 6 תווים"}>
          <PasswordInput value={password} onChange={setPassword} autoComplete="new-password" invalid={!!show("password", password)} />
        </Field>
        <Field label="אימות סיסמה" hint={show("confirm", confirm) ?? undefined}>
          <PasswordInput value={confirm} onChange={setConfirm} autoComplete="new-password" invalid={!!show("confirm", confirm)} />
        </Field>
      </div>

      {error && (
        <p role="alert" className="bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
          {error}
        </p>
      )}
      <Button
        type="submit"
        variant="accent"
        size="lg"
        className="w-full"
        loading={saving}
        disabled={touched && hasErrors}
        icon={<Building2 className="h-5 w-5" />}
      >
        הקמת המשרד והתחברות
      </Button>
    </form>
  );
}
