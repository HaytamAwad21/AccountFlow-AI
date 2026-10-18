"""Vision AI receipt validator.

Providers:
  * openai  – gpt-4o-mini vision (images + PDFs) via the Chat Completions API
  * gemini  – gemini-2.5-flash via the Generative Language API
  * local   – deterministic offline simulator: real Laplacian blur detection on any
              image, plus the embedded text layer of simulator-generated invoices.

Every provider produces the same *extraction*; `validate_extraction` then applies the
accounting checks (clarity, document type, supplier match, math integrity at the office's
live VAT rate) plus the Israeli Tax Authority rules: a 9-digit supplier ח.פ / ע.מ and a
9-digit מספר הקצאה on invoices at or above the allocation threshold (before VAT).
"""
from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
from difflib import SequenceMatcher
from pathlib import Path

import httpx
from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from config import settings
from services.demo_invoices import META_KEY, parse_amount
from services.i18n import join_reasons, t

log = logging.getLogger("accountflow.vision")

SUPPLIER_MATCH_THRESHOLD = 0.6
NINE_DIGITS = re.compile(r"^\d{9}$")
TAX_HEADER_PATTERNS = ("tax invoice", "חשבונית מס", "فاتورة ضريبية", "חשבונית מס קבלה")

LLM_PROMPT = """You are the document-verification engine of an Israeli bookkeeping firm.
Analyze the attached supplier document and return ONLY one JSON object with these keys:
  "is_legible": boolean - true only if the key text (title, supplier, invoice number, amounts) can be read reliably,
  "document_title": string - the title exactly as printed (e.g. "חשבונית מס", "Tax Invoice", "קבלה"),
  "has_tax_invoice_header": boolean - true only if the document is a TAX INVOICE (Tax Invoice / חשבונית מס /
      חשבונית מס קבלה / فاتورة ضريبية); false for receipts-only, quotes, delivery notes, orders or payment slips,
  "invoice_number": string or null,
  "supplier_name": string or null - the issuing business,
  "business_id": string or null - the supplier's VAT / company number (עוסק מורשה / ח.פ),
  "allocation_number": string or null - the Tax Authority allocation number (מספר הקצאה), if printed,
  "invoice_date": string or null - YYYY-MM-DD,
  "net_amount": number or null - total before VAT,
  "vat_amount": number or null,
  "total_amount": number or null - total including VAT,
  "currency": string or null,
  "confidence": number between 0 and 1.
Never guess: use null for anything not clearly visible."""


# ── helpers ──────────────────────────────────────────────────────────────────

def active_provider() -> str:
    choice = (settings.vision_provider or "auto").lower()
    if choice == "openai" and settings.openai_api_key:
        return "openai"
    if choice == "gemini" and settings.gemini_api_key:
        return "gemini"
    if choice == "auto":
        if settings.openai_api_key:
            return "openai"
        if settings.gemini_api_key:
            return "gemini"
    return "local"


