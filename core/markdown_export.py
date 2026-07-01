from __future__ import annotations

from pathlib import Path
import re
from typing import Dict, Iterable, List

from core.storage import make_obsidian_entry_path, make_obsidian_index_path, make_obsidian_tracker_path, slugify
from core.utils import now
from modules.tracker.info import task_info
from modules.tracker.status import get_status


def _safe(value):
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


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


def _wikilink(path: str, label: str | None = None) -> str:
    """Create a compact Obsidian wikilink. Uses the file stem so links survive GITHUB_VAULT_ROOT folders."""
    stem = Path(path or "Untitled").stem
    if label and label != stem:
        return f"[[{stem}|{label}]]"
    return f"[[{stem}]]"




OBSIDIAN_WORKSPACE_START = "<!-- LIFEOS:OBSIDIAN_WORKSPACE_START -->"
OBSIDIAN_WORKSPACE_END = "<!-- LIFEOS:OBSIDIAN_WORKSPACE_END -->"


def _tag_wikilinks(tags: Iterable[str]) -> str:
    tags = [str(tag).strip().lstrip("#") for tag in (tags or []) if str(tag).strip()]
    return " ".join(f"[[Tags/{slugify(tag)}|#{tag}]]" for tag in tags)


def _obsidian_workspace_block() -> str:
    return "\n".join([
        "",
        "---",
        "",
        "## Obsidian Workspace",
        "",
        OBSIDIAN_WORKSPACE_START,
        "Write here if you want to add personal Obsidian-only notes. LifeOS will preserve everything inside this block.",
        OBSIDIAN_WORKSPACE_END,
        "",
    ])


def extract_obsidian_workspace(text: str) -> str | None:
    pattern = re.compile(
        re.escape(OBSIDIAN_WORKSPACE_START) + r"\n?(.*?)\n?" + re.escape(OBSIDIAN_WORKSPACE_END),
        re.DOTALL,
    )
    match = pattern.search(text or "")
    if not match:
        return None
    return match.group(1).strip("\n")


def strip_obsidian_workspace(text: str) -> str:
    pattern = re.compile(
        r"\n?---\n\n## Obsidian Workspace\n\n" +
        re.escape(OBSIDIAN_WORKSPACE_START) + r"\n?.*?\n?" + re.escape(OBSIDIAN_WORKSPACE_END) + r"\n?",
        re.DOTALL,
    )
    cleaned = pattern.sub("\n", text or "")
    pattern2 = re.compile(
        re.escape(OBSIDIAN_WORKSPACE_START) + r"\n?.*?\n?" + re.escape(OBSIDIAN_WORKSPACE_END),
        re.DOTALL,
    )
    return pattern2.sub("", cleaned).strip()


def merge_obsidian_workspace(generated: str, remote: str | None) -> str:
    manual = extract_obsidian_workspace(remote or "")
    if manual is None:
        return generated

    pattern = re.compile(
        re.escape(OBSIDIAN_WORKSPACE_START) + r"\n?.*?\n?" + re.escape(OBSIDIAN_WORKSPACE_END),
        re.DOTALL,
    )
    replacement = f"{OBSIDIAN_WORKSPACE_START}\n{manual}\n{OBSIDIAN_WORKSPACE_END}"
    if pattern.search(generated or ""):
        return pattern.sub(replacement, generated)
    return (generated or "").rstrip() + _obsidian_workspace_block().replace(
        f"{OBSIDIAN_WORKSPACE_START}\nWrite here if you want to add personal Obsidian-only notes. LifeOS will preserve everything inside this block.\n{OBSIDIAN_WORKSPACE_END}",
        replacement,
    ) + "\n"


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


def _entry_path(journal: Dict, entry: Dict) -> str:
    return entry.get("obsidian_file") or make_obsidian_entry_path(journal, entry)


def _tracker_path(task: Dict) -> str:
    return task.get("obsidian_file") or make_obsidian_tracker_path(task)


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
            "github_sha": entry.get("github_sha"),
            "last_synced_at": entry.get("last_synced_at"),
            "last_local_edit_at": entry.get("last_local_edit_at"),
            "created_at": entry.get("created_at"),
            "edited_at": entry.get("edited_at"),
        }),
        "",
        f"# {entry.get('title', 'Untitled')}",
        "",
    ]

    meta = []
    if entry.get("status"):
        meta.append(f"**Status:** {entry.get('status')}")
    if entry.get("date"):
        meta.append(f"**Date:** {entry.get('date')}")
    tags = _tags_line(entry.get("tags", []))
    if tags:
        meta.append(f"**Tags:** {tags}")
        meta.append(f"**Tag pages:** {_tag_wikilinks(entry.get("tags", []))}")
    if linked_task:
        meta.append(f"**Linked tracker:** {_wikilink(_tracker_path(linked_task), linked_task.get('title', 'Untitled'))}")
    lines.extend([m + "  " for m in meta])
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
        lines.append(f"**Tracker:** {_wikilink(_tracker_path(linked_task), linked_task.get('title', 'Untitled'))}  ")
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
                lines.extend(["", f"- **{_pretty_action(item)}** — `{item.get('time', '')}`"])
        else:
            lines.append("No tracker history yet.")

    lines.append(_obsidian_workspace_block())
    return "\n".join(lines).strip() + "\n"


