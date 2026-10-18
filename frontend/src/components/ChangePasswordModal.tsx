import { useEffect, useState } from "react";
import { KeyRound } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api } from "../lib/api";
import { Button, Field, Modal, PasswordInput } from "./ui";

/** The logged-in user changes their own password (other browsers of this user are signed out). */
export function ChangePasswordModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { toast } = useApp();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setCurrent("");
      setNext("");
      setConfirm("");
      setError(null);
    }
  }, [open]);

  const problem = next && next.length < 6 ? "הסיסמה החדשה חייבת להכיל לפחות 6 תווים" : confirm && next !== confirm ? "אימות הסיסמה אינו תואם" : null;

  const save = async () => {
    if (!current || !next || problem) return;
    setSaving(true);
    setError(null);
    try {
      await api.changePassword(current, next);
      toast({ tone: "success", title: "הסיסמה עודכנה", body: "חיבורים פתוחים בדפדפנים אחרים נותקו." });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="שינוי סיסמה">
      <form
        dir="rtl"
        className="space-y-3 p-6"
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <Field label="סיסמה נוכחית">
          <PasswordInput value={current} onChange={setCurrent} autoComplete="current-password" />
        </Field>
        <Field label="סיסמה חדשה (לפחות 6 תווים)">
          <PasswordInput value={next} onChange={setNext} autoComplete="new-password" />
        </Field>
        <Field label="אימות סיסמה חדשה">
          <PasswordInput value={confirm} onChange={setConfirm} autoComplete="new-password" invalid={!!confirm && confirm !== next} />
        </Field>
        {(problem || error) && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{problem ?? error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            ביטול
          </Button>
          <Button type="submit" variant="primary" loading={saving} disabled={!current || !next || !confirm || !!problem} icon={<KeyRound className="h-4 w-4" />}>
            עדכון סיסמה
          </Button>
        </div>
      </form>
    </Modal>
  );
}
