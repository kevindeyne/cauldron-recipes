"""Unit tests for update_daemon.py — all HTTP calls are mocked."""

import pytest
from update_daemon import _parse_versions, build_entry, run

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAKE_SHA512 = "b" * 128

FAKE_INDEX_HTML = """
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
<html>
 <head><title>Index of /maven/daemon</title></head>
 <body>
<pre>      <a href="?C=N;O=D">Name</a>         <a href="?C=M;O=A">Last modified</a>      <a href="?C=S;O=A">Size</a>
<hr>
      <a href="/maven/">Parent Directory</a>                        -
      <a href="1.0.2/">1.0.2/</a>          2024-08-24 10:34        -
      <a href="1.0.3/">1.0.3/</a>          2025-09-20 21:12        -
      <a href="2.0.0-rc-3/">2.0.0-rc-3/</a>    2025-03-14 10:57        -
</pre>
</body></html>
"""


# ---------------------------------------------------------------------------
# _parse_versions
# ---------------------------------------------------------------------------

class TestParseVersions:
    def test_extracts_all_versions(self):
        versions = _parse_versions(FAKE_INDEX_HTML)
        assert versions == ["1.0.2", "1.0.3", "2.0.0-rc-3"]

    def test_skips_parent_directory(self):
        assert "/maven/" not in _parse_versions(FAKE_INDEX_HTML)

    def test_empty_index(self):
        assert _parse_versions("<html></html>") == []


# ---------------------------------------------------------------------------
# build_entry
# ---------------------------------------------------------------------------

class TestBuildEntry:
    def test_happy_path(self):
        entry = build_entry("1.0.4", fetcher=lambda url: FAKE_SHA512)
        assert entry["version"] == "1.0.4"
        assert "maven-mvnd-1.0.4-windows-amd64.zip" in entry["url"]
        assert entry["checksums"]["SHA-512"] == FAKE_SHA512

    def test_rc_version(self):
        entry = build_entry("2.0.0-rc-3", fetcher=lambda url: FAKE_SHA512)
        assert "maven-mvnd-2.0.0-rc-3-windows-amd64.zip" in entry["url"]
        assert entry["checksums"]["SHA-512"] == FAKE_SHA512

    def test_url_points_to_cdn(self):
        entry = build_entry("1.0.4", fetcher=lambda url: FAKE_SHA512)
        assert entry["url"].startswith("https://downloads.apache.org/maven/mvnd/")

    def test_sha_url_is_zip_plus_sha512(self):
        seen = []
        def capturing_fetcher(url):
            seen.append(url)
            return FAKE_SHA512
        build_entry("1.0.4", fetcher=capturing_fetcher)
        assert len(seen) == 1
        assert seen[0].endswith(".zip.sha512")

    def test_fetcher_failure_returns_empty_checksums(self):
        def bad_fetcher(url):
            raise Exception("network error")
        entry = build_entry("1.0.4", fetcher=bad_fetcher)
        assert entry["checksums"] == {}
        assert entry["version"] == "1.0.4"

    def test_sha_with_filename_suffix(self):
        entry = build_entry("1.0.4", fetcher=lambda url: f"{FAKE_SHA512}  maven-mvnd-1.0.4-windows-amd64.zip")
        assert entry["checksums"]["SHA-512"] == FAKE_SHA512


# ---------------------------------------------------------------------------
# run (integration-level, fully mocked)
# ---------------------------------------------------------------------------

class TestRun:
    def _fetcher(self, url):
        if url.endswith("/mvnd/"):
            return FAKE_INDEX_HTML
        if url.endswith(".sha512"):
            return FAKE_SHA512
        raise Exception(f"Unexpected URL in test: {url}")

    def test_returns_one_entry_per_version(self):
        assert len(run(fetcher=self._fetcher)) == 3

    def test_versions_match(self):
        versions = [r["version"] for r in run(fetcher=self._fetcher)]
        assert "1.0.2" in versions
        assert "1.0.3" in versions
        assert "2.0.0-rc-3" in versions

    def test_checksums_populated(self):
        for entry in run(fetcher=self._fetcher):
            assert entry["checksums"]["SHA-512"] == FAKE_SHA512

    def test_skips_entries_with_failed_checksums(self):
        def fetcher(url):
            if url.endswith("/mvnd/"):
                return FAKE_INDEX_HTML
            raise Exception("network error")
        assert run(fetcher=fetcher) == []

    def test_empty_index_returns_empty_list(self):
        assert run(fetcher=lambda url: "<html></html>") == []