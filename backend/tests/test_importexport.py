import io
import csv
import pytest
from app.api.importexport import _csv_safe
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus


def test_csv_safe_prefixes_formula_cells():
    assert _csv_safe("=1+1") == "'=1+1"
    assert _csv_safe("+cmd") == "'+cmd"
    assert _csv_safe("-cmd") == "'-cmd"
    assert _csv_safe("@SUM(A1)") == "'@SUM(A1)"
    assert _csv_safe("\tfoo") == "'\tfoo"


def test_csv_safe_leaves_normal_text():
    assert _csv_safe("web01") == "web01"
    assert _csv_safe("10.0.0.0/24") == "10.0.0.0/24"
    assert _csv_safe("") == ""


def _csv(rows: list[dict], fieldnames: list[str]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode()


SUBNET_COLS = ["name", "cidr", "ip_version", "vlan_id", "description", "notes",
               "parent_cidr", "scan_interval_minutes"]
ADDRESS_COLS = ["address", "subnet_cidr", "hostname", "status",
                "mac_address", "description", "notes"]


# ── Export ─────────────────────────────────────────────────────────────────────

def test_export_subnets_empty(client):
    r = client.get("/api/importexport/subnets.csv")
    assert r.status_code == 200
    lines = r.text.strip().splitlines()
    assert lines[0] == ",".join(SUBNET_COLS + ["tags"])
    assert len(lines) == 1


def test_export_subnets_content(client, db):
    db.add(Subnet(name="net1", cidr="10.0.0.0/24", ip_version=4, vlan_id=10,
                  description="d", notes="n", scan_interval_minutes=5))
    db.commit()
    r = client.get("/api/importexport/subnets.csv")
    assert r.status_code == 200
    reader = csv.DictReader(io.StringIO(r.text))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["name"] == "net1"
    assert rows[0]["cidr"] == "10.0.0.0/24"
    assert rows[0]["vlan_id"] == "10"
    assert rows[0]["scan_interval_minutes"] == "5"


def test_export_addresses_empty(client):
    r = client.get("/api/importexport/addresses.csv")
    assert r.status_code == 200
    lines = r.text.strip().splitlines()
    assert lines[0] == ",".join(ADDRESS_COLS + ["tags"])


def test_export_addresses_content(client, db):
    s = Subnet(name="net1", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.flush()
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, hostname="host1",
                     status=AddressStatus.assigned, mac_address="aa:bb:cc:dd:ee:ff"))
    db.commit()
    r = client.get("/api/importexport/addresses.csv")
    assert r.status_code == 200
    reader = csv.DictReader(io.StringIO(r.text))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["address"] == "10.0.0.5"
    assert rows[0]["subnet_cidr"] == "10.0.0.0/24"
    assert rows[0]["hostname"] == "host1"
    assert rows[0]["status"] == "assigned"


# ── Import subnets ─────────────────────────────────────────────────────────────

