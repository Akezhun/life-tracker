import streamlit as st
import json
from datetime import datetime, timedelta
from uuid import uuid4

DATA_FILE = "tasks.json"

# -----------------------
# LOAD / SAVE
# -----------------------
def load_tasks():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except:
        data = []

    changed = False
    for task in data:
        if "id" not in task:
            task["id"] = str(uuid4())
            changed = True
        if "history" not in task:
            task["history"] = []
            changed = True
        if "notes" not in task:
            task["notes"] = []
            changed = True
        if "archived" not in task:
            task["archived"] = False
            changed = True
        if "done" not in task:
            task["done"] = False
            changed = True

    if changed:
        save_tasks(data)

    return data

def save_tasks(tasks):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)

tasks = load_tasks()

# -----------------------
# TIME
# -----------------------
def now():
    return datetime.now()

def parse(dt):
    return datetime.fromisoformat(dt) if dt else None

def fmt_dt(dt):
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M")

# -----------------------
# HELPERS
# -----------------------
def get_task_by_id(task_id):
    for t in tasks:
        if t["id"] == task_id:
            return t
    return None

def cycle_start_end(freq, t):
    if freq == "daily":
        start = datetime(t.year, t.month, t.day)
        end = start + timedelta(days=1)
        label = "daily"
    elif freq == "weekly":
        start_day = t - timedelta(days=t.weekday())
        start = datetime(start_day.year, start_day.month, start_day.day)
        end = start + timedelta(days=7)
        label = "weekly"
    else:
        start = datetime(t.year, t.month, 1)
        if t.month == 12:
            end = datetime(t.year + 1, 1, 1)
        else:
            end = datetime(t.year, t.month + 1, 1)
        label = "monthly"
    return label, start, end

def previous_cycle_bounds(freq, current_start):
    if freq == "daily":
        prev_start = current_start - timedelta(days=1)
        prev_end = current_start
    elif freq == "weekly":
        prev_start = current_start - timedelta(days=7)
        prev_end = current_start
    else:
        prev_end = current_start
        if current_start.month == 1:
            prev_start = datetime(current_start.year - 1, 12, 1)
        else:
            prev_start = datetime(current_start.year, current_start.month - 1, 1)
    return prev_start, prev_end

def log(task, action, details=None):
    task.setdefault("history", []).append({
        "action": action,
        "time": now().isoformat(),
        "details": details or {}
    })

# -----------------------
# SYNC FAILURES INTO HISTORY
# -----------------------
def sync_pending_events():
    t = now()
    changed = False

    for task in tasks:
        # archived/manual frozen tasks do not keep progressing
        if task.get("archived") and not task.get("done"):
            continue

        if task["type"] == "deadline":
            deadline = parse(task.get("deadline"))
            if deadline and not task.get("done") and t > deadline:
                marker = deadline.isoformat()
                if task.get("deadline_fail_logged_for") != marker:
                    log(task, "fail", {
                        "type": "deadline",
                        "deadline": deadline.isoformat(),
                        "overdue_at": t.isoformat()
                    })
                    task["deadline_fail_logged_for"] = marker
                    changed = True

        elif task["type"] == "cycle":
            cycle = task.get("cycle", "weekly")
            _, current_start, _ = cycle_start_end(cycle, t)
            current_start_iso = current_start.isoformat()

            if task.get("cycle_last_checked_start") != current_start_iso:
                prev_start, prev_end = previous_cycle_bounds(cycle, current_start)
                last_done = parse(task.get("last_done"))

                success = (
                    last_done is not None
                    and prev_start <= last_done < prev_end
                )

                if not success:
                    log(task, "fail", {
                        "type": "cycle",
                        "cycle": cycle,
                        "failed_period_start": prev_start.isoformat(),
                        "failed_period_end": prev_end.isoformat(),
                        "checked_at": t.isoformat()
                    })

                task["cycle_last_checked_start"] = current_start_iso
                changed = True

        elif task["type"] == "countdown":
            last = parse(task.get("last_done"))
            if last:
                days = int(task.get("days", 3))
                target = last + timedelta(days=days)
                marker = target.isoformat()

                if t > target and task.get("countdown_fail_logged_for") != marker:
                    log(task, "fail", {
                        "type": "countdown",
                        "days": days,
                        "target": target.isoformat(),
                        "overdue_at": t.isoformat()
                    })
                    task["countdown_fail_logged_for"] = marker
                    changed = True

    if changed:
        save_tasks(tasks)

sync_pending_events()

