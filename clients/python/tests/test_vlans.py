from ipforge_client.resources.vlans import Vlans


def test_list(fake):
    fake.set("GET", "/vlans", [{"id": 1, "vlan_id": 100, "name": "prod"}])
    out = Vlans(fake).list()
    assert out[0].vlan_id == 100 and out[0].name == "prod"


def test_create_and_delete(fake):
    fake.set("POST", "/vlans", {"id": 2, "vlan_id": 200})
    Vlans(fake).create(vlan_id=200, name="lab")
    Vlans(fake).delete(2)
    assert fake.calls[0][:2] == ("POST", "/vlans")
    assert fake.calls[1][:2] == ("DELETE", "/vlans/2")
