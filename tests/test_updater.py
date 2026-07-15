"""updater.py — güncelleme kontrolü testleri."""

import time
import pytest

from core.updater import (
    _parse_semver, _is_newer, check_for_update, _extract_changelog,
    clear_cache, VERSION, CACHE_INTERVAL,
)


class TestParseSemver:
    def test_v_prefix(self):
        assert _parse_semver("v1.2.3") == (1, 2, 3)

    def test_no_prefix(self):
        assert _parse_semver("1.2.3") == (1, 2, 3)

    def test_uppercase_v(self):
        assert _parse_semver("V2.0.0") == (2, 0, 0)

    def test_two_parts(self):
        assert _parse_semver("v1.0") == (1, 0, 0)

    def test_invalid_letters(self):
        assert _parse_semver("vabc") == (0, 0, 0)

    def test_empty(self):
        assert _parse_semver("") == (0, 0, 0)


class TestIsNewer:
    def test_higher_major(self):
        assert _is_newer("v2.0.0", "1.0.0") is True

    def test_higher_minor(self):
        assert _is_newer("v1.1.0", "1.0.0") is True

    def test_higher_patch(self):
        assert _is_newer("v1.0.1", "1.0.0") is True

    def test_same_version(self):
        assert _is_newer("v1.0.0", "1.0.0") is False

    def test_lower_version(self):
        assert _is_newer("v0.9.9", "1.0.0") is False

    def test_equal_current_version(self):
        assert _is_newer(VERSION, VERSION) is False


class TestExtractChangelog:
    def test_with_installation_separator(self):
        body = "## What's Changed\n\n- Fix X\n\n---\n\n## Installation\n\n..."
        result = _extract_changelog(body)
        assert "Fix X" in result
        assert "Installation" not in result

    def test_with_kurulum_separator(self):
        body = "## What's Changed\n\n- Fix X\n\n---\n\n## Kurulum\n\n..."
        result = _extract_changelog(body)
        assert "Fix X" in result
        assert "Kurulum" not in result

    def test_with_plain_separator(self):
        body = "## What's Changed\n\n- Fix X\n\n---\n\nSome other content"
        result = _extract_changelog(body)
        assert "Fix X" in result
        assert "Some other" not in result

    def test_no_separator(self):
        body = "Just changelog content"
        assert _extract_changelog(body) == "Just changelog content"

    def test_empty_body(self):
        assert _extract_changelog("") == ""


class TestCheckForUpdate:
    def setup_method(self):
        clear_cache()

    def teardown_method(self):
        clear_cache()

    def test_returns_network_error_on_failure(self, monkeypatch):
        """Network hatası {'error': 'network'} döndürmeli — crash değil."""
        import core.updater as mod
        monkeypatch.setattr(mod, "fetch_latest_release", lambda: None)
        result = check_for_update()
        assert result is not None
        assert result.get("error") == "network"

    def test_returns_none_when_up_to_date(self, monkeypatch):
        import core.updater as mod
        monkeypatch.setattr(mod, "fetch_latest_release", lambda: {"tag_name": "v" + VERSION})
        assert check_for_update() is None

    def test_returns_info_when_newer(self, monkeypatch):
        import core.updater as mod
        monkeypatch.setattr(mod, "fetch_latest_release", lambda: {
            "tag_name": "v99.0.0",
            "html_url": "https://github.com/s-balli/latex-editor/releases/v99.0.0",
            "body": "New release",
        })
        result = check_for_update()
        assert result is not None
        assert result["tag"] == "v99.0.0"
        assert "html_url" not in result
        assert result["url"] == "https://github.com/s-balli/latex-editor/releases/v99.0.0"
        assert result["notes"] == "New release"

    def test_returns_network_error_when_tag_missing(self, monkeypatch):
        """Tag yoksa {'error': 'network'} döndürmeli."""
        import core.updater as mod
        monkeypatch.setattr(mod, "fetch_latest_release", lambda: {"body": "no tag"})
        result = check_for_update()
        assert result is not None
        assert result.get("error") == "network"

    def test_force_bypasses_cache(self, monkeypatch):
        """force=True cache'i bypass etmeli."""
        import core.updater as mod
        call_count = [0]
        def mock_fetch():
            call_count[0] += 1
            return {"tag_name": "v99.0.0", "html_url": "url", "body": "x"}
        monkeypatch.setattr(mod, "fetch_latest_release", mock_fetch)
        check_for_update()
        assert call_count[0] == 1
        check_for_update(force=True)
        assert call_count[0] == 2

    def test_cache_prevents_repeat_calls(self, monkeypatch):
        """Cache 24h içinde tekrar API çağrısı yapmamalı."""
        import core.updater as mod
        call_count = [0]
        def mock_fetch():
            call_count[0] += 1
            return {"tag_name": "v99.0.0", "html_url": "url", "body": "x"}
        monkeypatch.setattr(mod, "fetch_latest_release", mock_fetch)
        check_for_update()
        check_for_update()
        check_for_update()
        assert call_count[0] == 1

    def test_cache_prevents_repeat_calls_when_up_to_date(self, monkeypatch):
        """'Güncelleme yok' durumu da cache'lenmeli — tekrar API çağrısı yapmamalı.

        Regression: eskiden sadece 'yeni sürüm var' (positive) cache'leniyordu;
        up-to-date durumunda _cached_result=None set edilmesine rağmen cache kontrolü
        'is not None' gerektirdiği için her çağrıda yeniden fetch edilirdi.
        """
        import core.updater as mod
        call_count = [0]
        def mock_fetch():
            call_count[0] += 1
            return {"tag_name": "v" + VERSION}  # mevcut sürüm → güncelleme yok
        monkeypatch.setattr(mod, "fetch_latest_release", mock_fetch)
        assert check_for_update() is None
        assert check_for_update() is None
        assert check_for_update() is None
        assert call_count[0] == 1  # tek fetch — sonraki çağrılar cacheden döner

    def test_cache_returns_same_result(self, monkeypatch):
        """Cache aynı sonucu döndürmeli."""
        import core.updater as mod
        monkeypatch.setattr(mod, "fetch_latest_release", lambda: {
            "tag_name": "v99.0.0", "html_url": "url", "body": "x"
        })
        r1 = check_for_update()
        r2 = check_for_update()
        assert r1 == r2
        assert r1 is not None
