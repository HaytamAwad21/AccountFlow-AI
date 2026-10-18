import { Check, CheckCheck, CornerUpLeft, ImageIcon } from "lucide-react";
import { mediaUrl } from "../lib/api";
import { clockTime, cx } from "../lib/format";
import type { DeliveryStatus, MessageType, RenderedButton } from "../lib/types";

const TYPE_TAG: Partial<Record<MessageType, { label: string; className: string }>> = {
  AUTO_REMINDER: { label: "🔁 תזכורת אוטומטית", className: "text-violet-700" },
  OCR_FEEDBACK: { label: "🤖 בדיקת Vision AI", className: "text-indigo-700" },
  TEMPLATE: { label: "📤 תבנית", className: "text-wa-teal" },
};

function Ticks({ status }: { status: DeliveryStatus }) {
  if (status === "FAILED") return <span className="text-[10px] font-semibold text-red-600">נכשל</span>;
  if (status === "SENT") return <Check className="h-3.5 w-3.5 text-slate-400" />;
  return <CheckCheck className={cx("h-3.5 w-3.5", status === "READ" ? "text-sky-500" : "text-slate-400")} />;
}

/**
 * A WhatsApp chat bubble as seen on the CLIENT's phone (RTL layout):
 * firm messages arrive on the start side (white), client replies go out on the end side (green).
 */
export function WaBubble({
  text,
  fromFirm,
  createdAt,
  buttons,
  onButton,
  buttonsDisabled,
  delivery,
  mediaPath,
  type,
  compact = false,
}: {
  text: string;
  fromFirm: boolean;
  createdAt?: string;
  buttons?: RenderedButton[] | null;
  onButton?: (b: RenderedButton) => void;
  buttonsDisabled?: boolean;
  delivery?: DeliveryStatus;
  mediaPath?: string | null;
  type?: MessageType;
  compact?: boolean;
}) {
  const tag = fromFirm && type ? TYPE_TAG[type] : undefined;
  const isButtonReply = !fromFirm && type === "BUTTON_REPLY";
  const src = mediaUrl(mediaPath);
  return (
    <div className={cx("flex w-full flex-col", fromFirm ? "items-start" : "items-end")}>
      <div
        className={cx(
          "relative max-w-[86%] rounded-lg px-2.5 pb-1.5 pt-1.5 text-[13.5px] leading-snug text-slate-900 shadow-[0_1px_0.5px_rgba(0,0,0,0.13)]",
          fromFirm ? "rounded-ss-none bg-white" : "rounded-se-none bg-wa-bubble",
          compact && "max-w-full",
        )}
      >
        {tag && <div className={cx("mb-0.5 text-[10.5px] font-semibold", tag.className)}>{tag.label}</div>}
        {src && (
          <a href={src} target="_blank" rel="noreferrer" className="mb-1 block overflow-hidden rounded-md bg-slate-100">
            {/\.pdf$/i.test(src) ? (
              <span className="flex items-center gap-2 p-3 text-xs text-slate-700">
                <ImageIcon className="h-4 w-4" /> מסמך PDF
              </span>
            ) : (
              <img src={src} alt="מסמך שהועלה" className="max-h-56 w-[220px] max-w-full object-cover object-top" />
            )}
          </a>
        )}
        {isButtonReply && <CornerUpLeft className="me-1 inline h-3 w-3 text-slate-500" />}
        <span dir="auto" className="whitespace-pre-wrap break-words [unicode-bidi:plaintext]">
          {text}
        </span>
        <span className="float-end ms-2 mt-1.5 flex translate-y-0.5 items-center gap-0.5 text-[10px] text-slate-500" dir="ltr">
          {createdAt && clockTime(createdAt)}
          {fromFirm && delivery && <Ticks status={delivery} />}
        </span>
      </div>
      {fromFirm && buttons && buttons.length > 0 && (
        <div className={cx("mt-1 flex w-full max-w-[86%] flex-col gap-1", compact && "max-w-full")}>
          {buttons.map((b) => (
            <button
              key={b.id}
              type="button"
              disabled={buttonsDisabled || !onButton}
              onClick={() => onButton?.(b)}
              dir="auto"
              className={cx(
                "rounded-lg bg-white px-3 py-1.5 text-center text-[13px] font-medium shadow-[0_1px_0.5px_rgba(0,0,0,0.13)] transition",
                buttonsDisabled || !onButton ? "cursor-default text-slate-400" : "text-wa-link hover:bg-slate-50 active:scale-[0.99]",
              )}
            >
              {b.title}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
