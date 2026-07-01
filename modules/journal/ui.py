from datetime import date, datetime
from uuid import uuid4

import streamlit as st

from core.history import log
from core.links import find_task, link_tracker_to_entry, unlink_entry
from core.storage import (
    ENTRY_STATUSES,
    JOURNAL_TYPE_LABELS,
    JOURNAL_TYPES,
    find_entry,
    find_journal,
    load_journals,
    load_tasks,
    make_obsidian_entry_path,
    make_obsidian_index_path,
    save_journals,
    save_tasks,
    slugify,
)
from core.utils import now, parse
from modules.tracker.status import get_status

TASK_TYPES = ["deadline", "cycle", "countdown", "gray"]
PRIORITIES = ["high", "mid", "low"]
CYCLES = ["daily", "weekly", "monthly"]


# -----------------------
# SMALL HELPERS
# -----------------------
def _parse_tags(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(tag).strip().lstrip("#") for tag in raw if str(tag).strip()]
    return [tag.strip().lstrip("#") for tag in raw.split(",") if tag.strip()]


def _tags_text(tags):
    tags = _parse_tags(tags)
    return " ".join([f"#{tag}" for tag in tags]) if tags else ""

def _touch_journal(journal):
    stamp = now().isoformat()
    journal["last_local_edit_at"] = stamp
    journal["edited_at"] = stamp


def _touch_entry(journal, entry):
    stamp = now().isoformat()
    entry["last_local_edit_at"] = stamp
    entry["edited_at"] = stamp
    journal["last_local_edit_at"] = stamp
    journal["edited_at"] = stamp



def _date_value(value):
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value[:10])
    except Exception:
        return date.today()


def _status_index(status):
    return ENTRY_STATUSES.index(status) if status in ENTRY_STATUSES else 1


def _type_label(jtype):
    return JOURNAL_TYPE_LABELS.get(jtype, jtype)


def _render_back(on_back):
    if on_back and st.button("← Back to menu", key="journals_back_to_menu"):
        on_back()
        st.rerun()


def _ensure_state():
    st.session_state.setdefault("selected_journal_id", None)
    st.session_state.setdefault("journal_open_edit", {})
    st.session_state.setdefault("journal_open_full", {})
    st.session_state.setdefault("journal_open_sync", {})
    st.session_state.setdefault("writer_journal_id", None)
    st.session_state.setdefault("writer_entry_id", None)
    st.session_state.setdefault("writer_section", None)


def _go_to_journals():
    st.session_state["selected_journal_id"] = None


def _entry_summary(entry, journal_type):
    fields = entry.get("fields", {})
    content = entry.get("content", "") or ""

    if journal_type == "essay":
        parts = []
        if fields.get("subject"):
            parts.append(f"Subject: {fields.get('subject')}")
        if fields.get("deadline"):
            parts.append(f"Deadline: {fields.get('deadline')}")
        if fields.get("draft"):
            parts.append(fields.get("draft")[:350])
        elif fields.get("outline"):
            parts.append(fields.get("outline")[:350])
        elif content:
            parts.append(content[:350])
        return "\n\n".join(parts)

    if journal_type == "project":
        parts = []
        for key, label in [("project", "Project"), ("problem", "Problem"), ("what_i_did", "What I did"), ("next_step", "Next step")]:
            if fields.get(key):
                parts.append(f"{label}: {fields.get(key)}")
        if content:
            parts.append(content[:350])
        return "\n\n".join(parts)

    if journal_type == "learning":
        parts = []
        for key, label in [("course", "Course"), ("topic", "Topic"), ("learned", "Learned"), ("confused", "Still unclear")]:
            if fields.get(key):
                parts.append(f"{label}: {fields.get(key)}")
        if content:
            parts.append(content[:350])
        return "\n\n".join(parts)

    return content[:700]


def _entry_metadata_line(entry, journal_type, linked_task=None):
    chunks = []
    if journal_type != "draft" and entry.get("date"):
        chunks.append(entry.get("date"))
    chunks.append(entry.get("status", "Draft"))
    if entry.get("tags"):
        chunks.append(_tags_text(entry.get("tags")))
    if linked_task:
        chunks.append(f"linked tracker: {get_status(linked_task)} {linked_task.get('title', 'Untitled')}")
    return " · ".join([chunk for chunk in chunks if chunk])


# -----------------------
# CREATE JOURNAL / ENTRY
# -----------------------
def _create_journal(journals, name, jtype, description, tags):
    current_time = now().isoformat()
    journal = {
        "id": str(uuid4()),
        "name": name or "Untitled Journal",
        "type": jtype,
        "description": description or "",
        "tags": _parse_tags(tags),
        "entries": [],
        "created_at": current_time,
        "edited_at": None,
        "archived": False,
        "slug": slugify(name or "Untitled Journal"),
        "obsidian_index": None,
        "github_sha": None,
        "last_synced_at": None,
        "last_local_edit_at": current_time,
    }
    journal["obsidian_index"] = make_obsidian_index_path(journal)
    journals.append(journal)
    save_journals(journals)


