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
    subnet_ids = [1, 2, 3, 4, 5]
    rows = scale_seed.build_address_rows(10000, subnet_ids)
    assert len(rows) == 10000
    assert len({r["address"] for r in rows}) == 10000   # unique addresses
    assert all(r["subnet_id"] in subnet_ids for r in rows)
    # status distribution exercises real filters, not all-one-value
    assert len({r["status"] for r in rows}) >= 3


def test_tiers_mapping():
    assert scale_seed.TIERS["10k"] == (10000, 100)
    assert scale_seed.TIERS["50k"] == (50000, 300)
    assert scale_seed.TIERS["100k"] == (100000, 500)