def _journal_index_body(journal: Dict) -> str:
    lines = [
        _frontmatter({
            "lifeos_type": "journal_index",
            "journal_id": journal.get("id"),
            "journal_type": journal.get("type"),
            "tags": journal.get("tags", []),
            "github_sha": journal.get("github_sha"),
            "last_synced_at": journal.get("last_synced_at"),
            "last_local_edit_at": journal.get("last_local_edit_at"),
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
        path = _entry_path(journal, entry)
        meta = []
        if entry.get("date"):
            meta.append(entry.get("date"))
        if entry.get("status"):
            meta.append(entry.get("status"))
        suffix = f" — {' · '.join(meta)}" if meta else ""
        lines.append(f"- {_wikilink(path, entry.get('title', 'Untitled'))}{suffix}")
    return "\n".join(lines).strip() + "\n"


def _pretty_action(item: Dict) -> str:
    action = item.get("action", "")
    details = item.get("details", {}) or {}
    if action == "create":
        return "🆕 Created"
    if action == "done":
        parts = ["✅ Done"]
        if details.get("current_confirmations") and details.get("required_confirmations"):
            parts.append(f"{details.get('current_confirmations')}/{details.get('required_confirmations')}")
        if details.get("cycle"):
            parts.append(f"cycle: {details.get('cycle')}")
        if details.get("next_due"):
            parts.append(f"next: {details.get('next_due')[:16]}")
        return " · ".join(parts)
    if action == "partial_done":
        return f"🟡 Progress {details.get('current_confirmations', '?')}/{details.get('required_confirmations', '?')}"
    if action == "fail":
        if details.get("failed_period_start"):
            return f"❌ Failed period {details.get('failed_period_start')[:10]} → {details.get('failed_period_end', '')[:10]}"
        return "❌ Failed"
    if action == "note":
        text = _safe(details.get("text", ""))
        return "📝 Note" + (f": {text[:80]}" if text else "")
    if action == "edit":
        return "✏️ Edited"
    if action == "archive":
        return "📦 Archived"
    if action == "restore":
        return "↩️ Restored"
    return action or "event"


def _history_details(item: Dict) -> str:
    details = item.get("details") or {}
    if not details:
        return ""
    useful = []
    for key in ["deadline", "cycle", "cycle_start", "cycle_end", "next_due", "failed_period_start", "failed_period_end", "current_confirmations", "required_confirmations"]:
        if key in details and details.get(key) is not None:
            useful.append(f"- **{key}:** `{details.get(key)}`")
    return "\n".join(useful)


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
            "github_sha": task.get("github_sha"),
            "last_synced_at": task.get("last_synced_at"),
            "last_local_edit_at": task.get("last_local_edit_at"),
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
        lines.append(f"**Tag pages:** {_tag_wikilinks(task.get('tags', []))}  ")
    if journal and entry:
        lines.append(f"**Linked journal entry:** {_wikilink(_entry_path(journal, entry), f'{journal.get('name')} / {entry.get('title')}')}  ")

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
            lines.extend(["", f"### {item.get('time', '')}", _pretty_action(item)])
            details = _history_details(item)
            if details:
                lines.extend(["", details])
    else:
        lines.append("No history yet.")

    lines.append(_obsidian_workspace_block())
    return "\n".join(lines).strip() + "\n"


def _tag_index_body(tag: str, journal_items: List[Dict], tracker_items: List[Dict]) -> str:
    lines = [
        _frontmatter({
            "lifeos_type": "tag_index",
            "tag": tag,
            "generated_at": now().isoformat(),
            "journal_entry_count": len(journal_items),
            "tracker_count": len(tracker_items),
        }),
        "",
        f"# #{tag}",
        "",
        "## Journal Entries",
    ]
    if not journal_items:
        lines.append("No journal entries yet.")
    for item in journal_items:
        lines.append(f"- {_wikilink(item.get('path'), item.get('label'))}")

    lines.extend(["", "## Tags", "Tag pages are generated from LifeOS tags and can be used as Obsidian hubs.", "", "## Trackers"])
    if not tracker_items:
        lines.append("No trackers yet.")
    for item in tracker_items:
        lines.append(f"- {_wikilink(item.get('path'), item.get('label'))}")

    lines.append(_obsidian_workspace_block())
    return "\n".join(lines).strip() + "\n"


def _collect_tag_pages(journals: List[Dict], tasks: List[Dict]) -> Dict[str, Dict[str, List[Dict]]]:
    tags: Dict[str, Dict[str, List[Dict]]] = {}

    def add(tag: str, kind: str, path: str, label: str):
        clean = str(tag).strip().lstrip("#")
        if not clean:
            return
        tags.setdefault(clean, {"journal": [], "tracker": []})
        tags[clean][kind].append({"path": path, "label": label})

    for journal in journals:
        if journal.get("archived"):
            continue
        for entry in journal.get("entries", []):
            if entry.get("archived"):
                continue
            for tag in entry.get("tags", []) or []:
                add(tag, "journal", _entry_path(journal, entry), f"{journal.get('name')} / {entry.get('title')}")

    for task in tasks:
        for tag in task.get("tags", []) or []:
            add(tag, "tracker", _tracker_path(task), task.get("title", "Untitled"))

    return tags


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
        path = journal.get("obsidian_index") or make_obsidian_index_path(journal)
        lines.append(f"- {_wikilink(path, journal.get('name', 'Untitled Journal'))}")

    lines.extend(["", "## Trackers"])
    if not tasks:
        lines.append("No trackers yet.")
    for task in tasks:
        path = _tracker_path(task)
        lines.append(f"- {_wikilink(path, task.get('title', 'Untitled'))} — {get_status(task, archived=task.get('archived', False))}")
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
            path = _entry_path(journal, entry)
            linked_task = _find_task(tasks, entry.get("linked_tracker_id"))
            files[path] = _entry_body(journal, entry, linked_task)

    for task in tasks:
        path = _tracker_path(task)
        files[path] = _tracker_body(task, journals)

    for tag, items in _collect_tag_pages(journals, tasks).items():
        files[f"Tags/{slugify(tag)}.md"] = _tag_index_body(tag, items.get("journal", []), items.get("tracker", []))

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
