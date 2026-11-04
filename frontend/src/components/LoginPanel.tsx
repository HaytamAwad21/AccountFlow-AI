import { useEffect, useRef, useState } from "react";
import { ArrowRight, Check, KeyRound, LogIn, Smartphone } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api, ApiError } from "../lib/api";
import { cx, ROLE_LABEL, splitUserName } from "../lib/format";
import type { LoginUser } from "../lib/types";
import { Button, inputClass, PasswordInput, RoleBadge, Spinner } from "./ui";

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
  // Two-step login: after the right password, the server asks for the 6-digit code from the phone app.
  const [needCode, setNeedCode] = useState(false);
  const [code, setCode] = useState("");
  const passwordRef = useRef<HTMLInputElement>(null);
  const codeRef = useRef<HTMLInputElement>(null);

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

  const pick = (u: LoginUser | null) => {
    setPicked(u);
    setPassword("");
    setError(null);
    setNeedCode(false);
    setCode("");
  };

  const submit = async () => {
    if (!picked || !password || submitting || (needCode && code.length !== 6)) return;
    setSubmitting(true);
    setError(null);
    try {
      await login(picked.id, password, needCode ? code : undefined);
      setPassword("");
      setCode("");
      onDone?.();
    } catch (e) {
      const reason = e instanceof ApiError ? e.code : undefined;
      if (reason === "two_factor_required" || reason === "two_factor_invalid") {
        // The password was right: keep it and ask for (another) code.
        setNeedCode(true);
        setCode("");
        if (reason === "two_factor_invalid") setError(e instanceof Error ? e.message : null);
        window.setTimeout(() => codeRef.current?.focus(), 30);
      } else {
        setError(e instanceof ApiError ? e.message : "ההתחברות נכשלה");
        setPassword("");
        setNeedCode(false);
        passwordRef.current?.focus();
      }
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
        <button type="button" onClick={() => pick(null)} className="flex items-center gap-1 text-xs font-medium text-ink-500 hover:text-ink-800">
          <ArrowRight className="h-3.5 w-3.5" /> בחירת משתמש אחר
        </button>
        <div className="flex items-center gap-3 rounded-xl border border-brand-500 bg-brand-50 px-4 py-3">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-brand-600 text-sm font-bold text-white">{picked.avatar_initials}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold text-ink-900">{parts.name}</span>
            <span className="block truncate text-xs text-ink-500">{picked.job_title || parts.title || ROLE_LABEL[picked.role]}</span>
          </span>
          <RoleBadge role={picked.role} />
        </div>
        <label className="block">
          <span className="mb-1 flex items-center gap-1.5 text-xs font-medium text-ink-600">
            <KeyRound className="h-3.5 w-3.5" /> סיסמה
          </span>
          <PasswordInput
            inputRef={passwordRef}
            value={password}
            onChange={(v) => {
              setPassword(v);
              setError(null);
            }}
            invalid={!!error && !needCode}
          />
        </label>
        {needCode && (
          <label className="block">
            <span className="mb-1 flex items-center gap-1.5 text-xs font-medium text-ink-600">
              <Smartphone className="h-3.5 w-3.5" /> קוד מאפליקציית האימות
            </span>
            <input
              ref={codeRef}
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
              aria-describedby="code-hint"
              className={cx(inputClass, "text-center text-lg tracking-[0.4em] tabular-nums", error && "ring-2 ring-red-400")}
            />
            <span id="code-hint" className="mt-1 block text-xs text-ink-500">
              פתחו את Google Authenticator או Microsoft Authenticator בטלפון והקלידו את הקוד שמופיע עכשיו.
            </span>
          </label>
        )}
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-700">{error}</p>}
        <Button
          type="submit"
          variant="accent"
          size="lg"
          className="w-full"
          loading={submitting}
          disabled={!password || (needCode && code.length !== 6)}
          icon={<LogIn className="h-5 w-5 -scale-x-100" />}
        >
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
            onClick={() => pick(u)}
            className={cx(
              "flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-start transition",
              current ? "border-brand-500 bg-brand-50 ring-1 ring-brand-500" : "border-ink-200 hover:border-ink-300 hover:bg-ink-50",
            )}
          >
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-brand-600 text-sm font-bold text-white">{u.avatar_initials}</span>
            <span className="min-w-0 flex-1">
              <span className="block break-words text-sm font-bold text-ink-900">{parts.name}</span>
              <span className="block break-words text-xs text-ink-500">{u.job_title || parts.title || ROLE_LABEL[u.role]}</span>
            </span>
            <span className="flex shrink-0 flex-col items-end gap-1">
              <RoleBadge role={u.role} />
              {current && (
                <span className="flex items-center gap-1 text-xs font-semibold text-link">
                  <Check className="h-3 w-3" /> מחובר/ת כעת
                </span>
              )}
            </span>
          </button>
        );
      })}
      <p className="pt-2 text-xs leading-snug text-ink-500">בחרו את המשתמש/ת שלכם והקלידו את הסיסמה האישית. כל פעולה במערכת נרשמת ביומן הפעילות.</p>
    </div>
  );
}