# -----------------------
# STATUS
# -----------------------
def get_status(task, archived=False):
    t = now()

    if archived:
        if task.get("done"):
            return "🟢"
        return "⚪"

    if task["type"] == "grey":
        if task.get("done"):
            return "🟢"
        return "⚪"

    if task["type"] == "deadline":
        if task.get("done"):
            return "🟢"

        deadline = parse(task.get("deadline"))
        if not deadline:
            return "🟡"

        diff = (deadline - t).total_seconds()

        if diff < 0:
            return "⚫"
        if diff < 3600:
            return "🔴"
        if diff < 86400:
            return "🟠"
        return "🟢"

    if task["type"] == "cycle":
        last = parse(task.get("last_done"))
        cycle = task.get("cycle", "weekly")
        _, cycle_start, cycle_end = cycle_start_end(cycle, t)

        if last and cycle_start <= last < cycle_end:
            return "🟢"

        remaining = (cycle_end - t).total_seconds()
        total = (cycle_end - cycle_start).total_seconds()
        if total <= 0:
            return "🟢"

        ratio = remaining / total

        if ratio > 0.66:
            return "🟢"
        if ratio > 0.33:
            return "🟠"
        return "🔴"

    if task["type"] == "countdown":
        last = parse(task.get("last_done"))
        if not last:
            return "🔴"

        days = int(task.get("days", 3))
        target = last + timedelta(days=days)
        diff = (target - t).total_seconds()

        if diff < 0:
            return "⚫"
        if diff < 3600:
            return "🔴"
        if diff < 86400:
            return "🟠"
        return "🟢"

    return "🟡"

# -----------------------
# INFO BLOCK
# -----------------------
def task_info(task):
    t = now()

    if task["type"] == "grey":
        if task.get("done"):
            done_time = parse(task.get("last_done"))
            if done_time:
                return f"✅ Completed at {fmt_dt(done_time)} | grey task"
            return "✅ Completed | grey task"
        return "⚪ Grey task | no deadline"

    if task["type"] == "deadline":
        deadline = parse(task.get("deadline"))
        if not deadline:
            return "📅 Deadline: not set"

        if task.get("done"):
            done_time = parse(task.get("last_done"))
            if done_time:
                return f"✅ Completed at {fmt_dt(done_time)} | 📅 Deadline was {fmt_dt(deadline)}"
            return f"✅ Completed | 📅 Deadline was {fmt_dt(deadline)}"

        delta = deadline - t
        days_left = delta.days
        hours_left = delta.seconds // 3600

        if delta.total_seconds() >= 0:
            return f"📅 Deadline: {fmt_dt(deadline)} | ⏳ {days_left} days {hours_left} hours left"
        return f"📅 Deadline: {fmt_dt(deadline)} | ⚫ overdue"

    if task["type"] == "cycle":
        cycle = task.get("cycle", "weekly")
        label, cycle_start, cycle_end = cycle_start_end(cycle, t)
        last = parse(task.get("last_done"))

        if last and cycle_start <= last < cycle_end:
            return f"✅ bro, chill — until {fmt_dt(cycle_end)}"

        left = cycle_end - t
        return f"🔁 Cycle: {label} | next reset: {fmt_dt(cycle_end)} | ⏳ {left.days} days {left.seconds // 3600} hours left"

    if task["type"] == "countdown":
        days = int(task.get("days", 3))
        last = parse(task.get("last_done"))

        if not last:
            return f"⏳ Every {days} days"

        target = last + timedelta(days=days)
        if now() < target:
            left = target - now()
            return f"⏳ Every {days} days | next in {left.days} days {left.seconds // 3600} hours"
        return f"⚫ Every {days} days | overdue"

    return ""

# -----------------------
# SORT
# -----------------------
priority_map = {"high": 3, "mid": 2, "low": 1}
status_map = {"🟢": 4, "🟠": 3, "🔴": 2, "⚫": 1, "⚪": 0}

def urgency_score(task):
    t = now()

    if task["type"] == "grey":
        return 0

    if task["type"] == "deadline":
        if task.get("done"):
            return 4

        deadline = parse(task.get("deadline"))
        if not deadline:
            return 0

        diff = (deadline - t).total_seconds()
        if diff < 0:
            return 1
        if diff < 3600:
            return 4
        if diff < 86400:
            return 3
        return 2

    if task["type"] == "cycle":
        cycle = task.get("cycle", "weekly")
        _, cycle_start, cycle_end = cycle_start_end(cycle, t)
        last = parse(task.get("last_done"))

        if last and cycle_start <= last < cycle_end:
            return 4  # done in current cycle, keep visually chill

        remaining = (cycle_end - t).total_seconds()
        total = (cycle_end - cycle_start).total_seconds()
        if total <= 0:
            return 2

        ratio = remaining / total
        if ratio > 0.66:
            return 2
        if ratio > 0.33:
            return 3
        return 4

    if task["type"] == "countdown":
        last = parse(task.get("last_done"))
        if not last:
            return 2

        days = int(task.get("days", 3))
        target = last + timedelta(days=days)
        diff = (target - t).total_seconds()

        if diff < 0:
            return 1
        if diff < 3600:
            return 4
        if diff < 86400:
            return 3
        return 2

    return 0

