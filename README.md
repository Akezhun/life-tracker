# LifeOS V8.3 — Obsidian-safe sync

V8.3 fixes the biggest Obsidian workflow risk: LifeOS should not erase text that you write directly in Obsidian.

## What V8.3 does

- Keeps GitHub Vault as the cloud database:
  - `LifeOS_Data/tasks.json`
  - `LifeOS_Data/journals.json`
- Pushes generated Markdown to Obsidian Vault.
- Pulls Journal Markdown back into LifeOS.
- Keeps Tracker logic one-way: LifeOS → Obsidian.
- Adds protected Obsidian sections to generated Markdown files:

```md
## Obsidian Workspace

<!-- LIFEOS:OBSIDIAN_WORKSPACE_START -->
Write here. LifeOS will preserve this block.
<!-- LIFEOS:OBSIDIAN_WORKSPACE_END -->
```

LifeOS preserves everything inside this block during future pushes.

## Safe editing rules

### Journals
You can edit the main Journal sections in Obsidian, then open LifeOS → Obsidian → Pull from Vault.

### Trackers
Do not edit generated tracker status/history as the source of truth. Use the Obsidian Workspace block for your own Obsidian notes.

### Conflicts
If you edit generated parts of a Markdown file in Obsidian, LifeOS should not silently overwrite it. It will report a conflict unless you force push.

## Tag pages
V8.3 also generates Obsidian tag hub pages:

```text
Tags/<tag>.md
```

Entries and trackers with tags link to those pages.

## Install

Replace the code in your Streamlit app repo (`life-tracker`) with this folder, commit and push.

Make sure Streamlit Cloud secrets include:

```toml
GITHUB_TOKEN = "..."
GITHUB_REPO = "Akezhun/life-tracker-vault"
GITHUB_BRANCH = "main"
GITHUB_VAULT_ROOT = "LifeOS"
```
