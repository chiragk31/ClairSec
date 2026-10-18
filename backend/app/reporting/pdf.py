"""
PDF export (FEATURES.md F12) without a new dependency.

Prints the already-rendered, already-redacted HTML report to PDF with a locally
installed Chromium browser (Microsoft Edge ships with Windows; Chrome/Chromium
elsewhere) in headless mode. The input is ClairSec's own report file; nothing
from the scanned project is executed. If no browser is found, PDF is reported as
unavailable and the HTML report (which has print CSS) remains the fallback.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
_NAMES = ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser")


def find_browser() -> str | None:
    override = os.environ.get("CLAIRSEC_PDF_BROWSER")
    if override and Path(override).is_file():
        return override
    for c in _CANDIDATES:
        if Path(c).is_file():
            return c
    for n in _NAMES:
        found = shutil.which(n)
        if found:
            return found
    return None


class PdfUnavailable(Exception):
    pass


def html_to_pdf(html_path: Path, pdf_path: Path, timeout_s: int = 90) -> Path:
    browser = find_browser()
    if browser is None:
        raise PdfUnavailable("No Edge/Chrome/Chromium found to print the PDF; open the HTML report and use Print -> Save as PDF.")
    with tempfile.TemporaryDirectory(prefix="clairsec-pdf-") as profile:
        cmd = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--disable-extensions",
            f"--user-data-dir={profile}",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}",
            html_path.resolve().as_uri(),
        ]
        subprocess.run(cmd, capture_output=True, timeout=timeout_s, check=False)
    if not pdf_path.is_file() or pdf_path.stat().st_size < 1000:
        raise PdfUnavailable("The browser did not produce a PDF; use the HTML report instead.")
    return pdf_path
