from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from core.storage import make_obsidian_entry_path, make_obsidian_index_path, slugify
from core.utils import now
from modules.tracker.info import task_info
from modules.tracker.status import get_status


def _safe(value):
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n")


def _yaml_value(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_yaml_value(v) for v in value) + "]"
    text = str(value).replace('"', '\\"')
    return f'"{text}"'


def _frontmatter(data: Dict) -> str:
    lines = ["---"]
    for key, value in data.items():
        lines.append(f"{key}: {_yaml_value(value)}")
    lines.append("---")
    return "\n".join(lines)


def _tags_line(tags: Iterable[str]) -> str:
    tags = [str(tag).strip().lstrip("#") for tag in (tags or []) if str(tag).strip()]
    return " ".join(f"#{tag}" for tag in tags)


def _find_task(tasks: List[Dict], task_id: str | None) -> Dict | None:
    if not task_id:
        return None
    for task in tasks:
        if task.get("id") == task_id:
            return task
    return None


def _find_entry(journals: List[Dict], journal_id: str | None, entry_id: str | None):
    if not entry_id:
        return None, None
    for journal in journals:
        if journal_id and journal.get("id") != journal_id:
            continue
        for entry in journal.get("entries", []):
            if entry.get("id") == entry_id:
                return journal, entry
    return None, None


def _entry_body(journal: Dict, entry: Dict, linked_task: Dict | None = None) -> str:
    fields = entry.get("fields", {}) or {}
    jtype = journal.get("type", "custom")
    lines = [
        _frontmatter({
            "lifeos_type": "journal_entry",
            "journal": journal.get("name"),
            "journal_type": jtype,
            "entry_id": entry.get("id"),
            "status": entry.get("status"),
            "date": entry.get("date"),
            "tags": entry.get("tags", []),
            "linked_tracker_id": linked_task.get("id") if linked_task else None,
            "created_at": entry.get("created_at"),
            "edited_at": entry.get("edited_at"),
        }),
        "",
        f"# {entry.get('title', 'Untitled')}",
        "",
    ]

    if entry.get("status"):
        lines.append(f"**Status:** {entry.get('status')}  ")
    if entry.get("date"):
        lines.append(f"**Date:** {entry.get('date')}  ")
    tags = _tags_line(entry.get("tags", []))
    if tags:
        lines.append(f"**Tags:** {tags}  ")
    if linked_task:
        lines.append(f"**Linked tracker:** [[../../Trackers/{linked_task.get('id')}|{linked_task.get('title', 'Untitled')}]]  ")
    lines.extend(["", "---", ""])

    if jtype == "essay":
        if fields.get("subject"):
            lines.append(f"**Subject:** {fields.get('subject')}  ")
        if fields.get("deadline"):
            lines.append(f"**Deadline:** {fields.get('deadline')}  ")
        lines.extend([
            "",
            "## Outline",
            _safe(fields.get("outline")),
            "",
            "## Draft",
            _safe(fields.get("draft", entry.get("content", ""))),
            "",
            "## Sources",
            _safe(fields.get("sources")),
            "",
            "## Final Version",
            _safe(fields.get("final_text")),
        ])
    elif jtype == "project":
        if fields.get("project"):
            lines.extend([f"**Project:** {fields.get('project')}  ", ""])
        lines.extend([
            "## Problem / Context",
            _safe(fields.get("problem")),
            "",
            "## What I did",
            _safe(fields.get("what_i_did")),
            "",
            "## Next step",
            _safe(fields.get("next_step")),
            "",
            "## Additional Notes",
            _safe(entry.get("content")),
        ])
    elif jtype == "learning":
        if fields.get("course") or fields.get("topic"):
            lines.append(f"**Course:** {fields.get('course', '')}  ")
            lines.append(f"**Topic:** {fields.get('topic', '')}  ")
            lines.append("")
        lines.extend([
            "## What I learned",
            _safe(fields.get("learned")),
            "",
            "## What I still don't understand",
            _safe(fields.get("confused")),
            "",
            "## Questions",
            _safe(fields.get("questions")),
            "",
            "## Free Notes",
            _safe(entry.get("content")),
        ])
    else:
        lines.extend(["## Main Text", _safe(entry.get("content"))])

    if linked_task:
        lines.extend(["", "---", "", "## Tracker Mirror", ""])
        lines.append(f"**Tracker status:** {get_status(linked_task, archived=linked_task.get('archived', False))}  ")
        lines.append(f"**Tracker type:** {linked_task.get('type', 'gray')}  ")
        info = task_info(linked_task)
        if info:
            lines.append(f"**Tracker info:** {info}  ")
        lines.extend(["", "### Tracker Notes"])
        notes = linked_task.get("notes", []) or []
        if notes:
            for note in notes:
                lines.extend(["", f"#### {note.get('time', '')}", _safe(note.get("text", ""))])
        else:
            lines.append("No tracker notes yet.")
        lines.extend(["", "### Tracker History"])
        history = linked_task.get("history", []) or []
        if history:
            for item in history[-50:]:
                lines.extend(["", f"#### {item.get('time', '')}", f"`{item.get('action', '')}`"])
        else:
            lines.append("No tracker history yet.")

    return "\n".join(lines).strip() + "\n"


