class TestLogsRuntimeState:
    def test_should_suppress_message_tracks_po_token_warning_in_custom_runtime_state(self):
        from app.download_runtime_state import MemoryRuntimeState
        from app.logs_utils import should_suppress_message

        state = MemoryRuntimeState()
        message = "There are missing subtitles languages because a PO Token was not provided for GVS"

        assert should_suppress_message(message, runtime_state=state) is False
        assert state.get("po_token_warning_shown") is True
        assert should_suppress_message(message, runtime_state=state) is True
