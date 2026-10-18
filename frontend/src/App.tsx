import { useEffect, useState, type ReactNode } from "react";
import { Bot, ClipboardList, History, KeyRound, LogIn, LogOut, Megaphone, Moon, Settings as SettingsIcon, Smartphone, Sun, Users, Zap } from "lucide-react";
import { useApp } from "./context/AppContext";
import { cx, splitUserName } from "./lib/format";
import { PhoneSimulator } from "./components/PhoneSimulator";
import { LoginPanel } from "./components/LoginPanel";
import { ChangePasswordModal } from "./components/ChangePasswordModal";
import { Modal, RoleBadge, Spinner, Toaster } from "./components/ui";
import { useTheme } from "./lib/theme";
import { QuickDispatch } from "./pages/QuickDispatch";
import { ChasingBoard } from "./pages/ChasingBoard";
import { BulkTax } from "./pages/BulkTax";
import { ClientsTemplates } from "./pages/ClientsTemplates";
import { Settings } from "./pages/Settings";
import { ActivityLog } from "./pages/ActivityLog";

type Tab = "trigger" | "board" | "bulk" | "clients" | "settings" | "activity";

/** Sidebar order — "הגדרות" always last. Manager-only tabs are not rendered at all for workers. */
const TABS: { key: Tab; label: string; sub: string; icon: ReactNode; managerOnly?: boolean }[] = [
  { key: "trigger", label: "שליחת בקשה", sub: "עמדת שליחה מהירה", icon: <Zap className="h-4 w-4" /> },
  { key: "board", label: "לוח מעקב חי", sub: "מצב הפניות והבוט", icon: <ClipboardList className="h-4 w-4" /> },
  { key: "bulk", label: "הדיווח מוכן", sub: "הודעות מס בתפוצה", icon: <Megaphone className="h-4 w-4" /> },
  { key: "clients", label: "לקוחות ותבניות", sub: "לקוחות ונוסחי הודעות", icon: <Users className="h-4 w-4" /> },
  { key: "activity", label: "יומן פעילות", sub: "פעולות צוות המשרד", icon: <History className="h-4 w-4" />, managerOnly: true },
  { key: "settings", label: "הגדרות", sub: "הגדרות המשרד", icon: <SettingsIcon className="h-4 w-4" />, managerOnly: true },
];

const MANAGER_ONLY_TABS = new Set<Tab>(TABS.filter((t) => t.managerOnly).map((t) => t.key));

function readTab(): Tab {
  const h = window.location.hash.replace("#", "") as Tab;
  return TABS.some((t) => t.key === h) ? h : "trigger";
}

/** Full-page login shown whenever there is no valid session. */
function LoginScreen() {
  return (
    <div dir="rtl" className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-950 via-slate-900 to-brand-900 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <div className="mb-5 flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-brand-600 text-white shadow-lg shadow-brand-600/30">
            <Bot className="h-6 w-6" />
          </span>
          <div>
            <h1 className="text-xl font-bold text-slate-900">התחברות למערכת</h1>
            <p className="text-xs text-slate-500" dir="ltr">
              AccountFlow AI
            </p>
          </div>
        </div>
        <LoginPanel />
      </div>
      <Toaster />
    </div>
  );
}

