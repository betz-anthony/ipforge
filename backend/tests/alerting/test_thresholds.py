from unittest.mock import patch
from app.alerting.thresholds import eval_utilization, eval_stale_queue
from app.alerting.models import AlertRule
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus


def _rule_util(pct):
    return AlertRule(id=1, name="util", trigger_type="utilization",
                     condition={"threshold_pct": pct}, channel_ids=[1], enabled=True)


def _rule_stale(n):
    return AlertRule(id=2, name="stale", trigger_type="stale_queue",
                     condition={"threshold": n}, channel_ids=[1], enabled=True)


def test_eval_utilization_emits_when_above(db_session):
    s = Subnet(name="test-29", cidr="10.0.0.0/29", ip_version=4)  # 6 usable hosts
    db_session.add(s); db_session.commit()
    for i in range(1, 7):
        db_session.add(IPAddress(address=f"10.0.0.{i}", subnet_id=s.id, status=AddressStatus.assigned))
    db_session.commit()
    with patch("app.alerting.thresholds.emit") as e:
        eval_utilization(db_session, [_rule_util(50)])
    e.assert_called_once()
    args, _ = e.call_args
    assert args[0] == "utilization"
    assert args[1] == f"subnet:{s.cidr}"


def test_eval_utilization_skips_when_below(db_session):
    s = Subnet(name="test-24", cidr="10.0.0.0/24", ip_version=4)
    db_session.add(s); db_session.commit()
    with patch("app.alerting.thresholds.emit") as e:
        eval_utilization(db_session, [_rule_util(50)])
    e.assert_not_called()


def test_eval_stale_queue_emits_above_threshold(db_session):
    with patch("app.alerting.thresholds._stale_count", return_value=15), \
         patch("app.alerting.thresholds.emit") as e:
        eval_stale_queue(db_session, [_rule_stale(10)])
    e.assert_called_once()


def test_eval_stale_queue_skips_when_below(db_session):
    with patch("app.alerting.thresholds._stale_count", return_value=5), \
         patch("app.alerting.thresholds.emit") as e:
        eval_stale_queue(db_session, [_rule_stale(10)])
    e.assert_not_called()


def test_disabled_rule_is_ignored(db_session):
    s = Subnet(name="test-disabled", cidr="10.0.0.0/29", ip_version=4)
    db_session.add(s); db_session.commit()
    for i in range(1, 7):
        db_session.add(IPAddress(address=f"10.0.0.{i}", subnet_id=s.id, status=AddressStatus.assigned))
    db_session.commit()
    r = _rule_util(50); r.enabled = False
    with patch("app.alerting.thresholds.emit") as e:
        eval_utilization(db_session, [r])
    e.assert_not_called()
