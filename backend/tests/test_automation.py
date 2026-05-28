from app.automation import run_automation
from app.alerting.emit import TriggerEvent
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.automation import AutomationRule
from app.core.custom_fields import load_tags


def _addr(db, ip="10.0.0.5", status=AddressStatus.discovered, mac=None, tags=None):
    s = db.query(Subnet).filter_by(cidr="10.0.0.0/24").first()
    if s is None:
        s = Subnet(name="N", cidr="10.0.0.0/24", ip_version=4)
        db.add(s)
        db.flush()
    a = IPAddress(address=ip, subnet_id=s.id, status=status, mac_address=mac)
    db.add(a)
    db.commit()
    if tags:
        from app.core.custom_fields import set_tags
        set_tags(db, "address", a.id, tags)
        db.commit()
    return a


def _rule(db, trigger_type, action, condition=None, enabled=True):
    r = AutomationRule(name=f"r{db.query(AutomationRule).count()}", trigger_type=trigger_type,
                       condition=condition or {}, action=action, enabled=enabled)
    db.add(r)
    db.commit()
    return r


def _ev(trigger, ip, category=None):
    ctx = {"ip": ip}
    if category:
        ctx["category"] = category
    return TriggerEvent(trigger_type=trigger, resource_key=f"ip:{ip}", context=ctx)


def test_rogue_adds_tag(db):
    a = _addr(db)
    _rule(db, "rogue", {"add_tags": ["unverified"]})
    run_automation(db, _ev("rogue", "10.0.0.5"))
    assert "unverified" in load_tags(db, "address", a.id)


def test_set_status(db):
    a = _addr(db, status=AddressStatus.discovered)
    _rule(db, "rogue", {"set_status": "reserved"})
    run_automation(db, _ev("rogue", "10.0.0.5"))
    db.refresh(a)
    assert a.status == AddressStatus.reserved


def test_drift_category_condition_match(db):
    a = _addr(db)
    _rule(db, "drift", {"add_tags": ["orphan"]}, condition={"category": "orphan_dhcp"})
    run_automation(db, _ev("drift", "10.0.0.5", category="orphan_dhcp"))
    assert "orphan" in load_tags(db, "address", a.id)


def test_drift_category_condition_skip(db):
    a = _addr(db)
    _rule(db, "drift", {"add_tags": ["orphan"]}, condition={"category": "orphan_dhcp"})
    run_automation(db, _ev("drift", "10.0.0.5", category="missing_dns"))
    assert load_tags(db, "address", a.id) == []


def test_disabled_rule_skipped(db):
    a = _addr(db)
    _rule(db, "rogue", {"add_tags": ["x"]}, enabled=False)
    run_automation(db, _ev("rogue", "10.0.0.5"))
    assert load_tags(db, "address", a.id) == []


def test_unknown_ip_noop(db):
    _rule(db, "rogue", {"add_tags": ["x"]})
    run_automation(db, _ev("rogue", "10.9.9.9"))  # no address — must not raise


def test_additive_tags_keep_existing(db):
    a = _addr(db, tags=["keep"])
    _rule(db, "rogue", {"add_tags": ["new"]})
    run_automation(db, _ev("rogue", "10.0.0.5"))
    assert set(load_tags(db, "address", a.id)) == {"keep", "new"}


def test_wrong_trigger_skipped(db):
    a = _addr(db)
    _rule(db, "drift", {"add_tags": ["x"]})
    run_automation(db, _ev("rogue", "10.0.0.5"))
    assert load_tags(db, "address", a.id) == []


def test_dispatcher_tick_applies_automation(db):
    a = _addr(db)
    _rule(db, "rogue", {"add_tags": ["via-tick"]})
    from app.alerting.emit import emit, drain_queue
    from app.alerting.dispatcher import process_tick
    drain_queue()  # clear residue
    emit("rogue", "ip:10.0.0.5", {"ip": "10.0.0.5"})
    process_tick(db)
    assert "via-tick" in load_tags(db, "address", a.id)
