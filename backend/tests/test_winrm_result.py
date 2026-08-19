"""WinRM result handling for the msdns / msdhcp providers.

Regression: PowerShell non-terminating errors (access denied, unreachable
-ComputerName, missing RSAT module) exit 0 with empty stdout and the message
on stderr. The old check only looked at status_code, so the stderr was
discarded and the caller failed later on json.loads('') with
"Expecting value: line 1 column 1 (char 0)".
"""

import pytest

from app.providers._winrm import check_result, check_transport


class _Result:
    def __init__(self, status_code=0, std_out=b"", std_err=b""):
        self.status_code = status_code
        self.std_out = std_out
        self.std_err = std_err


def test_stdout_returned_on_success():
    assert check_result(_Result(std_out=b'["example.com"]')) == '["example.com"]'


def test_non_terminating_error_surfaces_stderr():
    # Exit 0, nothing on stdout, real message on stderr.
    result = _Result(std_err=b"Access is denied. (Get-DnsServerZone)")
    with pytest.raises(RuntimeError, match="Access is denied"):
        check_result(result)


def test_empty_stdout_without_stderr_is_not_an_error():
    # A server with zero zones/scopes emits no ConvertTo-Json output at all.
    assert check_result(_Result(std_out=b"")).strip() == ""


def test_nonzero_exit_surfaces_stderr():
    with pytest.raises(RuntimeError, match="term is not recognized"):
        check_result(_Result(status_code=1, std_err=b"The term is not recognized"))


def test_nonzero_exit_without_stderr_still_raises():
    with pytest.raises(RuntimeError, match="exit 5"):
        check_result(_Result(status_code=5))


def test_undecodable_output_does_not_mask_the_error():
    with pytest.raises(RuntimeError):
        check_result(_Result(std_err=b"\xff\xfe bad bytes"))


def test_ntlm_transport_needs_no_extra():
    assert check_transport("ntlm") is None


def test_unavailable_transport_names_the_fix(monkeypatch):
    monkeypatch.setattr("app.providers._winrm.find_spec", lambda _: None)
    with pytest.raises(RuntimeError, match=r"pywinrm\[kerberos\]"):
        check_transport("kerberos")
