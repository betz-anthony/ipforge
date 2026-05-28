"""GITOPS-001 — plan/apply API."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.deps import require_operator
from app.database import get_db
from app.gitops import parse, plan, apply, GitopsError
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


async def _parse_body(request: Request) -> dict:
    raw = (await request.body()).decode("utf-8")
    if not raw.strip():
        raise HTTPException(400, "Empty body")
    try:
        return parse(raw)
    except GitopsError as e:
        raise HTTPException(400, str(e))


@router.post("/plan")
async def gitops_plan(
    request: Request,
    _: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    doc = await _parse_body(request)
    return {"source": doc["source"], "plan": plan(doc, db)}


@router.post("/apply")
async def gitops_apply(
    request: Request,
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    doc = await _parse_body(request)
    return apply(doc, db, current_user)
