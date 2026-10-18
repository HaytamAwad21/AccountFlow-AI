"""Engine D endpoints: bulk "Tax is ready" broadcasts."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import BulkTaxCampaign, User
from routers.deps import client_ip, require_user
from services.activity import log_activity
from schemas import BulkUploadResult, CampaignDetail, CampaignOut, campaign_out
from services.bulk_tax import campaign_stats, demo_batch_rows, read_sheet, run_bulk_campaign, sample_sheet
from services.ticket_engine import EngineError

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


@router.get("", response_model=list[CampaignOut])
def list_campaigns(db: Session = Depends(get_db), _user: User = Depends(require_user)):
    campaigns = db.scalars(select(BulkTaxCampaign).order_by(BulkTaxCampaign.created_at.desc())).all()
    return [campaign_out(c, campaign_stats(c)) for c in campaigns]


@router.get("/sample-sheet")
def download_sample(format: str = Query("csv", pattern="^(csv|xlsx)$"), _user: User = Depends(require_user)):
    content, filename, media_type = sample_sheet(format)
    return Response(content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{campaign_id}", response_model=CampaignDetail)
def get_campaign(campaign_id: int, db: Session = Depends(get_db), _user: User = Depends(require_user)):
    campaign = db.get(BulkTaxCampaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "הקמפיין לא נמצא")
    return campaign_out(campaign, campaign_stats(campaign), detail=True)


def _finish(db: Session, result: dict, user: User, ip: str, source: str) -> BulkUploadResult:
    campaign = result["campaign"]
    log_activity(db, user, "CAMPAIGN_SENT", f"נשלחה תפוצת ”{campaign.title}“ ל-{result['sent']} לקוחות ({source})",
                 entity_type="campaign", entity_id=campaign.id,
                 details={"errors": len(result["errors"]), "created_clients": result["created_clients"]}, ip_address=ip)
    db.commit()
    return BulkUploadResult(
        campaign=campaign_out(campaign, campaign_stats(campaign), detail=True),
        errors=result["errors"],
        created_clients=result["created_clients"],
        sent=result["sent"],
    )


@router.post("/bulk-tax-upload", response_model=BulkUploadResult, status_code=201)
async def bulk_tax_upload(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    content = await file.read()
    try:
        rows = read_sheet(content, file.filename or "upload.csv")
        result = run_bulk_campaign(db, rows, title=title or None, worker_id=user.id)
    except EngineError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, str(exc)) from exc
    return _finish(db, result, user, client_ip(request), f"קובץ {file.filename}")


@router.post("/demo-batch", response_model=BulkUploadResult, status_code=201)
def demo_batch(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    rows = demo_batch_rows(db, limit=8)
    result = run_bulk_campaign(db, rows, worker_id=user.id)
    return _finish(db, result, user, client_ip(request), "קבוצת הדגמה")
