"""
Detached subprocess runner for background download jobs.
"""

from __future__ import annotations

import subprocess

from app.download_runtime_state import adapt_runtime_state
from app.job_progress import ProgressUpdate, parse_progress_update
from app.logs_utils import should_suppress_message


def run_monitored_command(
    cmd: list[str],
    _progress_placeholder=None,
    _status_placeholder=None,
    _info_placeholder=None,
    *,
    runtime_state=None,
    log_fn=None,
    progress_callback=None,
) -> int:
    """Execute one command and surface progress/log lines through callbacks."""
    state = adapt_runtime_state(runtime_state)
    emit_log = log_fn or (lambda _line: None)
    emit_progress = progress_callback or (lambda _update: None)

    try:
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        ) as proc:
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                line = raw_line.rstrip("\n")
                if not should_suppress_message(line, runtime_state=state):
                    emit_log(line)

                line_lower = line.lower()
                if any(keyword in line_lower for keyword in ("error", "failed", "unable")):
                    state["last_error"] = line

                update = parse_progress_update(line)
                if update is not None:
                    emit_progress(update)
                    continue

                if any(keyword in line_lower for keyword in ("merging", "muxing", "combining")):
                    emit_progress(ProgressUpdate(progress_percent=None, status_message="Merging"))
                elif any(keyword in line_lower for keyword in ("downloading", "fetching", "[download]")):
                    emit_progress(ProgressUpdate(progress_percent=None, status_message="Downloading"))

            return proc.wait()
    except Exception as exc:
        emit_log(f"Command execution failed: {exc}")
        return 1