def guess_mime(path: str | Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def measure_blur(img: Image.Image) -> float:
    """Variance of the Laplacian (FIND_EDGES kernel) on a width-normalized grayscale copy.

    Sharp documents with crisp text score in the hundreds/thousands; blurry phone
    photos collapse toward zero.
    """
    gray = ImageOps.exif_transpose(img).convert("L")
    target_w = 900
    if gray.width != target_w:
        gray = gray.resize((target_w, max(1, int(gray.height * target_w / gray.width))), Image.LANCZOS)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    # FIND_EDGES leaves a bright 1px frame at the image border; crop it so it doesn't mask blur.
    if edges.width > 8 and edges.height > 8:
        edges = edges.crop((3, 3, edges.width - 3, edges.height - 3))
    return round(float(ImageStat.Stat(edges).var[0]), 2)


_SUPPLIER_NOISE = re.compile(
    r"\b(ltd|limited|inc|llc|co|corp|company|group|בע\"?מ|בעמ|שותפות|شركة|م\.?ض|ش\.?م)\b|[^\w\s]",
    re.IGNORECASE | re.UNICODE,
)


def normalize_supplier(name: str | None) -> str:
    if not name:
        return ""
    cleaned = _SUPPLIER_NOISE.sub(" ", name.lower())
    return " ".join(cleaned.split())


def supplier_similarity(expected: str | None, detected: str | None) -> float:
    a, b = normalize_supplier(expected), normalize_supplier(detected)
    if not a or not b:
        return 0.0
    if a == b or a in b or b in a:
        return 1.0
    ratio = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    jaccard = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    return round(max(ratio, jaccard), 3)


def _fmt_money(v: float | None) -> str:
    return "—" if v is None else f"{v:,.2f}"


def normalize_id(value: str | None) -> str:
    """Strip spaces, dashes and dots that people type inside ID numbers (514-782-301 -> 514782301)."""
    return re.sub(r"[\s\-.]", "", value or "")


def is_nine_digits(value: str | None) -> bool:
    return bool(NINE_DIGITS.match(normalize_id(value)))


def _empty_extraction(provider: str) -> dict:
    return {
        "provider": provider,
        "simulated": provider == "local",
        "is_legible": False,
        "blur_score": None,
        "document_title": None,
        "has_tax_invoice_header": False,
        "invoice_number": None,
        "supplier_name": None,
        "business_id": None,
        "allocation_number": None,
        "invoice_date": None,
        "net_amount": None,
        "vat_amount": None,
        "total_amount": None,
        "currency": None,
        "confidence": 0.0,
        "manual_review_required": False,
        "unreadable_file": False,
        "provider_note": "",
    }


def _clean_str(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _normalize_fields(ex: dict, data: dict) -> dict:
    ex["document_title"] = _clean_str(data.get("document_title"))
    header = data.get("has_tax_invoice_header")
    if header is None and ex["document_title"]:
        header = any(p in ex["document_title"].lower() for p in TAX_HEADER_PATTERNS)
    ex["has_tax_invoice_header"] = bool(header)
    ex["invoice_number"] = _clean_str(data.get("invoice_number"))
    ex["supplier_name"] = _clean_str(data.get("supplier_name"))
    ex["business_id"] = _clean_str(data.get("business_id"))
    ex["allocation_number"] = _clean_str(data.get("allocation_number"))
    ex["invoice_date"] = _clean_str(data.get("invoice_date"))
    ex["net_amount"] = parse_amount(data.get("net_amount"))
    ex["vat_amount"] = parse_amount(data.get("vat_amount"))
    ex["total_amount"] = parse_amount(data.get("total_amount"))
    ex["currency"] = _clean_str(data.get("currency")) or "ILS"
    return ex


# ── providers ────────────────────────────────────────────────────────────────

def _local_extract(path: Path, mime: str) -> dict:
    ex = _empty_extraction("local")
    if mime == "application/pdf":
        ex.update(is_legible=True, manual_review_required=True, confidence=0.3,
                  provider_note="PDF התקבל במצב לא מקוון: לא הוגדר מפתח Vision API, הועבר לבדיקת פקיד.")
        return ex
    try:
        with Image.open(path) as img:
            img.load()
            meta_raw = img.info.get(META_KEY)
            ex["blur_score"] = measure_blur(img)
            small = min(img.size) < 320
    except (UnidentifiedImageError, OSError):
        ex["unreadable_file"] = True
        ex["provider_note"] = "לא ניתן לפענח את הקובץ כתמונה."
        return ex

    sharp = ex["blur_score"] >= settings.blur_threshold and not small
    if meta_raw:
        data = json.loads(meta_raw)
        _normalize_fields(ex, data)
        ex["is_legible"] = bool(data.get("legible", True)) and sharp
        ex["confidence"] = 0.97 if ex["is_legible"] else 0.31
        ex["provider_note"] = f"הסימולטור הלא מקוון קרא את שכבת הטקסט המוטמעת (תרחיש: {data.get('scenario')})."
    else:
        ex["is_legible"] = sharp
        ex["confidence"] = 0.55 if sharp else 0.2
        ex["manual_review_required"] = sharp
        ex["provider_note"] = (
            "מצב לא מקוון: בדיקת הטשטוש עברה; לא הוגדר מפתח Vision API לחילוץ שדות, הועבר לבדיקת פקיד."
            if sharp else "מצב לא מקוון: בדיקת הטשטוש נכשלה."
        )
    return ex


def _file_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def _parse_llm_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1] if start >= 0 else text)


