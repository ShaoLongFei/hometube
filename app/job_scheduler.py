"""
Pure scheduling helpers for HomeTube background jobs.
"""

from collections import defaultdict


def select_dispatch_batch(
    *,
    runnable_items: list[dict],
    active_per_job: dict[str, int],
    global_active_count: int,
    global_limit: int,
    default_per_job_limit: int,
    job_parallelism: dict[str, int],
) -> list[dict]:
    """
    Select a fair dispatch batch from queued job items.

    The policy is intentionally simple:
    - respect the remaining global capacity
    - respect each job's active-count cap
    - give each eligible job one slot before filling extra capacity
    """
    available_slots = max(global_limit - global_active_count, 0)
    if available_slots == 0 or not runnable_items:
        return []

    grouped_items: dict[str, list[dict]] = defaultdict(list)
    job_order: list[str] = []

    for item in runnable_items:
        job_id = item["job_id"]
        if job_id not in grouped_items:
            job_order.append(job_id)
        grouped_items[job_id].append(item)

    current_active = dict(active_per_job)
    selected: list[dict] = []

    def take_one(job_id: str) -> bool:
        if not grouped_items[job_id]:
            return False

        limit = job_parallelism.get(
            job_id,
            grouped_items[job_id][0].get("job_parallelism", default_per_job_limit),
        )
        if current_active.get(job_id, 0) >= limit:
            return False

        selected.append(grouped_items[job_id].pop(0))
        current_active[job_id] = current_active.get(job_id, 0) + 1
        return True

    # First pass: spread first slots across jobs.
    for job_id in job_order:
        if len(selected) >= available_slots:
            break
        take_one(job_id)

    # Second pass: continue in round-robin order until capacity is exhausted.
    while len(selected) < available_slots:
        dispatched_this_round = False
        for job_id in job_order:
            if len(selected) >= available_slots:
                break
            if take_one(job_id):
                dispatched_this_round = True
        if not dispatched_this_round:
            break

    return selected
