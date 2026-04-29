from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_command_generation_script_does_not_embed_personal_cookie_path():
    script = PROJECT_ROOT / "scripts" / "test_command_generation.py"

    assert "/Users/" not in script.read_text(encoding="utf-8")