def _openai_extract(path: Path, mime: str) -> dict:
    if mime == "application/pdf":
        part = {"type": "file", "file": {"filename": path.name, "file_data": f"data:{mime};base64,{_file_b64(path)}"}}
    else:
        part = {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{_file_b64(path)}", "detail": "high"}}
    payload = {
        "model": settings.openai_model,
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "messages": [
            {"role": "system", "content": LLM_PROMPT},
            {"role": "user", "content": [{"type": "text", "text": "Verify this supplier document."}, part]},
        ],
    }
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json=payload,
        timeout=settings.vision_timeout_seconds,
    )
    resp.raise_for_status()
    data = _parse_llm_json(resp.json()["choices"][0]["message"]["content"])
    ex = _normalize_fields(_empty_extraction("openai"), data)
    ex["is_legible"] = bool(data.get("is_legible"))
    ex["confidence"] = float(data.get("confidence") or 0.0)
    ex["provider_note"] = f"חולץ באמצעות OpenAI {settings.openai_model}."
    return ex


def _gemini_extract(path: Path, mime: str) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": LLM_PROMPT}, {"inline_data": {"mime_type": mime, "data": _file_b64(path)}}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }
    resp = httpx.post(url, headers={"x-goog-api-key": settings.gemini_api_key}, json=payload,
                      timeout=settings.vision_timeout_seconds)
    resp.raise_for_status()
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = _parse_llm_json(text)
    ex = _normalize_fields(_empty_extraction("gemini"), data)
    ex["is_legible"] = bool(data.get("is_legible"))
    ex["confidence"] = float(data.get("confidence") or 0.0)
    ex["provider_note"] = f"חולץ באמצעות Google {settings.gemini_model}."
    return ex


def extract_invoice_fields(path: str | Path, mime: str | None = None, force_local: bool = False) -> dict:
    path = Path(path)
    mime = mime or guess_mime(path)
    provider = "local" if force_local else active_provider()

    # Simulator-generated images always use their embedded layer so demos stay deterministic.
    if provider != "local" and mime == "image/png":
        try:
            with Image.open(path) as img:
                if META_KEY in img.info:
                    provider = "local"
        except (UnidentifiedImageError, OSError):
            pass

    if provider == "local":
        return _local_extract(path, mime)
    try:
        ex = _openai_extract(path, mime) if provider == "openai" else _gemini_extract(path, mime)
        if mime.startswith("image/"):
            try:
                with Image.open(path) as img:
                    ex["blur_score"] = measure_blur(img)
            except (UnidentifiedImageError, OSError):
                pass
        return ex
    except Exception as exc:  # network / quota / parsing problems fall back to offline mode
        log.warning("Vision provider %s failed (%s); using offline simulator", provider, exc)
        ex = _local_extract(path, mime)
        ex["provider_note"] = f"{provider} נכשל ({type(exc).__name__}); " + ex["provider_note"]
        return ex


# ── validation ───────────────────────────────────────────────────────────────

