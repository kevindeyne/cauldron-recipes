"""
Fetches all Amazon Corretto releases from the endoflife.date API,
scrapes the corresponding GitHub release page for each, and extracts
the Windows x64 JDK ZIP download URL and its MD5/SHA-256 checksums.

Output: main/java/corretto.json
"""

import json
import pathlib
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser

EOL_API = "https://endoflife.date/api/v1/products/amazon-corretto"
OUTPUT = pathlib.Path("main/java/corretto.json")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode()


class ReleaseTableParser(HTMLParser):
    """
    Parses the GitHub release page HTML table and extracts MD5 + SHA-256
    for the row whose download link ends in 'windows-x64-jdk.zip'.

    Table columns: Platform | Type | Download Link | Checksum (MD5 / SHA256) | Sig
    """

    def __init__(self):
        super().__init__()
        self._in_tr = False
        self._cells = []
        self._cur_cell = None
        self.result = {}

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._in_tr = True
            self._cells = []
        elif tag == "td" and self._in_tr:
            self._cur_cell = {"text": "", "hrefs": []}
        elif tag == "a" and self._cur_cell is not None:
            href = dict(attrs).get("href", "")
            if href:
                self._cur_cell["hrefs"].append(href)

    def handle_endtag(self, tag):
        if tag == "td" and self._cur_cell is not None:
            self._cells.append(self._cur_cell)
            self._cur_cell = None
        elif tag == "tr":
            self._process_row()
            self._in_tr = False
            self._cells = []

    def handle_data(self, data):
        if self._cur_cell is not None:
            self._cur_cell["text"] += data

    def _process_row(self):
        if self.result or len(self._cells) < 4:
            return
        for cell in self._cells:
            for href in cell["hrefs"]:
                if re.search(r"windows-x64-jdk\.zip$", href, re.IGNORECASE):
                    self.result = _parse_checksums(self._cells[3]["text"])
                    return

    @staticmethod
    def parse(html: str) -> dict:
        p = ReleaseTableParser()
        p.feed(html)
        return p.result


def _parse_checksums(text: str) -> dict:
    """Extract MD5 (32 hex chars) and SHA-256 (64 hex chars) from a checksum cell."""
    hashes = re.findall(r"[a-fA-F0-9]{32,64}", text)
    result = {}
    for h in hashes:
        h = h.lower()
        if len(h) == 32:
            result.setdefault("MD5", h)
        elif len(h) == 64:
            result.setdefault("SHA-256", h)
    return result


def build_entry(version: str, release: dict) -> dict:
    dl_url = (
        f"https://corretto.aws/downloads/latest/"
        f"amazon-corretto-{version}-x64-windows-jdk.zip"
    )

    gh_url = next(
        (
            l["url"]
            for l in release.get("links", [])
            if "github.com/corretto" in l.get("url", "")
            and "/releases/tag/" in l.get("url", "")
        ),
        None,
    )

    if not gh_url:
        print(f"[WARN] No GitHub release link for version {version}")
        return {"version": version, "url": dl_url, "checksums": {}}

    try:
        page = fetch(gh_url)
    except Exception as e:
        print(f"[WARN] Could not fetch {gh_url}: {e}")
        return {"version": version, "url": dl_url, "checksums": {}}

    checksums = ReleaseTableParser.parse(page)
    if not checksums:
        print(f"[WARN] Could not parse checksums for version {version} from {gh_url}")

    return {"version": version, "url": dl_url, "checksums": checksums}


def run(fetcher=fetch) -> list:
    data = json.loads(fetcher(EOL_API))
    releases = data.get("releases", [])
    return [
        build_entry(r["name"], r)
        for r in releases
        if r.get("name")
    ]


if __name__ == "__main__":
    results = run()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2) + "\n")
    print(f"Written {len(results)} entries to {OUTPUT}")
