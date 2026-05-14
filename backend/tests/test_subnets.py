from app.models.subnet import Subnet


def test_subnet_list_includes_hierarchy_fields(client, db):
    db.add(Subnet(name="Root", cidr="10.0.0.0/8", ip_version=4))
    db.commit()
    r = client.get("/api/subnets")
    assert r.status_code == 200
    s = r.json()[0]
    assert "parent_id" in s
    assert "rollup_used_count" in s
    assert "rollup_total_count" in s
    assert "rollup_utilization_pct" in s
