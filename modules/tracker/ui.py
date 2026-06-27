import json
from uuid import uuid4

import streamlit as st

from core.history import log
from core.links import entry_label, link_tracker_to_entry, unlink_tracker
from core.storage import (
    find_entry,
    flatten_journal_entries,
    load_journals,
    load_tasks,
    save_tasks,
)
from core.utils import now, parse
from modules.tracker.actions import (
    add_note,
    archive_task,
    delete_task,
    edit_task,
    fail_task,
    mark_done,
    restore_task,
)
from modules.tracker.info import task_info
from modules.tracker.sorting import sort_tasks
from modules.tracker.status import get_status, sync_pending_events

TASK_TYPES = ["deadline", "cycle", "countdown", "gray"]
PRIORITIES = ["high", "mid", "low"]
CYCLES = ["daily", "weekly", "monthly"]


# -----------------------
# HELPERS
# -----------------------
def _ensure_session_state():
    if "open_notes" not in st.session_state:
        st.session_state.open_notes = {}
    if "open_history" not in st.session_state:
        st.session_state.open_history = {}


def _toggle_state(bucket, task_id):
    current = st.session_state[bucket].get(task_id, False)
    st.session_state[bucket][task_id] = not current


def _task_index(tasks, task):
    return tasks.index(task)


def _parse_tags(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(tag).strip().lstrip("#") for tag in raw if str(tag).strip()]
    return [tag.strip().lstrip("#") for tag in raw.split(",") if tag.strip()]


def _journal_entry_options(journals):
    rows = flatten_journal_entries(journals)
    options = [("None", None, None)]
    for row in rows:
        label = f"{row.get('journal_name')} / {row.get('entry_title')} · {row.get('entry_status')}"
        options.append((label, row.get("journal_id"), row.get("entry_id")))
    return options


def _current_link_label(task, journals):
    journal, entry = find_entry(journals, task.get("linked_entry_id"), task.get("linked_journal_id"))
    if journal and entry:
        return entry_label(journal, entry)
    return "None"


def _default_link_index(task, options):
    current_entry_id = task.get("linked_entry_id")
    if not current_entry_id:
        return 0
    for idx, (_, _, entry_id) in enumerate(options):
        if entry_id == current_entry_id:
            return idx
    return 0


def _apply_link_choice(tasks, journals, task, selected_option, source):
    _, journal_id, entry_id = selected_option
    task_id = task.get("id")

    if not entry_id:
        if task.get("linked_entry_id"):
            unlink_tracker(tasks, journals, task_id, source=source)
        return

    if task.get("linked_entry_id") != entry_id:
        link_tracker_to_entry(tasks, journals, task_id, journal_id, entry_id, source=source)


def _render_link_badge(task, journals):
    label = _current_link_label(task, journals)
    if label != "None":
        st.caption(f"🔗 Linked journal: {label}")


# -----------------------
# ADD TASK
# -----------------------
def _render_add_task(tasks, journals):
    st.subheader("➕ Add task")

    with st.form("add"):
        title = st.text_input("Title")
        ttype = st.selectbox("Type", TASK_TYPES)
        priority = st.selectbox("Priority", PRIORITIES)
        tags_raw = st.text_input("Tags (comma separated)", placeholder="gym, health, university")
        required_confirmations = st.number_input("Required confirmations", 1, 99, 1)

        link_options = _journal_entry_options(journals)
        link_labels = [label for label, _, _ in link_options]
        link_selected_label = st.selectbox("Linked Journal Entry", link_labels, index=0)
        selected_link = link_options[link_labels.index(link_selected_label)]

        deadline = None
        cycle = None
        days = None

        if ttype == "deadline":
            deadline = st.datetime_input("Deadline").isoformat()

        if ttype == "cycle":
            cycle = st.selectbox("Cycle", CYCLES)

        if ttype == "countdown":
            days = st.number_input("Days", 1, 365, 3)

        submitted = st.form_submit_button("Add")

        if submitted:
            current_time = now().isoformat()
            new_task = {
                "id": str(uuid4()),
                "title": title or "Untitled",
                "type": ttype,
                "priority": priority,
                "deadline": deadline,
                "cycle": cycle,
                "days": days,
                "last_done": None,
                "archived": False,
                "done": False,
                "failed": False,
                "history": [],
                "notes": [],
                "created_at": current_time,
                "edited_at": None,
                "completed_at": None,
                "failed_at": None,
                "archived_at": None,
                "tags": _parse_tags(tags_raw),
                "obsidian_file": None,
                "github_sha": None,
                "last_synced_at": None,
                "last_local_edit_at": current_time,
                "required_confirmations": int(required_confirmations),
                "current_confirmations": 0,
                "linked_journal_id": None,
                "linked_entry_id": None,
            }
            log(new_task, "create", {"time": current_time})
            tasks.append(new_task)
            save_tasks(tasks)
            _apply_link_choice(tasks, journals, new_task, selected_link, source="tracker_create")
            st.rerun()


