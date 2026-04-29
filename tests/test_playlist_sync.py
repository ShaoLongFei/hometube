from pathlib import Path
from types import SimpleNamespace


def test_sync_playlist_finds_bilibili_tmp_video_in_playlist_platform_workspace(
    tmp_path: Path, monkeypatch
):
    from app.playlist_sync import sync_playlist

    tmp_root = tmp_path / "tmp"
    playlist_workspace = tmp_root / "playlists" / "bilibili" / "6656145"
    video_workspace = tmp_root / "videos" / "bilibili" / "BV1abc_p2"
    dest_dir = tmp_path / "library" / "Bili Playlist"
    playlist_workspace.mkdir(parents=True)
    video_workspace.mkdir(parents=True)
    (video_workspace / "final.mkv").write_bytes(b"video")

    monkeypatch.setattr(
        "app.playlist_sync.get_settings",
        lambda: SimpleNamespace(
            TMP_DOWNLOAD_FOLDER=tmp_root,
            VIDEOS_FOLDER=tmp_path / "library",
            PLAYLIST_KEEP_OLD_VIDEOS=False,
        ),
    )

    plan = sync_playlist(
        playlist_workspace=playlist_workspace,
        dest_dir=dest_dir,
        new_url_info={
            "_type": "playlist",
            "id": "6656145",
            "title": "Bili Playlist",
            "webpage_url": "https://space.bilibili.com/1/lists?sid=6656145",
            "entries": [
                {
                    "id": "BV1abc_p2",
                    "title": "Part 2",
                    "url": "https://www.bilibili.com/video/BV1abc?p=2",
                }
            ],
        },
        new_location="/",
        new_pattern="{idx} - {pretty(title)}.{ext}",
    )

    assert [action.video_id for action in plan.videos_ready_to_move] == ["BV1abc_p2"]
    assert plan.videos_to_download == []
