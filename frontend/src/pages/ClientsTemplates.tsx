import { useEffect, useMemo, useState } from "react";
import { Lock, Pencil, Plus, Save, Search, UserX, Users } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api } from "../lib/api";
import { cx, FREQUENCY_LABEL, hasArabic, localizedButtons, NAME_LANGUAGE_ERROR, renderTemplate, splitUserName, templateName, VAT_DEADLINE_DAY } from "../lib/format";
import type { Client, ClientInput, ReportingFrequency, Template, TemplateButton } from "../lib/types";
import { PageHeader } from "../components/PageHeader";
import { WaBubble } from "../components/WaBubble";
import { Button, Card, Empty, Field, inputClass, Ltr, Modal, TabButton } from "../components/ui";

const NINE_DIGITS = /^\d{9}$/;

const SAMPLE_VARS: Record<string, string> = {
  client_name: "יוסי",
  supplier_name: "Ace Building Supplies",
  amount: "₪1,240.00",
  invoice_date: "03/10/2026",
  invoice_number: "88412",
  missing_detail: "מספר הקצאה",
  charge_amount: "₪2,350.00",
  charge_date: "08/10/2026",
  bank_reference: "CC-7781-2290",
  tax_period: "10/2026",
  vat_amount: "₪4,820.00",
  tax_advance_amount: "₪2,150.00",
  due_date: "15/11/2026",
  rejection_reason: "הצילום מטושטש",
  open_items_count: "3",
  days_left: "2",
};

