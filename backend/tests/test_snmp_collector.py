from app.discovery.snmp import SnmpDiscovery, OID_ARP, OID_FDB, OID_BASEPORT, OID_IFNAME


def _make(responses):
    p = SnmpDiscovery({"host": "10.0.0.1", "snmp_version": "2c", "community": "public"}, "sw1")
    p._walk = lambda oid: responses.get(oid, [])
    return p


def test_merge_ip_mac_port_vlan():
    p = _make({
        # ARP: ifindex.ipv4 -> mac string
        OID_ARP: [("5.10.0.0.20", "aa:bb:cc:dd:ee:ff")],
        # FDB: vlan.mac(6 octets) -> bridge port
        OID_FDB: [("100.170.187.204.221.238.255", 3)],  # vlan 100, mac aa:bb:cc:dd:ee:ff, port 3
        # baseport: bridgeport -> ifindex
        OID_BASEPORT: [("3", 7)],
        # ifname: ifindex -> name
        OID_IFNAME: [("7", "GigabitEthernet0/3")],
    })
    eps = {e.mac: e for e in p.poll()}
    e = eps["aa:bb:cc:dd:ee:ff"]
    assert e.ip == "10.0.0.20"
    assert e.vlan == 100
    assert e.ifindex == 7
    assert e.port_name == "GigabitEthernet0/3"


def test_arp_only_mac_no_switchport():
    p = _make({OID_ARP: [("5.10.0.0.30", "11:22:33:44:55:66")]})
    eps = {e.mac: e for e in p.poll()}
    e = eps["11:22:33:44:55:66"]
    assert e.ip == "10.0.0.30"
    assert e.vlan is None
    assert e.port_name is None


def test_fdb_only_mac_no_ip():
    p = _make({
        OID_FDB: [("200.1.2.3.4.5.6", 4)],
        OID_BASEPORT: [("4", 9)],
        OID_IFNAME: [("9", "Gi0/9")],
    })
    eps = {e.mac: e for e in p.poll()}
    e = eps["01:02:03:04:05:06"]
    assert e.ip is None
    assert e.vlan == 200
    assert e.port_name == "Gi0/9"


def test_unresolved_bridgeport_leaves_port_none():
    p = _make({
        OID_FDB: [("10.1.2.3.4.5.6", 99)],  # bridgeport 99 not in baseport map
    })
    eps = {e.mac: e for e in p.poll()}
    e = eps["01:02:03:04:05:06"]
    assert e.vlan == 10
    assert e.ifindex is None
    assert e.port_name is None
