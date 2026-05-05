import os
from pathlib import Path
import zipfile

import pytest


SAMPLE_COOKIES_TEXT = """# Netscape HTTP Cookie File
.youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tyt-sid
www.youtube.com\tFALSE\t/\tTRUE\t2147483647\tSSID\tyt-ssid
.bilibili.com\tTRUE\t/\tFALSE\t2147483647\tSESSDATA\tbili-session
space.bilibili.com\tFALSE\t/\tFALSE\t2147483647\tDedeUserID\tbili-user
"""


class TestSiteCookiesParsing:
    def test_groups_cookies_by_primary_domain(self):
        from app.site_cookies import parse_cookies_text_by_site

        grouped = parse_cookies_text_by_site(SAMPLE_COOKIES_TEXT)

        assert sorted(grouped.keys()) == ["bilibili.com", "youtube.com"]
        assert len(grouped["youtube.com"]) == 2
        assert len(grouped["bilibili.com"]) == 2

    def test_rejects_invalid_cookies_text(self):
        from app.site_cookies import parse_cookies_text_by_site

        try:
            parse_cookies_text_by_site("not a cookies file")
        except ValueError as exc:
            assert "No valid cookie entries" in str(exc)
        else:
            raise AssertionError("Expected invalid cookies text to raise ValueError")

    def test_primary_domain_uses_public_suffix_rules(self):
        from app.site_cookies import get_primary_domain

        assert get_primary_domain("www.example.co.nz") == "example.co.nz"
        assert get_primary_domain("assets.example.com.ar") == "example.com.ar"
        assert get_primary_domain("project.github.io") == "project.github.io"
        assert get_primary_domain("space.bilibili.com") == "bilibili.com"


class TestSiteCookiesStorage:
    def test_saves_one_file_per_site(self, tmp_path):
        from app.site_cookies import save_cookies_text_by_site

        result = save_cookies_text_by_site(SAMPLE_COOKIES_TEXT, tmp_path)

        assert sorted(result.keys()) == ["bilibili.com", "youtube.com"]
        assert (tmp_path / "youtube.com.txt").exists()
        assert (tmp_path / "bilibili.com.txt").exists()

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permission check")
    def test_saves_cookies_with_private_permissions(self, tmp_path):
        from app.site_cookies import save_cookies_text_by_site

        cookies_dir = tmp_path / "site-cookies"
        result = save_cookies_text_by_site(SAMPLE_COOKIES_TEXT, cookies_dir)

        assert (cookies_dir.stat().st_mode & 0o777) == 0o700
        assert (result["youtube.com"].stat().st_mode & 0o777) == 0o600

    def test_lists_saved_site_cookies(self, tmp_path):
        from app.site_cookies import list_saved_site_cookies, save_cookies_text_by_site

        save_cookies_text_by_site(SAMPLE_COOKIES_TEXT, tmp_path)
        saved = list_saved_site_cookies(tmp_path)

        assert [entry["site"] for entry in saved] == ["bilibili.com", "youtube.com"]
        assert saved[0]["cookie_count"] > 0
        assert saved[0]["path"].endswith(".txt")

    def test_deletes_saved_site_cookies(self, tmp_path):
        from app.site_cookies import delete_site_cookies_file, save_cookies_text_by_site

        save_cookies_text_by_site(SAMPLE_COOKIES_TEXT, tmp_path)

        assert delete_site_cookies_file("youtube.com", tmp_path) is True
        assert (tmp_path / "youtube.com.txt").exists() is False


class TestSiteCookiesResolution:
    def test_resolves_matching_cookies_file_for_url(self, tmp_path):
        from app.site_cookies import (
            resolve_site_cookies_file_for_url,
            save_cookies_text_by_site,
        )

        save_cookies_text_by_site(SAMPLE_COOKIES_TEXT, tmp_path)

        path = resolve_site_cookies_file_for_url(
            "https://www.youtube.com/watch?v=test",
            tmp_path,
        )

        assert path == tmp_path / "youtube.com.txt"

    def test_returns_none_when_no_site_match_exists(self, tmp_path):
        from app.site_cookies import resolve_site_cookies_file_for_url

        path = resolve_site_cookies_file_for_url("https://vimeo.com/123456", tmp_path)

        assert path is None

    def test_builds_ytdlp_cookies_args_for_matching_site(self, tmp_path):
        from app.site_cookies import build_site_cookies_params, save_cookies_text_by_site

        save_cookies_text_by_site(SAMPLE_COOKIES_TEXT, tmp_path)

        params = build_site_cookies_params(
            "https://space.bilibili.com/3546624353634458/lists?sid=6656145",
            tmp_path,
        )

        assert params == ["--cookies", str(tmp_path / "bilibili.com.txt")]

    def test_ignores_empty_managed_site_cookies_file(self, tmp_path):
        from app.site_cookies import build_site_cookies_params

        (tmp_path / "bilibili.com.txt").write_text("", encoding="utf-8")

        params = build_site_cookies_params(
            "https://space.bilibili.com/3546624353634458/lists?sid=6656145",
            tmp_path,
        )

        assert params == []

    def test_ignores_header_only_managed_site_cookies_file(self, tmp_path):
        from app.site_cookies import build_site_cookies_params

        (tmp_path / "bilibili.com.txt").write_text(
            "# Netscape HTTP Cookie File\n",
            encoding="utf-8",
        )

        params = build_site_cookies_params(
            "https://space.bilibili.com/3546624353634458/lists?sid=6656145",
            tmp_path,
        )

        assert params == []


class TestExtensionBundle:
    def test_builds_extension_zip_from_directory(self, tmp_path):
        extension_dir = tmp_path / "extension"
        extension_dir.mkdir()
        (extension_dir / "manifest.json").write_text('{"name":"test"}', encoding="utf-8")
        (extension_dir / "popup.html").write_text("<html></html>", encoding="utf-8")

        from app.extension_bundle import build_extension_zip_bytes

        zip_bytes = build_extension_zip_bytes(extension_dir)

        with zipfile.ZipFile(Path(tmp_path / "bundle.zip"), "w") as _:
            pass

        bundle_path = tmp_path / "bundle.zip"
        bundle_path.write_bytes(zip_bytes)
        with zipfile.ZipFile(bundle_path) as archive:
            names = sorted(archive.namelist())

        assert names == ["manifest.json", "popup.html"]

    def test_content_script_bridges_streamlit_iframe_extension_detection(self):
        content_script = Path(
            "browser-extension/hometube-cookie-export/content.js"
        ).read_text(encoding="utf-8")

        assert "event.source !== window" not in content_script
        assert "event.source || window" in content_script
        assert "HOMETUBE_EXTENSION_PONG" in content_script
