from __future__ import annotations

import subprocess


class TestPlaylistEntryExpansion:
    def test_expands_bilibili_multipart_entry_into_part_entries(self):
        from app.playlist_entry_expansion import expand_playlist_entries

        entries = [
            {
                "id": "BV1abc",
                "title": "Parent Video",
                "url": "https://www.bilibili.com/video/BV1abc",
                "playlist_index": 7,
            },
            {
                "id": "normal",
                "title": "Normal Video",
                "url": "https://www.youtube.com/watch?v=normal",
                "playlist_index": 8,
            },
        ]

        expanded = expand_playlist_entries(
            entries,
            entry_info_resolver=lambda url: {
                "_type": "playlist",
                "entries": [
                    {"url": f"{url}?p=1"},
                    {"url": f"{url}?p=2"},
                ],
            },
        )

        assert [
            {
                "id": item["id"],
                "url": item["url"],
                "title": item["title"],
                "playlist_index": item["playlist_index"],
                "parent_video_id": item.get("parent_video_id"),
                "multipart_index": item.get("multipart_index"),
            }
            for item in expanded
        ] == [
            {
                "id": "BV1abc_p1",
                "url": "https://www.bilibili.com/video/BV1abc?p=1",
                "title": "Parent Video P01",
                "playlist_index": 1,
                "parent_video_id": "BV1abc",
                "multipart_index": 1,
            },
            {
                "id": "BV1abc_p2",
                "url": "https://www.bilibili.com/video/BV1abc?p=2",
                "title": "Parent Video P02",
                "playlist_index": 2,
                "parent_video_id": "BV1abc",
                "multipart_index": 2,
            },
            {
                "id": "normal",
                "url": "https://www.youtube.com/watch?v=normal",
                "title": "Normal Video",
                "playlist_index": 3,
                "parent_video_id": None,
                "multipart_index": None,
            },
        ]

    def test_resolver_failures_keep_original_entry(self):
        from app.playlist_entry_expansion import expand_playlist_entries

        expanded = expand_playlist_entries(
            [
                {
                    "id": "BV1abc",
                    "title": "Parent Video",
                    "url": "https://www.bilibili.com/video/BV1abc",
                }
            ],
            entry_info_resolver=lambda _url: (_ for _ in ()).throw(
                RuntimeError("probe failed")
            ),
        )

        assert len(expanded) == 1
        assert expanded[0]["id"] == "BV1abc"
        assert expanded[0]["playlist_index"] == 1

    def test_fetch_flat_playlist_info_uses_cookies_and_parses_json(self):
        from app.playlist_entry_expansion import fetch_flat_playlist_info

        calls = []

        def fake_run(cmd, capture_output, text, timeout):
            calls.append(
                {
                    "cmd": cmd,
                    "capture_output": capture_output,
                    "text": text,
                    "timeout": timeout,
                }
            )
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout='{"_type":"playlist","entries":[{"url":"part"}]}',
                stderr="",
            )

        info = fetch_flat_playlist_info(
            "https://www.bilibili.com/video/BV1abc",
            cookies_params=["--cookies", "/tmp/bili.txt"],
            run_cmd=fake_run,
        )

        assert info == {"_type": "playlist", "entries": [{"url": "part"}]}
        assert calls == [
            {
                "cmd": [
                    "yt-dlp",
                    "-J",
                    "--skip-download",
                    "--flat-playlist",
                    "--cookies",
                    "/tmp/bili.txt",
                    "https://www.bilibili.com/video/BV1abc",
                ],
                "capture_output": True,
                "text": True,
                "timeout": 30,
            }
        ]
