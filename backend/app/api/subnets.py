import ipaddress
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.subnet import Subnet
from app.schemas.subnet import SubnetCreate, SubnetRead, SubnetUpdate

router = APIRouter()


@router.get("", response_model=list[SubnetRead])
def list_subnets(
    ip_version: int | None = Query(None, description="Filter by IP version (4 or 6)"),
    db: Session = Depends(get_db),
):
    q = db.query(Subnet)
    if ip_version is not None:
        q = q.filter(Subnet.ip_version == ip_version)
    return q.all()


@router.post("", response_model=SubnetRead, status_code=201)
def create_subnet(data: SubnetCreate, db: Session = Depends(get_db)):
    try:
        network = ipaddress.ip_network(data.cidr, strict=False)
    except ValueError:
        raise HTTPException(400, "Invalid CIDR notation")
    if db.query(Subnet).filter(Subnet.cidr == data.cidr).first():
        raise HTTPException(409, "Subnet already exists")
    subnet = Subnet(**data.model_dump(), ip_version=network.version)
    db.add(subnet)
    db.commit()
    db.refresh(subnet)
    return subnet


@router.get("/{subnet_id}", response_model=SubnetRead)
def get_subnet(subnet_id: int, db: Session = Depends(get_db)):
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    return subnet


@router.put("/{subnet_id}", response_model=SubnetRead)
def update_subnet(subnet_id: int, data: SubnetUpdate, db: Session = Depends(get_db)):
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(subnet, key, value)
    db.commit()
    db.refresh(subnet)
    return subnet


@router.delete("/{subnet_id}", status_code=204)
def delete_subnet(subnet_id: int, db: Session = Depends(get_db)):
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    db.delete(subnet)
    db.commit()
