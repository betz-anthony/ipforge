from app.core.dns_names import short_name_for_zone


def test_fqdn_in_own_zone_returns_short_name():
    assert short_name_for_zone("lnx-o9bam-test.test.drake.edu", "test.drake.edu") == "lnx-o9bam-test"


def test_short_name_not_flagged():
    assert short_name_for_zone("lnx-o9bam-test", "test.drake.edu") is None


def test_case_and_zone_trailing_dot_ignored():
    assert short_name_for_zone("Host.Test.Drake.EDU", "test.drake.edu.") == "Host"


def test_trailing_dot_name_is_absolute_not_flagged():
    assert short_name_for_zone("host.test.drake.edu.", "test.drake.edu") is None


def test_apex_not_flagged():
    assert short_name_for_zone("@", "test.drake.edu") is None
    assert short_name_for_zone("test.drake.edu", "test.drake.edu") is None


def test_partial_label_overlap_not_flagged():
    assert short_name_for_zone("footest.drake.edu", "test.drake.edu") is None
    assert short_name_for_zone("host.test", "drake.edu") is None


def test_multi_label_prefix_kept():
    assert short_name_for_zone("a.b.test.drake.edu", "test.drake.edu") == "a.b"