# -----------------------
# EDIT TASK
# -----------------------
def _render_edit_panel(tasks, journals, task, task_id):
    if not st.session_state.get(f"edit_{task_id}", False):
        return

    with st.expander("Edit task", expanded=True):
        new_title = st.text_input("Title", value=task.get("title", "Untitled"), key=f"et_{task_id}")

        new_type = st.selectbox(
            "Type",
            TASK_TYPES,
            index=TASK_TYPES.index(task.get("type", "gray")) if task.get("type", "gray") in TASK_TYPES else 0,
            key=f"etype_{task_id}",
        )

        new_priority = st.selectbox(
            "Priority",
            PRIORITIES,
            index=PRIORITIES.index(task.get("priority", "low")) if task.get("priority", "low") in PRIORITIES else 2,
            key=f"ep_{task_id}",
        )

        new_tags_raw = st.text_input(
            "Tags (comma separated)",
            value=", ".join(task.get("tags", [])),
            key=f"etags_{task_id}",
        )

        new_required_confirmations = st.number_input(
            "Required confirmations",
            1,
            99,
            value=max(1, int(task.get("required_confirmations", 1))),
            key=f"erq_{task_id}",
        )

        link_options = _journal_entry_options(journals)
        link_labels = [label for label, _, _ in link_options]
        selected_link_label = st.selectbox(
            "Linked Journal Entry",
            link_labels,
            index=_default_link_index(task, link_options),
            key=f"elink_{task_id}",
        )
        selected_link = link_options[link_labels.index(selected_link_label)]

        new_deadline = None
        new_cycle = None
        new_days = None

        if new_type == "deadline":
            new_deadline = st.datetime_input(
                "Deadline",
                value=parse(task.get("deadline")) if task.get("deadline") else now(),
                key=f"ed_{task_id}",
            ).isoformat()

        elif new_type == "cycle":
            new_cycle = st.selectbox(
                "Cycle",
                CYCLES,
                index=CYCLES.index(task.get("cycle", "weekly")) if task.get("cycle", "weekly") in CYCLES else 1,
                key=f"ec_{task_id}",
            )

        elif new_type == "countdown":
            new_days = st.number_input(
                "Days",
                1,
                365,
                value=int(task.get("days") or 3),
                key=f"ecd_{task_id}",
            )

        elif new_type == "gray":
            new_deadline = None
            new_cycle = None
            new_days = None

        if st.button("Save changes", key=f"save_{task_id}"):
            edit_task(tasks, task, {
                "title": new_title or "Untitled",
                "type": new_type,
                "priority": new_priority,
                "deadline": new_deadline,
                "cycle": new_cycle,
                "days": new_days,
                "tags": _parse_tags(new_tags_raw),
                "required_confirmations": int(new_required_confirmations),
            })
            _apply_link_choice(tasks, journals, task, selected_link, source="tracker_edit")
            st.session_state[f"edit_{task_id}"] = False
            st.rerun()


# -----------------------
# NOTES / HISTORY
# -----------------------
def _render_notes(tasks, journals, task, task_id):
    if st.button("📝 Notes", key=f"n_{task_id}"):
        _toggle_state("open_notes", task_id)

    if st.session_state.open_notes.get(task_id, False):
        if task.get("linked_entry_id"):
            st.caption("These notes stay inside Tracker, but the linked Journal Entry can mirror them in a separate Tracker Notes block.")

        note = st.text_input("Add note", key=f"nt_{task_id}")
        if st.button("Save note", key=f"sn_{task_id}"):
            add_note(tasks, task, note)
            st.rerun()

        if task.get("notes"):
            for note_item in task["notes"]:
                st.write(f"📝 {note_item.get('text', '')}")


