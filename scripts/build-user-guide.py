#!/usr/bin/env python3
"""Build docs/user-guide.html from docs/user-guide.md.

Standalone HTML with embedded CSS — no external assets needed.
Run before commit when user-guide.md changes:
    python3 scripts/build-user-guide.py
"""
from pathlib import Path
import markdown

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "private" / "user-guide.md"
DST = ROOT / "docs" / "user-guide.html"

CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  line-height: 1.6;
  max-width: 920px;
  margin: 2rem auto;
  padding: 0 1.25rem;
  color: #1f2328;
  background: #ffffff;
}
@media (prefers-color-scheme: dark) {
  body { color: #e6edf3; background: #0d1117; }
  a { color: #58a6ff; }
  code { background: #161b22; }
  pre { background: #161b22; }
  th { background: #161b22; }
  tr:nth-child(even) td { background: #0d1117; }
  blockquote { color: #8b949e; border-left-color: #30363d; }
  hr { border-color: #30363d; }
  table, th, td { border-color: #30363d; }
}
h1, h2, h3, h4 { line-height: 1.25; margin-top: 1.75rem; }
h1 { border-bottom: 1px solid #d0d7de; padding-bottom: 0.3rem; }
h2 { border-bottom: 1px solid #d0d7de; padding-bottom: 0.3rem; }
a { color: #0969da; text-decoration: none; }
a:hover { text-decoration: underline; }
code {
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  font-size: 0.9em;
  background: #f6f8fa;
  padding: 0.15em 0.35em;
  border-radius: 4px;
}
pre {
  background: #f6f8fa;
  padding: 0.85rem 1rem;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 0.85em;
}
pre code { background: none; padding: 0; font-size: 1em; }
table { border-collapse: collapse; width: 100%; margin: 0.75rem 0 1.25rem; }
th, td {
  border: 1px solid #d0d7de;
  padding: 0.45rem 0.7rem;
  text-align: left;
  vertical-align: top;
}
th { background: #f6f8fa; }
blockquote {
  border-left: 4px solid #d0d7de;
  margin: 0.5rem 0;
  padding: 0.1rem 0.9rem;
  color: #57606a;
}
hr { border: 0; border-top: 1px solid #d0d7de; margin: 2rem 0; }
ul, ol { padding-left: 1.5rem; }
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IPForge User Guide</title>
<style>{css}</style>
</head>
<body>
{body}
</body>
</html>
"""


def main() -> None:
    src_text = SRC.read_text(encoding="utf-8")
    html_body = markdown.markdown(
        src_text,
        extensions=["extra", "toc", "sane_lists"],
        output_format="html5",
    )
    DST.write_text(TEMPLATE.format(css=CSS, body=html_body), encoding="utf-8")
    print(f"wrote {DST.relative_to(ROOT)} ({DST.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