def sort_tasks(list_):
    return sorted(
        list_,
        key=lambda x: (
            urgency_score(x),
            priority_map.get(x.get("priority", "low"), 1)
        ),
        reverse=True
    )

# -----------------------
# ACTIONS
# -----------------------
def mark_done(i):
    task = tasks[i]
    t = now()

    task["last_done"] = t.isoformat()

    details = {
        "time": t.isoformat(),
        "type": task["type"]
    }

    if task["type"] == "grey":
        task["done"] = True
        task["archived"] = True

    elif task["type"] == "deadline":
        task["done"] = True
        task["archived"] = True
        deadline = parse(task.get("deadline"))
        if deadline:
            details["deadline"] = deadline.isoformat()
            details["days_left"] = (deadline - t).days

    elif task["type"] == "cycle":
        cycle = task.get("cycle", "weekly")
        label, cycle_start, cycle_end = cycle_start_end(cycle, t)
        details["cycle"] = label
        details["cycle_start"] = cycle_start.isoformat()
        details["cycle_end"] = cycle_end.isoformat()

    elif task["type"] == "countdown":
        days = int(task.get("days", 3))
        next_due = t + timedelta(days=days)
        details["days"] = days
        details["next_due"] = next_due.isoformat()

    log(task, "done", details)
    save_tasks(tasks)

def archive_task(i):
    task = tasks[i]
    task["archived"] = True
    log(task, "archive", {"time": now().isoformat()})
    save_tasks(tasks)

def restore_task(i):
    task = tasks[i]
    task["archived"] = False
    log(task, "restore", {"time": now().isoformat()})
    save_tasks(tasks)

def delete_task(i):
    tasks.pop(i)
    save_tasks(tasks)

def edit_task(task, new_data):
    before = {
        "priority": task.get("priority"),
        "deadline": task.get("deadline"),
        "cycle": task.get("cycle"),
        "days": task.get("days")
    }

    for k, v in new_data.items():
        if v is not None:
            task[k] = v

    after = {
        "priority": task.get("priority"),
        "deadline": task.get("deadline"),
        "cycle": task.get("cycle"),
        "days": task.get("days")
    }

    task["edited_at"] = now().isoformat()
    log(task, "edit", {"before": before, "after": after, "time": now().isoformat()})
    save_tasks(tasks)

def add_note(task, text):
    if not text:
        return
    task.setdefault("notes", []).append({
        "time": now().isoformat(),
        "text": text
    })
    log(task, "note", {"text": text, "time": now().isoformat()})
    save_tasks(tasks)

# -----------------------
# SESSION STATE
# -----------------------
if "open_notes" not in st.session_state:
    st.session_state.open_notes = {}

if "open_history" not in st.session_state:
    st.session_state.open_history = {}

def toggle_state(bucket, task_id):
    current = st.session_state[bucket].get(task_id, False)
    st.session_state[bucket][task_id] = not current

# -----------------------
# UI
# -----------------------
st.title("🧠 Life Tracker V4")

view = st.sidebar.radio("View", ["Active", "Archive"])

active_tasks = [t for t in tasks if not t.get("archived")]
archived_tasks = [t for t in tasks if t.get("archived")]

# -----------------------
# ADD TASK
# -----------------------
if view == "Active":
    st.subheader("➕ Add task")

    with st.form("add"):
        title = st.text_input("Title")
        ttype = st.selectbox("Type", ["deadline", "cycle", "countdown", "grey"])
        priority = st.selectbox("Priority", ["high", "mid", "low"])

        deadline = None
        cycle = None
        days = None

        if ttype == "deadline":
            deadline = st.datetime_input("Deadline").isoformat()

        if ttype == "cycle":
            cycle = st.selectbox("Cycle", ["daily", "weekly", "monthly"])

        if ttype == "countdown":
            days = st.number_input("Days", 1, 365, 3)

        if st.form_submit_button("Add"):
            new_task = {
                "id": str(uuid4()),
                "title": title,
                "type": ttype,
                "priority": priority,
                "deadline": deadline,
                "cycle": cycle,
                "days": days,
                "last_done": None,
                "archived": False,
                "done": False,
                "history": [],
                "notes": []
            }

            if ttype == "grey":
                new_task["deadline"] = None
                new_task["cycle"] = None
                new_task["days"] = None

            log(new_task, "create", {"time": now().isoformat(), "type": ttype})
            tasks.append(new_task)
            save_tasks(tasks)
            st.rerun()

