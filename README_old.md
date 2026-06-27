# LifeOS V7.2

V7.2 is a visual Journal upgrade over V7.1.

## What changed

- Added Focus Writer for Journal entries.
- Every entry now has a `✍️ Write` button.
- New entries can immediately open in Focus Writer after saving.
- Focus Writer gives a clean, Word-like writing workspace:
  - large text area,
  - hidden metadata panel,
  - section selector for Essay / Project / Learning journals,
  - word and character count,
  - Save and Save & Exit buttons,
  - linked tracker mirror hidden in an expander.
- Existing V7.1 Tracker ↔ Journal linking remains unchanged.
- Tracker notes still stay inside Tracker, but linked entries can show tracker notes/history separately.

## How to run

```bash
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

## Data

Copy your old data files into `data/` if needed:

- `tasks.json`
- `journals.json`
- `journal.json` for legacy migration

