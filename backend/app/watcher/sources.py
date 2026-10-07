"""Scan official listing pages and diff them against the stored state."""

from __future__ import annotations

import json
import re
import ssl
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import certifi
import httpx
import yaml
from bs4 import BeautifulSoup

from app.engine.rules import RULES_DIR

SOURCES_FILE = RULES_DIR / "watch_sources.yaml"
STATE_FILE = RULES_DIR / "watch_state.json"
USER_AGENT = "AutoTax-RuleWatch/1.0 (+tax rule change monitor)"


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    url: str
    item_pattern: str


@dataclass(frozen=True)
class Item:
    source_id: str
    url: str
    title: str


@dataclass
class WatchConfig:
    sources: list[Source]
    relevant_keywords: list[str]
    ignore_keywords: list[str]

    def is_relevant(self, title: str) -> bool:
        t = title.casefold()
        if any(k.casefold() in t for k in self.ignore_keywords):
            return False
        return any(_keyword_in(k.casefold(), t) for k in self.relevant_keywords)


def _keyword_in(keyword: str, text: str) -> bool:
    # Short ASCII keywords ("tds") must match as whole words.
    if keyword.isascii() and len(keyword) <= 4:
        return re.search(rf"\b{re.escape(keyword)}\b", text) is not None
    return keyword in text


def load_config(path: Path | None = None) -> WatchConfig:
    path = path or SOURCES_FILE
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return WatchConfig(
        sources=[Source(**s) for s in data["sources"]],
        relevant_keywords=data["relevant_keywords"],
        ignore_keywords=data.get("ignore_keywords", []),
    )


def parse_listing(source: Source, html: str) -> list[Item]:
    soup = BeautifulSoup(html, "html.parser")
    pattern = re.compile(source.item_pattern)
    items: dict[str, Item] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not pattern.search(href):
            continue
        url = urljoin(source.url, href)
        title = " ".join(a.get_text(" ", strip=True).split())
        # The CMS often repeats a link (image + text); keep the version with a title.
        if url not in items or (title and not items[url].title):
            items[url] = Item(source.id, url, title)
    return [i for i in items.values() if i.title]


def fetch_listing(source: Source, client: httpx.Client) -> list[Item]:
    resp = client.get(source.url)
    resp.raise_for_status()
    return parse_listing(source, resp.text)


# --- state -----------------------------------------------------------------------------------

def load_state(path: Path | None = None) -> dict:
    path = path or STATE_FILE
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"seen": {}}


def save_state(state: dict, path: Path | None = None) -> None:
    path = path or STATE_FILE
    state["seen"] = dict(sorted(state["seen"].items()))
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def diff_new(items: list[Item], state: dict) -> list[Item]:
    """Items not seen before (keyed by URL, so the same document across sources counts once)."""
    out, seen_now = [], set()
    for i in items:
        if i.url in state["seen"] or i.url in seen_now:
            continue
        seen_now.add(i.url)
        out.append(i)
    return out


def mark_seen(items: list[Item], state: dict, relevant: set[str]) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for i in items:
        state["seen"][i.url] = {**asdict(i), "first_seen": now, "relevant": i.url in relevant}


# Some government servers (e.g. mof.gov.np) omit their intermediate certificate. Browsers and
# macOS fetch it automatically; OpenSSL on Linux CI does not. We ship the missing intermediates
# (public CA certs, chaining to roots already in certifi) instead of disabling verification.
INTERMEDIATES = Path(__file__).parent / "certs" / "intermediates.pem"


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=certifi.where())
    ctx.load_verify_locations(cafile=str(INTERMEDIATES))
    return ctx


def http_client() -> httpx.Client:
    return httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": USER_AGENT}, verify=_ssl_context())
