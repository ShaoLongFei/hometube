"""
Background job model primitives for HomeTube.
"""

from enum import StrEnum


class JobStatus(StrEnum):
    """Lifecycle states for top-level jobs."""

    QUEUED = "queued"
    RUNNING = "running"
    PARTIALLY_FAILED = "partially_failed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


class JobItemStatus(StrEnum):
    """Lifecycle states for individual executable job items."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


TERMINAL_JOB_ITEM_STATES = {
    JobItemStatus.COMPLETED,
    JobItemStatus.FAILED,
    JobItemStatus.CANCELLED,
    JobItemStatus.SKIPPED,
}

SUCCESSFUL_JOB_ITEM_STATES = {
    JobItemStatus.COMPLETED,
    JobItemStatus.SKIPPED,
}

ACTIVE_JOB_ITEM_STATES = {
    JobItemStatus.RUNNING,
}