def validate_extraction(
    ex: dict,
    expected_supplier: str | None = None,
    expected_invoice_number: str | None = None,
    lang: str = "he",
    vat_rate: float = settings.vat_rate,
    allocation_threshold: float = settings.allocation_number_threshold_nis,
) -> dict:
    """`vat_rate` is a fraction (0.18); `allocation_threshold` is in ₪ before VAT."""
    codes: list[str] = []
    warnings: list[str] = []
    checks = {"clarity": None, "document_type": None, "supplier_match": None, "math_integrity": None,
              "tax_id": None, "allocation_number": None}
    reason_kwargs: dict[str, dict] = {}

    is_blurry = not ex.get("is_legible") and not ex.get("unreadable_file")
    supplier_score = None
    supplier_match = None
    math_valid = None
    vat_rate_ok = None
    allocation_required = None

    if ex.get("unreadable_file"):
        codes.append("unreadable_file")
        checks["clarity"] = False
    elif is_blurry:
        codes.append("blurry")
        checks["clarity"] = False
    elif ex.get("manual_review_required"):
        checks["clarity"] = True
    else:
        checks["clarity"] = True

        doc_ok = bool(ex.get("has_tax_invoice_header")) and bool(ex.get("invoice_number"))
        checks["document_type"] = doc_ok
        if not ex.get("has_tax_invoice_header"):
            codes.append("not_tax_invoice")
        if not ex.get("invoice_number"):
            codes.append("missing_number")

        detected = ex.get("supplier_name")
        if expected_supplier:
            supplier_score = supplier_similarity(expected_supplier, detected)
            supplier_match = supplier_score >= SUPPLIER_MATCH_THRESHOLD
            checks["supplier_match"] = supplier_match
            if detected and not supplier_match:
                codes.append("wrong_supplier")
                reason_kwargs["wrong_supplier"] = {"detected": detected, "expected": expected_supplier}
            elif not detected:
                warnings.append("supplier_unreadable")
        else:
            checks["supplier_match"] = bool(detected)

        net, vat, total = ex.get("net_amount"), ex.get("vat_amount"), ex.get("total_amount")
        if None in (net, vat, total):
            codes.append("amounts_missing")
            math_valid = False
        else:
            tolerance = max(1.0, abs(total) * 0.005)
            math_valid = abs((net + vat) - total) <= tolerance
            vat_rate_ok = abs(vat - net * vat_rate) <= max(1.0, abs(net) * 0.005)
            if not math_valid:
                codes.append("math_mismatch")
                reason_kwargs["math_mismatch"] = {"net": _fmt_money(net), "vat": _fmt_money(vat), "total": _fmt_money(total)}
            elif not vat_rate_ok:
                codes.append("vat_rate_mismatch")
                reason_kwargs["vat_rate_mismatch"] = {"rate": f"{vat_rate * 100:g}"}
                math_valid = False
        checks["math_integrity"] = math_valid

        # Israeli Tax Authority: the supplier's ח.פ / ע.מ must be exactly 9 digits
        business_id = ex.get("business_id")
        if not business_id:
            warnings.append("business_id_missing")
        elif not is_nine_digits(business_id):
            codes.append("invalid_tax_id")
            checks["tax_id"] = False
        else:
            checks["tax_id"] = True

        # Israeli Tax Authority: a 9-digit allocation number (מספר הקצאה) at or above the threshold
        if net is not None:
            allocation_required = net >= allocation_threshold
            allocation = ex.get("allocation_number")
            if allocation_required:
                reason_kwargs["missing_allocation"] = {"threshold": f"{allocation_threshold:,.0f}"}
                if not allocation:
                    codes.append("missing_allocation")
                    checks["allocation_number"] = False
                elif not is_nine_digits(allocation):
                    codes.append("invalid_allocation")
                    checks["allocation_number"] = False
                else:
                    checks["allocation_number"] = True
            elif allocation:
                checks["allocation_number"] = is_nine_digits(allocation)

        if expected_invoice_number and ex.get("invoice_number") and \
                re.sub(r"\W", "", str(expected_invoice_number)) != re.sub(r"\W", "", str(ex["invoice_number"])):
            warnings.append("invoice_number_differs_from_request")

    if ex.get("manual_review_required") and not codes:
        is_valid = None
    else:
        is_valid = not codes

    confidence = float(ex.get("confidence") or 0.0)
    if warnings and is_valid:
        confidence = round(max(0.0, confidence - 0.05 * len(warnings)), 2)

    reasons_local = [t(f"reason_{c}", lang, **reason_kwargs.get(c, {})) for c in codes]
    reasons_he = [t(f"reason_{c}", "he", **reason_kwargs.get(c, {})) for c in codes]

    return {
        "is_valid": is_valid,
        "status": "PASSED" if is_valid else ("MANUAL_REVIEW" if is_valid is None else "FAILED"),
        "is_blurry": is_blurry,
        "blur_score": ex.get("blur_score"),
        "has_tax_invoice_header": bool(ex.get("has_tax_invoice_header")),
        "document_title": ex.get("document_title"),
        "detected_supplier": ex.get("supplier_name"),
        "detected_invoice_num": ex.get("invoice_number"),
        "detected_business_id": ex.get("business_id"),
        "invoice_number": ex.get("invoice_number"),
        "supplier_name": ex.get("supplier_name"),
        "business_id": ex.get("business_id"),
        "allocation_number": ex.get("allocation_number"),
        "allocation_required": allocation_required,
        "allocation_threshold": allocation_threshold,
        "vat_rate_applied": round(vat_rate * 100, 2),
        "invoice_date": ex.get("invoice_date"),
        "net_amount": ex.get("net_amount"),
        "vat_amount": ex.get("vat_amount"),
        "total_amount": ex.get("total_amount"),
        "currency": ex.get("currency"),
        "math_valid": math_valid,
        "vat_rate_ok": vat_rate_ok,
        "supplier_match": supplier_match,
        "supplier_match_score": supplier_score,
        "expected_supplier": expected_supplier,
        "expected_invoice_number": expected_invoice_number,
        "confidence_score": confidence,
        "checks": checks,
        "rejection_codes": codes,
        "warnings": warnings,
        "rejection_reason": join_reasons(reasons_local, lang) or None,
        "rejection_reason_he": join_reasons(reasons_he, "he") or None,
        "manual_review_required": bool(ex.get("manual_review_required")),
        "provider": ex.get("provider"),
        "simulated": bool(ex.get("simulated")),
        "provider_note": ex.get("provider_note", ""),
        "extraction": ex,
    }


