"""
Fetches all Apache Maven releases from the endoflife.date API,
derives the source ZIP download URL and SHA-512 checksum from the
official Apache CDN, and writes the result.

Output: maven/maven.json

Tag format: maven-3.9.14 -> version 3.9.14, major 3
CDN pattern:
  https://dlcdn.apache.org/maven/maven-{major}/{version}/source/apache-maven-{version}-src.zip
"""

import json
import pathlib
import re
import urllib.request

EOL_API = "https://endoflife.date/api/v1/products/maven"
OUTPUT = pathlib.Path("maven/maven.json")

CDN_BASE = "https://dlcdn.apache.org/maven/maven-{major}/{version}/source/apache-maven-{version}-src.zip"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode()


def _parse_version(version: str) -> tuple[str, str] | None:
    """
    Parse a Maven version string into (major, version).

    '3.9.14' -> ('3', '3.9.14')
    '4.0.0'  -> ('4', '4.0.0')

    Returns None if the version doesn't look like a valid semver.
    """
    m = re.fullmatch(r"(\d+)\.\d+.*", version)
    if not m:
        return None
    return m.group(1), version


def build_entry(version: str, fetcher=fetch) -> dict:
    print(f"Retrieving version: {version}")

    parsed = _parse_version(version)
    if not parsed:
        print(f"[WARN] Unexpected version format: {version}")
        return {"version": version, "url": "", "checksums": {}}

    major, ver = parsed
    zip_url = CDN_BASE.format(major=major, version=ver)
    sha_url = zip_url + ".sha512"

    try:
        sha512 = fetcher(sha_url).strip().split()[0].lower()
    except Exception as e:
        print(f"[WARN] Could not fetch checksum for version {version}: {e}")
        sha512 = None

    checksums = {"SHA-512": sha512} if sha512 else {}
    return {"version": version, "url": zip_url, "checksums": checksums}


def run(fetcher=fetch) -> list:
    data = json.loads(fetcher(EOL_API))
    releases = data.get("result", {}).get("releases", [])

    result = []
    for r in releases:
        if not r.get("name") or not r.get("latest", {}).get("name"):
            continue
        entry = build_entry(r["latest"]["name"], fetcher)
        if entry.get("checksums"):
            result.append(entry)

    return result


if __name__ == "__main__":
    results = run()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2) + "\n")
    print(f"Written {len(results)} entries to {OUTPUT}")