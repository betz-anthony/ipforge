import csv
import io
import ipaddress
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import require_operator
from app.core.audit import write_audit
from app.core.mac import normalize_mac
from app.database import get_db
from app.models.address import IPAddress, AddressStatus
from app.models.subnet import Subnet
from app.models.user import User
from app.models.custom_field import CustomFieldDef
from app.core.custom_fields import load_custom_fields_bulk, load_tags_bulk

router = APIRouter()

# ── CSV column definitions ────────────────────────────────────────────────────

_SUBNET_COLS  = ["name", "cidr", "ip_version", "vlan_id", "description", "notes",
                 "parent_cidr", "scan_interval_minutes"]
_ADDRESS_COLS = ["address", "subnet_cidr", "hostname", "status",
                 "mac_address", "description", "notes"]

_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: str) -> str:
    """Neutralize spreadsheet formula injection by prefixing an apostrophe.

    A cell beginning with =, +, -, @, tab or CR is executed as a formula by
    Excel/Sheets. The leading apostrophe forces the cell to be read as text.
    """
    if value and value[0] in _CSV_FORMULA_PREFIXES:
        return "'" + value
    return value


# ── Export ────────────────────────────────────────────────────────────────────

def _cf_names(db: Session, entity_type: str) -> list[str]:
    return [d.name for d in db.query(CustomFieldDef)
            .filter_by(entity_type=entity_type)
            .order_by(CustomFieldDef.name).all()]


@router.get("/subnets.csv")
def export_subnets(db: Session = Depends(get_db)):
    subnets = db.query(Subnet).order_by(Subnet.id).all()
    cidr_map = {s.id: s.cidr for s in subnets}
    ids = [s.id for s in subnets]
    cf_names = _cf_names(db, "subnet")
    cf = load_custom_fields_bulk(db, "subnet", ids)
    tags = load_tags_bulk(db, "subnet", ids)

    buf = io.StringIO()
    fieldnames = _SUBNET_COLS + ["tags"] + [f"cf_{n}" for n in cf_names]
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for s in subnets:
        row = {
            "name":                  _csv_safe(s.name),
            "cidr":                  s.cidr,
            "ip_version":            s.ip_version,
            "vlan_id":               s.vlan_id if s.vlan_id is not None else "",
            "description":           _csv_safe(s.description or ""),
            "notes":                 _csv_safe(s.notes or ""),
            "parent_cidr":           cidr_map.get(s.parent_id, "") if s.parent_id else "",
            "scan_interval_minutes": s.scan_interval_minutes if s.scan_interval_minutes is not None else "",
            "tags":                  ";".join(tags.get(s.id, [])),
        }
        for n in cf_names:
            row[f"cf_{n}"] = _csv_safe(cf.get(s.id, {}).get(n, ""))
        w.writerow(row)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=subnets.csv"},
    )


@router.get("/addresses.csv")
def export_addresses(db: Session = Depends(get_db)):
    addresses = db.query(IPAddress).order_by(IPAddress.id).all()
    subnet_map = {s.id: s.cidr for s in db.query(Subnet).all()}
    ids = [a.id for a in addresses]
    cf_names = _cf_names(db, "address")
    cf = load_custom_fields_bulk(db, "address", ids)
    tags = load_tags_bulk(db, "address", ids)

    buf = io.StringIO()
    fieldnames = _ADDRESS_COLS + ["tags"] + [f"cf_{n}" for n in cf_names]
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for a in addresses:
        row = {
            "address":     a.address,
            "subnet_cidr": subnet_map.get(a.subnet_id, ""),
            "hostname":    _csv_safe(a.hostname or ""),
            "status":      a.status.value,
            "mac_address": a.mac_address or "",
            "description": _csv_safe(a.description or ""),
            "notes":       _csv_safe(a.notes or ""),
            "tags":        ";".join(tags.get(a.id, [])),
        }
        for n in cf_names:
            row[f"cf_{n}"] = _csv_safe(cf.get(a.id, {}).get(n, ""))
        w.writerow(row)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=addresses.csv"},
    )


# ── Import result schema ──────────────────────────────────────────────────────

class ImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]


# ── Import subnets ────────────────────────────────────────────────────────────

