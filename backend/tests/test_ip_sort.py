from app.core.ip_sort import ip_sort_key


def test_v4_addresses_sort_numerically():
    ips = ["10.10.1.100", "10.10.1.1", "10.10.1.103", "10.10.1.11"]
    ordered = sorted(ips, key=ip_sort_key)
    assert ordered == ["10.10.1.1", "10.10.1.11", "10.10.1.100", "10.10.1.103"]


def test_v6_addresses_sort_numerically():
    ips = ["fe80::10", "fe80::1", "fe80::2"]
    ordered = sorted(ips, key=ip_sort_key)
    assert ordered == ["fe80::1", "fe80::2", "fe80::10"]


def test_v4_sorts_before_v6():
    ips = ["fe80::1", "10.0.0.1"]
    ordered = sorted(ips, key=ip_sort_key)
    assert ordered == ["10.0.0.1", "fe80::1"]


def test_same_ip_v4_and_v6_form_produce_different_keys():
    # Not the same key by design — packed() differs per version even for the
    # "same" address in IPv4-mapped-IPv6 notation; no attempt made to unify
    # those two textual spellings.
    assert ip_sort_key("10.0.0.1") != ip_sort_key("::ffff:10.0.0.1")


def test_unparseable_input_returns_none():
    assert ip_sort_key("not-an-ip") is None
    assert ip_sort_key("") is None
