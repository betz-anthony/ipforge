from ipforge_client.resources.subnets import Subnets


def test_list(fake):
    fake.set("GET", "/subnets", [{"id": 1, "cidr": "10.0.0.0/24"}])
    out = Subnets(fake).list()
    assert out[0].cidr == "10.0.0.0/24"
    assert fake.calls[0][:2] == ("GET", "/subnets")


def test_get(fake):
    fake.set("GET", "/subnets/7", {"id": 7})
    assert Subnets(fake).get(7).id == 7


def test_create_posts_body(fake):
    fake.set("POST", "/subnets", {"id": 9, "cidr": "10.1.0.0/24"})
    Subnets(fake).create(cidr="10.1.0.0/24", name="lab")
    m, p, params, body = fake.calls[0]
    assert (m, p) == ("POST", "/subnets")
    assert body == {"cidr": "10.1.0.0/24", "name": "lab"}


def test_delete(fake):
    Subnets(fake).delete(3)
    assert fake.calls[0][:2] == ("DELETE", "/subnets/3")


def test_allocate_builds_body(fake):
    fake.set("POST", "/subnets/1/allocate", {"address": "10.0.0.2", "is_new": True})
    Subnets(fake).allocate(1, "web-01", mac="aa:bb:cc:dd:ee:ff", register_dns=True, dns_zone="ex.com")
    body = fake.calls[0][3]
    assert body["hostname"] == "web-01" and body["mac_address"] == "aa:bb:cc:dd:ee:ff"
    assert body["register_dns"] is True and body["dns_zone"] == "ex.com"


def test_ranges_endpoints(fake):
    Subnets(fake).add_range(2, type="reserved", start="10.0.0.10", end="10.0.0.20")
    Subnets(fake).delete_range(2, 5)
    assert fake.calls[0][:2] == ("POST", "/subnets/2/ranges")
    assert fake.calls[1][:2] == ("DELETE", "/subnets/2/ranges/5")
