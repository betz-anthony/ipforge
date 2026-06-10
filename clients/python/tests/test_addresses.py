from ipforge_client.resources.addresses import Addresses


def test_list_returns_iterator_threading_filters(fake):
    fake.set("GET", "/addresses",
             {"items": [{"id": 1, "address": "10.0.0.5"}], "total": 1, "limit": 200, "offset": 0})
    out = list(Addresses(fake).list(subnet_id=3, q="web"))
    assert out[0].address == "10.0.0.5"
    params = fake.calls[0][2]
    assert params["subnet_id"] == 3 and params["q"] == "web"
    assert params["limit"] == 200 and params["offset"] == 0


def test_list_page_returns_page(fake):
    fake.set("GET", "/addresses",
             {"items": [{"id": 1}], "total": 7, "limit": 50, "offset": 0})
    page = Addresses(fake).list_page(limit=50, offset=0, subnet_id=3)
    assert page.total == 7 and len(page) == 1


def test_create_update_delete(fake):
    fake.set("POST", "/addresses", {"id": 1})
    Addresses(fake).create(address="10.0.0.9", subnet_id=2, status="assigned")
    Addresses(fake).update(1, hostname="db-01")
    Addresses(fake).delete(1)
    assert fake.calls[0][:2] == ("POST", "/addresses")
    assert fake.calls[1][:2] == ("PUT", "/addresses/1")
    assert fake.calls[2][:2] == ("DELETE", "/addresses/1")


def test_by_ip_and_history(fake):
    fake.set("GET", "/addresses/by-ip/10.0.0.5", {"id": 4, "address": "10.0.0.5"})
    assert Addresses(fake).by_ip("10.0.0.5").id == 4
    Addresses(fake).history_by_ip("10.0.0.5", as_of="2026-01-01")
    assert fake.calls[-1][:2] == ("GET", "/addresses/by-ip/10.0.0.5/history")
    assert fake.calls[-1][2] == {"as_of": "2026-01-01"}
