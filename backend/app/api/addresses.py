from app.core.deps import require_operator
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.address import IPAddress, AddressStatus
from app.schemas.address import AddressCreate, AddressRead, AddressUpdate

router = APIRouter()


@router.get("", response_model=list[AddressRead])
def list_addresses(
    subnet_id: int | None = Query(None),
    status: AddressStatus | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(IPAddress)
    if subnet_id is not None:
        q = q.filter(IPAddress.subnet_id == subnet_id)
    if status is not None:
        q = q.filter(IPAddress.status == status)
    return q.all()


@router.post("", response_model=AddressRead, status_code=201, dependencies=[Depends(require_operator)])
def create_address(data: AddressCreate, db: Session = Depends(get_db)):
    if db.query(IPAddress).filter(IPAddress.address == data.address).first():
        raise HTTPException(409, "Address already exists")
    address = IPAddress(**data.model_dump())
    db.add(address)
    db.commit()
    db.refresh(address)
    return address


@router.get("/by-ip/{address}", response_model=AddressRead)
def get_address_by_ip(address: str, db: Session = Depends(get_db)):
    record = db.query(IPAddress).filter(IPAddress.address == address).first()
    if not record:
        raise HTTPException(404, "Address not found")
    return record


@router.get("/{address_id}", response_model=AddressRead)
def get_address(address_id: int, db: Session = Depends(get_db)):
    address = db.get(IPAddress, address_id)
    if not address:
        raise HTTPException(404, "Address not found")
    return address


@router.put("/{address_id}", response_model=AddressRead, dependencies=[Depends(require_operator)])
def update_address(address_id: int, data: AddressUpdate, db: Session = Depends(get_db)):
    address = db.get(IPAddress, address_id)
    if not address:
        raise HTTPException(404, "Address not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(address, key, value)
    db.commit()
    db.refresh(address)
    return address


@router.delete("/{address_id}", status_code=204, dependencies=[Depends(require_operator)])
def delete_address(address_id: int, db: Session = Depends(get_db)):
    address = db.get(IPAddress, address_id)
    if not address:
        raise HTTPException(404, "Address not found")
    db.delete(address)
    db.commit()
