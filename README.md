# LifeOS V8.1

V8.1 is the cloud-first Obsidian/GitHub sync upgrade.

## What changed from V8

- Auto-push after LifeOS changes when Streamlit secrets are set.
- Manual **Push all** button.
- **Pull from Vault** button.
- LifeOS stores cloud data in GitHub Vault:
  - `LifeOS_Data/tasks.json`
  - `LifeOS_Data/journals.json`
- LifeOS can pull Journal Markdown changes back from the vault.
- Trackers remain one-way: LifeOS → Obsidian.
- Added sync metadata:
  - `github_sha`
  - `last_synced_at`
  - `last_local_edit_at`
- Added overwrite protection for Markdown files. If the remote file changed since the last sync, LifeOS skips it unless you enable Force push / Force pull.
- Tracker Markdown is now cleaner:
  - readable filenames: `Trackers/chtenie-knig--ef769709.md`
  - pretty history instead of raw JSON blocks
  - Obsidian wikilinks between linked trackers and journal entries

## Recommended secrets

In Streamlit Cloud secrets:

```toml
GITHUB_TOKEN = "your_token"
GITHUB_REPO = "Akezhun/life-tracker-vault"
GITHUB_BRANCH = "main"
GITHUB_VAULT_ROOT = "LifeOS"
```

`GITHUB_VAULT_ROOT = "LifeOS"` is recommended so all generated files stay inside one folder in the vault.

## Run locally

```cmd
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

Local Markdown export works without secrets. GitHub sync requires either Streamlit Cloud secrets or local `.streamlit/secrets.toml`.

## Data migration

To migrate from V8/V7.2, copy these files into the new `data/` folder:

```text
data/tasks.json
data/journals.json
```

Then open Obsidian module and press **Manual push all** once.

## Safe workflow

- Write/edit in LifeOS.
- LifeOS auto-pushes to GitHub Vault.
- Obsidian Git auto-pulls and shows your vault.
- Journal Markdown can be pulled back into LifeOS.
- Tracker Markdown should be treated as read-only in Obsidian.
