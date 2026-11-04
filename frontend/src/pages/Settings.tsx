import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Pencil, Save, ShieldCheck, UserPlus, Users } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api } from "../lib/api";
import { cx, formatNumber, fullDateTime, splitUserName } from "../lib/format";
import type { EditableSettings, User } from "../lib/types";
import { EditWorkerModal } from "../components/EditWorkerModal";
import { AddWorkerModal } from "../components/AddWorkerModal";
import { PageHeader } from "../components/PageHeader";
import { Button, Card, Field, inputClass, RoleBadge, Toggle } from "../components/ui";

type NumericKey = "vat_rate" | "allocation_number_threshold_nis" | "vat_deadline_day" | "reminder_interval_hours" | "max_reminders";

const LIMITS: Record<NumericKey, { min: number; max: number; step: number; label: string }> = {
  vat_rate: { min: 0, max: 50, step: 0.5, label: "שיעור מע״מ" },
  allocation_number_threshold_nis: { min: 0, max: 10_000_000, step: 500, label: "סף מספר הקצאה" },
  vat_deadline_day: { min: 1, max: 31, step: 1, label: "מועד דיווח מע״מ" },
  reminder_interval_hours: { min: 1, max: 720, step: 1, label: "מרווח תזכורות" },
  max_reminders: { min: 1, max: 10, step: 1, label: "מספר תזכורות מקסימלי" },
};

/** A number inside a Hebrew sentence: formatted with Intl he-IL and isolated left-to-right
 *  so digits, separators, "%" and "₪" never reorder the surrounding RTL text. */
function Num({ value, prefix = "", suffix = "", className }: { value: number; prefix?: string; suffix?: string; className?: string }) {
  return (
    <span dir="ltr" className={cx("inline-block font-semibold tabular-nums text-ink-900", className)}>
      {prefix}
      {formatNumber(value)}
      {suffix}
    </span>
  );
}

function Section({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <Card className="p-5">
      <div className="mb-4">
        <h2 className="font-display text-lg leading-tight text-ink-900">{title}</h2>
        <p className="mt-0.5 text-xs text-ink-500">{hint}</p>
      </div>
      {children}
    </Card>
  );
}

function NumberInput({
  value,
  onChange,
  suffix,
  limits,
  disabled = false,
}: {
  value: number;
  onChange: (v: number) => void;
  suffix: string;
  limits: { min: number; max: number; step: number };
  disabled?: boolean;
}) {
  return (
    <div className="relative">
      <input
        type="number"
        dir="ltr"
        min={limits.min}
        max={limits.max}
        step={limits.step}
        value={Number.isFinite(value) ? value : ""}
        onChange={(e) => onChange(e.target.value === "" ? NaN : Number(e.target.value))}
        disabled={disabled}
        readOnly={disabled}
        className={cx(inputClass, "pl-14 pr-3 text-right tabular-nums", disabled && "cursor-not-allowed bg-ink-50 text-ink-600")}
      />
      {/* physical sides: the LTR number sits on the right, the unit on the left — never overlapping */}
      <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-xs text-ink-400">{suffix}</span>
    </div>
  );
}

