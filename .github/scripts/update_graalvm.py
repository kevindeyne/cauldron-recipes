import json
import pathlib
import re
import urllib.request
import urllib.error
import os

GITHUB_API_URL = "https://api.github.com/repos/graalvm/graalvm-ce-builds/releases?per_page=100"
OUTPUT = pathlib.Path("java/graalvm.json")

def fetch(url: str) -> str:
    """Fetches content from a URL, using GITHUB_TOKEN if available."""
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "cauldron-recipes-scraper"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode()

def get_sha256(url: str, fetcher=fetch) -> str:
    """Fetches the SHA-256 checksum from a .sha256 file URL."""
    try:
        content = fetcher(url)
        # Expected format: "hash filename" or just "hash"
        return content.split()[0]
    except Exception as e:
        print(f"[WARN] Could not fetch SHA-256 from {url}: {e}")
        return None

def build_entry(version: str, release: dict, fetcher=fetch) -> dict:
    """Builds a single version entry for the JSON output."""
    print(f"Processing GraalVM {version}...")

    zip_url = None
    for asset in release.get("assets", []):
        if asset["name"].endswith("windows-x64_bin.zip"):
            zip_url = asset["browser_download_url"]
            break

    if not zip_url:
        print(f"[WARN] No windows-x64_bin.zip found for version {version}")
        return None

    sha256 = get_sha256(zip_url + ".sha256", fetcher)

    return {
        "version": version,
        "url": zip_url,
        "checksums": {
            "MD5": None,
            "SHA-256": sha256,
            "SHA-512": None
        }
    }

def run(fetcher=fetch) -> list:
    """Main logic to fetch and process all relevant GraalVM releases."""
    print("Fetching releases from GitHub API...")
    try:
        releases_json = fetcher(GITHUB_API_URL)
        releases = json.loads(releases_json)
    except Exception as e:
        print(f"[ERROR] Failed to fetch releases: {e}")
        return []

    # Group by major version to find the latest release for each
    versions_map = {}
    for release in releases:
        tag = release.get("tag_name", "")
        if not tag or not tag.startswith("jdk-"):
            continue

        match = re.search(r"jdk-(\d+)", tag)
        if not match:
            continue

        major = match.group(1)
        # GitHub API usually returns releases sorted by published_at DESC.
        # We ensure we take the latest for each major version.
        if major not in versions_map:
            versions_map[major] = release
        else:
            if release.get("published_at", "") > versions_map[major].get("published_at", ""):
                versions_map[major] = release

    result = []
    # Sort by major version for consistent output order
    for major in sorted(versions_map.keys(), key=int):
        release = versions_map[major]
        tag = release["tag_name"]
        version = tag.replace("jdk-", "")

        entry = build_entry(version, release, fetcher)
        if entry:
            result.append(entry)

    return result

if __name__ == "__main__":
    results = run()
    if results:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(results, indent=2) + "\n")
        print(f"Written {len(results)} entries to {OUTPUT}")
    else:
        print("No entries found.")