def _journal_index_body(journal: Dict) -> str:
    lines = [
        _frontmatter({
            "lifeos_type": "journal_index",
            "journal_id": journal.get("id"),
            "journal_type": journal.get("type"),
            "tags": journal.get("tags", []),
            "created_at": journal.get("created_at"),
            "edited_at": journal.get("edited_at"),
        }),
        "",
        f"# {journal.get('name', 'Untitled Journal')}",
        "",
    ]
    if journal.get("description"):
        lines.extend([_safe(journal.get("description")), ""])
    tags = _tags_line(journal.get("tags", []))
    if tags:
        lines.extend([f"Tags: {tags}", ""])

    lines.append("## Entries")
    entries = [e for e in journal.get("entries", []) if not e.get("archived")]
    if not entries:
        lines.append("No entries yet.")
    for entry in entries:
        entry_slug = entry.get("slug") or slugify(entry.get("title", "Untitled"))
        meta = []
        if entry.get("date"):
            meta.append(entry.get("date"))
        if entry.get("status"):
            meta.append(entry.get("status"))
        suffix = f" — {' · '.join(meta)}" if meta else ""
        lines.append(f"- [[entries/{entry_slug}|{entry.get('title', 'Untitled')}]]{suffix}")
    return "\n".join(lines).strip() + "\n"


def _tracker_body(task: Dict, journals: List[Dict]) -> str:
    journal, entry = _find_entry(journals, task.get("linked_journal_id"), task.get("linked_entry_id"))
    status = get_status(task, archived=task.get("archived", False))
    lines = [
        _frontmatter({
            "lifeos_type": "tracker",
            "tracker_id": task.get("id"),
            "tracker_type": task.get("type"),
            "priority": task.get("priority"),
            "status": status,
            "done": task.get("done"),
            "archived": task.get("archived"),
            "failed": task.get("failed"),
            "deadline": task.get("deadline"),
            "cycle": task.get("cycle"),
            "days": task.get("days"),
            "tags": task.get("tags", []),
            "linked_journal_id": task.get("linked_journal_id"),
            "linked_entry_id": task.get("linked_entry_id"),
            "created_at": task.get("created_at"),
            "edited_at": task.get("edited_at"),
            "completed_at": task.get("completed_at"),
            "failed_at": task.get("failed_at"),
        }),
        "",
        f"# {task.get('title', 'Untitled')}",
        "",
        f"**Status:** {status}  ",
        f"**Type:** {task.get('type', 'gray')}  ",
        f"**Priority:** {task.get('priority', 'low')}  ",
        f"**Info:** {task_info(task)}  ",
    ]
    if task.get("tags"):
        lines.append(f"**Tags:** {_tags_line(task.get('tags', []))}  ")
    if journal and entry:
        jslug = journal.get("slug") or slugify(journal.get("name", "Journal"))
        eslug = entry.get("slug") or slugify(entry.get("title", "Untitled"))
        lines.append(f"**Linked journal entry:** [[../Journals/{jslug}/entries/{eslug}|{journal.get('name')} / {entry.get('title')}]]  ")
    lines.extend(["", "---", "", "## Notes"])
    notes = task.get("notes", []) or []
    if notes:
        for note in notes:
            lines.extend(["", f"### {note.get('time', '')}", _safe(note.get("text", ""))])
    else:
        lines.append("No notes yet.")

    lines.extend(["", "## History"])
    history = task.get("history", []) or []
    if history:
        for item in history:
            lines.extend(["", f"### {item.get('time', '')}", f"Action: `{item.get('action', '')}`"])
            details = item.get("details")
            if details:
                lines.append("")
                lines.append("```json")
                import json
                lines.append(json.dumps(details, indent=2, ensure_ascii=False))
                lines.append("```")
    else:
        lines.append("No history yet.")
    return "\n".join(lines).strip() + "\n"


def _root_index_body(journals: List[Dict], tasks: List[Dict]) -> str:
    lines = [
        _frontmatter({
            "lifeos_type": "root_index",
            "generated_at": now().isoformat(),
            "journal_count": len(journals),
            "tracker_count": len(tasks),
        }),
        "",
        "# LifeOS Vault Index",
        "",
        "## Journals",
    ]
    if not journals:
        lines.append("No journals yet.")
    for journal in journals:
        jslug = journal.get("slug") or slugify(journal.get("name", "Journal"))
        lines.append(f"- [[Journals/{jslug}/index|{journal.get('name', 'Untitled Journal')}]]")

    lines.extend(["", "## Trackers"])
    if not tasks:
        lines.append("No trackers yet.")
    for task in tasks:
        lines.append(f"- [[Trackers/{task.get('id')}|{task.get('title', 'Untitled')}]] — {get_status(task, archived=task.get('archived', False))}")
    return "\n".join(lines).strip() + "\n"


def build_vault_files(journals: List[Dict], tasks: List[Dict]) -> Dict[str, str]:
    files: Dict[str, str] = {}
    files["LifeOS_Index.md"] = _root_index_body(journals, tasks)

    for journal in journals:
        if journal.get("archived"):
            continue
        index_path = journal.get("obsidian_index") or make_obsidian_index_path(journal)
        files[index_path] = _journal_index_body(journal)
        for entry in journal.get("entries", []):
            if entry.get("archived"):
                continue
            path = entry.get("obsidian_file") or make_obsidian_entry_path(journal, entry)
            linked_task = _find_task(tasks, entry.get("linked_tracker_id"))
            files[path] = _entry_body(journal, entry, linked_task)

    for task in tasks:
        files[f"Trackers/{task.get('id')}.md"] = _tracker_body(task, journals)

    return files


def export_files_locally(files: Dict[str, str], output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for relative_path, content in files.items():
        target = output_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(str(target))
    return written