def _create_entry(journals, journal, entry_data):
    current_time = now().isoformat()
    entry = {
        "id": str(uuid4()),
        "title": entry_data.get("title") or "Untitled",
        "status": entry_data.get("status") or "Draft",
        "date": entry_data.get("date"),
        "tags": _parse_tags(entry_data.get("tags", [])),
        "content": entry_data.get("content", ""),
        "fields": entry_data.get("fields", {}),
        "linked_tracker_id": None,
        "created_at": current_time,
        "edited_at": None,
        "archived": False,
        "slug": slugify(entry_data.get("title") or "Untitled"),
        "obsidian_file": None,
        "github_sha": None,
        "last_synced_at": None,
        "last_local_edit_at": current_time,
    }
    if journal.get("type") == "draft":
        entry["date"] = None
    entry["obsidian_file"] = make_obsidian_entry_path(journal, entry)
    journal.setdefault("entries", []).insert(0, entry)
    journal["edited_at"] = current_time
    save_journals(journals)
    return entry


def _render_new_journal_form(journals):
    with st.expander("➕ New Journal", expanded=not journals):
        with st.form("new_journal_form"):
            name = st.text_input("Journal name", placeholder="Дневник, Эссе, Проекты, Черновики...")
            type_options = JOURNAL_TYPES
            type_labels = [_type_label(t) for t in type_options]
            selected_label = st.selectbox("Journal type", type_labels)
            jtype = type_options[type_labels.index(selected_label)]
            description = st.text_area("Description", height=90, placeholder="What is this journal for?")
            tags = st.text_input("Tags", placeholder="study, personal, writing")
            submitted = st.form_submit_button("Create Journal")

            if submitted:
                _create_journal(journals, name, jtype, description, tags)
                st.success("Journal created.")
                st.rerun()


def _render_type_specific_entry_fields(journal_type, prefix, entry=None):
    entry = entry or {}
    fields = entry.get("fields", {}) or {}
    content = entry.get("content", "") or ""
    result = {"fields": {}, "content": content}

    if journal_type == "diary":
        col1, col2 = st.columns(2)
        with col1:
            result["fields"]["mood"] = st.slider("Mood", 1, 5, int(fields.get("mood", 3)), key=f"{prefix}_mood")
        with col2:
            result["fields"]["energy"] = st.slider("Energy", 1, 5, int(fields.get("energy", 3)), key=f"{prefix}_energy")
        result["content"] = st.text_area("Diary text", value=content, height=280, key=f"{prefix}_content")

    elif journal_type == "essay":
        col1, col2 = st.columns(2)
        with col1:
            result["fields"]["subject"] = st.text_input("Subject / Course", value=fields.get("subject", ""), key=f"{prefix}_subject")
        with col2:
            use_deadline = st.checkbox("Has deadline", value=bool(fields.get("deadline")), key=f"{prefix}_has_deadline")
            if use_deadline:
                result["fields"]["deadline"] = st.date_input(
                    "Deadline",
                    value=_date_value(fields.get("deadline")),
                    key=f"{prefix}_deadline",
                ).isoformat()
            else:
                result["fields"]["deadline"] = None
        result["fields"]["outline"] = st.text_area("Outline", value=fields.get("outline", ""), height=150, key=f"{prefix}_outline")
        result["fields"]["draft"] = st.text_area("Draft", value=fields.get("draft", content), height=280, key=f"{prefix}_draft")
        result["fields"]["sources"] = st.text_area("Sources", value=fields.get("sources", ""), height=120, key=f"{prefix}_sources")
        result["fields"]["final_text"] = st.text_area("Final version", value=fields.get("final_text", ""), height=180, key=f"{prefix}_final")
        result["content"] = result["fields"].get("draft", "")

    elif journal_type == "project":
        result["fields"]["project"] = st.text_input("Project", value=fields.get("project", ""), key=f"{prefix}_project")
        result["fields"]["problem"] = st.text_area("Problem / Context", value=fields.get("problem", ""), height=120, key=f"{prefix}_problem")
        result["fields"]["what_i_did"] = st.text_area("What I did", value=fields.get("what_i_did", ""), height=140, key=f"{prefix}_did")
        result["fields"]["next_step"] = st.text_area("Next step", value=fields.get("next_step", ""), height=100, key=f"{prefix}_next")
        result["content"] = st.text_area("Additional notes", value=content, height=180, key=f"{prefix}_content")

    elif journal_type == "learning":
        col1, col2 = st.columns(2)
        with col1:
            result["fields"]["course"] = st.text_input("Course", value=fields.get("course", ""), key=f"{prefix}_course")
        with col2:
            result["fields"]["topic"] = st.text_input("Topic", value=fields.get("topic", ""), key=f"{prefix}_topic")
        result["fields"]["learned"] = st.text_area("What I learned", value=fields.get("learned", ""), height=150, key=f"{prefix}_learned")
        result["fields"]["confused"] = st.text_area("What I still don't understand", value=fields.get("confused", ""), height=130, key=f"{prefix}_confused")
        result["fields"]["questions"] = st.text_area("Questions", value=fields.get("questions", ""), height=120, key=f"{prefix}_questions")
        result["content"] = st.text_area("Free notes", value=content, height=180, key=f"{prefix}_content")

    elif journal_type == "draft":
        result["content"] = st.text_area("Draft text", value=content, height=430, key=f"{prefix}_content")

    else:
        result["content"] = st.text_area("Content", value=content, height=320, key=f"{prefix}_content")

    return result


