import { useEffect, useState } from "react";
import { ShieldCheck, ShieldOff } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import { Button, Field, inputClass, Modal, PasswordInput, Spinner } from "./ui";

type Setup = { secret: string; qr: string };

/**
 * The logged-in user's two-step login: scan a QR code with an authenticator app on the phone and confirm one
 * code to switch it on; switch it off with the password. A worker who lost the phone asks a manager to reset it.
 */
export function TwoFactorModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user, toast, refreshUsers } = useApp();
  const [setup, setSetup] = useState<Setup | null>(null);
  const [starting, setStarting] = useState(false);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const enabled = !!user?.two_factor_enabled;

  useEffect(() => {
    if (!open) return;
    setSetup(null);
    setCode("");
    setPassword("");
    setError(null);
  }, [open]);

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      setSetup(await api.twoFactorSetup());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  };

  const run = async (fn: () => Promise<unknown>, done: string) => {
    setSaving(true);
    setError(null);
    try {
      await fn();
      await refreshUsers();
      toast({ tone: "success", title: done });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="אימות דו-שלבי" subtitle="כניסה עם סיסמה וקוד מהטלפון">
      <div dir="rtl" className="space-y-4 p-6 text-sm">
        {enabled ? (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (password) run(() => api.twoFactorDisable(password), "האימות הדו-שלבי כובה");
            }}
          >
            <p className="flex items-center gap-2 font-bold text-emerald-700">
              <ShieldCheck className="h-5 w-5" /> פעיל: כל כניסה דורשת את הסיסמה ואת הקוד מהטלפון.
            </p>
            <p className="text-ink-600">כדי לעבור לטלפון אחר, כבו את האימות והפעילו אותו מחדש עם הטלפון החדש.</p>
            <Field label="הסיסמה שלך, כדי לכבות">
              <PasswordInput value={password} onChange={setPassword} autoComplete="current-password" />
            </Field>
            {error && <p className="bg-red-50 px-3 py-2 text-red-700">{error}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={onClose}>
                סגירה
              </Button>
              <Button type="submit" variant="danger" loading={saving} disabled={!password} icon={<ShieldOff className="h-4 w-4" />}>
                כיבוי האימות הדו-שלבי
              </Button>
            </div>
          </form>
        ) : !setup ? (
          <div className="space-y-4">
            <p className="text-ink-700">
              עם אימות דו-שלבי, סיסמה שנגנבה לא מספיקה כדי להיכנס: בכל כניסה מקלידים גם קוד בן 6 ספרות שמתחלף כל 30 שניות באפליקציה בטלפון.
            </p>
            <p className="text-ink-600">צריך אפליקציה חינמית: Google Authenticator או Microsoft Authenticator.</p>
            {error && <p className="bg-red-50 px-3 py-2 text-red-700">{error}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={onClose}>
                לא עכשיו
              </Button>
              <Button variant="accent" loading={starting} onClick={start} icon={<ShieldCheck className="h-4 w-4" />}>
                הפעלה
              </Button>
            </div>
          </div>
        ) : (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (code.length === 6) run(() => api.twoFactorEnable(code), "האימות הדו-שלבי הופעל");
            }}
          >
            <ol className="list-inside list-decimal space-y-1 text-ink-700">
              <li>פתחו את אפליקציית האימות בטלפון והוסיפו חשבון.</li>
              <li>סרקו את הקוד שבתמונה.</li>
              <li>הקלידו כאן את 6 הספרות שמופיעות באפליקציה.</li>
            </ol>
            <div className="flex flex-wrap items-center gap-4">
              {setup.qr ? (
                <img src={setup.qr} alt="קוד QR לאפליקציית האימות" className="h-44 w-44 border border-ink-300 bg-[#fff] p-1" />
              ) : (
                <Spinner />
              )}
              <div className="min-w-0 flex-1 space-y-1">
                <p className="text-xs text-ink-500">אי אפשר לסרוק? הקלידו באפליקציה את המפתח:</p>
                <p dir="ltr" className="select-all break-all font-mono text-sm text-ink-900">
                  {setup.secret.match(/.{1,4}/g)?.join(" ")}
                </p>
              </div>
            </div>
            <Field label="קוד מהאפליקציה">
              <input
                autoFocus
                dir="ltr"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={(e) => {
                  setCode(e.target.value.replace(/\D/g, "").slice(0, 6));
                  setError(null);
                }}
                placeholder="000000"
                className={cx(inputClass, "text-center text-lg tracking-[0.4em] tabular-nums", error && "ring-2 ring-red-400")}
              />
            </Field>
            {error && <p className="bg-red-50 px-3 py-2 text-red-700">{error}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={onClose}>
                ביטול
              </Button>
              <Button type="submit" variant="accent" loading={saving} disabled={code.length !== 6} icon={<ShieldCheck className="h-4 w-4" />}>
                אישור והפעלה
              </Button>
            </div>
          </form>
        )}
      </div>
    </Modal>
  );
}
