import streamlit as st

from core.storage import load_journals, load_tasks
from core.sync_engine import bootstrap_from_cloud_once
from modules.journal.ui import render_journal
from modules.obsidian.ui import render_obsidian
from modules.schedule.ui import render_schedule
from modules.tracker.status import get_status, sync_pending_events
from modules.tracker.ui import render_tracker

st.set_page_config(
    page_title="LifeOS",
    page_icon="🧠",
    layout="wide",
)

APP_NAME = "LifeOS"
APP_SUBTITLE = "personal operating system"


def set_page(page: str):
    st.session_state["page"] = page


def get_page() -> str:
    if "page" not in st.session_state:
        st.session_state["page"] = "home"
    return st.session_state["page"]


def render_home():
    tasks = load_tasks()
    sync_pending_events(tasks)
    journals = load_journals()

    active_tasks = [task for task in tasks if not task.get("archived")]
    urgent_count = sum(
        1 for task in active_tasks
        if get_status(task) in ["⚫", "🔴", "🟠"]
    )
    tracker_count = len(active_tasks)
    journal_count = sum(len(journal.get("entries", [])) for journal in journals)
    journals_count = len(journals)

    st.markdown(
        """
        <style>
        .lifeos-title {
            text-align: center;
            font-size: 4rem;
            font-weight: 800;
            margin-top: 2rem;
            margin-bottom: 0rem;
        }
        .lifeos-subtitle {
            text-align: center;
            opacity: 0.7;
            font-size: 1.2rem;
            margin-bottom: 2.5rem;
        }
        .lifeos-card {
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-radius: 18px;
            padding: 1.2rem;
            min-height: 130px;
            background: rgba(128, 128, 128, 0.06);
        }
        .lifeos-card h3 {
            margin-top: 0rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(f'<div class="lifeos-title">🧠 {APP_NAME}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="lifeos-subtitle">{APP_SUBTITLE}</div>', unsafe_allow_html=True)

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    metric_col1.metric("Active trackers", tracker_count)
    metric_col2.metric("Needs attention", urgent_count)
    metric_col3.metric("Journals", journals_count)
    metric_col4.metric("Journal entries", journal_count)

    st.divider()
    st.markdown("### Choose module")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown('<div class="lifeos-card"><h3>📋 Life Tracker</h3><p>Tasks, habits, cycles, countdowns, notes and history.</p></div>', unsafe_allow_html=True)
        if st.button("Open Life Tracker", use_container_width=True):
            set_page("tracker")
            st.rerun()

    with col2:
        st.markdown('<div class="lifeos-card"><h3>📖 Journals</h3><p>Diaries, essays, drafts, learning logs and project writing spaces.</p></div>', unsafe_allow_html=True)
        if st.button("Open Journals", use_container_width=True):
            set_page("journal")
            st.rerun()

    with col3:
        st.markdown('<div class="lifeos-card"><h3>🗓 Schedule</h3><p>Future weekly planner connected to trackers.</p></div>', unsafe_allow_html=True)
        if st.button("Open Schedule", use_container_width=True):
            set_page("schedule")
            st.rerun()

    with col4:
        st.markdown('<div class="lifeos-card"><h3>🪨 Obsidian</h3><p>GitHub Vault sync and Markdown export center.</p></div>', unsafe_allow_html=True)
        if st.button("Open Obsidian", use_container_width=True):
            set_page("obsidian")
            st.rerun()

    st.divider()
    with st.expander("⚙️ Settings preview"):
        st.write("Settings will become its own module later: theme, sync rules, notification rules and data export.")


bootstrap_from_cloud_once()

page = get_page()

if page == "home":
    render_home()
elif page == "tracker":
    render_tracker(on_back=lambda: set_page("home"))
elif page == "journal":
    render_journal(on_back=lambda: set_page("home"))
elif page == "schedule":
    render_schedule(on_back=lambda: set_page("home"))
elif page == "obsidian":
    render_obsidian(on_back=lambda: set_page("home"))
else:
    set_page("home")
    st.rerun()