def _render_new_entry_form(journals, journal):
    jtype = journal.get("type", "custom")
    with st.expander("➕ New Entry", expanded=False):
        with st.form(f"new_entry_{journal.get('id')}"):
            title_label = "Draft title" if jtype == "draft" else "Entry title"
            title = st.text_input(title_label, placeholder="Title")

            col1, col2, col3 = st.columns(3)
            with col1:
                entry_date = None
                if jtype != "draft":
                    entry_date = st.date_input("Date").isoformat()
            with col2:
                status = st.selectbox("Entry status", ENTRY_STATUSES, index=1)
            with col3:
                tags = st.text_input("Tags", placeholder="essay, idea, study")

            specific = _render_type_specific_entry_fields(jtype, f"new_{journal.get('id')}")
            open_writer = st.checkbox("Open Focus Writer after saving", value=True)
            submitted = st.form_submit_button("Save Entry")

            if submitted:
                created_entry = _create_entry(journals, journal, {
                    "title": title,
                    "date": entry_date,
                    "status": status,
                    "tags": tags,
                    "fields": specific.get("fields", {}),
                    "content": specific.get("content", ""),
                })
                if open_writer:
                    st.session_state["writer_journal_id"] = journal.get("id")
                    st.session_state["writer_entry_id"] = created_entry.get("id")
                    st.session_state["writer_section"] = None
                st.success("Entry saved.")
                st.rerun()


# -----------------------
# FOCUS WRITER
# -----------------------
def _writer_sections(journal_type):
    if journal_type == "essay":
        return [
            ("field:draft", "Draft"),
            ("field:outline", "Outline"),
            ("field:sources", "Sources"),
            ("field:final_text", "Final Version"),
        ]
    if journal_type == "project":
        return [
            ("field:problem", "Problem / Context"),
            ("field:what_i_did", "What I did"),
            ("field:next_step", "Next step"),
            ("content", "Additional Notes"),
        ]
    if journal_type == "learning":
        return [
            ("field:learned", "What I learned"),
            ("field:confused", "Still unclear"),
            ("field:questions", "Questions"),
            ("content", "Free Notes"),
        ]
    return [("content", "Text")]


def _get_section_text(entry, section_id):
    if section_id == "content":
        return entry.get("content", "") or ""
    if section_id.startswith("field:"):
        key = section_id.split(":", 1)[1]
        return (entry.get("fields", {}) or {}).get(key, "") or ""
    return entry.get("content", "") or ""


def _set_section_text(journal_type, entry, section_id, text):
    if section_id == "content":
        entry["content"] = text or ""
        return

    if section_id.startswith("field:"):
        key = section_id.split(":", 1)[1]
        entry.setdefault("fields", {})[key] = text or ""
        if journal_type == "essay" and key == "draft":
            entry["content"] = text or ""


def _word_count(text):
    return len([w for w in (text or "").split() if w.strip()])


def _char_count(text):
    return len(text or "")


def _close_writer():
    st.session_state["writer_journal_id"] = None
    st.session_state["writer_entry_id"] = None
    st.session_state["writer_section"] = None


