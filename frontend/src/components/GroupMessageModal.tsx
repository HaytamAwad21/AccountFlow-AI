import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Search, Send, Users } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api } from "../lib/api";
import { cx } from "../lib/format";
import type { Client } from "../lib/types";
import { Button, Empty, inputClass, Ltr, Modal } from "./ui";
import { WaBubble } from "./WaBubble";

const collator = new Intl.Collator(["he", "en"], { sensitivity: "base", numeric: true });

function matches(c: Client, q: string): boolean {
  if (!q) return true;
  const digits = q.replace(/\D/g, "");
  return (
    c.full_name.toLowerCase().includes(q) ||
    c.company_name.toLowerCase().includes(q) ||
    (digits.length > 2 && (c.whatsapp_phone.replace(/\D/g, "").includes(digits) || c.tax_id.includes(digits)))
  );
}

/**
 * Free-text message from the logged-in worker to several clients.
 * Step 1: pick clients (alphabetical list, search, select all). Step 2: write the message and send.
 */
export function GroupMessageModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { clients, user, toast, refreshClients } = useApp();
  const [step, setStep] = useState<"select" | "compose">("select");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const selectAllRef = useRef<HTMLInputElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const workerName = user?.full_name ?? "עובד/ת המשרד";

  useEffect(() => {
    if (!open) return;
    setStep("select");
    setQuery("");
    setSelected(new Set());
    setText("");
    window.setTimeout(() => searchRef.current?.focus(), 30);
  }, [open]);

  const sorted = useMemo(
    () => clients.filter((c) => c.is_active).sort((a, b) => collator.compare(a.full_name, b.full_name)),
    [clients],
  );
  const q = query.trim().toLowerCase();
  const visible = useMemo(() => sorted.filter((c) => matches(c, q)), [sorted, q]);
  const visibleSelected = visible.filter((c) => selected.has(c.id)).length;
  const allVisibleSelected = visible.length > 0 && visibleSelected === visible.length;
  const chosen = sorted.filter((c) => selected.has(c.id));

  useEffect(() => {
    if (selectAllRef.current) selectAllRef.current.indeterminate = visibleSelected > 0 && !allVisibleSelected;
  }, [visibleSelected, allVisibleSelected]);

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  /** "Select all" works on the clients currently shown (all of them when the search is empty). */
  const toggleAllVisible = () =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) visible.forEach((c) => next.delete(c.id));
      else visible.forEach((c) => next.add(c.id));
      return next;
    });

  const goCompose = () => {
    if (!selected.size) return;
    setStep("compose");
    window.setTimeout(() => textRef.current?.focus(), 30);
  };

  const send = async () => {
    const value = text.trim();
    if (!value || !chosen.length || sending) return;
    setSending(true);
    try {
      const r = await api.manualBroadcast(
        chosen.map((c) => c.id),
        value,
      );
      toast({ tone: "success", title: `ההודעה נשלחה ל-${r.sent} לקוחות`, body: `נשלחה בשם ${workerName} · מופיעה בצ׳אט של כל לקוח` });
      refreshClients().catch(() => undefined);
      onClose();
    } catch (e) {
      toast({ tone: "error", title: "שליחת ההודעה הקבוצתית נכשלה", body: e instanceof Error ? e.message : String(e) });
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={
        <span className="flex items-center gap-2">
          <Users className="h-5 w-5 text-wa-teal" /> הודעה לקבוצת לקוחות
        </span>
      }
      subtitle={step === "select" ? "שלב 1 מתוך 2 · בוחרים לקוחות" : `שלב 2 מתוך 2 · כותבים הודעה ל-${chosen.length} לקוחות`}
    >
      {step === "select" ? (
        <div className="flex max-h-[70vh] flex-col">
          <div className="space-y-2 border-b border-slate-200 px-6 py-3">
            <div className="relative">
              <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                ref={searchRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="חיפוש לפי שם, עסק, טלפון או ח.פ"
                className={cx(inputClass, "ps-9")}
                dir="auto"
              />
            </div>
            <label className="flex cursor-pointer items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm font-medium text-slate-800">
              <input
                ref={selectAllRef}
                type="checkbox"
                checked={allVisibleSelected}
                onChange={toggleAllVisible}
                disabled={!visible.length}
                className="h-4 w-4 rounded border-slate-300 text-wa-teal focus:ring-wa-teal"
              />
              {q ? `בחירת כל תוצאות החיפוש (${visible.length})` : `בחירת כל הלקוחות (${visible.length})`}
              <span className="ms-auto text-xs font-normal text-slate-500">נבחרו {selected.size}</span>
            </label>
          </div>

          <div className="min-h-[200px] flex-1 overflow-y-auto px-3 py-2">
            {visible.length === 0 ? (
              <Empty icon={<Users className="h-8 w-8" />} title="לא נמצאו לקוחות" />
            ) : (
              <ul className="space-y-0.5">
                {visible.map((c) => {
                  const on = selected.has(c.id);
                  return (
                    <li key={c.id}>
                      <label
                        className={cx(
                          "flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 transition",
                          on ? "bg-teal-50 ring-1 ring-inset ring-teal-200" : "hover:bg-slate-50",
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={on}
                          onChange={() => toggle(c.id)}
                          className="h-4 w-4 shrink-0 rounded border-slate-300 text-wa-teal focus:ring-wa-teal"
                        />
                        <div className="min-w-0 flex-1">
                          <p dir="auto" className="truncate text-sm font-medium text-slate-900">
                            {c.full_name}
                          </p>
                          <p dir="auto" className="truncate text-xs text-slate-500">
                            {c.company_name}
                          </p>
                        </div>
                        <span className="shrink-0 text-[11px] text-slate-400">
                          <Ltr>{c.whatsapp_phone}</Ltr>
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className="flex items-center justify-between gap-3 border-t border-slate-200 px-6 py-3">
            <span className="text-sm text-slate-600">
              {selected.size ? `נבחרו ${selected.size} לקוחות` : "לא נבחרו לקוחות"}
            </span>
            <div className="flex gap-2">
              {selected.size > 0 && (
                <Button variant="ghost" onClick={() => setSelected(new Set())}>
                  ניקוי הבחירה
                </Button>
              )}
              <Button variant="wa" disabled={!selected.size} onClick={goCompose}>
                המשך לכתיבת ההודעה
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <form
          className="space-y-4 px-6 py-4"
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
        >
          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-medium text-slate-600">נמענים ({chosen.length})</span>
              <button type="button" onClick={() => setStep("select")} className="flex items-center gap-1 text-xs font-medium text-brand-600 hover:underline">
                <ArrowRight className="h-3.5 w-3.5" /> חזרה לבחירת לקוחות
              </button>
            </div>
            <div className="flex max-h-24 flex-wrap gap-1 overflow-y-auto">
              {chosen.map((c) => (
                <span key={c.id} dir="auto" className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">
                  {c.full_name}
                </span>
              ))}
            </div>
          </div>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">תוכן ההודעה</span>
            <textarea
              ref={textRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                  e.preventDefault();
                  send();
                }
              }}
              rows={5}
              dir="auto"
              maxLength={4096}
              placeholder="כתבו כאן את ההודעה לכל הלקוחות שנבחרו…"
              className={cx(inputClass, "resize-y leading-relaxed")}
            />
          </label>

          {text.trim() && (
            <div className="rounded-lg bg-wa-wall p-3" dir="rtl">
              <p className="mb-1.5 text-[11px] text-slate-500">כך תופיע ההודעה אצל כל לקוח:</p>
              <WaBubble text={text.trim()} fromFirm compact automated={false} senderName={workerName} type="TEXT" />
            </div>
          )}

          <div className="flex items-center justify-between gap-3 border-t border-slate-200 pt-3">
            <span className="text-[11px] text-slate-400">Ctrl+Enter לשליחה · ללא תזכורות אוטומטיות</span>
            <Button type="submit" variant="wa" loading={sending} disabled={!text.trim()} icon={<Send className="h-4 w-4 -scale-x-100" />}>
              שליחה ל-{chosen.length} לקוחות
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
