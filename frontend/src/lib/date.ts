/** dd/mm/yyyy helpers for date fields (see components/DateInput). */

const pad = (n: number) => String(n).padStart(2, "0");
export const toDdMmYyyy = (d: Date) => `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;

/** "05/10/2026" → Date, or null when the text is not a complete, real calendar date. */
export function parseDdMmYyyy(s: string): Date | null {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(s.trim());
  if (!m) return null;
  const d = new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1]));
  return d.getDate() === Number(m[1]) && d.getMonth() === Number(m[2]) - 1 ? d : null;
}

/** Typing mask for dd/mm/yyyy: digits only, slashes are inserted automatically.
 *  "5/" pads to "05/", pasted "2026-10-05" or "5.10.2026" are converted. While deleting,
 *  no trailing slash is re-added, so Backspace walks back over the separators. */
export function maskDate(raw: string, prev: string): string {
  const iso = /^\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*$/.exec(raw);
  if (iso) return `${pad(Number(iso[3]))}/${pad(Number(iso[2]))}/${iso[1]}`;
  const deleting = raw.length < prev.length;
  const s = raw
    .replace(/[.\-\s]/g, "/")
    .replace(/[^\d/]/g, "")
    .replace(/(?<=^|\/)(\d)(?=\/)/g, "0$1"); // a slash typed after a single digit pads it
  const digits = s.replace(/\//g, "").slice(0, 8);
  let out = digits.slice(0, 2);
  if (digits.length > 2) out += "/" + digits.slice(2, 4);
  if (digits.length > 4) out += "/" + digits.slice(4);
  if (!deleting && (digits.length === 2 || digits.length === 4)) out += "/";
  return out;
}