def test_import_subnets_create(client, db):
    data = _csv([{"name": "net1", "cidr": "10.0.0.0/24", "ip_version": "",
                  "vlan_id": "10", "description": "desc", "notes": "",
                  "parent_cidr": "", "scan_interval_minutes": "15"}], SUBNET_COLS)
    r = client.post("/api/importexport/subnets",
                    files={"file": ("subnets.csv", data, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 1
    assert body["updated"] == 0
    assert body["skipped"] == 0
    s = db.query(Subnet).filter_by(cidr="10.0.0.0/24").first()
    assert s is not None
    assert s.name == "net1"
    assert s.vlan_id == 10
    assert s.scan_interval_minutes == 15


def test_import_subnets_update(client, db):
    db.add(Subnet(name="old", cidr="10.0.0.0/24", ip_version=4))
    db.commit()
    data = _csv([{"name": "new", "cidr": "10.0.0.0/24", "ip_version": "",
                  "vlan_id": "", "description": "", "notes": "",
                  "parent_cidr": "", "scan_interval_minutes": ""}], SUBNET_COLS)
    r = client.post("/api/importexport/subnets",
                    files={"file": ("subnets.csv", data, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 0
    assert body["updated"] == 1
    s = db.query(Subnet).filter_by(cidr="10.0.0.0/24").first()
    assert s.name == "new"


def test_import_subnets_parent_cidr(client, db):
    data = _csv([
        {"name": "parent", "cidr": "10.0.0.0/16", "ip_version": "",
         "vlan_id": "", "description": "", "notes": "",
         "parent_cidr": "", "scan_interval_minutes": ""},
        {"name": "child", "cidr": "10.0.1.0/24", "ip_version": "",
         "vlan_id": "", "description": "", "notes": "",
         "parent_cidr": "10.0.0.0/16", "scan_interval_minutes": ""},
    ], SUBNET_COLS)
    r = client.post("/api/importexport/subnets",
                    files={"file": ("subnets.csv", data, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 2
    child = db.query(Subnet).filter_by(cidr="10.0.1.0/24").first()
    parent = db.query(Subnet).filter_by(cidr="10.0.0.0/16").first()
    assert child.parent_id == parent.id


def test_import_subnets_missing_parent(client, db):
    data = _csv([{"name": "child", "cidr": "10.0.1.0/24", "ip_version": "",
                  "vlan_id": "", "description": "", "notes": "",
                  "parent_cidr": "10.0.0.0/16", "scan_interval_minutes": ""}], SUBNET_COLS)
    r = client.post("/api/importexport/subnets",
                    files={"file": ("subnets.csv", data, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["skipped"] == 1
    assert "parent_cidr" in body["errors"][0]


def test_import_subnets_invalid_cidr(client, db):
    data = _csv([{"name": "bad", "cidr": "not-a-cidr", "ip_version": "",
                  "vlan_id": "", "description": "", "notes": "",
                  "parent_cidr": "", "scan_interval_minutes": ""}], SUBNET_COLS)
    r = client.post("/api/importexport/subnets",
                    files={"file": ("subnets.csv", data, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["skipped"] == 1
    assert "invalid CIDR" in body["errors"][0]


def test_import_subnets_missing_columns(client):
    data = b"name,description\nfoo,bar\n"
    r = client.post("/api/importexport/subnets",
                    files={"file": ("subnets.csv", data, "text/csv")})
    assert r.status_code == 400
    assert "missing required columns" in r.json()["detail"].lower()


# ── Import addresses ───────────────────────────────────────────────────────────

def test_import_addresses_create(client, db):
    s = Subnet(name="net1", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.commit()
    data = _csv([{"address": "10.0.0.5", "subnet_cidr": "10.0.0.0/24",
                  "hostname": "host1", "status": "assigned",
                  "mac_address": "aa:bb:cc:dd:ee:ff",
                  "description": "", "notes": ""}], ADDRESS_COLS)
    r = client.post("/api/importexport/addresses",
                    files={"file": ("addresses.csv", data, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 1
    a = db.query(IPAddress).filter_by(address="10.0.0.5").first()
    assert a is not None
    assert a.hostname == "host1"
    assert a.status == AddressStatus.assigned


def test_import_addresses_update(client, db):
    s = Subnet(name="net1", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.flush()
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.available))
    db.commit()
    data = _csv([{"address": "10.0.0.5", "subnet_cidr": "10.0.0.0/24",
                  "hostname": "updated", "status": "reserved",
                  "mac_address": "", "description": "", "notes": ""}], ADDRESS_COLS)
    r = client.post("/api/importexport/addresses",
                    files={"file": ("addresses.csv", data, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["updated"] == 1
    a = db.query(IPAddress).filter_by(address="10.0.0.5").first()
    assert a.hostname == "updated"
    assert a.status == AddressStatus.reserved


def test_import_addresses_invalid_status(client, db):
    s = Subnet(name="net1", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.commit()
    data = _csv([{"address": "10.0.0.5", "subnet_cidr": "10.0.0.0/24",
                  "hostname": "", "status": "bad_status",
                  "mac_address": "", "description": "", "notes": ""}], ADDRESS_COLS)
    r = client.post("/api/importexport/addresses",
                    files={"file": ("addresses.csv", data, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["skipped"] == 1
    assert "invalid status" in body["errors"][0]


def test_import_addresses_out_of_subnet(client, db):
    s = Subnet(name="net1", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.commit()
    data = _csv([{"address": "192.168.1.1", "subnet_cidr": "10.0.0.0/24",
                  "hostname": "", "status": "",
                  "mac_address": "", "description": "", "notes": ""}], ADDRESS_COLS)
    r = client.post("/api/importexport/addresses",
                    files={"file": ("addresses.csv", data, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["skipped"] == 1
    assert "not within subnet" in body["errors"][0]


def test_import_addresses_missing_subnet(client, db):
    data = _csv([{"address": "10.0.0.5", "subnet_cidr": "10.0.0.0/24",
                  "hostname": "", "status": "",
                  "mac_address": "", "description": "", "notes": ""}], ADDRESS_COLS)
    r = client.post("/api/importexport/addresses",
                    files={"file": ("addresses.csv", data, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["skipped"] == 1
    assert "not found" in body["errors"][0]


def test_import_addresses_default_status(client, db):
    s = Subnet(name="net1", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.commit()
    data = _csv([{"address": "10.0.0.10", "subnet_cidr": "10.0.0.0/24",
                  "hostname": "", "status": "",
                  "mac_address": "", "description": "", "notes": ""}], ADDRESS_COLS)
    r = client.post("/api/importexport/addresses",
                    files={"file": ("addresses.csv", data, "text/csv")})
    assert r.status_code == 200
    a = db.query(IPAddress).filter_by(address="10.0.0.10").first()
    assert a.status == AddressStatus.available