def verify_invoice_image(
    file_path: str | Path,
    expected_supplier: str | None = None,
    expected_invoice_number: str | None = None,
    lang: str = "he",
    mime: str | None = None,
    vat_rate: float = settings.vat_rate,
    allocation_threshold: float = settings.allocation_number_threshold_nis,
) -> dict:
    ex = extract_invoice_fields(file_path, mime)
    return validate_extraction(ex, expected_supplier, expected_invoice_number, lang, vat_rate, allocation_threshold)


EDITABLE_FIELDS = ("invoice_number", "supplier_name", "business_id", "allocation_number", "invoice_date",
                   "net_amount", "vat_amount", "total_amount")


def revalidate_with_overrides(
    ocr: dict | None,
    overrides: dict,
    lang: str = "he",
    vat_rate: float = settings.vat_rate,
    allocation_threshold: float = settings.allocation_number_threshold_nis,
) -> dict:
    """Clerk corrected or completed the extracted fields by hand; re-run the accounting checks."""
    ex = dict((ocr or {}).get("extraction") or _empty_extraction("clerk"))
    for field in EDITABLE_FIELDS:
        if field in overrides and overrides[field] is not None:
            value = overrides[field]
            ex[field] = parse_amount(value) if field.endswith("_amount") else (str(value).strip() or None)
    ex.update(is_legible=True, unreadable_file=False, manual_review_required=False, has_tax_invoice_header=True,
              provider_note=(ex.get("provider_note") or "") + " השדות אומתו ידנית על ידי הצוות.")
    ex["confidence"] = max(float(ex.get("confidence") or 0), 0.99)
    ex["provider"] = f"{ex.get('provider') or 'local'}+clerk"
    result = validate_extraction(ex, (ocr or {}).get("expected_supplier"), (ocr or {}).get("expected_invoice_number"), lang,
                                 vat_rate, allocation_threshold)
    result["clerk_edited"] = True
    return result