def _render_writer_metadata_form(journal, entry, prefix):
    jtype = journal.get("type", "custom")
    fields = entry.setdefault("fields", {})

    title = st.text_input("Title", value=entry.get("title", "Untitled"), key=f"{prefix}_title")

    col1, col2, col3 = st.columns(3)
    with col1:
        entry_date = None
        if jtype != "draft":
            entry_date = st.date_input("Date", value=_date_value(entry.get("date")), key=f"{prefix}_date").isoformat()
    with col2:
        status = st.selectbox("Status", ENTRY_STATUSES, index=_status_index(entry.get("status", "Draft")), key=f"{prefix}_status")
    with col3:
        tags = st.text_input("Tags", value=", ".join(entry.get("tags", [])), key=f"{prefix}_tags")

    extra = {}
    if jtype == "diary":
        c1, c2 = st.columns(2)
        with c1:
            extra["mood"] = st.slider("Mood", 1, 5, int(fields.get("mood", 3)), key=f"{prefix}_mood")
        with c2:
            extra["energy"] = st.slider("Energy", 1, 5, int(fields.get("energy", 3)), key=f"{prefix}_energy")
    elif jtype == "essay":
        c1, c2 = st.columns(2)
        with c1:
            extra["subject"] = st.text_input("Subject / Course", value=fields.get("subject", ""), key=f"{prefix}_subject")
        with c2:
            use_deadline = st.checkbox("Has deadline", value=bool(fields.get("deadline")), key=f"{prefix}_has_deadline")
            if use_deadline:
                extra["deadline"] = st.date_input("Deadline", value=_date_value(fields.get("deadline")), key=f"{prefix}_deadline").isoformat()
            else:
                extra["deadline"] = None
    elif jtype == "project":
        extra["project"] = st.text_input("Project", value=fields.get("project", ""), key=f"{prefix}_project")
    elif jtype == "learning":
        c1, c2 = st.columns(2)
        with c1:
            extra["course"] = st.text_input("Course", value=fields.get("course", ""), key=f"{prefix}_course")
        with c2:
            extra["topic"] = st.text_input("Topic", value=fields.get("topic", ""), key=f"{prefix}_topic")

    return title, entry_date, status, tags, extra


def _save_writer_changes(journals, journal, entry, section_id, title, entry_date, status, tags, extra, text):
    jtype = journal.get("type", "custom")
    entry["title"] = title or "Untitled"
    entry["status"] = status
    entry["date"] = None if jtype == "draft" else entry_date
    entry["tags"] = _parse_tags(tags)
    entry.setdefault("fields", {}).update(extra or {})
    _set_section_text(jtype, entry, section_id, text)
    entry["slug"] = slugify(entry["title"])
    entry["obsidian_file"] = make_obsidian_entry_path(journal, entry)
    _touch_entry(journal, entry)
    save_journals(journals)


