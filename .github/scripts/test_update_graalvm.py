import json
import pytest
from unittest.mock import patch, MagicMock
from update_graalvm import run, build_entry, get_sha256

# --- Mock Data ---

FAKE_SHA256 = "ea03f291937e6b32700fa325ec2bf77dcf570f1ace8ef0f01e752d66c035877e"

FAKE_RELEASES = [
    {
        "tag_name": "jdk-21.0.2",
        "published_at": "2024-01-16T00:00:00Z",
        "assets": [
            {
                "name": "graalvm-ce-java21-windows-x64-21.0.2.zip",
                "browser_download_url": "https://github.com/graalvm/graalvm-ce-builds/releases/download/jdk-21.0.2/graalvm-ce-java21-windows-x64-21.0.2.zip"
            },
            {
                "name": "graalvm-ce-java21-windows-x64_bin.zip",
                "browser_download_url": "https://github.com/graalvm/graalvm-ce-builds/releases/download/jdk-21.0.2/graalvm-ce-java21-windows-x64_bin.zip"
            }
        ]
    },
    {
        "tag_name": "jdk-17.0.9",
        "published_at": "2023-10-17T00:00:00Z",
        "assets": [
            {
                "name": "graalvm-ce-java17-windows-x64_bin.zip",
                "browser_download_url": "https://github.com/graalvm/graalvm-ce-builds/releases/download/jdk-17.0.9/graalvm-ce-java17-windows-x64_bin.zip"
            }
        ]
    },
    {
        "tag_name": "not-a-jdk-tag",
        "published_at": "2024-01-01T00:00:00Z",
        "assets": []
    }
]

# --- Tests ---

class TestGetSha256:
    def test_get_sha256_success(self):
        def fetcher(url):
            return f"{FAKE_SHA256}  some_filename.zip"

        result = get_sha256("https://example.com/file.sha256", fetcher)
        assert result == FAKE_SHA256

    def test_get_sha256_failure(self):
        def fetcher(url):
            raise Exception("404")

        result = get_sha256("https://example.com/file.sha256", fetcher)
        assert result is None

class TestBuildEntry:
    def test_build_entry_success(self):
        release = FAKE_RELEASES[0]
        def fetcher(url):
            return FAKE_SHA256

        entry = build_entry("21.0.2", release, fetcher)
        assert entry["version"] == "21.0.2"
        assert entry["url"] == "https://github.com/graalvm/graalvm-ce-builds/releases/download/jdk-21.0.2/graalvm-ce-java21-windows-x64_bin.zip"
        assert entry["checksums"]["SHA-256"] == FAKE_SHA256

    def test_build_entry_no_asset(self):
        release = {"assets": []}
        entry = build_entry("21.0.2", release)
        assert entry is None

class TestRun:
    def test_run_success(self):
        def fetcher(url):
            if "api.github.com" in url:
                return json.dumps(FAKE_RELEASES)
            if ".sha256" in url:
                return FAKE_SHA256
            return ""

        results = run(fetcher=fetcher)
        assert len(results) == 2
        versions = [r["version"] for r in results]
        assert "21" in versions
        assert "17" in versions

        # Verify order (sorted by major version)
        assert results[1]["version"] == "17"
        assert results[0]["version"] == "21"

    def test_run_filters_tags(self):
        def fetcher(url):
            return json.dumps(FAKE_RELEASES)

        # We need to mock build_entry because we don't want it to actually call fetch for sha256
        with patch("update_graalvm.build_entry") as mock_build:
            mock_build.side_effect = lambda v, r, f: {"version": v}
            results = run(fetcher=fetcher)
            assert len(results) == 2
            for r in results:
                assert r["version"] != "not-a-jdk-tag"

    def test_run_latest_per_major(self):
        extra_releases = FAKE_RELEASES + [
            {
                "tag_name": "jdk-21.0.1",
                "published_at": "2023-10-17T00:00:00Z",
                "assets": [{"name": "windows-x64_bin.zip", "browser_download_url": "..."}]
            }
        ]
        def fetcher(url):
            return json.dumps(extra_releases)

        with patch("update_graalvm.build_entry") as mock_build:
            mock_build.side_effect = lambda v, r, f: {"version": v}
            results = run(fetcher=fetcher)
            # Should still only have 2 versions (latest of 21 and 17)
            assert len(results) == 2
            versions = [r["version"] for r in results]
            assert "21" in versions
            assert "17" in versions