@router.post("/subnets", response_model=ImportResult)
async def import_subnets(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # strip BOM if present
    except UnicodeDecodeError:
        raise HTTPException(400, "File must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text))
    missing = set(_SUBNET_COLS[:2]) - set(reader.fieldnames or [])
    if missing:
        raise HTTPException(400, f"CSV missing required columns: {', '.join(sorted(missing))}")

    cidr_to_id: dict[str, int] = {s.cidr: s.id for s in db.query(Subnet).all()}
    created = updated = skipped = 0
    errors: list[str] = []

    for i, row in enumerate(reader, start=2):
        cidr = (row.get("cidr") or "").strip()
        name = (row.get("name") or "").strip()
        if not cidr or not name:
            errors.append(f"Row {i}: 'name' and 'cidr' are required")
            skipped += 1
            continue

        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            errors.append(f"Row {i}: invalid CIDR '{cidr}'")
            skipped += 1
            continue

        vlan_id = None
        raw_vlan = (row.get("vlan_id") or "").strip()
        if raw_vlan:
            try:
                vlan_id = int(raw_vlan)
            except ValueError:
                errors.append(f"Row {i}: invalid vlan_id '{raw_vlan}'")
                skipped += 1
                continue

        scan_interval = None
        raw_interval = (row.get("scan_interval_minutes") or "").strip()
        if raw_interval:
            try:
                scan_interval = int(raw_interval)
                if scan_interval < 1:
                    raise ValueError
            except ValueError:
                errors.append(f"Row {i}: scan_interval_minutes must be a positive integer")
                skipped += 1
                continue

        parent_id = None
        parent_cidr = (row.get("parent_cidr") or "").strip()
        if parent_cidr:
            if parent_cidr not in cidr_to_id:
                errors.append(f"Row {i}: parent_cidr '{parent_cidr}' not found — import parents first")
                skipped += 1
                continue
            parent_id = cidr_to_id[parent_cidr]

        existing = db.query(Subnet).filter_by(cidr=cidr).first()
        if existing:
            before = {"name": existing.name, "cidr": existing.cidr}
            existing.name        = name
            existing.vlan_id     = vlan_id
            existing.description = (row.get("description") or "").strip() or None
            existing.notes       = (row.get("notes") or "").strip() or None
            existing.parent_id   = parent_id
            existing.scan_interval_minutes = scan_interval
            db.flush()
            write_audit(db, current_user.username, "update", "subnet", str(existing.id),
                        f"{cidr} (CSV import)", before=before,
                        after={"name": name, "cidr": cidr})
            updated += 1
        else:
            subnet = Subnet(
                name=name, cidr=cidr, ip_version=network.version,
                vlan_id=vlan_id,
                description=(row.get("description") or "").strip() or None,
                notes=(row.get("notes") or "").strip() or None,
                parent_id=parent_id,
                scan_interval_minutes=scan_interval,
            )
            db.add(subnet)
            db.flush()
            cidr_to_id[cidr] = subnet.id
            write_audit(db, current_user.username, "create", "subnet", str(subnet.id),
                        f"{cidr} (CSV import)", after={"name": name, "cidr": cidr})
            created += 1

    db.commit()
    return ImportResult(created=created, updated=updated, skipped=skipped, errors=errors)


# ── Import addresses ──────────────────────────────────────────────────────────

_VALID_STATUSES = {s.value for s in AddressStatus}


@router.post("/addresses", response_model=ImportResult)
async def import_addresses(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "File must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text))
    missing = {"address", "subnet_cidr"} - set(reader.fieldnames or [])
    if missing:
        raise HTTPException(400, f"CSV missing required columns: {', '.join(sorted(missing))}")

    cidr_to_subnet: dict[str, Subnet] = {s.cidr: s for s in db.query(Subnet).all()}
    created = updated = skipped = 0
    errors: list[str] = []

    for i, row in enumerate(reader, start=2):
        address    = (row.get("address") or "").strip()
        subnet_cidr = (row.get("subnet_cidr") or "").strip()
        if not address or not subnet_cidr:
            errors.append(f"Row {i}: 'address' and 'subnet_cidr' are required")
            skipped += 1
            continue

        try:
            ipaddress.ip_address(address)
        except ValueError:
            errors.append(f"Row {i}: invalid IP address '{address}'")
            skipped += 1
            continue

        subnet = cidr_to_subnet.get(subnet_cidr)
        if subnet is None:
            errors.append(f"Row {i}: subnet_cidr '{subnet_cidr}' not found")
            skipped += 1
            continue

        try:
            net = ipaddress.ip_network(subnet_cidr, strict=False)
            if ipaddress.ip_address(address) not in net:
                errors.append(f"Row {i}: address '{address}' not within subnet '{subnet_cidr}'")
                skipped += 1
                continue
        except ValueError:
            pass

        raw_status = (row.get("status") or "").strip()
        if raw_status and raw_status not in _VALID_STATUSES:
            errors.append(f"Row {i}: invalid status '{raw_status}' (valid: {', '.join(sorted(_VALID_STATUSES))})")
            skipped += 1
            continue
        status = AddressStatus(raw_status) if raw_status else AddressStatus.available

        raw_mac = (row.get("mac_address") or "").strip()
        try:
            mac = normalize_mac(raw_mac) if raw_mac else None
        except ValueError:
            errors.append(f"Row {i}: invalid mac_address '{raw_mac}'")
            skipped += 1
            continue

        existing = db.query(IPAddress).filter_by(address=address).first()
        if existing:
            before = {"address": address, "status": existing.status.value}
            existing.subnet_id   = subnet.id
            existing.hostname    = (row.get("hostname") or "").strip() or None
            existing.status      = status
            existing.mac_address = mac
            existing.description = (row.get("description") or "").strip() or None
            existing.notes       = (row.get("notes") or "").strip() or None
            db.flush()
            write_audit(db, current_user.username, "update", "address", str(existing.id),
                        f"{address} (CSV import)", before=before,
                        after={"address": address, "status": status.value})
            updated += 1
        else:
            addr = IPAddress(
                address=address, subnet_id=subnet.id,
                hostname=(row.get("hostname") or "").strip() or None,
                status=status,
                mac_address=mac,
                description=(row.get("description") or "").strip() or None,
                notes=(row.get("notes") or "").strip() or None,
            )
            db.add(addr)
            db.flush()
            write_audit(db, current_user.username, "create", "address", str(addr.id),
                        f"{address} (CSV import)", after={"address": address, "status": status.value})
            created += 1

    db.commit()
    return ImportResult(created=created, updated=updated, skipped=skipped, errors=errors)