def _render_history(task, task_id, archive=False):
    key = f"ha_{task_id}" if archive else f"h_{task_id}"
    if st.button("📜 History", key=key):
        _toggle_state("open_history", task_id)

    if st.session_state.open_history.get(task_id, False):
        st.markdown("#### History")
        if not task.get("history"):
            st.write("No history yet")
        else:
            for item in task["history"]:
                dt = item.get("time", "")
                action = item.get("action", "")
                details = item.get("details", {})
                st.write(f"• {action} → {dt}")
                if details:
                    st.caption(json.dumps(details, ensure_ascii=False))


# -----------------------
# LISTS
# -----------------------
def _render_active_tasks(tasks, journals):
    st.subheader("📋 Active")
    active_tasks = sort_tasks([task for task in tasks if not task.get("archived")])

    for task in active_tasks:
        task_id = task["id"]
        status = get_status(task, archived=False)

        st.markdown(f"### {status} {task.get('title', 'Untitled')} ({task.get('type', 'gray')})")
        st.write(task_info(task))
        _render_link_badge(task, journals)

        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            if st.button("✔ Done", key=f"d_{task_id}"):
                mark_done(tasks, _task_index(tasks, task))
                st.rerun()

        with col2:
            if st.button("❌ Fail", key=f"f_{task_id}"):
                fail_task(tasks, _task_index(tasks, task))
                st.rerun()

        with col3:
            if st.button("📦 Archive", key=f"a_{task_id}"):
                archive_task(tasks, _task_index(tasks, task))
                st.rerun()

        with col4:
            if st.button("🗑 Delete", key=f"x_{task_id}"):
                unlink_tracker(tasks, journals, task_id, source="tracker_delete")
                delete_task(tasks, _task_index(tasks, task))
                st.rerun()

        with col5:
            if st.button("✏ Edit", key=f"e_{task_id}"):
                st.session_state[f"edit_{task_id}"] = not st.session_state.get(f"edit_{task_id}", False)

        _render_edit_panel(tasks, journals, task, task_id)
        _render_notes(tasks, journals, task, task_id)
        _render_history(task, task_id, archive=False)

        st.divider()


def _render_archive(tasks, journals):
    st.subheader("📦 Archive")
    archived_tasks = sort_tasks([task for task in tasks if task.get("archived")])

    for task in archived_tasks:
        task_id = task["id"]
        status = get_status(task, archived=True)

        st.markdown(f"### {status} {task.get('title', 'Untitled')} ({task.get('type', 'gray')})")
        st.write(task_info(task))
        _render_link_badge(task, journals)

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("↩ Restore", key=f"r_{task_id}"):
                restore_task(tasks, _task_index(tasks, task))
                st.rerun()

        with col2:
            if st.button("🗑 Delete", key=f"dx_{task_id}"):
                unlink_tracker(tasks, journals, task_id, source="tracker_delete")
                delete_task(tasks, _task_index(tasks, task))
                st.rerun()

        with col3:
            _render_history(task, task_id, archive=True)

        st.divider()


def _render_overview(tasks):
    st.subheader("📊 Overview")

    counts = {
        "🟢": 0,
        "🟡": 0,
        "🟠": 0,
        "🔴": 0,
        "⚫": 0,
        "⚪": 0,
    }

    for task in tasks:
        status = get_status(task, archived=task.get("archived", False))
        counts[status] = counts.get(status, 0) + 1

    st.write(counts)


# -----------------------
# MAIN RENDER
# -----------------------
def render_tracker(on_back=None):
    _ensure_session_state()

    if on_back:
        if st.button("← Back to menu", key="tracker_back"):
            on_back()
            st.rerun()

    tasks = load_tasks()
    sync_pending_events(tasks)
    journals = load_journals()

    st.title("📋 Life Tracker")
    st.caption("Tracker Stable + Journal linking. Notes stay in Tracker; linked Journals can mirror them separately.")
    view = st.radio("Tracker View", ["Active", "Archive"], horizontal=True)

    if view == "Active":
        _render_add_task(tasks, journals)
        _render_active_tasks(tasks, journals)
    else:
        _render_archive(tasks, journals)

    _render_overview(tasks)
