from app.providers._ps import ps_quote

INJECTION = "x'; Remove-Item C:\\ -Recurse -Force; '"


def test_ps_quote_plain_string():
    assert ps_quote("server01") == "'server01'"


def test_ps_quote_doubles_embedded_quote():
    assert ps_quote("a'b") == "'a''b'"


def test_ps_quote_empty():
    assert ps_quote("") == "''"


def test_ps_quote_non_string():
    assert ps_quote(3600) == "'3600'"


def test_ps_quote_neutralizes_injection():
    quoted = ps_quote(INJECTION)
    # Result is a single PowerShell literal: starts and ends with a quote,
    # every embedded quote doubled, so the total quote count is even — there
    # is no unescaped quote to break out of the string.
    assert quoted.startswith("'") and quoted.endswith("'")
    assert quoted.count("'") % 2 == 0
    assert "''" in quoted  # the payload's quote was escaped, not passed through
