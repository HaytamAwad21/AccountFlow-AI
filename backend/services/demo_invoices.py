"""Renders realistic tax-invoice PNGs for the WhatsApp simulator's one-click demo buttons.

Each image embeds a machine-readable text layer (PNG tEXt chunk `accountflow_ocr`)
that the offline Vision simulator reads in place of a cloud OCR call. The blurry
scenario is genuinely blurred, so the real Laplacian blur detector rejects it too.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, features
from PIL.PngImagePlugin import PngInfo

from config import settings

META_KEY = "accountflow_ocr"
SCENARIOS = ("clear", "blurry", "missing_number", "wrong_supplier", "bad_math", "missing_allocation", "invalid_tax_id")

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]
BOLD_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]
_HAS_RAQM = features.check("raqm")
_RTL = re.compile(r"[\u0590-\u06FF]")


def _find_font(candidates: list[str]) -> str | None:
    for path in candidates:
        if Path(path).exists():
            return path
    return None


_FONT_PATH = _find_font(FONT_CANDIDATES)
_BOLD_PATH = _find_font(BOLD_CANDIDATES) or _FONT_PATH


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    path = _BOLD_PATH if bold else _FONT_PATH
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _visual(text: str) -> str:
    """Without libraqm Pillow draws RTL text in logical order; reverse it so it reads correctly."""
    if _HAS_RAQM or not _RTL.search(text):
        return text
    return text[::-1]


def parse_amount(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^\d.\-]", "", str(value).replace(",", ""))
    try:
        return float(cleaned) if cleaned not in ("", "-", ".") else None
    except ValueError:
        return None


def _stable_number(seed: str, lo: int, hi: int) -> int:
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    return lo + h % (hi - lo + 1)


def generate_invoice_image(
    *,
    scenario: str,
    supplier_name: str,
    invoice_number: str | None,
    client_company: str,
    amount_total: float | None = None,
    invoice_date: str | None = None,
    business_id: str | None = None,
    dest_dir: Path | None = None,
    vat_rate: float | None = None,
    allocation_threshold: float | None = None,
) -> tuple[Path, dict]:
    """`vat_rate` is a fraction (0.18). Invoices whose net reaches `allocation_threshold` (₪)
    carry a 9-digit מספר הקצאה, except in the `missing_allocation` scenario."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario}'. Use one of {SCENARIOS}.")
    dest_dir = dest_dir or settings.upload_dir
    dest_dir.mkdir(parents=True, exist_ok=True)

    seed = f"{supplier_name}|{invoice_number}|{client_company}"
    supplier_name = supplier_name or "Supplier Ltd."
    if scenario == "wrong_supplier":
        supplier_name = "Global Trade Imports Ltd." if "global trade" not in supplier_name.lower() else "Northern Office Supply Ltd."
    invoice_number = invoice_number or str(_stable_number(seed, 10000, 99999))
    business_id = business_id or str(_stable_number(seed + "bid", 510000000, 519999999))
    if scenario == "invalid_tax_id":
        business_id = business_id[:6]
    invoice_date = invoice_date or date.today().strftime("%d/%m/%Y")

    vat_rate = settings.vat_rate if vat_rate is None else vat_rate
    allocation_threshold = settings.allocation_number_threshold_nis if allocation_threshold is None else allocation_threshold
    total = round(amount_total, 2) if amount_total else float(_stable_number(seed + "amt", 350, 9800))
    net = round(total / (1 + vat_rate), 2)
    vat = round(total - net, 2)
    printed_total = round(total + 137.0, 2) if scenario == "bad_math" else total
    if scenario == "missing_allocation" and net < allocation_threshold:
        # make sure the invoice crosses the threshold so the missing number matters
        net = round(allocation_threshold * 1.25, 2)
        vat = round(net * vat_rate, 2)
        total = printed_total = round(net + vat, 2)
    allocation_number = None
    if net >= allocation_threshold and scenario != "missing_allocation":
        allocation_number = str(_stable_number(seed + "alloc", 100000000, 999999999))

    width, height = 900, 1250
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    f_title, f_big, f_mid, f_small = _font(40, True), _font(30, True), _font(22), _font(18)

    # Header band with supplier identity
    d.rectangle([0, 0, width, 150], fill=(22, 50, 92))
    d.text((40, 32), _visual(supplier_name), font=f_big, fill="white")
    d.text((40, 82), "12 HaMasger St., Tel Aviv  |  Tel 03-555-0199", font=f_small, fill=(210, 222, 240))
    d.text((40, 110), _visual(f"Business ID / ע.מ: {business_id}"), font=f_small, fill=(210, 222, 240))

    title = "TAX INVOICE"
    if _FONT_PATH:
        title = f"TAX INVOICE  |  {_visual('חשבונית מס')}"
    d.text((40, 185), title, font=f_title, fill=(15, 23, 42))
    d.line([40, 245, width - 40, 245], fill=(15, 23, 42), width=3)

    y = 270
    if scenario != "missing_number":
        d.text((40, y), f"Invoice No.: {invoice_number}", font=f_mid, fill=(15, 23, 42))
    d.text((520, y), f"Date: {invoice_date}", font=f_mid, fill=(15, 23, 42))
    y += 45
    d.text((40, y), _visual(f"Bill to: {client_company}"), font=f_mid, fill=(15, 23, 42))
    if allocation_number:
        d.text((520, y), _visual(f"מספר הקצאה: {allocation_number}"), font=f_mid, fill=(15, 23, 42))
    y += 70

    # Line items
    d.rectangle([40, y, width - 40, y + 44], fill=(232, 238, 247))
    for x, label in ((55, "Description"), (520, "Qty"), (610, "Unit"), (740, "Amount")):
        d.text((x, y + 10), label, font=f_small, fill=(15, 23, 42))
    y += 56
    shares = (0.5, 0.3, 0.2)
    items = ("Materials & supplies", "Professional services", "Delivery & handling")
    for desc, share in zip(items, shares):
        line_total = round(net * share, 2)
        qty = _stable_number(seed + desc, 1, 6)
        d.text((55, y), desc, font=f_small, fill=(30, 41, 59))
        d.text((525, y), str(qty), font=f_small, fill=(30, 41, 59))
        d.text((610, y), f"{line_total / qty:,.2f}", font=f_small, fill=(30, 41, 59))
        d.text((740, y), f"{line_total:,.2f}", font=f_small, fill=(30, 41, 59))
        y += 40
        d.line([40, y - 8, width - 40, y - 8], fill=(226, 232, 240), width=1)

    y += 40
    for label, val in (("Total before VAT", net), (f"VAT {vat_rate * 100:g}%", vat), ("TOTAL (ILS)", printed_total)):
        bold = label.startswith("TOTAL")
        d.text((470, y), label, font=_font(24, bold), fill=(15, 23, 42))
        d.text((720, y), f"{val:,.2f}", font=_font(24, bold), fill=(15, 23, 42))
        y += 44
    d.line([460, y, width - 40, y], fill=(15, 23, 42), width=2)

    d.text((40, height - 150), "Payment: bank transfer 30 days. Original document — computerized invoice.", font=f_small, fill=(71, 85, 105))
    d.text((40, height - 115), "Thank you for your business!", font=f_mid, fill=(22, 50, 92))
    d.rectangle([0, height - 40, width, height], fill=(22, 50, 92))

    legible = True
    if scenario == "blurry":
        img = img.rotate(4, expand=False, fillcolor=(240, 240, 236), resample=Image.BICUBIC)
        small = img.resize((width // 4, height // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3))
        img = small.resize((width, height), Image.BICUBIC).filter(ImageFilter.GaussianBlur(7))
        legible = False

    meta = {
        "scenario": scenario,
        "legible": legible,
        "document_title": "Tax Invoice / חשבונית מס",
        "has_tax_invoice_header": True,
        "invoice_number": None if scenario == "missing_number" else invoice_number,
        "supplier_name": supplier_name,
        "business_id": business_id,
        "allocation_number": allocation_number,
        "invoice_date": invoice_date,
        "net_amount": net,
        "vat_amount": vat,
        "total_amount": printed_total,
        "currency": "ILS",
    }
    info = PngInfo()
    info.add_text(META_KEY, json.dumps(meta, ensure_ascii=False))
    path = dest_dir / f"demo_{scenario}_{uuid.uuid4().hex[:10]}.png"
    img.save(path, format="PNG", pnginfo=info)
    return path, meta
