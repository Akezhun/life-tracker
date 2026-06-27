import json
from pathlib import Path
from uuid import uuid4

from core.utils import now

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
TASKS_FILE = DATA_DIR / "tasks.json"
LEGACY_TASKS_FILE = PROJECT_ROOT / "tasks.json"
OLD_JOURNAL_FILE = DATA_DIR / "journal.json"
JOURNALS_FILE = DATA_DIR / "journals.json"


# -----------------------
# GENERIC JSON STORAGE
# -----------------------
def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def save_json(path, data):
    _ensure_data_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(path, default):
    _ensure_data_dir()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# -----------------------
# TASKS
# -----------------------
def save_tasks(tasks):
    save_json(TASKS_FILE, tasks)


def _ensure_task_defaults(task):
    changed = False
    current_time = now().isoformat()

    defaults = {
        "id": str(uuid4()),
        "type": "gray",
        "title": "Untitled",
        "priority": "low",
        "deadline": None,
        "cycle": None,
        "days": None,
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
        "tags": [],
        "obsidian_file": None,
        "required_confirmations": 1,
        "current_confirmations": 0,
        "linked_journal_id": None,
        "linked_entry_id": None,
    }

    for key, value in defaults.items():
        if key not in task:
            task[key] = value
            changed = True

    try:
        task["required_confirmations"] = max(1, int(task.get("required_confirmations", 1)))
    except Exception:
        task["required_confirmations"] = 1
        changed = True

    try:
        task["current_confirmations"] = max(0, int(task.get("current_confirmations", 0)))
    except Exception:
        task["current_confirmations"] = 0
        changed = True

    if isinstance(task.get("tags"), str):
        task["tags"] = [tag.strip().lstrip("#") for tag in task["tags"].split(",") if tag.strip()]
        changed = True

    if not isinstance(task.get("notes"), list):
        task["notes"] = []
        changed = True

    if not isinstance(task.get("history"), list):
        task["history"] = []
        changed = True

    return changed


def load_tasks():
    _ensure_data_dir()

    source = TASKS_FILE
    if not TASKS_FILE.exists() and LEGACY_TASKS_FILE.exists():
        source = LEGACY_TASKS_FILE

    data = load_json(source, [])

    changed = False
    for task in data:
        if _ensure_task_defaults(task):
            changed = True

    if changed or source == LEGACY_TASKS_FILE:
        save_tasks(data)

    return data


# -----------------------
# JOURNALS V7.1
# -----------------------
JOURNAL_TYPES = ["diary", "essay", "project", "learning", "draft", "custom"]
JOURNAL_TYPE_LABELS = {
    "diary": "Diary",
    "essay": "Essay / Academic Writing",
    "project": "Project Journal",
    "learning": "Learning Journal",
    "draft": "Draft / Черновик",
    "custom": "Custom",
}
ENTRY_STATUSES = ["Idea", "Draft", "Active", "Revision", "Final", "Submitted", "Finished", "Archived"]


def slugify(text):
    raw = (text or "untitled").strip().lower()
    replacements = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
        "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    out = []
    previous_dash = False
    for ch in raw:
        ch = replacements.get(ch, ch)
        if ch.isalnum():
            out.append(ch)
            previous_dash = False
        elif not previous_dash:
            out.append("-")
            previous_dash = True
    slug = "".join(out).strip("-")
    return slug or "untitled"


def _parse_tags_value(value):
    if isinstance(value, list):
        return [str(tag).strip().lstrip("#") for tag in value if str(tag).strip()]
    if isinstance(value, str):
        return [tag.strip().lstrip("#") for tag in value.split(",") if tag.strip()]
    return []


def make_obsidian_entry_path(journal, entry):
    journal_slug = journal.get("slug") or slugify(journal.get("name", "Journal"))
    entry_slug = entry.get("slug") or slugify(entry.get("title", "Untitled"))
    return f"Journals/{journal_slug}/entries/{entry_slug}.md"


def make_obsidian_index_path(journal):
    journal_slug = journal.get("slug") or slugify(journal.get("name", "Journal"))
    return f"Journals/{journal_slug}/index.md"


def _ensure_entry_defaults(entry, journal):
    changed = False
    current_time = now().isoformat()

    defaults = {
        "id": str(uuid4()),
        "title": "Untitled",
        "status": "Draft",
        "date": current_time[:10],
        "tags": [],
        "content": "",
        "fields": {},
        "linked_tracker_id": None,
        "created_at": current_time,
        "edited_at": None,
        "archived": False,
        "slug": None,
        "obsidian_file": None,
    }

    for key, value in defaults.items():
        if key not in entry:
            entry[key] = value
            changed = True

    if isinstance(entry.get("tags"), str):
        entry["tags"] = _parse_tags_value(entry.get("tags"))
        changed = True

    if not isinstance(entry.get("fields"), dict):
        entry["fields"] = {}
        changed = True

    if not entry.get("slug"):
        entry["slug"] = slugify(entry.get("title", "Untitled"))
        changed = True

    if not entry.get("obsidian_file"):
        entry["obsidian_file"] = make_obsidian_entry_path(journal, entry)
        changed = True

    if journal.get("type") == "draft":
        # Draft entries deliberately do not need a date.
        entry["date"] = None

    return changed


