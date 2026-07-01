import importlib.util, os
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "scale_seed", Path(__file__).resolve().parents[2] / "scripts" / "scale_seed.py")
scale_seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scale_seed)


def test_build_subnet_rows_count_and_unique_cidr():
    rows = scale_seed.build_subnet_rows(300)
    assert len(rows) == 300
    cidrs = [r["cidr"] for r in rows]
    assert len(set(cidrs)) == 300            # all CIDRs unique
    assert all(r["name"] and r["ip_version"] == 4 for r in rows)


def test_build_address_rows_count_unique_and_valid_fk():
    subnet_ids = list(range(1, 101))           # 100 subnets
    rows = scale_seed.build_address_rows(10000, subnet_ids)   # 100 hosts/subnet
    assert len(rows) == 10000
    assert len({r["address"] for r in rows}) == 10000
    assert all(r["subnet_id"] in subnet_ids for r in rows)
    assert len({r["status"] for r in rows}) >= 3
    # every address lives in its subnet's /24 (index-based: subnet k -> 10.(k>>8).(k&0xFF).0/24)
    import ipaddress
    for r in rows[:500]:
        k = subnet_ids.index(r["subnet_id"])
        net = ipaddress.ip_network(f"10.{(k>>8)&0xFF}.{k&0xFF}.0/24")
        assert ipaddress.ip_address(r["address"]) in net


def test_build_address_rows_rejects_overflow():
    import pytest
    with pytest.raises(ValueError):
        scale_seed.build_address_rows(10000, [1, 2, 3])   # 3334 hosts/subnet > 254


def test_tiers_mapping():
    assert scale_seed.TIERS["10k"] == (10000, 100)
    assert scale_seed.TIERS["50k"] == (50000, 300)
    assert scale_seed.TIERS["100k"] == (100000, 500)
