def ps_quote(value) -> str:
    """Return value as a safe PowerShell single-quoted string literal.

    A PowerShell single-quoted string is terminated by the next quote; an
    embedded quote is escaped by doubling it. Wrapping every interpolated
    value through this prevents user input from breaking out of the quote
    and injecting arbitrary commands on the WinRM target.
    """
    return "'" + str(value).replace("'", "''") + "'"
