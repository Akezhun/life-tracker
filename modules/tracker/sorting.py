from datetime import timedelta

from core.utils import cycle_start_end, now, parse
from modules.tracker.status import get_status

priority_map = {"high": 2, "mid": 1, "low": 0}


def task_sort_key(task):
    t = now()
    status = get_status(task, archived=task.get("archived", False))

    status_rank = {
        "⚫": 5,
        "🔴": 4,
        "🟠": 3,
        "🟢": 2,
        "⚪": 1,
        "🟡": 0,
    }.get(status, 0)

    priority_rank = priority_map.get(task.get("priority", "low"), 0)
    time_urgency = 0

    if task.get("type") == "deadline":
        deadline = parse(task.get("deadline"))
        if deadline:
            time_urgency = -(deadline - t).total_seconds()

    elif task.get("type") == "cycle":
        cycle = task.get("cycle", "weekly")
        _, _, cycle_end = cycle_start_end(cycle, t)
        time_urgency = -(cycle_end - t).total_seconds()

    elif task.get("type") == "countdown":
        last = parse(task.get("last_done"))
        if last:
            days = int(task.get("days", 3))
            target = last + timedelta(days=days)
            time_urgency = -(target - t).total_seconds()
        else:
            time_urgency = -(10**18)

    elif task.get("type") == "gray":
        time_urgency = 0

    return (status_rank, priority_rank, time_urgency)


def sort_tasks(tasks):
    return sorted(tasks, key=task_sort_key, reverse=True)
