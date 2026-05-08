from app.utils import ip_in_cidr


def test_ip_in_cidr_match():
    assert ip_in_cidr("10.0.0.5", "10.0.0.0/24") is True


def test_ip_in_cidr_boundary_low():
    assert ip_in_cidr("10.0.0.1", "10.0.0.0/24") is True


def test_ip_in_cidr_boundary_high():
    assert ip_in_cidr("10.0.0.254", "10.0.0.0/24") is True


def test_ip_in_cidr_miss():
    assert ip_in_cidr("192.168.1.1", "10.0.0.0/24") is False


def test_ip_in_cidr_bad_ip():
    assert ip_in_cidr("notanip", "10.0.0.0/24") is False


def test_ip_in_cidr_bad_cidr():
    assert ip_in_cidr("10.0.0.1", "notacidr") is False