def _ensure_journal_defaults(journal):
    changed = False
    current_time = now().isoformat()

    defaults = {
        "id": str(uuid4()),
        "name": "Untitled Journal",
        "type": "custom",
        "description": "",
        "tags": [],
        "entries": [],
        "created_at": current_time,
        "edited_at": None,
        "archived": False,
        "slug": None,
        "obsidian_index": None,
    }

    for key, value in defaults.items():
        if key not in journal:
            journal[key] = value
            changed = True

    if journal.get("type") not in JOURNAL_TYPES:
        journal["type"] = "custom"
        changed = True

    if isinstance(journal.get("tags"), str):
        journal["tags"] = _parse_tags_value(journal.get("tags"))
        changed = True

    if not isinstance(journal.get("entries"), list):
        journal["entries"] = []
        changed = True

    if not journal.get("slug"):
        journal["slug"] = slugify(journal.get("name", "Untitled Journal"))
        changed = True

    if not journal.get("obsidian_index"):
        journal["obsidian_index"] = make_obsidian_index_path(journal)
        changed = True

    for entry in journal.get("entries", []):
        if _ensure_entry_defaults(entry, journal):
            changed = True

    return changed


def _migrate_old_journal_entries():
    old_entries = load_json(OLD_JOURNAL_FILE, [])
    if not old_entries:
        return []

    current_time = now().isoformat()
    diary = {
        "id": str(uuid4()),
        "name": "Дневник",
        "type": "diary",
        "description": "Migrated from the old V7 journal.json.",
        "tags": ["migrated"],
        "entries": [],
        "created_at": current_time,
        "edited_at": current_time,
        "archived": False,
        "slug": "dnevnik",
        "obsidian_index": "Journals/dnevnik/index.md",
    }

    for old in old_entries:
        title = old.get("title", "Untitled")
        entry = {
            "id": old.get("id") or str(uuid4()),
            "title": title,
            "status": "Active",
            "date": old.get("date") or current_time[:10],
            "tags": _parse_tags_value(old.get("tags", [])),
            "content": old.get("content", ""),
            "fields": {
                "mood": old.get("mood", 3),
                "energy": old.get("energy", 3),
            },
            "linked_tracker_id": None,
            "created_at": old.get("created_at") or current_time,
            "edited_at": old.get("edited_at"),
            "archived": old.get("archived", False),
            "slug": slugify(title),
            "obsidian_file": None,
        }
        entry["obsidian_file"] = make_obsidian_entry_path(diary, entry)
        diary["entries"].append(entry)

    return [diary]


def load_journals():
    journals = load_json(JOURNALS_FILE, None)
    if journals is None:
        journals = _migrate_old_journal_entries()
        if not journals:
            journals = []

    changed = False
    for journal in journals:
        if _ensure_journal_defaults(journal):
            changed = True

    if changed or not JOURNALS_FILE.exists():
        save_journals(journals)

    return journals


def save_journals(journals):
    save_json(JOURNALS_FILE, journals)


def find_journal(journals, journal_id):
    for journal in journals:
        if journal.get("id") == journal_id:
            return journal
    return None


def find_entry(journals, entry_id, journal_id=None):
    for journal in journals:
        if journal_id and journal.get("id") != journal_id:
            continue
        for entry in journal.get("entries", []):
            if entry.get("id") == entry_id:
                return journal, entry
    return None, None


def flatten_journal_entries(journals, include_archived=False):
    rows = []
    for journal in journals:
        if journal.get("archived") and not include_archived:
            continue
        for entry in journal.get("entries", []):
            if entry.get("archived") and not include_archived:
                continue
            rows.append({
                "journal_id": journal.get("id"),
                "journal_name": journal.get("name", "Untitled Journal"),
                "journal_type": journal.get("type", "custom"),
                "entry_id": entry.get("id"),
                "entry_title": entry.get("title", "Untitled"),
                "entry_status": entry.get("status", "Draft"),
            })
    return rows


# -----------------------
# BACKWARDS-COMPATIBILITY FOR V7 HOME
# -----------------------
def load_journal_entries():
    journals = load_journals()
    entries = []
    for journal in journals:
        for entry in journal.get("entries", []):
            item = dict(entry)
            item["journal_id"] = journal.get("id")
            item["journal_name"] = journal.get("name")
            entries.append(item)
    return entries


def save_journal_entries(entries):
    # Legacy helper retained so old imports do not crash.
    journal = {
        "id": str(uuid4()),
        "name": "Imported Entries",
        "type": "diary",
        "description": "Generated by legacy save_journal_entries.",
        "entries": entries,
        "created_at": now().isoformat(),
        "edited_at": now().isoformat(),
        "archived": False,
        "tags": [],
        "slug": "imported-entries",
        "obsidian_index": "Journals/imported-entries/index.md",
    }
    save_journals([journal])
