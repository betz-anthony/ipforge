"""Shared WinRM session, result handling and JSON parsing for msdns/msdhcp."""

import json
import re
from importlib.util import find_spec
from xml.sax.saxutils import unescape

# Transports whose pywinrm support lives behind an optional dependency. The
# import is checked up front: pywinrm itself only fails when the transport is
# built on the first command, which surfaces as an opaque WinRMError long
# after the provider was saved in Settings → Providers.
_OPTIONAL_TRANSPORTS = {
    "kerberos": ("requests_kerberos", "pywinrm[kerberos]"),
    "credssp": ("requests_credssp", "pywinrm[credssp]"),
}


def check_transport(transport: str) -> None:
    """Raise with an actionable message if `transport` is unavailable."""
    requirement = _OPTIONAL_TRANSPORTS.get(transport)
    if requirement is None:
        return
    module, extra = requirement
    if find_spec(module) is None:
        raise RuntimeError(
            f"WinRM transport '{transport}' needs the {module} package, which is "
            f"not installed. Rebuild the api image (it installs {extra}), or "
            f"choose the 'ntlm' transport instead."
        )


def build_session(host: str, user: str, password: str, transport: str):
    # Imported lazily so the result/transport helpers stay importable — and
    # unit-testable — in environments without pywinrm installed.
    import winrm

    check_transport(transport)
    return winrm.Session(host, auth=(user, password), transport=transport)


# PowerShell wraps the non-stdout streams as CLIXML. Progress records land
# there routinely ("Preparing modules for first use") and mean nothing went
# wrong; only <S S="Error"> entries are actual errors.
_CLIXML_ERROR_RE = re.compile(r'<S S="Error">(.*?)</S>', re.S)


def clixml_error_text(stderr: str) -> str:
    """Extract the error text from a CLIXML stderr payload.

    Returns "" when the payload holds no error records — a progress-only
    stream must not be reported as a failure. Non-CLIXML stderr is passed
    through unchanged.
    """
    stderr = stderr.strip()
    if not stderr.startswith("#< CLIXML"):
        return stderr
    parts = _CLIXML_ERROR_RE.findall(stderr)
    if not parts:
        return ""
    # PowerShell escapes CR/LF as _x000D_/_x000A_ inside CLIXML strings.
    text = "".join(parts).replace("_x000D_", "").replace("_x000A_", "\n")
    return unescape(text).strip()


def check_result(result) -> str:
    """Return stdout, raising with the real message on either failure mode.

    A PowerShell *non-terminating* error — access denied, an unreachable
    -ComputerName, a missing RSAT module — leaves the exit code at 0 and
    writes to stderr while stdout stays empty. Without this check the caller
    sees json.loads('') fail with "Expecting value: line 1 column 1", which
    says nothing about the actual cause.
    """
    stdout = result.std_out.decode(errors="replace")
    raw_stderr = result.std_err.decode(errors="replace").strip()
    error = clixml_error_text(raw_stderr)
    if result.status_code != 0:
        raise RuntimeError(
            error or raw_stderr or f"WinRM command failed (exit {result.status_code})"
        )
    if not stdout.strip() and error:
        raise RuntimeError(error)
    return stdout


def parse_ps_json(out: str) -> list:
    """Parse ConvertTo-Json output, tolerating anything printed ahead of it.

    Logon banners and $PROFILE output share stdout with the pipeline, so the
    JSON is not necessarily at offset 0 — a "Type logoff and press Enter..."
    notice in front of it made json.loads fail at char 0. Scan for the first
    bracket that actually starts valid JSON rather than trusting the offset.
    An empty pipeline produces no output at all and is not an error.
    """
    text = out.lstrip("﻿").strip()
    if not text:
        return []
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            data, _ = decoder.raw_decode(text, index)
        except ValueError:
            continue
        return data if isinstance(data, list) else [data]
    raise RuntimeError(f"expected JSON from PowerShell, got: {text[:200]}")