# -----------------------
# ACTIVE VIEW
# -----------------------
if view == "Active":
    st.subheader("📋 Active")
    active_tasks = sort_tasks(active_tasks)

    for idx, task in enumerate(active_tasks):
        task_id = task["id"]
        status = get_status(task, archived=False)

        st.markdown(f"### {status} {task['title']} ({task['type']})")
        st.write(task_info(task))

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if st.button("✔ Done", key=f"d_{task_id}"):
                mark_done(tasks.index(task))
                st.rerun()

        with col2:
            if st.button("📦 Archive", key=f"a_{task_id}"):
                archive_task(tasks.index(task))
                st.rerun()

        with col3:
            if st.button("🗑 Delete", key=f"x_{task_id}"):
                delete_task(tasks.index(task))
                st.rerun()

        with col4:
            if st.button("✏ Edit", key=f"e_{task_id}"):
                st.session_state[f"edit_{task_id}"] = not st.session_state.get(f"edit_{task_id}", False)

        if st.session_state.get(f"edit_{task_id}", False):
            with st.expander("Edit task", expanded=True):
                new_priority = st.selectbox(
                    "Priority",
                    ["high", "mid", "low"],
                    index=["high", "mid", "low"].index(task["priority"]),
                    key=f"ep_{task_id}"
                )

                new_deadline = task.get("deadline")
                new_cycle = task.get("cycle")
                new_days = task.get("days")

                if task["type"] == "deadline":
                    new_deadline = st.datetime_input(
                        "Deadline",
                        value=parse(task["deadline"]) if task.get("deadline") else now(),
                        key=f"ed_{task_id}"
                    ).isoformat()

                if task["type"] == "cycle":
                    new_cycle = st.selectbox(
                        "Cycle",
                        ["daily", "weekly", "monthly"],
                        index=["daily", "weekly", "monthly"].index(task.get("cycle", "weekly")),
                        key=f"ec_{task_id}"
                    )

                if task["type"] == "countdown":
                    new_days = st.number_input(
                        "Days",
                        1, 365,
                        value=int(task.get("days", 3)),
                        key=f"ecd_{task_id}"
                    )

                if task["type"] == "grey":
                    st.caption("Grey task: only priority can be changed here.")

                if st.button("Save changes", key=f"save_{task_id}"):
                    edit_task(task, {
                        "priority": new_priority,
                        "deadline": new_deadline,
                        "cycle": new_cycle,
                        "days": new_days
                    })
                    st.session_state[f"edit_{task_id}"] = False
                    st.rerun()

        if st.button("📝 Notes", key=f"n_{task_id}"):
            toggle_state("open_notes", task_id)

        if st.session_state.open_notes.get(task_id, False):
            note = st.text_input("Add note", key=f"nt_{task_id}")
            if st.button("Save note", key=f"sn_{task_id}"):
                add_note(task, note)
                st.rerun()

            if task.get("notes"):
                for n in task["notes"]:
                    st.write(f"📝 {n['text']}")

        if st.button("📜 History", key=f"h_{task_id}"):
            toggle_state("open_history", task_id)

        if st.session_state.open_history.get(task_id, False):
            st.markdown("#### History")
            if not task.get("history"):
                st.write("No history yet")
            else:
                for h in task["history"]:
                    dt = h.get("time", "")
                    action = h.get("action", "")
                    details = h.get("details", {})
                    st.write(f"• {action} → {dt}")
                    if details:
                        st.caption(json.dumps(details, ensure_ascii=False))

        st.divider()

# -----------------------
# ARCHIVE VIEW
# -----------------------
if view == "Archive":
    st.subheader("📦 Archive")

    for idx, task in enumerate(archived_tasks):
        task_id = task["id"]
        status = get_status(task, archived=True)

        st.markdown(f"### {status} {task['title']} ({task['type']})")
        st.write(task_info(task))

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("↩ Restore", key=f"r_{task_id}"):
                restore_task(tasks.index(task))
                st.rerun()

        with col2:
            if st.button("🗑 Delete", key=f"dx_{task_id}"):
                delete_task(tasks.index(task))
                st.rerun()

        with col3:
            if st.button("📜 History", key=f"ha_{task_id}"):
                toggle_state("open_history", task_id)

        if st.session_state.open_history.get(task_id, False):
            st.markdown("#### History")
            if not task.get("history"):
                st.write("No history yet")
            else:
                for h in task["history"]:
                    dt = h.get("time", "")
                    action = h.get("action", "")
                    details = h.get("details", {})
                    st.write(f"• {action} → {dt}")
                    if details:
                        st.caption(json.dumps(details, ensure_ascii=False))

        st.divider()

# -----------------------
# REPORT
# -----------------------
st.subheader("📊 Overview")

c = {
    "🟢": 0,
    "🟡": 0,
    "🟠": 0,
    "🔴": 0,
    "⚫": 0,
    "⚪": 0  # на случай если ты добавишь этот статус
}

for t in tasks:
    status = get_status(t, archived=t.get("archived", False))
    c[status] = c.get(status, 0) + 1

st.write(c)