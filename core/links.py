from core.history import log
from core.storage import find_entry, save_journals, save_tasks
from core.utils import now


def find_task(tasks, task_id):
    for task in tasks:
        if task.get("id") == task_id:
            return task
    return None


def tracker_label(task):
    if not task:
        return "No tracker"
    return f"{task.get('title', 'Untitled')} ({task.get('type', 'gray')})"


def entry_label(journal, entry):
    if not journal or not entry:
        return "No journal entry"
    return f"{journal.get('name', 'Journal')} / {entry.get('title', 'Untitled')}"


def unlink_tracker_from_all_entries(journals, task_id):
    changed = False
    if not task_id:
        return changed
    for journal in journals:
        for entry in journal.get("entries", []):
            if entry.get("linked_tracker_id") == task_id:
                entry["linked_tracker_id"] = None
                entry["edited_at"] = now().isoformat()
                changed = True
    return changed


def unlink_entry_from_all_tasks(tasks, entry_id):
    changed = False
    if not entry_id:
        return changed
    for task in tasks:
        if task.get("linked_entry_id") == entry_id:
            task["linked_journal_id"] = None
            task["linked_entry_id"] = None
            task["edited_at"] = now().isoformat()
            log(task, "unlink_journal_entry", {"time": now().isoformat(), "entry_id": entry_id})
            changed = True
    return changed


def link_tracker_to_entry(tasks, journals, task_id, journal_id, entry_id, source="manual"):
    task = find_task(tasks, task_id)
    journal, entry = find_entry(journals, entry_id, journal_id)

    if not task or not journal or not entry:
        return False, "Tracker or journal entry not found."

    # One tracker links to one entry. One entry links to one tracker.
    unlink_tracker_from_all_entries(journals, task_id)
    unlink_entry_from_all_tasks(tasks, entry_id)

    task["linked_journal_id"] = journal_id
    task["linked_entry_id"] = entry_id
    task["edited_at"] = now().isoformat()

    entry["linked_tracker_id"] = task_id
    entry["edited_at"] = now().isoformat()

    log(task, "link_journal_entry", {
        "time": now().isoformat(),
        "source": source,
        "journal_id": journal_id,
        "journal_name": journal.get("name"),
        "entry_id": entry_id,
        "entry_title": entry.get("title"),
    })

    save_tasks(tasks)
    save_journals(journals)
    return True, "Linked."


def unlink_tracker(tasks, journals, task_id, source="manual"):
    task = find_task(tasks, task_id)
    if not task:
        return False, "Tracker not found."

    old_entry_id = task.get("linked_entry_id")
    task["linked_journal_id"] = None
    task["linked_entry_id"] = None
    task["edited_at"] = now().isoformat()
    log(task, "unlink_journal_entry", {
        "time": now().isoformat(),
        "source": source,
        "entry_id": old_entry_id,
    })

    unlink_tracker_from_all_entries(journals, task_id)
    save_tasks(tasks)
    save_journals(journals)
    return True, "Unlinked."


def unlink_entry(tasks, journals, entry_id, source="manual"):
    journal, entry = find_entry(journals, entry_id)
    if not entry:
        return False, "Entry not found."

    task_id = entry.get("linked_tracker_id")
    entry["linked_tracker_id"] = None
    entry["edited_at"] = now().isoformat()

    if task_id:
        task = find_task(tasks, task_id)
        if task:
            task["linked_journal_id"] = None
            task["linked_entry_id"] = None
            task["edited_at"] = now().isoformat()
            log(task, "unlink_journal_entry", {
                "time": now().isoformat(),
                "source": source,
                "entry_id": entry_id,
            })

    save_tasks(tasks)
    save_journals(journals)
    return True, "Unlinked."
