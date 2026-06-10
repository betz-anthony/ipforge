from ipforge_client.models import Subnet, Address


def test_typed_properties_read_known_fields():
    s = Subnet({"id": 1, "cidr": "10.0.0.0/24", "name": "core"})
    assert s.id == 1 and s.cidr == "10.0.0.0/24" and s.name == "core"


def test_unknown_fields_tolerated_via_raw_and_getitem():
    a = Address({"id": 2, "address": "10.0.0.5", "future_field": "x"})
    assert a.address == "10.0.0.5"
    assert a["future_field"] == "x"
    assert a.raw["future_field"] == "x"


def test_missing_known_field_is_none():
    assert Subnet({"id": 1}).cidr is None


def test_equality_by_raw():
    assert Subnet({"id": 1}) == Subnet({"id": 1})
    assert Subnet({"id": 1}) != Subnet({"id": 2})
