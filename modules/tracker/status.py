from datetime import timedelta

from core.history import log
from core.storage import save_tasks
from core.utils import cycle_start_end, now, parse, previous_cycle_bounds


def sync_pending_events(tasks):
    t = now()
    changed = False

    for task in tasks:
        if task.get("archived") and not task.get("done"):
            continue

        if task.get("type") == "deadline":
            deadline = parse(task.get("deadline"))
            if deadline and not task.get("done") and t > deadline:
                marker = deadline.isoformat()
                if task.get("deadline_fail_logged_for") != marker:
                    log(task, "fail", {
                        "type": "deadline",
                        "deadline": deadline.isoformat(),
                        "overdue_at": t.isoformat(),
                        "current_confirmations": task.get("current_confirmations", 0),
                        "required_confirmations": task.get("required_confirmations", 1),
                    })
                    task["failed"] = True
                    task["failed_at"] = t.isoformat()
                    task["deadline_fail_logged_for"] = marker
                    changed = True

        elif task.get("type") == "cycle":
            cycle = task.get("cycle", "weekly")
            _, current_start, _ = cycle_start_end(cycle, t)
            current_start_iso = current_start.isoformat()

            if task.get("cycle_last_checked_start") != current_start_iso:
                prev_start, prev_end = previous_cycle_bounds(cycle, current_start)
                last_done = parse(task.get("last_done"))

                success = last_done is not None and prev_start <= last_done < prev_end

                if not success:
                    log(task, "fail", {
                        "type": "cycle",
                        "cycle": cycle,
                        "failed_period_start": prev_start.isoformat(),
                        "failed_period_end": prev_end.isoformat(),
                        "checked_at": t.isoformat(),
                        "current_confirmations": task.get("current_confirmations", 0),
                        "required_confirmations": task.get("required_confirmations", 1),
                    })
                    task["failed_at"] = t.isoformat()

                # New cycle always visually resets. Partial progress belongs to old cycle.
                task["current_confirmations"] = 0
                task.pop("failed_current_cycle_start", None)
                task["cycle_last_checked_start"] = current_start_iso
                changed = True

        elif task.get("type") == "countdown":
            last = parse(task.get("last_done"))
            if last:
                days = int(task.get("days", 3))
                target = last + timedelta(days=days)
                marker = target.isoformat()

                if t > target and task.get("countdown_fail_logged_for") != marker:
                    log(task, "fail", {
                        "type": "countdown",
                        "days": days,
                        "target": target.isoformat(),
                        "overdue_at": t.isoformat(),
                        "current_confirmations": task.get("current_confirmations", 0),
                        "required_confirmations": task.get("required_confirmations", 1),
                    })
                    task["failed"] = True
                    task["failed_at"] = t.isoformat()
                    task["countdown_fail_logged_for"] = marker
                    changed = True

    if changed:
        save_tasks(tasks)


def get_status(task, archived=False):
    t = now()

    if archived:
        if task.get("done"):
            return "🟢"
        if task.get("failed"):
            return "⚫"
        return "⚪"

    if task.get("type") == "deadline":
        if task.get("done"):
            return "🟢"

        deadline = parse(task.get("deadline"))
        if not deadline:
            return "🟡"

        diff = (deadline - t).total_seconds()

        if diff < 0:
            return "⚫"
        if diff < 3600:
            return "🔴"
        if diff < 86400:
            return "🟠"
        return "🟢"

    if task.get("type") == "cycle":
        cycle = task.get("cycle", "weekly")
        _, cycle_start, cycle_end = cycle_start_end(cycle, t)
        last = parse(task.get("last_done"))

        if task.get("failed_current_cycle_start") == cycle_start.isoformat():
            return "⚪"

        if last and cycle_start <= last < cycle_end:
            return "🟢"

        remaining = (cycle_end - t).total_seconds()
        total = (cycle_end - cycle_start).total_seconds()

        if total <= 0:
            return "🟢"

        ratio = remaining / total

        if ratio > 0.66:
            return "🟢"
        if ratio > 0.33:
            return "🟠"
        return "🔴"

    if task.get("type") == "countdown":
        last = parse(task.get("last_done"))
        if not last:
            return "🔴"

        days = int(task.get("days", 3))
        target = last + timedelta(days=days)
        diff = (target - t).total_seconds()

        if diff < 0:
            return "⚫"
        if diff < 3600:
            return "🔴"
        if diff < 86400:
            return "🟠"
        return "🟢"

    if task.get("type") == "gray":
        if task.get("done"):
            return "🟢"
        return "⚪"

    return "🟡"