/** Sidebar profile button: shows who is logged in; opens the "התחברות למערכת" modal (password required). */
function ProfileSwitcher() {
  const { user, logout } = useApp();
  const [open, setOpen] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);

  if (!user) return null;
  const { name } = splitUserName(user.full_name);
  return (
    <div className="space-y-1.5">
      <button
        onClick={() => setOpen(true)}
        className={cx(
          "flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-start ring-1 transition",
          user.role === "MANAGER" ? "bg-amber-400/10 ring-amber-400/40 hover:bg-amber-400/20" : "bg-sky-400/10 ring-sky-400/40 hover:bg-sky-400/20",
        )}
        title="התחברות למערכת כמשתמש אחר"
      >
        <span
          className={cx(
            "grid h-9 w-9 shrink-0 place-items-center rounded-full text-sm font-bold",
            user.role === "MANAGER" ? "bg-amber-400 text-amber-950" : "bg-sky-400 text-sky-950",
          )}
        >
          {user.avatar_initials}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-white">{name}</span>
          <span className="mt-0.5 block">
            <RoleBadge role={user.role} />
          </span>
        </span>
        <LogIn className="h-4 w-4 shrink-0 text-slate-400" />
      </button>
      <div className="flex gap-1 text-[11px]">
        <button onClick={() => setChangingPassword(true)} className="flex flex-1 items-center justify-center gap-1 rounded-md py-1 text-slate-400 hover:bg-white/5 hover:text-white">
          <KeyRound className="h-3.5 w-3.5" /> שינוי סיסמה
        </button>
        <button onClick={() => logout()} className="flex flex-1 items-center justify-center gap-1 rounded-md py-1 text-slate-400 hover:bg-white/5 hover:text-white">
          <LogOut className="h-3.5 w-3.5 -scale-x-100" /> התנתקות
        </button>
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="התחברות למערכת" subtitle="בחרו משתמש/ת והקלידו את הסיסמה">
        <div className="p-5">{open && <LoginPanel onDone={() => setOpen(false)} />}</div>
      </Modal>
      <ChangePasswordModal open={changingPassword} onClose={() => setChangingPassword(false)} />
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState<Tab>(readTab);
  const { settings, phoneOpen, setPhoneOpen, clients, user, isManager, authChecked } = useApp();
  const { dark, toggle: toggleTheme } = useTheme();

  useEffect(() => {
    const onHash = () => setTab(readTab());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (t: Tab) => {
    window.location.hash = t;
    setTab(t);
  };

  // A worker never stays on a manager-only tab (e.g. after switching users, or via a typed URL).
  const blocked = !!user && !isManager && MANAGER_ONLY_TABS.has(tab);
  useEffect(() => {
    if (blocked) go("trigger");
  }, [blocked]); // eslint-disable-line react-hooks/exhaustive-deps

  const openCount = clients.reduce((n, c) => n + (c.is_active ? c.open_ticket_count : 0), 0);

  if (!authChecked) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950">
        <Spinner className="h-8 w-8 text-white" />
      </div>
    );
  }
  if (!user) return <LoginScreen />;

  return (
    <div dir="rtl" className="flex h-screen overflow-hidden bg-slate-50 text-slate-900">
      <nav className="flex w-64 shrink-0 flex-col border-e border-slate-200 bg-slate-950 text-slate-300">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <button
            type="button"
            onClick={toggleTheme}
            title="מעבר למצב כהה / בהיר"
            aria-label={dark ? "מעבר למצב בהיר" : "מעבר למצב כהה"}
            aria-pressed={dark}
            className="group relative grid h-9 w-9 place-items-center rounded-xl bg-brand-600 text-white shadow-lg shadow-brand-600/30 transition hover:bg-brand-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60"
          >
            <Bot className="h-5 w-5" />
            <span className="absolute -bottom-1 -start-1 grid h-4 w-4 place-items-center rounded-full bg-slate-950 text-amber-300 ring-1 ring-white/10">
              {dark ? <Sun className="h-2.5 w-2.5" /> : <Moon className="h-2.5 w-2.5" />}
            </span>
          </button>
          <div className="min-w-0">
            <p className="text-sm font-bold text-white" dir="ltr">
              AccountFlow AI
            </p>
            <p className="truncate text-[11px] text-slate-500">{settings?.firm_name ?? "מעקב לקוחות"}</p>
          </div>
        </div>

        <div className="flex-1 space-y-1 overflow-y-auto px-3">
          {TABS.filter((t) => !t.managerOnly || isManager).map((t) => (
            <button
              key={t.key}
              onClick={() => go(t.key)}
              className={cx(
                "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-start transition",
                tab === t.key ? "bg-white/10 text-white" : "hover:bg-white/5 hover:text-white",
              )}
            >
              <span className={cx("grid h-7 w-7 place-items-center rounded-md", tab === t.key ? "bg-brand-600 text-white" : "bg-white/5")}>{t.icon}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{t.label}</span>
                <span className="block truncate text-[11px] text-slate-500">{t.sub}</span>
              </span>
              {t.key === "board" && openCount > 0 && (
                <span className="rounded-full bg-amber-500/20 px-1.5 text-[10px] font-semibold text-amber-300">{openCount}</span>
              )}
            </button>
          ))}
        </div>

        <div className="space-y-3 border-t border-white/10 p-3 text-[11px]">
          <button
            onClick={() => setPhoneOpen(!phoneOpen)}
            className="flex w-full items-center gap-2 rounded-lg bg-wa-teal/20 px-3 py-2 font-medium text-emerald-300 hover:bg-wa-teal/30"
          >
            <Smartphone className="h-4 w-4" /> {phoneOpen ? "הסתרת" : "הצגת"} הטלפון של הלקוח
          </button>
          <ProfileSwitcher />
        </div>
      </nav>

      <main className="min-w-0 flex-1 overflow-y-auto">
        {tab === "trigger" && <QuickDispatch />}
        {tab === "board" && <ChasingBoard />}
        {tab === "bulk" && <BulkTax />}
        {tab === "clients" && <ClientsTemplates />}
        {tab === "activity" && isManager && <ActivityLog />}
        {tab === "settings" && isManager && <Settings />}
      </main>

      <PhoneSimulator />
      <Toaster />
    </div>
  );
}
