"""Unit tests for update_corretto.py — all HTTP calls are mocked."""

import json
import pytest
from unittest.mock import patch
from update_corretto import ReleaseTableParser, _parse_checksums, build_entry, run

# ---------------------------------------------------------------------------
# Minimal HTML table that matches the real GitHub release page structure
# ---------------------------------------------------------------------------

WINDOWS_MD5 = "403888fc1d84a8d7a823ad7ff3ecc589"
WINDOWS_SHA = "ea03f291937e6b32700fa325ec2bf77dcf570f1ace8ef0f01e752d66c035877e"

FAKE_RELEASE_HTML = f"""
<table>
  <tr>
    <td>Linux x64</td>
    <td>JDK</td>
    <td><a href="https://corretto.aws/downloads/resources/21.0.10.7.1/amazon-corretto-21.0.10.7.1-linux-x64.tar.gz">linux.tar.gz</a></td>
    <td><code>aabbccdd11223344556677889900aabb</code> / <code>{"a" * 64}</code></td>
    <td></td>
  </tr>
  <tr>
    <td>Windows x64</td>
    <td>JDK</td>
    <td><a href="https://corretto.aws/downloads/resources/21.0.10.7.1/amazon-corretto-21.0.10.7.1-windows-x64-jdk.zip">windows-x64-jdk.zip</a></td>
    <td><code>{WINDOWS_MD5}</code> / <code>{WINDOWS_SHA}</code></td>
    <td></td>
  </tr>
</table>
"""

FAKE_EOL_RESPONSE = json.dumps({
    "releases": [
        {
            "name": "21",
            "links": [
                {"url": "https://github.com/corretto/corretto-21/releases/tag/21.0.10.7.1"}
            ],
        },
        {
            "name": "17",
            "links": [
                {"url": "https://github.com/corretto/corretto-17/releases/tag/17.0.1.1"}
            ],
        },
    ]
})


# ---------------------------------------------------------------------------
# _parse_checksums
# ---------------------------------------------------------------------------

class TestParseChecksums:
    def test_extracts_md5_and_sha256(self):
        text = f"`{WINDOWS_MD5}` /  `{WINDOWS_SHA}`"
        result = _parse_checksums(text)
        assert result["MD5"] == WINDOWS_MD5
        assert result["SHA-256"] == WINDOWS_SHA

    def test_empty_string(self):
        assert _parse_checksums("") == {}

    def test_only_md5(self):
        result = _parse_checksums(f"`{WINDOWS_MD5}`")
        assert result == {"MD5": WINDOWS_MD5}

    def test_only_sha256(self):
        result = _parse_checksums(f"`{WINDOWS_SHA}`")
        assert result == {"SHA-256": WINDOWS_SHA}

    def test_lowercases_hashes(self):
        result = _parse_checksums(WINDOWS_MD5.upper())
        assert result["MD5"] == WINDOWS_MD5.lower()


# ---------------------------------------------------------------------------
# ReleaseTableParser
# ---------------------------------------------------------------------------

class TestReleaseTableParser:
    def test_extracts_windows_row(self):
        result = ReleaseTableParser.parse(FAKE_RELEASE_HTML)
        assert result["MD5"] == WINDOWS_MD5
        assert result["SHA-256"] == WINDOWS_SHA

    def test_ignores_non_windows_rows(self):
        html = """
        <table><tr>
          <td>Linux x64</td><td>JDK</td>
          <td><a href="https://example.com/linux-x64.tar.gz">linux</a></td>
          <td><code>aabbccdd11223344556677889900aabb</code> / <code>{"b" * 64}</code></td>
          <td></td>
        </tr></table>
        """
        assert ReleaseTableParser.parse(html) == {}

    def test_empty_html(self):
        assert ReleaseTableParser.parse("") == {}

    def test_no_table(self):
        assert ReleaseTableParser.parse("<p>No table here</p>") == {}


# ---------------------------------------------------------------------------
# build_entry
# ---------------------------------------------------------------------------

class TestBuildEntry:
    RELEASE = {
        "links": [
            {"url": "https://github.com/corretto/corretto-21/releases/tag/21.0.10.7.1"}
        ]
    }

    def test_happy_path(self):
        with patch("update_corretto.fetch", return_value=FAKE_RELEASE_HTML):
            entry = build_entry("21", self.RELEASE)
        assert entry["version"] == "21"
        assert entry["url"].endswith("amazon-corretto-21-x64-windows-jdk.zip")
        assert entry["checksums"]["MD5"] == WINDOWS_MD5
        assert entry["checksums"]["SHA-256"] == WINDOWS_SHA

    def test_no_github_link(self):
        entry = build_entry("21", {"links": []})
        assert entry["checksums"] == {}

    def test_fetch_error(self):
        with patch("update_corretto.fetch", side_effect=Exception("timeout")):
            entry = build_entry("21", self.RELEASE)
        assert entry["checksums"] == {}

    def test_unparseable_page(self):
        with patch("update_corretto.fetch", return_value="<html>no table</html>"):
            entry = build_entry("21", self.RELEASE)
        assert entry["checksums"] == {}


# ---------------------------------------------------------------------------
# run (integration-level, fully mocked)
# ---------------------------------------------------------------------------

class TestRun:
    def _fetcher(self, url):
        if "endoflife" in url:
            return FAKE_EOL_RESPONSE
        return FAKE_RELEASE_HTML

    def test_returns_one_entry_per_release(self):
        results = run(fetcher=self._fetcher)
        assert len(results) == 2

    def test_versions_match(self):
        results = run(fetcher=self._fetcher)
        versions = [r["version"] for r in results]
        assert "21" in versions
        assert "17" in versions

    def test_checksums_populated(self):
        results = run(fetcher=self._fetcher)
        for entry in results:
            assert entry["checksums"]["MD5"] == WINDOWS_MD5
            assert entry["checksums"]["SHA-256"] == WINDOWS_SHA

    def test_skips_entries_without_name(self):
        eol = json.dumps({"releases": [{"links": []}]})  # no "name"

        def fetcher(url):
            return eol if "endoflife" in url else FAKE_RELEASE_HTML

        assert run(fetcher=fetcher) == []
