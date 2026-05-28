"""DISCOVERY-SNMP-001 — device + endpoint API."""
import threading
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.crypto import encrypt_secret
from app.core.deps import get_current_user, require_admin, require_operator
from app.core.time import utcnow
from app.database import get_db
from app.discovery.runner import poll_device
from app.models.cache import SyncStatus
from app.models.network_device import NetworkDevice, DiscoveredEndpoint
from app.models.user import User

router = APIRouter()

SnmpVersion = Literal["2c", "3"]
_SECRET_FIELDS = ("community", "auth_key", "priv_key")


class DeviceIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    host: str = Field(min_length=1, max_length=255)
    snmp_version: SnmpVersion = "2c"
    community: str | None = None
    v3_user: str | None = None
    auth_protocol: str | None = None
    auth_key: str | None = None
    priv_protocol: str | None = None
    priv_key: str | None = None
    security_level: str | None = None
    poll_interval_minutes: int = Field(default=60, ge=1)
    enabled: bool = True


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    snmp_version: SnmpVersion | None = None
    community: str | None = None
    v3_user: str | None = None
    auth_protocol: str | None = None
    auth_key: str | None = None
    priv_protocol: str | None = None
    priv_key: str | None = None
    security_level: str | None = None
    poll_interval_minutes: int | None = Field(default=None, ge=1)
    enabled: bool | None = None


def _device_out(d: NetworkDevice, db: Session) -> dict:
    status = db.get(SyncStatus, f"discovery:{d.id}")
    return {
        "id": d.id, "name": d.name, "host": d.host, "snmp_version": d.snmp_version,
        "v3_user": d.v3_user, "auth_protocol": d.auth_protocol, "priv_protocol": d.priv_protocol,
        "security_level": d.security_level,
        "poll_interval_minutes": d.poll_interval_minutes, "enabled": d.enabled,
        "has_community": bool(d.community), "has_auth_key": bool(d.auth_key), "has_priv_key": bool(d.priv_key),
        "last_status": status.status if status else "never",
        "last_synced_at": status.synced_at.isoformat() + "Z" if status and status.synced_at else None,
        "last_error": status.error if status else None,
    }


@router.get("/devices")
def list_devices(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [_device_out(d, db) for d in db.query(NetworkDevice).order_by(NetworkDevice.name).all()]


@router.post("/devices", status_code=201)
def create_device(body: DeviceIn, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    data = body.model_dump()
    for f in _SECRET_FIELDS:
        if data.get(f):
            data[f] = encrypt_secret(data[f])
    d = NetworkDevice(**data)
    db.add(d)
    db.flush()
    write_audit(db, current_user.username, "create", "network_device", str(d.id), f"{d.name} ({d.host})")
    db.commit()
    db.refresh(d)
    return _device_out(d, db)


@router.put("/devices/{device_id}")
def update_device(device_id: int, body: DeviceUpdate, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    d = db.get(NetworkDevice, device_id)
    if d is None:
        raise HTTPException(404, "Device not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        if key in _SECRET_FIELDS:
            if value:
                setattr(d, key, encrypt_secret(value))
            continue  # empty/None leaves the existing secret untouched
        setattr(d, key, value)
    write_audit(db, current_user.username, "update", "network_device", str(d.id), f"{d.name} ({d.host})")
    db.commit()
    db.refresh(d)
    return _device_out(d, db)


@router.delete("/devices/{device_id}", status_code=204)
def delete_device(device_id: int, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    d = db.get(NetworkDevice, device_id)
    if d is None:
        raise HTTPException(404, "Device not found")
    db.query(DiscoveredEndpoint).filter_by(device_id=device_id).delete(synchronize_session=False)
    write_audit(db, current_user.username, "delete", "network_device", str(d.id), f"{d.name} ({d.host})")
    db.delete(d)
    db.commit()
    return Response(status_code=204)


@router.post("/devices/{device_id}/poll")
def poll_now(device_id: int, _: User = Depends(require_operator), db: Session = Depends(get_db)):
    d = db.get(NetworkDevice, device_id)
    if d is None:
        raise HTTPException(404, "Device not found")
    threading.Thread(target=poll_device, args=(device_id,), daemon=True, name=f"ipam-discovery-{device_id}").start()
    return {"status": "started"}


@router.get("/endpoints")
def list_endpoints(
    ip: str | None = Query(None),
    mac: str | None = Query(None),
    device_id: int | None = Query(None),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(DiscoveredEndpoint)
    if ip is not None:
        q = q.filter(DiscoveredEndpoint.ip == ip)
    if mac is not None:
        q = q.filter(DiscoveredEndpoint.mac == mac)
    if device_id is not None:
        q = q.filter(DiscoveredEndpoint.device_id == device_id)
    return [
        {
            "id": e.id, "device_id": e.device_id, "ip": e.ip, "mac": e.mac,
            "ifindex": e.ifindex, "port_name": e.port_name, "vlan": e.vlan,
            "last_seen": e.last_seen.isoformat() + "Z" if e.last_seen else None, "source": e.source,
        }
        for e in q.order_by(DiscoveredEndpoint.last_seen.desc()).all()
    ]
