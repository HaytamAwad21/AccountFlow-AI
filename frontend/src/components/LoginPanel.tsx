import { useEffect, useRef, useState } from "react";
import { ArrowRight, Check, KeyRound, LogIn } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api, ApiError } from "../lib/api";
import { cx, ROLE_LABEL, splitUserName } from "../lib/format";
import type { LoginUser } from "../lib/types";
import { Button, PasswordInput, RoleBadge, Spinner } from "./ui";

/**
 * Two-step password login: pick a user card, then type that user's password.
 * Used by the full-page login screen and by the sidebar "התחברות למערכת" modal.
 */
export function LoginPanel({ onDone }: { onDone?: () => void }) {
  const { login, user } = useApp();
  const [list, setList] = useState<LoginUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [picked, setPicked] = useState<LoginUser | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const passwordRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .loginUsers()
      .then((rows) => !cancelled && setList(rows))
      .catch((e: Error) => !cancelled && setLoadError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (picked) window.setTimeout(() => passwordRef.current?.focus(), 30);
  }, [picked]);

  const pick = (u: LoginUser) => {
    if (!u.is_active) return;
    setPicked(u);
    setPassword("");
    setError(null);
  };

  const submit = async () => {
    if (!picked || !password || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await login(picked.id, password);
      setPassword("");
      onDone?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "ההתחברות נכשלה");
      setPassword("");
      passwordRef.current?.focus();
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-10">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  if (loadError) {
    return <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">טעינת רשימת המשתמשים נכשלה: {loadError}</p>;
  }

  if (picked) {
    const parts = splitUserName(picked.full_name);
    return (
      <form
        dir="rtl"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <button type="button" onClick={() => setPicked(null)} className="flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-800">
          <ArrowRight className="h-3.5 w-3.5" /> בחירת משתמש אחר
        </button>
        <div className="flex items-center gap-3 rounded-xl border border-brand-500 bg-brand-50 px-4 py-3">
          <span
            className={cx(
              "grid h-11 w-11 shrink-0 place-items-center rounded-full text-sm font-bold",
              picked.role === "MANAGER" ? "bg-amber-100 text-amber-800" : "bg-sky-100 text-sky-800",
            )}
          >
            {picked.avatar_initials}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold text-slate-900">{parts.name}</span>
            <span className="block truncate text-xs text-slate-500">{picked.job_title || parts.title || ROLE_LABEL[picked.role]}</span>
          </span>
          <RoleBadge role={picked.role} />
        </div>
        <label className="block">
          <span className="mb-1 flex items-center gap-1.5 text-xs font-medium text-slate-600">
            <KeyRound className="h-3.5 w-3.5" /> סיסמה
          </span>
          <PasswordInput
            inputRef={passwordRef}
            value={password}
            onChange={(v) => {
              setPassword(v);
              setError(null);
            }}
            invalid={!!error}
          />
        </label>
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-700">{error}</p>}
        <Button type="submit" variant="primary" size="lg" className="w-full" loading={submitting} disabled={!password} icon={<LogIn className="h-5 w-5 -scale-x-100" />}>
          התחברות
        </Button>
      </form>
    );
  }

  return (
    <div dir="rtl" className="space-y-2">
      {list.map((u) => {
        const parts = splitUserName(u.full_name);
        const current = u.id === user?.id;
        return (
          <button
            key={u.id}
            type="button"
            disabled={!u.is_active}
            onClick={() => pick(u)}
            className={cx(
              "flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-start transition",
              current ? "border-brand-500 bg-brand-50 ring-1 ring-brand-500" : "border-slate-200 hover:border-slate-300 hover:bg-slate-50",
              !u.is_active && "cursor-not-allowed opacity-50 hover:bg-white",
            )}
          >
            <span
              className={cx(
                "grid h-10 w-10 shrink-0 place-items-center rounded-full text-sm font-bold",
                u.role === "MANAGER" ? "bg-amber-100 text-amber-800" : "bg-sky-100 text-sky-800",
              )}
            >
              {u.avatar_initials}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold text-slate-900">{parts.name}</span>
              <span className="block truncate text-xs text-slate-500">{u.job_title || parts.title || ROLE_LABEL[u.role]}</span>
            </span>
            <span className="flex shrink-0 flex-col items-end gap-1">
              <RoleBadge role={u.role} />
              {!u.is_active && <span className="text-[10.5px] font-semibold text-red-600">הושעה</span>}
              {current && (
                <span className="flex items-center gap-1 text-[10.5px] font-semibold text-brand-600">
                  <Check className="h-3 w-3" /> מחובר/ת כעת
                </span>
              )}
            </span>
          </button>
        );
      })}
      <p className="pt-2 text-[11px] leading-snug text-slate-500">בחרו את המשתמש/ת שלכם והקלידו את הסיסמה האישית. כל פעולה במערכת נרשמת ביומן הפעילות.</p>
    </div>
  );
}
