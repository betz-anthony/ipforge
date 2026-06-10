from app.models.subnet import Subnet
from app.models.vlan import Vlan

DOC = """
source: prod
vlans:
  - { vlan_id: 20, name: dmz }
subnets:
  - { cidr: 10.1.0.0/24, name: dmz, vlan_id: 20 }
allocations: []
"""


def test_plan_endpoint(client, db):
    r = client.post("/api/v1/gitops/plan", content=DOC, headers={"content-type": "text/yaml"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "prod"
    assert "10.1.0.0/24" in body["plan"]["subnets"]["create"]


def test_apply_endpoint(client, db):
    r = client.post("/api/v1/gitops/apply", content=DOC, headers={"content-type": "text/yaml"})
    assert r.status_code == 200, r.text
    assert db.query(Subnet).filter_by(cidr="10.1.0.0/24").count() == 1
    assert db.query(Vlan).filter_by(vlan_id=20).count() == 1


def test_bad_yaml_400(client, db):
    r = client.post("/api/v1/gitops/apply", content="subnets: [", headers={"content-type": "text/yaml"})
    assert r.status_code == 400


def test_missing_source_400(client, db):
    r = client.post("/api/v1/gitops/plan", content="subnets: []", headers={"content-type": "text/yaml"})
    assert r.status_code == 400


def test_requires_operator(client_gr, db):
    r = client_gr.post("/api/v1/gitops/plan", content=DOC, headers={"content-type": "text/yaml"})
    assert r.status_code == 403