export function Settings() {
  const { settings, refreshSettings, users, user, isManager, toast } = useApp();
  const [draft, setDraft] = useState<EditableSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [addingWorker, setAddingWorker] = useState(false);
  const [editingWorker, setEditingWorker] = useState<User | null>(null);

  useEffect(() => {
    if (!settings) return;
    setDraft({
      firm_name: settings.firm_name,
      vat_rate: settings.vat_rate,
      allocation_number_threshold_nis: settings.allocation_number_threshold_nis,
      reminder_interval_hours: settings.reminder_interval_hours,
      max_reminders: settings.max_reminders,
      vat_deadline_day: settings.vat_deadline_day,
      auto_approve_verified: settings.auto_approve_verified,
    });
  }, [settings]);

  const invalid = useMemo(() => {
    if (!draft) return [] as string[];
    const errs: string[] = [];
    (Object.keys(LIMITS) as NumericKey[]).forEach((k) => {
      const v = draft[k];
      const l = LIMITS[k];
      if (!Number.isFinite(v) || v < l.min || v > l.max) errs.push(`${l.label}: ${l.min}–${l.max.toLocaleString("he-IL")}`);
    });
    if (draft.firm_name.trim().length < 2) errs.push("שם המשרד: לפחות 2 תווים");
    return errs;
  }, [draft]);

  const dirty = useMemo(() => {
    if (!draft || !settings) return false;
    return (Object.keys(draft) as (keyof EditableSettings)[]).some((k) => draft[k] !== settings[k]);
  }, [draft, settings]);

  // Workers see the firm's current rules read-only: disabled inputs, no save / cancel and
  // no team management. Managers edit everything.
  const readOnly = !isManager;
  if (!settings || !draft) {
    return <div className="p-6 text-sm text-ink-500">טוען הגדרות…</div>;
  }

  const set = <K extends keyof EditableSettings>(k: K, v: EditableSettings[K]) => setDraft((d) => (d ? { ...d, [k]: v } : d));

  const save = async () => {
    if (readOnly || invalid.length) return;
    setSaving(true);
    try {
      const body: Partial<EditableSettings> = {};
      (Object.keys(draft) as (keyof EditableSettings)[]).forEach((k) => {
        if (draft[k] !== settings[k]) (body as Record<string, unknown>)[k] = draft[k];
      });
      await api.updateSettings(body);
      await refreshSettings();
      toast({
        tone: "success",
        title: "הגדרות המשרד נשמרו",
        body: body.vat_rate !== undefined ? `שיעור המע״מ עודכן ל-${body.vat_rate}% — בדיקות ה-OCR יחושבו מעכשיו לפי השיעור החדש.` : undefined,
      });
    } catch (e) {
      toast({ tone: "error", title: "שמירת ההגדרות נכשלה", body: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  };



  // Live example, recalculated on every keystroke from the (unsaved) draft values:
  // an invoice exactly at the allocation threshold, its VAT and its total including VAT.
  const exampleRate = Number.isFinite(draft.vat_rate) ? draft.vat_rate : 0;
  const exampleThreshold = Number.isFinite(draft.allocation_number_threshold_nis) ? draft.allocation_number_threshold_nis : 0;
  const exampleVat = (exampleThreshold * exampleRate) / 100;
  const exampleTotal = exampleThreshold * (1 + exampleRate / 100);

  return (
    <>
      <PageHeader
        title="הגדרות המשרד"
        hint={
          readOnly
            ? "הכללים שהמשרד מפעיל כרגע על בדיקות Vision AI, על קצב התזכורות של הבוט ועל ההודעות בוואטסאפ. רק מנהל/ת המשרד יכול/ה לשנות אותם."
            : "הערכים כאן משפיעים מיידית על בדיקות Vision AI, על קצב התזכורות של הבוט ועל ההודעות בוואטסאפ."
        }
        actions={
          !readOnly && (
            <>
              <Button variant="accent" icon={<Save className="h-4 w-4" />} loading={saving} disabled={!dirty || invalid.length > 0} onClick={save}>
                שמירת הגדרות
              </Button>
              <Button
                variant="fieldGhost"
                disabled={!dirty}
                onClick={() =>
                  setDraft({
                    firm_name: settings.firm_name,
                    vat_rate: settings.vat_rate,
                    allocation_number_threshold_nis: settings.allocation_number_threshold_nis,
                    reminder_interval_hours: settings.reminder_interval_hours,
                    max_reminders: settings.max_reminders,
                    vat_deadline_day: settings.vat_deadline_day,
                    auto_approve_verified: settings.auto_approve_verified,
                  })
                }
              >
                ביטול שינויים
              </Button>
              {dirty && <span className="text-sm font-semibold text-white">יש שינויים שלא נשמרו</span>}
            </>
          )
        }
      />
    <div className="mx-auto max-w-5xl space-y-6 p-4 @3xl:p-6">
      {settings.updated_by_name && (
        <p className="text-xs text-ink-500">
          עודכן לאחרונה ע״י {splitUserName(settings.updated_by_name).name} · {fullDateTime(settings.updated_at)}
        </p>
      )}

      {!readOnly && invalid.length > 0 && (
        <p className="rounded-lg bg-red-50 px-4 py-2 text-xs text-red-700">ערכים לא תקינים: {invalid.join(" · ")}</p>
      )}

      <Section title="הגדרות מס ורגולציה" hint="כללי רשות המסים שהבוט ו-Vision AI אוכפים על כל חשבונית">
        <div className="grid gap-4 @2xl:grid-cols-3">
          <Field label="שיעור מע״מ נוכחי (%)" hint="משמש לבדיקת התאמת המע״מ בכל חשבונית ובתצוגות המס">
            <NumberInput value={draft.vat_rate} onChange={(v) => set("vat_rate", v)} suffix="%" limits={LIMITS.vat_rate} disabled={readOnly} />
          </Field>
          <Field label="סף חובת מספר הקצאה (₪ לפני מע״מ)" hint="חשבונית בסכום זה ומעלה חייבת מספר הקצאה בן 9 ספרות">
            <NumberInput
              value={draft.allocation_number_threshold_nis}
              onChange={(v) => set("allocation_number_threshold_nis", v)}
              disabled={readOnly}
              suffix="₪"
              limits={LIMITS.allocation_number_threshold_nis}
            />
          </Field>
          <Field label="מועד דיווח מע״מ (יום בחודש)" hint="ברירת מחדל: 26. ניתן לשנות כאשר רשות המסים מזיזה את המועד.">
            <NumberInput
              value={draft.vat_deadline_day}
              onChange={(v) => set("vat_deadline_day", v)}
              disabled={readOnly}
              suffix="בחודש"
              limits={LIMITS.vat_deadline_day}
            />
          </Field>
        </div>
        <div className="mt-4 bg-ink-100 px-4 py-3 text-sm leading-relaxed text-ink-700">
          <p className="mb-1 font-bold text-ink-900">דוגמה חיה לפי הערכים הנוכחיים</p>
          <p>
            חשבונית בסך <Num value={exampleThreshold} prefix="₪" /> לפני מע״מ (סף ההקצאה) · מע״מ <Num value={exampleRate} suffix="%" /> בסך{" "}
            <Num value={exampleVat} prefix="₪" /> · סה״כ כולל מע״מ <Num value={exampleTotal} prefix="₪" />
          </p>
          <p className="mt-1">
            מחשבונית זו ומעלה (לפני מע״מ) נדרש <span className="font-semibold text-ink-900">מספר הקצאה</span> בן <Num value={9} /> ספרות; מתחת לסף —
            <span className="font-semibold text-ink-900"> מספר הקצאה אינו נדרש</span>.
          </p>
        </div>
      </Section>

      <Section title="הגדרות בוט ותזכורות" hint="קצב המעקב האוטומטי אחרי לקוחות שלא השיבו">
        <div className="grid gap-4 @xl:grid-cols-2">
          <Field label="מרווח זמן בין תזכורות אוטומטיות (שעות)" hint="חל על פניות חדשות ועל התזכורת הבאה בפניות פתוחות">
            <NumberInput value={draft.reminder_interval_hours} onChange={(v) => set("reminder_interval_hours", v)} suffix="שעות" limits={LIMITS.reminder_interval_hours} disabled={readOnly} />
          </Field>
          <Field label="מספר תזכורות מקסימלי לפני התראה אדומה" hint="לאחר מכן הפנייה מסומנת ”הוסלם“ לשיחת טלפון; מתעדכן גם בפניות פתוחות">
            <NumberInput value={draft.max_reminders} onChange={(v) => set("max_reminders", v)} suffix="פעמים" limits={LIMITS.max_reminders} disabled={readOnly} />
          </Field>
        </div>
        <div className="mt-4">
          <Toggle
            checked={draft.auto_approve_verified}
            onChange={(v) => set("auto_approve_verified", v)}
            disabled={readOnly}
            label="אישור אוטומטי לחשבוניות שעברו את כל בדיקות Vision AI (ללא בדיקת פקיד)"
          />
        </div>
      </Section>

      <Section
        title={readOnly ? "פרטי המשרד" : "פרטי המשרד וניהול צוות"}
        hint="שם המשרד מוצג ללקוחות בכותרת הוואטסאפ ובכל הודעה"
      >
        <div className="max-w-md">
          <Field label="שם המשרד">
            <input
              value={draft.firm_name}
              onChange={(e) => set("firm_name", e.target.value)}
              disabled={readOnly}
              readOnly={readOnly}
              className={cx(inputClass, readOnly && "cursor-not-allowed bg-ink-50 text-ink-600")}
              dir="auto"
            />
          </Field>
        </div>

        {isManager && (
        <div className="mt-6">
          <h3 className="mb-2 flex items-center gap-2 font-bold text-ink-900">
            <Users className="h-4 w-4" /> עובדי המשרד
          </h3>
          <div className="overflow-x-auto border border-ink-300">
            <table className="data-table">
              <thead>
                <tr className="data-head">
                  <th className="px-3 py-2 text-start">עובד/ת</th>
                  <th className="px-3 py-2 text-start">אימייל</th>
                  <th className="px-3 py-2 text-start">תפקיד</th>
                  <th className="px-3 py-2 text-start">סטטוס</th>
                  <th className="px-3 py-2 text-start">פעולות</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-200">
                {users.map((u) => (
                  <tr key={u.id} className={cx(!u.is_active && "opacity-50")}>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-brand-600 text-xs font-bold text-white">{u.avatar_initials}</span>
                        <span className="whitespace-nowrap">
                          <b className="text-ink-900">{splitUserName(u.full_name).name}</b>
                          <span className="ms-2 text-ink-600">{u.job_title || splitUserName(u.full_name).title}</span>
                          {u.id === user?.id && <span className="ms-1 font-semibold text-link">(את/ה)</span>}
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-2 text-ink-600" dir="ltr">
                      <span className="block text-end">{u.email}</span>
                    </td>
                    <td className="px-3 py-2">
                      <RoleBadge role={u.role} />
                    </td>
                    <td className="px-3 py-2">
                      <span className={cx("block font-semibold", u.is_active ? "text-ink-900" : "text-red-600")}>{u.is_active ? "פעיל" : "הושעה"}</span>
                      {u.two_factor_enabled && (
                        <span className="flex items-center gap-1 whitespace-nowrap text-xs text-emerald-700" title="נכנס/ת עם סיסמה וקוד מהטלפון">
                          <ShieldCheck className="h-3.5 w-3.5" /> אימות דו-שלבי
                        </span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2">
                      <Button size="sm" variant="secondary" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => setEditingWorker(u)}>
                        עריכה
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Button variant="secondary" className="mt-3" icon={<UserPlus className="h-4 w-4" />} onClick={() => setAddingWorker(true)}>
            הוספת עובד/ת
          </Button>
        </div>
        )}
      </Section>

      <Section title="מצב המערכת" hint="מידע לקריאה בלבד">
        <dl className="grid gap-3 text-sm @xl:grid-cols-3">
          <div>
            <dt className="text-xs text-ink-500">מנוע Vision AI</dt>
            <dd className="font-medium text-ink-900">{settings.vision_provider === "local" ? "סימולטור לא מקוון" : settings.vision_provider}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-500">וואטסאפ</dt>
            <dd className="font-medium text-ink-900">{settings.whatsapp_live ? "Meta Cloud API + סימולטור" : "סימולטור בלבד"}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-500">מנוע התזכורות</dt>
            <dd className={cx("flex items-center gap-1 font-medium", settings.scheduler.running ? "text-ink-900" : "text-amber-700")}>
              <ShieldCheck className="h-4 w-4" />
              {settings.scheduler.running ? `פעיל · בדיקה כל ${settings.scheduler.interval_seconds} שניות` : "מושהה"}
            </dd>
          </div>
        </dl>
      </Section>
      {isManager && (
        <>
          <EditWorkerModal worker={editingWorker} onClose={() => setEditingWorker(null)} />
          <AddWorkerModal open={addingWorker} onClose={() => setAddingWorker(false)} />
        </>
      )}
    </div>
    </>
  );
}
