"""
Discovers all Apache Maven Daemon (mvnd) releases from the Apache CDN
directory listing, then fetches the Windows x64 ZIP download URL and
SHA-512 checksum for each version.

Output: maven/daemon.json

CDN root:  https://downloads.apache.org/maven/mvnd/
Asset:     maven-mvnd-{version}-windows-amd64.zip
Checksum:  maven-mvnd-{version}-windows-amd64.zip.sha512
"""

import json
import pathlib
import re
import urllib.request

CDN_ROOT = "https://downloads.apache.org/maven/mvnd/"
OUTPUT = pathlib.Path("maven/daemon.json")

ASSET_FILENAME = "maven-mvnd-{version}-windows-amd64.zip"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode()


def _parse_versions(index_html: str) -> list[str]:
    """
    Extract version directory names from an Apache directory listing.

    Matches hrefs like '1.0.4/' or '2.0.0-rc-3/' — skips parent dir links.
    """
    return re.findall(r'href="([\d][^"/]+)/"', index_html)


def build_entry(version: str, fetcher=fetch) -> dict:
    print(f"Retrieving version: {version}")

    filename = ASSET_FILENAME.format(version=version)
    zip_url = CDN_ROOT + version + "/" + filename
    sha_url = zip_url + ".sha512"

    try:
        sha512 = fetcher(sha_url).strip().split()[0].lower()
    except Exception as e:
        print(f"[WARN] Could not fetch checksum for version {version}: {e}")
        sha512 = None

    checksums = {"SHA-512": sha512} if sha512 else {}
    return {"version": version, "url": zip_url, "checksums": checksums}


def run(fetcher=fetch) -> list:
    index_html = fetcher(CDN_ROOT)
    versions = _parse_versions(index_html)

    result = []
    for version in versions:
        entry = build_entry(version, fetcher)
        if entry.get("checksums"):
            result.append(entry)

    return result


if __name__ == "__main__":
    results = run()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2) + "\n")
    print(f"Written {len(results)} entries to {OUTPUT}")