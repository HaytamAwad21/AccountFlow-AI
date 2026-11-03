import { useEffect, useState, type ReactNode } from "react";
import { ClipboardList, FolderOpen, History, KeyRound, LogIn, LogOut, Megaphone, Menu, Moon, Settings as SettingsIcon, Smartphone, Sun, Users, X, Zap } from "lucide-react";
import { useApp } from "./context/AppContext";
import { api } from "./lib/api";
import { cx, DEFAULT_VAT_DEADLINE_DAY, nextDeadlineDate, splitUserName } from "./lib/format";
import { PhoneSimulator } from "./components/PhoneSimulator";
import { LoginPanel } from "./components/LoginPanel";
import { SetupPanel } from "./components/SetupPanel";
import { ChangePasswordModal } from "./components/ChangePasswordModal";
import { DeadlineCalendar } from "./components/DeadlineCalendar";
import { DeadlineDisc } from "./components/PageHeader";
import { Modal, RoleBadge, Spinner, Toaster } from "./components/ui";
import { useTheme } from "./lib/theme";
import { QuickDispatch } from "./pages/QuickDispatch";
import { ChasingBoard } from "./pages/ChasingBoard";
import { BulkTax } from "./pages/BulkTax";
import { ClientsTemplates } from "./pages/ClientsTemplates";
import { Settings } from "./pages/Settings";
import { ActivityLog } from "./pages/ActivityLog";
import { Documents } from "./pages/Documents";

type Tab = "trigger" | "board" | "documents" | "bulk" | "clients" | "settings" | "activity";

/** Sidebar order — "הגדרות" always last. Manager-only tabs are not rendered at all for workers. */
const TABS: { key: Tab; label: string; icon: ReactNode; managerOnly?: boolean }[] = [
  { key: "trigger", label: "שליחת בקשה", icon: <Zap className="h-4 w-4" /> },
  { key: "board", label: "לוח מעקב חי", icon: <ClipboardList className="h-4 w-4" /> },
  { key: "documents", label: "מסמכים מלקוחות", icon: <FolderOpen className="h-4 w-4" /> },
  { key: "bulk", label: "הדיווח מוכן", icon: <Megaphone className="h-4 w-4" /> },
  { key: "clients", label: "לקוחות ותבניות", icon: <Users className="h-4 w-4" /> },
  { key: "activity", label: "יומן פעילות", icon: <History className="h-4 w-4" />, managerOnly: true },
  { key: "settings", label: "הגדרות", icon: <SettingsIcon className="h-4 w-4" /> },
];

const MANAGER_ONLY_TABS = new Set<Tab>(TABS.filter((t) => t.managerOnly).map((t) => t.key));

function readTab(): Tab {
  const h = window.location.hash.replace("#", "") as Tab;
  return TABS.some((t) => t.key === h) ? h : "trigger";
}

