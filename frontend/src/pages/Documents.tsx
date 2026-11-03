import { useEffect, useMemo, useState } from "react";
import { ExternalLink, FileText, FolderOpen, Search, Users } from "lucide-react";
import { useApp } from "../context/AppContext";
import { api, mediaUrl } from "../lib/api";
import { cx, DOCUMENT_TYPES, fullDateTime } from "../lib/format";
import type { ClientDocument } from "../lib/types";
import { PageHeader } from "../components/PageHeader";
import { TicketModal } from "../components/TicketModal";
import { Card, Empty, inputClass, Spinner, StatusBadge, TabButton } from "../components/ui";

const NO_REQUEST = "ללא בקשה";

/** What the check found, shown for the copy a request was checked against ("waiting for the clerk" is already the status). */
const CHECK_LABEL: Partial<Record<NonNullable<ClientDocument["check_status"]>, string>> = {
  PASSED: "עבר את הבדיקה",
  FAILED: "נדחה בבדיקה",
};

/** The group a document is filed under: its type, the request it answered, or "no request". */
function groupOf(d: ClientDocument): string {
  if (d.ticket_id === null) return NO_REQUEST;
  return d.document_type ?? d.request_name ?? "אחר";
}

function monthKey(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function monthLabel(key: string): string {
  const [y, m] = key.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("he-IL", { month: "long", year: "numeric" });
}

/** Every photo or PDF a client sent on WhatsApp, filed by type and month, so the office can find it later. */
export function Documents() {
  const { clients, selectedClientId, selectClient, tick } = useApp();
  const [query, setQuery] = useState("");
  const [docs, setDocs] = useState<ClientDocument[] | null>(null);
  const [group, setGroup] = useState("all");
  const [month, setMonth] = useState("all");
  const [openTicket, setOpenTicket] = useState<number | null>(null);
  const client = clients.find((c) => c.id === selectedClientId) ?? null;

  // Another client starts unfiltered; server events refresh the current list in place.
  useEffect(() => {
    setDocs(null);
    setGroup("all");
    setMonth("all");
  }, [client?.id]);

  useEffect(() => {
    if (!client) return;
    let cancelled = false;
    api
      .documents(client.id)
      .then((rows) => !cancelled && setDocs(rows))
      .catch(() => !cancelled && setDocs([]));
    return () => {
      cancelled = true;
    };
  }, [client?.id, tick]); // eslint-disable-line react-hooks/exhaustive-deps

  const listed = useMemo(() => {
    const q = query.trim().toLowerCase();
    const digits = q.replace(/\D/g, "");
    return clients.filter(
      (c) =>
        !q ||
        c.full_name.toLowerCase().includes(q) ||
        c.company_name.toLowerCase().includes(q) ||
        (digits.length > 2 && (c.whatsapp_phone.replace(/\D/g, "").includes(digits) || c.tax_id.includes(digits))),
    );
  }, [clients, query]);

  const groups = useMemo(() => {
    const counts = new Map<string, number>();
    for (const d of docs ?? []) counts.set(groupOf(d), (counts.get(groupOf(d)) ?? 0) + 1);
    const order = [...DOCUMENT_TYPES, ...[...counts.keys()].filter((g) => g !== NO_REQUEST && !(DOCUMENT_TYPES as readonly string[]).includes(g)), NO_REQUEST];
    return order.filter((g) => counts.has(g)).map((g) => ({ name: g, count: counts.get(g) ?? 0 }));
  }, [docs]);

  const months = useMemo(() => [...new Set((docs ?? []).map((d) => monthKey(d.created_at)))].sort().reverse(), [docs]);
  const visible = (docs ?? []).filter((d) => (group === "all" || groupOf(d) === group) && (month === "all" || monthKey(d.created_at) === month));

  return (
    <>
      <PageHeader
        title="מסמכים מלקוחות"
        hint="כל צילום או קובץ PDF שלקוח שלח בוואטסאפ, מהחדש לישן, עם הבקשה שהוא ענה עליה ותוצאת הבדיקה."
      />
      <div className="mx-auto grid w-full max-w-7xl gap-5 p-4 @2xl/main:grid-cols-[260px_minmax(0,1fr)] @3xl/main:p-6">
        <Card className="flex max-h-[420px] flex-col p-3 @2xl/main:max-h-[70vh]">
          <h2 className="mb-2 font-display text-lg leading-tight text-ink-900">לקוח</h2>
          <div className="relative mb-3">
            <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="שם, עסק, טלפון או ח.פ…" className={cx(inputClass, "ps-9")} dir="auto" />
          </div>
          <div className="min-h-0 flex-1 divide-y divide-ink-200 overflow-y-auto">
            {listed.length === 0 && <Empty icon={<Users className="h-8 w-8" />} title="לא נמצאו לקוחות" />}
            {listed.map((c) => {
              const selected = c.id === client?.id;
              return (
                <button
                  key={c.id}
                  onClick={() => selectClient(c.id)}
                  aria-pressed={selected}
                  className={cx(
                    "block w-full px-2.5 py-2 text-start transition-colors",
                    selected ? "bg-brand-600 text-white" : "text-ink-900 hover:bg-ink-100",
                    !c.is_active && !selected && "opacity-60",
                  )}
                >
                  <p dir="auto" className="truncate text-sm font-bold">
                    {c.full_name}
                  </p>
                  <p dir="auto" className={cx("truncate text-xs", selected ? "text-white" : "text-ink-500")}>
                    {c.company_name}
                    {!c.is_active && " · לא פעיל"}
                  </p>
                </button>
              );
            })}
          </div>
        </Card>

        <Card className="@container min-w-0">
          {!client ? (
            <Empty icon={<FolderOpen className="h-10 w-10" />} title="בחרו לקוח" hint="המסמכים שהלקוח שלח בוואטסאפ יופיעו כאן." />
          ) : (
            <>
              <div className="space-y-3 border-b border-ink-300 p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h2 dir="auto" className="font-display text-xl leading-tight text-ink-900">
                    {client.full_name}
                    <span className="ms-2 font-sans text-sm font-normal text-ink-500">{client.company_name}</span>
                  </h2>
                  {docs && <span className="text-sm text-ink-600">{docs.length} מסמכים</span>}
                </div>
                {docs && docs.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="flex flex-wrap gap-1">
                      <TabButton active={group === "all"} onClick={() => setGroup("all")}>
                        הכל <span className="ms-1 font-normal opacity-75">{docs.length}</span>
                      </TabButton>
                      {groups.map((g) => (
                        <TabButton key={g.name} active={group === g.name} onClick={() => setGroup(g.name)}>
                          {g.name} <span className="ms-1 font-normal opacity-75">{g.count}</span>
                        </TabButton>
                      ))}
                    </div>
                    <select value={month} onChange={(e) => setMonth(e.target.value)} className={cx(inputClass, "ms-auto w-auto py-1.5")} aria-label="סינון לפי חודש">
                      <option value="all">כל החודשים</option>
                      {months.map((m) => (
                        <option key={m} value={m}>
                          {monthLabel(m)}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              {docs === null ? (
                <div className="flex justify-center p-10">
                  <Spinner className="h-6 w-6" />
                </div>
              ) : docs.length === 0 ? (
                <Empty icon={<FolderOpen className="h-10 w-10" />} title="הלקוח עדיין לא שלח מסמכים" hint="צילומים וקובצי PDF שהלקוח ישלח בוואטסאפ יישמרו כאן." />
              ) : visible.length === 0 ? (
                <Empty icon={<FolderOpen className="h-10 w-10" />} title="אין מסמכים שמתאימים לסינון" />
              ) : (
                <div className="grid grid-cols-2 gap-3 p-4 @lg:grid-cols-3 @4xl:grid-cols-4">
                  {visible.map((d) => (
                    <DocumentTile key={d.message_id} doc={d} onOpenTicket={setOpenTicket} />
                  ))}
                </div>
              )}
            </>
          )}
        </Card>
      </div>
      <TicketModal ticketId={openTicket} onClose={() => setOpenTicket(null)} />
    </>
  );
}

function DocumentTile({ doc, onOpenTicket }: { doc: ClientDocument; onOpenTicket: (id: number) => void }) {
  const src = mediaUrl(doc.media_url);
  const name = groupOf(doc);
  return (
    <article className="flex min-w-0 flex-col border border-ink-300 bg-surface">
      <a
        href={src ?? "#"}
        target="_blank"
        rel="noreferrer"
        title="פתיחת המסמך בגודל מלא"
        className="group relative block aspect-[4/3] overflow-hidden bg-ink-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
      >
        {doc.file_kind === "pdf" ? (
          <span className="grid h-full place-items-center text-ink-500">
            <span className="flex flex-col items-center gap-1 text-sm">
              <FileText className="h-10 w-10" /> PDF
            </span>
          </span>
        ) : (
          <img src={src ?? ""} alt={`${name}, ${fullDateTime(doc.created_at)}`} loading="lazy" className="h-full w-full object-cover object-top" />
        )}
        <span className="absolute end-2 top-2 bg-surface p-1 text-ink-700 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
          <ExternalLink className="h-3.5 w-3.5" />
        </span>
      </a>
      <div className="min-w-0 space-y-1 p-3 text-sm">
        <p className="font-bold text-ink-900">{name}</p>
        <p className="text-xs text-ink-500">{fullDateTime(doc.created_at)}</p>
        {doc.ticket_id !== null ? (
          <button
            type="button"
            onClick={() => onOpenTicket(doc.ticket_id as number)}
            className="block max-w-full truncate text-start text-link underline-offset-2 hover:underline"
            title="פתיחת הפנייה"
          >
            {doc.ticket_ref} · {doc.request_name}
          </button>
        ) : (
          <p className="text-ink-600">נשלח בלי בקשה פתוחה</p>
        )}
        {doc.ticket_status && doc.is_latest && (
          <div className="flex flex-wrap items-center gap-x-2">
            <StatusBadge status={doc.ticket_status} short />
            {doc.check_status && CHECK_LABEL[doc.check_status] && (
              <span className={cx("text-xs", doc.check_status === "FAILED" ? "text-red-700" : "text-ink-600")}>{CHECK_LABEL[doc.check_status]}</span>
            )}
          </div>
        )}
        {doc.ticket_id !== null && !doc.is_latest && <p className="text-xs text-ink-500">צילום קודם, הוחלף בצילום חדש יותר</p>}
        {doc.caption && (
          <p dir="auto" className="line-clamp-2 text-xs text-ink-600">
            {doc.caption}
          </p>
        )}
      </div>
    </article>
  );
}
