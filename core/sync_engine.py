from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

from core.github_vault import GitHubVaultClient, load_github_config
from core.markdown_export import build_vault_files, merge_obsidian_workspace, strip_obsidian_workspace
from core.storage import JOURNALS_FILE, TASKS_FILE, load_journals, load_tasks, save_json, save_journals, save_tasks
from core.utils import now

DATA_PREFIX = "LifeOS_Data"
SYNC_META_FILE = Path(__file__).resolve().parents[1] / "data" / "sync_meta.json"
_AUTOSYNC_RUNNING = False
_AUTOSYNC_SUSPENDED = False


def _secrets():
    if st is not None:
        try:
            return st.secrets
        except Exception:
            return {}
    return {}


def _config():
    return load_github_config(_secrets())


def _read_json_file(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json_file(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_sync_meta() -> dict:
    return _read_json_file(SYNC_META_FILE, {})


def save_sync_meta(meta: dict):
    _write_json_file(SYNC_META_FILE, meta)


def _touch_synced_object(obj: dict, sha: str | None = None, synced_at: str | None = None):
    synced_at = synced_at or now().isoformat()
    if sha:
        obj["github_sha"] = sha
    obj["last_synced_at"] = synced_at


def _find_task_by_path(tasks: List[dict], path: str):
    for task in tasks:
        if task.get("obsidian_file") == path:
            return task
    return None


def _find_journal_index_by_path(journals: List[dict], path: str):
    for journal in journals:
        if journal.get("obsidian_index") == path:
            return journal
    return None


def _find_entry_by_path(journals: List[dict], path: str):
    for journal in journals:
        for entry in journal.get("entries", []):
            if entry.get("obsidian_file") == path:
                return journal, entry
    return None, None


def _object_for_path(journals: List[dict], tasks: List[dict], path: str):
    obj = _find_task_by_path(tasks, path)
    if obj:
        return obj
    obj = _find_journal_index_by_path(journals, path)
    if obj:
        return obj
    _, entry = _find_entry_by_path(journals, path)
    if entry:
        return entry
    return None


def _expected_shas_for_files(journals: List[dict], tasks: List[dict], files: Dict[str, str]) -> Dict[str, str]:
    expected: Dict[str, str] = {}
    for path in files:
        obj = _object_for_path(journals, tasks, path)
        if obj and obj.get("github_sha"):
            expected[path] = obj.get("github_sha")
    return expected


def _data_files(tasks: List[dict], journals: List[dict]) -> Dict[str, str]:
    return {
        f"{DATA_PREFIX}/tasks.json": json.dumps(tasks, indent=2, ensure_ascii=False),
        f"{DATA_PREFIX}/journals.json": json.dumps(journals, indent=2, ensure_ascii=False),
    }


def build_all_vault_files(journals: List[dict] | None = None, tasks: List[dict] | None = None) -> Dict[str, str]:
    tasks = tasks if tasks is not None else load_tasks()
    journals = journals if journals is not None else load_journals()

    # V8.2 EMERGENCY RULE:
    # Cloud JSON data is the real database. Push it BEFORE generated Markdown.
    # If Markdown conflicts happen, tasks.json / journals.json must still be safe in GitHub.
    files = _data_files(tasks, journals)
    files.update(build_vault_files(journals, tasks))
    return files



def _preserve_remote_obsidian_workspaces(client: GitHubVaultClient, files: Dict[str, str]) -> Dict[str, str]:
    """
    Preserve text the user wrote directly in Obsidian inside the protected
    Obsidian Workspace block. If the remote file differs ONLY in that protected
    block, this returns a safe SHA override so the file can still be updated
    without creating a conflict.
    """
    safe_sha_overrides: Dict[str, str] = {}
    for path, generated in list(files.items()):
        if not path.endswith(".md"):
            continue
        try:
            remote_text, remote_sha = client.read_text(path)
        except Exception:
            continue
        if not remote_text:
            continue

        files[path] = merge_obsidian_workspace(generated, remote_text)
        if remote_sha and strip_obsidian_workspace(remote_text) == strip_obsidian_workspace(generated):
            safe_sha_overrides[path] = remote_sha
    return safe_sha_overrides


def push_all_to_github(force: bool = False, reason: str = "manual") -> dict:
    config = _config()
    if not config.is_ready:
        return {"ok": [], "failed": ["Missing GITHUB_TOKEN or GITHUB_REPO"], "conflicts": [], "shas": {}}

    tasks = load_tasks()
    journals = load_journals()
    files = build_all_vault_files(journals, tasks)
    expected = _expected_shas_for_files(journals, tasks, files)
    client = GitHubVaultClient(config)

    # V8.3: never silently erase text written directly in Obsidian inside the
    # protected Obsidian Workspace block. If only that block changed remotely,
    # allow the update using the current remote SHA while preserving the block.
    safe_sha_overrides = _preserve_remote_obsidian_workspaces(client, files)
    expected.update(safe_sha_overrides)

    results = client.sync_files(files, message_prefix=f"LifeOS {reason} sync", expected_shas=expected, force=force)

    synced_at = now().isoformat()
    shas = results.get("shas", {}) or {}
    changed_metadata = False
    for path, sha in shas.items():
        obj = _object_for_path(journals, tasks, path)
        if obj is not None:
            _touch_synced_object(obj, sha, synced_at)
            changed_metadata = True

    # Data files get tracked in sync meta, not every object.
    meta = load_sync_meta()
    if shas.get(f"{DATA_PREFIX}/tasks.json"):
        meta["tasks_json_sha"] = shas.get(f"{DATA_PREFIX}/tasks.json")
    if shas.get(f"{DATA_PREFIX}/journals.json"):
        meta["journals_json_sha"] = shas.get(f"{DATA_PREFIX}/journals.json")
    meta[f"last_{reason}_push_at"] = synced_at
    meta["last_push_at"] = synced_at
    meta["last_push_ok_count"] = len(results.get("ok", []))
    meta["last_push_failed_count"] = len(results.get("failed", []))
    meta["last_push_conflict_count"] = len(results.get("conflicts", []))
    meta["last_error"] = "; ".join(results.get("failed", [])[:3]) if results.get("failed") else None
    save_sync_meta(meta)

    if changed_metadata:
        global _AUTOSYNC_SUSPENDED
        _AUTOSYNC_SUSPENDED = True
        try:
            save_tasks(tasks)
            save_journals(journals)
        finally:
            _AUTOSYNC_SUSPENDED = False

    return results


def auto_push_after_local_save(trigger: str = "local save"):
    global _AUTOSYNC_RUNNING
    if _AUTOSYNC_RUNNING or _AUTOSYNC_SUSPENDED:
        return
    config = _config()
    if not config.is_ready:
        return
    _AUTOSYNC_RUNNING = True
    try:
        results = push_all_to_github(force=False, reason="auto")
        meta = load_sync_meta()
        meta["last_auto_trigger"] = trigger
        save_sync_meta(meta)
        return results
    except Exception as exc:
        meta = load_sync_meta()
        meta["last_error"] = str(exc)
        meta["last_auto_push_failed_at"] = now().isoformat()
        save_sync_meta(meta)
    finally:
        _AUTOSYNC_RUNNING = False


def bootstrap_from_cloud_once():
    """
    V8.2 cloud-first bootstrap.

    Streamlit Cloud filesystem is only a cache. On each browser session we hydrate
    local JSON from GitHub Vault LifeOS_Data/*.json. If remote data does not exist
    yet, we seed it from the current local JSON once, so future reboots stop
    reverting to repo-bundled files.
    """
    if st is None:
        return
    try:
        if st.session_state.get("lifeos_cloud_bootstrapped"):
            return
    except Exception:
        return

    config = _config()
    if not config.is_ready:
        try:
            st.session_state["lifeos_cloud_bootstrapped"] = True
        except Exception:
            pass
        return

    client = GitHubVaultClient(config)
    pulled = []
    seeded_remote = False
    global _AUTOSYNC_SUSPENDED
    _AUTOSYNC_SUSPENDED = True
    try:
        tasks_text, tasks_sha = client.read_text(f"{DATA_PREFIX}/tasks.json")
        journals_text, journals_sha = client.read_text(f"{DATA_PREFIX}/journals.json")

        if tasks_text is not None:
            tasks = json.loads(tasks_text or "[]")
            _write_json_file(TASKS_FILE, tasks)
            pulled.append("tasks.json")
        if journals_text is not None:
            journals = json.loads(journals_text or "[]")
            _write_json_file(JOURNALS_FILE, journals)
            pulled.append("journals.json")

        meta = load_sync_meta()
        meta["last_bootstrap_pull_at"] = now().isoformat()
        meta["bootstrap_pulled"] = pulled
        meta["cloud_data_ready"] = bool(tasks_text is not None or journals_text is not None)
        if tasks_sha:
            meta["tasks_json_sha"] = tasks_sha
        if journals_sha:
            meta["journals_json_sha"] = journals_sha
        save_sync_meta(meta)

        # First-time cloud setup: if the vault has no LifeOS_Data yet, create it.
        # This prevents the app from living only on Streamlit's temporary disk.
        if tasks_text is None and journals_text is None:
            _AUTOSYNC_SUSPENDED = False
            results = push_all_to_github(force=True, reason="initial-cloud-seed")
            seeded_remote = bool(results.get("ok"))
            _AUTOSYNC_SUSPENDED = True
            meta = load_sync_meta()
            meta["initial_cloud_seed_at"] = now().isoformat()
            meta["initial_cloud_seed_ok"] = seeded_remote
            meta["cloud_data_ready"] = seeded_remote
            save_sync_meta(meta)

    except Exception as exc:
        meta = load_sync_meta()
        meta["last_bootstrap_error"] = str(exc)
        meta["cloud_data_ready"] = False
        save_sync_meta(meta)
    finally:
        _AUTOSYNC_SUSPENDED = False
        try:
            st.session_state["lifeos_cloud_bootstrapped"] = True
        except Exception:
            pass


# -----------------------
# Markdown pull helpers for journals
# -----------------------
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _parse_frontmatter(text: str) -> Tuple[dict, str]:
    match = _FRONTMATTER_RE.match(text or "")
    if not match:
        return {}, text or ""
    raw = match.group(1)
    body = text[match.end():]
    data = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value == "null":
            parsed = None
        elif value in ("true", "false"):
            parsed = value == "true"
        elif value.startswith('"') and value.endswith('"'):
            parsed = value[1:-1].replace('\\"', '"')
        elif value.startswith("[") and value.endswith("]"):
            inside = value[1:-1].strip()
            parsed = [] if not inside else [v.strip().strip('"') for v in inside.split(",")]
        else:
            parsed = value
        data[key.strip()] = parsed
    return data, body


def _section(body: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(body or "")
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+.+$", body[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(body)
    return body[start:end].strip("\n ")


def _clean_main_text(text: str) -> str:
    return (text or "").strip()


def _apply_markdown_to_entry(entry: dict, journal: dict, markdown_text: str, remote_sha: str, force: bool = False) -> Tuple[bool, str]:
    fm, body = _parse_frontmatter(markdown_text)
    if fm.get("lifeos_type") != "journal_entry":
        return False, "not a LifeOS journal entry"

    last_synced = entry.get("last_synced_at")
    last_local = entry.get("last_local_edit_at") or entry.get("edited_at")
    if remote_sha and entry.get("github_sha") and remote_sha != entry.get("github_sha"):
        if last_local and last_synced and last_local > last_synced and not force:
            return False, "conflict — local entry changed after last sync"

    if fm.get("status"):
        entry["status"] = fm.get("status")
    if "date" in fm:
        entry["date"] = fm.get("date")
    if isinstance(fm.get("tags"), list):
        entry["tags"] = fm.get("tags")

    fields = entry.setdefault("fields", {})
    jtype = journal.get("type")
    if jtype == "essay":
        fields["outline"] = _section(body, "Outline")
        fields["draft"] = _section(body, "Draft")
        fields["sources"] = _section(body, "Sources")
        fields["final_text"] = _section(body, "Final Version")
        entry["content"] = fields.get("draft", "")
    elif jtype == "project":
        fields["problem"] = _section(body, "Problem / Context")
        fields["what_i_did"] = _section(body, "What I did")
        fields["next_step"] = _section(body, "Next step")
        entry["content"] = _section(body, "Additional Notes")
    elif jtype == "learning":
        fields["learned"] = _section(body, "What I learned")
        fields["confused"] = _section(body, "What I still don't understand")
        fields["questions"] = _section(body, "Questions")
        entry["content"] = _section(body, "Free Notes")
    else:
        entry["content"] = _clean_main_text(_section(body, "Main Text"))

    entry["github_sha"] = remote_sha
    entry["last_synced_at"] = now().isoformat()
    entry["edited_at"] = now().isoformat()
    return True, "updated from Markdown"


def pull_from_github(force: bool = False, pull_markdown_journals: bool = True) -> dict:
    config = _config()
    if not config.is_ready:
        return {"ok": [], "failed": ["Missing GITHUB_TOKEN or GITHUB_REPO"], "conflicts": []}
    client = GitHubVaultClient(config)
    ok: List[str] = []
    failed: List[str] = []
    conflicts: List[str] = []

    global _AUTOSYNC_SUSPENDED
    _AUTOSYNC_SUSPENDED = True
    try:
        tasks_text, tasks_sha = client.read_text(f"{DATA_PREFIX}/tasks.json")
        journals_text, journals_sha = client.read_text(f"{DATA_PREFIX}/journals.json")
        if tasks_text:
            _write_json_file(TASKS_FILE, json.loads(tasks_text))
            ok.append("Pulled LifeOS_Data/tasks.json")
        if journals_text:
            _write_json_file(JOURNALS_FILE, json.loads(journals_text))
            ok.append("Pulled LifeOS_Data/journals.json")

        journals = load_journals()
        if pull_markdown_journals:
            files = client.list_files("Journals")
            by_path = {f.get("path"): f.get("sha") for f in files if f.get("path", "").endswith(".md")}
            for journal in journals:
                for entry in journal.get("entries", []):
                    path = entry.get("obsidian_file")
                    if not path or path not in by_path:
                        continue
                    text, sha = client.read_text(path)
                    if text is None:
                        continue
                    changed, msg = _apply_markdown_to_entry(entry, journal, text, sha or by_path[path], force=force)
                    if changed:
                        ok.append(f"Pulled Markdown: {path}")
                    elif msg.startswith("conflict"):
                        conflicts.append(f"{path}: {msg}")
            save_journals(journals)

        meta = load_sync_meta()
        meta["last_pull_at"] = now().isoformat()
        meta["last_pull_ok_count"] = len(ok)
        meta["last_pull_conflict_count"] = len(conflicts)
        if tasks_sha:
            meta["tasks_json_sha"] = tasks_sha
        if journals_sha:
            meta["journals_json_sha"] = journals_sha
        save_sync_meta(meta)
    except Exception as exc:
        failed.append(str(exc))
        meta = load_sync_meta()
        meta["last_pull_error"] = str(exc)
        save_sync_meta(meta)
    finally:
        _AUTOSYNC_SUSPENDED = False

    return {"ok": ok, "failed": failed, "conflicts": conflicts}
