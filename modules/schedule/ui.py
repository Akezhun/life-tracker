import streamlit as st


def render_schedule(on_back=None):
    if on_back:
        if st.button("← Back to menu", key="schedule_back"):
            on_back()
            st.rerun()

    st.title("🗓 Schedule")
    st.caption("Schedule will come after Obsidian sync. It will use existing trackers and journal entries as schedulable tokens.")

    st.info("Planned for V9: weekly grid, tracker tokens, journal writing blocks, drag-like planning, and time allocation.")