def _render_focus_writer(journals, tasks, journal, entry):
    jtype = journal.get("type", "custom")
    entry_id = entry.get("id")
    sections = _writer_sections(jtype)
    section_ids = [sid for sid, _ in sections]
    section_labels = [label for _, label in sections]

    if st.session_state.get("writer_section") not in section_ids:
        st.session_state["writer_section"] = section_ids[0]

    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1180px;
            padding-top: 1.2rem;
            padding-bottom: 3rem;
        }
        div[data-testid="stTextArea"] textarea {
            min-height: 68vh !important;
            font-size: 18px !important;
            line-height: 1.75 !important;
            padding: 1.5rem !important;
            border-radius: 18px !important;
        }
        .writer-title {
            text-align: center;
            font-size: 2.3rem;
            font-weight: 800;
            margin-bottom: 0.2rem;
        }
        .writer-subtitle {
            text-align: center;
            opacity: 0.7;
            margin-bottom: 1.2rem;
        }
        .writer-tip {
            text-align: center;
            opacity: 0.65;
            font-size: 0.92rem;
            margin-top: -0.4rem;
            margin-bottom: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    top1, top2, top3 = st.columns([1, 2, 1])
    with top1:
        if st.button("← Back to Journal", use_container_width=True, key=f"writer_back_{entry_id}"):
            _close_writer()
            st.rerun()
    with top2:
        st.markdown(f'<div class="writer-title">✍️ {entry.get("title", "Untitled")}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="writer-subtitle">{journal.get("name", "Journal")} · {_type_label(jtype)} · {entry.get("status", "Draft")}</div>',
            unsafe_allow_html=True,
        )
    with top3:
        if st.button("Exit Writer", use_container_width=True, key=f"writer_exit_{entry_id}"):
            _close_writer()
            st.rerun()

    st.caption(f"Obsidian file preview: `{entry.get('obsidian_file')}`")

    selected_label = st.radio(
        "Writing section",
        section_labels,
        index=section_ids.index(st.session_state["writer_section"]),
        horizontal=True,
        key=f"writer_section_radio_{entry_id}",
    )
    section_id = sections[section_labels.index(selected_label)][0]
    st.session_state["writer_section"] = section_id

    st.markdown('<div class="writer-tip">Write first. Metadata and tracker tools are hidden so the page stays clean.</div>', unsafe_allow_html=True)

    current_text = _get_section_text(entry, section_id)
    with st.form(f"focus_writer_form_{entry_id}_{section_id}"):
        with st.expander("Metadata / settings", expanded=False):
            title, entry_date, status, tags, extra = _render_writer_metadata_form(journal, entry, f"writer_meta_{entry_id}_{section_id}")

        text = st.text_area(
            "Writing area",
            value=current_text,
            height=720,
            key=f"writer_text_{entry_id}_{section_id}",
            placeholder="Start writing...",
            label_visibility="collapsed",
        )

        st.caption(f"Words: {_word_count(text)} · Characters: {_char_count(text)}")
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            save_only = st.form_submit_button("💾 Save", use_container_width=True)
        with c2:
            save_exit = st.form_submit_button("💾 Save & Exit", use_container_width=True)
        with c3:
            st.caption("Tip: save before switching sections, especially for essays with Draft / Outline / Sources.")

        if save_only or save_exit:
            _save_writer_changes(journals, journal, entry, section_id, title, entry_date, status, tags, extra, text)
            if save_exit:
                _close_writer()
            st.success("Saved.")
            st.rerun()

    linked_task = find_task(tasks, entry.get("linked_tracker_id"))
    if linked_task:
        with st.expander("Linked tracker mirror", expanded=False):
            st.write(f"**{linked_task.get('title', 'Untitled')}** · {get_status(linked_task, archived=linked_task.get('archived', False))} · {linked_task.get('type', 'gray')}")
            notes = linked_task.get("notes", [])
            if notes:
                st.markdown("##### Recent notes")
                for note in notes[-5:]:
                    st.write(f"📝 {note.get('time', '')}")
                    st.write(note.get("text", ""))
            else:
                st.caption("No tracker notes yet.")


# -----------------------
# TRACKER LINKING
# -----------------------
def _tracker_options(tasks):
    options = []
    for task in tasks:
        status = get_status(task, archived=task.get("archived", False))
        label = f"{status} {task.get('title', 'Untitled')} · {task.get('type', 'gray')}"
        if task.get("archived"):
            label += " · archived"
        options.append((label, task.get("id")))
    return options


def _create_tracker_from_entry(tasks, journals, journal, entry, title, ttype, priority, deadline, cycle, days, required_confirmations):
    current_time = now().isoformat()
    task = {
        "id": str(uuid4()),
        "title": title or f"Work on {entry.get('title', 'entry')}",
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
        "tags": list(dict.fromkeys(_parse_tags(entry.get("tags", [])) + _parse_tags(journal.get("tags", [])))),
        "obsidian_file": None,
        "required_confirmations": int(required_confirmations),
        "current_confirmations": 0,
        "linked_journal_id": journal.get("id"),
        "linked_entry_id": entry.get("id"),
    }
    log(task, "create", {
        "time": current_time,
        "source": "journal_entry",
        "journal_id": journal.get("id"),
        "entry_id": entry.get("id"),
    })
    tasks.append(task)
    entry["linked_tracker_id"] = task.get("id")
    entry["last_local_edit_at"] = current_time
    entry["edited_at"] = current_time
    journal["last_local_edit_at"] = current_time
    journal["edited_at"] = current_time
    save_tasks(tasks)
    save_journals(journals)


def _render_sync_panel(journals, tasks, journal, entry):
    entry_id = entry.get("id")
    if not st.session_state.journal_open_sync.get(entry_id, False):
        return

    with st.container(border=True):
        st.markdown("#### 🔗 Sync Tracker")
        linked_task = find_task(tasks, entry.get("linked_tracker_id"))

        if linked_task:
            st.success(f"Linked to: {get_status(linked_task, archived=linked_task.get('archived', False))} {linked_task.get('title', 'Untitled')}")
            if st.button("Unlink tracker", key=f"unlink_entry_{entry_id}"):
                unlink_entry(tasks, journals, entry_id, source="journal")
                st.rerun()
        else:
            st.caption("No linked tracker yet.")

        st.markdown("##### Link existing tracker")
        options = _tracker_options(tasks)
        if options:
            labels = [label for label, _ in options]
            selected = st.selectbox("Existing trackers", labels, key=f"existing_tracker_{entry_id}")
            task_id = options[labels.index(selected)][1]
            if st.button("Link selected tracker", key=f"link_existing_{entry_id}"):
                ok, message = link_tracker_to_entry(tasks, journals, task_id, journal.get("id"), entry_id, source="journal")
                st.success(message) if ok else st.error(message)
                st.rerun()
        else:
            st.info("No trackers yet. Create one below.")

        st.markdown("##### Create new tracker from this entry")
        with st.form(f"create_tracker_from_entry_{entry_id}"):
            default_deadline = entry.get("fields", {}).get("deadline")
            default_type = "deadline" if default_deadline else "gray"
            tracker_title = st.text_input("Tracker title", value=f"Work on: {entry.get('title', 'Untitled')}")
            ttype = st.selectbox("Tracker type", TASK_TYPES, index=TASK_TYPES.index(default_type))
            priority = st.selectbox("Priority", PRIORITIES, index=1)
            required = st.number_input("Required confirmations", 1, 99, 1)

            deadline = None
            cycle = None
            days = None

            if ttype == "deadline":
                deadline = st.date_input("Deadline", value=_date_value(default_deadline)).isoformat() + "T23:59:00"
            elif ttype == "cycle":
                cycle = st.selectbox("Cycle", CYCLES, index=1)
            elif ttype == "countdown":
                days = st.number_input("Days", 1, 365, 3)

            submitted = st.form_submit_button("Create and link tracker")
            if submitted:
                _create_tracker_from_entry(
                    tasks,
                    journals,
                    journal,
                    entry,
                    tracker_title,
                    ttype,
                    priority,
                    deadline,
                    cycle,
                    days,
                    required,
                )
                st.success("Tracker created and linked.")
                st.rerun()


# -----------------------
# ENTRY VIEW / EDIT
# -----------------------
def _render_entry_markdown_preview(journal, entry, linked_task=None):
    fields = entry.get("fields", {})
    lines = [f"# {entry.get('title', 'Untitled')}", ""]
    lines.append(f"Status: {entry.get('status', 'Draft')}")
    if entry.get("date"):
        lines.append(f"Date: {entry.get('date')}")
    if entry.get("tags"):
        lines.append("Tags: " + " ".join(f"#{tag}" for tag in entry.get("tags", [])))
    if linked_task:
        lines.append(f"Linked tracker: {linked_task.get('title', 'Untitled')}")
    lines.extend(["", "---", ""])

    jtype = journal.get("type", "custom")
    if jtype == "essay":
        for key, title in [("subject", "Subject"), ("deadline", "Deadline")]:
            if fields.get(key):
                lines.append(f"{title}: {fields.get(key)}")
        lines.extend(["", "## Outline", fields.get("outline", ""), "", "## Draft", fields.get("draft", entry.get("content", "")), "", "## Sources", fields.get("sources", ""), "", "## Final Version", fields.get("final_text", "")])
    elif jtype == "project":
        lines.extend(["## Problem / Context", fields.get("problem", ""), "", "## What I did", fields.get("what_i_did", ""), "", "## Next step", fields.get("next_step", ""), "", "## Notes", entry.get("content", "")])
    elif jtype == "learning":
        lines.extend(["## What I learned", fields.get("learned", ""), "", "## What I still don't understand", fields.get("confused", ""), "", "## Questions", fields.get("questions", ""), "", "## Free Notes", entry.get("content", "")])
    else:
        lines.extend(["## Main Text", entry.get("content", "")])

    if linked_task:
        lines.extend(["", "---", "", "## Tracker Notes"])
        notes = linked_task.get("notes", [])
        if notes:
            for note in notes:
                lines.append(f"### {note.get('time', '')}")
                lines.append(note.get("text", ""))
                lines.append("")
        else:
            lines.append("No tracker notes yet.")

        lines.extend(["", "## Tracker History"])
        history = linked_task.get("history", [])
        if history:
            for item in history[-20:]:
                lines.append(f"### {item.get('time', '')}")
                lines.append(item.get("action", ""))
                lines.append("")
        else:
            lines.append("No tracker history yet.")

    st.code("\n".join(lines), language="markdown")


def _render_full_entry(journal, entry, linked_task=None):
    entry_id = entry.get("id")
    if not st.session_state.journal_open_full.get(entry_id, False):
        return

    fields = entry.get("fields", {})
    jtype = journal.get("type", "custom")

    with st.container(border=True):
        st.markdown("#### Full view")
        st.caption(f"Obsidian path preview: `{entry.get('obsidian_file')}`")

        if jtype == "diary":
            st.write(entry.get("content", ""))
            st.caption(f"Mood: {fields.get('mood', 3)}/5 · Energy: {fields.get('energy', 3)}/5")

        elif jtype == "essay":
            if fields.get("subject"):
                st.write(f"**Subject:** {fields.get('subject')}")
            if fields.get("deadline"):
                st.write(f"**Deadline:** {fields.get('deadline')}")
            if fields.get("outline"):
                st.markdown("##### Outline")
                st.write(fields.get("outline"))
            if fields.get("draft"):
                st.markdown("##### Draft")
                st.write(fields.get("draft"))
            if fields.get("sources"):
                st.markdown("##### Sources")
                st.write(fields.get("sources"))
            if fields.get("final_text"):
                st.markdown("##### Final Version")
                st.write(fields.get("final_text"))

        elif jtype == "project":
            for key, label in [("project", "Project"), ("problem", "Problem / Context"), ("what_i_did", "What I did"), ("next_step", "Next step")]:
                if fields.get(key):
                    st.markdown(f"##### {label}")
                    st.write(fields.get(key))
            if entry.get("content"):
                st.markdown("##### Additional notes")
                st.write(entry.get("content"))

        elif jtype == "learning":
            if fields.get("course") or fields.get("topic"):
                st.write(f"**Course:** {fields.get('course', '')} · **Topic:** {fields.get('topic', '')}")
            for key, label in [("learned", "What I learned"), ("confused", "What I still don't understand"), ("questions", "Questions")]:
                if fields.get(key):
                    st.markdown(f"##### {label}")
                    st.write(fields.get(key))
            if entry.get("content"):
                st.markdown("##### Free notes")
                st.write(entry.get("content"))

        else:
            st.write(entry.get("content", ""))

        if linked_task:
            st.divider()
            st.markdown("#### Tracker mirror")
            st.write(f"Tracker: **{linked_task.get('title', 'Untitled')}** · {get_status(linked_task, archived=linked_task.get('archived', False))} · {linked_task.get('type', 'gray')}")

            with st.expander("Tracker Notes mirror"):
                notes = linked_task.get("notes", [])
                if notes:
                    for note in notes:
                        st.write(f"📝 {note.get('time', '')}")
                        st.write(note.get("text", ""))
                else:
                    st.caption("No tracker notes yet.")

            with st.expander("Tracker History mirror"):
                history = linked_task.get("history", [])
                if history:
                    for item in history[-30:]:
                        st.write(f"• {item.get('action', '')} → {item.get('time', '')}")
                else:
                    st.caption("No tracker history yet.")

        with st.expander("Markdown preview for Obsidian"):
            _render_entry_markdown_preview(journal, entry, linked_task)


def _render_edit_entry(journals, journal, entry):
    entry_id = entry.get("id")
    if not st.session_state.journal_open_edit.get(entry_id, False):
        return

    jtype = journal.get("type", "custom")
    with st.container(border=True):
        st.markdown("#### Edit entry")
        with st.form(f"edit_entry_{entry_id}"):
            title = st.text_input("Title", value=entry.get("title", "Untitled"), key=f"edit_title_{entry_id}")
            col1, col2, col3 = st.columns(3)
            with col1:
                entry_date = None
                if jtype != "draft":
                    entry_date = st.date_input("Date", value=_date_value(entry.get("date")), key=f"edit_date_{entry_id}").isoformat()
            with col2:
                status = st.selectbox("Entry status", ENTRY_STATUSES, index=_status_index(entry.get("status", "Draft")), key=f"edit_status_{entry_id}")
            with col3:
                tags = st.text_input("Tags", value=", ".join(entry.get("tags", [])), key=f"edit_tags_{entry_id}")

            specific = _render_type_specific_entry_fields(jtype, f"edit_{entry_id}", entry)
            submitted = st.form_submit_button("Save changes")

            if submitted:
                entry["title"] = title or "Untitled"
                entry["status"] = status
                entry["date"] = entry_date
                entry["tags"] = _parse_tags(tags)
                entry["fields"] = specific.get("fields", {})
                entry["content"] = specific.get("content", "")
                entry["slug"] = slugify(entry["title"])
                entry["obsidian_file"] = make_obsidian_entry_path(journal, entry)
                _touch_entry(journal, entry)
                save_journals(journals)
                st.session_state.journal_open_edit[entry_id] = False
                st.rerun()


def _delete_entry(journals, tasks, journal, entry):
    entry_id = entry.get("id")
    unlink_entry(tasks, journals, entry_id, source="delete_entry")
    journal["entries"] = [e for e in journal.get("entries", []) if e.get("id") != entry_id]
    _touch_journal(journal)
    save_journals(journals)


def _render_entry_card(journals, tasks, journal, entry):
    entry_id = entry.get("id")
    linked_task = find_task(tasks, entry.get("linked_tracker_id"))
    jtype = journal.get("type", "custom")

    with st.container(border=True):
        st.markdown(f"### 📄 {entry.get('title', 'Untitled')}")
        meta = _entry_metadata_line(entry, jtype, linked_task)
        if meta:
            st.caption(meta)

        summary = _entry_summary(entry, jtype)
        if summary:
            st.write(summary + ("..." if len(summary) > 700 else ""))
        else:
            st.caption("Empty entry")

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            if st.button("✍️ Write", key=f"entry_write_{entry_id}"):
                st.session_state["writer_journal_id"] = journal.get("id")
                st.session_state["writer_entry_id"] = entry_id
                st.session_state["writer_section"] = None
                st.rerun()
        with col2:
            if st.button("📋 Full", key=f"entry_full_{entry_id}"):
                st.session_state.journal_open_full[entry_id] = not st.session_state.journal_open_full.get(entry_id, False)
        with col3:
            if st.button("✏ Edit", key=f"entry_edit_{entry_id}"):
                st.session_state.journal_open_edit[entry_id] = not st.session_state.journal_open_edit.get(entry_id, False)
        with col4:
            if st.button("🔗 Sync", key=f"entry_sync_{entry_id}"):
                st.session_state.journal_open_sync[entry_id] = not st.session_state.journal_open_sync.get(entry_id, False)
        with col5:
            if st.button("🗑 Delete", key=f"entry_delete_{entry_id}"):
                _delete_entry(journals, tasks, journal, entry)
                st.rerun()

        _render_full_entry(journal, entry, linked_task)
        _render_edit_entry(journals, journal, entry)
        _render_sync_panel(journals, tasks, journal, entry)


# -----------------------
# JOURNAL PAGES
# -----------------------
def _render_journals_dashboard(journals):
    st.title("📖 Journals")
    st.caption("Journals are big writing spaces. Each journal will become an Obsidian folder with an index and separate entry files.")

    total_entries = sum(len(journal.get("entries", [])) for journal in journals)
    linked_entries = sum(
        1
        for journal in journals
        for entry in journal.get("entries", [])
        if entry.get("linked_tracker_id")
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Journals", len(journals))
    col2.metric("Entries", total_entries)
    col3.metric("Linked trackers", linked_entries)

    _render_new_journal_form(journals)

    st.subheader("Your Journals")
    if not journals:
        st.info("Create your first journal. Good starters: Дневник, Эссе, Черновики, Учеба, Проекты.")
        return

    query = st.text_input("Search journals", placeholder="Search by name, type, description, tags")
    q = query.lower().strip()

    visible = []
    for journal in journals:
        haystack = " ".join([
            journal.get("name", ""),
            journal.get("type", ""),
            journal.get("description", ""),
            " ".join(journal.get("tags", [])),
        ]).lower()
        if not q or q in haystack:
            visible.append(journal)

    for journal in visible:
        with st.container(border=True):
            st.markdown(f"### 📁 {journal.get('name', 'Untitled Journal')}")
            st.caption(f"{_type_label(journal.get('type', 'custom'))} · {len(journal.get('entries', []))} entries · `{journal.get('obsidian_index')}`")
            if journal.get("description"):
                st.write(journal.get("description"))
            if journal.get("tags"):
                st.caption(_tags_text(journal.get("tags")))

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Open", key=f"open_journal_{journal.get('id')}", use_container_width=True):
                    st.session_state["selected_journal_id"] = journal.get("id")
                    st.rerun()
            with col2:
                if st.button("Delete journal", key=f"delete_journal_{journal.get('id')}", use_container_width=True):
                    journals.remove(journal)
                    save_journals(journals)
                    st.rerun()


def _render_single_journal(journals, tasks, journal):
    if st.button("← Back to Journals", key="back_to_journals"):
        _go_to_journals()
        st.rerun()

    st.title(f"📁 {journal.get('name', 'Untitled Journal')}")
    st.caption(f"{_type_label(journal.get('type', 'custom'))} · Obsidian index: `{journal.get('obsidian_index')}`")
    if journal.get("description"):
        st.write(journal.get("description"))

    _render_new_entry_form(journals, journal)

    entries = journal.get("entries", [])
    st.subheader("Entries")

    if not entries:
        st.info("No entries yet.")
        return

    col1, col2 = st.columns([2, 1])
    with col1:
        query = st.text_input("Search entries", placeholder="Search title, text, tags, fields")
    with col2:
        status_filter = st.selectbox("Status", ["All"] + ENTRY_STATUSES)

    q = query.lower().strip()
    filtered = []
    for entry in entries:
        fields_text = " ".join(str(v) for v in (entry.get("fields") or {}).values() if v)
        haystack = " ".join([
            entry.get("title", ""),
            entry.get("status", ""),
            entry.get("content", ""),
            fields_text,
            " ".join(entry.get("tags", [])),
        ]).lower()
        status_ok = status_filter == "All" or entry.get("status") == status_filter
        query_ok = not q or q in haystack
        if status_ok and query_ok:
            filtered.append(entry)

    if not filtered:
        st.warning("No entries match this filter.")
        return

    for entry in filtered:
        _render_entry_card(journals, tasks, journal, entry)


def render_journal(on_back=None):
    _ensure_state()
    _render_back(on_back)

    journals = load_journals()
    tasks = load_tasks()

    writer_journal_id = st.session_state.get("writer_journal_id")
    writer_entry_id = st.session_state.get("writer_entry_id")
    if writer_journal_id and writer_entry_id:
        writer_journal = find_journal(journals, writer_journal_id)
        found_journal, writer_entry = find_entry(journals, writer_entry_id, writer_journal_id)
        if writer_journal and writer_entry:
            _render_focus_writer(journals, tasks, writer_journal, writer_entry)
            return
        _close_writer()

    selected_id = st.session_state.get("selected_journal_id")
    selected_journal = find_journal(journals, selected_id) if selected_id else None

    if selected_journal:
        _render_single_journal(journals, tasks, selected_journal)
    else:
        _render_journals_dashboard(journals)
