"""IP-REQUEST-001 — see docs/superpowers/specs/2026-05-24-ip-request-design.md"""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import get_current_user, require_operator
from app.core.audit import write_audit
from app.core.mac import normalize_mac_optional
from app.core.validators import validate_hostname
from app.core.time import utcnow
from app.alerting.emit import emit
from app.models.user import User
from app.models.subnet import Subnet
from app.models.ip_request import IPRequest, RequestStatus
from app.api.allocation import _do_allocate, _BYPASS_ACCESS, AllocateRequest

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
    status: RequestStatus
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
    status: RequestStatus | None = None,
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


class ApproveIn(BaseModel):
    description: str | None = None
    register_dns: bool = False
    register_dhcp: bool = False
    dns_zone: str | None = None
    dns_provider: str | None = None
    dhcp_provider: str | None = None
    register_ptr: bool = False


@router.put("/{request_id}/approve", response_model=RequestOut)
def approve_request(
    request_id: int,
    body: ApproveIn = ApproveIn(),
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
):
    r = db.get(IPRequest, request_id)
    if not r:
        raise HTTPException(404, "not found")
    if r.status != "pending":
        raise HTTPException(409, f"request is already {r.status}")
    if r.subnet_id is None:
        raise HTTPException(409, "request's subnet has been deleted")
    subnet = db.get(Subnet, r.subnet_id)
    if not subnet:
        raise HTTPException(409, "request's subnet has been deleted")

    allocate_req = AllocateRequest(
        hostname=r.hostname,
        description=body.description or f"From IP request #{r.id}",
        mac_address=r.mac_address,
        register_dns=body.register_dns,
        register_dhcp=body.register_dhcp,
        dns_zone=body.dns_zone,
        dns_provider=body.dns_provider,
        dhcp_provider=body.dhcp_provider,
        register_ptr=body.register_ptr,
    )
    # access=_BYPASS_ACCESS: operator-gated route, authorization already satisfied
    result = _do_allocate(db, r.subnet_id, allocate_req, user, access=_BYPASS_ACCESS)

    r.status = "approved"
    r.reviewer_username = user.username
    r.reviewed_at = utcnow()
    r.allocated_ip = result["address"]
    r.allocated_id = result["id"]
    db.commit()
    db.refresh(r)

    emit(
        "ip_request_resolved",
        f"ip_request:{r.id}",
        {
            "request_id": r.id, "status": "approved",
            "requester": r.requester_username, "reviewer": user.username,
            "subnet_cidr": subnet.cidr, "hostname": r.hostname,
            "allocated_ip": r.allocated_ip,
        },
    )
    write_audit(db, user.username, "update", "ip_request", str(r.id), r.hostname,
                after={"status": "approved", "allocated_ip": r.allocated_ip})
    return RequestOut.from_orm_obj(r, subnet.cidr)


class DenyIn(BaseModel):
    review_notes: str = Field(min_length=1, max_length=2000)


@router.put("/{request_id}/deny", response_model=RequestOut)
def deny_request(
    request_id: int,
    body: DenyIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
):
    r = db.get(IPRequest, request_id)
    if not r:
        raise HTTPException(404, "not found")
    if r.status != "pending":
        raise HTTPException(409, f"request is already {r.status}")
    subnet = db.get(Subnet, r.subnet_id) if r.subnet_id else None

    r.status = "denied"
    r.reviewer_username = user.username
    r.reviewed_at = utcnow()
    r.review_notes = body.review_notes
    db.commit(); db.refresh(r)

    emit(
        "ip_request_resolved",
        f"ip_request:{r.id}",
        {
            "request_id": r.id, "status": "denied",
            "requester": r.requester_username, "reviewer": user.username,
            "subnet_cidr": subnet.cidr if subnet else None, "hostname": r.hostname,
            "review_notes": body.review_notes,
        },
    )
    write_audit(db, user.username, "update", "ip_request", str(r.id), r.hostname,
                after={"status": "denied", "review_notes": body.review_notes})
    return RequestOut.from_orm_obj(r, subnet.cidr if subnet else None)


@router.delete("/{request_id}", status_code=204)
def delete_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = db.get(IPRequest, request_id)
    if not r:
        raise HTTPException(404, "not found")
    if user.role in ("admin", "operator"):
        pass  # any request
    elif user.role == "requester":
        if r.requester_username != user.username:
            raise HTTPException(403, "not your request")
        if r.status != "pending":
            raise HTTPException(403, "cannot delete a resolved request")
    else:
        raise HTTPException(403, "insufficient role")
    name = r.hostname
    db.delete(r); db.commit()
    write_audit(db, user.username, "delete", "ip_request", str(request_id), name)
    return Response(status_code=204)
