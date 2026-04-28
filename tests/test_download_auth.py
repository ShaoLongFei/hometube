from pathlib import Path


class TestDownloadAuth:
    def test_resolve_cookies_params_prefers_managed_site_cookies(self, tmp_path: Path):
        from app.download_auth import resolve_cookies_params
        from app.download_runtime_state import MemoryRuntimeState

        result = resolve_cookies_params(
            url="https://www.bilibili.com/video/BV1xx",
            runtime_state=MemoryRuntimeState({"cookies_method": "browser"}),
            cookies_file_path=str(tmp_path / "cookies.txt"),
            managed_cookies_params_fn=lambda url: ["--cookies", "/managed/bilibili.txt"],
            core_build_cookies_params_fn=lambda **kwargs: ["unexpected"],
            log_fn=lambda _message: None,
        )

        assert result == ["--cookies", "/managed/bilibili.txt"]

    def test_resolve_cookies_params_uses_browser_from_runtime_state(self, tmp_path: Path):
        from app.download_auth import resolve_cookies_params
        from app.download_runtime_state import MemoryRuntimeState

        calls: dict[str, object] = {}

        def fake_core_build(**kwargs):
            calls["kwargs"] = kwargs
            return ["--cookies-from-browser", "chrome:Profile 1"]

        result = resolve_cookies_params(
            url="https://www.youtube.com/watch?v=abc123",
            runtime_state=MemoryRuntimeState(
                {
                    "cookies_method": "browser",
                    "browser_select": "chrome",
                    "browser_profile": "Profile 1",
                }
            ),
            cookies_file_path=str(tmp_path / "cookies.txt"),
            managed_cookies_params_fn=lambda url: [],
            core_build_cookies_params_fn=fake_core_build,
            log_fn=lambda _message: None,
        )

        assert result == ["--cookies-from-browser", "chrome:Profile 1"]
        assert calls["kwargs"] == {
            "cookies_method": "browser",
            "browser_select": "chrome",
            "browser_profile": "Profile 1",
        }

    def test_resolve_cookies_params_from_config_prefers_cookie_file(self, tmp_path: Path):
        from app.download_auth import resolve_cookies_params_from_config

        cookies_file = tmp_path / "cookies.txt"
        cookies_file.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

        result = resolve_cookies_params_from_config(
            url="https://www.youtube.com/watch?v=abc123",
            cookies_file_path=str(cookies_file),
            cookies_from_browser="chrome",
            managed_cookies_params_fn=lambda url: [],
            core_build_cookies_params_fn=lambda **kwargs: [kwargs["cookies_method"], kwargs.get("cookies_file_path", "")],
            is_valid_browser_fn=lambda browser: browser == "chrome",
        )

        assert result == ["file", str(cookies_file)]

    def test_resolve_cookies_params_from_config_falls_back_to_browser(self):
        from app.download_auth import resolve_cookies_params_from_config

        result = resolve_cookies_params_from_config(
            url="https://www.youtube.com/watch?v=abc123",
            cookies_file_path="",
            cookies_from_browser="chrome",
            managed_cookies_params_fn=lambda url: [],
            core_build_cookies_params_fn=lambda **kwargs: [kwargs["cookies_method"], kwargs.get("browser_select", "")],
            is_valid_browser_fn=lambda browser: browser == "chrome",
        )

        assert result == ["browser", "chrome"]
