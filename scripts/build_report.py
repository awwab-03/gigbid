"""Render docs/REPORT.md to docs/GigBid_RnD_Report.pdf (A4) with Python-Markdown + Playwright's Chromium.

  python scripts/build_report.py            # needs: pip install markdown; npm ci --prefix apps/web (Playwright)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
SRC, HTML, PDF = ROOT / "docs" / "REPORT.md", ROOT / "docs" / "report.html", ROOT / "docs" / "GigBid_RnD_Report.pdf"
CSS = """
@page { size: A4; margin: 15mm 15mm 16mm 15mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 9.6pt; line-height: 1.38; color: #111; }
h1 { font-size: 17pt; margin: 0 0 2pt; } h2 { font-size: 12.2pt; margin: 11pt 0 3pt; border-bottom: 1px solid #bbb; padding-bottom: 1pt; }
h3 { font-size: 10.2pt; margin: 8pt 0 2pt; } p { margin: 3pt 0 5pt; } ul, ol { margin: 2pt 0 5pt 15pt; padding: 0; } li { margin: 1pt 0; }
table { border-collapse: collapse; margin: 4pt 0 7pt; font-size: 8.5pt; page-break-inside: avoid; }
th, td { border: 1px solid #c8c8c8; padding: 2pt 5pt; text-align: left; vertical-align: top; } th { background: #f0f0f0; }
code { font-family: Consolas, monospace; font-size: 8.3pt; background: #f4f4f4; padding: 0 2px; }
pre { background: #f6f6f6; padding: 5pt; font-size: 8pt; white-space: pre-wrap; page-break-inside: avoid; }
.sub { color: #444; font-size: 9pt; margin-bottom: 8pt; } h2 { page-break-after: avoid; }
"""
PRINT_JS = """
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('file:///' + process.argv[2].replace(/\\\\/g, '/'));
  await p.pdf({ path: process.argv[3], format: 'A4', printBackground: true, displayHeaderFooter: true,
    headerTemplate: '<span></span>',
    footerTemplate: '<div style="font-size:7pt;width:100%;text-align:center;color:#777">GigBid R&D report, page <span class="pageNumber"></span> of <span class="totalPages"></span></div>',
    margin: { top: '15mm', bottom: '16mm', left: '15mm', right: '15mm' } });
  await b.close();
})();
"""


def main() -> int:
    body = markdown.markdown(SRC.read_text(encoding="utf-8"), extensions=["tables", "fenced_code", "sane_lists"])
    HTML.write_text(f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>",
                    encoding="utf-8")
    js = ROOT / "apps" / "web" / "print_report.cjs"
    js.write_text(PRINT_JS, encoding="utf-8")
    try:
        r = subprocess.run(["node", str(js), str(HTML), str(PDF)], cwd=ROOT / "apps" / "web", capture_output=True, text=True)
    finally:
        js.unlink(missing_ok=True)
    if r.returncode:
        print(r.stderr, file=sys.stderr)
        return r.returncode
    print(f"wrote {PDF}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
