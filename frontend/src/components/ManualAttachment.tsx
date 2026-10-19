import { useEffect, useState } from "react";
import { FileText, X } from "lucide-react";
import { cx } from "../lib/format";

/** File types a worker can attach to a manual message (same list as POST /api/whatsapp/manual-send). */
export const MANUAL_ATTACHMENT_ACCEPT = ".jpg,.jpeg,.png,.webp,.pdf,image/jpeg,image/png,image/webp,application/pdf";
const ALLOWED_EXT = /\.(jpe?g|png|webp|pdf)$/i;
const ALLOWED_MIME = new Set(["image/jpeg", "image/png", "image/webp", "application/pdf"]);
export const MANUAL_ATTACHMENT_MAX_BYTES = 15 * 1024 * 1024;

/** Hebrew error for a file the API would reject, or null when it can be sent. */
export function attachmentError(file: File): string | null {
  if (!ALLOWED_EXT.test(file.name) && !ALLOWED_MIME.has(file.type)) return "ניתן לצרף JPG, PNG, WEBP או PDF בלבד";
  if (file.size > MANUAL_ATTACHMENT_MAX_BYTES) return "הקובץ גדול מדי (מקסימום 15MB)";
  return null;
}

export function attachmentKind(file: File): "image" | "pdf" {
  return file.type === "application/pdf" || /\.pdf$/i.test(file.name) ? "pdf" : "image";
}

/** A local blob: URL for previewing the file before it is sent; revoked when the file changes. */
export function useObjectUrl(file: File | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!file) {
      setUrl(null);
      return;
    }
    const next = URL.createObjectURL(file);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [file]);
  return url;
}

/** Thumbnail + file name + remove button for a picked attachment. */
export function AttachmentChip({
  file,
  previewUrl,
  onRemove,
  disabled,
  className,
}: {
  file: File;
  previewUrl: string | null;
  onRemove: () => void;
  disabled?: boolean;
  className?: string;
}) {
  const kind = attachmentKind(file);
  return (
    <div className={cx("flex items-center gap-2 rounded-lg bg-white p-1.5 ring-1 ring-slate-200", className)}>
      {kind === "image" && previewUrl ? (
        <img src={previewUrl} alt="תצוגה מקדימה של הקובץ המצורף" className="h-12 w-12 shrink-0 rounded-md object-cover" />
      ) : (
        <span className="grid h-12 w-12 shrink-0 place-items-center rounded-md bg-slate-100 text-slate-500">
          <FileText className="h-5 w-5" />
        </span>
      )}
      <div className="min-w-0 flex-1">
        <p dir="auto" className="truncate text-xs font-medium text-slate-800">
          {file.name}
        </p>
        <p className="text-[11px] text-slate-500">
          {kind === "pdf" ? "מסמך PDF" : "תמונה"} · {(file.size / 1024).toFixed(0)} KB
        </p>
      </div>
      <button
        type="button"
        onClick={onRemove}
        disabled={disabled}
        className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-40"
        title="הסרת הקובץ המצורף"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
