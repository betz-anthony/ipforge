import pytest
from types import SimpleNamespace

from app.gitops import parse, plan, apply, GitopsError
from app.models.subnet import Subnet
from app.models.vlan import Vlan
from app.models.address import IPAddress
from app.models.subnet_range import SubnetRange
from app.models.gitops import GitopsManaged

USER = SimpleNamespace(username="gitops")

DOC = """
source: prod
vlans:
  - { vlan_id: 10, name: servers }
subnets:
  - cidr: 10.0.0.0/24
    name: servers
    vlan_id: 10
    reserved_ranges:
      - { start: 10.0.0.1, kind: gateway, label: gw }
allocations:
  - { subnet: 10.0.0.0/24, hostname: web-01 }
"""


def test_parse_valid():
    doc = parse(DOC)
    assert doc["source"] == "prod"
    assert doc["subnets"][0]["cidr"] == "10.0.0.0/24"


def test_parse_missing_source():
    with pytest.raises(GitopsError):
        parse("subnets: []")


def test_parse_bad_cidr():
    with pytest.raises(GitopsError):
        parse("source: x\nsubnets:\n  - { cidr: nope, name: a }")


def test_plan_create_lists_new(db):
    p = plan(parse(DOC), db)
    assert "10.0.0.0/24" in p["subnets"]["create"]
    assert any("10" in v for v in p["vlans"]["create"])
    assert any("web-01" in a for a in p["allocations"]["create"])


def test_apply_creates_and_tags(db):
    apply(parse(DOC), db, USER)
    assert db.query(Vlan).filter_by(vlan_id=10).count() == 1
    s = db.query(Subnet).filter_by(cidr="10.0.0.0/24").first()
    assert s is not None and s.vlan_id == 10
    assert db.query(SubnetRange).filter_by(subnet_id=s.id, kind="gateway").count() == 1
    assert db.query(IPAddress).filter_by(hostname="web-01").count() == 1
    # markers exist for each resource type
    types = {m.resource_type for m in db.query(GitopsManaged).all()}
    assert {"vlan", "subnet", "subnet_range", "address"} <= types


def test_apply_idempotent(db):
    apply(parse(DOC), db, USER)
    p2 = plan(parse(DOC), db)
    assert p2["subnets"]["create"] == [] and p2["subnets"]["update"] == []
    assert p2["vlans"]["create"] == []
    assert p2["allocations"]["create"] == []


def test_prune_only_managed(db):
    apply(parse(DOC), db, USER)
    # a manually-created subnet (no marker) must survive a prune
    db.add(Subnet(name="manual", cidr="10.9.9.0/24", ip_version=4))
    db.commit()
    # re-apply a doc that drops the managed subnet
    apply(parse("source: prod\nsubnets: []\nvlans: []\nallocations: []"), db, USER)
    assert db.query(Subnet).filter_by(cidr="10.0.0.0/24").count() == 0  # pruned (managed)
    assert db.query(Subnet).filter_by(cidr="10.9.9.0/24").count() == 1  # survives (manual)


def test_prune_skips_other_source(db):
    apply(parse(DOC), db, USER)
    # different source applies an empty doc -> must NOT prune prod's resources
    apply(parse("source: other\nsubnets: []\nvlans: []\nallocations: []"), db, USER)
    assert db.query(Subnet).filter_by(cidr="10.0.0.0/24").count() == 1


def test_update_changed_field(db):
    apply(parse(DOC), db, USER)
    doc2 = parse(DOC.replace("name: servers\n    vlan_id: 10", "name: renamed\n    vlan_id: 10"))
    p = plan(doc2, db)
    assert "10.0.0.0/24" in p["subnets"]["update"]
    apply(doc2, db, USER)
    assert db.query(Subnet).filter_by(cidr="10.0.0.0/24").first().name == "renamed"
