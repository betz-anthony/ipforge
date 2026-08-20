"""WinRM result handling for the msdns / msdhcp providers.

Regression: PowerShell non-terminating errors (access denied, unreachable
-ComputerName, missing RSAT module) exit 0 with empty stdout and the message
on stderr. The old check only looked at status_code, so the stderr was
discarded and the caller failed later on json.loads('') with
"Expecting value: line 1 column 1 (char 0)".
"""

import pytest

from app.providers._winrm import (
    check_result,
    check_transport,
    clixml_error_text,
    parse_ps_json,
)

# Verbatim from a Server 2022 DC: a logon banner shares stdout with the
# pipeline, so the JSON does not start at offset 0.
BANNER = "Type logoff and press Enter when ready to exit this server.\n"

# PowerShell emits progress records on stderr as CLIXML on every first-use of
# a module. Nothing is wrong; it must not be read as a failure.
CLIXML_PROGRESS = (
    '#< CLIXML\r\n<Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/'
    'powershell/2004/04"><Obj S="progress" RefId="0"><TN RefId="0"><T>System.'
    'Management.Automation.PSCustomObject</T></TN><MS><I64 N="SourceId">1</I64>'
    '<PR N="Record"><AV>Preparing modules for first use.</AV><AI>0</AI><Nil />'
    "<PI>-1</PI><PC>-1</PC><T>Completed</T><SR>-1</SR><SD> </SD></PR></MS></Obj></Objs>"
)

CLIXML_ERROR = (
    '#< CLIXML\r\n<Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/'
    'powershell/2004/04"><S S="Error">Access is denied._x000D__x000A_</S></Objs>'
)


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


def test_progress_clixml_is_not_an_error():
    # Empty stdout + progress-only stderr: an empty result set, not a failure.
    result = _Result(std_out=b"", std_err=CLIXML_PROGRESS.encode())
    assert check_result(result) == ""


def test_error_clixml_is_decoded():
    result = _Result(std_out=b"", std_err=CLIXML_ERROR.encode())
    with pytest.raises(RuntimeError, match="Access is denied"):
        check_result(result)


def test_clixml_error_text_unescapes_newlines():
    assert clixml_error_text(CLIXML_ERROR) == "Access is denied."


def test_clixml_error_text_ignores_progress_only():
    assert clixml_error_text(CLIXML_PROGRESS) == ""


def test_plain_stderr_passes_through():
    assert clixml_error_text("  RPC server unavailable  ") == "RPC server unavailable"


def test_json_parsed_behind_logon_banner():
    out = BANNER + '[\r\n    "example.com",\r\n    "sub.example.com"\r\n]\r\n'
    assert parse_ps_json(out) == ["example.com", "sub.example.com"]


def test_object_behind_banner_is_wrapped_in_a_list():
    assert parse_ps_json(BANNER + '{"Name": "scope1"}') == [{"Name": "scope1"}]


def test_banner_containing_a_brace_does_not_derail_parsing():
    # A banner with a stray brace must not be mistaken for the start of JSON.
    out = "Notice: see {policy} before use.\n[1, 2]"
    assert parse_ps_json(out) == [1, 2]


def test_bom_prefix_is_stripped():
    assert parse_ps_json('﻿["a"]') == ["a"]


def test_empty_output_is_an_empty_list():
    assert parse_ps_json("") == []
    assert parse_ps_json("   \r\n  ") == []


def test_output_without_json_reports_what_it_got():
    with pytest.raises(RuntimeError, match="expected JSON from PowerShell"):
        parse_ps_json("Access is denied.")


def test_ntlm_transport_needs_no_extra():
    assert check_transport("ntlm") is None


def test_unavailable_transport_names_the_fix(monkeypatch):
    monkeypatch.setattr("app.providers._winrm.find_spec", lambda _: None)
    with pytest.raises(RuntimeError, match=r"pywinrm\[kerberos\]"):
        check_transport("kerberos")
