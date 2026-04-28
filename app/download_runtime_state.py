"""
Lightweight runtime-state adapters for UI and background download execution.
"""

from __future__ import annotations

from collections.abc import MutableMapping


class MemoryRuntimeState:
    """Simple in-memory runtime state for background execution and tests."""

    def __init__(self, initial: dict | None = None):
        self._data = dict(initial or {})

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def snapshot(self) -> dict:
        return dict(self._data)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __getitem__(self, key: str):
        return self._data[key]

    def __setitem__(self, key: str, value) -> None:
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        self._data.pop(key, None)


class MappingRuntimeStateAdapter:
    """Adapter around an existing mutable mapping such as st.session_state."""

    def __init__(self, mapping: MutableMapping):
        self._mapping = mapping

    def get(self, key: str, default=None):
        return self._mapping.get(key, default)

    def delete(self, key: str) -> None:
        self._mapping.pop(key, None)

    def __contains__(self, key: str) -> bool:
        return key in self._mapping

    def __getitem__(self, key: str):
        return self._mapping[key]

    def __setitem__(self, key: str, value) -> None:
        self._mapping[key] = value

    def __delitem__(self, key: str) -> None:
        self._mapping.pop(key, None)


def adapt_runtime_state(state) -> MemoryRuntimeState | MappingRuntimeStateAdapter:
    """Normalize runtime state to a small common interface."""
    if isinstance(state, (MemoryRuntimeState, MappingRuntimeStateAdapter)):
        return state
    return MappingRuntimeStateAdapter(state)


def reset_runtime_keys(state, keys: list[str]) -> None:
    """Delete a list of transient runtime keys if present."""
    adapted = adapt_runtime_state(state)
    for key in keys:
        adapted.delete(key)
