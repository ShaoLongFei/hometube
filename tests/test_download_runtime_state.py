class TestDownloadRuntimeState:
    def test_memory_runtime_state_supports_mutation_and_reset(self):
        from app.download_runtime_state import MemoryRuntimeState, reset_runtime_keys

        state = MemoryRuntimeState({"keep": 1, "drop": 2})
        state["new"] = 3

        assert state.get("keep") == 1
        assert state.get("new") == 3
        assert "drop" in state

        reset_runtime_keys(state, ["drop", "missing"])

        assert "drop" not in state
        assert state.snapshot() == {"keep": 1, "new": 3}

    def test_mapping_runtime_state_adapter_updates_underlying_mapping(self):
        from app.download_runtime_state import adapt_runtime_state

        backing = {"flag": True}
        state = adapt_runtime_state(backing)
        state["value"] = "x"
        state.delete("flag")

        assert state.get("value") == "x"
        assert "flag" not in state
        assert backing == {"value": "x"}
