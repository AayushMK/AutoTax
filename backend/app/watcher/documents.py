"""Download and archive documents linked from a content page, with SHA-256 fingerprints.

Archived PDFs live in rules/sources/ (git-ignored: large scans). Rule files record each
source's URL + sha256, and `python -m app.watcher fetch-sources` re-downloads and re-verifies them.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urljoin

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.engine.rules import RULES_DIR

ARCHIVE_DIR = RULES_DIR / "sources"
MAX_BYTES = 200 * 1024 * 1024
PDF_LINK = re.compile(r"""[^"'\s<>]*media/pdf_upload/[^"'<>]*?\.pdf""", re.IGNORECASE)


@dataclass(frozen=True)
class ArchivedDoc:
    url: str
    path: Path
    sha256: str
    size: int
    pages: int | None
    has_text_layer: bool

    @property
    def filename(self) -> str:
        return unquote(self.url.rsplit("/", 1)[-1])


def find_pdf_links(page_url: str, html: str) -> list[str]:
    links: list[str] = []
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["a", "iframe", "embed", "object"]):
        ref = tag.get("href") or tag.get("src") or tag.get("data")
        if ref and ref.lower().split("?")[0].endswith(".pdf"):
            links.append(urljoin(page_url, ref))
    for m in PDF_LINK.findall(html):  # the CMS embeds PDFs in a viewer script, not a plain link
        links.append(m if m.startswith("http") else urljoin("https://giwmscdnone.gov.np/", m.lstrip("/")))
    return list(dict.fromkeys(links))


def inspect_pdf(path: Path) -> tuple[int | None, bool]:
    try:
        reader = PdfReader(str(path))
        n = len(reader.pages)
        sample = [reader.pages[i] for i in sorted({0, n // 2, n - 1}) if n]
        text = "".join((p.extract_text() or "") for p in sample)
        return n, len(text.strip()) > 50
    except Exception:
        return None, False


def archive(url: str, client: httpx.Client, archive_dir: Path | None = None) -> ArchivedDoc:
    archive_dir = archive_dir or ARCHIVE_DIR
    archive_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    tmp = archive_dir / ".download.tmp"
    size = 0
    with client.stream("GET", url) as resp, tmp.open("wb") as f:
        resp.raise_for_status()
        for chunk in resp.iter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError(f"{url} exceeds {MAX_BYTES} bytes")
            h.update(chunk)
            f.write(chunk)
    digest = h.hexdigest()
    path = archive_dir / f"{digest[:16]}.pdf"
    tmp.replace(path)
    pages, text = inspect_pdf(path)
    return ArchivedDoc(url, path, digest, size, pages, text)


def archive_from_page(page_url: str, client: httpx.Client, archive_dir: Path | None = None) -> list[ArchivedDoc]:
    if page_url.lower().endswith(".pdf"):
        return [archive(page_url, client, archive_dir)]
    resp = client.get(page_url)
    resp.raise_for_status()
    return [archive(u, client, archive_dir) for u in find_pdf_links(page_url, resp.text)]