/** Full-page login shown whenever there is no valid session; a new office with no users gets the setup form. */
function LoginScreen() {
  // No session here, so the logo's day comes from the public endpoint.
  const [deadlineDay, setDeadlineDay] = useState<number | null>(null);
  const [needsSetup, setNeedsSetup] = useState(false);
  useEffect(() => {
    api
      .deadlineDay()
      .then((r) => setDeadlineDay(r.vat_deadline_day))
      .catch(() => setDeadlineDay(DEFAULT_VAT_DEADLINE_DAY));
    api
      .setupStatus()
      .then((r) => setNeedsSetup(r.needed))
      .catch(() => undefined);
  }, []);
  const day = deadlineDay === null ? null : nextDeadlineDate(deadlineDay).getDate();

  return (
    <div dir="rtl" className="relative flex min-h-screen items-center justify-center overflow-hidden bg-field p-4 @container lg:justify-start lg:ps-[12vw]">
      <DeadlineDisc day={day} className="pointer-events-none absolute -bottom-[14vh] -end-[8vw] hidden h-[78vh] w-[78vh] text-[34vh] lg:grid" />
      <div className={cx("relative w-full bg-surface p-7", needsSetup ? "max-w-lg" : "max-w-md")}>
        <div className="mb-6 flex items-center gap-3">
          <DeadlineDisc day={day} className="h-11 w-11 text-lg" />
          <div>
            <h1 className="font-display text-2xl leading-tight text-ink-900">{needsSetup ? "הקמת המשרד במערכת" : "התחברות למערכת"}</h1>
            <p className="text-xs text-ink-500" dir="ltr">
              AccountFlow AI
            </p>
          </div>
        </div>
        {needsSetup ? <SetupPanel /> : <LoginPanel />}
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
    <div className="space-y-1">
      <button onClick={() => setOpen(true)} className="flex w-full items-center gap-3 px-2 py-2 text-start transition-colors hover:bg-white/10" title="התחברות למערכת כמשתמש אחר">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#fff] text-sm font-bold text-accent-ink">{user.avatar_initials}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-bold text-white">{name}</span>
          <RoleBadge role={user.role} className="text-field-muted" />
        </span>
        <LogIn className="h-4 w-4 shrink-0 text-field-muted" />
      </button>
      <div className="flex gap-1 text-xs">
        <button onClick={() => setChangingPassword(true)} className="flex flex-1 items-center justify-center gap-1 py-1 text-field-muted transition-colors hover:bg-white/10 hover:text-white">
          <KeyRound className="h-3.5 w-3.5" /> שינוי סיסמה
        </button>
        <button onClick={() => logout()} className="flex flex-1 items-center justify-center gap-1 py-1 text-field-muted transition-colors hover:bg-white/10 hover:text-white">
          <LogOut className="h-3.5 w-3.5 -scale-x-100" /> התנתקות
        </button>
      </div>

      <Modal narrow open={open} onClose={() => setOpen(false)} title="התחברות למערכת" subtitle="בחרו משתמש/ת והקלידו את הסיסמה">
        <div className="p-5">{open && <LoginPanel onDone={() => setOpen(false)} />}</div>
      </Modal>
      <ChangePasswordModal open={changingPassword} onClose={() => setChangingPassword(false)} />
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState<Tab>(readTab);
  // Below the lg breakpoint the sidebar is a drawer opened from the top bar.
  const [navOpen, setNavOpen] = useState(false);
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
    setNavOpen(false);
  };

  // A worker never stays on a manager-only tab (e.g. after switching users, or via a typed URL).
  const blocked = !!user && !isManager && MANAGER_ONLY_TABS.has(tab);
  useEffect(() => {
    if (blocked) go("trigger");
  }, [blocked]); // eslint-disable-line react-hooks/exhaustive-deps

  const logoDay = settings ? nextDeadlineDate(settings.vat_deadline_day).getDate() : null;
  const openCount = clients.reduce((n, c) => n + (c.is_active ? c.open_ticket_count : 0), 0);

  if (!authChecked) {
    return (
      <div className="flex h-screen items-center justify-center bg-field">
        <Spinner className="h-8 w-8 text-white" />
      </div>
    );
  }
  if (!user) return <LoginScreen />;

  return (
    <div dir="rtl" className="flex h-screen overflow-hidden bg-canvas text-ink-800">
      {navOpen && <div className="fixed inset-0 z-40 bg-[#0d1533]/70 lg:hidden" onClick={() => setNavOpen(false)} aria-hidden />}
      <nav
        className={cx(
          "fixed inset-y-0 start-0 z-50 flex w-64 shrink-0 flex-col border-e border-white/10 bg-field text-field-muted transition-transform",
          "lg:static lg:z-auto lg:w-56 lg:translate-x-0 2xl:w-64",
          navOpen ? "translate-x-0" : "translate-x-full",
        )}
      >
        <div className="flex items-center gap-2 px-3 pb-5 pt-4">
          <DeadlineDisc day={logoDay} className="h-9 w-9 text-sm" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-end font-display text-base leading-tight text-white" dir="ltr">
              AccountFlow
            </p>
            <p className="text-xs leading-tight text-field-muted">{settings?.firm_name ?? "מעקב לקוחות"}</p>
          </div>
          <button
            type="button"
            onClick={toggleTheme}
            title="מעבר למצב כהה / בהיר"
            aria-label={dark ? "מעבר למצב בהיר" : "מעבר למצב כהה"}
            aria-pressed={dark}
            className="grid h-8 w-8 shrink-0 place-items-center text-field-muted transition-colors hover:bg-white/10 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60"
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          <button type="button" onClick={() => setNavOpen(false)} aria-label="סגירת התפריט" className="grid h-8 w-8 shrink-0 place-items-center text-field-muted hover:bg-white/10 hover:text-white lg:hidden">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-0.5 overflow-y-auto px-2">
          {TABS.filter((t) => !t.managerOnly || isManager).map((t) => (
            <button
              key={t.key}
              onClick={() => go(t.key)}
              aria-current={tab === t.key ? "page" : undefined}
              className={cx(
                "flex w-full items-center gap-3 px-3 py-2.5 text-start text-sm font-semibold transition-colors",
                tab === t.key ? "bg-brand-600 text-white" : "hover:bg-white/10 hover:text-white",
              )}
            >
              {t.icon}
              <span className="min-w-0 flex-1 truncate">{t.label}</span>
              {t.key === "board" && openCount > 0 && <span className="text-sm font-bold">{openCount}</span>}
            </button>
          ))}
        </div>

        <div className="space-y-2 p-2">
          <button onClick={() => setPhoneOpen(!phoneOpen)} className="flex w-full items-center gap-2 px-3 py-2 text-sm font-semibold text-white ring-1 ring-inset ring-white/40 transition-colors hover:bg-white/10">
            <Smartphone className="h-4 w-4" /> {phoneOpen ? "הסתרת" : "הצגת"} הטלפון של הלקוח
          </button>
          <ProfileSwitcher />
        </div>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 bg-field px-3 pt-2 text-white lg:hidden">
          <button type="button" onClick={() => setNavOpen(true)} aria-label="פתיחת התפריט" className="grid h-9 w-9 place-items-center hover:bg-white/10">
            <Menu className="h-5 w-5" />
          </button>
          <DeadlineDisc day={logoDay} className="h-7 w-7 text-xs" />
          <span className="min-w-0 flex-1" />
          <button
            type="button"
            onClick={() => setPhoneOpen(!phoneOpen)}
            aria-label={phoneOpen ? "הסתרת הטלפון של הלקוח" : "הצגת הטלפון של הלקוח"}
            className="grid h-9 w-9 place-items-center hover:bg-white/10"
          >
            <Smartphone className="h-5 w-5" />
          </button>
        </header>
        <main className="@container/main flex min-h-0 flex-1 flex-col overflow-y-auto">
          <DeadlineCalendar />
          <div className="flex-1">
            {tab === "trigger" && <QuickDispatch />}
            {tab === "board" && <ChasingBoard />}
            {tab === "documents" && <Documents />}
            {tab === "bulk" && <BulkTax />}
            {tab === "clients" && <ClientsTemplates />}
            {tab === "activity" && isManager && <ActivityLog />}
            {tab === "settings" && <Settings />}
          </div>
        </main>
      </div>

      <PhoneSimulator />
      <Toaster />
    </div>
  );
}
