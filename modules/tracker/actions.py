from datetime import timedelta

from core.history import log
from core.storage import save_tasks
from core.utils import cycle_start_end, now, parse


def _reset_confirmations(task):
    task["current_confirmations"] = 0


def _confirmation_details(task):
    return {
        "current_confirmations": int(task.get("current_confirmations", 0)),
        "required_confirmations": int(task.get("required_confirmations", 1)),
    }


def _touch(task):
    task["last_local_edit_at"] = now().isoformat()


def _complete_task(task, t, details):
    task["last_done"] = t.isoformat()
    task["failed"] = False
    task["failed_at"] = None
    task["completed_at"] = t.isoformat()

    if task.get("type") == "deadline":
        task["done"] = True
        task["archived"] = True
        task["archived_at"] = t.isoformat()
        deadline = parse(task.get("deadline"))
        if deadline:
            details["deadline"] = deadline.isoformat()
            details["days_left"] = (deadline - t).days

    elif task.get("type") == "cycle":
        cycle = task.get("cycle", "weekly")
        label, cycle_start, cycle_end = cycle_start_end(cycle, t)
        details["cycle"] = label
        details["cycle_start"] = cycle_start.isoformat()
        details["cycle_end"] = cycle_end.isoformat()
        task.pop("failed_current_cycle_start", None)

    elif task.get("type") == "countdown":
        days = int(task.get("days", 3))
        next_due = t + timedelta(days=days)
        details["days"] = days
        details["next_due"] = next_due.isoformat()
        task.pop("countdown_fail_logged_for", None)

    elif task.get("type") == "gray":
        task["done"] = True
        task["archived"] = True
        task["archived_at"] = t.isoformat()

    _reset_confirmations(task)
    log(task, "done", details)


def mark_done(tasks, i):
    task = tasks[i]
    t = now()

    required = max(1, int(task.get("required_confirmations", 1)))
    current = max(0, int(task.get("current_confirmations", 0))) + 1
    task["current_confirmations"] = current

    base_details = {
        "time": t.isoformat(),
        "type": task.get("type"),
        "current_confirmations": current,
        "required_confirmations": required,
    }

    if current < required:
        log(task, "partial_done", base_details)
        _touch(task)
        save_tasks(tasks)
        return

    _complete_task(task, t, base_details)
    _touch(task)
    save_tasks(tasks)


def fail_task(tasks, i):
    task = tasks[i]
    t = now()
    task_type = task.get("type")

    details = {
        "time": t.isoformat(),
        "type": task_type,
        **_confirmation_details(task),
    }

    task["failed"] = True
    task["failed_at"] = t.isoformat()
    _reset_confirmations(task)

    if task_type == "deadline":
        deadline = parse(task.get("deadline"))
        if deadline:
            details["deadline"] = deadline.isoformat()
            details["days_left"] = (deadline - t).days
        task["done"] = False
        task["archived"] = True
        task["archived_at"] = t.isoformat()

    elif task_type == "cycle":
        cycle = task.get("cycle", "weekly")
        label, cycle_start, cycle_end = cycle_start_end(cycle, t)
        task["failed_current_cycle_start"] = cycle_start.isoformat()
        task["cycle_last_checked_start"] = cycle_start.isoformat()
        details["cycle"] = label
        details["cycle_start"] = cycle_start.isoformat()
        details["cycle_end"] = cycle_end.isoformat()

    elif task_type == "countdown":
        days = int(task.get("days", 3))
        task["last_done"] = t.isoformat()
        next_due = t + timedelta(days=days)
        details["days"] = days
        details["next_due"] = next_due.isoformat()
        task.pop("countdown_fail_logged_for", None)

    elif task_type == "gray":
        task["done"] = False
        task["archived"] = True
        task["archived_at"] = t.isoformat()

    log(task, "fail", details)
    _touch(task)
    save_tasks(tasks)


def archive_task(tasks, i):
    task = tasks[i]
    t = now()
    task["archived"] = True
    task["archived_at"] = t.isoformat()
    log(task, "archive", {"time": t.isoformat()})
    _touch(task)
    save_tasks(tasks)


def restore_task(tasks, i):
    task = tasks[i]
    task["archived"] = False
    log(task, "restore", {"time": now().isoformat()})
    _touch(task)
    save_tasks(tasks)


def delete_task(tasks, i):
    tasks.pop(i)
    save_tasks(tasks)


def edit_task(tasks, task, new_data):
    before = {
        "type": task.get("type"),
        "priority": task.get("priority"),
        "deadline": task.get("deadline"),
        "cycle": task.get("cycle"),
        "days": task.get("days"),
        "tags": task.get("tags", []),
        "required_confirmations": task.get("required_confirmations", 1),
        "current_confirmations": task.get("current_confirmations", 0),
        "linked_journal_id": task.get("linked_journal_id"),
        "linked_entry_id": task.get("linked_entry_id"),
    }

    for key, value in new_data.items():
        task[key] = value

    # If type changes, remove irrelevant scheduling fields but keep identity/history/notes.
    task_type = task.get("type")
    if task_type == "deadline":
        task["cycle"] = None
        task["days"] = None
    elif task_type == "cycle":
        task["deadline"] = None
        task["days"] = None
        if not task.get("cycle"):
            task["cycle"] = "weekly"
    elif task_type == "countdown":
        task["deadline"] = None
        task["cycle"] = None
        if not task.get("days"):
            task["days"] = 3
    elif task_type == "gray":
        task["deadline"] = None
        task["cycle"] = None
        task["days"] = None

    task["required_confirmations"] = max(1, int(task.get("required_confirmations", 1)))
    task["current_confirmations"] = min(
        max(0, int(task.get("current_confirmations", 0))),
        task["required_confirmations"],
    )

    after = {
        "type": task.get("type"),
        "priority": task.get("priority"),
        "deadline": task.get("deadline"),
        "cycle": task.get("cycle"),
        "days": task.get("days"),
        "tags": task.get("tags", []),
        "required_confirmations": task.get("required_confirmations", 1),
        "current_confirmations": task.get("current_confirmations", 0),
        "linked_journal_id": task.get("linked_journal_id"),
        "linked_entry_id": task.get("linked_entry_id"),
    }

    task["edited_at"] = now().isoformat()
    _touch(task)
    log(task, "edit", {"before": before, "after": after, "time": now().isoformat()})
    save_tasks(tasks)


def add_note(tasks, task, text):
    if not text:
        return
    task.setdefault("notes", []).append({
        "time": now().isoformat(),
        "text": text,
    })
    log(task, "note", {"text": text, "time": now().isoformat()})
    _touch(task)
    save_tasks(tasks)
