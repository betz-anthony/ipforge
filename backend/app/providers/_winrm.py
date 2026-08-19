"""Shared WinRM session construction for the msdns / msdhcp providers."""

from importlib.util import find_spec

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


def check_result(result) -> str:
    """Return stdout, raising with stderr on either failure mode.

    A PowerShell *non-terminating* error — access denied, an unreachable
    -ComputerName, a missing RSAT module — leaves the exit code at 0 and
    writes to stderr while stdout stays empty. Without this check the caller
    sees json.loads('') fail with "Expecting value: line 1 column 1", which
    says nothing about the actual cause.
    """
    stdout = result.std_out.decode(errors="replace")
    stderr = result.std_err.decode(errors="replace").strip()
    if result.status_code != 0:
        raise RuntimeError(stderr or f"WinRM command failed (exit {result.status_code})")
    if not stdout.strip() and stderr:
        raise RuntimeError(stderr)
    return stdout
