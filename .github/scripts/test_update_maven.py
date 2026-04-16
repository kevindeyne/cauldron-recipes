"""Unit tests for update_maven.py — all HTTP calls are mocked."""

import json
import pytest
from update_maven import _parse_version, build_entry, run

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAKE_SHA512 = "a" * 128
FAKE_EOL_RESPONSE = json.dumps({
    "result": {
        "releases": [
            {"name": "3.9.14"},
            {"name": "3.8.9"},
            {"name": "4.0.0"},
        ]
    }
})


# ---------------------------------------------------------------------------
# _parse_version
# ---------------------------------------------------------------------------

class TestParseVersion:
    def test_three_part(self):
        assert _parse_version("3.9.14") == ("3", "3.9.14")

    def test_major_4(self):
        assert _parse_version("4.0.0") == ("4", "4.0.0")

    def test_two_part(self):
        assert _parse_version("3.9") == ("3", "3.9")

    def test_invalid_returns_none(self):
        assert _parse_version("") is None
        assert _parse_version("not-a-version") is None
        assert _parse_version("maven-3.9.14") is None


# ---------------------------------------------------------------------------
# build_entry
# ---------------------------------------------------------------------------

class TestBuildEntry:
    def test_happy_path_3x(self):
        entry = build_entry("3.9.14", fetcher=lambda url: FAKE_SHA512)
        assert entry["version"] == "3.9.14"
        assert "maven/maven-3/3.9.14/source/apache-maven-3.9.14-src.zip" in entry["url"]
        assert entry["checksums"]["SHA-512"] == FAKE_SHA512

    def test_happy_path_4x(self):
        entry = build_entry("4.0.0", fetcher=lambda url: FAKE_SHA512)
        assert "maven/maven-4/4.0.0/source/apache-maven-4.0.0-src.zip" in entry["url"]
        assert entry["checksums"]["SHA-512"] == FAKE_SHA512

    def test_sha_url_is_zip_plus_sha512(self):
        seen = []
        def capturing_fetcher(url):
            seen.append(url)
            return FAKE_SHA512
        build_entry("3.9.14", fetcher=capturing_fetcher)
        assert len(seen) == 1
        assert seen[0].endswith(".zip.sha512")

    def test_fetcher_failure_returns_empty_checksums(self):
        def bad_fetcher(url):
            raise Exception("network error")
        entry = build_entry("3.9.14", fetcher=bad_fetcher)
        assert entry["checksums"] == {}
        assert entry["version"] == "3.9.14"

    def test_sha_with_filename_suffix(self):
        # some .sha512 files include the filename after the hash
        entry = build_entry("3.9.14", fetcher=lambda url: f"{FAKE_SHA512}  apache-maven-3.9.14-src.zip")
        assert entry["checksums"]["SHA-512"] == FAKE_SHA512

    def test_invalid_version_returns_empty_checksums(self):
        entry = build_entry("not-a-version", fetcher=lambda url: FAKE_SHA512)
        assert entry["checksums"] == {}


# ---------------------------------------------------------------------------
# run (integration-level, fully mocked)
# ---------------------------------------------------------------------------

class TestRun:
    def _fetcher(self, url):
        if "endoflife" in url:
            return FAKE_EOL_RESPONSE
        if ".sha512" in url:
            return FAKE_SHA512
        raise Exception(f"Unexpected URL in test: {url}")

    def test_returns_one_entry_per_release(self):
        assert len(run(fetcher=self._fetcher)) == 3

    def test_versions_match(self):
        versions = [r["version"] for r in run(fetcher=self._fetcher)]
        assert "3.9.14" in versions
        assert "3.8.9" in versions
        assert "4.0.0" in versions

    def test_checksums_populated(self):
        for entry in run(fetcher=self._fetcher):
            assert entry["checksums"]["SHA-512"] == FAKE_SHA512

    def test_skips_entries_without_name(self):
        eol = json.dumps({"result": {"releases": [{}]}})
        assert run(fetcher=lambda url: eol if "endoflife" in url else FAKE_SHA512) == []

    def test_skips_entries_with_failed_checksums(self):
        def fetcher(url):
            if "endoflife" in url:
                return FAKE_EOL_RESPONSE
            raise Exception("network error")
        assert run(fetcher=fetcher) == []

    def test_correct_cdn_major_in_url(self):
        entries = {e["version"]: e for e in run(fetcher=self._fetcher)}
        assert "maven-3/" in entries["3.9.14"]["url"]
        assert "maven-4/" in entries["4.0.0"]["url"]
