# LifeOS V8

V8 adds Obsidian/GitHub Vault sync on top of V7.2.

## What is included

- Home screen from V7.
- Life Tracker from V6.1.
- Journals system from V7.1.
- Focus Writer from V7.2.
- Obsidian module now generates Markdown files:
  - `LifeOS_Index.md`
  - `Journals/<journal-slug>/index.md`
  - `Journals/<journal-slug>/entries/<entry-slug>.md`
  - `Trackers/<tracker-id>.md`
- Local Markdown export to `obsidian_export/`.
- GitHub Vault sync using Streamlit secrets.

## Secrets

Add these in Streamlit Cloud secrets or local `.streamlit/secrets.toml`:

```toml
GITHUB_TOKEN = "your_token"
GITHUB_REPO = "Akezhun/life-tracker-vault"
GITHUB_BRANCH = "main"
GITHUB_VAULT_ROOT = ""
```

`GITHUB_VAULT_ROOT` is optional. Use it if you want everything inside a subfolder, for example `LifeOS`.

## Run

```cmd
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

## Data migration

To migrate from V7.2, copy these files into the new `data/` folder:

```text
data/tasks.json
data/journals.json
```

Then open the Obsidian module and try local export first.


## V8.0.1 hotfix

Fixed Obsidian page crash when `.streamlit/secrets.toml` is missing. Local Markdown export now works even before GitHub secrets are configured.
