from pathlib import Path


class TestVideoCodecInspection:
    def test_probe_video_codecs_parses_video_audio_and_container(self, tmp_path: Path):
        from app.video_codec_inspection import probe_video_codecs

        sample_file = tmp_path / "sample.mp4"
        sample_file.write_bytes(b"video")

        def fake_probe(cmd, timeout=30, error_context=""):
            import json
            import subprocess

            payload = {
                "format": {
                    "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                    "duration": "123.45",
                },
                "streams": [
                    {"codec_type": "video", "codec_name": "h264"},
                    {"codec_type": "audio", "codec_name": "aac", "profile": "LC"},
                    {"codec_type": "audio", "codec_name": "aac", "profile": "LC"},
                ],
            }
            return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")

        result = probe_video_codecs(sample_file, probe_runner=fake_probe)

        assert result.container == "mp4"
        assert result.video_codec == "h264"
        assert result.audio_codecs == ["aac", "aac"]
        assert result.audio_profiles == ["lc", "lc"]
        assert result.duration_seconds == 123.45

    def test_needs_codec_normalization_only_when_not_h264_aac_family(self):
        from app.video_codec_inspection import (
            CodecInspectionResult,
            needs_codec_normalization,
        )

        compliant = CodecInspectionResult(
            container="mkv",
            video_codec="h264",
            audio_codecs=["aac-lc", "mp4a.40.2"],
            audio_profiles=["lc", None],
        )
        non_compliant = CodecInspectionResult(
            container="matroska",
            video_codec="vp9",
            audio_codecs=["opus"],
            audio_profiles=[None],
        )

        assert needs_codec_normalization(compliant) is False
        assert needs_codec_normalization(non_compliant) is True

    def test_needs_codec_normalization_rejects_missing_audio(self):
        from app.video_codec_inspection import (
            CodecInspectionResult,
            needs_codec_normalization,
        )

        no_audio = CodecInspectionResult(
            container="mkv",
            video_codec="h264",
            audio_codecs=[],
            audio_profiles=[],
        )

        assert needs_codec_normalization(no_audio) is True

    def test_format_codec_summary_formats_user_visible_codec_info(self):
        from app.video_codec_inspection import (
            CodecInspectionResult,
            format_codec_summary,
        )

        result = CodecInspectionResult(
            container="mp4",
            video_codec="h264",
            audio_codecs=["aac", "aac"],
            audio_profiles=["lc", "lc"],
        )

        assert format_codec_summary(result) == "MP4 / H.264 / AAC-LC x2"

    def test_format_codec_summary_accepts_mp4a_audio_aliases(self):
        from app.video_codec_inspection import (
            CodecInspectionResult,
            format_codec_summary,
        )

        result = CodecInspectionResult(
            container="mkv",
            video_codec="h264",
            audio_codecs=["mp4a.40.2"],
            audio_profiles=[None],
        )

        assert format_codec_summary(result) == "MKV / H.264 / AAC"
