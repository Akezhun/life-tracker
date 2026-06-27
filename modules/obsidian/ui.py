from pathlib import Path

import streamlit as st

from core.github_vault import GitHubVaultClient, load_github_config
from core.markdown_export import build_vault_files, export_files_locally
from core.storage import PROJECT_ROOT, load_journals, load_tasks


def _render_file_preview(files):
    st.markdown("### Files ready for Obsidian")
    col1, col2, col3 = st.columns(3)
    col1.metric("Markdown files", len(files))
    col2.metric("Journal files", sum(1 for path in files if path.startswith("Journals/")))
    col3.metric("Tracker files", sum(1 for path in files if path.startswith("Trackers/")))

    with st.expander("Vault file list", expanded=False):
        for path in sorted(files.keys()):
            st.write(f"📄 `{path}`")

    with st.expander("Markdown preview", expanded=False):
        selected = st.selectbox("Select file", sorted(files.keys()), key="obsidian_preview_file")
        st.code(files[selected], language="markdown")


def render_obsidian(on_back=None):
    if on_back:
        if st.button("← Back to menu", key="obsidian_back"):
            on_back()
            st.rerun()

    st.title("🪨 Obsidian Vault Sync")
    st.caption("V8 turns LifeOS trackers and journals into Markdown files for your GitHub/Obsidian Vault.")

    journals = load_journals()
    tasks = load_tasks()
    files = build_vault_files(journals, tasks)
    config = load_github_config(st.secrets)

    st.markdown("### Vault structure")
    st.code(
        """
LifeOS_Index.md
Journals/
  <journal-slug>/
    index.md
    entries/
      <entry-slug>.md
Trackers/
  <tracker-id>.md
        """.strip(),
        language="text",
    )

    st.markdown("### GitHub Vault status")
    status_col1, status_col2, status_col3, status_col4 = st.columns(4)
    status_col1.metric("GITHUB_REPO", "set" if config.repo else "missing")
    status_col2.metric("GITHUB_TOKEN", "set" if config.token else "missing")
    status_col3.metric("Branch", config.branch or "main")
    status_col4.metric("Vault root", config.root or "/")

    if not config.is_ready:
        st.warning(
            "GitHub sync needs Streamlit secrets: GITHUB_TOKEN and GITHUB_REPO. "
            "Local Markdown export still works without them."
        )
        with st.expander("Secrets example"):
            st.code(
                'GITHUB_TOKEN = "your_token"\nGITHUB_REPO = "Akezhun/life-tracker-vault"\nGITHUB_BRANCH = "main"\nGITHUB_VAULT_ROOT = ""',
                language="toml",
            )
    else:
        st.success(f"Ready to sync to `{config.repo}` on branch `{config.branch}`.")

    _render_file_preview(files)

    st.divider()
    st.markdown("### Actions")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("📁 Export Markdown locally", use_container_width=True):
            output_dir = PROJECT_ROOT / "obsidian_export"
            written = export_files_locally(files, output_dir)
            st.success(f"Exported {len(written)} files to `{output_dir}`.")
            with st.expander("Written files"):
                for item in written[:150]:
                    st.write(f"✅ `{item}`")
                if len(written) > 150:
                    st.caption(f"...and {len(written) - 150} more")

    with col2:
        sync_disabled = not config.is_ready
        if st.button("☁️ Sync to GitHub Vault", use_container_width=True, disabled=sync_disabled):
            client = GitHubVaultClient(config)
            with st.spinner("Syncing Markdown files to GitHub Vault..."):
                results = client.sync_files(files)
            if results["failed"]:
                st.error(f"Synced {len(results['ok'])} files, failed {len(results['failed'])} files.")
                with st.expander("Failed files", expanded=True):
                    for msg in results["failed"]:
                        st.write(f"❌ {msg}")
            else:
                st.success(f"Synced {len(results['ok'])} files to GitHub Vault.")
            with st.expander("Sync log"):
                for msg in results["ok"][:200]:
                    st.write(f"✅ {msg}")
                if len(results["ok"]) > 200:
                    st.caption(f"...and {len(results['ok']) - 200} more")

    st.info(
        "V8.0 uses manual sync first so you can verify the Markdown output before we make automatic sync aggressive. "
        "Tracker notes/history are mirrored into linked journal entries during export."
    )