function ClientForm({ initial, onSaved, onCancel }: { initial: Client | null; onSaved: () => void; onCancel: () => void }) {
  const { users, toast } = useApp();
  const [form, setForm] = useState<ClientInput>(() =>
    initial
      ? {
          full_name: initial.full_name,
          company_name: initial.company_name,
          tax_id: initial.tax_id,
          whatsapp_phone: initial.whatsapp_phone,
          reporting_frequency: initial.reporting_frequency,
          assigned_worker_id: initial.assigned_worker_id,
          notes: initial.notes,
          is_active: initial.is_active,
        }
      : {
          full_name: "",
          company_name: "",
          tax_id: "",
          whatsapp_phone: "",
          reporting_frequency: "MONTHLY",
          assigned_worker_id: null,
          notes: "",
          is_active: true,
        },
  );
  const [saving, setSaving] = useState(false);
  const set = <K extends keyof ClientInput>(k: K, v: ClientInput[K]) => setForm((f) => ({ ...f, [k]: v }));
  const taxIdInvalid = form.tax_id.length > 0 && !NINE_DIGITS.test(form.tax_id);
  const nameInvalid = hasArabic(form.full_name) || hasArabic(form.company_name);

  const save = async () => {
    if (nameInvalid) {
      toast({ tone: "error", title: "שם לא תקין", body: NAME_LANGUAGE_ERROR });
      return;
    }
    if (!NINE_DIGITS.test(form.tax_id)) {
      toast({ tone: "error", title: "ח.פ / ע.מ לא תקין", body: "לפי הוראות רשות המסים, מספר ח.פ או עוסק מורשה חייב להכיל בדיוק 9 ספרות." });
      return;
    }
    setSaving(true);
    try {
      if (initial) await api.updateClient(initial.id, form);
      else await api.createClient(form);
      toast({ tone: "success", title: initial ? "פרטי הלקוח עודכנו" : "הלקוח נוסף", body: form.full_name });
      onSaved();
    } catch (e) {
      toast({ tone: "error", title: "שמירת הלקוח נכשלה", body: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      className="space-y-3 p-6"
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="שם איש הקשר" hint={hasArabic(form.full_name) ? `${NAME_LANGUAGE_ERROR}` : "עברית או אנגלית"}>
          <input
            required
            dir="auto"
            value={form.full_name}
            onChange={(e) => set("full_name", e.target.value)}
            className={cx(inputClass, hasArabic(form.full_name) && "ring-2 ring-red-400")}
          />
        </Field>
        <Field label="שם העסק" hint={hasArabic(form.company_name) ? `${NAME_LANGUAGE_ERROR}` : "עברית או אנגלית"}>
          <input
            dir="auto"
            value={form.company_name}
            onChange={(e) => set("company_name", e.target.value)}
            className={cx(inputClass, hasArabic(form.company_name) && "ring-2 ring-red-400")}
          />
        </Field>
        <Field label="ח.פ / ע.מ (9 ספרות)" hint={taxIdInvalid ? "נדרשות בדיוק 9 ספרות" : "לפי הוראות רשות המסים"}>
          <input
            required
            dir="ltr"
            value={form.tax_id}
            onChange={(e) => set("tax_id", e.target.value.replace(/[^\d]/g, "").slice(0, 9))}
            className={cx(inputClass, "text-end", taxIdInvalid && "ring-2 ring-red-400")}
            inputMode="numeric"
            placeholder="514782301"
          />
        </Field>
        <Field label="מספר וואטסאפ" hint="05x… או ‎+972… — נשמר בפורמט בינלאומי">
          <input required dir="ltr" value={form.whatsapp_phone} onChange={(e) => set("whatsapp_phone", e.target.value)} className={cx(inputClass, "text-end")} inputMode="tel" />
        </Field>
        <Field label="תדירות דיווח" hint={`מועד הדיווח: ה-${VAT_DEADLINE_DAY} בחודש${form.reporting_frequency === "BIMONTHLY" ? " (בחודשים אי-זוגיים)" : ""}`}>
          <select
            value={form.reporting_frequency}
            onChange={(e) => set("reporting_frequency", e.target.value as ReportingFrequency)}
            className={inputClass}
          >
            {(Object.keys(FREQUENCY_LABEL) as ReportingFrequency[]).map((f) => (
              <option key={f} value={f}>
                {FREQUENCY_LABEL[f]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="עובד/ת אחראי/ת">
          <select value={form.assigned_worker_id ?? ""} onChange={(e) => set("assigned_worker_id", e.target.value ? Number(e.target.value) : null)} className={inputClass}>
            <option value="">— ללא שיוך —</option>
            {users
              .filter((u) => u.is_active)
              .map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name}
                </option>
              ))}
          </select>
        </Field>
        <Field label="סטטוס">
          <select value={form.is_active ? "1" : "0"} onChange={(e) => set("is_active", e.target.value === "1")} className={inputClass}>
            <option value="1">פעיל</option>
            <option value="0">לא פעיל</option>
          </select>
        </Field>
      </div>
      <Field label="הערות">
        <textarea dir="auto" rows={2} value={form.notes} onChange={(e) => set("notes", e.target.value)} className={inputClass} />
      </Field>
      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="ghost" onClick={onCancel}>
          ביטול
        </Button>
        <Button type="submit" variant="accent" loading={saving} icon={<Save className="h-4 w-4" />}>
          {initial ? "שמירת שינויים" : "הוספת לקוח"}
        </Button>
      </div>
    </form>
  );
}

function ClientsPanel({ editing, setEditing }: { editing: Client | "new" | null; setEditing: (c: Client | "new" | null) => void }) {
  const { clients, refreshClients, toast, selectClient, isManager } = useApp();
  const [q, setQ] = useState("");
  const [confirming, setConfirming] = useState<Client | null>(null);
  const [showInactive, setShowInactive] = useState(false);

  const list = useMemo(() => {
    const n = q.trim().toLowerCase();
    return clients
      .filter((c) => showInactive || c.is_active)
      .filter((c) => !n || `${c.full_name} ${c.company_name} ${c.whatsapp_phone} ${c.tax_id}`.toLowerCase().includes(n));
  }, [clients, q, showInactive]);

  const deactivate = async (c: Client) => {
    try {
      await api.deactivateClient(c.id);
      await refreshClients();
      toast({ tone: "info", title: "הלקוח הושבת", body: `${c.full_name} · הפניות הפתוחות שלו נסגרו` });
    } catch (e) {
      toast({ tone: "error", title: "ההשבתה נכשלה", body: e instanceof Error ? e.message : String(e) });
    } finally {
      setConfirming(null);
    }
  };

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-3 border-b border-ink-300 p-3">
        <div className="relative w-full @xl:w-72">
          <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="חיפוש לקוחות…" className={cx(inputClass, "py-1.5 ps-9")} dir="auto" />
        </div>
        <label className="flex items-center gap-1.5 text-xs text-ink-600">
          <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} /> הצגת לקוחות לא פעילים
        </label>
      </div>
      {list.length === 0 ? (
        <Empty icon={<Users className="h-10 w-10" />} title="אין לקוחות" />
      ) : (
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr className="data-head">
                <th className="px-4 py-2.5 text-start">לקוח</th>
                <th className="hidden px-3 py-2.5 text-start @5xl:table-cell">עסק</th>
                <th className="px-3 py-2.5 text-start">ח.פ / ע.מ</th>
                <th className="px-3 py-2.5 text-start">וואטסאפ</th>
                <th className="hidden px-3 py-2.5 text-start @5xl:table-cell">תדירות דיווח</th>
                <th className="px-3 py-2.5 text-start">מועד הדיווח הבא</th>
                <th className="whitespace-nowrap px-3 py-2.5 text-start">עובד/ת אחראי/ת</th>
                <th className="px-3 py-2.5 text-start">פתוחות</th>
                {isManager && <th className="px-3 py-2.5 text-start">פעולות</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-200">
              {list.map((c) => (
                <tr key={c.id} className={cx("hover:bg-ink-50", !c.is_active && "opacity-50")}>
                  <td className="max-w-[180px] px-4 py-2.5">
                    <button dir="auto" className="block max-w-full truncate text-start font-bold text-ink-900" onClick={() => selectClient(c.id, true)} title={`${c.company_name} · פתיחת שיחת הוואטסאפ`}>
                      {c.full_name}
                    </button>
                  </td>
                  <td dir="auto" className="hidden max-w-[180px] truncate px-3 py-2.5 text-ink-600 @5xl:table-cell" title={c.company_name}>
                    {c.company_name}
                  </td>
                  <td className="px-3 py-2.5">
                    <Ltr>{c.tax_id || "—"}</Ltr>
                  </td>
                  <td className="px-3 py-2.5">
                    <Ltr>{c.whatsapp_phone}</Ltr>
                  </td>
                  <td className="hidden whitespace-nowrap px-3 py-2.5 @5xl:table-cell">{FREQUENCY_LABEL[c.reporting_frequency]}</td>
                  <td className="whitespace-nowrap px-3 py-2.5">
                    <Ltr>{c.next_deadline}</Ltr> ·{" "}
                    <span className={cx(c.days_to_deadline <= 3 ? "font-semibold text-red-600" : "text-ink-500")}>
                      עוד <Ltr>{c.days_to_deadline}</Ltr> ימים
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-ink-600">{c.assigned_worker_name ? splitUserName(c.assigned_worker_name).name : "—"}</td>
                  <td className="px-3 py-2.5">{c.open_ticket_count}</td>
                  {isManager && (
                    <td className="whitespace-nowrap px-3 py-2.5">
                      <span className="flex gap-1">
                        <Button size="sm" variant="ghost" className="w-8 !px-0" title="עריכה" aria-label="עריכה" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => setEditing(c)} />
                        {c.is_active && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="w-8 !px-0 hover:bg-red-50 hover:text-red-700"
                            title="מחיקת / השבתת לקוח"
                            aria-label="מחיקת / השבתת לקוח"
                            icon={<UserX className="h-3.5 w-3.5" />}
                            onClick={() => setConfirming(c)}
                          />
                        )}
                      </span>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "הוספת לקוח" : "עריכת לקוח"}>
        {editing !== null && (
          <ClientForm
            key={editing === "new" ? "new" : editing.id}
            initial={editing === "new" ? null : editing}
            onCancel={() => setEditing(null)}
            onSaved={() => {
              setEditing(null);
              refreshClients();
            }}
          />
        )}
      </Modal>
      <Modal open={confirming !== null} onClose={() => setConfirming(null)} title="השבתת לקוח">
        {confirming && (
          <div className="space-y-4 p-6">
            <p className="text-sm text-ink-700">
              להשבית את <b dir="auto">{confirming.full_name}</b> ({confirming.company_name})? כל הפניות הפתוחות שלו ייסגרו והבוט יפסיק לשלוח לו תזכורות.
              היסטוריית ההודעות נשמרת, וניתן להפעיל את הלקוח מחדש בעריכה.
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setConfirming(null)}>
                ביטול
              </Button>
              <Button variant="danger" icon={<UserX className="h-4 w-4" />} onClick={() => deactivate(confirming)}>
                השבתת הלקוח
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </Card>
  );
}

function TemplateEditor({ template }: { template: Template }) {
  const { refreshTemplates, toast, isManager } = useApp();
  const [draft, setDraft] = useState<Template>(template);
  const [saving, setSaving] = useState(false);
  useEffect(() => setDraft(template), [template]);

  const dirty = JSON.stringify(draft) !== JSON.stringify(template);
  const setButton = (i: number, v: string) =>
    setDraft((d) => ({ ...d, buttons_json: d.buttons_json.map((b, j): TemplateButton => (j === i ? { ...b, he: v } : b)) }));

  const save = async () => {
    setSaving(true);
    try {
      await api.updateTemplate(template.id, {
        name_he: draft.name_he,
        body_he: draft.body_he,
        buttons_json: draft.buttons_json,
      });
      await refreshTemplates();
      toast({ tone: "success", title: "התבנית נשמרה", body: draft.name_he });
    } catch (e) {
      toast({ tone: "error", title: "שמירת התבנית נכשלה", body: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="min-w-0 p-4">
      <div className="flex flex-wrap items-center gap-2 border-b border-ink-300 pb-2">
        <div className="min-w-0">
          <p className="font-display text-lg leading-tight text-ink-900">{templateName(template)}</p>
          <p className="tabular-nums text-xs text-ink-400">
            <Ltr>{template.slug}</Ltr>
            {template.requires_media_reply ? " · נסגר לאחר אימות Vision AI" : " · נסגר בלחיצת כפתור"}
          </p>
        </div>
        {isManager && (
          <div className="ms-auto flex items-center gap-2">
            {dirty && <span className="text-xs text-amber-600">יש שינויים שלא נשמרו</span>}
            <Button variant="ghost" size="sm" disabled={!dirty} onClick={() => setDraft(template)}>
              ביטול שינויים
            </Button>
            <Button variant="accent" size="sm" disabled={!dirty} loading={saving} icon={<Save className="h-3.5 w-3.5" />} onClick={save}>
              שמירה
            </Button>
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-1 pt-3">
        <span className="text-xs text-ink-500">משתנים:</span>
        {template.variables.map((v) => (
          <code key={v} dir="ltr" className="rounded bg-ink-100 px-1.5 py-0.5 text-xs text-ink-700">{`{{${v}}}`}</code>
        ))}
      </div>
      <div className={cx("grid gap-4 pt-4", isManager && "@5xl:grid-cols-[minmax(0,1fr)_340px]")}>
        {isManager && (
        <div className="min-w-0 space-y-2" dir="rtl">
          <Field label="שם התבנית">
            <input
              dir="rtl"
              value={draft.name_he}
              onChange={(e) => setDraft((d) => ({ ...d, name_he: e.target.value }))}
              className={cx(inputClass, "py-1.5 text-sm")}
            />
          </Field>
          <Field label="נוסח ההודעה בוואטסאפ">
            <textarea
              dir="rtl"
              rows={9}
              value={draft.body_he}
              onChange={(e) => setDraft((d) => ({ ...d, body_he: e.target.value }))}
              className={cx(inputClass, "font-sans text-sm leading-relaxed")}
            />
          </Field>
          <div>
            <span className="mb-1 block text-xs font-medium text-ink-600">כפתורי תגובה מהירה</span>
            <div className="space-y-1">
              {draft.buttons_json.map((b, i) => (
                <input
                  key={b.id}
                  dir="rtl"
                  value={b.he}
                  onChange={(e) => setButton(i, e.target.value)}
                  className={cx(inputClass, "py-1 text-xs")}
                  title={`כפתור ${b.id} (${b.action})`}
                />
              ))}
            </div>
          </div>
        </div>
        )}
        <div className={cx(!isManager && "max-w-md")}>
          <span className="mb-1 block text-xs font-medium text-ink-600">{isManager ? "תצוגה מקדימה" : "נוסח ההודעה בוואטסאפ"}</span>
          <div className="rounded-lg bg-wa-wall p-3" dir="rtl">
            <WaBubble text={renderTemplate(draft.body_he, SAMPLE_VARS)} fromFirm compact buttons={localizedButtons(draft)} type="TEMPLATE" />
          </div>
        </div>
      </div>
    </Card>
  );
}

function TemplatesPanel() {
  const { templates } = useApp();
  const [activeId, setActiveId] = useState<number | null>(null);
  const active = templates.find((t) => t.id === activeId) ?? templates[0] ?? null;
  return (
    <div className="space-y-4">
      <div className="grid gap-5 @3xl:grid-cols-[260px_minmax(0,1fr)]">
        <div className="h-fit divide-y divide-ink-200 border border-ink-300 bg-surface">
          {templates.map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveId(t.id)}
              className={cx("flex w-full items-start gap-2 px-3 py-2.5 text-start transition-colors", active?.id === t.id ? "bg-brand-600 text-white" : "hover:bg-ink-100")}
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{t.name_he}</p>
              </div>
              {t.is_system && <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-70" aria-label="תבנית מערכת של Vision AI" />}
            </button>
          ))}
        </div>
        {active && <TemplateEditor template={active} />}
      </div>
    </div>
  );
}

export function ClientsTemplates() {
  const { isManager } = useApp();
  const [tab, setTab] = useState<"clients" | "templates">("clients");
  const [editing, setEditing] = useState<Client | "new" | null>(null);
  const TABS = { clients: "לקוחות", templates: "תבניות הודעה" } as const;
  return (
    <>
      <PageHeader
        title="לקוחות ותבניות הודעה"
        hint="פרטי הלקוח קובעים את תדירות הדיווח והעובד האחראי. כל ההודעות ללקוחות נשלחות בוואטסאפ בעברית."
        actions={
          isManager &&
          tab === "clients" && (
            <Button variant="accent" icon={<Plus className="h-4 w-4" />} onClick={() => setEditing("new")}>
              הוספת לקוח
            </Button>
          )
        }
      />
      <div className="mx-auto max-w-7xl space-y-4 p-4 @3xl:p-6">
        <div className="flex gap-1">
          {(["clients", "templates"] as const).map((t) => (
            <TabButton key={t} active={tab === t} onClick={() => setTab(t)}>
              {TABS[t]}
            </TabButton>
          ))}
        </div>
        {tab === "clients" ? <ClientsPanel editing={editing} setEditing={setEditing} /> : <TemplatesPanel />}
      </div>
    </>
  );
}
