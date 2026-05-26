"""IP-REQUEST-001 — see docs/superpowers/specs/2026-05-24-ip-request-design.md"""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import get_current_user
from app.core.audit import write_audit
from app.core.mac import normalize_mac_optional
from app.core.validators import validate_hostname
from app.alerting.emit import emit
from app.models.user import User
from app.models.subnet import Subnet
from app.models.ip_request import IPRequest

router = APIRouter()


class RequestIn(BaseModel):
    subnet_id: int
    hostname: str
    mac_address: str | None = None
    purpose: str = Field(min_length=5, max_length=2000)

    @field_validator("hostname")
    @classmethod
    def _hostname(cls, v: str) -> str:
        return validate_hostname(v)

    @field_validator("mac_address")
    @classmethod
    def _mac(cls, v: str | None) -> str | None:
        return normalize_mac_optional(v)


class RequestOut(BaseModel):
    id: int
    requester_username: str
    subnet_id: int | None
    subnet_cidr: str | None
    hostname: str
    mac_address: str | None
    purpose: str
    status: Literal["pending", "approved", "denied"]
    reviewer_username: str | None
    reviewed_at: str | None
    review_notes: str | None
    allocated_ip: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_orm_obj(cls, r: IPRequest, subnet_cidr: str | None) -> "RequestOut":
        return cls(
            id=r.id, requester_username=r.requester_username,
            subnet_id=r.subnet_id, subnet_cidr=subnet_cidr,
            hostname=r.hostname, mac_address=r.mac_address, purpose=r.purpose,
            status=r.status, reviewer_username=r.reviewer_username,
            reviewed_at=r.reviewed_at.isoformat() if r.reviewed_at else None,
            review_notes=r.review_notes, allocated_ip=r.allocated_ip,
            created_at=r.created_at.isoformat(), updated_at=r.updated_at.isoformat(),
        )


class EligibleSubnetOut(BaseModel):
    id: int
    cidr: str
    name: str | None
    description: str | None


def _block_scoped(user: User) -> None:
    if user.role == "scoped":
        raise HTTPException(403, "scoped users cannot use the request workflow")


def _to_out(db: Session, r: IPRequest) -> RequestOut:
    cidr = None
    if r.subnet_id:
        s = db.get(Subnet, r.subnet_id)
        cidr = s.cidr if s else None
    return RequestOut.from_orm_obj(r, cidr)


@router.post("", response_model=RequestOut, status_code=201)
def submit_request(
    body: RequestIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _block_scoped(user)
    subnet = db.get(Subnet, body.subnet_id)
    if not subnet:
        raise HTTPException(400, "subnet not found")
    if not subnet.request_eligible:
        raise HTTPException(400, "subnet is not request-eligible")
    dup = (
        db.query(IPRequest)
        .filter(
            IPRequest.requester_username == user.username,
            IPRequest.subnet_id == body.subnet_id,
            IPRequest.hostname == body.hostname,
            IPRequest.status == "pending",
        )
        .first()
    )
    if dup:
        raise HTTPException(409, "you already have a pending request for this hostname in this subnet")
    r = IPRequest(
        requester_username=user.username,
        subnet_id=body.subnet_id,
        hostname=body.hostname,
        mac_address=body.mac_address,
        purpose=body.purpose,
        status="pending",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    emit(
        "ip_request_submitted",
        f"ip_request:{r.id}",
        {
            "request_id": r.id, "requester": user.username,
            "subnet_cidr": subnet.cidr, "hostname": r.hostname,
            "purpose": r.purpose,
        },
    )
    write_audit(db, user.username, "create", "ip_request", str(r.id), r.hostname,
                after={"hostname": r.hostname, "subnet_id": r.subnet_id})
    return _to_out(db, r)


@router.get("", response_model=list[RequestOut])
def list_requests(
    status: Literal["pending", "approved", "denied"] | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _block_scoped(user)
    q = db.query(IPRequest)
    if user.role == "requester":
        q = q.filter(IPRequest.requester_username == user.username)
    if status:
        q = q.filter(IPRequest.status == status)
    rows = q.order_by(desc(IPRequest.created_at)).limit(min(limit, 1000)).all()

    # Bulk-load subnets to avoid N+1
    subnet_ids = {r.subnet_id for r in rows if r.subnet_id is not None}
    subnet_map: dict[int, str] = {}
    if subnet_ids:
        subnet_map = {
            s.id: s.cidr
            for s in db.query(Subnet).filter(Subnet.id.in_(subnet_ids)).all()
        }
    return [RequestOut.from_orm_obj(r, subnet_map.get(r.subnet_id)) for r in rows]


@router.get("/eligible-subnets", response_model=list[EligibleSubnetOut])
def eligible_subnets(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _block_scoped(user)
    rows = db.query(Subnet).filter(Subnet.request_eligible == True).order_by(Subnet.cidr).all()  # noqa: E712
    return [
        EligibleSubnetOut(
            id=s.id, cidr=s.cidr,
            name=getattr(s, "name", None),
            description=getattr(s, "description", None),
        )
        for s in rows
    ]


@router.get("/{request_id}", response_model=RequestOut)
def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _block_scoped(user)
    r = db.get(IPRequest, request_id)
    if not r:
        raise HTTPException(404, "not found")
    if user.role == "requester" and r.requester_username != user.username:
        raise HTTPException(403, "not your request")
    return _to_out(db, r)
