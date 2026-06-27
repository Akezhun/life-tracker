from datetime import timedelta

from core.utils import cycle_start_end, fmt_dt, now, parse


def confirmation_info(task):
    required = int(task.get("required_confirmations", 1))
    current = int(task.get("current_confirmations", 0))
    if required <= 1:
        return ""
    return f" | Progress: {current}/{required}"


def tag_info(task):
    tags = task.get("tags", [])
    if not tags:
        return ""
    return " | Tags: " + ", ".join(f"#{tag}" for tag in tags)


def task_info(task):
    t = now()
    extra = confirmation_info(task) + tag_info(task)

    if task.get("type") == "deadline":
        deadline = parse(task.get("deadline"))
        if not deadline:
            return "📅 Deadline: not set" + extra

        if task.get("done"):
            done_time = parse(task.get("last_done"))
            if done_time:
                return f"✅ Completed at {fmt_dt(done_time)} | 📅 Deadline was {fmt_dt(deadline)}" + extra
            return f"✅ Completed | 📅 Deadline was {fmt_dt(deadline)}" + extra

        if task.get("failed") and task.get("archived"):
            failed_time = parse(task.get("failed_at"))
            if failed_time:
                return f"❌ Failed at {fmt_dt(failed_time)} | 📅 Deadline was {fmt_dt(deadline)}" + extra
            return f"❌ Failed | 📅 Deadline was {fmt_dt(deadline)}" + extra

        delta = deadline - t
        days_left = delta.days
        hours_left = delta.seconds // 3600

        if delta.total_seconds() >= 0:
            return f"📅 Deadline: {fmt_dt(deadline)} | ⏳ {days_left} days {hours_left} hours left" + extra
        return f"📅 Deadline: {fmt_dt(deadline)} | ⚫ overdue" + extra

    if task.get("type") == "cycle":
        cycle = task.get("cycle", "weekly")
        label, cycle_start, cycle_end = cycle_start_end(cycle, t)
        last = parse(task.get("last_done"))

        if task.get("failed_current_cycle_start") == cycle_start.isoformat():
            return f"❌ failed this cycle — next reset: {fmt_dt(cycle_end)}" + extra

        if last and cycle_start <= last < cycle_end:
            return f"✅ bro, chill — until {fmt_dt(cycle_end)}" + extra

        left = cycle_end - t
        return f"🔁 Cycle: {label} | next reset: {fmt_dt(cycle_end)} | ⏳ {left.days} days {left.seconds // 3600} hours left" + extra

    if task.get("type") == "countdown":
        days = int(task.get("days", 3))
        last = parse(task.get("last_done"))

        if not last:
            return f"⏳ Every {days} days" + extra

        target = last + timedelta(days=days)
        if now() < target:
            left = target - now()
            return f"⏳ Every {days} days | next in {left.days} days {left.seconds // 3600} hours" + extra
        return f"⚫ Every {days} days | overdue" + extra

    if task.get("type") == "gray":
        if task.get("done"):
            return "✅ Completed optional task" + extra
        if task.get("failed"):
            return "❌ Failed optional task" + extra
        return "⚪ Optional task" + extra

    return ""
