from pathlib import Path

import streamlit as st

from core.github_vault import load_github_config
from core.markdown_export import export_files_locally
from core.storage import PROJECT_ROOT, load_journals, load_tasks
from core.sync_engine import (
    build_all_vault_files,
    load_sync_meta,
    pull_from_github,
    push_all_to_github,
)


def _render_file_preview(files):
    st.markdown("### Files ready for Obsidian")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Markdown files", sum(1 for path in files if path.endswith(".md")))
    col2.metric("Journal files", sum(1 for path in files if path.startswith("Journals/")))
    col3.metric("Tracker files", sum(1 for path in files if path.startswith("Trackers/")))
    col4.metric("Cloud data files", sum(1 for path in files if path.startswith("LifeOS_Data/")))

    with st.expander("Vault file list", expanded=False):
        for path in sorted(files.keys()):
            st.write(f"📄 `{path}`")

    with st.expander("Markdown preview", expanded=False):
        selected = st.selectbox("Select file", sorted(files.keys()), key="obsidian_preview_file")
        st.code(files[selected], language="markdown")


def _render_sync_status(config):
    meta = load_sync_meta()
    st.markdown("### Sync status")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Repo", "set" if config.repo else "missing")
    c2.metric("Token", "set" if config.token else "missing")
    c3.metric("Branch", config.branch or "main")
    c4.metric("Vault root", config.root or "/")

    c5, c6, c7 = st.columns(3)
    c5.metric("Last push", meta.get("last_push_at") or "never")
    c6.metric("Last auto push", meta.get("last_auto_push_at") or "never")
    c7.metric("Last pull", meta.get("last_pull_at") or "never")

    if meta.get("last_error"):
        st.warning(f"Last sync error: {meta.get('last_error')}")
    if meta.get("last_pull_error"):
        st.warning(f"Last pull error: {meta.get('last_pull_error')}")

    if config.is_ready:
        st.success(f"Connected to `{config.repo}` on branch `{config.branch}`. Auto-push after LifeOS changes is ON in cloud mode.")
    else:
        st.warning(
            "GitHub sync needs Streamlit secrets: GITHUB_TOKEN and GITHUB_REPO. "
            "Local Markdown export still works without them."
        )
        with st.expander("Secrets example"):
            st.code(
                'GITHUB_TOKEN = "your_token"\nGITHUB_REPO = "Akezhun/life-tracker-vault"\nGITHUB_BRANCH = "main"\nGITHUB_VAULT_ROOT = "LifeOS"',
                language="toml",
            )


def _render_results(title, results):
    ok = results.get("ok", []) or []
    failed = results.get("failed", []) or []
    conflicts = results.get("conflicts", []) or []

    if failed:
        st.error(f"{title}: {len(ok)} ok, {len(conflicts)} conflicts, {len(failed)} failed.")
    elif conflicts:
        st.warning(f"{title}: {len(ok)} ok, {len(conflicts)} conflicts.")
    else:
        st.success(f"{title}: {len(ok)} ok.")

    with st.expander("Details", expanded=bool(failed or conflicts)):
        for msg in ok[:250]:
            st.write(f"✅ {msg}")
        if len(ok) > 250:
            st.caption(f"...and {len(ok) - 250} more ok messages")
        for msg in conflicts:
            st.write(f"⚠️ {msg}")
        for msg in failed:
            st.write(f"❌ {msg}")


def render_obsidian(on_back=None):
    if on_back:
        if st.button("← Back to menu", key="obsidian_back"):
            on_back()
            st.rerun()

    st.title("🪨 Obsidian Vault Sync")
    st.caption("V8.3: cloud-first sync with protected Obsidian Workspace blocks. LifeOS writes structured data; Obsidian can safely hold extra notes.")

    # Loading triggers defaults, including readable tracker Markdown paths.
    journals = load_journals()
    tasks = load_tasks()
    files = build_all_vault_files(journals, tasks)
    config = load_github_config(st.secrets)

    st.markdown("### Vault structure")
    st.code(
        """
LifeOS_Index.md
LifeOS_Data/
  tasks.json
  journals.json
Journals/
  <journal-slug>/
    index.md
    entries/
      <entry-slug>.md
Trackers/
  <tracker-title>--<short-id>.md
Tags/
  <tag>.md
        """.strip(),
        language="text",
    )

    _render_sync_status(config)
    _render_file_preview(files)

    st.divider()
    st.markdown("### Actions")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("📁 Export locally", use_container_width=True):
            output_dir = PROJECT_ROOT / "obsidian_export"
            written = export_files_locally(files, output_dir)
            st.success(f"Exported {len(written)} files to `{output_dir}`.")

    with c2:
        disabled = not config.is_ready
        force_push = st.checkbox("Force push", value=False, help="Use only if you want LifeOS to overwrite remote Markdown conflicts.")
        if st.button("☁️ Manual push all", use_container_width=True, disabled=disabled):
            with st.spinner("Pushing all LifeOS data and Markdown to GitHub Vault..."):
                results = push_all_to_github(force=force_push, reason="manual")
            _render_results("Manual push", results)

    with c3:
        disabled = not config.is_ready
        force_pull = st.checkbox("Force pull journals", value=False, help="Use only if you want vault Markdown to overwrite local journal conflicts.")
        if st.button("⬇️ Pull from Vault", use_container_width=True, disabled=disabled):
            with st.spinner("Pulling LifeOS data and journal Markdown from GitHub Vault..."):
                results = pull_from_github(force=force_pull, pull_markdown_journals=True)
            _render_results("Pull", results)
            if not results.get("failed"):
                st.info("Reloading app state from pulled data...")
                st.rerun()

    st.info(
        "V8.3 sync rule: Journal main sections can be pulled back from Obsidian. "
        "Tracker logic stays one-way from LifeOS to Obsidian. Any text written inside the "
        "protected 'Obsidian Workspace' block is preserved during LifeOS pushes."
    )
    with st.expander("How to edit safely in Obsidian"):
        st.markdown(
            """
- For **Journal entries**, you can edit the main writing sections in Obsidian, then press **Pull from Vault** in LifeOS.
- For **Trackers**, do not edit generated status/history directly. Write your own text inside **Obsidian Workspace**.
- LifeOS preserves everything between `LIFEOS:OBSIDIAN_WORKSPACE_START` and `LIFEOS:OBSIDIAN_WORKSPACE_END`.
- If you edit generated parts of a Markdown file, LifeOS will report a conflict instead of silently overwriting it.
            """.strip()
        )
