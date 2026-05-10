"""Markdown report → PDF, via inline-styled HTML and Chrome headless.

Used both as a post-step in the scan pipeline (write_run hooks) and via
the `canslim report-pdf` CLI command for ad-hoc conversion of existing reports.

Chrome is required (Chromium / Brave / Edge also work). On macOS the
default Google Chrome bundle is auto-detected. If no browser is found
this module logs a warning and skips PDF generation rather than failing
the scan — markdown remains the canonical output.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

log = logging.getLogger("canslim.pdf")


_PRINT_CSS = """
@page { size: Letter; margin: 0.6in 0.5in; }
body { font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
       font-size: 10.5pt; color: #222; line-height: 1.45; max-width: 7.5in; margin: 0 auto; }
h1 { font-size: 20pt; border-bottom: 2px solid #333; padding-bottom: 6pt; margin-top: 12pt; }
h2 { font-size: 15pt; border-bottom: 1px solid #ccc; padding-bottom: 4pt;
     margin-top: 18pt; page-break-after: avoid; }
h3 { font-size: 12.5pt; margin-top: 14pt; page-break-after: avoid; color: #1a4480; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 9.5pt;
        page-break-inside: avoid; }
th, td { border: 1px solid #ddd; padding: 4pt 6pt; text-align: left; vertical-align: top; }
th { background: #f3f3f3; font-weight: 600; }
tr:nth-child(even) { background: #fafafa; }
code { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 9.5pt;
       background: #f5f5f5; padding: 1px 4px; border-radius: 3px; }
pre { background: #f5f5f5; padding: 8pt; border-radius: 4px; overflow-x: auto; }
img { max-width: 6.5in; height: auto; display: block; margin: 6pt 0; page-break-inside: avoid; }
ul, ol { margin: 6pt 0 6pt 20pt; }
em { color: #555; }
hr { border: none; border-top: 1px solid #ccc; margin: 12pt 0; }
"""


# Common Chrome / Chromium / Brave / Edge install locations across platforms.
# First match wins. Override via CANSLIM_CHROME env var.
_CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/brave-browser",
    "/snap/bin/chromium",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


def _find_chrome() -> Optional[str]:
    env = os.environ.get("CANSLIM_CHROME")
    if env and Path(env).exists():
        return env
    for cand in _CHROME_CANDIDATES:
        if Path(cand).exists():
            return cand
    # PATH fallbacks
    for name in ("google-chrome", "chromium", "chromium-browser", "brave-browser"):
        which = shutil.which(name)
        if which:
            return which
    return None


def _markdown_to_html(md_text: str, title: str = "CANSLIM Scan Report") -> str:
    try:
        import markdown  # python-markdown
    except ImportError as e:
        raise RuntimeError(
            "The `markdown` package is required for PDF rendering. "
            "Install with: pip install markdown"
        ) from e
    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"],
    )
    return (
        f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>{title}</title>'
        f"<style>{_PRINT_CSS}</style></head><body>{body}</body></html>"
    )


def render_pdf(md_path: Path, pdf_path: Optional[Path] = None) -> Optional[Path]:
    """Render `md_path` to PDF.

    Writes a sibling `.html` (intermediate, kept for inspection) and `.pdf`.
    Returns the PDF path on success, or None if Chrome wasn't found
    (logs a warning rather than raising — the markdown is the canonical output).
    """
    md_path = Path(md_path)
    if not md_path.exists():
        raise FileNotFoundError(f"Markdown not found: {md_path}")
    pdf_path = Path(pdf_path) if pdf_path else md_path.with_suffix(".pdf")
    html_path = md_path.with_suffix(".html")

    html_path.write_text(_markdown_to_html(md_path.read_text(), title=md_path.stem))

    chrome = _find_chrome()
    if not chrome:
        log.warning(
            "PDF generation skipped: no Chrome / Chromium / Brave / Edge found. "
            "Set CANSLIM_CHROME=/path/to/chrome to enable. (HTML written: %s)",
            html_path,
        )
        return None

    file_url = f"file://{html_path.resolve()}"
    try:
        subprocess.run(
            [
                chrome,
                "--headless",
                "--disable-gpu",
                "--no-pdf-header-footer",
                "--print-to-pdf-no-header",
                "--virtual-time-budget=10000",
                f"--print-to-pdf={pdf_path}",
                file_url,
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as e:
        log.warning(
            "PDF generation failed (chrome exit %d): %s",
            e.returncode, e.stderr.decode(errors="replace")[:500],
        )
        return None
    except subprocess.TimeoutExpired:
        log.warning("PDF generation timed out after 120s")
        return None

    if not pdf_path.exists():
        log.warning("Chrome reported success but PDF not present at %s", pdf_path)
        return None

    return pdf_path
